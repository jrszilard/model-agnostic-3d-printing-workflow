import importlib.util
import os
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    path = os.path.join(HERE, name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class CadQueryTemplateSmokeTests(unittest.TestCase):
    def test_safe_boolean_and_explicit_datum_examples_build(self):
        booleans = load("cadquery-safe-booleans.py")
        shape = booleans.overlapping_pads([(0, 0), (2, 0)], [3, 3], 2)
        self.assertEqual(len(shape.val().Solids()), 1)
        workplanes = load("cadquery-stable-workplanes.py")
        self.assertEqual(len(workplanes.two_boss_plate().val().Solids()), 1)

    def test_plate_check_fires_on_pieces_a_compound_count_passes(self):
        booleans = load("cadquery-safe-booleans.py")
        import cadquery as cq
        a = cq.Workplane("XY").box(10, 10, 2)
        booleans.assert_disjoint_plate([a, a.translate((12, 0, 0))])
        for x in (9.0, 10.0, 10.5):          # overlapping, touching, 0.5 apart: one compound, two solids
            with self.assertRaises(Exception):
                booleans.assert_disjoint_plate([("A", a), ("B", a.translate((x, 0, 0)))])

    def test_sol_terra_transition_example_is_valid(self):
        transition = load("cadquery-clean-transition.py").example_transition()
        self.assertTrue(transition.val().isValid())
        self.assertEqual(len(transition.val().Solids()), 1)

    def test_mechanism_checks_pass_and_refuse_a_holder_with_no_catch(self):
        m = load("cadquery-mechanism-checks.py")
        lines = m.all_checks(m.holder(), m.box(), jobs=1)
        self.assertEqual(len(lines), 6)
        self.assertIn("never nearer than 0.15", lines[3])
        swing = float(lines[5].split(":")[1].split()[0])           # the box rolls in its 0.3 of room
        self.assertGreater(swing, 0.15); self.assertLess(swing, 0.45)
        with self.assertRaises(Exception) as caught:
            m.hold_checks(m.holder(catch=False), m.box())
        self.assertIn("only friction holds it", str(caught.exception))
        with self.assertRaises(Exception) as caught:              # set against the deck, it scrapes on the way in
            m.motion.sweep(m.box(), m.holder(), m.motion.slide((0.0, -30.0, 0.0), 6, start=1.0, end=0.0), clearance=0.1)
        self.assertIn("comes within", str(caught.exception))

    def test_surface_and_fitcore_helpers_load(self):
        surfaces = load("cadquery-surfaces-and-text.py")
        self.assertEqual(surfaces.layer_aligned_height(1.6), 1.6)
        fitcore = load("cadquery-fitcore.py")
        self.assertEqual(len(fitcore.FIT_ID), 16)


if __name__ == "__main__":
    unittest.main()
