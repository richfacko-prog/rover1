"""Tiny CAD kit: 2D polygons with holes -> extruded watertight solids -> STL."""
import math
import struct
import numpy as np


# ---------- 2D shapes (lists of (u, v) points) ----------
def rect(u0, v0, u1, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def circle(cu, cv, r, n=32):
    return [(cu + r * math.cos(2 * math.pi * i / n), cv + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def stadium(u0, u1, cv, h, n=12):
    """Horizontal slot from u0 to u1 (end to end), height h, centered on v=cv."""
    r = h / 2
    a, b = u0 + r, u1 - r
    pts = []
    for i in range(n + 1):  # right cap, bottom -> top
        t = -math.pi / 2 + math.pi * i / n
        pts.append((b + r * math.cos(t), cv + r * math.sin(t)))
    for i in range(n + 1):  # left cap, top -> bottom
        t = math.pi / 2 + math.pi * i / n
        pts.append((a + r * math.cos(t), cv + r * math.sin(t)))
    return pts


def chamfered_rect(u0, v0, u1, v1, c):
    return [(u0 + c, v0), (u1 - c, v0), (u1, v0 + c), (u1, v1 - c),
            (u1 - c, v1), (u0 + c, v1), (u0, v1 - c), (u0, v0 + c)]


def area(p):
    p = np.asarray(p)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def orient(p, ccw=True):
    p = list(p)
    return p if (area(p) > 0) == ccw else p[::-1]


# ---------- triangulation (ear clipping with hole bridging) ----------
def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _seg_hit(p, q, edges):
    """True if segment p-q properly crosses any edge (array Nx4)."""
    if len(edges) == 0:
        return False
    a, b = edges[:, 0:2], edges[:, 2:4]
    d1 = (q[0] - p[0]) * (a[:, 1] - p[1]) - (q[1] - p[1]) * (a[:, 0] - p[0])
    d2 = (q[0] - p[0]) * (b[:, 1] - p[1]) - (q[1] - p[1]) * (b[:, 0] - p[0])
    d3 = (b[:, 0] - a[:, 0]) * (p[1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (p[0] - a[:, 0])
    d4 = (b[:, 0] - a[:, 0]) * (q[1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (q[0] - a[:, 0])
    eps = 1e-9
    hit = (d1 * d2 < -eps) & (d3 * d4 < -eps)
    return bool(hit.any())


def _edges(ring):
    r = np.asarray(ring, float)
    return np.hstack([r, np.roll(r, -1, axis=0)])


def triangulate(outer, holes):
    """Returns (points Nx2, triangles Mx3) covering outer minus holes (CCW tris)."""
    outer = orient(outer, True)
    holes = [orient(h, False) for h in holes]
    holes.sort(key=lambda h: -max(pt[0] for pt in h))
    poly = list(outer)
    remaining = list(holes)
    while remaining:
        h = remaining.pop(0)
        hi = max(range(len(h)), key=lambda i: h[i][0])
        hp = h[hi]
        other = [_edges(x) for x in remaining] + [_edges(h)]
        other_edges = np.vstack(other) if other else np.zeros((0, 4))
        cands = sorted(range(len(poly)), key=lambda i: (poly[i][0] - hp[0]) ** 2 + (poly[i][1] - hp[1]) ** 2)
        poly_edges = _edges(poly)
        chosen = None
        for ci in cands:
            op = poly[ci]
            if _seg_hit(hp, op, poly_edges) or _seg_hit(hp, op, other_edges):
                continue
            # bridge must leave the outer vertex into the polygon interior
            prv, nxt = poly[ci - 1], poly[(ci + 1) % len(poly)]
            mid = ((hp[0] + op[0]) / 2, (hp[1] + op[1]) / 2)
            if _cross(prv, op, nxt) >= 0:  # convex vertex
                ok = _cross(prv, op, mid) > 0 and _cross(op, nxt, mid) > 0
            else:
                ok = not (_cross(prv, op, mid) <= 0 and _cross(op, nxt, mid) <= 0)
            if ok:
                chosen = ci
                break
        if chosen is None:
            raise RuntimeError("no bridge found")
        hring = h[hi:] + h[:hi]
        poly = poly[:chosen + 1] + hring + [hring[0]] + poly[chosen:]
    pts = np.array(poly, float)
    idx = list(range(len(pts)))
    tris = []
    guard = 0
    i = 0
    while len(idx) > 3:
        guard += 1
        if guard > 50 * len(pts) ** 1:
            if guard > 200 * len(pts):
                raise RuntimeError("ear clipping stuck")
        n = len(idx)
        found = False
        for k in range(n):
            j = (i + k) % n
            a, b, c = idx[j - 1], idx[j], idx[(j + 1) % n]
            A, B, C = pts[a], pts[b], pts[c]
            cr = _cross(A, B, C)
            if cr <= 1e-12:
                if abs(cr) <= 1e-12 and n > 3 and np.allclose(A, C):
                    pass
                continue
            others = np.array([idx[m] for m in range(n) if m not in (j - 1 if j > 0 else n - 1, j, (j + 1) % n)])
            P = pts[others]
            # exclude points coincident with triangle corners (bridge duplicates)
            same = (np.all(np.isclose(P, A), 1) | np.all(np.isclose(P, B), 1) | np.all(np.isclose(P, C), 1))
            P = P[~same]
            if len(P):
                d1 = (B[0] - A[0]) * (P[:, 1] - A[1]) - (B[1] - A[1]) * (P[:, 0] - A[0])
                d2 = (C[0] - B[0]) * (P[:, 1] - B[1]) - (C[1] - B[1]) * (P[:, 0] - B[0])
                d3 = (A[0] - C[0]) * (P[:, 1] - C[1]) - (A[1] - C[1]) * (P[:, 0] - C[0])
                inside = (d1 >= -1e-9) & (d2 >= -1e-9) & (d3 >= -1e-9)
                if inside.any():
                    continue
            tris.append((a, b, c))
            idx.pop(j)
            i = j % len(idx)
            found = True
            break
        if not found:
            # remove a degenerate (collinear) vertex and continue
            for k in range(n):
                j = (i + k) % n
                a, b, c = idx[j - 1], idx[j], idx[(j + 1) % n]
                if abs(_cross(pts[a], pts[b], pts[c])) <= 1e-9:
                    tris.append((a, b, c))  # zero-area sliver keeps edges matched
                    idx.pop(j)
                    found = True
                    break
            if not found:
                raise RuntimeError("ear clipping failed")
    tris.append(tuple(idx))
    return pts, np.array(tris)


# ---------- 3D solids ----------
AXES = {"z": (0, 1, 2), "y": (0, 2, 1), "x": (1, 2, 0)}  # local (u, v, w) -> xyz index


def extrude(outer, holes, w0, w1, axis="z"):
    """Extrude a 2D region along `axis`. For axis 'x' the 2D coords are (y, z);
    for 'y' they are (x, z); for 'z' they are (x, y). Returns triangles (N,3,3)."""
    pts, tri = triangulate(outer, holes)
    tris = []
    for a, b, c in tri:  # top (w1) CCW, bottom (w0) reversed
        tris.append([(*pts[a], w1), (*pts[b], w1), (*pts[c], w1)])
        tris.append([(*pts[a], w0), (*pts[c], w0), (*pts[b], w0)])
    for ring, ccw in [(outer, True)] + [(h, False) for h in holes]:
        r = orient(ring, ccw)
        for k in range(len(r)):
            p, q = r[k], r[(k + 1) % len(r)]
            tris.append([(*p, w0), (*q, w0), (*q, w1)])
            tris.append([(*p, w0), (*q, w1), (*p, w1)])
    t = np.array(tris, float)
    out = np.empty_like(t)
    m = AXES[axis]
    for local, glob in enumerate(m):
        out[..., glob] = t[..., local]
    return fix_winding(out)


def signed_volume(t):
    return np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0


def fix_winding(t):
    if signed_volume(t) < 0:
        t = t[:, [0, 2, 1]]
    return t


def transform(t, R=None, T=(0, 0, 0)):
    t = t.copy()
    if R is not None:
        t = t @ np.asarray(R, float).T
    return t + np.asarray(T, float)


def write_stl(path, bodies, name="part"):
    t = np.vstack(bodies)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 0)
    with open(path, "wb") as f:
        f.write(name.encode().ljust(80, b" ")[:80])
        f.write(struct.pack("<I", len(t)))
        for nn, tri in zip(n, t):
            f.write(struct.pack("<12fH", *nn, *tri.ravel(), 0))
    return t


def check_closed(t):
    """Every edge must be shared by exactly two triangles, in opposite directions."""
    from collections import Counter
    key = lambda p: tuple(np.round(p, 5))
    c = Counter()
    for tri in t:
        for i in range(3):
            c[(key(tri[i]), key(tri[(i + 1) % 3]))] += 1
    bad = sum(1 for (a, b), n in c.items() if c.get((b, a), 0) != n)
    return bad
