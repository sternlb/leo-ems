"""Wärmepumpen-Steuerung — REQ-010/011/012/014/064 (Stufe 2).

Zwei Überschuss-Hebel auf dieselbe Vaillant-Anlage:

  1. **Warmwasser vorziehen** (REQ-010): Sollwert von 45 auf 57 °C anheben,
     solange PV-Überschuss trägt, und automatisch zurückstellen. Zurückgestellt
     wird nicht nur beim Boost-Ende, sondern in jedem Tick, in dem ohne
     laufenden Boost noch der Boost-Sollwert auf der Anlage steht
     (`_ww_rueckstand`, Issue #15) — der Rückweg hängt damit an einem Zustand
     und nicht an einem einzelnen Ereignis, das verloren gehen kann.
  2. **Heizkreis anheben** (REQ-011): Raum-Sollwert um Δ anheben — nur in der
     Heizperiode und nur, wenn das Zeitprogramm überhaupt einen Sollwert hat.

Beide Hebel sind **getrennt schaltbar** (`wp_ww_aktiv` / `wp_hk_aktiv`,
Issue #1): Leo will Warmwasser jetzt nutzen, den Heizkreis erst mit dem
dynamischen Tarif. Eine abgeschaltete Funktion wird nicht bewertet — ein
laufender Boost wird sofort zurückgestellt, **ohne** auf die Mindestlaufzeit zu
warten. Ein Ausschalter, der erst in 20 Minuten wirkt, ist keiner.

Festlegungen von Leo (2026-07-25):
  - **Vorrang Auto.** Der Controller sieht nur den Überschuss, der nach der
    Wallbox-Zuteilung übrig ist — das Ladeverhalten ändert sich dadurch nicht.
  - **Konservative Schwellen:** an ab 2,5 kW, zurück unter 0,5 kW.

Drei Eigenheiten, die die Logik prägen:

  * **Kein Leistungsmesswert.** Die WP hat in HA nur Energiezähler, ihr
    Verbrauch steckt also im Hausverbrauch und senkt den gemessenen Überschuss,
    sobald ein Boost läuft. Genau dafür ist das Hysterese-Band da: der Abstand
    zwischen An- und Aus-Schwelle (2,5 → 0,5 kW) ist so breit wie der
    geschätzte WP-Verbrauch `wp_leistung_w`, damit sich der Boost nicht selbst
    abschaltet. Wird das Band zu schmal konfiguriert, zieht `_aus_schwelle()`
    die Aus-Schwelle nach unten statt in den Schaltzyklus zu laufen.
  * **Cloud-Ratenlimit** (REQ-014). Geschrieben wird nur bei Zustandswechsel
    und höchstens alle `wp_cloud_min_gap_s`. Ein Sollwert gilt als „gewünscht",
    bis ihn ein Rücklesen bestätigt — dadurch wird ein verlorener Cloud-Aufruf
    von selbst wiederholt, ohne Dauerschleife.
  * **Hysterese nach oben** (Issue #15). Ein beendeter Boost sperrt den
    nächsten, bis der Speicher unter `wp_ww_wieder_c` (53 °C) fällt. Ohne diese
    Sperre reichte ein halbes Grad Abkühlung, damit der nächste Boost lossetzte
    — Takten um ein paar hundert Wattstunden.
  * **Keine Dauer-Übersteuerung.** Sobald ein Sollwert bestätigt ist, schreibt
    das EMS nicht mehr nach. Wer in der MyVaillant-App etwas von Hand ändert,
    wird nicht überstimmt.

Reine Logik, testbar ohne Geräte: Zeit kommt von außen, Geräte-Werte als dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..config import RegelConfig

TOLERANZ_K = 0.5   # Sollwert gilt als erreicht/bestätigt innerhalb dieser Spanne

# Lauf-Erkennung fürs Dashboard (Lüfter-Animation). MyVaillant liefert keine
# Verdichter- oder Ventilatorleistung, deshalb wird aus den beiden Klartext-
# Sensoren abgeleitet: Heizkreis-Zustand und Warmwasser-Sonderfunktion.
HK_LAEUFT = {"HEATING", "COOLING", "HEIZEN", "KUEHLEN", "KÜHLEN", "ON", "ACTIVE"}
WW_RUHT = {"", "NONE", "NULL", "KEINE", "REGULAR", "NORMAL", "NORMALBETRIEB",
           "STANDBY", "OFF", "AUS", "UNKNOWN", "UNAVAILABLE"}


@dataclass
class HeatPumpCommand:
    """Was gesendet werden soll; None = nichts zu tun."""

    ww_soll_c: float | None = None
    raum_soll_c: float | None = None
    ww_boost: bool = False
    hk_boost: bool = False
    grund: str = "—"


class HeatPumpController:
    def __init__(self, cfg: RegelConfig):
        self.cfg = cfg
        self.ww_boost = False
        self.hk_boost = False
        # Hysterese-Latch Warmwasser (Issue #15): einmal auf Boost-Temperatur,
        # bleibt gesperrt, bis der Speicher unter `wp_ww_wieder_c` fällt.
        self._ww_warm = False
        self._ziel: dict[str, float | None] = {"ww": None, "hk": None}
        self._hk_basis: float | None = None      # Raum-Sollwert vor der Anhebung
        self._seit: dict[str, datetime] = {}
        self._start: dict[str, datetime] = {}
        self._last_write: datetime | None = None
        # Rückstellungen, die nicht auf das Cloud-Gap warten sollen (Issue #1):
        # das Abschalten einer Funktion ist eine Handlung von Leo, keine
        # Regelentscheidung — sie darf nicht bis zu 15 min in der Warteschlange
        # liegen. Gilt nur für den einen Aufruf, danach greift das Gap wieder.
        self._eilig: set[str] = set()
        self._grund = "Wärmepumpe noch nicht bewertet"
        self._frei_w = 0.0
        self._ev_zuteilung_w = 0.0

    # --- Hilfen ------------------------------------------------------------
    def _held(self, key: str, bedingung: bool, now: datetime) -> timedelta:
        """Wie lange ist `bedingung` ununterbrochen wahr (über die Ticks)?"""
        if bedingung:
            self._seit.setdefault(key, now)
            return now - self._seit[key]
        self._seit.pop(key, None)
        return timedelta(0)

    def _laufzeit(self, key: str, now: datetime) -> timedelta:
        start = self._start.get(key)
        return now - start if start else timedelta(0)

    def _vorrang_text(self, was: str) -> str:
        """Begründung, wenn ein Boost dem Auto weicht (Issue #6).

        Wichtig, dass das im Klartext steht: „Boost aus, Überschuss weg" und
        „Boost aus, das Auto hat ihn bekommen" sehen in den Zahlen gleich aus,
        sind aber zwei völlig verschiedene Sachverhalte.
        """
        return (f"{was} zurückgestellt — Vorrang Auto: die Wallbox lädt mit "
                f"{self._ev_zuteilung_w / 1000:.1f} kW")

    def _ww_untergrenze(self) -> float:
        """Komfortgrenze Warmwasser (REQ-012): nie unter die harte Grenze stellen."""
        grenze = self.cfg.hard_limit_ww_min_temp
        return max(self.cfg.wp_ww_normal_c, grenze) if grenze is not None else self.cfg.wp_ww_normal_c

    def _ww_wieder_c(self, boost_c: float) -> float:
        """Ab wo darf ein neuer Boost starten, nachdem der Speicher warm war?

        Gedeckelt auf den Arm-Punkt: eine Schwelle **über** `boost_c - TOLERANZ_K`
        würde den Latch im selben Tick setzen und wieder löschen — also gar nicht
        wirken. So ist eine Fehlkonfiguration schlimmstenfalls wirkungslos und
        nie eine Dauersperre.
        """
        return min(self.cfg.wp_ww_wieder_c, boost_c - TOLERANZ_K)

    def _ww_warm_pflegen(self, ist: float | None, boost_c: float) -> None:
        """Den Latch nachführen — die einzige Stelle, die ihn setzt oder löscht."""
        if ist is None:
            return
        if ist >= boost_c - TOLERANZ_K:
            self._ww_warm = True
        elif ist < self._ww_wieder_c(boost_c):
            self._ww_warm = False

    def _aus_schwelle(self, an_w: int, aus_w: int) -> float:
        """Aus-Schwelle, die den eigenen Verbrauch nicht gegen den Boost wendet.

        Der laufende Boost drückt den gemessenen Überschuss um rund
        `wp_leistung_w`. Ist das Band an→aus schmaler als dieser Verbrauch,
        würde der Boost sich selbst abschalten — dann zählt die weiter unten
        liegende Schwelle (toleriert etwas Netzbezug statt Schaltzyklen).
        """
        return min(aus_w, an_w - self.cfg.wp_leistung_w)

    def leistung_w(self, wp: dict | None) -> float:
        """Geschätzte el. Aufnahme eines **laufenden** Überschuss-Boosts (Issue #6).

        Die WP hat keinen Leistungsmesswert — ihr Verbrauch steckt im
        Hausverbrauch und drückt damit den gemessenen Überschuss. Für die
        Vorrangfrage „Auto oder Wärmepumpe?" muss dieser Anteil wieder sichtbar
        werden, sonst gewinnt schlicht, wer zuerst angelaufen ist: läuft der
        Warmwasser-Boost, sieht die Wallbox rund 2 kW weniger und startet gar
        nicht erst. Genau das Fehlerbild aus Issue #6.

        Bewusst konservativ: **gefordert und laufend**. Ein Boost, den die
        Anlage nicht ausführt (Speicher schon warm, Beobachtungsmodus), nimmt
        dem Auto nichts weg — würde man ihn mitzählen, plante das EMS mit
        Leistung, die es nicht gibt, und das wäre wieder Netzbezug (Issue #7).
        """
        if not (self.ww_boost or self.hk_boost):
            return 0.0
        return float(self.cfg.wp_leistung_w) if self._laeuft(wp or {}) else 0.0

    # --- Hauptentscheidung -------------------------------------------------
    def update(
        self, now: datetime, *, frei_w: float, wp: dict | None, ev_zuteilung_w: float = 0.0
    ) -> HeatPumpCommand:
        """Ein Tick.

        `frei_w` ist der Überschuss NACH der Wallbox-Zuteilung — inklusive der
        Leistung, die ein eigener laufender Boost gerade selbst verbraucht
        (`leistung_w`), damit beide Verbraucher gegen dasselbe Budget geprüft
        werden. `ev_zuteilung_w` sagt, wie viel davon an die Wallbox gegangen
        ist; nur daran erkennt der Controller, ob ein Boost dem Auto weichen
        muss oder ob einfach die Sonne weg ist (Issue #6).
        """
        self._ev_zuteilung_w = max(0.0, ev_zuteilung_w)
        if not wp:
            # Fail-Safe E7: WP/HA nicht erreichbar → nichts entscheiden, nichts
            # zurücksetzen. Offene Sollwerte bleiben stehen und gehen raus,
            # sobald die Verbindung wieder steht.
            self._grund = "keine Verbindung zur Wärmepumpe — keine Befehle"
            self._frei_w = frei_w
            return HeatPumpCommand(ww_boost=self.ww_boost, hk_boost=self.hk_boost, grund=self._grund)

        self._frei_w = frei_w
        gruende = [self._ww_entscheiden(now, frei_w, wp)]
        gruende.append(self._hk_entscheiden(now, frei_w, wp))
        self._grund = " · ".join(g for g in gruende if g)

        return self._befehl(now, wp)

    # --- Warmwasser (REQ-010) ----------------------------------------------
    def _ww_entscheiden(self, now: datetime, frei: float, wp: dict) -> str:
        ist = wp.get("ww_ist_c")
        boost_c = self.cfg.wp_ww_boost_c
        normal_c = self._ww_untergrenze()
        self._ww_warm_pflegen(ist, boost_c)

        # Funktion abgeschaltet (Issue #1): laufenden Boost sofort zurückstellen,
        # ohne Mindestlaufzeit. Danach wird Warmwasser gar nicht mehr bewertet.
        if not self.cfg.wp_ww_aktiv:
            self._seit.pop("ww_an", None)
            if self.ww_boost:
                self._eilig.add("ww")
                return self._ww_beenden(
                    normal_c, f"Warmwasser abgeschaltet — zurück auf {normal_c:.0f} °C")
            return "Warmwasser: Überschussnutzung abgeschaltet"

        an = self.cfg.wp_ww_an_w
        aus = self._aus_schwelle(an, self.cfg.wp_ww_aus_w)

        if self.ww_boost:
            if ist is not None and ist >= boost_c - TOLERANZ_K:
                return self._ww_beenden(normal_c, f"Warmwasser {ist:.0f} °C erreicht — zurück auf {normal_c:.0f} °C")
            zu_wenig = self._held("ww_aus", frei < aus, now)
            laufzeit = self._laufzeit("ww", now)
            if zu_wenig >= timedelta(seconds=self.cfg.wp_aus_entprellung_s):
                if self._ev_zuteilung_w > 0:
                    self._eilig.add("ww")
                    return self._ww_beenden(normal_c, self._vorrang_text("Warmwasser-Boost"))
                if laufzeit >= timedelta(seconds=self.cfg.wp_min_laufzeit_s):
                    return self._ww_beenden(
                        normal_c,
                        f"Warmwasser-Boost aus: Überschuss {frei / 1000:.1f} kW < {aus / 1000:.1f} kW"
                        f" — zurück auf {normal_c:.0f} °C")
                rest = self.cfg.wp_min_laufzeit_s - int(laufzeit.total_seconds())
                return (f"Warmwasser-Boost {boost_c:.0f} °C: Überschuss weg, Mindestlaufzeit läuft"
                        f" (noch {rest // 60}:{rest % 60:02d} min)")
            stand = f"{ist:.0f} → {boost_c:.0f} °C" if ist is not None else f"Ziel {boost_c:.0f} °C"
            return f"Warmwasser-Boost aktiv ({stand}), Überschuss {frei / 1000:.1f} kW"

        # Kein Boost aktiv → erstens: steht auf der Anlage noch der Boost-Sollwert?
        rueck = self._ww_rueckstand(wp, boost_c, normal_c)

        # zweitens: Startbedingung — mit Hysterese (Issue #15)
        if self._ww_warm:
            self._seit.pop("ww_an", None)
            stand = f"{ist:.0f} °C" if ist is not None else "warm"
            return (f"{rueck}Warmwasser {stand} — kein Boost nötig "
                    f"(wieder ab unter {self._ww_wieder_c(boost_c):.0f} °C)")
        gehalten = self._held("ww_an", frei >= an, now)
        if gehalten >= timedelta(seconds=self.cfg.wp_entprellung_s):
            self.ww_boost = True
            self._start["ww"] = now
            self._ziel["ww"] = boost_c
            self._seit.pop("ww_aus", None)
            return (f"{rueck}Warmwasser-Boost startet: Überschuss {frei / 1000:.1f} kW ≥ "
                    f"{an / 1000:.1f} kW → Sollwert {boost_c:.0f} °C")
        if gehalten > timedelta(0):
            noetig = self.cfg.wp_entprellung_s
            return (f"{rueck}Warmwasser: Überschuss reicht, Bedingungszeit läuft "
                    f"({int(gehalten.total_seconds())}/{noetig} s)")
        return f"{rueck}Warmwasser: Überschuss {frei / 1000:.1f} kW < {an / 1000:.1f} kW"

    def _ww_rueckstand(self, wp: dict, boost_c: float, normal_c: float) -> str:
        """Boost-Sollwert ohne laufenden Boost → zurücknehmen (Issue #15).

        Bis v0.15 wurde `wp_ww_normal_c` **nur** im Moment des Boost-Endes
        gestellt und danach so lange wiederholt, bis das Rücklesen es bestätigt.
        Zwei Wege führen daran vorbei, und beide sind am 27./28.08.2026
        aufgetreten:

        * Die Bestätigung kommt nie, weil der Rücklese-Sensor `unavailable` ist
          (MyVaillant-Ausfall). Dann schreibt das EMS zwar weiter, aber die
          Schreibvorgänge landen ebenfalls nirgends — HA nimmt den Service-Call
          an, die Integration bringt ihn nicht zur Anlage. Auf der Anlage bleibt
          das Boost-Ziel stehen, ohne dass es jemand merkt.
        * Der Sollwert wird von außen wieder hochgesetzt (Anlage, App,
          Zeitprogramm), nachdem der Rückstellwert bestätigt war. Dann ist
          `_ziel["ww"]` bereits None — es gibt kein offenes Ziel mehr, das
          wiederholt werden könnte, und der Controller sieht die 57 °C nur noch
          als fremden Wert an.

        In der Nacht zum 28.08.2026 stand der Sollwert dadurch ab 22:20 auf
        57 °C. Um 05:30 öffnete das Warmwasser-Zeitprogramm der Anlage
        (Mo–Fr 05:30–22:00) und die WP heizte den Speicher von 52 auf 57 °C —
        ohne Sonne, also aus der ohnehin fast leeren Hausbatterie.

        Statt des Ereignisses wird deshalb der **Zustand** geprüft: kein Boost,
        aber Boost-Sollwert auf der Anlage → Rückstellwert setzen. Das ist
        selbstheilend, denn es gilt bei jedem Tick aufs Neue, und es hängt weder
        an einem gemerkten Zustand noch daran, wer den Sollwert hochgesetzt hat.

        Bewusst eng gefasst: zurückgenommen wird nur, was aussieht wie *unser*
        Boost-Sollwert (`>= boost_c - TOLERANZ_K`). Ein von Hand in der
        MyVaillant-App gestellter Zwischenwert bleibt stehen — die Zusage
        „keine Dauer-Übersteuerung" aus dem Modulkopf gilt weiter.
        """
        if self._ziel["ww"] is not None:
            return ""                      # es ist ohnehin schon einer unterwegs
        soll = wp.get("ww_soll_c")
        if soll is None or soll < boost_c - TOLERANZ_K:
            return ""
        if normal_c >= boost_c - TOLERANZ_K:
            return ""                      # Komfortgrenze liegt selbst auf Boost-Höhe
        self._ziel["ww"] = normal_c
        return (f"Sollwert stand noch auf {soll:.0f} °C ohne Boost — "
                f"zurück auf {normal_c:.0f} °C · ")

    def _ww_beenden(self, normal_c: float, grund: str) -> str:
        self.ww_boost = False
        self._ziel["ww"] = normal_c
        self._start.pop("ww", None)
        self._seit.pop("ww_aus", None)
        return grund

    # --- Heizkreis (REQ-011) ------------------------------------------------
    def _hk_entscheiden(self, now: datetime, frei: float, wp: dict) -> str:
        aussen = wp.get("aussen_c")
        basis_ist = wp.get("raum_soll_c")

        # Funktion abgeschaltet (Issue #1) — wie beim Warmwasser: sofort zurück
        # auf den Wert, der vor der Anhebung stand.
        if not self.cfg.wp_hk_aktiv:
            self._seit.pop("hk_an", None)
            if self.hk_boost:
                self._eilig.add("hk")
                return self._hk_beenden("Heizkreis abgeschaltet — zurück auf den Basiswert")
            return "Heizkreis: Anhebung abgeschaltet"

        # Heizperiode: draußen kalt genug UND das Zeitprogramm hat einen Sollwert.
        # Im Sommer liefert die Anlage 0 °C — dann gäbe es nichts anzuheben.
        zu_warm = aussen is not None and aussen > self.cfg.wp_hk_max_aussen_c
        kein_sollwert = basis_ist is None or basis_ist <= 0

        if self.hk_boost:
            if zu_warm or kein_sollwert:
                return self._hk_beenden("Heizkreis-Anhebung aus: außerhalb der Heizperiode")
            aus = self._aus_schwelle(self.cfg.wp_hk_an_w, self.cfg.wp_hk_aus_w)
            zu_wenig = self._held("hk_aus", frei < aus, now)
            laufzeit = self._laufzeit("hk", now)
            if zu_wenig >= timedelta(seconds=self.cfg.wp_aus_entprellung_s):
                if self._ev_zuteilung_w > 0:
                    self._eilig.add("hk")
                    return self._hk_beenden(self._vorrang_text("Heizkreis-Anhebung"))
                if laufzeit >= timedelta(seconds=self.cfg.wp_min_laufzeit_s):
                    return self._hk_beenden(
                        f"Heizkreis-Anhebung aus: Überschuss {frei / 1000:.1f} kW < "
                        f"{aus / 1000:.1f} kW")
                rest = self.cfg.wp_min_laufzeit_s - int(laufzeit.total_seconds())
                return f"Heizkreis-Anhebung: Mindestlaufzeit läuft (noch {rest // 60}:{rest % 60:02d} min)"
            ziel = self._ziel["hk"] if self._ziel["hk"] is not None else basis_ist
            return f"Heizkreis angehoben auf {ziel:.1f} °C (+{self.cfg.wp_hk_anhebung_k:.1f} K)"

        # nicht aktiv → Startbedingung
        if zu_warm:
            self._seit.pop("hk_an", None)
            return f"Heizkreis: {aussen:.0f} °C draußen — keine Anhebung"
        if kein_sollwert:
            self._seit.pop("hk_an", None)
            return "Heizkreis: Zeitprogramm ohne Sollwert — keine Anhebung"
        # Die WP kann nur eines zur Zeit: läuft der Warmwasser-Boost, hat er Vorrang.
        if self.ww_boost:
            self._seit.pop("hk_an", None)
            return "Heizkreis: Warmwasser hat Vorrang"
        if self._held("hk_an", frei >= self.cfg.wp_hk_an_w, now) >= timedelta(
            seconds=self.cfg.wp_entprellung_s
        ):
            ziel = min(basis_ist + self.cfg.wp_hk_anhebung_k, self.cfg.wp_hk_max_raum_c)
            if ziel <= basis_ist + TOLERANZ_K:
                return f"Heizkreis: Komfort-Obergrenze {self.cfg.wp_hk_max_raum_c:.0f} °C erreicht"
            self.hk_boost = True
            self._start["hk"] = now
            self._hk_basis = basis_ist
            self._ziel["hk"] = ziel
            self._seit.pop("hk_aus", None)
            return f"Heizkreis-Anhebung startet: {basis_ist:.1f} → {ziel:.1f} °C"
        return "Heizkreis: keine Anhebung"

    def _hk_beenden(self, grund: str) -> str:
        self.hk_boost = False
        if self._hk_basis is not None:
            self._ziel["hk"] = self._hk_basis
        self._hk_basis = None
        self._start.pop("hk", None)
        self._seit.pop("hk_aus", None)
        return grund

    # --- Schreibzugriffe drosseln (REQ-014) ---------------------------------
    def _befehl(self, now: datetime, wp: dict) -> HeatPumpCommand:
        """Offene Sollwerte in Befehle übersetzen — höchstens einer pro Gap.

        Ein Ziel bleibt offen, bis das Rücklesen es bestätigt; danach schreibt
        das EMS nicht mehr nach (Handbedienung in der App bleibt möglich).
        """
        cmd = HeatPumpCommand(ww_boost=self.ww_boost, hk_boost=self.hk_boost, grund=self._grund)
        gap_ok = self._last_write is None or (
            now - self._last_write >= timedelta(seconds=self.cfg.wp_cloud_min_gap_s)
        )

        ziel_ww, ist_ww = self._ziel["ww"], wp.get("ww_soll_c")
        if ziel_ww is not None:
            if ist_ww is not None and abs(ist_ww - ziel_ww) <= TOLERANZ_K:
                self._ziel["ww"] = None       # von der Cloud bestätigt
                self._eilig.discard("ww")
            elif gap_ok or "ww" in self._eilig:
                cmd.ww_soll_c = ziel_ww
                self._eilig.discard("ww")     # ein Versuch am Gap vorbei, dann normal
                gap_ok = False                # pro Tick nur ein Cloud-Aufruf

        ziel_hk, ist_hk = self._ziel["hk"], wp.get("raum_soll_c")
        if ziel_hk is not None:
            if ist_hk is not None and abs(ist_hk - ziel_hk) <= TOLERANZ_K:
                self._ziel["hk"] = None
                self._eilig.discard("hk")
            elif gap_ok or "hk" in self._eilig:
                cmd.raum_soll_c = ziel_hk
                self._eilig.discard("hk")

        return cmd

    def schreiben_bestaetigt(self, now: datetime) -> None:
        """Von der Regelschleife aufzurufen, NACHDEM wirklich gesendet wurde.

        Im Beobachtungsmodus wird nicht gesendet und damit auch nicht bestätigt —
        der Status zeigt dann dauerhaft, was das EMS tun *würde*.
        """
        self._last_write = now

    # --- Anzeige (REQ-050/051) ---------------------------------------------
    @staticmethod
    def _laeuft(wp: dict) -> bool:
        """Läuft die Anlage gerade? Nur aus **gelesenen** Werten abgeleitet.

        Bewusst nicht aus `self.ww_boost`/`hk_boost`: im Beobachtungsmodus wird
        nichts gesendet — dann wäre ein „gewünschter" Boost kein Beleg dafür,
        dass die Anlage wirklich anläuft. Ein real gestellter Sollwert schlägt
        eine Runde später ohnehin in diesen Sensoren durch.
        """
        if (wp.get("hk_zustand") or "").strip().upper() in HK_LAEUFT:
            return True
        return (wp.get("ww_sonderfunktion") or "").strip().upper() not in WW_RUHT

    def status(self, wp: dict | None) -> dict:
        """Zweigeteilte Sicht fürs Dashboard: Warmwasser und Heizkreis (Issue #1)."""
        wp = wp or {}
        return {
            "verbunden": bool(wp),
            "laeuft": self._laeuft(wp),
            "grund": self._grund,
            "frei_w": round(self._frei_w),
            # Was die Wallbox vorher aus demselben Budget genommen hat (Issue #6)
            "ev_zuteilung_w": round(self._ev_zuteilung_w),
            "leistung_w": round(self.leistung_w(wp)),
            "warmwasser": {
                "aktiv": self.cfg.wp_ww_aktiv,
                "ist_c": wp.get("ww_ist_c"),
                "soll_c": wp.get("ww_soll_c"),
                "modus": wp.get("ww_modus"),
                "sonderfunktion": wp.get("ww_sonderfunktion"),
                "boost": self.ww_boost,
                "boost_c": self.cfg.wp_ww_boost_c,
                "normal_c": self._ww_untergrenze(),
                "wieder_c": self._ww_wieder_c(self.cfg.wp_ww_boost_c),
                "warm": self._ww_warm,
                "offen_c": self._ziel["ww"],
            },
            "heizkreis": {
                "aktiv": self.cfg.wp_hk_aktiv,
                "vorlauf_c": wp.get("hk_vorlauf_c"),
                "vorlauf_soll_c": wp.get("hk_vorlauf_soll_c"),
                "zustand": wp.get("hk_zustand"),
                "modus": wp.get("hk_modus"),
                "raum_ist_c": wp.get("raum_ist_c"),
                "raum_soll_c": wp.get("raum_soll_c"),
                "boost": self.hk_boost,
                "anhebung_k": self.cfg.wp_hk_anhebung_k,
                "basis_c": self._hk_basis,
                "offen_c": self._ziel["hk"],
            },
            "aussen_c": wp.get("aussen_c"),
            "cop": wp.get("cop"),
        }
