"""
FACE CAM ROVER - one file, paste into Thonny and press Run.

Drive the rover from a web page (arrow keys / W A S D, or the buttons on a phone) with live video.
The camera also watches for faces: when it sees one it takes a photo (only while the rover is
standing still, so photos aren't blurry).
Open the page on your PC or phone (same Wi-Fi):   http://richardfacko.local:8000
                                       or:        http://192.168.2.159:8000
Photos are saved in the folder  face_photos  in your home folder.

Before running: stop any other program that uses the camera (like robot_drive.py).
To stop Face Cam: press the red Stop button in Thonny.
Needs OpenCV. If it says it's missing, run this once in the Terminal:
    sudo apt install -y python3-opencv
"""

import base64
import datetime
import gzip
import io
import json
import os
import re
import socket
import socketserver
import threading
import time
from http import server
from urllib.parse import urlparse

PORT = 8000
PHOTOS = os.path.expanduser("~/face_photos")
SETTINGS = {
    "START_WATCHING": True,  # start watching as soon as you press Run
    "CHECK_EVERY_S": 0.25,   # how often it looks for faces
    "CONFIRM": 3,            # checks in a row with a face before it counts
    "BURST_S": 1.0,          # then watch this long and keep the best frame
    "COOLDOWN_S": 8,         # at least this long between photos
    "GONE_S": 3,             # same person: wait until nobody's been seen this long...
    "REPEAT_S": 60,          # ...or this long has passed
    "FAR": True,             # also look for small, far-away faces
    "MAX_PHOTOS": 500,
    "FLIP_CAMERA": False,    # True if the picture is upside down
}
S = SETTINGS

# ---- driving (same wiring as the rover: L298N IN1..IN4 on pins 11, 12, 15, 16) ----
LEFT_PINS = (17, 18)         # (forward, backward) GPIO numbers
RIGHT_PINS = (23, 22)        # right side is reversed on this rover
SPEEDS = {"slow": 0.5, "medium": 0.75, "fast": 1.0}
TURN_SPEED = 1.0             # 4-wheel rovers need full power to spin
STOP_AFTER = 0.5             # stop if no command arrives for this long (safety)
USE_SENSOR = True            # distance sensor: blocks driving forward when too close
TRIG_GPIO, ECHO_GPIO = 5, 6  # pins 29 and 31
BLOCK_CM = 20

try:
    import cv2
    import numpy as np
except Exception as e:
    cv2 = None
    print("OpenCV is not installed, so faces can't be found yet.")
    print("Open the Terminal and run:  sudo apt install -y python3-opencv   then press Run again.")

# OpenCV's LBP frontal-face detector (BSD license, from the OpenCV project), packed into this file
DETECTOR_GZ_B64 = """
H4sIAI1J72oC/8Wdb68cx5Xe3y/g7zDxe1pdVV1VXQBXi/UGSV4Eu4vESF4aXOnaJiKJAknZm2+f3+/UkKJmmOD2tNIUDOvq3umZ
nuqq8+c5z3nOy3/49++/u/z16e27129++Pvfpt8tv/2Hr3/zdy//w4sXv/m7H376/t+e3l7e/Ony45t3r9+//uvT5d2r73/87und
pSzL8ukLfnj686tfvCBVX/DihW/25senH7756x/fvX/z9tWfn/zNN6/effPq26fL+//949MfX3/797+dL3lx/f2Lb7579e7d6z+9
fnr7W15+ubx8954r/8Crv/79v/zLf//Dy69+/kX8/U9Pr97/9Hb+4r/+/l9ffvXpL+IVf3l6/ee/vP86ry+/uv4Yv/7b62/f/yV+
O3/6+dP+9dXbV9+/i1/wq3978+bd+3i3//yPv3/51c//ef37969/+C+v3/+3V++fvl5+Nwbfnn/W3rbSU3v51Sd//nDBq3//T6++
e/f0j9+9evs918wrfv6Ha37xiutlf4t7/8Pb199/+Kx6e93NS37+vP/49CPfMMU7z59//tv/fHr1v/7pzU8/vP86XT/7599cV/uT
Bfmw3r9cIy76p1fv5zW5tniXj7/4+Eg+fZt433/+6fuv83L9EP/j5z99fGv24yV+c1kusanit3+8/nD7FcrNF/j4qrlr/vL26d1f
3nz37dcvlt/1mpdt5CWvy7rknD/srI+v+Xjt33y7j/vy3cc/XO/u/dunX9zczQ3Gf77+4f3T2x9efffPb759eveLP128NF3WdnnR
eipLX8blRU618a+05pbysqTCz7nXlLnnGn/e6i/f5EVqZauXuvW01m34Huuy1Jdf/d8/+eV3T6/+9D9efffT3R2xOq2uJaclrduW
UlmXy/K7bf4zak2p5c6CffIGL7/642fXJR1cl/jqrfDVe2OJeht1lF43frssuS+xWi3zpS8valrX2re63i7NKFxUKm9V85o3V/bh
hem9jJyaW2fdWu0sTM99a4XjXjr7KI9nLUw+uDBcX1oZpfXBf2+j5KW02DTcyVi3Jfmy0sbSt3GzImnZtr7lXpovWXPqPbu4a6rr
OhrPLNWx8D6Pr9LSttpK4p54WGtmlVpvqfph65JG7/VulbRfvzxoP6/dJ2YgPcMMrM83A+vWM0uUsdzZI/NlzcC2Xligvm6lrf2S
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
3te/+bv/A15zd8WQygAA
"""

NAME_OK = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(-\d+)?(_face)?\.jpg$")


def load_detector():
    if cv2 is None:
        return None
    path = os.path.join(PHOTOS, ".face_detector.xml")
    os.makedirs(PHOTOS, exist_ok=True)
    with open(path, "wb") as f:
        f.write(gzip.decompress(base64.b64decode("".join(DETECTOR_GZ_B64.split()))))
    c = cv2.CascadeClassifier(path)
    return None if c.empty() else c


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
        transform = Transform(hflip=1, vflip=1) if S["FLIP_CAMERA"] else Transform()
        cam.configure(cam.create_video_configuration(main={"size": (640, 480)}, transform=transform,
                                                     controls={"FrameRate": 20}))
        out = StreamingOutput()
        cam.start_recording(MJPEGEncoder(), FileOutput(out))
        return cam, out
    except Exception as e:
        print(f"Camera not working: {e}")
        print("Is another program using the camera? Stop robot_drive.py (or reboot), then press Run again.")
        print("Check the camera: rpicam-hello --list-cameras")
        return None, None


# ---------------------------------------------------------------------------
# driving
# ---------------------------------------------------------------------------
class Drive:
    def __init__(self):
        self.lock = threading.Lock()
        self.cmd, self.last, self.moved = "stop", 0.0, 0.0
        self.speed, self.dist, self.ok = "fast", None, False
        try:
            from gpiozero import Motor, DigitalOutputDevice, DigitalInputDevice
            self.left = Motor(forward=LEFT_PINS[0], backward=LEFT_PINS[1])
            self.right = Motor(forward=RIGHT_PINS[0], backward=RIGHT_PINS[1])
            self.ok = True
        except Exception as e:
            print(f"Motors not available ({e}). The camera still works, but no driving.")
            print("Is another program using the motors? Stop it (or reboot) and press Run again.")
            return
        self.sensor = False
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
                self.cmd = cmd
                self.apply(cmd)

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

    def moving_recently(self):
        return self.cmd != "stop" or time.monotonic() - self.moved < 1.0

    def stop(self):
        if self.ok:
            self.left.stop(); self.right.stop()

    def status(self):
        return {"drive": self.ok, "cmd": self.cmd, "speed": self.speed, "sensor": self.ok and self.sensor,
                "dist": None if self.dist is None else round(self.dist, 1), "blocked": self.ok and self.blocked()}


# ---------------------------------------------------------------------------
# Face Cam
# ---------------------------------------------------------------------------
class FaceCam:
    def __init__(self, get_frame):
        self.lock = threading.Lock()
        self.get_frame = get_frame
        self.detector = load_detector()
        self.watching = bool(S["START_WATCHING"])
        self.viewed = 0.0
        self.faces, self.faces_t = [], 0.0
        self.status = "off"
        self.streak = 0
        self.last_face = 0.0
        self.last_shot = 0.0
        self.wait_gone = False
        self.busy = False
        self.seq = 0
        os.makedirs(PHOTOS, exist_ok=True)

    def detect(self, jpg):
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        grey = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        found = self.detector.detectMultiScale(grey, 1.1, 4, minSize=(24, 24))
        faces = [tuple(int(v) for v in f) for f in found]
        if not faces and S["FAR"]:
            big = cv2.resize(grey, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
            found = self.detector.detectMultiScale(big, 1.1, 5, minSize=(24, 24))
            faces = [tuple(int(v / 2) for v in f) for f in found]
        return faces, img, grey

    def loop(self):
        last = None
        while True:
            t0 = time.monotonic()
            if self.detector is None:
                self.status = "no-opencv"
                time.sleep(1)
                continue
            active = self.watching or t0 - self.viewed < 5
            if not active or self.busy:
                if not active:
                    self.status = "off"
                time.sleep(0.2)
                continue
            frame = self.get_frame()
            if frame is None:
                self.status = "no-camera"
                time.sleep(0.5)
                continue
            if frame is last:
                time.sleep(0.03)
                continue
            last = frame
            try:
                got = self.detect(frame)
            except Exception as e:
                self.status = f"error: {e}"
                time.sleep(1)
                continue
            if got is None:
                continue
            faces, img, _ = got
            h, w = img.shape[:2]
            with self.lock:
                self.faces = [{"x": x / w, "y": y / h, "w": fw / w, "h": fh / h} for x, y, fw, fh in faces]
                self.faces_t = time.time()
            if self.watching:
                self.decide(bool(faces), time.monotonic())
            else:
                self.status = "off"
            time.sleep(max(0.01, S["CHECK_EVERY_S"] - (time.monotonic() - t0)))

    def decide(self, seen, now):
        if seen:
            self.streak += 1
            self.last_face = now
        else:
            self.streak = 0
            if self.wait_gone and now - self.last_face >= S["GONE_S"]:
                self.wait_gone = False
        if drive.moving_recently():
            self.status = "driving"                       # no photos while moving: they'd be blurry
            self.streak = 0
        elif now - self.last_shot < S["COOLDOWN_S"]:
            self.status = "cooldown"
        elif self.wait_gone and now - self.last_shot < S["REPEAT_S"]:
            self.status = "waiting"
        elif self.streak >= S["CONFIRM"] and self.claim():
            self.status = "snapping"
            threading.Thread(target=self._take, args=("face",), daemon=True).start()
        elif seen:
            self.status = "spotted"
        else:
            self.status = "watching"

    def claim(self):
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            return True

    def take(self, reason="button"):
        return self._take(reason) if self.claim() else None

    def _take(self, reason):
        try:
            best, best_score, last = None, -1.0, None
            end = time.monotonic() + (S["BURST_S"] if reason == "face" else 0.4)
            while time.monotonic() < end or best is None:
                frame = self.get_frame()
                if frame is None:
                    return None
                if frame is not last:
                    last = frame
                    got = self.detect(frame) if self.detector is not None else None
                    if got:
                        faces, img, grey = got
                        score = 0.0
                        for x, y, fw, fh in faces:
                            sharp = cv2.Laplacian(grey[y:y + fh, x:x + fw], cv2.CV_64F).var()
                            score = max(score, fw * fh * (1 + min(sharp, 400) / 100))
                        if best is None or score > best_score:
                            best, best_score = (frame, faces, img), score
                    elif best is None:
                        best = (frame, [], None)
                if time.monotonic() > end + 2:
                    break
                time.sleep(0.04)
            if best is None:
                return None
            frame, faces, img = best
            if reason == "face" and not faces:
                return None
            name = self.save(frame, faces, img)
            self.last_shot = time.monotonic()
            self.wait_gone = reason == "face"
            self.streak = 0
            with self.lock:
                self.seq += 1
            print(f"Photo saved: {name} ({len(faces)} face{'s' if len(faces) != 1 else ''})")
            return name
        finally:
            self.busy = False

    def save(self, frame, faces, img):
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name, n = stamp, 1
        while os.path.exists(os.path.join(PHOTOS, name + ".jpg")):
            n += 1
            name = f"{stamp}-{n}"

        def put(fname, data):
            tmp = os.path.join(PHOTOS, "." + fname + ".tmp")
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, os.path.join(PHOTOS, fname))
        if faces and img is not None:
            ok, zoom = cv2.imencode(".jpg", self.zoom(img, faces), [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                put(name + "_face.jpg", zoom.tobytes())
        put(name + ".jpg", frame)
        for old in self.photos()[S["MAX_PHOTOS"]:]:
            self.delete(old)
        return name + ".jpg"

    @staticmethod
    def zoom(img, faces):
        H, W = img.shape[:2]
        x0 = min(x - 0.9 * w for x, y, w, h in faces)
        x1 = max(x + 1.9 * w for x, y, w, h in faces)
        y0 = min(y - 0.6 * h for x, y, w, h in faces)
        y1 = max(y + 2.0 * h for x, y, w, h in faces)
        cx, cy, cw, ch = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
        if cw * 4 > ch * 3:
            ch = cw * 4 / 3
        else:
            cw = ch * 3 / 4
        x0, x1 = int(max(0, cx - cw / 2)), int(min(W, cx + cw / 2))
        y0, y1 = int(max(0, cy - ch / 2)), int(min(H, cy + ch / 2))
        crop = img[y0:y1, x0:x1]
        scale = min(4.0, max(1.0, 640 / max(1, crop.shape[0])))
        if scale > 1:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            soft = cv2.GaussianBlur(crop, (0, 0), 1.2)
            crop = cv2.addWeighted(crop, 1.5, soft, -0.5, 0)
        return crop

    @staticmethod
    def photos():
        try:
            names = [f for f in os.listdir(PHOTOS) if NAME_OK.match(f) and "_face" not in f]
        except FileNotFoundError:
            return []
        return sorted(names, reverse=True)

    @staticmethod
    def delete(name):
        if not NAME_OK.match(name) or "_face" in name:
            return False
        for f in (name, name[:-4] + "_face.jpg"):
            try:
                os.remove(os.path.join(PHOTOS, f))
            except FileNotFoundError:
                pass
        return True

    def state(self):
        self.viewed = time.monotonic()
        names = self.photos()
        with self.lock:
            fresh = time.time() - self.faces_t < 1.0
            return {**drive.status(),
                "watching": self.watching, "status": self.status,
                "faces": self.faces if fresh else [],
                "detector": "built in" if self.detector is not None else None, "opencv": cv2 is not None,
                "seq": self.seq, "count": len(names),
                "photos": [{"name": n, "face": os.path.exists(os.path.join(PHOTOS, n[:-4] + "_face.jpg"))}
                           for n in names[:120]],
                "cooldown": round(max(0.0, S["COOLDOWN_S"] - (time.monotonic() - self.last_shot)), 1),
                "name": socket.gethostname(),
            }


# ---------------------------------------------------------------------------
# web page
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0b0d12">
<link rel="icon" href="data:,">
<title>Face Cam Rover</title>
<style>
:root { --bg:#0b0d12; --panel:#151922; --line:#2a3140; --ink:#eef2f8; --dim:#8a93a6;
        --ok:#3ddc84; --gold:#ffc83d; --hot:#ff3b4e; }
* { box-sizing:border-box; }
[hidden] { display:none !important; }
html, body { margin:0; background:var(--bg); color:var(--ink);
  font-family:system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; -webkit-tap-highlight-color:transparent; }
button { font:inherit; color:inherit; border:0; cursor:pointer; }
a { color:#8cf; }

header { display:flex; align-items:center; gap:12px; padding:10px 16px; border-bottom:1px solid var(--line);
  background:#0e1118; flex-wrap:wrap; }
header h1 { margin:0; font-size:18px; letter-spacing:.08em; font-weight:900; }
header .who { color:var(--dim); font-size:14px; }
header nav { margin-left:auto; display:flex; gap:14px; font-size:14px; }

main { max-width:1100px; margin:0 auto; padding:16px; display:grid; gap:20px; }
.live { display:grid; grid-template-columns:minmax(0, 1fr) 280px; gap:16px; align-items:start; }
@media (max-width:820px) { .live { grid-template-columns:1fr; } }

.view { position:relative; aspect-ratio:4/3; background:#000; border-radius:14px; overflow:hidden; border:2px solid var(--line); }
.view.on { border-color:var(--ok); }
.view img, .view canvas { position:absolute; inset:0; width:100%; height:100%; }
.view img { object-fit:contain; }
.view .off { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:var(--dim); text-align:center; padding:16px; }
.flash { position:absolute; inset:0; background:#fff; opacity:0; pointer-events:none; }
.flash.go { animation:flash .6s ease-out; }
@keyframes flash { 0% { opacity:.95; } 100% { opacity:0; } }
.pill { position:absolute; left:12px; top:12px; padding:6px 12px; border-radius:999px; font-size:14px; font-weight:800;
  background:rgba(0,0,0,.6); backdrop-filter:blur(4px); display:flex; align-items:center; gap:8px; }
.pill i { width:10px; height:10px; border-radius:50%; background:#666; }
.pill.watching i { background:var(--ok); box-shadow:0 0 8px var(--ok); animation:pulse 1.6s infinite; }
.pill.spotted i, .pill.snapping i { background:var(--gold); box-shadow:0 0 8px var(--gold); }
.pill.cooldown i, .pill.waiting i { background:#5ab8ff; }
@keyframes pulse { 50% { opacity:.35; } }

.side { display:flex; flex-direction:column; gap:12px; }
.big { height:64px; border-radius:14px; font-size:19px; font-weight:900; letter-spacing:.03em; background:var(--ok); color:#06210f; }
.big.stop { background:#3a1d22; color:#ffd3d8; border:1px solid #6b2b35; }
.snap { height:48px; border-radius:12px; background:var(--panel); border:1px solid var(--line); font-weight:800; font-size:16px; }
.snap:disabled { opacity:.5; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px 14px; font-size:14px; color:var(--dim); line-height:1.45; }
.card b { color:var(--ink); }
.stat { display:flex; justify-content:space-between; color:var(--ink); font-weight:700; }
.warn { color:var(--gold); }

.drive { display:flex; flex-direction:column; align-items:center; gap:8px; }
.pad { display:grid; grid-template-columns:repeat(3, 64px); grid-template-rows:repeat(3, 56px); gap:6px; }
.pad button { background:#232a37; border-radius:12px; font-size:22px; touch-action:none; user-select:none; -webkit-user-select:none; }
.pad button.on { background:var(--ok); color:#06210f; }
.pad.off button { opacity:.35; }
.speeds { display:flex; gap:6px; }
.speeds button { height:32px; padding:0 12px; border-radius:8px; background:#232a37; font-size:13px; font-weight:700; }
.speeds button.sel { background:#d9822b; }
.dist { font-size:13px; color:var(--dim); min-height:18px; text-align:center; }
.dist.close { color:var(--hot); font-weight:800; }
.gallery-head { display:flex; align-items:baseline; gap:12px; }
.gallery-head h2 { margin:0; font-size:18px; }
.gallery-head span { color:var(--dim); font-size:14px; }
.gallery-head button { margin-left:auto; background:none; color:var(--dim); font-size:13px; text-decoration:underline; }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:10px; }
.th { position:relative; aspect-ratio:3/4; border-radius:10px; overflow:hidden; background:#000; cursor:pointer; border:2px solid transparent; }
.th:hover { border-color:var(--ok); }
.th img { width:100%; height:100%; object-fit:cover; display:block; }
.th span { position:absolute; left:0; right:0; bottom:0; padding:16px 8px 6px; font-size:12px; font-weight:700;
  background:linear-gradient(transparent, rgba(0,0,0,.75)); }
.th.new { animation:pop .5s cubic-bezier(.2,1.5,.4,1); }
@keyframes pop { from { transform:scale(.4); opacity:0; } }
.empty { color:var(--dim); padding:24px; text-align:center; border:1px dashed var(--line); border-radius:12px; }

#box { position:fixed; inset:0; background:rgba(0,0,0,.92); display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; padding:16px; z-index:9; }
#box img { max-width:100%; max-height:calc(100vh - 120px); border-radius:8px; }
#box .bar { display:flex; gap:8px; flex-wrap:wrap; justify-content:center; }
#box .bar button, #box .bar a { height:40px; padding:0 14px; border-radius:10px; background:var(--panel); border:1px solid var(--line);
  display:inline-flex; align-items:center; font-size:14px; font-weight:700; color:var(--ink); text-decoration:none; }
#box .bar .sel { background:var(--ok); color:#06210f; border-color:transparent; }
#box .bar .del { background:#3a1d22; border-color:#6b2b35; }
#box .when { color:var(--dim); font-size:14px; }
</style></head>
<body>
<header>
  <h1>FACE CAM ROVER</h1>
  <span class="who" id="who"></span>
</header>

<main>
  <section class="live">
    <div class="view" id="view">
      <img id="cam" alt="live camera">
      <div class="off" id="off">connecting...</div>
      <canvas id="cv"></canvas>
      <div class="flash" id="flash"></div>
      <div class="pill" id="pill"><i></i><span id="status">...</span></div>
    </div>
    <div class="side">
      <div class="card drive">
        <div class="pad" id="pad">
          <span></span><button data-cmd="forward" aria-label="forward">&#9650;</button><span></span>
          <button data-cmd="left" aria-label="left">&#9664;</button><button data-cmd="stop" aria-label="stop">&#9632;</button><button data-cmd="right" aria-label="right">&#9654;</button>
          <span></span><button data-cmd="backward" aria-label="back">&#9660;</button><span></span>
        </div>
        <div class="speeds"><button data-speed="slow">Slow</button><button data-speed="medium">Medium</button><button data-speed="fast">Fast</button></div>
        <div class="dist" id="dist"></div>
        <div class="dist">Keys: arrows or W A S D &middot; 1 2 3 speed &middot; let go to stop</div>
      </div>
      <button class="big" id="watch">Start watching</button>
      <button class="snap" id="snap">Snap a photo now</button>
      <div class="card">
        <div class="stat"><span>Photos taken</span><span id="count">0</span></div>
      </div>
      <div class="card" id="tips">
        <b>Tips.</b> Drive it somewhere and park it facing where people walk or sit. Photos pause while it's moving. It works best on faces looking
        toward it, in good light, up to about 3–4 m away. It takes one photo per person, then waits
        for someone new. Each photo also gets a zoomed-in close-up of the face.
      </div>
      <div class="card warn" id="warn" hidden></div>
    </div>
  </section>

  <section>
    <div class="gallery-head"><h2>Photos</h2><span id="sub"></span><button id="clear" hidden>Delete all</button></div>
    <div class="grid" id="grid" style="margin-top:12px"></div>
  </section>
</main>

<div id="box" hidden>
  <img id="boxImg" alt="photo">
  <div class="when" id="boxWhen"></div>
  <div class="bar">
    <button id="prev">&#9664;</button>
    <button id="showFace">Close-up</button>
    <button id="showFull">Whole picture</button>
    <a id="dl" download>Download</a>
    <button class="del" id="del">Delete</button>
    <button id="next">&#9654;</button>
    <button id="close">Close</button>
  </div>
</div>

<script>
"use strict";
const $ = s => document.querySelector(s);
const TEXT = {
  off: "Not watching. Press Start.",
  watching: "Watching for faces...",
  spotted: "Face spotted! Hold still...",
  snapping: "Snap!",
  driving: "Driving (photos pause while moving)",
  cooldown: "Got it! Ready again in a moment",
  waiting: "Already got you. Waiting for someone new...",
  "no-opencv": "OpenCV isn't installed yet",
  "no-detector": "Face detector file missing",
  "no-camera": "No camera picture",
};
let S = null, seq = null, shown = [], boxIdx = -1, boxFace = true, busy = false;

// ---------- live camera ----------
const cam = $("#cam"), off = $("#off");
function startStream() { cam.src = "/stream.mjpg?t=" + Date.now(); }
cam.onload = () => { off.hidden = true; };
cam.onerror = () => { off.hidden = false; off.textContent = "No camera picture. Retrying..."; setTimeout(startStream, 3000); };
startStream();

// ---------- sound: a little camera shutter, made on the fly ----------
let ac = null;
function shutter() {
  try {
    ac = ac || new (window.AudioContext || window.webkitAudioContext)();
    const n = ac.sampleRate * 0.12, b = ac.createBuffer(1, n, ac.sampleRate), d = b.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 3) * (i < n * 0.3 || i > n * 0.5 ? 1 : 0.2);
    const s = ac.createBufferSource(), g = ac.createGain(); s.buffer = b; g.gain.value = 0.4;
    s.connect(g).connect(ac.destination); s.start();
  } catch (e) {}
}
document.addEventListener("pointerdown", () => { try { ac = ac || new (window.AudioContext || window.webkitAudioContext)(); ac.resume(); } catch (e) {} }, { once: true });

// ---------- talking to the rover ----------
function post(path, body) {
  return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
    .then(r => r.json()).catch(() => ({ ok: false }));
}
$("#watch").onclick = () => { if (S) post("/facecam/watch", { on: !S.watching }).then(poll); };
$("#snap").onclick = () => {
  const b = $("#snap"); b.disabled = true; b.textContent = "Snapping...";
  post("/facecam/snap").then(() => { b.disabled = false; b.textContent = "Snap a photo now"; poll(); });
};
$("#clear").onclick = () => {
  if (confirm("Delete all " + (S ? S.count : "") + " photos? This can't be undone.")) post("/facecam/delete_all").then(poll);
};

function poll() {
  if (busy) return;
  busy = true;
  fetch("/facecam/state").then(r => r.json()).then(s => {
    const firstLoad = S === null;
    S = s;
    $("#who").textContent = s.name;
    document.title = "Face Cam Rover · " + s.name;
    $("#status").textContent = s.status === "cooldown" ? "Got it! Ready again in " + Math.ceil(s.cooldown) + "s" : (TEXT[s.status] || s.status);
    $("#pill").className = "pill " + s.status;
    $("#view").classList.toggle("on", s.watching);
    const w = $("#watch");
    w.textContent = s.watching ? "Stop watching" : "Start watching";
    w.classList.toggle("stop", s.watching);
    $("#count").textContent = s.count;
    const warn = $("#warn");
    if (!s.opencv) { warn.hidden = false; warn.innerHTML = "<b>OpenCV isn't installed on this rover yet.</b> The rover's updater installs it by itself within a few minutes, or run <code>sudo apt install -y python3-opencv</code> and restart robot-drive."; }
    else if (!s.detector) { warn.hidden = false; warn.textContent = "The face detector file (models/lbpcascade_frontalface.xml) is missing."; }
    else warn.hidden = true;
    if (seq !== null && s.seq > seq) { const f = $("#flash"); f.classList.remove("go"); void f.offsetWidth; f.classList.add("go"); shutter(); }
    seq = s.seq;
    showDrive(s);
    renderGallery(s.photos, firstLoad);
  }).catch(() => { $("#status").textContent = "Can't reach the rover"; $("#pill").className = "pill"; })
    .finally(() => { busy = false; });
}
setInterval(poll, 250);
poll();

// ---------- driving ----------
let cmd = "stop", canDrive = true;
const held = [];
function sendCmd(c) { fetch("/drive/" + c, { method: "POST" }).catch(() => {}); }
function setCmd(c) {
  if (!canDrive) c = "stop";
  if (c === cmd) return;
  cmd = c; sendCmd(c);
  document.querySelectorAll("#pad button").forEach(b => b.classList.toggle("on", b.dataset.cmd === c && c !== "stop"));
}
setInterval(() => { if (cmd !== "stop") sendCmd(cmd); }, 150);   // keep it going while held
document.querySelectorAll("#pad button").forEach(b => {
  b.addEventListener("pointerdown", e => { e.preventDefault(); try { b.setPointerCapture(e.pointerId); } catch (err) {} setCmd(b.dataset.cmd); });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach(ev => b.addEventListener(ev, () => setCmd("stop")));
});
document.querySelectorAll("[data-speed]").forEach(b => b.addEventListener("click", () => {
  fetch("/speed/" + b.dataset.speed, { method: "POST" }).catch(() => {});
  document.querySelectorAll("[data-speed]").forEach(x => x.classList.toggle("sel", x === b));
}));
const KEYS = { ArrowUp: "forward", ArrowDown: "backward", ArrowLeft: "left", ArrowRight: "right",
               w: "forward", s: "backward", a: "left", d: "right" };
const SPEEDKEYS = { "1": "slow", "2": "medium", "3": "fast" };
document.addEventListener("keydown", e => {
  if (!$("#box").hidden) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (KEYS[k]) { e.preventDefault(); if (!held.includes(KEYS[k])) held.push(KEYS[k]); setCmd(held[held.length - 1]); }
  else if (k === " ") { e.preventDefault(); held.length = 0; setCmd("stop"); }
  else if (SPEEDKEYS[k] && !e.repeat) { const b = document.querySelector('[data-speed="' + SPEEDKEYS[k] + '"]'); if (b) b.click(); }
});
document.addEventListener("keyup", e => {
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (!KEYS[k]) return;
  const i = held.indexOf(KEYS[k]); if (i >= 0) held.splice(i, 1);
  setCmd(held.length ? held[held.length - 1] : "stop");
});
window.addEventListener("blur", () => { held.length = 0; setCmd("stop"); });
document.addEventListener("visibilitychange", () => { if (document.hidden) { held.length = 0; setCmd("stop"); } });
function showDrive(s) {
  canDrive = s.drive;
  $("#pad").classList.toggle("off", !s.drive);
  document.querySelectorAll("[data-speed]").forEach(x => x.classList.toggle("sel", x.dataset.speed === s.speed));
  const d = $("#dist");
  if (!s.drive) { d.textContent = "Motors not available (see the Thonny Shell)"; d.classList.add("close"); return; }
  if (!s.sensor || s.dist === null) { d.textContent = s.sensor ? "distance sensor: no reading" : ""; d.classList.remove("close"); return; }
  d.textContent = "Distance ahead: " + Math.round(s.dist) + " cm" + (s.blocked ? " (too close, forward blocked)" : "");
  d.classList.toggle("close", s.blocked);
}

// ---------- face boxes over the live view ----------
const cv = $("#cv"), ctx = cv.getContext("2d");
function draw(t) {
  requestAnimationFrame(draw);
  const W = cv.clientWidth, H = cv.clientHeight, dpr = window.devicePixelRatio || 1;
  if (cv.width !== Math.round(W * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  if (!S || !S.faces.length) return;
  const nw = cam.naturalWidth || 4, nh = cam.naturalHeight || 3, sc = Math.min(W / nw, H / nh);
  const rw = nw * sc, rh = nh * sc, ox = (W - rw) / 2, oy = (H - rh) / 2;
  const col = S.status === "spotted" || S.status === "snapping" ? "#ffc83d" : S.watching ? "#3ddc84" : "#5ab8ff";
  S.faces.forEach(f => {
    const x = ox + f.x * rw, y = oy + f.y * rh, w = f.w * rw, h = f.h * rh;
    const pad = Math.max(4, w * 0.15) + (S.status === "spotted" ? Math.sin(t / 120) * 3 : 0);
    const L = Math.max(8, w * 0.3);
    ctx.save(); ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.shadowColor = col; ctx.shadowBlur = 10;
    [[x - pad, y - pad, 1, 1], [x + w + pad, y - pad, -1, 1], [x + w + pad, y + h + pad, -1, -1], [x - pad, y + h + pad, 1, -1]].forEach(([cx, cy, sx, sy]) => {
      ctx.beginPath(); ctx.moveTo(cx + sx * L, cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy + sy * L); ctx.stroke();
    });
    ctx.restore();
  });
}
requestAnimationFrame(draw);

// ---------- gallery ----------
function when(name) {
  const m = name.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})/);
  if (!m) return name;
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
  return d.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
const url = (p, face) => "/facecam/photos/" + (face && p.face ? p.name.replace(/\.jpg$/, "_face.jpg") : p.name);
function renderGallery(photos, firstLoad) {
  const key = photos.map(p => p.name).join("|");
  if (key === shown.map(p => p.name).join("|")) return;
  const old = new Set(shown.map(p => p.name));
  shown = photos;
  $("#sub").textContent = S.count > photos.length ? "newest " + photos.length + " of " + S.count : "";
  $("#clear").hidden = !photos.length;
  const grid = $("#grid");
  grid.innerHTML = "";
  if (!photos.length) {
    grid.innerHTML = '<div class="empty">No photos yet. Press <b>Start watching</b> and walk in front of the rover.</div>';
    return;
  }
  photos.forEach((p, i) => {
    const d = document.createElement("div");
    d.className = "th" + (!firstLoad && !old.has(p.name) ? " new" : "");
    const im = document.createElement("img"); im.loading = "lazy"; im.alt = "photo"; im.src = url(p, true);
    const s = document.createElement("span"); s.textContent = when(p.name);
    d.append(im, s);
    d.onclick = () => openBox(i);
    grid.appendChild(d);
  });
  if (boxIdx >= 0) boxIdx = Math.min(boxIdx, photos.length - 1);
}

// ---------- big view ----------
function openBox(i) { boxIdx = i; boxFace = shown[i].face; showBox(); $("#box").hidden = false; }
function showBox() {
  const p = shown[boxIdx];
  if (!p) { $("#box").hidden = true; boxIdx = -1; return; }
  $("#boxImg").src = url(p, boxFace);
  $("#boxWhen").textContent = when(p.name) + (p.face ? "" : " · no close-up (no face found)");
  $("#showFace").hidden = !p.face;
  $("#showFace").classList.toggle("sel", boxFace && p.face);
  $("#showFull").classList.toggle("sel", !boxFace || !p.face);
  const dl = $("#dl"); dl.href = url(p, boxFace); dl.download = (boxFace && p.face ? p.name.replace(/\.jpg$/, "_face.jpg") : p.name);
}
$("#showFace").onclick = () => { boxFace = true; showBox(); };
$("#showFull").onclick = () => { boxFace = false; showBox(); };
$("#prev").onclick = () => { if (boxIdx > 0) { boxIdx--; showBox(); } };
$("#next").onclick = () => { if (boxIdx < shown.length - 1) { boxIdx++; showBox(); } };
$("#close").onclick = () => { $("#box").hidden = true; boxIdx = -1; };
$("#box").addEventListener("click", e => { if (e.target.id === "box") $("#close").onclick(); });
$("#del").onclick = () => {
  const p = shown[boxIdx];
  if (p && confirm("Delete this photo?")) post("/facecam/delete", { name: p.name }).then(() => { shown = []; poll(); });
};
document.addEventListener("keydown", e => {
  if ($("#box").hidden) return;
  if (e.key === "Escape") $("#close").onclick();
  if (e.key === "ArrowLeft") $("#prev").onclick();
  if (e.key === "ArrowRight") $("#next").onclick();
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

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/facecam"):
            self._send(200, "text/html", PAGE.encode("utf-8"))
        elif path == "/facecam/state":
            self._send(200, "application/json", json.dumps(cam.state()).encode())
        elif path.startswith("/facecam/photos/"):
            name = path[len("/facecam/photos/"):]
            try:
                if not NAME_OK.match(name):
                    raise FileNotFoundError
                with open(os.path.join(PHOTOS, name), "rb") as f:
                    self._send(200, "image/jpeg", f.read())
            except FileNotFoundError:
                self.send_error(404)
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
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "drive" and parts[1] in ("forward", "backward", "left", "right", "stop"):
            drive.go(parts[1])
            self.send_response(204); self.end_headers()
            return
        if len(parts) == 2 and parts[0] == "speed" and parts[1] in SPEEDS:
            drive.set_speed(parts[1])
            self.send_response(204); self.end_headers()
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            if path == "/facecam/watch":
                cam.watching = bool(body.get("on"))
                cam.streak, cam.wait_gone = 0, False
                res = {"ok": True}
            elif path == "/facecam/snap":
                name = cam.take("button")
                res = {"ok": bool(name), "name": name}
            elif path == "/facecam/delete":
                res = {"ok": cam.delete(str(body.get("name", "")))}
            elif path == "/facecam/delete_all":
                for name in cam.photos():
                    cam.delete(name)
                res = {"ok": True}
            else:
                self.send_error(404)
                return
            self._send(200, "application/json", json.dumps(res).encode())
        except Exception as e:
            self._send(400, "application/json", json.dumps({"ok": False, "why": str(e)}).encode())


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
cam = FaceCam(lambda: output.frame if output else None)
threading.Thread(target=cam.loop, daemon=True).start()
try:
    httpd = Server(("", PORT), Handler)
except OSError:
    print(f"Port {PORT} is busy: another program (probably robot_drive.py) is already running.")
    print("Stop it first:  sudo systemctl stop robot-drive   (or close it in Thonny), then press Run again.")
    raise SystemExit
print()
print("FACE CAM ROVER IS RUNNING. Open this on your PC or phone (same Wi-Fi):")
print(f"    http://{my_address()}:{PORT}")
print(f"    http://{socket.gethostname()}.local:{PORT}")
print(f"Drive: arrow keys or W A S D (let go to stop). Photos go to {PHOTOS}.")
print("Press the red Stop button in Thonny to quit.")
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
    print("Face Cam stopped.")
