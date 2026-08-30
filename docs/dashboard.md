# Aufbau des Dashboards (Issue #14)

**Stand:** 2026-08-30 (v0.17.0) · Das Web-Dashboard des Add-ons
(`backend/leo_ems/web/index.html`), ausgeliefert unter `/` und im HA-Ingress.
Die Android-App ist ein anderes Thema: [app-design.md](app-design.md).

## Drei Reiter, drei Fragen

| Reiter | Beantwortet | Wie oft schaut man hin |
|---|---|---|
| **Übersicht** | Was läuft gerade? | mehrmals täglich |
| **Historie** | Was war? | gelegentlich |
| **Einstellungen** | Wie soll es sich verhalten? | selten |

Bis v0.16 standen alle drei auf einer Seite. Das hieß: Wer nachsehen wollte, ob
das Auto lädt, scrollte an zwölf Zahlenfeldern für Phasenumschaltschwellen
vorbei. Die Trennung folgt der Häufigkeit, mit der man etwas braucht — nicht der
technischen Verwandtschaft.

## Was auf der Übersicht bleibt

Die Regel ist nicht „keine Bedienelemente", sondern **keine Zahlen zum
Einstellen**. Was man im Alltag anfasst, bleibt:

- **Lademodus** — Nur-PV / PV+Min / PV+Batterie / Schnell / Aus
- **Hausbatterie im Modus „Schnell" mitnutzen** (Schalter)
- **Warmwasser-Boost** und **Heizkreis-Anhebung** je an/aus (in der
  Wärmepumpen-Kachel, Issue #1)
- **Scharf schalten / In Beobachtung wechseln** — der wichtigste Schalter des
  Systems. Er entscheidet, ob das EMS überhaupt etwas stellt, und gehört
  deshalb dorthin, wo man ihn sieht, und nicht zwei Klicks tief.

Alles mit einem Zahlenfeld — Ströme, SoC-Schwellen, Temperaturen, Phasen- und
Zeitparameter, die Laderegeln — steht unter **Einstellungen**. Das Protokoll
liegt dort ebenfalls: Es ist keine Konfiguration, aber auch nichts, was man im
Vorbeigehen liest.

## Das Detailfenster

Ein Klick auf eine Kachel öffnet ein Fenster mit den Einzelheiten dahinter —
und mit dem **Tagesverlauf des heutigen Tages**.

Das Fenster gab es schon seit v0.6, aber nur über die Hausansicht-Grafik
erreichbar, und die ist auf dem Handy eingeklappt. Praktisch existierte es dort
also nicht. Jetzt öffnen es auch die Kacheln der Übersicht („PV gesamt", „Haus",
„Batterie", „Netz", „Wallbox") und die Tageskacheln darunter — samt
Tastaturbedienung.

| Kanal | Diagramm |
|---|---|
| PV gesamt | Dach + Garage, gestapelt |
| Haus | Hausverbrauch |
| Wallbox | Ladeenergie |
| Netz | Bezug nach oben, Einspeisung nach unten |
| Batterie | geladen nach oben, entladen nach unten |

Die Daten kommen aus der Stundentabelle
(`/api/v1/energie/reihe?ebene=stunde`), die seit v0.16.1 für ein Tagesfenster
immer alle 24 Stunden liefert — die Achse hängt damit nicht davon ab, wie
lückenlos aufgezeichnet wurde ([energie-historie.md](energie-historie.md)).

### Die Wärmepumpe bekommt kein Verbrauchsdiagramm

Sie hat keinen eigenen Zähler; ihr Verbrauch steckt im Hausverbrauch und lässt
sich daraus nicht herauslösen. Eine Kurve wäre geraten.

Was das EMS dagegen genau weiß, ist **wann es die Anlage angefordert hat**. Das
steht seit v0.17.0 in jedem Tick-Snapshot (`wp_ww_boost`, `wp_hk_boost`) und
wird als Band über 24 Stunden gezeigt: je Stunde der Anteil, in dem
Warmwasser-Boost bzw. Heizkreis-Anhebung liefen, dazu die Summe in Minuten.

```
GET /api/v1/wp/aktiv[?tag=YYYY-MM-DD]
→ 24 Zeilen: { stunde, ticks, ww, hk }   ww/hk = Anteil 0…1, null = nicht gemessen
```

Gezählt wird als **Anteil und nicht in Minuten**: Der Regeltick liegt bei 10 s,
war aber nicht immer dort, und nach einem Neustart fehlen Ticks. `treffer /
ticks` bleibt auch dann richtig, während `treffer × 10 s` still zu klein würde.
Eine Stunde ohne einen einzigen Tick liefert `null` und wird im Band gestreift
dargestellt — „nicht gemessen" ist eine andere Aussage als „lief nicht", und
beide als 0 zu zeigen wäre eine erfundene Auskunft.

## Der Diagramm-Renderer

`chartZeichnen()` zeichnet inzwischen an zwei Stellen: in der Historie und im
Detailfenster. Beschriftung und Tooltip kommen deshalb als Option herein
(`opt.label`, `opt.titel`) — vorher zog der Renderer sie direkt aus dem Zustand
der Historie-Ansicht, und im Fenster stünden dann die Beschriftungen der zuletzt
dort gewählten Ebene. `opt.dicht` rückt die Säulen zusammen, damit 24 Stunden
ohne Seitwärtsscrollen in ein 440 px breites Fenster passen.
