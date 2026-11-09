"""
Raspberry Pi 4 case for the rover, with a 25 mm fan (ADDA AD0205DX-K59) in the lid.
Board coordinates: X along the 85 mm side (0 = microSD end, 85 = USB/Ethernet end),
Y along the 56 mm side (0 = USB-C/HDMI/audio edge, 56 = GPIO header edge), Z up.

Base sits over the rover deck's 4 Pi standoffs (sockets underneath).
Lid has 4 tubes that clamp the Pi; one M2.5 x 30 screw per corner goes
lid -> tube -> Pi -> base standoff -> into the deck standoff.
"""
import os
import numpy as np
from cad import rect, circle, extrude, transform, write_stl, check_closed

OUT = os.path.join(os.path.dirname(__file__), "stl")
HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]

X0, X1, Y0, Y1 = -3.0, 88.0, -3.0, 59.0      # outer footprint (91 x 62 mm)
T = 2.0                                       # wall / floor thickness
FLOOR = 2.0
BOARD_Z = 10.0                                # underside of the Pi board
BOARD_TOP = BOARD_Z + 1.4
TOP = BOARD_TOP + 18.0                        # top of walls / underside of lid
LID_T = 2.0
SCREW = 1.45                                  # M2.5 clearance radius
SOCKET = 3.7                                  # fits over the deck's 6.5 mm standoffs
GPIO_X = (6.5, 58.5)                          # opening for the jumper wires
FAN_C, FAN_HOLE, FAN_OPEN = (30.0, 28.0), 10.0, 11.5   # 25 mm fan: 20 mm hole spacing


def base():
    b = []
    b.append(extrude(rect(X0, Y0, X1, Y1), [circle(x, y, SOCKET, 40) for x, y in HOLES], 0, FLOOR, "z"))
    for x, y in HOLES:                                        # standoffs with sockets underneath
        b.append(extrude(circle(x, y, 5.0, 40), [circle(x, y, SOCKET, 40)], 0, 5.3, "z"))
        b.append(extrude(circle(x, y, 5.0, 40), [circle(x, y, SCREW, 24)], 5.3, 6.5, "z"))
        b.append(extrude(circle(x, y, 3.0, 40), [circle(x, y, SCREW, 24)], 6.5, BOARD_Z, "z"))
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
    holes += [circle(x, y, SCREW, 24) for x, y in HOLES]
    holes += [rect(x, 12.0, x + 3.0, 38.0) for x in (48.0, 54.0, 66.0, 72.0, 78.0)]   # vents
    b = [extrude(outline, holes, TOP, TOP + LID_T, "z")]
    for x, y in HOLES:                                        # clamp tubes down onto the board
        b.append(extrude(circle(x, y, 2.75, 40), [circle(x, y, SCREW, 24)], BOARD_TOP, TOP, "z"))
    return b


def drop(bodies):
    z = min(t[..., 2].min() for t in bodies)
    return [transform(t, T=(0, 0, -z)) for t in bodies]


if __name__ == "__main__":
    parts = {"pi_case_base": (base(), None), "pi_case_lid": (lid(), np.diag([1, -1, -1]))}
    for name, (bodies, R) in parts.items():
        for t in bodies:
            assert check_closed(t) == 0, name
        out = write_stl(os.path.join(OUT, name + ".stl"), drop([transform(t, R) for t in bodies]), name)
        p = out.reshape(-1, 3)
        print(name, len(out), "tris", np.round(p.max(0) - p.min(0), 1))
