# 01 — Requirements

**Status:** ✅ **Phase 1 abgeschlossen** — alle Requirements per MoSCoW priorisiert (26 Must, 13 Should). Einzige offene Flanke: REQ-043 ist vorläufig eingestuft, bis Elektriker Waldemar die 70 %-Frage für die Neuanlage klärt.
**Stand:** 2026-07-12 (MoSCoW-Priorisierung)

> **Architektur-Richtung (Runde 2, von Leo entschieden):** Das EMS ist ein **Eigenbau und ersetzt das bestehende EVCC** (aktuell als HACS-Installation in HA). EVCC dient als Funktions-Referenz fürs Laden (REQ-007/008), wird aber nicht eingebunden. Die ADR in Phase 3 dokumentiert nur noch das *Wie* (Tech-Stack: AppDaemon / Custom Integration / Add-on), nicht mehr das *Ob*.

Konventionen:
- IDs `REQ-<Nr>` sind stabil, auch wenn ein Requirement später verworfen wird (dann Status *Verworfen*).
- Formulierung nach dem Muster „Das EMS muss/soll/kann …" — testbar, eine Anforderung pro Eintrag.
- Priorisierung (MoSCoW) erfolgte am 2026-07-12 gemeinsam — Ergebnis in der Spalte *MoSCoW* und im Abschnitt „Priorisierung" am Dateiende.

---

## A — PV-Überschussladen E-Auto

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-001 | Das EMS muss den aktuellen PV-Überschuss (Erzeugung beider Anlagen minus Hausverbrauch, unter Berücksichtigung der Batterie) berechnen. | Must | Priorisiert |
| REQ-002 | Das EMS muss die Ladeleistung der go-e Wallbox stufenlos bzw. in Ampere-Schritten an den PV-Überschuss anpassen (inkl. 1-/3-phasig-Umschaltung, sofern verfügbar). | Must | Priorisiert |
| REQ-003 | Das EMS muss eine Zielladung unterstützen: bis zur konfigurierten Abfahrtszeit muss der Enyaq einen Ziel-SoC erreichen — notfalls mit Netzstrom. **Defaults: Abfahrt 07:30, Mindest-SoC 50 %.** Werte über die Bedienoberfläche änderbar (→ REQ-070). | Must | Priorisiert |
| REQ-004 | Das EMS muss einen Mindest-SoC des Enyaq garantieren, der unabhängig vom PV-Angebot immer schnellstmöglich hergestellt wird (Wert über UI einstellbar, → REQ-070). | Must | Priorisiert |
| REQ-005 | Das EMS muss Lademodi anbieten (mindestens: Nur-PV, PV+Min, Schnell/Egal-woher, Aus), umschaltbar über HA. | Must | Priorisiert |
| REQ-006 | Das EMS soll den SoC und Ladezustand des Enyaq aus der Fahrzeug-Integration einbeziehen (nicht nur Wallbox-Zählerstand). | Must | Priorisiert |
| REQ-007 | Das EMS muss fürs Autoladen den Funktionsumfang von EVCC **funktionsäquivalent nachbilden** (Überschussregelung mit Phasenumschaltung, Ladeplanung auf Zielzeit, Fahrzeug-SoC-Integration, Lademodi). EVCC ist Referenz, wird aber nicht eingebunden. | Must | Priorisiert |
| REQ-008 | Das EMS muss die bestehende EVCC-Installation (HACS in HA) vollständig ablösen: Nach der Migration übernimmt das EMS alle EVCC-Aufgaben (E3DC-Messung via RSCP, Wallbox-Steuerung, Enyaq-Anbindung); EVCC wird deinstalliert. | Must | Priorisiert |

## B — Wärmepumpen-Steuerung

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-010 | Das EMS soll bei anhaltendem PV-Überschuss die Warmwasserbereitung der Vaillant WP vorziehen (Boost/Sollwert-Anhebung mittags statt abends). | Should | Priorisiert |
| REQ-011 | Das EMS soll bei PV-Überschuss die Heizkreis-Solltemperatur moderat anheben können (thermische Speicherung im Gebäude/Puffer). | Should | Priorisiert |
| REQ-012 | Das EMS darf Komfortgrenzen nie verletzen (Warmwasser-Mindesttemperatur, Raumtemperatur-Korridor); Grenzen sind konfigurierbar. | Should | Priorisiert |
| REQ-013 | Das EMS soll die WP über die **MyVaillant-Cloud** ansteuern (Vaillant-Internetmodul hängt am eBUS). Ein lokaler eBUS-Direktzugang (z.B. ebusd, zusätzliche Hardware nötig) bleibt als spätere Option offen, ist aber kein Requirement. | Should | Priorisiert |
| REQ-014 | Das EMS muss die Ratenlimits der MyVaillant-Cloud respektieren (Anfrage-Budget, keine Dauerschleifen) und mit Cloud-Latenz/Aussetzern robust umgehen. | Should | Priorisiert |

## C — Batterie-Management (E3DC)

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-020 | Das EMS soll verhindern, dass die E3DC-Batterie sich während des EV-Ladens ins Auto entlädt (Entladesperre bzw. Entladelimit während Wallbox-Betrieb). | Must | Priorisiert |
| REQ-021 | Das EMS muss eine konfigurierbare SoC-Reserve der Hausbatterie respektieren und darf sie nicht aktiv unterschreiten. **Über die UI einstellbar, Default 0 %** (→ REQ-071). | Must | Priorisiert |
| REQ-022 | Das EMS soll die Batterieladung zeitlich steuern können (z.B. mittags drosseln, wenn EV-Ladung Vorrang hat; vor Schlechtwetter voll laden). | Should | Priorisiert |
| REQ-023 | Das EMS soll Netzladen der Batterie unterstützen, sobald ein dynamischer Tarif vorliegt (Billigstunden nutzen). | Should | Priorisiert |
| REQ-024 | Bei Wegfall der EMS-Steuerung muss die E3DC auf ihre autonome Standardregelung zurückfallen (kein „hängender" Übersteuerungszustand). | Must | Priorisiert |

## D — Dynamischer Tarif / Preisoptimierung *(Tarif geplant, noch nicht vorhanden)*

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-030 | Das EMS soll stündliche (bzw. viertelstündliche) Strompreise eines dynamischen Tarifs einlesen können. Die Anbindung ist als **austauschbarer Adapter** zu gestalten, vorbereitet auf die Top-5-Anbieter in Deutschland: **Tibber, Octopus Energy, Rabot Charge, Ostrom, aWATTar/EPEX Spot** (Anbieterliste bei Vertragsabschluss verifizieren). | Should | Priorisiert |
| REQ-031 | Das EMS soll verschiebbare Lasten (EV-Restladung, WW-Bereitung, Batterie-Netzladen) in die günstigsten Stunden legen, wenn kein PV-Überschuss verfügbar ist. | Should | Priorisiert |
| REQ-032 | Das EMS soll ohne dynamischen Tarif vollständig funktionieren (Preislogik ist optionales Modul, kein Kernpfad). | Must | Priorisiert |

## E — Erzeugung & Prognose

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-040 | Das EMS muss die Erzeugung beider Anlagen (E3DC-DC-seitig + Sungrow AC-seitig) zu einer Gesamterzeugung zusammenführen. | Must | Priorisiert |
| REQ-041 | Das EMS soll eine PV-Ertragsprognose (mind. 24 h) über **Forecast.Solar** nutzen, um Ladeplanung und WP-Vorziehen vorausschauend zu steuern — konfiguriert für beide Anlagen (Ost 22° + Garagendach Ost/West 15°). | Must | Priorisiert |
| REQ-042 | Das EMS soll den Sungrow SG 6.0RT lokal auslesen (Modbus TCP bevorzugt, keine Cloud-Pflicht). | Must | Priorisiert |
| REQ-043 | Das EMS soll die **70 %-Einspeisebegrenzung** berücksichtigen und drohende Abregelung durch lokale Verwertung des Überschusses vermeiden. Bestandsanlage: Regel aktiv, in der E3DC-Steuerung hinterlegt. *Für die Neuanlage (Sungrow) noch zu klären.* | Should | Priorisiert |

## F — Monitoring / Dashboard

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-050 | Das EMS muss seinen Zustand und jede aktive Übersteuerung sichtbar machen (aktueller Modus, warum lädt/lädt nicht, welche Regel greift). | Must | Priorisiert |
| REQ-051 | Das EMS soll ein Dashboard mit **Hausverbrauch und allen Hauptverbrauchern** (Wallbox, Wärmepumpe, Batterie-Lade-/Entladeleistung) sowie Erzeugung, Prognose und Ladeplan bereitstellen. | Must | Priorisiert |
| REQ-052 | Das EMS soll Kennzahlen historisieren (Autarkie, PV-Anteil am EV-Laden, verschobene kWh), um den Nutzen gegen die Baseline 2025 zu belegen. | Should | Priorisiert |
| REQ-053 | Das EMS kann bei relevanten Ereignissen benachrichtigen (Ziel-SoC nicht erreichbar, Gerät nicht erreichbar, ungewöhnlicher Netzbezug). | Should | Priorisiert |

## G — Sicherheit / Fallback

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-060 | Fail-Safe: Bei Ausfall des EMS, von HA oder einzelner APIs müssen alle Geräte in ihrem autonomen Standardverhalten weiterlaufen (keine Blockade von Laden/Heizen). | Must | Priorisiert |
| REQ-061 | Das EMS muss manuelle Übersteuerung durch den Nutzer jederzeit zulassen und darf sie nicht „zurückdrehen" (Override mit definierter Gültigkeit). | Must | Priorisiert |
| REQ-062 | Alle Steuerentscheidungen müssen nachvollziehbar geloggt werden (Zeitpunkt, Regel, Messwerte). | Must | Priorisiert |
| REQ-063 | Konfigurationsgrenzen (Min-SoC, Temperaturen, max. Schaltfrequenz) müssen zentral definiert sein; das EMS validiert gegen diese Grenzen vor jedem Steuerbefehl. | Must | Priorisiert |
| REQ-064 | Das EMS soll Geräte schonen: keine schnellen Schaltzyklen (Hysterese/Mindestlaufzeiten für WP-Boost, Wallbox-Phasenumschaltung, Batterie-Modi). | Must | Priorisiert |

## H — Konfiguration & Bedienung (App/UI)

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-070 | Der Nutzer muss Laderegeln (Abfahrtszeit + Ziel-/Mindest-SoC) über ein Eingabefenster in der App/UI **anlegen, ändern und wieder entfernen** können — ohne YAML/Code. Default-Regel: Abfahrt 07:30, Mindest-SoC 50 %. | Must | Priorisiert |
| REQ-071 | Die SoC-Reserve der Hausbatterie muss über die App/UI einstellbar sein. **Default: 0 %.** | Must | Priorisiert |
| REQ-072 | Harte Grenzen (z.B. WW-Mindesttemperatur, EV-Mindest-SoC, Batterie-Limits) müssen über die App/UI einstellbar sein. **Default: keine Grenze aktiv** — das System läuft zunächst ohne harte Grenzen, sie sind aber nachrüstbar ohne Codeänderung. | Should | Priorisiert |
| REQ-073 | Konfigurationsänderungen über die UI müssen sofort wirken (kein Neustart) und persistent gespeichert werden. | Must | Priorisiert |
| REQ-074 | Die Bedienoberfläche soll entweder als **HA-Dashboard** oder als **separate App** realisierbar sein — die EMS-Logik ist von der UI zu entkoppeln (Steuerung über definierte Schnittstelle/Entities), damit die Entscheidung offen bleiben kann. | Must | Priorisiert |

---

## Interview-Runde 1 — Antworten (2026-07-12)

| # | Frage | Antwort | Eingeflossen in |
|---|---|---|---|
| 1 | WP-Anbindung | ~~SG-Ready verdrahtet~~ **Korrektur Runde 2:** Internetmodul am eBUS → Steuerweg = MyVaillant-Cloud | REQ-013/014 |
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

## Interview-Runde 2 — Antworten (2026-07-12)

| # | Frage | Antwort | Eingeflossen in |
|---|---|---|---|
| — | *(Grundsatz)* | **EVCC soll ersetzt werden** — EMS ist Eigenbau, EVCC nur Funktions-Referenz | Architektur-Richtung, REQ-007/008 |
| 1 | EVCC-Bestand | In HA über **HACS** installiert | REQ-008 (Ablösung/Migration) |
| 2 | „App" | EMS-Oberfläche **entweder HA-Dashboard oder separate App** — offen halten | REQ-074 |
| 3 | Prognosequelle | **Forecast.Solar** | REQ-041 |
| 4 | Dashboard | **Hausverbrauch + alle Hauptverbraucher** (Wallbox, …) | REQ-051 |
| 5 | SG-Ready | Korrektur: kein SG-Ready-Kontakt — **Internetmodul am eBUS**, ggf. doch Cloud-Anbindung nutzen | REQ-013/014 |
| 6 | 70 %-Regel Neuanlage | Unklar — **Elektriker Waldemar** muss antworten | REQ-043 (offen) |

## Offene Fragen (Runde 3)

1. **70 %-Regel Neuanlage:** Antwort von Elektriker Waldemar einholen — gilt die Begrenzung auch für die Sungrow-Anlage bzw. den Summenzähler? *(externe Abhängigkeit)*
2. **UI-Entscheidung:** HA-Dashboard vs. separate App — kann bis zur Architekturphase offen bleiben (REQ-074 hält beides möglich), sollte aber vor Phase 4 fallen.
3. **MyVaillant-Steuerbarkeit:** Reichen die per Cloud verfügbaren Stellgrößen (WW-Boost, Sollwerte) praktisch aus? → in Phase 2 mit einem kurzen Praxistest verifizieren.
4. ~~**Migrations-Baseline**~~ ✅ Erledigt (2026-07-12): siehe [docs/evcc-baseline.md](../docs/evcc-baseline.md) — EVCC läuft als **Add-on** (nicht HACS), Site-Parameter, Loadpoint „Garage", Vehicle und Statistik-Baseline (99,4 % Solaranteil 30d) dokumentiert. Rest-Todo dort: `evcc.yaml`/Zugangsdaten vor der Ablösung sichern.

## Priorisierung (MoSCoW) — Ergebnis vom 2026-07-12

**26 Must, 13 Should, 0 Could, 3 Won't.** Kein Requirement wurde verworfen.

### Leitlinie

Die Musts bilden zusammen **Ausbaustufe 1: den EVCC-Ersatz** — Überschussladen des Enyaq inkl. Zielladung, Batterie-Koordination (Entladesperre, Reserve), Gesamterzeugung + Forecast.Solar, Dashboard, komplette Sicherheits- und UI-Basis. Die Shoulds verteilen sich auf zwei spätere Stufen.

### Ausbaustufen

| Stufe | Inhalt | Requirements | Voraussetzung |
|---|---|---|---|
| **1 — EVCC-Ersatz** | EV-Überschussladen, Batterie-Grundsteuerung, Prognose, Dashboard, Sicherheit, UI | alle Musts (REQ-001–008, 020/021/024, 032, 040–042, 050/051, 060–064, 070/071/073/074) | EVCC-Baseline dokumentieren (Fragen Runde 3) |
| **2 — Wärmepumpe** | WW-Vorziehen, Heizkreis-Anhebung, Komfortgrenzen, Cloud-Robustheit | REQ-010–014 (Should) | MyVaillant-Praxistest bestanden |
| **3 — Dynamischer Tarif** | Preis-Adapter, Lastverschiebung in Billigstunden, Batterie-Netzladen, Feinsteuerung | REQ-022/023, 030/031, 043, 052/053, 072 (Should) | Tarifvertrag abgeschlossen |

*(REQ-052/053/072 sind nicht tarifgebunden und können vorgezogen werden, sobald Stufe 1 stabil läuft. REQ-042 (Sungrow) ist Must, aber erst nach der Installation Ende 2026 real testbar — bis dahin gegen simulierte Werte entwickeln.)*

### Won't (aus den Nicht-Zielen der Vision)

| ID | Ausschluss |
|---|---|
| WONT-1 | Steuerung von Haushaltsgeräten (Smart Plugs: Waschmaschine & Co.) |
| WONT-2 | Ersatz der E3DC-internen Regelung im Normalbetrieb — nur gezielte Übersteuerung |
| WONT-3 | Stromhandel/Arbitrage über die Einspeisung hinaus (kein Regelenergiemarkt) |

### Einzelentscheidungen (Leo, 2026-07-12)

- REQ-010 (WW-Vorziehen): **Should / Stufe 2** — v1 konzentriert sich auf den EVCC-Ersatz.
- REQ-020 (Entladesperre beim EV-Laden): **Must** — gehört zum sauberen Überschussladen.
- REQ-011 (Heizkreis-Anhebung): **Should** — gleiche Stufe wie das Warmwasser-Vorziehen.
- REQ-053 (Benachrichtigungen): **Should** — Kern-Alarme früh, aber nicht v1-blockierend.
