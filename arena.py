"""
Robot Arena: camera games for the rovers (no extra electronics needed).

Each rover wears a printed ArUco marker (print them from http://<rover>.local:8000/markers).
The camera looks for the OTHER rover's marker, and everything in the games comes from that:

  Laser Battle   aim the crosshair at the other rover's marker and fire. 10 HP each.
  Manhunt        one rover hides, the other seeks. Every minute the hider's camera sends a
                 photo clue to the hunter. Get close enough to see the hider's marker for
                 1 second to catch it.
  Treasure Hunt  find printed treasure markers (IDs 10-19) hidden around the house.

The page is http://<rover>.local:8000/arena. Play on one PC (split screen, keyboard)
or on two phones (one per player). The FIRST rover in the list runs the game (the "host"),
so every phone and PC sees the same game, whichever rover's page it opened.

robot_drive.py loads this file. If anything here fails, driving still works.
Needs OpenCV for the camera targeting: sudo apt install python3-opencv
(update.sh installs it automatically on the next update).
"""

import json
import os
import random
import socket
import threading
import time
import urllib.request
from collections import deque
from urllib.parse import parse_qs

from rover_config import CFG

try:
    import cv2
    import numpy as np
except Exception as e:          # OpenCV missing: games run, but nothing gets detected
    cv2 = None
    print(f"Arena: OpenCV not available ({e}). Camera targeting is off until it's installed:")
    print("       sudo apt install -y python3-opencv")

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8000

# ---------------------------------------------------------------------------
# GAME SETTINGS. Change any of them per rover in ~/rover.json, e.g.
#     {"ARENA": {"HP": 15, "CLUE_EVERY_S": 45}}
# (only the host rover's settings matter during a game)
# ---------------------------------------------------------------------------
SETTINGS = {
    "COUNTDOWN_S": 3,
    # Laser Battle
    "HP": 10,
    "AMMO": 12,
    "RELOAD_S": 3.0,
    "SHOT_GAP_S": 0.45,      # fastest you can fire
    "SHIELD_S": 3.0,
    "SHIELD_COOLDOWN_S": 15,
    "BATTLE_S": 180,         # round length; if time runs out, more HP wins
    "AIM_X": 0.16,           # how far from the centre a hit still counts (fraction of the picture)
    "AIM_Y": 0.24,
    "MIN_W": 0.035,          # marker must be at least this wide (fraction of the picture) = in range
    "CLOSE_W": 0.20,         # this wide or more = point-blank, 2 damage
    # Manhunt
    "HIDE_S": 120,           # head start
    "HUNT_S": 600,           # hunting time after the head start
    "CLUE_EVERY_S": 60,
    "CATCH_W": 0.15,         # hider's marker this big in the hunter's camera = close enough
    "CATCH_HOLD_S": 1.0,     # ...for this long
    "PINGS": 2,              # hunter: extra photo on demand
    "JAMS": 1,               # hider: scramble the next photo
    # Treasure Hunt
    "TREASURE_S": 300,
    "TREASURE_FIRST": 10,
    "TREASURE_COUNT": 10,    # IDs 10..19
    "TREASURE_W": 0.08,
    # camera
    "DETECT_FPS": 8,
}
SETTINGS.update(CFG.get("ARENA") or {})
S = SETTINGS
TREASURE_IDS = set(range(S["TREASURE_FIRST"], S["TREASURE_FIRST"] + S["TREASURE_COUNT"]))


def my_marker_id():
    """Marker this rover wears: MARKER_ID in rover.json, else its place in the FLEET list (1, 2...)."""
    if CFG.get("MARKER_ID"):
        return int(CFG["MARKER_ID"])
    me = socket.gethostname().lower()
    for i, h in enumerate(CFG["FLEET"]):
        name = h.split("//")[-1].split(":")[0].lower()
        if name in (me, me + ".local"):
            return i + 1
    return 1


MARKER_ID = my_marker_id()


# ---------------------------------------------------------------------------
# VISION: find markers in this rover's own camera picture
# ---------------------------------------------------------------------------
class Vision:
    def __init__(self):
        self.get_frame = lambda: None
        self.markers = []
        self.when = 0.0
        self.wanted = 0.0          # last time someone asked for markers (detection sleeps otherwise)
        self.status = "no-opencv" if cv2 is None else "starting"
        self.find = None
        if cv2 is not None:
            d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            try:                                           # OpenCV 4.7 and newer
                det = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())
                self.find = det.detectMarkers
            except AttributeError:                         # older OpenCV
                self.find = lambda g: cv2.aruco.detectMarkers(g, d)

    def start(self, get_frame):
        self.get_frame = get_frame
        if cv2 is not None:
            threading.Thread(target=self.loop, daemon=True).start()

    def want(self):
        self.wanted = time.monotonic()

    def detect(self, jpg):
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        h, w = img.shape[:2]
        corners, ids, _ = self.find(img)
        found = []
        if ids is not None:
            for c, i in zip(corners, ids.flatten()):
                p = c.reshape(4, 2)
                side = float(np.mean(np.linalg.norm(p - np.roll(p, 1, axis=0), axis=1)))
                cx, cy = p.mean(axis=0)
                found.append({"id": int(i), "x": round(float(cx) / w, 4),
                              "y": round(float(cy) / h, 4), "w": round(side / w, 4)})
        return found

    def loop(self):
        last = None
        gap = 1.0 / max(1, S["DETECT_FPS"])
        while True:
            t0 = time.monotonic()
            if t0 - self.wanted > 5:                       # nobody playing: save the CPU
                self.status = "idle"
                time.sleep(0.25)
                continue
            frame = self.get_frame()
            if frame is None:
                self.status = "no-camera"
            elif frame is not last:
                last = frame
                try:
                    found = self.detect(frame)
                    if found is not None:
                        self.markers, self.when, self.status = found, time.time(), "ok"
                except Exception as e:
                    self.status = f"error: {e}"
            time.sleep(max(0.01, gap - (time.monotonic() - t0)))

    def report(self):
        """Added to /status."""
        fresh = time.time() - self.when < 0.6
        return {"marker_id": MARKER_ID, "vision": self.status,
                "markers": self.markers if fresh else []}


vision = Vision()


# ---------------------------------------------------------------------------
# GAME HOST (only used on the rover that's first in the list)
# ---------------------------------------------------------------------------
def base_url(host):
    if host.startswith("http"):
        return host.rstrip("/")
    return "http://" + host + ("" if ":" in host else f":{PORT}")


def fetch(host, path, timeout=0.6):
    with urllib.request.urlopen(base_url(host) + path, timeout=timeout) as r:
        return r.read()


def new_player(slot, host):
    return {"slot": slot, "host": host, "name": host.split(".")[0], "color": "#888",
            "online": False, "marker_id": slot + 1, "markers": [], "seen": 0.0,
            "hp": S["HP"], "ammo": S["AMMO"], "reload_at": 0.0, "last_shot": 0.0,
            "shield_until": 0.0, "shield_ready": 0.0, "wins": 0, "score": 0}


class Game:
    def __init__(self):
        self.lock = threading.RLock()
        self.events = deque(maxlen=200)
        self.seq = 0
        self.gen = 0
        self.players = []
        self.mode, self.phase = "free", "idle"
        self.phase_end = None
        self.winner = None
        self.message = ""
        self.clues = []
        self.reset_round()
        threading.Thread(target=self.ticker, daemon=True).start()

    # ----- bookkeeping -----
    def reset_round(self):
        self.hunter = 0
        self.next_clue = None
        self.pings = S["PINGS"]
        self.jams = S["JAMS"]
        self.jam_armed = False
        self.catch_since = None
        self.catch_seen = 0.0
        self.catch_progress = 0.0
        self.claims = {}
        self.winner = None
        self.message = ""

    def event(self, kind, **kw):
        self.seq += 1
        self.events.append(dict(seq=self.seq, type=kind, t=time.time(), **kw))

    def set_phase(self, phase, length=None):
        self.phase = phase
        self.phase_end = None if length is None else time.monotonic() + length
        self.event("phase", phase=phase, mode=self.mode)

    def left(self):
        return None if self.phase_end is None else max(0.0, self.phase_end - time.monotonic())

    # ----- players: poll each rover's /status -----
    def set_rovers(self, hosts):
        hosts = [h.strip() for h in hosts if h and h.strip()][:2]
        if [p["host"] for p in self.players] == hosts:
            return
        self.gen += 1
        self.players = [new_player(i, h) for i, h in enumerate(hosts)]
        for p in self.players:
            threading.Thread(target=self.poller, args=(p, self.gen), daemon=True).start()

    def read_status(self, p, timeout=0.6):
        try:
            s = json.loads(fetch(p["host"], "/status?v=1", timeout))
            with self.lock:
                p.update(online=True, name=s.get("name", p["name"]), color=s.get("color", p["color"]),
                         marker_id=s.get("marker_id", p["marker_id"]), markers=s.get("markers", []),
                         seen=time.time())
        except Exception:
            with self.lock:
                if time.time() - p["seen"] > 2:
                    p["online"] = False
                    p["markers"] = []

    def poller(self, p, gen):
        while gen == self.gen:
            self.read_status(p)
            time.sleep(0.12)

    def other(self, slot):
        return self.players[1 - slot] if len(self.players) == 2 else None

    def sees(self, p, marker_id, min_w=0.0):
        """Biggest sighting of marker_id in p's camera, or None."""
        if time.time() - p["seen"] > 0.7:
            return None
        hits = [m for m in p["markers"] if m["id"] == marker_id and m["w"] >= min_w]
        return max(hits, key=lambda m: m["w"]) if hits else None

    # ----- starting and stopping -----
    def start(self, mode, hosts, opts):
        with self.lock:
            if hosts:
                self.set_rovers(hosts)
            if mode not in ("free", "battle", "manhunt", "treasure"):
                raise ValueError("unknown game")
            same = mode == self.mode
            self.mode = mode
            self.reset_round()
            self.clues = []
            for p in self.players:
                p.update(hp=S["HP"], ammo=S["AMMO"], reload_at=0.0, shield_until=0.0,
                         shield_ready=0.0, score=0)
                if not same:
                    p["wins"] = 0
            if mode == "manhunt":
                self.hunter = 1 if int(opts.get("hider", 0)) == 0 else 0
            self.event("start", mode=mode, hunter=self.hunter)
            if mode == "free":
                self.set_phase("idle")
            else:
                self.set_phase("countdown", S["COUNTDOWN_S"])

    def stop(self):
        with self.lock:
            self.mode = "free"
            self.reset_round()
            self.set_phase("idle")

    # ----- player actions -----
    def action(self, slot, what):
        with self.lock:
            if not (0 <= slot < len(self.players)):
                return {"ok": False, "why": "no such player"}
            if self.mode == "battle" and what == "fire":
                return self.fire(slot)
            if self.mode == "battle" and what == "shield":
                return self.shield(slot)
            if self.mode == "manhunt" and what == "ping":
                return self.ping(slot)
            if self.mode == "manhunt" and what == "jam":
                return self.jam(slot)
            return {"ok": False, "why": "not in this game"}

    def fire(self, slot):
        p, foe = self.players[slot], self.other(slot)
        now = time.monotonic()
        if self.phase != "play" or foe is None or p["hp"] <= 0:
            return {"ok": False}
        if p["ammo"] <= 0 or now - p["last_shot"] < S["SHOT_GAP_S"]:
            return {"ok": False, "why": "reloading" if p["ammo"] <= 0 else "too fast"}
        p["last_shot"] = now
        p["ammo"] -= 1
        if p["ammo"] == 0:
            p["reload_at"] = now + S["RELOAD_S"]
            self.event("reload", by=slot)
        # a fresh look through the shooter's camera (the background poll can be 0.1 s old)
        self.lock.release()
        try:
            self.read_status(p, timeout=0.35)
        finally:
            self.lock.acquire()
        m = self.sees(p, foe["marker_id"], S["MIN_W"])
        on_target = m and abs(m["x"] - 0.5) <= S["AIM_X"] and abs(m["y"] - 0.5) <= S["AIM_Y"]
        if not on_target:
            self.event("miss", by=slot)
            return {"ok": True, "hit": False}
        if now < foe["shield_until"]:
            self.event("blocked", by=slot, target=foe["slot"], x=m["x"], y=m["y"], w=m["w"])
            return {"ok": True, "hit": False, "blocked": True}
        dmg = 2 if m["w"] >= S["CLOSE_W"] else 1
        foe["hp"] = max(0, foe["hp"] - dmg)
        self.event("hit", by=slot, target=foe["slot"], dmg=dmg, x=m["x"], y=m["y"], w=m["w"],
                   hp=foe["hp"])
        if foe["hp"] == 0:
            self.finish(slot, "ko")
        return {"ok": True, "hit": True, "dmg": dmg}

    def shield(self, slot):
        p = self.players[slot]
        now = time.monotonic()
        if self.phase != "play" or now < p["shield_ready"] or p["hp"] <= 0:
            return {"ok": False}
        p["shield_until"] = now + S["SHIELD_S"]
        p["shield_ready"] = now + S["SHIELD_COOLDOWN_S"]
        self.event("shield", by=slot)
        return {"ok": True}

    def ping(self, slot):
        if slot != self.hunter or self.phase != "play" or self.pings <= 0:
            return {"ok": False}
        self.pings -= 1
        self.event("ping", by=slot)
        self.take_clue(asked=True)
        return {"ok": True}

    def jam(self, slot):
        if slot == self.hunter or self.phase not in ("hide", "play") or self.jams <= 0:
            return {"ok": False}
        self.jams -= 1
        self.jam_armed = True
        self.event("jam", by=slot)
        return {"ok": True}

    def finish(self, winner, why):
        self.winner = winner
        if winner is not None and winner < len(self.players):
            self.players[winner]["wins"] += 1
        self.set_phase("over")
        self.event("over", winner=winner, why=why, mode=self.mode)

    # ----- Manhunt photo clues -----
    def take_clue(self, asked=False):
        ghost = self.other(self.hunter)
        if ghost is None:
            return
        n = len(self.clues) + 1
        jammed = self.jam_armed
        self.jam_armed = False
        clue = {"n": n, "at": time.time(), "jammed": jammed, "jpg": None, "failed": False, "asked": asked}
        self.clues.append(clue)
        self.clues = self.clues[-30:]
        gen = self.gen

        def grab():
            try:
                jpg = None if jammed else fetch(ghost["host"], "/snapshot.jpg", timeout=2.5)
            except Exception:
                jpg = None
                clue["failed"] = True
            with self.lock:
                if gen != self.gen:
                    return
                clue["jpg"] = jpg
                self.event("clue", n=n, jammed=jammed, failed=clue["failed"], asked=asked,
                           ghost=ghost["slot"], hunter=self.hunter)
        threading.Thread(target=grab, daemon=True).start()

    def clue_jpg(self, n):
        with self.lock:
            for c in self.clues:
                if c["n"] == n:
                    return c["jpg"]
        return None

    # ----- the clock: runs 10 times a second -----
    def ticker(self):
        while True:
            time.sleep(0.1)
            try:
                with self.lock:
                    self.tick()
            except Exception as e:
                print("Arena tick error:", e)

    def tick(self):
        now = time.monotonic()
        left = self.left()
        if self.phase == "countdown" and left == 0:
            if self.mode == "manhunt":
                self.set_phase("hide", S["HIDE_S"])
            elif self.mode == "battle":
                self.set_phase("play", S["BATTLE_S"])
            else:
                self.set_phase("play", S["TREASURE_S"])
            return
        if self.mode == "battle" and self.phase == "play":
            for p in self.players:
                if p["ammo"] == 0 and p["reload_at"] and now >= p["reload_at"]:
                    p["ammo"], p["reload_at"] = S["AMMO"], 0.0
                    self.event("reloaded", by=p["slot"])
            if left == 0 and len(self.players) == 2:
                a, b = self.players
                self.finish(None if a["hp"] == b["hp"] else (0 if a["hp"] > b["hp"] else 1), "time")
        elif self.mode == "manhunt":
            self.tick_manhunt(now, left)
        elif self.mode == "treasure" and self.phase == "play":
            for p in self.players:
                for tid in sorted(TREASURE_IDS - set(self.claims)):
                    m = self.sees(p, tid, S["TREASURE_W"])
                    if m:
                        self.claims[tid] = p["slot"]
                        p["score"] += 1
                        self.event("treasure", by=p["slot"], id=tid, x=m["x"], y=m["y"], w=m["w"])
            if left == 0 or len(self.claims) == len(TREASURE_IDS):
                sc = [p["score"] for p in self.players]
                best = max(sc) if sc else 0
                tops = [i for i, s in enumerate(sc) if s == best]
                self.finish(tops[0] if len(tops) == 1 and best > 0 else None, "treasure")

    def tick_manhunt(self, now, left):
        if self.phase == "hide" and left == 0:
            self.set_phase("play", S["HUNT_S"])
            self.take_clue()                                # first clue right away
            self.next_clue = now + S["CLUE_EVERY_S"]
            return
        if self.phase != "play":
            return
        if self.next_clue and now >= self.next_clue:
            self.take_clue()
            self.next_clue = now + S["CLUE_EVERY_S"]
        hunter, ghost = self.players[self.hunter], self.other(self.hunter)
        if ghost is None:
            return
        m = self.sees(hunter, ghost["marker_id"], S["CATCH_W"])
        if m:
            self.catch_seen = now
            if self.catch_since is None:
                self.catch_since = now
                self.event("locking", by=self.hunter)
        elif self.catch_since is not None and now - self.catch_seen > 0.35:
            self.catch_since = None
        self.catch_progress = 0.0 if self.catch_since is None else \
            min(1.0, (now - self.catch_since) / S["CATCH_HOLD_S"])
        if self.catch_progress >= 1.0:
            hunter["score"] += 1
            self.finish(self.hunter, "caught")
        elif left == 0:
            ghost["score"] += 1
            self.finish(ghost["slot"], "escaped")

    # ----- what every page polls -----
    def snapshot(self, since):
        with self.lock:
            now = time.monotonic()
            players = []
            for p in self.players:
                players.append({
                    "slot": p["slot"], "host": p["host"], "name": p["name"], "color": p["color"],
                    "online": p["online"], "marker_id": p["marker_id"], "hp": p["hp"],
                    "ammo": p["ammo"], "reload": round(max(0.0, p["reload_at"] - now), 2) if p["ammo"] == 0 else 0,
                    "shield": round(max(0.0, p["shield_until"] - now), 2),
                    "shield_cd": round(max(0.0, p["shield_ready"] - now), 2),
                    "wins": p["wins"], "score": p["score"]})
            left = self.left()
            out = {
                "seq": self.seq, "mode": self.mode, "phase": self.phase,
                "left": None if left is None else round(left, 2),
                "winner": self.winner, "players": players,
                "settings": {k: S[k] for k in ("HP", "AMMO", "RELOAD_S", "SHOT_GAP_S", "SHIELD_S", "SHIELD_COOLDOWN_S",
                                               "AIM_X", "AIM_Y", "MIN_W", "CATCH_W", "CLUE_EVERY_S",
                                               "HIDE_S", "HUNT_S")},
                "manhunt": {
                    "hunter": self.hunter, "ghost": 1 - self.hunter,
                    "clues": [{"n": c["n"], "jammed": c["jammed"], "failed": c["failed"],
                               "ready": c["jpg"] is not None or c["jammed"] or c["failed"]}
                              for c in self.clues],
                    "next_clue": None if not self.next_clue or self.phase != "play"
                    else round(max(0.0, self.next_clue - now), 1),
                    "pings": self.pings, "jams": self.jams, "jam_armed": self.jam_armed,
                    "catch": round(self.catch_progress, 2)},
                "treasure": {"ids": sorted(TREASURE_IDS),
                             "claims": {str(k): v for k, v in self.claims.items()}},
                "events": [e for e in self.events if e["seq"] > since],
            }
            return out


game = Game()


# ---------------------------------------------------------------------------
# PRINTABLE MARKERS
# ---------------------------------------------------------------------------
def marker_png(marker_id, px=600):
    if cv2 is None:
        return None
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    inner = int(px * 0.8)
    try:
        img = cv2.aruco.generateImageMarker(d, marker_id, inner)
    except AttributeError:
        img = cv2.aruco.drawMarker(d, marker_id, inner)
    pad = (px - inner) // 2
    img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    ok, png = cv2.imencode(".png", img)
    return png.tobytes() if ok else None


def markers_page():
    if cv2 is None:
        return ("<p style='font-family:sans-serif'>Markers need OpenCV on this rover: "
                "<code>sudo apt install -y python3-opencv</code>, then reload.</p>")
    rovers = "".join(
        f"<div class=card><img src='/markers/{i}.png'><b>Rover marker {i}</b>"
        f"<span>{'Rover ' + str(i) + ' (' + h + ')' if h else ''}: print 3, stick on back, left and right</span></div>"
        for i, h in [(k + 1, CFG['FLEET'][k] if k < len(CFG['FLEET']) else '') for k in range(2)])
    treasure = "".join(f"<div class='card small'><img src='/markers/{i}.png'><b>Treasure {i}</b></div>"
                       for i in sorted(TREASURE_IDS))
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Arena markers</title><style>
body{{font-family:sans-serif;margin:16px;color:#111}} h1{{font-size:20px}} p{{max-width:700px}}
.grid{{display:flex;flex-wrap:wrap;gap:16px}} .card{{display:flex;flex-direction:column;align-items:center;
border:1px dashed #999;padding:8px;width:9cm;page-break-inside:avoid}} .card img{{width:8cm;height:8cm}}
.card span{{font-size:12px;color:#555;text-align:center}} .small{{width:6cm}} .small img{{width:5cm;height:5cm}}
@media print{{button{{display:none}}}}</style></head><body>
<h1>Robot Arena markers</h1>
<p>Print at 100% size. Keep the white border around each marker, it's part of it. Stick them flat
(cardboard backing helps). Rover markers: about 8 cm, on the back and both sides of each rover.
Treasure markers: hide them around the house, standing up at camera height.</p>
<button onclick="print()">Print</button>
<h2>Rovers</h2><div class=grid>{rovers}</div>
<h2>Treasure Hunt (IDs {min(TREASURE_IDS)}-{max(TREASURE_IDS)})</h2><div class=grid>{treasure}</div>
</body></html>"""


# ---------------------------------------------------------------------------
# HTTP: robot_drive.py calls these from its request handler
# ---------------------------------------------------------------------------
def attach(get_frame):
    """Give the arena the camera's latest JPEG frame (called once the camera is running)."""
    vision.start(get_frame)


def status_extra(query):
    if "v" in parse_qs(query):
        vision.want()
    return vision.report()


def arena_page():
    with open(os.path.join(HERE, "arena.html"), encoding="utf-8") as f:
        html = f.read()
    return (html.replace("__DEFAULT_LIST__", json.dumps(CFG["FLEET"]))
                .replace("__PORT__", str(PORT)))


def handle_get(h, path, query):
    """True if this was an arena page; h is the BaseHTTPRequestHandler."""
    if path == "/arena":
        h._send(200, "text/html", arena_page().encode("utf-8"))
    elif path == "/markers":
        h._send(200, "text/html", markers_page().encode("utf-8"))
    elif path.startswith("/markers/") and path.endswith(".png"):
        try:
            png = marker_png(int(path[9:-4]))
        except ValueError:
            png = None
        if png:
            h._send(200, "image/png", png)
        else:
            h.send_error(404)
    elif path == "/snapshot.jpg":
        frame = vision.get_frame()
        if frame is None:
            h.send_error(503, "camera not working")
        else:
            h._send(200, "image/jpeg", frame)
    elif path == "/game/state":
        try:
            since = int(parse_qs(query).get("since", ["0"])[0])
        except ValueError:
            since = 0
        h._send(200, "application/json", json.dumps(game.snapshot(since)).encode())
    elif path.startswith("/game/clue/") and path.endswith(".jpg"):
        try:
            jpg = game.clue_jpg(int(path[11:-4]))
        except ValueError:
            jpg = None
        if jpg:
            h._send(200, "image/jpeg", jpg)
        else:
            h.send_error(404)
    else:
        return False
    return True


def handle_post(h, path):
    if not path.startswith("/game/"):
        return False
    try:
        n = int(h.headers.get("Content-Length") or 0)
        body = json.loads(h.rfile.read(n) or b"{}") if n else {}
        if path == "/game/start":
            game.start(body.get("mode", "free"), body.get("rovers") or [], body.get("options") or {})
            res = {"ok": True}
        elif path == "/game/stop":
            game.stop()
            res = {"ok": True}
        elif path == "/game/action":
            res = game.action(int(body.get("player", -1)), str(body.get("action", "")))
        elif path == "/game/rovers":
            with game.lock:
                game.set_rovers(body.get("rovers") or [])
            res = {"ok": True}
        else:
            h.send_error(404)
            return True
        h._send(200, "application/json", json.dumps(res).encode())
    except Exception as e:
        h._send(400, "application/json", json.dumps({"ok": False, "why": str(e)}).encode())
    return True
