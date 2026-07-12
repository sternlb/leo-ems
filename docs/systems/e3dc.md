# E3DC S10E Infinity

**Rolle:** Hauskraftwerk — 9,23 kWp PV (Ost, 22°) + 12 kWh Batterie + Hausanschlussmessung. Zentrale Messquelle des EMS (Netz, PV, Batterie, Hausverbrauch).

## Integration

- **HA:** „E3DC Remote Storage Control Protocol" (RSCP, HACS) — ✅ installiert, Entities vorhanden (u.a. `S10E Battery discharge - today`, `S10E Energy charged from grid`, `S10E Manual charge`).
- **Protokoll:** RSCP lokal über IP; Zugangsdaten = E3DC-Portal-Login + RSCP-Passwort (E3DC: *Personalisierung > Benutzerprofil*).
- **EVCC:** unterstützt E3DC nativ als Grid-/Battery-/PV-Meter (Vorrecherche im Second Brain, „PV Anlage Garagendach").

## Fähigkeiten (für das EMS relevant)

- Lesen: PV-Leistung, Netz-Bezug/-Einspeisung, Batterie-SoC/-Leistung, Hausverbrauch — Messfundament für die Überschussberechnung.
- Schreiben (RSCP, zu verifizieren): Ladeleistungs-Limits, Entladesperre, manuelles Laden/Netzladen.

## Offene Fragen

- [ ] Schreibzugriffe der HACS-Integration in der Praxis getestet? Welche Set-Entities existieren?
- [ ] Verhält sich die E3DC-Regelung sauber, wenn extern übersteuert wird (Rückfall nach Timeout)?
- [ ] Sieht die E3DC die AC-gekoppelte Sungrow-Erzeugung am Hausanschlusspunkt korrekt als „negative Last"?
