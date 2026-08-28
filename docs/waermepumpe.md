# Wärmepumpen-Steuerung (Stufe 2)

Seit v0.4.0 nutzt Leo-EMS PV-Überschuss für die Vaillant aroTHERM — Warmwasser
vorziehen (REQ-010) und Heizkreis anheben (REQ-011). Umgesetzt in
`planner/heatpump.py` (Logik) und `devices/vaillant.py` (Anbindung).

## Warum über Home Assistant

Das Vaillant-Internetmodul hängt am eBUS, es gibt **keinen SG-Ready-Kontakt**
und keinen lokalen Steuerweg (`docs/systems/vaillant.md`). Der Steuerweg ist die
MyVaillant-Cloud — und die hängt über die MyVaillant-Integration bereits in Home
Assistant. Leo-EMS baut deshalb **keinen zweiten Cloud-Client** (zweiter Login,
zweites Anfrage-Budget), sondern geht über die HA-REST-API:

| Richtung | Weg |
|---|---|
| Lesen | `GET /api/states/<entity>` gegen die lokale HA-Instanz — billig, Poll-Takt 60 s statt der 10 s der Regelschleife |
| Schreiben | `POST /api/services/water_heater/set_temperature` bzw. `climate/set_temperature` — geht über die Cloud, deshalb gedrosselt |

Zugang im Add-on: der `SUPERVISOR_TOKEN`, dafür steht `homeassistant_api: true`
in der `config.yaml`. Welcher **Weg** zur HA-API führt, hängt vom Netzmodus ab —
und Leo-EMS läuft mit `host_network: true`, wo es keine Docker-DNS gibt. Seit
v0.6.2 wird deshalb gesucht statt geraten: beim ersten Lesen probiert der Adapter
die bekannten Wege der Reihe nach (`HA_KANDIDATEN` in `devices/vaillant.py`) und
merkt sich den, der mit HTTP 200 antwortet.

| # | Weg | funktioniert wenn |
|---|---|---|
| 1 | `http://supervisor/core/api` | Bridge-Netz (Docker-DNS löst `supervisor` auf) |
| 2 | `http://172.30.32.2/core/api` | derselbe Proxy per IP, auch ohne DNS |
| 3 | `http://127.0.0.1:8123/api` | `host_network` — Core-Port 8123 liegt auf dem Host |
| 4 | `http://homeassistant:8123/api` | Bridge-Netz, Core direkt |

Der gefundene Weg steht im Add-on-Log (`Wärmepumpe: HA-API über …`). Klappt
keiner, nennt der Fehler **jeden** Versuch mit Status bzw. Fehlerart — 401 heißt
„Weg richtig, Token abgelehnt", ein Verbindungsfehler heißt „Adresse gibt es hier
nicht". Nach einem Fehlschlag wird 60 s nicht erneut gesucht, damit die
10-s-Regelschleife nicht an vier Zeitüberschreitungen hängt.

Für den Betrieb außerhalb des Add-ons (Entwicklung am PC) lassen sich
`ha_base_url` und `ha_token` (Long-Lived Token) als Optionen setzen — dann wird
nichts durchprobiert, sondern genau diese Adresse benutzt.

## Entities

Abgelesen an Leos HA-Instanz am 2026-07-25. Stellgrößen sind über die
Add-on-Optionen änderbar, die Lese-Sensoren stehen in `devices/vaillant.py`.

| Zweck | Entity |
|---|---|
| **Stellgröße Warmwasser** | `water_heater.home_domestic_hot_water_0` (35–70 °C) |
| **Stellgröße Heizkreis** | `climate.home_zone_zone_1_circuit_0_climate` (MyVaillant setzt das als Quick-Veto) |
| WW Speichertemperatur | `sensor.home_domestic_hot_water_0_tank_temperature` |
| WW Sollwert / Modus | `sensor.home_domestic_hot_water_0_setpoint`, `…_operation_mode` |
| Vorlauftemperatur | `sensor.home_circuit_0_current_flow_temperature` |
| Heizkreis-Zustand | `sensor.home_circuit_0_state` (`STANDBY` / `HEATING`) |
| Raum Ist / Soll | `sensor.home_zone_zone_1_circuit_0_current_temperature`, `…_desired_temperature` |
| Außentemperatur / COP | `sensor.home_outdoor_temperature`, `sensor.home_heating_energy_efficiency` |

**Leeres Feld `vaillant_ww_entity` = WP nicht angebunden.** Dann wird der
Adapter gar nicht gebaut und das Dashboard zeigt „keine Verbindung".

## Warum die WP bis v0.6.4 gar nicht ankam

Der Adapter war fertig, die Entities stimmten, die Optionen stimmten — und
trotzdem kam auf **jedem** Zugangsweg HTTP 401. Ursache lag eine Ebene tiefer:
Die HA-Basis-Images starten über **s6-overlay**, und s6 führt das `CMD` mit einer
*bereinigten Umgebung* aus. Das Add-on startete direkt `python -m leo_ems.main`,
der Prozess sah deshalb weder die `ENV`-Zeilen aus dem Dockerfile noch die
Variablen des Supervisors — nachgewiesen über `/api/v1/diag/umgebung`, das genau
vier Variablen fand: `PATH`, `PWD`, `OLDPWD`, `SHLVL`.

Zwei Folgen, dieselbe Wurzel:

1. **Kein `SUPERVISOR_TOKEN`** → kein Zugang zur HA-API → WP dauerhaft „nicht
   verbunden".
2. **Kein `LEO_EMS_DATA_DIR`** → Daten landeten unter `/app/data` *im Container*
   statt im persistenten `/data`. Bei **jedem Add-on-Update** waren damit
   API-Token, Regel-Konfiguration (inklusive `read_only`, also der
   Scharfschaltung) und die Beobachtungs-Datenbank verloren.

Der Fix ist der dokumentierte Add-on-Weg: Start über `run.sh` mit
`#!/usr/bin/with-contenv bashio` (v0.6.5). Die Begründung steht im Skript selbst,
damit sie beim nächsten Dockerfile-Umbau nicht wieder verloren geht.

## Wenn keine Werte kommen

Die Fail-Safe-Matrix verlangt, dass ein Lesefehler den Ladebetrieb nicht anhält
(E7) — bis v0.6.1 war er deshalb aber auch **nirgends sichtbar**: `_safe_read` in
der Regelschleife hat jede Ausnahme verschluckt, „WP nicht verbunden" sah im
Dashboard genauso aus wie „WP gar nicht konfiguriert". Seit v0.6.2 gilt:

- `GET /api/v1/diag/devices` liest **jeden** Adapter einmal aktiv und liefert
  Werte oder Fehler im Klartext — der erste Griff bei „Gerät XY zeigt nichts".
- `status.geraete` nennt pro Adapter `ok`, `fehler`, `seit` und `letzte_lesung`;
  `status.wp.fehler` steht zusätzlich unter der WP-Kachel im Dashboard.
- Ausfall und Rückkehr landen im Protokoll (`gerät_<name>`) und im Add-on-Log —
  bei Wechsel sofort, danach höchstens stündlich, damit 6 Ticks/min das
  Protokoll nicht zumüllen.

## Regelverhalten

Festlegungen von Leo, 2026-07-25:

- **Vorrang Auto.** Der HeatPumpController sieht nur den Überschuss, der nach
  der Wallbox-Zuteilung übrig ist (`verteilbar − Strom × 230 V × Phasen`). Am
  Ladeverhalten ändert sich dadurch nichts — das WP-Vorziehen ist reiner Zusatz.
- **Konservative Schwellen:** Boost an ab 2,5 kW, zurück unter 0,5 kW.
- **Warmwasser vor Heizkreis.** Die WP kann nur eines zur Zeit; läuft der
  WW-Boost, wird der Heizkreis nicht zusätzlich angehoben.

### Der Vorrang gilt auch rückwirkend (Issue #6, v0.8.0)

„Vorrang Auto" stimmte bis v0.7.0 nur, solange die WP noch **nicht** lief.
Danach entschied faktisch, wer zuerst angelaufen war — Leos Fehlerbild vom
31.07.: *„Wärmepumpe läuft auf Warmwasser, Wallbox wird nicht priorisiert, Auto
wird nicht geladen."*

**Warum:** Die WP hat keinen Leistungsmesswert (nur Energiezähler, siehe oben).
Ihr Verbrauch steckt damit im Hausverbrauch und drückt den gemessenen
Überschuss um rund `wp_leistung_w` (2 kW). Die Wallbox rechnete gegen diesen
gedrückten Wert und kam nicht mehr über ihre Einschaltschwelle von 1,38 kW —
obwohl die Leistung physisch da war, nur eben in der WP.

**Wie es jetzt läuft** (`ControlLoop.tick`, Schritt 7):

```
verteilbar   = gemessener Überschuss + Leistung eines LAUFENDEN WP-Boosts
Wallbox      entscheidet gegen `verteilbar`
Wärmepumpe   bekommt `verteilbar − EV-Zuteilung`
```

Zwei Details, an denen die Sache hängt:

- **Nur real fließende Leistung wird zurückgerechnet** (`leistung_w()`): Boost
  gewünscht **und** Anlage läuft (`_laeuft()`). Ein Boost, den die Anlage nicht
  ausführt — Speicher schon warm, Beobachtungsmodus — verbraucht nichts. Ihn
  mitzuzählen hieße, dem Auto Leistung zuzuteilen, die es nicht gibt, und das
  wäre wieder Netzbezug (Issue #7).
- **Weicht ein Boost dem Auto, gilt die Mindestlaufzeit nicht.** Sie schützt den
  Verdichter vor Taktzyklen und ist in einer Verteilungsfrage kein Argument;
  bis zu 30 min darauf zu warten hieße, die Wallbox so lange aus dem Netz laden
  zu lassen. Die Rückstellung geht wie das Abschalten aus Issue #1 am Cloud-Gap
  vorbei. Die 5-min-Bedingungszeit (`wp_aus_entprellung_s`) bleibt — eine
  vorbeiziehende Wolke soll den Boost nicht killen. Der Wiederanlauf ist durch
  die 10-min-Startbedingungszeit ohnehin gebremst, ein Taktzyklus entsteht also
  nicht.

Im Protokoll und in der Kachel steht der Unterschied im Klartext: „Überschuss
weg" und „das Auto hat ihn bekommen" sehen in den Zahlen gleich aus, sind aber
zwei verschiedene Sachverhalte.

### Getrennt schaltbar (Issue #1, v0.7.0)

Warmwasser und Heizkreis sind **zwei getrennte Funktionen auf derselben
Anlage** und werden unabhängig voneinander ein- und ausgeschaltet:
`wp_ww_aktiv` (Default **an**) und `wp_hk_aktiv` (Default **aus** — die
Heizkreis-Anhebung wird erst mit dem dynamischen Tarif interessant).

Bedient wird das direkt in der Wärmepumpen-Kachel des Dashboards: je ein
AN/AUS-Schalter in der Überschrift, der `PUT /api/v1/config` schreibt. Eine
abgeschaltete Funktion bleibt sichtbar und ablesbar, tritt aber optisch zurück;
in den Einstellungen werden ihre Schwellwerte mit ausgegraut.

Zwei Festlegungen dahinter:

- **Ausschalten wirkt sofort.** Ein laufender Boost wird zurückgestellt, ohne
  die Mindestlaufzeit abzuwarten — und die Rückstellung geht am Cloud-Gap
  vorbei. Ein Ausschalter, der erst in 15 Minuten wirkt, ist keiner.
- **Der Schalter steht in der Konfiguration, nicht am Gerät.** Er ist deshalb
  auch dann gültig und bedienbar, wenn die WP gerade nicht erreichbar ist.

### Warmwasser (REQ-010)

1. Überschuss ≥ `wp_ww_an_w` (2500 W) **10 min am Stück** → Sollwert auf
   `wp_ww_boost_c` (57 °C).
2. Zurück auf `wp_ww_normal_c` (45 °C), sobald
   - der Speicher die 57 °C erreicht hat (sofort), **oder**
   - der Überschuss 5 min unter `wp_ww_aus_w` liegt **und** die Mindestlaufzeit
     von 30 min um ist (REQ-064).
3. Ein neuer Boost erst wieder, wenn der Speicher unter `wp_ww_wieder_c`
   (53 °C) fällt.
4. Eine gesetzte harte Komfortgrenze (`hard_limit_ww_min_temp`, REQ-012) sticht
   den Rückstellwert — es wird nie darunter gestellt.

**Der Rückweg hängt nicht am Boost-Ende.** In jedem Tick, in dem kein Boost
läuft und auf der Anlage trotzdem der Boost-Sollwert steht, setzt das EMS
`wp_ww_normal_c` — auch wenn es selbst nie einen Boost gestartet hat. Ohne das
war die Rückstellung ein einzelnes Ereignis, und ein Add-on-Neustart mitten im
Boost ließ die 57 °C stehen: der Controller startet ohne Gedächtnis, sah nur
einen fremden Sollwert und rührte ihn nie an. Am **28.08.2026** stand der
Sollwert dadurch die ganze Nacht auf 57 °C; gegen 06:20 heizte die WP den
Speicher aus der ohnehin fast leeren Hausbatterie nach und drückte sie auf 0 %.
Zurückgenommen wird nur, was aussieht wie der eigene Boost-Sollwert
(≥ `wp_ww_boost_c` − 0,5 K) — ein von Hand in der MyVaillant-App gestellter
Zwischenwert bleibt stehen.

**Warum die Wiedereinschalt-Schwelle.** Der Boost endet bei 57 °C, der Speicher
kühlt in Minuten auf 56,4 ab — und ohne Sperre startet bei liegendem Überschuss
sofort der nächste Boost für ein paar hundert Wattstunden. Mit 53 °C liegt
zwischen zwei Boosts ein sinnvolles Energiepaket. Die Schwelle wird intern auf
`wp_ww_boost_c` − 0,5 K gedeckelt: eine versehentlich zu hoch gesetzte Schwelle
ist damit wirkungslos statt eine Dauersperre.

**Warum 57 und nicht 60 °C.** Ursprünglich war das Boost-Ziel 60 °C. Die
Betriebsdaten vom 31.07.2026 (fünf echte Boosts) zeigen: der Speicher kommt bei
Warmwasserbereitung real auf **~57,5 °C** und bleibt dort stehen. Mit dem Ziel
60 wurde die Abbruchbedingung „Ziel erreicht" nie wahr, jeder Boost lief stumpf
weiter bis der Überschuss wegbrach. Mit 57 greift sie.

### Heizkreis (REQ-011)

Per Default **abgeschaltet** (`wp_hk_aktiv`, siehe oben) — Leo will die
Heizungs-Anhebung erst mit dem dynamischen Tarif nutzen. Eingeschaltet gilt:

Nur in der Heizperiode: Außentemperatur ≤ `wp_hk_max_aussen_c` (15 °C) **und**
das Zeitprogramm hat überhaupt einen Sollwert (im Sommer liefert die Anlage
0 °C — dann gibt es nichts anzuheben). Angehoben wird um `wp_hk_anhebung_k`
(1,5 K), gekappt bei `wp_hk_max_raum_c` (23 °C, REQ-012). Zurückgestellt wird
auf den Wert, der vor der Anhebung stand.

## Drei Dinge, die die Logik prägen

**Kein Leistungsmesswert.** Die WP hat in HA nur Energiezähler. Ihr Verbrauch
steckt also im Hausverbrauch und senkt den gemessenen Überschuss, sobald ein
Boost läuft. Genau dafür ist das Hysterese-Band da: der Abstand zwischen An- und
Aus-Schwelle (2,5 → 0,5 kW = 2,0 kW) ist so breit wie der geschätzte Verbrauch
`wp_leistung_w`. Wird das Band enger konfiguriert, zieht `_aus_schwelle()` die
Aus-Schwelle nach unten und toleriert etwas Netzbezug — statt in einen
Schaltzyklus zu laufen.

**Cloud-Ratenlimit (REQ-014).** Geschrieben wird nur bei Zustandswechsel und
höchstens alle `wp_cloud_min_gap_s` (15 min), maximal ein Aufruf pro Tick. Ein
Sollwert gilt als „gewünscht", bis ihn ein Rücklesen bestätigt — dadurch wird
ein verlorener Cloud-Aufruf von selbst wiederholt, ohne Dauerschleife. Praktische
Folge: das Zurückstellen kann sich um bis zu 15 min verzögern. Unkritisch, weil
die WP bei erreichtem Sollwert ohnehin abschaltet.

**Keine Dauer-Übersteuerung.** Sobald ein Sollwert bestätigt ist, schreibt das
EMS nicht mehr nach. Wer in der MyVaillant-App von Hand etwas ändert, wird nicht
überstimmt.

## Sicherheit

- Der **Beobachtungsmodus** (`read_only`, Default an) gilt auch hier: es geht
  nichts an die Cloud raus. Der Status zeigt trotzdem, was das EMS tun *würde*.
- **Fail-Safe E7** (neu in der Matrix, Spec §7): HA/WP nicht erreichbar →
  keine WP-Befehle, keine Zustandsrücksetzung, Ladebetrieb unverändert. Offene
  Sollwerte gehen raus, sobald die Verbindung wieder steht.
- Fällt der E3DC aus (E1), bricht der Tick vorher ab — die WP wird dann gar
  nicht bewertet, weil ohne E3DC keine Überschussdaten vorliegen.

## Der Schreibweg funktioniert (bestätigt 2026-08-02)

Nach dem ersten Boost am 26.07.2026 stand der Verdacht im Raum, MyVaillant
übernehme in der Betriebsart `Auto` gar keinen Sollwert — der Aufruf ging
fehlerfrei durch, der Sollwert blieb aber auf 45 °C. Daraus wurde die Frage, ob
das EMS vorher per `set_operation_mode` in den Tag-/Manuell-Betrieb schalten
muss, also in Leos Heizungsprogramm eingreifen.

**Muss es nicht.** Die HA-Historie von `sensor.home_domestic_hot_water_0_setpoint`
zeigt seit dem 29.07. durchgehend echte Boost-Zyklen, alle in Betriebsart
`Auto` — allein am 31.07. fünfmal 45 → 57/60 → 45, und die Speichertemperatur
folgt (48,5 → 56,5 °C zwischen 08:15 und 08:52). Der Befund vom 26.07. war
eine einzelne verzögerte oder verschluckte Cloud-Übernahme, kein systematisches
Verhalten. Genau dafür ist die Wiederholung am Cloud-Gap da.

Bleibt richtig: das EMS schreibt nur bei Zustandswechsel, wiederholt höchstens
alle `wp_cloud_min_gap_s`, und `set_operation_mode` wird **nicht** benutzt —
das Zeitprogramm bleibt unangetastet.

## Offen

- REQ-011 im Praxistest: Wie schnell reagiert die Anlage auf
  Sollwertänderungen (Latenz Cloud → Gerät)? Die Werte für Entprellung und
  Mindestlaufzeit sind Schätzungen und in der ersten Heizperiode zu prüfen.
- WP-Leistungsmessung: Solange es keinen Leistungssensor gibt, steckt der
  WP-Verbrauch im Wert „Haus" und `wp_leistung_w` bleibt eine Schätzung.
