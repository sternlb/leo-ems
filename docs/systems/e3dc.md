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

## Spike-Ergebnis (2026-07-12, `backend/spikes/e3dc_spike.py`, eigener RSCP-Client via pye3dc)

**Lesen:** funktioniert, plausible Live-Werte (Solar 6.875–6.881 W, Netz −2.490/−2.559 W Einspeisung, Haus ~4,3 kW, SoC 98 %, Batterie 0 W).

**Schreiben:** `set_power_limits(enable=True, max_discharge=0)` und das Lösen (`enable=False`) wurden **ohne Fehler angenommen** — der eigene RSCP-Zugriff (unabhängig von der HACS-Integration/EVCC) kann die Batterie also grundsätzlich fernsteuern. ✅ Wichtigste technische Risikoannahme des Systems damit bestätigt.

**Noch offen (braucht Leos Beobachtung in Echtzeit):**
- [ ] **Sichtbare Wirkung bei echtem Entladen:** Der Test lief bei SoC 98 % ohne Batterieaktivität — der Befehl kam durch, aber ohne sichtbaren Effekt (nichts entlud). Rerun empfohlen, wenn die Batterie abends tatsächlich Leistung abgibt: `python spikes/e3dc_spike.py --schreiben`, dabei E3DC-App/Portal offen halten und prüfen, ob die Entladeleistung während der 60 s auf 0 fällt.
- [ ] **Abbruch-Test (kalibriert das Lease-TTL, Spec §5.1):** Skript mit `--schreiben` starten, **während der 60-Sekunden-Wartezeit mit Strg+C abbrechen** (Sperre bleibt dann gesetzt, da das Lösen im Skript nicht mehr läuft), danach am E3DC-Display/Portal stoppen, **wie lange es dauert, bis die Batterie von selbst wieder normal lädt/entlädt**. Ergebnis bitte melden — falls die E3DC deutlich schneller oder langsamer als 15 min zurückkehrt, passen wir `lease_ttl_s` in `backend/leo_ems/config.py` an.

## Ursprüngliche offene Fragen

- [x] ~~RSCP getestet?~~ **Ja — funktioniert über EVCC** (2026-07-12); zusätzlich jetzt eigener RSCP-Zugriff verifiziert (s.o.).
- [x] ~~Deckt die HACS-Integration/braucht das EMS einen eigenen RSCP-Client?~~ Das EMS nutzt einen **eigenen RSCP-Client** (pye3dc) — bestätigt funktionsfähig für Lesen + Schreiben.
- [ ] Verhält sich die E3DC-Regelung sauber, wenn extern übersteuert wird (Rückfall nach Timeout)? → wird durch den Abbruch-Test oben beantwortet.
- [ ] Sieht die E3DC die AC-gekoppelte Sungrow-Erzeugung am Hausanschlusspunkt korrekt als „negative Last"?
