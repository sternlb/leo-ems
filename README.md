# Leo-EMS

Energy Management System für den Haushalt Basel Latour — läuft auf Home Assistant und koordiniert Erzeuger, Speicher und flexible Lasten nach einer gemeinsamen Strategie.

## Warum

Die Analyse der realen Messdaten 2025 zeigt: Der Engpass ist nicht die PV-Erzeugung, sondern **Speicher + zeitgleicher Verbrauch**. Mehr Module allein erhöhen vor allem die Einspeisung. Die echten Hebel sind Lastverschiebung — E-Auto und Wärmepumpe in den PV-Überschuss legen, die Batterie intelligent führen. Genau das ist der Job dieses EMS.

## Systemlandschaft

| System | Rolle |
|---|---|
| E3DC S10E Infinity | 9,23 kWp PV + 12 kWh Batterie (Hauskraftwerk), HA-Integration via RSCP |
| Sungrow SG 6.0RT *(geplant)* | Wechselrichter Garagendach-Anlage, 5,64 kWp Ost/West, AC-gekoppelt |
| Vaillant Wärmepumpe | Heizung + Warmwasser, HA-Integration via MyVaillant |
| go-e Wallbox Gemini flexibel | EV-Laden, HA-Integration via go-eCharger |
| Škoda Enyaq | E-Auto (SoC, Ladeziel), eigene HA-Integration |
| Home Assistant | Zentrale (2026.7.x) |

## Vorgehen: Spec-Driven Development

Erst die Spezifikation, dann der Code. Jede Phase erzeugt ein prüfbares Artefakt in `specs/`:

| Phase | Artefakt | Status |
|---|---|---|
| 1. Requirements | [specs/01-requirements.md](specs/01-requirements.md) | 🔵 laufend |
| 2. Spezifikation | specs/02-specification.md | ⚪ offen |
| 3. Architektur/Design (ADR: Tech-Stack, UI-Form) | specs/03-architecture.md | ⚪ offen |
| 4. Implementierung | src/ | ⚪ offen |
| 5. Test/Validierung | Testprotokolle | ⚪ offen |

Die Vision und die Ziele stehen in [specs/00-vision.md](specs/00-vision.md). Geräteprofile mit Integrationsdetails und offenen Fragen liegen unter [docs/systems/](docs/systems/).

## Repo-Struktur

```
specs/          Spezifikationen (eine Datei pro SDD-Phase)
docs/systems/   Geräteprofile: Fähigkeiten, Schnittstellen, offene Fragen
src/            Implementierung (ab Phase 4)
```

## Status

Phase 1 (Requirements) läuft. Der Katalog in `specs/01-requirements.md` enthält Kandidaten im Status *Entwurf*; am Phasenende werden sie gemeinsam sortiert und per MoSCoW priorisiert.

**Architektur-Richtung (2026-07-12):** Eigenbau — das EMS ersetzt die bestehende EVCC-Installation und bildet deren Lade-Funktionen äquivalent nach. Tech-Stack und UI-Form (HA-Dashboard vs. separate App) werden in Phase 3 entschieden.
