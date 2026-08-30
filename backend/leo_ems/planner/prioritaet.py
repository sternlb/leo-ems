"""Reihenfolge der Überschussverwertung (Issue #16, docs/priorisierung.md).

Bis v0.17 stand die Reihenfolge fest im Code und war über drei Dateien
verteilt: das Batterie-Tor in `surplus.py`, „Auto vor Wärmepumpe" in
`core/loop.py`. Beides war einzeln gut begründet (Issue #6), aber im Winter ist
eine andere Reihenfolge richtig als im Sommer, und ändern konnte sie niemand.

**Zwei Arten von Einträgen, und der Unterschied ist wichtig.**

*Verbraucher* (Wallbox, Warmwasser) nehmen der Reihe nach aus dem Topf.

*Tore* (die beiden Batterie-Einträge) sind keine Verbraucher. Die Hausbatterie
bekommt nichts zugeteilt — sie nimmt sich, was sonst niemand abruft, und das
regelt die E3DC autonom. Das EMS kann sie nur dadurch bevorzugen, dass es ihren
Anteil **nicht** an andere weiterreicht. Ein Tor sagt deshalb: „Die
Ladeleistung der Batterie steht allem, was unter mir steht, erst zur Verfügung,
wenn der SoC die Schwelle erreicht hat."

Daraus folgt die ganze Rechnung hier: Für jeden Verbraucher zählt die
**höchste** Torschwelle, die über ihm steht. Mehrere Tore übereinander sind
damit kein Sonderfall, und die Standardliste (Tor 25 % → Wallbox → Warmwasser →
Tor 100 %) ergibt exakt das Verhalten von v0.17.
"""

from __future__ import annotations

# Reihenfolge hier = Vorgabe-Reihenfolge. Sie bildet das Verhalten bis v0.17
# ab, damit ein Update nichts verändert, solange niemand etwas umstellt.
STANDARD: tuple[str, ...] = ("batterie_vorrang", "wallbox", "warmwasser", "batterie_voll")

VERBRAUCHER: frozenset[str] = frozenset({"wallbox", "warmwasser"})
# Schwelle je Tor. `None` heißt „aus der Konfiguration" (`priority_soc_pct`);
# `batterie_voll` steht fest auf 100 % (Leo, 2026-08-30) — eine zweite
# einstellbare Zahl ohne belegten Bedarf kostet nur Bedienfläche.
TORE: dict[str, int | None] = {"batterie_vorrang": None, "batterie_voll": 100}

BEKANNT: frozenset[str] = VERBRAUCHER | frozenset(TORE)


def pruefe(liste: object) -> list[str]:
    """Eine Liste validieren — wirft `ValueError` mit lesbarem Grund.

    Bewusst streng: **genau** die bekannten Einträge, jeder genau einmal. Eine
    unvollständige Liste stillschweigend zu ergänzen wäre schlimmer als eine
    Fehlermeldung — der fehlende Eintrag landete dann an einer Stelle, die
    niemand gewählt hat, und niemand würde es merken.
    """
    if not isinstance(liste, (list, tuple)) or not all(isinstance(e, str) for e in liste):
        raise ValueError("Priorität muss eine Liste von Namen sein")
    eintraege = list(liste)
    unbekannt = [e for e in eintraege if e not in BEKANNT]
    if unbekannt:
        raise ValueError("unbekannte Einträge: " + ", ".join(sorted(set(unbekannt))))
    doppelt = [e for e in set(eintraege) if eintraege.count(e) > 1]
    if doppelt:
        raise ValueError("doppelte Einträge: " + ", ".join(sorted(doppelt)))
    fehlt = BEKANNT - set(eintraege)
    if fehlt:
        raise ValueError("fehlende Einträge: " + ", ".join(sorted(fehlt)))
    return eintraege


def normalisiere(liste: object) -> list[str]:
    """Wie `pruefe`, fällt bei Unsinn aber auf die Vorgabe zurück.

    Für den Lesepfad: Eine Konfigurationsdatei aus einer älteren Version kennt
    das Feld nicht, und eine von Hand verbogene soll die Regelschleife nicht
    anhalten. Der Schreibpfad (API) nutzt `pruefe` und lehnt ab — dort steht ein
    Mensch davor, der die Meldung lesen kann.
    """
    try:
        return pruefe(liste)
    except ValueError:
        return list(STANDARD)


def torschwelle(name: str, cfg) -> int:
    """SoC-Schwelle eines Tors in Prozent."""
    fest = TORE[name]
    return int(cfg.priority_soc_pct) if fest is None else fest


def verbraucher_reihenfolge(liste: object, cfg) -> list[tuple[str, int]]:
    """Verbraucher in ihrer Reihenfolge, je mit der für sie geltenden Torschwelle.

    Beispiel Standardliste bei `priority_soc_pct = 25`:

        [("wallbox", 25), ("warmwasser", 25)]

    Das abschließende `batterie_voll` taucht nicht auf — unter ihm steht kein
    Verbraucher mehr, es ist der Normalfall „der Rest geht in die Batterie".
    Zieht man es dagegen nach oben, erscheint es als Schwelle 100 bei allen
    Verbrauchern darunter.
    """
    hoechste = 0
    raus: list[tuple[str, int]] = []
    for eintrag in normalisiere(liste):
        if eintrag in TORE:
            hoechste = max(hoechste, torschwelle(eintrag, cfg))
        else:
            raus.append((eintrag, hoechste))
    return raus
