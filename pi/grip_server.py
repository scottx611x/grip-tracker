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
session_max = 0.0            # highest value seen in session (either hand)
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
<title>Grip Logger</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
<style>
:root {--accent:#ff7a18;--bg1:#1c1c1e;--bg2:#2b2b2e}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Inter,system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;justify-content:center;align-items:center;background:linear-gradient(145deg,var(--bg1),var(--bg2));color:#fff}
.card{background:#0006;border:1px solid #ffffff22;border-radius:14px;padding:1.4rem 2rem;width:90vw;max-width:20rem;text-align:center;backdrop-filter:blur(6px)}
h1{font-size:1.8rem;font-weight:700;margin-bottom:.2rem}
.value{font-size:2.6rem;font-weight:700;margin:.3rem 0}
form{margin-top:1.1rem;display:flex;flex-wrap:wrap;gap:.5rem;justify-content:center}
input,select{padding:.4rem .6rem;border-radius:6px;border:1px solid #666;background:#1e1e20;color:#fff}
button{background:var(--accent);border:none;border-radius:6px;padding:.45rem 1.1rem;font-weight:700;cursor:pointer;color:#000}
.flame-wrap{margin:.8rem auto 0;height:120px;width:90px;position:relative}
.flame{position:absolute;left:50%;bottom:0;transform:translateX(-50%) rotate(45deg);width:40px;height:40px;background:var(--accent);border-radius:0 50% 50% 50%;animation:flicker .3s infinite alternate;filter:drop-shadow(0 0 8px #ffae40) drop-shadow(0 0 14px #ffae40)}
@keyframes flicker{from{transform:translateX(-50%) rotate(45deg) scale(1)}to{transform:translateX(-50%) rotate(45deg) scale(1.08)}}
</style></head><body>

<div class="card">
  <h1 id=user>{{ user }} ({{ side|capitalize }})</h1>

  <div>Grip&nbsp;force</div><div class=value id=grip>0.00&nbsp;lbs</div>
  <div>Session&nbsp;max</div><div class=value id=max>0.00&nbsp;lbs</div>

  <div class="flame-wrap"><div class="flame" id=flame></div></div>

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

<script>
const spanGrip=document.getElementById("grip");
const spanMax =document.getElementById("max");
const flame   =document.getElementById("flame");

async function poll(){
  try{
    const r=await fetch("/data");if(!r.ok)throw Error(r.status);
    const j=await r.json();
    spanGrip.textContent=j.grip.toFixed(2)+" lbs";
    spanMax .textContent=j.max .toFixed(2)+" lbs";
    const pct=j.max?Math.min(j.grip/j.max,1):0;
    flame.style.transform=`translateX(-50%) rotate(45deg) scale(${0.2+pct*0.8})`;
  }catch(e){}
  setTimeout(poll,200);
}
document.addEventListener("DOMContentLoaded",poll);
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