# 02 — Spezifikation (Stufe 1: EVCC-Ersatz)

**Status:** ✅ Abgenommen für Stufe 1 (Leo, 2026-07-12) — Review-Änderungen §4.3/§7 eingearbeitet. **Stand:** 2026-07-12
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
- **Einschalten:** P_überschuss ≥ 6 A × 230 V ≈ 1,4 kW ununterbrochen für **60 s** (`enableDelay`) — gestartet wird immer 1-phasig.
- **Ausschalten:** P_überschuss < **Minimum der aktuellen Phasenzahl** ununterbrochen für **180 s** (`disableDelay`).
- Stromvorgabe: `I = floor(P_überschuss / (230 V × Phasenzahl))`, begrenzt auf 6–16 A, Nachführung je Regelintervall.

**Phasenabhängiges Minimum** ⚡ *korrigiert mit Issue #7 (v0.8.0)*: `P_min(n) = 6 A × 230 V × n` — 1-phasig ≈ 1,38 kW, **3-phasig ≈ 4,14 kW**. Bis v0.7.0 wurde die Ausschaltbedingung gegen das 1p-Minimum geprüft, auch während 3-phasig geladen wurde: die Bedingung wurde in einem Band von 2,76 kW nie wahr, die Ladung lief weiter und holte sich die Differenz aus dem Netz. Je Tick wird deshalb **zuerst die Phasenzahl nachgeführt** (§4.2) und erst danach gegen `P_min(n)` geprüft.

### 4.2 Phasenumschaltung 1↔3 (REQ-002, REQ-064)

Die Umschaltung ist **bewusst asymmetrisch** (Leo, Issue #7). Hochschalten ist eine Optimierung — Warten kostet nichts. Der Rückfall auf 1p ist Schadensbegrenzung — jede Sekunde unter dem 3p-Minimum kostet Netzstrom.

- **1p → 3p:** P_überschuss ≥ **4,2 kW** für 60 s (3 × 6 A × 230 V + Reserve), **zusätzlich Mindestabstand 10 min** seit der letzten Umschaltung (⚙ Festlegung; Fahrzeug- und Schützschonung).
- **3p → 1p:** P_überschuss < **4,14 kW** (= `P_min(3)`) für **60 s**, **ohne** Mindestabstand.
- Die Rückfall-Schwelle liegt per Definition auf `P_min(3)` und nie darunter — läge sie tiefer, gäbe es ein Band, in dem der Rückfall noch nicht greift, die Leistung aber schon nicht mehr reicht.
- Umschaltung nur mit kurzer Ladepause gemäß go-e-API-Vorgabe.
- Nach dem Rückfall läuft der Mindestabstand neu — der Weg zurück auf 3p ist damit frühestens 10 min später möglich (genau Leos Formulierung in Issue #7: „dann sollte der Entprell-Timer loslaufen und gucken, wann er wieder auf dreiphasig wechseln darf").

### 4.3 Zielladung & Garantie-SoC (REQ-003/004) ⚡ *neu*

**Regel-Modell** (Leo, 2026-07-12): Die Zielladung wird über eine **frei konfigurierbare Regelliste** gesteuert — beliebig viele Regeln, jede vollständig über die App anleg-, änder- und löschbar (REQ-070):

```
Regel = { Wochentage ⊆ {Mo…So}, Abfahrtszeit T_ab, Mindest-SoC SoC_min, aktiv: ja/nein }
```

- **Default-Regel** (bei Erstinstallation): Mo–Fr, 07:30, 50 %.
- Beispiel-Konfiguration: `Mo–Fr 07:30 → 50 %`, `Sa 09:00 → 30 %`, `So — keine Regel`.
- **Auswertung:** Das EMS bestimmt aus allen aktiven Regeln die **nächste zukünftige Abfahrt** und plant auf deren `SoC_min`. Treffen mehrere Regeln auf denselben Zeitpunkt, gilt der **höchste** `SoC_min`.
- Keine aktive Regel für die kommende Zeit ⇒ reines PV-Laden ohne Garantie.

**Planungsrechnung** (je nächster Abfahrt):

```
E_fehlt  = max(0, SoC_min − SoC_ist) × 77 kWh × 1/η        (η = 0,90 Ladewirkungsgrad, ⚙ Festlegung)
T_dauer  = E_fehlt / 11 kW
T_start  = T_ab − T_dauer − 15 min Puffer
```

1. Ab Ansteck-Zeitpunkt plant das EMS mit der Forecast.Solar-Prognose: Reicht erwarteter Überschuss vor `T_ab`, bleibt es bei PV-Laden.
2. Spätestens ab `T_start` wird mit maximaler Leistung **netzunabhängig garantiert geladen** („Garantieladung"), bis `SoC_min` erreicht ist — unabhängig vom Modus (auch bei „Aus", sichtbar begründet).
3. Oberhalb `SoC_min` wird nur noch PV-Überschuss geladen, bis fahrzeugseitiges Limit (aktuell 80 %).
4. Kein Fahrzeug angesteckt ⇒ keine Aktion; ab `T_start` Benachrichtigungs-Hook (Stufe: Should, REQ-053).

**Akzeptanz:** SoC 30 %, Regel Mo–Fr 07:30/50 %, Mittwochabend ⇒ E_fehlt = 17,1 kWh, T_dauer ≈ 1:33 h ⇒ Garantieladung startet spätestens 05:42, Ziel Donnerstag 07:30 erreicht.
**Akzeptanz:** Freitagabend, Regeln `Mo–Fr 07:30/50 %` + `Sa 09:00/30 %` ⇒ nächste Abfahrt = Sa 09:00, geplant wird auf 30 %.
**Akzeptanz:** Regel per App deaktiviert ⇒ ab dem nächsten Regelintervall keine Garantieplanung mehr für diese Regel.

### 4.4 Fahrzeug-SoC (REQ-006)

Primär Škoda-Cloud. Ist der Wert älter als **30 min** während einer aktiven Ladung, schätzt das EMS: `SoC_geschätzt = SoC_letzt + E_geladen × η / 77 kWh`. Schätzwerte werden als solche gekennzeichnet (REQ-050).

## 5. Batterie-Koordination (REQ-020/021/024)

### 5.1 Entladegrenze beim EV-Laden ⚡ *dynamisch seit v0.9.0*

Bis v0.8.0 galt beim Laden eine **harte Sperre** (`max_discharge = 0`). Sie hielt die 12 kWh zwar vom Auto fern, zwang aber jede Leistungslücke ins Netz: Regelübergänge, das 3p-Mindestband während der Rückfall-Entprellung, eine zugeschaltete Hauslast, ein Wolkenzug. Genau der Netzbezug, den Leo nach v0.8.0 weiterhin beobachtet hat. Statt „gesperrt oder frei" folgt die Grenze deshalb dem **gemessenen Restbedarf des Hauses**.

- **Dynamisch** (Modus „Nur-PV", und „PV+Min", solange die PV das Minimum trägt): `Grenze = min(max(0, P_netz) + max(0, −P_batterie) + Puffer, Deckel)`. Hoch wird sofort geregelt, runter höchstens `batt_dyn_abbau_w` je Tick. Die Summe ist stationär selbstkonsistent: deckt die Batterie den Bedarf, bleibt der Bedarf derselbe und die Grenze steht — ein reiner Netzbezugs-Regler würde stattdessen schwingen. Die E3DC regelt selbst auf `P_netz ≈ 0` und entlädt nie mehr, als das Haus zieht; die Grenze deckelt also nur, was sie decken *darf*.
- **Hart (0 W)**, wo Netzbezug **gewollt** ist: Modus „Schnell", Garantieladung und das Minimum in „PV+Min", wenn die PV es nicht trägt (Flag `netz_gewollt` aus der Ladesteuerung §4 — nicht aus Modus-Strings abgeleitet). Ebenso unterhalb `priority_soc_pct`, wo die Hausbatterie Vorrang hat (Hysterese 2 Punkte).
- **Aufheben:** ≤ 60 s nach Ladeende — Begrenzung ganz weg, nicht auf 0.
- **Rückwirkung auf §2:** Eine laufende Entladung wird vom Überschuss **abgezogen**. Ohne das sähe die Wallbox die Deckung als PV und speiste sich selbst aus der Batterie. So bleibt jede Deckung transient — Abschalthysterese und Phasenrückfall greifen wie vorgesehen.
- **Schreibdrossel:** `set_power_limits` ist ein persistenter Anlagen-Schreibzugriff. Geschrieben wird erst ab `batt_dyn_schreibschwelle_w` Änderung; ein Wechsel von oder auf die harte Sperre geht immer sofort raus.
- **TTL-Pflicht (REQ-024):** Jede Grenze wird mit Ablaufzeit **15 min** gesetzt und zyklisch erneuert. Stirbt das EMS, läuft der Lease aus und die E3DC regelt autonom weiter.
- **Notausstieg:** `batt_dyn_aktiv = false` (per API, ohne Deployment) stellt das Verhalten von v0.8.0 wieder her.

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
| E1 | E3DC/RSCP weg | keine Daten > 60 s | **Abschalten** (Leo, 2026-07-12): laufende Ladung wird gestoppt, das EMS stellt die Steuerung ein, bis wieder Daten kommen. Entladesperren laufen per TTL aus. Alarm-Hook. |
| E2 | go-e weg | API-Timeout > 60 s | Keine Steuerbefehle mehr; Wallbox behält letzten/eigenen Zustand (autonomes Standardverhalten). Alarm-Hook. |
| E3 | Škoda-Cloud weg | Daten > 30 min alt | **Keine Änderung am Betrieb** (Leo, 2026-07-12): EMS arbeitet unverändert weiter, SoC per Schätzung (§4.4). |
| E4 | Forecast.Solar weg | HTTP-Fehler | **Keine Änderung am Betrieb** (Leo, 2026-07-12): EMS arbeitet unverändert weiter mit der letzten gespeicherten Prognose. |
| E5 | Sungrow weg | Modbus-Timeout | **Sungrow-Werte auf 0 setzen und weiterarbeiten** (Leo, 2026-07-12): Erzeugung = E3DC-only; Überschussrechnung am Netzpunkt bleibt korrekt. |
| E6 | EMS selbst stirbt | — | Keine persistenten Übersteuerungen: alle Overrides tragen TTL (max. 15 min). Wallbox und E3DC laufen autonom weiter. **Watchdog-Test ist Teil der Abnahme.** |
| E7 | Vaillant/HA weg | Lesefehler gegen die HA-API | **Keine Änderung am Betrieb** (Stufe 2, v0.4.0): keine WP-Sollwerte mehr, aber auch kein Zurücksetzen — der Ladebetrieb läuft unverändert weiter. Offene Sollwerte gehen raus, sobald die Verbindung wieder steht. Details: [docs/waermepumpe.md](../docs/waermepumpe.md). |

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
| `GET/POST/PUT/DELETE /api/v1/rules` | Laderegeln — CRUD ohne Neustart (REQ-070/073). Schema: `{wochentage[], abfahrtszeit, soc_min, aktiv}` (§4.3) |
| `GET/PUT /api/v1/config` | residualPower, prioritySoc, SoC_reserve, Hysteresen, harte Grenzen (REQ-071/072) |
| `GET /api/v1/history` | Kennzahlen & Entscheidungs-Log |
| `WS /api/v1/live` | Push der Live-Werte für das Dashboard |

Konfiguration wird persistent gespeichert (Datei/SQLite), Änderungen wirken sofort (REQ-073).

### 9.2 App-Dashboard (REQ-051)
Pflicht-Inhalte: **Hausverbrauch**, **Wallbox** (Leistung, Modus, Fahrzeug-SoC, Plan), **Wärmepumpe** (Leistung, Stufe 1 nur lesend), **Batterie** (SoC, Lade-/Entladeleistung, Sperr-Status), **Erzeugung** (E3DC + Sungrow), **Prognose** (heute/morgen), **Status-Begründung** (aktive Regel in Klartext). Erreichbar im LAN vom Smartphone und PC.

## 10. Abnahme Stufe 1 (Auszug — je REQ mind. ein Test)

| Test | Prüft | Kriterium | Status (Stufe-1-Implementierung) |
|---|---|---|---|
| T1 Überschussfolge | REQ-001/002 | Bei simuliertem Einspeise-Sprung 0→3 kW startet Ladung nach 60 s mit ~12 A 1p; bei Wegfall stoppt sie nach 180 s | ✅ `test_charge_control.test_t1_ueberschussfolge` |
| T2 Phasenwechsel | REQ-002/064 | Überschuss 5 kW ⇒ 3p nach 60 s; zurück auf 1p erst nach 180 s UND ≥ 10 min Abstand | ✅ `test_charge_control.test_t2_phasenwechsel` |
| T3 Garantieladung | REQ-003/004 | Szenario aus §4.3 erreicht 50 % vor 07:30, auch bei Prognose = 0. Mehrere Regeln: Freitagabend mit Mo–Fr- und Sa-Regel ⇒ Planung auf Sa 09:00/30 % | ✅ `test_rules` (mehrere) |
| T4 Entladesperre | REQ-020/024 | Beim Ladestart wird Sperre gesetzt; nach Kill des EMS-Prozesses ist sie ≤ 15 min später ausgelaufen (Watchdog-Test) | ✅ `test_loop` (Sim) + `test_safety`; HW-Watchdog offen (E3DC-Spike-Abbruchtest) |
| T5 Fail-Safe | REQ-060 | Jede Zeile der Matrix §7 einzeln provoziert; kein Gerät bleibt gesperrt | 🟡 E1 ✅ (`test_loop`); E2–E5 folgen mit realer Adapter-Verdrahtung |
| T6 Regel-CRUD | REQ-070/073 | Regel in App anlegen/ändern/löschen ⇒ wirkt ohne Neustart, übersteht EMS-Neustart | 🟡 API steht (`/api/v1/rules`), End-to-End-Test folgt mit App |
| T7 Log | REQ-062 | Für jeden Befehl in T1–T4 existiert ein vollständiger Log-Eintrag | 🟡 `store.log_decision` verdrahtet, Prüfung folgt |
| T8 Baseline-Vergleich | REQ-052-Vorbereitung | Solaranteil-Statistik wird ab Tag 1 erfasst und ist mit der EVCC-Baseline (99,4 % 30d Sommer) vergleichbar | ⚪ offen |

## 11. Festlegungen (⚙) — Stand der Durchsicht

**Von Leo bestätigt (2026-07-12):**

3. **Entladesperre auch bei „PV+Min" und „Schnell" aktiv** (§5.1) — die 12 kWh bleiben fürs Haus, kein doppelter Wandlungsverlust. *Präzisiert v0.9.0:* Der Grundsatz gilt unverändert gegenüber dem **Auto**. Neu darf die Batterie beim Laden aber den **Hausbedarf** decken, statt ihn ins Netz zu schieben — ins Auto fließt dadurch nichts, denn die Grenze folgt nur dem gemessenen Bedarf. Hart gesperrt bleibt es überall dort, wo der Netzbezug Absicht ist (Schnell, Garantie, das Minimum in PV+Min).
4. **Override-Gültigkeit: bis Abstecken oder max. 24 h** (§8.1).
5. **Garantieladung übersteuert Modus „Aus"** (§3) — das Auto ist zur Abfahrt immer fahrbereit; die App begründet sichtbar.

**Review-Änderungen von Leo (2026-07-12):**

6. **Zielladung als Regelliste** (§4.3): mehrere Regeln mit Wochentagen, Uhrzeit und frei definierbarem Mindest-SoC, komplett App-verwaltet.
7. **Fail-Safe-Matrix angepasst** (§7): E1 E3DC weg → Abschalten (auch Garantieladung); E3/E4 → Betrieb unverändert; E5 → Sungrow = 0 und weiter.

**Defaults gesetzt, im Realbetrieb zu kalibrieren (nicht blockierend):**

1. Phasenumschalt-Schwellen 4,2 / 4,0 kW, Mindestabstand 10 min (§4.2)
2. Ladewirkungsgrad η = 0,90, Puffer 15 min in der Zielladungsrechnung (§4.3)
