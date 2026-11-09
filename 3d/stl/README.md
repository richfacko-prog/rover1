# 4WD Rover Chassis: Print & Build Guide

Two-deck chassis for a Raspberry Pi 4, L298N motor driver, 6xAA battery holder,
USB power bank, HC-SR04 distance sensor, and 4 TT gear motors with 65 mm wheels.

Footprint: lower deck 200 x 110 mm, upper deck 230 x 110 mm (it sticks out 30 mm at the front to fit
the power bank). About 255 mm wide including wheels, about 95 mm tall.
Ground clearance under the motors is about 23 mm.

## Parts to print

| File | Qty | Print orientation (already set in the file) |
|---|---|---|
| lower_deck.stl | 1 | Flat, motor walls pointing UP |
| upper_deck.stl | 1 | Flat, Pi standoffs pointing up |
| sensor_bracket.stl | 1 | Face flat on the bed |
| deck_posts_x4.stl | 1 (contains all 4 posts) | Standing up |

**Settings:** PLA or PETG, 0.2 mm layers, 3 walls/perimeters, 20-25% infill.
**No supports needed** for any part. Each deck uses roughly 50-70 g of filament.

## Hardware

- 8 zip ties (4 mm wide or less): motor mounting, 2 per motor
- Double-sided foam tape or hot glue (recommended): helps hold each motor while you tighten the ties
- 8x M3 x 8-10 screws: deck posts (they thread straight into the printed posts)
- 4x M3 x 10 screws + nuts, plus 4 spacers about 5 mm (or a couple of extra nuts each): L298N
- 2x M3 x 10 screws + nuts: sensor bracket
- 4x M2.5 x 6 screws: Raspberry Pi (they thread into the printed standoffs)
- Velcro tape for the battery holder, and one Velcro strap about 20 mm wide for the power bank

## Assembly

1. **Motors.** Each motor goes under the lower deck in a corner, with its outer side flush with the deck
   edge and the axle pointing out to the side, near the corner. The short printed wall sits beside the
   gearbox end of the motor (the end with the axle); the rest of the motor extends past it toward the
   middle of the rover. Stick a strip of foam tape on top of the motor to hold it in place.
2. **Zip ties (2 per motor, no bolts needed).** For each tie: go down through the small slot on the inner
   side, under the motor, up the outer side through the notch in the deck edge, and back over the top.
   The tie nearest the axle also wraps around the wall. Pull both ties tight.
3. **Wires.** Feed each motor's wires up through the round hole next to it.
4. **L298N.** Mount it at the front of the lower deck on spacers, heatsink up.
5. **Battery holder.** Stick it at the back of the lower deck with Velcro so you can swap batteries.
6. **Sensor.** Push the HC-SR04's two "eyes" through the bracket from behind, then screw the bracket to
   the two holes at the front edge, facing forward.
7. **Posts.** Screw the four posts onto the lower deck from underneath, at the four corner holes.
8. **Upper deck.** Run the Pi and driver cables up through the center slots. Screw the upper deck onto the posts.
9. **Pi and power bank.** Screw the Pi to the standoffs with the USB/Ethernet ports facing the back.
   Lay the power bank (127 x 51 mm) lengthwise on the front half and strap it down through the four slots.

The two holes at the front corners of the upper deck are for a camera mast later.

## Check before printing

- **Sensor eye holes:** 16.8 mm wide, 26.5 mm apart (center to center). Measure your HC-SR04 first.
- **Power bank:** sized for yours (5 x 2 in, about 127 x 51 mm). Anything up to about 58 mm wide fits between the strap slots.
- **Wheels:** the layout assumes 65 mm TT wheels. Bigger wheels are fine. Smaller ones reduce ground clearance.
