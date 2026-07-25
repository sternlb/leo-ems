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
   Die **Batterie-Kachel zeigt seit v0.4.0 den SoC als Hauptwert** (Prozent +
   Füllbalken), die Lade-/Entladeleistung steht darunter — vorher war es
   umgekehrt und der SoC fehlte in der Handy-Schemaliste ganz (Issue #2).
   Die Schemaliste führt jetzt bei jeder Zeile die Zusatzangabe mit (Batterie:
   SoC, Netz: Bezug/Einspeisung, Wallbox: Phasen/Strom).

   **Bewegte Szene seit v0.5.0.** Die Ostansicht reagiert auf drei Zustände;
   die Abläufe stecken komplett im CSS, das JS setzt nur Klassen an `.scene`:
   - `auto-da` (Fahrzeug an der Wallbox): das linke Torblatt fährt in 0,9 s im
     Ausschnitt nach oben (`clipPath#clipTorL`), danach rollt der Enyaq in 1,5 s
     ein Stück heraus — leicht größer und tiefer, also auf den Betrachter zu —
     und bleibt stehen. Beim Abstecken läuft alles rückwärts.
   - `pv-an` (E3DC erzeugt, gleiche 50-W-Hysterese wie die Flüsse): das
     Modulfeld glimmt lime auf, ein Glanzband wandert alle 5,5 s darüber und
     einzelne Modulecken funkeln. Die Intensität kommt als CSS-Variable
     `--pv-i` (0,35 bei 50 W → 0,95 ab ~6 kW von 9,23 kWp). Der Effekt ist
     bewusst auf die Modulflächen geclippt und gedeckelt — Spec 04 §5 verbietet
     großflächige Dauer-Glows (Einbrennschutz Wand-Tablet).
   - `wp-an` / `wp-boost`: das Lüfterrad der Wärmepumpe dreht (2,6 s pro
     Umdrehung, im Überschuss-Boost 1,2 s). Quelle ist das neue Statusfeld
     `wp.laeuft`, siehe unten.

   **Räumliche Tiefe seit v0.6.0** (Details und Begründung: Spec 04 §5):
   - **Licht und Schatten** — Querverlauf auf Fassade und Garagenfront,
     Verlaufsbänder unter der Traufe und am Wandfuß, dunkle Laibungskanten in
     jeder Öffnung, weiche Schlagschatten auf dem Boden.
   - **Parallax** — acht Ebenen mit `data-d` (0,12 Netzmast … 0,85 Boden)
     verschieben sich bei Zeigerbewegung bzw. Tablet-Neigung um bis zu ±9 px,
     nur waagerecht. Boden und Horizontlinie sind über den Bildrand hinaus
     gezeichnet, sonst blitzt beim Verschieben der Himmel durch.
   - **Flüsse als Röhren** — vier Pfade auf derselben Kurve: Schattenkern,
     Röhrenkörper, weicher Leuchtsaum, laufende Ladungsperlen.
   - **Tageszeit-Licht** — `sonnenstand()` rechnet lokal (kein Cloud-Call).
     Schattenrichtung und -länge, Himmelsverlauf, Nachtschleier und die
     Besonnung der Ostfassade (nur vormittags) folgen der Uhrzeit;
     Aktualisierung alle 2 Minuten.

   Die KPI-Kacheln unter der Szene bleiben bewusst flach — das
   Basel-AI-Branding ist scharfkantig, Tiefe gibt es nur in der Szene.

   Bei `prefers-reduced-motion: reduce` sind alle Bewegungen aus (auch Parallax
   und Leuchtsaum); Tor, Auto, PV-Leuchten und Tageszeit-Licht bleiben als
   statische Zustände sichtbar.
2. **Wärmepumpe (v0.4.0, Issue #1):** zweigeteilt in **Warmwasser**
   (Speichertemperatur, Sollwert, Modus, `BOOST`-Badge) und **Heizkreis**
   (Vorlauftemperatur, Raum-Ist/-Soll, Zustand, Außentemperatur,
   `ANHEBUNG`-Badge). Darunter der Klartext-Grund der Überschuss-Steuerung.
   Quelle ist `status.wp` aus `planner/heatpump.py`; ohne Verbindung steht dort
   „keine Verbindung zur Wärmepumpe" und es wird nichts gestellt (Fail-Safe E7).
3. **Ladestatus:** Zustand + Klartext-Grund (REQ-050), Garantieladungs-Badge.
4. **Phasen & Entprellung** — beantwortet „Überschuss ist da, warum lädt er nur 1p?":
   `status.phasen_info` (aus `ChargeController.phase_diagnose`) liefert
   - `entprellung_aktiv/seit_s/noetig_s`: die 60/180-s-Bedingungszeit läuft noch
   - `umschaltsperre_aktiv/rest_s`: 10-min-Mindestabstand zwischen Umschaltungen
   - `grund`: Klartext, z. B. *„Überschuss 4.8 kW ≥ 3p-Schwelle 4.2 kW —
     Entprellung läuft (34/60 s), zusätzlich Umschaltsperre (noch 7:12 min)"*
   Die Seite zählt Countdown/Fortschritt zwischen den 5-s-Polls lokal weiter.
5. **Einstellungen:** Lademodus (`PUT /api/v1/mode`, neu), Fahrzeug-Ladelimit,
   Ladegrenzen (min/max A), Batterie-Reserve, Batterie-Vorrang (prioritySoc),
   Ziel-Netzbezug, Phasenschwellen + Umschaltsperre (`PUT /api/v1/config`) —
   und der Beobachtungs-/Scharf-Schalter mit Rückfrage. Seit v0.4.0 zusätzlich
   die WP-Schwellen (An/Aus, Boost- und Rückstelltemperatur, Heizkreis-Anhebung,
   Raum-Obergrenze, Außentemperatur-Grenze); die Timing-Parameter
   (Entprellung, Mindestlaufzeit, Cloud-Gap) bleiben API-only.
6. **Laderegeln:** Regelliste anlegen/aktivieren/löschen (Garantieladung §4.3).
7. **Protokoll:** letzte Entscheidungen aus `GET /api/v1/history`.

## Neue/geänderte API

- `PUT /api/v1/mode` — `{"modus": "Nur-PV|PV+Min|Schnell|Aus", "fahrzeug_limit_soc": 0–100?}`
  setzt den Modus live in der Regelschleife (vorher nur intern).
- `GET /api/v1/status` — erweitert um Leistungsbilanz + `phasen_info` (s. o.)
  und seit v0.4.0 um `wp` (Wärmepumpe, zweigeteilt `warmwasser`/`heizkreis`).
  Seit v0.5.0 enthält `wp` zusätzlich `laeuft` (bool): läuft die Anlage gerade?
  Abgeleitet in `HeatPumpController._laeuft()` aus `hk_zustand` (HEATING/COOLING)
  und `ww_sonderfunktion` — MyVaillant liefert keine Verdichter- oder
  Ventilatorleistung. Bewusst **nicht** aus dem gewünschten Boost: im
  Beobachtungsmodus wird nichts gesendet, dort dürfte der Lüfter nicht drehen.
- `GET/PUT /api/v1/config` — die `wp_*`-Parameter aus `RegelConfig`.

## Lokal testen (ohne Pi)

```
cd backend
set LEO_EMS_DATA_DIR=%TEMP%\leo-ems-preview
py -m leo_ems.main
```

Dann `http://localhost:8099/` öffnen; Token steht im Konsolen-Log. Ohne
konfigurierte Geräte läuft das EMS in Fail-Safe E1 („E3DC nicht erreichbar") —
für UI-Tests reicht das.
