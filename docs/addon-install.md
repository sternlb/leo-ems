# Add-on-Installation auf Home Assistant

Das EMS läuft als **lokales Home-Assistant-Add-on** (ADR-001) — ein Docker-Container auf HAOS, wie EVCC. Das Add-on-Manifest (`config.yaml`, `build.yaml`, `Dockerfile`) liegt in der **Repo-Wurzel**, damit der Build-Kontext `backend/` erreicht.

## Zielsystem (verifiziert 2026-07-12)

- **Home Assistant OS 18.1**, Supervisor 2026.06, Core 2026.7.1
- **Board:** Raspberry Pi 5 → Architektur **`aarch64`** (in `build.yaml` abgedeckt)
- **HA-IP im LAN:** `192.168.178.150` → Backend/App später unter `http://192.168.178.150:8099`

## Installation (lokales Add-on)

1. **Repo auf den HA-Host holen** — per Samba/SSH nach `/addons/leo-ems/` (der Ordner unter `/addons/` wird vom Supervisor als lokales Add-on erkannt):
   ```sh
   # via SSH-Add-on auf dem HA-Host
   git clone https://github.com/sternlb/leo-ems /addons/leo-ems
   ```
2. **Add-on-Store neu laden:** Einstellungen → Add-ons → Add-on-Store → ⋮ → *Nach Updates suchen*. „Leo-EMS" erscheint unter „Lokale Add-ons".
3. **Installieren** (Supervisor baut das Image für aarch64 aus `build.yaml`).
4. **Konfigurieren** (Tab *Konfiguration*): Geräte-Zugangsdaten eintragen —
   `e3dc_host/user/password/rscp_key`, `goe_host`, `skoda_user/password`, `lat`/`lon`
   (Sungrow leer lassen bis zur Installation Ende 2026). Zugangsdaten liegen nur hier, nie im Code.
5. **Starten.** Im *Protokoll* erscheinen der API-Token (einmalig, für die App) und die Liste der verbundenen Geräte.
6. **Update später:** `git pull` in `/addons/leo-ems`, dann Add-on neu bauen/starten.

## Netzwerk & Sicherheit

- `host_network: true` — nötig für RSCP (E3DC), go-e-HTTP, Modbus (Sungrow) und mDNS-Erreichbarkeit der App; das Backend lauscht direkt auf Port **8099** im LAN.
- API ist Token-geschützt (`docs/api-token-auth.md`).
- `watchdog` auf `/api/v1/health` — der Supervisor startet das Add-on bei Absturz neu (ergänzt das Lease/TTL-Fail-Safe, Spec §7/E6).

## Hinweis zum Teststand

Die Backend-Logik ist mit 31 Unit-Tests abgesichert (auf dem Entwicklungsrechner). Das Add-on-**Image selbst wurde noch nicht auf dem Pi gebaut/gestartet** — das ist der nächste reale Schritt (zusammen mit dem 2-Wochen-Beobachtungsmodus parallel zu EVCC, siehe `specs/03-architecture.md`).
