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
) -> float:
    """Verfügbare Leistung für den Loadpoint (Spec §2).

    P_überschuss = P_lade_ist − P_netz − P_residual
    Batterie-Behandlung: Ab prioritySoc darf das EV der Batterie die
    Ladeleistung "wegnehmen" — darunter hat die Hausbatterie Vorrang.
    """
    ueberschuss = p_lade_ist_w - p_netz_w - cfg.residual_power_w
    if soc_batterie_pct >= cfg.priority_soc_pct and p_batterie_w > 0:
        ueberschuss += p_batterie_w
    elif p_batterie_w < 0:
        # Entladung ist kein Überschuss. Seit der dynamischen Entladegrenze
        # (planner/batt_limit.py) darf die Batterie beim Laden Netzbezug decken —
        # ohne diesen Abzug sähe die Wallbox genau diese Deckung als zusätzlichen
        # Überschuss und würde sich selbst aus der Batterie speisen.
        ueberschuss += p_batterie_w
    return ueberschuss
