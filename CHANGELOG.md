# Changelog

Versionshistorie des Add-ons **Leo-EMS**. Diese Datei liegt bewusst neben der
`config.yaml` in der Repo-Wurzel — genau dort sucht der Supervisor sie und zeigt
sie im Update-Dialog an. Ohne sie meldet Home Assistant
„No changelog found for app ed35676c_leo_ems!".

Ausführliche Begründungen zu jeder Änderung stehen in den Specs (`specs/`) und in
der Projektnotiz im Second Brain.

## 0.17.0

**Die Übersicht zeigt wieder das, was läuft — und ein Klick auf eine Kachel
zeigt den Tagesverlauf dahinter (Issue #14).**

*Konfiguration hat die Seite gewechselt.* Wer nachsehen wollte, ob das Auto
lädt, scrollte bisher an zwölf Zahlenfeldern für Phasenumschaltschwellen
vorbei. Es gibt jetzt einen dritten Reiter **Einstellungen**; dorthin sind alle
Zahlenfelder gewandert (Ströme, SoC-Schwellen, WP-Temperaturen, Phasen- und
Zeitparameter), dazu die Laderegeln und das Protokoll. Die Aufteilung folgt der
Häufigkeit, mit der man etwas braucht, nicht der technischen Verwandtschaft.

Auf der Übersicht bleibt, was man im Alltag anfasst: der **Lademodus**, der
Schalter „Hausbatterie im Modus Schnell mitnutzen", die beiden
Wärmepumpen-Schalter und **Scharf schalten / In Beobachtung wechseln** — der
wichtigste Schalter des Systems gehört dorthin, wo man ihn sieht.

*Neu: Tagesverlauf im Detailfenster.* Ein Klick auf eine Kachel — PV, Haus,
Batterie, Netz, Wallbox — öffnet die Einzelheiten dahinter, jetzt mit dem
Verlauf des heutigen Tages über 24 Stunden. Das Fenster gab es schon, aber nur
über die Hausansicht-Grafik erreichbar, und die ist auf dem Handy eingeklappt;
praktisch existierte es dort nicht.

*Die Wärmepumpe bekommt kein Verbrauchsdiagramm, sondern ein Aktivitätsband.*
Sie hat keinen eigenen Zähler, ihr Verbrauch steckt im Hausverbrauch — eine
Kurve wäre geraten. Was das EMS sicher weiß, ist, wann es Boost bzw. Anhebung
angefordert hat: Das steht ab sofort in jedem Tick-Snapshot und wird als Band
über den Tag gezeigt, mit der Summe in Minuten. Stunden, in denen das EMS nicht
lief, sind gestreift und nicht etwa leer — „nicht gemessen" ist eine andere
Aussage als „lief nicht".

Aufbau und Begründungen: `docs/dashboard.md`.

## 0.16.1

**Die Tagesansicht der Historie zeigt wieder einen ganzen Tag (Issue #17).**

*Der Fehler.* Am 27.08.2026 standen in der Tagesansicht zwei Säulen über die
volle Breite, und darüber eine Bilanz von 57,9 kWh Erzeugung — aber gerechnet
aus genau diesen zwei Stunden. Die Stundentabelle kam an dem Tag um 22:46 dazu
(v0.15), mehr als 22:00 und 23:00 gibt es für den 27. nicht und wird es nie
geben: Stunden lassen sich nicht nachtragen. Die Ansicht hat daraus stillschweigend
„der Tag" gemacht.

*Die Behebung, zwei Teile.* Ein Tag hat jetzt **immer 24 Säulen** — nicht
gemessene Stunden bleiben sichtbar leer, statt dass die vorhandenen sich über
die Breite verteilen. Und die **Kennzahlen kommen aus der Tageszeile**
(`energie_tag`) statt aus der Summe der Stunden. Die Tageszeile kennt den ganzen
Tag, auch den aus der E3DC nachimportierten; die Stunden sind ihre
Aufschlüsselung, nicht ihre Quelle. Über der Ansicht steht die Abdeckung
(„2 von 24 Stunden") und, wenn sie unvollständig ist, warum.

*Was bewusst gleich bleibt.* Der CSV-Export liefert weiter nur die echten
Stundenzeilen. Das Raster ist Anzeige; 22 erfundene Nullzeilen in einer Datei,
mit der jemand weiterrechnet, wären etwas anderes als eine ehrliche Lücke.

## 0.16.0

**Der Warmwasser-Sollwert kommt jetzt zuverlässig auf 45 °C zurück — und ein
Boost startet nicht sofort wieder.**

*Der Fehler.* In der Nacht zum 28.08.2026 stand der Warmwasser-Sollwert
durchgehend auf 57 °C. Gegen 06:20 heizte die Wärmepumpe den Speicher von 52
auf 57 °C nach — ohne Sonne, also aus der Hausbatterie, die dadurch auf 0 %
gefahren wurde. Um 06:49 nahm das EMS den Sollwert zurück, weil es die 57 °C
endlich als „erreicht" sah.

*Die Ursache.* Das EMS hat die Rückstellung sehr wohl versucht: Der Boost endete
um 18:38, danach ging fünfzehnmal 45 °C raus, bis 22:09. Angekommen ist keiner
davon — die MyVaillant-Integration war ausgefallen und kam erst um 22:19:58
zurück, mit 57 °C auf der Anlage. Home Assistant nimmt einen Service-Call auch
dann an, wenn die Integration ihn nicht weiterreicht; das EMS sieht keinen
Fehler. Ab 22:20 gab es dann gar kein offenes Ziel mehr, das hätte wiederholt
werden können, und der Controller sah die 57 °C nur noch als fremden Wert an,
den er nicht anfasst. Um 05:30 öffnete das Warmwasser-Zeitprogramm der Anlage
(Mo–Fr 05:30–22:00) und die WP heizte auf die stehen gebliebenen 57 °C hoch.

*Die Behebung.* Zurückgestellt wird jetzt nach **Zustand** statt nach Ereignis:
Läuft kein Boost und steht auf der Anlage trotzdem der Boost-Sollwert, setzt
das EMS `wp_ww_normal_c` — in jedem Tick aufs Neue, also selbstheilend. Eng
gefasst auf den eigenen Boost-Wert (≥ `wp_ww_boost_c` − 0,5 K), damit ein von
Hand in der MyVaillant-App gestellter Zwischenwert stehen bleibt.

*Neu: Wiedereinschalt-Schwelle `wp_ww_wieder_c` (53 °C).* Bisher war ein neuer
Boost erlaubt, sobald der Speicher unter 56,5 °C fiel — also Minuten nach dem
letzten. Jetzt sperrt ein erreichtes Boost-Ziel den nächsten Boost, bis der
Speicher unter 53 °C fällt. Der Wert steht in der Konfiguration unter
„Wärmepumpe — Überschuss-Nutzung" und wird intern auf `wp_ww_boost_c` − 0,5 K
gedeckelt, damit eine zu hohe Eingabe wirkungslos bleibt statt dauerhaft zu
sperren.

*Ein ausgefallener Sensor ist jetzt ein Ausfall.* Der Adapter zählte nur solche
Sensoren als „nicht lesbar", deren Abfrage eine Ausnahme wirft. Ein Sensor, der
brav `unavailable` antwortet, wurde still zu None — und eine Entity, die HA gar
nicht mehr kennt (404), ebenso. Der Status meldete deshalb tagelang „Wärmepumpe
in Ordnung", während das Rücklesen tot war. Beide Fälle stehen jetzt in
`geraete.vaillant.fehler`. Ist **kein einziger** Sensor lesbar, greift der
Fail-Safe E7 wie bei einem Verbindungsabbruch: keine Entscheidung, keine
Befehle — statt auf lauter None-Werten weiterzuregeln.

*Schreibversuche haben eine Obergrenze.* Ein Sollwert galt als offen, bis das
Rücklesen ihn bestätigt, und wurde bis dahin alle 15 Minuten wiederholt. Fällt
das Rücklesen aus, kann diese Bestätigung nie kommen: am 24./25.08.2026 ging
derselbe Wert **71-mal** hintereinander raus, keiner davon kam an. Nach
`wp_schreib_versuche` (4, rund eine Stunde) wird deshalb nicht weiter
geschrieben, sondern gemeldet — im Status unter `warmwasser.stoerung` bzw.
`heizkreis.stoerung` und im Klartext-Grund, also auch im Entscheidungsprotokoll.
Eine neue Entscheidung mit einem anderen Sollwert bekommt frische Versuche; eine
Störung legt die Regelung nicht dauerhaft lahm.

## 0.15.0

**Die Historie zeigt jetzt den Zeitraum, den man auswählt — und der Tag
zerfällt in seine 24 Stunden.**

*Der Fehler.* Die vier Knöpfe hießen Tag/Woche/Monat/Jahr, meinten aber die
**Säulenbreite** und nicht den Zeitraum: „Tag" zeigte einen ganzen Monat in
Tagessäulen, „Woche" ein ganzes Jahr in Wochensäulen. Entsprechend bot die
Navigation rechts auf „Tag" nur Monate an und auf „Woche" nur Jahre — genau
Leos Beobachtung. Jetzt heißt eine Ansicht nach dem Zeitraum, den man wählt:
**Tag** = ein Tag über 0–24 Uhr, **Woche** = die sieben Tage dieser Woche,
**Monat** = die Tage dieses Monats, **Jahr** = die Monate dieses Jahres. Die
Pfeile springen um genau eine dieser Einheiten weiter.

*Direktwahl.* Neben den Pfeilen steht ein Datumsfeld (Tag/Woche/Monat) bzw.
eine Jahresliste. Bewusst ein `type="date"` und kein `type="week"`/`"month"`:
die beiden gibt es auf iOS nicht und fallen dort auf ein nacktes Textfeld
zurück. Welche Woche bzw. welcher Monat aus dem Datum wird, steht daneben im
Fenstertitel. Die frühere Übersicht über **alle Jahre** ist als erster
Eintrag der Jahresliste erhalten geblieben.

*Stundenwerte.* Für „ein Tag über 24 Stunden" gab es schlicht keine Daten:
`energie_tag` ist auf den Tag genau, und die Ticks in `snapshots` führen
weder `p_pv_e3dc_w` noch `p_haus_w`. Neue Tabelle `energie_stunde`, gefüllt
vom selben Zähler nach denselben Regeln (absolute Stände, UPSERT, Rückladen
beim Neustart). Nachtragen lässt sich das **nicht** — die E3DC-Historie
liefert Tagessummen. Stundensäulen gibt es deshalb erst ab dem Tag, an dem
diese Version läuft; für ältere Tage sagt die Ansicht das offen, statt eine
flache Kurve zu erfinden. Neu ist dafür `ebene=stunde` in
`/api/v1/energie/reihe` und im CSV-Export.

## 0.14.0

**Der Tagesertrag steht jetzt auf der Startseite, und die Historie hat einen
eigenen Reiter mit Diagrammen.**

*Heute.* Bis hierher zeigte das Dashboard ausschließlich Leistungen — was in
diesem Augenblick fließt. Die Frage „wie viel ist heute zusammengekommen?"
war damit nur in der E3DC-App oder im HA-Energie-Dashboard zu beantworten,
und dort steht seit der Garagen-Anlage der falsche Hausverbrauch (siehe
0.13.0). Der Energiezähler rechnet den richtigen Wert längst mit; er stand
bloß nirgends. `/api/v1/status` liefert ihn jetzt als `energie_heute` mit,
und darunter steht eine eigene Kachelreihe: Ertrag (Haus/Garage), Verbrauch
(Haus/Wallbox), Netzbezug und Einspeisung, Batterie, Autarkie mit Balken.
Bewusst eine **eigene Reihe** und nicht in die Leistungskacheln gemischt —
kW und kWh nebeneinander in derselben Zeile liest man unweigerlich falsch.

*Historie als Reiter.* Die Energie-Historie war eine weitere einklappbare
Sektion am Ende eines ohnehin langen Scrolls. Sie wird aber nicht im
Vorbeigehen gelesen, sondern gezielt aufgesucht, und sie lädt Daten, die der
Statusblick nicht braucht. Sie ist deshalb jetzt ein eigener Reiter neben
„Übersicht", und sie lädt erst beim ersten Öffnen.

*Vier Ebenen, drei Diagramme.* Tag, Woche, Monat, Jahr — jeweils mit
Kennzahlen des Zeitraums (Erzeugung, Verbrauch, Netz, Autarkie,
Eigenverbrauch) und drei Balkendiagrammen:

- **Erzeugung und Verbrauch** — je Zeitraum zwei gestapelte Säulen
  nebeneinander, links PV Haus + Garage, rechts Haus + Wallbox.
- **Woher der Verbrauch gedeckt wurde** — ein Stapel aus PV direkt,
  Batterie und Netz. Der PV-Direktanteil ist der Rest, der nach Netzbezug
  und Batterieentladung bleibt: aus der Bilanz abgeleitet statt separat
  gemessen, damit sich der Stapel exakt auf den Verbrauch summiert.
- **Netzaustausch** — Bezug nach oben, Einspeisung nach unten, gleiche Skala.

Ein Klick auf eine Säule geht eine Ebene tiefer (Jahr → Monate, Monat oder
Woche → Tage). Die Diagramme sind selbst gezeichnetes SVG und keine
Bibliothek: Das Add-on liefert sein Dashboard offline aus dem Container aus,
ein CDN-Skript wäre dort schlicht nicht erreichbar, und eine mitgelieferte
Bibliothek wiegt mehr als die drei Balkentypen, um die es geht.

*Woche als neue Ebene.* Gruppiert wird über den **Montag als Datum**, nicht
über eine Kalenderwochennummer: SQLites `%W` zählt ab dem ersten Montag des
Jahres, alles davor landet in Woche 00, und zum Jahreswechsel gehören Tage
zweier Jahre in dieselbe Woche — ein Nummernpaar wäre dort mehrdeutig.

*Fenster statt Vollauszug.* Tage werden monatsweise gezeigt, Wochen und
Monate jahrweise, Jahre alle. Ohne das stünden entweder 1800 Säulen
nebeneinander oder drei. Das Fenster grenzt auf **Tagesebene** ein, nicht auf
Periodenebene; eine angeschnittene Randwoche ist die Summe ihrer Tage im
Fenster, und die neue Spalte `tage` weist aus, wie viele das waren — sonst
läse man eine kurze Randsäule als schlechten Ertrag. Der CSV-Export folgt
demselben Fenster: Eine Datei, die stillschweigend mehr enthält als das
Diagramm darüber, führt beim Nachrechnen in die Irre.

Neu: `GET /api/v1/energie/reihe?ebene=tag|woche|monat|jahr&von=&bis=&jahr=`
— eine Zeilenform für alle vier Ebenen, damit das Diagramm seine Achse nicht
von der Ebene abhängig machen muss. Die älteren `/tage`, `/monate`, `/jahre`
bleiben unverändert. 196 Tests grün.

## 0.13.1

**Der Historien-Import hat die Netzrichtung falsch bestimmt — am ersten
Live-Lauf aufgefallen.**

Ob `grid_power_in` in der E3DC-Historie den Bezug oder die Einspeisung meint,
steht nirgends; v0.13.0 hat es deshalb aus der Bilanz erschlossen — aber am
**ersten** Tag des Zeitraums. Der 23.08.2021 hatte 0,196 kWh Bezug gegen
0,198 kWh Einspeisung: Beide Deutungen ergaben denselben Rest (2,28 gegen
2,29 kWh), die Entscheidung fiel praktisch per Münzwurf und galt anschließend
für alle 1800 Tage. Sie fiel falsch. Im Ergebnis stand für den 25.08.2021 ein
Netzbezug von 35,7 kWh an einem Tag mit 50 kWh Eigenerzeugung — eine Zahl, die
in einer Jahresauswertung niemandem auffällt.

Der Import läuft jetzt in **zwei Phasen**: erst den ganzen Zeitraum lesen und im
Speicher halten, dann die Richtung aus der **Summe** aller Tagesreste bestimmen,
dann schreiben. Über 1800 Tage ist die Frage eindeutig (im Live-Lauf 74 kWh Rest
gegen 3,7 kWh am selben Tag). Der Bericht weist beide Summen aus — liegen sie
dicht beieinander, ist die Zuordnung nicht belegt und das ist jetzt ablesbar
statt versteckt. Zwei Regressionstests halten den Fall mit den echten Zahlen
fest. 189 Tests grün.

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
