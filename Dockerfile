# BUILD_FROM wird vom HA-Supervisor aus build.yaml je Architektur gesetzt
# (Leos HA = Raspberry Pi 5 / aarch64). Default nur für manuelle Builds.
# Build-Kontext ist die Repo-Wurzel (Add-on-Manifest liegt hier), daher ist backend/ erreichbar.
ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21
FROM ${BUILD_FROM}

WORKDIR /app
COPY backend/ /app/
RUN pip install --no-cache-dir .[devices]

ENV LEO_EMS_DATA_DIR=/data

CMD ["python", "-m", "leo_ems.main"]
