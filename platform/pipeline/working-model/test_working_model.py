"""The working model's arithmetic, its refusals, and the page's own between-steps motion (run under node).

No CAD kernel here: cadquery_test_working_model.py covers the markers, the meshes and the exact distances.
"""
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import working_model as w  # noqa: E402


def slide(x, y=0.0, z=0.0):
    return (1.0, 0.0, 0.0, x, 0.0, 1.0, 0.0, y, 0.0, 0.0, 1.0, z)


def turn_z(deg, pivot=(0.0, 0.0), lift=0.0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    px, py = pivot
    return (c, -s, 0.0, px - c * px + s * py, s, c, 0.0, py - s * px - c * py, 0.0, 0.0, 1.0, lift)


def close(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class Matrices(unittest.TestCase):
    def test_compose_inverse_apply(self):
        m = w.compose(turn_z(90, (20.0, 10.0)), slide(5.0))
        self.assertTrue(close(w.apply(m, (0.0, 0.0, 0.0)), w.apply(turn_z(90, (20.0, 10.0)), (5.0, 0.0, 0.0))))
        self.assertTrue(w.is_identity(w.compose(w.inverse(m), m), 1e-12))
        self.assertTrue(close(w.apply(turn_z(90, (20.0, 10.0)), (20.0, 10.0, 0.0)), (20.0, 10.0, 0.0)))   # its pivot stays

    def test_a_stretch_and_a_mirror_are_refused(self):
        w.require_rigid(turn_z(37.0, (3.0, 4.0), 2.0))
        with self.assertRaisesRegex(w.ModelError, "stretches"):
            w.require_rigid((2.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0))
        with self.assertRaisesRegex(w.ModelError, "mirrors"):
            w.require_rigid((1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, -1.0, 0))


def pair(a, b):
    """gap_table's `frames` for two ends, each a list (one entry per step) of its bodies' poses, on two controls."""
    return lambda at: (a[at[0]], b[at[1]])


class GapTable(unittest.TestCase):
    def test_two_sliders_on_one_line_are_measured_once_per_offset(self):
        steps = 21
        a = [(slide(2.0 * i),) for i in range(steps)]
        b = [(slide(2.0 * j),) for j in range(steps)]
        calls = []

        def measure(at):
            i, j = at
            calls.append(at)
            return abs(2.0 * i - 2.0 * j) + 1.0, (2.0 * i, 0.0, 0.0), (2.0 * j, 1.0, 0.0)

        t = w.gap_table([steps, steps], pair(a, b), measure)
        self.assertEqual(len(calls), 2 * steps - 1)                 # 41, not 441
        self.assertEqual((t["least"], t["kept"]), (1.0, [0, 1]))
        for i in range(steps):
            for j in range(steps):
                u = t["unique"][t["table"][i][j]]
                self.assertAlmostEqual(u["gap"], abs(2.0 * i - 2.0 * j) + 1.0)
                # the stored points, carried by B's frame at this step, are where this pair's nearest points are
                self.assertTrue(close(w.apply(b[j][0], u["pa"]), (2.0 * i, 0.0, 0.0), 1e-6))
                self.assertTrue(close(w.apply(b[j][0], u["pb"]), (2.0 * j, 1.0, 0.0), 1e-6))

    def test_a_turning_piece_against_what_is_fixed_is_measured_at_every_step(self):
        a = [(turn_z(5.0 * i, (20.0, 10.0)),) for i in range(13)]
        t = w.gap_table([13], lambda at: (a[at[0]], (w.IDENTITY,)),
                        lambda at: (30.0 - at[0], (at[0], 0.0, 0.0), (0.0, 0.0, 0.0)))
        self.assertEqual(len(t["unique"]), 13)
        self.assertEqual(t["table"], list(range(13)))               # one control: one level
        self.assertEqual(t["least"], 18.0)

    def test_a_mover_whose_groups_move_differently_is_not_one_rigid_thing(self):
        # A's second group slides twice as far as its first, so A changes shape with its step: sliding B by the same
        # amount as A's first group no longer gives the same arrangement.
        a = [(slide(2.0 * i), slide(4.0 * i)) for i in range(5)]
        b = [(slide(2.0 * j),) for j in range(5)]
        calls = []
        w.gap_table([5, 5], pair(a, b), lambda at: (calls.append(at) or 1.0, (0, 0, 0), (0, 0, 0)))
        self.assertEqual(len(calls), 25)
        rigid = [(slide(2.0 * i), slide(2.0 * i)) for i in range(5)]
        calls.clear()
        w.gap_table([5, 5], pair(rigid, b), lambda at: (calls.append(at) or 1.0, (0, 0, 0), (0, 0, 0)))
        self.assertEqual(len(calls), 9)

    def test_two_things_turning_about_one_pin_repeat_by_the_angle_between_them(self):
        # B turns about a pin; A rides 5 along B's own x, turned to its own step. What B sees of A depends only on the
        # angle between them, so nine arrangements serve all twenty-five pairs. (Turns and slides do not commute:
        # "as B sees it" taken the wrong way round would make every pair look new.)
        pin, steps = (20.0, 10.0), 5
        b = [(turn_z(15.0 * j, pin),) for j in range(steps)]
        a = [(w.compose(turn_z(15.0 * i, pin), slide(5.0)),) for i in range(steps)]
        calls = []

        def measure(at):
            i, j = at
            calls.append(at)
            return float(abs(i - j)), w.apply(a[i][0], (0.0, 0.0, 0.0)), w.apply(b[j][0], (1.0, 0.0, 0.0))

        t = w.gap_table([steps, steps], pair(a, b), measure)
        self.assertEqual(len(calls), 2 * steps - 1)
        for i in range(steps):
            for j in range(steps):
                u = t["unique"][t["table"][i][j]]
                self.assertTrue(close(w.apply(b[j][0], u["pa"]), w.apply(a[i][0], (0.0, 0.0, 0.0)), 2e-3))
                self.assertTrue(close(w.apply(b[j][0], u["pb"]), w.apply(b[j][0], (1.0, 0.0, 0.0)), 2e-3))

    def test_the_measured_end_changing_shape_is_a_new_arrangement_too(self):
        # B's second group stays put while its first slides with A: A sits the same as B's first group sees it at
        # every step, but B itself is a different shape each time.
        a = [(slide(2.0 * i),) for i in range(4)]
        b = [(slide(2.0 * j), w.IDENTITY) for j in range(4)]
        calls = []
        w.gap_table([4, 4], pair(a, b), lambda at: (calls.append(at) or 1.0, (0, 0, 0), (0, 0, 0)))
        self.assertEqual(len(calls), 16)

    def test_two_ends_on_one_control_are_measured_at_each_of_its_steps(self):
        a = [(slide(1.0 * i),) for i in range(6)]
        b = [(slide(3.0 * i),) for i in range(6)]
        calls = []
        t = w.gap_table([6], lambda at: (a[at[0]], b[at[0]]),
                        lambda at: (calls.append(at) or 10.0 - at[0], (0, 0, 0), (0, 0, 0)))
        self.assertEqual(calls, [(i,) for i in range(6)])
        self.assertEqual((t["table"], t["least"]), (list(range(6)), 5.0))

    def test_a_control_that_carries_both_ends_is_left_out(self):
        # a tray (4 steps, turning) carries a bar (3 steps) and a peg (5 steps): the gap answers to the bar and the peg
        # alone, so the tray drops out of the table and 3 x 5 arrangements are measured, not 4 x 3 x 5
        pin = (7.0, -3.0)
        tray = [turn_z(20.0 * k, pin) for k in range(4)]
        bar = [slide(1.0 * i) for i in range(3)]
        peg = [slide(0.0, 2.0 * j) for j in range(5)]
        calls = []

        def frames(at):
            k, i, j = at
            return (w.compose(tray[k], bar[i]),), (w.compose(tray[k], peg[j]),)

        def measure(at):
            calls.append(at)
            k, i, j = at
            point = w.apply(w.compose(tray[k], peg[j]), (1.0, 2.0, 3.0))
            return 10.0 + i - j, point, point

        t = w.gap_table([4, 3, 5], frames, measure)
        self.assertEqual((t["kept"], len(calls)), ([1, 2], 15))
        self.assertEqual([len(t["table"]), len(t["table"][0])], [3, 5])
        for i in range(3):
            for j in range(5):
                u = t["unique"][t["table"][i][j]]
                self.assertEqual(u["gap"], 10.0 + i - j)
                for k in range(4):                           # kept in the peg's frame: right wherever the tray stands
                    here = w.compose(tray[k], peg[j])
                    self.assertTrue(close(w.apply(here, u["pb"]), w.apply(here, (1.0, 2.0, 3.0)), 2e-3))

    def test_a_control_in_the_middle_that_does_not_matter_is_the_one_left_out(self):
        a = [slide(1.0 * i) for i in range(3)]
        b = [slide(0.0, 0.0, 2.0 * j) for j in range(4)]
        t = w.gap_table([3, 6, 4], lambda at: ((a[at[0]],), (b[at[2]],)),
                        lambda at: (1.0 + at[0] + 10.0 * at[2], (0, 0, 0), (0, 0, 0)))
        self.assertEqual(t["kept"], [0, 2])
        self.assertEqual(t["unique"][t["table"][2][3]]["gap"], 33.0)

    def test_two_fixed_things_are_one_number(self):
        t = w.gap_table([], lambda at: ((w.IDENTITY,), (w.IDENTITY,)), lambda at: (4.25, (0, 0, 0), (0, 4.25, 0)))
        self.assertEqual((t["table"], t["kept"], t["least"]), (0, [], 4.25))


class Carried(unittest.TestCase):
    """A control that rides on another: its pieces stand where the carrier puts them, moved on it."""
    PIN = (20.0, 10.0)

    def setUp(self):
        self.frames = {"tray": [(turn_z(30.0 * k, self.PIN),) for k in range(4)],
                       "bar": [(slide(2.0 * i), slide(0.0, 0.0, 1.0 * i)) for i in range(3)],
                       "pip": [(slide(0.0, 5.0 * j),) for j in range(2)]}
        self.carrier = {"tray": None, "bar": ("tray", 0), "pip": ("bar", 1)}

    def test_the_carriers_pose_comes_after_the_pieces_own(self):
        # the bar slides 4 along the tray's x, then the tray turns 90 degrees about its pin: a point at the pin ends
        # 4 along the turned tray's x (scene y). The other way round it would stay on the scene's x.
        at = {"tray": 3, "bar": 2, "pip": 0}
        got = w.apply(w.carried(self.frames, self.carrier, ("bar", 0), at), (self.PIN[0], self.PIN[1], 0.0))
        self.assertTrue(close(got, (self.PIN[0], self.PIN[1] + 4.0, 0.0), 1e-9), got)

    def test_three_deep(self):
        at = {"tray": 3, "bar": 2, "pip": 1}                 # the pip rides the bar's second group, which rose 2
        want = w.compose(turn_z(90.0, self.PIN), w.compose(slide(0.0, 0.0, 2.0), slide(0.0, 5.0)))
        self.assertTrue(close(w.carried(self.frames, self.carrier, ("pip", 0), at), want))
        self.assertEqual(w.chain(self.carrier, ("pip", 0)), ["pip", "bar", "tray"])
        self.assertEqual(w.chain(self.carrier, None), [])
        self.assertEqual(w.carried(self.frames, self.carrier, None, at), w.IDENTITY)


def stop_gaps():
    """A road that lifts (5 steps) with a bolt (3 steps: locked, half, open) under a plate: locked or half out, the
    bolt meets the plate from the second step of the lift. A second gap never stops anything."""
    lock = {"stops": True, "drivers": ["road", "bolt"], "label": "bolt under the plate",
            "table": [[0, 0, 1], [0, 0, 1], [2, 2, 1], [2, 2, 1], [2, 2, 1]],
            "unique": [{"gap": 0.4}, {"gap": 1.0}, {"gap": 0.0}]}
    ruler = {"stops": False, "drivers": ["road"], "label": "ruler", "table": [0, 1, 1, 1, 1],
             "unique": [{"gap": 3.0}, {"gap": 0.0}]}
    return [ruler, lock]


class Stops(unittest.TestCase):
    def test_a_control_stops_at_the_last_step_before_the_two_meet(self):
        gaps = stop_gaps()
        self.assertEqual(w.reach(gaps, "road", 0, 4, {"road": 0, "bolt": 0}), (1, gaps[1]))    # locked: it lifts one step
        self.assertEqual(w.reach(gaps, "road", 0, 4, {"road": 0, "bolt": 2}), (4, None))       # open: all the way
        self.assertEqual(w.reach(gaps, "road", 4, 0, {"road": 4, "bolt": 2}), (0, None))       # and back down
        self.assertEqual(w.reach(gaps, "road", 0, 1, {"road": 0, "bolt": 0}), (1, None))       # up to the stop is free

    def test_the_other_control_is_stopped_by_the_same_gap(self):
        gaps = stop_gaps()
        self.assertEqual(w.reach(gaps, "bolt", 2, 0, {"road": 3, "bolt": 2}), (2, gaps[1]))    # lifted: it cannot lock
        self.assertEqual(w.reach(gaps, "bolt", 2, 0, {"road": 1, "bolt": 2}), (0, None))       # seated: it can
        self.assertEqual(w.reach(gaps, "bolt", 0, 2, {"road": 1, "bolt": 0}), (2, None))

    def test_a_gap_that_does_not_stop_and_a_control_it_does_not_answer_to_change_nothing(self):
        gaps = stop_gaps()
        gaps[1]["stops"] = False
        self.assertEqual(w.reach(gaps, "road", 0, 4, {"road": 0, "bolt": 0}), (4, None))
        self.assertEqual(w.reach(stop_gaps(), "lamp", 0, 3, {"road": 3, "bolt": 0, "lamp": 0}), (3, None))


class Refusals(unittest.TestCase):
    def scene(self, **change):
        pieces = [w.Piece("base", None, "Base"), w.Piece("bar", None, "Bar", colour="a"),
                  w.Piece("bolt", None, "Bolt", colour="b")]
        movers = [w.Mover("M", "The bar", ["bar"], [w.IDENTITY, slide(1.0)],
                          also=[(["bolt"], [w.IDENTITY, slide(2.0)])])]
        given = dict(title="T", pieces=pieces, movers=movers, gaps=[w.Gap("M", "fixed", "bar to base", limit=0.5)])
        given.update(change)
        return w.Scene(**given)

    def test_a_sound_scene_names_who_moves_what(self):
        self.assertEqual(self.scene().validate(), {"bar": ("M", 0), "bolt": ("M", 1)})

    def test_each_broken_scene_is_refused_for_its_own_reason(self):
        two = [w.IDENTITY, slide(1.0)]
        cases = [
            ("distinct keys", dict(pieces=[w.Piece("a", None, "A"), w.Piece("a", None, "B")], movers=[], gaps=[])),
            ("at least one piece", dict(pieces=[], movers=[], gaps=[])),
            ("front must be", dict(front="north")),
            ("start_view must be", dict(start_view="sideways")),
            ("explode must be", dict(explode="w")),
            ("at least two poses", dict(movers=[w.Mover("M", "m", ["bar"], [w.IDENTITY])], gaps=[])),
            ("starts at a step it does not have", dict(movers=[w.Mover("M", "m", ["bar"], two, start=2)], gaps=[])),
            ("one pose per step", dict(movers=[w.Mover("M", "m", ["bar"], two, also=[(["bolt"], two + two)])],
                                       gaps=[])),
            ("not in the scene", dict(movers=[w.Mover("M", "m", ["lid"], two)], gaps=[])),
            ("moved by both", dict(movers=[w.Mover("M", "m", ["bar"], two), w.Mover("N", "n", ["bar"], two)],
                                   gaps=[])),
            ("moves nothing", dict(movers=[w.Mover("M", "m", [], two)], gaps=[])),
            ("none may be called 'fixed'", dict(movers=[w.Mover("fixed", "m", ["bar"], two)], gaps=[])),
            ("not a mover or 'fixed'", dict(gaps=[w.Gap("M", "N", "g")])),
            ("to itself", dict(gaps=[w.Gap("M", "M", "g")])),
            ("to itself", dict(gaps=[w.Gap(["bar", "base"], ["base"], "g")])),
            ("rides on 'N', which is not a mover", dict(movers=[w.Mover("M", "m", ["bar"], two, on="N")], gaps=[])),
            ("rides on group 1 of M", dict(movers=[w.Mover("M", "m", ["bar"], two),
                                                   w.Mover("N", "n", ["bolt"], two, on=("M", 1))], gaps=[])),
            ("rides on itself", dict(movers=[w.Mover("M", "m", ["bar"], two, on="N"),
                                             w.Mover("N", "n", ["bolt"], two, on="M")], gaps=[])),
            ("rides on itself", dict(movers=[w.Mover("M", "m", ["bar"], two, on="M")], gaps=[])),
            ("one mark per step", dict(movers=[w.Mover("M", "m", ["bar"], two, marks=["in"])], gaps=[])),
            ("layer must be a number or", dict(pieces=[w.Piece("bar", None, "Bar", layer=(1.0, 2.0))], movers=[],
                                               gaps=[])),
            ("play needs at least one move", dict(play=[])),
            ("which is not a mover and the step", dict(play=[("N", 1)])),
            ("to a step it does not have", dict(play=[("M", 2)])),
            ("needs play", dict(gaps=[w.Gap("M", "fixed", "g", stops=True)])),
        ]
        for reason, change in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(w.ModelError, reason):
                self.scene(**change).validate()

    def test_what_a_scene_may_say(self):
        two = [w.IDENTITY, slide(1.0)]
        scene = self.scene(movers=[w.Mover("M", "m", ["bar"], two, marks=["in", "out"]),
                                   w.Mover("N", "n", ["bolt"], two, on="M")],
                           gaps=[w.Gap(["bolt"], ["base", "bar"], "g", stops=True)], play=[("N", -1), ("M", 1)])
        self.assertEqual(scene.validate(), {"bar": ("M", 0), "bolt": ("N", 0)})
        self.assertEqual((scene.movers[1].on, scene.movers[0].marks), (("M", 0), ["in", "out"]))
        self.assertEqual(w.spread(2.0, "y"), [0.0, 2.0, 0.0])
        self.assertEqual(w.spread((1, -2, 0.5), "z"), [1.0, -2.0, 0.5])

    def test_an_unknown_colour_is_refused_when_the_piece_is_made(self):
        with self.assertRaisesRegex(w.ModelError, "colour must be one of"):
            w.Piece("p", None, "P", colour="red")
        with self.assertRaisesRegex(w.ModelError, "colour must be one of"):
            w.Mover("M", "m", ["p"], [w.IDENTITY, slide(1.0)], colour="red")


class ReadmeLines(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.readme = Path(self.dir.name) / "README.md"
        self.readme.write_text("# Part\n\n### What i5's generator checks\n\nRead off the solids:\n\n"
                               "- passing: 5.12 or more apart\n- going on: clears the plate\n\nRefused: one thing.\n\n"
                               "### Next\n\n- not this one\n")

    def tearDown(self):
        self.dir.cleanup()

    def test_the_list_under_a_heading(self):
        lines = w.bullets(self.readme, "What i5's generator checks")
        self.assertEqual(lines, ["passing: 5.12 or more apart", "going on: clears the plate"])
        self.assertEqual(w.pick(lines, [("Passing", "passing:")]), [("Passing", "Passing: 5.12 or more apart")])

    def test_a_stale_heading_or_prefix_is_loud(self):
        with self.assertRaisesRegex(w.ModelError, "no list under a heading"):
            w.bullets(self.readme, "What i6's generator checks")
        lines = w.bullets(self.readme, "generator checks")
        with self.assertRaisesRegex(w.ModelError, "0 lines start with"):
            w.pick(lines, [("Sealed", "sealed:")])
        with self.assertRaisesRegex(w.ModelError, "2 lines start with"):
            w.pick(lines + ["passing: again"], [("Passing", "passing:")])


class Page(unittest.TestCase):
    def test_the_data_goes_in_whole_and_cannot_close_its_own_script(self):
        model = {"title": "A <b> & </script><script>alert(1)</script>", "name": "T & <Model>", "pieces": []}
        html = w.page(model)
        self.assertIn("<title>T &amp; &lt;Model&gt;</title>", html)
        self.assertNotIn("__MODEL_JSON__", html)
        self.assertNotIn("__NAME__", html)
        start = html.index('<script type="application/json" id="model">') + len('<script type="application/json" id="model">')
        end = html.index("</script>", start)
        self.assertEqual(json.loads(html[start:end]), model)        # the first </script> after it is the block's own

    def test_the_page_keeps_the_artifact_contract(self):
        template = (HERE / "page.template.html").read_text()
        for needed in ('<meta name="claude:viewport-fit-sides" content="cover">',
                       "padding-left: max(16px, env(safe-area-inset-left, 0px))",
                       '@media (prefers-color-scheme: dark) { :root:not([data-theme="light"])',
                       ':root[data-theme="dark"]', "body { background: var(--bg)",
                       "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"):
            self.assertIn(needed, template)
        for banned in ("<!doctype", "<html", "<body", "alert(", "localStorage"):
            self.assertNotIn(banned, template.lower() if banned.startswith("<") else template)
        self.assertEqual(template.count("<script src="), 1)          # one library, from the allowed host


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class BetweenSteps(unittest.TestCase):
    """The page moves a piece between two given steps along the one screw motion that joins them. This runs the page's
    own function, cut out of the template, so a hinge given as 'closed' and 'open' swings about its pin."""

    @classmethod
    def setUpClass(cls):
        template = (HERE / "page.template.html").read_text()
        cls.source = template[template.index("// motion:begin"):template.index("// motion:end")]

    def between(self, a, b, t):
        script = self.source + "\nconsole.log(JSON.stringify(between(%s, %s, %r)));" % (json.dumps(list(a)),
                                                                                     json.dumps(list(b)), t)
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_a_slide(self):
        self.assertTrue(close(self.between(w.IDENTITY, slide(10.0, -4.0, 2.0), 0.3), slide(3.0, -1.2, 0.6)))

    def test_a_hinge_swings_about_its_own_pin(self):
        pin = (20.0, 10.0)
        self.assertTrue(close(self.between(w.IDENTITY, turn_z(90.0, pin), 0.5), turn_z(45.0, pin)))
        self.assertTrue(close(self.between(turn_z(30.0, pin), turn_z(80.0, pin), 0.2), turn_z(40.0, pin)))
        self.assertTrue(close(self.between(turn_z(80.0, pin), turn_z(30.0, pin), 0.5), turn_z(55.0, pin)))   # and back

    def test_a_turn_about_an_axis_that_is_not_upright(self):
        # 120 degrees about the (1, 1, 1) line through the origin carries x to y to z; a third of it is 40 degrees
        third = self.between(w.IDENTITY, (0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0), 1 / 3)
        n, c, s = 1 / math.sqrt(3), math.cos(math.radians(40)), math.sin(math.radians(40))
        v = (1 - c) / 3
        want = (c + v, v - n * s, v + n * s, 0, v + n * s, c + v, v - n * s, 0, v - n * s, v + n * s, c + v, 0)
        self.assertTrue(close(third, want))

    def test_a_screw_turns_and_rises_together(self):
        pin = (5.0, -3.0)
        self.assertTrue(close(self.between(w.IDENTITY, turn_z(60.0, pin, lift=6.0), 0.5), turn_z(30.0, pin, lift=3.0)))

    def test_half_a_turn_keeps_its_pin_and_goes_a_quarter(self):
        pin = (20.0, 10.0)
        m = self.between(w.IDENTITY, turn_z(180.0, pin), 0.5)
        self.assertTrue(close(w.apply(m, (pin[0], pin[1], 0.0)), (pin[0], pin[1], 0.0)))
        self.assertAlmostEqual(m[0] + m[5] + m[10], 1.0)             # a quarter turn's trace
        w.require_rigid(m)

    def test_the_ends_are_the_given_steps(self):
        a, b = turn_z(10.0, (1.0, 2.0)), turn_z(70.0, (1.0, 2.0), lift=4.0)
        self.assertTrue(close(self.between(a, b, 0.0), a))
        self.assertTrue(close(self.between(a, b, 1.0), b))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class PageArithmetic(unittest.TestCase):
    """The page works out for itself where a carried piece stands, what a gap reads and where a control stops. These run
    the page's own functions under node and hold them to the ones the export uses."""

    @classmethod
    def setUpClass(cls):
        template = (HERE / "page.template.html").read_text()
        cls.source = template[template.index("// motion:begin"):template.index("// motion:end")]

    def node(self, expression, **given):
        script = self.source + "\nvar G = %s;\nconsole.log(JSON.stringify(%s));" % (json.dumps(given), expression)
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_a_carried_piece_stands_where_the_export_says(self):
        pin = (20.0, 10.0)
        frames = {"tray": [(turn_z(30.0 * k, pin),) for k in range(4)],
                  "bar": [(slide(2.0 * i), slide(0.0, 0.0, 1.0 * i)) for i in range(3)],
                  "pip": [(slide(0.0, 5.0 * j),) for j in range(2)]}
        carrier = {"tray": None, "bar": ("tray", 0), "pip": ("bar", 1)}
        movers = {key: {"on": list(carrier[key]) if carrier[key] else None,
                        "groups": [{"poses": [list(step[n]) for step in steps]} for n in range(len(steps[0]))]}
                  for key, steps in frames.items()}
        at = {"tray": 3, "bar": 2, "pip": 1}
        for body in (("pip", 0), ("bar", 0), ("bar", 1), ("tray", 0), None):
            got = self.node("world(G.movers, G.body, function (k) { return G.at[k]; })", movers=movers,
                            body=list(body) if body else None, at=at)
            self.assertTrue(close(got, w.carried(frames, carrier, body, at)), body)

    def test_a_control_stops_where_the_export_says(self):
        gaps = stop_gaps()
        steps = {"road": 5, "bolt": 3, "lamp": 2}
        asked = [(key, start, to, {"road": road, "bolt": bolt, "lamp": 0})
                 for road in range(5) for bolt in range(3) for key in ("road", "bolt", "lamp")
                 for start in [{"road": road, "bolt": bolt, "lamp": 0}[key]] for to in range(steps[key]) if to != start]
        got = self.node("G.asked.map(function (q) { var r = reach(G.gaps, q[0], q[1], q[2], function (k) { return q[3][k]; });"
                        " return [r.step, r.by]; })", gaps=gaps, asked=asked)
        self.assertEqual(len(got), len(asked))
        stopped = 0
        for (key, start, to, at), (step, by) in zip(asked, got):
            want, gap = w.reach(gaps, key, start, to, at)
            self.assertEqual((step, by), (want, gaps.index(gap) if gap else -1), (key, start, to, at))
            stopped += gap is not None
        self.assertGreater(stopped, 10)                      # the cases really do meet the stop

    def test_a_gap_reads_the_same(self):
        gaps = stop_gaps()
        for road in range(5):
            for bolt in range(3):
                at = {"road": road, "bolt": bolt}
                got = self.node("[found(G.gaps[0], function (k) { return G.at[k]; }).gap,"
                                " found(G.gaps[1], function (k) { return G.at[k]; }).gap]", gaps=gaps, at=at)
                self.assertEqual(got, [w.found(gaps[0], at)["gap"], w.found(gaps[1], at)["gap"]])


if __name__ == "__main__":
    unittest.main()
