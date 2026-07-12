# go-e Wallbox Gemini flexibel

**Rolle:** EV-Ladepunkt — die größte und flexibelste elektrische Last, Hauptstellglied fürs PV-Überschussladen.

## Integration

- **HA:** go-eCharger — ✅ installiert (Update-Entity „go-eCharger" sichtbar). Lokale HTTP-API v2 (kein Cloud-Zwang), alternativ MQTT.
- **EVCC:** go-e wird nativ unterstützt (falls Architekturentscheidung Richtung EVCC/Hybrid fällt).

## Fähigkeiten (für das EMS relevant)

- Ladestrom in 1-A-Schritten setzen (6–16 A bei „flexibel" je Anschluss/Konfiguration).
- **Phasenumschaltung 1↔3-phasig** („flexibel"-Modell) → Regelbereich ca. 1,4–11 kW; wichtig für kleinen Überschuss.
- Laden freigeben/sperren, Energie-Limit pro Ladevorgang.
- Lesen: Ladeleistung, geladene Energie, Fahrzeug-Status (angesteckt/lädt).

## Offene Fragen

- [ ] Anschluss 11 kW oder 22 kW? Tatsächlicher A-Regelbereich?
- [ ] Phasenumschaltung automatisch per API nutzbar und mit dem Enyaq problemlos (manche Fahrzeuge mögen häufiges Umschalten nicht)?
- [ ] Integration lokal (HTTP/MQTT) oder via Cloud konfiguriert?
- [ ] Wird die Wallbox auch von Dritten/Gästen genutzt (Gastmodus nötig)?
