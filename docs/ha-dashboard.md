# Web-Dashboard in der HA-Seitenleiste (Ingress)

Seit v0.2.0 bringt das Add-on ein Web-Dashboard mit, das wie EVCC als eigener
Eintrag in der linken Home-Assistant-Seitenleiste erscheint (Panel „Leo-EMS").

## Wie es funktioniert

- `config.yaml`: `ingress: true` + `ingress_port: 8099` + `panel_title`/`panel_icon`.
  Der HA-Supervisor proxied die Seite unter `/api/hassio_ingress/<token>/`.
- Die Seite selbst liegt im Backend (`backend/leo_ems/web/index.html`) und wird
  von FastAPI unter `GET /` ausgeliefert — eine Datei, kein Build-Schritt.
- Alle API-Aufrufe der Seite sind **relative Pfade** (`api/v1/...`), dadurch
  funktioniert dieselbe Seite hinter dem Ingress-Prefix **und** direkt im LAN
  (`http://<pi>:8099/`).

## Auth-Modell

| Zugriffsweg | Auth |
|---|---|
| HA-Seitenleiste (Ingress) | Home-Assistant-Anmeldung. Ingress-Requests kommen immer vom Supervisor-Proxy `172.30.32.2` — diese Quelle ist vom Bearer-Token befreit (`create_app(ingress_host=...)`). |
| Direkt im LAN / Android-App | Bearer-Token wie bisher (docs/api-token-auth.md). Die Seite fragt den Token einmalig ab und merkt ihn im localStorage; über das Verbindungs-Badge oben rechts erneut eingebbar. |

`GET /` (die statische Seite) und `GET /api/v1/health` sind ohne Auth — sie
enthalten keine Geheimnisse.

## Was das Dashboard zeigt

1. **Lastverteilung (v0.2.2, 2D-Grafik):** flache Ostansicht des Hauses nach
   dem Bauplan (Juli 2026) mit PV-Modulen auf dem Dach — funkelt bei Erzeugung
   (Sparkles + Sonne, dimmt sonst), Netzanschluss links, Hausverbrauch mittig.
   Darunter drei Gerätekarten mit echten Produktfotos: **E3DC-Batterie** (SoC-
   Balken, Lade/Entlade-Leistung, Entladesperre), **Enyaq iV80 / Wallbox**
   (Fahrzeug-SoC, Ladeleistung, „nicht verbunden" wenn kein Auto da ist) und
   **Wärmepumpe** (Platzhalter „Stufe 2 · geplant", noch nicht angebunden).
   Aktive Karten bekommen einen Lime-Rahmen; animierte Linien verbinden Haus
   und Karten passend zum Energiefluss. Bilder liegen unter
   `backend/leo_ems/web/assets/` (per `Leo`-Auswahl aus mehreren Vorschlägen
   ausgesucht, 2026-07-14; Quellen: biber-solarkonzept.de, skodaforum.eu,
   idealo.de — zugeschnitten auf freigestellten Ausschnitt) und werden von
   FastAPI unter `/assets/...` ausgeliefert.
   Grundlage sind die Statusfelder `p_pv_w`, `p_pv_e3dc_w`, `p_haus_w`,
   `p_batterie_w`, `p_wallbox_w` (Bilanz: Haus = PV + Netz − Batterieladung − Wallbox).
   Darunter weiterhin die Kacheln PV gesamt / Haus / Batterie / Netz / Wallbox.
2. **Ladestatus:** Zustand + Klartext-Grund (REQ-050), Garantieladungs-Badge.
3. **Phasen & Entprellung** — beantwortet „Überschuss ist da, warum lädt er nur 1p?":
   `status.phasen_info` (aus `ChargeController.phase_diagnose`) liefert
   - `entprellung_aktiv/seit_s/noetig_s`: die 60/180-s-Bedingungszeit läuft noch
   - `umschaltsperre_aktiv/rest_s`: 10-min-Mindestabstand zwischen Umschaltungen
   - `grund`: Klartext, z. B. *„Überschuss 4.8 kW ≥ 3p-Schwelle 4.2 kW —
     Entprellung läuft (34/60 s), zusätzlich Umschaltsperre (noch 7:12 min)"*
   Die Seite zählt Countdown/Fortschritt zwischen den 5-s-Polls lokal weiter.
4. **Einstellungen:** Lademodus (`PUT /api/v1/mode`, neu), Fahrzeug-Ladelimit,
   Ladegrenzen (min/max A), Batterie-Reserve, Batterie-Vorrang (prioritySoc),
   Ziel-Netzbezug, Phasenschwellen + Umschaltsperre (`PUT /api/v1/config`) —
   und der Beobachtungs-/Scharf-Schalter mit Rückfrage.
5. **Laderegeln:** Regelliste anlegen/aktivieren/löschen (Garantieladung §4.3).
6. **Protokoll:** letzte Entscheidungen aus `GET /api/v1/history`.

## Neue/geänderte API

- `PUT /api/v1/mode` — `{"modus": "Nur-PV|PV+Min|Schnell|Aus", "fahrzeug_limit_soc": 0–100?}`
  setzt den Modus live in der Regelschleife (vorher nur intern).
- `GET /api/v1/status` — erweitert um Leistungsbilanz + `phasen_info` (s. o.).

## Lokal testen (ohne Pi)

```
cd backend
set LEO_EMS_DATA_DIR=%TEMP%\leo-ems-preview
py -m leo_ems.main
```

Dann `http://localhost:8099/` öffnen; Token steht im Konsolen-Log. Ohne
konfigurierte Geräte läuft das EMS in Fail-Safe E1 („E3DC nicht erreichbar") —
für UI-Tests reicht das.
