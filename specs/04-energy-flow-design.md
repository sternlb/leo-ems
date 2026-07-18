# Spec 04 — Energy-Flow-Redesign (Lastverteilungs-Szene v0.3)

**Status:** Phase 1 abgenommen (2026-07-18) · Phase 2 — Design-Spec (Entwurf zur Abnahme)
**Datum:** 2026-07-18
**Ersetzt:** 2D-Lastverteilungs-Szene v0.2.2 (Ostansicht + Produktfotos) in `backend/leo_ems/web/index.html`

## Ziel

Die Lastverteilungs-Szene im HA-Sidebar-Dashboard wird komplett neu gestaltet:
**Hybrid-Design** aus cinematischem, KI-generiertem Hintergrundbild (Higgsfield,
Haus nach Bauplan) und einer strikt im Basel-AI-Branding gehaltenen funktionalen
Ebene (Live-Energieflüsse, Werte, Interaktion). Vorgehen: Spec-Driven — dieses
Dokument durchläuft die Phasen Requirements → Design-Spec → Design-Exploration
(Higgsfield-Varianten) → Implementierung → Validierung.

## Interview-Ergebnisse (2026-07-18, Runde 1+2)

| Frage | Entscheidung |
|---|---|
| Scope | Komplett-Redesign, alte Szene wird ersetzt |
| Stil | Hybrid: Higgsfield-Hintergrund + Basel-AI-Branding für alles Funktionale |
| Medium | Statisches Hintergrundbild (kein Video-Loop) |
| Zielgeräte | Desktop (HA-Sidebar) **und** Wand-Tablet (Dauerbetrieb) **und** Handy (App, Hochformat) |
| Knoten | PV getrennt (E3DC + Sungrow), Batterie mit SoC, Wallbox + Enyaq, Wärmepumpe, restlicher Hausverbrauch |
| Infodichte | kW-Wert an jedem aktiven Fluss, inaktive Flüsse ohne Wert |
| Hausmotiv | Nach Bauplan/Foto — Leos reales Haus erkennbar |
| Interaktion | Tap/Klick auf Knoten öffnet Detail-Panel |

## Requirements (EF-Katalog)

### A — Inhalt & Knoten

| ID | Requirement | MoSCoW |
|---|---|---|
| EF-001 | Die Szene zeigt als Knoten: PV E3DC, PV Sungrow (getrennt), E3DC-Batterie mit Live-SoC, Netzanschluss (Bezug/Einspeisung), Wallbox + Enyaq, Wärmepumpe, restlicher Hausverbrauch. | Must |
| EF-002 | Jeder **aktive** Energiefluss trägt seinen Live-Wert in kW direkt an der Flusslinie. Inaktive Flüsse sind dezent sichtbar, aber ohne Wert. | Must |
| EF-003 | Flussrichtung ist über die Animationsrichtung erkennbar. Farbcode konsistent zum Bestand: Bezug rot, Einspeisung grau, Batterie gelb, PV/Laden lime. | Must |
| EF-004 | Wallbox-Knoten zeigt: Fahrzeug verbunden/getrennt, Ladezustand, 1p/3p-Status. | Must |
| EF-005 | Sungrow erscheint bis zur Inbetriebnahme (Ende 2026) als vorbereiteter Knoten (0 W / „geplant"), ohne die Szene zu stören. | Must |

### B — Interaktion

| ID | Requirement | MoSCoW |
|---|---|---|
| EF-010 | Tap/Klick auf einen Knoten öffnet ein Detail-Panel: Wallbox → Phasen-Diagnose mit Klartext-Grund (`phasen_info`), Batterie → SoC/Leistung/Reserve, PV → Werte je Anlage + Forecast, WP → Status. | Must |
| EF-011 | Detail-Panels funktionieren per Touch (Tablet/Handy) und Maus (Desktop). | Must |
| EF-012 | Schnellaktionen direkt am Knoten (z. B. Lademodus wechseln). | Won't (v0.3) — Einstellungen bleiben im Einstellungs-Tab |

### C — Stil & Assets

| ID | Requirement | MoSCoW |
|---|---|---|
| EF-020 | Hintergrund: **ein statisches, cinematisches Bild** (Higgsfield-generiert) von Leos Haus nach Bauplan — Satteldach, Giebel Süd/Nord, PV auf der Ost-Dachfläche (2×5 Module), Einfahrt mit Lademöglichkeit, WP an der Ostseite. | Must |
| EF-021 | Funktionale Ebene strikt im Basel-AI-Branding: Deep Forest + Lime, scharfe 2px-Kanten, Space Grotesk/Inter/Space Mono (vgl. `docs/app-design.md`). | Must |
| EF-022 | Asset-Budget: Hintergrundbild ≤ 500 KB (WebP), alle Assets zusammen ≤ 1 MB, lokal im Add-on gebündelt (LAN-only, keine externen Requests). | Must |
| EF-023 | Tageszeitabhängige Bildvarianten (Tag/Dämmerung/Nacht nach Sonnenstand). | Should (hochgestuft 2026-07-18) |

### D — Responsive & Dauerbetrieb

| ID | Requirement | MoSCoW |
|---|---|---|
| EF-030 | Die Szene funktioniert auf Desktop-Browser (HA-Sidebar, quer), Wand-Tablet (Dauerbetrieb) und Handy (Hochformat). Auf Handy darf das Layout umbrechen/stapeln. | Must |
| EF-031 | Dauerbetriebstauglich: ruhige Animationen, `prefers-reduced-motion` wird respektiert (Animationen aus, Zustand bleibt ablesbar). | Must |
| EF-032 | Performance: flüssig auf Pi-5-Ingress und Tablet-Browser; SVG/CSS/JS ohne WebGL-Pflicht. | Must |

### E — Technik & Fail-Safe

| ID | Requirement | MoSCoW |
|---|---|---|
| EF-040 | Live-Daten kommen aus der bestehenden API v1 (Status-Endpoint); die Flüsse sind datengetrieben in SVG/CSS/JS — kein vorgerendertes Video für die Datenvisualisierung. | Must |
| EF-041 | Fehlende/ausgefallene Geräte werden in der Szene sichtbar gemacht (Knoten gedimmt + „offline"), konsistent zur Fail-Safe-Matrix in Spec 02. | Must |
| EF-042 | Die Android-App übernimmt die Szene perspektivisch (gleiches Datenmodell); v0.3 liefert nur das Web-Dashboard. | Should |

## Spezifikation (Phase 2)

### §1 Aufbau & Layout-Zonen

Die Szene besteht aus zwei Ebenen:

1. **Hintergrund-Ebene:** statisches Higgsfield-Bild (Ostansicht des Hauses,
   §6). Es wird per `object-fit: cover` skaliert; alle Knoten-Anker sind als
   **relative Koordinaten (% des Bildes)** definiert, damit Overlay und Bild bei
   jeder Viewport-Größe deckungsgleich bleiben.
2. **Funktions-Ebene (SVG-Overlay):** Knoten-Chips, Flusslinien, Werte —
   strikt Basel-AI-Branding (EF-021).

**Knoten-Anker im Bild** (Ostansicht):

| Knoten | Position im Motiv |
|---|---|
| PV E3DC | Ost-Dachfläche des Hauses (2×5 Module) |
| PV Sungrow | Garagendach (bis Inbetriebnahme gedimmt, Badge „geplant") |
| Batterie (E3DC) | Hauswand/Keller-Bereich, Chip mit SoC-Füllbalken |
| Netz | Bildrand links (Anschlusspunkt/Mast) |
| Wallbox + Enyaq | Einfahrt rechts; Auto nur sichtbar wenn verbunden |
| Wärmepumpe | Ostseite des Hauses (Außeneinheit) |
| Hausverbrauch | zentral am Haus (Chip „Haus") |

**Responsive-Verhalten (EF-030):**

- **Desktop / Tablet quer (≥ 768 px):** volle Szene, Bild 16:9, Overlay wie oben.
- **Handy hoch (< 768 px):** Schema-Modus — das Bild wird schmaler Header
  (Anschnitt Hausmitte), darunter stapeln die Knoten als vertikale Liste
  mit denselben Chips, Flüssen (vertikale Linien) und Werten. Gleiche
  Datenlogik, anderes Layout.

### §2 Daten-Mapping (API v1 `/api/v1/status`)

| Statusfeld | Element | Regel |
|---|---|---|
| `p_pv_e3dc_w` | Fluss PV-E3DC → Haus | aktiv ab Schwelle, Wert am Fluss |
| `p_sungrow_w` | Fluss PV-Sungrow → Haus | bis Inbetriebnahme immer 0 → Knoten gedimmt „geplant" (EF-005) |
| `p_netz_w` | Fluss Netz ↔ Haus | > +50 W: Bezug (rot, Richtung → Haus); < −50 W: Einspeisung (grau, Richtung → Netz); dazwischen inaktiv |
| `p_batterie_w` | Fluss Batterie ↔ Haus | Vorzeichen bestimmt Richtung (laden/entladen), gelb |
| `soc_batterie` | SoC-Füllbalken im Batterie-Chip | 0–100 %, numerisch daneben |
| `p_wallbox_w` | Fluss Haus → Wallbox | lime, Wert am Fluss |
| `laedt`, `phasen`, `strom_a` | Wallbox-Chip | Badge „1p/3p · x A" nur wenn `laedt` |
| `soc_fahrzeug` | Enyaq-Chip | SoC-Badge; `null` → Auto ausgeblendet/getrennt |
| `p_haus_w` | Hausverbrauch-Chip | enthält die WP, solange kein MyVaillant-Adapter liefert (Hinweis im Panel) |
| `phasen_info` | Detail-Panel Wallbox | Klartext-Grund, Entprellungs-Fortschritt, Sperr-Countdown |
| `grund`, `modus` | Kopfzeile der Szene | Klartext-Status wie bisher |
| `entladesperre` | Batterie-Chip | Schloss-Badge wenn aktiv |
| `garantieladung` | Wallbox-Chip | Badge „Garantie" wenn aktiv |

**Wertformat:** Flüsse ≥ 1000 W als `x,y kW` (eine Nachkommastelle), 50–999 W
als `xxx W`, darunter gilt der Fluss als inaktiv (keine Linie, kein Wert) —
50-W-Schwelle mit Hysterese gegen Flackern.

### §3 Knoten-Zustände

| Knoten | Zustände |
|---|---|
| PV (je Anlage) | erzeugt (Fluss + Wert) · Ruhe (gedimmt) · **geplant** (Sungrow, Badge) · offline (EF-041) |
| Batterie | lädt · entlädt · Ruhe · Entladesperre (Schloss) · offline → **Szene zeigt Warnbanner** (E3DC weg = Fail-Safe E1, Spec 02) |
| Netz | Bezug · Einspeisung · ausgeglichen |
| Wallbox | kein Fahrzeug · verbunden, wartet (mit Klartext-Grund) · lädt (1p/3p, A, kW) · Garantieladung · offline |
| Enyaq | getrennt (ausgeblendet) · verbunden (SoC, Limit) · SoC unbekannt (`soc_fahrzeug: null` bei verbundenem Kabel → „SoC —") |
| Wärmepumpe | **vorbereitet** (Stufe 2, keine Live-Daten — gedimmt, Badge „Stufe 2") · später: läuft/Ruhe |
| Haus | immer aktiv, Wert = `p_haus_w` |

Offline-Darstellung (EF-041): Knoten gedimmt + „offline"-Badge, zugehörige
Flüsse aus; konsistent zur Fail-Safe-Matrix (Škoda/Forecast weg → nur Badge,
Betrieb normal; Sungrow weg → Werte 0).

### §4 Detail-Panels (EF-010)

Tap/Klick auf Knoten öffnet ein Panel (Overlay-Karte im Branding, Schließen per
X/Tap außerhalb, ESC am Desktop):

| Knoten | Panel-Inhalt |
|---|---|
| Wallbox | Phasen-Diagnose komplett: `phasen_info` (Klartext-Grund, Entprellungs-Fortschrittsbalken 60/180 s, 10-min-Sperre mit Countdown), Modus, Strom, Garantiestatus |
| Batterie | SoC, Lade-/Entladeleistung, Reserve-Einstellung (nur Anzeige), Entladesperre mit Rest-TTL |
| PV | Werte je Anlage (E3DC / Sungrow), Forecast.Solar-Prognose heute |
| Enyaq | SoC, Fahrzeug-Limit, aktive Laderegel (nächste Abfahrt + Mindest-SoC) |
| WP | Status „Stufe 2 — Steuerung folgt nach MyVaillant-Praxistest" |
| Haus | `p_haus_w` + Hinweis, dass WP enthalten ist; Bilanzformel |
| Netz | aktueller Bezug/Einspeisung, Tageszähler (sofern Store-Daten da) |

### §5 Animation & Dauerbetrieb

- Flusslinien: gerichtete Strichanimation wie bisher (`dash`), Geschwindigkeit
  in 3 Stufen nach Leistungshöhe (< 1 kW langsam, 1–5 kW mittel, > 5 kW schnell).
- `prefers-reduced-motion`: alle Animationen aus, aktive Flüsse als
  durchgezogene Linie mit Richtungspfeil (EF-031).
- Keine Dauer-Glow/Pulse-Effekte großflächig (Einbrennschutz Wand-Tablet);
  statische dunkle Flächen dominieren.

### §6 Higgsfield-Asset-Spezifikation (Phase 3)

- **Motiv:** Leos Haus, Ostansicht, nach Foto-Referenz (`docs/referenz/`):
  Satteldach mit Giebeln Süd/Nord, PV 2×5 auf der Ost-Dachfläche, Garage
  (künftig Sungrow), Einfahrt, WP-Außeneinheit Ostseite.
- **Stimmung:** cinematisch, dunkel-ruhig (Dämmerung als Leitvariante), damit
  die Lime/Deep-Forest-Overlays kontrastieren; keine Menschen, keine Texte im Bild.
- **Varianten (EF-023 Should):** Tag / Dämmerung / Nacht, identische Kamera
  und Geometrie (gleiche Anker-Koordinaten für alle drei!), Wechsel nach
  Sonnenstand (Forecast/Uhrzeit, lokal berechnet).
- **Format:** 16:9 quer, Export als WebP ≤ 500 KB pro Variante; 3 Varianten
  gesamt ≤ 1,2 MB → **Anpassung EF-022:** Asset-Budget gesamt ≤ 1,5 MB bei
  3 Tageszeit-Varianten (Einzelbild-Grenze bleibt 500 KB).
- **Prozess:** 2–3 Kompositions-Varianten generieren → Leo wählt → Feinschliff
  → Anker-Koordinaten vermessen → in `web/assets/` einchecken.

### §7 Abnahmetests

| Test | Szenario | Erwartung |
|---|---|---|
| T-EF-1 | PV 3,2 kW, Wallbox lädt 2,4 kW 1p, Batterie lädt 0,6 kW | drei lime/gelbe Flüsse mit Werten „3,2 kW / 2,4 kW / 600 W", Wallbox-Badge „1p · 10 A" |
| T-EF-2 | Einspeisung −1,5 kW | grauer Fluss Haus → Netz „1,5 kW", kein Bezugsfluss |
| T-EF-3 | Tap auf Wallbox bei wartendem Fahrzeug | Panel mit Klartext-Grund + Entprellungs-Fortschritt sichtbar |
| T-EF-4 | `prefers-reduced-motion` aktiv | keine Animation, aktive Flüsse mit Richtungspfeil ablesbar |
| T-EF-5 | Viewport 375 px hoch | Schema-Modus: alle Knoten + Werte ohne horizontales Scrollen |
| T-EF-6 | E3DC-Adapter getrennt | Warnbanner + Batterie/PV-E3DC offline-gedimmt (Fail-Safe E1) |
| T-EF-7 | `soc_fahrzeug: null` bei verbundenem Kabel | Enyaq-Chip „SoC —", kein JS-Fehler |
| T-EF-8 | Asset-Prüfung | Hintergrund-WebP ≤ 500 KB/Bild, gesamt ≤ 1,5 MB, keine externen Requests |

## Offene Punkte

- [ ] **Fotos vom Haus** (Ostansicht ideal, 1–2 Stück) → Leo legt sie unter `docs/referenz/` im leo-ems-Repo ab — Grundlage für die Higgsfield-Generierung.
- [ ] **Higgsfield-MCP autorisieren** (claude.ai-Connector-Einstellungen oder `/mcp` in interaktiver Session) — nötig ab Phase 3 (Design-Exploration).
- [ ] Kostenrahmen für Higgsfield-Generierungen klären (der Skill sieht Kostenschätzung + Freigabe vor).
- [ ] Netz-Panel-Tageszähler: prüfen, ob der Store die Tagessummen schon hergibt (sonst Could).

## Phasenplan dieses Inkrements

| Phase | Ergebnis | Status |
|---|---|---|
| 1. Design-Requirements | EF-Katalog (dieses Dokument), MoSCoW abgenommen | ✅ abgeschlossen (2026-07-18, EF-023 → Should) |
| 2. Design-Spec | §1–§7: Layout-Zonen, Daten-Mapping, Zustände, Panels, Animation, Asset-Spec, Abnahmetests | 🔵 zur Abnahme |
| 3. Design-Exploration | 2–3 Higgsfield-Varianten als Mockup, Leo wählt | ⚪ blockiert: MCP-Auth + Fotos |
| 4. Implementierung | Neue Szene in `index.html`, Live-Verdrahtung, Tests | ⚪ offen |
| 5. Validierung | Preview-Verifikation + real auf Pi/Tablet/Handy, Release v0.3.0 | ⚪ offen |
