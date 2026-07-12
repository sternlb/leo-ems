# 00 — Vision

**Status:** Entwurf · **Stand:** 2026-07-12

## Problem

Der Haushalt hat starke Erzeugung (9,23 kWp, bald +5,64 kWp) und einen 12-kWh-Speicher, aber die Komponenten arbeiten unkoordiniert:

- Das E-Auto lädt, wann es angesteckt wird — nicht, wenn PV-Überschuss da ist.
- Die Wärmepumpe heizt nach eigenem Zeitplan — nicht, wenn Strom im Überfluss vorhanden ist.
- Die E3DC-Batterie regelt nur ihren eigenen Hausanschluss und "sieht" weder die geplante zweite Anlage noch die Absichten von EV und WP (z.B. entlädt sie sich in ein ladendes Auto).

Messdaten 2025: ~50 % Autarkie, 54 % der Erzeugung wurden eingespeist. Die Simulation zeigt, dass mehr Module allein kaum helfen (~90 % des Mehrertrags gehen in die Einspeisung). Der Hebel ist **Koordination**.

## Ziel

Ein EMS auf Home-Assistant-Basis, das:

1. **PV-Überschuss aktiv verwertet** — zuerst ins E-Auto, dann in Warmwasser/Puffer, dann in die Batterie, zuletzt ins Netz.
2. **Beide Erzeugungsanlagen als Einheit** betrachtet (E3DC + Sungrow AC-gekoppelt).
3. **Bedarfe respektiert** — das Auto ist zur Abfahrtszeit ausreichend geladen, Warmwasser-Komfort bleibt gewahrt, die Batterie hält eine Reserve.
4. **Vorbereitet ist auf dynamische Strompreise** — Lasten und Batterieladung folgen künftig auch dem Preissignal, nicht nur der Sonne.
5. **Sicher versagt** — bei Ausfall von APIs oder des EMS selbst fallen alle Geräte auf ihr autonomes Standardverhalten zurück.

## Nicht-Ziele

- Steuerung von Haushaltsgeräten (Waschmaschine & Co. via Smart Plugs) — bewusst außerhalb des Scopes.
- Ersatz der E3DC-internen Regelung im Normalbetrieb — das EMS übersteuert nur gezielt.
- Handel/Arbitrage über Einspeisung hinaus (kein Regelenergie-Markt o.ä.).

## Erfolgskriterien (erste Fassung, in Phase 1/2 zu schärfen)

- Autarkie steigt messbar gegenüber Baseline 2025 (~50 %) bei gleichem Komfort.
- Anteil des EV-Ladestroms aus eigener PV steigt deutlich (Baseline zu ermitteln).
- Kein manueller Eingriff im Alltag nötig; Eingriffe des EMS sind nachvollziehbar geloggt.

## Rahmenentscheidungen

- **Eigenbau, EVCC wird ersetzt** (Leo, 2026-07-12): Das EMS bildet EVCCs Lade-Funktionen selbst nach (REQ-007) und löst die bestehende EVCC-Installation ab (REQ-008). Die ADR in Phase 3 klärt nur noch den Tech-Stack (AppDaemon / Custom Integration / Add-on) und die UI-Frage (HA-Dashboard vs. separate App).
- **Plattform:** Home Assistant ist gesetzt (alle Geräte sind dort bereits integriert).
- **PV-Prognose:** Forecast.Solar.
- **Dynamischer Tarif:** geplant, noch kein Anbieter gewählt → Requirements als *Should* führen, Adapter für Top-5-Anbieter DE.
