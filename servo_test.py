"""
Servo test: finds out if a shaking servo is a CODE problem or a WIRING/POWER problem.

Stop the drive page first (it uses the servo too):
    sudo systemctl stop robot-drive
Then run:  python3 servo_test.py
Afterwards: sudo systemctl start robot-drive

Wiring: yellow -> pin 32, red -> 5V, black -> pin 34
"""
import time
import lgpio

GPIO = 12
h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(h, GPIO, 0)


def hold(us, seconds, label):
    print(f"{label} ... watch the servo")
    lgpio.tx_servo(h, GPIO, us)
    time.sleep(seconds)


try:
    hold(1450, 4, "1) CENTER, holding still for 4 seconds")
    hold(1100, 3, "2) one way (about 35 degrees)")
    hold(1800, 3, "3) the other way")
    hold(1450, 3, "4) back to CENTER")
    print("5) slow sweep")
    for us in list(range(1450, 1800, 10)) + list(range(1800, 1100, -10)) + list(range(1100, 1460, 10)):
        lgpio.tx_servo(h, GPIO, us)
        time.sleep(0.04)
    lgpio.tx_servo(h, GPIO, 0)
    print()
    print("If it shook even in step 1 (holding still): it's POWER or WIRING.")
    print("   -> push the red wire in firmly, or move red to the motor board's 5V screw.")
    print("If steps 1-5 were smooth: the wiring is fine. Tell Claude 'servo test was smooth'.")
finally:
    lgpio.tx_servo(h, GPIO, 0)
    lgpio.gpiochip_close(h)
