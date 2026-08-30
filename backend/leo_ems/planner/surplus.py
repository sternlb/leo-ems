"""Überschussberechnung — Spec §2 (REQ-001/040).

Vorzeichenkonvention: p_netz_w > 0 = Bezug, < 0 = Einspeisung.
p_batterie_w > 0 = Batterie lädt (E3DC-Konvention, siehe Baseline).
"""

from __future__ import annotations

from ..config import RegelConfig


def berechne_ueberschuss(
    p_lade_ist_w: float,
    p_netz_w: float,
    p_batterie_w: float,
    soc_batterie_pct: float,
    cfg: RegelConfig,
    *,
    mit_batterie: bool = False,
    tor_soc_pct: int | None = None,
) -> float:
    """Verfügbare Leistung für den Loadpoint (Spec §2).

    P_überschuss = P_lade_ist − P_netz − P_residual
    Batterie-Behandlung: Ab der Torschwelle (`tor_soc_pct`, sonst prioritySoc)
    darf der Verbraucher der Batterie die Ladeleistung "wegnehmen" — darunter
    hat die Hausbatterie Vorrang.

    `mit_batterie=True` liefert das Budget für den Modus „PV+Batterie" (Issue
    #11): dort fällt der Batterie-Term **ganz** weg, übrig bleibt die Leistung,
    die der Standort bei Netzbezug ≈ `residual_power_w` insgesamt liefern kann —
    PV und Batterie zusammen, ohne sie trennen zu müssen. Der Abzug der
    Entladung wäre hier falsch herum: die Batterie deckt, das Budget sänke, der
    Ladestrom fiele, die Batterie deckte weniger — der Ladevorgang würde sich
    selbst herunterregeln. Die Formel ohne Batterie-Term ist dagegen stationär
    selbstkonsistent (dieselbe Überlegung wie in planner/batt_limit.py) und
    begrenzt sich von allein: stößt die Batterie an ihre Entladegrenze, wird
    `p_netz_w` positiv und das Budget fällt.
    """
    ueberschuss = p_lade_ist_w - p_netz_w - cfg.residual_power_w
    if mit_batterie:
        return ueberschuss
    # `tor_soc_pct` ist die Schwelle, ab der die Batterie ihre Ladeleistung an
    # diesen Verbraucher abgibt. Sie kommt seit v0.18 aus der Prioritätenliste
    # (Issue #16) und kann je Verbraucher verschieden sein — steht ein zweites
    # Batterie-Tor über nur einem von beiden, gilt sie auch nur für ihn. Ohne
    # Angabe bleibt es bei `priority_soc_pct`, dem Verhalten bis v0.17.
    tor = cfg.priority_soc_pct if tor_soc_pct is None else tor_soc_pct
    if soc_batterie_pct >= tor and p_batterie_w > 0:
        ueberschuss += p_batterie_w
    elif p_batterie_w < 0:
        # Entladung ist kein Überschuss. Seit der dynamischen Entladegrenze
        # (planner/batt_limit.py) darf die Batterie beim Laden Netzbezug decken —
        # ohne diesen Abzug sähe die Wallbox genau diese Deckung als zusätzlichen
        # Überschuss und würde sich selbst aus der Batterie speisen.
        ueberschuss += p_batterie_w
    return ueberschuss
