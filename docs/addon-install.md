# Add-on-Installation auf Home Assistant

Das EMS läuft als **Home-Assistant-Add-on aus einem registrierten Add-on-Repository** (seit 2026-07-23; vorher lokales Add-on, siehe „Historie" unten) — ein Docker-Container auf HAOS, wie EVCC/Zigbee2MQTT. Das Add-on-Manifest (`config.yaml`, `build.yaml`, `Dockerfile`, `run.sh`, `repository.yaml`, `CHANGELOG.md`) liegt in der **Repo-Wurzel**, damit der Build-Kontext `backend/` erreicht und das Repo zugleich als Single-Add-on-Repository gültig ist.

> **Changelog gehört neben die `config.yaml`.** Der Supervisor sucht `CHANGELOG.md` im Add-on-Verzeichnis — hier also die Repo-Wurzel. Fehlte sie (so bis v0.9.0), stand im Update-Dialog „No changelog found for app ed35676c_leo_ems!". Zwei Tests in `backend/tests/test_addon_paket.py` halten fest, dass die Datei existiert **und** einen Abschnitt `## <version>` für die aktuelle Version enthält — ein Update ohne Eintrag zeigt sonst die Änderungen der Vorversion, was schlimmer ist als gar kein Changelog, weil es plausibel aussieht. Gelesen wird aus dem **Store-Klon** des Repos, nicht aus dem installierten Image: ein `git push` plus Store-Reload genügt, ein Versionssprung ist dafür nicht nötig.

> **Start immer über `run.sh`** (`CMD ["/run.sh"]`, Shebang `#!/usr/bin/with-contenv bashio`). Die HA-Basis-Images starten über s6-overlay, das das `CMD` mit **bereinigter Umgebung** ausführt — ein direktes `CMD ["python", …]` sieht weder die `ENV`-Zeilen des Dockerfiles noch den `SUPERVISOR_TOKEN`. Bis v0.6.4 war genau das der Fall: die Wärmepumpe kam nicht an die HA-API, und `/data` wurde nie benutzt (Token, Konfiguration und Beobachtungsdaten waren nach jedem Update weg). Details: [waermepumpe.md](waermepumpe.md).

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
   Für die **Wärmepumpe** (ab v0.4.0) sind `vaillant_ww_entity` und
   `vaillant_zone_entity` bereits vorbelegt; `ha_base_url`/`ha_token` bleiben
   leer, weil das Add-on über den Supervisor-Proxy geht (`homeassistant_api: true`
   in der `config.yaml`). `vaillant_ww_entity` leeren = WP nicht ansteuern.
   Details: [waermepumpe.md](waermepumpe.md).
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
