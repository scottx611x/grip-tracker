#!/usr/bin/env python3
# grip_server.py  –  live serial reader + Flask UI (polling JSON feed)

import serial, threading, time, sys
from flask import Flask, render_template_string, request, redirect, jsonify
from influxdb_client import InfluxDBClient, Point


# ---------- serial port ---------------------------------------------------
try:
    SER = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
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

threading.Thread(target=serial_reader, daemon=True).start()

# ---------- Influx --------------------------------------------------------
iclient = InfluxDBClient(
            url="influxdb:8086",
            token="",
            org="garage")


def write_max(user, side, value):
    p = (Point("grip_max")
         .tag("user", user)
         .tag("side", side)
         .field("value", value))
    iclient.write_api().write("grip", "garage", p)

# ---------- Flask app -----------------------------------------------------
app = Flask(__name__)

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
  position:fixed;bottom:0;left:50%;transform:translateX(-50%);
  image-rendering:pixelated;
  width:100vw;height:auto;max-height:45vh;pointer-events:none;opacity:.9}
</style>
</head><body>

<canvas id="fireCanvas"></canvas>

<div class="card">
  <h1 id=user>{{ user }} ({{ side|capitalize }})</h1>

  <div>Grip&nbsp;force</div><div class=value id=grip>0.00&nbsp;lbs</div>
  <div>Session&nbsp;max</div><div class=value id=max>0.00&nbsp;lbs</div>

  <form method=post>
    <input name=name value="{{ user }}" placeholder="Your name">
    <select name=side>
       <option value=right {% if side=='right' %}selected{% endif %}>Right</option>
       <option value=left  {% if side=='left'  %}selected{% endif %}>Left</option>
    </select>
    <button name=action value=setmeta>Set</button>
    <button name=action value=savemax>Save&nbsp;Max</button>
  </form>
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
  for(let y=1;y<fireHeight;y++){
    for(let x=0;x<fireWidth;x++){
      const src = index(x,y);
      const decay = Math.floor(Math.random()*3);
      const below = src + fireWidth;
      const newInt = Math.max(firePixels[below]-decay,0);
      const dst = src - decay + 1;
      firePixels[(dst<firePixels.length)?dst:src] = newInt;
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
</body></html>
"""

@app.route("/", methods=["GET","POST"])
def index():
    global current_user, current_side
    if request.method=="POST":
        if request.form["action"]=="setmeta":
            current_user=request.form["name"].strip() or "guest"
            current_side=request.form["side"]
        elif request.form["action"]=="savemax":
            write_max(current_user, current_side, request.form["value"])
        return redirect("/")
    return render_template_string(HTML, user=current_user, side=current_side)

@app.route("/data")
def data():
    """Return latest numbers as JSON for the polling JS."""
    return jsonify(grip=latest_grip, max=max_grip)

# ---------- run -----------------------------------------------------------
if __name__ == "__main__":
    print("Serving on http://0.0.0.0:80  (Ctrl-C to quit)")
    app.run(host="0.0.0.0", port=80)