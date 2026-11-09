"""
Rover: drive around and avoid obstacles (v2). Works on both rovers.

- Full power, slows a little when something is close.
- Too close: backs up, looks left and right, turns toward the open side.
- STUCK detection: if it's trying to drive but the distance isn't changing,
  it knows it's stuck (e.g. on something at its side) and escapes.
- Turns until it actually SEES open space, instead of turning a fixed amount.

Wiring (Pi pin numbers, same on the Pi 3 and Pi 4):
  L298N IN1 -> pin 11   IN2 -> pin 12   IN3 -> pin 15   IN4 -> pin 16   GND -> pin 6
  Sensor VCC -> pin 2 (5V)   GND -> pin 9   Trig -> pin 29
         Echo -> 1k resistor -> joining row -> pin 31, and joining row -> 2k resistor -> pin 20
Which wheels are flipped is stored per rover in ~/rover.json (calibrate.py sets it).

Stop the drive page first: sudo systemctl stop robot-drive
Run in Thonny with the green Run button. Stop with the red Stop button.
"""
from gpiozero import Robot, DigitalOutputDevice, DigitalInputDevice
from time import sleep, time

from rover_config import CFG, motor_pins

# ---------- settings you can change ----------
CRUISE_SPEED = 1.0    # 0.0 to 1.0  (full power)
SLOW_SPEED = 0.85     # used when something is getting close
TURN_SPEED = 1.0      # turning needs lots of power on a 4-wheel rover
BACKUP_SPEED = 1.0
STOP_CM = 30          # closer than this: stop and turn away
SLOW_CM = 60          # closer than this: slow down
CLEAR_CM = 60         # "open space" = at least this much room ahead
LOOK_TIME = 0.35      # seconds of turning to look to one side
BACKUP_TIME = 0.5     # seconds to back up before turning
STUCK_TIME = 1.5      # seconds of "no progress" before it decides it's stuck
# ---------------------------------------------

left_pins, right_pins = motor_pins(CFG)
robot = Robot(left=left_pins, right=right_pins)
trig = DigitalOutputDevice(CFG["TRIG_GPIO"])    # pin 29
echo = DigitalInputDevice(CFG["ECHO_GPIO"])     # pin 31
NO_ECHO = None


def ping():
    """One measurement in cm, or None if the sensor doesn't answer."""
    trig.on()
    sleep(0.00002)
    trig.off()
    t0 = time()
    while not echo.value:
        if time() - t0 > 0.03:
            return NO_ECHO
    rise = time()
    while echo.value:
        if time() - rise > 0.03:
            return 500.0
    return (time() - rise) * 34300 / 2


def distance_cm():
    """Median of 3 pings. Returns None if the sensor isn't answering."""
    readings = []
    for _ in range(3):
        r = ping()
        if r is not None:
            readings.append(r)
        sleep(0.01)
    if not readings:
        return NO_ECHO
    readings.sort()
    return readings[len(readings) // 2]


def spin(direction, seconds):
    """Turn on the spot for a moment, then stop."""
    if direction == "left":
        robot.left(TURN_SPEED)
    else:
        robot.right(TURN_SPEED)
    sleep(seconds)
    robot.stop()
    sleep(0.1)


def back_up(seconds=BACKUP_TIME):
    robot.backward(BACKUP_SPEED)
    sleep(seconds)
    robot.stop()
    sleep(0.1)


def turn_until_clear(direction, max_time=4.0):
    """Keep turning in small steps until the sensor sees open space."""
    start = time()
    while time() - start < max_time:
        spin(direction, 0.15)
        d = distance_cm()
        if d is not None and d >= CLEAR_CM:
            return True
    return False


def avoid(reason):
    print(reason)
    robot.stop()
    sleep(0.1)
    back_up()

    spin("left", LOOK_TIME)               # look left
    left_room = distance_cm() or 0
    spin("right", LOOK_TIME * 2)          # swing over and look right
    right_room = distance_cm() or 0
    print(f"  looked around: left {left_room:.0f} cm, right {right_room:.0f} cm")

    if right_room >= CLEAR_CM and right_room >= left_room:
        print("  going right")            # already pointing right
        return
    if left_room >= CLEAR_CM:
        print("  going left")
        spin("left", LOOK_TIME * 2)
        return

    print("  both sides blocked, turning until I see open space")
    if not turn_until_clear("right"):
        print("  still blocked, backing up more and trying the other way")
        back_up(BACKUP_TIME * 1.5)
        turn_until_clear("left")


def main():
    print(f"{CFG['NAME']} starting in 3 seconds. Put it on the floor!")
    for n in (3, 2, 1):
        print(n)
        sleep(1)
    print("Go! (press Stop to end)")

    last_print = 0
    last_warn = 0
    history = []                          # (time, distance) while driving forward

    while True:
        d = distance_cm()
        now = time()

        if d is NO_ECHO:
            robot.forward(SLOW_SPEED)
            if now - last_warn > 3:
                print("Sensor not answering, driving slowly. Check the sensor wiring.")
                last_warn = now
            history.clear()
            sleep(0.05)
            continue

        if d < STOP_CM:
            avoid(f"Obstacle at {d:.0f} cm!")
            history.clear()
            continue

        robot.forward(SLOW_SPEED if d < SLOW_CM else CRUISE_SPEED)

        # stuck check: driving forward but the distance ahead isn't changing
        history.append((now, d))
        history = [(t, x) for t, x in history if now - t <= STUCK_TIME]
        if (d < 300 and now - history[0][0] >= STUCK_TIME * 0.9
                and max(x for _, x in history) - min(x for _, x in history) < 4):
            avoid("I think I'm stuck! Escaping...")
            history.clear()
            continue

        if now - last_print > 1:
            print(f"Distance ahead: {d:.0f} cm")
            last_print = now
        sleep(0.03)


try:
    main()
except KeyboardInterrupt:
    pass
finally:
    robot.stop()
    print("Rover stopped.")
