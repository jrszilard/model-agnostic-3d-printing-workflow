#!/usr/bin/env python3
"""label-map.py — name every face of a part so a human can point at one.

WHY THIS EXISTS
`plan-drawing.py` has always been able to draw a labelled orthographic view, but its annotations
are HAND-AUTHORED: you supply the text and the coordinate. That requires already knowing which
feature matters and where it is, which is backwards. The reason to look at a labelled drawing is to
work out which area needs revising, and then to say so without inventing a description — "the
curved bit near the top on the left" is exactly the ambiguity `docs/workflow.md` says to kill with a
labelled drawing, and it is the dominant published failure mode in text-to-CAD (Pro-CAD,
arXiv:2602.03045: a clarifier asking 1-2 targeted questions took mean Chamfer 7.80 -> 0.63).

So the labels are DERIVED from the B-rep instead of typed. Every face gets a short id, its surface
type, and its size. You say "F07 is too shallow" and there is no ambiguity left to resolve.

It reads the STEP, not the STL, because a mesh has no faces — only triangles. A cylindrical face is
the bore you want to point at; in a mesh it is 96 unnamed facets.

Output is exactly the annotation format plan-drawing.py already eats, so nothing in the renderer
changes:  [{"text": "F07", "at": [u, v]}, ...]

Usage:  STEP=<part.step> freecadcmd label-map.py            (env var: freecadcmd opens argv paths)
        options via LABEL_VIEW=top|front|side  LABEL_OUT=<dir>  LABEL_MAX=<n>
"""
import hashlib
import json
import os
import sys

import Part

# Which two axes each view shows, and which way the camera looks. Mirrors plan-drawing.py's VIEWS
# so a label lands where the renderer draws it.
VIEWS = {
    "top":   {"plane": (0, 1), "normal": 2, "sign": +1, "axes": ("X", "Y")},
    "front": {"plane": (0, 2), "normal": 1, "sign": -1, "axes": ("X", "Z")},
    "side":  {"plane": (1, 2), "normal": 0, "sign": -1, "axes": ("Y", "Z")},
}

# A part can have hundreds of faces — k1c-elbow has 94, and a labelled drawing with 94 callouts is
# not a decision aid. Filter to what a human could actually point at.
MIN_AREA_MM2 = 0.5          # absolute floor: below this it is a sliver or a fillet edge
MIN_AREA_FRAC = 0.01        # and at least 1% of the largest face
DEFAULT_MAX_LABELS = 14


def surface_kind(face):
    """Plane / Cylinder / Cone / Sphere / Toroid / BSplineSurface -> a word you would say aloud."""
    raw = face.Surface.__class__.__name__
    return {"Plane": "flat", "Cylinder": "round", "Cone": "taper", "Sphere": "dome",
            "Toroid": "torus", "BSplineSurface": "curve", "SurfaceOfRevolution": "revolve",
            "BezierSurface": "curve"}.get(raw, raw.lower())


def face_radius(face):
    surface = face.Surface
    for attr in ("Radius", "Radius1"):
        if hasattr(surface, attr):
            try:
                return float(getattr(surface, attr))
            except (TypeError, ValueError):
                pass
    return None


def fingerprint(face):
    """Stable identity for ONE face, independent of its position in Shape.Faces.

    Same idea as parts/_lib/fitcore.py: hash what the thing IS, not how the exporter happened to
    order it. Lets a later run report "the face you called F07 is now F09" instead of silently
    renumbering under a reference you already gave.
    """
    com = face.CenterOfMass
    payload = "%s|%.4f|%.3f,%.3f,%.3f|%s" % (
        surface_kind(face), face.Area, com.x, com.y, com.z,
        ("%.4f" % face_radius(face)) if face_radius(face) is not None else "-")
    return hashlib.sha256(payload.encode()).hexdigest()[:8]


def outward_normal(face):
    """FreeCAD's normalAt already applies face orientation — do NOT flip on Orientation.

    Proven on Part.makeBox: the bottom face is Orientation='Reversed' and normalAt returns z=-1.00
    unaided. A flip here inverts roughly half of every solid's faces, and the 2026-08-22 review
    caught exactly that bug in a proposed overhang implementation.
    """
    u0, u1, v0, v1 = face.ParameterRange
    return face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)


def sort_key(face):
    """Deterministic geometric order, so ids do not shuffle between runs of the same geometry."""
    com = face.CenterOfMass
    return (round(com.z, 3), round(com.y, 3), round(com.x, 3), round(face.Area, 3))


def catalogue(shape, max_labels=DEFAULT_MAX_LABELS):
    faces = sorted(shape.Faces, key=sort_key)
    if not faces:
        return []
    largest = max(f.Area for f in faces)
    floor = max(MIN_AREA_MM2, MIN_AREA_FRAC * largest)
    rows = []
    for index, face in enumerate(faces, 1):
        com = face.CenterOfMass
        rows.append({
            "id": "F%02d" % index,
            "kind": surface_kind(face),
            "area_mm2": round(face.Area, 3),
            "radius_mm": (round(face_radius(face), 3) if face_radius(face) is not None else None),
            "centroid": [round(com.x, 4), round(com.y, 4), round(com.z, 4)],
            "normal": [round(v, 4) for v in tuple(outward_normal(face))],
            "fingerprint": fingerprint(face),
            "notable": face.Area >= floor,
        })
    # Rank by area so the cap keeps the faces a human would actually point at.
    notable = sorted([r for r in rows if r["notable"]], key=lambda r: -r["area_mm2"])
    keep = {r["id"] for r in notable[:max_labels]}
    for row in rows:
        row["labelled"] = row["id"] in keep
    return rows


def annotations_for_view(rows, view):
    """Faces whose outward normal points at this camera, projected onto the drawing plane."""
    spec = VIEWS[view]
    axis, sign = spec["normal"], spec["sign"]
    u_ax, v_ax = spec["plane"]
    out = []
    for row in rows:
        if not row["labelled"]:
            continue
        if row["normal"][axis] * sign <= 0.15:      # facing away, or edge-on: the label would lie
            continue
        out.append({"text": row["id"], "at": [row["centroid"][u_ax], row["centroid"][v_ax]]})
    return out


def main():
    step = os.environ.get("STEP")
    if not step or not os.path.exists(step):
        print("usage: STEP=<part.step> freecadcmd label-map.py [LABEL_VIEW=top|front|side]")
        return 2
    # LABEL_VIEW takes a comma-separated list. Reading and cataloguing the STEP does not depend on
    # the view -- only annotations_for_view does, and that is a pure comprehension over rows already
    # in memory, measured at 0.0 ms -- so calling this once per view re-read and re-tessellated the
    # same file three times and rewrote the identical 73 KB labelmap.json three times. One name is
    # still accepted, unchanged, because decision-drawing.sh and any hand invocation pass one.
    views = [v.strip() for v in os.environ.get("LABEL_VIEW", "top").split(",") if v.strip()]
    unknown = [v for v in views if v not in VIEWS]
    if not views or unknown:
        print("unknown view %r; choose from %s"
              % (unknown[0] if unknown else "", ", ".join(sorted(VIEWS))))
        return 2
    outdir = os.environ.get("LABEL_OUT") or os.path.dirname(os.path.abspath(step))
    max_labels = int(os.environ.get("LABEL_MAX", DEFAULT_MAX_LABELS))

    shape = Part.Shape(); shape.read(step)
    rows = catalogue(shape, max_labels)
    stem = os.path.splitext(os.path.basename(step))[0]

    map_path = os.path.join(outdir, "%s.labelmap.json" % stem)
    with open(map_path, "w") as stream:
        json.dump({"source": os.path.relpath(step, outdir), "faces": rows}, stream, indent=1)

    shown = sum(1 for r in rows if r["labelled"])
    for view in views:
        ann_path = os.path.join(outdir, "%s_%s.labels.json" % (stem, view))
        annotations = annotations_for_view(rows, view)
        with open(ann_path, "w") as stream:
            json.dump(annotations, stream, indent=1)
        print("labelled %d of %d faces (%s view: %d visible)"
              % (shown, len(rows), view, len(annotations)))
        print("  annotations -> %s" % ann_path)
    print("  label map   -> %s" % map_path)
    for row in rows:
        if row["labelled"]:
            radius = (" r%.2f" % row["radius_mm"]) if row["radius_mm"] else ""
            print("  %-4s %-8s %8.2f mm2%s" % (row["id"], row["kind"], row["area_mm2"], radius))
    sys.stdout.flush()   # freecadcmd can exit without flushing block-buffered stdout
    return 0


# freecadcmd sets __name__ to the module basename, so a standard guard never fires. This file is
# only ever executed as a FreeCAD script (it imports Part), never imported.
sys.exit(main())
