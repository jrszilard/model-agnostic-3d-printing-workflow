import os
import sys
import unittest

import cadquery as cq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fitcore import assert_fit_regions
from probe import ProbeError


class FitCoreRegionTests(unittest.TestCase):
    def test_final_solid_must_match_frozen_interface_inside_roi(self):
        reference = cq.Workplane("XY").box(4, 4, 4)
        roi = cq.Workplane("XY").box(5, 5, 5)
        cosmetic = cq.Workplane("XY").box(2, 2, 2).translate((10, 0, 0))
        variant = cq.Compound.makeCompound([reference.val(), cosmetic.val()])
        result = assert_fit_regions({"cosmetic": variant}, {"mate": (reference, roi)})
        self.assertIn("mate", result["cosmetic"])
        invaded = reference.union(cq.Workplane("XY").box(2, 6, 2))
        with self.assertRaises(ProbeError):
            assert_fit_regions({"bad": invaded}, {"mate": (reference, roi)})


if __name__ == "__main__":
    unittest.main()
