#!/usr/bin/env python3
"""Deterministic generator for the stress corpus.

Writes items.jsonl: one JSON object per line with
id, category, features, size, difficulty, brief.

No network, no randomness beyond a fixed seed. Run: python3 gen.py
Same seed, same file, byte for byte.
"""
import hashlib
import json
import math
import random
import sys

SEED = 20261116
COUNT = 10000
SIZES = ["small", "medium", "large"]
DIFFS = ["easy", "medium", "hard"]
SCALE = {"small": 0.6, "medium": 1.0, "large": 1.8}
PLATE_T = {"small": 0.75, "medium": 1.0, "large": 1.5}

MSIZES = [4, 5, 6, 8, 10, 12, 16, 20, 24, 30, 36, 42, 48]
PITCH = {4: 0.7, 5: 0.8, 6: 1, 8: 1.25, 10: 1.5, 12: 1.75, 16: 2, 20: 2.5,
         24: 3, 30: 3.5, 36: 4, 42: 4.5, 48: 5}
HOLES = [2, 2.5, 3, 4, 5, 6, 8, 10, 12]


class Skip(Exception):
    pass


def fmt(x):
    x = round(x * 2) / 2 if abs(x - round(x)) > 0.05 and x >= 3 else round(x, 1)
    return str(int(x)) if x == int(x) else ("%.1f" % x).rstrip("0").rstrip(".")


def nice(x):
    if x >= 80:
        return int(round(x / 10.0) * 10)
    if x >= 30:
        return int(round(x / 5.0) * 5)
    return max(1, int(round(x)))


def std_le(x, lst):
    best = lst[0]
    for v in lst:
        if v <= x:
            best = v
    return best


# kind: prism (a x b x h block), round (D x h cylinder), plate (a x b x t sheet)
# (name, kind, a, b, h, materials)
CATEGORIES = [
    ("wall bracket", "plate", 60, 40, 3, ["steel", "aluminium", "stainless steel"]),
    ("shelf bracket", "plate", 120, 80, 4, ["steel", "aluminium"]),
    ("mounting plate", "plate", 100, 70, 4, ["aluminium", "steel"]),
    ("hinge leaf", "plate", 70, 40, 2, ["brass", "steel", "stainless steel"]),
    ("name sign plate", "plate", 150, 50, 3, ["acrylic", "aluminium", "brass"]),
    ("switch cover plate", "plate", 115, 75, 3, ["ABS plastic", "steel"]),
    ("baking tray blank", "plate", 300, 200, 2, ["aluminium", "stainless steel"]),
    ("garden plant label", "plate", 100, 25, 2, ["zinc", "copper", "polypropylene"]),
    ("spring clip strip", "plate", 80, 15, 1, ["spring steel", "phosphor bronze"]),
    ("printer bed shim", "plate", 90, 90, 3, ["aluminium", "PEI-coated steel"]),
    ("cable cover plate", "plate", 140, 60, 2, ["steel", "ABS plastic"]),
    ("puzzle tile", "plate", 50, 50, 5, ["birch plywood", "PLA plastic"]),
    ("electronics enclosure", "prism", 100, 70, 35, ["ABS plastic", "aluminium"]),
    ("storage box", "prism", 160, 110, 70, ["polypropylene", "PETG plastic"]),
    ("phone stand", "prism", 90, 75, 60, ["aluminium", "walnut", "PLA plastic"]),
    ("desk pen tray", "prism", 200, 60, 25, ["oak", "PLA plastic"]),
    ("drawer organizer", "prism", 180, 120, 45, ["PETG plastic", "birch plywood"]),
    ("bookend", "prism", 120, 90, 100, ["steel", "oak"]),
    ("stool", "prism", 320, 320, 450, ["pine", "oak"]),
    ("table leg", "prism", 60, 60, 700, ["oak", "ash"]),
    ("cutting board", "prism", 350, 250, 20, ["maple", "bamboo"]),
    ("hand tool handle", "prism", 120, 35, 30, ["ash", "nylon"]),
    ("clamp jaw", "prism", 80, 40, 30, ["steel", "aluminium"]),
    ("extruder mount", "prism", 60, 45, 30, ["PETG plastic", "aluminium"]),
    ("camera case", "prism", 130, 90, 60, ["ABS plastic", "polycarbonate"]),
    ("pill case", "prism", 70, 45, 20, ["polypropylene", "aluminium"]),
    ("toy block", "prism", 48, 32, 19, ["beech", "ABS plastic"]),
    ("sign post", "prism", 80, 80, 600, ["pine", "aluminium"]),
    ("garden bed corner", "prism", 90, 90, 150, ["cedar", "galvanised steel"]),
    ("pipe junction block", "prism", 70, 50, 50, ["brass", "PVC"]),
    ("knob", "round", 40, 40, 25, ["aluminium", "ABS plastic", "brass"]),
    ("spur gear blank", "round", 60, 60, 12, ["steel", "nylon", "brass"]),
    ("belt pulley", "round", 50, 50, 20, ["aluminium", "steel"]),
    ("bottle cap", "round", 38, 38, 18, ["HDPE plastic", "aluminium"]),
    ("mug", "round", 80, 80, 95, ["ceramic", "stainless steel"]),
    ("bowl", "round", 150, 150, 70, ["ceramic", "bamboo", "stainless steel"]),
    ("lamp base", "round", 120, 120, 40, ["steel", "brass", "marble"]),
    ("lamp shade", "round", 200, 200, 150, ["PLA plastic", "aluminium"]),
    ("plant pot", "round", 120, 120, 110, ["terracotta", "polypropylene"]),
    ("pipe fitting", "round", 40, 40, 45, ["brass", "PVC", "copper"]),
    ("spacer", "round", 30, 30, 15, ["aluminium", "nylon"]),
    ("bushing", "round", 30, 30, 25, ["bronze", "PTFE"]),
    ("flanged bolt head", "round", 36, 36, 14, ["steel", "stainless steel"]),
    ("toy wheel", "round", 60, 60, 20, ["beech", "rubber", "ABS plastic"]),
    ("filament spool", "round", 200, 200, 65, ["PETG plastic", "cardboard-free ABS plastic"]),
    ("candle holder", "round", 70, 70, 50, ["brass", "glass", "ceramic"]),
    ("coaster", "round", 95, 95, 8, ["cork", "silicone", "slate"]),
    ("hose adapter", "round", 45, 45, 50, ["brass", "polypropylene"]),
    ("round cable clip", "round", 28, 28, 15, ["nylon", "polypropylene"]),
    ("pedestal stand", "round", 140, 140, 90, ["aluminium", "oak"]),
    ("hinge barrel", "round", 25, 25, 60, ["stainless steel", "brass"]),
    ("vase", "round", 100, 100, 220, ["glass", "ceramic"]),
]

# ---------- atoms ----------
# Each atom: (key, label, kinds, builder). Builder(c) returns a sentence and may
# set flags in c.  c has: a b h f kind idx(0..2) rng size.


def hole_layout(c, d, cluster=None):
    """Return (count, sentence fragment) for a hole pattern."""
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    if kind == "round":
        n = [4, 6, 8][i]
        pcd = nice(0.7 * a)
        return n, "evenly spaced on a Ø%s mm bolt circle, the first at 0° on the +X axis" % fmt(pcd)
    cols, rows = [(2, 2), (3, 2), (3, 3)][i]
    px = round(0.7 * a / (cols - 1), 1)
    py = round(0.7 * b / (rows - 1), 1)
    n = cols * rows - (1 if i == 2 else 0)
    s = "in a %d × %d grid, %s mm apart in X and %s mm apart in Y, centred on the top face" % (
        cols, rows, fmt(px), fmt(py))
    if i == 2:
        s += " (the centre position left empty)"
    return n, s


def a_holes(c):
    f, h, i = c["f"], c["h"], c["idx"]
    d = std_le(0.12 * f, [3, 4, 5, 6, 8, 10])
    n, where = hole_layout(c, d)
    s = "Drill %d through holes of Ø%s mm %s." % (n, fmt(d), where)
    if i == 2 and c["kind"] != "plate" and h >= d * 0.6 + 5:
        s = "Drill %d through holes of Ø%s mm %s, each with a Ø%s mm counterbore %s mm deep." % (
            n, fmt(d), where, fmt(d * 2), fmt(d * 0.6))
    c["holes"] = True
    return s


def a_csk(c):
    f, h = c["f"], c["h"]
    d = std_le(min(0.12 * f, 1.6 * h), HOLES)
    n, where = hole_layout(c, d)
    return "Cut %d countersunk holes for M%s flat-head screws (Ø%s mm clearance, 90° countersink to Ø%s mm) %s." % (
        n, fmt(d), fmt(d + 0.4), fmt(d * 2), where)


def a_fillet(c):
    f, h, kind, i = c["f"], c["h"], c["kind"], c["idx"]
    if kind == "plate":
        r = max(2, round(f * 0.08))
        r = min(r, f * 0.2)
        s = "Round the four plan-view corners with a %s mm radius." % fmt(r)
        if i == 2:
            r2 = round(h * 0.3, 1)
            s += " Then fillet the top perimeter edge with %s mm." % fmt(r2)
        return s
    r = max(1, round(min(f, h) * 0.08))
    if kind == "prism":
        s = "Fillet the four vertical corner edges with a %s mm radius." % fmt(r)
    else:
        s = "Fillet the top and bottom outer rim edges with a %s mm radius." % fmt(r)
    if i == 2:
        s += " Then fillet the remaining outer edges with %s mm." % fmt(max(0.5, r / 2))
    return s


def a_chamfer(c):
    f, h, kind, i = c["f"], c["h"], c["kind"], c["idx"]
    if kind == "plate":
        cc = round(min(0.3 * h, 1.0), 1)
        cc = max(cc, 0.2)
        s = "Chamfer the top perimeter edge by %s × 45°." % fmt(cc)
    else:
        cc = max(0.5, round(min(f, h) * 0.04 * 2) / 2)
        s = "Chamfer the top outer edge loop by %s mm × 45°." % fmt(cc)
    if i == 2:
        s += " Add an equal chamfer to the bottom outer edge loop."
    return s


def a_pocket(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    dep = round(h * (0.5 if kind == "plate" else 0.4), 1)
    if kind == "round":
        s = "Cut a centred round pocket of Ø%s mm and %s mm deep into the top face." % (fmt(0.4 * a), fmt(dep))
        if i == 2:
            s += " Leave a Ø%s mm round island standing in the middle of the pocket, flush with the top face." % fmt(0.12 * a)
        return s
    s = "Cut a centred %s × %s mm rectangular pocket, %s mm deep, into the top face." % (
        fmt(0.4 * a), fmt(0.4 * b), fmt(dep))
    if i == 1:
        s = s[:-1] + ", with %s mm corner radii." % fmt(max(1, 0.05 * f))
    if i == 2:
        s = s[:-1] + ", with %s mm corner radii, and leave a Ø%s mm round island standing in the middle, flush with the top face." % (
            fmt(max(1, 0.05 * f)), fmt(0.1 * f))
    return s


def a_slot(c):
    a, b, f, i, kind = c["a"], c["b"], c["f"], c["idx"], c["kind"]
    w = std_le(0.12 * f, [3, 4, 5, 6, 8, 10])
    ln = nice(0.5 * a)
    if i == 0:
        return "Cut a %s mm wide, %s mm long slot with fully rounded ends through the part along the X axis, centred." % (fmt(w), fmt(ln))
    if i == 1:
        return "Cut two parallel %s mm wide, %s mm long slots with fully rounded ends through the part along the X axis, at Y = +%s mm and Y = -%s mm." % (
            fmt(w), fmt(ln), fmt(0.25 * b), fmt(0.25 * b))
    return "Cut three parallel %s mm wide, %s mm long slots with fully rounded ends through the part along the X axis, at Y = 0, +%s mm and -%s mm." % (
        fmt(w), fmt(ln), fmt(0.3 * b), fmt(0.3 * b))


def a_boss(c):
    f, h, i = c["f"], c["h"], c["idx"]
    d = nice(0.3 * f)
    bh = max(2, nice(0.2 * f))
    s = "Add a Ø%s mm boss, %s mm tall, centred on the top face." % (fmt(d), fmt(bh))
    if i >= 1:
        s += " Put a %s mm fillet around its base." % fmt(max(0.5, round(bh * 0.15 * 2) / 2))
    if i == 2:
        hd = std_le(0.4 * d, [2, 2.5, 3, 4, 5, 6])
        s += " Drill a Ø%s mm hole down the middle of the boss, %s mm deep." % (fmt(hd), fmt(bh))
    return s


def a_shell(c):
    f, h, kind, i = c["f"], c["h"], c["kind"], c["idx"]
    if kind == "plate" or h < 12:
        raise Skip
    t = max(1.5, round(min(f, h) * 0.06 * 2) / 2)
    if 3 * t > h or 3 * t > f:
        raise Skip
    c["shelled"] = t
    s = "Hollow it from the top face, leaving %s mm walls and a %s mm floor." % (fmt(t), fmt(t))
    if i == 2:
        s += " Then cut a %s mm wide, %s mm deep rebate around the inside of the opening for a lid." % (fmt(t / 2), fmt(t / 2))
    return s


def a_rib(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    n = [2, 3, 4][i]
    t = max(1.5, round(f * 0.03 * 2) / 2)
    if c.get("shelled"):
        rh = round(0.4 * h)
        sp = round(0.6 * b / (n - 1), 1)
        if t * 2 > sp or rh < 3:
            raise Skip
        return "Inside the cavity add %d straight ribs %s mm thick and %s mm tall, running along X, standing on the floor and joined to both end walls, %s mm apart in Y and centred." % (
            n, fmt(t), fmt(rh), fmt(sp))
    rh = max(3, round(0.25 * h)) if kind != "plate" else max(3, round(f * 0.08))
    sp = round(0.6 * b / (n - 1), 1)
    if t * 2 > sp:
        raise Skip
    return "Add %d straight ribs %s mm thick and %s mm tall on the top face, running the full length along X, %s mm apart in Y and centred." % (
        n, fmt(t), fmt(rh), fmt(sp))


def a_draft(c):
    kind = c["kind"]
    if kind == "plate":
        raise Skip
    deg = [1, 2, 3][c["idx"]]
    if c.get("shelled"):
        return "Apply %d° of draft to the inner and outer wall faces, pulling away from the top opening." % deg
    return "Apply %d° of draft to all vertical side faces, with the part narrowing toward the top and the bottom face as the neutral plane." % deg


def a_thread(c):
    f, h, i = c["f"], c["h"], c["idx"]
    if c.get("upper"):
        n = c["upper"]
        p = PITCH[n]
        s = "Model an M%d × %s external thread over the full height of the upper Ø%d mm section, with a %s mm chamfer at the tip." % (
            n, fmt(p), n, fmt(max(0.5, p)))
        if i == 2:
            s += " Cut a %s mm wide thread run-out groove at its base." % fmt(p * 2)
        return s
    n = std_le(0.4 * f, MSIZES)
    if n < 4:
        raise Skip
    p = PITCH[n]
    ln = max(8, n)
    s = "Add a Ø%d mm boss, %d mm tall, centred on the top face and model an M%d × %s external thread over its full length, with a %s mm chamfer at the tip." % (
        n, ln, n, fmt(p), fmt(max(0.5, p)))
    if i == 2:
        s += " Cut a %s mm wide thread run-out groove at the base of the boss." % fmt(p * 2)
    return s


def a_revolve(c):
    a, h, f, i = c["a"], c["h"], c["f"], c["idx"]
    if c["kind"] != "round":
        raise Skip
    n = std_le(0.6 * a, MSIZES)
    if n < 4:
        raise Skip
    sh = max(4, round(0.35 * h))
    if sh > h - 4:
        raise Skip
    c["upper"] = n
    s = "Make the body from a single revolved profile: a Ø%s mm lower section %s mm tall, stepping up through a 1 mm fillet into a Ø%d mm upper section %s mm tall." % (
        fmt(a), fmt(h - sh), n, fmt(sh))
    if i == 2:
        s += " Add a 2 mm wide, 1 mm deep ring groove on the lower section, 3 mm below the shoulder."
    return s


def a_sweep(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    if kind == "plate":
        w = max(1.5, h)
        R = nice(0.3 * f)
        s = "Add a raised bead: sweep a Ø%s mm circle along a 180° arc of %s mm radius lying flat on the top face, centred on the part, so the bead sits half proud of the face." % (
            fmt(w), fmt(R))
        if i == 2:
            s += " Make the bead path a second concentric arc of %s mm radius mirrored on the other side of the centre." % fmt(R * 0.6)
        return s
    sp = max(8, round(0.5 * h))
    if sp > 0.8 * f:
        sp = round(0.5 * f)
    w = max(2, round(sp * 0.25))
    ln = max(6, nice(0.25 * a))
    s = "Add a loop handle on the +X side face: sweep a Ø%s mm circle along a U-shaped path that leaves the face at mid-height, runs %s mm straight out, turns through a %s mm radius half-circle and returns %s mm to the face." % (
        fmt(w), fmt(ln), fmt(sp / 2.0), fmt(ln))
    if i == 2:
        s += " Fillet the joins between the handle and the side face with 1 mm."
    return s


def a_loft(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    nh = max(4, nice(0.25 * f))
    if kind == "round":
        s = "Loft a %s mm tall neck from a Ø%s mm circle sketched on the top face to a %s × %s mm square on a plane %s mm higher, centred." % (
            fmt(nh), fmt(0.4 * a), fmt(0.2 * a), fmt(0.2 * a), fmt(nh))
    else:
        s = "Loft a %s mm tall neck from a %s × %s mm rectangle sketched on the top face to a Ø%s mm circle on a plane %s mm higher, centred." % (
            fmt(nh), fmt(0.4 * a), fmt(0.4 * b), fmt(0.25 * f), fmt(nh))
    if i == 2:
        s += " Rotate the end sketch 45° about the vertical axis so the loft twists."
    return s


def a_mirror(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    w = nice(0.2 * f)
    dep = round(h * (0.5 if kind == "plate" else 0.4), 1)
    s = "Cut a %s × %s mm square pocket %s mm deep into the top face, centred %s mm from the centre line toward +X, then mirror it across the YZ symmetry plane." % (
        fmt(w), fmt(w), fmt(dep), fmt(0.25 * a))
    if i == 2:
        d = std_le(0.1 * f, [3, 4, 5, 6])
        s += " Also drill a Ø%s mm through hole at Y = +%s mm on the centre line and mirror it across the XZ plane." % (fmt(d), fmt(0.3 * b))
    return s


def a_flange(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    if kind != "plate":
        raise Skip
    fh = max(10, nice(0.3 * b))
    s = "Treat it as sheet metal and bend a %s mm tall flange up 90° along one long edge, with an inside bend radius of %s mm (the sheet thickness) and a K-factor of 0.44." % (
        fmt(fh), fmt(h))
    if i >= 1:
        s = s.replace("along one long edge", "along both long edges")
    if i == 2:
        s += " Add %s mm wide rectangular bend reliefs at the ends of each bend." % fmt(max(2, h))
    return s


def a_union(c):
    a, b, h, f, i = c["a"], c["b"], c["h"], c["f"], c["idx"]
    d = nice(0.25 * f)
    ln = max(4, nice(0.3 * f))
    s = "Build a second body, a Ø%s mm cylinder %s mm tall standing on the top face with its centre %s mm from the middle toward +X, and union it with the main body." % (
        fmt(d), fmt(ln), fmt(0.25 * a))
    if i >= 1:
        s += " Add a third body, the same cylinder mirrored to -X, and union that too."
    if i == 2:
        s += " Fillet the joins between the cylinders and the top face with 1 mm."
    return s


def a_cut(c):
    a, h, f, kind, i = c["a"], c["h"], c["f"], c["kind"], c["idx"]
    dep = round(h * (0.5 if kind == "plate" else 0.4), 1)
    R = nice(0.3 * f)
    z = R - dep
    s = "Subtract a sphere of Ø%s mm whose centre is %s mm above the top face on the vertical centre line, leaving a spherical dish %s mm deep." % (
        fmt(2 * R), fmt(z), fmt(dep))
    if i >= 1:
        s += " Then subtract a Ø%s mm through-cylinder along the vertical centre line, centred in the dish." % fmt(std_le(0.1 * f, [3, 4, 5, 6, 8]))
    if i == 2:
        s += " Subtract the same sphere again, scaled to half size, from the bottom face centre."
    return s


def a_asm_rev(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    d = std_le(0.1 * f, [3, 4, 5, 6, 8])
    arm_l = nice(0.5 * a)
    arm_w = max(2 * d, nice(0.15 * f))
    t = max(2, round(0.1 * h)) if kind != "plate" else max(1.5, h)
    pin_depth = max(2, round(min(h * 0.6, 20)))
    s = "Make it an assembly of three parts. Part 1 is the main body, fixed. Part 2 is a flat arm %s × %s × %s mm with a Ø%s mm hole %s mm in from one end. Part 3 is a Ø%s mm pin that passes through the arm's hole into a blind hole %s mm deep in the top face of the main body at X = +%s mm. Add a revolute joint about the pin's vertical axis, limited to 0° to 90°." % (
        fmt(arm_l), fmt(arm_w), fmt(t), fmt(d), fmt(1.5 * d), fmt(d), fmt(pin_depth), fmt(0.25 * a))
    if i >= 1:
        s += " Rest the arm on the top face and show its swing sweeps clear of the main body."
    if i == 2:
        s += " Add a second identical arm stacked on the first on the same pin, with its own revolute joint limited to 0° to 180°, and check the two arms do not collide through their travel."
    return s


def a_asm_slide(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    gw = nice(0.25 * f)
    dep = round(h * (0.5 if kind == "plate" else 0.4), 1)
    sl = nice(0.2 * a)
    travel = nice(0.5 * a)
    s = "Make it an assembly of two parts. Part 1 is the main body, fixed, with a %s mm wide, %s mm deep straight groove cut along the top face in the X direction from end to end, centred. Part 2 is a slider block %s mm long, %s mm wide (0.2 mm narrower than the groove) and %s mm tall that sits in the groove. Add a prismatic joint along X with %s mm of travel." % (
        fmt(gw), fmt(dep), fmt(sl), fmt(gw - 0.2), fmt(dep), fmt(travel))
    if i >= 1:
        s += " Show the slider fully at both ends of its travel without touching anything."
    if i == 2:
        s += " Add a %s mm wide end stop block at each end of the groove, as separate bodies fixed to the main body." % fmt(max(2, 0.04 * a))
    return s


def a_linpat(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    n = [3, 5, 7][i]
    pitch = round(0.6 * a / (n - 1), 1)
    w = max(1, round(pitch * 0.4 * 2) / 2)
    dep = round(h * (0.4 if kind == "plate" else 0.3), 1)
    if dep < 0.5:
        raise Skip
    return "Cut a %s mm wide, %s mm deep groove across the top face along Y, the full width, starting %s mm from the centre toward -X, then repeat it %d times in total at %s mm pitch with a linear pattern along X." % (
        fmt(w), fmt(dep), fmt(0.3 * a), n, fmt(pitch))


def a_circpat(c):
    a, b, h, f, kind, i = c["a"], c["b"], c["h"], c["f"], c["kind"], c["idx"]
    n = [4, 6, 8][i]
    w = max(1.5, round(f * 0.05 * 2) / 2)
    r0 = 0.2 * f
    if 2 * math.pi * r0 / n < 1.5 * w:
        raise Skip
    # boss in the same mix is dia 0.3 f (radius 0.15 f) so r0 clears it
    dep = round(h * (0.4 if kind == "plate" else 0.3), 1)
    if dep < 0.5:
        raise Skip
    return "Cut a radial slot %s mm wide and %s mm deep in the top face, running from %s mm to %s mm from the centre along +X, then repeat it %d times in a circular pattern about the vertical centre axis." % (
        fmt(w), fmt(dep), fmt(r0), fmt(0.4 * f), n)


ATOMS = {
    "holes": ("hole pattern", a_holes),
    "csk": ("countersunk hole pattern", a_csk),
    "fillet": ("fillet", a_fillet),
    "chamfer": ("chamfer", a_chamfer),
    "pocket": ("pocket", a_pocket),
    "slot": ("slot", a_slot),
    "boss": ("boss", a_boss),
    "shell": ("shell", a_shell),
    "rib": ("ribs", a_rib),
    "draft": ("draft", a_draft),
    "thread": ("thread", a_thread),
    "revolve": ("revolve", a_revolve),
    "sweep": ("sweep", a_sweep),
    "loft": ("loft", a_loft),
    "mirror": ("mirror", a_mirror),
    "flange": ("sheet-metal flange", a_flange),
    "union": ("body union", a_union),
    "cut": ("body subtract", a_cut),
    "asm_rev": ("assembly with revolute joint", a_asm_rev),
    "asm_slide": ("assembly with slider joint", a_asm_slide),
    "linpat": ("linear pattern", a_linpat),
    "circpat": ("circular pattern", a_circpat),
}

MIXES = [
    ["holes"], ["holes", "fillet"], ["csk", "fillet"], ["pocket", "fillet"],
    ["pocket", "holes"], ["slot", "chamfer"], ["boss", "holes"],
    ["shell", "fillet"], ["shell", "rib"], ["rib", "fillet"],
    ["draft", "fillet"], ["draft", "shell"], ["thread", "chamfer"],
    ["thread", "holes"], ["revolve", "fillet"], ["revolve", "thread"],
    ["sweep", "fillet"], ["loft", "shell"], ["loft", "fillet"],
    ["mirror", "pocket"], ["mirror", "holes"], ["flange", "holes"],
    ["flange", "slot"], ["union", "fillet"], ["cut", "chamfer"],
    ["union", "cut", "holes"], ["linpat", "fillet"], ["circpat", "boss"],
    ["asm_rev"], ["asm_slide", "chamfer"],
]


def mix_label(mix):
    return " + ".join(ATOMS[k][0] for k in mix)


def dims_for(cat, size):
    name, kind, a, b, h, mats = cat
    s = SCALE[size]
    if kind == "plate":
        A, B = nice(a * s), nice(b * s)
        H = max(0.5, round(h * PLATE_T[size] * 2) / 2)
    elif kind == "round":
        A = B = nice(a * s)
        H = nice(h * s)
    else:
        A, B, H = nice(a * s), nice(b * s), nice(h * s)
    return A, B, H


MEDIUM_EXTRA = ("Cut a groove %s mm wide and %s mm deep across the bottom face along the "
                "long direction, centred.")
HARD_EXTRA = (" Cut a second groove %s mm wide across the first at right angles, "
              "to the same depth, so the underside has four separate feet.")


def article(text):
    word = text.split(" ", 2)[1]
    if word[0] in "AEIOUaeiou" or word.startswith("8") or word.startswith("18"):
        return "An " + text[2:]
    return text


def build(cat, mix, size, diff):
    name, kind, _, _, _, mats = cat
    key = "%d:%s:%s:%s:%s" % (SEED, name, "+".join(mix), size, diff)
    rng = random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))
    a, b, h = dims_for(cat, size)
    f = min(a, b)
    if f < 12:
        raise Skip
    mat = rng.choice(mats)
    i = DIFFS.index(diff)
    c = {"a": a, "b": b, "h": h, "f": f, "kind": kind, "idx": i, "rng": rng, "size": size}
    if kind == "plate":
        base = "A %s mm %s %s, modelled from a %s × %s mm flat sheet." % (
            fmt(h), mat, name, fmt(a), fmt(b))
    elif kind == "round":
        base = "A %s %s, modelled from a Ø%s × %s mm cylinder." % (
            mat, name, fmt(a), fmt(h))
    else:
        base = "A %s %s, modelled from a %s × %s × %s mm block." % (
            mat, name, fmt(a), fmt(b), fmt(h))
    parts = [base]
    # thread after revolve needs the revolve context; atoms run in listed order
    for k in mix:
        parts.append(ATOMS[k][1](c))
    if i >= 1:
        gw = max(1.5, round(f * 0.05 * 2) / 2)
        gd = round(h * (0.4 if kind == "plate" else 0.2), 1)
        if c.get("shelled"):
            gd = round(min(gd, c["shelled"] * 0.5), 1)
        if gd < 0.5:
            raise Skip
        e = MEDIUM_EXTRA % (fmt(gw), fmt(gd))
        if i == 2:
            e += HARD_EXTRA % fmt(gw)
        parts.append(e)
    if i == 2:
        parts.append("Fully constrain every sketch and name each feature.")
    parts[0] = article(parts[0])
    return mat, " ".join(parts)


def main(out="items.jsonl"):
    cats = CATEGORIES
    combos = []
    for ci, cat in enumerate(cats):
        for mi, mix in enumerate(MIXES):
            for size in SIZES:
                for diff in DIFFS:
                    try:
                        mat, brief = build(cat, mix, size, diff)
                    except Skip:
                        continue
                    combos.append((ci, mi, SIZES.index(size), DIFFS.index(diff), brief))
    print("grid cells valid:", len(combos), file=sys.stderr)
    if len(combos) < COUNT:
        sys.exit("grid too small: %d" % len(combos))
    rng = random.Random(SEED)
    rng.shuffle(combos)
    chosen = sorted(combos[:COUNT], key=lambda x: x[:4])
    seen = set()
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for n, (ci, mi, si, di, brief) in enumerate(chosen, 1):
            assert brief not in seen, brief
            seen.add(brief)
            item = {
                "id": "S%04d" % n,
                "category": cats[ci][0],
                "features": mix_label(MIXES[mi]),
                "size": SIZES[si],
                "difficulty": DIFFS[di],
                "brief": brief,
            }
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print("wrote", len(chosen), "items to", out, file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:2])
