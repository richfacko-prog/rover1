"""
Face Cam: park the rover and it takes a photo whenever someone's face is in view.

Page: http://<rover>.local:8000/facecam  (start / stop, live view with face boxes, photo gallery)
Photos: ~/face_photos on the Pi, two files per photo:
    2026-11-07_14-03-22.jpg        the whole picture
    2026-11-07_14-03-22_face.jpg   zoomed in on the face(s), since people are usually far away

How it works
  - The camera can't aim, so the rover just watches what's in front of it.
  - Several times a second it looks for faces. Small (far away) faces are found by
    enlarging the picture first, so it sees people up to about 3-4 m away.
  - A face has to show up in 3 checks in a row (about 1 second): no photos of random shadows.
  - Then it watches for 1 more second and keeps the sharpest frame with the biggest face.
  - After a photo it waits until the person has left (or a minute has passed) before taking
    another one of the same person.

robot_drive.py loads this file. If anything here fails, driving still works.
Needs OpenCV: sudo apt install -y python3-opencv (the rover updater installs it by itself).
Change settings in ~/rover.json, e.g. {"FACECAM": {"COOLDOWN_S": 5, "START_WATCHING": true}}
"""

import datetime
import json
import os
import re
import threading
import time

from rover_config import CFG

try:
    import cv2
    import numpy as np
except Exception as e:          # OpenCV missing: the page explains, driving still works
    cv2 = None
    print(f"Face Cam: OpenCV not available ({e}). Install it: sudo apt install -y python3-opencv")

HERE = os.path.dirname(os.path.abspath(__file__))
PHOTOS = os.path.expanduser("~/face_photos")

SETTINGS = {
    "CHECK_EVERY_S": 0.25,   # how often it looks for faces
    "CONFIRM": 3,            # checks in a row with a face before it counts
    "BURST_S": 1.0,          # after that, watch this long and keep the best frame
    "COOLDOWN_S": 8,         # at least this long between photos
    "GONE_S": 3,             # same person: wait until nobody's been seen this long...
    "REPEAT_S": 60,          # ...or this long has passed, whichever comes first
    "FAR": True,             # also look for small, far-away faces (uses more CPU)
    "MAX_PHOTOS": 500,       # oldest photos are deleted beyond this
    "START_WATCHING": False, # start watching as soon as the rover boots
}
SETTINGS.update(CFG.get("FACECAM") or {})
S = SETTINGS
NAME_OK = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}(-\d+)?(_face)?\.jpg$")


def load_detector():
    """Bundled detector first (no extra install), then OpenCV's own files if they're there."""
    if cv2 is None:
        return None, None
    for path in (os.path.join(HERE, "models", "lbpcascade_frontalface.xml"),
                 "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
                 "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"):
        if os.path.exists(path):
            c = cv2.CascadeClassifier(path)
            if not c.empty():
                return c, os.path.basename(path)
    return None, None


class FaceCam:
    def __init__(self):
        self.lock = threading.Lock()
        self.get_frame = lambda: None
        self.detector, self.detector_name = load_detector()
        self.watching = bool(S["START_WATCHING"])
        self.viewed = 0.0                 # last time the page asked (live boxes even when not watching)
        self.faces, self.faces_t = [], 0.0
        self.status = "off"
        self.streak = 0
        self.last_face = 0.0
        self.last_shot = 0.0
        self.wait_gone = False
        self.busy = False                 # taking a photo right now
        self.seq = 0                      # goes up by one per photo (the page flashes)
        self.last_name = None
        os.makedirs(PHOTOS, exist_ok=True)

    # ----- finding faces -----
    def detect(self, jpg):
        """(faces as (x, y, w, h) pixels, colour image, grey image) or None."""
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        grey = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        found = self.detector.detectMultiScale(grey, 1.1, 4, minSize=(24, 24))
        faces = [tuple(int(v) for v in f) for f in found]
        if not faces and S["FAR"]:
            # far away: faces are tiny, so look at the picture twice as big
            big = cv2.resize(grey, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
            found = self.detector.detectMultiScale(big, 1.1, 5, minSize=(24, 24))
            faces = [tuple(int(v / 2) for v in f) for f in found]
        return faces, img, grey

    def loop(self):
        last = None
        while True:
            t0 = time.monotonic()
            active = self.watching or t0 - self.viewed < 5
            if self.detector is None:
                self.status = "no-opencv" if cv2 is None else "no-detector"
                time.sleep(1)
                continue
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
            now = time.monotonic()
            with self.lock:
                self.faces = [{"x": x / w, "y": y / h, "w": fw / w, "h": fh / h} for x, y, fw, fh in faces]
                self.faces_t = time.time()
            if self.watching:
                self.decide(bool(faces), now)
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
                self.wait_gone = False                    # they left: the next face is a new photo
        cooling = now - self.last_shot < S["COOLDOWN_S"]
        same_person = self.wait_gone and now - self.last_shot < S["REPEAT_S"]
        if cooling:
            self.status = "cooldown"
        elif same_person:
            self.status = "waiting"                       # already got this person
        elif self.streak >= S["CONFIRM"] and self.claim():
            self.status = "snapping"
            threading.Thread(target=self._take, args=("face",), daemon=True).start()
        elif seen:
            self.status = "spotted"
        else:
            self.status = "watching"

    # ----- taking the photo -----
    def claim(self):
        """Only one photo at a time."""
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
                if time.monotonic() > end + 2:            # camera stalled
                    break
                time.sleep(0.04)
            if best is None:
                return None
            frame, faces, img = best
            if reason == "face" and not faces:
                return None                               # they walked away during the burst
            name = self.save(frame, faces, img)
            now = time.monotonic()
            self.last_shot = now
            self.wait_gone = reason == "face"
            self.streak = 0
            with self.lock:
                self.seq += 1
                self.last_name = name
            print(f"Face Cam: saved {name} ({len(faces)} face{'s' if len(faces) != 1 else ''})")
            return name
        finally:
            self.busy = False

    def save(self, frame, faces, img):
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name, n = stamp, 1
        while os.path.exists(os.path.join(PHOTOS, name + ".jpg")):
            n += 1
            name = f"{stamp}-{n}"
        def put(fname, data):                             # write whole, then show it (no half files)
            tmp = os.path.join(PHOTOS, "." + fname + ".tmp")
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, os.path.join(PHOTOS, fname))
        if faces and img is not None:                     # close-up first: the gallery lists the photo
            ok, zoom = cv2.imencode(".jpg", self.zoom(img, faces), [cv2.IMWRITE_JPEG_QUALITY, 92])
            if ok:
                put(name + "_face.jpg", zoom.tobytes())
        put(name + ".jpg", frame)                         # the whole picture, untouched
        self.prune()
        return name + ".jpg"

    @staticmethod
    def zoom(img, faces):
        """Head-and-shoulders crop around every face, enlarged so it's nice to look at."""
        H, W = img.shape[:2]
        x0 = min(x - 0.9 * w for x, y, w, h in faces)
        x1 = max(x + 1.9 * w for x, y, w, h in faces)
        y0 = min(y - 0.6 * h for x, y, w, h in faces)
        y1 = max(y + 2.0 * h for x, y, w, h in faces)
        # make it 3:4 (portrait) around the centre so every zoom looks the same shape
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        cw, ch = x1 - x0, y1 - y0
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
            crop = cv2.addWeighted(crop, 1.5, soft, -0.5, 0)   # a little sharpening
        return crop

    def prune(self):
        names = self.photos()
        for old in names[S["MAX_PHOTOS"]:]:
            self.delete(old)

    # ----- gallery -----
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
            return {
                "watching": self.watching, "status": self.status,
                "faces": self.faces if fresh else [],
                "detector": self.detector_name, "opencv": cv2 is not None,
                "seq": self.seq, "last": self.last_name, "count": len(names),
                "photos": [{"name": n, "face": os.path.exists(os.path.join(PHOTOS, n[:-4] + "_face.jpg"))}
                           for n in names[:120]],
                "cooldown": round(max(0.0, S["COOLDOWN_S"] - (time.monotonic() - self.last_shot)), 1),
                "name": CFG["NAME"],
            }


cam = FaceCam()


# ---------------------------------------------------------------------------
# HTTP: robot_drive.py calls these from its request handler
# ---------------------------------------------------------------------------
def attach(get_frame):
    """Give Face Cam the camera's latest JPEG frame (called once the camera is running)."""
    cam.get_frame = get_frame
    threading.Thread(target=cam.loop, daemon=True).start()


def handle_get(h, path, query):
    if path == "/facecam":
        with open(os.path.join(HERE, "facecam.html"), encoding="utf-8") as f:
            h._send(200, "text/html", f.read().encode("utf-8"))
    elif path == "/facecam/state":
        h._send(200, "application/json", json.dumps(cam.state()).encode())
    elif path.startswith("/facecam/photos/"):
        name = path[len("/facecam/photos/"):]
        if not NAME_OK.match(name):
            h.send_error(404)
            return True
        try:
            with open(os.path.join(PHOTOS, name), "rb") as f:
                data = f.read()
        except FileNotFoundError:
            h.send_error(404)
            return True
        h._send(200, "image/jpeg", data)
    else:
        return False
    return True


def handle_post(h, path):
    if not path.startswith("/facecam/"):
        return False
    try:
        n = int(h.headers.get("Content-Length") or 0)
        body = json.loads(h.rfile.read(n) or b"{}") if n else {}
        if path == "/facecam/watch":
            cam.watching = bool(body.get("on"))
            cam.streak, cam.wait_gone = 0, False
            res = {"ok": True, "watching": cam.watching}
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
            h.send_error(404)
            return True
        h._send(200, "application/json", json.dumps(res).encode())
    except Exception as e:
        h._send(400, "application/json", json.dumps({"ok": False, "why": str(e)}).encode())
    return True
