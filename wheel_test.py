"""
Wheel test: spins each side of the rover forward, one at a time. Works on both rovers.
Prop the rover up so the wheels are off the table, switch the AA pack on,
stop the drive page (sudo systemctl stop robot-drive), then press Run in Thonny
and watch which wheels spin which way.

Uses the flip settings from ~/rover.json (set by calibrate.py).
"""
from gpiozero import Robot
from time import sleep

from rover_config import CFG, motor_pins

left_pins, right_pins = motor_pins(CFG)
robot = Robot(left=left_pins, right=right_pins)
SPEED = 0.8

print(f"{CFG['NAME']}: FLIP_LEFT={CFG['FLIP_LEFT']} FLIP_RIGHT={CFG['FLIP_RIGHT']} SWAP_SIDES={CFG['SWAP_SIDES']}")
print("Watch the wheels. All 'forward' means: the top of the wheel rolls toward the sensor.\n")
sleep(2)

print("1) LEFT side only, FORWARD (3 seconds)...")
robot.left_motor.forward(SPEED); sleep(3); robot.stop(); sleep(1)

print("2) RIGHT side only, FORWARD (3 seconds)...")
robot.right_motor.forward(SPEED); sleep(3); robot.stop(); sleep(1)

print("3) ALL wheels, FORWARD (3 seconds)...")
robot.forward(SPEED); sleep(3); robot.stop()

print("""
What did you see?
- During step 1 only the LEFT wheels should spin, during step 2 only the RIGHT wheels.
  (If not, run calibrate.py: it fixes swapped sides too.)
- ONE wheel spins backward while its partner spins forward:
    swap THAT motor's two wires on its OUT terminal (code can't fix this one).
- BOTH wheels on one side spin backward: run calibrate.py.
""")
