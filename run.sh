#!/usr/bin/with-contenv bashio
# Startskript des Add-ons — der Umweg über with-contenv ist keine Kosmetik.
#
# Die HA-Basis-Images starten über s6-overlay, und s6 führt das CMD mit einer
# *bereinigten* Umgebung aus: ohne `with-contenv` sieht der Prozess weder die
# ENV-Zeilen aus dem Dockerfile noch die Variablen, die der Supervisor setzt.
# Genau das war bis v0.6.4 der Fall (nachgewiesen über /api/v1/diag/umgebung:
# die Umgebung enthielt nur PATH, PWD, OLDPWD, SHLVL) — mit zwei Folgen:
#
#   1. Kein SUPERVISOR_TOKEN → die Wärmepumpe bekam auf jedem Zugangsweg zur
#      HA-API ein HTTP 401 und galt dauerhaft als "nicht verbunden".
#   2. Kein LEO_EMS_DATA_DIR → Daten landeten unter /app/data *im Container*
#      statt im persistenten /data. Bei jedem Add-on-Update waren damit
#      API-Token, Regel-Konfiguration (auch der Schalter read_only) und die
#      Beobachtungs-Datenbank weg.
#
# Der Default steht hier zusätzlich explizit: das Datenverzeichnis ist zu
# wichtig, um von einer Dockerfile-Zeile abzuhängen.
export LEO_EMS_DATA_DIR="${LEO_EMS_DATA_DIR:-/data}"
export PYTHONUNBUFFERED=1

bashio::log.info "Leo-EMS startet — Datenverzeichnis ${LEO_EMS_DATA_DIR}"
if bashio::var.has_value "${SUPERVISOR_TOKEN:-}"; then
  bashio::log.info "Supervisor-Token vorhanden (Zugang zur HA-API für die Wärmepumpe)"
else
  bashio::log.warning "Kein SUPERVISOR_TOKEN — die Wärmepumpe kann Home Assistant nicht lesen"
fi

exec python -m leo_ems.main
