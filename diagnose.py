"""
ROVER SENSOR DIAGNOSTIC
Open in Thonny and press Run. Read the "WHAT'S WRONG" section at the end.

Before running:
  - Trig -> pin 29, Echo -> resistors -> pin 31 (2k to pin 20), VCC -> pin 2, GND -> pin 9.
  - Point the sensor at a wall or box about 30-100 cm away.
  - The motors won't move during this test.
"""
from gpiozero import Device, DigitalOutputDevice, DigitalInputDevice
from time import sleep, time

# BCM GPIO number -> physical pin number on the header
PIN = {2: 3, 3: 5, 4: 7, 17: 11, 27: 13, 22: 15, 10: 19, 9: 21, 11: 23, 5: 29,
       6: 31, 13: 33, 19: 35, 26: 37, 14: 8, 15: 10, 18: 12, 23: 16, 24: 18,
       25: 22, 8: 24, 7: 26, 12: 32, 16: 36, 20: 38, 21: 40}
MOTOR = {17, 18, 22, 23}                       # used by the L298N, left alone
TRIG, ECHO = 5, 6                              # pin 29 and pin 31 
problems = []


def p(gpio):
    return f"pin {PIN[gpio]}"


def state(gpio):
    """How a pin behaves with nothing driving it: 'floating', 'held LOW' or 'held HIGH'."""
    d = DigitalInputDevice(gpio, pull_up=False); sleep(0.01); down = d.value; d.close()
    u = DigitalInputDevice(gpio, pull_up=True); sleep(0.01); up = u.value; u.close()
    if down == 0 and up == 1:
        return "floating"
    return "held LOW" if up == 0 else "held HIGH"


def listen_everywhere(trig_gpio, tries=5):
    """Pulse trig_gpio and watch every other free pin for an echo. Returns {gpio: hits}."""
    watch = [g for g in PIN if g not in MOTOR and g != trig_gpio and g not in (2, 3)]
    ins = {g: DigitalInputDevice(g, pull_up=False) for g in watch}
    trig = DigitalOutputDevice(trig_gpio)
    hits = {}
    for _ in range(tries):
        base = {g: d.value for g, d in ins.items()}
        trig.on(); sleep(0.0001); trig.off()
        t0 = time()
        while time() - t0 < 0.04:
            for g, d in ins.items():
                if base[g] == 0 and d.value:
                    hits[g] = hits.get(g, 0) + 1
                    base[g] = 1
        sleep(0.1)
    trig.close()
    for d in ins.values():
        d.close()
    return hits


print("=" * 50)
print("ROVER SENSOR DIAGNOSTIC")
print("=" * 50)

# 1. GPIO library
print("\n[1] Checking the Pi's pin system...")
try:
    DigitalInputDevice(ECHO).close()
    print("    OK, pin system working:", type(Device.pin_factory).__name__)
except Exception as e:
    print("    PROBLEM:", e)
    problems.append("The Pi's pin system isn't working. Restart the Pi and try again.")

# 2. Is anything actually connected to the trig and echo pins?
print("\n[2] Checking what is plugged into", p(TRIG), "(Trig) and", p(ECHO), "(Echo)...")
t_state, e_state = state(TRIG), state(ECHO)
print(f"    {p(TRIG)} (Trig): {t_state}")
print(f"    {p(ECHO)} (Echo): {e_state}")
if t_state == "held LOW":
    print(f"    -> WARNING: {p(TRIG)} (Trig) is held LOW. It may be touching ground, or the pin may be damaged.")
    problems.append(f"{p(TRIG)} (Trig) is held LOW: its wire is touching ground, or the pin is damaged. Run the pin test below.")
if e_state == "floating":
    print(f"    -> Nothing seems connected to {p(ECHO)}.")
elif e_state == "held LOW":
    print(f"    -> Good: {p(ECHO)} is connected to something (the resistors or the sensor's Echo).")
else:
    print(f"    -> {p(ECHO)} is stuck HIGH: it might be touching a power wire.")
    problems.append(f"{p(ECHO)} is stuck HIGH. Its wire may be on a power pin or touching VCC. Check the Echo wiring.")

# 3. Send pings and listen on EVERY free pin
print("\n[3] Sending pings and listening on every pin (about 2 seconds)...")
hits = listen_everywhere(TRIG)
if hits:
    for g, n in sorted(hits.items(), key=lambda kv: -kv[1]):
        print(f"    Echo heard on {p(g)}: {n}/5 times")
else:
    print("    No echo heard on ANY pin.")

# 4. Try the trigger on the old/other pin too, in case Trig is plugged in somewhere else
other_trig = []
if not hits:
    print("\n[4] Checking whether Trig is plugged into a different pin...")
    for g in (24, 25, 27, 4, 26):
        if g == TRIG or state(g) == "held LOW":
            continue
        h = listen_everywhere(g, tries=3)
        if h:
            other_trig.append((g, h))
            print(f"    Pinging from {p(g)} WORKS, echo heard on: " + ", ".join(p(x) for x in h))
    if not other_trig:
        print("    No other pin worked as Trig either.")

# 5. Verdict
print("\n" + "=" * 50)
print("WHAT'S WRONG")
print("=" * 50)
if hits.get(ECHO, 0) >= 3:
    print(f"NOTHING! The sensor works on {p(TRIG)} / {p(ECHO)}.")
    print("robot.py should work now. If it doesn't, tell Claude.")
elif hits:
    best = max(hits, key=hits.get)
    print(f"The echo is arriving on {p(best)}, NOT {p(ECHO)}.")
    print(f"-> Move the wire that is on {p(best)} over to {p(ECHO)}.")
    print("   (You probably counted one pin off, or used the wrong row.)")
elif other_trig:
    g, h = other_trig[0]
    print(f"Your Trig wire is on {p(g)}, not {p(TRIG)}.")
    print(f"-> Move the Trig wire from {p(g)} to {p(TRIG)}.")
    if ECHO not in h:
        print(f"   The echo also comes in on {', '.join(p(x) for x in h)}: move that wire to {p(ECHO)}.")
else:
    for msg in problems:
        print("-", msg)
    if e_state == "floating":
        print(f"- {p(ECHO)} has NOTHING connected. The Echo path isn't reaching the Pi:")
        print(f"    * Is the wire really on {p(ECHO)}?")
        print("    * On the breadboard, is that wire in the SAME row where the two resistors meet?")
        print("    * Try a different jumper wire for that connection.")
    print("- The sensor never answered on any pin. The sensor isn't powered, or Trig isn't reaching it:")
    print("    * VCC must be on pin 2 or 4 (5V). GND on pin 6, 9, 14, 20 or 25.")
    print("    * Try different jumper wires for VCC and GND. Broken jumper wires are common.")
    print("    * Make sure the wires are on the sensor's pins, not just touching them.")

# 6. Optional: test the Pi's own pins with a single wire
print()
try:
    ans = input(f"Want to test the Pi's {p(TRIG)} and {p(ECHO)} themselves? Type y and press Enter (or just Enter to skip): ")
except EOFError:
    ans = ""
if ans.strip().lower().startswith("y"):
    input(f"Unplug the sensor wires from {p(TRIG)} and {p(ECHO)}. Connect ONE jumper wire from {p(TRIG)} straight to {p(ECHO)}. Then press Enter...")
    out, inp = DigitalOutputDevice(TRIG), DigitalInputDevice(ECHO, pull_up=False)
    good = 0
    for v in (1, 0, 1, 0, 1, 0):
        out.value = v; sleep(0.02)
        good += (inp.value == v)
    out.close(); inp.close()
    if good == 6:
        print(f"PINS OK: {p(TRIG)} and {p(ECHO)} work fine. The problem is in the sensor wiring, not the Pi.")
    else:
        print(f"PINS PROBLEM: only {good}/6 checks passed. {p(TRIG)} or {p(ECHO)} (or that wire) is damaged.")
        print("-> Tell Claude: we'll move the sensor to different pins and update robot.py.")
print("\nDone. Copy the WHAT'S WRONG part and send it to Claude.")
