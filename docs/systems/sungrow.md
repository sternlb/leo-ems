# Sungrow SG 6.0RT

**Rolle:** String-Wechselrichter der Garagendach-Anlage — 12× Trina Vertex S+ 470 W = 5,64 kWp, Ost/West 15°, AC-gekoppelt zusätzlich zur E3DC. Prognose: ~5.160 kWh/Jahr (PVGIS, Details im Second Brain „PV Anlage Garagendach").

**Status:** ✅ **in Betrieb seit 2026-08-22**, per Modbus TCP angebunden (v0.11.0). Seriennummer A2331605241, Device Type Code 0x2431, 6,0 kW, dreiphasig (3P4L). Die 12 Module hängen als **2 Strings à 6** an den beiden MPPT-Eingängen — nicht dokumentiert, sondern aus den fast gleichen Strangspannungen erschlossen.

## Verbindung

| Parameter | Wert | Add-on-Option |
|---|---|---|
| Host | 192.168.178.51 | `sungrow_host` |
| Port | 502 | `sungrow_port` |
| Unit-ID | **1** | `sungrow_unit_id` |

Kommunikation über den **WiNet-S**-Dongle. Modbus TCP war ab Werk aktiv, es musste nichts freigeschaltet werden. Die Web-UI des Dongles liegt unter `http://192.168.178.51/`, Werkszugänge `user`/`pw1111` und `admin`/`pw8888`.

Leerer `sungrow_host` = `SungrowStub`, konstant 0 W. Das ist der definierte Zustand für Entwicklung ohne Anlage im Netz.

## Fallstricke (alle real aufgetreten)

- **Die Unit-ID ist am WiNet-S nirgends einstellbar oder ablesbar.** Sie musste durch Abtasten gefunden werden (hier: 1). Falsche IDs antworten nicht, sondern laufen in einen Timeout — es gibt also keine hilfreiche Fehlermeldung, nur Stille. Deshalb ist die ID eine Add-on-Option: Bei einem Gerätetausch muss man sie neu erraten können, ohne das Add-on neu zu bauen.
- **Nur eine Modbus-Verbindung gleichzeitig.** Der Adapter hält die Verbindung deshalb über Ticks hinweg offen. Läuft das Add-on, schlägt ein paralleles Testskript fehl — und die iSolarCloud-App kann ebenfalls dazwischenfunken.
- **32-Bit-Werte liegen Low-Word zuerst.** `wert = (hi << 16) | lo` mit `lo` im *ersten* Register. Die mit Abstand häufigste Fehlerquelle bei diesen Geräten.
- **Registernummern sind 1-basiert dokumentiert, auf dem Draht 0-basiert.** Der Adapter rechnet das zentral in `baue_anfrage()` um; die Konstanten stehen im Code so, wie sie im Datenblatt stehen.
- **Register 5036 (Netzfrequenz) skaliert mit 0,1 Hz**, nicht mit 0,01 wie in manchen Registerkarten. Kontrollwert: das Ergebnis muss ~50 Hz sein.
- Nachts oder bei stromlosem Wechselrichter meldet die Dongle-Web-UI „Netzwerkfehler, bitte Netzwerk prüfen" — das ist kein Netzproblem, sondern der abwesende Wechselrichter.

## Genutzte Register (Nummern 1-basiert, alle FC04 Input Register)

| Reg | Anz | Inhalt | Skalierung |
|---|---|---|---|
| 5003 | 1 | Tagesertrag | 0,1 kWh |
| 5004 | 2 | Gesamtertrag | 1 kWh, u32 |
| 5008 | 1 | Innentemperatur | 0,1 °C, **vorzeichenbehaftet** |
| 5011 | 2 | MPPT1 Spannung / Strom | 0,1 V / 0,1 A |
| 5013 | 2 | MPPT2 Spannung / Strom | 0,1 V / 0,1 A |
| 5017 | 2 | DC-Leistung gesamt | 1 W, u32 |
| 5031 | 2 | **AC-Wirkleistung** | 1 W, u32 |
| 5036 | 1 | Netzfrequenz | 0,1 Hz |

Gelesen wird in **zwei Blöcken je Tick** statt in acht Einzelabfragen: 5011–5036 (Messwerte, Pflicht) und 5003–5008 (Ertragszähler, nur Anzeige). Fällt der zweite Block aus, bleiben die Messwerte gültig und der Fehler wird in `letzter_fehler` benannt — die Regelschleife darf wegen eines Anzeigewerts nicht in den Fail-Safe laufen.

Zur Diagnose ebenfalls nützlich (FC03 Holding): **5007** = Leistungsbegrenzung Schalter (0xAA an / 0x55 aus), **5008** = Sollwert in 0,1 %.

## Rolle in der Regelung

Der Wechselrichter ist ein **reiner Erzeuger** — nichts zu steuern. Sein Wert geht in die Gesamterzeugungs-Anzeige (REQ-040/051) und ausdrücklich **nicht** in die Überschussformel: Die Anlage ist AC-gekoppelt und erscheint bereits im Netzzähler der E3DC. Doppelt gezählt sähe das EMS einen Überschuss, den es nicht gibt, und gäbe zu viel Ladeleistung frei.

**Fail-Safe E5** (Leo, 2026-07-12): Ausfall → Erzeugung 0, Betrieb läuft unverändert weiter. Der Adapter wirft dazu eine `ConnectionError`; bewertet wird in `core/loop.py`.

## Einspeisebegrenzung

Für die Neuanlage gilt die **60-%-Grenze, durchgesetzt über die E3DC-Anlage** am gemeinsamen Netzverknüpfungspunkt (Leo, 2026-08-22). Der Sungrow läuft bewusst unbegrenzt — der ausgelesene Sollwert von 100 % ist der gewollte Zustand, am Wechselrichter ist nichts zu tun.

Offen: Die E3DC-Steuerung muss von Elektriker Waldemar auf die neue Situation umkonfiguriert werden; Leo kommt an die Einstellung nicht heran. 60 % von 13,96 kWp sind rund 8,4 kW — beide Anlagen zusammen können darüber liegen, abgeregelte Energie ist dann verloren. Das erhöht den Wert der lokalen Überschussverwertung (REQ-043): Sie vermeidet nicht nur Netzbezug, sondern **Abregelung**.

## Warum kein pymodbus

Gebraucht wird ein einziger Funktionscode: Input-Register lesen. Das sind ~40 Zeilen in `devices/sungrow.py`, gegen die reale Anlage verifiziert. pymodbus hat den Slave-Parameter zwischen 3.7 und 3.9 von `slave` auf `device_id` umbenannt — diese Fallhöhe lohnt für einen Funktionscode nicht, und das Add-on-Image baut eine Abhängigkeit weniger.

## Erledigte offene Fragen

- [x] ~~LAN in der Garage?~~ **Ja** (2026-07-12) → Modbus TCP ist der Weg.
- [x] ~~Zeitplan?~~ **Installiert und angebunden am 2026-08-22.**
- [x] ~~WiNet-S-Dongle im Lieferumfang / Modbus TCP darüber freigeschaltet?~~ **Dongle vorhanden, Modbus TCP ab Werk offen.**
- [x] ~~Gilt die 70-%-Regel auch für die Neuanlage?~~ **Nein — 60 %, und die setzt die E3DC durch.** Siehe oben.
