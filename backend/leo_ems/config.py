"""Konfiguration und API-Token-Verwaltung.

Regelparameter mit den Baseline-Defaults aus docs/evcc-baseline.md.
Der API-Token wird beim ersten Start erzeugt und persistiert —
Details in docs/api-token-auth.md.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATA_DIR = Path(os.environ.get("LEO_EMS_DATA_DIR", "./data"))
TOKEN_FILE = DATA_DIR / "api_token"
CONFIG_FILE = DATA_DIR / "config.json"


@dataclass
class RegelConfig:
    """Regelparameter (Spec §2–§5). Alle Werte über die API/App änderbar (REQ-071/072/073)."""

    # Beobachtungsmodus: True = KEINE Steuerbefehle an Geräte, nur messen/loggen.
    # Default True — die erste Installation auf dem Pi läuft gefahrlos parallel
    # zu EVCC (Migrationsstrategie specs/03-architecture.md). Scharfschalten ist
    # ein bewusster Akt über die API/App (PUT /api/v1/config {"read_only": false}).
    read_only: bool = True
    residual_power_w: int = 100        # Ziel-Netzbezug (Spec §2)
    priority_soc_pct: int = 25         # Batterie-Vorrang unterhalb (Spec §2)
    soc_reserve_pct: int = 0           # Batterie-Reserve, Default 0 % (REQ-021)
    interval_s: int = 10               # Regelintervall (Spec §2)
    enable_delay_s: int = 60           # Einschalt-Hysterese (Spec §4.1)
    disable_delay_s: int = 180         # Ausschalt-Hysterese (Spec §4.1)
    min_current_a: int = 6
    max_current_a: int = 16
    phase_up_w: int = 4200             # 1p→3p (Spec §4.2)
    # 3p→1p (Spec §4.2). 4140 W statt der ursprünglichen 4000 W: Das ist exakt
    # das Minimum, das die Wallbox 3-phasig überhaupt abnehmen kann
    # (3 × 6 A × 230 V). Wer darunter auf 3p stehen bleibt, zieht die Differenz
    # aus dem Netz — genau Leos Beobachtung in Issue #7.
    phase_down_w: int = 4140
    phase_min_gap_s: int = 600         # Mindestabstand HOCHschaltungen (Spec §4.2, ⚙1)
    # Rückfall 3p→1p: kurz entprellt und vom Mindestabstand nicht gebremst
    # (Issue #7). Hochschalten ist eine Optimierung und darf warten; unter dem
    # 3p-Minimum stehen zu bleiben kostet dagegen jede Sekunde Netzstrom.
    phase_down_delay_s: int = 60
    charge_efficiency: float = 0.90    # η Zielladung (Spec §4.3, ⚙2)
    plan_buffer_min: int = 15          # Puffer Zielladung (Spec §4.3, ⚙2)
    lease_ttl_s: int = 900             # TTL für Übersteuerungen, 15 min (Spec §5.1)
    battery_capacity_kwh: float = 77.0 # Enyaq iV80
    # Fahrzeug-Ladelimit (Issue #9/#10). Stand bis v0.9.0 als reine Instanz-
    # Variable in der Regelschleife und war damit nach jedem Add-on-Update weg —
    # bei aktivem `auto_update` also regelmäßig. Als Config-Feld läuft es durch
    # save_config()/load_config() und überlebt Neustarts.
    ev_limit_soc: int = 80
    # Harte Grenzen: Default KEINE aktiv (REQ-072); None = Grenze inaktiv
    hard_limit_ev_min_soc: int | None = None
    # Ausnahme von „Default keine": die Obergrenze steht auf 80 %, weil sie die
    # Fahrzeugbatterie schützt (Leo, Issue #9). Sie zu lockern ist ein bewusster
    # Akt — erst `hard_limit_ev_max_soc` anheben, dann `ev_limit_soc`.
    hard_limit_ev_max_soc: int | None = 80
    hard_limit_ww_min_temp: float | None = None

    # --- Dynamische Entladegrenze beim EV-Laden (planner/batt_limit.py) ------
    # Ersetzt die harte Sperre in den PV-Modi: die Batterie darf Netzbezug
    # decken, aber nicht ins Auto entladen. `batt_dyn_aktiv=False` stellt das
    # Verhalten von v0.8.0 wieder her (Notausstieg ohne Deployment).
    batt_dyn_aktiv: bool = True
    batt_dyn_max_w: int = 3000             # Deckel der Entladegrenze (S10E könnte mehr)
    batt_dyn_puffer_w: int = 200           # Kopffreiheit über dem gemessenen Bedarf
    batt_dyn_abbau_w: int = 500            # max. Absenkung je Tick (Dämpfung nach unten)
    batt_dyn_schreibschwelle_w: int = 100  # RSCP-Schreibzugriff erst ab diesem Delta

    # --- Bewusste Batterie-Freigabe ans Auto (Issue #11) ---------------------
    # Zwei getrennte Wege, die Hausbatterie ins Auto zu schicken:
    #   "Schnell" + schnell_batt_nutzen  → max. Leistung aus PV, Batterie UND Netz
    #   Modus "PV+Batterie"              → max. Leistung ohne Netzbezug
    # Beide enden hart bei `soc_reserve_pct`; `priority_soc_pct` gilt dort NICHT,
    # das ist eine Heuristik für die Automatik-Modi — hier hat Leo es angeordnet.
    schnell_batt_nutzen: bool = False
    # Deckel darf über `batt_dyn_max_w` liegen: die dynamische Grenze deckt nur
    # Lücken, die Freigabe soll laden.
    batt_schnell_max_w: int = 5000

    # --- Wärmepumpe, Stufe 2 (REQ-010–014, planner/heatpump.py) --------------
    # Schwellen konservativ nach Leos Festlegung 2026-07-25: an ab 2,5 kW,
    # zurück unter 0,5 kW — bezogen auf den Überschuss NACH der Wallbox.
    #
    # Warmwasser und Heizkreis sind zwei getrennt schaltbare Funktionen auf
    # derselben Anlage (Issue #1). Default: Warmwasser an — das will Leo im
    # Sommer 2026 nutzen; Heizkreis aus — der wird erst mit dem dynamischen
    # Tarif interessant (Stufe 3) und greift ohnehin erst in der Heizperiode.
    wp_ww_aktiv: bool = True           # Warmwasser-Überschussnutzung (Issue #1)
    wp_hk_aktiv: bool = False          # Heizkreis-Anhebung (Issue #1)
    wp_ww_an_w: int = 2500             # Warmwasser-Boost startet ab
    wp_ww_aus_w: int = 500             # darunter zurück auf Normal
    # 57 statt der ursprünglich geplanten 60 °C: die Anlage kommt bei
    # Warmwasser real nur auf ~57,5 °C (belegt am 31.07.2026, fünf Boosts).
    # Mit 60 wurde die Abbruchbedingung „Ziel erreicht" nie wahr und jeder
    # Boost lief stumpf bis zum Wegfall des Überschusses weiter.
    wp_ww_boost_c: float = 57.0        # Boost-Sollwert Warmwasser (Issue #1)
    wp_ww_normal_c: float = 45.0       # Rückstellwert (Issue #1)
    wp_hk_an_w: int = 2500             # Heizkreis-Anhebung startet ab
    wp_hk_aus_w: int = 500
    wp_hk_anhebung_k: float = 1.5      # Anhebung des Raum-Sollwerts
    wp_hk_max_raum_c: float = 23.0     # Komfort-Obergrenze (REQ-012)
    wp_hk_max_aussen_c: float = 15.0   # darüber keine Heizkreis-Anhebung
    wp_leistung_w: int = 2000          # geschätzte el. Leistung im Boost (kein Messwert!)
    wp_min_laufzeit_s: int = 1800      # Mindestlaufzeit je Boost (REQ-064)
    wp_entprellung_s: int = 600        # Bedingungszeit vor dem Start
    wp_aus_entprellung_s: int = 300    # Bedingungszeit vor dem Zurückstellen
    wp_cloud_min_gap_s: int = 900      # Mindestabstand Cloud-Schreibzugriffe (REQ-014)


def load_config() -> RegelConfig:
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return RegelConfig(**{k: v for k, v in data.items() if k in RegelConfig.__dataclass_fields__})
    return RegelConfig()


def save_config(cfg: RegelConfig) -> None:
    """Persistiert sofort — Änderungen wirken ohne Neustart (REQ-073)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def get_or_create_token() -> str:
    """Statischer API-Token, erzeugt beim ersten Start (docs/api-token-auth.md).

    256 Bit Zufall, URL-safe kodiert. Steht danach in /data/api_token und wird
    beim Add-on-Start ins Log geschrieben, damit er in die App übertragen werden kann.
    """
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    return token
