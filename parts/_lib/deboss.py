"""Debossed part-ID on a bed face — the physical marker tying a printed part
to its file structure.

THE RULE (docs/naming.md): every printed part carries its VARIANT KEY debossed
on the bed-facing surface — the same key the generator's VARIANTS dict and the
STL filename segment use (`<part>--<status>-<key>-<slug>.stl`), rendered
UPPERCASE on the part. When a pile of prints exists, the bottom face IS the
version history.

Lessons encoded (bottle-lamp-carrier rev history, see wiki cadquery-occ-folklore):
- Cut the label from a PLAIN primitive BEFORE fusing it into a complex solid —
  compound text cutters on swept/complex solids silently no-op.
- Start the text 0.2 BELOW the face: a cut boundary coplanar with the face
  silently no-ops too.
- Mirror in XZ: the text reads correctly when the part is flipped forward
  (unmirrored it prints backwards).

Usage:
    from _lib.deboss import deboss
    hub = deboss(hub, "C1PF", z_face=-5.0)          # then fuse hub into the part
"""
import os
import sys
import cadquery as cq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from joints import SAMPLES        # noqa: E402  — the registry owns the legibility baseline
from probe import intersection, volume  # noqa: E402

LD6 = SAMPLES["LD6"]


def deboss(solid, label, z_face, y=3.5, size=5.0, depth=0.8):
    """Legacy-compatible mirrored bed-face label.

    `depth` is the cutter extrusion beginning 0.2mm outside the face, so effective recess is
    `depth-0.2`. Preserve this API because historical generators depend on it; new physical parts
    should use `legible_deboss` where the face permits.
    """
    # Mirror the glyphs around their own origin, then place them. Mirroring text that was already
    # centered at +Y also mirrored its POSITION to -Y, so labels silently missed positive-Y parts.
    txt = (cq.Workplane("XY").workplane(offset=-0.2)
           .text(label, size, depth, combine=False, halign="center", valign="center"))
    cutter = txt.val().mirror("XZ").translate(cq.Vector(0, y, z_face))
    return solid.cut(cutter)


def _assert_on_face(solid, cutter, label, tol=0.05):
    """The glyph must sit entirely ON the face it marks (rule R8)."""
    inside = intersection(solid, cutter)
    if volume(inside) <= 1e-9:
        raise RuntimeError("label %r misses the part entirely — check x/y/z_face" % label)
    cb, ib = cutter.BoundingBox(), inside.BoundingBox()
    over = {"-x": cb.xmin - ib.xmin, "+x": ib.xmax - cb.xmax,
            "-y": cb.ymin - ib.ymin, "+y": ib.ymax - cb.ymax}
    bad = {k: v for k, v in over.items() if v < -tol}
    if bad:
        raise RuntimeError(
            "label %r is CLIPPED — it overhangs the face by %s (rule R8: labels centred on "
            "their face, along its long edge). Glyph spans x %.1f..%.1f y %.1f..%.1f; only "
            "x %.1f..%.1f y %.1f..%.1f lands on material."
            % (label, ", ".join("%s %.2fmm" % (k, -v) for k, v in bad.items()),
               cb.xmin, cb.xmax, cb.ymin, cb.ymax, ib.xmin, ib.xmax, ib.ymin, ib.ymax))


def legible_deboss(solid, label, z_face, y=4.0, x=0.0, size=None, effective_depth=None,
                    font="DejaVu Sans", kind=None, strict=True):
    """Physically qualified high-legibility bed-face identifier — registry sample **LD6**.

    The size/depth/weight defaults are NOT style choices and are NOT owned by this function: they
    come from `joints.SAMPLES["LD6"]`, qualified on Core One / PLA / 0.4 / 0.20. The counter-
    evidence is registered too — LD3 (3mm regular at ~0.4mm effective depth) was NEARLY
    UNREADABLE as printed, which is why the baseline exists.

    Passing smaller values still works, because a genuinely tiny face sometimes has no choice —
    but you are then off a qualified sample and owe a label coupon, exactly as with any other
    off-registry fit. Nothing here silently shrinks on your behalf.

    `x` places the glyph along the face. It defaults to 0, which is only the centre for a part
    modelled symmetrically about the origin — a rod built from x=0 to x=L has its centre at L/2,
    and leaving x at 0 hangs half the label off the end.

    CLIPPING IS NOW A BUILD-TIME FAILURE (`strict`). Rule R8 has been prose since the first
    incident and parts kept coming off the bed with unreadable IDs — bottle gauges, VC gauges, VD
    males, and on 2026-07-30 the tower rods, a print Justin had to stop. The check intersects the
    glyph cutter with the solid and requires the result to keep the cutter's full XY extent: if
    any part of the text overhangs the face, the intersection is smaller and this raises. Prose
    did not stop it four times; a check does.
    """
    _m = LD6.measures
    size = _m["size"] if size is None else size
    effective_depth = _m["effective_depth"] if effective_depth is None else effective_depth
    kind = _m["weight"] if kind is None else kind
    txt = (cq.Workplane("XY").workplane(offset=-0.2)
           .text(label, size, effective_depth+0.2, combine=False,
                 halign="center", valign="center", font=font, kind=kind))
    cutter = txt.val().mirror("XZ").translate(cq.Vector(x, y, z_face))
    if strict:
        _assert_on_face(solid, cutter, label)
    return solid.cut(cutter)


# A mesh-safe fallback for tight/boolean-heavy faces. Unlike a font outline it has no
# enclosed glyph loops or splines: every mark is a separated rectangular stencil pixel. It is
# deliberately suitable for variant IDs only, not decorative typography. The social-notebook
# production base caught the need: a conventional SSBA outline passed B-rep validity but made the
# STL self-intersect; this keeps the required physical traceability without weakening the mesh.
_STENCIL = {
    "A": ("010", "101", "101", "111", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("111", "100", "100", "100", "111"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("111", "100", "101", "101", "111"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("011", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("111", "101", "101", "101", "111"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("111", "101", "101", "111", "001"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("111", "100", "111", "001", "111"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("110", "001", "111", "100", "111"),
    "3": ("110", "001", "011", "001", "110"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "-": ("000", "000", "111", "000", "000"),
}


def stencil_deboss(solid, label, z_face, x=0.0, y=0.0, cell=1.2, depth=1.2,
                   mirror_y=True, strict=True):
    """Cut a 3×5 separated-pixel variant label from a planar face.

    This is a deliberately mesh-safe FALLBACK for an ID face where conventional font
    outlines introduce self-intersections — it is NOT the default marker. Where the face
    takes a real font, use :func:`legible_deboss` (docs/workflow.md: the qualified baseline
    is 6mm bold with a true 1mm recess; the pixel font is materially harder to read, which
    the LFC coupon proved physically on 2026-08-18). ``cell=1.2`` gives a 6 mm high
    identifier matching the physical LD6 height baseline; each pixel is 0.86 cell wide with
    a visible gap, so no character encloses a loose material island. Like
    :func:`legible_deboss`, the default mirrors the glyph around its own origin for a
    bed-face label that reads after the part is flipped.

    CLIPPING IS A BUILD-TIME FAILURE here too (``strict``). Rule R8's check originally
    lived only in ``legible_deboss``, so the ungated stencil path shipped a clipped coupon
    ID (third escape overall). The pixel cutters make the bbox check unsuitable; instead
    the cut volume is compared against the label's nominal recess volume — a pixel hanging
    off the face removes less material than it should, and this raises.
    """
    label = label.upper()
    if not label or any(ch not in _STENCIL and ch != " " for ch in label):
        raise ValueError("stencil label supports uppercase A-Z, 0-9, hyphen and space: %r" % label)
    char_w, advance, pixel = 3 * cell, 4.05 * cell, 0.86 * cell
    total = (len(label) - 1) * advance + char_w
    out = solid
    n_pixels = 0
    for i, ch in enumerate(label):
        if ch == " ":
            continue
        x0 = x - total / 2.0 + i * advance
        for row, bits in enumerate(_STENCIL[ch]):
            for col, bit in enumerate(bits):
                if bit != "1":
                    continue
                n_pixels += 1
                px = x0 + col * cell + cell / 2.0
                py_local = (2 - row) * cell
                py = y - py_local if mirror_y else y + py_local
                cutter = (cq.Workplane("XY").center(px, py)
                          .box(pixel, pixel, depth, centered=(True, True, False))
                          .translate((0, 0, z_face - 0.2)))
                out = out.cut(cutter.val())
    if strict:
        removed = solid.Volume() - out.Volume()
        nominal = n_pixels * pixel * pixel * (depth - 0.2)
        if removed < nominal * 0.95:
            raise RuntimeError(
                "stencil label %r is CLIPPED or off-face — cut %.2fmm³ of a nominal %.2fmm³ "
                "(rule R8: labels centred on their face). Check x/y/z_face against the face "
                "extents." % (label, removed, nominal))
    return out.clean()
