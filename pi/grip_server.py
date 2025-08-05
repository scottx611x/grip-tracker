#!/usr/bin/env python3
# grip_server.py  –  live serial reader + Flask UI (polling JSON feed)
import os

import serial, threading, time, sys
from flask import Flask, render_template_string, request, redirect, jsonify
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
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
    """Read lines of the form 'CURRENT@MAX\\n' from NodeMCU."""
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
app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

HTML = r"""
<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grip Furnace</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--bg1:#0d0d11;--bg2:#1d1d24;font-family:Inter,system-ui,sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{
  min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
  background:linear-gradient(145deg,var(--bg1),var(--bg2));color:#fff;overflow:hidden}
.card{
  backdrop-filter:blur(6px);background:#0007;padding:1.4rem 2.1rem;
  border-radius:14px;border:1px solid #ffffff22;width:90vw;max-width:20rem;text-align:center;z-index:10}
h1{font-size:1.8rem;font-weight:700;margin-bottom:.3rem}
.value{font-size:2.6rem;font-weight:700;margin:.35rem 0}
form{margin-top:1.1rem;display:flex;flex-wrap:wrap;gap:.5rem;justify-content:center}
input,select{padding:.45rem .7rem;border-radius:6px;border:1px solid #666;background:#1e1e20;color:#fff}
button{background:#f80;border:none;border-radius:6px;padding:.5rem 1rem;font-weight:700;cursor:pointer;color:#000}
/* canvas fills bottom */
#fireCanvas{
  position:fixed;z-index:-1;
  left:0;top:0;
  width:100vw;height:100vh;
  image-rendering:pixelated;
  pointer-events:none;opacity:.9}
</style>
</head><body>

<canvas id="fireCanvas"></canvas>

<div class="card">
  <h1 id=user>{{ user }} ({{ side|capitalize }})</h1>

  <div>Grip&nbsp;force</div><div class=value id=grip>0.00&nbsp;lbs</div>
  <div>Session&nbsp;max</div><div class=value id=max>0.00&nbsp;lbs</div>

  <form id="metaForm" autocomplete="off">
      <input  id="nameInput"  name="name" value="{{ user }}" placeholder="Your name">
      <select id="sideSelect" name="side">
         <option value="right" {% if side=='right' %}selected{% endif %}>Right</option>
         <option value="left"  {% if side=='left'  %}selected{% endif %}>Left</option>
      </select>
      <button id="saveBtn">Save&nbsp;Max</button>
      <button id="resetBtn" type="button" style="background:#444;color:#fff">Clear</button>  </form>
</div>

<!-- ----------  PIXEL FIRE ENGINE  (adapted from leonardosposina) --------- -->
<script>
/* basic parameters */
const fireWidth  = 90,    /* logical pixels   */
      fireHeight = 40,
      HARD_GRIP  = 150;   /* lbs that equals full intensity */

const firePixels = new Array(fireWidth * fireHeight).fill(0);
const palette =["070707","1f0707","2f0f07","470f07","571707","671f07","771f07",
"8f2707","9f2f07","af3f07","bf4707","c74707","df4f07","df5707","df5707","d75f07",
"d7670f","cf6f0f","cf770f","cf7f0f","cf8717","c78717","c78f17","c7971f","bf9f1f",
"bf9f1f","bfa727","bfa727","bfa727","c7af2f","c7af2f","c7b72f","c7b737","cfbf37",
"cfbf37","cfbf37","d7c747","d7c747","d7cf4f","d7cf4f","dfd75f","dfd75f","dfdf6f",
"efef9f","ffffff"].map(h=>"#"+h);

const canvas = document.getElementById("fireCanvas");
canvas.width  = fireWidth;
canvas.height = fireHeight;
const ctx = canvas.getContext("2d");

function index(x,y){return y*fireWidth+x}

/* initialize fire source (bottom row) at low intensity */
function setFireSource(intensity){
  for(let x=0;x<fireWidth;x++){
    firePixels[index(x,fireHeight-1)] = intensity;
  }
}

function updateFire(){
  /* iterate from row 0 up to next-to-last row (fireHeight-2) */
  for (let y = 0; y < fireHeight - 1; y++){
      for (let x = 0; x < fireWidth; x++){
          const src   = index(x, y);
          const below = src + fireWidth;
          const decay = Math.floor(Math.random() * 3);
          const newInt = Math.max(firePixels[below] - decay, 0);
          const dst   = src - decay + 1;
          firePixels[(dst < firePixels.length) ? dst : src] = newInt;
      }
  }
}

function renderFire(){
  const img = ctx.getImageData(0,0,fireWidth,fireHeight);
  for(let i=0;i<firePixels.length;i++){
    const color = palette[firePixels[i]];
    const r=parseInt(color.substr(1,2),16),
          g=parseInt(color.substr(3,2),16),
          b=parseInt(color.substr(5,2),16);
    img.data[i*4+0]=r;
    img.data[i*4+1]=g;
    img.data[i*4+2]=b;
    img.data[i*4+3]=255;
  }
  ctx.putImageData(img,0,0);
}

/* game loop */
function fireLoop(){
  updateFire();
  renderFire();
  requestAnimationFrame(fireLoop);
}
fireLoop();

/* ----------  live grip polling & intensity mapping  ---------- */
let grip=0,max=0;
async function poll(){
  try{
    const r=await fetch("/data");if(r.ok){
      const j=await r.json();grip=j.grip;max=j.max;
      document.getElementById("grip").textContent=grip.toFixed(2)+" lbs";
      document.getElementById("max" ).textContent=max .toFixed(2)+" lbs";
      /* intensity: map 0..HARD_GRIP to palette index 0..42 */
      const pct = Math.min(grip/HARD_GRIP,1);
      const intensity = Math.round(pct * (palette.length-1));
      setFireSource(intensity);
    }
  }catch(e){}
  setTimeout(poll,200);
}
poll();
</script>

<script>
/* ------------ live meta updates ----------------- */
const nameInput  = document.getElementById("nameInput");
const sideSelect = document.getElementById("sideSelect");
const hUser      = document.getElementById("user");

function sendMeta(){
  const name = nameInput.value.trim() || "guest";
  const side = sideSelect.value;
  /* optimistic UI: update title immediately */
  hUser.textContent = `${name} (${side.charAt(0).toUpperCase()+side.slice(1)})`;

  fetch("/meta",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ name, side })
  });
}
/* 'input' fires on every keystroke, 'change' on dropdown click */
nameInput.addEventListener("input" , sendMeta);
sideSelect.addEventListener("change", sendMeta);


const saveBtn   = document.getElementById("saveBtn");
const gripSpan  = document.getElementById("max");

saveBtn.addEventListener("click", () =>{
  fetch("/savemax",{
    method : "POST",
    headers: {"Content-Type":"application/json"},
    body   : JSON.stringify({
      value : parseFloat(gripSpan.textContent),   //  e.g. 137.2
      name  : document.getElementById("nameInput").value.trim() || "guest",
      side  : document.getElementById("sideSelect").value
    })
  }).then(r => r.ok ? alert("Saved!") : alert("Save failed"));
});


/* ----- hard-reset NodeMCU & zero counters ----- */
document.getElementById("resetBtn").addEventListener("click", () =>{
  fetch("/reset", {method:"POST"}).then(()=>{
    /* reset UI immediately */
    document.getElementById("grip").textContent = "0.00 lbs";
    document.getElementById("max").textContent  = "0.00 lbs";
  });
});
</script>

</body></html>
"""

@app.route("/", methods=["GET","POST"])
def index():
    global current_user, current_side
    if request.method == "POST":
        action = request.form["action"]
        if action == "savemax":
            write_max(current_user, current_side, max_grip)
        return redirect("/")
    return render_template_string(HTML, user=current_user, side=current_side)

@app.route("/data")
def data():
    """Return latest numbers as JSON for the polling JS."""
    return jsonify(grip=latest_grip, max=max_grip)

@app.route("/meta", methods=["POST"])
def meta():
    global current_user, current_side, latest_grip, session_max
    j    = request.get_json(silent=True) or {}
    name = (j.get("name") or "guest").strip()
    side = j.get("side", "right")

    if side != current_side:
        reset_nodemcu()
        latest_grip  = 0.0
        session_max  = 0.0

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

# ---------- run -----------------------------------------------------------
if __name__ == "__main__":
    print("Serving on http://0.0.0.0:80  (Ctrl-C to quit)")
    app.run(host="0.0.0.0", port=80)