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

## Entladegrenze statt Entladesperre (v0.9.0)

Seit v0.9.0 schreibt das EMS beim Laden nicht mehr nur 0, sondern eine **dynamische Grenze** (Spec §5.1, `backend/leo_ems/planner/batt_limit.py`). Was dabei über den RSCP-Weg zu wissen ist:

- `set_power_limits(enable, max_charge=None, max_discharge=None, discharge_start=None)` sendet `EMS_REQ_SET_POWER_SETTINGS`. `max_discharge` ist ein Uint32 — nicht-negative ganze Watt. Rückgabe: `0` angenommen, `1` angenommen-aber-nicht-optimal, `-1` abgelehnt. Der Adapter wirft seit v0.9.0 bei `-1`; bis dahin lief eine Ablehnung stumm durch.
- **Untere Wirkschwelle:** unterhalb `discharge_start` (Anlagen-Default ~65 W) entlädt die E3DC ohnehin nicht. Grenzen unter 100 W schreibt das EMS deshalb als 0 — sie wären nur Schein.
- **`max_charge` bleibt ungenutzt** — das ist der Anknüpfungspunkt für REQ-022/023 (Zeitverschiebung, Netzladen bei dynamischem Tarif).
- **Schreibfrequenz:** eine persistente Anlagen-Einstellung alle 10 s zu beschicken wäre unnötiger Verschleiß. Das EMS rastert auf 50 W und schreibt erst ab `batt_dyn_schreibschwelle_w` Änderung. **Zu beobachten:** Wie viele `entladegrenze`-Einträge stehen unter `/api/v1/history` pro Minute? Ziel < 6; falls mehr, die Schwelle anheben.

**Noch offen:**
- [ ] Folgt die reale Entladeleistung der gesetzten Grenze (nicht nur 0/frei)? Bei einem Ladevorgang mit Netzbezug prüfen, ob die Batterie genau den Hausbedarf deckt und nicht mehr.

## Ursprüngliche offene Fragen

- [x] ~~RSCP getestet?~~ **Ja — funktioniert über EVCC** (2026-07-12); zusätzlich jetzt eigener RSCP-Zugriff verifiziert (s.o.).
- [x] ~~Deckt die HACS-Integration/braucht das EMS einen eigenen RSCP-Client?~~ Das EMS nutzt einen **eigenen RSCP-Client** (pye3dc) — bestätigt funktionsfähig für Lesen + Schreiben.
- [ ] Verhält sich die E3DC-Regelung sauber, wenn extern übersteuert wird (Rückfall nach Timeout)? → wird durch den Abbruch-Test oben beantwortet.
- [ ] Sieht die E3DC die AC-gekoppelte Sungrow-Erzeugung am Hausanschlusspunkt korrekt als „negative Last"?
