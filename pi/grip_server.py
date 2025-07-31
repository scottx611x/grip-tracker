#!/usr/bin/env python3
# grip_server.py  –  live serial reader + Flask UI (polling JSON feed)

import serial, threading, time, sys, os
from flask import Flask, render_template_string, request, redirect, jsonify
from influxdb_client import InfluxDBClient, Point


# ---------- serial port ---------------------------------------------------
try:
    SER = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
except serial.SerialException as e:
    sys.exit(f"Cannot open /dev/ttyUSB0: {e}")

# ---------- shared state --------------------------------------------------
latest_grip = 0.0
max_grip    = -1.0
current_user = "guest"

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


def write_max(user, value):
    p = Point("grip_max").tag("user", user).field("value", value)
    iclient.write_api().write("grip", "garage", p)

# ---------- Flask app -----------------------------------------------------
app = Flask(__name__)

HTML_PAGE = r"""
<!doctype html>
<title>Grip Logger</title>
<style>
 body{font-family:sans-serif;max-width:28rem;margin:2rem auto;}
 h1{margin-bottom:.3rem;}
 .value{font-size:2.4rem;margin:.2rem 0;}
 label{display:block;margin-top:1rem;}
 button{padding:.4rem 1.2rem;margin-top:.6rem;}
</style>

<h1>Current user: <span id="user">{{ user }}</span></h1>

<div>Grip&nbsp;force: <span class=value id="grip">0.00</span> lbs</div>
<div>Session&nbsp;max: <span class=value id="max" >0.00</span> lbs</div>

<form method=post>
  <label>Your name:
     <input name=name value="{{ user }}" autocomplete=off>
  </label>
  <button name=action value=setname>Set Name</button>
  <button name=action value=savemax>Save&nbsp;Max</button>
</form>

{% if saved %}
  <p style="color:green;">Saved {{ m }} lbs for {{ user }} ✓</p>
{% endif %}

<script>
async function poll(){
  try{
    const r = await fetch("/data");
    if(r.ok){
      const j = await r.json();
      document.getElementById("grip").textContent = j.grip.toFixed(2);
      document.getElementById("max" ).textContent = j.max .toFixed(2);
    }
  }catch(e){ /* network glitch – ignore */ }
  setTimeout(poll, 200);      /* ~5 Hz */
}
window.onload = poll;
</script>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    global current_user
    saved = False
    if request.method == "POST":
        action = request.form.get("action")
        if action == "setname":
            current_user = request.form["name"].strip() or "guest"
        elif action == "savemax":
            write_max(current_user, max_grip)
        return redirect("/")         # avoid form-resubmission on reload
    return render_template_string(HTML_PAGE,
                                  user=current_user,
                                  saved=saved,
                                  m=f"{max_grip:.2f}")

@app.route("/data")
def data():
    """Return latest numbers as JSON for the polling JS."""
    return jsonify(grip=latest_grip, max=max_grip)

# ---------- run -----------------------------------------------------------
if __name__ == "__main__":
    print("Serving on http://0.0.0.0:80  (Ctrl-C to quit)")
    app.run(host="0.0.0.0", port=80)