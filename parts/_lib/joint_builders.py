"""Geometry builders for the QUALIFIED JOINT REGISTRY (`joints.py`).

One implementation per qualified feature. Before this module the wave profile existed three
times — a real `wave_pts()` in the extension coupons, plus two hand-retyped 7-point literals in
`photo-calibration-corner-pcc2.py` and the VD orientation coupons, each with its own amplitude
convention. Retyping a profile is how "add the waves" produces a different shape every time.

TWO PROPERTIES THIS MODULE ENFORCES, which prose could not:

1. **Retention is a PARAMETER, not a step you remember.** `twin_dovetail()` emits the fins AND
   their wave/ratchet train AND the mating female half from one call, phase-locked by
   construction. There is no way to build the dovetail and forget the ridges.
2. **Rule R1 is checked where the geometry is made.** A captured joint whose retention amplitude
   meets or exceeds its clearance raises at build time — the VD R1 jam becomes impossible to
   author, not merely discouraged in a doc.

Separated from `joints.py` because that module must stay dependency-free: `joint_check.py`
imports the registry under `freecadcmd`, which has no cadquery.

Usage (the whole point — "double" vs "triple" is one integer):
    from joints import SAMPLES, STUDIO_PITCH
    from joint_builders import twin_dovetail
    male, female = twin_dovetail(SAMPLES["VDF30"], count=3, retention=SAMPLES["VW20"],
                                 length=40.0, engage=20.0)
"""
import math
import os
import sys

import cadquery as cq
from cadquery import Solid, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from joints import (SAMPLES, STUDIO_PITCH, check_retention, resolve, stations)  # noqa: E402

# A boolean that lands exactly on a face silently no-ops in OCC (same failure `deboss` documents).
# Every cutter/fuser below overruns its host face by this much.
OVERRUN = 0.05


# ─────────────────────────────────────────────────────────────────────────────
# PROFILES — 2-D, in (along, normal). Placement is a separate concern.
# ─────────────────────────────────────────────────────────────────────────────
def wave_profile(center, amp, width, base=0.0, invert=False, overrun=OVERRUN):
    """THE canonical rounded wave — the single source for every ridge and divot.

    Seven points: a flat foot, a 0.6*amp shoulder at width/4, the crest at `center`, mirrored.
    Rounded rather than sawtooth so it cams over under assembly force (FX round 3).

    `invert` is a DIRECTION, not an operation. The profile rises from `base` by `amp`; invert
    mirrors it to the other side. **A male ridge and the female divot that receives it use the
    SAME value** — they are the same shape in the same place, and only the boolean differs
    (fuse for the ridge, cut for the divot). Choose it from where the HOST MATERIAL lies: a face
    whose material is on the negative side needs invert=True.

    Getting this backwards yields a pocket that does not receive its ridge — silently, because
    both halves still build and both still look like waves. The seat assertion catches it as
    interference; the `wave_ridge_and_divot` helper below avoids it entirely.
    """
    if amp <= 0 or width <= 0:
        raise ValueError("wave amp and width must be positive")
    s = -1.0 if invert else 1.0
    half, q = width / 2.0, width / 4.0
    return [(center - half, base - s * overrun),
            (center - half, base),
            (center - q, base + s * 0.6 * amp),
            (center, base + s * amp),
            (center + q, base + s * 0.6 * amp),
            (center + half, base),
            (center + half, base - s * overrun)]


def wave_ridge_and_divot(male_center, female_center, retention, male_base=0.0, female_base=0.0,
                         divot_depth=None, invert=False):
    """The two halves of one station, from one call — they cannot disagree.

    Returns (ridge_pts, divot_pts). Same profile, same direction, so the divot receives the
    ridge by construction. `divot_depth` defaults to the ridge amplitude; pass a deeper value
    when one female must serve several male amplitudes (a shallower ridge just does not bottom).
    `female_center` is the seat-mapped coordinate — male station c seats at whatever the caller's
    assembly transform sends it to, so the caller supplies it explicitly rather than guessing.
    """
    r = retention if hasattr(retention, "pattern") else resolve(retention)
    amp, width = r.m["amp"], r.m["width"]
    ridge = wave_profile(male_center, amp, width, base=male_base, invert=invert)
    divot = wave_profile(female_center, divot_depth or amp, width, base=female_base, invert=invert)
    return ridge, divot


def ratchet_profile(center, depth, groove_w, base=0.0, phase_ramp=1.0, overrun=OVERRUN):
    """QZ asymmetric groove — the uncut lands between grooves ARE the zip teeth.

    One ramped flank and one steep flank; mirroring `phase_ramp` on the opposing face is what
    produces zip-tie engagement (easy in, resisting out).
    """
    if depth <= 0 or groove_w <= 0:
        raise ValueError("ratchet depth and groove width must be positive")
    half = groove_w / 2.0
    ramp = half * phase_ramp
    return [(center - half, base + overrun),
            (center - ramp, base - depth),
            (center + half, base - depth),
            (center + half, base + overrun)]


def triangle_profile(base_w, y_center=0.0, z0=0.0):
    """Equilateral triangle, apex UP — the TF channel section and the TK key section."""
    h = base_w * math.sqrt(3) / 2.0
    return [(y_center - base_w / 2.0, z0), (y_center + base_w / 2.0, z0), (y_center, z0 + h)]


# ─────────────────────────────────────────────────────────────────────────────
# PLACEMENT — turn a profile into a solid on a named face.
# ─────────────────────────────────────────────────────────────────────────────
def _prism_xz(points, y0, y1):
    return (cq.Workplane("XZ", origin=(0, y1, 0)).polyline(points).close().extrude(y1 - y0).val())


def _prism_yz(points, x0, x1):
    return (cq.Workplane("YZ", origin=(x0, 0, 0)).polyline(points).close().extrude(x1 - x0).val())


def wave_train(retention, centers, band, plane="xz", base=0.0, invert=False):
    """A full train of waves at `centers`, spanning `band` transversely.

    `retention` is a WAVE_TRAIN registry sample — amplitude, width and pitch all come from it,
    never from a local constant. Returns solids; the CALLER fuses (ridge) or cuts (divot).
    `invert` is direction only — see `wave_profile`; both halves of a station share it.
    """
    r = retention if hasattr(retention, "pattern") else resolve(retention)
    if r.pattern.id != "WAVE_TRAIN":
        raise ValueError("%s is not a WAVE_TRAIN sample" % r.id)
    amp, width = r.m["amp"], r.m["width"]
    lo, hi = band
    out = []
    for c in centers:
        pts = wave_profile(c, amp, width, base=base, invert=invert)
        out.append(_prism_xz(pts, lo, hi) if plane == "xz" else _prism_yz(pts, lo, hi))
    return out


def wave_centers(start, span, retention):
    """Pitch-matched centers filling `span` from `start` — male ridges and female divots MUST
    be generated from this same call, or the train interlocks at seat and nowhere else."""
    r = retention if hasattr(retention, "pattern") else resolve(retention)
    pitch = r.m["pitch"]
    n = int(span // pitch)
    return tuple(round(start + pitch * i, 4) for i in range(n))


def ratchet_band(retention, centers, band, base=0.0, phase=0.0, mirror=False):
    """QZ groove cutters across `band`. Pass `phase=retention.m['phase']` on the opposing face —
    the half-pitch offset plus mirrored ramps is what makes it a ratchet rather than a rasp."""
    r = retention if hasattr(retention, "pattern") else resolve(retention)
    if r.pattern.id != "SHOULDER_RATCHET":
        raise ValueError("%s is not a SHOULDER_RATCHET sample" % r.id)
    depth, groove_w = r.m["depth"], r.m["groove_w"]
    lo, hi = band
    return [_prism_xz(ratchet_profile(c + phase, depth, groove_w, base=base,
                                      phase_ramp=-1.0 if mirror else 1.0), lo, hi)
            for c in centers]


# ─────────────────────────────────────────────────────────────────────────────
# JOINTS — count-parameterised, retention attached by construction.
# ─────────────────────────────────────────────────────────────────────────────
def _assert_retention_fits(joint, retention, location=None, allow_unproven=False):
    """RULE R1, enforced at BUILD time — you cannot author the VD R1 jam by accident.

    Only binds where the teeth sit inside the joint's clearance envelope; shoulder teeth on
    compression faces outside the dovetail are governed by preload instead (see
    `joints.retention_location`).

    `allow_unproven=True` is the COUPON escape hatch. Configurations that are merely unproven
    (as opposed to known-jamming) must be buildable — otherwise the library forbids the very
    experiment that would qualify them. Known failures stay blocked either way, so the hatch
    cannot resurrect VW20 or an open-lap amplitude used captured.
    """
    if retention is None:
        return
    r = retention if hasattr(retention, "pattern") else resolve(retention)
    ok, msg = check_retention(joint, r, location=location, strict=not allow_unproven)
    if not ok:
        hint = "" if allow_unproven else \
            " — pass allow_unproven=True if this IS the coupon meant to prove it"
        raise ValueError("%s + %s: %s%s" % (joint.id, r.id, msg, hint))


def twin_dovetail(sample, count=2, pitch=STUDIO_PITCH, retention=None, length=20.0,
                  engage=20.0, center=0.0, wave_band=None, wave_start=None,
                  retention_location=None, allow_unproven=False):
    """N-up flared-fin dovetail: male fins + the matching female groove cutters, WITH retention.

    `count` is the ONLY thing that changes between a double and a triple dovetail — spacing comes
    from `stations()`, the studio's +/-7 convention, and the retention train is emitted on both
    halves from one profile so the ridges and divots cannot drift out of phase.

    Returns (male_solids, female_cutters). The female carries the sample's clearances; the male
    is built at exact nominal, which is the qualified convention (VDM is exact, VDF adds).
    """
    s = sample if hasattr(sample, "pattern") else resolve(sample)
    if s.pattern.id != "TWIN_DOVETAIL":
        raise ValueError("%s is not a TWIN_DOVETAIL sample" % s.id)
    _assert_retention_fits(s, retention, location=retention_location,
                           allow_unproven=allow_unproven)

    neck, crest, proud = s.m["neck"], s.m["crest"], s.m["proud"]
    wc, dc = s.m["width_clearance"], s.m["depth_clearance"]
    ys = stations(count, pitch=pitch, center=center)

    males, females = [], []
    for y in ys:
        males.append(_fin(y, neck, crest, proud, length))
        females.append(_fin(y, neck + wc, crest + wc, proud + dc, engage))

    if retention is not None:
        r = retention if hasattr(retention, "pattern") else resolve(retention)
        band = wave_band if wave_band is not None else (ys[0] + crest / 2.0, ys[-1] - crest / 2.0)
        if band[0] >= band[1]:
            raise ValueError("no flat wall band between fins at count=%d pitch=%.2f — widen the "
                             "pitch or drop retention (teeth never go on the sloped flanks, R5)"
                             % (count, pitch))
        start = wave_start if wave_start is not None else r.m["pitch"] / 2.0
        centers = wave_centers(start, engage, r)
        males += wave_train(r, centers, band, plane="xz", base=proud, invert=False)
        females += wave_train(r, centers, band, plane="xz", base=proud + dc, invert=False)
    return males, females


def _fin(y_center, neck, crest, proud, length):
    """One flared fin: neck at the root, crest at the top, flaring over `proud`.

    Wide-at-TOP in build orientation. NOTE the registry gotcha: this inverts under a 180 deg
    assembly flip, so a foot authored here must be run through the ACTUAL assembly transform in
    the caller's assert — checking a separately-built 'correct' foot masks the bug.
    """
    pts = [(-neck / 2.0, 0.0), (neck / 2.0, 0.0), (crest / 2.0, proud), (-crest / 2.0, proud)]
    shifted = [(y + y_center, z) for y, z in pts]
    return (cq.Workplane("YZ").polyline(shifted).close().extrude(length).val())


def triangle_channels(sample, count=2, pitch=STUDIO_PITCH, center=0.0, section_t=None,
                      length=None, axis="x"):
    """N-up TF female channels — apex-up, self-supporting, centred in the section thickness.

    Returns cutters. Skins above and below are asserted against the sample's qualified value:
    1.575mm in an 8mm section is the proven geometry, and a thinner skin is a different joint.
    """
    s = sample if hasattr(sample, "pattern") else resolve(sample)
    if s.pattern.id != "TRIANGLE_CHANNEL":
        raise ValueError("%s is not a TRIANGLE_CHANNEL sample" % s.id)
    t = section_t if section_t is not None else s.m["section_t"]
    depth = length if length is not None else s.m["depth"]
    h = s.m["base_w"] * math.sqrt(3) / 2.0
    skin = (t - h) / 2.0
    if skin < s.m["skin"] - 1e-6:
        raise ValueError("%s in a %.2fmm section leaves %.3fmm skins, under the qualified "
                         "%.3fmm — re-coupon or thicken the section (rule R3)"
                         % (s.id, t, skin, s.m["skin"]))
    cutters = []
    for y in stations(count, pitch=pitch, center=center):
        pts = triangle_profile(s.m["base_w"], y_center=y, z0=skin)
        cutters.append(_prism_yz(pts, -OVERRUN, depth) if axis == "x"
                       else _prism_xz(pts, -OVERRUN, depth))
    return cutters


def triangle_key(sample, dimples=True):
    """The TK barrel key: tapered tips under bore size, oversize middle, apex flat, edge chamfers.

    The barrel is the whole trick — tips UNDER the channel so end-face seam blobs never gate
    insertion, and a 10mm seam-spanning tight zone in the middle doing the holding (R6).
    """
    s = sample if hasattr(sample, "pattern") else resolve(sample)
    if s.pattern.id != "TRIANGLE_KEY":
        raise ValueError("%s is not a TRIANGLE_KEY sample" % s.id)
    mid_w, tip_w = s.m["mid_w"], s.m["tip_w"]
    klen, taper = s.m["key_len"], s.m["taper_len"]
    h_mid = mid_w * math.sqrt(3) / 2.0

    def wire_at(w, x):
        return cq.Workplane("YZ", origin=(x, 0, 0)).polyline(triangle_profile(w)).close()

    lead = wire_at(tip_w, 0).workplane(offset=taper).polyline(triangle_profile(mid_w)).close() \
        .loft().val()
    mid = (cq.Workplane("YZ", origin=(taper, 0, 0)).polyline(triangle_profile(mid_w)).close()
           .extrude(klen - 2 * taper).val())
    tail = wire_at(mid_w, klen - taper).workplane(offset=taper) \
        .polyline(triangle_profile(tip_w)).close().loft().val()
    k = lead.fuse(mid).fuse(tail)

    z_flat = h_mid * (1 - s.m["apex_flat"] / mid_w)
    k = k.cut(Solid.makeBox(klen + 2, mid_w + 2, h_mid, Vector(-1, -mid_w / 2 - 1, z_flat)))
    ch = s.m["edge_chamfer"]
    for sgn in (-1, 1):
        pts = [(sgn * (mid_w / 2 - ch), -0.1), (sgn * (mid_w / 2 + 0.1), -0.1),
               (sgn * (mid_w / 2 + 0.1), ch)]
        k = k.cut(cq.Workplane("YZ").polyline(pts).close().extrude(klen + 2).val()
                  .translate(Vector(-1, 0, 0)))
    if dimples:
        for dx, dy in _DIMPLES.get(s.id, ()):
            k = k.cut(Solid.makeCylinder(0.5, 0.4, Vector(klen / 2 + dx, dy, -0.1),
                                         Vector(0, 0, 1)))
    return k.clean()


def banded_triangle_key(sample, centres=None, dimples=True):
    """A triangle key that spans SEVERAL members: tip width throughout, gauge-width BANDS where it
    grips.

    The barrel key holds along its whole middle, which is fine across one member and wrong across
    three: a 36mm stretch of TK10 grips over 24mm, 2.4x the qualified engagement at the same
    interference, and it needs pliers (RTG, 2026-08-01). Relieving everything except short bands
    makes friction track BAND LENGTH instead of KEY LENGTH, so a long key can carry a qualified
    engagement.

    THE GOVERNING MEASURE IS `tight_zone`, THE TOTAL. RTG ran 12mm of contact as three bands and
    again as two and BOTH jammed, while 9mm as three bands came in and out by hand — so where the
    grip sits does not matter and only how much of it there is does. `centres` is therefore a
    layout convenience, not a fit parameter: place the bands wherever the members are.
    """
    s = sample if hasattr(sample, "pattern") else resolve(sample)
    if s.pattern.id != "BANDED_TRIANGLE_KEY":
        raise ValueError("%s is not a BANDED_TRIANGLE_KEY sample" % s.id)
    mid_w, tip_w = s.m["mid_w"], s.m["tip_w"]
    klen, L, ramp = s.m["key_len"], s.m["band_len"], s.m["ramp_len"]
    pitch, n = s.m["band_pitch"], int(s.m["band_n"])
    if centres is None:
        centres = tuple(pitch / 2.0 + i * pitch for i in range(n))
    if len(centres) != n:
        raise ValueError("%s declares band_n=%d but got %d centres" % (s.id, n, len(centres)))
    if abs(L * n - s.m["tight_zone"]) > 1e-6:
        raise ValueError("%s: %d bands of %.2f is %.2f of contact, but tight_zone says %.2f — the "
                         "governing measure and the geometry disagree"
                         % (s.id, n, L, L * n, s.m["tight_zone"]))
    relief = pitch - L - 2 * ramp
    if relief < 1.0:
        raise ValueError("%s: a %.1fmm band with %.1fmm ramps on a %.1fmm pitch leaves %.2fmm of "
                         "relieved run — the bands merge and the key silently becomes a plain "
                         "barrel gripping its whole length" % (s.id, L, ramp, pitch, relief))

    def wire(w, x):
        return cq.Workplane("YZ", origin=(x, 0, 0)).polyline(triangle_profile(w)).close()

    k = wire(tip_w, 0).workplane(offset=klen).polyline(triangle_profile(tip_w)).close().loft().val()
    for c in centres:
        x0, x1 = c - L / 2.0, c + L / 2.0
        if x0 - ramp < -1e-9 or x1 + ramp > klen + 1e-9:
            raise ValueError("%s: a band centred at %.1f overruns the %.0fmm key" % (s.id, c, klen))
        seg = wire(tip_w, x0 - ramp).workplane(offset=ramp).polyline(
            triangle_profile(mid_w)).close().loft().val()
        seg = seg.fuse(cq.Workplane("YZ", origin=(x0, 0, 0))
                       .polyline(triangle_profile(mid_w)).close().extrude(L).val())
        seg = seg.fuse(wire(mid_w, x1).workplane(offset=ramp).polyline(
            triangle_profile(tip_w)).close().loft().val())
        k = k.fuse(seg)
    k = _apex_and_chamfer(k.clean(), mid_w, s.m["apex_flat"], s.m["edge_chamfer"], klen)
    if dimples:
        for dx, dy in _DIMPLES.get(s.id, ()):
            k = k.cut(Solid.makeCylinder(0.5, 0.4, Vector(klen / 2 + dx, dy, -0.1),
                                         Vector(0, 0, 1)))
    return k.clean()


def _apex_and_chamfer(k, w_ref, apex_flat, edge_chamfer, klen):
    """TK's apex flat + bottom edge chamfers, both sized from `w_ref`.

    The chamfer cutter sits at a FIXED y for the whole key, so it bites a tip-width section
    differently from a gauge-width one — which is what `triangle_key` has always done, its cutter
    being sized from mid_w while the key still has tapered tips. Preserved, not corrected: it
    means no section's finished width follows from its nominal, so anything checking a key must
    measure against a reference put through this same function.
    """
    h = w_ref * math.sqrt(3) / 2.0
    z_flat = h * (1 - apex_flat / w_ref)
    k = k.cut(Solid.makeBox(klen + 4, w_ref + 4, h, Vector(-2, -(w_ref + 4) / 2, z_flat)))
    for sgn in (-1, 1):
        pts = [(sgn * (w_ref / 2 - edge_chamfer), -0.1), (sgn * (w_ref / 2 + 0.1), -0.1),
               (sgn * (w_ref / 2 + 0.1), edge_chamfer)]
        k = k.cut(cq.Workplane("YZ").polyline(pts).close().extrude(klen + 4).val()
                  .translate(Vector(-2, 0, 0)))
    return k


# Bed-dimple identity, transverse cluster = the R3 family mark (an R3 one-dot must not read as
# R2's TK15, whose single dot sits in a lengthwise row).
_DIMPLES = {"TK05": ((0.0, 0.0),),
            "TK10": ((0.0, -1.2), (0.0, 1.2)),
            "TK12": ((0.0, -1.2), (0.0, 1.2), (2.2, 0.0)),
            # SUB-NOMINAL family: dots in a LENGTHWISE row, well spread, so a TKN can never be
            # mistaken for its positive namesake — TK10's two dots sit across the width at +/-1.2,
            # TKN10's sit along the length at +/-5. Same trick that separated the R3 keys from
            # R2's. Without this all four sub-nominal keys print identical and the ladder is
            # unreadable once the parts leave the bed (rule R8).
            "TKN05": ((-5.0, 0.0),),
            "TKN10": ((-5.0, 0.0), (5.0, 0.0)),
            "TKN15": ((-5.0, 0.0), (0.0, 0.0), (5.0, 0.0)),
            # RKL rim-key re-ladder: TRANSVERSE, because every 36mm key from the RTG round carries
            # LENGTHWISE dots. RK3 itself stays unmarked, so it is identical to the 16 already
            # printed and serves as the control without a second geometry.
            "RK3A": ((0.0, 0.0),),
            "RK3B": ((0.0, -1.3), (0.0, 1.3))}


def containment(male, female_envelope):
    """Fraction of `male` inside the female clearance envelope. 1.0 = fully contained.

    The standing digital gate for every joint here: a male that is not 100% contained will not
    assemble, and interference volume against the SMOOTH envelope must be 0.0mm^3.
    """
    if male.Volume() <= 0:
        raise ValueError("male solid has no volume")
    return female_envelope.intersect(male).Volume() / male.Volume()
