"""Curved envelopes, matching reliefs and mesh-safe text/colour planes."""
import cadquery as cq

BOOLEAN_OVERRUN = 0.05


def periodic_spline_body(points, height, top_fillet=0):
    """One clean top rim; a 194-segment polyline edge will usually refuse a fillet."""
    body = cq.Workplane("XY").spline(points, periodic=True).close().extrude(height)
    return body.edges(">Z").fillet(top_fillet) if top_fillet else body


def matching_lofts(outer_wires, relief_wires):
    """Outer and relief come from the same station/profile function.

    A constant-X cutter is an offset only from a parallel face. On a taper it created a nominal
    2 mm panel measuring 0.50..9.75 mm. Build both wire lists in one loop, then loft both.
    """
    outer = cq.Workplane(obj=cq.Solid.makeLoft(outer_wires, ruled=False))
    relief = cq.Workplane(obj=cq.Solid.makeLoft(relief_wires, ruled=False))
    return outer, relief


def pinned_text(text, font, size, z_face, depth, kind="bold", operation="raise"):
    """Pin string × font × size. Never silently fall through to a substitute font."""
    if not font:
        raise ValueError("font is a required geometric input")
    z0 = z_face - BOOLEAN_OVERRUN if operation == "cut" else z_face - BOOLEAN_OVERRUN
    solid = (cq.Workplane("XY").workplane(offset=z0)
             .text(text, size, depth + BOOLEAN_OVERRUN, combine=False,
                   font=font, kind=kind))
    if not solid.solids().size():
        raise RuntimeError("text produced no glyphs for %r in %s" % (text, font))
    return solid


def layer_aligned_height(nominal, layer_height=0.2):
    """M600 is a layer/Z event. Return an exact layer multiple or fail the design explicitly."""
    layers = round(nominal / layer_height)
    aligned = layers * layer_height
    if abs(aligned - nominal) > 1e-6:
        raise ValueError("%.3f mm is not a %.3f mm layer boundary; use %.3f (%d layers)" %
                         (nominal, layer_height, aligned, layers))
    return aligned


# Example: 1.6 mm relief is exactly eight 0.2 mm layers; 1.5 mm is rejected.
COLOUR_RELIEF = layer_aligned_height(1.6, 0.2)
