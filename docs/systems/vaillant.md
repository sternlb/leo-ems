# Vaillant Wärmepumpe

**Rolle:** Heizung + Warmwasser — größte thermische, verschiebbare Last. Ziel: Warmwasser/Puffer mittags mit PV-Überschuss laden statt abends mit Netzstrom.

## Integration

- **HA:** MyVaillant (Cloud) — ✅ installiert. Entities u.a. `water_heater.home_domestic_hot_water_0`, Climate Zone 1, Betriebsmodus-Sensoren, Away-Mode, Legionellenschutz. Sensor `Vaillant API Request Count` deutet auf aktives Ratenlimit-Monitoring hin.
- **Cloud-Limitierung:** MyVaillant-API ist ratenlimitiert und bietet primär Sollwerte/Modi, keine direkte Leistungsvorgabe.
- **SG-Ready/eBUS: ✅ verdrahtet** (bestätigt 2026-07-12) → lokaler, schneller Steuerweg vorhanden. Präferenz: lokal steuern, Cloud nur lesen/Fallback (REQ-013/014).

## Fähigkeiten (für das EMS relevant)

- Lesen: WW-Temperatur, Betriebsmodus, Zonen-Solltemperaturen.
- Schreiben: WW-Boost / Sollwert-Anhebung, Zeitprogramm-Übersteuerung, Heizkreis-Sollwert.

## Offene Fragen

- [x] ~~SG-Ready-Kontakte verdrahtet?~~ **Ja, SG-Ready/eBUS verdrahtet** (2026-07-12).
- [ ] Welche SG-Ready-Betriebsart ist an der WP konfiguriert (Einschaltempfehlung vs. Zwangslauf)? Kontakt schon mal real geschaltet?
- [ ] Wie ist der Kontakt ansteuerbar — Relais an HA (welches?), Shelly, o.ä.?
- [ ] Wie schnell reagiert die WP auf MyVaillant-Sollwertänderungen (Latenz Cloud → Gerät)?
- [ ] Gibt es einen Pufferspeicher (Heizung) und welches WW-Speichervolumen? Bestimmt das „thermische Batterie"-Potenzial.
- [ ] Mindest-Komfortgrenzen: WW-Temperatur nie unter __ °C, Raumtemperatur-Korridor?
