FROM python:3.11-alpine

RUN apk add --no-cache gcc musl-dev linux-headers libffi-dev && \
    pip install --no-cache-dir \
      flask==3.0.3 \
      pyserial==3.5 \
      influxdb-client==1.48.0 \
      opentelemetry-sdk==1.25.0 \
      opentelemetry-exporter-otlp==1.25.0 \
      opentelemetry-instrumentation-flask==0.46b0 \
      python-logging-loki==0.3.1 \
      gunicorn==21.2.0 \
      gevent==24.2.1

WORKDIR /app
COPY grip_server.py .
COPY templates ./templates
COPY static ./static

ENV PYTHONUNBUFFERED=1
CMD python grip_server.py