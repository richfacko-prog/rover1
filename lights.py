"""
Lights and horn for the rover (Armored Rover body).

  Headlights (2 white LEDs)   on/off with the L key or the Lights button (on when the rover starts)
  Taillights (2 red LEDs)     dim while driving, BRIGHT when braking or reversing,
                              the left/right one BLINKS while turning (turn signals)
  Horn (active buzzer module) hold H or the Horn button; beeps by itself while reversing

Wiring (Pi physical pins; each LED: long leg = +, through its resistor):
  Headlights  pin 36 (GPIO 16) -> 33 ohm -> white LED + ; same for the 2nd white LED ; both LED - -> GND (pin 34)
  Left tail   pin 38 (GPIO 20) -> 150 ohm -> red LED + ; LED - -> GND (pin 39)
  Right tail  pin 40 (GPIO 21) -> 150 ohm -> red LED + ; LED - -> GND (pin 39)
  Horn module VCC -> 3.3 V (pin 17), GND -> pin 30, I/O (or S) -> pin 37 (GPIO 26)
Pins can be changed in ~/rover.json (HEADLIGHT_GPIO, TAIL_LEFT_GPIO, TAIL_RIGHT_GPIO, HORN_GPIO).
If the horn is on all the time and goes quiet when "on", set "HORN_ACTIVE_HIGH": false.

robot_drive.py loads this file. If anything here fails, driving still works.
"""
import threading
import time

from rover_config import CFG

TAIL_DIM = 0.25          # taillight brightness while driving / parked with headlights on
BRAKE_S = 0.8            # brake lights stay bright this long after stopping
BLINK_HZ = 2.5           # turn signal speed
HORN_HOLD_S = 0.4        # horn stops if the page stops saying "still pressed" (key released, tab closed)
REVERSE_BEEP = (0.35, 0.35)   # on, off seconds while backing up


class Lights:
    def __init__(self):
        self.ok = False
        self.head_on = True
        self.horn_until = 0.0
        self.get_cmd = lambda: "stop"
        self.lock = threading.Lock()
        if not CFG.get("LIGHTS", True):
            return
        try:
            from gpiozero import LED, PWMLED, OutputDevice
            self.head = LED(CFG["HEADLIGHT_GPIO"])
            self.tail_l = PWMLED(CFG["TAIL_LEFT_GPIO"])
            self.tail_r = PWMLED(CFG["TAIL_RIGHT_GPIO"])
            self.horn = OutputDevice(CFG["HORN_GPIO"], active_high=CFG.get("HORN_ACTIVE_HIGH", True))
            self.ok = True
        except Exception as e:
            print(f"Lights/horn not available ({e}). Driving still works.")

    def attach(self, get_cmd):
        self.get_cmd = get_cmd
        if self.ok:
            threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        last_cmd, stopped_at, back_since = "stop", 0.0, None
        while True:
            now = time.monotonic()
            cmd = self.get_cmd()
            if cmd == "stop" and last_cmd != "stop":
                stopped_at = now                                  # just stopped: brake lights
            if cmd == "backward" and back_since is None:
                back_since = now
            if cmd != "backward":
                back_since = None
            last_cmd = cmd
            blink = int(now * BLINK_HZ * 2) % 2 == 0
            braking = now - stopped_at < BRAKE_S or cmd == "backward"
            base = 1.0 if braking else (TAIL_DIM if (self.head_on or cmd != "stop") else 0.0)
            left = base if cmd != "left" else (1.0 if blink else 0.0)
            right = base if cmd != "right" else (1.0 if blink else 0.0)
            on, off = REVERSE_BEEP
            beep = back_since is not None and (now - back_since) % (on + off) < on
            with self.lock:
                honk = now < self.horn_until
                self.head.value = self.head_on
            self.tail_l.value = left
            self.tail_r.value = right
            self.horn.value = honk or beep
            time.sleep(0.03)

    def toggle_head(self):
        with self.lock:
            self.head_on = not self.head_on

    def honk(self, on):
        with self.lock:
            self.horn_until = time.monotonic() + HORN_HOLD_S if on else 0.0

    def state(self):
        return {"lights": self.ok, "headlights": self.head_on}

    def off(self):
        if self.ok:
            for d in (self.head, self.tail_l, self.tail_r, self.horn):
                d.off()


lights = Lights()


def handle_post(h, path):
    """POST /lights/toggle, /horn/on (repeat while held), /horn/off."""
    if path == "/lights/toggle":
        lights.toggle_head()
    elif path == "/horn/on":
        lights.honk(True)
    elif path == "/horn/off":
        lights.honk(False)
    else:
        return False
    h.send_response(204)
    h.end_headers()
    return True
