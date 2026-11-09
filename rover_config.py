"""
Per-rover settings, shared by every program in this repo.

Both rovers run the SAME code from GitHub. Anything that's different between them
(name, which wheels are flipped, camera speed...) lives in a small file on each Pi:

    ~/rover.json        (in the user's home folder, NOT in the repo, so updates never wipe it)

Only put in the settings you want to change. Example for the Pi 3 rover:

    {"NAME": "Rover 2", "COLOR": "#3b82f6", "VIDEO_FPS": 15}

If ~/rover.json doesn't exist, the defaults below are used (they match Rover 1).
"""
import json
import os
import socket

PATH = os.path.expanduser("~/rover.json")

DEFAULTS = {
    "NAME": socket.gethostname(),   # shown on the web page
    "COLOR": "#22aa77",             # accent colour on the split-screen page
    # motor wiring: L298N IN1..IN4 = GPIO 17, 18, 22, 23 (pins 11, 12, 15, 16)
    "FLIP_LEFT": False,             # True if BOTH left wheels spin backward
    "FLIP_RIGHT": True,             # True if BOTH right wheels spin backward
    "SWAP_SIDES": False,            # True if the left/right wire bundles are swapped
    # distance sensor
    "TRIG_GPIO": 5,                 # pin 29
    "ECHO_GPIO": 6,                 # pin 31
    # camera
    "VIDEO_SIZE": [640, 480],
    "VIDEO_FPS": 24,                # Pi 3: 15 keeps two streams smooth on the same Wi-Fi
    "FLIP_CAMERA": False,           # True if the picture is upside down
    # tilt servo (SG90 on tilt_mount): yellow -> pin 32 (GPIO 12)
    "USE_TILT": False,
    "TILT_GPIO": 12,
    "TILT_CENTER_US": 1450,
    "TILT_MIN_US": 1100,
    "TILT_MAX_US": 1800,
    # split-screen page (http://<any rover>.local:8000/fleet): which rovers to show, left to right
    "FLEET": ["richardfacko.local", "rover2.local"],
    # Arena games (arena.py)
    "MARKER_ID": None,              # printed marker this rover wears; None = its place in FLEET (1, 2)
    "ARENA": {},                    # game setting changes, e.g. {"HP": 15, "CLUE_EVERY_S": 45}
    # Face Cam (facecam.py)
    "FACECAM": {},                  # e.g. {"COOLDOWN_S": 5, "START_WATCHING": true}
}


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(PATH) as f:
            user = json.load(f)
        for k, v in user.items():
            if k.upper() in DEFAULTS:
                cfg[k.upper()] = v
            else:
                print(f"rover.json: unknown setting '{k}' ignored")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"rover.json could not be read ({e}), using defaults")
    return cfg


def save(changes):
    """Merge `changes` into ~/rover.json (used by calibrate.py)."""
    try:
        with open(PATH) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.update(changes)
    with open(PATH, "w") as f:
        json.dump(data, f, indent=2)
    return PATH


def motor_pins(cfg):
    """((left_fwd, left_back), (right_fwd, right_back)) as GPIO numbers."""
    left, right = ((22, 23), (17, 18)) if cfg["SWAP_SIDES"] else ((17, 18), (22, 23))
    if cfg["FLIP_LEFT"]:
        left = left[::-1]
    if cfg["FLIP_RIGHT"]:
        right = right[::-1]
    return left, right


CFG = load()
