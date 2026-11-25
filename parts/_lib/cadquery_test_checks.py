import os
import sys
import unittest

import cadquery as cq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_fast
from checks import run

SIDE = 4.0


def shared_volume(body, x):
    """A check section as a generator writes one: module-level, the solid handed in."""
    return ["%.9f" % probe_fast.volume(body, cq.Solid.makeBox(SIDE, SIDE, SIDE, cq.Vector(x, -2.0, -2.0)))]


def threads():
    return len(os.listdir("/proc/self/task")) if os.path.isdir("/proc/self/task") else 0


class ChecksWithTheKernelTests(unittest.TestCase):
    def test_sections_on_a_solid_built_here_answer_as_they_do_in_this_process(self):
        """The failure this guards: sections forked after the kernel had started its thread pool hung for ever
        (touge road, 2026-11-11). Fresh workers are handed the solid and must answer, and answer the same."""
        body = (cq.Workplane("XY").box(120, 40, 5).faces(">Z").workplane().rarray(10, 10, 10, 3).hole(3.0)).val()
        body.tessellate(0.01)                                    # meshing is one of the things that starts the pool
        positions = [-50.0 + 9.0 * i for i in range(8)]
        expected = [shared_volume(body, x)[0] for x in positions]
        os.environ["CHECK_TIMEOUT"] = "120"
        try:
            got = run([("x %g" % x, shared_volume, (body, x)) for x in positions], jobs=4)
        finally:
            del os.environ["CHECK_TIMEOUT"]
        self.assertEqual(got, expected)
        self.assertGreater(len(set(got)), 1)                     # not eight copies of one number


if __name__ == "__main__":
    print("threads in this process after kernel work:", threads())
    unittest.main()
