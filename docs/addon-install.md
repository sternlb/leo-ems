# Add-on-Installation auf Home Assistant

Das EMS läuft als **Home-Assistant-Add-on aus einem registrierten Add-on-Repository** (seit 2026-07-23; vorher lokales Add-on, siehe „Historie" unten) — ein Docker-Container auf HAOS, wie EVCC/Zigbee2MQTT. Das Add-on-Manifest (`config.yaml`, `build.yaml`, `Dockerfile`, `repository.yaml`) liegt in der **Repo-Wurzel**, damit der Build-Kontext `backend/` erreicht und das Repo zugleich als Single-Add-on-Repository gültig ist.

## Zielsystem (verifiziert 2026-07-12)

- **Home Assistant OS 18.1**, Supervisor 2026.06, Core 2026.7.1
- **Board:** Raspberry Pi 5 → Architektur **`aarch64`** (in `build.yaml` abgedeckt)
- **HA-IP im LAN:** `192.168.178.150` → Backend/App unter `http://192.168.178.150:8099`

## Installation (Add-on-Repository)

1. **Repository registrieren:** Einstellungen → Add-ons → Add-on-Store → ⋮ → *Repositories* → `https://github.com/sternlb/leo-ems` eintragen. Voraussetzung ist die `repository.yaml` in der Repo-Wurzel (name/url/maintainer).
2. **Installieren:** „Leo-EMS" erscheint unter dem neuen Repository (Supervisor baut das Image für aarch64 aus `build.yaml`).
3. **Konfigurieren** (Tab *Konfiguration*): Geräte-Zugangsdaten eintragen —
   `e3dc_host/user/password/rscp_key`, `goe_host`, `skoda_user/password`, `lat`/`lon`
   (Sungrow leer lassen bis zur Installation Ende 2026). Zugangsdaten liegen nur hier, nie im Code.
4. **`Watchdog` aktivieren** (Tab *Info*, Schalter „Watchdog") — startet das Add-on bei Absturz neu; wird bei einer Neuinstallation nicht automatisch übernommen.
5. **Sidebar-Panel aktivieren** (Tab *Info*, Schalter „Zur Seitenleiste hinzufügen") — Ingress-Panel ist nach der Installation noch aus; per API nicht setzbar.
6. **Starten.** Im *Protokoll* erscheinen der API-Token (einmalig, für die App) und die Liste der verbundenen Geräte.
7. **Updates:** laufen automatisch (`auto_update: true`) — ein `git push` auf `main` reicht, Supervisor erkennt die neue Version im Repository selbst (kein SSH/`git pull` auf dem Pi mehr nötig).

## Netzwerk & Sicherheit

- `host_network: true` — nötig für RSCP (E3DC), go-e-HTTP, Modbus (Sungrow) und mDNS-Erreichbarkeit der App; das Backend lauscht direkt auf Port **8099** im LAN.
- API ist Token-geschützt (`docs/api-token-auth.md`).
- `watchdog` auf `/api/v1/health` — der Supervisor startet das Add-on bei Absturz neu (ergänzt das Lease/TTL-Fail-Safe, Spec §7/E6).

## Historie: lokales Add-on (bis 2026-07-23)

Ursprünglich lief das EMS als **lokales Add-on** (Ordner `/addons/leo-ems/` per `git clone`/SSH auf dem Host, vom Supervisor automatisch als „Lokales Add-on" erkannt, Slug `local_leo_ems`). Updates erforderten dort jedes Mal einen manuellen `git pull` auf dem Pi **und** einen manuellen Store-Reload (`homeassistant.update_entity`) in HA, bevor der Update-Button erschien — anders als bei Repository-Add-ons, die Supervisor selbst klont und periodisch prüft. Der Wechsel auf ein registriertes Repository (`repository.yaml`) behebt das: gleiche Konfiguration, aber automatische Update-Erkennung wie bei jedem anderen Add-on aus dem Store.

Das alte lokale Add-on (`local_leo_ems`) blieb zur Sicherheit zunächst **gestoppt, aber installiert** als Rückfalloption; kann nach ein paar Tagen Beobachtung deinstalliert werden.
