# 01 — Requirements

**Status Phase 1:** ✅ **abgeschlossen** — alle Requirements per MoSCoW priorisiert (26 Must, 13 Should), keine offenen Flanken. Zur 70 %-Regel der Neuanlage gilt eine dokumentierte Arbeitsannahme (REQ-043), die bei der Sungrow-Inbetriebnahme verifiziert wird.
**Stand Anforderungen:** 2026-07-12 (MoSCoW + finale Entscheidungen UI/70 %-Regel)
**Stand Umsetzung:** 2026-07-26 (v0.6.5) — die Spalte *Umsetzung* wird bei jedem Release mitgeführt.

> **Architektur-Richtung (Runde 2, von Leo entschieden):** Das EMS ist ein **Eigenbau und ersetzt das bestehende EVCC** (aktuell als HACS-Installation in HA). EVCC dient als Funktions-Referenz fürs Laden (REQ-007/008), wird aber nicht eingebunden. Die ADR in Phase 3 dokumentiert nur noch das *Wie* (Tech-Stack: AppDaemon / Custom Integration / Add-on), nicht mehr das *Ob*.

Konventionen:
- IDs `REQ-<Nr>` sind stabil, auch wenn ein Requirement später verworfen wird (dann Status *Verworfen*).
- Formulierung nach dem Muster „Das EMS muss/soll/kann …" — testbar, eine Anforderung pro Eintrag.
- Priorisierung (MoSCoW) erfolgte am 2026-07-12 gemeinsam — Ergebnis in der Spalte *MoSCoW* und im Abschnitt „Priorisierung" am Dateiende.
- Spalte *Umsetzung*: ✅ umgesetzt · 🔵 teilweise · ⚪ offen. Welcher **Test** ein Requirement hält und wo es im Code steht, steht in [05-umsetzungsstand.md](05-umsetzungsstand.md) — diese Datei bleibt die Anforderungsliste, dort liegt der Nachweis.

---

## Umsetzungsstand auf einen Blick (2026-07-26, v0.6.5)

| | Must (26) | Should (13) | Gesamt (39) |
|---|---|---|---|
| ✅ umgesetzt | 20 | 5 | **25** |
| 🔵 teilweise | 4 | 4 | **8** |
| ⚪ offen | 2 | 4 | **6** |

86 automatisierte Tests. **34 der 39 Requirements haben einen Nachweis** (Test, Live-Verifikation oder beides). Ohne jeden Nachweis sind nur REQ-008, 022, 023, 030 und 031 — vier davon gehören zu Ausbaustufe 3 (dynamischer Tarif), die es real noch nicht gibt.

**Die vier Punkte, die den größten Unterschied machen würden:**

1. **REQ-041 (Must)** — der Forecast.Solar-Adapter ist fertig **und wird von der Regelschleife nie gelesen**. Die Zielladung plant ohne Prognose, obwohl das laut `docs/evcc-baseline.md` eine der drei Neuerungen gegenüber EVCC sein sollte. Größte inhaltliche Lücke der Stufe 1.
2. **REQ-013 (Should)** — WP-**Lesen** läuft seit v0.6.5 vollständig, das **Schreiben** ist unbestätigt: `set_temperature` geht fehlerfrei durch, der Sollwert folgt nicht (Verdacht Betriebsart `Auto`).
3. **REQ-061 (Must)** — Nutzer-Override „bis Abstecken oder 24 h" ist für die Wallbox gar nicht implementiert.
4. **REQ-052 (Should)** — Kennzahlen gegen die Baseline 2025 fehlen. Erst seit v0.6.5 überhaupt messbar, weil die Beobachtungsdaten vorher bei jedem Update gelöscht wurden.

> **Zwei Requirements waren im Betrieb verletzt, ohne dass es jemand sehen konnte** (gefunden 2026-07-26): REQ-006 (Fahrzeug-SoC) lief seit dem Go-live in eine `AttributeError`, weil myskoda ein Feld umbenannt hat — `soc_fahrzeug` war immer `null`. Und REQ-073 (Konfiguration persistent) galt nicht, weil das Add-on wegen s6-overlay ohne `LEO_EMS_DATA_DIR` startete und alle Daten im Container ablegte: Token, Konfiguration und Messdaten waren nach **jedem** Update weg, inklusive der Scharfschaltung. Beides ist behoben; die Verpackungs-Zusagen hält jetzt `backend/tests/test_addon_paket.py` fest, und `status.geraete` + `/api/v1/diag/*` machen solche Ausfälle künftig sichtbar.

---

## A — PV-Überschussladen E-Auto

| ID | Anforderung | MoSCoW | Umsetzung |
|---|---|---|---|
| REQ-001 | Das EMS muss den aktuellen PV-Überschuss (Erzeugung beider Anlagen minus Hausverbrauch, unter Berücksichtigung der Batterie) berechnen. | Must | ✅ getestet + live |
| REQ-002 | Das EMS muss die Ladeleistung der go-e Wallbox stufenlos bzw. in Ampere-Schritten an den PV-Überschuss anpassen (inkl. 1-/3-phasig-Umschaltung, sofern verfügbar). | Must | ✅ getestet (T1/T2) + live |
| REQ-003 | Das EMS muss eine Zielladung unterstützen: bis zur konfigurierten Abfahrtszeit muss der Enyaq einen Ziel-SoC erreichen — notfalls mit Netzstrom. **Defaults: Abfahrt 07:30, Mindest-SoC 50 %.** Werte über die Bedienoberfläche änderbar (→ REQ-070). | Must | ✅ getestet — plant aber ohne Prognose (→ REQ-041) |
| REQ-004 | Das EMS muss einen Mindest-SoC des Enyaq garantieren, der unabhängig vom PV-Angebot immer schnellstmöglich hergestellt wird (Wert über UI einstellbar, → REQ-070). | Must | ✅ getestet |
| REQ-005 | Das EMS muss Lademodi anbieten (mindestens: Nur-PV, PV+Min, Schnell/Egal-woher, Aus), umschaltbar über HA. | Must | ✅ getestet |
| REQ-006 | Das EMS soll den SoC und Ladezustand des Enyaq aus der Fahrzeug-Integration einbeziehen (nicht nur Wallbox-Zählerstand). | Must | ✅ **seit v0.6.3 erstmals wirklich** — lief vorher in eine AttributeError |
| REQ-007 | Das EMS muss fürs Autoladen den Funktionsumfang von EVCC **funktionsäquivalent nachbilden** (Überschussregelung mit Phasenumschaltung, Ladeplanung auf Zielzeit, Fahrzeug-SoC-Integration, Lademodi). EVCC ist Referenz, wird aber nicht eingebunden. | Must | 🔵 Einzelfunktionen da und getestet, **Äquivalenz gegen die Baseline nicht belegt** |
| REQ-008 | Das EMS muss die bestehende EVCC-Installation (HACS in HA) vollständig ablösen: Nach der Migration übernimmt das EMS alle EVCC-Aufgaben (E3DC-Messung via RSCP, Wallbox-Steuerung, Enyaq-Anbindung); EVCC wird deinstalliert. | Must | ⚪ EVCC läuft weiter parallel — erst nach belegtem Vergleich (REQ-007/052) |

## B — Wärmepumpen-Steuerung

| ID | Anforderung | MoSCoW | Umsetzung |
|---|---|---|---|
| REQ-010 | Das EMS soll bei anhaltendem PV-Überschuss die Warmwasserbereitung der Vaillant WP vorziehen (Boost/Sollwert-Anhebung mittags statt abends). | Should | ✅ 11 Tests; Entscheidung läuft live (Boost wird ausgelöst) |
| REQ-011 | Das EMS soll bei PV-Überschuss die Heizkreis-Solltemperatur moderat anheben können (thermische Speicherung im Gebäude/Puffer). | Should | 🔵 umgesetzt + 4 Tests, **Heizperiode noch nicht erlebt** |
| REQ-012 | Das EMS darf Komfortgrenzen nie verletzen (Warmwasser-Mindesttemperatur, Raumtemperatur-Korridor); Grenzen sind konfigurierbar. | Should | ✅ getestet |
| REQ-013 | Das EMS soll die WP über die **MyVaillant-Cloud** ansteuern (Vaillant-Internetmodul hängt am eBUS). Ein lokaler eBUS-Direktzugang (z.B. ebusd, zusätzliche Hardware nötig) bleibt als spätere Option offen, ist aber kein Requirement. | Should | 🔵 **Lesen ✅ (seit v0.6.5), Schreiben unbestätigt** — Aufruf geht durch, Sollwert folgt nicht |
| REQ-014 | Das EMS muss die Ratenlimits der MyVaillant-Cloud respektieren (Anfrage-Budget, keine Dauerschleifen) und mit Cloud-Latenz/Aussetzern robust umgehen. | Should | ✅ getestet (15-min-Gap, kein Nachschreiben nach Bestätigung) |

## C — Batterie-Management (E3DC)

| ID | Anforderung | MoSCoW | Umsetzung |
|---|---|---|---|
| REQ-020 | Das EMS soll verhindern, dass die E3DC-Batterie sich während des EV-Ladens ins Auto entlädt (Entladesperre bzw. Entladelimit während Wallbox-Betrieb). | Must | ✅ getestet + live |
| REQ-021 | Das EMS muss eine konfigurierbare SoC-Reserve der Hausbatterie respektieren und darf sie nicht aktiv unterschreiten. **Über die UI einstellbar, Default 0 %** (→ REQ-071). | Must | ✅ getestet |
| REQ-022 | Das EMS soll die Batterieladung zeitlich steuern können (z.B. mittags drosseln, wenn EV-Ladung Vorrang hat; vor Schlechtwetter voll laden). | Should | ⚪ offen (Stufe 3) |
| REQ-023 | Das EMS soll Netzladen der Batterie unterstützen, sobald ein dynamischer Tarif vorliegt (Billigstunden nutzen). | Should | ⚪ offen (Stufe 3) |
| REQ-024 | Bei Wegfall der EMS-Steuerung muss die E3DC auf ihre autonome Standardregelung zurückfallen (kein „hängender" Übersteuerungszustand). | Must | ✅ Lease/TTL (ADR-005), getestet |

## D — Dynamischer Tarif / Preisoptimierung *(Tarif geplant, noch nicht vorhanden)*

| ID | Anforderung | MoSCoW | Umsetzung |
|---|---|---|---|
| REQ-030 | Das EMS soll stündliche (bzw. viertelstündliche) Strompreise eines dynamischen Tarifs einlesen können. Die Anbindung ist als **austauschbarer Adapter** zu gestalten, vorbereitet auf die Top-5-Anbieter in Deutschland: **Tibber, Octopus Energy, Rabot Charge, Ostrom, aWATTar/EPEX Spot** (Anbieterliste bei Vertragsabschluss verifizieren). | Should | ⚪ offen (Stufe 3, wartet auf Vertrag) |
| REQ-031 | Das EMS soll verschiebbare Lasten (EV-Restladung, WW-Bereitung, Batterie-Netzladen) in die günstigsten Stunden legen, wenn kein PV-Überschuss verfügbar ist. | Should | ⚪ offen (Stufe 3) |
| REQ-032 | Das EMS soll ohne dynamischen Tarif vollständig funktionieren (Preislogik ist optionales Modul, kein Kernpfad). | Must | ✅ das ganze System läuft ohne Preisdaten |

## E — Erzeugung & Prognose

| ID | Anforderung | MoSCoW | Umsetzung |
|---|---|---|---|
| REQ-040 | Das EMS muss die Erzeugung beider Anlagen (E3DC-DC-seitig + Sungrow AC-seitig) zu einer Gesamterzeugung zusammenführen. | Must | ✅ getestet + live |
| REQ-041 | Das EMS soll eine PV-Ertragsprognose (mind. 24 h) über **Forecast.Solar** nutzen, um Ladeplanung und WP-Vorziehen vorausschauend zu steuern — konfiguriert für beide Anlagen (Ost 22° + Garagendach Ost/West 15°). | Must | 🔵 **Adapter fertig und getestet, aber von der Regelschleife nie gelesen** — die Planung nutzt keine Prognose |
| REQ-042 | Das EMS soll den Sungrow SG 6.0RT lokal auslesen (Modbus TCP bevorzugt, keine Cloud-Pflicht). | Must | ⚪ Stub (0 W) bis zur Installation Ende 2026 |
| REQ-043 | Das EMS soll Abregelungsverluste durch die **70 %-Einspeisebegrenzung** minimieren, indem Überschuss lokal verwertet wird (EV, WP, Batterie), statt ihn abregeln zu lassen. Die Begrenzung selbst **durchsetzen muss das EMS nicht**: Bestandsanlage → in der E3DC-Steuerung hinterlegt; Neuanlage → *Annahme lt. Elektriker Waldemar (2026-07-12): der Sungrow-Wechselrichter übernimmt das selbst.* Annahme bei Inbetriebnahme verifizieren. | Should | ✅ lokale Verwertung über EV + WP; Annahme zur Neuanlage bleibt zu verifizieren |

## F — Monitoring / Dashboard

| ID | Anforderung | MoSCoW | Umsetzung |
|---|---|---|---|
| REQ-050 | Das EMS muss seinen Zustand und jede aktive Übersteuerung sichtbar machen (aktueller Modus, warum lädt/lädt nicht, welche Regel greift). | Must | ✅ getestet + live (inkl. Entprellungs-/Sperr-Transparenz) |
| REQ-051 | Das EMS soll ein Dashboard mit **Hausverbrauch und allen Hauptverbrauchern** (Wallbox, Wärmepumpe, Batterie-Lade-/Entladeleistung) sowie Erzeugung, Prognose und Ladeplan bereitstellen. | Must | ✅ getestet + live — **Prognose und Ladeplan fehlen im Dashboard** (Folge von REQ-041) |
| REQ-052 | Das EMS soll Kennzahlen historisieren (Autarkie, PV-Anteil am EV-Laden, verschobene kWh), um den Nutzen gegen die Baseline 2025 zu belegen. | Should | 🔵 Snapshots + Auswertungs-API da, **Kennzahlen gegen die Baseline fehlen**; Historie erst seit v0.6.5 überhaupt haltbar |
| REQ-053 | Das EMS kann bei relevanten Ereignissen benachrichtigen (Ziel-SoC nicht erreichbar, Gerät nicht erreichbar, ungewöhnlicher Netzbezug). | Should | 🔵 Geräteausfall/-rückkehr im Protokoll und im Status, **keine aktive Benachrichtigung** |

## G — Sicherheit / Fallback

| ID | Anforderung | MoSCoW | Umsetzung |
|---|---|---|---|
| REQ-060 | Fail-Safe: Bei Ausfall des EMS, von HA oder einzelner APIs müssen alle Geräte in ihrem autonomen Standardverhalten weiterlaufen (keine Blockade von Laden/Heizen). | Must | ✅ E1/E2/E3/E5/E7 umgesetzt und getestet |
| REQ-061 | Das EMS muss manuelle Übersteuerung durch den Nutzer jederzeit zulassen und darf sie nicht „zurückdrehen" (Override mit definierter Gültigkeit). | Must | 🔵 für die WP erfüllt und getestet, **Wallbox-Override „bis Abstecken/24 h" fehlt komplett** |
| REQ-062 | Alle Steuerentscheidungen müssen nachvollziehbar geloggt werden (Zeitpunkt, Regel, Messwerte). | Must | ✅ getestet + live (`/api/v1/history`) |
| REQ-063 | Konfigurationsgrenzen (Min-SoC, Temperaturen, max. Schaltfrequenz) müssen zentral definiert sein; das EMS validiert gegen diese Grenzen vor jedem Steuerbefehl. | Must | ✅ getestet |
| REQ-064 | Das EMS soll Geräte schonen: keine schnellen Schaltzyklen (Hysterese/Mindestlaufzeiten für WP-Boost, Wallbox-Phasenumschaltung, Batterie-Modi). | Must | ✅ getestet (Wallbox und WP, inkl. Selbstabschalt-Falle) |

## H — Konfiguration & Bedienung (App/UI)

| ID | Anforderung | MoSCoW | Umsetzung |
|---|---|---|---|
| REQ-070 | Der Nutzer muss **beliebig viele Laderegeln** — jeweils mit **Wochentagen, Abfahrtszeit und frei definierbarem Mindest-SoC** — über ein Eingabefenster in der App **anlegen, ändern, deaktivieren und entfernen** können, ohne YAML/Code. Default-Regel: Mo–Fr, 07:30, 50 %. Regel-Modell in Spec §4.3. | Must | ✅ API + Dashboard; **die API-Endpunkte selbst sind ungetestet** |
| REQ-071 | Die SoC-Reserve der Hausbatterie muss über die App/UI einstellbar sein. **Default: 0 %.** | Must | ✅ API + Dashboard; `PUT /config` ungetestet |
| REQ-072 | Harte Grenzen (z.B. WW-Mindesttemperatur, EV-Mindest-SoC, Batterie-Limits) müssen über die App/UI einstellbar sein. **Default: keine Grenze aktiv** — das System läuft zunächst ohne harte Grenzen, sie sind aber nachrüstbar ohne Codeänderung. | Should | ✅ Wirkung getestet |
| REQ-073 | Konfigurationsänderungen über die UI müssen sofort wirken (kein Neustart) und persistent gespeichert werden. | Must | ✅ **persistent erst seit v0.6.5** — vorher lag die Konfiguration im Container und war nach jedem Update weg |
| REQ-074 | Die Bedienoberfläche wird als **eigenständige App** realisiert, die **vollständig im Heim-LAN funktioniert** — lokal gehostet, vom Smartphone/PC im LAN erreichbar, ohne Cloud- oder Internet-Abhängigkeit. Die EMS-Logik bleibt von der UI entkoppelt (definierte lokale Schnittstelle). *(Entschieden 2026-07-12: separate App statt HA-Dashboard.)* | Must | 🔵 Web-Dashboard erfüllt die LAN-Bedienung, **die Android-App ist Gerüst und wurde nie gebaut** |

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

1. ~~**70 %-Regel Neuanlage**~~ ✅ Beantwortet (2026-07-12, Elektriker Waldemar): Arbeitsannahme — **der Wechselrichter kümmert sich selbst darum**. In REQ-043 dokumentiert, bei Sungrow-Inbetriebnahme verifizieren.
2. ~~**UI-Entscheidung**~~ ✅ Entschieden (2026-07-12): **eigenständige App, funktioniert komplett im Heim-LAN** (REQ-074).
3. **MyVaillant-Steuerbarkeit:** Reichen die per Cloud verfügbaren Stellgrößen (WW-Boost, Sollwerte) praktisch aus? → **Teilantwort 2026-07-26 (v0.6.5):** Lesen funktioniert vollständig (Speicher-/Vorlauf-/Außentemperatur, Betriebsarten, COP). Beim **Schreiben** hat der erste echte Boost `water_heater.set_temperature` mit 60 °C ausgelöst — der Aufruf ging fehlerfrei durch (kein Fehler im EMS-Protokoll, keiner im HA-Log), der Sollwert stand danach aber weiter auf 45 °C. Verdacht: In der Betriebsart **`Auto`** (Zeitprogramm) übernimmt MyVaillant den Sollwert nicht, es müsste vorher `set_operation_mode` auf Tag-/Manuell-Betrieb. Das ist ein **Eingriff in Leos Heizungsprogramm** und deshalb bewusst nicht auf Verdacht umgesetzt. → Entscheidung Leo.
4. ~~**Migrations-Baseline**~~ ✅ Erledigt (2026-07-12): siehe [docs/evcc-baseline.md](../docs/evcc-baseline.md) — EVCC läuft als **Add-on** (nicht HACS), Site-Parameter, Loadpoint „Garage", Vehicle und Statistik-Baseline (99,4 % Solaranteil 30d) dokumentiert. Rest-Todo dort: `evcc.yaml`/Zugangsdaten vor der Ablösung sichern.

## Priorisierung (MoSCoW) — Ergebnis vom 2026-07-12

**26 Must, 13 Should, 0 Could, 3 Won't.** Kein Requirement wurde verworfen.

### Leitlinie

Die Musts bilden zusammen **Ausbaustufe 1: den EVCC-Ersatz** — Überschussladen des Enyaq inkl. Zielladung, Batterie-Koordination (Entladesperre, Reserve), Gesamterzeugung + Forecast.Solar, Dashboard, komplette Sicherheits- und UI-Basis. Die Shoulds verteilen sich auf zwei spätere Stufen.

### Ausbaustufen

| Stufe | Inhalt | Requirements | Voraussetzung | Stand 2026-07-26 |
|---|---|---|---|---|
| **1 — EVCC-Ersatz** | EV-Überschussladen, Batterie-Grundsteuerung, Prognose, Dashboard, Sicherheit, UI | alle Musts (REQ-001–008, 020/021/024, 032, 040–042, 050/051, 060–064, 070/071/073/074) | EVCC-Baseline dokumentieren (Fragen Runde 3) | 🔵 20 von 26 Musts fertig; offen: Forecast verdrahten (041), Wallbox-Override (061), Sungrow (042), EVCC-Ablösung (007/008), eigenständige App (074) |
| **2 — Wärmepumpe** | WW-Vorziehen, Heizkreis-Anhebung, Komfortgrenzen, Cloud-Robustheit | REQ-010–014 (Should) | MyVaillant-Praxistest bestanden | 🔵 Logik vollständig und getestet, Anbindung seit v0.6.5 live; **Schreibweg klären**, Heizkreis erst in der Heizperiode belegbar |
| **3 — Dynamischer Tarif** | Preis-Adapter, Lastverschiebung in Billigstunden, Batterie-Netzladen, Feinsteuerung | REQ-022/023, 030/031, 043, 052/053, 072 (Should) | Tarifvertrag abgeschlossen | ⚪ nicht begonnen (außer 043/072, die nicht tarifgebunden sind) |

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
