# 01 — Requirements

**Status:** Phase 1 laufend — alle Einträge sind **Kandidaten (Entwurf)**, keine Zusagen.
**Stand:** 2026-07-12 (aktualisiert nach Interview-Runde 1)

> **Architektur-Input (Runde 1):** EVCC ist bereits im Einsatz — die E3DC ist darüber via RSCP angebunden — und der EVCC-Funktionsumfang fürs Autoladen ist explizit gefordert (REQ-007). Das ist ein starker Hinweis Richtung *EVCC als Lade-Kern + EMS drumherum (Hybrid)*. Die Entscheidung fällt trotzdem erst als ADR nach Phase 1.

Konventionen:
- IDs `REQ-<Nr>` sind stabil, auch wenn ein Requirement später verworfen wird (dann Status *Verworfen*).
- Formulierung nach dem Muster „Das EMS muss/soll/kann …" — testbar, eine Anforderung pro Eintrag.
- Priorisierung (MoSCoW) erfolgt **am Ende der Phase 1** gemeinsam, Spalte bleibt bis dahin leer.

---

## A — PV-Überschussladen E-Auto

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-001 | Das EMS muss den aktuellen PV-Überschuss (Erzeugung beider Anlagen minus Hausverbrauch, unter Berücksichtigung der Batterie) berechnen. | | Entwurf |
| REQ-002 | Das EMS muss die Ladeleistung der go-e Wallbox stufenlos bzw. in Ampere-Schritten an den PV-Überschuss anpassen (inkl. 1-/3-phasig-Umschaltung, sofern verfügbar). | | Entwurf |
| REQ-003 | Das EMS muss eine Zielladung unterstützen: bis zur konfigurierten Abfahrtszeit muss der Enyaq einen Ziel-SoC erreichen — notfalls mit Netzstrom. **Defaults: Abfahrt 07:30, Mindest-SoC 50 %.** Werte über die Bedienoberfläche änderbar (→ REQ-070). | | Entwurf |
| REQ-004 | Das EMS muss einen Mindest-SoC des Enyaq garantieren, der unabhängig vom PV-Angebot immer schnellstmöglich hergestellt wird (Wert über UI einstellbar, → REQ-070). | | Entwurf |
| REQ-005 | Das EMS muss Lademodi anbieten (mindestens: Nur-PV, PV+Min, Schnell/Egal-woher, Aus), umschaltbar über HA. | | Entwurf |
| REQ-006 | Das EMS soll den SoC und Ladezustand des Enyaq aus der Fahrzeug-Integration einbeziehen (nicht nur Wallbox-Zählerstand). | | Entwurf |
| REQ-007 | Das EMS muss fürs Autoladen den Funktionsumfang von EVCC bereitstellen (Überschussregelung mit Phasenumschaltung, Ladeplanung auf Zielzeit, Fahrzeug-SoC-Integration, Lademodi) — entweder durch Einbindung von EVCC selbst oder funktionsäquivalent. | | Entwurf |

## B — Wärmepumpen-Steuerung

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-010 | Das EMS soll bei anhaltendem PV-Überschuss die Warmwasserbereitung der Vaillant WP vorziehen (Boost/Sollwert-Anhebung mittags statt abends). | | Entwurf |
| REQ-011 | Das EMS soll bei PV-Überschuss die Heizkreis-Solltemperatur moderat anheben können (thermische Speicherung im Gebäude/Puffer). | | Entwurf |
| REQ-012 | Das EMS darf Komfortgrenzen nie verletzen (Warmwasser-Mindesttemperatur, Raumtemperatur-Korridor); Grenzen sind konfigurierbar. | | Entwurf |
| REQ-013 | Das EMS soll die WP bevorzugt lokal über die **verdrahtete SG-Ready-/eBUS-Anbindung** ansteuern; die MyVaillant-Cloud dient als Lese- und Fallback-Pfad. | | Entwurf |
| REQ-014 | Sofern die MyVaillant-Cloud genutzt wird, muss das EMS deren Ratenlimits respektieren (Anfrage-Budget, keine Dauerschleifen). | | Entwurf |

## C — Batterie-Management (E3DC)

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-020 | Das EMS soll verhindern, dass die E3DC-Batterie sich während des EV-Ladens ins Auto entlädt (Entladesperre bzw. Entladelimit während Wallbox-Betrieb). | | Entwurf |
| REQ-021 | Das EMS muss eine konfigurierbare SoC-Reserve der Hausbatterie respektieren und darf sie nicht aktiv unterschreiten. **Über die UI einstellbar, Default 0 %** (→ REQ-071). | | Entwurf |
| REQ-022 | Das EMS soll die Batterieladung zeitlich steuern können (z.B. mittags drosseln, wenn EV-Ladung Vorrang hat; vor Schlechtwetter voll laden). | | Entwurf |
| REQ-023 | Das EMS soll Netzladen der Batterie unterstützen, sobald ein dynamischer Tarif vorliegt (Billigstunden nutzen). | | Entwurf |
| REQ-024 | Bei Wegfall der EMS-Steuerung muss die E3DC auf ihre autonome Standardregelung zurückfallen (kein „hängender" Übersteuerungszustand). | | Entwurf |

## D — Dynamischer Tarif / Preisoptimierung *(Tarif geplant, noch nicht vorhanden)*

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-030 | Das EMS soll stündliche (bzw. viertelstündliche) Strompreise eines dynamischen Tarifs einlesen können. Die Anbindung ist als **austauschbarer Adapter** zu gestalten, vorbereitet auf die Top-5-Anbieter in Deutschland: **Tibber, Octopus Energy, Rabot Charge, Ostrom, aWATTar/EPEX Spot** (Anbieterliste bei Vertragsabschluss verifizieren). | | Entwurf |
| REQ-031 | Das EMS soll verschiebbare Lasten (EV-Restladung, WW-Bereitung, Batterie-Netzladen) in die günstigsten Stunden legen, wenn kein PV-Überschuss verfügbar ist. | | Entwurf |
| REQ-032 | Das EMS soll ohne dynamischen Tarif vollständig funktionieren (Preislogik ist optionales Modul, kein Kernpfad). | | Entwurf |

## E — Erzeugung & Prognose

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-040 | Das EMS muss die Erzeugung beider Anlagen (E3DC-DC-seitig + Sungrow AC-seitig) zu einer Gesamterzeugung zusammenführen. | | Entwurf |
| REQ-041 | Das EMS soll eine PV-Ertragsprognose (mind. 24 h) nutzen, um Ladeplanung und WP-Vorziehen vorausschauend zu steuern (Quelle offen: Forecast.Solar / Solcast / E3DC). | | Entwurf |
| REQ-042 | Das EMS soll den Sungrow SG 6.0RT lokal auslesen (Modbus TCP bevorzugt, keine Cloud-Pflicht). | | Entwurf |
| REQ-043 | Das EMS soll die **70 %-Einspeisebegrenzung** berücksichtigen und drohende Abregelung durch lokale Verwertung des Überschusses vermeiden. Bestandsanlage: Regel aktiv, in der E3DC-Steuerung hinterlegt. *Für die Neuanlage (Sungrow) noch zu klären.* | | Entwurf |

## F — Monitoring / Dashboard

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-050 | Das EMS muss seinen Zustand und jede aktive Übersteuerung sichtbar machen (aktueller Modus, warum lädt/lädt nicht, welche Regel greift). | | Entwurf |
| REQ-051 | Das EMS soll ein HA-Dashboard mit Energiefluss, Prognose und Ladeplan bereitstellen. | | Entwurf |
| REQ-052 | Das EMS soll Kennzahlen historisieren (Autarkie, PV-Anteil am EV-Laden, verschobene kWh), um den Nutzen gegen die Baseline 2025 zu belegen. | | Entwurf |
| REQ-053 | Das EMS kann bei relevanten Ereignissen benachrichtigen (Ziel-SoC nicht erreichbar, Gerät nicht erreichbar, ungewöhnlicher Netzbezug). | | Entwurf |

## G — Sicherheit / Fallback

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-060 | Fail-Safe: Bei Ausfall des EMS, von HA oder einzelner APIs müssen alle Geräte in ihrem autonomen Standardverhalten weiterlaufen (keine Blockade von Laden/Heizen). | | Entwurf |
| REQ-061 | Das EMS muss manuelle Übersteuerung durch den Nutzer jederzeit zulassen und darf sie nicht „zurückdrehen" (Override mit definierter Gültigkeit). | | Entwurf |
| REQ-062 | Alle Steuerentscheidungen müssen nachvollziehbar geloggt werden (Zeitpunkt, Regel, Messwerte). | | Entwurf |
| REQ-063 | Konfigurationsgrenzen (Min-SoC, Temperaturen, max. Schaltfrequenz) müssen zentral definiert sein; das EMS validiert gegen diese Grenzen vor jedem Steuerbefehl. | | Entwurf |
| REQ-064 | Das EMS soll Geräte schonen: keine schnellen Schaltzyklen (Hysterese/Mindestlaufzeiten für WP-Boost, Wallbox-Phasenumschaltung, Batterie-Modi). | | Entwurf |

## H — Konfiguration & Bedienung (App/UI)

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-070 | Der Nutzer muss Laderegeln (Abfahrtszeit + Ziel-/Mindest-SoC) über ein Eingabefenster in der App/UI **anlegen, ändern und wieder entfernen** können — ohne YAML/Code. Default-Regel: Abfahrt 07:30, Mindest-SoC 50 %. | | Entwurf |
| REQ-071 | Die SoC-Reserve der Hausbatterie muss über die App/UI einstellbar sein. **Default: 0 %.** | | Entwurf |
| REQ-072 | Harte Grenzen (z.B. WW-Mindesttemperatur, EV-Mindest-SoC, Batterie-Limits) müssen über die App/UI einstellbar sein. **Default: keine Grenze aktiv** — das System läuft zunächst ohne harte Grenzen, sie sind aber nachrüstbar ohne Codeänderung. | | Entwurf |
| REQ-073 | Konfigurationsänderungen über die UI müssen sofort wirken (kein Neustart) und persistent gespeichert werden. | | Entwurf |

---

## Interview-Runde 1 — Antworten (2026-07-12)

| # | Frage | Antwort | Eingeflossen in |
|---|---|---|---|
| 1 | WP-Anbindung | **SG-Ready/eBUS verdrahtet** → lokaler Steuerweg vorhanden | REQ-013/014 |
| 2 | E3DC schreibend | **Funktioniert — RSCP läuft bereits über EVCC** | REQ-020 ff., Architektur-Input |
| 3 | EV-Nutzung | Abfahrt typ. **07:30**, Mindest-SoC **50 %**; per App-Eingabefenster erweiter-/entfernbar | REQ-003/004, REQ-070 |
| 4 | Batterie-Reserve | Über App einstellbar, **Default 0 %** | REQ-021, REQ-071 |
| 5 | Tarifanbieter | Noch offen — Schnittstelle für **Top-5-Anbieter DE** vorbereiten | REQ-030 |
| 6 | Prognosequelle | *(noch offen)* | REQ-041 |
| 7 | Einspeisebegrenzung | **70 %-Regel**, für Bestandsanlage in der E3DC-Steuerung hinterlegt | REQ-043 |
| 8 | Sungrow | **LAN vorhanden**, Installation **bis Ende 2026** | REQ-042, docs/systems/sungrow.md |
| 9 | Dashboard | *(noch offen)* | REQ-050 ff. |
| 10 | Harte Grenzen | Aktuell keine nötig, müssen aber **einstellbar** sein | REQ-072 |
| 11 | Autoladen-Features | **EVCC-Funktionsumfang gefordert** | REQ-007 |

## Offene Fragen (Runde 2)

1. **Prognosequelle:** Forecast.Solar, Solcast oder E3DC-intern?
2. **Dashboard:** Was willst du auf einen Blick sehen, und wo (HA-Dashboard, Handy, beides)?
3. **EVCC-Bestand:** Wo läuft dein EVCC (HA-Add-on, Raspberry Pi, Docker)? Sind Wallbox und Enyaq dort schon als Loadpoint/Vehicle konfiguriert?
4. **„App":** Meint App/UI das HA-Dashboard bzw. die HA-Companion-App — oder eine eigene EMS-Oberfläche?
5. **SG-Ready:** Welche Betriebsart nutzt die Vaillant bei SG-Ready-Signal (Empfehlung vs. Zwangslauf)? Ist der Kontakt schon mal geschaltet worden?
6. **70 %-Regel Neuanlage:** Gilt die Begrenzung auch für die Sungrow-Anlage bzw. den Summenzähler? (Klärung mit Stadtwerken Röthenbach.)

## Priorisierung (MoSCoW)

> Folgt am Ende von Phase 1 — gemeinsame Durchsicht aller Kandidaten, dann Einstufung Must/Should/Could/Won't und Sortierung.
