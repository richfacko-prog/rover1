"""
4WD two-deck rover chassis for: Raspberry Pi 4, L298N, 6xAA holder,
~222 g USB power bank, HC-SR04, 4x TT gear motors with 65 mm wheels.

Frame: X = forward, Y = left, Z = up. Units: mm.
All key dimensions are parameters below.
"""
import os
import numpy as np
from cad import (rect, circle, stadium, chamfered_rect, extrude, transform,
                 write_stl, check_closed)

OUT = os.path.join(os.path.dirname(__file__), "stl")
os.makedirs(OUT, exist_ok=True)

# ---- overall ----
L, W = 200.0, 110.0          # deck length / width
LOWER_T, UPPER_T = 4.0, 3.5  # deck thickness
CORNER = 8.0
POST_H = 45.0                # gap between decks
UPPER_FRONT = 130.0          # upper deck extends 30 mm forward to fit a 127 mm power bank
POSTS = [(sx * 95.5, sy * 40) for sx in (1, -1) for sy in (1, -1)]  # past the motor ends
M3_CLEAR = 1.7               # radius, M3 clearance hole
M3_TAP = 1.4                 # radius, M3 self-tapping into plastic

# ---- TT motors (front pair gearbox faces forward, rear pair faces back) ----
SHAFT_X = 80.0               # axle position from center (wheelbase 160)
MOTOR_W = 22.5               # gearbox width along the axle
MOTOR_H = 18.8               # motor thickness
MOTOR_OUT_Y = W / 2          # outer face of motor flush with deck edge
WALL_T = 3.0
WALL_X = (50.0, 74.0)        # short locating wall beside the gearbox only, so any TT motor is longer than it
ZIP_X = (42.0, 60.0)         # two zip ties around each motor (the outer one goes through a gap in the wall)
NOTCH_W, NOTCH_D = 5.5, 2.0   # edge notch that locates the zip tie
WALL_GAP = 6.5               # gap in the motor wall where the zip tie passes through

# ---- electronics ----
L298N_C, L298N_PITCH = (48.0, 0.0), 37.0
PI_HOLES_X = (-74.5, -16.5)  # Pi 4: 58 x 49 mm hole pattern, ports face the rear
PI_HOLES_Y = (-24.5, 24.5)
SENSOR_HOLES = [(90.0, 15.0), (90.0, -15.0)]


def notched_outline():
    """Chamfered deck outline with zip-tie notches on both long edges."""
    c, hx, hy, nw = CORNER, L / 2, W / 2, NOTCH_W / 2
    xs = sorted(sx * z for z in ZIP_X for sx in (1, -1))
    pts = [(-hx + c, -hy)]
    for x in xs:                                   # bottom edge, left -> right
        pts += [(x - nw, -hy), (x - nw, -hy + NOTCH_D), (x + nw, -hy + NOTCH_D), (x + nw, -hy)]
    pts += [(hx - c, -hy), (hx, -hy + c), (hx, hy - c), (hx - c, hy)]
    for x in reversed(xs):                         # top edge, right -> left
        pts += [(x + nw, hy), (x + nw, hy - NOTCH_D), (x - nw, hy - NOTCH_D), (x - nw, hy)]
    pts += [(-hx + c, hy), (-hx, hy - c), (-hx, -hy + c)]
    return pts


def lower_deck():
    holes = []
    holes += [circle(x, y, M3_CLEAR, 24) for x, y in POSTS]
    cx, cy = L298N_C
    p = L298N_PITCH / 2
    holes += [circle(cx + dx, cy + dy, M3_CLEAR, 24) for dx in (-p, p) for dy in (-p, p)]
    holes += [circle(x, y, M3_CLEAR, 24) for x, y in SENSOR_HOLES]
    holes += [circle(sx * 15, sy * 43, 5.0, 32) for sx in (1, -1) for sy in (1, -1)]  # motor wires
    holes.append(rect(-12, -7, 12, 7))  # cable pass-through to upper deck
    inner_y = MOTOR_OUT_Y - MOTOR_W - WALL_T  # 29.5
    for sx in (1, -1):
        for sy in (1, -1):
            for zx in ZIP_X:
                x = sx * zx
                y0, y1 = sorted((sy * (inner_y - 4.0), sy * (inner_y - 1.0)))
                holes.append(rect(x - 2.75, y0, x + 2.75, y1))            # inner zip slot
    plate = extrude(notched_outline(), holes, 0, LOWER_T, "z")

    bodies = [plate]
    # motor mounting walls hang below the deck, on the inboard side of each motor.
    # Each wall has a gap where a zip tie crosses it, so the tie drops straight down past it.
    spans, a = [], WALL_X[0]
    for zx in sorted(ZIP_X):
        if WALL_X[0] < zx < WALL_X[1]:
            spans.append((a, zx - WALL_GAP / 2))
            a = zx + WALL_GAP / 2
    spans.append((a, WALL_X[1]))
    for sx in (1, -1):
        for sy in (1, -1):
            for w0, w1 in spans:
                x0, x1 = sorted((sx * w0, sx * w1))
                outline = rect(x0, -MOTOR_H, x1, 0.6)                 # (x, z)
                y0, y1 = sorted((sy * inner_y, sy * (inner_y + WALL_T)))
                bodies.append(extrude(outline, [], y0, y1, "y"))
    return bodies


def upper_deck():
    holes = [circle(x, y, M3_CLEAR, 24) for x, y in POSTS]
    holes += [circle(x, y, 1.2, 20) for x in PI_HOLES_X for y in PI_HOLES_Y]
    # power bank: 127 x 51 mm (5 x 2 in), lying lengthwise from x = 0 to 127
    holes += [rect(x0, 30, x0 + 22, 34) for x0 in (25, 85)]
    holes += [rect(x0, -34, x0 + 22, -30) for x0 in (25, 85)]               # power-bank strap slots
    holes.append(rect(-11, -8, -2, 8))                                      # cable pass-through
    holes += [circle(118, y, M3_CLEAR, 24) for y in (42, -42)]             # future camera mast
    plate = extrude(chamfered_rect(-L / 2, -W / 2, UPPER_FRONT, W / 2, CORNER), holes, 0, UPPER_T, "z")
    bodies = [plate]
    for x in PI_HOLES_X:
        for y in PI_HOLES_Y:
            bodies.append(extrude(circle(x, y, 3.25, 32), [circle(x, y, 1.2, 20)],
                                  UPPER_T - 0.5, UPPER_T + 5.0, "z"))       # Pi standoffs
    return bodies


def sensor_bracket():
    """Face sits at deck front edge; HC-SR04 'eyes' push through the two holes."""
    face_w, face_h, t = 52.0, 26.0, 3.0
    eye_r, eye_pitch = 8.4, 26.5
    face = extrude(rect(-face_w / 2, 0, face_w / 2, face_h),
                   [circle(sy * eye_pitch / 2, 13.0, eye_r, 48) for sy in (1, -1)],
                   0, t, "x")                                               # (y, z) extruded along x
    flange = extrude(rect(-14, -face_w / 2, t, face_w / 2),
                     [circle(-7, sy * 15, M3_CLEAR, 24) for sy in (1, -1)],
                     0, 3.0, "z")
    gussets = [extrude([(0.5, 2.5), (-10, 2.5), (0.5, 16)], [], y0, y0 + 3, "y")
               for y0 in (-face_w / 2, face_w / 2 - 3)]
    return [face, flange] + gussets


def posts():
    bodies = []
    for i, (x, y) in enumerate([(0, 0), (15, 0), (0, 15), (15, 15)]):
        bodies.append(extrude(circle(x, y, 4.5, 40), [circle(x, y, M3_TAP, 20)], 0, POST_H, "z"))
    return bodies


def drop_to_bed(bodies):
    zmin = min(b[..., 2].min() for b in bodies)
    return [transform(b, T=(0, 0, -zmin)) for b in bodies]


if __name__ == "__main__":
    parts = {
        "lower_deck": (lower_deck(), np.diag([1, -1, -1])),                 # flip: walls point up
        "upper_deck": (upper_deck(), None),
        "sensor_bracket": (sensor_bracket(), [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]),  # face down
        "deck_posts_x4": (posts(), None),
    }
    for name, (bodies, R) in parts.items():
        for b in bodies:
            assert check_closed(b) == 0, f"{name}: open mesh"
        printable = drop_to_bed([transform(b, R) for b in bodies])
        t = write_stl(os.path.join(OUT, f"{name}.stl"), printable, name)
        ext = t.reshape(-1, 3).max(0) - t.reshape(-1, 3).min(0)
        print(f"{name:15s} {len(t):6d} tris  size {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm")
