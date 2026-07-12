# 01 — Requirements

**Status:** Phase 1 laufend — alle Einträge sind **Kandidaten (Entwurf)**, keine Zusagen.
**Stand:** 2026-07-12

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
| REQ-003 | Das EMS muss eine Zielladung unterstützen: bis zur konfigurierten Abfahrtszeit muss der Enyaq einen Ziel-SoC erreichen — notfalls mit Netzstrom. | | Entwurf |
| REQ-004 | Das EMS muss einen Mindest-SoC des Enyaq garantieren, der unabhängig von PV-Angebot immer schnellstmöglich hergestellt wird. | | Entwurf |
| REQ-005 | Das EMS muss Lademodi anbieten (mindestens: Nur-PV, PV+Min, Schnell/Egal-woher, Aus), umschaltbar über HA. | | Entwurf |
| REQ-006 | Das EMS soll den SoC und Ladezustand des Enyaq aus der Fahrzeug-Integration einbeziehen (nicht nur Wallbox-Zählerstand). | | Entwurf |

## B — Wärmepumpen-Steuerung

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-010 | Das EMS soll bei anhaltendem PV-Überschuss die Warmwasserbereitung der Vaillant WP vorziehen (Boost/Sollwert-Anhebung mittags statt abends). | | Entwurf |
| REQ-011 | Das EMS soll bei PV-Überschuss die Heizkreis-Solltemperatur moderat anheben können (thermische Speicherung im Gebäude/Puffer). | | Entwurf |
| REQ-012 | Das EMS darf Komfortgrenzen nie verletzen (Warmwasser-Mindesttemperatur, Raumtemperatur-Korridor); Grenzen sind konfigurierbar. | | Entwurf |
| REQ-013 | Das EMS muss die Ratenlimits der MyVaillant-Cloud-API respektieren (Anfrage-Budget, keine Dauerschleifen). *Abhängig von der Antwort zur SG-Ready-Frage ggf. obsolet.* | | Entwurf |

## C — Batterie-Management (E3DC)

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-020 | Das EMS soll verhindern, dass die E3DC-Batterie sich während des EV-Ladens ins Auto entlädt (Entladesperre bzw. Entladelimit während Wallbox-Betrieb). | | Entwurf |
| REQ-021 | Das EMS muss eine konfigurierbare SoC-Reserve der Hausbatterie respektieren und darf sie nicht aktiv unterschreiten. | | Entwurf |
| REQ-022 | Das EMS soll die Batterieladung zeitlich steuern können (z.B. mittags drosseln, wenn EV-Ladung Vorrang hat; vor Schlechtwetter voll laden). | | Entwurf |
| REQ-023 | Das EMS soll Netzladen der Batterie unterstützen, sobald ein dynamischer Tarif vorliegt (Billigstunden nutzen). | | Entwurf |
| REQ-024 | Bei Wegfall der EMS-Steuerung muss die E3DC auf ihre autonome Standardregelung zurückfallen (kein „hängender" Übersteuerungszustand). | | Entwurf |

## D — Dynamischer Tarif / Preisoptimierung *(Tarif geplant, noch nicht vorhanden)*

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-030 | Das EMS soll stündliche (bzw. viertelstündliche) Strompreise eines dynamischen Tarifs einlesen können; die Anbieter-Anbindung ist austauschbar zu gestalten. | | Entwurf |
| REQ-031 | Das EMS soll verschiebbare Lasten (EV-Restladung, WW-Bereitung, Batterie-Netzladen) in die günstigsten Stunden legen, wenn kein PV-Überschuss verfügbar ist. | | Entwurf |
| REQ-032 | Das EMS soll ohne dynamischen Tarif vollständig funktionieren (Preislogik ist optionales Modul, kein Kernpfad). | | Entwurf |

## E — Erzeugung & Prognose

| ID | Anforderung | MoSCoW | Status |
|---|---|---|---|
| REQ-040 | Das EMS muss die Erzeugung beider Anlagen (E3DC-DC-seitig + Sungrow AC-seitig) zu einer Gesamterzeugung zusammenführen. | | Entwurf |
| REQ-041 | Das EMS soll eine PV-Ertragsprognose (mind. 24 h) nutzen, um Ladeplanung und WP-Vorziehen vorausschauend zu steuern (Quelle offen: Forecast.Solar / Solcast / E3DC). | | Entwurf |
| REQ-042 | Das EMS soll den Sungrow SG 6.0RT lokal auslesen (Modbus TCP bevorzugt, keine Cloud-Pflicht). | | Entwurf |
| REQ-043 | Das EMS soll eine ggf. bestehende Einspeisebegrenzung des Netzbetreibers berücksichtigen (Abregelung vermeiden = Überschuss lokal verwerten). *Auflagen der Stadtwerke Röthenbach zu klären.* | | Entwurf |

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

---

## Offene Fragen (Input für Requirements-Interview)

1. **WP-Anbindung:** SG-Ready-Kontakte verdrahtet oder nur MyVaillant-Cloud? → entscheidet über REQ-010/011/013-Machbarkeit.
2. **E3DC schreibend:** Ist die RSCP-Integration schreibend getestet (Ladeleistung, Entladesperre, Netzladen)?
3. **EV-Nutzung:** Typische Abfahrtszeiten (Pendeltage Neumarkt)? Mindest-SoC? Wer außer Leo nutzt das Auto?
4. **Batterie-Reserve:** Gewünschter Mindest-SoC? Notstromanforderung?
5. **Tarifanbieter:** Welcher dynamische Tarif ist angepeilt (Tibber, aWATTar, Ostrom …)?
6. **Prognosequelle:** Forecast.Solar, Solcast oder E3DC-intern?
7. **Einspeisebegrenzung:** Auflagen der Stadtwerke Röthenbach (70 %-Regel, §14a EnWG) für Bestand + Neuanlage?
8. **Sungrow:** Modbus TCP direkt möglich (LAN in Garage)? Welche HA-Integration?
9. **Dashboard:** Was willst du auf einen Blick sehen, und wo (HA, Handy)?
10. **Harte Grenzen:** Was darf das EMS *nie* tun?

## Priorisierung (MoSCoW)

> Folgt am Ende von Phase 1 — gemeinsame Durchsicht aller Kandidaten, dann Einstufung Must/Should/Could/Won't und Sortierung.
