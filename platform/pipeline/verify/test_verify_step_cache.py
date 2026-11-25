"""The two things a stdout diff cannot see about verify.py's STEP memo and probe prefilter.

verify.py itself cannot be imported here: it imports Part/Mesh/FreeCAD and runs main() at
module level (freecadcmd never sets __name__ to "__main__"). The geometry-only cache now lives in import-safe geometry.py. These tests lift the two
helpers out of both real sources by AST and exercise them against stubs. What that buys, and
what it does not:

  covered   the memo returns the SAME object for one path and DIFFERENT objects for two —
            parts/mounts/pegboard-canister-holder slices step/pegboard-arm.step AND
            step/pegboard-cup.step in one run, and one shared shape would measure the wrong
            solid; that every read site still goes through the memo, so a raw
            Part.Shape().read() cannot creep back in; that nothing in the file caches a
            triangulation on the now-shared shape; and that the prefilter drops only solids
            that cannot reach the region, falls back to the whole-shape boolean when the
            shape is not solids-only, and performs no boolean at all when nothing reaches.
  NOT       bit-exactness of OCCT's own numbers. Proving that needs FreeCAD and a real STEP:
            it was proven by hand instead (balloon-lamp, 10 probe volumes and observe()'s
            volume/bbox/counts/CenterOfMass repr-identical before and after, e.g.
            2.664000000000007 and 113909.59108974767), and a test that spawned freecadcmd
            would add seconds to the very suite this change exists to shrink. Re-run the
            hand proof after an OCCT/FreeCAD upgrade — that is when the drift could appear.
"""
import ast
import os
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY_PY = os.path.join(HERE, "verify.py")
with open(VERIFY_PY) as _stream:
    SOURCE = _stream.read()
with open(os.path.join(HERE, "geometry.py")) as _stream:
    GEOMETRY_SOURCE = _stream.read()
TREE = ast.parse(SOURCE + "\n" + GEOMETRY_SOURCE)

READ_SITES = ("_measure", "cad_integrity", "_probe_region_shape",
              "evaluate_spec_probes", "observe")

# Calls that attach a triangulation to a shape. Banned outright, because the memo made the
# five read sites share one object and FreeCAD takes BoundBox off the triangulation once one
# exists. Measured: one shp.tessellate(0.1) in cad_integrity moves parts/vent/k1c-elbow's
# reported STEP bbox from 149.887 x 174.887 to 139.993 x 165.000 and flips step_stl_agree
# from WARN to ok — the 9.887 mm divergence observe() exists to catch, switched off. Against
# a fresh read per site the same line changed nothing, so this is a hazard the memo created
# and only a static rule closes: no stdout diff can see it until someone adds the line.
TESSELLATORS = ("tessellate", "meshFromShape", "exportStl", "writeInventor")


def _lift(names, namespace):
    """Exec only the named top-level statements of the real verify.py into a namespace."""
    body = [node for node in TREE.body
            if getattr(node, "name", None) in names
            or (isinstance(node, ast.Assign)
                and any(getattr(target, "id", None) in names for target in node.targets))]
    exec(compile(ast.Module(body=body, type_ignores=[]), VERIFY_PY, "exec"), namespace)
    return namespace


def _function(name):
    return next(node for node in ast.walk(TREE)
                if isinstance(node, ast.FunctionDef) and node.name == name)


def _calls(node, name):
    """Every Call in `node` whose callee is `name` or `<something>.name`."""
    found = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Attribute) and func.attr == name:
            found.append(child)
        elif isinstance(func, ast.Name) and func.id == name:
            found.append(child)
    return found


class FakeBoundBox:
    """Only intersect() is used by the prefilter; inclusive, like FreeCAD's."""

    def __init__(self, lo, hi):
        self.lo, self.hi = lo, hi

    def intersect(self, other):
        return all(self.lo[i] <= other.hi[i] and other.lo[i] <= self.hi[i] for i in range(3))


class FakeSolid:
    ShapeType = "Solid"

    def __init__(self, name, lo, hi, volume=1.0):
        self.name, self.BoundBox, self.volume = name, FakeBoundBox(lo, hi), volume


class FakeResult:
    def __init__(self, volume):
        self.Volume = volume


class FakeShape:
    """A shape that records what was handed to common(), and returns a modelled volume."""

    def __init__(self, solids, shape_type="Compound", children=None):
        self._solids, self.ShapeType = list(solids), shape_type
        self._children = list(children) if children is not None else list(solids)
        self.commoned = []

    @property
    def Solids(self):
        return list(self._solids)

    def childShapes(self):
        return list(self._children)

    def common(self, region):
        self.commoned.append([s.name for s in self._solids])
        return FakeResult(sum(s.volume for s in self._solids))


class FakePart:
    """Part.Compound / Part.Shape, with a read counter."""

    def __init__(self):
        self.reads = []
        self.compounds = []

    def Compound(self, solids):
        self.compounds.append([s.name for s in solids])
        shape = FakeShape(solids)
        shape.parent = self
        return shape

    def Shape(self):
        return FakeReadShape(self)


class FakeReadShape:
    ShapeType = "Compound"

    def __init__(self, part):
        self._part = part
        self.path = None

    def read(self, path):
        self.path = path
        self._part.reads.append(path)


def _region(lo, hi):
    region = FakeShape([])
    region.BoundBox = FakeBoundBox(lo, hi)
    return region


class StepMemo(unittest.TestCase):
    def setUp(self):
        self.part = FakePart()
        self.ns = _lift({"_STEP_SHAPES", "_read_step"}, {"os": os, "Part": self.part})

    def test_one_path_is_read_once_and_returns_one_object(self):
        first = self.ns["_read_step"](VERIFY_PY)
        second = self.ns["_read_step"](VERIFY_PY)
        self.assertIs(first, second)
        self.assertEqual(self.part.reads, [VERIFY_PY])

    def test_two_paths_get_two_shapes(self):
        # pegboard-canister-holder slices step/pegboard-arm.step and step/pegboard-cup.step in
        # the same run. If these ever aliased, one of the two would be measured as the other.
        other = os.path.join(HERE, "spec_check.py")
        self.assertIsNot(self.ns["_read_step"](VERIFY_PY), self.ns["_read_step"](other))
        self.assertEqual(len(self.part.reads), 2)
        self.assertEqual(len(self.ns["_STEP_SHAPES"]), 2)

    def test_the_key_is_the_resolved_path(self):
        # spec.yaml paths are joined onto part_dir, so the same file arrives spelled several
        # ways; keying on the literal string would read it again for each spelling.
        spelled = os.path.join(HERE, "..", os.path.basename(HERE), os.path.basename(VERIFY_PY))
        self.assertIs(self.ns["_read_step"](VERIFY_PY), self.ns["_read_step"](spelled))
        self.assertEqual(self.part.reads, [VERIFY_PY])


class EveryReadGoesThroughTheMemo(unittest.TestCase):
    def test_only_read_step_constructs_and_reads_a_shape(self):
        reader = _function("_read_step")
        for call_name in ("Shape", "read"):
            sites = _calls(TREE, call_name)
            inside = _calls(reader, call_name)
            self.assertEqual(len(sites), 1, "%s() outside _read_step" % call_name)
            self.assertEqual(len(inside), 1, "_read_step no longer calls %s()" % call_name)

    def test_nothing_caches_a_triangulation_on_the_shared_shape(self):
        for name in TESSELLATORS:
            self.assertFalse(
                _calls(TREE, name),
                "%s() rewrites the memoised shape's BoundBox for every later site — read a "
                "private Part.Shape() if a mesh is really needed here" % name)

    def test_the_five_read_sites_still_call_it(self):
        for name in READ_SITES:
            self.assertTrue(_calls(_function(name), "_read_step"),
                            "%s no longer reads its STEP through the memo" % name)


class ProbePrefilter(unittest.TestCase):
    def setUp(self):
        self.part = FakePart()
        self.ns = _lift({"_occupied_volume"}, {"os": os, "Part": self.part})

    def test_only_solids_reaching_the_region_are_boolean(self):
        near = FakeSolid("near", (0, 0, 0), (10, 10, 10), volume=3.0)
        far = FakeSolid("far", (100, 100, 100), (110, 110, 110), volume=99.0)
        touching = FakeSolid("touching", (10, 0, 0), (20, 10, 10), volume=1.0)
        shape = FakeShape([near, far, touching])
        volume = self.ns["_occupied_volume"](shape, _region((1, 1, 1), (10, 5, 5)))
        self.assertEqual(self.part.compounds, [["near", "touching"]])
        self.assertEqual(volume, 4.0)
        self.assertEqual(shape.commoned, [])

    def test_nothing_reaching_costs_no_boolean(self):
        far = FakeSolid("far", (100, 100, 100), (110, 110, 110))
        shape = FakeShape([far])
        self.assertEqual(self.ns["_occupied_volume"](shape, _region((0, 0, 0), (1, 1, 1))), 0.0)
        self.assertEqual(self.part.compounds, [])
        self.assertEqual(shape.commoned, [])

    def test_a_lone_solid_needs_no_compound_check(self):
        solid = FakeSolid("only", (0, 0, 0), (10, 10, 10), volume=7.0)
        shape = FakeShape([solid], shape_type="Solid", children=[])
        self.assertEqual(self.ns["_occupied_volume"](shape, _region((1, 1, 1), (2, 2, 2))), 7.0)
        self.assertEqual(self.part.compounds, [["only"]])

    def test_a_shape_that_is_not_solids_alone_is_commoned_whole(self):
        # OCCT's volume properties do count a loose face, so dropping non-solid content would
        # change the number this gate reports. Anything but a compound of solids falls back.
        loose = FakeSolid("shell", (0, 0, 0), (10, 10, 10), volume=2.0)
        loose.ShapeType = "Shell"
        shape = FakeShape([FakeSolid("s", (0, 0, 0), (10, 10, 10), volume=2.0)], children=[loose])
        self.assertEqual(self.ns["_occupied_volume"](shape, _region((1, 1, 1), (2, 2, 2))), 2.0)
        self.assertEqual(shape.commoned, [["s"]])
        self.assertEqual(self.part.compounds, [])


if __name__ == "__main__":
    unittest.main()
