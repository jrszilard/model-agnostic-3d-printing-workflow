import unittest

from probe import ProbeError, assert_pieces_apart, assert_single_solid, volume


class FakeShape:
    def __init__(self, amount=1.0, count=1):
        self.amount, self.count = amount, count
    def isNull(self): return False
    def Volume(self): return self.amount
    def Solids(self): return [self] * self.count


class FakeBox(FakeShape):
    """An axis-aligned box, x0..x1 along x, unit size in y and z."""
    def __init__(self, x0, x1, count=1):
        super().__init__(x1 - x0, count)
        self.x0, self.x1 = x0, x1
        self.measured = 0
    def BoundingBox(self):
        return type("BB", (), dict(xmin=self.x0, xmax=self.x1, ymin=0, ymax=1, zmin=0, zmax=1))()
    def distance(self, other):
        self.measured += 1
        return max(other.x0 - self.x1, self.x0 - other.x1, 0.0)


class ProbeDependencyTests(unittest.TestCase):
    def test_module_operates_without_importing_cadquery(self):
        self.assertEqual(volume(FakeShape(3.5)), 3.5)

    def test_single_solid_is_a_fail_loud_invariant(self):
        with self.assertRaises(ProbeError):
            assert_single_solid(FakeShape(count=2), "fixture")

    def test_pieces_apart_fires_on_near_pieces_and_a_split_piece(self):
        self.assertEqual(assert_pieces_apart([FakeBox(0, 1), FakeBox(3, 4)], 1.0), 2.0)
        with self.assertRaises(ProbeError):
            assert_pieces_apart([FakeBox(0, 1), FakeBox(1.5, 2)], 1.0)
        with self.assertRaises(ProbeError):
            assert_pieces_apart([FakeBox(0, 1), FakeBox(5, 6, count=2)], 1.0)

    def test_pieces_apart_skips_the_exact_measure_for_distant_boxes(self):
        a = FakeBox(0, 1)
        assert_pieces_apart([("A", a), ("B", FakeBox(10, 11))], 1.0)
        self.assertEqual(a.measured, 0)


if __name__ == "__main__":
    unittest.main()
