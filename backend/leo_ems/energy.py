"""Energiebilanz: Tageswerte mitschreiben und E3DC-Historie nachimportieren (Issue #13).

**Warum das EMS das überhaupt rechnet.** Seit die Garagen-Anlage läuft, kann die
E3DC den Hausverbrauch nicht mehr richtig ausweisen: Der Sungrow ist AC-gekoppelt
und speist hinter dem Zähler ein, die E3DC sieht davon nur weniger Bezug bzw.
mehr Einspeisung. Ihr Hausverbrauch ist damit um die Garagen-Erzeugung zu klein —
und wenn die Bilanz negativ wird, meldet sie schlicht 0 W. Genau das war Leos
Beobachtung am 2026-08-22. Das EMS ist die einzige Stelle, die **beide** Anlagen
kennt, also rechnet es hier:

    Hausverbrauch = PV(Haus) + PV(Garage) + Netzbezug + Batterieentladung
                    − Netzeinspeisung − Batterieladung − Wallbox

Die Wallbox wird abgezogen, weil sie im Dashboard als eigener Verbraucher steht;
`haus_gesamt` (mit Wallbox) ist die Größe, die der E3DC-Wert meinte.

**Warum Tageszeilen und keine Ticks.** Die Ticks liegen bereits in `snapshots`.
Für „Überblick über beliebige Jahre und Monate" (Issue #13) braucht es einen
Datenbestand, der Jahre überlebt, ohne zu wachsen wie ein Tick-Log: 365 Zeilen
pro Jahr, aggregierbar per SQL. Der Zähler hält den laufenden Tagesstand im
Speicher und schreibt ihn im Takt von `SCHREIB_INTERVALL_S` als absoluten Wert.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

# Ein Tick, der länger her ist als das, wird nicht integriert. Er entsteht durch
# Neustart, Netzausfall oder einen hängenden Adapter — die Leistung von damals
# über die ganze Lücke fortzuschreiben, würde die Tagesbilanz verfälschen. Eine
# echte Lücke ist die ehrlichere Aussage als eine erfundene Fläche.
MAX_LUECKE_S = 120.0
SCHREIB_INTERVALL_S = 60.0   # Regeltick ist 10 s; jede Minute reicht für Tageswerte

KANAELE = (
    "pv_haus_wh", "pv_garage_wh", "netz_bezug_wh", "netz_einspeisung_wh",
    "batt_laden_wh", "batt_entladen_wh", "haus_wh", "wallbox_wh",
)


def leistungen_aus_status(st: dict) -> dict[str, float]:
    """Statusbild → Leistung je Kanal in W, alle **vorzeichenfrei**.

    Reine Funktion ohne I/O, damit die Vorzeichen-Konvention an einer Stelle
    steht und testbar ist: `p_netz_w` > 0 = Bezug, `p_batterie_w` > 0 = laden.
    """
    p_netz = float(st.get("p_netz_w") or 0.0)
    p_batt = float(st.get("p_batterie_w") or 0.0)
    return {
        "pv_haus_wh": max(0.0, float(st.get("p_pv_e3dc_w") or 0.0)),
        "pv_garage_wh": max(0.0, float(st.get("p_sungrow_w") or 0.0)),
        "netz_bezug_wh": max(0.0, p_netz),
        "netz_einspeisung_wh": max(0.0, -p_netz),
        "batt_laden_wh": max(0.0, p_batt),
        "batt_entladen_wh": max(0.0, -p_batt),
        "haus_wh": max(0.0, float(st.get("p_haus_w") or 0.0)),
        "wallbox_wh": max(0.0, float(st.get("p_wallbox_w") or 0.0)),
    }


class Energiezaehler:
    """Integriert die Tick-Leistungen zur Tagesbilanz und persistiert sie.

    Der Zustand lebt bewusst im Speicher und nicht in der Datenbank: Ein
    `UPDATE … SET x = x + ?` je Tick wäre bei einem wiederholten Aufruf oder
    einem Neustart mitten im Schreibvorgang doppelt gezählt. Absolute Stände
    sind gegen beides immun — dafür muss der Tagesstand beim Start aus der
    Datenbank zurückgeholt werden (`_tag_laden`), sonst begänne jeder Neustart
    den Tag bei null und überschriebe die schon gezählten Stunden.
    """

    def __init__(self, store, schreib_intervall_s: float = SCHREIB_INTERVALL_S):
        self.store = store
        self._intervall = timedelta(seconds=schreib_intervall_s)
        self._tag: str | None = None
        self._stand: dict[str, float] = {}
        # Zweiter Zähler mit derselben Mechanik, nur feiner: die Tagesansicht
        # zeigt den Tag über 24 Stunden und braucht dafür Stundenzeilen (v0.15).
        self._stunde: str | None = None
        self._stand_h: dict[str, float] = {}
        self._letzter_tick: datetime | None = None
        self._letzte_schrift: datetime | None = None
        self.luecken = 0          # übersprungene Integrationen (Diagnose)
        self.geschrieben = 0

    # --- laufender Betrieb -------------------------------------------------
    def tick(self, st: dict, jetzt: datetime) -> None:
        """Ein Regeltick. Wirft nie — Buchhaltung darf die Regelung nicht stören."""
        try:
            self._tick(st, jetzt)
        except Exception as exc:  # pragma: no cover — Sicherheitsnetz
            print(f"[leo-ems] Energiezähler: {type(exc).__name__}: {exc}", flush=True)

    def _tick(self, st: dict, jetzt: datetime) -> None:
        tag = jetzt.date().isoformat()
        stunde = jetzt.strftime("%Y-%m-%d %H")
        if self._tag is None:
            self._tag = tag
            self._stand = self._tag_laden(tag)
        if self._stunde is None:
            self._stunde = stunde
            self._stand_h = self._stunde_laden(stunde)

        # ERST integrieren, DANN den Tag wechseln. Das Intervall, das über
        # Mitternacht läuft, gehört damit vollständig zum alten Tag. Andersherum
        # — erst wechseln, dann integrieren — fiele es zwischen beide Tage und
        # ginge ersatzlos verloren; bei 10 s Tick ist die Fehlzuordnung höchstens
        # ein Tick lang, der Verlust wäre dagegen jede Nacht real.
        vorher = self._letzter_tick
        self._letzter_tick = jetzt
        if vorher is not None:
            dt_s = (jetzt - vorher).total_seconds()
            if dt_s <= 0 or dt_s > MAX_LUECKE_S:
                self.luecken += 1
            else:
                faktor = dt_s / 3600.0
                for kanal, watt in leistungen_aus_status(st).items():
                    zuwachs = watt * faktor
                    self._stand[kanal] = self._stand.get(kanal, 0.0) + zuwachs
                    self._stand_h[kanal] = self._stand_h.get(kanal, 0.0) + zuwachs

        if tag != self._tag or stunde != self._stunde:
            # Perioden­wechsel: die alte Periode ein letztes Mal festschreiben,
            # sonst verfallen die Minuten seit dem letzten Schreibtakt im
            # Speicher. Ein Tageswechsel ist immer auch ein Stundenwechsel;
            # beide werden deshalb in derselben Verzweigung behandelt, damit
            # der Tageswechsel den Stundenwechsel nicht überspringt.
            self._schreiben(jetzt)
            if tag != self._tag:
                self._tag = tag
                self._stand = self._tag_laden(tag)
            self._stunde = stunde
            self._stand_h = self._stunde_laden(stunde)
            self._letzte_schrift = None
            return

        if self._letzte_schrift is None or (jetzt - self._letzte_schrift) >= self._intervall:
            self._schreiben(jetzt)

    def _schreiben(self, jetzt: datetime) -> None:
        if self._tag is None:
            return
        self.store.energie_tag_schreiben(self._tag, self._stand, "ems", jetzt)
        if self._stunde is not None:
            self.store.energie_stunde_schreiben(self._stunde, self._stand_h, jetzt)
        self._letzte_schrift = jetzt
        self.geschrieben += 1

    def _tag_laden(self, tag: str) -> dict[str, float]:
        """Tagesstand aus der Datenbank holen (Neustart mitten am Tag).

        Eine importierte E3DC-Zeile wird dabei **verworfen**: Sie ist die
        schlechtere Quelle (kennt die Garage nicht), und würde sie als Startwert
        dienen, addierte sich die eigene Messung obendrauf.
        """
        zeile = self.store.energie_tag_lesen(tag)
        if zeile is None or zeile.get("quelle") != "ems":
            return {k: 0.0 for k in KANAELE}
        return {k: float(zeile.get(k) or 0.0) for k in KANAELE}

    def _stunde_laden(self, stunde: str) -> dict[str, float]:
        """Stundenstand zurückholen (Neustart mitten in der Stunde).

        Kein Quellen-Vorbehalt wie beim Tag: Stundenzeilen entstehen
        ausschließlich hier, es gibt keinen Import, der sie überschreiben
        könnte.
        """
        zeile = self.store.energie_stunde_lesen(stunde)
        if zeile is None:
            return {k: 0.0 for k in KANAELE}
        return {k: float(zeile.get(k) or 0.0) for k in KANAELE}

    def status(self) -> dict:
        """Für /api/v1/status und die Diagnose.

        `stand_kwh` enthält **immer alle** Kanäle, auch vor dem ersten Tick.
        Sonst müsste jede Anzeige zwischen „Kanal fehlt" und „Kanal ist null"
        unterscheiden, obwohl das für einen Tagesstand dasselbe bedeutet.
        """
        return {
            "tag": self._tag,
            "stand_kwh": {k: round(self._stand.get(k, 0.0) / 1000.0, 3) for k in KANAELE},
            "luecken": self.luecken,
            "schreibvorgaenge": self.geschrieben,
        }


# --- Nachimport aus der E3DC ------------------------------------------------

class ImportBericht:
    """Ergebnis eines Historien-Imports — bewusst ein Objekt statt eines Tupels,
    weil der Import lange läuft und die API seinen Fortschritt abfragen können
    muss, während er noch arbeitet."""

    def __init__(self, von: str, bis: str):
        self.von, self.bis = von, bis
        self.laeuft = True
        self.phase = "lesen"       # lesen → schreiben → fertig
        self.geprueft = 0
        self.geschrieben = 0
        self.uebersprungen = 0     # Tag liegt schon als EMS-Messung vor
        self.leer = 0              # E3DC hat für den Tag nichts
        self.fehler: str | None = None
        self.richtung: str | None = None
        # Summierter Bilanz-Rest beider Deutungen — die Entscheidungsgrundlage
        # für `richtung`, und zugleich das Qualitätsmaß des Imports: Der Rest
        # der gewählten Richtung sollte klein sein (Wandlungsverluste), der der
        # verworfenen um ein Vielfaches größer. Liegen beide dicht beieinander,
        # ist die Zuordnung nicht belegt und die Zahl darf nicht geglaubt werden.
        self.rest_direkt_kwh: float | None = None
        self.rest_getauscht_kwh: float | None = None
        self.aktueller_tag: str | None = None

    def as_dict(self) -> dict:
        return {
            "laeuft": self.laeuft, "phase": self.phase, "von": self.von, "bis": self.bis,
            "geprueft": self.geprueft, "geschrieben": self.geschrieben,
            "uebersprungen": self.uebersprungen, "leer": self.leer,
            "aktueller_tag": self.aktueller_tag,
            "netz_richtung": self.richtung, "fehler": self.fehler,
            "rest_direkt_kwh": self.rest_direkt_kwh,
            "rest_getauscht_kwh": self.rest_getauscht_kwh,
        }


def _bilanz_rest(roh: dict, getauscht: bool) -> float:
    """Wie gut schließt die Bilanz bei dieser Deutung von grid_power_in/out?

    Die E3DC benennt die Netzrichtungen aus Sicht ihres Zählers, und welche
    Richtung `grid_power_in` meint, ist aus dem Namen allein nicht zu
    entscheiden — falsch geraten kehrt sich Bezug und Einspeisung um, was in
    einer Jahresauswertung niemandem auffällt und alles wertlos macht. Statt zu
    raten wird gerechnet: Die Anlage liefert ihren eigenen `consumption`-Wert
    mit, also probieren wir beide Deutungen und nehmen die, unter der die
    Bilanz aufgeht.
    """
    a, b = abs(float(roh.get("grid_power_in") or 0.0)), abs(float(roh.get("grid_power_out") or 0.0))
    bezug, einspeisung = (b, a) if getauscht else (a, b)
    pv = abs(float(roh.get("solarProduction") or 0.0))
    lade = abs(float(roh.get("bat_power_in") or 0.0))
    entlade = abs(float(roh.get("bat_power_out") or 0.0))
    haus = abs(float(roh.get("consumption") or 0.0))
    return abs(pv + bezug + entlade - einspeisung - lade - haus)


def e3dc_tag_umrechnen(roh: dict, getauscht: bool, pv_garage_wh: float = 0.0) -> dict:
    """Ein E3DC-Tagesdatensatz (Wh) → Kanäle der Tabelle.

    `consumption` der E3DC ist der Hausverbrauch **inklusive Wallbox** und
    **ohne** Kenntnis der Garagen-Anlage. Beides wird hier geradegezogen: Die
    Garagen-Erzeugung fehlt in der Bilanz und wird addiert; die Wallbox lässt
    sich rückwirkend nicht heraustrennen, deshalb steht sie in `haus_wh` mit
    drin und `wallbox_wh` bleibt 0 — eine erfundene Aufteilung wäre schlimmer
    als eine ehrlich zusammengefasste Zahl.
    """
    a = abs(float(roh.get("grid_power_in") or 0.0))
    b = abs(float(roh.get("grid_power_out") or 0.0))
    bezug, einspeisung = (b, a) if getauscht else (a, b)
    return {
        "pv_haus_wh": abs(float(roh.get("solarProduction") or 0.0)),
        "pv_garage_wh": pv_garage_wh,
        "netz_bezug_wh": bezug,
        "netz_einspeisung_wh": einspeisung,
        "batt_laden_wh": abs(float(roh.get("bat_power_in") or 0.0)),
        "batt_entladen_wh": abs(float(roh.get("bat_power_out") or 0.0)),
        "haus_wh": abs(float(roh.get("consumption") or 0.0)) + pv_garage_wh,
        "wallbox_wh": 0.0,
    }


def _leer(roh: dict) -> bool:
    """Tage vor der Inbetriebnahme liefert die Anlage als lauter Nullen."""
    return not any(abs(float(roh.get(k) or 0.0)) > 1.0 for k in
                   ("solarProduction", "consumption", "grid_power_in", "grid_power_out"))


async def importiere_e3dc_historie(adapter, store, von: date, bis: date,
                                   bericht: ImportBericht | None = None,
                                   pause_s: float = 0.05,
                                   garage_seit: date | None = None) -> ImportBericht:
    """Tag für Tag aus der E3DC nachladen (Issue #13, „historische Daten").

    **Warum sequenziell mit Pause und nicht in einem Rutsch:** Ein RSCP-Aufruf
    dauert Millisekunden, aber drei Jahre sind über tausend davon. In einem
    Block ausgeführt stünde die Regelschleife für die ganze Zeit still — sie
    teilt sich den Event-Loop mit dem Import. Die Pause zwischen zwei Tagen
    gibt ihr den Tick zurück; der Import dauert dadurch Minuten statt Sekunden,
    läuft aber im Hintergrund und stört keine einzige Regelentscheidung.

    Eigene Messungen (`quelle='ems'`) werden **nie** überschrieben. Sie sind die
    bessere Quelle, sobald es die Garagen-Anlage gibt.

    **Zwei Phasen, und warum das nötig ist.** Erst wird der ganze Zeitraum
    gelesen und im Speicher gehalten, dann erst geschrieben. Grund ist die
    Netzrichtung: Sie wird aus der Bilanz erschlossen (siehe `_bilanz_rest`),
    und ein einzelner Tag taugt dafür nicht. Der erste Import am 22.08.2026 lief
    genau da hinein — sein erster Tag hatte 0,196 kWh Bezug gegen 0,198 kWh
    Einspeisung, beide Deutungen ergaben denselben Rest (2,28 gegen 2,29 kWh),
    und die Entscheidung fiel praktisch per Münzwurf. Falsch. Zwei Tage später
    lagen 35,7 kWh gegen 0,13 kWh an, dort hätte man es nicht verfehlen können.
    Über den ganzen Zeitraum summiert ist die Frage eindeutig — deshalb wird sie
    dort entschieden. 1800 Tagesdatensätze im Speicher sind dafür ein
    vernachlässigbarer Preis.
    """
    bericht = bericht or ImportBericht(von.isoformat(), bis.isoformat())
    vorhanden_ems = store.energie_bekannte_tage("ems")
    try:
        # --- Phase 1: lesen ------------------------------------------------
        bericht.phase = "lesen"
        gelesen: list[tuple[date, dict]] = []
        rest_direkt = rest_getauscht = 0.0
        tag = von
        while tag <= bis:
            bericht.aktueller_tag = tag.isoformat()
            if tag.isoformat() in vorhanden_ems:
                bericht.uebersprungen += 1
            else:
                roh = await adapter.historie_tag(tag)
                bericht.geprueft += 1
                if roh is None or _leer(roh):
                    bericht.leer += 1
                else:
                    gelesen.append((tag, roh))
                    rest_direkt += _bilanz_rest(roh, False)
                    rest_getauscht += _bilanz_rest(roh, True)
            tag += timedelta(days=1)
            if pause_s:
                await asyncio.sleep(pause_s)

        if not gelesen:
            return bericht

        getauscht = rest_getauscht < rest_direkt
        bericht.richtung = "getauscht" if getauscht else "direkt"
        bericht.rest_direkt_kwh = round(rest_direkt / 1000.0, 1)
        bericht.rest_getauscht_kwh = round(rest_getauscht / 1000.0, 1)

        # --- Phase 2: schreiben --------------------------------------------
        # Reine Datenbankarbeit, kein Netz: läuft in Sekunden durch.
        bericht.phase = "schreiben"
        for tag, roh in gelesen:
            bericht.aktueller_tag = tag.isoformat()
            unvollstaendig = garage_seit is not None and tag >= garage_seit
            store.energie_tag_schreiben(
                tag.isoformat(), e3dc_tag_umrechnen(roh, getauscht),
                "e3dc-ohne-garage" if unvollstaendig else "e3dc",
            )
            bericht.geschrieben += 1
    except Exception as exc:
        bericht.fehler = f"{type(exc).__name__}: {exc}"
    finally:
        bericht.laeuft = False
        bericht.phase = "fertig" if bericht.fehler is None else "abgebrochen"
        bericht.aktueller_tag = None
    return bericht


# --- Anzeige-Aufbereitung ---------------------------------------------------

def stunden_auffuellen(zeilen: list[dict], von: str, bis: str) -> list[dict]:
    """Ein Tagesfenster auf **alle** Stunden auffüllen (Issue #17).

    Die Datenbank kennt nur Stunden, in denen das EMS gelaufen ist. Zeichnet man
    genau die, wird aus einem Tag mit zwei aufgezeichneten Stunden ein Diagramm
    mit zwei Säulen über die volle Breite — es sieht aus wie „der Tag", ist aber
    ein Ausschnitt. Genau das war am 27.08.2026 zu sehen, dem Tag, an dem die
    Stundentabelle um 22:46 dazukam.

    Deshalb bekommt die Reihe hier ihr vollständiges Raster: 00 bis 23 für jeden
    Tag des Fensters. Fehlende Stunden kommen mit Nullen, aber mit `stunden: 0`
    und leerer `quellen` — daran ist „nicht gemessen" von „gemessen, war null"
    unterscheidbar, und die Summe über `stunden` ist die Abdeckung des Tages.

    Bewusst hier und nicht in der Datenbankschicht: Der CSV-Export soll weiter
    die echten Zeilen ausliefern. Eine Datei mit 22 erfundenen Nullzeilen wäre
    nicht dasselbe wie eine ehrliche Lücke, sobald jemand sie weiterrechnet.
    """
    vorhanden = {z["periode"]: z for z in zeilen}
    raus = []
    tag = date.fromisoformat(von)
    ende = date.fromisoformat(bis)
    while tag <= ende:
        for h in range(24):
            schluessel = f"{tag.isoformat()} {h:02d}"
            z = vorhanden.get(schluessel)
            raus.append(z if z is not None else
                        {"periode": schluessel, "stunden": 0, "quellen": "",
                         **{k: 0.0 for k in KANAELE}})
        tag += timedelta(days=1)
    return raus
