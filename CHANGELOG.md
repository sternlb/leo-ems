# Changelog

Versionshistorie des Add-ons **Leo-EMS**. Diese Datei liegt bewusst neben der
`config.yaml` in der Repo-Wurzel — genau dort sucht der Supervisor sie und zeigt
sie im Update-Dialog an. Ohne sie meldet Home Assistant
„No changelog found for app ed35676c_leo_ems!".

Ausführliche Begründungen zu jeder Änderung stehen in den Specs (`specs/`) und in
der Projektnotiz im Second Brain.

## 0.13.0

**Der Hausverbrauch stimmt wieder — und die Energiebilanz wird jetzt dauerhaft
mitgeschrieben.**

*Der Fehler.* Seit die Garagen-Anlage läuft, kann die E3DC den Hausverbrauch
nicht mehr richtig ausweisen. Der Sungrow ist AC-gekoppelt und speist hinter
ihrem Zähler ein; sie sieht davon nur weniger Bezug bzw. mehr Einspeisung und
rechnet ihren Hausverbrauch deshalb um die Garagen-Erzeugung zu klein. Wird die
Bilanz negativ, meldet sie schlicht **0 W** — genau so stand es am 22.08.2026 im
HA-Dashboard. Betroffen ist alles, was auf `sensor.s10e_house_consumption`
aufsetzt, auch rückwirkend in der E3DC-App.

*Neue Sensoren.* Das EMS kennt beide Anlagen und ist damit die einzige Stelle,
die den Wert bilden kann:

| Entity | Inhalt |
|---|---|
| `sensor.hausverbrauch_leistung` | Hausverbrauch **ohne** Wallbox, W |
| `sensor.hausverbrauch_gesamt_leistung` | Hausverbrauch **mit** Wallbox, W |

Zwei Werte, weil zwei Fragen dahinterstehen: Die Flussdarstellung zeichnet die
Wallbox als eigenen Verbraucher und darf sie nicht doppelt zählen, der kWh-
Zähler im HA-Energie-Dashboard will dagegen den Gesamtverbrauch. Fällt die
Bilanz aus (Fail-Safe E1), wird **kein** Wert geschrieben statt einer 0 — eine
gemeldete Null würde der Riemann-Integrator in HA als echte Messung integrieren.

*Energie-Historie (Issue #13).* Neue Tabelle `energie_tag` in der Add-on-
Datenbank: je Tag eine Zeile mit PV Haus, PV Garage, Netzbezug, Einspeisung,
Batterie laden/entladen, Hausverbrauch und Wallbox. Der Zähler integriert die
Tick-Leistungen im Speicher und schreibt höchstens minütlich; Messlücken über
zwei Minuten werden **nicht** überbrückt, sondern gezählt. Neue Endpunkte:

| Endpunkt | Inhalt |
|---|---|
| `GET /api/v1/energie/tage?von=&bis=` | Tageswerte in kWh |
| `GET /api/v1/energie/monate?jahr=` | Monatssummen |
| `GET /api/v1/energie/jahre` | Jahressummen |
| `GET /api/v1/energie/export.csv?ebene=` | CSV (Semikolon, Dezimalkomma) |
| `POST /api/v1/energie/import?von=&bis=` | Historie aus der E3DC nachladen |
| `GET /api/v1/energie/import` | Fortschritt des laufenden Imports |

Der Import holt die Jahre vor dem EMS aus der E3DC-eigenen Datenbank, Tag für
Tag im Hintergrund. Er überschreibt **nie** eine eigene Messung, erkennt die
Bedeutung von `grid_power_in/out` aus der Bilanz statt sie zu raten, und
markiert Tage ab `pv_garage_seit` als `e3dc-ohne-garage` — dort ist der
Hausverbrauch aus dem gleichen Grund zu klein wie oben.

Im Dashboard: neue Sektion **Energie-Historie** mit Monats-/Jahrestabelle,
CSV-Download und dem Import-Knopf. 187 Tests grün.

## 0.12.0

**Die PV-Werte stehen jetzt auch in Home Assistant — als eigene Sensoren.**

Neue Entities, im Takt von 30 s vom EMS geschrieben:

| Entity | Inhalt |
|---|---|
| `sensor.pv_haus_leistung` | Hausdach-Anlage (E3DC), W |
| `sensor.pv_garage_leistung` | Garagendach-Anlage (Sungrow), W |
| `sensor.pv_gesamt_leistung` | beide zusammen, W |
| `sensor.pv_garage_ertrag_gesamt` | Zählerstand der Garagen-Anlage, kWh |

- **Warum das EMS pusht, statt HA selbst lesen zu lassen:** Der WiNet-S-Dongle
  nimmt nur **eine** Modbus-Verbindung an. Eine zusätzliche HA-Modbus-Integration
  würde sich mit dem EMS um dieselbe Verbindung streiten und beide bekämen
  Aussetzer. Es gibt genau einen Modbus-Leser, und der reicht weiter.
- Auch die Hausdach-Anlage wird exportiert, obwohl es `sensor.s10e_solar_production`
  längst gibt: In einem gemeinsamen Diagramm müssen die Linien denselben
  Zeitraster haben, sonst treppen sie gegeneinander. Aus einer Quelle gepusht
  tragen sie denselben Zeitstempel.
- Der Ertragszähler ist `total_increasing` — damit kann die Garagen-Anlage im
  **HA-Energie-Dashboard** auftauchen.
- **Der Export läuft nebenläufig und hält den Regeltick nie auf.** Beim ersten
  Entwurf wartete der Tick auf die HTTP-Antwort: Bei hängendem Home Assistant
  hätte das die Regelschleife bis zu 12 s pro Tick angehalten — bei 10 s
  Tick-Intervall hätte die Anzeige die Steuerung ausgebremst. Aufgefallen ist es
  daran, dass die Testsuite von 4 s auf 174 s sprang.
- Ohne `SUPERVISOR_TOKEN` (Entwicklung am PC) ist der Export inaktiv statt in
  vergebliche Verbindungsversuche zu laufen.

170 Tests grün (8 neue).

## 0.11.1

**Die Garagen-Anlage leuchtet jetzt mit.**

- Auf dem Garagendach standen im Szenenbild **gar keine Module** — die Anlage
  erschien nur als Chip, während das Hausdach bei Erzeugung glimmte. Jetzt
  liegt dort eine Ost/West-Aufständerung mit sechs Zacken: ein Modulpaar je
  Zacke, zwölf Module, je Flanke ein String an einem MPPT-Eingang.
- Eigener Leuchtzustand `.sg-an` mit eigener Intensität `--sg-i` aus der
  Sungrow-Leistung. Bezugswert sind 4 kW statt der 6 kW des Hausdachs: 5,64 kWp
  Ost/West erreichen wegen der geteilten Ausrichtung real kaum mehr; mit dem
  größeren Nenner bliebe die Garage dauerhaft blasser, obwohl sie voll läuft.
- Zwei Funken statt vier — die Modulfläche im Bild ist kleiner, vier wirkten
  darauf wie ein Blinklicht. Einbrennschutz und `prefers-reduced-motion` gelten
  unverändert auch für den neuen Zustand.

## 0.11.0

**Die Garagen-Anlage ist da — 5,64 kWp mehr, jetzt auch im EMS sichtbar.**

- **Sungrow SG 6.0RT angebunden** (REQ-042): Der Wechselrichter der neuen
  Garagendach-Anlage wird per **Modbus TCP** gelesen, ohne Cloud. Seine Leistung
  fließt in die Gesamterzeugung — das Dashboard zeigt ab sofort beide Anlagen.
- **Neue Add-on-Optionen** `sungrow_port` und `sungrow_unit_id`. Die Unit-ID ist
  am WiNet-S-Dongle nirgends ablesbar und musste abgetastet werden (hier: 1).
  Als Option lässt sie sich bei einem Gerätetausch neu setzen, ohne das Add-on
  neu zu bauen. Ein leerer `sungrow_host` bleibt der Stub mit 0 W.
- **Strang-Diagnose im Status**: Spannung und Strom beider MPPT-Eingänge,
  Tages- und Gesamtertrag, Innentemperatur, Netzfrequenz. Bei zwei gleich
  bestückten Strings à 6 Modulen müssen beide Spannungen dicht beieinander
  liegen — driften sie auseinander, ist ein String gestört.
- **Der Sungrow-Wert geht bewusst NICHT in die Überschussformel.** Die Anlage
  ist AC-gekoppelt und erscheint bereits im Netzzähler der E3DC. Doppelt gezählt
  sähe das EMS einen Überschuss, den es nicht gibt, und gäbe zu viel
  Ladeleistung frei.
- **Fail-Safe E5 bleibt scharf**: Fällt der Wechselrichter aus, wird die
  Erzeugung 0 und der Betrieb läuft unverändert weiter. Die Ertragszähler sind
  davon ausgenommen — sie sind reine Anzeige und dürfen die Leistungsmessung
  nicht mitreißen.
- **Ohne pymodbus.** Gebraucht wird ein einziger Funktionscode; die ~40 Zeilen
  Modbus-TCP stehen jetzt direkt im Adapter, gegen die reale Anlage verifiziert.
  pymodbus hat den Slave-Parameter zwischen 3.7 und 3.9 umbenannt — diese
  Fallhöhe entfällt damit, und das Image baut eine Abhängigkeit weniger.
- **Einspeisebegrenzung geklärt** (REQ-043): Für die Neuanlage gilt **60 %**,
  durchgesetzt über die E3DC am gemeinsamen Netzverknüpfungspunkt. Der Sungrow
  läuft unbegrenzt — der ausgelesene Sollwert von 100 % ist der gewollte
  Zustand. Damit vermeidet die lokale Überschussverwertung nicht mehr nur
  Netzbezug, sondern **Abregelung**.

17 neue Tests (162 gesamt, alle grün), darunter ein Ende-zu-Ende-Lauf gegen einen
nachgebauten WiNet-S. Zusätzlich am 2026-08-22 gegen die reale Anlage verifiziert.

## 0.10.0

**Die Fahrzeugbatterie wird geschützt — und die Hausbatterie darf das Auto laden, wenn du es willst.**

Fahrzeug-Ladelimit (Issues #9/#10):

- Das Ladelimit steht jetzt in der Konfiguration und **überlebt Add-on-Updates**.
  Bisher war es eine Variable in der Regelschleife und bei jedem Neustart wieder
  auf dem Startwert — bei aktivem `auto_update` also regelmäßig.
- Neue **harte Obergrenze** `hard_limit_ev_max_soc`, Default **80 %**. Ein höheres
  Ladelimit lehnt die API mit Klartext ab; wer wirklich mehr will, hebt zuerst
  die Grenze. Das Dashboard zeigt sie im Feld-Label an.
- Die **Garantieladung** wird mitgedeckelt. Eine Laderegel mit Mindest-SoC 90 %
  hätte das Auto sonst per Netzstrom über die Schutzgrenze gezogen — sie
  übersteuert laut Spec alles, auch den Modus „Aus".
- Der Default-Parameter `vehicle_limit_soc = 100` in der Ladesteuerung ist weg:
  ein vergessenes Argument ist jetzt ein Fehler, kein stilles Laden bis 100 %.

Batterie ins Auto (Issue #11):

- Neuer Schalter **„Hausbatterie im Modus Schnell mitnutzen"** (Default aus).
  Bis v0.9.0 war die Batterie in genau diesem Modus hart gesperrt.
- Neuer Lademodus **„PV+Batterie" — Schnellladen ohne Netzbezug**: geregelt wird
  gegen PV *plus* Hausbatterie, der Netzbezug bleibt bei ≈ 0. Es ist dieselbe
  Zustandsmaschine wie „Nur-PV", nur mit größerem Budget — die bekannte
  Abschalthysterese greift unverändert, sobald auch das nicht mehr reicht.
- **Untergrenze ist die Batterie-Reserve** (`soc_reserve_pct`, mit 2 Punkten
  Hysterese). Der Parameter wurde bis v0.9.0 nirgends durchgesetzt — **bitte vor
  dem ersten Schnellladen setzen**, mit dem Default 0 % darf das Auto die
  Hausbatterie bis auf null ziehen. Der Vorrang-SoC (25 %) gilt hier bewusst
  nicht: er ist eine Heuristik für die Automatik-Modi.
- Die Wärmepumpe rechnet weiter mit dem reinen PV-Überschuss — die Freigabe gilt
  dem Auto, sonst liefe die Hausbatterie über den Warmwasser-Boost leer.
- `batt_dyn_aktiv: false` bleibt der Notausstieg und sticht auch die Freigabe.
- 146 Tests grün (27 neue).

## 0.9.0

**Die Hausbatterie darf beim EV-Laden einspringen — dynamische Entladegrenze statt harter Sperre.**

- Statt `max_discharge = 0` folgt die Entladegrenze jetzt dem gemessenen
  Restbedarf des Hauses: `min(max(0, P_netz) + max(0, −P_batterie) + 200 W, 3000 W)`.
  Damit fällt der Netzbezug weg, der bei Regelübergängen, im 3p-Mindestband und
  bei plötzlichen Lasten (Backofen, Wolkenzug) entstand.
- Hoch wird sofort geregelt, runter nur 500 W je Tick.
- **Hart gesperrt bleibt es, wo Netzbezug Absicht ist:** Modus Schnell,
  Garantieladung und das 6-A-Minimum bei PV+Min — sowie unterhalb des
  Vorrang-SoC von 25 % (Hysterese 2 Punkte).
- Begleitfix: Batterieentladung wird jetzt vom Überschuss abgezogen. Sonst hätte
  die Wallbox die Deckung als PV-Überschuss gesehen und sich selbst aus der
  Batterie gespeist.
- RSCP-Ablehnungen (`-1`) werfen jetzt, statt stumm durchzulaufen.
  Schreibdrossel: 50-W-Raster, 100-W-Schwelle.
- Notausstieg ohne Deployment: `batt_dyn_aktiv: false` per API = Verhalten v0.8.0.
- 117 Tests grün.

## 0.8.0

**Vorrang Wallbox vor Wärmepumpe (Issue #6) und kein Netzbezug mehr bei 3p (Issue #7).**

- Der Anteil eines *laufenden* WP-Boosts wird aus dem Hausverbrauch
  zurückgerechnet und zuerst der Wallbox zugeteilt. Vorher drückte die WP den
  gemessenen Überschuss um ~2 kW und die Wallbox kam nicht über ihre
  Einschaltschwelle.
- Weicht ein Boost dem Auto, gilt die Mindestlaufzeit nicht.
- Die Abschaltbedingung war phasenblind: geprüft wurde gegen das 1p-Minimum
  (1,38 kW), auch während 3-phasig geladen wurde — 3p braucht aber 4,14 kW. In
  diesem Band lief die Ladung dauerhaft aus dem Netz weiter. Jetzt wird je Tick
  zuerst die Phasenzahl nachgeführt, dann gegen deren Minimum geprüft.
- Phasenumschaltung asymmetrisch: hoch wie bisher (4,2 kW / 60 s / 10 min
  Abstand), runter nach 60 s und ohne Abstand. `phase_down_w` jetzt 4140 W.
- Dashboard: Die Überschuss-Kachel zeigt den *verteilbaren* Wert, das
  Hausverbrauch-Panel schlüsselt auf (gemessen → WP-Boost → verteilbar → Wallbox).
- 100 Tests grün.

## 0.7.0

**Warmwasser und Heizkreis getrennt schaltbar (Issue #1).**

- Neue Schalter `wp_ww_aktiv` (Default an) und `wp_hk_aktiv` (Default aus),
  bedienbar direkt in der Überschrift der WP-Kachel.
- Ausschalten wirkt sofort: ein laufender Boost wird zurückgestellt, ohne
  Mindestlaufzeit und am 15-min-Cloud-Gap vorbei.
- Die Schalter stehen in der Konfiguration, nicht am Gerät — sie gelten und sind
  bedienbar, auch wenn die WP gerade nicht antwortet.
- **Boost-Ziel von 60 auf 57 °C:** Der Speicher erreicht real nur ~57,5 °C, damit
  wurde „Ziel erreicht" nie wahr und jeder Boost lief bis zum Überschuss-Ende.
- Bestätigt: Der MyVaillant-Schreibweg funktioniert in Betriebsart `Auto`, ohne
  Eingriff ins Heizungsprogramm.
- 92 Tests grün.

## 0.6.5

**Start über `run.sh` mit `with-contenv` — Wurzel zweier stiller Fehler.**

- Die HA-Basis-Images starten über s6-overlay, und s6 führt das `CMD` mit
  bereinigter Umgebung aus. Das Add-on sah genau vier Variablen.
- Folge 1: kein `SUPERVISOR_TOKEN` → die Wärmepumpe bekam auf allen vier
  Zugangswegen zur HA-API HTTP 401.
- Folge 2: kein `LEO_EMS_DATA_DIR` → Daten lagen unter `/app/data` im Container.
  **API-Token, Regel-Konfiguration und Beobachtungs-Datenbank waren nach jedem
  Add-on-Update weg**, inklusive `read_only` — das EMS fiel bei jedem Update
  stillschweigend in den Beobachtungsmodus zurück.
- Regressionsschutz: `test_addon_paket.py` hält die Verpackungs-Zusagen fest,
  `.gitattributes` erzwingt LF für `run.sh` (CRLF im Shebang killt den Container).

## 0.6.4

- Diagnose-Endpunkt `GET /api/v1/diag/umgebung` — er hat den Umgebungs-Fehler
  überhaupt erst sichtbar gemacht.

## 0.6.3

- Add-on-Token für die HA-API verdrahtet (`homeassistant_api` + `hassio_api`).
- Škoda-Adapter repariert: myskoda hat das vertippte Feld
  `state_of_charged_in_percent` korrigiert — deshalb war `soc_fahrzeug` seit dem
  Go-live immer `null`. Liest jetzt wieder den echten SoC.

## 0.6.2

- Wärmepumpe findet ihren Weg zu Home Assistant: Zugang über
  `http://supervisor/core/api`, Lese-Gesundheit je Gerät in `status.geraete`,
  neuer Endpunkt `GET /api/v1/diag/devices`. Geräteausfall und -rückkehr stehen
  jetzt im Protokoll.

## 0.6.1

**Energieflüsse laufen in die richtige Richtung.**

- Jede Flusskurve war fest vom Knoten zum Haus gezeichnet — Einspeisung sah aus
  wie Bezug, Batterieladung wie Entladung, die Wallbox speiste scheinbar ein.
  Die Richtung steckt jetzt in der Geometrie statt in der Animation.
- Beim Laden zeigt die Batterie ihre Quelle: PV → Batterie bei Erzeugung, sonst
  Haus → Batterie (Netzladung).
- Bei `prefers-reduced-motion` gibt es jetzt einen Richtungspfeil (die Perlen
  stehen dort still, die Richtung war gar nicht ablesbar).

## 0.6.0

**Räumliche Tiefe in der Energy-Flow-Szene.**

- Licht und Schatten auf Fassade, Laibungen und Boden.
- Parallax über acht Ebenen (Zeigerbewegung bzw. Tablet-Neigung, ±9 px, nur waagerecht).
- Flüsse als Röhren: Schattenkern, Körper, Leuchtsaum, laufende Ladungsperlen.
- Tageszeit-Licht, rein lokal gerechnet (kein Cloud-Call).

## 0.5.0

**Die Szene wird lebendig.**

- Garagentor öffnet und der Enyaq rollt heraus, sobald das Auto angesteckt ist.
- PV-Modulfeld glimmt bei Erzeugung, Intensität aus der Leistung.
- WP-Lüfter dreht, solange die Anlage läuft (schneller im Überschuss-Boost).
- Neue Wärmepumpen-Skizze nach der Vaillant-aroTHERM-Referenz.
- Neues Statusfeld `wp.laeuft`. `prefers-reduced-motion` schaltet alle
  Bewegungen ab, die Zustände bleiben statisch ablesbar.

## 0.4.0

- **Wärmepumpe im EMS (Ausbaustufe 2):** PV-Überschuss steuert Warmwasser und
  Heizkreis, Anzeige zweigeteilt mit Temperaturen.
- Vorrang Auto vor Wärmepumpe eingeführt (griff zunächst nur, solange die WP noch
  nicht lief — vollständig erst ab v0.8.0).
- Batterie-Kachel zeigt den SoC in Prozent.

## 0.3.2

- Die Hausansicht wurde auf dem Handy unten abgeschnitten (Wärmepumpe, Terrasse,
  Boden fielen weg). Ursache: `preserveAspectRatio="…slice"` bei flachem
  Container, Fix auf `meet`.
- Erste Version, die über das Add-on-Repository automatisch ausgerollt wurde.

## 0.3.1

**Dashboard im Handy-Hochkant lesbar.**

- Labels und Badges vergrößert, Touch-Ziele auf 44 px.
- Protokoll bricht um statt seitlich zu scrollen, Laderegeln werden zu
  gestapelten Karten.
- Hero-Szene und die Sektionen Einstellungen/Laderegeln/Protokoll einklappbar
  (Zustand je Sektion gemerkt). Scrollhöhe −44 %. Desktop unverändert.

## 0.3.0

- **Energy-Flow-Szene im Dashboard** (Spec 04): stilisierte Ostansicht des Hauses
  mit Live-Daten aus `/api/v1/status`, Detail-Panels, Fail-Safe E1 als Warnbanner.
- Ganzes Dashboard auf die helle Palette umgestellt.

## 0.2.2

- Zwischenschritt: 2D-Lastverteilungsdesign mit echten Produktfotos (durch die
  Energy-Flow-Szene in 0.3.0 ersetzt).

## 0.2.1

- 3D-Lastverteilungs-Szene: isometrisches Haus nach den Bauplan-Ansichten, PV auf
  der Ost-Dachfläche, Enyaq in der Einfahrt, E3DC-Speicher mit Live-SoC.

## 0.2.0

- **Web-Dashboard direkt in Home Assistant** über Add-on-Ingress, als eigener
  Eintrag in der Seitenleiste. Auth über die HA-Anmeldung, im LAN weiterhin Token.
- Inhalte: Energieverteilung, Ladestatus mit Klartext-Grund, Einstellungen
  (inkl. `PUT /api/v1/mode`), Laderegeln, Protokoll.
- **`phasen_info` im Status:** beantwortet „Überschuss da, warum lädt er nur 1p?"
  — Entprellung mit Fortschritt, 10-min-Umschaltsperre mit Restzeit und Grund.

## 0.1.2

- Token-Ausgabe im Add-on-Log erschien nicht (Docker-stdout-Pufferung).

## 0.1.1

- Pi-Build repariert: Basis-Image auf Python 3.13, weil myskoda >= 2.0 das verlangt.

## 0.1.0

- **Erste lauffähige Add-on-Version.** Regelschleife (10 s), Ladesteuerung mit
  Hysterese und 1↔3-Phasenumschaltung, alle vier Lademodi, Zielladung als
  Regelliste, Entladesperre als Lease mit TTL, Fail-Safe-Matrix.
- Adapter: E3DC (RSCP), go-e, Škoda, Forecast.Solar, Sungrow (Stub).
- **Beobachtungsmodus `read_only` (Default an):** volle Entscheidungslogik, null
  Gerätebefehle — die Erstinstallation läuft gefahrlos parallel zu EVCC.
  10-s-Snapshots in SQLite plus Auswertungs-API.
- API v1 auf Port 8099, Bearer-Token, aarch64- und amd64-Build.
