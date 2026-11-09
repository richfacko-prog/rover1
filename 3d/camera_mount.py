"""
Camera mount for the rover's top deck.

Bridges over the power bank and bolts into the two "camera mast" holes at the front
corners of the upper deck (x = 118 mm, y = +/-42 mm). The Pi Camera Module (v1/v2/v3,
holes 21 x 12.5 mm) screws onto 4 standoffs on the front face, lens facing forward.

Frame (same as chassis.py, upper deck top = z 0): X forward, Y left, Z up.
Printed lying on its back (camera face up), so it needs no supports.
"""
import os
import numpy as np
from cad import rect, circle, extrude, transform, write_stl, check_closed

OUT = os.path.join(os.path.dirname(__file__), "stl")

HOLE_X, HOLE_Y = 118.0, 42.0        # deck "camera mast" holes
LEG_H = 26.0                        # clearance over the power bank (+ strap)
BAR_T = 4.0                         # cross bar thickness
X0, X1 = 113.0, 123.0               # depth of legs / bar / back block
PLATE_T = 3.0                       # camera plate thickness (x 123..126)
PLATE_W, PLATE_Z1 = 34.0, LEG_H + 36.0
CAM_ZC = LEG_H + 20.0               # centre of the camera's hole pattern
CAM_DX, CAM_DZ = 21.0 / 2, 12.5 / 2 # half hole spacing (Pi Camera Module)
STANDOFF = 4.0                      # gap behind the camera board (connector clearance)
M3_TAP, M2_TAP = 1.4, 0.9


def parts():
    b = []
    # legs, each with an M3 hole for a screw coming up through the deck from below
    for sy in (1, -1):
        b.append(extrude(rect(X0, sy * HOLE_Y - 5, X1, sy * HOLE_Y + 5),
                         [circle(HOLE_X, sy * HOLE_Y, M3_TAP, 24)], 0, LEG_H, "z"))
    # cross bar on top of the legs
    b.append(extrude(rect(X0, -HOLE_Y - 5, X1, HOLE_Y + 5), [], LEG_H, LEG_H + BAR_T, "z"))
    # back block + camera plate in one piece, with 4 screw holes running through
    holes = [circle(sy * CAM_DX, CAM_ZC + sz * CAM_DZ, M2_TAP, 20) for sy in (1, -1) for sz in (1, -1)]
    face = rect(-PLATE_W / 2, LEG_H, PLATE_W / 2, PLATE_Z1)        # (y, z)
    b.append(extrude(face, holes, X0, X1 + PLATE_T, "x"))
    # standoffs on the front face
    for sy in (1, -1):
        for sz in (1, -1):
            y, z = sy * CAM_DX, CAM_ZC + sz * CAM_DZ
            b.append(extrude(circle(y, z, 2.3, 32), [circle(y, z, M2_TAP, 20)],
                             X1 + PLATE_T - 0.5, X1 + PLATE_T + STANDOFF, "x"))
    return b


if __name__ == "__main__":
    bodies = parts()
    for t in bodies:
        assert check_closed(t) == 0
    R = [[0, 0, -1], [0, 1, 0], [1, 0, 0]]          # lay it on its back: forward -> up
    printed = [transform(t, R) for t in bodies]
    zmin = min(t[..., 2].min() for t in printed)
    printed = [transform(t, T=(0, 0, -zmin)) for t in printed]
    out = write_stl(os.path.join(OUT, "camera_mount.stl"), printed, "camera_mount")
    p = out.reshape(-1, 3)
    print("camera_mount", len(out), "tris, print size", np.round(p.max(0) - p.min(0), 1))
