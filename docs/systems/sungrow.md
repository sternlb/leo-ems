# Sungrow SG 6.0RT *(in Planung)*

**Rolle:** String-Wechselrichter der geplanten Garagendach-Anlage — 12× Trina Vertex S+ 470 W = 5,64 kWp, Ost/West 15°, AC-gekoppelt zusätzlich zur E3DC. Prognose: ~5.160 kWh/Jahr (PVGIS, Details im Second Brain „PV Anlage Garagendach").

## Integration (geplant)

- **Bevorzugt:** Modbus TCP lokal — der SG 6.0RT hat LAN/WLAN (WiNet-S-Dongle); HACS-Integrationen: „Sungrow Inverter" (Modbus) oder SunGather.
- **Fallback:** iSolarCloud (Cloud) — nicht bevorzugt (Latenz, Cloud-Abhängigkeit).
- **EVCC:** Sungrow wird via Modbus/SunSpec unterstützt (Kompatibilitätskriterium aus der Vorrecherche erfüllt).

## Fähigkeiten (für das EMS relevant)

- Lesen: aktuelle AC-Leistung, Tages-/Gesamtertrag, ggf. String-Werte.
- Kein Speicher, keine Steuerlast — reiner Erzeuger. EMS-Aufgabe: Erzeugung zur E3DC-Messung addieren (REQ-040).
- Ggf. Wirkleistungsbegrenzung per Modbus (relevant falls Netzbetreiber-Auflagen, REQ-043).

## Offene Fragen

- [ ] LAN in der Garage vorhanden oder WLAN-Reichweite ausreichend?
- [ ] WiNet-S-Dongle im Lieferumfang / Modbus TCP darüber freigeschaltet? (Firmware-Versionen unterscheiden sich hier.)
- [ ] Auflagen der Stadtwerke Röthenbach: Einspeisebegrenzung / §14a-Steuerbarkeit für die neue Anlage?
- [ ] Zeitplan der Installation (bestimmt, ab wann REQ-040/042 real testbar sind).
