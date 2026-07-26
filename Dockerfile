# BUILD_FROM wird vom HA-Supervisor aus build.yaml je Architektur gesetzt
# (Leos HA = Raspberry Pi 5 / aarch64). Default nur für manuelle Builds.
# Build-Kontext ist die Repo-Wurzel (Add-on-Manifest liegt hier), daher ist backend/ erreichbar.
ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21
FROM ${BUILD_FROM}

WORKDIR /app
COPY backend/ /app/
RUN pip install --no-cache-dir .[devices]

ENV LEO_EMS_DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

# Start über run.sh statt direkt über python: s6-overlay (in den HA-Basis-Images)
# führt das CMD mit bereinigter Umgebung aus, deshalb muss `with-contenv` davor —
# sonst fehlen dem Prozess die ENV-Zeilen oben UND der SUPERVISOR_TOKEN. Die
# Begründung im Detail steht in run.sh (Fehlerbild bis v0.6.4).
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
