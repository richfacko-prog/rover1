#!/usr/bin/env python3
"""
Robot remote control: live camera video + arrow-key driving in a web browser.
Works on both rovers (Pi 4 "Rover 1" and Pi 3 "Rover 2"). Per-rover settings: ~/rover.json
(see rover_config.py).

Pages (open on your PC):
  http://<rover>.local:8000          this rover on its own
  http://<rover>.local:8000/fleet    SPLIT SCREEN: every rover side by side
                                     (W A S D drive the left one, arrow keys the right one)
  http://<rover>.local:8000/arena    GAMES: Laser Battle, Manhunt, Treasure Hunt (see ARENA.md)
                                     on two phones or one PC
  http://<rover>.local:8000/facecam  FACE CAM: takes a photo whenever it sees a face (see FACECAM.md)

Speed: Slow / Medium / Fast buttons, or keys 1 / 2 / 3 (7 / 8 / 9 for the right rover).
Turning always uses FULL power in every speed mode (4-wheel rovers need it to spin).
Camera tilt (if USE_TILT is on): R / F keys (Page Up / Page Down for the right rover).
Lights: L toggles the headlights, hold H for the horn (see lights.py for the wiring).

Safety:
- The robot stops on its own if it stops hearing from the browser
  (key released, tab closed, Wi-Fi drops).
- The distance sensor blocks driving FORWARD when something is closer than
  BLOCK_CM. Turning and reversing still work so you can get away.

Don't run robot.py or patrol.py at the same time (they use the motors and camera).
Normally this runs as the robot-drive service; stop it with: sudo systemctl stop robot-drive
"""

import io
import json
import socket
import socketserver
import threading
import time
from http import server
from urllib.parse import urlparse, parse_qs

from gpiozero import Motor, DigitalOutputDevice, DigitalInputDevice

from rover_config import CFG, motor_pins

try:
    import arena            # camera games: http://<rover>.local:8000/arena
except Exception as e:      # a problem in the games must never stop the driving
    arena = None
    print(f"Arena games not available ({e}). Driving still works.")

try:
    import facecam          # photo when it sees a face: http://<rover>.local:8000/facecam
except Exception as e:
    facecam = None
    print(f"Face Cam not available ({e}). Driving still works.")

try:
    from lights import lights, handle_post as lights_post   # headlights, taillights, horn
except Exception as e:
    lights = None
    print(f"Lights/horn not available ({e}). Driving still works.")

# ---------------------------------------------------------------------------
# SETTINGS (shared by both rovers; per-rover ones are in ~/rover.json)
# ---------------------------------------------------------------------------
SPEEDS = {"slow": 0.5, "medium": 0.75, "fast": 1.0}   # forward/backward power for each mode
START_SPEED = "fast"      # mode when the robot starts
TURN_SPEED = 1.0          # turning: always 100% power, whatever the mode
PORT = 8000
STOP_AFTER = 0.5          # seconds without a command before the robot stops
USE_SENSOR = True         # distance sensor guard on/off
BLOCK_CM = 20             # block forward driving when something is closer than this
TILT_STEP_US = 40         # how far one tilt key press moves the camera
# ---------------------------------------------------------------------------

LEFT_PINS, RIGHT_PINS = motor_pins(CFG)
left = Motor(forward=LEFT_PINS[0], backward=LEFT_PINS[1])
right = Motor(forward=RIGHT_PINS[0], backward=RIGHT_PINS[1])

state = {"cmd": "stop", "last": 0.0, "dist": None, "speed": START_SPEED,
         "tilt": CFG["TILT_CENTER_US"]}
state_lock = threading.Lock()


# ---------- distance sensor ----------
if USE_SENSOR:
    trig = DigitalOutputDevice(CFG["TRIG_GPIO"])
    echo = DigitalInputDevice(CFG["ECHO_GPIO"])


def ping():
    trig.on()
    time.sleep(0.00002)
    trig.off()
    t0 = time.time()
    while not echo.value:
        if time.time() - t0 > 0.03:
            return None
    rise = time.time()
    while echo.value:
        if time.time() - rise > 0.03:
            return 500.0
    return (time.time() - rise) * 34300 / 2


def sensor_loop():
    """Measure the distance ahead ~10 times a second; block forward if too close."""
    while True:
        r = [x for x in (ping(), ping(), ping()) if x is not None]
        d = sorted(r)[len(r) // 2] if r else None
        with state_lock:
            state["dist"] = d
            if state["cmd"] == "forward" and d is not None and d < BLOCK_CM:
                state["cmd"] = "stop"
                apply("stop")
        time.sleep(0.05)


def blocked():
    d = state["dist"]
    return USE_SENSOR and d is not None and d < BLOCK_CM


# ---------- camera tilt servo ----------
class Tilt:
    """SG90 on TILT_GPIO. Pulses stop shortly after each move so the servo doesn't buzz."""

    def __init__(self):
        self.h = None
        self.timer = None
        if not CFG["USE_TILT"]:
            return
        try:
            import lgpio
            self.lgpio = lgpio
            self.h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_output(self.h, CFG["TILT_GPIO"], 0)
            self.move(CFG["TILT_CENTER_US"])
        except Exception as e:
            print(f"Tilt servo not available ({e}), carrying on without it")
            self.h = None

    @property
    def ok(self):
        return self.h is not None

    def move(self, us):
        us = max(CFG["TILT_MIN_US"], min(CFG["TILT_MAX_US"], int(us)))
        state["tilt"] = us
        if not self.ok:
            return
        self.lgpio.tx_servo(self.h, CFG["TILT_GPIO"], us)
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(0.6, self.relax)
        self.timer.daemon = True
        self.timer.start()

    def relax(self):
        if self.ok:
            self.lgpio.tx_servo(self.h, CFG["TILT_GPIO"], 0)


# ---------- driving ----------
def apply(cmd):
    """Set both motors for a drive command."""
    speed = SPEEDS[state["speed"]]
    if cmd == "forward":
        left.forward(speed); right.forward(speed)
    elif cmd == "backward":
        left.backward(speed); right.backward(speed)
    elif cmd == "left":
        left.backward(TURN_SPEED); right.forward(TURN_SPEED)
    elif cmd == "right":
        left.forward(TURN_SPEED); right.backward(TURN_SPEED)
    else:
        left.stop(); right.stop()


def drive(cmd):
    with state_lock:
        state["last"] = time.monotonic()
        if cmd == "forward" and blocked():
            cmd = "stop"
        if cmd != state["cmd"]:
            state["cmd"] = cmd
            apply(cmd)


def set_speed(mode):
    with state_lock:
        state["speed"] = mode
        apply(state["cmd"])          # takes effect right away, even while moving


def set_tilt(how):
    with state_lock:
        us = {"up": state["tilt"] - TILT_STEP_US, "down": state["tilt"] + TILT_STEP_US,
              "center": CFG["TILT_CENTER_US"]}[how]
        tilt.move(us)


def watchdog():
    """Safety: stop the motors if commands stop arriving."""
    while True:
        time.sleep(0.1)
        with state_lock:
            if state["cmd"] != "stop" and time.monotonic() - state["last"] > STOP_AFTER:
                state["cmd"] = "stop"
                apply("stop")


class StreamingOutput(io.BufferedIOBase):
    """Holds the latest camera frame for the video stream."""

    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


# ---------------------------------------------------------------------------
# The web page. The same page is used for one rover ("/") and for the split
# screen ("/fleet"): it just gets a list of rover addresses.
# ---------------------------------------------------------------------------
PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  * { box-sizing:border-box; }
  [hidden] { display:none !important; }
  body { margin:0; background:#111; color:#eee; font-family:sans-serif; }
  header { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:8px 12px; }
  header h1 { font-size:18px; margin:0 8px 0 0; }
  header #list { background:#222; color:#eee; border:1px solid #444; border-radius:6px;
                 padding:6px 8px; font-size:14px; width:min(420px, 70vw); }
  header label { font-size:14px; color:#ccc; }
  header .arena { color:#ffc83d; font-weight:bold; text-decoration:none; font-size:15px; }
  .small { height:32px; font-size:14px; padding:0 12px; }
  #panes { display:flex; flex-wrap:wrap; justify-content:center; gap:12px; padding:0 8px 12px; }
  .pane { flex:1 1 420px; max-width:960px; display:flex; flex-direction:column; align-items:center;
          border:2px solid var(--c); border-radius:12px; padding:8px; }
  .pane.one { border:0; }
  .title { display:flex; align-items:center; gap:8px; width:100%; font-size:16px; }
  .dot { width:12px; height:12px; border-radius:50%; background:#666; }
  .dot.live { background:var(--c); }
  .keys { margin-left:auto; color:#999; font-size:12px; }
  .view { position:relative; width:100%; margin-top:6px; }
  .view img { width:100%; aspect-ratio:4/3; max-height:58vh; object-fit:contain; border-radius:8px; background:#000; display:block; }
  .view .off { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
               color:#888; font-size:15px; text-align:center; padding:12px; }
  .status { margin:6px; font-size:15px; color:#8f8; height:20px; }
  .dist { font-size:14px; color:#aaa; height:18px; }
  .dist.close { color:#f66; font-weight:bold; }
  .row { display:flex; gap:8px; margin:6px 0; flex-wrap:wrap; justify-content:center; }
  .pad { display:grid; grid-template-columns:repeat(3, 72px); gap:6px; margin:6px 0; }
  button { height:56px; font-size:24px; border:0; border-radius:10px;
           background:#333; color:#fff; touch-action:none; user-select:none; cursor:pointer; }
  button.on { background:var(--c); }
  .row button { height:40px; width:92px; font-size:15px; }
  .row button.sel { background:#d9822b; }
  .ctl { display:flex; align-items:center; justify-content:center; gap:16px; flex-wrap:wrap; }
  .ctl .row { flex-direction:column; }
  body.fleet .view img { max-height:52vh; }
  body.fleet .pad { grid-template-columns:repeat(3, 60px); }
  body.fleet .pad button { height:46px; font-size:20px; }
  body.fleet .row button { height:34px; width:84px; font-size:14px; }
  .hint { color:#999; font-size:13px; text-align:center; margin:4px 0 16px; }
</style></head>
<body>
<header>
  <h1>__TITLE__</h1>
  <a class="arena" href="/arena">&#127918; Arena games</a>
  <a class="arena" href="/facecam">&#128248; Face Cam</a>
  <span id="fleetbar" hidden>
    <input id="list" title="Rover addresses, left to right, separated by commas">
    <button class="small" id="apply">Apply</button>
    <label><input type="checkbox" id="link"> Drive all together</label>
  </span>
</header>
<div id="panes"></div>
<div class="hint" id="hint"></div>
<template id="tpl">
  <div class="pane">
    <div class="title"><span class="dot"></span><b class="name">...</b><span class="keys"></span></div>
    <div class="view"><img alt="camera"><div class="off">connecting...</div></div>
    <div class="status">stopped</div>
    <div class="dist"></div>
    <div class="ctl">
    <div class="row speeds">
      <button data-speed="slow">Slow</button><button data-speed="medium">Medium</button><button data-speed="fast">Fast</button>
    </div>
    <div class="pad">
      <span></span><button data-cmd="forward">&#9650;</button><span></span>
      <button data-cmd="left">&#9664;</button><button data-cmd="stop">&#9632;</button><button data-cmd="right">&#9654;</button>
      <span></span><button data-cmd="backward">&#9660;</button><span></span>
    </div>
    <div class="row extras" hidden>
      <button data-lights="1">Lights</button><button data-horn="1">Horn</button>
    </div>
    <div class="row tilt" hidden>
      <button data-tilt="up">Tilt &#8593;</button><button data-tilt="center">Level</button><button data-tilt="down">Tilt &#8595;</button>
    </div>
    </div>
  </div>
</template>
<script>
const FLEET_MODE = __FLEET_MODE__;
const DEFAULT_LIST = __DEFAULT_LIST__;

// ----- which rovers to show -----
function roverList() {
  if (!FLEET_MODE) return [""];                          // this rover only, same address
  const q = new URLSearchParams(location.search).get("r");
  let saved = null;
  try { saved = localStorage.getItem("rovers"); } catch (e) {}
  const txt = q || saved || DEFAULT_LIST.join(", ");
  return txt.split(",").map(s => s.trim()).filter(Boolean);
}
function baseUrl(host) {
  if (!host) return "";
  if (host.startsWith("http")) return host.replace(/\\/$/, "");
  return "http://" + host + (host.includes(":") ? "" : ":__PORT__");
}

// ----- one pane per rover -----
const panes = [];
function makePane(host, i, total) {
  const el = document.getElementById("tpl").content.firstElementChild.cloneNode(true);
  const p = { host, base: baseUrl(host), el, cmd: "stop", online: false, retry: 0,
              img: el.querySelector("img"), off: el.querySelector(".off") };
  el.style.setProperty("--c", "#555");
  if (total === 1) el.classList.add("one");
  el.querySelector(".name").textContent = host || location.hostname;
  el.querySelector(".keys").textContent = total === 1 ? "" :
      (i === 0 ? "W A S D · 1 2 3 · R F" : i === 1 ? "Arrows · 7 8 9 · PgUp PgDn" : "mouse only");
  p.send = c => fetch(p.base + "/drive/" + c, {method: "POST"}).catch(() => {});
  p.set = c => {
    if (c === p.cmd) return;
    p.cmd = c; p.send(c);
    el.querySelector(".status").textContent = c === "stop" ? "stopped" : c;
    el.querySelectorAll("button[data-cmd]").forEach(b =>
      b.classList.toggle("on", b.dataset.cmd === c && c !== "stop"));
  };
  p.showSpeed = m => el.querySelectorAll("button[data-speed]").forEach(b =>
      b.classList.toggle("sel", b.dataset.speed === m));
  p.speed = m => { p.showSpeed(m); fetch(p.base + "/speed/" + m, {method: "POST"}).catch(() => {}); };
  p.tilt = t => fetch(p.base + "/tilt/" + t, {method: "POST"}).catch(() => {});
  p.lights = () => fetch(p.base + "/lights/toggle", {method: "POST"}).catch(() => {});
  p.hornTimer = null;
  p.horn = on => {
    clearInterval(p.hornTimer); p.hornTimer = null;
    fetch(p.base + "/horn/" + (on ? "on" : "off"), {method: "POST"}).catch(() => {});
    if (on) p.hornTimer = setInterval(() => fetch(p.base + "/horn/on", {method: "POST"}).catch(() => {}), 150);
  };
  p.startStream = () => { p.img.src = p.base + "/stream.mjpg?t=" + Date.now(); };
  p.img.onload = () => { p.off.hidden = true; p.img.style.visibility = ""; };
  p.img.onerror = () => {
    p.off.hidden = false; p.img.style.visibility = "hidden";
    p.off.textContent = p.online ? "no camera picture (camera unplugged?)" : "can't reach " + (host || "the rover");
    clearTimeout(p.retry); p.retry = setTimeout(p.startStream, 3000);
  };
  el.querySelectorAll("button[data-cmd]").forEach(b => {
    b.addEventListener("pointerdown", e => { e.preventDefault(); p.set(b.dataset.cmd); });
    ["pointerup", "pointerleave", "pointercancel"].forEach(ev => b.addEventListener(ev, () => p.set("stop")));
  });
  el.querySelectorAll("button[data-speed]").forEach(b => b.addEventListener("click", () => p.speed(b.dataset.speed)));
  el.querySelectorAll("button[data-tilt]").forEach(b => b.addEventListener("click", () => p.tilt(b.dataset.tilt)));
  el.querySelector("button[data-lights]").addEventListener("click", () => p.lights());
  const hb = el.querySelector("button[data-horn]");
  hb.addEventListener("pointerdown", e => { e.preventDefault(); p.horn(true); });
  ["pointerup", "pointerleave", "pointercancel"].forEach(ev => hb.addEventListener(ev, () => p.horn(false)));
  document.getElementById("panes").appendChild(el);
  p.startStream();
  return p;
}

function poll(p) {
  fetch(p.base + "/status").then(r => r.json()).then(s => {
    if (!p.online) { p.online = true; if (!p.off.hidden) p.startStream(); }
    p.el.querySelector(".dot").classList.add("live");
    p.el.querySelector(".name").textContent = s.name;
    p.el.style.setProperty("--c", s.color);
    if (!FLEET_MODE) document.title = s.name;
    if (p.img.naturalWidth > 0) { p.off.hidden = true; p.img.style.visibility = ""; }
    p.showSpeed(s.speed);
    p.el.querySelector(".tilt").hidden = !s.tilt;
    p.el.querySelector(".extras").hidden = !s.lights;
    p.el.querySelector("button[data-lights]").classList.toggle("sel", !!s.headlights);
    const dist = p.el.querySelector(".dist");
    if (s.dist === null) { dist.textContent = s.sensor ? "sensor: no reading" : ""; dist.classList.remove("close"); return; }
    dist.textContent = "Distance ahead: " + Math.round(s.dist) + " cm" + (s.blocked ? "  (too close, forward blocked)" : "");
    dist.classList.toggle("close", s.blocked);
  }).catch(() => {
    p.online = false;
    p.el.querySelector(".dot").classList.remove("live");
    p.el.querySelector(".dist").textContent = "offline";
  });
}

// ----- keyboard: keyset 0 = WASD (left rover), keyset 1 = arrows (right rover) -----
const KEYSETS = [
  { drive: { w:"forward", a:"left", s:"backward", d:"right" },
    speed: { "1":"slow", "2":"medium", "3":"fast" }, tilt: { r:"up", f:"down" } },
  { drive: { ArrowUp:"forward", ArrowLeft:"left", ArrowDown:"backward", ArrowRight:"right" },
    speed: { "7":"slow", "8":"medium", "9":"fast" }, tilt: { PageUp:"up", PageDown:"down" } },
];
const held = [[], []];
function targets(k) {
  if (panes.length === 1 || document.getElementById("link").checked) return panes;
  return panes[k] ? [panes[k]] : [];
}
function keyName(e) { return e.key.length === 1 ? e.key.toLowerCase() : e.key; }
function update(k) { const c = held[k].length ? held[k][held[k].length - 1] : "stop"; targets(k).forEach(p => p.set(c)); }
function stopAll() { held.forEach(h => h.length = 0); panes.forEach(p => p.set("stop")); }

document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" && e.target.type !== "checkbox") return;
  const key = keyName(e);
  if (key === " ") { e.preventDefault(); stopAll(); return; }
  if (key === "l" && !e.repeat) { targets(0).forEach(p => p.lights()); return; }
  if (key === "h") { e.preventDefault(); if (!e.repeat) targets(0).forEach(p => p.horn(true)); return; }
  KEYSETS.forEach((ks, k) => {
    if (ks.drive[key]) {
      e.preventDefault();
      if (!held[k].includes(ks.drive[key])) held[k].push(ks.drive[key]);
      update(k);
    } else if (ks.speed[key] && !e.repeat) {
      targets(k).forEach(p => p.speed(ks.speed[key]));
    } else if (ks.tilt[key]) {
      e.preventDefault();
      targets(k).forEach(p => p.tilt(ks.tilt[key]));      // hold the key to keep tilting
    }
  });
});
document.addEventListener("keyup", e => {
  const key = keyName(e);
  if (key === "h") { targets(0).forEach(p => p.horn(false)); return; }
  KEYSETS.forEach((ks, k) => {
    const c = ks.drive[key];
    if (!c) return;
    const i = held[k].indexOf(c); if (i >= 0) held[k].splice(i, 1);
    update(k);
  });
});
window.addEventListener("blur", () => { stopAll(); panes.forEach(p => p.horn(false)); });
document.addEventListener("visibilitychange", () => { if (document.hidden) stopAll(); });

// keep sending the current command so the rover's safety stop doesn't kick in
setInterval(() => panes.forEach(p => { if (p.cmd !== "stop") p.send(p.cmd); }), 150);
setInterval(() => panes.forEach(poll), 300);

// ----- start -----
const list = roverList();
list.forEach((h, i) => panes.push(makePane(h, i, list.length)));
panes.forEach(poll);
const hint = document.getElementById("hint");
if (FLEET_MODE) {
  document.body.classList.add("fleet");
  document.getElementById("fleetbar").hidden = false;
  const box = document.getElementById("list");
  box.value = list.join(", ");
  document.getElementById("apply").onclick = () => {
    try { localStorage.setItem("rovers", box.value); } catch (e) {}
    location.search = "";
  };
  document.getElementById("link").addEventListener("change", e => { stopAll(); e.target.blur(); });
  hint.textContent = "Left rover: W A S D, speed 1 2 3, tilt R F  ·  Right rover: arrow keys, speed 7 8 9, tilt Page Up / Page Down  ·  Space stops everything  ·  let go to stop";
} else {
  hint.innerHTML = 'Arrow keys or W A S D to drive &middot; let go to stop &middot; 1 / 2 / 3 = slow / medium / fast &middot; L lights &middot; hold H horn &middot; <a href="/fleet" style="color:#8cf">split screen</a> &middot; <a href="/arena" style="color:#8cf">arena games</a>';
}
</script>
</body></html>
"""


def page(fleet):
    return (PAGE.replace("__TITLE__", "Rover Fleet" if fleet else "Robot Control")
                .replace("__FLEET_MODE__", "true" if fleet else "false")
                .replace("__DEFAULT_LIST__", json.dumps(CFG["FLEET"]))
                .replace("__PORT__", str(PORT)))


COMMANDS = {"forward", "backward", "left", "right", "stop"}
TILTS = {"up", "down", "center"}


class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the output quiet

    def end_headers(self):
        # lets the split-screen page (served by the other rover) talk to this one
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path == "/":
            self._send(200, "text/html", page(False).encode("utf-8"))
        elif path == "/fleet":
            self._send(200, "text/html", page(True).encode("utf-8"))
        elif path == "/status":
            with state_lock:
                info = {
                    "name": CFG["NAME"], "color": CFG["COLOR"],
                    "sensor": USE_SENSOR,
                    "dist": None if state["dist"] is None else round(state["dist"], 1),
                    "blocked": blocked(),
                    "speed": state["speed"], "cmd": state["cmd"],
                    "tilt": tilt.ok, "tilt_us": state["tilt"],
                    "camera": output is not None,
                }
            if lights:
                info.update(lights.state())
            if arena:
                info.update(arena.status_extra(url.query))   # markers the camera sees
            self._send(200, "application/json", json.dumps(info).encode())
        elif path == "/stream.mjpg":
            if output is None:
                self.send_error(503, "camera not working")
                return
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(b"Content-Length: %d\r\n\r\n" % len(frame))
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif arena and arena.handle_get(self, path, url.query):
            pass                                              # an arena page
        elif facecam and facecam.handle_get(self, path, url.query):
            pass                                              # a Face Cam page or photo
        else:
            self.send_error(404)

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _ok(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if arena and arena.handle_post(self, path):
            return                                            # a game request
        if facecam and facecam.handle_post(self, path):
            return                                            # a Face Cam button
        if lights and lights_post(self, path):
            return                                            # lights / horn
        parts = path.strip("/").split("/")
        if len(parts) != 2:
            self.send_error(404)
        elif parts[0] == "drive" and parts[1] in COMMANDS:
            drive(parts[1]); self._ok()
        elif parts[0] == "speed" and parts[1] in SPEEDS:
            set_speed(parts[1]); self._ok()
        elif parts[0] == "tilt" and parts[1] in TILTS:
            set_tilt(parts[1]); self._ok()
        else:
            self.send_error(404)


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_camera():
    """Start the camera. Returns (picam2, output), or (None, None) if there's no camera."""
    try:
        from libcamera import Transform
        from picamera2 import Picamera2
        from picamera2.encoders import MJPEGEncoder
        from picamera2.outputs import FileOutput
        cam = Picamera2()
        transform = Transform(hflip=1, vflip=1) if CFG["FLIP_CAMERA"] else Transform()
        cam.configure(cam.create_video_configuration(
            main={"size": tuple(CFG["VIDEO_SIZE"])}, transform=transform,
            controls={"FrameRate": CFG["VIDEO_FPS"]}))
        out = StreamingOutput()
        cam.start_recording(MJPEGEncoder(), FileOutput(out))
        return cam, out
    except Exception as e:
        print(f"Camera not working ({e}). Driving still works, but there's no video.")
        print("Check the ribbon cable, then run: rpicam-hello --list-cameras")
        return None, None


output = None
tilt = Tilt()

if __name__ == "__main__":
    picam2, output = start_camera()
    if arena:
        arena.attach(lambda: output.frame if output else None)
    if facecam:
        facecam.attach(lambda: output.frame if output else None)
    if lights:
        lights.attach(lambda: state["cmd"])

    threading.Thread(target=watchdog, daemon=True).start()
    if USE_SENSOR:
        threading.Thread(target=sensor_loop, daemon=True).start()

    host = socket.gethostname()
    try:
        httpd = StreamingServer(("", PORT), Handler)
        print(f"{CFG['NAME']} running - open http://{host}.local:{PORT} on your PC")
        print(f"Split screen (all rovers): http://{host}.local:{PORT}/fleet")
        print(f"Games (phones or one PC):  http://{host}.local:{PORT}/arena")
        print(f"Face Cam (photo on faces): http://{host}.local:{PORT}/facecam")
        print("(If that doesn't load, run 'hostname -I' on the Pi to get its address.)")
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        apply("stop")
        tilt.relax()
        if lights:
            lights.off()
        if picam2:
            picam2.stop_recording()
        print("\nStopped.")
