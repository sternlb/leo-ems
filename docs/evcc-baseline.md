# EVCC-Baseline (Migrations-Referenz für REQ-008)

**Ausgelesen:** 2026-07-12 via EVCC-REST-API (`http://homeassistant:7070/api/state`) und HA-Supervisor.
**Zweck:** Dokumentiert den Ist-Zustand der EVCC-Installation, bevor das EMS sie ablöst. Jede hier gelistete Funktion/Einstellung muss das EMS übernehmen oder bewusst anders lösen (REQ-007/008).

## Installation

| Eigenschaft | Wert |
|---|---|
| Form | **HA-Add-on** (Slug `49686a9f_evcc`), nicht HACS-Integration |
| Version | 0.310.1 (Update auf 0.311.1 verfügbar) |
| Web-UI | Port 7070, Host-Netzwerk, HA-Ingress aktiv |
| Konfiguration | `evcc.yaml` (Add-on-Option `config_file: /config/evcc.yaml` → liegt auf dem HAOS-Host unter `/addon_configs/49686a9f_evcc/`) + **Geräte-Datenbank** `/data/evcc.db` (Geräte per UI konfiguriert, Referenzen `db:N`) |
| In HA sichtbar | nur `update.evcc_update` — keine Entities, keine Integration |

> ⚠️ **Vor der Ablösung:** `evcc.yaml` + Geräteliste aus der UI sichern (enthalten go-e-IP, E3DC-RSCP-Zugangsdaten, Škoda-Login). Per SSH/Samba auf `/addon_configs/49686a9f_evcc/` zugreifen oder in der EVCC-UI unter Konfiguration abfotografieren/exportieren.

## Site-Regelparameter

| Parameter | Wert | Bedeutung fürs EMS |
|---|---|---|
| `interval` | **10 s** | Regelintervall der Überschussregelung — Referenz für REQ-001/002 |
| `residualPower` | **100 W** | Ziel-Netzbezug (leicht positiv = Batterie-Schonung) |
| `prioritySoc` | **25 %** | Unterhalb 25 % Batterie-SoC hat Hausbatterie-Ladung Vorrang vor dem EV |
| `bufferSoc` / `bufferStartSoc` | 0 / 0 | Kein Batterie-Puffer fürs EV-Laden freigegeben |
| `batteryDischargeControl` | **false** | ❗ Entladesperre ist HEUTE NICHT aktiv — REQ-020 (Must) ist neue Funktionalität, kein Nachbau |
| Tarife (`tariffs`) | leer | Kein dynamischer Tarif konfiguriert (passt zu REQ-030 = Stufe 3) |
| Solar-Forecast (`forecast`) | leer | ❗ Kein PV-Forecast in EVCC — Forecast.Solar (REQ-041, Must) ist ebenfalls neu |
| Währung | EUR | |

## Meter (Site)

| Rolle | db-Ref | Titel | Details |
|---|---|---|---|
| Grid | `db:2` | — | Netz-Bezug/-Einspeisung (via E3DC RSCP) |
| PV | `db:1` | „PV_main" | nur die E3DC-Anlage (Sungrow existiert noch nicht) |
| Batterie | `db:3` | „E3DC bat" | 12 kWh, `controllable: true` — Steuerbarkeit via RSCP bestätigt ✅ |

## Loadpoint „Garage" (`db:5`)

| Parameter | Wert |
|---|---|
| Modus | **pv** (reines Überschussladen) |
| Phasenumschaltung 1p/3p | **aktiv** (`chargerPhases1p3p: true`), aktuell 1-phasig |
| Stromgrenzen | effektiv **6–16 A** → Regelbereich ≈ 1,4–11 kW (Wallbox-Anschluss 11 kW) |
| Hysterese | `enableDelay` 60 s, `disableDelay` 180 s, Schwellen 0 W — Referenz für REQ-064 |
| Ladeplan | keiner konfiguriert (`planTime: null`) — ❗ Zielladung 07:30/50 % (REQ-003) ist neu |
| Fahrzeug-Limit | 80 % (fahrzeugseitig im Enyaq) |
| Priorität | 10 |

## Vehicle „Enyaq iV80" (`db:8`)

| Parameter | Wert |
|---|---|
| Kapazität | 77 kWh |
| Phasen / Strom | 3-phasig, 4–16 A |
| SoC-Anbindung | Škoda-Cloud, liefert live (beim Auslesen: 79,96 %, Reichweite 316 km) ✅ |
| Wiederkehrende Pläne | keine |

## Statistiken (Nutzen-Baseline für REQ-052)

| Zeitraum | Geladen | Solaranteil | Ø Preis |
|---|---:|---:|---:|
| Letzte 30 Tage | 197,7 kWh | **99,4 %** | 0,082 €/kWh |
| Dieses Jahr | 979,6 kWh | 50,4 % | 0,239 €/kWh |
| Letzte 365 Tage | 1.514,6 kWh | 37,9 % | 0,267 €/kWh |

**Interpretation:** Im Sommer lädt EVCC das Auto praktisch vollständig solar (99 %+), übers Jahr sind es ~38–50 %. Das EMS muss den Sommerwert halten und den Jahreswert heben (Zielladung + Forecast + später Tarif). Diese Zahlen sind die Messlatte.

## Konsequenzen für die Migration (REQ-007/008)

**Nachbauen (Ist-Funktionalität):**
1. Überschussregelung mit 10-s-Intervall, `residualPower`-Äquivalent (100 W) und `prioritySoc`-Logik (25 %)
2. 1p/3p-Phasenumschaltung mit Hysterese (60 s / 180 s)
3. Lademodi (aktuell: pv), Fahrzeug-SoC via Škoda-Cloud
4. Session-Tracking + Statistik (kWh, Solaranteil) — nahtlos an obige Baseline anschließen

**Neu (heute nicht vorhanden):**
5. Batterie-Entladesperre beim EV-Laden (REQ-020)
6. Zielladung bis Abfahrtszeit 07:30 / Mindest-SoC 50 % (REQ-003/004)
7. PV-Forecast via Forecast.Solar (REQ-041)
8. Wärmepumpe (Stufe 2), dynamischer Tarif (Stufe 3)

**Offen:**
- [ ] `evcc.yaml` + Geräte-Konfiguration (IPs/Zugangsdaten) vor der Ablösung sichern (siehe Warnung oben)
- [ ] Historie: EVCC-Sessions (`evcc.db`) exportieren, falls die Statistik-Baseline im EMS weitergeführt werden soll
