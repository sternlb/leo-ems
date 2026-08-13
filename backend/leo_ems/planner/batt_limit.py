"""Dynamische Entladegrenze der Hausbatterie beim EV-Laden — Spec §5.1 (REQ-024).

Bis v0.8.0 galt beim Laden eine **harte Sperre**: `max_discharge = 0`. Damit
konnte die Batterie das Auto nicht mitfüttern — sie konnte aber auch nichts
anderes mehr decken. Jede Leistungslücke musste zwingend das Netz füllen:
Regelübergänge, das 3p-Mindestband während der Rückfall-Entprellung, ein
zugeschalteter Backofen, ein Wolkenzug. Genau der Netzbezug, den Leo nach
v0.8.0 immer noch beobachtet hat.

Statt zwischen „gesperrt" und „frei" zu wählen, folgt die Grenze jetzt dem
gemessenen Restbedarf des Hauses:

    bedarf = max(0, Netzbezug) + max(0, laufende Entladung)

Die E3DC regelt selbst auf Netzbezug ≈ 0 und entlädt nie mehr, als das Haus
zieht — die Grenze deckelt also nur, was sie decken *darf*, und begrenzt damit
den einzigen relevanten Fehlerfall: dass die E3DC-eigene Regelung den
Wallbox-Bezug für Hauslast hält.

Warum diese Summe und kein Integrator auf den Netzbezug: Sie ist stationär
selbstkonsistent. Deckt die Batterie 800 W bei Netzbezug 0, bleibt der Bedarf
800 W und die Grenze steht. Ein reiner Netzbezugs-Regler würde stattdessen
schwingen — Grenze hoch, Netz auf 0, Grenze auf 0, Netzbezug zurück.

Hoch wird sofort geregelt, runter nur gedämpft (`batt_dyn_abbau_w` je Tick):
dieselbe Asymmetrie wie beim Phasenrückfall aus Issue #7 — Netzbezug abstellen
ist Schadensbegrenzung und darf nicht warten, ihn zurücknehmen ist Optimierung.

Hart gesperrt bleibt es, wo Netzbezug **gewollt** ist (Modus Schnell,
Garantieladung, das Minimum in PV+Min — `netz_gewollt` aus dem ChargeController)
und unterhalb `priority_soc_pct`, wo die Hausbatterie Vorrang hat.

Seit v0.10.0 gibt es einen dritten Fall (Issue #11): die **bewusste Freigabe**.
Fordert Leo die Batterie ausdrücklich an — Modus „PV+Batterie" oder „Schnell"
mit `schnell_batt_nutzen` —, darf sie das Auto bis `batt_schnell_max_w` speisen.
Dort gilt `priority_soc_pct` bewusst **nicht**: die 25-%-Schwelle ist eine
Heuristik für die Automatik-Modi und soll eine Anordnung nicht überstimmen. Der
harte Boden ist stattdessen `soc_reserve_pct` (REQ-021) — bis v0.9.0 war dieser
Parameter nirgends durchgesetzt (`SafetyGuard.validate_battery_discharge` wurde
nur von Tests aufgerufen), hier wird er zum ersten Mal wirksam.

Reine Logik, testbar ohne Geräte.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import RegelConfig
from ..safety import SafetyGuard

RASTER_W = 50        # Grenzen werden gerastert — Basis der Schreibdrossel
MIN_WIRKSAM_W = 100  # darunter entlädt die E3DC ohnehin nicht (discharge_start ~65 W)
SOC_HYSTERESE = 2    # Prozentpunkte über der Schwelle, bevor sie wieder freigibt


@dataclass
class LimitEntscheid:
    """`limit_w`: None = keine Begrenzung, 0 = harte Sperre, sonst Grenze in W."""

    limit_w: int | None
    art: str        # "aus" | "hart" | "dynamisch" | "freigabe"
    grund: str      # Klartext für Status und Protokoll (REQ-050)


class EntladeLimitRegler:
    def __init__(self, cfg: RegelConfig, guard: SafetyGuard | None = None):
        self.cfg = cfg
        # Die Reserve-Prüfung gehört laut Spec §8.3 in die zentrale Validierung;
        # ein eigener Guard auf derselben Config verhält sich identisch, falls
        # keiner hereingereicht wird (Tests).
        self.guard = guard or SafetyGuard(cfg)
        self._limit_w = 0.0        # laufendes Soll (ungerastert), nicht das Geschriebene
        self._war_hart = False     # für die SoC-Hysterese an priority_soc_pct

    def update(
        self,
        *,
        charging: bool,
        netz_gewollt: bool,
        soc_batt: float,
        p_netz_w: float,
        p_batterie_w: float,
        batt_freigabe: bool = False,
    ) -> LimitEntscheid:
        """Ein Tick. Vorzeichen: p_netz_w > 0 = Bezug, p_batterie_w > 0 = lädt."""
        if not charging:
            self._limit_w = 0.0
            self._war_hart = False
            return LimitEntscheid(None, "aus", "kein Ladevorgang — Batterie frei")

        # Bewusste Freigabe geht allen Automatik-Regeln vor — bis auf die
        # Reserve und den Notausstieg `batt_dyn_aktiv`.
        #
        # Die Reserve wird hier **ohne Hysterese** geprüft: `batt_freigabe` hat
        # die Entscheidung schon getroffen (samt Hysterese, siehe
        # `ControlLoop._batt_verfuegbar` — dort hängt auch das Ladeverhalten
        # dran, nicht nur diese Grenze). Ein zweiter Zustandsautomat auf
        # derselben Schwelle würde sich mit dem ersten überlagern; was bleibt,
        # ist ein reiner Rückfallschutz, falls jemand die Freigabe unterhalb der
        # Reserve hereinreicht.
        if batt_freigabe and self.cfg.batt_dyn_aktiv \
                and self.guard.validate_battery_discharge(soc_batt):
            self._limit_w = float(self.cfg.batt_schnell_max_w)
            self._war_hart = False
            return LimitEntscheid(
                self.cfg.batt_schnell_max_w, "freigabe",
                f"Batterie freigegeben: bis {self.cfg.batt_schnell_max_w} W ins Auto "
                f"(Reserve {self.cfg.soc_reserve_pct} %, SoC {soc_batt:.0f} %)",
            )

        hart, grund = self._hart_pruefen(netz_gewollt, soc_batt)
        if hart:
            self._limit_w = 0.0
            self._war_hart = True
            return LimitEntscheid(0, "hart", f"harte Entladesperre: {grund}")
        self._war_hart = False

        bedarf_w = max(0.0, p_netz_w) + max(0.0, -p_batterie_w)
        soll_w = min(bedarf_w + self.cfg.batt_dyn_puffer_w, float(self.cfg.batt_dyn_max_w))
        if soll_w >= self._limit_w:
            self._limit_w = soll_w                                   # hoch: sofort
        else:
            self._limit_w = max(soll_w, self._limit_w - self.cfg.batt_dyn_abbau_w)

        limit = int(round(self._limit_w / RASTER_W) * RASTER_W)
        if limit < MIN_WIRKSAM_W:
            limit = 0
        return LimitEntscheid(
            limit, "dynamisch",
            f"dynamische Entladegrenze {limit} W (Bedarf {bedarf_w:.0f} W)",
        )

    def _hart_pruefen(self, netz_gewollt: bool, soc_batt: float) -> tuple[bool, str]:
        """Gilt die harte Sperre? Zweiter Rückgabewert ist die Begründung."""
        if not self.cfg.batt_dyn_aktiv:
            return True, "dynamische Entladegrenze abgeschaltet"
        if netz_gewollt:
            return True, "Netzbezug ist in dieser Betriebsart gewollt"
        # Hysterese: einmal hart, bleibt es bis SOC_HYSTERESE über der Schwelle.
        # Der SoC ändert sich langsam, ein Flattern an der Grenze wäre reiner
        # Schreibverkehr Richtung E3DC.
        schwelle = self.cfg.priority_soc_pct + (SOC_HYSTERESE if self._war_hart else 0)
        if soc_batt < schwelle:
            return True, (f"SoC {soc_batt:.0f} % unter Vorrang-Grenze "
                          f"{self.cfg.priority_soc_pct} % — Hausbatterie zuerst")
        return False, ""
