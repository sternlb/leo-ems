# Škoda Enyaq

**Rolle:** E-Auto — Ziel und Randbedingung des Überschussladens: liefert SoC und Ladeziel, definiert über Abfahrtszeiten die harte Deadline der Ladeplanung.

## Integration

- **HA:** Škoda-Integration — ✅ installiert. Entities u.a. SoC/Software-Sensoren, Türen/Verriegelung, `climate.skoda_enyaq_air_conditioning`, „Battery Protection".
- **Charakter:** Cloud-API (Škoda Connect) — Latenz und gelegentliche Aussetzer einplanen; SoC-Werte können veraltet sein, solange das Auto „schläft".

## Fähigkeiten (für das EMS relevant)

- Lesen: SoC (zentral für Ziel-/Mindestladung REQ-003/004), Ladelimit, Steckerstatus.
- Schreiben (begrenzt): Ladelimit, Laden starten/stoppen, Klimatisierung — primäres Stellglied bleibt aber die Wallbox.

## Offene Fragen

- [x] ~~SoC über Cloud zuverlässig?~~ **Ja — EVCC nutzt den Cloud-SoC produktiv** (Baseline-Auslesung: 79,96 % live, Reichweite 316 km). Langzeitverhalten beim Laden weiter beobachten.
- [ ] Typische Abfahrtszeiten und Pendel-Muster (Neumarkt-Tage)? Fester Wochenplan oder Kalender-gesteuert?
- [ ] Mindest-SoC, der immer verfügbar sein muss?
- [ ] Fahrzeugseitiges Ladelimit (z.B. 80 %) fest — und soll das EMS es situativ anheben dürfen (vor Langstrecke)?
