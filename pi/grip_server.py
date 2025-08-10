#!/usr/bin/env python3
# grip_server.py  –  live serial reader + Flask UI (polling JSON feed)
import os

import serial, threading, time, sys
from flask import Flask, render_template, request, redirect, jsonify
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor

trace.set_tracer_provider(
    TracerProvider(
        resource=Resource.create(
            {
                "service.name": "grip-web",
                "service.version": "1.0.0",
            }
        )
    )
)
span_processor = BatchSpanProcessor(OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    insecure=True
))
trace.get_tracer_provider().add_span_processor(span_processor)


# ---------- serial port ---------------------------------------------------
try:
    SER = serial.Serial('/dev/ttyUSB0', 9600, timeout=3)
except serial.SerialException as e:
    sys.exit(f"Cannot open /dev/ttyUSB0: {e}")

# ---------- shared state --------------------------------------------------
latest_grip = 0.0
max_grip = 0.0            # highest value seen in session (either hand)
current_user = "guest"
current_side = "right"

# ---------- background thread --------------------------------------------
def serial_reader():
    """Read lines of the form 'CURRENT@MAX\n' from NodeMCU."""
    global latest_grip, max_grip
    buf = b''
    while True:
        if SER.in_waiting:
            buf += SER.read(SER.in_waiting)
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                try:
                    data = line.decode().strip()
                    if "@" not in data:
                        continue
                    cur, m = data.split("@")
                    latest_grip = float(cur)
                    max_grip    = float(m)
                except ValueError:
                    continue
        time.sleep(0.02)          # 20 ms

def reset_nodemcu():
    """Toggle DTR to reset the ESP8266 on the NodeMCU board."""
    SER.dtr = False          # drive DTR low  (EN pulled low) – reset asserted
    time.sleep(0.1)          # ≥ 100 ms is safe
    SER.reset_input_buffer() # discard any old bytes
    SER.dtr = True           # release reset – board reboots

threading.Thread(target=serial_reader, daemon=True).start()

# ---------- Influx --------------------------------------------------------
iclient = InfluxDBClient(
            url="http://influxdb:8086",
            token=os.environ["INFLUX_TOKEN"],
            org="grip")
_influx_write_api = iclient.write_api(write_options=SYNCHRONOUS)

def write_max(user, side, value):
    p = (Point("grip_max")
         .tag("user", user)
         .tag("side", side)
         .field("value", value))
    result = _influx_write_api.write(bucket="grip", record=p)
    print(result)

# ---------- Flask app -----------------------------------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
FlaskInstrumentor().instrument_app(app)

@app.route("/", methods=["GET","POST"])
def index():
    global current_user, current_side
    if request.method == "POST":
        action = request.form.get("action")
        if action == "savemax":
            write_max(current_user, current_side, max_grip)
        return redirect("/")
    return render_template("index.html", user=current_user, side=current_side)

@app.route("/data")
def data():
    """Return latest numbers as JSON for the polling JS."""
    return jsonify(grip=latest_grip, max=max_grip)

@app.route("/meta", methods=["POST"])
def meta():
    global current_user, current_side, latest_grip, max_grip
    j    = request.get_json(silent=True) or {}
    name = (j.get("name") or "guest").strip()
    side = j.get("side", "right")

    if side != current_side:
        reset_nodemcu()
        latest_grip  = 0.0
        max_grip  = 0.0

    current_user, current_side = name, side
    return ("", 204)

@app.route("/reset", methods=["POST"])
def reset_board():
    reset_nodemcu()            # pulses DTR as before
    global latest_grip, max_grip
    latest_grip = 0.0
    max_grip = 0.0
    return ("", 204)

@app.route("/savemax", methods=["POST"])
def save_max():
    j     = request.get_json(force=True)
    user  = j.get("name","guest")
    side  = j.get("side","right")
    value = float(j["value"])
    write_max(user, side, value)
    return ("",204)

