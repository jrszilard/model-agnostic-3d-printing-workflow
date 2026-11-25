"""Label-map logic: the parts that must hold without FreeCAD.

The point of a labelled drawing is that the human REPLY is unambiguous — "F12 is too shallow"
rather than "the curved bit near the top on the left". That only works if an id means one face,
the same face, every time the drawing is regenerated from the same geometry.
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, "..", "..", ".."))
LABEL_MAP = os.path.join(ROOT, "platform", "pipeline", "preview", "label-map.py")


def _load_pure():
    """label-map.py imports Part and calls sys.exit() at module scope, because freecadcmd never
    sets __name__ to __main__. Read the source and exec only the pure helpers."""
    with open(LABEL_MAP) as stream:
        source = stream.read()
    head = source.split("def main(")[0].replace("import Part", "")
    namespace = {"__name__": "labelmap"}
    exec(compile(head, LABEL_MAP, "exec"), namespace)
    return namespace


class Fake(object):
    """Minimal stand-in for a FreeCAD face."""
    class _Surface(object):
        def __init__(self, name, radius=None):
            self.__class__ = type(name, (object,), {})
            if radius is not None:
                self.Radius = radius

    def __init__(self, kind, area, centroid, normal, radius=None):
        surface = type(kind, (object,), {})()
        if radius is not None:
            surface.Radius = radius
        self.Surface = surface
        self.Area = area
        self.CenterOfMass = type("V", (object,), dict(x=centroid[0], y=centroid[1],
                                                      z=centroid[2]))()
        self._normal = normal
        self.ParameterRange = (0.0, 1.0, 0.0, 1.0)

    def normalAt(self, u, v):
        return self._normal


class Shape(object):
    def __init__(self, faces):
        self.Faces = faces


LM = _load_pure()


class SurfaceNaming(unittest.TestCase):
    def test_kinds_are_words_you_would_say_aloud(self):
        cases = {"Plane": "flat", "Cylinder": "round", "Cone": "taper", "BSplineSurface": "curve"}
        for raw, spoken in cases.items():
            with self.subTest(raw=raw):
                face = Fake(raw, 1.0, (0, 0, 0), (0, 0, 1))
                self.assertEqual(LM["surface_kind"](face), spoken)


class StableIdentity(unittest.TestCase):
    def test_same_geometry_gives_the_same_ids(self):
        """A drawing regenerated from unchanged geometry must reuse its labels, or a reference
        given in review stops meaning anything."""
        def build():
            return Shape([Fake("Plane", 10.0, (0, 0, 5), (0, 0, 1)),
                          Fake("Cylinder", 8.0, (1, 1, 2), (1, 0, 0), radius=3.0),
                          Fake("Plane", 6.0, (0, 2, 9), (0, 1, 0))])
        first = {r["id"]: r["fingerprint"] for r in LM["catalogue"](build())}
        second = {r["id"]: r["fingerprint"] for r in LM["catalogue"](build())}
        self.assertEqual(first, second)

    def test_ids_do_not_depend_on_export_order(self):
        """OCCT's face order is an exporter artifact. Sorting is geometric so the same solid
        catalogues identically however Shape.Faces happens to come out."""
        faces = [Fake("Plane", 10.0, (0, 0, 5), (0, 0, 1)),
                 Fake("Cylinder", 8.0, (1, 1, 2), (1, 0, 0), radius=3.0),
                 Fake("Plane", 6.0, (0, 2, 9), (0, 1, 0))]
        forward = [(r["id"], r["fingerprint"]) for r in LM["catalogue"](Shape(list(faces)))]
        reverse = [(r["id"], r["fingerprint"]) for r in LM["catalogue"](Shape(list(reversed(faces))))]
        self.assertEqual(forward, reverse)

    def test_a_changed_face_changes_its_fingerprint(self):
        before = LM["catalogue"](Shape([Fake("Cylinder", 8.0, (1, 1, 2), (1, 0, 0), radius=3.0)]))
        after = LM["catalogue"](Shape([Fake("Cylinder", 8.0, (1, 1, 2), (1, 0, 0), radius=4.0)]))
        self.assertNotEqual(before[0]["fingerprint"], after[0]["fingerprint"])


class LabelSelection(unittest.TestCase):
    def test_slivers_are_not_labelled(self):
        """k1c-elbow has 94 faces. A drawing with 94 callouts is not a decision aid."""
        rows = LM["catalogue"](Shape([Fake("Plane", 100.0, (0, 0, 0), (0, 0, 1)),
                                      Fake("Plane", 0.02, (1, 0, 0), (0, 0, 1))]))
        by_area = {r["area_mm2"]: r["labelled"] for r in rows}
        self.assertTrue(by_area[100.0])
        self.assertFalse(by_area[0.02])

    def test_the_cap_keeps_the_largest_faces(self):
        faces = [Fake("Plane", float(n), (0, 0, n), (0, 0, 1)) for n in range(1, 31)]
        rows = LM["catalogue"](Shape(faces), max_labels=5)
        kept = sorted((r["area_mm2"] for r in rows if r["labelled"]), reverse=True)
        self.assertEqual(kept, [30.0, 29.0, 28.0, 27.0, 26.0])


class ViewVisibility(unittest.TestCase):
    def test_only_faces_pointing_at_the_camera_are_annotated(self):
        """A label on a face pointing away lands on top of whatever is in front of it, and says
        something false about the part."""
        rows = LM["catalogue"](Shape([Fake("Plane", 10.0, (0, 0, 5), (0, 0, 1)),    # up: in TOP
                                      Fake("Plane", 10.0, (0, 0, -5), (0, 0, -1))]))  # down: not
        top = LM["annotations_for_view"](rows, "top")
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["at"], [0, 0])

    def test_edge_on_faces_are_skipped(self):
        rows = LM["catalogue"](Shape([Fake("Plane", 10.0, (0, 0, 0), (1, 0, 0.05))]))
        self.assertEqual(LM["annotations_for_view"](rows, "top"), [])

    def test_annotation_shape_matches_what_plan_drawing_consumes(self):
        """plan-drawing.load_annotations requires text and a two-element `at`."""
        rows = LM["catalogue"](Shape([Fake("Plane", 10.0, (1, 2, 3), (0, 0, 1))]))
        for item in LM["annotations_for_view"](rows, "top"):
            self.assertTrue(item["text"])
            self.assertEqual(len(item["at"]), 2)


if __name__ == "__main__":
    unittest.main()
