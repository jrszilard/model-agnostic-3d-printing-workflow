# Codegen templates — start from a proven idiom, not a blank CadQuery file

These are small, valid Python patterns for the failure modes this bench has already paid for. They
are not a second framework and do not replace the joint registry. Copy only the relevant function;
keep one geometry source and verify the real export.

## Start here

| Situation | Template | Why |
|---|---|---|
| New part generator | `cadquery-part.py` | self-locating export, spec-provenance gate, stage telemetry |
| Circles/cutters/unions/tangencies, pieces on a plate | `cadquery-safe-booleans.py` | avoids even-odd voids, coplanar kisses, quadratic cutter fuses and pieces that print fused |
| Boss/text after earlier features | `cadquery-stable-workplanes.py` | explicit datum planes; `faces(">Z")` drifts after the first boss |
| Plate → hook/gusset/section blend | `cadquery-clean-transition.py` | six-section smoothstep loft from the GPT-5.6 Sol solution; Terra's frozen mating-ROI check |
| Curved rim, tapered relief, text/M600 | `cadquery-surfaces-and-text.py` | periodic spline, same-profile relief, pinned fonts, layer-aligned colour plane |
| Shared fit across variants | `cadquery-fitcore.py` | semantic fingerprint plus final-solid ROI proof |
| Human placement decision | `annotations.example.yaml` | labels for `preview/plan-drawing.py` |
| Anything that clips, slides, hangs or flexes | `cadquery-mechanism-checks.py` | requirement lines, a cut that must bite, the way in, the fall, the rock, sections in their own processes |

## Traps encoded here

1. **Even-odd chaining:** overlapping circles in one wire/extrude produce a void. Build solids and
   union them explicitly.
2. **`faces(">Z")` drift:** after boss one, the topmost face is boss one. Boss two floats above the
   plate. Use `Workplane("XY").workplane(offset=KNOWN_Z)`.
3. **Tangent/coplanar union:** line/face contact is not volumetric. Overlap deliberately, or author
   one closed profile with no internal seam.
4. **Pile + final fillet is not a blend:** transition geometry carries load. Build width/depth change
   into an unruled multi-section loft; round it in isolation only if the next boolean and STL keep it.
5. **A clean-looking blend can still invade a mate:** compare final variant and frozen reference
   inside the exact same ROI. Geom id, solid count and input hash cannot see neighboring material.
6. **A constant cutter is not an offset from a taper:** derive outer and relief sections from the
   same profile function.
7. **Font fallback is a silent decision:** pin string × font × size and fail if absent.
8. **Colour change is a Z event:** relief boundary must be a layer-height multiple.
9. **A compound's solid count cannot see touching pieces:** `makeCompound` never merges, so
   `len(plate.Solids()) == len(pieces)` holds however the pieces overlap, and the slicer prints them
   as one (TR3S i4's tabs, rows closer than the tabs were wide). Check the plate with
   `assert_disjoint_plate` (`probe.assert_pieces_apart`): each piece one solid, each pair measured.

10. **A final-pose check passes a part that cannot get there, falls out, or rocks off.** Sweep it in along the
    hand's path (`motion.sweep`), let it fall (`motion.must_stop`: something must stop it, or only friction holds
    it), and roll it through its room (`motion.free_turn`). TM1's magnets jammed 1 mm short, TR8's box fell out
    upside down and TR11's shoe rolled its arm off a fin, each with every final-pose check green.
11. **A requirement nobody computed is a print spent finding it.** One `mech.require(label, value, at_most=...)`
    line per requirement, held to the requirement's own number: cover sag, root strain, push force against
    buckling, play times lever. Nine of twenty-six round trips in five weeks were this.
12. **A slow generator is slow in its checks.** Point tests through `probe_fast.inside`, volumes through
    `probe_fast.volume` or `volumes` (exact: one classifier a solid, local tiles, one boolean for probes that are
    apart), sections through `checks.run`. The touge road went from 790 s to 247 s with every line identical.
    Sections run in FRESH processes: forked after the kernel has started its threads, they hang for ever.
13. **A negative control in a scratch file is a control nobody can run again.** Keep them in the part's
    `qa/negatives.py` (`platform/pipeline/verify/negatives.py`): text mutations of the source, each in a fresh
    interpreter, side by side; a case whose text has gone is STALE, never skipped.

## The repair rule

When a generator fails — an OCC fillet that will not build, a boolean that produces nothing, a
loft that self-intersects — **look up the correct syntax and keep the intended geometric
complexity. Never simplify the geometry to make the error go away.**

This is the one prompt-level rule the 2026 literature states outright (Zero-to-CAD,
arXiv:2604.24479, which gives its agent exactly three tools: execute-and-validate, look-up-docs,
grep-docs) and it is also this bench's most expensive recorded failure mode. Dropping the fillet,
flattening the loft to a wedge, or replacing a transition with a stacked box makes the traceback
disappear and silently changes the part. The wiper adaptor lost a hook that way and still exported
a valid single solid — see trap 4 below, and `parts/_lib/probe.py`, which exists because a valid
BRep is not evidence the geometry survived.

If the shape genuinely cannot be built as specified, that is an escalation, not a simplification.

## Escalation

After two failed topology strategies, stop varying fillet radii. Save the exported mesh, failure
log, intended section and frozen mating ROI; ask an independent model to review a *different
invariant*. On the wiper adaptor, GPT-5.6 Sol solved Claude's repeated wedge/fillet dead end with a
six-section transition; GPT-5.6 Terra then found the old plate body still widened H94's proven grip.
Both contributions are represented in `cadquery-clean-transition.py`.
