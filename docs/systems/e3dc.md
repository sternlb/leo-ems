# E3DC S10E Infinity

**Rolle:** Hauskraftwerk — 9,23 kWp PV (Ost, 22°) + 12 kWh Batterie + Hausanschlussmessung. Zentrale Messquelle des EMS (Netz, PV, Batterie, Hausverbrauch).

## Integration

- **HA:** „E3DC Remote Storage Control Protocol" (RSCP, HACS) — ✅ installiert, Entities vorhanden (u.a. `S10E Battery discharge - today`, `S10E Energy charged from grid`, `S10E Manual charge`).
- **Protokoll:** RSCP lokal über IP; Zugangsdaten = E3DC-Portal-Login + RSCP-Passwort (E3DC: *Personalisierung > Benutzerprofil*).
- **EVCC:** unterstützt E3DC nativ als Grid-/Battery-/PV-Meter (Vorrecherche im Second Brain, „PV Anlage Garagendach").

## Fähigkeiten (für das EMS relevant)

- Lesen: PV-Leistung, Netz-Bezug/-Einspeisung, Batterie-SoC/-Leistung, Hausverbrauch — Messfundament für die Überschussberechnung.
- Schreiben (RSCP, zu verifizieren): Ladeleistungs-Limits, Entladesperre, manuelles Laden/Netzladen.

## Status-Update (2026-07-12)

**RSCP-Anbindung läuft bereits produktiv über EVCC** (HACS-Installation in HA) — der Mess-/Steuerweg ist damit praktisch validiert. **Aber: EVCC soll durch das EMS ersetzt werden (REQ-008)** → das EMS braucht einen eigenen RSCP-Zugang (HACS-Integration „E3DC RSCP" oder eigene RSCP-Client-Bibliothek). Zusätzlich: 70 %-Einspeisebegrenzung ist für die Bestandsanlage in der E3DC-Steuerung hinterlegt.

## Offene Fragen

- [x] ~~RSCP getestet?~~ **Ja — funktioniert über EVCC** (2026-07-12); EVCC wird ersetzt, eigener Zugang nötig.
- [ ] Deckt die vorhandene HACS-Integration alle nötigen Schreibbefehle ab (Entladesperre, Ladeleistungslimit, Netzladen), oder braucht das EMS einen eigenen RSCP-Client?
- [ ] Verhält sich die E3DC-Regelung sauber, wenn extern übersteuert wird (Rückfall nach Timeout)?
- [ ] Sieht die E3DC die AC-gekoppelte Sungrow-Erzeugung am Hausanschlusspunkt korrekt als „negative Last"?
