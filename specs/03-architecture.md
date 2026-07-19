# 03 — Architektur & Design (Stufe 1)

**Status:** Entwurf, Kernentscheidungen von Leo getroffen (ADR-001–003). **Stand:** 2026-07-12
**Grundlage:** [02-specification.md](02-specification.md) — insbesondere API v1 (§9.1), Fail-Safe-Matrix (§7) und TTL-Prinzip (§5.1).

---

## Architekturentscheidungen (ADRs)

### ADR-001 — Laufzeit: eigenes HA-Add-on ✅ (Leo, 2026-07-12)

Der EMS-Kern läuft als **eigenes Home-Assistant-Add-on** (Docker-Container auf HAOS, wie EVCC heute).

- **Begründung:** Vorhandene Infrastruktur (Supervisor: Backup, Watchdog, Updates), Host-Netzwerk für RSCP/Modbus/go-e, kein zusätzliches Gerät.
- **Konsequenzen:** Eigenes Add-on-Repository (Dockerfile + `config.yaml`), Installation über „eigene Repositories" im Add-on-Store. HA-Ausfall = EMS-Ausfall — akzeptiert, da Fail-Safe (Spec §7/E6) alle Geräte autonom weiterlaufen lässt.
- **Verworfen:** separater Host (Mehraufwand), AppDaemon (eigene API/App-Auslieferung unhandlich).

### ADR-002 — Backend: Python 3.12 + asyncio ✅ (Leo, 2026-07-12)

- **Framework:** FastAPI + Uvicorn (REST + WebSocket, OpenAPI-Schema gratis → Client-Generierung für die Android-App).
- **Gerätebibliotheken:** `pye3dc` (E3DC RSCP), `myskoda` (Enyaq), `aiohttp` (go-e lokale HTTP-API v2, Forecast.Solar), `pymodbus` (Sungrow, ab Ende 2026), `myPyllant` (Vaillant, Stufe 2).
- **Persistenz:** SQLite (eine Datei im Add-on-Datenverzeichnis `/data`): Konfiguration, Regeln, Entscheidungs-Log, Statistik.
- **Verworfen:** Go (RSCP-/Škoda-Bibliotheken müssten portiert werden), C#/.NET (dünnes Geräte-Ökosystem).

### ADR-003 — UI: native Android-App ✅ (Leo, 2026-07-12)

- **Stack:** Kotlin + Jetpack Compose; Retrofit/OkHttp gegen die lokale API v1, OkHttp-WebSocket für Live-Daten.
- **Erreichbarkeit:** LAN-only per Design (REQ-074). Backend-Adresse: `http://homeassistant.local:<port>` via mDNS-Discovery, manuelle IP als Fallback (Einstellungs-Screen).
- **Verteilung:** APK-Sideload auf die Haushalts-Geräte (alle Android); kein Store-Zwang.
- **Konsequenz Benachrichtigungen (REQ-053, Should):** Ohne Cloud-Push erhält die App Alarme nur im LAN (WebSocket/Polling). Für Unterwegs-Alarme später optional Brücke über die HA-Companion-App — bewusst NICHT Stufe 1.
- **Verworfen:** PWA (Leo bevorzugt natives App-Gefühl), da alle Nutzer-Geräte Android sind.

### ADR-004 — Geräteanbindung: direkt, nicht über HA-Entities

Das EMS spricht die Geräte **direkt** an (RSCP, go-e-HTTP, Škoda-Cloud, Modbus) — wie EVCC. HA-Entities werden NICHT als Steuer- oder Messpfad benutzt.

- **Begründung:** Kein Umweg über HA-Polling-Latenz; 10-s-Regelintervall braucht frische Werte; EMS bleibt von HA-Core-Restarts unabhängig (nur der Container-Host ist gemeinsam).
- **Optional (Could, später):** Status-Spiegel als MQTT-Entities (Mosquitto vorhanden) für HA-Automationen/Anzeigen.

### ADR-005 — Fail-Safe als Architekturprinzip: Leases statt Zustände

Jede Übersteuerung (Entladesperre, Garantieladung, Override) wird intern als **Lease mit Ablaufzeit** modelliert (Spec §5.1: TTL 15 min, zyklisch erneuert). Es gibt keinen Codepfad, der einen Geräte-Zustand „dauerhaft" setzt. Ein zentraler `SafetyGuard` validiert jeden Befehl (Spec §8.3) und verwaltet die Leases.

---

## Komponentenschnitt (Backend)

```
leo-ems Add-on (Docker, host network)
│
├── core/            Regelschleife (10 s Tick): liest Messwerte, ruft Planner, gibt Befehle
├── planner/         Überschussrechnung (§2), Lademodi (§3), Zustandsmaschine (§4.1/4.2),
│                    Zielladungs-Planung mit Regelliste (§4.3)
├── devices/         Adapter je Gerät hinter gemeinsamem Interface:
│   ├── e3dc.py        (pye3dc/RSCP: Messwerte + Entladesperre)
│   ├── goe.py         (HTTP v2: Strom, Phasen, Freigabe)
│   ├── skoda.py       (myskoda: SoC, Steckerstatus)
│   ├── forecast.py    (Forecast.Solar)
│   ├── sungrow.py     (pymodbus — bis Installation: Stub liefert 0 W)
│   └── simulator/     Simulatoren je Adapter für Tests (T1–T8) und Entwicklung
├── safety/          SafetyGuard: Grenzen-Validierung, Lease-Verwaltung, Schaltfrequenz-Schutz
├── store/           SQLite: Config, Regeln, Entscheidungs-Log (JSON-Zeilen), Statistik
└── api/             FastAPI: REST /api/v1/* + WS /api/v1/live (Spec §9.1), statische Doku
```

**Datenfluss eines Ticks:** `devices → core (Messbild) → planner (Entscheidung) → safety (Validierung + Lease) → devices (Befehl) → store (Log)`.

Jeder Geräteadapter implementiert dasselbe Interface (`read() / command()` + Frische-Zeitstempel) — die Fail-Safe-Matrix (§7) wird zentral im `core` anhand der Frische-Zeitstempel ausgewertet, nicht in jedem Adapter einzeln.

## Android-App (Struktur)

| Screen | Inhalt (Spec-Referenz) |
|---|---|
| **Dashboard** | Energiefluss: Erzeugung, Hausverbrauch, Wallbox, Batterie (inkl. Sperr-Status), Prognose, Klartext-Begründung (§9.2, REQ-050/051) |
| **Laderegeln** | Regelliste: Wochentage + Uhrzeit + Mindest-SoC, anlegen/ändern/deaktivieren/löschen (§4.3, REQ-070) |
| **Einstellungen** | Lademodus, SoC-Reserve, residualPower/prioritySoc, harte Grenzen, Backend-Adresse (REQ-071/072) |
| **Protokoll** | Entscheidungs-Log + Kennzahlen-Historie (REQ-062, REQ-052-Vorbereitung) |

API-Client wird aus dem OpenAPI-Schema des Backends generiert — App und Backend können nicht auseinanderlaufen.

## Repo-Struktur (Ziel)

```
leo-ems/
├── specs/            (bestehend)
├── docs/             (bestehend)
├── backend/          Python-Paket: core, planner, devices, safety, store, api + tests/
├── config.yaml       HA-Add-on-Manifest (Wurzel), build.yaml, Dockerfile
└── app/              Android-Studio-Projekt (Kotlin, Compose)
```

## Teststrategie

- **Unit/Verhalten:** pytest gegen die Simulatoren — jeder Abnahmetest T1–T8 (Spec §10) als automatisierter Test, Zeit wird simuliert (kein Echtzeit-Warten).
- **Watchdog-Test (T4):** Integrationstest — Container kill, prüfen dass die E3DC-Sperre binnen TTL ausläuft (gegen den E3DC-Simulator; einmalig real vor der EVCC-Ablösung).
- **Migrationstest (REQ-008):** EMS zwei Wochen parallel zu EVCC im Beobachtungsmodus (nur messen/loggen, nicht steuern), Solaranteil vergleichen; erst dann EVCC deaktivieren.

## Offene Punkte — Backlog (laufend)

- [ ] **Deployment ohne manuellen `git pull` (2026-07-19):** Aktuell ist Leo-EMS ein **lokales Add-on** (`git clone`/`git pull` per SSH nach `/addons/leo-ems`, siehe [docs/addon-install.md](../docs/addon-install.md)) — jedes Update braucht einen manuellen Schritt auf dem Pi. ADR-001 sieht eigentlich ein **Add-on-Repository** vor („Installation über 'eigene Repositories' im Add-on-Store"); das wurde bisher nicht genutzt. Lösungsrichtung: das leo-ems-GitHub-Repo unter Einstellungen → Add-ons → Add-on-Store → Repositories als eigene Repository-URL eintragen (statt lokalem Ordner) — der Supervisor prüft dann selbst auf neue Versionen und kann sie automatisch installieren (Auto-Update-Schalter). Voraussetzung: `repository.yaml` im Repo-Root, saubere Versions-Tags statt jedes Commit als Update zu werten. Aufwand: einmalige Einrichtung, danach entfällt der manuelle Pull komplett.

## Offene Punkte Phase 3 — alle geschlossen (2026-07-12)

- [x] **API-Absicherung:** statischer Bearer-Token (Leo folgt der Empfehlung). Ausführliches Konzept inkl. Bedrohungsmodell und verworfener Alternativen: [docs/api-token-auth.md](../docs/api-token-auth.md). Implementiert in `config.get_or_create_token()` + `api.require_token()`.
- [x] **Add-on-Basis:** HA-Base-Image Python 3.12/Alpine, **aarch64** (Pi 5), **Port 8099** — Manifest an der Repo-Wurzel ([config.yaml](../config.yaml), [build.yaml](../build.yaml), [Dockerfile](../Dockerfile)); Installation in [docs/addon-install.md](../docs/addon-install.md).
- [x] **RSCP-Spike ausgeführt** (2026-07-12): Lesen + Schreiben (Entladesperre setzen/lösen) **funktionieren**, eigener RSCP-Zugriff unabhängig von EVCC bestätigt. Details und offene Restpunkte (Sichtbarkeit bei echtem Entladen, Abbruch-Test fürs Lease-TTL) in [docs/systems/e3dc.md](../docs/systems/e3dc.md#spike-ergebnis-2026-07-12-backendspikese3dc_spikepy-eigener-rscp-client-via-pye3dc).
