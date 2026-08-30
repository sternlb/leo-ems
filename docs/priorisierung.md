# Priorisierung der Überschussverwertung (Issue #16, Schritt 1)

**Stand:** 2026-08-30 · **Status:** umgesetzt in v0.18.0
**Bezug:** REQ-075 · Spec §2 (Überschuss), §4 (Zuteilung)

Schritt 2 des Issues — Planung über den Tag anhand des Börsenstrompreises —
steht hier ausdrücklich **nicht**. Er kommt erst, wenn es einen dynamischen
Tarif gibt, und wird dann abschaltbar gebaut.

## Wie es heute zugeht

Die Reihenfolge steht fest im Code und ist über drei Dateien verteilt:

| # | Wer | Wo |
|---|---|---|
| 1 | Hausbatterie, bis SoC ≥ `priority_soc_pct` (25 %) | `planner/surplus.py` |
| 2 | Wallbox (PV-Überschussladen) | `core/loop.py` Schritt 7 |
| 3 | Warmwasser-Boost | `core/loop.py` Schritt 7b |
| 4 | Hausbatterie, bis voll | ergibt sich — der Rest fließt dorthin |

Die Reihenfolge ist nicht willkürlich, sie ist gewachsen: Punkt 1 kam mit der
Überschussformel, Punkt 2 vor 3 wurde in Issue #6 entschieden (ein laufender
WP-Boost hatte das Auto ausgesperrt). Nur ändern kann Leo sie nicht — und im
Winter ist eine andere richtig als im Sommer.

## Das Modell: eine geordnete Liste

Vier Einträge, frei sortierbar:

| Eintrag | Art | Bedeutung |
|---|---|---|
| `batterie_vorrang` | Tor | Die Hausbatterie behält ihre Ladeleistung, bis SoC ≥ `priority_soc_pct` |
| `wallbox` | Verbraucher | PV-Überschussladen des Enyaq |
| `warmwasser` | Verbraucher | Warmwasser-Boost der Wärmepumpe |
| `batterie_voll` | Tor | Wie `batterie_vorrang`, Schwelle 100 % |

**Verbraucher** nehmen der Reihe nach aus dem Topf, was sie brauchen; was übrig
bleibt, geht an den nächsten.

**Tore** sind keine Verbraucher, und das ist der Punkt, an dem das Modell zur
Anlage passen muss: Die Hausbatterie *bekommt* keine Leistung zugeteilt, sie
nimmt sich, was niemand sonst abruft — die E3DC regelt das autonom. Das EMS kann
sie nur dadurch bevorzugen, dass es ihren Anteil **nicht** an andere weiterreicht.
Ein Tor sagt also: „Die Ladeleistung der Batterie ist für alles, was unter mir
steht, nicht verfügbar, solange die Schwelle nicht erreicht ist."

Die Vorgabe ist das heutige Verhalten:

```
batterie_vorrang (25 %)  →  wallbox  →  warmwasser  →  batterie_voll
```

`batterie_voll` ganz unten ist der Normalfall und tut nichts — unter ihm steht
niemand mehr, der Rest landet ohnehin in der Batterie. Wer es nach oben zieht,
sagt: erst die Batterie voll, dann alles andere.

## Reihenfolge ist kein Verbot

Steht die Batterie über der Wallbox und nimmt gerade nur 500 W — weil sie fast
voll ist oder kalt —, bekommt die Wallbox trotzdem den Rest. Alles andere hieße,
Energie ins Netz zu schicken, während ein Verbraucher wartet. Die Priorität
entscheidet, **wer zuerst bedient wird**, nicht, wer als Einziger darf.

Das gilt auch nach oben: Der Überlauf über die Aufnahmefähigkeit eines
bevorrechtigten Verbrauchers fließt immer weiter nach unten.

## Was die Reihenfolge nicht schlägt

| Vorrang | Warum |
|---|---|
| **Garantieladung** (REQ-003/004) | Sie ist eine Zusage auf eine Uhrzeit, keine Optimierung. Läuft sie, lädt das Auto — unabhängig von der Liste. |
| **Modus „Schnell" / „PV+Batterie"** | Wer den Modus wählt, hat die Priorität gerade von Hand gesetzt. |
| **Batterie-Reserve** (`soc_reserve_pct`) | Harte Untergrenze, gilt immer. |
| **Komfortgrenzen der WP** (REQ-012) | Mindesttemperaturen sind kein Überschussthema. |

Diese vier stehen über der Liste, weil sie etwas anderes sind als eine
Vorliebe: Zusagen und harte Grenzen. Eine Prioritätenliste, die eine
Mindesttemperatur oder eine Abfahrtszeit aushebeln kann, wäre keine
Konfiguration, sondern eine Falle.

## Folge für Issue #6

Steht `warmwasser` **über** `wallbox`, kehrt sich die Entscheidung aus Issue #6
um: Ein laufender Boost weicht dem Auto dann nicht mehr sofort, sondern das Auto
bekommt, was nach dem Boost übrig ist. Das ist die gewollte Wirkung der
Einstellung und kein Rückschritt — die Mechanik aus Issue #6 (Rückrechnung des
geschätzten WP-Verbrauchs, damit beide gegen dasselbe Budget geprüft werden)
bleibt in beiden Reihenfolgen nötig und unverändert.

Umgekehrt heißt das für den Code: Die Zuteilung darf nicht länger fest „erst
Wallbox, dann WP" rechnen. Steht die WP oben, muss ihre Entscheidung zuerst
fallen und die Wallbox bekommt `verteilbar − wp_erwartet`.

## Änderungen

| Stelle | Was |
|---|---|
| `config.py` | Neues Feld `prioritaet: list[str]`, Vorgabe wie oben. Validierung: genau die vier bekannten Einträge, jeder genau einmal. Eine unbekannte oder fehlende Marke wird abgelehnt, nicht stillschweigend ergänzt. |
| `planner/prioritaet.py` (neu) | Reine Funktion: Liste + Messwerte → Budget je Verbraucher. Ohne I/O, damit die Reihenfolge testbar ist, ohne die Regelschleife zu starten. |
| `planner/surplus.py` | Das Batterie-Tor kommt aus der Liste statt aus `priority_soc_pct` allein. |
| `core/loop.py` | Schritt 7: Reihenfolge der beiden Verbraucher datengesteuert statt fest. |
| `api` | `PUT /api/v1/config` nimmt `prioritaet` entgegen; Status meldet die aktive Reihenfolge und die Zuteilung je Verbraucher. |
| Dashboard | Die Liste steht **auf der Übersicht** im Abschnitt „Betrieb" (Leo, 2026-08-30) — sie wird saisonal umgestellt und ist damit eine Hauptoption wie der Lademodus, keine Einstellung im Sinne von Issue #14. Hoch/Runter-Knöpfe statt Drag & Drop: Auf dem Handy ist das unzuverlässig, und die Liste hat vier Einträge. |
| Übersicht | Dazu die Anzeige, wer gerade wie viel vom Überschuss bekommt. |

## Abnahmekriterien

1. **Vorgabe = heutiges Verhalten.** Mit der Standardliste verhält sich das EMS
   messbar wie v0.17.0. Belegt durch die bestehenden Tests zu Issue #6 und #7,
   die unverändert grün bleiben müssen.
2. **Warmwasser vor Wallbox.** Bei 3 kW Überschuss und angestecktem Auto
   startet der WW-Boost, das Auto bekommt den Rest.
3. **Wallbox vor Warmwasser.** Dieselbe Lage, umgekehrte Liste: Das Auto lädt,
   der Boost startet nicht.
4. **Batterie voll nach oben.** Bei SoC 60 % und 3 kW Überschuss bekommen weder
   Auto noch WW etwas, solange die Batterie die 3 kW aufnimmt — nimmt sie nur
   1 kW, gehen 2 kW weiter nach unten.
5. **Garantieladung schlägt die Liste.** Auch mit `wallbox` an letzter Stelle
   lädt das Auto, wenn die Garantie greift.
6. **Ungültige Liste.** `PUT` mit doppeltem oder unbekanntem Eintrag wird mit
   422 abgelehnt, die alte Reihenfolge bleibt aktiv.

## Offene Punkte

- ~~**Zweite Batterieschwelle.**~~ Entschieden (Leo, 2026-08-30): `batterie_voll`
  bleibt fest bei 100 %. Einstellbar ist nur `batterie_vorrang`
  (`priority_soc_pct`, heute 25 %). Eine zweite Zahl ohne belegten Bedarf kostet
  nur Bedienfläche; nachrüsten geht jederzeit.
- **Wärmepumpe Heizkreis.** Die Heizkreis-Anhebung ist bewusst kein eigener
  Eintrag: Sie ist per Default aus und hängt an der Heizperiode. Kommt sie in
  Betrieb, wird sie ein fünfter Eintrag.
