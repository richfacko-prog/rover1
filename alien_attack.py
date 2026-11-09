"""
ALIEN ATTACK - one file, paste into Thonny and press Run.

Aliens invade the room! They appear on the rover's live camera, standing at real spots in the room.
The camera is fixed, so you AIM BY TURNING THE ROVER: when you turn, the aliens slide across the
screen like real things would. Get one in the crosshair and blast it before it gets too close.

Open the game on your PC or phone (same Wi-Fi):   http://richardfacko.local:8000
                                       or:        http://192.168.2.159:8000

Controls on a PC:  arrows / W A S D drive and turn,  Q / E small aiming turns,
                   Space (or click the picture) fires.
On a phone:        D-pad on the left, FIRE and the small aim buttons on the right.

Before running: stop any other program that uses the camera or motors (Face Cam, robot_drive.py).
To stop: press the red Stop button in Thonny.
OpenCV makes the aiming follow the camera exactly. Without it the game guesses from the motors.
To install it, run once in the Terminal:   sudo apt install -y python3-opencv
"""

import io
import json
import os
import socket
import socketserver
import threading
import time
from http import server
from urllib.parse import urlparse

PORT = 8000
FLIP_CAMERA = False          # True if the picture is upside down

# ---- driving (same wiring as the rover: L298N IN1..IN4 on pins 11, 12, 15, 16) ----
LEFT_PINS = (17, 18)         # (forward, backward) GPIO numbers
RIGHT_PINS = (23, 22)        # right side is reversed on this rover
SPEEDS = {"slow": 0.5, "medium": 0.75, "fast": 1.0}
TURN_SPEED = 1.0             # 4-wheel rovers need full power to spin
NUDGE_S = 0.07               # Q / E: a short turn for fine aiming (make it bigger if a tap barely moves it)
STOP_AFTER = 0.5             # stop if no command arrives for this long (safety)
USE_SENSOR = True            # distance sensor: blocks driving forward when too close
TRIG_GPIO, ECHO_GPIO = 5, 6  # pins 29 and 31
BLOCK_CM = 20

# ---- aiming ----
TURN_RATE_GUESS = 1.0        # screen widths per second when spinning (only used without OpenCV;
                             # with OpenCV it's measured from the camera)

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    print("OpenCV is not installed: the game will guess your aim from the motors instead.")
    print("For exact aiming, run in the Terminal:  sudo apt install -y python3-opencv")


# ---------------------------------------------------------------------------
# camera
# ---------------------------------------------------------------------------
class StreamingOutput(io.BufferedIOBase):
    """Holds the latest camera frame."""

    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


def start_camera():
    try:
        from libcamera import Transform
        from picamera2 import Picamera2
        from picamera2.encoders import MJPEGEncoder
        from picamera2.outputs import FileOutput
        cam = Picamera2()
        transform = Transform(hflip=1, vflip=1) if FLIP_CAMERA else Transform()
        cam.configure(cam.create_video_configuration(main={"size": (640, 480)}, transform=transform,
                                                     controls={"FrameRate": 24}))
        out = StreamingOutput()
        cam.start_recording(MJPEGEncoder(), FileOutput(out))
        return cam, out
    except Exception as e:
        print(f"Camera not working: {e}")
        print("Is another program using the camera? Stop it (or reboot), then press Run again.")
        print("Check the camera: rpicam-hello --list-cameras")
        return None, None


# ---------------------------------------------------------------------------
# driving
# ---------------------------------------------------------------------------
class Drive:
    def __init__(self):
        self.lock = threading.Lock()
        self.cmd, self.last, self.moved, self.token = "stop", 0.0, 0.0, 0
        self.speed, self.dist, self.ok, self.sensor = "fast", None, False, False
        try:
            from gpiozero import Motor, DigitalOutputDevice, DigitalInputDevice
            self.left = Motor(forward=LEFT_PINS[0], backward=LEFT_PINS[1])
            self.right = Motor(forward=RIGHT_PINS[0], backward=RIGHT_PINS[1])
            self.ok = True
        except Exception as e:
            print(f"Motors not available ({e}). The game still runs, but the rover can't move.")
            print("Is another program using the motors? Stop it (or reboot) and press Run again.")
            return
        if USE_SENSOR:
            try:
                self.trig = DigitalOutputDevice(TRIG_GPIO)
                self.echo = DigitalInputDevice(ECHO_GPIO)
                self.sensor = True
                threading.Thread(target=self.sensor_loop, daemon=True).start()
            except Exception as e:
                print(f"Distance sensor not available ({e}). Driving works without it.")
        threading.Thread(target=self.watchdog, daemon=True).start()

    def ping(self):
        self.trig.on(); time.sleep(0.00002); self.trig.off()
        t0 = time.time()
        while not self.echo.value:
            if time.time() - t0 > 0.03:
                return None
        rise = time.time()
        while self.echo.value:
            if time.time() - rise > 0.03:
                return 500.0
        return (time.time() - rise) * 34300 / 2

    def sensor_loop(self):
        while True:
            r = [x for x in (self.ping(), self.ping(), self.ping()) if x is not None]
            d = sorted(r)[len(r) // 2] if r else None
            with self.lock:
                self.dist = d
                if self.cmd == "forward" and self.blocked():
                    self.cmd = "stop"
                    self.apply("stop")
            time.sleep(0.05)

    def blocked(self):
        return self.sensor and self.dist is not None and self.dist < BLOCK_CM

    def apply(self, cmd):
        sp = SPEEDS[self.speed]
        if cmd == "forward":
            self.left.forward(sp); self.right.forward(sp)
        elif cmd == "backward":
            self.left.backward(sp); self.right.backward(sp)
        elif cmd == "left":
            self.left.backward(TURN_SPEED); self.right.forward(TURN_SPEED)
        elif cmd == "right":
            self.left.forward(TURN_SPEED); self.right.backward(TURN_SPEED)
        else:
            self.left.stop(); self.right.stop()

    def go(self, cmd):
        if not self.ok:
            return
        with self.lock:
            self.last = time.monotonic()
            if cmd == "forward" and self.blocked():
                cmd = "stop"
            if cmd != "stop":
                self.moved = self.last
            if cmd != self.cmd:
                self.token += 1
                self.cmd = cmd
                self.apply(cmd)

    def nudge(self, direction):
        """A short turn for fine aiming."""
        if not self.ok:
            return
        with self.lock:
            self.token += 1
            tok = self.token
            self.cmd = direction
            self.last = self.moved = time.monotonic()
            self.apply(direction)

        def end():
            with self.lock:
                if self.token == tok:
                    self.cmd = "stop"
                    self.apply("stop")
                    self.moved = time.monotonic()
        threading.Timer(NUDGE_S, end).start()

    def set_speed(self, mode):
        if not self.ok:
            return
        with self.lock:
            self.speed = mode
            self.apply(self.cmd)

    def watchdog(self):
        while True:
            time.sleep(0.1)
            with self.lock:
                if self.cmd != "stop" and time.monotonic() - self.last > STOP_AFTER:
                    self.cmd = "stop"
                    self.apply("stop")
                    self.moved = time.monotonic()

    def turn_dir(self):
        return {"left": -1, "right": 1}.get(self.cmd, 0)

    def moving_recently(self, window=0.6):
        return self.cmd != "stop" or time.monotonic() - self.moved < window

    def stop(self):
        if self.ok:
            self.left.stop(); self.right.stop()


# ---------------------------------------------------------------------------
# aiming: how far has the rover turned? (in screen widths, right = +)
# ---------------------------------------------------------------------------
class Tracker:
    """Compares each camera frame with the last one to see how far the picture slid sideways.
    Only counts while the rover is moving, so people walking past don't move the aliens."""

    def __init__(self, get_frame, drive):
        self.get_frame, self.drive = get_frame, drive
        self.lock = threading.Lock()
        self.x = 0.0
        self.rate = TURN_RATE_GUESS
        self.mode = "camera" if cv2 is not None else "estimate"
        self.seq = 0

    def loop(self):
        prev, win, last, last_t = None, None, None, time.monotonic()
        while True:
            frame = self.get_frame()
            now = time.monotonic()
            if frame is None:
                # no camera: still move the aim while turning, from the motors
                dt, last_t = min(0.2, now - last_t), now
                if self.drive.turn_dir():
                    with self.lock:
                        self.x += self.drive.turn_dir() * self.rate * dt
                        self.mode, self.seq = "estimate", self.seq + 1
                time.sleep(0.04)
                continue
            if frame is last:
                time.sleep(0.008)
                continue
            last = frame
            dt, last_t = min(0.2, now - last_t), now
            turning = self.drive.turn_dir()
            step = None
            if cv2 is not None:
                try:
                    g = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_REDUCED_GRAYSCALE_4)
                except Exception:
                    g = None
                if g is not None:
                    f = np.float32(g)
                    if prev is not None and prev.shape == f.shape:
                        if win is None or win.shape != f.shape:
                            win = cv2.createHanningWindow((f.shape[1], f.shape[0]), cv2.CV_32F)
                        (dx, dy), resp = cv2.phaseCorrelate(prev, f, win)
                        if resp > 0.08 and abs(dx) < f.shape[1] * 0.4:
                            step = -dx / f.shape[1]          # picture slid left = rover turned right
                            if turning and abs(step) > 0.003 and dt > 0:
                                self.rate = 0.9 * self.rate + 0.1 * min(4.0, abs(step) / dt)
                    prev = f
            if not self.drive.moving_recently():
                continue
            mode = "camera"
            if step is None:                                 # blank wall or blur: use the motors
                step, mode = turning * self.rate * dt, "estimate"
            with self.lock:
                self.x += step
                self.mode = mode
                self.seq += 1

    def state(self):
        with self.lock:
            return {"x": round(self.x, 5), "seq": self.seq, "mode": self.mode, "rate": round(self.rate, 3)}

    def reset(self):
        with self.lock:
            self.x = 0.0


# ---------------------------------------------------------------------------
# web page
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="theme-color" content="#05070d">
<link rel="icon" href="data:,">
<title>Alien Attack</title>
<style>
:root { --bg:#05070d; --panel:#111624; --line:#26304a; --ink:#eef2f8; --dim:#8a93a6;
        --slime:#5dff6a; --hot:#ff3b4e; --gold:#ffc83d; --ice:#5ab8ff; --violet:#b06bff; }
* { box-sizing:border-box; }
[hidden] { display:none !important; }
html, body { margin:0; height:100%; background:var(--bg); color:var(--ink); overflow:hidden;
  font-family:system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; -webkit-tap-highlight-color:transparent; }
button { font:inherit; color:inherit; border:0; cursor:pointer; user-select:none; -webkit-user-select:none; touch-action:manipulation; }

#app { height:100vh; height:100dvh; display:grid; grid-template-columns:auto minmax(0, 1fr) auto;
  align-items:center; gap:12px; padding:10px; }
#view { position:relative; height:100%; max-height:calc((100vw - 380px) * 0.75); aspect-ratio:4/3; margin:0 auto;
  background:#000; border-radius:14px; overflow:hidden; border:2px solid #1d2a1f; touch-action:none; cursor:crosshair;
  box-shadow:0 0 40px rgba(93,255,106,.08); }
#view img, #view canvas { position:absolute; inset:0; width:100%; height:100%; }
#view img { object-fit:contain; }
#view .nocam { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:var(--dim);
  background:radial-gradient(ellipse at center, #0f1a12, #000); text-align:center; padding:20px; }
#view.shake { animation:shake .5s; }
@keyframes shake { 10%,90%{transform:translate(-3px,2px)} 20%,80%{transform:translate(6px,-4px)}
  30%,50%,70%{transform:translate(-9px,5px)} 40%,60%{transform:translate(9px,-3px)} }

.side { display:flex; flex-direction:column; align-items:center; gap:12px; }
.pad { display:grid; grid-template-columns:repeat(3, 62px); grid-template-rows:repeat(3, 56px); gap:6px; }
.pad button { background:#1a2133; border-radius:12px; font-size:22px; touch-action:none; }
.pad button.on { background:var(--slime); color:#062008; }
.speeds { display:flex; gap:4px; }
.speeds button { height:30px; padding:0 9px; border-radius:8px; background:#1a2133; font-size:12px; font-weight:700; }
.speeds button.sel { background:#d9822b; }
.fire { width:112px; height:112px; border-radius:50%; font-weight:900; font-size:21px; letter-spacing:.06em; touch-action:none;
  background:radial-gradient(circle at 35% 30%, #ff7a86, var(--hot) 60%, #a01526);
  box-shadow:0 6px 0 #6d0e1a, 0 0 26px rgba(255,59,78,.45); transition:transform .05s; }
.fire.on { transform:translateY(4px); box-shadow:0 2px 0 #6d0e1a, 0 0 34px rgba(255,59,78,.85); }
.nudges { display:flex; gap:10px; }
.nudges button { width:52px; height:44px; border-radius:12px; background:#26304a; font-size:13px; font-weight:800; touch-action:none; }
.nudges button.on { background:var(--ice); color:#04121f; }
.small { color:var(--dim); font-size:11.5px; text-align:center; max-width:150px; line-height:1.35; }
.dist { font-size:12px; color:var(--dim); min-height:16px; text-align:center; }
.dist.close { color:var(--hot); font-weight:800; }

/* ---------- title / game over ---------- */
.screen { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:14px; text-align:center; padding:18px; background:rgba(3,6,10,.78); backdrop-filter:blur(3px); z-index:3; }
.screen h1 { margin:0; font-size:clamp(34px, 7vw, 68px); font-weight:900; letter-spacing:.08em; line-height:1;
  color:var(--slime); text-shadow:0 0 18px rgba(93,255,106,.6), 0 4px 0 #0a3a10; }
.screen h2 { margin:0; font-size:clamp(26px, 5vw, 48px); font-weight:900; letter-spacing:.06em; }
.screen p { margin:0; max-width:520px; color:#c8d0de; font-size:15px; line-height:1.45; }
.screen .keys { color:var(--dim); font-size:13px; }
.screen .row { display:flex; gap:8px; flex-wrap:wrap; justify-content:center; }
.screen .opt { height:38px; padding:0 14px; border-radius:10px; background:var(--panel); border:1px solid var(--line); font-weight:700; font-size:14px; }
.screen .opt.sel { border-color:var(--slime); color:var(--slime); }
.screen .go { height:56px; padding:0 34px; border-radius:14px; background:var(--slime); color:#062008; font-size:20px; font-weight:900;
  letter-spacing:.05em; box-shadow:0 5px 0 #1f8a2a, 0 0 28px rgba(93,255,106,.4); }
.screen .big { font-size:clamp(22px, 4vw, 34px); font-weight:900; color:var(--gold); }
.screen details { color:var(--dim); font-size:13px; }
.screen summary { cursor:pointer; }
.screen label { display:flex; align-items:center; gap:8px; justify-content:center; margin-top:8px; }
.screen input[type=range] { width:180px; }

/* phone held upright: picture on top, controls underneath */
@media (orientation:portrait) {
  #app { grid-template-columns:1fr 1fr; grid-template-rows:auto auto; align-content:start; }
  #view { grid-column:1 / -1; width:100%; height:auto; max-height:none; }
  .side.left { grid-column:1; } .side.right { grid-column:2; }
}
@media (max-height:520px) and (orientation:landscape) {
  #app { gap:8px; padding:6px; }
  #view { max-height:none; }
  .pad { grid-template-columns:repeat(3, 54px); grid-template-rows:repeat(3, 48px); }
  .small, .speeds { display:none; }
  .fire { width:96px; height:96px; }
}
</style></head>
<body>
<div id="app">
  <div class="side left">
    <div class="pad" id="pad">
      <span></span><button data-cmd="forward" aria-label="forward">&#9650;</button><span></span>
      <button data-cmd="left" aria-label="turn left">&#9664;</button><button data-cmd="stop" aria-label="stop">&#9632;</button><button data-cmd="right" aria-label="turn right">&#9654;</button>
      <span></span><button data-cmd="backward" aria-label="back">&#9660;</button><span></span>
    </div>
    <div class="speeds"><button data-speed="slow">Slow</button><button data-speed="medium">Med</button><button data-speed="fast">Fast</button></div>
    <div class="dist" id="dist"></div>
    <div class="small">Arrows / W A S D drive<br>Q / E aim a little</div>
  </div>

  <div id="view">
    <img id="cam" alt="rover camera">
    <div class="nocam" id="nocam">connecting to the rover camera...</div>
    <canvas id="cv"></canvas>

    <div class="screen" id="title">
      <h1>ALIEN ATTACK</h1>
      <p>Aliens are invading the house! They're hiding all around the room. <b>Turn the rover to aim</b>,
         put them in the crosshair and blast them before they get too close.</p>
      <div class="row" id="diff">
        <button class="opt" data-diff="easy">Easy</button>
        <button class="opt sel" data-diff="normal">Normal</button>
        <button class="opt" data-diff="hard">Hard</button>
      </div>
      <button class="go" id="start">START</button>
      <div class="keys">Turn: arrows or A / D &middot; Fine aim: Q / E &middot; Fire: Space or click &middot; Phone: D-pad + FIRE</div>
      <details><summary>Settings</summary>
        <label>Video sync <input type="range" id="sync" min="0" max="500" step="10"> <span id="syncv"></span> ms</label>
        <div style="max-width:380px;margin:6px auto 0">If aliens slide a little before the picture moves when you turn, raise this. If they slide after, lower it.</div>
      </details>
    </div>

    <div class="screen" id="over" hidden>
      <h2 id="overTitle">GAME OVER</h2>
      <div class="big" id="overScore"></div>
      <p id="overInfo"></p>
      <button class="go" id="again">PLAY AGAIN</button>
    </div>

    <div class="screen" id="paused" hidden>
      <h2>PAUSED</h2>
      <button class="go" id="resume">RESUME</button>
    </div>
  </div>

  <div class="side right">
    <button class="fire" id="fire">FIRE</button>
    <div class="nudges"><button data-nudge="left" aria-label="aim left">&#8249; aim</button><button data-nudge="right" aria-label="aim right">aim &#8250;</button></div>
    <div class="small">Space or click the picture to fire. Don't fire too fast or the blaster overheats.</div>
  </div>
</div>

<script>
"use strict";
const $ = s => document.querySelector(s);
const rand = (a, b) => a + Math.random() * (b - a);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
};

// ============================================================ rover link
const cam = $("#cam"), view = $("#view"), cv = $("#cv"), ctx = cv.getContext("2d");
function startStream() { cam.src = "/stream.mjpg?t=" + Date.now(); }
cam.onload = () => { $("#nocam").hidden = true; };
cam.onerror = () => { $("#nocam").hidden = false; $("#nocam").textContent = "No camera picture. You can still play. Retrying..."; setTimeout(startStream, 4000); };
startStream();

let TR = { x: 0, mode: "", drive: true };
const hist = [];                         // [{t, x}] aim history, to line up with the video
let SYNC = +store.get("aa_sync", 150);
let trackBusy = false;
function pollTrack() {
  if (trackBusy) return;
  trackBusy = true;
  fetch("/track").then(r => r.json()).then(s => {
    TR = s;
    const now = performance.now();
    if (hist.length && Math.abs(s.x - hist[hist.length - 1].x) > 5) hist.length = 0;   // reset
    hist.push({ t: now, x: s.x });
    while (hist.length > 2 && now - hist[0].t > 2500) hist.shift();
    showDrive(s);
  }).catch(() => {}).finally(() => { trackBusy = false; });
}
setInterval(pollTrack, 35);
function camX(now) {
  if (!hist.length) return 0;
  const t = now - SYNC;
  if (t <= hist[0].t) return hist[0].x;
  for (let i = hist.length - 1; i >= 0; i--) {
    if (hist[i].t <= t) {
      const a = hist[i], b = hist[i + 1];
      if (!b) return a.x;
      return a.x + (b.x - a.x) * ((t - a.t) / (b.t - a.t));
    }
  }
  return hist[hist.length - 1].x;
}

// ---- driving ----
let cmd = "stop";
const held = [];
function sendCmd(c) { fetch("/drive/" + c, { method: "POST" }).catch(() => {}); }
function setCmd(c) {
  if (c === cmd) return;
  cmd = c; sendCmd(c);
  document.querySelectorAll("#pad button").forEach(b => b.classList.toggle("on", b.dataset.cmd === c && c !== "stop"));
}
setInterval(() => { if (cmd !== "stop") sendCmd(cmd); }, 150);
function nudge(d) { fetch("/nudge/" + d, { method: "POST" }).catch(() => {}); }
document.querySelectorAll("#pad button").forEach(b => {
  b.addEventListener("pointerdown", e => { e.preventDefault(); try { b.setPointerCapture(e.pointerId); } catch (err) {} setCmd(b.dataset.cmd); });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach(ev => b.addEventListener(ev, () => setCmd("stop")));
});
document.querySelectorAll("[data-nudge]").forEach(b => {
  b.addEventListener("pointerdown", e => { e.preventDefault(); b.classList.add("on"); nudge(b.dataset.nudge); });
  ["pointerup", "pointercancel", "pointerleave"].forEach(ev => b.addEventListener(ev, () => b.classList.remove("on")));
});
document.querySelectorAll("[data-speed]").forEach(b => b.addEventListener("click", () => {
  fetch("/speed/" + b.dataset.speed, { method: "POST" }).catch(() => {});
}));
function showDrive(s) {
  document.querySelectorAll("[data-speed]").forEach(x => x.classList.toggle("sel", x.dataset.speed === s.speed));
  const d = $("#dist");
  if (!s.drive) { d.textContent = "motors not available"; d.classList.add("close"); return; }
  if (!s.sensor || s.dist === null || s.dist === undefined) { d.textContent = ""; d.classList.remove("close"); return; }
  d.textContent = Math.round(s.dist) + " cm ahead" + (s.blocked ? " (blocked)" : "");
  d.classList.toggle("close", s.blocked);
}

// ============================================================ sound (made on the fly)
const sfx = (() => {
  let ac = null, muted = false;
  function c() { if (!ac) { try { ac = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { return null; } }
    if (ac.state === "suspended") ac.resume(); return ac; }
  function tone(f0, f1, d, type = "square", vol = 0.1, delay = 0) {
    const a = c(); if (!a || muted) return;
    const t = a.currentTime + delay, o = a.createOscillator(), g = a.createGain();
    o.type = type; o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(Math.max(1, f1), t + d);
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + d);
    o.connect(g).connect(a.destination); o.start(t); o.stop(t + d + 0.03);
  }
  function noise(d, vol = 0.3, lp = 1200, delay = 0) {
    const a = c(); if (!a || muted) return;
    const n = (a.sampleRate * d) | 0, b = a.createBuffer(1, n, a.sampleRate), ch = b.getChannelData(0);
    for (let k = 0; k < n; k++) ch[k] = (Math.random() * 2 - 1) * Math.pow(1 - k / n, 2);
    const s = a.createBufferSource(), f = a.createBiquadFilter(), g = a.createGain();
    s.buffer = b; f.type = "lowpass"; f.frequency.value = lp; g.gain.value = vol;
    s.connect(f).connect(g).connect(a.destination); s.start(a.currentTime + delay);
  }
  return {
    unlock: c,
    pew() { tone(1700, 180, 0.15, "square", 0.06); tone(900, 120, 0.12, "sawtooth", 0.03); },
    splat() { noise(0.35, 0.45, 900); tone(320, 60, 0.25, "sine", 0.18); },
    ping() { tone(520, 380, 0.08, "triangle", 0.08); },
    spawn() { tone(200, 900, 0.25, "sine", 0.05); },
    warn() { tone(980, 980, 0.07, "square", 0.04); },
    hurt() { noise(0.5, 0.55, 500); tone(160, 40, 0.5, "sawtooth", 0.14); },
    shield() { tone(300, 1200, 0.35, "sine", 0.12); },
    power() { [660, 880, 1320].forEach((f, k) => tone(f, f, 0.12, "square", 0.07, k * 0.08)); },
    heat() { tone(140, 90, 0.3, "sawtooth", 0.08); },
    wave() { [392, 523, 659, 784].forEach((f, k) => tone(f, f, 0.16, "square", 0.07, k * 0.1)); },
    boss() { tone(70, 50, 1.2, "sawtooth", 0.18); tone(105, 70, 1.2, "square", 0.06); },
    over() { [523, 392, 330, 262].forEach((f, k) => tone(f, f * 0.97, 0.3, "sawtooth", 0.08, k * 0.22)); },
    nuke() { noise(1.2, 0.7, 700); tone(90, 30, 1.0, "sine", 0.3); },
  };
})();

// ============================================================ the game
const DIFF = {
  easy:   { life: 10, lives: 6, spread: 1.15, maxAlive: 2, heat: 0.07 },
  normal: { life: 7.5, lives: 5, spread: 1.6, maxAlive: 3, heat: 0.09 },
  hard:   { life: 5.5, lives: 4, spread: 2.2, maxAlive: 4, heat: 0.10 },
};
const KIND = {
  blip:   { hp: 1, pts: 100, size: 0.085 },
  brute:  { hp: 3, pts: 300, size: 0.115 },
  saucer: { hp: 1, pts: 500, size: 0.075 },
  crate:  { hp: 1, pts: 50,  size: 0.06 },
  boss:   { hp: 14, pts: 3000, size: 0.08 },
};
let diffName = "normal";
let game = window.game = { state: "title" };
let nextId = 1;

function newGame() {
  const D = DIFF[diffName];
  game = window.game = {
    state: "play", D, lives: D.lives, maxLives: D.lives + 2, score: 0, wave: 0, combo: 0, lastKill: 0,
    aliens: [], fx: [], texts: [], splats: [], lasers: [],
    heat: 0, overheated: false, lastShot: 0, rapid: 0, shield: 0,
    toSpawn: 0, nextSpawn: 0, waveEnd: 0, nextCrate: performance.now() + rand(15000, 25000),
    kills: 0, shots: 0, hits: 0, started: performance.now(),
  };
  hist.length = 0;
  fetch("/track/reset", { method: "POST" }).catch(() => {});
  $("#title").hidden = true; $("#over").hidden = true; $("#paused").hidden = true;
  startWave(1);
}

function startWave(n) {
  const g = game, now = performance.now();
  g.wave = n;
  g.boss = n % 5 === 0;
  g.toSpawn = g.boss ? 2 + n : 3 + 2 * n;
  g.nextSpawn = now + 2200;
  g.firstOfWave = true;
  g.waveEnd = 0;
  banner(g.boss ? "BOSS WAVE " + n : "WAVE " + n, g.boss ? "#ff3b4e" : "#5dff6a", 2000);
  g.boss ? sfx.boss() : sfx.wave();
  if (g.boss) setTimeout(() => { if (game === g && g.state === "play") spawn("boss"); }, 1800);
}

function spawn(kind) {
  const g = game, now = performance.now(), cx = camX(now), K = KIND[kind];
  const spread = g.D.spread;
  let off;
  if (kind === "boss") off = (Math.random() < 0.5 ? -1 : 1) * rand(0.15, 0.4);
  else if (g.firstOfWave || Math.random() < 0.35) off = rand(-0.32, 0.32);      // on screen
  else off = (Math.random() < 0.5 ? -1 : 1) * rand(0.6, spread);                // turn to find it
  g.firstOfWave = false;
  const speedUp = Math.max(0.55, 1 - (g.wave - 1) * 0.05);
  const a = {
    id: nextId++, kind, wx: cx + off, wy: rand(0.3, 0.62), born: now, hp: K.hp + (kind === "boss" ? g.wave : 0),
    life: g.D.life * speedUp * (kind === "brute" ? 1.25 : 1) * 1000, hitT: 0, warned: false, seed: Math.random() * 1000,
  };
  a.maxhp = a.hp;
  if (kind === "saucer") { a.wy = rand(0.14, 0.26); a.vx = (Math.random() < 0.5 ? -1 : 1) * rand(0.18, 0.3); a.life = 1e9; }
  if (kind === "crate") { a.wy = rand(0.35, 0.6); a.life = 11000; }
  if (kind === "boss") { a.wy = 0.4; a.life = 1e9; a.nextAtk = now + 6000; a.base = a.wx; }
  g.aliens.push(a);
  sfx.spawn();
}

function hurtPlayer(src) {
  const g = game, now = performance.now();
  if (g.shield > now) { addText("BLOCKED!", 0.5, 0.42, "#5ab8ff", 900, 1.2); sfx.shield(); return; }
  g.lives -= 1;
  g.combo = 0;
  for (let k = 0; k < 3; k++) g.splats.push({ x: rand(0.12, 0.88), y: rand(0.15, 0.8), r: rand(0.07, 0.13), t0: now, dur: 2600, seed: Math.random() });
  g.fx.push({ kind: "red", t0: now, dur: 600 });
  view.classList.remove("shake"); void view.offsetWidth; view.classList.add("shake");
  sfx.hurt();
  if (navigator.vibrate) navigator.vibrate([100, 50, 150]);
  if (g.lives <= 0) gameOver();
}

function gameOver() {
  const g = game;
  g.state = "over";
  setCmd("stop");
  const best = Math.max(+store.get("aa_best_" + diffName, 0), g.score);
  const isBest = g.score >= best && g.score > 0;
  store.set("aa_best_" + diffName, best);
  $("#overTitle").textContent = isBest ? "NEW HIGH SCORE!" : "GAME OVER";
  $("#overTitle").style.color = isBest ? "#ffc83d" : "#ff3b4e";
  $("#overScore").textContent = g.score.toLocaleString() + " points";
  const acc = g.shots ? Math.round(100 * g.hits / g.shots) : 0;
  $("#overInfo").textContent = `Reached wave ${g.wave} · ${g.kills} aliens zapped · ${acc}% accuracy · best on ${diffName}: ${best.toLocaleString()}`;
  $("#over").hidden = false;
  sfx.over();
}

// ---------- shooting ----------
let fireHeld = false;
function tryFire() {
  const g = game, now = performance.now();
  if (g.state !== "play") return;
  const gap = g.rapid > now ? 90 : 210;
  if (now - g.lastShot < gap) return;
  if (g.overheated) { if (now - g.lastHeatSnd > 400) { sfx.heat(); g.lastHeatSnd = now; } return; }
  g.lastShot = now;
  g.shots++;
  g.heat += g.rapid > now ? g.D.heat * 0.4 : g.D.heat;
  if (g.heat >= 1) { g.heat = 1; g.overheated = true; addText("OVERHEAT!", 0.5, 0.62, "#ff7a2a", 1000, 1); sfx.heat(); g.lastHeatSnd = now; }
  g.lasers.push({ t0: now, dur: 170 });
  sfx.pew();
  // what's under the crosshair? (the biggest = closest one wins)
  const cr = rectNow, cx = camX(now);
  let best = null, bestR = 0;
  for (const a of g.aliens) {
    if (a.dead) continue;
    const p = screenPos(a, cr, cx, now);
    const d = Math.hypot(p.x - (cr.x + cr.w / 2), p.y - (cr.y + cr.h / 2));
    if (d < hitRadius(p, cr) && p.r > bestR) { best = a; bestR = p.r; }
  }
  if (!best) { g.fx.push({ kind: "spark", x: 0.5, y: 0.5, t0: now, dur: 250 }); return; }
  g.hits++;
  best.hp -= 1;
  best.hitT = now;
  if (best.hp > 0) { sfx.ping(); g.fx.push({ kind: "spark", x: 0.5, y: 0.5, t0: now, dur: 300, color: "#fff" }); return; }
  kill(best, now, cr, cx);
}

function kill(a, now, cr, cx, quiet) {
  const g = game, K = KIND[a.kind];
  a.dead = true;
  const p = screenPos(a, cr, cx, now);
  const fx = (p.x - cr.x) / cr.w, fy = (p.y - cr.y) / cr.h;
  if (a.kind === "crate") { power(fx, fy); g.fx.push({ kind: "burst", x: fx, y: fy, r: p.r / cr.h, t0: now, dur: 700, color: "#ffc83d" }); return; }
  g.kills++;
  g.combo = now - g.lastKill < 2500 ? Math.min(5, g.combo + 1) : 1;
  g.lastKill = now;
  const quick = a.kind !== "saucer" && a.kind !== "boss" && (now - a.born) / a.life < 0.35;
  const pts = K.pts * g.combo * (quick ? 2 : 1);
  g.score += pts;
  g.fx.push({ kind: "goo", x: fx, y: fy, r: p.r / cr.h, t0: now, dur: a.kind === "boss" ? 1600 : 900, seed: Math.random(),
              color: a.kind === "brute" ? "#c77dff" : a.kind === "boss" ? "#ff5aa0" : "#5dff6a" });
  if (!quiet) {
    addText("+" + pts + (quick ? " QUICK!" : "") + (g.combo > 1 ? " x" + g.combo : ""), fx, fy - 0.08, quick ? "#ffc83d" : "#fff", 1000, 1);
    sfx.splat();
  }
  if (a.kind === "boss") { banner("BOSS DESTROYED!", "#ffc83d", 2200); sfx.nuke(); }
}

function power(fx, fy) {
  const g = game, now = performance.now();
  const opts = ["rapid", "shield", "nuke"];
  if (g.lives < g.maxLives) opts.push("life", "life");
  const p = opts[Math.floor(Math.random() * opts.length)];
  sfx.power();
  if (p === "rapid") { g.rapid = now + 9000; g.heat = 0; g.overheated = false; addText("RAPID FIRE!", fx, fy, "#ffc83d", 1300, 1.3); }
  if (p === "shield") { g.shield = now + 9000; addText("SHIELD!", fx, fy, "#5ab8ff", 1300, 1.3); }
  if (p === "life") { g.lives = Math.min(g.maxLives, g.lives + 1); addText("+1 LIFE", fx, fy, "#ff5a7a", 1300, 1.3); }
  if (p === "nuke") {
    addText("SPACE BOMB!", fx, fy, "#fff", 1400, 1.4);
    g.fx.push({ kind: "flash", t0: now, dur: 700 });
    sfx.nuke();
    const cr = rectNow, cx = camX(now);
    for (const a of g.aliens) {
      if (a.dead || a.kind === "crate") continue;
      if (a.kind === "boss") { a.hp = Math.max(1, a.hp - 5); a.hitT = now; continue; }
      kill(a, now, cr, cx, true);
    }
  }
}

function addText(text, x, y, color, dur, scale) { game.texts.push({ text, x, y, color, t0: performance.now(), dur, scale: scale || 1 }); }
let bannerFx = null;
function banner(text, color, dur) { bannerFx = { text, color, t0: performance.now(), dur }; }

// ---------- the clock ----------
function update(now, dt) {
  const g = game;
  if (g.state !== "play") return;
  const cx = camX(now);
  g.heat = Math.max(0, g.heat - dt * 0.45);
  if (g.overheated && g.heat < 0.35) g.overheated = false;
  if (fireHeld) tryFire();
  // spawning
  const alive = g.aliens.filter(a => !a.dead && a.kind !== "crate" && a.kind !== "boss").length;
  if (g.toSpawn > 0 && now >= g.nextSpawn && alive < g.D.maxAlive + Math.floor(g.wave / 3)) {
    const r = Math.random();
    const kind = g.wave >= 3 && r < 0.13 ? "saucer" : g.wave >= 2 && r < 0.38 ? "brute" : "blip";
    spawn(kind);
    g.toSpawn--;
    g.nextSpawn = now + rand(900, 2200) * Math.max(0.5, 1 - g.wave * 0.04);
  }
  if (now > g.nextCrate) {
    if (!g.aliens.some(a => a.kind === "crate" && !a.dead)) spawn("crate");
    g.nextCrate = now + rand(18000, 28000);
  }
  // aliens
  for (const a of g.aliens) {
    if (a.dead) continue;
    if (a.kind === "saucer") {
      a.wx += a.vx * dt;
      if (Math.abs(a.wx - cx) > g.D.spread + 1.2) { a.dead = true; a.escaped = true; }
      continue;
    }
    if (a.kind === "boss") {
      a.wx = a.base + Math.sin((now - a.born) / 1800) * 0.35;
      if (now > a.nextAtk - 1300 && !a.warned) { a.warned = true; sfx.warn(); }
      if (now >= a.nextAtk) { hurtPlayer(a); a.nextAtk = now + Math.max(3500, 6500 - g.wave * 200); a.warned = false; }
      continue;
    }
    const t = (now - a.born) / a.life;
    if (a.kind === "crate") { if (t >= 1) { a.dead = true; a.escaped = true; } continue; }
    if (t > 0.78 && !a.warned) { a.warned = true; sfx.warn(); }
    if (t >= 1) { a.dead = true; a.attacked = true; hurtPlayer(a); }
    if (g.state !== "play") return;
  }
  g.aliens = g.aliens.filter(a => !a.dead);
  g.fx = g.fx.filter(f => now - f.t0 < f.dur);
  g.texts = g.texts.filter(f => now - f.t0 < f.dur);
  g.splats = g.splats.filter(f => now - f.t0 < f.dur);
  g.lasers = g.lasers.filter(f => now - f.t0 < f.dur);
  // wave cleared?
  const left = g.aliens.filter(a => a.kind !== "crate").length;
  if (g.toSpawn === 0 && left === 0) {
    if (!g.waveEnd) { g.waveEnd = now + 2600; g.score += 250 * g.wave; banner("WAVE " + g.wave + " CLEARED! +" + 250 * g.wave, "#ffc83d", 2200); }
    else if (now >= g.waveEnd) startWave(g.wave + 1);
  }
}

// ============================================================ drawing
let rectNow = { x: 0, y: 0, w: 4, h: 3 };
function contentRect(W, H) {
  const nw = cam.naturalWidth || 4, nh = cam.naturalHeight || 3, s = Math.min(W / nw, H / nh);
  return { x: (W - nw * s) / 2, y: (H - nh * s) / 2, w: nw * s, h: nh * s };
}
// how close to the crosshair counts as a hit: the alien itself, or a small aim-help circle for tiny far-away ones
function hitRadius(p, cr) { return Math.max(p.r * 1.15 + 4, cr.w * 0.05); }
function screenPos(a, cr, cx, now) {
  const K = KIND[a.kind];
  let grow;
  if (a.kind === "blip" || a.kind === "brute") grow = 0.38 + 0.62 * clamp((now - a.born) / a.life, 0, 1);
  else grow = 1;
  const pop = clamp((now - a.born) / 350, 0, 1);                          // teleport-in
  const bob = Math.sin(now / 420 + a.seed) * 0.012 * cr.h;
  let shake = 0;
  if (a.warned) shake = Math.sin(now / 28) * 3;
  return { x: cr.x + (0.5 + (a.wx - cx)) * cr.w + shake, y: cr.y + a.wy * cr.h + bob,
           r: K.size * cr.h * grow * (0.3 + 0.7 * pop) * (a.kind === "boss" ? 1.25 : 1), grow, pop };
}

function glowCircle(x, y, r, color, a = 1) {
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = color; ctx.shadowColor = color; ctx.shadowBlur = r * 1.5;
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.restore();
}
function eye(x, y, rx, ry, rot, angry, lookX, lookY) {
  ctx.save(); ctx.translate(x, y); ctx.rotate(rot);
  ctx.fillStyle = angry ? "#ff2030" : "#0b0d12";
  if (angry) { ctx.shadowColor = "#ff2030"; ctx.shadowBlur = rx * 2; }
  ctx.beginPath(); ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2); ctx.fill();
  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(255,255,255,.9)";
  ctx.beginPath(); ctx.ellipse(-rx * 0.3 + lookX * rx * 0.2, -ry * 0.35 + lookY * ry * 0.15, rx * 0.28, ry * 0.2, 0, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

function drawBlip(x, y, r, now, a) {
  const angry = a.warned, t = now / 1000 + a.seed;
  ctx.save(); ctx.translate(x, y);
  // antennae
  ctx.strokeStyle = "#3fbf4c"; ctx.lineWidth = Math.max(1.5, r * 0.07); ctx.lineCap = "round";
  for (const s of [-1, 1]) {
    const tx = s * r * (0.55 + 0.06 * Math.sin(t * 3 + s)), ty = -r * 1.32;
    ctx.beginPath(); ctx.moveTo(s * r * 0.3, -r * 0.7); ctx.quadraticCurveTo(s * r * 0.5, -r * 1.1, tx, ty); ctx.stroke();
    glowCircle(tx, ty, r * 0.12, angry ? "#ff4050" : "#e6ff5a");
  }
  // little body + arms
  ctx.fillStyle = "#2c9a37";
  ctx.beginPath(); ctx.ellipse(0, r * 0.95, r * 0.42, r * 0.38, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = "#2c9a37"; ctx.lineWidth = r * 0.12;
  for (const s of [-1, 1]) { ctx.beginPath(); ctx.moveTo(s * r * 0.35, r * 0.85); ctx.lineTo(s * r * 0.72, r * (0.55 + 0.15 * Math.sin(t * 6 + s))); ctx.stroke(); }
  // head
  const g = ctx.createRadialGradient(-r * 0.3, -r * 0.35, r * 0.1, 0, 0, r * 1.05);
  g.addColorStop(0, "#b6ff9a"); g.addColorStop(0.55, "#4fe05c"); g.addColorStop(1, "#1f7a2a");
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.ellipse(0, 0, r, r * 0.86, 0, 0, Math.PI * 2); ctx.fill();
  // eyes
  eye(-r * 0.38, -r * 0.05, r * 0.27, r * 0.38, -0.35, angry, 0, 0);
  eye(r * 0.38, -r * 0.05, r * 0.27, r * 0.38, 0.35, angry, 0, 0);
  // mouth
  ctx.strokeStyle = "#0b3d12"; ctx.lineWidth = Math.max(1.2, r * 0.06);
  ctx.beginPath();
  if (angry) { ctx.ellipse(0, r * 0.5, r * 0.16, r * 0.1, 0, 0, Math.PI * 2); ctx.fillStyle = "#0b3d12"; ctx.fill(); }
  else ctx.arc(0, r * 0.38, r * 0.2, 0.2 * Math.PI, 0.8 * Math.PI);
  ctx.stroke();
  ctx.restore();
}

function drawBrute(x, y, r, now, a) {
  const angry = a.warned, t = now / 1000 + a.seed;
  ctx.save(); ctx.translate(x, y);
  // horns
  ctx.fillStyle = "#e9d8ff";
  for (const s of [-1, 1]) {
    ctx.beginPath(); ctx.moveTo(s * r * 0.55, -r * 0.6); ctx.quadraticCurveTo(s * r * 1.05, -r * 1.0, s * r * 0.95, -r * 1.35);
    ctx.quadraticCurveTo(s * r * 0.8, -r * 0.95, s * r * 0.3, -r * 0.75); ctx.fill();
  }
  // shoulders
  ctx.fillStyle = "#5a2a8f";
  ctx.beginPath(); ctx.ellipse(0, r * 0.95, r * 0.85, r * 0.42, 0, 0, Math.PI * 2); ctx.fill();
  // head
  const g = ctx.createRadialGradient(-r * 0.3, -r * 0.35, r * 0.1, 0, 0, r * 1.1);
  g.addColorStop(0, "#e3b6ff"); g.addColorStop(0.55, "#9d4dff"); g.addColorStop(1, "#4a1a82");
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.ellipse(0, 0, r * 1.05, r * 0.9, 0, 0, Math.PI * 2); ctx.fill();
  // three eyes
  eye(-r * 0.45, -r * 0.12, r * 0.18, r * 0.22, -0.2, angry, 0, 0);
  eye(0, -r * 0.32, r * 0.22, r * 0.27, 0, angry, 0, 0);
  eye(r * 0.45, -r * 0.12, r * 0.18, r * 0.22, 0.2, angry, 0, 0);
  // frown with teeth
  ctx.fillStyle = "#2a0b4a";
  ctx.beginPath(); ctx.ellipse(0, r * 0.42, r * 0.45, r * (angry ? 0.24 : 0.14), 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#fff";
  for (let k = -2; k <= 2; k++) { ctx.beginPath(); ctx.moveTo(k * r * 0.15 - r * 0.05, r * 0.3); ctx.lineTo(k * r * 0.15 + r * 0.05, r * 0.3); ctx.lineTo(k * r * 0.15, r * 0.42); ctx.fill(); }
  // health pips
  if (a.maxhp > 1) for (let k = 0; k < a.maxhp; k++) {
    ctx.fillStyle = k < a.hp ? "#ff5a7a" : "rgba(255,255,255,.25)";
    ctx.beginPath(); ctx.arc((k - (a.maxhp - 1) / 2) * r * 0.32, -r * 1.25, r * 0.1, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
}

function drawSaucer(x, y, r, now, a) {
  ctx.save(); ctx.translate(x, y); ctx.rotate(Math.sin(now / 300 + a.seed) * 0.12);
  // beam
  ctx.globalAlpha = 0.18 + 0.08 * Math.sin(now / 120);
  ctx.fillStyle = "#9dff8a";
  ctx.beginPath(); ctx.moveTo(-r * 0.5, r * 0.3); ctx.lineTo(r * 0.5, r * 0.3); ctx.lineTo(r * 1.2, r * 3.2); ctx.lineTo(-r * 1.2, r * 3.2); ctx.fill();
  ctx.globalAlpha = 1;
  // dome + pilot
  ctx.fillStyle = "rgba(160,230,255,.45)";
  ctx.beginPath(); ctx.ellipse(0, -r * 0.25, r * 0.6, r * 0.55, 0, Math.PI, 0); ctx.fill();
  ctx.fillStyle = "#4fe05c"; ctx.beginPath(); ctx.arc(0, -r * 0.35, r * 0.28, 0, Math.PI * 2); ctx.fill();
  eye(-r * 0.1, -r * 0.37, r * 0.07, r * 0.1, -0.3, false, 0, 0); eye(r * 0.1, -r * 0.37, r * 0.07, r * 0.1, 0.3, false, 0, 0);
  // disc
  const g = ctx.createLinearGradient(0, -r * 0.3, 0, r * 0.35);
  g.addColorStop(0, "#e8edf5"); g.addColorStop(1, "#5d6678");
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.ellipse(0, 0, r * 1.5, r * 0.4, 0, 0, Math.PI * 2); ctx.fill();
  for (let k = 0; k < 6; k++) {
    const on = Math.floor(now / 140 + k) % 3 === 0;
    glowCircle((k - 2.5) * r * 0.45, r * 0.08, r * 0.09, on ? "#ffe25a" : "#7a6a2a");
  }
  ctx.restore();
}

function drawCrate(x, y, r, now, a) {
  ctx.save(); ctx.translate(x, y + Math.sin(now / 300) * r * 0.2); ctx.rotate(Math.sin(now / 500) * 0.25);
  glowCircle(0, 0, r * 1.25, "rgba(255,200,61,.25)");
  ctx.fillStyle = "#9a6a32"; ctx.fillRect(-r, -r, r * 2, r * 2);
  ctx.strokeStyle = "#5d3b14"; ctx.lineWidth = r * 0.14; ctx.strokeRect(-r, -r, r * 2, r * 2);
  ctx.beginPath(); ctx.moveTo(-r, -r); ctx.lineTo(r, r); ctx.stroke();
  ctx.fillStyle = "#ffc83d"; ctx.font = `900 ${r * 1.4}px system-ui, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.shadowColor = "#ffc83d"; ctx.shadowBlur = r; ctx.fillText("?", 0, r * 0.08);
  ctx.restore();
}

function drawBoss(x, y, r, now, a, cr) {
  const t = now / 1000, charging = a.warned;
  ctx.save(); ctx.translate(x, y);
  // tentacles
  ctx.strokeStyle = "#a01d5a"; ctx.lineCap = "round";
  for (let k = 0; k < 6; k++) {
    const bx = (k - 2.5) * r * 0.3;
    ctx.lineWidth = r * 0.12;
    ctx.beginPath(); ctx.moveTo(bx, r * 0.6);
    ctx.bezierCurveTo(bx + Math.sin(t * 2 + k) * r * 0.4, r * 1.1, bx - Math.sin(t * 2.4 + k) * r * 0.4, r * 1.4, bx + Math.sin(t * 3 + k) * r * 0.3, r * 1.8);
    ctx.stroke();
  }
  // brain head
  const g = ctx.createRadialGradient(-r * 0.3, -r * 0.4, r * 0.1, 0, 0, r * 1.15);
  g.addColorStop(0, "#ffb3d6"); g.addColorStop(0.6, "#e0427f"); g.addColorStop(1, "#7a0f3e");
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.ellipse(0, 0, r * 1.15, r, 0, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = "rgba(122,15,62,.6)"; ctx.lineWidth = r * 0.04;
  for (let k = 0; k < 7; k++) {
    ctx.beginPath(); ctx.arc((k - 3) * r * 0.3, -r * 0.55, r * 0.22, Math.PI * 0.1, Math.PI * 0.9 + (k % 2) * 0.5); ctx.stroke();
  }
  // one giant eye that watches your crosshair
  const lx = clamp((cr.x + cr.w / 2 - x) / (r * 3), -1, 1), ly = clamp((cr.y + cr.h / 2 - y) / (r * 3), -1, 1);
  ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.ellipse(0, r * 0.05, r * 0.5, r * 0.42, 0, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = charging ? "#ff1020" : "#3dff9a";
  if (charging) { ctx.shadowColor = "#ff1020"; ctx.shadowBlur = r * 0.8; }
  ctx.beginPath(); ctx.arc(lx * r * 0.22, r * 0.05 + ly * r * 0.16, r * 0.24, 0, Math.PI * 2); ctx.fill();
  ctx.shadowBlur = 0; ctx.fillStyle = "#000";
  ctx.beginPath(); ctx.arc(lx * r * 0.27, r * 0.05 + ly * r * 0.2, r * 0.11, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
  // health bar
  const w = r * 2.4, h = 8, bx = x - w / 2, by = y - r * 1.35;
  ctx.fillStyle = "rgba(0,0,0,.6)"; ctx.fillRect(bx - 2, by - 2, w + 4, h + 4);
  ctx.fillStyle = "#ff3b7a"; ctx.fillRect(bx, by, w * a.hp / a.maxhp, h);
}

function drawAlien(a, now, cr, cx) {
  const p = screenPos(a, cr, cx, now);
  if (p.x + p.r * 2 < cr.x || p.x - p.r * 2 > cr.x + cr.w) return p;
  // teleport ring
  if (p.pop < 1) {
    ctx.save(); ctx.strokeStyle = "#7dff8a"; ctx.globalAlpha = 1 - p.pop; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.ellipse(p.x, p.y + p.r * 0.9, p.r * 2 * p.pop + 6, p.r * 0.5 * p.pop + 3, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
  }
  // shadow on the floor
  if (a.kind !== "saucer" && a.kind !== "crate") {
    ctx.save(); ctx.fillStyle = "rgba(0,0,0,.28)";
    ctx.beginPath(); ctx.ellipse(p.x, p.y + p.r * (a.kind === "boss" ? 2.0 : 1.45), p.r * 0.8, p.r * 0.18, 0, 0, Math.PI * 2); ctx.fill(); ctx.restore();
  }
  if (a.warned && a.kind !== "boss") glowCircle(p.x, p.y, p.r * 1.25, "rgba(255,40,60,.25)");
  if (a.kind === "blip") drawBlip(p.x, p.y, p.r, now, a);
  else if (a.kind === "brute") drawBrute(p.x, p.y, p.r, now, a);
  else if (a.kind === "saucer") drawSaucer(p.x, p.y, p.r, now, a);
  else if (a.kind === "crate") drawCrate(p.x, p.y, p.r, now, a);
  else if (a.kind === "boss") drawBoss(p.x, p.y, p.r, now, a, cr);
  if (now - a.hitT < 110) glowCircle(p.x, p.y, p.r * 1.05, "rgba(255,255,255,.7)");
  if (a.warned && a.kind !== "boss" && a.kind !== "crate" && a.kind !== "saucer") {
    big("!", p.x, p.y - p.r * 1.75, "#ff3b4e", Math.max(16, p.r * 0.9), 0.6 + 0.4 * Math.sin(now / 60));
  }
  return p;
}

function big(text, x, y, color, size, alpha = 1) {
  ctx.save(); ctx.globalAlpha = clamp(alpha, 0, 1);
  ctx.font = `900 ${size}px system-ui, -apple-system, Segoe UI, Roboto, sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
  ctx.lineWidth = Math.max(3, size * 0.12); ctx.strokeStyle = "rgba(0,0,0,.85)";
  ctx.strokeText(text, x, y); ctx.fillStyle = color; ctx.fillText(text, x, y); ctx.restore();
}

function drawEdgeArrows(cr, cx, now, list) {
  let left = 0, right = 0, leftWarn = false, rightWarn = false;
  for (const { a, p } of list) {
    if (a.kind === "crate") continue;
    const fx = (p.x - cr.x) / cr.w;
    if (fx >= -0.02 && fx <= 1.02) continue;
    const isLeft = fx < 0;
    const warn = a.warned || a.kind === "boss";
    if (isLeft) { left++; leftWarn = leftWarn || warn; } else { right++; rightWarn = rightWarn || warn; }
    const ex = isLeft ? cr.x + 18 : cr.x + cr.w - 18, ey = clamp(p.y, cr.y + 30, cr.y + cr.h - 60);
    const col = warn ? "#ff3b4e" : a.kind === "saucer" ? "#ffc83d" : "#5dff6a";
    const pulse = 1 + 0.15 * Math.sin(now / 120);
    ctx.save(); ctx.translate(ex, ey); ctx.scale(isLeft ? -pulse : pulse, pulse);
    ctx.fillStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 12;
    ctx.beginPath(); ctx.moveTo(14, 0); ctx.lineTo(-8, -15); ctx.lineTo(-8, 15); ctx.fill(); ctx.restore();
  }
  const onScreen = list.some(({ a, p }) => a.kind !== "crate" && p.x > cr.x && p.x < cr.x + cr.w);
  if (!onScreen && (left || right) && game.state === "play") {
    const txt = left >= right ? "◀ TURN LEFT" : "TURN RIGHT ▶";
    big(txt, cr.x + cr.w / 2, cr.y + cr.h * 0.22, (left >= right ? leftWarn : rightWarn) ? "#ff3b4e" : "#5dff6a", Math.max(18, cr.w * 0.04), 0.7 + 0.3 * Math.sin(now / 150));
  }
}

function drawRadar(cr, cx, list, now) {
  const range = game.D.spread + 0.6, w = Math.min(cr.w * 0.42, 340), h = 16;
  const x0 = cr.x + (cr.w - w) / 2, y0 = cr.y + cr.h - h - 12;
  ctx.save();
  ctx.fillStyle = "rgba(0,20,6,.55)"; ctx.strokeStyle = "rgba(93,255,106,.5)"; ctx.lineWidth = 1;
  ctx.fillRect(x0, y0, w, h); ctx.strokeRect(x0, y0, w, h);
  const vw = w / (2 * range);
  ctx.strokeStyle = "rgba(255,255,255,.8)"; ctx.strokeRect(x0 + w / 2 - vw / 2, y0 - 2, vw, h + 4);
  for (const { a } of list) {
    const rel = clamp((a.wx - cx) / range, -1, 1);
    const col = a.kind === "crate" ? "#ffc83d" : a.warned || a.kind === "boss" ? "#ff3b4e" : a.kind === "saucer" ? "#ffe25a" : a.kind === "brute" ? "#c77dff" : "#5dff6a";
    glowCircle(x0 + w / 2 + rel * w / 2, y0 + h / 2, a.kind === "boss" ? 5 : 3.2, col);
  }
  ctx.restore();
}

function drawCrosshair(cr, now, lock) {
  const x = cr.x + cr.w / 2, y = cr.y + cr.h / 2, g = game;
  const col = g.overheated ? "#ff7a2a" : lock ? "#ff3b4e" : "rgba(220,255,220,.9)";
  const rad = Math.max(13, cr.w * 0.03) * (lock ? 1 + 0.1 * Math.sin(now / 60) : 1);
  ctx.save(); ctx.strokeStyle = col; ctx.lineWidth = 2.5; ctx.shadowColor = col; ctx.shadowBlur = lock ? 14 : 5;
  ctx.beginPath(); ctx.arc(x, y, rad, 0, Math.PI * 2); ctx.stroke();
  for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
    ctx.beginPath(); ctx.moveTo(x + dx * rad * 0.45, y + dy * rad * 0.45); ctx.lineTo(x + dx * rad * 1.7, y + dy * rad * 1.7); ctx.stroke();
  }
  ctx.fillStyle = col; ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill();
  // heat bar under the crosshair
  if (g.heat > 0.02) {
    const w = rad * 3, bx = x - w / 2, by = y + rad * 2.1;
    ctx.shadowBlur = 0; ctx.fillStyle = "rgba(0,0,0,.5)"; ctx.fillRect(bx, by, w, 5);
    ctx.fillStyle = g.overheated ? "#ff3b2a" : g.heat > 0.7 ? "#ff9a2a" : "#ffc83d"; ctx.fillRect(bx, by, w * g.heat, 5);
  }
  ctx.restore();
}

function drawLasers(cr, now) {
  const x = cr.x + cr.w / 2, y = cr.y + cr.h / 2;
  for (const l of game.lasers) {
    const k = (now - l.t0) / l.dur, a = 1 - k;
    ctx.save(); ctx.globalCompositeOperation = "lighter";
    for (const sx of [0.1, 0.9]) {
      const x0 = cr.x + cr.w * sx, y0 = cr.y + cr.h;
      ctx.strokeStyle = "#5dff6a"; ctx.globalAlpha = a; ctx.lineWidth = 9 * a + 2; ctx.shadowColor = "#5dff6a"; ctx.shadowBlur = 22;
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x, y); ctx.stroke();
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2.5 * a + 0.5;
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x, y); ctx.stroke();
    }
    ctx.restore();
  }
}

function seeded(seed) { let s = Math.floor(seed * 2147483646) + 1; return () => (s = (s * 16807) % 2147483647) / 2147483647; }
function drawFx(cr, now) {
  for (const f of game.fx) {
    const k = (now - f.t0) / f.dur;
    if (f.kind === "goo" || f.kind === "burst") {
      const x = cr.x + f.x * cr.w, y = cr.y + f.y * cr.h, R = Math.max(30, f.r * cr.h * 2.2);
      const rnd = seeded(f.seed || 0.37);
      ctx.save();
      ctx.globalAlpha = Math.max(0, 1 - k);
      ctx.strokeStyle = f.color; ctx.lineWidth = 5 * (1 - k);
      ctx.beginPath(); ctx.arc(x, y, R * (0.3 + k), 0, Math.PI * 2); ctx.stroke();
      for (let n = 0; n < 28; n++) {
        const ang = rnd() * Math.PI * 2, sp = (0.4 + rnd()) * R, d = sp * (1 - Math.pow(1 - k, 2));
        ctx.fillStyle = n % 3 ? f.color : "#fff";
        ctx.beginPath(); ctx.arc(x + Math.cos(ang) * d, y + Math.sin(ang) * d + k * k * R * 0.8, (1 - k) * (3 + rnd() * 6), 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    } else if (f.kind === "spark") {
      const x = cr.x + cr.w / 2, y = cr.y + cr.h / 2;
      ctx.save(); ctx.globalAlpha = 1 - k; ctx.strokeStyle = f.color || "#ffe25a"; ctx.lineWidth = 2;
      for (let n = 0; n < 8; n++) { const a = n / 8 * Math.PI * 2; ctx.beginPath(); ctx.moveTo(x + Math.cos(a) * 6, y + Math.sin(a) * 6); ctx.lineTo(x + Math.cos(a) * (10 + 18 * k), y + Math.sin(a) * (10 + 18 * k)); ctx.stroke(); }
      ctx.restore();
    } else if (f.kind === "red") {
      const g = ctx.createRadialGradient(cr.x + cr.w / 2, cr.y + cr.h / 2, cr.w * 0.2, cr.x + cr.w / 2, cr.y + cr.h / 2, cr.w * 0.75);
      g.addColorStop(0, "rgba(255,0,30,0)"); g.addColorStop(1, `rgba(255,0,30,${0.7 * (1 - k)})`);
      ctx.fillStyle = g; ctx.fillRect(cr.x, cr.y, cr.w, cr.h);
    } else if (f.kind === "flash") {
      ctx.fillStyle = `rgba(255,255,255,${0.9 * (1 - k)})`; ctx.fillRect(cr.x, cr.y, cr.w, cr.h);
    }
  }
}

function drawSplats(cr, now) {
  for (const s of game.splats) {
    const k = (now - s.t0) / s.dur, rnd = seeded(s.seed);
    const x = cr.x + s.x * cr.w, y = cr.y + s.y * cr.h + k * cr.h * 0.06, R = s.r * cr.h;
    ctx.save(); ctx.globalAlpha = (k > 0.7 ? (1 - k) / 0.3 : 1) * 0.78;
    ctx.fillStyle = "#3fd94a";
    ctx.beginPath();
    for (let n = 0; n <= 18; n++) { const a = n / 18 * Math.PI * 2, rr = R * (0.75 + rnd() * 0.5); ctx.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
    ctx.fill();
    for (let n = 0; n < 5; n++) { ctx.beginPath(); ctx.ellipse(x + (rnd() - 0.5) * R, y + R * 0.7 + rnd() * R * 0.8 * (0.3 + k), R * 0.12, R * 0.3, 0, 0, Math.PI * 2); ctx.fill(); }
    ctx.fillStyle = "rgba(255,255,255,.35)"; ctx.beginPath(); ctx.ellipse(x - R * 0.3, y - R * 0.3, R * 0.25, R * 0.15, -0.6, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }
}

function drawHud(cr, now) {
  const g = game, pad = 12, fs = Math.max(14, cr.w * 0.026);
  ctx.save();
  // lives as little hearts
  for (let k = 0; k < g.maxLives; k++) {
    const x = cr.x + pad + 10 + k * (fs * 1.25), y = cr.y + pad + 10, s = fs * 0.5;
    ctx.fillStyle = k < g.lives ? "#ff4d6d" : "rgba(255,255,255,.18)";
    ctx.beginPath(); ctx.moveTo(x, y + s * 0.9);
    ctx.bezierCurveTo(x - s * 1.4, y - s * 0.1, x - s * 0.6, y - s * 1.1, x, y - s * 0.3);
    ctx.bezierCurveTo(x + s * 0.6, y - s * 1.1, x + s * 1.4, y - s * 0.1, x, y + s * 0.9); ctx.fill();
  }
  ctx.textBaseline = "top"; ctx.font = `900 ${fs}px system-ui, sans-serif`;
  ctx.lineWidth = 4; ctx.strokeStyle = "rgba(0,0,0,.8)"; ctx.lineJoin = "round";
  const tline = (txt, x, y, col, align) => { ctx.textAlign = align; ctx.strokeText(txt, x, y); ctx.fillStyle = col; ctx.fillText(txt, x, y); };
  tline(g.score.toLocaleString(), cr.x + cr.w - pad, cr.y + pad, "#fff", "right");
  ctx.font = `800 ${fs * 0.7}px system-ui, sans-serif`;
  tline("WAVE " + g.wave, cr.x + cr.w - pad, cr.y + pad + fs * 1.15, "#5dff6a", "right");
  if (g.combo > 1 && now - g.lastKill < 2500) tline("COMBO x" + g.combo, cr.x + cr.w - pad, cr.y + pad + fs * 1.95, "#ffc83d", "right");
  let py = cr.y + pad + fs * 1.3;
  if (g.rapid > now) { tline("RAPID " + Math.ceil((g.rapid - now) / 1000), cr.x + pad, py, "#ffc83d", "left"); py += fs * 0.9; }
  if (g.shield > now) { tline("SHIELD " + Math.ceil((g.shield - now) / 1000), cr.x + pad, py, "#5ab8ff", "left"); py += fs * 0.9; }
  if (TR.mode === "estimate") { ctx.font = `700 ${fs * 0.55}px system-ui, sans-serif`; tline("aim: guessing from motors", cr.x + pad, cr.y + cr.h - pad - fs * 0.6, "#8a93a6", "left"); }
  ctx.restore();
  // shield glow around the screen
  if (g.shield > now) {
    ctx.save(); ctx.strokeStyle = "#5ab8ff"; ctx.lineWidth = 7; ctx.globalAlpha = 0.45 + 0.2 * Math.sin(now / 90);
    ctx.shadowColor = "#5ab8ff"; ctx.shadowBlur = 26; ctx.strokeRect(cr.x + 4, cr.y + 4, cr.w - 8, cr.h - 8); ctx.restore();
  }
}

function drawTexts(cr, now) {
  for (const t of game.texts) {
    const k = (now - t.t0) / t.dur;
    big(t.text, cr.x + clamp(t.x, 0.12, 0.88) * cr.w, cr.y + clamp(t.y, 0.08, 0.92) * cr.h - k * cr.h * 0.07, t.color, Math.max(15, cr.w * 0.032) * t.scale, Math.min(1, (1 - k) * 2.5));
  }
  if (bannerFx) {
    const k = (now - bannerFx.t0) / bannerFx.dur;
    if (k >= 1) bannerFx = null;
    else {
      const s = k < 0.15 ? 0.5 + k / 0.15 * 0.6 : k < 0.25 ? 1.1 - (k - 0.15) : 1;
      big(bannerFx.text, cr.x + cr.w / 2, cr.y + cr.h * 0.38, bannerFx.color, Math.max(26, cr.w * 0.075) * s, k > 0.75 ? (1 - k) / 0.25 : 1);
    }
  }
}

// title screen: a few aliens wander about behind the menu
const demo = [{ kind: "blip", wx: -0.25, wy: 0.45, born: -1e6, life: 3.6e6, seed: 1, hp: 1, maxhp: 1, hitT: 0 },
              { kind: "brute", wx: 0.28, wy: 0.5, born: -1e6, life: 3.6e6, seed: 2, hp: 3, maxhp: 3, hitT: 0 },
              { kind: "saucer", wx: 0, wy: 0.18, born: -1e6, life: 1e12, seed: 3, hp: 1, maxhp: 1, hitT: 0 }];

let lastFrame = performance.now();
function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;
  const W = view.clientWidth, H = view.clientHeight, dpr = window.devicePixelRatio || 1;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const cr = rectNow = contentRect(W, H);
  if (game.state === "title") {
    for (const a of demo) drawAlien(Object.assign(a, { wx: a.kind === "saucer" ? Math.sin(now / 2000) * 0.3 : a.wx }), 2e6 + now, cr, 0);
    return;
  }
  if (game.state === "play") update(now, dt);
  const cx = camX(now);
  const list = game.aliens.map(a => ({ a, p: screenPos(a, cr, cx, now) })).sort((m, n) => m.p.r - n.p.r);
  let lock = false;
  for (const { a } of list) {
    const p = drawAlien(a, now, cr, cx);
    if (Math.hypot(p.x - (cr.x + cr.w / 2), p.y - (cr.y + cr.h / 2)) < hitRadius(p, cr)) lock = true;
  }
  drawFx(cr, now);
  drawLasers(cr, now);
  drawSplats(cr, now);
  drawEdgeArrows(cr, cx, now, list);
  drawRadar(cr, cx, list, now);
  drawCrosshair(cr, now, lock);
  drawTexts(cr, now);
  drawHud(cr, now);
}
requestAnimationFrame(frame);

// ============================================================ buttons and keys
document.querySelectorAll("[data-diff]").forEach(b => b.addEventListener("click", () => {
  diffName = b.dataset.diff;
  document.querySelectorAll("[data-diff]").forEach(x => x.classList.toggle("sel", x === b));
}));
$("#start").onclick = () => { sfx.unlock(); newGame(); };
$("#again").onclick = () => { sfx.unlock(); newGame(); };
$("#resume").onclick = () => {
  // freeze time while paused: push every timer forward by how long the pause lasted
  const g = game, now = performance.now(), d = now - (g.pausedAt || now);
  for (const a of g.aliens) { a.born += d; if (a.nextAtk) a.nextAtk += d; }
  for (const k of ["nextSpawn", "nextCrate", "lastKill", "lastShot"]) g[k] += d;
  for (const k of ["rapid", "shield", "waveEnd"]) if (g[k]) g[k] += d;
  $("#paused").hidden = true; g.state = "play"; lastFrame = now;
};
const sync = $("#sync");
sync.value = SYNC; $("#syncv").textContent = SYNC;
sync.oninput = () => { SYNC = +sync.value; $("#syncv").textContent = SYNC; store.set("aa_sync", SYNC); };

const fireBtn = $("#fire");
fireBtn.addEventListener("pointerdown", e => { e.preventDefault(); sfx.unlock(); fireBtn.classList.add("on"); fireHeld = true; tryFire(); });
["pointerup", "pointercancel", "pointerleave"].forEach(ev => fireBtn.addEventListener(ev, () => { fireBtn.classList.remove("on"); fireHeld = false; }));
cv.addEventListener("pointerdown", e => { e.preventDefault(); sfx.unlock(); fireHeld = true; tryFire(); });
["pointerup", "pointercancel", "pointerleave"].forEach(ev => cv.addEventListener(ev, () => { fireHeld = false; }));

const KEYS = { ArrowUp: "forward", ArrowDown: "backward", ArrowLeft: "left", ArrowRight: "right",
               w: "forward", s: "backward", a: "left", d: "right" };
document.addEventListener("keydown", e => {
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (KEYS[k]) { e.preventDefault(); if (!held.includes(KEYS[k])) held.push(KEYS[k]); setCmd(held[held.length - 1]); return; }
  if (k === " " || k === "Enter" || k === "f") {
    e.preventDefault();
    if (game.state === "title" && k !== "f") { $("#start").click(); return; }
    if (game.state === "over" && k !== "f") { $("#again").click(); return; }
    if (!e.repeat) { sfx.unlock(); fireHeld = true; tryFire(); }
    return;
  }
  if (k === "q" && !e.repeat) nudge("left");
  if (k === "e" && !e.repeat) nudge("right");
  if (k === "1" || k === "2" || k === "3") { const b = document.querySelector(`[data-speed="${{ 1: "slow", 2: "medium", 3: "fast" }[k]}"]`); if (b) b.click(); }
  if (k === "p" || k === "Escape") togglePause();
});
document.addEventListener("keyup", e => {
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (k === " " || k === "Enter" || k === "f") { fireHeld = false; return; }
  if (!KEYS[k]) return;
  const i = held.indexOf(KEYS[k]); if (i >= 0) held.splice(i, 1);
  setCmd(held.length ? held[held.length - 1] : "stop");
});
function togglePause() {
  if (game.state === "play") { game.state = "paused"; game.pausedAt = performance.now(); $("#paused").hidden = false; setCmd("stop"); }
  else if (game.state === "paused") $("#resume").click();
}
window.addEventListener("blur", () => { held.length = 0; fireHeld = false; setCmd("stop"); });
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { held.length = 0; fireHeld = false; setCmd("stop"); if (game.state === "play") togglePause(); }
});
</script>
</body></html>
"""


class Handler(server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

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

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, "text/html", PAGE.encode("utf-8"))
        elif path == "/track":
            s = tracker.state()
            s.update({"drive": drive.ok, "cmd": drive.cmd, "speed": drive.speed, "camera": output is not None,
                      "sensor": drive.sensor, "blocked": drive.ok and drive.blocked(),
                      "dist": None if drive.dist is None else round(drive.dist)})
            self._send(200, "application/json", json.dumps(s).encode())
        elif path == "/stream.mjpg":
            if output is None:
                self.send_error(503, "camera not working")
                return
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b"--FRAME\r\nContent-Type: image/jpeg\r\n")
                    self.wfile.write(b"Content-Length: %d\r\n\r\n" % len(frame))
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "drive" and parts[1] in ("forward", "backward", "left", "right", "stop"):
            drive.go(parts[1]); self._ok()
        elif len(parts) == 2 and parts[0] == "nudge" and parts[1] in ("left", "right"):
            drive.nudge(parts[1]); self._ok()
        elif len(parts) == 2 and parts[0] == "speed" and parts[1] in SPEEDS:
            drive.set_speed(parts[1]); self._ok()
        elif parts == ["track", "reset"]:
            tracker.reset(); self._ok()
        else:
            self.send_error(404)


class Server(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def my_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "<the Pi's address>"


picam2, output = start_camera()
drive = Drive()
tracker = Tracker(lambda: output.frame if output else None, drive)
threading.Thread(target=tracker.loop, daemon=True).start()
try:
    httpd = Server(("", PORT), Handler)
except OSError:
    print(f"Port {PORT} is busy: another program (Face Cam or robot_drive.py) is already running.")
    print("Stop it first (red Stop button in Thonny, or reboot), then press Run again.")
    raise SystemExit
print()
print("ALIEN ATTACK IS RUNNING. Open this on your PC or phone (same Wi-Fi):")
print(f"    http://{my_address()}:{PORT}")
print(f"    http://{socket.gethostname()}.local:{PORT}")
print("Turn the rover to aim, Space to fire. Press the red Stop button in Thonny to quit.")
print()
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    drive.stop()
    httpd.server_close()
    if picam2:
        picam2.stop_recording()
    print("Alien Attack stopped.")
