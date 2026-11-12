"""
4WD two-deck rover chassis for: Raspberry Pi 4, L298N, one 2S 7.4 V battery (70 x 37 x 19 mm)
with a 5 V converter for the Pi, DaierTek KCD1 rocker switch, battery gauge, HC-SR04,
4x TT gear motors with 65 mm wheels. Every part is screwed or zip-tied down.

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
WALL_X = (22.0, 90.0)        # inner wall along the WHOLE motor (motor end to gearbox end)
OUTER_X = (22.0, 44.0)       # outer wall at the motor end (stays clear of the wheel)
TAB_X = (20.0, 46.0)         # deck widened here to carry the outer wall
TAB_Y = MOTOR_OUT_Y + 0.3 + WALL_T   # 58.3: outer edge of that tab
ZIP_X = (31.0, 64.0)         # zip ties: one round the motor body, one round the gearbox
NOTCH_W, NOTCH_D = 5.5, 2.0  # edge notch that locates the zip tie
WALL_GAP = 6.5               # gap in the walls where a zip tie passes

# ---- electronics ----
L298N_C, L298N_PITCH = (48.0, 0.0), 37.0
PI_HOLES_X = (-74.5, -16.5)  # Pi 4: 58 x 49 mm hole pattern, ports face the rear
PI_HOLES_Y = (-24.5, 24.5)
SENSOR_HOLES = [(90.0, 15.0), (90.0, -15.0)]
BATT = (-94.0, -22.0, -19.5, 19.5)       # 2S pack 70 x 37 (+ clearance), at the back
BATT_TIES = (-80.0, -50.0)               # two zip ties (or a 10 mm Velcro strap) across the pack
BUCK_TIES = (-30.0, -16.0)               # 5 V converter, right of centre (x -12..12, y -37..-9)
WAGO_TIES = (15.0, 27.0)                 # two Wago 221-413, left of centre (x -12..12, y 9..33)
TIE_X = 15.5                             # those ties pass either side of the part
BRACKET_X = (-60.5, -34.5)               # switch bracket (left side) and gauge bracket (right side)
BRACKET_HOLES = [(-56.0, sy * 45.0) for sy in (1, -1)] + [(-39.0, sy * 45.0) for sy in (1, -1)]


def notched_outline():
    """Chamfered deck outline: zip-tie notches on both long edges, and a tab by each motor's
    back end that carries the outer motor wall."""
    c, hx, hy, nw, gw = CORNER, L / 2, W / 2, NOTCH_W / 2, WALL_GAP / 2
    feats = []
    for sx in (1, -1):
        a, b = sorted((sx * TAB_X[0], sx * TAB_X[1]))
        feats += [("tab", a, sx * ZIP_X[0], b), ("notch", sx * ZIP_X[1])]
    feats.sort(key=lambda f: f[1])
    bottom = [(-hx + c, -hy)]                       # right-hand edge (y = -hy), back -> front
    for f in feats:
        if f[0] == "notch":
            x = f[1]
            bottom += [(x - nw, -hy), (x - nw, -hy + NOTCH_D), (x + nw, -hy + NOTCH_D), (x + nw, -hy)]
        else:
            _, a, zx, b = f
            bottom += [(a, -hy), (a, -TAB_Y), (zx - gw, -TAB_Y), (zx - gw, -hy + 0.5),
                       (zx + gw, -hy + 0.5), (zx + gw, -TAB_Y), (b, -TAB_Y), (b, -hy)]
    bottom.append((hx - c, -hy))
    top = [(x, -y) for x, y in reversed(bottom)]   # left-hand edge, mirrored
    return bottom + [(hx, -hy + c), (hx, hy - c)] + top + [(-hx, hy - c), (-hx, -hy + c)]


def spans(x0, x1, gaps):
    """[x0, x1] minus a WALL_GAP around each gap position."""
    out, a = [], x0
    for g in sorted(gaps):
        if x0 < g < x1:
            out.append((a, g - WALL_GAP / 2))
            a = g + WALL_GAP / 2
    return out + [(a, x1)]


def lower_deck():
    holes = []
    holes += [circle(x, y, M3_CLEAR, 24) for x, y in POSTS]
    cx, cy = L298N_C
    p = L298N_PITCH / 2
    holes += [circle(cx + dx, cy + dy, M3_CLEAR, 24) for dx in (-p, p) for dy in (-p, p)]
    holes += [circle(x, y, M3_CLEAR, 24) for x, y in SENSOR_HOLES]
    holes += [circle(sx * 15, sy * 43, 5.0, 32) for sx in (1, -1) for sy in (1, -1)]  # motor wires
    holes.append(rect(-12, -7, 12, 7))                                   # cables up to the top deck
    holes += [circle(x, y, M3_TAP, 20) for x, y in BRACKET_HOLES]        # switch + gauge brackets
    inner_y = MOTOR_OUT_Y - MOTOR_W - WALL_T                             # 29.5
    for sx in (1, -1):
        for sy in (1, -1):
            for zx in ZIP_X:                                             # inner zip slot per tie
                y0, y1 = sorted((sy * (inner_y - 4.0), sy * (inner_y - 1.0)))
                holes.append(rect(sx * zx - 2.75, y0, sx * zx + 2.75, y1))
    for x in BATT_TIES:                                                  # battery: tie or strap slots
        holes += [rect(x - 6, 22.5, x + 6, 25.5), rect(x - 6, -25.5, x + 6, -22.5)]
    for y in BUCK_TIES + WAGO_TIES:                                      # converter + Wagos: tie slots
        holes += [rect(sx * TIE_X - 1.3, y - 2.75, sx * TIE_X + 1.3, y + 2.75) for sx in (1, -1)]
    plate = extrude(notched_outline(), holes, 0, LOWER_T, "z")

    bodies = [plate]
    # motor channel, hanging under the deck: a full-length inner wall, and an outer wall at the
    # motor's back end. Gaps where the zip ties pass.
    for sx in (1, -1):
        for sy in (1, -1):
            walls = [(w, (inner_y, inner_y + WALL_T)) for w in spans(*WALL_X, ZIP_X)]
            walls += [(w, (MOTOR_OUT_Y + 0.3, TAB_Y)) for w in spans(*OUTER_X, ZIP_X)]
            for (w0, w1), (ya, yb) in walls:
                x0, x1 = sorted((sx * w0, sx * w1))
                y0, y1 = sorted((sy * ya, sy * yb))
                bodies.append(extrude(rect(x0, -MOTOR_H, x1, 0.6), [], y0, y1, "y"))
    return bodies


def bracket(kind):
    """Small screw-on bracket at the deck edge. 'switch': the KCD1 rocker snaps into it.
    'gauge': the battery voltmeter sits behind the window, held by a small zip tie.
    Local frame: panel outer face at y = 0, foot pointing in (+y), z up from the deck top."""
    Wb = BRACKET_X[1] - BRACKET_X[0]
    PT = 1.8                                                              # panel thickness (KCD1 clips)
    if kind == "switch":
        H, g_top = 23.0, 14.0
        holes = [rect((Wb - 19.5) / 2, 6.0, (Wb + 19.5) / 2, 19.3)]      # 19.5 x 13.3 mm window
    else:
        H, g_top = 24.0, 7.0
        holes = [rect((Wb - 20.5) / 2, 10.0, (Wb + 20.5) / 2, 18.5),     # 20.5 x 8.5 mm window
                 rect(Wb / 2 - 1.6, 7.4, Wb / 2 + 1.6, 8.8), rect(Wb / 2 - 1.6, 19.6, Wb / 2 + 1.6, 21.0)]
    b = [extrude(rect(0, 0, Wb, H), holes, 0, PT, "y")]
    b.append(extrude(rect(0, 0, Wb, 12.0), [circle(4.5, 7.0, M3_CLEAR, 24), circle(Wb - 4.5, 7.0, M3_CLEAR, 24)],
                     0, 3.0, "z"))
    for x0 in (0.0, Wb - 2.0):
        b.append(extrude([(PT - 0.2, 2.8), (11.0, 2.8), (PT - 0.2, g_top)], [], x0, x0 + 2.0, "x"))
    return b


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
        "switch_bracket": (bracket("switch"), [[1, 0, 0], [0, 0, -1], [0, 1, 0]]),   # panel flat on the bed
        "gauge_bracket": (bracket("gauge"), [[1, 0, 0], [0, 0, -1], [0, 1, 0]]),
    }
    for name, (bodies, R) in parts.items():
        for b in bodies:
            assert check_closed(b) == 0, f"{name}: open mesh"
        printable = drop_to_bed([transform(b, R) for b in bodies])
        t = write_stl(os.path.join(OUT, f"{name}.stl"), printable, name)
        ext = t.reshape(-1, 3).max(0) - t.reshape(-1, 3).min(0)
        print(f"{name:15s} {len(t):6d} tris  size {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm")
