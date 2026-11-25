import unittest

import numpy as np

from dfm_check import gaps, normals_areas


def facing_planes(distance, second_faces_back=True):
    first = [[(0, 0, 0), (0, 1, 0), (0, 0, 1)]]       # +X
    second = ([(distance, 0, 0), (distance, 0, 1), (distance, 1, 0)]
              if second_faces_back else
              [(distance, 0, 0), (distance, 1, 0), (distance, 0, 1)])
    return np.array(first + [second], dtype=np.float64)


class ExternalGapTests(unittest.TestCase):
    def test_outward_rays_measure_a_nozzle_scale_valley(self):
        tri = facing_planes(0.25)
        normals, _ = normals_areas(tri)
        widths, _ = gaps(tri, normals, samples=10, rng=np.random.default_rng(0))
        self.assertEqual(len(widths), 2)
        self.assertAlmostEqual(widths.min(), 0.2499, places=4)  # ray starts 0.0001 into the gap
        self.assertLess(widths.min(), 0.4)

    def test_same_facing_surfaces_are_not_called_a_gap(self):
        tri = facing_planes(0.25, second_faces_back=False)
        normals, _ = normals_areas(tri)
        widths, _ = gaps(tri, normals, samples=10, rng=np.random.default_rng(0))
        self.assertEqual(len(widths), 0)

    def test_wide_valley_clears_nozzle_floor(self):
        tri = facing_planes(0.75)
        normals, _ = normals_areas(tri)
        widths, _ = gaps(tri, normals, samples=10, rng=np.random.default_rng(0))
        self.assertGreater(widths.min(), 0.4)


if __name__ == "__main__":
    unittest.main()
