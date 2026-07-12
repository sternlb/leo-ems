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
| 1. Requirements | [specs/01-requirements.md](specs/01-requirements.md) | ✅ abgeschlossen (2026-07-12) |
| 2. Spezifikation | [specs/02-specification.md](specs/02-specification.md) | ✅ abgenommen für Stufe 1 (2026-07-12) |
| 3. Architektur/Design | [specs/03-architecture.md](specs/03-architecture.md) | 🔵 laufend (ADR-001–003 entschieden) |
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

**Phase 1 (Requirements) ist abgeschlossen** (2026-07-12): 39 Requirements, priorisiert per MoSCoW — 26 Must, 13 Should, 3 Won't — gegliedert in drei Ausbaustufen (1: EVCC-Ersatz, 2: Wärmepumpe, 3: dynamischer Tarif). Einzige offene Flanke: die 70 %-Frage für die Neuanlage (REQ-043, wartet auf den Elektriker). Nächster Schritt: Phase 2 — testbare Spezifikation der Stufe-1-Musts.

**Architektur-Richtung (2026-07-12):** Eigenbau — das EMS ersetzt die bestehende EVCC-Installation (läuft als HA-Add-on, Baseline in [docs/evcc-baseline.md](docs/evcc-baseline.md)) und bildet deren Lade-Funktionen äquivalent nach. Die UI wird eine **eigenständige, LAN-lokale App** (kein HA-Dashboard). Nur der Tech-Stack wird noch in Phase 3 entschieden.
