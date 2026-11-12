# 4WD Rover Chassis: Print & Build Guide

Two-deck chassis for a Raspberry Pi 4, L298N motor driver, one 2S 7.4 V battery (70 x 37 x 19 mm)
with a 5 V converter for the Pi, HC-SR04 distance sensor, and 4 TT gear motors with 65 mm wheels.
Every part is screwed or zip-tied down.

Footprint: lower deck 200 x 117 mm, upper deck 230 x 110 mm. About 255 mm wide including wheels,
about 95 mm tall. Ground clearance under the motors is about 23 mm.

## Parts to print

| File | Qty | What it is | Print orientation (already set in the file) |
|---|---|---|---|
| lower_deck.stl | 1 | Bottom layer: motors underneath; battery, L298N, converter, Wagos on top | Flat, motor walls pointing UP |
| upper_deck.stl | 1 | Top layer: Pi and camera | Flat, Pi standoffs pointing up |
| deck_posts_x4.stl | 1 (all 4 posts) | Posts joining the two layers | Standing up |
| sensor_bracket.stl | 1 | HC-SR04 holder, front edge | Face flat on the bed |
| switch_bracket.stl | 1 | The DaierTek KCD1 rocker switch snaps into it | Window flat on the bed |
| gauge_bracket.stl | 1 | Battery voltmeter window | Window flat on the bed |
| pi_case_bolt_base.stl | 1 | Pi case (screws onto the upper deck) | Flat, as in the file |
| pi_case_bolt_lid.stl | 1 | Lid for the case (fan, vents, camera ribbon slot) | Flat |
| camera_mount.stl | 1 | Fixed camera mount | As in the file |
| tilt_bracket.stl + tilt_head.stl | 1 each | Optional: camera on an SG90 tilt servo (instead of camera_mount) | As in the file |

Older / spare files (not needed for a new build): `pi_case_base.stl` + `pi_case_lid.stl` (first Pi case),
`deck_posts_x2.stl` (2 spare posts).

**Settings:** PLA or PETG, 0.2 mm layers, 3 walls/perimeters, 20-25% infill.
**No supports needed** for any part.

## Hardware

- 8 zip ties (4 mm wide or less) for the motors, 2 per motor
- 6 more zip ties: battery (2), 5 V converter (2), Wagos (2). One small thin tie (2.5 mm) for the gauge
- Double-sided foam tape (recommended): a strip on top of each motor while you tighten the ties
- 8x M3 x 8-10 screws: deck posts (they thread straight into the printed posts)
- 2x M3 x 12 screws: the Pi case's two rear tabs (instead of 2 of the post screws)
- 4x M3 x 10 screws + nuts, plus 4 spacers about 5 mm: L298N
- 2x M3 x 10 screws + nuts: sensor bracket
- 4x M3 x 6 screws: switch and gauge brackets (they thread into the deck; no longer than 6 mm, a motor is under there)
- 4x M2.5 x 12 screws: Raspberry Pi (through the case into the deck's standoffs)
- 4x M3 x 8 screws: Pi case lid

## Assembly

1. **Motors.** Each motor goes under the lower deck in a corner, axle pointing out to the side. It drops
   into a channel: the long wall on the inside, the short wall on the outside at the motor's back end.
   Foam tape on top of the motor helps.
2. **Zip ties (2 per motor).** One around the motor body (near its back end), one around the gearbox.
   Each tie goes down through the small slot on the inside, through the gap in the wall, under the motor,
   up the outside through the notch in the deck edge, and back over the top. Pull them tight.
3. **Motor wires** up through the round hole next to each motor.
4. **L298N** at the front on 5 mm spacers, heatsink up. Leave the 2 jumper caps on.
   Left motors to OUT1/OUT2, right motors to OUT3/OUT4.
5. **Battery** at the back, held by 2 zip ties (or a 10 mm Velcro strap) through the slots either side.
   Leave it unplugged until all the wiring is done.
6. **Switch bracket** at the back of the left edge, **gauge bracket** at the back of the right edge,
   2x M3 x 6 each. Snap the switch into its window from outside. Hold the gauge behind its window with
   the thin zip tie through the two little slots.
7. **5 V converter** right of the middle slot and the **two Wagos** left of it, each with 2 zip ties.
8. **Power wiring:** battery + to the switch, switch to Wago +. Battery − to Wago −. From Wago +: L298N 12V
   and converter IN+. From Wago −: L298N GND and converter IN−. The gauge's thin wires share the
   L298N's 12V and GND screws. Add one more wire from L298N GND for the Pi (pin 6).
9. **Sensor.** Push the HC-SR04's eyes through the bracket from behind, screw it to the two front holes.
10. **Posts.** Screw the four posts onto the lower deck from underneath. Run the cables (IN1-IN4, GND, sensor,
    the converter's USB-C) up through the middle slot. Screw the upper deck on (front posts now, rear
    posts go through the Pi case tabs).
11. **Pi case and camera.** See the Pi case section in the main README. The mini breadboard for the sensor's
    resistors zip-ties to the strap slots on the upper deck.
12. **Before plugging the Pi in:** switch on and check the converter gives 5 V. Then plug its USB-C into the Pi.

The 2S pack: full is 8.4 V on the gauge. Charge at about 6.8 V. Never run it below 6.0 V.

## Check before printing

- **Sensor eye holes:** 16.8 mm wide, 26.5 mm apart (center to center). Measure your HC-SR04 first.
- **Motor channel:** 22.8 mm wide, for a TT motor 22.5 mm across.
- **Wheels:** the layout assumes 65 mm TT wheels. Bigger wheels are fine. Smaller ones reduce ground clearance.
