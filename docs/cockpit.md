# EMS-Cockpit — Auswertung des Beobachtungsmodus

**URL (fest, v1 seit 12.07.2026):** https://claude.ai/code/artifact/d711d336-f2bc-48c2-acbe-6c301b3ad352

Das Cockpit ist eine von Claude gepflegte **Artifact-Webseite mit fester URL** (Basel-AI-Branding). Es zeigt die Auswertung des Beobachtungsmodus: Was hätte das EMS getan vs. was hat EVCC real gemacht — die Entscheidungsgrundlage für die Umschaltung (REQ-008/052).

## So aktualisierst du es

In einer Claude-Session einfach sagen: **„aktualisiere mein EMS-Cockpit"**. Claude ruft dann die Auswertungs-API des Add-ons ab und veröffentlicht das Cockpit neu — die URL bleibt gleich.

Damit das klappt, braucht Claude die Zugangsdaten in einer lokalen Datei **`cockpit.env`** in der Repo-Wurzel (steht in `.gitignore`, landet nie auf GitHub):

```
LEO_EMS_HOST=192.168.178.150:8099
LEO_EMS_TOKEN=<API-Token aus dem Add-on-Log>
```

## Datenquellen (API v1)

| Endpunkt | Inhalt |
|---|---|
| `GET /api/v1/observation/summary` | Aggregat: Zeitraum, Ø/Max-Überschuss, „EMS hätte geladen" vs. „Wallbox real" (kWh), Tages-Tabelle |
| `GET /api/v1/observation/snapshots?limit=N` | Rohdaten je 10-s-Tick (Verlaufscharts) |
| `GET /api/v1/status` | Live-Zustand inkl. `read_only`-Flag und Klartext-Begründung |

Beispiel-Abruf:

```sh
curl -s -H "Authorization: Bearer $LEO_EMS_TOKEN" "http://$LEO_EMS_HOST/api/v1/observation/summary"
```

## Kennzahlen im Cockpit

- **EMS hätte geladen (kWh)** — Summe der Entscheidungen der Regelschleife (Strom × Phasen × 230 V je Tick)
- **Wallbox real (kWh)** — gemessene Ladeleistung (= EVCC, solange der Beobachtungsmodus läuft)
- **Delta/Deckung** — wie ähnlich sich EMS und EVCC verhalten; Ziel vor der Umschaltung: plausible Übereinstimmung über ≥ 2 Wochen
- **Überschuss-Profil** — Ø/Max je Tag, Batteriesoc-Verlauf
- Referenzlinie: **EVCC-Baseline** (99,4 % Solaranteil/30 d, docs/evcc-baseline.md)

## Beobachtungsmodus an/aus

`read_only` steht per Default auf `true` (gefahrlose Erstinstallation). Scharfschalten — erst nach der Beobachtungsphase:

```sh
curl -s -X PUT -H "Authorization: Bearer $LEO_EMS_TOKEN" -H "Content-Type: application/json" \
  -d '{"read_only": false}' "http://$LEO_EMS_HOST/api/v1/config"
```
