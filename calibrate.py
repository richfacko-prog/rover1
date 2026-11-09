"""
CALIBRATE THE WHEELS (works on both rovers)
Prop the rover up so the wheels are off the table, switch the AA pack ON,
stop the drive page (sudo systemctl stop robot-drive), then press Run in Thonny
or run: python3 ~/rover/calibrate.py
Answer the questions in the Shell box (bottom of Thonny).

It saves the result in ~/rover.json, which every rover program reads.
(It's outside the repo, so GitHub updates never undo it.)

"Forward" = the TOP of the wheel rolls toward the sensor (the front).
"""
from time import sleep
from gpiozero import Motor

import rover_config

SPEED = 0.8


def ask(question, options):
    while True:
        a = input(f"{question} ({'/'.join(options)}): ").strip().lower()
        if a[:1] in options:
            return a[:1]
        print("   Please type one of:", ", ".join(options))


def spin(pins):
    m = Motor(*pins)
    m.forward(SPEED)
    sleep(2.5)
    m.stop()
    m.close()


print("=== WHEEL CALIBRATION ===")
print("Watch the wheels. Each test spins for 2.5 seconds.\n")

results = {}
for name, pins in (("A", (17, 18)), ("B", (22, 23))):
    input(f"Press Enter to spin motor group {name}...")
    while True:
        spin(pins)
        side = ask("Which side spun? l = left, r = right, a = again", ["l", "r", "a"])
        if side != "a":
            break
    fwd = ask("Did those wheels roll FORWARD (top of the wheel toward the sensor)? y/n", ["y", "n"])
    results[name] = (side, fwd == "y")
    print()

(a_side, a_fwd), (b_side, b_fwd) = results["A"], results["B"]
if a_side == b_side:
    print("Hmm, both groups were on the same side. Run this again and watch closely.")
    raise SystemExit

swap = a_side == "r"                      # group A should be the left side
left_fwd = b_fwd if swap else a_fwd
right_fwd = a_fwd if swap else b_fwd
settings = {"FLIP_LEFT": not left_fwd, "FLIP_RIGHT": not right_fwd, "SWAP_SIDES": swap}

print("Your settings:")
for k, v in settings.items():
    print(f"   {k} = {v}")
path = rover_config.save(settings)
print(f"\nSaved into {path}")
print("Restart the drive page afterwards so it picks them up: sudo systemctl restart robot-drive")

# final check: all wheels forward
left_pins, right_pins = rover_config.motor_pins({**rover_config.DEFAULTS, **settings})
input("\nPress Enter for a final check: ALL wheels forward...")
L, R = Motor(*left_pins), Motor(*right_pins)
L.forward(SPEED); R.forward(SPEED); sleep(2.5); L.stop(); R.stop()
ok = ask("Did ALL four wheels roll forward? y/n", ["y", "n"])
print("\nAll set! Run robot.py or start the drive page." if ok == "y"
      else "\nRun calibrate.py once more and watch closely, or tell Claude what you saw.")
