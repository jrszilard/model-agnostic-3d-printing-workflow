# Working model

A page that shows a build working: every piece where it sits, each moving piece taken through its steps, the exact
distance between the pieces that must stay apart, and the build's own check lines. It is for looking, for telling
each other where something rubs ("CA at x 104"), and for seeing a change before it is printed.

Justin, 2026-11-11: *"a working dynamic ... model for complex builds to illustrate how all the pieces work together
and that will hopefully make testing and refining the parts improved ... an interactive tool that can be utilized for
future builds and parts"*. Then, 2026-11-12: *"yes start with the full road model"*.

```bash
~/cadquery-env/bin/python platform/pipeline/working-model/working_model.py parts/<category>/<part> <out.html>
```

The part says what its build is in `docs/working_model.py` (a `model()` function returning a `Scene`). The output is
one HTML file written for the Artifact tool: publish it, and republish the same file to keep its link.

## Writing a part's description

Start from one of:

- `parts/decor/touge-road-slider-coupon/docs/working_model.py`: a mechanism, two carriages passing (30 s to make);
- `parts/decor/touge-road/docs/working_model.py`: a whole build, 28 pieces from four generators, six controls, a
  latch that stops the road lifting, and the order it comes apart in (35 s, or 2 min with the road's own checks);
- the small lever-and-bolt scenes in `cadquery_test_working_model.py`.

| You give | What it is |
|---|---|
| `Piece(key, solid, name, code=, colour=, note=, layer=, see_through=, stand_in=, bought=)` | one solid, where it sits at the first step. `code` is the short name from the parts map. `layer` is how far it goes when the build is pulled apart: a number along the scene's `explode` axis, or `(x, y, z)`. |
| `Mover(key, label, pieces, poses, also=[(pieces, poses)], unit=, start=, on=, marks=)` | one control. `also` moves more pieces with the same control along their own paths (a sled dragged by a carriage). `on` names the control that carries this one (a bolt on a road that lifts). `marks` is what the readout says at each step ("locked", "2 mm out"). |
| `poses(place_at, count)` | the motion, read off the generator's own placement function at each step. |
| `poses_of(build_at, count)` | the motion, for a generator that builds the piece at each step instead of placing one: read off the two solids' corners, refused unless every corner lands. |
| `Gap(a, b, label, limit=, stops=)` | least distance for every arrangement of the controls that move either end or carry it. An end is a mover's key, `"fixed"`, or a list of piece keys. `stops=True`: the two cannot pass through each other. |
| `Scene(..., play=[(mover, step)], play_label=, back_label=)` | the order Play works the controls in (`-1` is a control's last step). |
| `bullets(readme, heading)` and `pick(lines, [(title, prefix)])` | the generator's printed check lines, as the part's README keeps them. A scene may also run the generator's checks and quote what they return. |

Rules:

1. **Solids and motion come from the generator.** Build with its functions and place with its placement functions;
   `poses()` and `poses_of()` read each step's motion off those. Nothing is drawn a second time for the page. Where a
   scene must place something itself (a whole guardrail the generator installs only as posts), it proves the placement
   against the generator's own solids with the kernel and raises if it is off.
2. **A stand-in is labelled and never measured.** A toy car, a wall or a hand may be a plain solid flagged
   `stand_in=True`. A bought part whose size the CAD already holds (a magnet, a battery box as measured) is a real
   piece, flagged `bought=True`.
3. **Give the steps the part has**: its clicks, its stops, several along a free travel. Between two steps the page
   moves a piece along the single screw motion that joins them, so a hinge given as closed and open swings about its
   pin, but a path that bends between two steps is not known to it.
4. **A gap of 0.00 is touching or overlapping.** A mover that rests on something fixed is 0 from `"fixed"`: name the
   pieces that must stay apart.
5. **A stop is a gap that starts apart.** With `stops=True` a control halts at the last step before the two would be
   touching, so give a step just short of where they meet. The export refuses a stop that already touches where the
   build starts, one no control can reach, and a `play` order that a stop would block (in either direction): the
   order a build comes apart in is checked against the kernel's distances.
6. **A model cannot bend plastic.** A snap tab or a click arm is drawn stiff and overlaps where the real one flexes.
   Say so in the scene's `note`; do not put a stop on it.
7. **The page approves nothing.** It quotes the build's checks; `verify`, the handoff and the print still decide.

## What the page does

- one slider per control; a control stops where a `stops` gap says two pieces would meet, and says what stopped it;
- Play: the scene's own order, one control at a time, then back the way each came (without `play`, every control
  runs its whole travel at once, every other one the opposite way, so two on one line pass);
- views from above, the front, underneath and one end, framed on the build as it stands; see-through for pieces
  flagged `see_through`;
- pull apart by `layer`, and a cut along the longer side;
- tap a piece: its code, its name, and the point's x, y, z in the CAD's own coordinates;
- each gap as the controls stand, with a line between the two nearest points, the least at any step, and the limit
  the build refuses under;
- a switch for each piece; bought parts and stand-ins labelled; light and dark, phone width.

## Tests

`test_working_model.py` (no kernel: the arithmetic, the refusals, and the page's own functions run under node: the
between-steps motion, where a carried piece stands, what a gap reads, where a control stops, each held to the export's)
and `cadquery_test_working_model.py` (the markers, the motion read off two solids, the meshes, the exact distances,
a control riding on another, a gap that stops). Planted faults, one at a time, each fail a test: twelve in the first
version (2026-11-11), thirty in what 2026-11-12 added (carried controls, the tables, stops, the motion read off two
solids, the page's own arithmetic).

The page was looked at in a headless browser at desktop and phone width (2026-11-12). Its controls were driven by
script there, not by hand.
