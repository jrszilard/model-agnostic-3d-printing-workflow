"""LEARNED RULES — the bench's hard-won design rules, structured so they can fire.

WHY THIS IS NOT A PROSE LIST
----------------------------
Every rule here was already written down somewhere in the knowledge base, and every one of them
still got re-derived or re-broken at least once. That is the documented failure mode of
lessons-learned systems generally: NASA's own reviews find they go unapplied because the
knowledge is unstructured and voluminous, so nobody finds the right lesson at the moment they
need it. Structure plus delivery-at-the-point-of-decision is the fix, not more prose.

So each rule carries the field that actually prevents the mistake:

    naive_fix — WHAT YOU WOULD REACH FOR, AND WHY IT FAILS.

That field is the point. Reading this bench's decision log, every expensive lesson has the same
shape: an obvious instinct ("make the hooks grippier", "make the passage bigger", "more brim",
"the analysis says self-weight is fine"), a different quantity actually governing the outcome,
and a correct move that is not the obvious one. A rule that states only the correct move loses
the half that does the work, because the obvious instinct is what an agent or a tired human
reaches for by default.

    trigger      — the situation that should surface this rule
    governing    — the quantity that actually controls the outcome
    instead      — what to do
    enforcement  — "gated" (a machine check exists, named in `gate`) or "advisory"
    cost         — what learning it cost, so its weight is legible

Dependency-free: the verify gates import this under `freecadcmd`, which has no cadquery.

    rules_for("joinery")            -> every joinery rule
    rules_for(trigger="orientation") -> rules whose triggers match a situation
    RULES["LEVERAGE"].naive_fix     -> the trap, quotable at the point of decision
"""

SCOPES = ("joinery", "retention", "orientation", "structure", "measurement", "process", "method")
ENFORCEMENT = ("gated", "advisory")


class RuleError(Exception):
    pass


class Rule:
    __slots__ = ("id", "title", "scope", "trigger", "naive_fix", "governing", "instead",
                 "enforcement", "gate", "evidence", "cost")

    def __init__(self, id, title, scope, trigger, governing, instead, naive_fix="",
                 enforcement="advisory", gate=None, evidence=(), cost=""):
        if scope not in SCOPES:
            raise RuleError("%s: unknown scope %r" % (id, scope))
        if enforcement not in ENFORCEMENT:
            raise RuleError("%s: unknown enforcement %r" % (id, enforcement))
        if enforcement == "gated" and not gate:
            raise RuleError("%s: gated rules must name the check that enforces them" % id)
        if not trigger:
            raise RuleError("%s: a rule with no trigger can never be surfaced" % id)
        self.id, self.title, self.scope = id, title, scope
        self.trigger = tuple(trigger)
        self.naive_fix, self.governing, self.instead = naive_fix, governing, instead
        self.enforcement, self.gate = enforcement, gate
        self.evidence, self.cost = tuple(evidence), cost

    def __repr__(self):
        return "Rule(%s %s)" % (self.id, self.enforcement)

    def brief(self):
        """One line for a gate to print at the point of decision."""
        return "%s — %s (%s)" % (self.id, self.title, self.governing)


_R = [
    # ── JOINERY ────────────────────────────────────────────────────────────────────────────
    Rule("R1", "Captured retention is governed by FACE interference, not depth clearance",
         scope="joinery", trigger=("wave", "detent", "retention", "captured", "amplitude"),
         naive_fix="Compare the ridge amplitude against the joint's depth clearance and call it "
                   "compliant if it is smaller. Those are DIFFERENT SURFACE PAIRS: on the VD twin "
                   "dovetail the depth clearance is fin-crest-to-groove-roof slack, while the "
                   "flat faces carrying the wave train meet at a ZERO gap. Raising depth "
                   "clearance 0.20->0.25 changed nothing, which is the proof.",
         governing="ridge amplitude MINUS the nominal gap between the mating flat faces — but "
                   "see R1b: this sets the PER-STATION force, and station count multiplies it",
         instead="Compare against the qualified envelope, not against the depth clearance. "
                 "0.20 interference is qualified over 2 stations and jams over 8.",
         enforcement="gated", gate="joints.check_retention",
         evidence=("2026-07-25-vd-r4-station-count-not-amplitude.md",
                   "2026-07-24-vd-r3-face-interference.md"),
         cost="two coupon rounds jammed (VD R1 at 0.30, VD R3 at 0.20) before R4 showed the "
              "amplitude was never the variable"),

    Rule("R1b", "Station count probably governs a captured train, not amplitude — CONFOUNDED",
         scope="joinery", trigger=("wave", "train", "pitch", "detent", "insertion-force",
                                   "stations", "retention"),
         naive_fix="Reduce the ridge amplitude when a detented joint will not go together. That "
                   "trades away the grip you wanted and does not address the cause. VD R4 ran "
                   "the SAME amp 0.20 against the SAME zero face gap and it fit BEST — the only "
                   "change was 8 stations over 18mm becoming 2 over 3.6mm. The halved-amplitude "
                   "arm (0.10) LOST: it gave up grip for nothing.",
         governing="stations engaged simultaneously x per-station interference; with "
                   "pitch-matched trains every station cams at once, so force scales with N",
         instead="SHORTEN THE TRAIN — put two stations at the trailing end so they engage only "
                 "in the last few mm — or detune the two pitches so one station engages at a "
                 "time. Keep the amplitude that grips.",
         enforcement="gated", gate="joints.check_retention",
         evidence=("2026-07-25-vd-r4-infill-confound.md",
                   "2026-07-25-vd-r4-station-count-not-amplitude.md",
                   "2026-07-24-vd-r3-face-interference.md"),
         cost="two jammed rounds to find it — but the round that 'proved' it also changed INFILL "
              "100%->15% (a springier part deforms to let a tight mate pass), so the direction is "
              "right and the cause is NOT isolated. Held as probable, not proven."),

    Rule("R2", "Fits do NOT transfer across print orientations",
         scope="joinery", trigger=("orientation", "flip", "standing", "flat", "vertical"),
         naive_fix="Reuse a clearance that passed on a coupon after reorienting the part. "
                   "Standing walls print true plus elephant foot; flat-printed overhung flanks "
                   "sag UNDERSIZE; bed-face voids squish narrow at the mouth; horizontal bore "
                   "roofs sag. Same numbers, different orientation, different joint.",
         governing="the print orientation of each mating surface",
         instead="Any orientation change on a mating surface re-opens the coupon gate.",
         enforcement="gated", gate="joints.check_orientation",
         evidence=("2026-07-24-qualified-joint-registry.md",),
         cost="bitten twice — QV5->VC05 and VDF30->VOM. IX35 is PASS_PERFECT vertical and "
              "FAIL_UNREMOVABLE horizontal at identical numbers"),

    Rule("R3", "Fits do NOT transfer across materials or printers",
         scope="joinery", trigger=("material", "printer", "PCTG", "TPU", "nozzle", "layer"),
         naive_fix="Carry a PLA clearance into PCTG because 'both are rigid'. A sample is "
                   "(pattern x context); outside its context it is unproven, not merely riskier.",
         governing="the (printer, material, nozzle, layer height) the measure was proven on",
         instead="Re-coupon in the new context. `qualified_in()` returns nothing rather than "
                 "handing back the old numbers.",
         enforcement="gated", gate="joints.check_context",
         evidence=("2026-07-24-joint-registry-as-code.md",),
         cost="none yet — this rule is why"),

    Rule("R4", "Refer to qualified joints by SAMPLE NUMBER",
         scope="joinery", trigger=("joint", "clearance", "fit", "reuse"),
         naive_fix="Describe a joint in prose ('the double dovetail with the waves') and rebuild "
                   "the geometry from that description. It comes out different every time.",
         governing="whether the geometry is read from the registry or reconstructed",
         instead="Cite the sample number; import the sample; build with joint_builders.",
         enforcement="gated", gate="joint_check.evaluate_joints",
         evidence=("2026-07-24-qualified-joint-registry.md",),
         cost="the reason this whole registry exists"),

    Rule("R5", "Dovetail floors and sloped walls stay SMOOTH; teeth are transverse only",
         scope="joinery", trigger=("dovetail", "rib", "teeth", "friction", "retention"),
         naive_fix="Add longitudinal ribs along the dovetail to increase friction. They run "
                   "parallel to the slide, so they bind it, and they mark a mating face.",
         governing="whether a feature is parallel or transverse to the slide axis",
         instead="Transverse teeth on broad flat faces outside the dovetail (style A).",
         evidence=("2026-07-23-pcc2-longitudinal-rib-friction-doe.md",
                   "2026-07-23-pcc2-compression-shoulder-zip-teeth.md"),
         cost="caught in CAD and rejected before printing"),

    Rule("R6", "Flat-printed insert keys beat vertical pins under bending",
         scope="joinery", trigger=("insert", "peg", "dowel", "key", "bending", "layer"),
         naive_fix="Print a round pin vertically so it comes out truly round. It does — and its "
                   "layer planes end up perpendicular to the axis, so bending loads the layers "
                   "in tension, FDM's weakest direction.",
         governing="the angle between the layer planes and the tension plane of the load",
         instead="Print keys FLAT so extrusion runs the key's length. Taper the ends UNDER bore "
                 "size so end-face seam blobs never gate insertion; the oversize middle holds.",
         evidence=("2026-07-24-trikey-flat-printed-triangle-joint.md",),
         cost="PG51 was qualified, then superseded by TK10/TK12 on this reasoning"),

    Rule("R7", "Entry and mouth chamfers are free",
         scope="joinery", trigger=("entry", "insertion", "chamfer", "lead-in", "jam"),
         naive_fix="Open up the clearance when a part will not start. That loosens the whole fit "
                   "to solve a problem that lives only at the entry.",
         governing="geometry at the first millimetre of engagement, not the running clearance",
         instead="Add fin-top lead-ins and groove-mouth squish relief; they turned a no-go into a "
                 "near fit at identical nominals.",
         evidence=("2026-07-24-qualified-joint-registry.md",), cost="one coupon round"),

    Rule("R8", "Identifiers never on a mating surface, and CENTRED on their face",
         scope="joinery", trigger=("label", "deboss", "identifier", "marking"),
         naive_fix="Shrink the text until it fits, or tuck it near an edge. `legible_deboss` y is "
                   "the text CENTER, so edge-adjacent placement clips it — three coupons running.",
         governing="text center position, and whether the face is longer than the label",
         instead="Bed face of an external tab, centred, along the face's LONG edge. Use the LD6 "
                 "baseline (6mm bold / 1.0mm recess); a face too small for it needs its own "
                 "label coupon, not smaller text. Pass `x` — the default 0 is only the centre "
                 "for a part modelled symmetrically about the origin.",
         enforcement="gated", gate="deboss.legible_deboss",
         evidence=("2026-07-30-label-clipping-is-now-gated.md",
                   "2026-07-23-b2b-r5-legible-identifiers-and-independent-nut-stops.md"),
         cost="FIVE incidents. LD3 illegible; VC gauge IDs clipped; VD males clipped; tower rods "
              "clipped and Justin STOPPED THE PRINT; and the check then found a fifth on an RHG "
              "gauge already printed and tested. Prose did not stop it four times — the "
              "containment check in legible_deboss did."),

    # ── RETENTION (beyond joints) ──────────────────────────────────────────────────────────
    Rule("PERPENDICULAR-RETENTION", "Retain soft filament perpendicular, never through gates",
         scope="retention", trigger=("soft", "silicone", "filament", "rope", "strip", "channel"),
         naive_fix="Chase the passage clearance when a soft strip will not feed through. Four "
                   "iterations went 1.82 -> 1.92 -> 2.09 -> 2.28mm against a 1.65 strip and it "
                   "still would not pass: 'like pushing on rope.' No clearance value fixes "
                   "buckling, and a passage wider than the filament kills the channel's own grip.",
         governing="the assembly MOTION — a soft filament buckles when pushed lengthwise",
         instead="Engage perpendicular to the filament axis (press/snap). Start from the motion, "
                 "then size the interference. Pinch stations swept into the profile won.",
         evidence=("2026-07-22-perpendicular-retention-over-gates.md",),
         cost="four coupon iterations chasing the wrong variable"),

    # ── STRUCTURE / ORIENTATION ────────────────────────────────────────────────────────────
    Rule("PRINT-LOAD", "Rigidity in use is not rigidity during printing",
         scope="structure", trigger=("tall", "helix", "cantilever", "thin", "wobble", "spine"),
         naive_fix="Analyse self-weight in service, find sag of 0.01-0.03mm, and conclude no "
                   "support structure is needed. The print failed at 60% Z anyway.",
         governing="nozzle contact force on a growing cantilever — the lever arm grows with Z "
                   "and every layer lands on a moving target",
         instead="Model the PRINT load case separately. Tall free geometry gets a printed spine "
                 "anchored into the part; it is structure, not an accessory.",
         evidence=("2026-07-21-print-rigidity-is-not-use-rigidity.md",),
         cost="a 150mm corkscrew abandoned at 80%"),

    Rule("LAYER-PLANE-FEATURES", "Anchor discrete features into the layer plane",
         scope="structure", trigger=("small-feature", "clip", "lip", "hook", "wisp"),
         naive_fix="Point a small feature upward because that is the direction it works in. "
                   "Upward lips are vertical wisps of stacked layers — the weakest possible "
                   "orientation, and the first thing to fail on a shaking substrate.",
         governing="whether the feature's strength lives in-layer or across layers",
         instead="Horizontal hooks and bridge staples survive; vertical wisps do not.",
         evidence=("2026-07-21-print-rigidity-is-not-use-rigidity.md",),
         cost="rev-2 clamp lips failed everywhere, including where the substrate was fine"),

    Rule("FOOTPRINT-NOT-ADHESION", "A lost print on a small base is leverage, not weak adhesion",
         scope="orientation", trigger=("adhesion", "brim", "footprint", "tall", "detached"),
         naive_fix="Add brim and glue after a tall part comes off the bed. It kept SOME adhesion "
                   "— it did not simply fail to stick. Mass built above a small footprint plus "
                   "wide toolhead moves created a rocking moment that worked the contact loose. "
                   "More brim would not have fixed it.",
         governing="the moment applied to the bed contact, not the contact's bond strength",
         instead="Orient for a large flat footprint. Print orientation favours bed adhesion.",
         evidence=("2026-07-08-print-orientation-base-on-bed.md",),
         cost="a ~165mm, 160g, 5h28m elbow cancelled mid-print"),

    Rule("NO-HABIT-BRIM", "Do not add a brim by habit",
         scope="process", trigger=("brim", "plate", "slice"),
         naive_fix="Add a brim for safety. On broad flat parts it is needless edge cleanup, and a "
                   "brim added for one tall coupon left an elephant-foot skirt on every flat part "
                   "on the plate.",
         governing="footprint size and tippiness, not caution",
         instead="brim_type=no_brim / brim_width=0 by default. Add a brim only for evidenced risk: "
                 "small or tippy footprint, warping material, failed first layer.",
         evidence=("2026-07-23-pcc2-rail-extension-trapezoidal-lock.md",),
         cost="one plate of parts that were harder to clean"),

    # ── LEVERAGE / MEASUREMENT ─────────────────────────────────────────────────────────────
    Rule("LEVERAGE", "For a cantilevered mount add leverage, not grip",
         scope="structure", trigger=("mount", "cantilever", "hook", "peg", "rock", "pull-out"),
         naive_fix="Make the hooks longer or grippier when a loaded mount rocks off. Engagement "
                   "is CAPPED by the hole: a rectangular peg in a round hole is limited by its "
                   "rounded corner, not its width, and narrowing the arm to buy height costs "
                   "bending section and makes the flex worse.",
         governing="the moment couple from the top row to the lowest bearing point",
         instead="Add a second row a board-pitch away. Two rows took the couple 8.2 -> 33.6mm "
                 "(4.1x) and split load over 4 pegs. Extending DOWN beats moving the ring.",
         evidence=("2026-07-20-leverage-not-grip-for-cantilever-mounts.md",),
         cost="one full holder that rocked forward under load"),

    Rule("SPAN-MEASUREMENT", "Measure a repeating pitch over a SPAN, never a single gap",
         scope="measurement", trigger=("pitch", "spacing", "grid", "pegboard", "caliper"),
         naive_fix="Caliper one gap and use it. A single reading gave 24.63mm; a 6-hole span gave "
                   "126.44/5 = 25.288mm — a 1 inch board. The error was 3x the ENTIRE fit budget "
                   "(peg play is 0.216mm), so a four-peg part built to it could not have entered.",
         governing="per-feature error divided across n gaps, versus the total play budget",
         instead="Measure over as many gaps as the part spans, and divide.",
         enforcement="advisory",
         evidence=("2026-07-20-leverage-not-grip-for-cantilever-mounts.md",),
         cost="caught before printing, but would have scrapped a multi-peg part"),

    Rule("LEVER-SCALE", "A clearance qualified on a coupon is not qualified for a long lever",
         scope="measurement", trigger=("coupon", "lever", "long", "slack", "wobble", "scale"),
         naive_fix="Promote a coupon-snug clearance straight into production. QV5 was PASS_SNUG "
                   "on a short coupon and showed ~0.6mm of slack on the real 180mm upright — "
                   "pressed to one side, all the slack appears opposite.",
         governing="slack multiplied by the engagement-to-length ratio",
         instead="Gauge against a real printed part, OR declare what covers the lever — a "
                 "production-orientation coupon, or a geometry change made for this load case "
                 "(twin fins replaced the single dovetail precisely because of QV5). Note the "
                 "gate itself must not demand a real part when the mating geometry just changed "
                 "and printing IS the only way to make one.",
         enforcement="gated", gate="joints.check_lever_scale",
         evidence=("2026-07-24-qualified-joint-registry.md",),
         cost="a full production connector reprint"),

    # ── METHOD ─────────────────────────────────────────────────────────────────────────────
    Rule("ONE-VARIABLE", "One variable per coupon round, and always ship a control",
         scope="method", trigger=("coupon", "round", "bracket", "doe", "experiment"),
         naive_fix="Trim a plate to save print time by dropping the 'boring' plain part. VD R3 "
                   "shipped three pieces and ALL of them carried waves, so when both females "
                   "jammed the dovetail clearance could not be exonerated or convicted — the "
                   "round produced an unattributable failure.",
         governing="whether exactly one thing differs between the arms, and whether a control "
                   "exists to read them against",
         instead="Change one variable per arm and always include the unmodified control, even "
                 "when it looks like a wasted slot.",
         evidence=("2026-07-24-vd-r3-face-interference.md",
                   "2026-07-25-vd-r4-station-count-not-amplitude.md"),
         cost="R3 lost a round to an uninterpretable result. R4 was BUILT to hold one variable "
              "and still slipped a second one — infill 100%->15% — because infill was not in the "
              "schema and nobody was watching it. Writing the rule down did not enforce it; "
              "putting infill in the schema is what enforces it."),

    Rule("CONFOUNDED-PAIR", "Never gauge a new part against a part that was itself modified",
         scope="method", trigger=("coupon", "gauge", "reference", "filed", "sanded", "mating"),
         naive_fix="Test a new male against the female you already have on the bench. QV4 'fit "
                   "only after filing' — and the mating QVM had ALSO been filed, so the datum "
                   "described neither part. The ladder had to restart on fresh parts.",
         governing="whether the reference side is in its as-printed state",
         instead="Keep an unmodified reference. Reuse only parts that were never worked, and say "
                 "so in the log.",
         evidence=("2026-07-23-photo-scale-pcc2-double-dovetail.md",),
         cost="a restarted clearance ladder"),

    Rule("COUPON-FIRST", "Fit-critical or long? Coupon the mating ends before the full part",
         scope="method", trigger=("coupon", "fit-critical", "long", "expensive", "print-decision"),
         naive_fix="Print the whole part to find out whether the fit is right. A multi-hour print "
                   "is an expensive way to learn a 0.1mm mistake.",
         governing="cost of the print versus cost of a coupon that answers the same question",
         instead="Print just the fit-critical features first. Never risk a long print to learn a "
                 "fit is wrong.",
         evidence=("2026-07-23-fastener-evidence-gate.md",),
         cost="the standing discipline that keeps the rest cheap"),

    Rule("ASSEMBLY-FRAME", "Verify in the frame the part is USED in, not the one it is authored in",
         scope="method", trigger=("mirror", "flip", "rotate", "assembly", "mate", "graphics",
                                  "label", "orientation"),
         naive_fix="Open the part and check it looks right. It does — in the authored frame. If "
                   "the mating transform rotates or mirrors the piece, everything reads correctly "
                   "on screen and wrongly on the bench. The PCC2 upright's extension mates "
                   "channel-to-channel, so it is rotated 180deg in use: its checker rows, its "
                   "colour phase and its DIGITS all turn over — three separate corrections, each "
                   "invisible until the part was held against its mate.",
         governing="the composition of the authored geometry with the actual mating transform",
         instead="Run the ACTUAL built feature through the ACTUAL assembly transform and assert "
                 "on the result. The same discipline the dovetail trapezoid-flip gotcha already "
                 "demanded for fits — it generalises to graphics and text.",
         enforcement="gated", gate="pcc2e.assert_extension",
         evidence=("2026-07-25-extension-scales-and-the-assembly-frame.md",),
         cost="caught only when Justin photographed the assembled tool; then MISSED AGAIN on the "
              "imperial rail, because I reasoned about ONE transform (180deg) instead of asking "
              "which transforms reverse the width axis (+90deg does too). Cost a 21g reprint. "
              "Root fix was to derive the layout FROM the mating transform, not patch each case."),

    Rule("SCALE-CONTINUITY", "An extension continues ONE parent scale, at that scale's datum",
         scope="measurement", trigger=("extension", "scale", "ruler", "numeral", "continue",
                                       "chain", "datum"),
         naive_fix="Copy the parent's graphics onto the extension. The assembled ruler then reads "
                   "0..180 and restarts at 50 — useless for the one thing it exists to do. And "
                   "the PCC2 base is not even one ruler: +X is metric, +Y is IMPERIAL, the "
                   "upright is metric measured up from the floor. A generic metric extension is "
                   "wrong on two of the three.",
         governing="the parent's scale value at the MATING FACE, and that scale's units",
         instead="Give the extension the parent's offset and units; place value V at (V - offset) "
                 "FROM THE MATING FACE. No extra tick-start term — the datum is the parent's "
                 "mm=0 tick centre, and adding the extension's own tick start put every feature "
                 "0.45mm out.",
         evidence=("2026-07-25-extension-scales-and-the-assembly-frame.md",),
         cost="0.45mm baked into every measurement made through an extension — invisible in the "
              "print and silently wrong forever"),

    Rule("FAIL-CLOSED", "An unrecognised failure must BLOCK, not shrug",
         scope="process", trigger=("gate", "exit", "verify", "unknown", "slice"),
         naive_fix="Classify an unmapped error code as 'unknown' and let it through, on the "
                   "grounds that you cannot say what went wrong. verify-slice did exactly that: "
                   "its exit table held OrcaSlicer's negative codes, the bench moved to "
                   "PrusaSlicer (which returns a plain 1), and every PrusaSlicer failure since "
                   "PASSED the gate — over the STALE gcode left by the previous run.",
         governing="whether a gate's default branch is permissive or restrictive",
         instead="Only success passes. Naming an unknown code is a diagnostic nicety; letting it "
                 "through is a safety bug. Re-check tool-specific tables after any tool change.",
         enforcement="gated", gate="orca_exit.classify_exit",
         evidence=("2026-07-25-verify-slice-passed-failed-slices.md",),
         cost="open from the 2026-07-20 slicer migration until found by accident on 2026-07-25"),

    Rule("STALE-ARTIFACT", "A build artifact outlives the design it came from",
         scope="process", trigger=("plate", "build", "superseded", "gcode", "handoff", "stale"),
         naive_fix="Leave a superseded plate in build/ — it is only a file, and the source is "
                   "clearly marked. But a sliced plate keeps its handoff.txt and its PASS "
                   "verdict, so send.sh accepts it: the gate cannot tell that the DESIGN behind "
                   "it was retired. RL1 v3 sat sliced and sendable for two days after its rope "
                   "dimensions were superseded, and verify-slice separately passed a FAILED "
                   "slice over the previous run's leftover gcode.",
         governing="whether a stale output can still satisfy the gate that guards it",
         instead="Delete the plate when the design is superseded, and mark the source. Artifacts "
                 "are regenerable; a wrong plate that passes its own gate is not recoverable "
                 "once it is on the printer.",
         evidence=("2026-07-26-rl1-v3-stale-plate.md",
                   "2026-07-25-verify-slice-passed-failed-slices.md"),
         cost="none yet, twice — caught RL1 v3 before it printed (47.85g / 1h47m of the wrong "
              "rope size) and the stale gcode before it shipped"),
]

RULES = {}
for _r in _R:
    if _r.id in RULES:
        raise RuleError("duplicate rule id %r" % _r.id)
    RULES[_r.id] = _r
del _R, _r


def rules_for(scope=None, trigger=None, enforcement=None):
    """Rules matching any combination of scope, trigger keyword, and enforcement.

    `trigger` is matched case-insensitively against each rule's trigger keywords, so a gate can
    surface the relevant rules for the situation it is looking at instead of relying on someone
    having read the whole list.
    """
    out = []
    t = trigger.lower() if trigger else None
    for r in RULES.values():
        if scope and r.scope != scope:
            continue
        if enforcement and r.enforcement != enforcement:
            continue
        if t and not any(t in k.lower() or k.lower() in t for k in r.trigger):
            continue
        out.append(r)
    return tuple(sorted(out, key=lambda r: r.id))


def gated_rules():
    """Rules with a machine check behind them. The rest are advisory — say so honestly."""
    return rules_for(enforcement="gated")


def advisory_briefs(trigger):
    """One-line briefs to print at a decision point. Used by the verify gates."""
    return tuple(r.brief() for r in rules_for(trigger=trigger))
