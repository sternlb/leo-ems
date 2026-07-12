# Vaillant Wärmepumpe

**Rolle:** Heizung + Warmwasser — größte thermische, verschiebbare Last. Ziel: Warmwasser/Puffer mittags mit PV-Überschuss laden statt abends mit Netzstrom.

## Integration

- **HA:** MyVaillant (Cloud) — ✅ installiert. Entities u.a. `water_heater.home_domestic_hot_water_0`, Climate Zone 1, Betriebsmodus-Sensoren, Away-Mode, Legionellenschutz. Sensor `Vaillant API Request Count` deutet auf aktives Ratenlimit-Monitoring hin.
- **Cloud-Limitierung:** MyVaillant-API ist ratenlimitiert und bietet primär Sollwerte/Modi, keine direkte Leistungsvorgabe.
- **Anbindung (korrigiert 2026-07-12):** Das Vaillant-**Internetmodul hängt am eBUS** — es gibt keinen separaten SG-Ready-Kontakt. Steuerweg ist damit die **MyVaillant-Cloud** (REQ-013/014). Lokaler eBUS-Direktzugang (ebusd + Koppler) bliebe eine spätere Nachrüst-Option.

## Fähigkeiten (für das EMS relevant)

- Lesen: WW-Temperatur, Betriebsmodus, Zonen-Solltemperaturen.
- Schreiben: WW-Boost / Sollwert-Anhebung, Zeitprogramm-Übersteuerung, Heizkreis-Sollwert.

## Offene Fragen

- [x] ~~SG-Ready-Kontakte verdrahtet?~~ **Nein — Internetmodul am eBUS, Steuerung via MyVaillant-Cloud** (korrigiert 2026-07-12).
- [ ] Reichen die Cloud-Stellgrößen (WW-Boost, Sollwert-Anhebung) praktisch fürs Überschuss-Vorziehen? → Praxistest in Phase 2.
- [ ] Wie schnell reagiert die WP auf MyVaillant-Sollwertänderungen (Latenz Cloud → Gerät)?
- [ ] Gibt es einen Pufferspeicher (Heizung) und welches WW-Speichervolumen? Bestimmt das „thermische Batterie"-Potenzial.
- [ ] Mindest-Komfortgrenzen: WW-Temperatur nie unter __ °C, Raumtemperatur-Korridor?
