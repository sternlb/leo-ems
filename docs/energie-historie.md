# Energiebilanz und Historie (Issue #13)

Warum es das gibt, wo die Zahlen herkommen und was sie **nicht** können.

## Der Auslöser

Seit die Garagen-Anlage läuft, weist die E3DC den Hausverbrauch zu klein aus.
Der Sungrow ist AC-gekoppelt und speist **hinter** ihrem Zähler ein — sie sieht
davon nur weniger Bezug bzw. mehr Einspeisung und rechnet:

```
Hausverbrauch(E3DC) = PV(Haus) + Netzbezug + Batt.entladung
                      − Einspeisung − Batt.ladung
```

Die Garagen-Erzeugung fehlt in dieser Summe. Am 22.08.2026 wurde die Bilanz
erstmals negativ (0,94 kW Hausdach, 1,04 kW Einspeisung, Garage 0,51 kW) und die
Anlage meldete **0 W**. Betroffen ist alles, was auf `sensor.s10e_house_consumption`
aufsetzt — im HA-Dashboard wie in der E3DC-App, und rückwirkend auch in deren
Historie.

Richtig ist:

```
Hausverbrauch = PV(Haus) + PV(Garage) + Netzbezug + Batt.entladung
                − Einspeisung − Batt.ladung
```

Das EMS ist die einzige Stelle, die beide Anlagen kennt. Deshalb rechnet es den
Wert und liefert ihn an Home Assistant, statt ihn dort zusammenzuflicken.

## Zwei Sensoren, zwei Fragen

| Entity | Inhalt | wofür |
|---|---|---|
| `sensor.hausverbrauch_leistung` | ohne Wallbox | Flussdarstellung — die Wallbox steht dort als eigener Verbraucher und wäre sonst doppelt im Bild |
| `sensor.hausverbrauch_gesamt_leistung` | mit Wallbox | kWh-Zähler, HA-Energie-Dashboard |

Fällt die Bilanz aus (Fail-Safe E1: E3DC weg), wird **kein** Wert geschrieben.
Eine gemeldete 0 wäre schlimmer als eine Lücke: Der Riemann-Integrator in Home
Assistant integriert sie als echte Messung und macht den Tageswert dauerhaft zu
klein.

## Arbeitsteilung EMS ↔ Home Assistant

Beide Seiten führen Energiewerte, und das ist Absicht:

- **Home Assistant** bildet aus `sensor.hausverbrauch_gesamt_leistung` per
  Riemann-Integral einen kWh-Zähler und daraus Utility-Meter für Tag/Monat/Jahr.
  Das ist der Weg, auf dem der Hausverbrauch im **HA-Energie-Dashboard** und in
  den Langzeitstatistiken landet — dafür braucht HA eine Entity, keine Datei.
- **Das EMS** führt in `energie_tag` die Tagesbilanz **aller** Kanäle. Das ist
  der Bestand für „beliebige Jahre und Monate" und für den Export.

Die beiden Zahlen weichen minimal voneinander ab (verschiedene Integratoren,
verschiedene Startzeitpunkte). Maßgeblich für Auswertungen ist die EMS-Tabelle;
die HA-Zähler sind die Live-Anzeige.

## Die Tabelle

`energie_tag`, eine Zeile je Kalendertag (Ortszeit), Werte in **Wh**:

| Spalte | Inhalt |
|---|---|
| `pv_haus_wh` / `pv_garage_wh` | Erzeugung je Anlage |
| `netz_bezug_wh` / `netz_einspeisung_wh` | getrennt, nicht als vorzeichenbehafteter Wert — in der Tagessumme höbe sich sonst genau das auf, was unterschieden werden soll |
| `batt_laden_wh` / `batt_entladen_wh` | dito |
| `haus_wh` | Hausverbrauch ohne Wallbox |
| `wallbox_wh` | Ladeenergie |
| `quelle` | `ems` (eigene Messung), `e3dc` (importiert), `e3dc-ohne-garage` (importiert, Hausverbrauch zu klein) |

Tageszeilen statt Ticks: Die Ticks liegen bereits in `snapshots` und werden
irgendwann entsorgt; die Jahresübersicht muss in fünf Jahren noch da sein.
~365 Zeilen pro Jahr bleiben winzig und lassen sich in SQL aggregieren.

Gerechnet wird in Wh, ausgeliefert in kWh. Auf kWh gerundete Tageswerte
summieren sich über ein Jahr zu spürbaren Beträgen.

### Was der Zähler bewusst nicht tut

- **Messlücken überbrücken.** Ist der letzte Tick länger als zwei Minuten her
  (Neustart, Ausfall, hängender Adapter), wird das Intervall verworfen und
  gezählt. Die letzte gemessene Leistung über Stunden fortzuschreiben würde
  eine Bilanz erfinden, die nie jemand gesehen hat.
- **Nach einem Neustart bei null anfangen.** Der Tagesstand wird aus der
  Datenbank zurückgeholt, sonst würde jedes Add-on-Update den laufenden Tag
  verkürzen.
- **Inkrementell schreiben.** Geschrieben wird der absolute Tagesstand. Ein
  `SET x = x + ?` würde bei jedem Wiederholungslauf addieren.

## Nachimport aus der E3DC

Für die Jahre vor dem EMS gibt es nur eine Quelle: die Anlage selbst. `pye3dc`
liefert über `get_db_data(startDate, timespan="DAY")` die Tagesbilanz seit der
Inbetriebnahme.

```
POST /api/v1/energie/import?von=2021-01-01&bis=2026-08-21
GET  /api/v1/energie/import      → Fortschritt
```

Der Import läuft als Hintergrund-Task, Tag für Tag mit einer kurzen Pause
dazwischen. Grund: Ein RSCP-Aufruf dauert Millisekunden, aber fünf Jahre sind
über 1800 davon — in einem Block ausgeführt stünde die Regelschleife minutenlang
still, sie teilt sich den Event-Loop mit dem Import. Aus demselben Grund gibt es
**keinen** zweiten RSCP-Kanal und keinen Thread: `pye3dc` hält genau eine
Sitzung, ein zweiter Leser darin würde die Antworten der Regelschleife
durcheinanderbringen.

Drei Eigenschaften, die den Bestand ehrlich halten:

1. **Eigene Messungen werden nie überschrieben.** `quelle='ems'` gewinnt — sie
   kennt die Garagen-Anlage, die E3DC-Historie nicht.
2. **Die Netzrichtung wird geprüft, nicht geraten.** Ob `grid_power_in` Bezug
   oder Einspeisung meint, ist aus dem Namen nicht zu entscheiden. Vertauscht
   fällt das in einer Jahresauswertung niemandem auf und macht sie wertlos.
   Der Import probiert deshalb beide Deutungen gegen den mitgelieferten
   `consumption`-Wert und nimmt die, unter der die Bilanz aufgeht — einmal je
   Import, nicht je Tag: Eine Anlage kehrt ihre Zählrichtung nicht mitten in
   der Historie um.
3. **Tage ab `pv_garage_seit` werden markiert.** Ab der Inbetriebnahme der
   Garagen-Anlage ist der E3DC-Hausverbrauch zu klein. Diese Tage als
   vollwertig auszuweisen wäre die stillste Art, die Auswertung zu verfälschen;
   sie bekommen die Quelle `e3dc-ohne-garage` und im Dashboard einen Hinweis.

Was der Import **nicht** kann: die Wallbox aus dem historischen Hausverbrauch
heraustrennen. Sie steckt dort mit drin (`wallbox_wh = 0`). Eine geschätzte
Aufteilung wäre schlimmer als eine ehrlich zusammengefasste Zahl.

## Ablageformat und Export

Der Bestand liegt in der Add-on-Datenbank (`/data/leo_ems.db`) und ist damit im
HA-Backup enthalten. Für alles außerhalb: CSV.

```
GET /api/v1/energie/export.csv?ebene=tag|monat|jahr[&jahr=2026]
```

Semikolon als Trenner, Komma als Dezimalzeichen — die Datei landet in Excel mit
deutscher Ländereinstellung, und dort zerlegt eine Punkt-Komma-Datei alles in
eine einzige Spalte. Im Dashboard hängt der Knopf „CSV herunterladen" direkt an
diesem Endpunkt, mit denselben Filtern wie die Tabelle darüber: Was auf dem
Bildschirm steht, ist exakt das, was in der Datei landet.
