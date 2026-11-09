"""
Distance sensor test for the rover.
Open in Thonny and press Run. It tells you what is wrong (if anything).

Wiring it expects:
  VCC  -> Pi pin 2 (5V)      GND -> Pi pin 9
  Trig -> Pi pin 29
  Echo -> 1k resistor -> joining row -> Pi pin 31; joining row -> 2k resistor -> Pi pin 20
"""
from gpiozero import DigitalOutputDevice, DigitalInputDevice
from time import sleep, time

trig = DigitalOutputDevice(5)    # pin 29
echo = DigitalInputDevice(6)     # pin 31

print("=== Rover sensor test ===")
idle = echo.value
print("Echo pin (pin 31) right now:", idle)
if idle == 1:
    print("-> Pin 31 is stuck ON. Check that the Echo wire isn't touching VCC or Trig.")

seen_count = 0
for i in range(1, 6):
    trig.on()
    sleep(0.0001)
    trig.off()

    start = time()
    rise = None
    while time() - start < 0.05:          # wait for the echo to start
        if echo.value:
            rise = time()
            break
    if rise is None:
        print(f"Ping {i}: no echo")
    else:
        while echo.value and time() - rise < 0.05:   # time how long the echo lasts
            pass
        cm = (time() - rise) * 34300 / 2
        seen_count += 1
        print(f"Ping {i}: ECHO SEEN!  about {cm:.0f} cm")
    sleep(0.5)

print()
if seen_count == 5:
    print("RESULT: The sensor works! Move your hand in front of it and run again to see the cm change.")
elif seen_count > 0:
    print("RESULT: Sometimes works. A wire is probably loose. Push every connection in firmly.")
elif idle == 1:
    print("RESULT: Pin 31 is stuck ON. Check the Echo wire (see above).")
else:
    print("RESULT: No echo at all. Check, in this order:")
    print("  1. Sensor VCC is on pin 2 (5V)")
    print("  2. Trig and Echo are not swapped at the sensor")
    print("  3. Trig wire is on pin 29, sensor GND is on pin 9")
    print("  4. Every wire is pushed on firmly at both ends")
