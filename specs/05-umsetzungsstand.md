# 05 — Umsetzungsstand & Testabdeckung

**Stand:** 2026-08-22 (v0.11.0) · **Grundlage:** [01-requirements.md](01-requirements.md)

Diese Datei ist die Brücke zwischen Anforderung und Beweis: pro Requirement, was
umgesetzt ist, wo es im Code steht und **welcher Test es hält**. Sie ersetzt keine
Spezifikation, sondern beantwortet die Frage „was ist fertig und woran merken wir
es, wenn es kaputtgeht?".

Legende Umsetzung: ✅ umgesetzt · 🔵 teilweise · ⚪ offen
Legende Abdeckung: **T** = automatisierter Test · **L** = am Live-System verifiziert · **—** = kein Test

## Zahlen

| | Must (26) | Should (13) | Gesamt (39) |
|---|---|---|---|
| ✅ umgesetzt | 21 | 5 | **26** |
| 🔵 teilweise | 4 | 4 | **8** |
| ⚪ offen | 1 | 4 | **5** |

162 automatisierte Tests. **35 der 39 Requirements haben einen Nachweis** (Test,
Live-Verifikation oder beides). Ohne jeden Nachweis sind nur REQ-008, 022, 023,
030 und 031 — vier davon gehören zu Ausbaustufe 3, die es real noch nicht gibt.

Die Anforderungsliste selbst führt denselben Stand in der Spalte *Umsetzung* mit:
[01-requirements.md](01-requirements.md). Dort steht das **Was**, hier das **Womit
bewiesen**.

---

## A — PV-Überschussladen E-Auto (Stufe 1, alle Must)

| ID | Umsetzung | Code | Nachweis |
|---|---|---|---|
| REQ-001 Überschuss berechnen | ✅ | `planner/surplus.py` | **T** `test_surplus.py` (4 Tests, inkl. Abnahmekriterium Spec §2) · **L** |
| REQ-002 Ladeleistung + 1p/3p | ✅ *(Netzbezug-Fehler behoben in v0.8.0)* | `planner/charge_control.py` | **T** `test_t1_ueberschussfolge`, `test_t2_phasenwechsel` (wörtlich nach Spec), `test_3p_unter_minimum_zieht_keinen_dauernetzbezug`, `test_pause_erst_wenn_auch_1p_nicht_mehr_traegt`, `test_hochschalten_wartet_weiter_auf_die_sperre` · **L** |
| REQ-003 Zielladung auf Abfahrtszeit | ✅ | `planner/rules.py` | **T** `test_rules.py` (6 Tests, inkl. T3-Mehrfachregel) |
| REQ-004 Mindest-SoC garantieren | ✅ | `planner/rules.py` | **T** `test_garantie_uebersteuert_aus`, `test_garantie_uebersteuert_aus_modus` |
| REQ-005 Lademodi | ✅ *(fünfter Modus „PV+Batterie" seit v0.10.0)* | `charge_control.py`, `PUT /api/v1/mode` | **T** `test_modus_aus_kein_laden`, `test_modus_schnell_max_sofort`, `test_pv_min_laedt_immer_mindestens`, `test_pv_batterie_regelt_gegen_das_budget_ohne_netzbezug`, `test_pv_batterie_regelt_gegen_pv_plus_batterie`, `test_api::test_mode_put` |
| REQ-006 Fahrzeug-SoC aus der Integration | ✅ *(seit v0.6.3 erstmals wirklich)* | `devices/skoda.py` | **T** `test_skoda_liest_soc_unter_beiden_feldnamen`, `test_skoda_unbekanntes_soc_feld_wird_als_ausfall_gemeldet` · **L** 80 % gelesen |
| REQ-007 EVCC funktionsäquivalent | 🔵 Funktionen da, Äquivalenz nicht belegt | ganzer Ladepfad | **T** je Einzelfunktion · **Vergleich gegen die EVCC-Baseline fehlt** |
| REQ-008 EVCC ablösen/deinstallieren | ⚪ EVCC läuft weiter parallel | — | — |

**Offen in A:** der Nutzenvergleich gegen `docs/evcc-baseline.md` (99,4 % Solaranteil
30 d) — dafür braucht es Beobachtungsdaten, die bis v0.6.4 bei jedem Update
gelöscht wurden (siehe REQ-073). Erst danach ist REQ-008 verantwortbar.

## B — Wärmepumpe (Stufe 2, alle Should)

| ID | Umsetzung | Code | Nachweis |
|---|---|---|---|
| REQ-010 Warmwasser vorziehen | ✅ | `planner/heatpump.py` | **T** 11 Tests (Entprellung, Mindestlaufzeit, Selbstabschaltung, Zieltemperatur) · **L** live, Boost-Zyklen 29.07.–01.08.2026 |
| REQ-011 Heizkreis anheben | 🔵 umgesetzt, per Default **aus** (Issue #1) | `heatpump.py` | **T** 4 Tests (Sommer/Winter, Obergrenze, Rückstellung) · **L erst ab Herbst** |
| REQ-012 Komfortgrenzen | ✅ | `heatpump.py`, `config.py` | **T** `test_ww_komfortgrenze_hebt_rueckstellwert_an`, `test_heizkreis_respektiert_komfort_obergrenze` |
| REQ-013 Steuerweg MyVaillant über HA | ✅ **Lesen und Schreiben bestätigt** | `devices/vaillant.py` | **T** 5 Tests (Zugangssuche, Token-Herkunft) · **L** HA-Historie `…_setpoint`: 45↔57/60 in Betriebsart `Auto`, Speicher folgt (31.07.: 48,5 → 56,5 °C) |
| REQ-014 Cloud-Ratenlimit | ✅ | `heatpump.py` | **T** `test_cloud_gap_bremst_wiederholungen`, `test_bestaetigter_sollwert_wird_nicht_nachgeschrieben` |
| Issue #1 getrennt schaltbar | ✅ | `config.py`, `heatpump.py`, `web/index.html` | **T** 6 Tests (Start unterdrückt, sofortige Rückstellung, Unabhängigkeit, Defaults, Status) · **L** am Vorschau-Server verifiziert |
| Issue #6 Vorrang Wallbox vor WP | ✅ | `core/loop.py` (Schritt 7), `heatpump.py` (`leistung_w`) | **T** `test_auto_startet_auch_wenn_die_waermepumpe_schon_laeuft`, `test_ww_boost_weicht_dem_auto_ohne_mindestlaufzeit`, `test_ohne_ladendes_auto_gilt_die_mindestlaufzeit_weiter`, `test_leistung_w_zaehlt_nur_einen_wirklich_laufenden_boost` · **L offen** |
| Issue #7 Netzbezug beim Zuschalten | ✅ | `charge_control.py`, `config.py` | **T** 4 Tests (3p-Minimum, Rückfall ohne Sperre, Pause, Diagnose) · **L offen** |

**Offen in B:** der Heizkreis-Praxistest steht noch aus — er beginnt frühestens
mit der Heizperiode und erst, wenn Leo `wp_hk_aktiv` einschaltet. Die
Warmwasser-Seite ist im Realbetrieb bestätigt (siehe REQ-010/013).

## C — Batterie-Management (E3DC)

| ID | Umsetzung | Code | Nachweis |
|---|---|---|---|
| REQ-020 Entladegrenze beim EV-Laden | ✅ *(dynamisch seit v0.9.0, Freigabe seit v0.10.0)* | `planner/batt_limit.py`, `core/loop.py`, `safety/guard.py` | **T** `test_batt_limit` (17 Fälle), `test_laden_und_entladegrenze`, `test_entladegrenze_folgt_dem_netzbezug`, `test_schnell_modus_sperrt_die_batterie_hart`, `test_schnell_mit_batterie_gibt_die_grenze_frei` · **L** offen für v0.9.0/v0.10.0 |
| REQ-021 SoC-Reserve respektieren | ✅ *(seit v0.10.0 wirklich durchgesetzt)* | `safety/guard.py`, `planner/batt_limit.py`, `planner/surplus.py` | **T** `test_batterie_reserve`, `test_batterie_vorrang_unter_priority_soc`, `test_freigabe_endet_an_der_reserve`, `test_reserve_hysterese_verhindert_flattern`, `test_pv_batterie_faellt_an_der_reserve_zurueck` |
| REQ-022 Batterieladung zeitlich steuern | ⚪ (Should, Stufe 3) | — | — |
| REQ-023 Netzladen bei dynamischem Tarif | ⚪ (Should, Stufe 3) | — | — |
| REQ-024 Rückfall auf autonome Regelung | ✅ Lease/TTL (ADR-005) | `safety/guard.py` | **T** `test_lease_laeuft_nach_ttl_aus`, `test_lease_laeuft_ohne_erneuerung_aus`, `test_sweep_meldet_abgelaufene_leases` |

## D — Dynamischer Tarif (Stufe 3)

| ID | Umsetzung | Code | Nachweis |
|---|---|---|---|
| REQ-030 Preis-Adapter Top-5 DE | ⚪ | — | — |
| REQ-031 Lasten in Billigstunden | ⚪ | — | — |
| REQ-032 ohne Tarif voll funktionsfähig | ✅ | ganzes System | **T** alle 86 Tests laufen ohne Preisdaten · **L** |

## E — Erzeugung & Prognose

| ID | Umsetzung | Code | Nachweis |
|---|---|---|---|
| REQ-040 Gesamterzeugung beider Anlagen | ✅ | `core/loop.py` (`p_pv_w`) | **T** `test_status_enthaelt_energieverteilung_und_phaseninfo` · **L** |
| REQ-041 Forecast.Solar in der Planung | 🔵 **Adapter fertig, aber nicht verdrahtet** | `devices/forecast.py` | **T** `test_forecast_erwartete_wh_zwischen` — die Regelschleife liest den Adapter **nicht**, die Garantieladung plant ohne Prognose |
| REQ-042 Sungrow lokal (Modbus) | ✅ Modbus TCP, 192.168.178.51:502, Unit-ID 1 | `devices/sungrow.py` | **T** `test_sungrow.py` (17 Tests: Dekodierung, Rahmenbau, Ende-zu-Ende gegen nachgebauten WiNet-S, Fail-Safe) + **L** am 2026-08-22 gegen die reale Anlage (1302 W AC / 1393 W DC, 12–19 ms je Tick) |
| REQ-043 70 %: Überschuss lokal verwerten | ✅ (EV + WP) | Ladepfad + `heatpump.py` | **T** indirekt · Annahme „Wechselrichter regelt selbst" bei Inbetriebnahme prüfen |

**Wichtigste Lücke der Stufe 1:** REQ-041. `plane_garantieladung()` bekommt keine
Prognose übergeben — die Zielladung entscheidet also ohne das Wissen „morgen
mittag kommen 8 kWh". Genau das war laut `docs/evcc-baseline.md` eine der drei
Neuerungen gegenüber EVCC.

## F — Monitoring / Dashboard

| ID | Umsetzung | Code | Nachweis |
|---|---|---|---|
| REQ-050 Zustand + Grund sichtbar | ✅ | `charge_control.phase_diagnose`, `/api/v1/status` | **T** `test_phase_diagnose_entprellung`, `…_umschaltsperre`, `…_stabil`, `test_phase_diagnose_entprellung` · **L** |
| REQ-051 Dashboard Haus + Hauptverbraucher | ✅ | `web/index.html`, Spec 04 | **T** `test_status_enthaelt_energieverteilung_und_phaseninfo`, `test_dashboard_wird_ausgeliefert` · **L** |
| REQ-052 Kennzahlen historisieren | 🔵 Snapshots ja, Kennzahlen gegen Baseline 2025 nein | `store/db.py`, `/api/v1/observation/summary` | **T** `test_snapshots_und_summary`, `test_summary_ohne_daten` — **Historie war bis v0.6.4 nach jedem Update weg** |
| REQ-053 Benachrichtigungen | 🔵 Geräteausfall wird protokolliert, kein Push | `core/loop.py` | **T** `test_lesefehler_steht_im_status_und_im_protokoll` |

## G — Sicherheit / Fallback

| ID | Umsetzung | Code | Nachweis |
|---|---|---|---|
| REQ-060 Fail-Safe, Geräte laufen autonom | ✅ E1/E2/E3/E5/E7 | `core/loop.py` | **T** `test_failsafe_e1_schaltet_ab`, `test_waermepumpe_ausfall_stoert_das_laden_nicht`, `test_read_only_failsafe_e1_stoppt_nichts` |
| REQ-061 manuelle Übersteuerung nicht zurückdrehen | 🔵 für die WP ja, Wallbox-Override fehlt | `heatpump.py` | **T** `test_bestaetigter_sollwert_wird_nicht_nachgeschrieben` — Override „bis Abstecken/24 h" (Spec §5) ist nicht implementiert |
| REQ-062 Entscheidungen geloggt | ✅ | `store/db.py`, `/api/v1/history` | **T** `test_snapshots_und_summary`, `test_lesefehler_steht_im_status_und_im_protokoll` · **L** |
| REQ-063 Grenzen zentral + vor jedem Befehl validiert | ✅ | `safety/guard.py` | **T** `test_strom_validierung_6_bis_16_a`, `test_batterie_reserve` |
| REQ-064 keine Schaltzyklen | ✅ | `charge_control.py`, `heatpump.py` | **T** `test_ww_boost_haelt_mindestlaufzeit_durch`, `test_ww_boost_schaltet_sich_nicht_selbst_ab`, `test_zu_schmales_band_fuehrt_nicht_zum_schaltzyklus`, `test_t2_phasenwechsel` |

## H — Konfiguration & Bedienung

| ID | Umsetzung | Code | Nachweis |
|---|---|---|---|
| REQ-070 Laderegeln frei verwaltbar | ✅ | `/api/v1/rules` (CRUD), Dashboard | **T** Regel-Logik in `test_rules.py`; **die API-Endpunkte selbst sind nicht getestet** |
| REQ-071 SoC-Reserve über die UI | ✅ | `/api/v1/config`, Dashboard | **T** Wirkung in `test_batterie_reserve`, `PUT /config` in `test_abgelehnte_konfiguration_wird_nicht_halb_geschrieben` |
| REQ-072 harte Grenzen über die UI | ✅ *(EV-Obergrenze seit v0.10.0)* | `config.py` (`hard_limit_*`), `safety/guard.py`, `api/app.py` | **T** `test_ww_komfortgrenze_hebt_rueckstellwert_an`, `test_ladelimit_ueber_der_harten_grenze_wird_abgelehnt`, `test_grenze_und_limit_gemeinsam_anheben`, `test_garantieladung_wird_auf_das_ladelimit_gedeckelt` |
| REQ-073 sofort wirksam **und persistent** | ✅ *(persistent erst seit v0.6.5, Ladelimit erst seit v0.10.0)* | `config.py`, `run.sh` | **T** `test_run_sh_setzt_das_persistente_datenverzeichnis`, `test_mode_put_persistiert_das_ladelimit` — bis v0.6.4 lag `config.json` im Container und war nach jedem Update weg, inklusive `read_only`; das Fahrzeug-Ladelimit stand bis v0.9.0 überhaupt nicht in der Config |
| REQ-074 eigenständige LAN-App | 🔵 HA-Dashboard erfüllt die LAN-Bedienung, die Android-App ist Gerüst | `web/index.html`, `app/` | **L** Dashboard; App nie gebaut |

---

## Verpackungs-Zusagen (kein Requirement, aber Voraussetzung für alle)

Die Wärmepumpe war zwei Wochen lang „fertig implementiert" und trotzdem nicht
angebunden — nicht wegen der Logik, sondern wegen der Add-on-Verpackung. Diese
Zusagen hält jetzt `test_addon_paket.py` (7 Tests):

| Zusage | Test | Warum |
|---|---|---|
| Start über `run.sh`, nicht direkt `python` | `test_start_geht_ueber_run_sh` | s6-overlay bereinigt sonst die Umgebung |
| `with-contenv` im Shebang | `test_run_sh_holt_die_container_umgebung` | ohne das: kein `SUPERVISOR_TOKEN`, keine `ENV` |
| Unix-Zeilenenden in `run.sh` | `test_run_sh_hat_unix_zeilenenden` | `\r` im Shebang bricht den Start |
| `/data` als Datenverzeichnis | `test_run_sh_setzt_das_persistente_datenverzeichnis` | sonst sind Token, Konfiguration und Messdaten nach jedem Update weg |
| Beide HA-API-Rechte | `test_addon_darf_die_ha_api_benutzen` | `homeassistant_api` + `hassio_api` |
| WP-Entities vorbelegt | `test_waermepumpen_entities_sind_vorbelegt` | leeres Feld heißt „WP aus" — darf kein Versehen sein |
| Versionen synchron | `test_versionen_laufen_synchron` | Dashboard und Supervisor sollen dasselbe melden |

Ergänzend zur Laufzeit: `GET /api/v1/diag/devices` (jeder Adapter aktiv gelesen),
`GET /api/v1/diag/umgebung` (Datenverzeichnis, Variablennamen) und `status.geraete`
(Lese-Gesundheit je Gerät, Ausfall/Rückkehr im Protokoll).

## Nächste Schritte, nach Nutzen sortiert

1. **REQ-041 verdrahten** — Forecast in `plane_garantieladung()`. Größte inhaltliche
   Lücke der Stufe 1 und eine der drei Neuerungen gegenüber EVCC.
2. **MyVaillant-Schreibweg klären** (Runde 3, Frage 3) — erster echter Boost am
   2026-07-26 lief fehlerfrei durch, ohne dass der Sollwert folgte. Vermutung:
   Betriebsart `Auto` blockt den Sollwert, es müsste vorher `set_operation_mode`.
   Das ändert Leos Heizungsprogramm → seine Entscheidung, kein Alleingang.
3. **REQ-052 Kennzahlen** — Autarkie und PV-Anteil gegen die Baseline 2025. Läuft
   jetzt auf persistenten Daten, also ab heute sinnvoll messbar.
4. **REQ-061 Wallbox-Override** — „bis Abstecken oder 24 h" fehlt komplett.
5. **REQ-008 EVCC deinstallieren** — erst nach 1./3., mit belegtem Vergleich.
6. **API-Tests für `/rules`** — REQ-070 hängt an Endpunkten, die kein Test
   anfasst. (`/config` ist seit v0.10.0 abgedeckt.)
7. **Realbetriebs-Nachweis für v0.9.0/v0.10.0** — die dynamische Entladegrenze und
   die Batterie-Freigabe sind vollständig getestet, aber noch nicht am Pi belegt.
   Vor der ersten Nutzung von „PV+Batterie": `soc_reserve_pct` setzen (§5.2).
