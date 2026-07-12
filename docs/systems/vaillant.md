# Vaillant Wärmepumpe

**Rolle:** Heizung + Warmwasser — größte thermische, verschiebbare Last. Ziel: Warmwasser/Puffer mittags mit PV-Überschuss laden statt abends mit Netzstrom.

## Integration

- **HA:** MyVaillant (Cloud) — ✅ installiert. Entities u.a. `water_heater.home_domestic_hot_water_0`, Climate Zone 1, Betriebsmodus-Sensoren, Away-Mode, Legionellenschutz. Sensor `Vaillant API Request Count` deutet auf aktives Ratenlimit-Monitoring hin.
- **Cloud-Limitierung:** MyVaillant-API ist ratenlimitiert und bietet primär Sollwerte/Modi, keine direkte Leistungsvorgabe.
- **Alternative:** SG-Ready-Kontakte (falls verdrahtet) oder eBUS (ebusd) für lokale, schnelle Steuerung.

## Fähigkeiten (für das EMS relevant)

- Lesen: WW-Temperatur, Betriebsmodus, Zonen-Solltemperaturen.
- Schreiben: WW-Boost / Sollwert-Anhebung, Zeitprogramm-Übersteuerung, Heizkreis-Sollwert.

## Offene Fragen

- [ ] SG-Ready-Kontakte an der WP verdrahtet/nutzbar? (Wäre der robustere Steuerweg als Cloud.)
- [ ] Wie schnell reagiert die WP auf MyVaillant-Sollwertänderungen (Latenz Cloud → Gerät)?
- [ ] Gibt es einen Pufferspeicher (Heizung) und welches WW-Speichervolumen? Bestimmt das „thermische Batterie"-Potenzial.
- [ ] Mindest-Komfortgrenzen: WW-Temperatur nie unter __ °C, Raumtemperatur-Korridor?
