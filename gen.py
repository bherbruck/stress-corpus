#!/usr/bin/env python3
"""Deterministic generator for the stress corpus.

Items come from kernel axes, not object categories:

  operation x surface x topology x scale x order

A seeded all-pairs (covering array) pass makes sure every feasible pair of
axis values appears in at least one item; random extra combinations then fill
the list up to COUNT. The pairwise items come first (lowest IDs).

Writes items.jsonl: one JSON object per line with
id, operation, surface, topology, scale, order, object, pairwise, brief.

No network, no AI. Same seed, same file, byte for byte:  python3 gen.py
"""
import hashlib
import itertools
import json
import math
import random
import sys

SEED = 20261116
COUNT = 10000

AXES = {
    "operation": [
        "extrude", "cut", "revolve", "sweep", "loft", "shell",
        "fillet (constant)", "fillet (variable)", "chamfer", "draft",
        "pattern (linear)", "pattern (circular)", "pattern (along a path)",
        "mirror", "boolean join", "boolean cut", "boolean intersect",
        "thread", "sheet-metal flange", "sheet-metal bend", "split",
        "offset face",
    ],
    "surface": ["plane", "cylinder", "cone", "sphere", "torus", "spline"],
    "topology": [
        "clean", "tangent edges", "coplanar faces", "vertex on an edge",
        "thin wall near tolerance", "feature at a seam or pole",
        "self-touching body", "multiple bodies", "edge chain around a corner",
    ],
    "scale": ["tiny", "normal", "huge", "extreme ratio"],
    "order": [
        "none", "before fillet", "after fillet", "before shell",
        "after shell", "before pattern", "after pattern",
    ],
}
KEYS = list(AXES)


def feasible(row):
    op, su, to, sc, orr = row
    if op.startswith("sheet-metal"):
        if su not in ("plane", "spline") or orr in ("before shell", "after shell"):
            return False
        if to == "thin wall near tolerance":
            return False
    if op == "thread" and su not in ("plane", "cylinder", "cone"):
        return False
    if op == "draft" and su in ("sphere", "torus"):
        return False
    if to == "feature at a seam or pole" and su == "plane":
        return False
    if to == "edge chain around a corner" and su not in ("plane", "cylinder", "spline"):
        return False
    if op == "shell" and orr in ("before shell", "after shell"):
        return False
    if op.startswith("fillet") and orr in ("before fillet", "after fillet"):
        return False
    if op.startswith("pattern") and orr in ("before pattern", "after pattern"):
        return False
    return True


# ------------------------------------------------------------------ numbers
def sig(x, n=2):
    if x == 0:
        return 0.0
    return round(x, -int(math.floor(math.log10(abs(x)))) + (n - 1))


def fmt(x):
    x = sig(x, 3) if abs(x) < 1e6 else x
    if x == int(x) and abs(x) < 1e9:
        return str(int(x))
    s = ("%.6f" % x).rstrip("0").rstrip(".")
    return s


# ------------------------------------------------------------------ bodies
TUBE_T = {"tiny": 0.2, "normal": 1.5, "huge": 6, "extreme ratio": 1}
THIN = {"tiny": 0.01, "normal": 0.02, "huge": 0.05, "extreme ratio": 0.005}


def body(surface, scale, sheet, rng):
    """Return dict: text, F (face name), C (centre phrase), hu, Wmin, H, loop."""
    d = {"F": "top face", "loop": None, "C": None, "z0": 0.0}
    if sheet:
        A, B = {"tiny": (4, 3), "normal": (60, 40), "huge": (2400, 1600),
                "extreme ratio": (1000, 200)}[scale]
        T = TUBE_T[scale]
        if surface == "plane":
            d["text"] = "a flat %s × %s mm sheet of thickness %s mm, centred on the origin" % (fmt(A), fmt(B), fmt(T))
            d["Wmin"], d["hu"] = min(A, B), A / 2.0
        else:
            d["text"] = "a flat sheet of thickness %s mm with a closed spline outline (see below), centred on the origin" % fmt(T)
            d["Wmin"], d["hu"] = 0.8 * B, A / 2.0
            d["text"] += spline_text(A, B)
        d["H"] = T
        d["fh"] = sig(0.15 * d["Wmin"])
        d["A"] = A
        d["T"] = T
    elif surface == "plane":
        A, B, H = {"tiny": (4, 3, 2), "normal": (60, 40, 25), "huge": (2400, 1600, 1000),
                   "extreme ratio": (1000, 200, 1)}[scale]
        d["text"] = "a %s × %s × %s mm block, centred on the origin and resting on Z = 0" % (fmt(A), fmt(B), fmt(H))
        d.update(Wmin=min(A, B), hu=A / 2.0, H=H)
    elif surface == "cylinder":
        D, H = {"tiny": (3, 4), "normal": (40, 60), "huge": (1200, 2400),
                "extreme ratio": (1, 1000)}[scale]
        d["text"] = "a Ø%s × %s mm cylinder with a vertical axis through the origin, resting on Z = 0" % (fmt(D), fmt(H))
        d.update(Wmin=D, hu=D / 2.0, H=H)
    elif surface == "cone":
        D1, D2, H = {"tiny": (4, 2, 3), "normal": (50, 20, 50), "huge": (2000, 800, 2000),
                     "extreme ratio": (6, 1, 1000)}[scale]
        d["text"] = "a cone frustum with a vertical axis through the origin, Ø%s mm at the bottom (Z = 0), Ø%s mm at the top, %s mm tall" % (fmt(D1), fmt(D2), fmt(H))
        d.update(Wmin=D2, hu=D2 / 2.0, H=H)
    elif surface == "sphere":
        D = {"tiny": 4, "normal": 50, "huge": 2400, "extreme ratio": 1000}[scale]
        R = D / 2.0
        if scale == "extreme ratio":
            fr = 0.5
            k = math.sqrt(R * R - fr * fr)
            flat = 1.0
            gap = R - k
            cut = ("the plane Z = %s mm, which is %s mm below the pole and leaves a flat of Ø%s mm" % (
                ("%.7f" % k).rstrip("0"), ("%.5f" % gap).rstrip("0"), fmt(flat)))
        else:
            k = 0.6 * R
            flat = 2 * math.sqrt(R * R - k * k)
            cut = "the plane Z = %s mm, leaving a flat of Ø%s mm" % (fmt(k), fmt(flat))
        d["text"] = "a sphere of Ø%s mm centred on the origin, with the top removed by %s; the body is the part below that plane" % (fmt(D), cut)
        d.update(Wmin=flat, hu=flat / 2.0, H=R + k, F="flat cap face", z0=-R)
    elif surface == "torus":
        Dm, Dt = {"tiny": (3.6, 1.2), "normal": (60, 16), "huge": (3000, 800),
                  "extreme ratio": (1000, 1)}[scale]
        d["text"] = ("the upper half (Z ≥ 0) of a torus about the Z axis: centre-circle Ø%s mm, tube Ø%s mm, "
                     "cut by the plane Z = 0, so the body has a flat annular face at Z = 0") % (fmt(Dm), fmt(Dt))
        d.update(Wmin=Dt, hu=Dt / 2.0, H=Dt / 2.0, F="flat cut face",
                 C="the point on the centre circle of the flat cut face at +X (X = %s mm, Y = 0)" % fmt(Dm / 2.0),
                 loop="both edge loops (inner and outer circle) of the flat cut face")
    else:  # spline
        A, B, H = {"tiny": (4, 3, 2), "normal": (60, 40, 25), "huge": (2400, 1600, 1000),
                   "extreme ratio": (1000, 200, 1)}[scale]
        d["text"] = "a %s mm tall extrusion, from Z = 0, of a closed spline outline (see below)%s" % (fmt(H), spline_text(A, B))
        d.update(Wmin=0.8 * B, hu=A / 2.0, H=H)
    if d["C"] is None:
        d["C"] = "the centre of the %s" % d["F"]
    if d["loop"] is None:
        d["loop"] = "the outer edge loop of the %s" % d["F"]
    return d


def spline_text(A, B):
    pts = []
    for k in range(8):
        th = k * math.pi / 4
        f = 1 + 0.1 * math.sin(3 * th)
        pts.append("(%s, %s)" % (fmt(0.5 * A * f * math.cos(th)), fmt(0.5 * B * f * math.sin(th))))
    return " [a closed periodic cubic spline through the points (X, Y) mm: %s]" % ", ".join(pts)


# ------------------------------------------------------------------ steps
def ex(x):
    """Exact number (no significant-figure rounding), for tangent/edge positions."""
    x = round(x, 6)
    return str(int(x)) if x == int(x) else ("%.6f" % x).rstrip("0").rstrip(".")


def inset(hu, e):
    """Offset along +X, from the local origin, for a small feature that must not touch the edge."""
    return hu - 0.1 * e if hu <= 1.2 * e else 0.6 * hu


def prelude(topo, b, e, scale):
    """Setup step that creates the topology situation. Sizes from e."""
    F, hu, C = b["F"], b["hu"], b["C"]
    s = sig(0.12 * e)
    h = sig(0.12 * e)
    u0 = ex(inset(hu, e))
    dd = fmt(0.5 * min(b["H"], e))
    if topo == "clean":
        return ""
    if topo == "tangent edges":
        return ("Add a \u00d8%s mm boss, %s mm tall, on the %s with its centre %s mm from %s toward +X, "
                "so its side is exactly tangent to the face's outer edge." % (fmt(s), fmt(h), F, ex(hu - s / 2.0), C))
    if topo == "coplanar faces":
        return ("Add a %s \u00d7 %s mm square pad, %s mm tall, on the %s with its centre %s mm from %s toward +X, "
                "and a second identical pad directly beside it toward +Y sharing one side face, "
                "so the two pad tops are exactly coplanar and the two pads touch face to face." % (
                    fmt(s), fmt(s), fmt(h), F, u0, C))
    if topo == "vertex on an edge":
        return ("Add a %s \u00d7 %s mm square pad, %s mm tall, on the %s, rotated 45\u00b0 about the vertical axis, "
                "with its +X corner vertex exactly on the face's outer edge at the +X point." % (
                    fmt(s), fmt(s), fmt(h), F))
    if topo == "thin wall near tolerance":
        tw = THIN[scale]
        return ("Drill a \u00d8%s mm blind hole, %s mm deep, in the %s with its centre %s mm from %s toward +X, "
                "so only a %s mm wall remains between the hole and the outer edge." % (
                    fmt(s), dd, F, ex(hu - tw - s / 2.0), C, fmt(tw)))
    if topo == "feature at a seam or pole":
        seam = {"cylinder": "the cylinder's 0\u00b0 seam line (at +X)",
                "cone": "the cone's 0\u00b0 seam line (at +X)",
                "sphere": "the sphere's 0\u00b0 meridian seam (at +X)",
                "torus": "the torus's 0\u00b0 meridian seam (at +X)",
                "spline": "the point where the periodic spline closes (the +X point)"}[b["su"]]
        return ("Cut a \u00d8%s mm notch, %s mm deep, centred exactly on the outer edge of the %s at %s, "
                "so it straddles the seam." % (fmt(s), dd, F, seam))
    if topo == "self-touching body":
        return ("Add two \u00d8%s mm cylinders, %s mm tall, standing on the %s with centres %s mm from %s toward +X "
                "and exactly %s mm apart in Y, so they touch along a single vertical line while both fuse to the face "
                "(the body touches itself there)." % (fmt(s), fmt(h), F, u0, C, fmt(s)))
    if topo == "multiple bodies":
        gap = sig(0.1 * e)
        return ("Add a separate \u00d8%s mm cylinder body, %s mm tall, standing on Z = 0 with its nearest side %s mm outside "
                "the body toward +X, and do not merge it." % (fmt(s), fmt(h), fmt(gap)))
    if topo == "edge chain around a corner":
        return ("Cut a %s \u00d7 %s mm square notch, %s mm deep, with its centre exactly on the outer edge of the %s at +Y "
                "(the notch corners turn the edge chain)." % (fmt(s), fmt(s), dd, F))
    raise ValueError(topo)


def pattern_step(b, e):
    F, C = b["F"], b["C"]
    d, p, dep = sig(0.1 * e), sig(0.15 * e), sig(0.4 * min(b["H"], e))
    u = ex(inset(b["hu"], e))
    return ("cut a \u00d8%s mm hole, %s mm deep, in the %s %s mm from %s toward -X, then repeat it "
            "in a linear pattern of 3 along Y at %s mm pitch" % (fmt(d), fmt(dep), F, u, C, fmt(p)))


def op_step(op, b, e, scale):
    F, C, loop = b["F"], b["C"], b["loop"]
    d = sig(0.1 * e)
    dep = sig(0.4 * min(b["H"], e))
    r = sig(0.07 * e)
    w = sig(0.05 * e)
    c = sig(0.05 * e)
    p = sig(0.15 * e)
    if op == "extrude":
        return "Extrude a Ø%s mm circle sketched at %s upward %s mm to add a boss." % (fmt(d), C, fmt(dep))
    if op == "cut":
        return "Cut a Ø%s mm hole at %s, %s mm deep." % (fmt(d), C, fmt(dep))
    if op == "revolve":
        g = sig(0.04 * e)
        return ("Sketch a %s × %s mm square whose centre is %s mm from the vertical axis through %s, and revolve it 360° "
                "about that axis to cut a ring groove into the %s." % (fmt(g), fmt(g), fmt(1.5 * d), C, F))
    if op == "sweep":
        return ("Sweep a Ø%s mm circle along a 90° arc of radius %s mm that leaves %s going straight up and ends heading toward +Y, "
                "to add a bent tube." % (fmt(d), fmt(3 * d), C))
    if op == "loft":
        return ("Loft a neck %s mm tall from a %s × %s mm square sketched at %s to a Ø%s mm circle on a plane %s mm above it." % (
            fmt(dep), fmt(d), fmt(d), C, fmt(d), fmt(dep)))
    if op == "shell":
        return "Hollow the body to %s mm walls, removing the %s." % (fmt(w), F)
    if op == "fillet (constant)":
        return "Fillet %s with a constant %s mm radius." % (loop, fmt(r))
    if op == "fillet (variable)":
        return ("Fillet %s with a variable radius: %s mm at the +X point, rising linearly to %s mm at the opposite point." % (
            loop, fmt(r), fmt(2 * r)))
    if op == "chamfer":
        return "Chamfer %s with an unequal chamfer, %s mm down the side and %s mm across the face." % (loop, fmt(c), fmt(2 * c))
    if op == "draft":
        return "Draft all side faces by 3°, with the bottom face as the neutral plane, so the body narrows toward the %s." % F
    if op == "pattern (linear)":
        return "Cut a Ø%s mm hole at %s, %s mm deep, then repeat it in a linear pattern of 3 along Y at %s mm pitch (centred on the hole)." % (
            fmt(d), C, fmt(dep), fmt(p))
    if op == "pattern (circular)":
        return ("Cut a Ø%s mm hole %s mm deep, centred %s mm from the vertical axis through %s, then repeat it 6 times in a circular pattern about that axis." % (
            fmt(d), fmt(dep), fmt(1.5 * d), C))
    if op == "pattern (along a path)":
        return ("Cut a Ø%s mm hole %s mm deep at %s, then repeat it 4 times, %s mm apart measured along a path, following an arc "
                "in the %s that curves toward +Y with a %s mm radius." % (fmt(d), fmt(dep), C, fmt(p), F, fmt(4 * p)))
    if op == "mirror":
        return ("Add a %s × %s mm square boss, %s mm tall, centred %s mm from %s toward +Y, then mirror it across the XZ plane through the face centre." % (
            fmt(d), fmt(d), fmt(dep), fmt(1.5 * d), C))
    if op == "boolean join":
        return "Make a separate Ø%s mm sphere centred on the %s at %s and join it to the body." % (fmt(2 * d), F, C)
    if op == "boolean cut":
        return "Make a separate Ø%s mm cylinder, %s mm long, lying along the Y axis with its axis %s mm below the %s at %s, and subtract it from the body." % (
            fmt(2 * d), fmt(8 * d), fmt(d / 2.0), F, C)
    if op == "boolean intersect":
        return ("Make a separate sphere of Ø%s mm centred on the body's bounding-box centre, and keep only the intersection of the body with it." % (
            fmt(1.2 * math.sqrt(b["Wmin"] ** 2 + b["H"] ** 2))))
    if op == "thread":
        n, pi, ln = {"tiny": (1.6, 0.35, 1.6), "normal": (12, 1.75, 14), "huge": (100, 6, 120),
                     "extreme ratio": (1, 0.25, 0.5)}[scale]
        return ("Add a Ø%s mm boss, %s mm tall, at %s and model an M%s × %s external thread over its full length, "
                "with a %s mm chamfer at the tip." % (fmt(n), fmt(ln), C, fmt(n), fmt(pi), fmt(pi)))
    if op == "sheet-metal flange":
        if b["su"] == "plane":
            where = "along the +X edge"
        else:
            where = "along the spline edge between the outline points at -45° and +45° (around +X)"
        return ("Bend a %s mm tall flange up 90° %s, with an inside bend radius of %s mm (the thickness) and a K-factor of 0.44." % (
            fmt(b["fh"]), where, fmt(b["T"])))
    if op == "sheet-metal bend":
        x = sig(0.2 * b["A"])
        return ("Fold the part of the sheet beyond X = %s mm up by 90° about the straight bend line X = %s mm (parallel to Y), "
                "inside radius %s mm, K-factor 0.44." % (fmt(x), fmt(x), fmt(b["T"])))
    if op == "split":
        z = sig(b["z0"] + 0.5 * b["H"], 4)
        return "Split the body with the plane Z = %s mm into two bodies and keep both." % fmt(z)
    if op == "offset face":
        return "Offset the %s outward by %s mm (move the face along its normal, keeping the side faces connected)." % (F, fmt(dep))
    raise ValueError(op)


def order_before(order, b, e):
    if order == "after fillet":
        return "Fillet %s with %s mm." % (b["loop"], fmt(sig(0.05 * e)))
    if order == "after shell":
        return "Hollow the body to %s mm walls leaving a closed internal void (no face removed)." % fmt(sig(0.06 * e))
    if order == "after pattern":
        return cap(pattern_step(b, e)) + "."
    return ""


def order_after(order, b, e):
    if order == "before fillet":
        return "Fillet %s with %s mm." % (b["loop"], fmt(sig(0.05 * e)))
    if order == "before shell":
        return "Hollow the body to %s mm walls leaving a closed internal void (no face removed)." % fmt(sig(0.06 * e))
    if order == "before pattern":
        return cap(pattern_step(b, e)) + "."
    return ""


def cap(t):
    return t[0].upper() + t[1:]


OBJECTS = {
    "plane": ["bracket", "spacer block", "shim", "label plate", "tile", "panel", "base plate", "bookend"],
    "cylinder": ["peg", "rod", "knob blank", "pin", "spacer", "handle", "bushing", "bollard"],
    "cone": ["funnel", "nozzle", "lamp shade", "traffic cone", "tip"],
    "sphere": ["ball", "bead", "dome cover", "finial", "ball joint housing"],
    "torus": ["ring", "O-ring seat", "hoop", "bangle", "donut"],
    "spline": ["guitar pick", "leaf", "paddle", "pebble", "key fob", "cam"],
}


def brief_for(row):
    op, su, to, sc, orr = row
    rng = random.Random(int(hashlib.sha256(("%d:%s" % (SEED, "|".join(row))).encode()).hexdigest()[:16], 16))
    sheet = op.startswith("sheet-metal")
    b = body(su, sc, sheet, rng)
    b["su"] = su
    e = min(b["Wmin"], 4 * b["H"])
    obj = rng.choice(OBJECTS[su]) if rng.random() < 0.6 else ""
    head = ("Like a %s: model " % obj) if obj else "Model "
    steps = [order_before(orr, b, e), prelude(to, b, e, sc), op_step(op, b, e, sc), order_after(orr, b, e)]
    steps = [x for x in steps if x]
    text = head + b["text"] + "."
    if len(steps) == 1:
        text += " " + steps[0]
    else:
        text += " " + " ".join("(%d) %s" % (i + 1, x) for i, x in enumerate(steps))
    return obj, text


# ------------------------------------------------------------------ pairwise
def all_rows():
    return [r for r in itertools.product(*[AXES[k] for k in KEYS]) if feasible(r)]


def pairs_of(row):
    return [((i, row[i]), (j, row[j])) for i, j in itertools.combinations(range(len(row)), 2)]


def covering(rows, rng):
    index = {}
    for ri, r in enumerate(rows):
        for p in pairs_of(r):
            index.setdefault(p, []).append(ri)
    uncovered = set(index)
    chosen = []
    plist = sorted(index)
    while uncovered:
        target = rng.choice(sorted(uncovered))
        cands = rng.sample(index[target], min(80, len(index[target])))
        best = max(cands, key=lambda ri: sum(1 for p in pairs_of(rows[ri]) if p in uncovered))
        chosen.append(best)
        for p in pairs_of(rows[best]):
            uncovered.discard(p)
    return chosen, len(index)


def main(out="items.jsonl"):
    rng = random.Random(SEED)
    rows = all_rows()
    pw, npairs = covering(rows, rng)
    print("feasible rows:", len(rows), "pairs:", npairs, "pairwise items:", len(pw), file=sys.stderr)
    pwset = set(pw)
    rest = [i for i in range(len(rows)) if i not in pwset]
    rng.shuffle(rest)
    order = pw[:]
    rng.shuffle(order)
    order = order + rest[:COUNT - len(order)]
    if len(order) < COUNT:
        sys.exit("not enough feasible rows: %d" % len(order))
    seen = set()
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for n, ri in enumerate(order, 1):
            r = rows[ri]
            obj, brief = brief_for(r)
            assert brief not in seen
            seen.add(brief)
            item = {"id": "S%04d" % n, "operation": r[0], "surface": r[1], "topology": r[2],
                    "scale": r[3], "order": r[4], "object": obj, "pairwise": ri in pwset, "brief": brief}
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print("wrote", len(order), "items to", out, file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:2])
