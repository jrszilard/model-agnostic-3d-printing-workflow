"""The working model against the CAD kernel: the motion read off the generator's placement, the exact distances at
every step, and what is refused. Run by platform/pipeline/cadquery_suites.py (cadquery-env).
"""
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

import cadquery as cq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import working_model as w  # noqa: E402

PIN = (20.0, 10.0)                                       # the lever's pin, well off the origin


def box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def about_pin(deg):
    """A placement as a generator writes one: turn about the origin, then move, so the pin stays put."""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    shift = cq.Vector(PIN[0] - c * PIN[0] + s * PIN[1], PIN[1] - s * PIN[0] - c * PIN[1], 0.0)
    return lambda solid: solid.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), deg).translate(shift)


def slid(x):
    return lambda solid: solid.translate(cq.Vector(x, 0.0, 0.0))


def latch(steps=7, stand_in_near=False, bolt_first=0.0):
    """A lever on a pin that pushes a bolt toward a stop: 5 degrees and 1.5 mm a step. The bolt's face starts 12.0
    from the stop, so the gap is 12.0 - 1.5 * step."""
    pieces = [
        w.Piece("base", box(0, 60, -5, 30, -2, 0), "Base", code="B", see_through=True, layer=-1.0),
        w.Piece("stop", box(52, 56, 0, 8, 0, 6), "Stop", code="ST", colour="dark"),
        w.Piece("lever", box(18, 22, 8, 28, 0, 3), "Lever", code="L", colour="a", layer=1.0),
        w.Piece("bolt", slid(bolt_first)(box(30, 40, 2, 6, 0, 4)), "Bolt", code="BT", colour="b"),
    ]
    if stand_in_near:                                        # a coin lying against the stop: a stand-in, never measured
        pieces.append(w.Piece("coin", cq.Solid.makeCylinder(3.0, 1.0, cq.Vector(44.0, 4.0, 0.0)), "Coin",
                              colour="steel", stand_in=True))
    movers = [w.Mover("lever", "The lever", ["lever"], w.poses(lambda i: about_pin(5.0 * i), steps),
                      also=[(["bolt"] + (["coin"] if stand_in_near else []),
                             w.poses(lambda i: slid(bolt_first + 1.5 * i), steps))],
                      colour="a", unit="stop")]
    return w.Scene(title="Latch", name="Latch Model", pieces=pieces, movers=movers,
                   gaps=[w.Gap(["bolt"], ["stop"], "Bolt to the stop", limit=1.0)], front="-y")


def on_a_tray(steps=5, shifts=(0.0, 3.0, 6.0, 9.0)):
    """The latch on a tray that slides across (along y): the tray carries the lever and its bolt; the stop stays put."""
    scene = latch(steps)
    scene.pieces.append(w.Piece("tray", box(10, 45, 0, 30, -1, 0), "Tray", colour="light", layer=(0.0, 1.0, -0.5)))
    scene.movers[0].on = ("tray", 0)
    scene.movers.insert(0, w.Mover("tray", "The tray", ["tray"],
                                   w.poses(lambda k: lambda solid: solid.translate(cq.Vector(0.0, shifts[k], 0.0)),
                                           len(shifts)), colour="c", marks=["%g across" % v for v in shifts]))
    return scene


class Markers(unittest.TestCase):
    def test_the_motion_is_read_off_the_placement(self):
        place = lambda solid: solid.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 30).translate(cq.Vector(5, -2, 3))
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        got = w.placement(place)
        want = (c, -s, 0, 5, s, c, 0, -2, 0, 0, 1, 3)
        self.assertTrue(all(abs(a - b) < 1e-9 for a, b in zip(got, want)), got)

    def test_a_placement_that_mirrors_or_stretches_is_refused(self):
        with self.assertRaisesRegex(w.ModelError, "mirrors"):
            w.placement(lambda solid: solid.mirror("XY"))
        with self.assertRaisesRegex(w.ModelError, "stretches"):
            w.placement(lambda solid: solid.scale(2.0))

    def test_poses_are_each_step_from_the_first(self):
        steps = w.poses(lambda i: about_pin(30.0 + 10.0 * i), 4)
        self.assertEqual(steps[0], w.IDENTITY)
        for i, pose in enumerate(steps):                     # 10 degrees a step about the pin, whatever the first was
            self.assertTrue(all(abs(a - b) < 1e-9 for a, b in zip(w.apply(pose, (PIN[0], PIN[1], 0.0)),
                                                                  (PIN[0], PIN[1], 0.0))))
            self.assertAlmostEqual(pose[0], math.cos(math.radians(10.0 * i)), places=9)

    def test_a_slide_stays_a_slide_however_the_piece_was_first_turned(self):
        # placed a quarter turn round and then slid along x: each step is 2.0 along the SCENE's x, not the piece's
        place_at = lambda i: (lambda solid: solid.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 90)
                              .translate(cq.Vector(10.0 + 2.0 * i, 0.0, 0.0)))
        steps = w.poses(place_at, 4)
        for i, pose in enumerate(steps):
            self.assertTrue(all(abs(a - b) < 1e-9 for a, b in
                                zip(pose, (1, 0, 0, 2.0 * i, 0, 1, 0, 0, 0, 0, 1, 0))), pose)
        start = place_at(0)(box(0, 4, 0, 2, 0, 1))
        for i in (1, 3):                                       # the pose carries the first step's solid onto step i's
            moved, want = start.moved(w.location(steps[i])).Center(), place_at(i)(box(0, 4, 0, 2, 0, 1)).Center()
            self.assertAlmostEqual((moved - want).Length, 0.0, places=9)

    def test_a_location_moves_a_solid_as_the_matrix_moves_its_points(self):
        m = w.placement(about_pin(40.0))
        moved = box(0, 2, 0, 2, 0, 2).moved(w.location(m)).Center()
        want = w.apply(m, (1.0, 1.0, 1.0))
        self.assertTrue(all(abs(a - b) < 1e-9 for a, b in zip((moved.x, moved.y, moved.z), want)))


class ReadOffTheSolids(unittest.TestCase):
    """A generator that builds a piece at each step, instead of placing one: the motion is read off the two solids."""

    def keyed(self, x=0.0, wide=10.0, notch=36.0):
        return box(30 + x, 30 + x + wide, 2, 6, 0, 4).cut(cq.Solid.makeCylinder(1.0, 6.0, cq.Vector(33 + x, 4, -1))) \
            .cut(box(notch + x, notch + 2 + x, 1, 3, 2, 5))

    def test_a_piece_built_further_along_has_slid_that_far(self):
        steps = w.poses_of(lambda i: self.keyed(1.5 * i), 5)
        self.assertEqual(steps[0], w.IDENTITY)
        for i, pose in enumerate(steps):
            self.assertTrue(all(abs(a - b) < 1e-9 for a, b in zip(pose, (1, 0, 0, 1.5 * i, 0, 1, 0, 0, 0, 0, 1, 0))), pose)

    def test_a_piece_built_turned_about_a_pin_has_turned_about_it(self):
        want = w.poses(lambda i: about_pin(20.0 * i), 4)
        got = w.poses_of(lambda i: about_pin(20.0 * i)(self.keyed()), 4)
        for a, b in zip(got, want):
            self.assertTrue(all(abs(u - v) < 1e-9 for u, v in zip(a, b)), (a, b))
        tilted = lambda solid: solid.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 1, 1), 50).translate(cq.Vector(3, -7, 2))
        m = w.motion(self.keyed(), tilted(self.keyed()))
        self.assertTrue(all(abs(u - v) < 1e-9 for u, v in zip(m, w.placement(tilted))))

    def test_what_cannot_be_read_is_refused(self):
        with self.assertRaisesRegex(w.ModelError, "stretches"):
            w.motion(self.keyed(), self.keyed(2.0, wide=10.5))               # it grew as it went
        with self.assertRaisesRegex(w.ModelError, "not the first one moved: a corner lands 0.5000 off"):
            w.motion(self.keyed(), self.keyed(2.0, notch=36.5))              # its outside slid, its notch slid further
        with self.assertRaisesRegex(w.ModelError, "four or more"):
            w.motion(cq.Solid.makeCylinder(3.0, 5.0), cq.Solid.makeCylinder(3.0, 5.0, cq.Vector(4, 0, 0)))
        with self.assertRaisesRegex(w.ModelError, "mirrors"):
            w.motion(self.keyed(), self.keyed().mirror("XZ"))
        with self.assertRaisesRegex(w.ModelError, "corners"):
            w.motion(self.keyed(), box(0, 1, 0, 1, 0, 1))


class Export(unittest.TestCase):
    def test_the_gap_is_the_kernels_at_every_step(self):
        model = w.export(latch())
        gap = model["gaps"][0]
        self.assertEqual((gap["drivers"], gap["bBody"], gap["stops"]), (["lever"], None, False))   # who it answers to
        self.assertEqual(len(gap["unique"]), 7)              # the bolt is somewhere new at every step
        for step in range(7):
            found = gap["unique"][gap["table"][step]]
            self.assertAlmostEqual(found["gap"], 12.0 - 1.5 * step, places=3)
            self.assertAlmostEqual(found["pb"][0], 52.0, places=3)                    # on the stop's face
            self.assertAlmostEqual(found["pa"][0], 40.0 + 1.5 * step, places=3)       # on the bolt's, where it is now
        self.assertAlmostEqual(gap["least"], 3.0, places=3)
        self.assertEqual(gap["limit"], 1.0)

    def test_a_stand_in_is_drawn_and_never_measured(self):
        model = w.export(latch(stand_in_near=True))
        self.assertAlmostEqual(model["gaps"][0]["least"], 3.0, places=3)             # the coin is 5.0 from the stop
        coin = next(p for p in model["pieces"] if p["key"] == "coin")
        self.assertTrue(coin["standIn"])
        self.assertFalse(coin["bought"])
        self.assertIn("coin", model["movers"][0]["groups"][1]["pieces"])

    def test_the_page_data_is_whole(self):
        model = w.export(latch())
        json.dumps(model)
        mover = model["movers"][0]
        self.assertEqual((mover["steps"], mover["unit"], len(mover["groups"])), (7, "stop", 2))
        self.assertEqual([len(g["poses"]) for g in mover["groups"]], [7, 7])
        self.assertEqual(mover["groups"][1]["poses"][6][3], 9.0)                      # the bolt's last step: 9.0 along
        base = next(p for p in model["pieces"] if p["key"] == "base")
        self.assertEqual(len(w.base64.b64decode(base["stl"])), 84 + 12 * 50)          # a box: twelve triangles
        x0, y0, z0, x1, y1, z1 = model["bbox"]
        self.assertLessEqual(x0, 0.0)
        self.assertGreaterEqual(x1, 60.0)
        self.assertLess(y0, -5.0 + 1e-6)
        self.assertGreater(y1, 28.0 - 1e-6)                  # the lever swung is inside the box the page frames
        html = w.page(model)
        self.assertIn("<title>Latch Model</title>", html)

    def test_pieces_must_be_given_where_the_first_step_puts_them(self):
        scene = latch()
        scene.movers[0].groups[1] = (["bolt"], [w.compose((1, 0, 0, 1.0, 0, 1, 0, 0, 0, 0, 1, 0), p)
                                               for p in scene.movers[0].groups[1][1]])
        with self.assertRaisesRegex(w.ModelError, "first pose must be the identity"):
            w.export(scene)

    def test_a_mover_resting_on_what_is_fixed_is_nought_from_it(self):
        scene = latch()
        scene.gaps = [w.Gap("lever", "fixed", "Everything the lever moves, to everything fixed")]
        self.assertEqual(w.export(scene)["gaps"][0]["least"], 0.0)                   # the lever lies on the base

    def test_two_ends_one_control_moves_are_measured_against_each_other(self):
        scene = latch()
        scene.gaps = [w.Gap(["lever"], ["bolt"], "Lever to the bolt")]
        gap = w.export(scene)["gaps"][0]
        self.assertEqual((gap["drivers"], gap["bBody"]), (["lever"], ["lever", 1]))
        self.assertEqual(len(gap["unique"]), 7)              # one control: only the same step of both is ever seen
        for step in (0, 3, 6):
            lever = about_pin(5.0 * step)(box(18, 22, 8, 28, 0, 3))
            bolt = slid(1.5 * step)(box(30, 40, 2, 6, 0, 4))
            self.assertAlmostEqual(gap["unique"][gap["table"][step]]["gap"], lever.distance(bolt), places=3)
        self.assertAlmostEqual(gap["unique"][gap["table"][0]]["gap"], math.sqrt(8.0 ** 2 + 2.0 ** 2), places=3)

    def test_an_end_may_name_pieces_that_different_things_move(self):
        scene = latch()
        scene.gaps = [w.Gap(["lever"], ["stop", "bolt"], "Lever to the stop or the bolt, whichever is nearer")]
        gap = w.export(scene)["gaps"][0]
        self.assertEqual((gap["drivers"], gap["bBody"]), (["lever"], None))           # kept in the stop's frame: fixed
        for step in (0, 6):
            lever = about_pin(5.0 * step)(box(18, 22, 8, 28, 0, 3))
            near = min(lever.distance(slid(1.5 * step)(box(30, 40, 2, 6, 0, 4))), lever.distance(box(52, 56, 0, 8, 0, 6)))
            self.assertAlmostEqual(gap["unique"][gap["table"][step]]["gap"], near, places=3)

    def test_a_control_that_rides_on_another(self):
        shifts = (0.0, 3.0, 6.0, 9.0)
        scene = on_a_tray(shifts=shifts)
        scene.gaps.append(w.Gap(["lever"], ["bolt"], "Lever to the bolt"))
        scene.gaps.append(w.Gap(["stop"], ["base"], "Stop on the base"))
        model = w.export(scene)
        to_stop, to_bolt, still = model["gaps"]
        self.assertEqual((to_stop["drivers"], to_stop["bBody"]), (["tray", "lever"], None))
        for k, across in enumerate(shifts):
            for i in range(5):                               # the bolt: 1.5 a step toward the stop, carried across
                dy = max(0.0, 2.0 + across - 8.0)
                self.assertAlmostEqual(to_stop["unique"][to_stop["table"][k][i]]["gap"],
                                       math.hypot(12.0 - 1.5 * i, dy), places=3)
        self.assertEqual((to_bolt["drivers"], to_bolt["bBody"]), (["lever"], ["lever", 1]))   # the tray carries both
        self.assertEqual(len(to_bolt["unique"]), 5)
        self.assertEqual((still["drivers"], still["table"], still["unique"][0]["gap"]), ([], 0, 0.0))
        tray, lever = model["movers"]
        self.assertEqual((tray["on"], tray["marks"][1], lever["on"], lever["marks"]), (None, "3 across", ["tray", 0], None))
        self.assertGreaterEqual(model["bbox"][4], 28.0 + 9.0 - 1e-6)                  # the lever, carried right across
        layers = {p["key"]: p["layer"] for p in model["pieces"]}
        self.assertEqual((layers["tray"], layers["lever"], layers["stop"]), ([0.0, 1.0, -0.5], [0.0, 0.0, 1.0], [0.0, 0.0, 0.0]))

    def test_a_gap_that_stops(self):
        def scene(steps=10, play=(("lever", 7),), first=0.0):
            s = latch(steps, bolt_first=first)                # the bolt's face reaches the stop at step 8
            s.gaps = [w.Gap(["bolt"], ["stop"], "Bolt to the stop", stops=True)]
            s.play = [tuple(move) for move in play]
            return s

        model = w.export(scene())
        self.assertEqual((model["gaps"][0]["stops"], model["play"]), (True, [["lever", 7]]))
        at = {"lever": 0}
        self.assertEqual(w.reach(model["gaps"], "lever", 0, 9, at)[0], 7)             # 1.5 off at step 7, touching at 8
        with self.assertRaisesRegex(w.ModelError, "play: lever is stopped at step 7 on its way to step 9"):
            w.export(scene(play=(("lever", -1),)))
        with self.assertRaisesRegex(w.ModelError, "already touch where the build starts"):
            w.export(scene(first=12.0))
        still = scene()
        still.gaps = [w.Gap(["stop"], ["lever"], "g", stops=True)]
        still.movers[0].groups[0] = (["lever"], [w.IDENTITY] * 10)                   # a control that moves neither end
        still.pieces[2].solid = box(18, 22, 12, 28, 0, 3)
        with self.assertRaisesRegex(w.ModelError, "stops nothing"):
            w.export(still)

    def test_what_a_gap_may_not_name(self):
        cases = [("a stand-in", [w.Gap(["coin"], ["stop"], "g")]),
                 ("not in the scene", [w.Gap(["lid"], ["stop"], "g")]),
                 ("to itself", [w.Gap(["bolt"], ["bolt"], "g")]),
                 ("no pieces", [w.Gap([], ["stop"], "g")])]
        for reason, gaps in cases:
            scene = latch(stand_in_near=True)
            scene.gaps = gaps
            with self.subTest(reason=reason), self.assertRaisesRegex(w.ModelError, reason):
                w.export(scene)

    def test_a_gap_to_stand_ins_only_is_refused(self):
        scene = latch()
        scene.gaps = [w.Gap("lever", "fixed", "g")]
        for piece in scene.pieces:
            if piece.key in ("base", "stop"):
                piece.stand_in = True
        with self.assertRaisesRegex(w.ModelError, "no real piece"):
            w.export(scene)


class CommandLine(unittest.TestCase):
    def test_a_parts_description_becomes_a_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "part" / "docs"
            docs.mkdir(parents=True)
            (docs / "working_model.py").write_text(
                "import cadquery as cq\n"
                "from working_model import Scene, Piece, Mover, Gap, poses\n"
                "def model():\n"
                "    block = cq.Solid.makeBox(10, 10, 10)\n"
                "    slider = cq.Solid.makeBox(4, 4, 4, cq.Vector(20, 3, 0))\n"
                "    steps = poses(lambda i: lambda s: s.translate(cq.Vector(-2.0 * i, 0, 0)), 4)\n"
                "    return Scene(title='Two blocks', pieces=[Piece('block', block, 'Block'),\n"
                "                 Piece('slider', slider, 'Slider', colour='a')],\n"
                "                 movers=[Mover('S', 'The slider', ['slider'], steps)],\n"
                "                 gaps=[Gap('S', 'fixed', 'Slider to block', limit=1.0)])\n")
            out = Path(tmp) / "out" / "page.html"
            self.assertEqual(w.main(["working_model.py", str(Path(tmp) / "part"), str(out)]), 0)
            html = out.read_text()
            start = html.index('id="model">') + len('id="model">')
            model = json.loads(html[start:html.index("</script>", start)])
            self.assertEqual([u["gap"] for u in model["gaps"][0]["unique"]], [10.0, 8.0, 6.0, 4.0])

    def test_a_part_without_a_description_says_so(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(w.ModelError, "no docs/working_model.py"):
            w.load(tmp)


if __name__ == "__main__":
    unittest.main()
