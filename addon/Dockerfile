ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.20
FROM ${BUILD_FROM}

WORKDIR /app
COPY backend/ /app/
RUN pip install --no-cache-dir .[devices]

ENV LEO_EMS_DATA_DIR=/data

CMD ["python", "-m", "leo_ems.main"]
