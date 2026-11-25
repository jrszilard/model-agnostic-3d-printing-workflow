"""One line of arithmetic before a mechanism is drawn. Units: mm, N, MPa (N/mm2), degrees.

About nine of the twenty-six print round trips between 2026-10-09 and 2026-11-11 came from physics nobody computed
first. Each function here is one of those, with the print that proved the need:

    beam_sag            a 200 x 17 x 1.6 PETG cover under 39 g of magnets sagged about 4 mm (touge road, 2026-10-10)
    cantilever_strain   a snap tab took a set at 1.70 % at its root and held at 0.6 % (TR8, 2026-10-29 to 11-02)
    euler_load          a 240 mm strip pushed into its slot bowed at about 2 N: "like pushing rope" (2026-10-12)
    friction_holds      crush ribs gripped a battery box less than its own 0.6 N: "none will hold upside down" (TR8 i1)
    rock_drop           0.35 of room on a 5.7 shoe dropped an arm's pad 5.0 at 80.6 reach (TR11 i2, 2026-11-10)
    hook_tip            play at a hook tips a 146-deep shelf 9x at its front edge (touge road v4, 2026-10-09)
    jam_ratio           a slider pushed 61 off a 35-long guide jams (2 mu d / L = 1.05) (TR11, 2026-11-11)
    mating_force        what a catch's angle and friction do to the push and to the pull-out

These size a coupon; they never replace one. Closed forms assume small deflection, one isotropic modulus and no creep,
and a root's stress concentration is not in them (TR8's square root strained 1.9x its beam value: use the 2D model in
parts/decor/touge-road-pack-coupon/docs/tab_strain.py when the root decides). Pure Python: no CAD kernel needed.
"""
from __future__ import annotations

import itertools
import math

G = 9.80665e-3                       # N per gram

# Printed values in use here, MPa. PETG is the touge road's (its "low printed modulus"); PLA and ASA are the
# Prusament datasheets' in-plane tensile moduli (0.20 layers). Pass your own E when you have a better one.
E_MPA = {"PLA": 2300.0, "PETG": 1800.0, "ASA": 1600.0}

# Strain a part may see repeatedly, as a fraction. DERIVED 2026-11-11 from the Prusament datasheets and Bayer's
# snap-fit manual (60 % of 70 % of yield strain in-plane; layer-bond strength over modulus across the layers), not
# measured here, except that PETG across the layers agrees with TR8 (0.6 % held; 1.1 and 1.7 % took a set).
STRAIN_LIMIT = {
    "PLA": {"in_plane": 0.012, "across_layers": 0.0045},
    "PETG": {"in_plane": 0.021, "across_layers": 0.007},
    "ASA": {"in_plane": 0.014, "across_layers": 0.004},
}

_SAG_SPREAD = {"pinned": 5.0 / 384.0, "fixed": 1.0 / 384.0, "propped": 1.0 / 184.6, "cantilever": 1.0 / 8.0}
_SAG_POINT = {"pinned": 1.0 / 48.0, "fixed": 1.0 / 192.0, "cantilever": 1.0 / 3.0}
_EULER_K = {"pinned": 1.0, "fixed": 0.5, "propped": 0.699, "cantilever": 2.0}


class Refused(RuntimeError):
    """A requirement that does not hold."""


def weight(grams):
    return grams * G


def rect_i(width, thickness):
    """Second moment of a rectangle bending across its thickness, mm4."""
    return width * thickness ** 3 / 12.0


def beam_sag(load_per_mm, span, e, i, ends="pinned"):
    """Largest deflection of a beam under an even load (N/mm) over `span`.

    ends: "pinned" (resting or clipped at both ends), "fixed" (screwed down at both), "propped" (one screwed, one
    resting), "cantilever" (one end held). The road's cover: 4.5 pinned as a flat plate; with edge ribs 0.19 propped
    and 0.09 fixed. Say which with every number."""
    return _SAG_SPREAD[ends] * load_per_mm * span ** 4 / (e * i)


def beam_sag_point(force, span, e, i, ends="pinned"):
    """Deflection under one force: mid-span for "pinned" and "fixed", at the tip for "cantilever"."""
    return _SAG_POINT[ends] * force * span ** 3 / (e * i)


def cantilever_strain(deflection, length, thickness, tapered=False):
    """Nominal strain at the root of a snap arm whose tip is pushed `deflection`.

    Constant section: 1.5 t y / L^2. `tapered`: thickness falling evenly to half at the tip, y = 1.09 strain L^2 / t
    (Bayer), which takes over 60 % more travel at the same strain. The root's rounds are NOT in this number."""
    factor = 1.0 / 1.09 if tapered else 1.5
    return factor * thickness * deflection / length ** 2


def cantilever_travel(strain, length, thickness, tapered=False):
    """The tip travel that puts `strain` at the root: the inverse of cantilever_strain."""
    factor = 1.0 / 1.09 if tapered else 1.5
    return strain * length ** 2 / (factor * thickness)


def cantilever_force(deflection, length, width, thickness, e):
    """Force at the tip of a constant-section arm pushed `deflection`: E b t^3 y / (4 L^3)."""
    return e * width * thickness ** 3 * deflection / (4.0 * length ** 3)


def mating_force(push, mu, angle_deg):
    """Force along the travel to drive a catch face at `angle_deg` (from the travel) past a spring pushing `push`
    across it: P (mu + tan a) / (1 - mu tan a). Infinite when the face is steep enough to lock (tan a >= 1 / mu):
    a 45-degree return face at mu 0.5 lets go at 3 P; nothing pulls out at 63 degrees or more."""
    t = math.tan(math.radians(angle_deg))
    return math.inf if mu * t >= 1.0 else push * (mu + t) / (1.0 - mu * t)


def euler_load(e, i, length, ends="pinned"):
    """The push at which a slender strip bows instead of sliding: pi^2 E I / (K L)^2."""
    return math.pi ** 2 * e * i / (_EULER_K[ends] * length) ** 2


def friction_holds(load, normal, mu, factor=2.0):
    """Whether friction alone carries `load`: mu x normal against factor x load. A part that hangs or sits upside
    down should be held by a catch whatever this says; friction is for rattle."""
    return mu * normal >= factor * load


def rock_angle(room, width):
    """Degrees a sliding fit can roll: its room across over the width it bears on."""
    return math.degrees(math.atan2(room, width))


def rock_drop(room, width, reach):
    """How far something `reach` out from a sliding fit moves when the fit rolls through its room."""
    return reach * room / width


def hook_tip(play, depth, couple):
    """Drop at the front edge of something `depth` deep hung on a hook with `play`, its bearing points `couple` apart."""
    return play * depth / couple


def jam_ratio(mu, offset, guide_length):
    """2 mu d / L for a slider pushed `offset` off its guide's line: under 1 it slides, at 1 or over it jams."""
    return 2.0 * mu * offset / guide_length


def corners(fn, **ranges):
    """`fn` at its nominal values and at every corner of their ranges: {"nominal", "low", "high"}.

    Each range is (low, nominal, high) or (low, high) (nominal = the middle). Corners only: an extreme inside a range
    (a resonance, a sign change) is not found, so use it on monotonic requirements.

        corners(rock_drop, room=(0.25, 0.35, 0.50), width=(5.6, 5.7, 5.8), reach=(80.6, 80.6, 80.6))
    """
    names = list(ranges)
    spans = []
    for name in names:
        r = ranges[name]
        spans.append((r[0], (r[0] + r[1]) / 2.0, r[1]) if len(r) == 2 else tuple(r))
    values = [fn(**dict(zip(names, combo))) for combo in itertools.product(*[(s[0], s[2]) for s in spans])]
    return {"nominal": fn(**{name: s[1] for name, s in zip(names, spans)}), "low": min(values), "high": max(values)}


def require(label, value, at_most=None, at_least=None, unit="mm"):
    """One line of a mechanism sheet: returns "label: value unit (limit)" or raises Refused.

    The limit is the REQUIREMENT's number, never the constant under test: a check that reads the constant it guards
    passes every broken value."""
    if at_most is None and at_least is None:
        raise ValueError("%s: give the requirement's limit (at_most= or at_least=)" % label)
    text = "%s: %.3g %s" % (label, value, unit)
    if at_most is not None and value > at_most:
        raise Refused("%s, over the %.3g allowed" % (text, at_most))
    if at_least is not None and value < at_least:
        raise Refused("%s, under the %.3g needed" % (text, at_least))
    limit = " and ".join(part for part in ("at most %.3g" % at_most if at_most is not None else "",
                                           "at least %.3g" % at_least if at_least is not None else "") if part)
    return "%s (%s)" % (text, limit)
