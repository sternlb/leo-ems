# Einspeisebegrenzung am Netzverknüpfungspunkt (Issue #15)

**Stand:** 2026-08-30 · **Status:** Spezifikation, noch nicht umgesetzt
**Bezug:** REQ-043 (neu gefasst), REQ-044 bis REQ-047 (neu) · Spec §5 (Stellgrößen), §7 (Fail-Safe)

## Das Problem

Seit dem 22.08.2026 speisen zwei Anlagen auf denselben Hausanschluss:

| Anlage | Modulleistung | Wechselrichter | Begrenzung heute |
|---|---|---|---|
| E3DC S10E (Dach, Ost 22°) | 9,23 kWp | im Hauskraftwerk | **70 % = 6,46 kW**, statisch in der E3DC hinterlegt |
| Sungrow SG 6.0RT (Garage, Ost/West 15°) | 5,64 kWp | 6,0 kW AC | **keine** — Sollwert steht auf 100 % |

Zusammen können damit bis zu **12,46 kW** ins Netz gehen. Erlaubt sind
**9,85 kW**. Die Lücke ist heute offen, und sie schließt sich nicht von selbst:
Die E3DC kappt ihre *eigene* Erzeugung und weiß nichts von der Garage; der
Sungrow läuft ungeregelt. Niemand im Haus kennt die Summe — außer dem EMS.

## Der Grenzwert

```
Grenze = 70 % × 9,23 kWp  +  60 % × 5,64 kWp
       =      6,461 kW    +      3,384 kW      =  9,845 kW
```

Die beiden Prozentsätze haben verschiedene Gründe, und beide sind an eine
Bedingung geknüpft, die irgendwann entfällt — deshalb ist der Wert
**konfigurierbar** und nicht einprogrammiert:

- **70 % (Bestandsanlage).** Die alte 70-%-Regel des EEG wurde für
  Bestandsanlagen zum 01.01.2023 aufgehoben — aber nur für Anlagen **bis 7 kW**
  voraussetzungslos. Größere Bestandsanlagen wie die 9,23-kWp-Dachanlage
  behalten die Begrenzung, bis ein intelligentes Messsystem verbaut ist.
- **60 % (Neuanlage).** Das Solarspitzengesetz hat mit § 9 EEG zum 25.02.2025
  eine Einspeisegrenze von 60 % der installierten Leistung für alle Anlagen
  eingeführt, die ab diesem Datum in Betrieb gehen und **noch kein Smart Meter
  mit zertifizierter Steuerbox** haben. Die Garagenanlage fällt darunter.

Beide Grenzen entfallen mit dem Einbau des intelligenten Messsystems. Wenn der
Zähler kommt, ändert sich hier eine Zahl in der Konfiguration — sonst nichts.

**Bezugsgröße** ist die *installierte Leistung* (§ 3 Nr. 31 EEG: die
Modulleistung in kWp), gemessen als Wirkleistungseinspeisung **am
Verknüpfungspunkt mit dem Netz**. Das ist ausdrücklich nicht die
Wechselrichterleistung und nicht die Erzeugung, sondern das, was nach
Eigenverbrauch und Batterieladung übrig bleibt und wirklich hinausfließt. Der
VDE-FNN-Hinweis zu § 9 EEG bestätigt diese Lesart für die 70-%-Variante
ausdrücklich (Abschnitt 3.2, mit Verweis auf VDE-AR-N 4105 Abschnitt 5.7.4.2.1),
und der SFV hält für mehrere Anlagen hinter einem Einspeisepunkt fest, dass sie
die Kappung **gemeinsam am Einspeisepunkt** erfüllen dürfen.

Das klingt zunächst nach einer Chance: Nicht jede Anlage müsste ihre eigene
Grenze einhalten, nur die Summe müsste stimmen — wenn das Dach im Dezember 2 kW
liefert, dürfte die Garage weit über ihre 3,38 kW hinaus. Der Spike weiter unten
zeigt, warum daraus nichts wird: Das einzige Stellglied im Haus braucht 90
Sekunden, um zu reagieren.

## Wie lange darf die Grenze überschritten werden?

Kurze Antwort: **Es gibt keine gesetzlich zugestandene Überschreitungsdauer.**
Recherchiert wurden EEG § 9, der VDE-FNN-Hinweis zur technischen Umsetzung des
§ 9 EEG, die Clearingstelle EEG|KWKG und die Erläuterungen zum
Solarspitzengesetz. Keine dieser Quellen nennt ein Mittelungsintervall, ein
Toleranzband oder eine zulässige Überschreitungsdauer. Der Gesetzestext sagt
nur „Begrenzung der maximalen Wirkleistungseinspeisung auf 60 Prozent der
installierten Leistung" — ohne Zeitbezug.

Zwei belastbare Anhaltspunkte gibt es trotzdem, und aus ihnen leiten wir die
Auslegung ab:

**1. Zehn Sekunden — die einzige Zahl im Regelwerk.** VDE-AR-N 4105 erlaubt
eine geregelte (statt fest parametrierten) Begrenzung am Netzanschlusspunkt und
formuliert die Anforderung so, dass nach einer technisch nie vollständig zu
vermeidenden Überschreitung **nach spätestens zehn Sekunden keine
Überschreitung mehr besteht**. Genau derselbe Fall liegt hier vor: eine Regelung
statt einer festen Parametrierung. Zehn Sekunden ist damit die Zeit, die eine
Regelabweichung höchstens stehen bleiben darf — nicht eine Zeit, die man
ausschöpfen soll.

**2. Die Viertelstunde — was überhaupt jemand sehen kann.** Der Netzbetreiber
misst die Einspeisung als viertelstündliche Energiewerte (der FNN-Hinweis führt
die „viertelstündige Ablesung der Ist-Einspeisung nach EEG" für Bestandsanlagen
als vorhandene Fähigkeit auf). Eine Überschreitung, die kürzer ist als ein
Regelzyklus, existiert in dieser Messung schlicht nicht — sie verschwindet im
Mittelwert. Das ist keine Erlaubnis, sondern die Beschreibung dessen, was
nachweisbar ist.

**Daraus die Auslegung fürs EMS:**

| Kriterium | Vorgabe | Warum |
|---|---|---|
| Regelziel | Momentanwert ≤ 9,845 kW | Der Gesetzeswortlaut kennt keinen Mittelwert |
| Ausregelzeit | Überschreitung nach **≤ 10 s** beendet | VDE-AR-N 4105, geregelte Begrenzung |
| Nachweis | **15-Minuten-Mittel** nie über der Grenze | Die Größe, die der Netzbetreiber misst |
| Arbeitspunkt | **statische Aufteilung**, keine laufende Regelung | Siehe Spike: das Stellglied ist zu langsam für eine Regelung |

Der letzte Punkt ist das Ergebnis der Messung weiter unten und nicht die
ursprüngliche Absicht. Eine Ausregelzeit von 10 s ist die Vorgabe für eine
*geregelte* Begrenzung — wer sie nicht halten kann, darf nicht regeln, sondern
muss fest parametrieren. Genau das tut dieser Entwurf.

## Der einzige Stellhebel: der Sungrow

Abregelbar ist genau ein Erzeuger. Die E3DC-Grenze liegt in der Anlagensteuerung
und ist über RSCP nicht fernstellbar (`pye3dc` kann Batterie-Limits, nichts
weiter); an die Einstellung selbst kommt nur der Installateur. Der Sungrow
dagegen hat zwei beschreibbare Holding-Register, beide bereits aus der Anbindung
bekannt (`docs/systems/sungrow.md`):

| Register | Bedeutung | Werte |
|---|---|---|
| 5007 | Leistungsbegrenzung ein/aus | `0xAA` = an, `0x55` = aus |
| 5008 | Sollwert | in 0,1 % der Nennleistung |

**Achtung, zwei verschiedene Prozentwerte.** Die 60 % des EEG beziehen sich auf
die **Modulleistung** (5,64 kWp → 3,384 kW). Register 5008 rechnet in Prozent
der **Wechselrichter-Nennleistung** (6,0 kW). Der Ruhe-Sollwert ist also nicht
60 %, sondern:

```
3.384 W / 6.000 W = 56,4 %   →   Register 5008 = 564
```

Diese Umrechnung ist eine der Stellen, an denen ein Zahlendreher unbemerkt
jahrelang falsch einspeisen würde. Sie steht deshalb als eigene Funktion im
Code und hat einen eigenen Test.

## Spike-Ergebnis 2026-08-30 (`backend/spikes/sungrow_limit_spike.py`)

Gemessen gegen die reale Anlage, abends bei 190–250 W Erzeugung. Drei Befunde,
einer davon kippt den Entwurf.

**1. Der Schreibzugriff funktioniert.** Register 5008 nimmt Werte an — sowohl
über FC06 als auch über FC16 —, und der Wert bleibt stehen (zurückgelesen über
90 s). Der WiNet-S-Dongle ist also nicht nur lesend freigeschaltet. Der
Ausgangszustand war übrigens `5007 = 0xAA` (Begrenzung **an**) bei
`5008 = 1000` (100 %): Der Mechanismus läuft, er ist nur auf „keine Begrenzung"
gestellt. Es muss nichts eingeschaltet werden, nur ein Zahlenwert geändert.

Nebenbei bestätigt sich die Registerkarte: 5000–5005 lieferten `2026, 8, 30,
18, 55, 41` — Datum und Uhrzeit der Anlage. Die Adressierung stimmt, ein
Off-by-one ist ausgeschlossen.

**2. Die Begrenzung wirkt — aber sie braucht anderthalb Minuten.**

| Zeit nach dem Schreiben | AC-Leistung |
|---|---|
| 0–70 s | 230 W (unverändert) |
| 80 s | 194 W |
| 90 s | 40 W |
| ab 100 s | ~85 W (eingeschwungen) |
| Freigabe | nach **< 10 s** wieder auf 199 W |

Rund **80–90 s Totzeit** bis überhaupt etwas passiert, dann ist es in ~20 s
eingeschwungen. Das Zurücknehmen geht dagegen sofort. Das Muster sieht nach
einem Abfrageintervall im Wechselrichter oder im Dongle aus, nicht nach einer
Rampe.

**3. Die Einheit von 5008 ist wahrscheinlich 0,1 %, aber nicht bewiesen.**
Gesetzt war `2`. Unter „1 %" wären 120 W zu erwarten gewesen, unter „0,1 %"
12 W — gemessen wurden 85 W. Der Wert liegt deutlich **unter** den 120 W, die
der Wechselrichter bei der 1-%-Deutung problemlos hätte liefern können; er
sieht nach der Einspeise-Untergrenze des Geräts aus, die eine Vorgabe von 12 W
nicht unterschreiten kann. Das spricht für 0,1 % — also für die Registerkarte
in `docs/systems/sungrow.md`. Ein sauberer Nachweis braucht Mittagssonne:
Sollwert 300 (= 30 % = 1.800 W) setzen und prüfen, ob sich die Anlage dort
einpendelt.

### Was das für den Entwurf heißt

**Stufe 2 in der ursprünglich gedachten Form ist nicht haltbar.** Eine Regelung,
deren Stellglied 90 Sekunden Totzeit hat, kann die Ausregelzeit von 10 s aus
VDE-AR-N 4105 nicht einhalten. Wer den Sungrow anhebt, weil das Dach gerade
wenig liefert, steht bei der nächsten Wolkenlücke 90 Sekunden lang über der
Grenze — und die Wolke kommt schneller zurück, als das Stellglied reagiert.

Damit bleibt nur, was **vorausschauend** sicher ist: ein Sollwert, der auch im
schlechtesten Moment hält. Das ist genau die statische Aufteilung aus Stufe 1.
Der Rest des Nutzens liegt nicht im Anheben des Sollwerts, sondern dort, wo er
von Anfang an lag: **Überschuss lokal verwerten, bevor er abgeregelt wird**
(REQ-043).

## Zwei Stufen

### Stufe 1 — die Grenze halten, ohne aufs EMS zu bauen

Der Sungrow bekommt den Sollwert **56,4 %** (3,384 kW) fest eingeschrieben,
Register 5007 auf „an". Damit gilt:

```
max. Einspeisung = 6,461 kW (E3DC, statisch) + 3,384 kW (Sungrow, statisch)
                 = 9,845 kW = die Grenze
```

Die Grenze ist danach **ohne jede Regelung** eingehalten — auch wenn das EMS
aus ist, das Add-on abstürzt oder der Pi ausfällt. Jede Anlage hält ihren
Anteil, unabhängig von der anderen. Das ist die Stufe, die zuerst kommt, und sie
ist der Ruhezustand, in den alles Weitere zurückfällt.

Preis: An wenigen Sommermittagen wird die Garage abgeregelt, obwohl das Dach
gerade unter seinen 6,46 kW liegt und in der Summe Platz wäre.

### Stufe 2 — den Überschuss verwerten, statt ihn abzuregeln

Nach dem Spike ist das die einzige Stufe 2, die bleibt. Das EMS regelt den
Sungrow **nicht** dynamisch nach; sein Sollwert steht fest auf dem sicheren
Anteil. Was das EMS stattdessen tut: Es erkennt, dass die Summe an die Grenze
stößt, und schafft *Verbrauch*, damit die Energie im Haus bleibt statt
abgeregelt zu werden — Batterie laden, Warmwasser-Boost vorziehen, Wallbox
freigeben. Das ist REQ-043 und im EMS längst gebaut; neu ist der Auslöser: Bis
heute war der Grund, Netzbezug zu vermeiden, künftig auch, Abregelung zu
vermeiden.

Der Unterschied ist nicht kosmetisch. Netzbezug vermeiden lohnt sich mit dem
Arbeitspreis, Abregelung vermeiden mit dem vollen Ertrag — eine abgeregelte
Kilowattstunde ist ersatzlos weg. Die Schwelle, ab der das EMS Verbraucher
zuschaltet, muss deshalb an sonnigen Mittagen früher greifen als bisher.

**Was ausdrücklich nicht kommt:** ein Anheben des Sungrow-Sollwerts über den
sicheren Anteil hinaus. Sobald der Wechselrichter (oder ein anderer Stellweg)
schneller als 10 s reagiert, kann man darüber neu nachdenken — dann steht hier
eine neue Stufe. Bis dahin wäre es eine Regelung, die ihre eigene Zusage nicht
halten kann.

## Fail-Safe

Mit der statischen Aufteilung ist der Fail-Safe unspektakulär, und genau das ist
sein Wert: Das EMS hält die Grenze nicht — die Anlagen halten sie selbst. Fällt
das Add-on aus, der Pi oder das ganze Netzwerk, bleibt der Sungrow-Sollwert
stehen, wo er steht, und die Summe bleibt eingehalten.

Das war der eigentliche Grund, Stufe 2 fallen zu lassen, noch vor der
Ausregelzeit: Ein Sungrow, dem das EMS gerade 100 % geschrieben hat, fällt
**nicht** von selbst zurück. Er hält den Sollwert, bis ihn jemand ändert. Ein
abgestürztes Add-on hinterließe eine dauerhaft zu hohe Einspeisung — und zwar
unbemerkt, bis irgendwann der Netzbetreiber fragt. Alle anderen Stellgrößen im
EMS sind harmlos, wenn das EMS verschwindet (REQ-060); diese eine wäre es nicht
gewesen.

| Ereignis | Verhalten |
|---|---|
| EMS aus, abgestürzt, nicht erreichbar | Sollwert bleibt stehen, Grenze bleibt eingehalten |
| Add-on-Start | Sollwert einmal prüfen und, falls abweichend, setzen |
| Sungrow nicht erreichbar | Diagnose im Status; kein Schreibversuch, nichts zu retten |
| Sollwert von Hand verstellt | das EMS meldet die Abweichung, überschreibt sie aber nicht ungefragt |

Der letzte Punkt ist Absicht: Wenn Leo oder ein Installateur am Wechselrichter
etwas einstellt, ist das eine Entscheidung und kein Fehler (REQ-061). Das EMS
sagt, dass der Wert von der Vorgabe abweicht — mehr nicht.

## Anforderungen

| ID | Anforderung | MoSCoW |
|---|---|---|
| REQ-044 | Die Summe der Einspeisung beider Anlagen am Netzverknüpfungspunkt darf einen konfigurierbaren Wert (Vorgabe 9.845 W) nicht überschreiten. Sichergestellt wird das durch eine feste Aufteilung je Anlage, nicht durch eine laufende Regelung. | Must |
| REQ-045 | Die Einhaltung darf nicht vom laufenden EMS abhängen: Fällt das Add-on aus, bleibt die Grenze eingehalten. Das EMS setzt den Sungrow-Sollwert, regelt ihn aber nicht dynamisch nach. | Must |
| REQ-046 | Das EMS muss die Einhaltung nachweisen: Einspeisung als 15-Minuten-Mittel historisieren, Überschreitungen mit Dauer und Höhe protokollieren. | Should |
| REQ-047 | Das EMS muss melden, wenn der Sungrow-Sollwert von der Vorgabe abweicht — überschreiben darf es eine Handeinstellung nicht ungefragt (REQ-061). | Should |
| REQ-043 | *(neu gefasst)* Das EMS soll Abregelungsverluste minimieren, indem Überschuss lokal verwertet wird (Batterie, WP, EV). Auslöser ist künftig auch die Einspeisegrenze, nicht nur der Netzbezug. | Should |

## Abnahmekriterien

1. **Sollwert gesetzt.** Register 5007 = `0xAA`, 5008 = `564`. Nachgelesen über
   Modbus und in der E3DC-/Sungrow-App sichtbar.
2. **Grenze gehalten.** Über einen sonnigen Tag mit voller Erzeugung: kein
   15-Minuten-Mittel der Einspeisung über 9.845 W. Der Momentanwert wird
   mitprotokolliert.
3. **Ohne EMS.** Add-on gestoppt, sonniger Mittag: die Grenze bleibt
   eingehalten. Dieser Test ist der wichtigste — er beweist, dass die Funktion
   nicht am EMS hängt.
4. **Handeinstellung.** Sollwert von Hand auf 1000 gesetzt: Das EMS meldet die
   Abweichung im Status und überschreibt sie nicht von selbst.
5. **Verwertung.** An einem Tag mit Abregelungsgefahr zieht das EMS Verbraucher
   vor (WW-Boost, Batterieladung), bevor die Anlage in die Begrenzung läuft.
   Nachweis über das Entscheidungsprotokoll.

## Offene Punkte

- **Einheit von Register 5008 endgültig belegen.** Der Abendtest spricht für
  0,1 %, beweist es aber nicht (die Anlage lief in ihre eigene Untergrenze).
  Nachweis bei Mittagssonne: Sollwert 300 setzen und prüfen, ob sich die
  Leistung bei ~1.800 W einpendelt. **Bevor das nicht gemessen ist, wird 564
  nicht scharf geschaltet** — bei der 1-%-Deutung wären 564 sinnlos (Anschlag)
  und die Grenze bliebe verletzt.
- **Totzeit gegenprüfen.** 80–90 s sind eine einzelne Messung. Zwei, drei
  Wiederholungen bei stabiler Einstrahlung sichern die Zahl ab — und falls sie
  in Wahrheit deutlich kürzer ist, wird die Absage an die dynamische Regelung
  noch einmal verhandelbar.
- **E3DC-Anteil verifizieren.** Dass die Dachanlage wirklich bei 6,46 kW kappt
  und nicht bei einem anderen Wert, ist Papierlage. Ein Blick in die
  Einspeisekurve eines klaren Sommertags zeigt es.
- **Intelligentes Messsystem.** Sobald der Zähler kommt, entfallen beide
  Grenzen. Dann wird aus der Begrenzung eine reine Konfigurationszeile.

## Quellen

- [§ 9 EEG](https://www.gesetze-im-internet.de/eeg_2014/__9.html) — Wortlaut der 60-%-Begrenzung, Bezug auf die installierte Leistung am Verknüpfungspunkt
- [VDE-FNN-Hinweis „Technik zur Umsetzung § 9 EEG"](https://www.vde.com/resource/blob/2326016/3c3156348fda908617e4a16f5666701f/vde-fnn-hinweis--technik-zur-umsetzung---9-eeg-und-echtzeitendatenuebertragung-zur-anpassung-von-stromeinspeisungen--data.pdf) — Abschnitt 3.2: Begrenzung am Netzverknüpfungspunkt, Verweis auf VDE-AR-N 4105 Abschnitt 5.7.4.2.1; viertelstündliche Ablesung der Ist-Einspeisung
- [Haustec zur VDE-AR-N 4105](https://www.haustec.de/energie/niederspannungsrichtlinie-das-bringt-die-neue-vde-ar-n-4105?page=all) — „nach spätestens zehn Sekunden keine Überschreitung mehr"
- [SFV: Leistungsbegrenzung auf 60 Prozent](https://www.sfv.de/leistungsbegrenzung-auf-60-prozent) — mehrere Anlagen dürfen die Kappung gemeinsam am Einspeisepunkt erfüllen
- [pv magazine zur EnSiG-Novelle](https://www.pv-magazine.de/2022/10/11/ensig-novelle-abschaffung-der-70-prozent-regelung-fuer-neue-photovoltaik-anlagen-bis-25-kilowatt-vorgezogen-kleine-bestandsanlagen-ab-1-januar-2023-ebenfalls-ohne-beschraenkung-g/) — Bestandsanlagen: voraussetzungslos frei nur bis 7 kW, größere erst mit Smart Meter
- [Clearingstelle EEG|KWKG](https://www.clearingstelle-eeg-kwkg.de/haeufige-rechtsfrage/70) — keine Aussage zu Toleranz oder Mittelwert
