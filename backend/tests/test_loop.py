"""Integrationstest der Regelschleife mit Simulatoren — Entladegrenze (§5.1) und Fail-Safe E1 (§7)."""

import asyncio
from datetime import datetime, timedelta

from leo_ems.config import RegelConfig
from leo_ems.core.loop import ControlLoop
from leo_ems.devices.e3dc import E3dcSimulator
from leo_ems.devices.goe import GoeSimulator
from leo_ems.devices.vaillant import VaillantSimulator
from leo_ems.safety import SafetyGuard
from leo_ems.store import Store

T0 = datetime(2026, 7, 15, 12, 0, 0)


def build(tmp_path, **cfg_kw):
    # Diese Tests prüfen den AKTIV-Betrieb; der Beobachtungsmodus (read_only,
    # Default True) hat eigene Tests in test_observation.py.
    cfg = RegelConfig(read_only=False, **cfg_kw)
    store = Store(tmp_path / "test.db")
    guard = SafetyGuard(cfg)
    # 2900 W Überschuss (Netz -3000, residual 100), Batterie weder lädt noch entlädt
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=0, soc_pct=60)
    goe = GoeSimulator(connected=True, power_w=0)
    loop = ControlLoop(cfg, guard, store, {"e3dc": e3dc, "goe": goe})
    return loop, e3dc, goe, guard


def test_laden_und_entladegrenze(tmp_path):
    """Nach der Einschaltverzögerung lädt die Wallbox und die Entladegrenze steht (§5.1)."""
    loop, e3dc, goe, guard = build(tmp_path)

    asyncio.run(loop.tick(T0))                       # Einschaltverzögerung startet
    assert not goe.charging

    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))   # Ladung beginnt
    assert goe.charging
    assert ("charging", True) in goe.commands
    # Die Anlage speist ein, es gibt nichts zu decken: die Grenze steht auf dem
    # reinen Puffer — Kopffreiheit für einen Lastsprung im nächsten Tick.
    assert e3dc.entladelimit_w == 200
    assert guard.active("e3dc_entladesperre", T0 + timedelta(seconds=60))


def test_entladegrenze_folgt_dem_netzbezug(tmp_path):
    """Der Kern der Änderung: Netzbezug beim Laden gibt die Batterie frei — genau so weit.

    Leos Fehlerbild nach v0.8.0: Auto lädt, eine Last kommt dazu, und weil die
    Batterie hart gesperrt war, deckte zwingend das Netz.
    """
    loop, e3dc, goe, guard = build(tmp_path)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert goe.charging

    e3dc.p_netz_w = 800                              # Backofen an → 800 W aus dem Netz
    asyncio.run(loop.tick(T0 + timedelta(seconds=70)))
    assert e3dc.entladelimit_w == 1000               # 800 Bedarf + 200 Puffer

    # Die Batterie deckt jetzt — der Bedarf ist derselbe, die Grenze bleibt stehen
    # (kein Zurückfallen auf 0, sonst begänne der Netzbezug von vorn).
    e3dc.p_netz_w, e3dc.p_batterie_w = 0.0, -800
    asyncio.run(loop.tick(T0 + timedelta(seconds=80)))
    assert e3dc.entladelimit_w == 1000

    # Last weg → die Grenze sinkt gedämpft (batt_dyn_abbau_w = 500 W je Tick)
    e3dc.p_batterie_w = 0.0
    asyncio.run(loop.tick(T0 + timedelta(seconds=90)))
    assert e3dc.entladelimit_w == 500
    asyncio.run(loop.tick(T0 + timedelta(seconds=100)))
    assert e3dc.entladelimit_w == 200


def test_entladegrenze_schreibt_nicht_bei_jedem_zittern(tmp_path):
    """set_power_limits ist ein persistenter Schreibzugriff — kleine Deltas werden gedrosselt."""
    loop, e3dc, goe, guard = build(tmp_path)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))       # Ladung läuft

    e3dc.p_netz_w = 800
    asyncio.run(loop.tick(T0 + timedelta(seconds=70)))
    assert e3dc.entladelimit_w == 1000
    vorher = len([c for c in e3dc.commands if c[0] == "entladelimit"])

    e3dc.p_netz_w = 850                              # +50 W → unter der Schreibschwelle
    asyncio.run(loop.tick(T0 + timedelta(seconds=80)))
    assert len([c for c in e3dc.commands if c[0] == "entladelimit"]) == vorher
    assert e3dc.entladelimit_w == 1000


def test_schnell_modus_sperrt_die_batterie_hart(tmp_path):
    """Modus Schnell zieht bewusst aus dem Netz — die Hausbatterie bleibt außen vor."""
    loop, e3dc, goe, guard = build(tmp_path)
    loop.mode = "Schnell"
    e3dc.p_netz_w = 5000                             # lädt mit voller Leistung aus dem Netz
    asyncio.run(loop.tick(T0))
    assert goe.charging
    assert e3dc.entladelimit_w == 0                  # harte Sperre trotz Netzbezug
    assert loop.status()["entladelimit_art"] == "hart"


def test_schnell_mit_batterie_gibt_die_grenze_frei(tmp_path):
    """Issue #11, erster Teil: derselbe Modus, ein Schalter — jetzt darf die
    Hausbatterie mitspeisen, der Netzbezug bleibt zusätzlich erlaubt."""
    loop, e3dc, goe, guard = build(tmp_path, schnell_batt_nutzen=True)
    loop.mode = "Schnell"
    e3dc.p_netz_w = 5000
    asyncio.run(loop.tick(T0))
    assert goe.charging
    assert e3dc.entladelimit_w == 5000                       # batt_schnell_max_w
    assert loop.status()["entladelimit_art"] == "freigabe"


def test_pv_batterie_regelt_gegen_pv_plus_batterie(tmp_path):
    """Issue #11, zweiter Teil: „Schnellladen ohne Netzbezug".

    Der Prüfstein ist das Budget. In Nur-PV wird die Batterieentladung vom
    Überschuss abgezogen (sonst speiste sich die Ladung selbst aus der Batterie);
    in PV+Batterie ist genau diese Entladung das Budget.
    """
    loop, e3dc, goe, guard = build(tmp_path)
    loop.mode = "PV+Batterie"
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert goe.charging

    # Auto zieht 4,0 kW: 2,0 kW aus der PV, 2,0 kW aus der Batterie, Netz auf 0
    goe._power_w, e3dc.p_netz_w, e3dc.p_batterie_w = 4000, 0.0, -2000
    for i in range(7, 10):                                   # Glättungsfenster füllen
        asyncio.run(loop.tick(T0 + timedelta(seconds=i * 10)))

    st = loop.status()
    assert st["ev_budget_w"] == 3900                         # 4000 − 0 − 100
    assert st["ueberschuss_w"] == 1900                       # ... abzüglich der Entladung
    assert st["ev_budget_w"] > st["verteilbar_w"]
    assert e3dc.entladelimit_w == 5000
    assert st["entladelimit_art"] == "freigabe"


def test_pv_batterie_faellt_an_der_reserve_zurueck(tmp_path):
    """`soc_reserve_pct` ist der harte Boden — davor lief der Parameter ins Leere."""
    loop, e3dc, goe, guard = build(tmp_path, soc_reserve_pct=15, priority_soc_pct=0)
    loop.mode = "PV+Batterie"
    e3dc.soc_pct = 15
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert goe.charging                                      # PV trägt weiter
    st = loop.status()
    assert st["entladelimit_art"] != "freigabe"
    assert st["ev_budget_w"] == st["verteilbar_w"]           # Budget ohne Batterie
    assert "Batterie-Reserve erreicht" in st["grund"]


def test_reserve_hysterese_verhindert_flattern(tmp_path):
    """Am Vorschau-Server aufgefallen: die Reserve-Schwelle stand an zwei Stellen,
    und die Schleife ohne Hysterese entschied zuerst — die in `batt_limit` sah
    die Unterschreitung nie und lief ins Leere.

    Die Hysterese gehört hierher, weil an `batt_verfuegbar` nicht nur die
    Entladegrenze hängt, sondern auch das Ladebudget: ohne sie springt an der
    Reserve der Ladestrom mit.
    """
    loop, e3dc, goe, guard = build(tmp_path, soc_reserve_pct=15, priority_soc_pct=0)
    loop.mode = "PV+Batterie"
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert loop.status()["entladelimit_art"] == "freigabe"

    e3dc.soc_pct = 14                                        # unter die Reserve
    asyncio.run(loop.tick(T0 + timedelta(seconds=70)))
    assert loop.status()["entladelimit_art"] != "freigabe"

    e3dc.soc_pct = 16                                        # +1 reicht nicht
    asyncio.run(loop.tick(T0 + timedelta(seconds=80)))
    assert loop.status()["entladelimit_art"] != "freigabe"

    e3dc.soc_pct = 17                                        # +2 (BATT_RESERVE_HYSTERESE)
    asyncio.run(loop.tick(T0 + timedelta(seconds=90)))
    assert loop.status()["entladelimit_art"] == "freigabe"


def test_waermepumpe_sieht_in_pv_batterie_nur_den_pv_anteil(tmp_path):
    """Die Freigabe gilt dem Auto. Reichte man sie an den Warmwasser-Boost
    weiter, liefe die Hausbatterie über die WP leer — derselbe Ratchet, den der
    Entladungs-Abzug in v0.9.0 verhindert hat."""
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    # Netz 0, Batterie liefert 6 kW, Wallbox zieht 6 kW → PV-Überschuss ist negativ
    e3dc = E3dcSimulator(p_netz_w=0.0, p_batterie_w=-6000, soc_pct=80, p_pv_w=0)
    goe = GoeSimulator(connected=True, power_w=6000)
    wp = VaillantSimulator()
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe, "vaillant": wp})
    loop.mode = "PV+Batterie"

    asyncio.run(loop.tick(T0))
    st = loop.status()
    assert st["ev_budget_w"] == 5900                          # 6000 − 0 − 100
    assert st["wp"]["frei_w"] < 0                             # WP sieht nichts davon
    assert loop.heatpump.ww_boost is False


def test_entladegrenze_faellt_am_ladeende_weg(tmp_path):
    """Ohne Ladung gehört die Batterie wieder dem Haus (Lease wird freigegeben)."""
    loop, e3dc, goe, guard = build(tmp_path)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert e3dc.entladelimit_w is not None

    goe._connected = False
    t = T0 + timedelta(seconds=70)
    asyncio.run(loop.tick(t))
    assert ("entladelimit", None) in e3dc.commands
    assert not guard.active("e3dc_entladesperre", t)


def test_entladegrenze_haelt_soc_untergrenze_ein(tmp_path):
    """Unter dem Vorrang-SoC bleibt es hart: die Hausbatterie ist nicht fürs Auto da."""
    loop, e3dc, goe, guard = build(tmp_path)
    e3dc.soc_pct = 20                                # < priority_soc_pct (25 %)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert goe.charging

    e3dc.p_netz_w = 800                              # Netzbezug — trotzdem keine Freigabe
    asyncio.run(loop.tick(T0 + timedelta(seconds=70)))
    assert e3dc.entladelimit_w == 0
    assert loop.status()["entladelimit_art"] == "hart"


def test_failsafe_e1_schaltet_ab(tmp_path):
    """E3DC nicht erreichbar → Ladung wird gestoppt (Spec §7/E1)."""
    loop, e3dc, goe, guard = build(tmp_path)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert goe.charging

    e3dc.available = False                           # Ausfall provozieren
    asyncio.run(loop.tick(T0 + timedelta(seconds=70)))   # 10 s ohne Daten → Grace, noch keine Änderung
    assert goe.charging is True
    asyncio.run(loop.tick(T0 + timedelta(seconds=130)))  # >60 s ohne Daten → abschalten
    assert goe.charging is False
    assert loop.status()["state"] == "abgeschaltet"


def test_status_enthaelt_energieverteilung_und_phaseninfo(tmp_path):
    """Dashboard-Daten (REQ-051): Leistungsbilanz + Entprellungs-Transparenz im Status."""
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=-300, soc_pct=60, p_pv_w=5000)
    goe = GoeSimulator(connected=True, power_w=0)
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe})
    asyncio.run(loop.tick(T0))

    st = loop.status()
    assert st["p_pv_w"] == 5000
    # Haus = PV + Netz − Batterieladung − Wallbox = 5000 − 3000 + 300 − 0
    assert st["p_haus_w"] == 2300
    pi = st["phasen_info"]
    assert pi["phasen"] == 1 and "grund" in pi
    assert {"entprellung_aktiv", "umschaltsperre_aktiv", "umschaltsperre_rest_s"} <= pi.keys()


def test_lease_laeuft_ohne_erneuerung_aus(tmp_path):
    """ADR-005: Wird nach gesetzter Grenze nicht mehr getickt, läuft sie per TTL aus (T4-Kern)."""
    loop, e3dc, goe, guard = build(tmp_path)
    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert guard.active("e3dc_entladesperre", T0 + timedelta(seconds=60))
    # EMS "stirbt" → keine Ticks mehr → Lease abgelaufen nach TTL (900 s)
    assert not guard.active("e3dc_entladesperre", T0 + timedelta(seconds=60 + 901))


def test_waermepumpe_bekommt_ueberschuss_nach_wallbox(tmp_path):
    """Vorrang Auto (Leo, 2026-07-25): die WP sieht nur den Rest nach der Ladezuteilung."""
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    # 14,9 kW Überschuss: genug für 16 A 3p (11,0 kW) UND danach noch für die WP
    e3dc = E3dcSimulator(p_netz_w=-15000, p_batterie_w=0, soc_pct=60, p_pv_w=16000)
    goe = GoeSimulator(connected=True, power_w=0)
    wp = VaillantSimulator()
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe, "vaillant": wp})

    asyncio.run(loop.tick(T0))
    st = loop.status()
    assert st["wp"]["verbunden"] is True
    assert st["wp"]["warmwasser"]["ist_c"] == 40.0
    assert st["wp"]["heizkreis"]["vorlauf_c"] == 27.5
    # Noch lädt niemand (Einschalt-Hysterese) → die WP sieht den vollen Überschuss
    assert st["wp"]["frei_w"] == st["ueberschuss_w"]

    # Nach der Bedingungszeit startet der Warmwasser-Boost und geht an die Anlage
    for i in range(1, 70):
        asyncio.run(loop.tick(T0 + timedelta(seconds=i * 10)))
    assert loop.heatpump.ww_boost is True
    assert ("ww_soll", 57.0) in wp.commands

    # Jetzt lädt das Auto — die WP bekommt nur noch, was danach übrig ist
    st = loop.status()
    assert st["laedt"] is True
    assert st["wp"]["frei_w"] < st["ueberschuss_w"]


def test_auto_startet_auch_wenn_die_waermepumpe_schon_laeuft(tmp_path):
    """Issue #6: „Wärmepumpe läuft auf Warmwasser, Auto wird nicht geladen."

    Die WP hat keinen Leistungsmesswert — ihr Verbrauch steckt im Hausverbrauch
    und drückt den gemessenen Überschuss. Entschied die Wallbox gegen diesen
    gedrückten Wert, kam sie nicht mehr über ihre Einschaltschwelle: die
    Verteilung entschied faktisch, wer zuerst angelaufen war.
    """
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    # 3,0 kW Überschuss, noch kein Auto — genug für den Warmwasser-Boost
    e3dc = E3dcSimulator(p_netz_w=-3100, p_batterie_w=0, soc_pct=60, p_pv_w=4000)
    goe = GoeSimulator(connected=False, power_w=0)
    wp = VaillantSimulator()
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe, "vaillant": wp})

    for i in range(70):                                  # ~11 min → Bedingungszeit voll
        asyncio.run(loop.tick(T0 + timedelta(seconds=i * 10)))
    assert loop.heatpump.ww_boost is True

    # Die Anlage läuft jetzt wirklich und zieht ~2 kW: der gemessene Überschuss
    # bricht auf 1,0 kW ein — unter der Einschaltschwelle der Wallbox (1,38 kW).
    # Genau in dieser Lage steckt Leo das Auto an.
    wp.werte["ww_sonderfunktion"] = "Zwangsladung"
    e3dc.p_netz_w = -1100
    goe._connected = True

    t = T0 + timedelta(seconds=700)
    for i in range(12):                                  # 2 min (Einschalt-Hysterese 60 s)
        asyncio.run(loop.tick(t + timedelta(seconds=i * 10)))

    st = loop.status()
    assert st["ueberschuss_w"] == 1000                   # gemessen zu wenig …
    assert st["wp_boost_w"] == 2000                      # … weil die WP 2 kW davon hält
    assert st["verteilbar_w"] == 3000                    # zurückgerechnet reicht es
    assert st["laedt"] is True and st["phasen"] == 1
    assert st["ev_zuteilung_w"] == 13 * 230              # floor(3000/230) = 13 A

    # Und die WP zieht sich zurück, statt die Wallbox ins Netz zu drücken
    t += timedelta(seconds=120)
    for i in range(36):                                  # 6 min > 5 min Bedingungszeit
        asyncio.run(loop.tick(t + timedelta(seconds=i * 10)))
    assert loop.heatpump.ww_boost is False
    assert ("ww_soll", 45.0) in wp.commands


def test_waermepumpe_im_beobachtungsmodus_stumm(tmp_path):
    """read_only: die Entscheidung steht im Status, aber nichts geht an die Cloud."""
    cfg = RegelConfig(read_only=True)
    store = Store(tmp_path / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-10000, p_batterie_w=0, soc_pct=60, p_pv_w=11000)
    wp = VaillantSimulator()
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "vaillant": wp})

    for i in range(70):
        asyncio.run(loop.tick(T0 + timedelta(seconds=i * 10)))
    assert loop.heatpump.ww_boost is True
    assert wp.commands == [] and wp.werte["ww_soll_c"] == 45.0


def test_waermepumpe_ausfall_stoert_das_laden_nicht(tmp_path):
    """Fail-Safe E7: WP/HA weg → keine WP-Befehle, Ladebetrieb unverändert."""
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=-300, soc_pct=60)
    goe = GoeSimulator(connected=True, power_w=0)
    wp = VaillantSimulator()
    wp.available = False
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "goe": goe, "vaillant": wp})

    asyncio.run(loop.tick(T0))
    asyncio.run(loop.tick(T0 + timedelta(seconds=60)))
    assert goe.charging                       # Laden läuft trotz WP-Ausfall
    assert wp.commands == []
    assert loop.status()["wp"]["verbunden"] is False


def test_lesefehler_steht_im_status_und_im_protokoll(tmp_path):
    """T-WP-1 (v0.6.2): ein ausgefallenes Gerät nennt den Grund, statt nur zu fehlen.

    Bis v0.6.1 hat `_safe_read` jede Ausnahme verschluckt — die nicht angebundene
    Wärmepumpe sah im Dashboard genauso aus wie eine gar nicht konfigurierte.
    """
    cfg = RegelConfig(read_only=False)
    store = Store(tmp_path / "test.db")
    e3dc = E3dcSimulator(p_netz_w=-3000, p_batterie_w=0, soc_pct=60)
    wp = VaillantSimulator()
    wp.available = False
    loop = ControlLoop(cfg, SafetyGuard(cfg), store, {"e3dc": e3dc, "vaillant": wp})

    asyncio.run(loop.tick(T0))
    st = loop.status()
    assert "nicht erreichbar" in st["wp"]["fehler"]
    assert st["geraete"]["vaillant"]["ok"] is False
    assert st["geraete"]["e3dc"]["ok"] is True
    assert st["geraete"]["e3dc"]["letzte_lesung"] is not None
    # Der Ausfall steht auch im Protokoll (REQ-062) — genau einmal, nicht je Tick
    for i in range(1, 30):
        asyncio.run(loop.tick(T0 + timedelta(seconds=i * 10)))
    meldungen = [d for d in store.recent_decisions(500) if "vaillant" in str(d)]
    assert len(meldungen) == 1

    # Kommt das Gerät zurück, verschwindet der Fehler und die Rückkehr wird gemeldet
    wp.available = True
    asyncio.run(loop.tick(T0 + timedelta(seconds=300)))
    st = loop.status()
    assert st["wp"]["verbunden"] is True and st["wp"]["fehler"] is None
    assert st["geraete"]["vaillant"]["ok"] is True
    assert len([d for d in store.recent_decisions(500) if "vaillant" in str(d)]) == 2
