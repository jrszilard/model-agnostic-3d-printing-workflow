#!/usr/bin/env python3
"""A working model of a build: every piece where it sits, moved the way it moves, in one page you can turn over.

Justin, 2026-11-11: "a working dynamic ... model for complex builds to illustrate how all the pieces work together and
that will hopefully make testing and refining the parts improved ... an interactive tool that can be utilized for
future builds and parts". The first was the touge road's slider coupon (TR11 i5); this is that page as a tool.

A part that has pieces moving against each other keeps a description beside its drawings:

    parts/<category>/<part>/docs/working_model.py

        from working_model import Scene, Piece, Mover, Gap, poses, poses_of, bullets   # this folder is on sys.path

        def model():
            ...import the generator; build its solids; place each with ITS OWN placement function...
            return Scene(
                title="TR11 i5, as it works", name="TR11 Working Model", front="+y",
                pieces=[Piece("base", road, "The road", code="B", colour="body", see_through=True), ...],
                movers=[Mover("A", "Car A, back lane", ["carriage-a"],
                              poses(lambda i: lambda s: gen.car_in_place(g, "A", s, click[i].u, click[i].hang), 21),
                              also=[(["sled-a", "magnet-a"], poses(lambda i: lambda s: gen.sled_in_place(...), 21))],
                              colour="a", unit="click")],
                gaps=[Gap("A", "B", "Nearest the two carriages come, here", limit=1.0)],
                checks=[("Passing", "the line the build printed")])

    ~/cadquery-env/bin/python platform/pipeline/working-model/working_model.py parts/<category>/<part> <out.html>

Rules that keep the model honest:

- EVERY SOLID COMES FROM THE GENERATOR, placed by the generator's own placement functions. Nothing is modelled again
  for the page, so the model cannot drift from the part. A bought or real object the CAD does not hold (a toy car, a
  battery) may be a plain stand-in, flagged `stand_in=True`: the page labels it and no gap is measured to it.
- THE MOTION COMES FROM THE GENERATOR TOO. `poses(place_at, count)` reads each step's rigid motion off where the
  generator's placement function puts four small markers, so a slide, a turn or both come out as the part defines
  them. One control can move several pieces along different paths (`also=`): a carriage and the sled it drags.
- Where the generator BUILDS a piece at each step instead of placing one (a bolt drawn pulled out so far),
  `poses_of(build_at, count)` reads the motion off the two solids' corners and refuses unless every corner lands.
- A CONTROL CAN RIDE ON ANOTHER (`on=`): a latch bolt on a road that lifts off its wall plate, a lens in a lamp in
  that road. Its pieces go where the carrier goes and move on it.
- A Gap is the kernel's own distance between two sets of pieces for every arrangement of the controls that move
  either, with the two nearest points, so the number shown is exact at each step, not read off the mesh.
- A Gap with `stops=True` is two things that cannot pass through each other: on the page a control stops at the last
  step before they meet (a locked bolt under its plate stops the road lifting). `play=[...]` is the order Play works
  the controls in; the export refuses a Play that a stop would block.
- Between two given steps the page turns and slides the piece along the one screw motion that joins them. Give the
  steps the part really has (its clicks, its stops, several along a free travel); it knows no other path.
- The page is a picture and a ruler. It attests nothing: the build's checks are quoted on it, not replaced by it.

The page is one HTML file (three.js from cdnjs, the meshes embedded), written for the Artifact tool to publish.
"""
from __future__ import annotations

import base64
import html
import importlib.util
import itertools
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLOURS = ("body", "dark", "light", "pale", "steel", "a", "b", "c", "d", "e")
FRONTS = ("+y", "-y", "+x", "-x")          # where the person stands, looking at the build
VIEWS = ("above", "front", "under", "end")
STOP_AT = 0.001                           # a gap under this is two things touching
CELLS_MAX = 60000                         # the most arrangements one gap, or one piece, may answer to


class ModelError(ValueError):
    pass


class Piece:
    """`layer`: how far it goes when the build is pulled apart, in lifts: a number along the scene's `explode` axis, or
    (x, y, z). `stand_in`: not the CAD's own shape, so nothing is measured to it. `bought`: a bought part (drawn from
    the sizes the generator holds for it), labelled so on the page."""

    def __init__(self, key, solid, name, code="", colour="body", note="", layer=0.0, see_through=False,
                 stand_in=False, tint=0.0, bought=False):
        if colour not in COLOURS:
            raise ModelError("%s: colour must be one of %s" % (key, ", ".join(COLOURS)))
        self.key, self.solid, self.name, self.code, self.colour = key, solid, name, code, colour
        self.note, self.layer, self.see_through, self.stand_in, self.tint = note, layer, see_through, stand_in, tint
        self.bought = bought


class Mover:
    """One control. `pieces` move through `poses`; each `(pieces, poses)` in `also` moves with the same control along
    its own path. Every pose list has one entry per step, the first being where the pieces are given.

    `on`: the control (or (control, group number)) that carries this one. Its pieces go where the carrier goes and
    move on it; their poses are given as they are with the carrier at its first step.
    `marks`: what the readout says at each step ("locked", "2 mm out"), in place of the unit and the step's number."""

    def __init__(self, key, label, pieces, poses, colour="a", unit="step", start=0, also=(), on=None, marks=None):
        if colour not in COLOURS:
            raise ModelError("%s: colour must be one of %s" % (key, ", ".join(COLOURS)))
        self.key, self.label, self.colour, self.unit, self.start = key, label, colour, unit, start
        self.groups = [(list(pieces), list(poses))] + [(list(p), list(q)) for p, q in also]
        self.on = None if on is None else ((on, 0) if isinstance(on, str) else (on[0], int(on[1])))
        self.marks = None if marks is None else [str(mark) for mark in marks]

    @property
    def steps(self):
        return len(self.groups[0][1])


class Gap:
    """The least distance between two ends, for every arrangement of the controls that move either end or carry it.
    An end is a mover's key (the real pieces it moves itself), "fixed" (every real piece no mover moves), or a list of
    piece keys. A mover that rests on something fixed is 0 from "fixed": name the pieces that must stay apart.

    `stops`: the two cannot pass through each other, so on the page a control stops at the last step before they meet.
    They must be apart where the build starts, and the scene needs `play`."""

    def __init__(self, a, b, label, limit=None, note="", stops=False):
        self.a, self.b, self.label, self.limit, self.note, self.stops = a, b, label, limit, note, stops


class Scene:
    """`play`: the order Play works the controls in, as (mover key, the step it goes to; -1 is its last). Pressed
    again, Play takes each back the way it came, last first. Without it every control runs its whole travel at once."""

    def __init__(self, title, pieces, movers, gaps=(), checks=(), facts=(), name="", tag="", intro="", note="",
                 front="-y", start_view="above", see_through_open=False, explode="z", lift=16.0, play=None,
                 play_label="Play", back_label="Play back"):
        self.title, self.name, self.tag, self.intro, self.note = title, name or title, tag, intro, note
        self.pieces, self.movers, self.gaps = list(pieces), list(movers), list(gaps)
        self.checks, self.facts = [list(c) for c in checks], [list(f) for f in facts]
        self.front, self.start_view, self.see_through_open = front, start_view, see_through_open
        self.explode, self.lift = explode, lift
        self.play = None if play is None else [tuple(move) for move in play]
        self.play_label, self.back_label = play_label, back_label

    def validate(self):
        """Piece key -> (mover key, group number) for every piece that moves; raises on a scene that cannot be drawn."""
        keys = [p.key for p in self.pieces]
        if not self.pieces:
            raise ModelError("a working model needs at least one piece")
        if len(set(keys)) != len(keys):
            raise ModelError("pieces need distinct keys: %r" % keys)
        if self.front not in FRONTS:
            raise ModelError("front must be one of %s" % ", ".join(FRONTS))
        if self.start_view not in VIEWS:
            raise ModelError("start_view must be one of %s" % ", ".join(VIEWS))
        if self.explode not in ("x", "y", "z"):
            raise ModelError("explode must be x, y or z")
        for p in self.pieces:
            spread(p.layer, self.explode, p.key)
        names = [m.key for m in self.movers]
        if len(set(names)) != len(names) or "fixed" in names:
            raise ModelError("movers need distinct keys, and none may be called 'fixed'")
        by = {m.key: m for m in self.movers}
        for m in self.movers:
            if m.on is not None and m.on[0] not in by:
                raise ModelError("mover %s rides on %r, which is not a mover" % (m.key, m.on[0]))
            if m.on is not None and not 0 <= m.on[1] < len(by[m.on[0]].groups):
                raise ModelError("mover %s rides on group %d of %s, which it does not have" % (m.key, m.on[1], m.on[0]))
        owner = {}
        for m in self.movers:
            seen, up = {m.key}, m.on
            while up is not None:
                if up[0] in seen:
                    raise ModelError("mover %s rides on itself, by way of %s" % (m.key, up[0]))
                seen.add(up[0])
                up = by[up[0]].on
            if m.steps < 2:
                raise ModelError("mover %s needs at least two poses: where it starts and where it goes" % m.key)
            if not 0 <= m.start < m.steps:
                raise ModelError("mover %s starts at a step it does not have" % m.key)
            if m.marks is not None and len(m.marks) != m.steps:
                raise ModelError("mover %s: one mark per step (%d), not %d" % (m.key, m.steps, len(m.marks)))
            for number, (pieces, poses) in enumerate(m.groups):
                if len(poses) != m.steps:
                    raise ModelError("mover %s: every group needs one pose per step (%d), not %d"
                                     % (m.key, m.steps, len(poses)))
                if not pieces:
                    raise ModelError("mover %s has a group that moves nothing" % m.key)
                for key in pieces:
                    if key not in keys:
                        raise ModelError("mover %s moves a piece that is not in the scene: %s" % (m.key, key))
                    if key in owner:
                        raise ModelError("%s is moved by both %s and %s" % (key, owner[key][0], m.key))
                    owner[key] = (m.key, number)
        for g in self.gaps:
            ends = [self.end(g, end, owner) for end in (g.a, g.b)]
            if set(ends[0]) & set(ends[1]):
                raise ModelError("gap %r measures a thing to itself" % g.label)
        if self.play is not None:
            if not self.play:
                raise ModelError("play needs at least one move")
            for move in self.play:
                if len(move) != 2 or move[0] not in by:
                    raise ModelError("play works %r, which is not a mover and the step it goes to" % (move,))
                if not -1 <= move[1] < by[move[0]].steps:
                    raise ModelError("play sends %s to a step it does not have (%r)" % move)
        elif any(g.stops for g in self.gaps):
            raise ModelError("a scene with a gap that stops a control needs play=[...]: the order Play works them in")
        return owner

    def end(self, gap, end, owner):
        """The real pieces at one end of a gap."""
        by_key = {p.key: p for p in self.pieces}
        if isinstance(end, str):
            if end != "fixed" and end not in [m.key for m in self.movers]:
                raise ModelError("gap %r measures to %r, which is not a mover or 'fixed'" % (gap.label, end))
            keys = [p.key for p in self.pieces if not p.stand_in
                    and (owner[p.key][0] == end if p.key in owner else end == "fixed")]
            if not keys:
                raise ModelError("gap %r is measured to %r, which has no real piece" % (gap.label, end))
            return keys
        keys = list(end)
        if not keys:
            raise ModelError("gap %r has an end with no pieces" % gap.label)
        for key in keys:
            if key not in by_key:
                raise ModelError("gap %r names a piece that is not in the scene: %s" % (gap.label, key))
            if by_key[key].stand_in:
                raise ModelError("gap %r names %s, a stand-in: only the CAD's own pieces are measured"
                                 % (gap.label, key))
        return keys


def spread(layer, axis, key="a piece"):
    """A piece's `layer` as (x, y, z) lifts."""
    if isinstance(layer, (int, float)):
        out = [0.0, 0.0, 0.0]
        out["xyz".index(axis)] = float(layer)
        return out
    try:
        out = [float(v) for v in layer]
    except (TypeError, ValueError):
        out = []
    if len(out) != 3:
        raise ModelError("%s: layer must be a number or (x, y, z), not %r" % (key, layer))
    return out


# ── rigid motions as 3 x 4 matrices, row by row ────────────────────────────────────────────────────────────────────
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def matrix(location):
    """A cq.Location (or anything with .wrapped.Transformation()) as twelve numbers; a tuple of twelve passes through."""
    if isinstance(location, (tuple, list)) and len(location) == 12:
        return tuple(float(v) for v in location)
    trsf = location.wrapped.Transformation()
    return tuple(float(trsf.Value(r, c)) for r in (1, 2, 3) for c in (1, 2, 3, 4))


def compose(m, n):
    """m after n."""
    out = []
    for r in range(3):
        for c in range(4):
            v = sum(m[r * 4 + k] * n[k * 4 + c] for k in range(3))
            out.append(v + (m[r * 4 + 3] if c == 3 else 0.0))
    return tuple(out)


def inverse(m):
    rot = [[m[c * 4 + r] for c in range(3)] for r in range(3)]                    # the transpose
    t = [-sum(rot[r][k] * m[k * 4 + 3] for k in range(3)) for r in range(3)]
    return tuple(v for r in range(3) for v in (rot[r][0], rot[r][1], rot[r][2], t[r]))


def apply(m, p):
    return tuple(m[r * 4] * p[0] + m[r * 4 + 1] * p[1] + m[r * 4 + 2] * p[2] + m[r * 4 + 3] for r in range(3))


def is_identity(m, tol=1e-9):
    return all(abs(a - b) <= tol for a, b in zip(m, IDENTITY))


def require_rigid(m, tol=1e-6, what="a pose"):
    cols = [(m[0 + c], m[4 + c], m[8 + c]) for c in range(3)]
    for i in range(3):
        for j in range(i, 3):
            dot = sum(a * b for a, b in zip(cols[i], cols[j]))
            if abs(dot - (1.0 if i == j else 0.0)) > tol:
                raise ModelError("%s is not a rigid motion (it stretches or shears)" % what)
    (a, b, c), (d, e, f), (g, h, k) = (m[0:3], m[4:7], m[8:11])
    if a * (e * k - f * h) - b * (d * k - f * g) + c * (d * h - e * g) < 0:
        raise ModelError("%s mirrors the piece" % what)
    return m


def relative_key(ma, mb, digits=6):
    """Where A sits as B sees it."""
    return tuple(round(v, digits) + 0.0 for v in compose(inverse(mb), ma))


def chain(carrier, body):
    """The controls a body answers to: its own, then each one that carries it. A body is a (control, group number),
    or None for what nothing moves; `carrier[control]` is the body that control rides on, or None."""
    out = []
    while body is not None:
        out.append(body[0])
        body = carrier[body[0]]
    return out


def carried(frames, carrier, body, at):
    """Where a body stands with each control at the step `at` gives it: its own pose, then the pose of each control
    that carries it, outward. `frames[control][step]` is the pose of each of that control's groups."""
    pose = IDENTITY
    while body is not None:
        key, number = body
        pose = compose(frames[key][at[key]][number], pose)
        body = carrier[key]
    return pose


def gap_table(counts, frames, measure):
    """Every arrangement of the controls that matter, measured once per distinct one. `counts` is each control's number
    of steps. With the controls at the steps `at` (one number each), `frames(at)` gives the pose of each of A's bodies
    and of each of B's, and `measure(at)` returns (gap, point_a, point_b) in the scene's frame. Two arrangements where
    everything sits the same as B's first body sees it are one arrangement, so one distance serves both: two carriages
    sliding along one line need 41 measurements, not 441. The points are kept in the frame of B's first body, which
    carries them to every arrangement that is the same.

    A control whose step never changes the arrangement (one that carries both ends) is left out: `kept` lists the
    others by their place in `counts`. The table is nested lists, one level per kept control, down to the number of
    the measurement in `unique`; with no control left it is that number alone."""
    unique, index = [], {}

    def cell(at):
        groups_a, groups_b = frames(at)
        seen_from = groups_b[0]
        key = tuple(relative_key(m, seen_from) for m in groups_a) \
            + tuple(relative_key(m, seen_from) for m in groups_b[1:])
        if key not in index:
            gap, pa, pb = measure(at)
            back = inverse(seen_from)
            index[key] = len(unique)
            unique.append({"gap": round(float(gap), 3), "pa": [round(v, 3) for v in apply(back, pa)],
                           "pb": [round(v, 3) for v in apply(back, pb)]})
        return index[key]

    def fill(at):
        if len(at) == len(counts):
            return cell(tuple(at))
        return [fill(at + [i]) for i in range(counts[len(at)])]

    def same_along(table, axis):
        if axis == 0:
            return all(sub == table[0] for sub in table)
        return all(same_along(sub, axis - 1) for sub in table)

    def without(table, axis):
        return table[0] if axis == 0 else [without(sub, axis - 1) for sub in table]

    table, kept = fill([]), list(range(len(counts)))
    for axis in reversed(range(len(counts))):                        # last first: the earlier ones keep their places
        if same_along(table, axis):
            table = without(table, axis)
            kept.remove(axis)
    return {"table": table, "unique": unique, "least": min(u["gap"] for u in unique), "kept": kept}


def found(gap, at):
    """A gap's measurement with each control at the step `at` gives it."""
    cell = gap["table"]
    for key in gap["drivers"]:
        cell = cell[at[key]]
    return gap["unique"][cell]


def reach(gaps, key, start, to, at):
    """How far control `key` gets from step `start` toward step `to` while the others stand at `at`: (the step it
    reaches, the gap that stopped it or None). It stops at the last step before a gap with `stops` would be touching.
    The page's own `reach` does the same; test_working_model.py holds the two to each other."""
    step, way = start, (1 if to > start else -1)
    while step != to:
        ahead = dict(at)
        ahead[key] = step + way
        for gap in gaps:
            if gap["stops"] and key in gap["drivers"] and found(gap, ahead)["gap"] < STOP_AT:
                return step, gap
        step += way
    return to, None


def bullets(path, heading):
    """The list items under the first heading that contains `heading`, without their dashes: the way a part's README
    keeps the lines its generator printed. Raises when the heading or its list is missing, so a stale name is loud."""
    lines, found, out = Path(path).read_text().splitlines(), False, []
    for line in lines:
        if line.startswith("#"):
            if found:
                break
            found = heading in line
        elif found and line.startswith("- "):
            out.append(line[2:].strip())
        elif found and out and line.strip() and not line.startswith(" "):
            break                                                    # the paragraph after the list
    if not out:
        raise ModelError("%s: no list under a heading containing %r" % (path, heading))
    return out


def pick(lines, titles):
    """[(title, line)] for each (title, prefix): the one line that starts with the prefix. Raises when none or two do."""
    out = []
    for title, prefix in titles:
        hits = [line for line in lines if line.startswith(prefix)]
        if len(hits) != 1:
            raise ModelError("%d lines start with %r; one was expected" % (len(hits), prefix))
        out.append((title, hits[0][0].upper() + hits[0][1:]))
    return out


# ── the kernel's side: markers, meshes and exact distances ─────────────────────────────────────────────────────────
def placement(place):
    """The rigid motion a placement function applies, read off where it puts four small markers: the motion is the
    generator's own, never derived a second time here."""
    import cadquery as cq

    def centre(p):
        marker = cq.Solid.makeBox(0.2, 0.2, 0.2, cq.Vector(p[0] - 0.1, p[1] - 0.1, p[2] - 0.1))
        c = place(marker).Center()
        return (c.x, c.y, c.z)

    o = centre((0.0, 0.0, 0.0))
    cols = [[v - w for v, w in zip(centre(p), o)] for p in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))]
    return require_rigid(tuple(v for r in range(3) for v in (cols[0][r], cols[1][r], cols[2][r], o[r])),
                         what="the placement")


def poses(place_at, count):
    """One pose per step for a Mover: `place_at(i)` is the generator's placement at step i (a function from a solid
    in its own frame to that solid in place). The poses are each step's motion from the first step."""
    first = placement(place_at(0))
    back = inverse(first)
    return [IDENTITY] + [compose(placement(place_at(i)), back) for i in range(1, count)]


def motion(a, b, tol=1e-5):
    """The rigid motion that carries solid `a` onto solid `b`, for a generator that builds one piece at two steps: the
    two then list their corners in the same order, and four corners that span space give the motion. Refused unless
    every corner lands within `tol` and the two are the same size, so a piece that changed shape is not passed off as
    one that moved."""
    pa, pb = [v.toTuple() for v in a.Vertices()], [v.toTuple() for v in b.Vertices()]
    if len(pa) != len(pb) or len(pa) < 4:
        raise ModelError("the motion cannot be read off these two solids: they have %d and %d corners (it takes four "
                         "or more, and as many on each)" % (len(pa), len(pb)))
    sub = lambda p, q: (p[0] - q[0], p[1] - q[1], p[2] - q[2])
    dot = lambda u, v: u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    cross = lambda u, v: (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    every = range(len(pa))
    i1 = max(every, key=lambda i: dot(sub(pa[i], pa[0]), sub(pa[i], pa[0])))
    e1 = sub(pa[i1], pa[0])
    i2 = max(every, key=lambda i: dot(cross(e1, sub(pa[i], pa[0])), cross(e1, sub(pa[i], pa[0]))))
    normal = cross(e1, sub(pa[i2], pa[0]))
    i3 = max(every, key=lambda i: abs(dot(normal, sub(pa[i], pa[0]))))
    if abs(dot(normal, sub(pa[i3], pa[0]))) < 1e-9:
        raise ModelError("the motion cannot be read off these two solids: their corners lie in one plane")
    fa, fb = [[sub(pts[i], pts[0]) for i in (i1, i2, i3)] for pts in (pa, pb)]     # three edges from the first corner
    det = dot(fa[0], cross(fa[1], fa[2]))
    back = [[c / det for c in cross(fa[1], fa[2])], [c / det for c in cross(fa[2], fa[0])],
            [c / det for c in cross(fa[0], fa[1])]]                                 # rows: the inverse of fa's columns
    rot = [[sum(fb[k][r] * back[k][c] for k in range(3)) for c in range(3)] for r in range(3)]
    shift = [pb[0][r] - sum(rot[r][c] * pa[0][c] for c in range(3)) for r in range(3)]
    m = require_rigid(tuple(v for r in range(3) for v in (rot[r][0], rot[r][1], rot[r][2], shift[r])),
                      what="what carries the first solid onto the second")
    worst = max(max(abs(u - v) for u, v in zip(apply(m, p), q)) for p, q in zip(pa, pb))
    if worst > tol or abs(a.Volume() - b.Volume()) > 1e-6 * max(1.0, abs(a.Volume())):
        raise ModelError("the second solid is not the first one moved: a corner lands %.4f off, the volumes are %.3f "
                         "and %.3f" % (worst, a.Volume(), b.Volume()))
    return m


def poses_of(build_at, count):
    """One pose per step for a Mover whose generator BUILDS the piece at each step (`build_at(i)` is the solid at step
    i) instead of placing a given one: each step's motion from the first, read off the solids (`motion`)."""
    first = build_at(0)
    return [IDENTITY] + [motion(first, build_at(i)) for i in range(1, count)]


def location(m):
    import cadquery as cq
    from OCP.gp import gp_Trsf
    trsf = gp_Trsf()
    trsf.SetValues(*m)
    return cq.Location(trsf)


def stl_bytes(solid, tolerance, angular):
    vertices, triangles = solid.tessellate(tolerance, angular)
    out = bytearray(b"working model".ljust(80, b" ")) + struct.pack("<I", len(triangles))
    for a, b, c in triangles:
        out += struct.pack("<3f", 0.0, 0.0, 0.0)
        for v in (vertices[a], vertices[b], vertices[c]):
            out += struct.pack("<3f", v.x, v.y, v.z)
        out += struct.pack("<H", 0)
    return bytes(out)


def export(scene, tolerance=0.03, angular=0.25, say=None):
    """The scene as the page's data: meshes, motions, exact gap tables. Needs the CAD kernel."""
    import cadquery as cq
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    say = say or (lambda text: None)
    owner = scene.validate()
    movers = {m.key: m for m in scene.movers}
    frames = {}                                                      # mover -> step -> (matrix of each group)
    for m in scene.movers:
        per_group = [[require_rigid(matrix(p), what="mover %s, step %d" % (m.key, i)) for i, p in enumerate(group)]
                     for _, group in m.groups]
        for group in per_group:
            if not is_identity(group[0], 1e-7):
                raise ModelError("mover %s: each first pose must be the identity (pieces are given where they start)"
                                 % m.key)
        frames[m.key] = [tuple(group[i] for group in per_group) for i in range(m.steps)]
    carrier = {m.key: m.on for m in scene.movers}
    solids = {p.key: p.solid for p in scene.pieces}

    def bodies(keys):
        """[(body, its pieces)]: the pieces grouped by what moves them, in the order they were named."""
        out = {}
        for key in keys:
            out.setdefault(owner.get(key), []).append(key)
        return list(out.items())

    def arrangements(keys, what):
        counts = [movers[key].steps for key in keys]
        cells = 1
        for count in counts:
            cells *= count
        if cells > CELLS_MAX:
            raise ModelError("%s answers to %d controls with %d arrangements between them: name fewer pieces, or give "
                             "the controls fewer steps" % (what, len(keys), cells))
        return counts

    gaps = []
    for g in scene.gaps:
        ends = [bodies(scene.end(g, end, owner)) for end in (g.a, g.b)]
        involved = {key for end in ends for body, _ in end for key in chain(carrier, body)}
        drivers = [m.key for m in scene.movers if m.key in involved]
        counts = arrangements(drivers, "gap %r" % g.label)

        def stand(at, drivers=drivers, ends=ends):
            now = dict(zip(drivers, at))
            return tuple([carried(frames, carrier, body, now) for body, _ in end] for end in ends)

        def measure(at, g=g, ends=ends, stand=stand):
            shapes = [cq.Compound.makeCompound([solids[key].moved(location(pose))
                                                for (_, keys), pose in zip(end, poses) for key in keys])
                      for end, poses in zip(ends, stand(at))]
            extrema = BRepExtrema_DistShapeShape(shapes[0].wrapped, shapes[1].wrapped)
            if not extrema.IsDone() or extrema.NbSolution() < 1:
                raise ModelError("gap %r: the kernel found no distance with the controls at %r" % (g.label, at))
            p, q = extrema.PointOnShape1(1), extrema.PointOnShape2(1)
            return extrema.Value(), (p.X(), p.Y(), p.Z()), (q.X(), q.Y(), q.Z())

        table = gap_table(counts, stand, measure)
        kept = [drivers[i] for i in table.pop("kept")]
        gap = dict(table, drivers=kept, bBody=list(ends[1][0][0]) if ends[1][0][0] else None, label=g.label,
                   limit=g.limit, note=g.note, stops=bool(g.stops))
        if g.stops and not kept:
            raise ModelError("gap %r stops nothing: no control moves its two ends against each other" % g.label)
        if g.stops and found(gap, {m.key: m.start for m in scene.movers})["gap"] < STOP_AT:
            raise ModelError("gap %r: the two already touch where the build starts, so it can stop nothing" % g.label)
        say("gap %r: %d arrangements measured, least %.3f%s" % (
            g.label, len(table["unique"]), table["least"], "" if kept else " (nothing moves them against each other)"))
        gaps.append(gap)

    play = None
    if scene.play is not None:                                       # Play forward, then back the way each came
        play = [[key, movers[key].steps - 1 if step == -1 else step] for key, step in scene.play]
        at, trail = {m.key: m.start for m in scene.movers}, []
        for key, to in play:
            trail.append((key, at[key]))
            got, by = reach(gaps, key, at[key], to, at)
            if by is not None:
                raise ModelError("play: %s is stopped at step %d on its way to step %d, by %r"
                                 % (key, got, to, by["label"]))
            at[key] = to
        for key, to in reversed(trail):
            got, by = reach(gaps, key, at[key], to, at)
            if by is not None:
                raise ModelError("play, on the way back: %s is stopped at step %d on its way to step %d, by %r"
                                 % (key, got, to, by["label"]))
            at[key] = to

    lo, hi = [1e18] * 3, [-1e18] * 3
    everywhere = {}                                                  # body -> every pose it can take
    pieces = []
    for p in scene.pieces:
        body = owner.get(p.key)
        if body not in everywhere:
            keys = chain(carrier, body)
            counts = arrangements(keys, "piece %s" % p.key)
            everywhere[body] = [carried(frames, carrier, body, dict(zip(keys, at)))
                                for at in itertools.product(*[range(count) for count in counts])]
        bb = p.solid.BoundingBox()
        corners = [(x, y, z) for x in (bb.xmin, bb.xmax) for y in (bb.ymin, bb.ymax) for z in (bb.zmin, bb.zmax)]
        for m in everywhere[body]:
            for corner in corners:
                at = apply(m, corner)
                lo = [min(a, b) for a, b in zip(lo, at)]
                hi = [max(a, b) for a, b in zip(hi, at)]
        mesh = stl_bytes(p.solid, tolerance, angular)
        say("%-18s %7d bytes" % (p.key, len(mesh)))
        pieces.append({"key": p.key, "name": p.name, "code": p.code, "note": p.note, "colour": p.colour,
                       "tint": p.tint, "layer": spread(p.layer, scene.explode, p.key),
                       "seeThrough": bool(p.see_through), "standIn": bool(p.stand_in), "bought": bool(p.bought),
                       "stl": base64.b64encode(mesh).decode()})
    return {"title": scene.title, "name": scene.name, "tag": scene.tag, "intro": scene.intro, "note": scene.note,
            "front": scene.front, "startView": scene.start_view, "seeThroughOpen": bool(scene.see_through_open),
            "lift": scene.lift, "bbox": [round(v, 3) for v in lo + hi], "pieces": pieces,
            "movers": [{"key": m.key, "label": m.label, "colour": m.colour, "unit": m.unit, "start": m.start,
                        "steps": m.steps, "on": list(m.on) if m.on else None, "marks": m.marks,
                        "groups": [{"pieces": keys, "poses": [[round(v, 6) for v in step[number]]
                                                              for step in frames[m.key]]}
                                   for number, (keys, _) in enumerate(m.groups)]} for m in scene.movers],
            "gaps": gaps, "play": play, "playLabel": scene.play_label, "backLabel": scene.back_label,
            "checks": scene.checks, "facts": scene.facts}


def page(model):
    """The one-file page for a model (the dict `export` returns)."""
    data = json.dumps(model, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    template = (HERE / "page.template.html").read_text()
    return template.replace("__NAME__", html.escape(model.get("name") or model["title"])).replace("__MODEL_JSON__", data)


def load(part_dir):
    path = Path(part_dir).resolve() / "docs" / "working_model.py"
    if not path.is_file():
        raise ModelError("%s has no docs/working_model.py" % part_dir)
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location("part_working_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.model()


def main(argv):
    if len(argv) != 3:
        print(__doc__.split("\n\n")[0])
        print("usage: working_model.py <part_dir> <out.html>")
        return 2
    sys.modules.setdefault("working_model", sys.modules[__name__])   # the part's file imports this module by name
    model = export(load(argv[1]), say=lambda text: print("  " + text, flush=True))
    out = Path(argv[2]); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(model))
    print("%s: %d pieces, %d movers, %d gap tables (%s distinct arrangements measured), %d bytes" % (
        out, len(model["pieces"]), len(model["movers"]), len(model["gaps"]),
        " + ".join(str(len(g["unique"])) for g in model["gaps"]) or "0", out.stat().st_size))
    if out.stat().st_size > 12 * 1024 * 1024:
        print("  WARN: over 12 MB; a published page may be 16 MB at most (raise the mesh tolerance)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
