"""
Bolt-down Raspberry Pi 4 case for the rover's upper deck (also fits a Pi 3: same holes).

Differences from pi_case.py:
  * The base is fixed to the chassis on its own: two rear ears share the deck's rear
    post screws, so the case stays put with the Pi and lid off.
  * The lid has its own 4 screws into corner bosses, so it comes off without
    unscrewing the Pi.
  * Slot in the lid for the camera ribbon, right above the CSI connector.

Board coordinates: X along the 85 mm side (0 = microSD end, 85 = USB/Ethernet end),
Y along the 56 mm side (0 = USB-C/HDMI/audio edge, 56 = GPIO header edge), Z up.
On the rover: deck x = -13 - X, deck y = Y - 28 (USB/Ethernet end faces the rear).
"""
import os
import numpy as np
from cad import rect, circle, extrude, transform, write_stl, check_closed

OUT = os.path.join(os.path.dirname(__file__), "stl")
os.makedirs(OUT, exist_ok=True)

HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]   # Pi mounting holes
X0, X1, Y0, Y1 = -3.0, 88.0, -8.5, 64.5       # outer footprint (91 x 73 mm)
T = 2.0                                       # wall thickness
FLOOR = 2.0
BOARD_Z = 10.0                                # underside of the Pi board
BOARD_TOP = BOARD_Z + 1.4
TOP = BOARD_TOP + 18.0                        # top of walls / underside of lid
LID_T = 2.0
M25_CLEAR = 1.45                              # M2.5 clearance radius
M3_CLEAR = 1.7                                # M3 clearance radius
M3_TAP = 1.4                                  # M3 self-tapping into plastic
SOCKET = 3.7                                  # fits over the deck's 6.5 mm Pi standoffs
GPIO_X = (6.5, 58.5)                          # opening for the jumper wires
FAN_C, FAN_HOLE, FAN_OPEN = (30.0, 28.0), 10.0, 11.5   # 25 mm fan, 20 mm hole spacing
LID_BOSSES = [(0.5, -4.5), (80.0, -4.5), (0.5, 60.5), (80.0, 60.5)]
EAR_X = (77.0, 87.0)                          # rear ears over the deck's rear posts
EAR_HOLES = [(82.5, -12.0), (82.5, 68.0)]     # = deck posts at (-95.5, +/-40)
EAR_T = 3.0
RIBBON = rect(36.0, 9.0, 54.0, 13.0)          # camera ribbon slot over the CSI connector


def base():
    b = []
    b.append(extrude(rect(X0, Y0, X1, Y1), [circle(x, y, SOCKET, 40) for x, y in HOLES], 0, FLOOR, "z"))
    for x, y in HOLES:                                        # Pi standoffs, socketed over the deck's
        b.append(extrude(circle(x, y, 5.0, 40), [circle(x, y, SOCKET, 40)], 0, 5.3, "z"))
        b.append(extrude(circle(x, y, 5.0, 40), [circle(x, y, M25_CLEAR, 24)], 5.3, 6.5, "z"))
        b.append(extrude(circle(x, y, 3.0, 40), [circle(x, y, M25_CLEAR, 24)], 6.5, BOARD_Z, "z"))
    for x, y in LID_BOSSES:                                   # lid screw bosses
        b.append(extrude(circle(x, y, 3.2, 40), [], 0, FLOOR, "z"))
        b.append(extrude(circle(x, y, 3.2, 40), [circle(x, y, M3_TAP, 24)], FLOOR, TOP, "z"))
    # mounting ears (same screws as the upper deck's two rear posts)
    b.append(extrude(rect(EAR_X[0], -17.0, EAR_X[1], Y0 + 1.0), [circle(*EAR_HOLES[0], M3_CLEAR, 24)], 0, EAR_T, "z"))
    b.append(extrude(rect(EAR_X[0], Y1 - 1.0, EAR_X[1], 73.0), [circle(*EAR_HOLES[1], M3_CLEAR, 24)], 0, EAR_T, "z"))
    for y0, y1 in ((-17.0, Y0 + 1.0), (Y1 - 1.0, 73.0)):     # small gussets so the ears don't flex
        for x0 in (EAR_X[0], EAR_X[1] - 2.0):
            near = Y0 if y0 < 0 else Y1
            far = y0 + 3.0 if y0 < 0 else y1 - 3.0
            b.append(extrude([(near, EAR_T - 0.5), (far, EAR_T - 0.5), (near, 9.0)] if y0 < 0
                             else [(far, EAR_T - 0.5), (near, EAR_T - 0.5), (near, 9.0)],
                             [], x0, x0 + 2.0, "x"))
    # HDMI / USB-C / audio side (y = Y0): long port window
    b.append(extrude(rect(X0, 0, X1, TOP), [rect(2.0, BOARD_Z - 1, 63.0, BOARD_TOP + 10)], Y0, Y0 + T, "y"))
    # GPIO side (y = Y1): open from board level to the top for the jumper wires
    gp = [(X0, 0), (X1, 0), (X1, TOP), (GPIO_X[1], TOP), (GPIO_X[1], BOARD_TOP),
          (GPIO_X[0], BOARD_TOP), (GPIO_X[0], TOP), (X0, TOP)]
    b.append(extrude(gp, [], Y1 - T, Y1, "y"))
    # microSD end (x = X0): slot for the card
    b.append(extrude(rect(Y0 + T, 0, Y1 - T, TOP), [rect(17.0, FLOOR + 1, 39.0, BOARD_TOP + 1)], X0, X0 + T, "x"))
    # USB / Ethernet end (x = X1): low lip only, ports fully open
    b.append(extrude(rect(Y0 + T, 0, Y1 - T, BOARD_Z - 1), [], X1 - T, X1, "x"))
    return b


def lid():
    outline = [(X0, Y0), (X1, Y0), (X1, Y1), (GPIO_X[1], Y1), (GPIO_X[1], 47.5),
               (GPIO_X[0], 47.5), (GPIO_X[0], Y1), (X0, Y1)]
    fx, fy = FAN_C
    holes = [circle(fx, fy, FAN_OPEN, 64)]
    holes += [circle(fx + dx, fy + dy, 1.15, 20) for dx in (-FAN_HOLE, FAN_HOLE) for dy in (-FAN_HOLE, FAN_HOLE)]
    holes += [circle(x, y, M3_CLEAR, 24) for x, y in LID_BOSSES]
    holes.append(RIBBON)
    holes += [rect(x, 17.0, x + 3.0, 42.0) for x in (48.0, 54.0, 60.0, 66.0, 72.0)]   # vents
    return [extrude(outline, holes, TOP, TOP + LID_T, "z")]


def drop(bodies):
    z = min(t[..., 2].min() for t in bodies)
    return [transform(t, T=(0, 0, -z)) for t in bodies]


if __name__ == "__main__":
    parts = {"pi_case_bolt_base": base(), "pi_case_bolt_lid": lid()}   # both print as oriented
    for name, bodies in parts.items():
        for t in bodies:
            assert check_closed(t) == 0, name
        out = write_stl(os.path.join(OUT, name + ".stl"), drop(bodies), name)
        p = out.reshape(-1, 3)
        print(name, len(out), "tris", np.round(p.max(0) - p.min(0), 1))
