# go-e Wallbox Gemini flexibel

**Rolle:** EV-Ladepunkt — die größte und flexibelste elektrische Last, Hauptstellglied fürs PV-Überschussladen.

## Integration

- **HA:** go-eCharger — ✅ installiert (Update-Entity „go-eCharger" sichtbar). Lokale HTTP-API v2 (kein Cloud-Zwang), alternativ MQTT.
- **Heute:** Steuerung läuft über EVCC (HACS). **Das EMS übernimmt die Wallbox-Steuerung direkt** (lokale API/MQTT), EVCC entfällt (REQ-008). EVCCs Überschussregelung inkl. Phasenumschaltung ist die Funktions-Referenz (REQ-007).

## Fähigkeiten (für das EMS relevant)

- Ladestrom in 1-A-Schritten setzen (6–16 A bei „flexibel" je Anschluss/Konfiguration).
- **Phasenumschaltung 1↔3-phasig** („flexibel"-Modell) → Regelbereich ca. 1,4–11 kW; wichtig für kleinen Überschuss.
- Laden freigeben/sperren, Energie-Limit pro Ladevorgang.
- Lesen: Ladeleistung, geladene Energie, Fahrzeug-Status (angesteckt/lädt).

## Offene Fragen

- [x] ~~Anschluss 11 oder 22 kW?~~ **11 kW** — EVCC-Loadpoint regelt 6–16 A (siehe [evcc-baseline.md](../evcc-baseline.md)).
- [x] ~~Phasenumschaltung nutzbar?~~ **Ja — in EVCC aktiv und im Einsatz** (`chargerPhases1p3p: true`, Hysterese 60 s/180 s).
- [ ] Integration lokal (HTTP/MQTT) oder via Cloud konfiguriert? → steht in der evcc.yaml (vor Migration sichern).
- [ ] Wird die Wallbox auch von Dritten/Gästen genutzt (Gastmodus nötig)?
