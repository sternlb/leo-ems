# 02 — Spezifikation (Stufe 1: EVCC-Ersatz)

**Status:** Entwurf, Verhaltens-Festlegungen von Leo bestätigt (§11). **Stand:** 2026-07-12
**Scope:** Alle Must-Requirements aus [01-requirements.md](01-requirements.md) (Stufe 1). Wärmepumpe (Stufe 2) und dynamischer Tarif (Stufe 3) sind hier nur als Erweiterungspunkte berücksichtigt.
**Referenzwerte** stammen aus der [EVCC-Baseline](../docs/evcc-baseline.md) — wo das EMS vom EVCC-Ist abweicht, ist es markiert (⚡ *neu*).

---

## 1. Systemkontext

### 1.1 Datenquellen (Eingänge)

| Quelle | Weg | Werte | Zyklus | Ausfallverhalten → §7 |
|---|---|---|---|---|
| E3DC S10E | RSCP (lokal) | PV-Leistung, Netz-Leistung (±), Batterie-Leistung/SoC, Hausverbrauch | ≤ 10 s | E1 |
| go-e Gemini | lokale HTTP-API v2 | Status, Ladeleistung, Ströme/Phasen, Energiezähler | ≤ 10 s | E2 |
| Škoda Enyaq | Škoda-Cloud | SoC, Steckerstatus, fahrzeugseitiges Ladelimit | ≤ 5 min | E3 |
| Forecast.Solar | HTTPS | PV-Prognose 24–48 h, beide Anlagen | 1×/h | E4 |
| Sungrow SG 6.0RT | Modbus TCP | AC-Leistung, Tagesertrag | ≤ 10 s | E5 — *bis zur Installation (Ende 2026): konstant 0 W bzw. Simulationsprofil* |

### 1.2 Stellglieder (Ausgänge)

| Gerät | Weg | Befehle |
|---|---|---|
| go-e Gemini | lokale HTTP-API | Laden ein/aus, Ladestrom 6–16 A, Phasen 1↔3 |
| E3DC | RSCP | Entladesperre setzen/aufheben (mit TTL, §5) |

Alle Steuerbefehle laufen durch die zentrale Grenzen-Validierung (§8.3, REQ-063).

## 2. Kerngrößen (REQ-001, REQ-040)

Vorzeichenkonvention: Erzeugung/Einspeisung negativ am Netzpunkt; `P_netz > 0` = Bezug.

```
P_erzeugung = P_pv_e3dc + P_pv_sungrow                     (REQ-040)
P_überschuss = P_lade_ist − P_netz − P_residual            (verfügbare Leistung für den Loadpoint)
```

- `P_residual` = **100 W** (Ziel-Netzbezug, konfigurierbar; Baseline-Wert)
- **Batterie-Behandlung:** Ist `SoC_batterie < prioritySoc` (**25 %**, konfigurierbar), zählt Batterie-Ladeleistung als Verbrauch (Batterie hat Vorrang vor dem EV). Ist `SoC_batterie ≥ prioritySoc`, wird Batterie-Ladeleistung dem Überschuss zugerechnet (das EV darf sie „wegnehmen").
- Berechnung im **Regelintervall 10 s**, gleitender Mittelwert über 3 Messungen gegen Flackern.

**Akzeptanz:** Bei P_netz = −3.000 W (Einspeisung), P_lade_ist = 0, SoC_bat ≥ 25 % ⇒ P_überschuss = 2.900 W.

## 3. Lademodi (REQ-005)

| Modus | Verhalten |
|---|---|
| **Aus** | Wallbox gesperrt. Ausnahme: aktive Garantieladung (§4.3) hat Vorrang und meldet dies sichtbar (REQ-050). |
| **Nur-PV** | Laden ausschließlich aus P_überschuss. Kein Überschuss ⇒ kein Laden. |
| **PV+Min** | Wie Nur-PV, aber nie unter 6 A 1-phasig (≈ 1,4 kW) — Differenz ggf. aus Netz/Batterie. |
| **Schnell** | Sofort maximale Leistung (16 A, 3-phasig ≈ 11 kW), Herkunft egal. |

Default-Modus: **Nur-PV** (Baseline). Umschaltung über App (§9) und HA; Wechsel wirkt innerhalb eines Regelintervalls.

## 4. Ladesteuerung E-Auto

### 4.1 Zustandsmaschine (REQ-002)

Zustände: `FREI` (kein Fahrzeug) → `VERBUNDEN` (wartet auf Freigabe) → `LADEN_1P` / `LADEN_3P` → `PAUSIERT` (Hysterese/kein Überschuss) → `BEENDET` (Ziel/Limit erreicht).

Hysterese (Baseline-Werte, konfigurierbar):
- **Einschalten:** P_überschuss ≥ 6 A × 230 V ≈ 1,4 kW ununterbrochen für **60 s** (`enableDelay`)
- **Ausschalten:** P_überschuss < Minimum ununterbrochen für **180 s** (`disableDelay`)
- Stromvorgabe: `I = floor(P_überschuss / (230 V × Phasenzahl))`, begrenzt auf 6–16 A, Nachführung je Regelintervall.

### 4.2 Phasenumschaltung 1↔3 (REQ-002, REQ-064)

- **1p → 3p:** P_überschuss ≥ **4,2 kW** für 60 s (3 × 6 A × 230 V + Reserve)
- **3p → 1p:** P_überschuss < **4,0 kW** für 180 s
- **Mindestabstand zwischen Umschaltungen: 10 min** (⚙ Festlegung; Fahrzeug- und Schützschonung), Umschaltung nur mit kurzer Ladepause gemäß go-e-API-Vorgabe.

### 4.3 Zielladung & Garantie-SoC (REQ-003/004) ⚡ *neu*

Konfiguration je Regel (§9.2): Abfahrtszeit `T_ab` (Default **07:30**), Garantie-SoC `SoC_min` (Default **50 %**).

```
E_fehlt  = max(0, SoC_min − SoC_ist) × 77 kWh × 1/η        (η = 0,90 Ladewirkungsgrad, ⚙ Festlegung)
T_dauer  = E_fehlt / 11 kW
T_start  = T_ab − T_dauer − 15 min Puffer
```

1. Ab Ansteck-Zeitpunkt plant das EMS mit der Forecast.Solar-Prognose: Reicht erwarteter Überschuss vor `T_ab`, bleibt es bei PV-Laden.
2. Spätestens ab `T_start` wird mit maximaler Leistung **netzunabhängig garantiert geladen** („Garantieladung"), bis `SoC_min` erreicht ist — unabhängig vom Modus (auch bei „Aus", sichtbar begründet).
3. Oberhalb `SoC_min` wird nur noch PV-Überschuss geladen, bis fahrzeugseitiges Limit (aktuell 80 %).
4. Kein Fahrzeug angesteckt ⇒ keine Aktion; ab `T_start` Benachrichtigungs-Hook (Stufe: Should, REQ-053).

**Akzeptanz:** SoC 30 %, Regel 07:30/50 % ⇒ E_fehlt = 17,1 kWh, T_dauer ≈ 1:33 h ⇒ Garantieladung startet spätestens 05:42, Ziel um 07:30 erreicht.
**Akzeptanz:** SoC 55 % um 23:00 ⇒ keine Garantieladung; PV-Laden am Morgen falls Überschuss.

### 4.4 Fahrzeug-SoC (REQ-006)

Primär Škoda-Cloud. Ist der Wert älter als **30 min** während einer aktiven Ladung, schätzt das EMS: `SoC_geschätzt = SoC_letzt + E_geladen × η / 77 kWh`. Schätzwerte werden als solche gekennzeichnet (REQ-050).

## 5. Batterie-Koordination (REQ-020/021/024)

### 5.1 Entladesperre beim EV-Laden ⚡ *neu*

- **Aktivieren:** Wenn Loadpoint in `LADEN_*` und Batterie entlädt > 200 W in Richtung Hausnetz ⇒ E3DC-Entladesperre setzen.
- **Aufheben:** ≤ 60 s nach Ladeende, bei Moduswechsel auf „Schnell" bleibt sie aktiv (Netzstrom statt Batterie), bei „PV+Min" bleibt sie aktiv (Minimalanteil aus Netz, nicht aus Batterie; ⚙ Festlegung).
- **TTL-Pflicht (REQ-024):** Jede Sperre wird mit Ablaufzeit **15 min** gesetzt und zyklisch erneuert. Stirbt das EMS, läuft die Sperre aus und die E3DC regelt autonom weiter.

### 5.2 SoC-Reserve (REQ-021)

`SoC_reserve` (Default **0 %**, App-einstellbar) — das EMS gibt keinen Befehl, der die Batterie aktiv unter die Reserve entlädt. Validierung in §8.3.

## 6. Prognose (REQ-041)

- Forecast.Solar, zwei Ebenen: **9,23 kWp Ost 22°** + ab Inbetriebnahme **5,64 kWp Ost/West 15°** (als zwei Flächen O+W modelliert).
- Abruf 1×/h (Rate-Limit Public-Tier), Persistierung der letzten gültigen Prognose.
- Verwendung: Zielladungsplanung (§4.3); Anzeige in der App (§9).

## 7. Ausfallverhalten (REQ-060) — Fail-Safe-Matrix

Grundprinzip: **Das EMS steuert nur aktiv, wenn seine Datenlage frisch ist.** Jeder Ausfall degradiert in einen sicheren, dokumentierten Zustand; kein Gerät bleibt blockiert.

| # | Ausfall | Erkennung | Verhalten |
|---|---|---|---|
| E1 | E3DC/RSCP weg | keine Daten > 60 s | Kein Überschusswert ⇒ PV-Regelung pausiert. Läuft eine Garantieladung, läuft sie weiter (netzbasiert). Entladesperren laufen per TTL aus. |
| E2 | go-e weg | API-Timeout > 60 s | Keine Steuerbefehle mehr; Wallbox behält letzten/eigenen Zustand (autonomes Standardverhalten). Alarm-Hook. |
| E3 | Škoda-Cloud weg | Daten > 30 min alt | SoC-Schätzung (§4.4). > 12 h ohne Wert: Garantieladung nutzt konservativ SoC_letzt. |
| E4 | Forecast.Solar weg | HTTP-Fehler | Letzte Prognose weiterverwenden (max. 24 h); danach Zielladung rein zeitbasiert (T_start ohne PV-Annahme = konservativ früh). |
| E5 | Sungrow weg | Modbus-Timeout | Erzeugung = E3DC-only; Überschussrechnung bleibt korrekt (Sungrow speist AC-seitig ein → erscheint am Netzpunkt). |
| E6 | EMS selbst stirbt | — | Keine persistenten Übersteuerungen: alle Overrides tragen TTL (max. 15 min). Wallbox und E3DC laufen autonom weiter. **Watchdog-Test ist Teil der Abnahme.** |

## 8. Sicherheit & Nachvollziehbarkeit

### 8.1 Manueller Override (REQ-061)
Nutzer-Eingriffe (App, HA, Wallbox-Taster, EVCC-artige Modusumschaltung) gelten **bis Abstecken des Fahrzeugs oder max. 24 h** (⚙ Festlegung). Das EMS dreht sie nicht zurück; aktive Overrides sind in der App sichtbar.

### 8.2 Entscheidungs-Log (REQ-062)
Jede Steuerentscheidung wird geloggt: Zeitstempel, Regel/Trigger, Eingangswerte (P_überschuss, SoCs), Befehl, Ergebnis. Format: strukturiert (JSON-Zeilen), Aufbewahrung ≥ 90 Tage, einsehbar über die App.

### 8.3 Zentrale Grenzen-Validierung (REQ-063, REQ-072)
Alle Befehle passieren einen Validator gegen die Konfiguration (Strom 6–16 A, SoC_reserve, harte Grenzen — Default: keine aktiv). Verstoß ⇒ Befehl verworfen + Log-Eintrag.

### 8.4 Schaltfrequenz-Schutz (REQ-064)
Phasenumschaltung ≥ 10 min Abstand (§4.2); Entladesperre max. 1 Zustandswechsel/min; Ladefreigabe folgt der Hysterese (§4.1).

## 9. Schnittstelle & App (REQ-050/051, REQ-070/071/073/074)

### 9.1 Lokale API (UI-Entkopplung, REQ-074)
Das EMS stellt eine **lokale HTTP-API + WebSocket** im LAN bereit (kein Cloud-Pfad). Endpunkte (v1):

| Endpunkt | Zweck |
|---|---|
| `GET /api/v1/status` | Live-Zustand: Leistungen, SoCs, Modus, aktive Regel, Begründung („warum lädt/lädt nicht") (REQ-050) |
| `GET/PUT /api/v1/mode` | Lademodus |
| `GET/POST/PUT/DELETE /api/v1/rules` | Laderegeln (Abfahrtszeit, Garantie-SoC) — CRUD ohne Neustart (REQ-070/073) |
| `GET/PUT /api/v1/config` | residualPower, prioritySoc, SoC_reserve, Hysteresen, harte Grenzen (REQ-071/072) |
| `GET /api/v1/history` | Kennzahlen & Entscheidungs-Log |
| `WS /api/v1/live` | Push der Live-Werte für das Dashboard |

Konfiguration wird persistent gespeichert (Datei/SQLite), Änderungen wirken sofort (REQ-073).

### 9.2 App-Dashboard (REQ-051)
Pflicht-Inhalte: **Hausverbrauch**, **Wallbox** (Leistung, Modus, Fahrzeug-SoC, Plan), **Wärmepumpe** (Leistung, Stufe 1 nur lesend), **Batterie** (SoC, Lade-/Entladeleistung, Sperr-Status), **Erzeugung** (E3DC + Sungrow), **Prognose** (heute/morgen), **Status-Begründung** (aktive Regel in Klartext). Erreichbar im LAN vom Smartphone und PC.

## 10. Abnahme Stufe 1 (Auszug — je REQ mind. ein Test)

| Test | Prüft | Kriterium |
|---|---|---|
| T1 Überschussfolge | REQ-001/002 | Bei simuliertem Einspeise-Sprung 0→3 kW startet Ladung nach 60 s mit ~12 A 1p; bei Wegfall stoppt sie nach 180 s |
| T2 Phasenwechsel | REQ-002/064 | Überschuss 5 kW ⇒ 3p nach 60 s; zurück auf 1p erst nach 180 s UND ≥ 10 min Abstand |
| T3 Garantieladung | REQ-003/004 | Szenario aus §4.3 erreicht 50 % vor 07:30, auch bei Prognose = 0 |
| T4 Entladesperre | REQ-020/024 | Beim Ladestart wird Sperre gesetzt; nach Kill des EMS-Prozesses ist sie ≤ 15 min später ausgelaufen (Watchdog-Test) |
| T5 Fail-Safe | REQ-060 | Jede Zeile der Matrix §7 einzeln provoziert; kein Gerät bleibt gesperrt |
| T6 Regel-CRUD | REQ-070/073 | Regel in App anlegen/ändern/löschen ⇒ wirkt ohne Neustart, übersteht EMS-Neustart |
| T7 Log | REQ-062 | Für jeden Befehl in T1–T4 existiert ein vollständiger Log-Eintrag |
| T8 Baseline-Vergleich | REQ-052-Vorbereitung | Solaranteil-Statistik wird ab Tag 1 erfasst und ist mit der EVCC-Baseline (99,4 % 30d Sommer) vergleichbar |

## 11. Festlegungen (⚙) — Stand der Durchsicht

**Von Leo bestätigt (2026-07-12):**

3. **Entladesperre auch bei „PV+Min" und „Schnell" aktiv** (§5.1) — die 12 kWh bleiben fürs Haus, kein doppelter Wandlungsverlust.
4. **Override-Gültigkeit: bis Abstecken oder max. 24 h** (§8.1).
5. **Garantieladung übersteuert Modus „Aus"** (§3) — das Auto ist um 07:30 immer fahrbereit; die App begründet sichtbar.

**Defaults gesetzt, im Realbetrieb zu kalibrieren (nicht blockierend):**

1. Phasenumschalt-Schwellen 4,2 / 4,0 kW, Mindestabstand 10 min (§4.2)
2. Ladewirkungsgrad η = 0,90, Puffer 15 min in der Zielladungsrechnung (§4.3)
