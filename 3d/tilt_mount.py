"""
Tilting camera mount (SG90 micro servo) for the rover's top deck.

Two printed parts:
  tilt_bracket.stl : bolts into the deck's 2 camera holes (x = 118, y = +/-42), bridges over the
                     power bank, and holds the SG90 servo upright with its shaft pointing left.
  tilt_head.stl    : screws onto the servo arm (horn) and holds the Pi camera, facing forward.
                     It tilts up/down about +/-35 degrees around the servo shaft.

Frame (same as chassis.py, upper deck top = z 0): X forward, Y left, Z up.
Both parts are laid flat for printing, no supports needed.
"""
import os
import numpy as np
from cad import rect, circle, extrude, transform, write_stl, check_closed

OUT = os.path.join(os.path.dirname(__file__), "stl")

# deck / bracket
HOLE_X, HOLE_Y = 118.0, 42.0
LEG_H, BAR_T = 26.0, 4.0
BX0, BX1 = 108.0, 128.0                 # bracket depth (front-back)
PLATE_Y0, PLATE_Y1 = 0.0, 3.0           # servo plate thickness
PLATE_TOP = 66.0
M3_TAP, M2_TAP, SERVO_TAP = 1.4, 0.9, 0.9

# SG90 servo (body 22.5 x 12.2 mm, tab holes 27.5 mm apart, shaft ~6 mm from one end)
SERVO_W, SERVO_L = 12.2 + 0.4, 22.5 + 0.6
CUT_Z0 = 36.4
CUT_Z1 = CUT_Z0 + SERVO_L
BODY_ZC = (CUT_Z0 + CUT_Z1) / 2
SHAFT_Z = CUT_Z1 - 6.0                  # tilt axis height
TAB_DZ = 27.5 / 2

# tilt head
ARM_Y0, ARM_Y1 = 14.5, 17.5             # plate that sits on the servo horn
CAM_X0 = 140.0                          # back of the camera plate
CAM_YC = 2.0                            # camera centre (left/right)
CAM_DY, CAM_DZ = 21.0 / 2, 12.5 / 2     # Pi camera hole spacing
STANDOFF = 4.0


def bracket():
    b = []
    for sy in (1, -1):                                       # legs
        b.append(extrude(rect(BX0, sy * HOLE_Y - 5, BX1, sy * HOLE_Y + 5),
                         [circle(HOLE_X, sy * HOLE_Y, M3_TAP, 24)], 0, LEG_H, "z"))
    b.append(extrude(rect(BX0, -HOLE_Y - 5, BX1, HOLE_Y + 5), [], LEG_H, LEG_H + BAR_T, "z"))
    # upright servo plate (in the X-Z plane) with the servo window and 2 tab screw holes
    holes = [rect(HOLE_X - SERVO_W / 2, CUT_Z0, HOLE_X + SERVO_W / 2, CUT_Z1)]
    holes += [circle(HOLE_X, BODY_ZC + s * TAB_DZ, SERVO_TAP, 20) for s in (1, -1)]
    b.append(extrude(rect(BX0, LEG_H, BX1, PLATE_TOP), holes, PLATE_Y0, PLATE_Y1, "y"))
    # two braces behind the plate (servo body hangs between them)
    tri = [(PLATE_Y0, LEG_H + BAR_T), (PLATE_Y0, 58.0), (PLATE_Y0 - 13.0, LEG_H + BAR_T)]
    b.append(extrude(tri, [], BX0, HOLE_X - SERVO_W / 2 - 0.6, "x"))
    b.append(extrude(tri, [], HOLE_X + SERVO_W / 2 + 0.6, BX1, "x"))
    return b


def head():
    b = []
    # side arm on the servo horn: big hole in the middle to reach the horn screw
    b.append(extrude(rect(BX0, SHAFT_Z - 8, CAM_X0 + 3, SHAFT_Z + 8),
                     [circle(HOLE_X, SHAFT_Z, 2.6, 32)], ARM_Y0, ARM_Y1, "y"))
    # camera plate facing forward
    holes = [circle(CAM_YC + sy * CAM_DY, SHAFT_Z + sz * CAM_DZ, M2_TAP, 20)
             for sy in (1, -1) for sz in (1, -1)]
    b.append(extrude(rect(-14.0, SHAFT_Z - 13, ARM_Y1, SHAFT_Z + 13), holes, CAM_X0, CAM_X0 + 3, "x"))
    for sy in (1, -1):
        for sz in (1, -1):
            y, z = CAM_YC + sy * CAM_DY, SHAFT_Z + sz * CAM_DZ
            b.append(extrude(circle(y, z, 2.3, 32), [circle(y, z, M2_TAP, 20)],
                             CAM_X0 + 2.5, CAM_X0 + 3 + STANDOFF, "x"))
    return b


def drop(bodies, R):
    out = [transform(t, R) for t in bodies]
    z = min(t[..., 2].min() for t in out)
    return [transform(t, T=(0, 0, -z)) for t in out]


if __name__ == "__main__":
    parts = {
        "tilt_bracket": (bracket(), [[0, 0, -1], [0, 1, 0], [1, 0, 0]]),   # lies on its back
        "tilt_head": (head(), [[1, 0, 0], [0, 0, 1], [0, -1, 0]]),         # lies on the horn plate
    }
    for name, (bodies, R) in parts.items():
        for t in bodies:
            assert check_closed(t) == 0, name
        out = write_stl(os.path.join(OUT, name + ".stl"), drop(bodies, R), name)
        p = out.reshape(-1, 3)
        print(name, len(out), "tris, print size", np.round(p.max(0) - p.min(0), 1))
