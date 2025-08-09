FROM python:3.11-alpine

RUN apk add --no-cache gcc musl-dev linux-headers && \
    pip install --no-cache-dir flask pyserial influxdb-client \
     opentelemetry-sdk opentelemetry-exporter-otlp opentelemetry-instrumentation-flask

WORKDIR /app
COPY grip_server.py .

ENV PYTHONUNBUFFERED=1
CMD ["python", "grip_server.py"]