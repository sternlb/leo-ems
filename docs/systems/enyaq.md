# Škoda Enyaq

**Rolle:** E-Auto — Ziel und Randbedingung des Überschussladens: liefert SoC und Ladeziel, definiert über Abfahrtszeiten die harte Deadline der Ladeplanung.

## Integration

- **HA:** Škoda-Integration — ✅ installiert. Entities u.a. SoC/Software-Sensoren, Türen/Verriegelung, `climate.skoda_enyaq_air_conditioning`, „Battery Protection".
- **Charakter:** Cloud-API (Škoda Connect) — Latenz und gelegentliche Aussetzer einplanen; SoC-Werte können veraltet sein, solange das Auto „schläft".

## Fähigkeiten (für das EMS relevant)

- Lesen: SoC (zentral für Ziel-/Mindestladung REQ-003/004), Ladelimit, Steckerstatus.
- Schreiben (begrenzt): Ladelimit, Laden starten/stoppen, Klimatisierung — primäres Stellglied bleibt aber die Wallbox.

## Offene Fragen

- [ ] Wie aktuell/zuverlässig ist der SoC über die Cloud während des Ladens? (Sonst SoC-Schätzung über Wallbox-Zähler nötig.)
- [ ] Typische Abfahrtszeiten und Pendel-Muster (Neumarkt-Tage)? Fester Wochenplan oder Kalender-gesteuert?
- [ ] Mindest-SoC, der immer verfügbar sein muss?
- [ ] Fahrzeugseitiges Ladelimit (z.B. 80 %) fest — und soll das EMS es situativ anheben dürfen (vor Langstrecke)?
