"""THE QUALIFIED JOINT REGISTRY — authoritative, in code.

`docs/joinery.md` is the human-readable MIRROR of this file; when they disagree, THIS WINS
(`test_joints.py` fails the build if the doc drifts). Nothing in a generator may re-type a
qualified measure: import the sample and read it, so "add a double dovetail with the waves"
resolves to one lookup instead of a reconstruction from prose.

THE SCHEMA (why this is a schema and not a database)
----------------------------------------------------
Three normalized entities, because the KB's own rule — "do not generalize dimensions across
printers/materials without a coupon, but preserve the architecture and test method" — is a
statement about two different things that must not share a row:

    Material  ── the polymer's recorded behaviour (creep, friction, profile status)
    Context   ── (printer, material, nozzle, layer_h): the process a measure was proven on
    Pattern   ── the PORTABLE architecture + its rules + its measure schema. No numbers.
    Sample    ── a (Pattern x Context) qualification carrying the EXACT measures.

So TK10 is not "a triangle key". It is the triangle key qualified on Core One / Prusament PLA /
0.4 / 0.20mm. There is no TK10 in PCTG until a coupon produces one. `qualified_in()` returns
None for an unproven context instead of quietly handing back PLA numbers — that silent
substitution is the failure this module exists to prevent.

Measures are validated against `Pattern.measure_schema` at import: a sample missing a required
measure, or carrying an unknown one, raises immediately. That is the foreign-key/NOT-NULL
discipline of a database, enforced at load, with git as the audit log.

This module is DEPENDENCY-FREE on purpose. `platform/pipeline/verify/joint_check.py` imports it
under `freecadcmd`, which has no cadquery. Geometry builders live in `joint_builders.py`.

Usage:
    from _lib.joints import SAMPLES, stations, qualified_in, TRIANGLE_KEY, CORE_ONE_PLA
    tk = SAMPLES["TK12"]                       # semi-permanent triangle key
    tk.m["mid_w"]                              # 5.72 — never re-typed
    stations(3, pitch=14.0)                    # (-14.0, 0.0, 14.0) — 2 -> 3 is one integer
"""

# Material and Context live in `process.py` — they are the shared dimension of every qualified
# measure (joints, fasteners, markings), not a joint concept. Re-exported here so `from joints
# import CORE_ONE_PLA` keeps working and this module stays the single import for joint work.
from process import (CONTEXTS, CORE_ONE_PCTG, CORE_ONE_PETG, CORE_ONE_PETG_015, CORE_ONE_PLA,  # noqa: F401
                     CORE_ONE_TPU95A, CORE_ONE_TPU95A_010, Context, K1C_PLA, MATERIALS, Material, PCTG,
                     PETG, PLA, RegistryError, SUNLU_TPU_95A, TPU_95A, context_from, material_advisories)

# ─────────────────────────────────────────────────────────────────────────────
# PORTABLE HARD RULES — structured in `rules.py`, not restated here.
# This module used to carry them as a tuple of prose strings, which duplicated the knowledge
# base and then drifted from it (R1 was WRONG here for a full day after the VD R3 bench result).
# `rules.py` is the single source; these are the joinery-scoped subset, in id order.
# ─────────────────────────────────────────────────────────────────────────────
from rules import RULES as ALL_RULES, rules_for  # noqa: E402

JOINERY_RULES = rules_for(scope="joinery")
RULES = tuple(r.brief() for r in JOINERY_RULES)   # legacy: prose briefs for display


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN — the portable architecture. Carries rules and a measure SCHEMA, no numbers.
# ─────────────────────────────────────────────────────────────────────────────
class Pattern:
    __slots__ = ("id", "title", "captured", "measure_schema", "retention_styles", "rules", "doc",
                 "retention_location")

    def __init__(self, id, title, captured, measure_schema, retention_styles=(), rules=(), doc="",
                 retention_location=None):
        self.id, self.title = id, title
        self.captured = captured          # True = the mate cannot lift away from the joint faces
        self.measure_schema = measure_schema
        self.retention_styles, self.rules, self.doc = retention_styles, rules, doc
        # Where this pattern's teeth SIT when used as retention. "captured" = inside the joint's
        # own clearance envelope, so rule R1 binds. "shoulder" = on compression faces OUTSIDE the
        # dovetail, governed by shoulder preload instead. Conflating the two is what made an
        # amplitude qualified on an open lap joint get reused inside a captured one.
        self.retention_location = retention_location

    def __repr__(self):
        return "Pattern(%s)" % self.id


DOVETAIL = Pattern(
    "DOVETAIL", "Trapezoidal sliding-dovetail lock", captured=True,
    measure_schema=("width_clearance", "depth_clearance"),
    retention_styles=("none", "shoulder-ratchet", "tongue-ratchet", "waves"),
    rules=("Sloped walls stay smooth — teeth on flat faces only, transverse only (R5).",
           "Style A (compression-shoulder teeth) is the qualified retention; style B "
           "(teeth on the tongue) is for thin edge-on parts and remains coupon-gate.",
           "The trapezoid INVERTS under a 180 deg assembly flip: author the print foot "
           "wide-at-top so it is wide-at-bottom after the flip, and run the ACTUAL built foot "
           "through the assembly transform in the assert."),
    doc="A trapezoidal cross-section that slides along its length and, via the overhanging "
        "wider base, captures the mate against both perpendicular directions. The slide axis "
        "is the only free direction; hold along it comes SEPARATELY from transverse teeth.")

TRIANGLE_KEY = Pattern(
    "TRIANGLE_KEY", "Flat-printed triangle key + channel", captured=True,
    measure_schema=("mid_w", "tip_w", "key_len", "taper_len", "tight_zone", "apex_flat",
                    "edge_chamfer", "interference"),
    rules=("Print FLAT so extrusion lines run the key's length and bending tension lies along "
           "the strands (R6) — this is why it supersedes the vertical spiral dowel.",
           "Tips must sit UNDER the channel base width so end-face seam blobs never gate "
           "insertion; the oversize middle does the holding (barrel profile).",
           "Face-normal squish is 0.433x the width delta per side (equilateral geometry)."),
    doc="An equilateral key wedging into an apex-up channel. Self-wedging, anti-rotation, and "
        "the female prints better than a round bore: two 60 deg roofs, fully self-supporting.")

BAYONET_LOCK = Pattern(
    "BAYONET_LOCK", "Quarter-turn bayonet: lugged spigot into a slotted socket", captured=True,
    measure_schema=("spig_d", "bore_d", "spig_h", "socket_h", "lug_arc", "lug_r", "lug_h",
                    "lug_cham", "run_h", "seat_h", "turn_deg"),
    rules=("The mount feature is the SAME DIAMETER as the column it carries, so there is no step "
           "and no overhang — this is what lets a bayonet print support-free where a small "
           "central peg cannot.",
           "TRANSIT and LOCK are separate fits and get separate numbers. `run_h` is the running "
           "groove the lug slides along and sets how much it rattles on the way round; `seat_h` "
           "is the pocket it ends in and sets the grip. Tuning one does nothing for the other, "
           "and a joint reported as 'loose' may be loose in only one of them.",
           "The seat is a STEP the lug must climb, and PLA will not squeeze by a millimetre: a "
           "step of 0.80 or more simply never engages, and the lug stays in the running groove "
           "reading LOOSER than a shallower seat. Keep the step in tenths.",
           "A lug chamfered for printability becomes the locking WEDGE — the seat roof bears on "
           "it, so the chamfer is load-bearing geometry and cannot be changed as cosmetics.",
           "Clearance lives in the SPIGOT, never added again at the bore. Adding it twice gave "
           "0.95mm diametral and a column that rocked 4mm at its top."),
    doc="For a slender column into a base where a central key would be too small to carry a wire "
        "channel. Quarter turn, tool-free, and support-free in the print orientation.")

BANDED_TRIANGLE_KEY = Pattern(
    "BANDED_TRIANGLE_KEY", "Triangle key spanning several members, gripping only in bands",
    captured=True,
    measure_schema=("mid_w", "tip_w", "key_len", "band_len", "band_n", "band_pitch", "ramp_len",
                    "tight_zone", "apex_flat", "edge_chamfer", "interference"),
    rules=("TOTAL contact governs; DISTRIBUTION does not. RTG ran 12mm of contact as three bands "
           "and again as two, and BOTH needed pliers, while 9mm as three bands went in and out by "
           "hand. Place the bands wherever the members are and size them by the total.",
           "`tight_zone` is that total (band_len x band_n) and is the measure to carry between "
           "key lengths — TK10's qualified 10mm on a 22mm key transferred straight onto a 36mm "
           "one, which is R1b: engagement length governs, not interference.",
           "Tip width everywhere outside the bands, so friction tracks BAND length and not KEY "
           "length. Without that a long key grips its whole middle and needs pliers.",
           "Band length is CAPPED by the pitch, not chosen: band + 2 ramps + real relief <= "
           "pitch, or the bands merge and the key is silently a plain barrel again.",
           "Print FLAT, as with every TK (R6)."),
    doc="For one key tying three stacked members — a rod, a rim and a rod. The barrel key holds "
        "along its whole middle, which is right across one member and 2.4x too much across three.")

TRIANGLE_CHANNEL = Pattern(
    "TRIANGLE_CHANNEL", "Triangle-key female channel", captured=True,
    measure_schema=("base_w", "height", "depth", "skin", "section_t"),
    rules=("Apex UP: the two 60 deg roofs are self-supporting, so the channel needs no support.",
           "Skins above and below are context-critical — 1.575mm in an 8mm section is the "
           "qualified geometry; re-coupon at any other section thickness."),
    doc="The universal extension interface. Supersedes the PG51 round bores on all new parts.")

SHOULDER_RATCHET = Pattern(
    "SHOULDER_RATCHET", "Compression-shoulder zip teeth", captured=False,
    measure_schema=("pitch", "groove_w", "land", "depth", "phase"),
    rules=("Teeth go on broad flat compression shoulders OUTSIDE the dovetail opening, never on "
           "its floor or sloped walls (R5).",
           "Opposing patterns offset by half pitch with mirrored ramps — zip-tie engagement.",
           "Requires the part to HAVE shoulders: thick, or a perpendicular join whose "
           "overlapping body supplies them."),
    doc="Retention isolated onto replaceable/testable texture so the precision sliding faces "
        "stay smooth and predictable.",
    retention_location="shoulder")

WAVE_TRAIN = Pattern(
    "WAVE_TRAIN", "Protruded wave ridges + aligned divots", captured=False,
    measure_schema=("amp", "width", "pitch", "face_gap", "stations"),
    rules=("RULE R1 LIVES HERE. Inside a captured joint what matters is amp MINUS face_gap (the "
           "nominal gap between the mating flat faces the train runs on), not amp versus the "
           "joint's depth clearance. A train on faces that meet at zero gap is 100% interfering.",
           "RULE R1b: pitch-matched trains on both pieces cam simultaneously; force scales with "
           "the station count. Detune the pitches to engage one at a time.",
           "The female half must RECESS (divots) — its back face prints on the bed and "
           "protrusions cannot print there.",
           "Rounded profile, not a sharp sawtooth, so it cams over under assembly force."),
    doc="Continuous ridges into pitch-matched divots — flush when mated, clicking at every "
        "intermediate station. Beat the single large snap detent on grip (FX round 3).",
    retention_location="captured")

SPIRAL_DOWEL = Pattern(
    "SPIRAL_DOWEL", "Spiral-grooved round dowel peg", captured=True,
    measure_schema=("peg_d", "bore_d", "interference", "length", "groove_r", "groove_depth",
                    "groove_pitch", "groove_span", "starts", "chamfer"),
    rules=("Print VERTICALLY on a modeled twist-off pad foot so the cross-section is truly "
           "round (XY-defined, no layer-line flats).",
           "Slice SOLID (100% infill) — sparse-infill cores snap.",
           "Layer planes end up perpendicular to the peg axis, so bending loads the layers in "
           "tension: FDM's weakest direction. This is why TRIANGLE_KEY supersedes it (R6).",
           "The helical grooves are the escape path that lets an over-size pin press into the "
           "bore — the woodworking spiral-dowel trick."),
    doc="Retained for v1-compatible parts with existing round bores (PCC2ER). Not for new work.")

TWIN_DOVETAIL = Pattern(
    "TWIN_DOVETAIL", "Twin flared fins at symmetric stations", captured=True,
    measure_schema=("neck", "crest", "proud", "fin_len", "width_clearance", "depth_clearance",
                    "overhang_deg"),
    rules=("Two fins resist the roll a single feature cannot, and double the shear area.",
           "26.6 deg flank overhang from vertical prints flat, support-free.",
           "Male fins on the piece that prints STANDING; female grooves in the mating bed face "
           "— and note R2: that split is exactly what re-opened the coupon gate (VDF30->VOM)."),
    doc="The v2 corner<->upright vertical joint, superseding the single VC05 dovetail.")

MARKING = Pattern(
    "MARKING", "Debossed bed-face part identifier", captured=False,
    measure_schema=("size", "effective_depth", "weight"),
    rules=("RULE R8: never on a mating surface. Bed face of an external tab only.",
           "CENTRED on the face, along its LONG edge — `legible_deboss` y is the text CENTER, "
           "and edge-adjacent placement clipped three coupons running.",
           "Cut the label from a PLAIN primitive BEFORE fusing into a complex solid; compound "
           "text cutters on swept solids silently no-op.",
           "Start the cutter 0.2mm OUTSIDE the face — a boundary coplanar with the face no-ops.",
           "Mirror in XZ so the text reads correctly when the part is flipped forward."),
    doc="The physical marker tying a printed part to its file structure: the same variant key "
        "the generator's VARIANTS dict and the STL filename use. A pile of prints is "
        "identifiable at a glance, and any print traces back to its exact source. Legibility is "
        "a QUALIFIED PHYSICAL MEASURE, not a style choice — it has coupon evidence.")

ROPE_HOLE = Pattern(
    "ROPE_HOLE", "Rope pass-through in a rim section", captured=False,
    measure_schema=("hole_d", "section_t", "rope_nom", "min_wall"),
    rules=("Bore it HORIZONTALLY through the production section thickness so the as-printed fit "
           "includes bridge sag at the bore top — a hole gauged any other way flatters itself.",
           "Size to the ROPE YOU HAVE, not its nominal: natural sisal sold as 8mm measured "
           "7.8-8.4 along one coil, and the hole has to pass the fat spots.",
           "Chamfer both faces: threading ease plus fibre-abrasion relief."),
    doc="The lattice's rope passes through rim holes and the bottle rests on the strands, so this "
        "is a pass-through, not a grip — the fit criterion is 'threads without fighting or "
        "shredding fibres', not tightness.")

CLEAT = Pattern(
    "CLEAT", "Mast cleat for a rope tie-off", captured=False,
    measure_schema=("gap", "bar_d", "bar_len"),
    rules=("The post behind the bar is the capstan; the gap is what the rope passes through.",
           "The bar's lower tip floats until the stem reaches it — carry a breakaway pillar from "
           "the BED and snip it after printing.",
           "Vertical figure-8 over two horns, finishing with a locking tuck."),
    doc="User-serviceable tension: slack the lacing, swap the bottle, re-tension by hand.")

T_SLOT = Pattern(
    "T_SLOT", "Face-down T-slot for a slide-in line strip", captured=True,
    measure_schema=("line_w", "gap", "lip", "channel_w", "channel_h"),
    rules=("Print FACE-DOWN: the mouth on the sheet, the hidden channel over the lips under a "
           "bridged roof, so nothing overhangs.",
           "The hidden channel carries the grip; only the visible gap (line_w + 2 gap) shows. "
           "Ladder the room over the strip's flange, not the mouth.",
           "A strip on a changing curve has to bend on the way in: TPU 95A does. A stiff PLA strip "
           "needs ~0.6 of room a side on a curve, and then the line shows a wide gap (TR3 i5/i6)."),
    doc="The touge road's line slots: a mouth line_w + 2 gap wide through `lip` of road, over a "
        "hidden channel channel_w x channel_h that the strip's flange slides along.")

T_STRIP = Pattern(
    "T_STRIP", "Slide-in T line strip", captured=True,
    measure_schema=("line_w", "flange_w", "flange_t", "height", "foot_chamfer"),
    rules=("Print flange-down and solid; the stem's top is the line you see, flush with the road.",
           "The room over the flange, under the slot's lips, sets the grip: 0.8 loose, 0.7 a little "
           "loose, 0.6 snug, 0.4 too tight (TPU 95A, TR3S i7-i9).",
           "Feed it in from one end of the slot."),
    doc="The line itself: a stem line_w wide on a flange the slot's lips trap; `height` sits it "
        "flush on the slot's floor.")

PUSH_TAB = Pattern(
    "PUSH_TAB", "Flush strip on push tabs with crush ribs", captured=True,
    measure_schema=("strip_w", "strip_t", "groove_clear", "tab_w", "tab_l", "tab_d", "body_clear",
                    "rib_past_sliced", "rib_past_drawn", "rib_base", "slack", "pitch_max", "end_margin"),
    rules=("The strip does not grip: it seats on the groove's floor, groove_clear a side, so its face is "
           "flush with the host's and cannot sit proud or sink. Only the tabs' ribs touch.",
           "Quote a rib by what it is AS SLICED, read back from the G-code: a drawn crest is a sharp "
           "triangle a 0.45 line cannot reach into (0.14 drawn prints 0.05).",
           "The tab is narrower than the groove by more than its widest rib, or the rib crushes the "
           "groove's visible edge on the way down.",
           "body_clear is per material and per socket direction: 0.12 a side slides free in PLA in a "
           "sideways socket and binds in PETG in a blind vertical one (tr6-i1).",
           "Slack along the strip at each socket end, so a whole line's tabs need not land exactly on "
           "their sockets: two prints shrink differently over 240."),
    doc="A line, a motto or a trim strip pressed into a face from above: a thin strip in a shallow groove, "
        "with short tabs behind it in their own blind sockets, one crush rib on each long face of a tab.")

RIBBED_SOCKET = Pattern(
    "RIBBED_SOCKET", "Post in a blind socket with crush ribs", captured=True,
    measure_schema=("peg_d", "body_clear", "ribs", "rib_past_sliced", "rib_past_drawn", "rib_base",
                    "rib_sink", "rib_start", "rib_ramp"),
    rules=("The part is unchanged; the ribs are on the socket's walls, so a plain socket can be "
           "tightened without reprinting what goes in it.",
           "No rib for rib_start under the mouth, then up to full over rib_ramp: the part starts by hand.",
           "Size each rib against the part AS PRINTED: a face built by layers ends at the last layer "
           "whose mid-height is inside the model (a 1.6 post lying down is 1.55 tall at 0.15 layers).",
           "Several posts that go in together need the lower rung: two prints can put an end post a "
           "little off over the span."),
    doc="A post, pole or peg pushed into a blind vertical socket and held by crush ribs on the socket's "
        "walls, its body clear of them.")

SNAP_TAB_HOLDER = Pattern(
    "SNAP_TAB_HOLDER", "Box held by two click tabs under its ends", captured=True,
    measure_schema=("tab_w", "tab_l", "tab_t_root", "tab_t_tip", "root_r_in", "root_r_out", "lip",
                    "preload", "tab_clear", "side_rib_past_sliced", "body_clear"),
    rules=("A hanging part is held by a catch under a face that points down, never by friction "
           "(crush ribs alone: 'none will hold upside down', tr8-i1).",
           "Size the tab by the peak strain at its ROOT, where it bends across the layers, from the "
           "travel its lip needs every time: 1.70 % took a set, 1.09 % went a little loose, about "
           "0.6 % held (PETG). The beam's nominal strain hides the root's.",
           "Levers in order: a shorter lip, a taper, a big round on the compression side, then preload "
           "the catch so a small set does not show. Stops behind the tabs did nothing (tr8-i4).",
           "The tabs' roots pull and press on what they stand on: keep sockets and thin floors out "
           "from under them."),
    doc="A bought box (a battery pack) clicked in between two tabs that reach under its ends, crush "
        "ribs on the side legs to stop rattle. Model: decor/touge-road-pack-coupon docs/tab_strain.py.")

PATTERNS = {p.id: p for p in (DOVETAIL, TRIANGLE_KEY, TRIANGLE_CHANNEL, SHOULDER_RATCHET,
                              WAVE_TRAIN, SPIRAL_DOWEL, TWIN_DOVETAIL, MARKING,
                              ROPE_HOLE, CLEAT, T_SLOT, T_STRIP, PUSH_TAB, RIBBED_SOCKET,
                              SNAP_TAB_HOLDER)}


# ─────────────────────────────────────────────────────────────────────────────
# SAMPLE — a (Pattern x Context) qualification. `id` is the number debossed on the coupon.
# ─────────────────────────────────────────────────────────────────────────────
STATUSES = ("qualified", "coupon-gate", "reference", "superseded", "rejected")


class _Unknown:
    """Sentinel: this measure EXISTS for the pattern but was never recorded.

    Distinct from omitting the key, which means "not applicable to this sample". QH4 and the QV
    ladder have no depth clearance in the log — the coupons had one, nobody wrote it down. Saying
    so explicitly is the difference between a known gap and a silent one, and it lets the schema
    keep requiring the field instead of being weakened to accommodate missing data.
    """
    __slots__ = ()

    def __repr__(self):
        return "UNKNOWN"

    def __bool__(self):
        return False


UNKNOWN = _Unknown()

# How strongly a sample is proven — borrowed from aerospace allowables practice (MMPDS/CMH-17),
# where a value is never quoted without its statistical basis. Ours is far cruder than A-/B-basis
# because n is 1-2, and saying that plainly is the point: `status` says whether we CHOSE it,
# `basis` says how much evidence stands behind it. They are different questions and were
# previously conflated.
BASES = (
    "single-coupon",     # one printed pair, one insertion — most of this registry
    "bracketed",         # selected from a ladder that straddles the fit line
    "cycled",            # survived a declared number of insert/remove cycles
    "in-service",        # proven on a real part doing its real job
    "derived",           # computed, never physically tested
    "unproven",          # declared, not yet gated
)

# How a sample behaves in the hand — the thing you actually select on.
BEHAVIOURS = ("pass-perfect", "tight-hand-removable", "tight-pliers", "snug", "loose",
              "too-tight", "unknown")


class Sample:
    __slots__ = ("id", "pattern", "context", "status", "measures", "behaviour", "use_when",
                 "orientation", "evidence", "supersedes", "superseded_by", "notes",
                 "basis", "cycles", "mates_with", "infill", "nozzle_temp")

    def __init__(self, id, pattern, context, status, measures, behaviour, use_when="",
                 orientation="flat", evidence=(), supersedes=(), superseded_by=None, notes="",
                 basis=None, cycles=None, mates_with=(), infill=None, nozzle_temp=None):
        if status not in STATUSES:
            raise RegistryError("%s: unknown status %r" % (id, status))
        if behaviour not in BEHAVIOURS:
            raise RegistryError("%s: unknown behaviour %r" % (id, behaviour))
        basis = basis or ("unproven" if status in ("coupon-gate",) else "single-coupon")
        if basis not in BASES:
            raise RegistryError("%s: unknown basis %r" % (id, basis))
        if basis == "cycled" and not cycles:
            raise RegistryError("%s: basis 'cycled' must state how many cycles" % id)
        required = set(pattern.measure_schema)
        given = set(measures)
        if status in ("qualified", "coupon-gate", "reference"):
            missing = required - given
            if missing:
                raise RegistryError("%s: missing measures %s for pattern %s — use UNKNOWN if the "
                                    "coupon had one but it was never recorded"
                                    % (id, sorted(missing), pattern.id))
        unknown = given - required
        if unknown:
            raise RegistryError("%s: measures %s not in the %s schema"
                                % (id, sorted(unknown), pattern.id))
        if status == "qualified":
            blank = sorted(k for k, v in measures.items() if v is UNKNOWN)
            if blank:
                raise RegistryError("%s: cannot be 'qualified' with unrecorded measures %s"
                                    % (id, blank))
        self.id, self.pattern, self.context, self.status = id, pattern, context, status
        self.measures, self.behaviour, self.use_when = measures, behaviour, use_when
        self.orientation, self.evidence = orientation, evidence
        self.supersedes, self.superseded_by, self.notes = supersedes, superseded_by, notes
        self.basis, self.cycles, self.mates_with = basis, cycles, tuple(mates_with)
        # Sparse-infill density (%) the COUPON was printed at. PER-SAMPLE, not in Context,
        # because it is a per-object slicer setting: a joint's male and female routinely differ
        # (TK10 keys were qualified at 100% against TF channels printed at 15%). None = not
        # recorded. Added 2026-07-25 after infill changed silently across three VD rounds.
        self.infill = infill
        # Nozzle temperature (C) the COUPON was printed at. PER-SAMPLE for the same reason infill
        # is: it is a slicer setting, not a property of the machine, and `Context` is only
        # (printer, material, nozzle, layer_h) — so a temperature change is INVISIBLE to R3 and to
        # every context check in this module. Added 2026-08-05, when the hotend was repaired and
        # PLA moved 225 -> 230: every fit in the rope tower (TFH/TFV/TFB/TK10/RK3) was qualified at
        # 225, and 5C of extra melt widens extrusions and shrinks holes slightly — in the
        # tightening direction, on ladders whose rungs are 0.03mm apart. Exactly the shape of the
        # infill confound, caught this time BEFORE the parts were printed rather than after.
        self.nozzle_temp = nozzle_temp

    @property
    def m(self):
        """Shorthand for measures — `SAMPLES['TK12'].m['mid_w']`."""
        return self.measures

    @property
    def usable(self):
        return self.status in ("qualified", "coupon-gate")

    def __repr__(self):
        return "Sample(%s %s %s)" % (self.id, self.pattern.id, self.status)


_S = []   # built in registry order, keyed below

# ── TRIANGLE KEYS (TK) — flat-printed, the current default extension interface ──────────────
# R3 landed the fine bracket: R1 +0.00 loose, R2 +0.15 extreme, R3 brackets between.
_TK_COMMON = dict(tip_w=5.30, key_len=22.0, taper_len=6.0, tight_zone=10.0,
                  apex_flat=0.6, edge_chamfer=0.5)
_TK_EV = ("2026-07-24-trikey-flat-printed-triangle-joint.md",
          "2026-07-24-qualified-joint-registry.md")

_S += [
    Sample("TK10", TRIANGLE_KEY, CORE_ONE_PLA, "qualified",
           dict(_TK_COMMON, mid_w=5.70, interference=0.10),
           behaviour="tight-hand-removable",
           use_when="THE DEFAULT. Serviceable / disassemblable joints.",
           orientation="flat", evidence=_TK_EV, basis="bracketed", mates_with=("TF",),
           notes="2 transverse bed dimples. Transverse cluster distinguishes the R3 family "
                 "from R2's lengthwise dimple row."),
    Sample("TK12", TRIANGLE_KEY, CORE_ONE_PLA, "qualified",
           dict(_TK_COMMON, mid_w=5.72, interference=0.12),
           behaviour="tight-pliers", use_when="Semi-permanent joints.",
           orientation="flat", evidence=_TK_EV, basis="bracketed", mates_with=("TF",),
           notes="3 transverse bed dimples."),
    Sample("TK05", TRIANGLE_KEY, CORE_ONE_PLA, "reference",
           dict(_TK_COMMON, mid_w=5.65, interference=0.05),
           behaviour="loose", use_when="Loose-end boundary of the R3 bracket. Not selected.",
           orientation="flat", evidence=_TK_EV, notes="1 transverse dot."),
    Sample("TK15", TRIANGLE_KEY, CORE_ONE_PLA, "reference",
           dict(_TK_COMMON, mid_w=5.75, interference=0.15),
           behaviour="too-tight",
           use_when="TIGHT-END BOUNDARY REFERENCE — keep, do not ship.",
           orientation="flat", evidence=_TK_EV,
           notes="R2 best performer but EXTREMELY tight; motivated the R3 bracket below it."),
    Sample("TK00", TRIANGLE_KEY, CORE_ONE_PLA, "superseded",
           dict(_TK_COMMON, mid_w=5.60, interference=0.00),
           behaviour="loose", use_when="", orientation="flat", evidence=_TK_EV,
           superseded_by="TK10", notes="R1: the only key that entered at all."),
]
# R2 tight ladder + slotted spring family — all lost, kept so they are never re-proposed.
for _k, _d in (("TK30", 0.30), ("TK45", 0.45), ("TK60", 0.60)):
    _S.append(Sample(_k, TRIANGLE_KEY, CORE_ONE_PLA, "rejected",
                     dict(_TK_COMMON, mid_w=5.60 + _d, interference=_d),
                     behaviour="too-tight", orientation="flat", evidence=_TK_EV,
                     superseded_by="TK10",
                     notes="R1/R2 ladder: gated by end-face seam blobs, never entered."))
for _k, _d in (("TS45", 0.45), ("TS70", 0.70)):
    _S.append(Sample(_k, TRIANGLE_KEY, CORE_ONE_PLA, "rejected",
                     dict(_TK_COMMON, mid_w=5.60 + _d, interference=_d),
                     behaviour="too-tight", orientation="flat", evidence=_TK_EV,
                     superseded_by="TK10",
                     notes="Apex-slotted spring key (1.0mm slot, 62% depth). The slotted family "
                           "lost to solid at R2."))
for _k, _h in (("TR20", 0.20), ("TR30", 0.30)):
    _S.append(Sample(_k, TRIANGLE_KEY, CORE_ONE_PLA, "coupon-gate",
                     dict(_TK_COMMON, mid_w=5.60, interference=_h),
                     behaviour="unknown",
                     use_when="Ribbed alternate: line-to-line body + raised face beads. Wider "
                              "forgiveness band than the rigid ladder if it proves out.",
                     orientation="flat", evidence=_TK_EV,
                     notes="Bead radius %.2f on both sloped faces, capsule span 5.0-17.0mm. "
                           "Crest carries all interference and crushes compliantly." % _h))

# ── SUB-NOMINAL keys for a VERTICAL channel in a thick surround ──────────────────────────────
# 2026-07-30 physical: in the rope tower's Ø14 posts, EVERY key of the TK00..TK12 ladder was hard
# to push in — including TK00 at line-to-line. So the channel prints UNDERSIZE here, which is the
# OPPOSITE of what was predicted: a vertical channel has no roof to sag, so it was expected to
# come out closer to nominal and therefore looser. The mechanism is corner-fill — a 0.4 nozzle
# cannot form the triangle's sharp internal corners, so a vertical channel loses area, while a
# horizontal one is OPENED by bridging sag. Orientation moves the fit in both directions and the
# sign is not guessable (rule R2, now with a worked example).
#
# The knob stays on the disposable part: these go below line-to-line rather than opening the
# channel in an expensive base, and they measure the as-printed shortfall directly.
#
# SUPERSEDED 2026-07-31 by TFV/TFH — see below. TKN10 did win its ladder, but winning it exposed
# that the QUESTION was wrong: no key in the rope tower lives in one orientation (the 22mm base
# key is half in a vertical socket and half in a horizontal rod end; 24 of the 36mm rim key's
# length is in rod ends), so no single male width can be right and a sub-nominal key just moves
# which half is wrong. The compensation belongs on the FEMALES, which ARE orientation-pure.
_TKN_EV = ("2026-07-30-vertical-channel-prints-undersize.md",
           "2026-07-31-compensate-the-female-not-the-key.md")
for _k, _d, _b in (("TKN05", -0.05, "loose"), ("TKN10", -0.10, "tight-hand-removable"),
                   ("TKN15", -0.15, "loose")):
    _S.append(Sample(_k, TRIANGLE_KEY, CORE_ONE_PLA, "superseded",
                     dict(_TK_COMMON, mid_w=round(5.60 + _d, 2), interference=_d),
                     behaviour=_b, orientation="flat", evidence=_TKN_EV, basis="bracketed",
                     mates_with=("TF",), superseded_by="TK10",
                     use_when="",
                     notes="Sub-nominal by %.2f. Read 2026-07-30 in a Ø14 vertical post channel: "
                           "TKN10 tight-hand-removable, TKN15 loose. Kept as the record of a "
                           "ladder that was WON and still abandoned — a second key width in the "
                           "drawer at 5.50 against TK10's 5.70, both marked with two dots and "
                           "differing only in dot DIRECTION, was a standing mis-pick waiting to "
                           "happen. Do not re-propose sub-nominal males for an orientation "
                           "problem; open the female instead." % abs(_d)))

# ── RK — the 36mm rim key, gripping in bands ────────────────────────────────────────────────
# RTG gate 2, read 2026-08-01. One key ties rod(0-12) | rim(12-24) | rod(24-36) at every rim
# corner, 16 of them in the tower. Stretching TK10 to 36mm gives 24mm of contact — 2.4x its
# qualified engagement at the same interference — so the arms varied TOTAL CONTACT and, at one
# value, its DISTRIBUTION:
#
#     RKF  24mm, one continuous zone      pliers
#     RK6  18mm, three 6mm bands          pliers
#     RK4  12mm, three 4mm bands          pliers   )  same contact,
#     RK2  12mm, two 6mm bands, no rim    pliers   )  different spread, SAME RESULT
#     RK3   9mm, three 3mm bands          in and out by hand, and the stack is SOLID   <-- SELECTED
#
# Two findings. Distribution is irrelevant — 12mm jammed whether spread over three members or
# two — so only the total matters and the bands go wherever the members are. And the threshold
# brackets TK10's qualified 10mm tight zone, so an engagement length qualified on a 22mm key
# transferred onto a 36mm one: R1b again, engagement governs rather than interference.
# ── BAYONET — the LED column's mount, qualified over three rounds ───────────────────────────
# R1 felt loose because its seat roof sat at 3.90 against a 3.20 lug: not weak grip, NO CONTACT.
# R2 stepped the seat 0.80-1.20 below the running groove, which solid PLA cannot climb, so those
# arms never engaged and read LOOSER than the shallow one — the inversion that showed the seat is
# a step the lug must climb rather than a squeeze it can absorb. R3 tightened the running groove
# (the actual complaint: "loose until it turns all the way and fully locks") and bracketed the
# seat narrowly around the depth that already worked.
#
# Justin, R3: "hard to tell, but TLRG seems the best, TLRF also works." Across seats 2.90/2.80/2.70
# the interference spans 0.86..1.92 mm3 — indistinguishable by hand, which is the finding worth
# keeping: THE JOINT IS INSENSITIVE ACROSS A 0.20mm BAND. A fit that does not care where in that
# band it lands survives print-to-print variation, so the round ends here rather than laddering
# finer. TLRG takes the deep end for margin against a socket printing slightly oversize.
_BAY_EV = ("2026-08-11-bayonet-transit-and-lock-are-two-fits.md",)
_S.append(Sample(
    "TLRG", BAYONET_LOCK, CORE_ONE_PLA, "qualified",
    dict(spig_d=15.40, bore_d=15.70, spig_h=11.0, socket_h=10.8, lug_arc=34.0, lug_r=1.9,
         lug_h=3.20, lug_cham=1.60, run_h=3.30, seat_h=2.70, turn_deg=62.0),
    behaviour="tight-hand-removable",
    use_when="THE LED COLUMN MOUNT. A slender column into a base, where a central key would be "
             "too small to carry a wire channel.",
    orientation="vertical", evidence=_BAY_EV, basis="bracketed", infill=15, nozzle_temp=230,
    notes="Seat 2.70 of a 2.90..2.70 working window; 2.40 does not engage. Running groove 3.30 "
          "for 0.10 of transit slop. Bore carries NO extra clearance — it is all in the spigot. "
          "A 0.20 detent bump was tested alongside (TLRH) and neither helped nor hurt, so it is "
          "left out: one less feature to print."))
for _k, _seat, _st, _b, _n in (
        ("TLRE", 2.90, "reference", 0.0, "Light end of the R3 bracket. Works; not selected."),
        ("TLRF", 2.80, "reference", 0.0, "Middle of the R3 bracket, and R2's TLRA depth. Works."),
        ("TLRH", 2.80, "rejected", 0.20, "TLRF plus a 0.20 detent bump. Indistinguishable from "
                                         "TLRF, so the bump is geometry that earns nothing."),
        ("TLRB", 2.40, "rejected", 0.0, "R2: an 0.80 step down from the running groove. The lug "
                                        "NEVER ENTERED — it stayed in the groove and read looser "
                                        "than a shallower seat. The bound on how far a lug climbs."),
        ("TLRC", 2.00, "rejected", 0.0, "R2: a 1.20 step. Same failure as TLRB, further past it.")):
    _S.append(Sample(_k, BAYONET_LOCK, CORE_ONE_PLA, _st,
                     dict(spig_d=15.40, bore_d=15.70, spig_h=11.0, socket_h=10.8, lug_arc=34.0,
                          lug_r=1.9, lug_h=3.20, lug_cham=1.60, run_h=3.30, seat_h=_seat,
                          turn_deg=62.0),
                     behaviour="loose" if _st == "reference" else "unknown",
                     use_when="", orientation="vertical", evidence=_BAY_EV,
                     superseded_by="TLRG", infill=15, nozzle_temp=230, notes=_n))

_RK_EV = ("2026-08-01-total-contact-not-distribution.md",)
_S.append(Sample(
    "RK3", BANDED_TRIANGLE_KEY, CORE_ONE_PLA, "superseded",
    dict(mid_w=5.70, tip_w=5.30, key_len=36.0, band_len=3.0, band_n=3, band_pitch=12.0,
         ramp_len=2.0, tight_zone=9.0, apex_flat=0.6, edge_chamfer=0.5, interference=0.10),
    behaviour="tight-hand-removable",
    use_when="",
    orientation="flat", evidence=_RK_EV, basis="bracketed", infill=100, nozzle_temp=225,
    mates_with=("TFH", "TFV"), superseded_by="RK3A",
    notes="Three 3mm bands on a 12mm pitch, one centred in each member, 2mm ramps, tip width "
          "between. 9mm of total contact against TK10's qualified 10mm. Chosen over the 12mm arms "
          "deliberately on the LOOSE side: 16 of these sit 340mm up inside a finished lamp, the "
          "rods bear on their END FACES rather than on the key, and a jammed key means pliers "
          "inside an assembly while a free one costs nothing. SUPERSEDED 2026-08-10: qualified on "
          "the RTG fixture at 225C, it needed HAMMERING into production rims and rods printed at "
          "230 — one member's worth of tightening multiplied by the three members it engages."))
# RKL, 2026-08-10: RK3 needs HAMMERING into the real rod-rim-rod joint. Justin's reads say why —
# a TK10 in ONE member is "a little hard to remove" at 230C, and RK3 engages THREE, so a small
# per-member tightening compounds. This is the 225->230 confound arriving exactly where it was
# flagged: the fits were qualified at 225 and the parts printed at 230.
#
# The knob goes on the KEY, not on the rods: the rods and rims are printed and expensive, a key is
# 0.5g. Narrowing also loosens the RIM band slightly, which is fine — the rim is the middle member,
# trapped between the two rod END FACES and carrying its load in compression through them. It needs
# locating, not gripping. RTG's RK2 arm was built to ask that and could not answer it because both
# 12mm arms jammed; this asks it from the other side.
#
# ONE VARIABLE: band width. tip_w, key_len, band_len, band_n, band_pitch and ramp_len all held.
_RKL_EV = ("2026-08-10-rim-key-reladder.md",)
_S.append(Sample(
    "RK3A", BANDED_TRIANGLE_KEY, CORE_ONE_PLA, "qualified",
    dict(mid_w=5.60, tip_w=5.30, key_len=36.0, band_len=3.0, band_n=3, band_pitch=12.0,
         ramp_len=2.0, tight_zone=9.0, apex_flat=0.6, edge_chamfer=0.5, interference=0.00),
    behaviour="tight-hand-removable",
    use_when="THE PRODUCTION RIM KEY. One key tying three stacked members (rod-rim-rod), against "
             "females printed at 230C.",
    orientation="flat", evidence=_RKL_EV, basis="bracketed", infill=100, nozzle_temp=230,
    mates_with=("TFH", "TFV"), supersedes=("RK3",),
    notes="Line-to-line on band width. Bracketed on BOTH sides in one round: RK3 at 5.70 needed "
          "HAMMERING and RK3B at 5.50 was loose. NOTE WHAT ELSE THIS SETTLES — TFH and TFV were "
          "qualified at 225 and these parts were printed at 230, and the entire 0.10 correction "
          "landed on the KEY, so the females AS PRINTED AT 230 are confirmed usable and only the "
          "male had to move. Unmarked in production; the ladder's single transverse dimple was a "
          "coupon mark."))
_S.append(Sample(
    "RK3B", BANDED_TRIANGLE_KEY, CORE_ONE_PLA, "reference",
    dict(mid_w=5.50, tip_w=5.30, key_len=36.0, band_len=3.0, band_n=3, band_pitch=12.0,
         ramp_len=2.0, tight_zone=9.0, apex_flat=0.6, edge_chamfer=0.5, interference=-0.10),
    behaviour="loose", use_when="Loose-end boundary of the RKL bracket. Not selected.",
    orientation="flat", evidence=_RKL_EV, infill=100, nozzle_temp=230,
    notes="0.10 under RK3A. Kept so the bracket is on the record from both sides."))

for _k, _c, _n, _l, _note in (
        ("RKF", 24.0, 1, 24.0, "One continuous zone — the naive stretch of TK10, and the control."),
        ("RK6", 18.0, 3, 6.0, "Three 6mm bands."),
        ("RK4", 12.0, 3, 4.0, "Three 4mm bands."),
        ("RK2", 12.0, 2, 6.0, "Two 6mm bands, RODS ONLY, rim relieved. Same 12mm of contact as "
                              "RK4 over two members instead of three — and it jammed identically, "
                              "which is what proved distribution does not matter.")):
    _S.append(Sample(_k, BANDED_TRIANGLE_KEY, CORE_ONE_PLA, "rejected",
                     dict(mid_w=5.70, tip_w=5.30, key_len=36.0, band_len=_l, band_n=_n,
                          band_pitch=12.0, ramp_len=2.0 if _k != "RKF" else 6.0, tight_zone=_c,
                          apex_flat=0.6, edge_chamfer=0.5, interference=0.10),
                     behaviour="too-tight", use_when="", orientation="flat", evidence=_RK_EV,
                     superseded_by="RK3A", infill=100,
                     notes="%.0fmm of total contact — needed PLIERS. %s" % (_c, _note)))

# ── TF — the triangle-key female channel ────────────────────────────────────────────────────
_S.append(Sample(
    "TF", TRIANGLE_CHANNEL, CORE_ONE_PLA, "qualified",
    dict(base_w=5.60, height=4.85, depth=12.0, skin=1.575, section_t=8.0),
    behaviour="pass-perfect",
    use_when="Every triangle-key rail end. THE universal extension interface.",
    orientation="flat", evidence=_TK_EV, supersedes=("PF",), basis="bracketed",
    mates_with=("TK10", "TK12"),
    notes="Equilateral, apex-up, stations +/-7 (14 apart) on a 28mm rail. 60 deg self-supporting "
          "roofs, support-free. Skins 1.575 above AND below in an 8mm section. TF is the "
          "THROUGH-channel case; a BLIND pocket of the same nominal runs tighter to withdraw "
          "from — see TFH."))

# ── TFH / TFV — TF compensated PER ORIENTATION, so ONE male serves the whole assembly ────────
# RTP round 1, read 2026-07-31 (Justin). Four profiles, one variable, control first, both
# orientations on the SAME plate against the SAME key — TK10 at its qualified interference — with
# a 4-rung ladder on the FEMALE in perpendicular face offset. Tightest rung still removable by
# hand:
#       TRIH  horizontal, BLIND pocket, rod stock   rung 2  ->  +0.03
#       TRIV  vertical,   through,      rim stock   rung 3  ->  +0.06
#
# TWO results, and the second is the one that unblocked the tower:
#
# 1. The orientation gap is ONE RUNG — 0.03 face offset, ~0.10 on width. HALF the 0.20-on-width
#    implied by setting TK10 from one round against TKN10 from another. Cross-round comparison
#    inflated it; a control on the same plate halved it. Sizes ONE-VARIABLE in mm.
# 2. TRIH won at rung 2, NOT rung 1 — and rung 1 IS TK10 x TF, the qualified pair. A BLIND pocket
#    therefore needs one rung more than the through-channel TF was qualified in. INSERTION is
#    unchanged; WITHDRAWAL is not, and serviceability is the entire reason the key exists. New
#    context axis: a channel's fit depends on whether it is blind, not only on its orientation.
#
# The profile question closed at the same time: the plain TRIANGLE won. Hexagon and octagon buy
# 6.4x / 12x less corner-fill and pay 2.52mm / 2.08mm of roof bridge against the apex-up
# triangle's 0.23mm. Corner-fill was never the binding term — the roof is.
_RTP_EV = ("2026-07-31-compensate-the-female-not-the-key.md",)
_RTG_EV = ("2026-07-31-compensate-the-female-not-the-key.md",
           "2026-08-01-blind-not-surround.md")
_S += [
    Sample("TFH", TRIANGLE_CHANNEL, CORE_ONE_PLA, "qualified",
           dict(base_w=5.704, height=4.940, depth=12.0, skin=4.53, section_t=14.0),
           behaviour="tight-hand-removable",
           use_when="A BLIND horizontal channel — a rod end, a socket you must pull back out of. "
                    "Not for a through channel: that is plain TF.",
           orientation="flat", evidence=_RTP_EV, basis="bracketed", mates_with=("TK10",),
           infill=15,
           notes="TF opened +0.03 on every face (base_w +0.104: width is not clearance, a face "
                 "moves by w/(2*sqrt(3))). Measured in 14mm rod stock with 3.2mm side walls, "
                 "12mm deep, at 15% infill."),
    Sample("TFV", TRIANGLE_CHANNEL, CORE_ONE_PLA, "qualified",
           dict(base_w=5.808, height=5.030, depth=12.0, skin=3.10, section_t=12.0),
           behaviour="tight-hand-removable",
           use_when="A VERTICAL socket in RIM-WEIGHT stock. Corner-fill closes a vertical "
                    "triangle and there is no bridging sag to reopen it.",
           orientation="vertical", evidence=_RTP_EV, basis="bracketed", mates_with=("TK10",),
           infill=15,
           notes="TF opened +0.06 on every face (base_w +0.208). Measured THROUGH 12x12 rim "
                 "stock at 15% infill. A BLIND vertical socket is a different sample — TFB."),
    Sample("TFB", TRIANGLE_CHANNEL, CORE_ONE_PLA, "qualified",
           dict(base_w=5.912, height=5.120, depth=11.0, skin=3.04, section_t=12.0),
           behaviour="tight-hand-removable",
           use_when="A BLIND vertical socket — the plinth. One rung above TFV, and the rung is "
                    "bought by the BLINDNESS, not by the surround.",
           orientation="vertical", evidence=_RTG_EV, basis="bracketed", mates_with=("TK10",),
           infill=15,
           notes="TF opened +0.09 on every face. RTG gate 1: TK10 would not come out of the +0.06 "
                 "rung by hand and would out of +0.09, in 11mm-deep blind sockets in 12mm plinth "
                 "stock with 10mm of surround."),
]

# WHAT GATE 1 ACTUALLY SETTLED, which is worth more than the number.
# The plinth differs from the rim in TWO ways — blind vs through, and 10mm of surround vs 3.2 —
# and the result separates them. Blind-vs-through cost exactly ONE RUNG when measured horizontally
# (TRIH rung 2 against the qualified through-channel's rung 1). The plinth came in exactly one
# rung above the rim. So the entire base-vs-rim difference is blindness, and tripling the surround
# moved the fit by NOTHING measurable:
#
#       SURROUND THICKNESS IS NOT A CONTEXT AXIS.  BLIND vs THROUGH IS.
#
# Two consequences. A future joint does not owe a surround-thickness coupon — which is what the
# 07-30 note assumed when it deferred the base as "one variable too many". And the blind penalty
# now looks like a CONSTANT +0.03 in both orientations rather than something to re-measure per
# part, which is a prediction the next blind joint will test for free.

# Justin's blunt-profile proposal, tested and lost. Kept so it is never re-proposed: the corner
# argument is correct and still loses, because on a REGULAR polygon corner bluntness and roof
# steepness are the same knob (vertex-up roof angle is 180/n), and a blind pocket cannot take
# support. Any future attempt has to break that coupling — radius the corners of a 60 deg gable
# rather than add sides.
for _k, _n, _span, _corner in (("TFX6", 6, 2.52, 0.013), ("TFX8", 8, 2.08, 0.007)):
    _S.append(Sample(_k, TRIANGLE_CHANNEL, CORE_ONE_PLA, "rejected",
                     dict(base_w=5.60, height=4.85, depth=12.0, skin=1.575, section_t=8.0),
                     behaviour="unknown", use_when="", orientation="flat", infill=15, evidence=_RTP_EV,
                     superseded_by="TFH",
                     notes="Regular %d-gon section, flat-up, sized to TF's cross-sectional area. "
                           "Cuts corner-fill to %.3fmm2 from the triangle's 0.082 but needs a "
                           "%.2fmm roof bridge against the apex-up triangle's 0.23. Lost the RTP "
                           "round to the plain triangle. Vertex-up is worse still: %.1f deg roof, "
                           "and the rod channel is blind." % (_n, _corner, _span, 180.0/_n)))

# ── QH2 / QZ — the horizontal dovetail + its retention. PASS_PERFECT, unchanged. ─────────────
_QZ_EV = ("2026-07-23-pcc2-compression-shoulder-zip-teeth.md",
          "2026-07-23-pcc2-rail-extension-trapezoidal-lock.md")
_S += [
    Sample("QH2", DOVETAIL, CORE_ONE_PLA, "qualified",
           dict(width_clearance=0.20, depth_clearance=0.10),
           behaviour="pass-perfect",
           use_when="Horizontal dovetail slides. The studio baseline cross-section.",
           orientation="flat", evidence=_QZ_EV, basis="bracketed", mates_with=("QZ",),
           notes="0.2mm TOTAL width clearance, 0.10mm depth. CAD interference 0.0mm^3."),
    Sample("QZ", SHOULDER_RATCHET, CORE_ONE_PLA, "qualified",
           dict(pitch=2.4, groove_w=1.8, land=0.6, depth=0.20, phase=1.2),
           behaviour="pass-perfect",
           use_when="Retention on dovetail slides that HAVE compression shoulders (style A).",
           orientation="flat", evidence=_QZ_EV, basis="cycled", cycles=10, mates_with=("QH2",),
           notes="QZTF/QZTM PASS_PERFECT. Each patterned face removes 18.48mm^3; QH2's 0.1mm "
                 "seat creates 30.76mm^3 localized shoulder preload."),
    Sample("QR", DOVETAIL, CORE_ONE_PLA, "rejected",
           dict(width_clearance=0.20, depth_clearance=0.10),
           behaviour="unknown", orientation="flat", superseded_by="QZ",
           evidence=("2026-07-23-pcc2-longitudinal-rib-friction-doe.md",),
           notes="LONGITUDINAL ribs on the dovetail floor/sidewalls (QRTF/QRTM/QRSF/QRSM). "
                 "Rejected before printing: they bind the slide and mark a mating face. "
                 "Distinct from transverse tongue teeth (style B), which are legitimate."),
    Sample("LSR", DOVETAIL, CORE_ONE_PLA, "rejected",
           dict(width_clearance=0.20, depth_clearance=0.10),
           behaviour="loose", infill=15,
           use_when="Leaf-scale spine rail: a full-height sliding dovetail joining a 5mm "
                    "bonded two-skin stack to its 9mm spine bar, both members printed flat. "
                    "Replaces a glue-only butt joint (social-media-sign middle leaf).",
           orientation="flat", evidence=("2026-08-18-lfc2-spine-rail-dovetail.md",),
           mates_with=("QZ",),
           notes="QH2's clearances at a NEW cross-section — male crest 3.2 / neck 1.5 / "
                 "proud 1.6 (QH2's ~28deg flank), female = +0.20 width / +0.10 depth. The "
                 "section change is why this is its own sample: QH2's 14.6/10.6x3.8 section "
                 "cannot live in a 5mm stack. Female cavity is formed by two mirrored "
                 "half-pockets in the skins' bond faces, so neither half has an undercut in "
                 "its own print frame; the bar prints on its SIDE so the male flares upward. "
                 "Engagement is full leaf height (lever ratio ~1, so LEVER-SCALE does not "
                 "amplify). LFC2 PHYSICAL (2026-08-18): NOT TIGHT -- the qualified "
                 "absolute clearance is ~6% of this crest vs ~1.4% of QH2's, so the "
                 "carried numbers read as slop at this scale. Clearances are only "
                 "portable while they stay a small FRACTION of the section."),
    Sample("LBK", DOVETAIL, CORE_ONE_PLA, "rejected",
           dict(width_clearance=-0.10, depth_clearance=0.10),
           behaviour="too-tight", infill=15,
           use_when="Butterfly (bowtie) closure keys tying two flat-printed plates "
                    "together ACROSS their bond plane, where a direct snap cannot print "
                    "(both bond faces are bed faces). Presses in snap-tight; the flares "
                    "block plate separation. First use: the leaf cartridge halves whose "
                    "female dovetail must grip the LSR rail.",
           orientation="flat", evidence=("2026-08-18-lfc2-spine-rail-dovetail.md",),
           mates_with=("LSR",),
           notes="Double-dovetail spline: waist 4.0 flaring to 5.26 over 1.2 per side at "
                 "QH2's flank; each plate carries a half-channel (wider at depth -- no "
                 "undercut per print). width_clearance is NEGATIVE: a +0.10 press over "
                 "the key's width (TK10's hand-removable interference precedent, "
                 "re-couponed here because fits never transfer across sections); the "
                 "flares float by depth_clearance so the flanks carry. Key prints flat "
                 "with the capture axis in-plane, so separation loads the strands, not "
                 "the layer bond. LFC2 PHYSICAL (2026-08-18): WILL NOT PRESS CLEANLY -- "
                 "both mates are BED-FACE features, so elephant-foot narrows the channel "
                 "mouths while widening the key's own first-layer flare; the two errors "
                 "stack against the fit."),
]

# ── WAVE TRAIN (FX) — the retention that beat the snap detent ────────────────────────────────
_S.append(Sample(
    "FXW", WAVE_TRAIN, CORE_ONE_PLA, "qualified",
    dict(amp=0.30, width=1.8, pitch=2.4, face_gap=None, stations=8),
    behaviour="pass-perfect",
    use_when="OPEN lap / corner joints ONLY, where the parts lift apart perpendicular to travel "
             "so the ridges can cam. NOT valid inside a captured joint at any amplitude yet.",
    orientation="flat",
    evidence=("2026-07-23-pcc2-rail-extension-trapezoidal-lock.md",),
    notes="Continuous female ridges into aligned male divets, flush when mated. Beat the "
          "one-large-button snap detent (FX-Fsd/Msd), which seated slightly loose. face_gap is "
          "None because an open lap has no bounded gap — that freedom IS why it works here."))
_S.append(Sample(
    "VW20", WAVE_TRAIN, CORE_ONE_PLA, "rejected",
    dict(amp=0.20, width=1.8, pitch=2.4, face_gap=0.0, stations=8),
    behaviour="too-tight",
    use_when="",
    orientation="flat",
    evidence=("2026-07-24-qualified-joint-registry.md",),
    notes="R3 physical (2026-07-24): VOM3 against BOTH VOZ30W and VOZ40W jammed halfway. The "
          "amplitude was picked to sit under the depth-clearance bracket, but the VD mating flat "
          "faces meet at ZERO gap — dc is fin-crest slack on a different surface pair — so face "
          "interference was the full 0.20 across 8 pitch-matched stations camming at once. "
          "Raising dc 0.20->0.25 changed nothing, which is the proof: dc was never the knob."))
# R4 (2026-07-24, Justin): "interlocking just at the end". The train shrinks from 8 stations
# spanning 18mm of travel to 2 at the male's TRAILING end, so the ridges only enter the female
# in the last 3.6mm. Amplitude deliberately UNCHANGED on VW20E — one variable — so the round
# answers which rule was actually driving the jam: R1b (simultaneity/travel) or R1 (interference).
_S.append(Sample(
    "VW20E", WAVE_TRAIN, CORE_ONE_PLA, "qualified",
    dict(amp=0.20, width=1.8, pitch=2.4, face_gap=0.0, stations=2),
    behaviour="pass-perfect", basis="cycled", cycles=10, mates_with=("VOZ30E",),
    use_when="THE captured-joint retention. Free travel, then interlock in the last 3.6mm of "
             "insertion. Two stations at the male's TRAILING end.",
    orientation="flat", evidence=("2026-07-25-vd-r4-station-count-not-amplitude.md",
                                  "2026-07-24-vd-r3-face-interference.md"),
    notes="R4 PHYSICAL PASS (2026-07-25, Justin): VOM4 x VOZ30E fit BEST of the matrix. This is "
          "byte-for-byte the rejected VW20 profile — same amp 0.20, same 1.8 width, same 2.4 "
          "pitch, same ZERO face gap — with ONLY the station count changed 8 -> 2 and moved to "
          "the trailing end. R3 jammed; this fits. That single-variable pair is the proof that "
          "R1b (simultaneous camming over travel) governs, NOT interference magnitude. "
          "HELD AFTER TEN CYCLES (2026-07-25) — and since a cycle is an insert AND a remove, "
          "ten of them prove hand-removability as a by-product."))
_S.append(Sample(
    "VW10E", WAVE_TRAIN, CORE_ONE_PLA, "reference",
    dict(amp=0.10, width=1.8, pitch=2.4, face_gap=0.0, stations=2),
    behaviour="loose", superseded_by="VW20E",
    use_when="Loose-end boundary of the R4 amplitude bracket. Not selected — VOM5 lost to VOM4, "
             "so 0.20 over two stations was not too stiff and 0.10 gave up grip for nothing.",
    orientation="flat", evidence=("2026-07-24-vd-r3-face-interference.md",),
    notes="Second variable moved only in this arm, as the fallback. Female divots stay 0.20 deep "
          "so one female serves both males — a shallower ridge simply does not bottom out."))

# ── VD — twin dovetail, the v2 vertical joint (IN FLIGHT) ────────────────────────────────────
_VD_COMMON = dict(neck=6.0, crest=9.0, proud=3.0, fin_len=20.0, overhang_deg=26.6)
_VD_EV = ("2026-07-24-qualified-joint-registry.md",)
for _k, _wc, _dc, _st, _bh, _nt in (
        ("VDF10", 0.10, 0.10, "rejected", "too-tight", "R1: would not assemble."),
        ("VDF20", 0.20, 0.15, "rejected", "too-tight", "R1: would not assemble."),
        ("VDF30", 0.30, 0.20, "superseded", "unknown",
         "Same clearance pair that R4 qualified as VOZ30E; use VOZ30E, which carries the "
         "physical result and the matching end-detent divots."),
        ("VDF40", 0.40, 0.25, "superseded", "unknown",
         "Fallback clearance; R4 selected the tighter VOZ30E."),
        ("VDF50", 0.50, 0.30, "reference", "loose", "Loose-end bracket.")):
    _S.append(Sample(_k, TWIN_DOVETAIL, CORE_ONE_PLA, _st,
                     dict(_VD_COMMON, width_clearance=_wc, depth_clearance=_dc),
                     behaviour=_bh, orientation="flat", evidence=_VD_EV,
                     superseded_by=("VOZ30E" if _st == "superseded" else None),
                     use_when="Corner<->upright vertical joint v2 (supersedes VC05).",
                     notes=_nt + " Fins at stations +/-7."))
# R3 physical, 2026-07-24: the two waved females printed and BOTH jammed halfway on VOM3.
for _k, _wc, _dc in (("VOZ30W", 0.30, 0.20), ("VOZ40W", 0.40, 0.25)):
    _S.append(Sample(_k, TWIN_DOVETAIL, CORE_ONE_PLA, "rejected",
                     dict(_VD_COMMON, width_clearance=_wc, depth_clearance=_dc),
                     behaviour="too-tight", orientation="flat", evidence=_VD_EV,
                     superseded_by="VOZ30E",
                     notes="R3 PHYSICAL FAIL (2026-07-24, Justin): entered, then STUCK HALFWAY "
                           "against VOM3's amp-0.20 ridge train. Both clearances failed "
                           "identically, so the dovetail clearance is exonerated and the wave "
                           "train is the cause — see VW20. Confounded DOE: R3 shipped no plain "
                           "control, so one variable per round was violated."))
# R4 females: same clearances as R3, but only TWO divots, at the mouth end, to receive a short
# end train. Divots are recesses, so a PLAIN male run down these also isolates the dovetail
# clearance — which is the datum R3 never captured.
_S.append(Sample(
    "VOZ30E", TWIN_DOVETAIL, CORE_ONE_PLA, "qualified",
    dict(_VD_COMMON, width_clearance=0.30, depth_clearance=0.20),
    behaviour="pass-perfect", orientation="flat", basis="cycled", cycles=10,
    mates_with=("VW20E",), supersedes=("VDF30",),
    evidence=("2026-07-25-vd-r4-station-count-not-amplitude.md",),
    use_when="THE corner<->upright vertical joint (v2). Twin fins at +/-7, 0.30 width / 0.20 "
             "depth clearance, with the VW20E two-station end detent.",
    notes="R4 SELECTED (2026-07-25, Justin): VOM4 x VOZ30E fit BEST, and HELD AFTER TEN CYCLES. "
          "Two divots 0.20 deep near the mouth receive the male's trailing stations at 1.2/3.6. "
          "Beat the looser VOZ40E. THE CLEARANCE IS INDEPENDENTLY QUALIFIED: the plain control "
          "VOM2 (no detent at all) also slid clean down this female, so 0.30/0.20 stands on its "
          "own and VW20E adds retention rather than compensating for a loose fit. That is the "
          "control R3 never printed. CAVEAT: proven on a 28mm coupon stub — see rule LEVER-SCALE "
          "before trusting it on the 180mm upright."))
_S.append(Sample(
    "VOZ40E", TWIN_DOVETAIL, CORE_ONE_PLA, "reference",
    dict(_VD_COMMON, width_clearance=0.40, depth_clearance=0.25),
    behaviour="loose", orientation="flat", superseded_by="VOZ30E",
    evidence=("2026-07-25-vd-r4-station-count-not-amplitude.md",),
    use_when="Loose-end boundary of the R4 clearance bracket. Not selected.",
    notes="R4: lost to VOZ30E."))

# ── VC — single-dovetail vertical slide gauges (superseded by VD, still qualified) ───────────
_VC_EV = ("2026-07-24-qualified-joint-registry.md",
          "2026-07-23-photo-scale-pcc2-double-dovetail.md")
_S.append(Sample(
    "VC05", DOVETAIL, CORE_ONE_PLA, "qualified",
    dict(width_clearance=0.05, depth_clearance=0.05),
    behaviour="snug",
    use_when="Long-lever vertical joints (holds a 180mm lever square).",
    orientation="standing", evidence=_VC_EV, supersedes=("QV5",), basis="in-service",
    notes="Male 28 front / 34 back x 8 thick; female = male + 0.05 width / 0.05 depth."))
# The original PCC2 clearance ladders, recovered from research/results/measurements.csv
# (2026-07-23). They were logged as observations but never registered, so the log referenced
# samples the registry did not know — exactly the orphaned-evidence case measurements_check.py
# now catches. Depth is recorded only where the log actually states it.
_S.append(Sample(
    "IX35", DOVETAIL, CORE_ONE_PLA, "superseded",
    dict(width_clearance=0.35, depth_clearance=0.45),
    behaviour="snug", orientation="vertical",
    evidence=("2026-07-23-pcc2-rail-extension-trapezoidal-lock.md",), superseded_by="TF",
    use_when="Legacy: the buried tongue-and-groove extension (retention style B).",
    notes="R3's winning EXTENSION fit — but only printed VERTICAL, where no support bonds to the "
          "floating tongue. The production 180mm rails cannot stand vertical, and horizontal "
          "support jammed insertion, so the whole architecture was replaced by pegs and then by "
          "TF/TK. The cleanest rule-R2 datum on record: same numbers, different orientation, "
          "different joint.")),
_LADDER_EV = ("2026-07-23-photo-scale-pcc2-double-dovetail.md",)
_S.append(Sample("QH3", DOVETAIL, CORE_ONE_PLA, "superseded",
                 dict(width_clearance=0.30, depth_clearance=0.15),
                 behaviour="snug", orientation="flat", evidence=_LADDER_EV, superseded_by="QH2",
                 notes="PASS_NEAR_SNUG: fits QHF nicely but not as snug as the vertical pair."))
_S.append(Sample("QH4", DOVETAIL, CORE_ONE_PLA, "superseded",
                 dict(width_clearance=0.40, depth_clearance=UNKNOWN),
                 behaviour="loose", orientation="flat", evidence=_LADDER_EV, superseded_by="QH2",
                 notes="PASS_LOOSE: best QHF mate of the initial set but not snug. Depth "
                       "clearance was not recorded in the log."))
for _k, _wc in (("QV8", 0.80), ("QV6", 0.60)):
    _S.append(Sample(_k, DOVETAIL, CORE_ONE_PLA, "superseded",
                     dict(width_clearance=_wc, depth_clearance=UNKNOWN),
                     behaviour="loose", orientation="standing", evidence=_LADDER_EV,
                     superseded_by="VC05",
                     notes="PASS_LOOSE: full insertion/removal works but the fit is loose. "
                           "Depth clearance not recorded."))
_S.append(Sample("QV4", DOVETAIL, CORE_ONE_PLA, "rejected",
                 dict(width_clearance=0.40, depth_clearance=UNKNOWN),
                 behaviour="too-tight", orientation="standing", evidence=_LADDER_EV,
                 superseded_by="VC05",
                 notes="FAIL_AS_PRINTED: too tight, fit only after filing — and the mating QVM "
                       "had also been filed, which is why the ladder restarted on fresh parts."))
for _k, _wc, _dc, _nt in (
        ("VC10", 0.10, 0.10, "Not selected."),
        ("VC15", 0.15, 0.15, "Best of R1's 15/25/35 but still a touch loose."),
        ("VC25", 0.25, 0.20, "Loose."),
        ("VC35", 0.35, 0.30, "Loose."),
        ("QV5", 0.50, 0.30, "Coupon-SNUG but LEVER-LOOSE (~0.6mm slack at 180mm). The R2 "
                            "lesson: a coupon-scale pass can fail at production scale.")):
    _S.append(Sample(_k, DOVETAIL, CORE_ONE_PLA, "superseded",
                     dict(width_clearance=_wc, depth_clearance=_dc),
                     behaviour="loose", orientation="standing", evidence=_VC_EV,
                     superseded_by="VC05", notes=_nt))

# ── PG / PR — spiral dowel pegs. Qualified, but superseded by TK for NEW parts. ──────────────
_PG_EV = ("2026-07-23-pcc2-rail-extension-trapezoidal-lock.md",
          "2026-07-24-trikey-flat-printed-triangle-joint.md")
_PG_COMMON = dict(bore_d=5.0, length=22.0, groove_r=0.45, groove_depth=0.45,
                  groove_pitch=9.5, groove_span=19.0, starts=2, chamfer=0.8)
for _k, _d, _st, _bh, _nt in (
        ("PG46", 4.6, "rejected", "loose", "R1: too loose in the 5.0 bore."),
        ("PG48", 4.8, "rejected", "loose", "R1: too loose. Centered single dimple."),
        ("PG49", 4.9, "reference", "loose", "R2 bracket, 0.1 clearance."),
        ("PG50", 5.0, "reference", "loose", "R2 bracket, line-to-line."),
        ("PG51", 5.1, "qualified", "snug",
         "BEST. +0.1mm diametral interference on full-diameter lands."),
        ("PG52", 5.2, "reference", "unknown", "R2 bracket, +0.2 interference.")):
    _S.append(Sample(_k, SPIRAL_DOWEL, CORE_ONE_PLA, _st,
                     dict(_PG_COMMON, peg_d=_d, interference=round(_d - 5.0, 2)),
                     behaviour=_bh, orientation="vertical", evidence=_PG_EV,
                     superseded_by=(None if _st == "qualified" else "PG51"),
                     basis=("bracketed" if _st == "qualified" else "single-coupon"),
                     mates_with=(("PF",) if _st == "qualified" else ()),
                     use_when=("Legacy v1-compatible parts with existing round bores (PCC2ER). "
                               "Superseded by TK10/TK12 for NEW extensions, 2026-07-24."
                               if _st == "qualified" else ""),
                     notes=_nt + " Print VERTICAL on a modeled dia-12 x 0.2 twist-off pad foot; "
                                 "slice SOLID."))
for _k, _body, _rib, _st, _nt in (
        ("PR51", 4.2, 0.45, "reference", "Envelope 5.1 (+0.1)."),
        ("PR53", 4.4, 0.45, "reference",
         "RUNNER-UP. Envelope 5.3 (+0.3). Works, but rigid lands at fine interference beat "
         "compliant crush ribs."),
        ("PR55", 4.6, 0.45, "reference", "Envelope 5.5 (+0.5).")):
    _S.append(Sample(_k, SPIRAL_DOWEL, CORE_ONE_PLA, _st,
                     dict(_PG_COMMON, peg_d=_body + 2 * _rib,
                          interference=round(_body + 2 * _rib - 5.0, 2)),
                     behaviour="snug" if _k == "PR53" else "unknown",
                     orientation="vertical", evidence=_PG_EV, superseded_by="PG51",
                     notes=_nt + " RAISED-helix family: identical 2-start helix fused PROUD of "
                                 "an undersized body — only rib crests touch the bore. "
                                 "Retention knob is rib height, not diameter."))
_S.append(Sample(
    "PF", TRIANGLE_CHANNEL, CORE_ONE_PLA, "superseded",
    dict(base_w=5.0, height=5.0, depth=12.0, skin=1.5, section_t=8.0),
    behaviour="pass-perfect", orientation="flat", evidence=_PG_EV, superseded_by="TF",
    use_when="Legacy round-bore rail ends (PCC2ER v1 compatibility).",
    notes="Two dia-5.0 x 12.0 blind bores at mid-thickness of an 8mm rail, 14mm apart "
          "(+/-7). Small horizontal bores self-bridge — no support. Round, not triangular: "
          "modeled here so the legacy interface stays addressable by sample number."))

# ── MARKING — legibility is coupon evidence, not a style preference ─────────────────────────
_MARK_EV = ("2026-07-23-b2b-r5-legible-identifiers-and-independent-nut-stops.md",)
_S += [
    Sample("LD6", MARKING, CORE_ONE_PLA, "qualified",
           dict(size=6.0, effective_depth=1.0, weight="bold"),
           behaviour="pass-perfect",
           use_when="THE BASELINE for every printed part ID where the face permits it.",
           orientation="flat", evidence=_MARK_EV,
           notes="6mm bold text, true 1.0mm recess. `legible_deboss` in parts/_lib/deboss.py "
                 "reads its defaults from HERE. A part too small for this baseline needs its own "
                 "label coupon rather than silently shrinking the text."),
    Sample("LD3", MARKING, CORE_ONE_PLA, "rejected",
           dict(size=3.0, effective_depth=0.4, weight="regular"),
           behaviour="too-tight",
           use_when="", orientation="flat", evidence=_MARK_EV, superseded_by="LD6",
           notes="R4 bottle-gauge evidence: 3mm regular text at ~0.4mm effective depth was "
                 "NEARLY UNREADABLE as printed. This is the measure that made LD6 a requirement; "
                 "it is kept so the failure is never re-proposed as 'just make it smaller'."),
]


# ── ROPE (2026-07-26 bench) — logged in measurements.csv before they were registered; the
# foreign-key check caught the orphan, which is the same signal as the QH3/QH4 recovery: evidence
# in the log with no registry row means the registry has the hole, not the log.
_ROPE_EV = ("2026-07-24-bottle-cradle-rope-lattice.md",)
for _k, _d, _st, _bh, _nt in (
        ("RHG80", 8.0, "rejected", "too-tight", "Predicted winner; too tight for the real rope."),
        ("RHG82", 8.2, "rejected", "too-tight", "Predicted winner; still too tight."),
        ("RHG84", 8.4, "qualified", "pass-perfect",
         "SELECTED. Threads the real 7.8-8.4mm sisal without fighting or shredding. LARGER than "
         "predicted (8.0/8.2): bridge sag at the bore top plus fibre bulk cost more clearance "
         "than a nominal-diameter estimate suggests."),
        ("RHG87", 8.7, "reference", "loose", "Passes but larger than needed.")):
    _S.append(Sample(_k, ROPE_HOLE, CORE_ONE_PLA, _st,
                     dict(hole_d=_d, section_t=12.0, rope_nom=8.0,
                          min_wall=round((12.0 - _d)/2, 2)),
                     behaviour=_bh, orientation="flat", evidence=_ROPE_EV,
                     superseded_by=(None if _st == "qualified" else "RHG84"),
                     use_when=("Every rope hole in a 12mm rim section." if _st == "qualified"
                               else ""),
                     notes=_nt + " Bored horizontally through a production-representative 12mm "
                                 "section, chamfered both faces."))
_S.append(Sample(
    "RCW95", CLEAT, CORE_ONE_PLA, "qualified",
    dict(gap=9.5, bar_d=8.0, bar_len=48.0),
    behaviour="pass-perfect", orientation="standing", evidence=_ROPE_EV,
    use_when="Rope tie-off on a tower post, 8mm sisal.",
    notes="Vertical figure-8 with the real rope: HOLDS UNDER LOAD and releases cleanly. The 8mm "
          "gap it replaced was sized for 6mm sisal. Breakaway pillar under the bar tip."))

# ── LINE STRIPS (TR3 / TR3S, 2026-10-06/07) — the touge road's slide-in lines ─────────────────
# Colour swaps in the print were too tedious; pressed-in strips looked wavy or didn't hold; stiff PLA
# T strips couldn't follow BO's changing curve (i5 none went in, i6 only with gaps too wide). TPU 95A
# strips bend to the curve, so the visible gap came back to 0.10; their flange then took up the room
# under the lips: 0.6 flange (0.8 room) "pretty loose", 1.0 (0.4) "too tight", 0.7 "a little loose",
# 0.8 (0.6) "snug, but still goes in" -- chosen. Proven on 118 mm of BO's front edge line, fed in from
# one end; a whole module's length is untried.
_LS_EV = ("2026-10-07-touge-line-strip-fit.md",)
_S += [
    Sample("TR3-1", T_SLOT, CORE_ONE_PLA, "qualified",
           dict(line_w=2.34375, gap=0.10, lip=0.8, channel_w=9.14, channel_h=1.4),
           behaviour="snug",
           use_when="Every touge road line, straight or curved, with a TR3S-8 strip.",
           orientation="face-down", evidence=_LS_EV, basis="bracketed", mates_with=("TR3S-8", "TR3S-7"),
           infill=15, nozzle_temp=230,
           notes="TR3 i7's slot 1: black Prusament PLA, 0.20 BALANCED HF0.4, 2 perimeters. A 2.54 mouth "
                 "through 0.8 lips over a 9.14 x 1.4 channel, 2.2 deep. Gaps 0.15 / 0.20 also took a "
                 "strip; nobody has compared how they look, so 0.10 stands."),
    Sample("TR3S-8", T_STRIP, CORE_ONE_TPU95A_010, "qualified",
           dict(line_w=2.34375, flange_w=7.14, flange_t=0.8, height=2.2, foot_chamfer=0.2),
           behaviour="snug",
           use_when="The line strip for every TR3-1 slot, straight and curved (Justin, 2026-10-08: \"let's "
                    "do the straight lines in TPU to keep the look consistent\").",
           orientation="flange-down", evidence=_LS_EV, basis="bracketed", mates_with=("TR3-1",),
           infill=100, nozzle_temp=210,
           notes='"8 fits best, it is snug, but still goes in." 1.0 a side in the 9.14 channel, 0.6 of '
                 "room under the lips. The foot's two edges are stepped 0.2 x 0.1 against first-layer "
                 "squish. SUNLU TPU 95A, 0.20 SPEED speeds slowed (TPU_020_SLOW), gap fill 30."),
    Sample("TR3S-7", T_STRIP, CORE_ONE_TPU95A_010, "reference",
           dict(line_w=2.34375, flange_w=7.14, flange_t=0.7, height=2.2, foot_chamfer=0.2),
           behaviour="loose", orientation="flange-down", evidence=_LS_EV, mates_with=("TR3-1",),
           infill=100, nozzle_temp=210,
           notes='"7 was still a little loose" -- the fallback if 8 binds (a longer strip, a tighter '
                 "curve, a slot that printed tight). 0.7 of room under the lips."),
]

# The road's PETG joints (registered 2026-11-11, five weeks after they were proven: every file in parts/_lib is an
# input to every part, so an edit here was put off rather than make other parts rebuild). All Overture PETG on the
# HF0.4 nozzle at 250 C, 3 perimeters, adaptive cubic 15 %, the host printed face-down so its sockets are blind and
# vertical. Numbers are the coupons' own constants at the accepted iteration; rib rungs are AS SLICED.
_PT_EV = ("2026-10-13-touge-road-petg-push-tabs-and-ribbed-sockets.md",)
_PT_COMMON = dict(strip_w=2.34375, strip_t=0.8, groove_clear=0.15, tab_w=1.34, tab_l=4.0, tab_d=3.0,
                  body_clear=0.25, rib_base=0.8, slack=0.5, pitch_max=16.0, end_margin=4.0)
_RS_COMMON = dict(peg_d=4.0, body_clear=0.25, ribs=4, rib_base=0.8, rib_sink=0.15, rib_start=0.3, rib_ramp=0.8)
_BOX_EV = ("2026-10-29-touge-road-box-tabs-get-stops.md",
           "2026-10-30-touge-road-box-tabs-tapered-and-preloaded.md")
_S += [
    Sample("TR6-1", PUSH_TAB, CORE_ONE_PETG, "qualified",
           dict(_PT_COMMON, rib_past_sliced=0.05, rib_past_drawn=0.14),
           behaviour="snug",
           use_when="Every touge road line in PETG, and any flush strip pressed into a face-down PETG part.",
           orientation="face-down", evidence=_PT_EV, basis="single-coupon", infill=15, nozzle_temp=250,
           notes='tr6-i2 strip 1 (2026-10-13), the LOWEST rung of its ladder. Justin: "okay 1 is the best, but 2 '
                 'also works"; strip 3 (0.17) was not mentioned, so no rung of this ladder is known to fail. '
                 "tr6-i1's three strips were \"all too tight\", but with the body at 0.12 as well as ribs at "
                 "0.17 / 0.23 / 0.28, so they do not bracket the rib alone. Nothing looser than 0.05 has been "
                 "tried. Strip flat, tabs up; sockets 1.84 x 5.0, 0.4 past the tab's tip."),
    Sample("TR6-2", PUSH_TAB, CORE_ONE_PETG, "reference",
           dict(_PT_COMMON, rib_past_sliced=0.10, rib_past_drawn=0.22),
           behaviour="unknown", orientation="face-down", evidence=_PT_EV, infill=15, nozzle_temp=250,
           notes='tr6-i2 strip 2: "2 also works". The rung to go to if strip 1 proves loose over a whole line.'),
    Sample("TR7-2", RIBBED_SOCKET, CORE_ONE_PETG_015, "qualified",
           dict(_RS_COMMON, rib_past_sliced=0.05, rib_past_drawn=0.14),
           behaviour="snug",
           use_when="Each guardrail post socket on the touge road; a post or peg in a blind vertical PETG "
                    "socket that must stay put and still go in by hand.",
           orientation="face-down", evidence=_PT_EV, basis="bracketed", infill=15, nozzle_temp=250,
           notes='tr7-i2 socket 2 (2026-10-13). Justin: "1 for the with the cross line worke dbest and 2 and 3 '
                 'worked best for the shorter ones": the guardrail\'s D posts (2.4 x 1.6, peg 4.0) in sockets 2 '
                 "and 3; the lamp's pole held best in socket 1, the road's own PLAIN socket at 0.15 a side, and "
                 "keeps it. On the D post's round crown the rib is drawn 0.22 (the crown prints 0.05 low at "
                 "0.15 layers). Socket 4 (0.15) was not picked."),
    Sample("TR7-3", RIBBED_SOCKET, CORE_ONE_PETG_015, "reference",
           dict(_RS_COMMON, rib_past_sliced=0.10, rib_past_drawn=0.22),
           behaviour="unknown", orientation="face-down", evidence=_PT_EV, infill=15, nozzle_temp=250,
           notes="tr7-i2 socket 3: also picked for the guardrail's posts. The tighter rung."),
    Sample("TR8-3", SNAP_TAB_HOLDER, CORE_ONE_PETG, "qualified",
           dict(tab_w=12.0, tab_l=27.0, tab_t_root=2.8, tab_t_tip=1.6, root_r_in=1.0, root_r_out=4.0, lip=1.0,
                preload=0.6, tab_clear=0.5, side_rib_past_sliced=0.15, body_clear=0.25),
           behaviour="tight-hand-removable",
           use_when="The touge road's 2 x AA box (68.54 x 34.56 x 18.9) hung cover-down under the road; the "
                    "starting point for any bought box clicked in under a face-down PETG part.",
           orientation="face-down", evidence=_BOX_EV, basis="single-coupon", infill=15, nozzle_temp=250,
           notes='tr8-i5 holder 3 (2026-11-02). Justin: "okay 3 works well". The preload ladder was 0.2 / 0.4 / '
                 "0.6 into the box's corner; 0.6, its TOP rung (5.4 N onto the pads), stayed tight, so nothing "
                 "tighter has been tried. Reached through i1 (ribs "
                 'only: "none will hold upside down"), i3 (2.2 tabs, square roots: "could still get '
                 'permanetly bent"), i4 (stops: "did not do anything"). About 30.7 N to pull the box out. '
                 "The tab grows up from a face-down print, so it bends across the layers at its root."),
]

# Infill each coupon was actually sliced at, read back off the qualifying plate's gcode.
_INFILL = {'TK00': 15, 'TF': 15, 'TK05': 100, 'TK10': 100, 'TK12': 100, 'TR20': 100, 'TR30': 100, 'TK15': 100, 'TK30': 100, 'TK45': 100, 'TK60': 100, 'TS45': 100, 'TS70': 100, 'QH2': 15, 'QH3': 15, 'QH4': 15, 'QV4': 15, 'QV5': 15, 'QV6': 15, 'QV8': 15, 'QZ': 15, 'QR': 15, 'VC05': 100, 'VC10': 100, 'VC15': 100, 'VC25': 100, 'VC35': 100, 'VDF10': 100, 'VDF20': 100, 'VDF30': 100, 'VDF40': 100, 'VDF50': 100, 'FXW': 15, 'IX35': 15, 'PF': 15, 'PG46': 15, 'PG48': 15, 'PG49': 15, 'PG50': 15, 'PG51': 15, 'PG52': 15, 'PR51': 15, 'PR53': 15, 'PR55': 15, 'VW20': 100, 'VOZ30W': 100, 'VOZ40W': 100, 'VW20E': 15, 'VW10E': 15, 'VOZ30E': 15, 'VOZ40E': 15, 'LD6': 15, 'LD3': 15, 'TKN05': 100, 'TKN10': 100, 'TKN15': 100, 'RHG80': 15, 'RHG82': 15, 'RHG84': 15, 'RHG87': 15, 'RCW95': 15}

# Nozzle temperature every sample above was qualified at. Uniform 225 because that is what the
# stock Prusament PLA profile ran until 2026-08-05; recorded rather than assumed so the next
# change is visible. A sample printed at a different temperature is a DIFFERENT sample until a
# fit is re-read, in the same way a different infill was.
_QUALIFIED_AT_C = 225

for _s in _S:
    # .get(id, _s.infill) — NOT .get(id). The bare form overwrote every sample that declared
    # its own infill in the constructor with None, because the table below only lists samples
    # that predate the constructor argument. TFH/TFV/TFB declared 15 and RK3 declared 100, and
    # all four read back None: the field added to close the infill confound was quietly dropping
    # the very values it existed to record.
    _s.infill = _INFILL.get(_s.id, _s.infill)
    # `or _QUALIFIED_AT_C` — NOT a bare assignment. The bare form is the same bug the infill
    # table had: it overwrites any sample that declared its own value in the constructor. RK3A is
    # the first sample qualified at 230 and was silently stamped 225 the moment it was added,
    # which is exactly the confound this field exists to make visible.
    _s.nozzle_temp = _s.nozzle_temp or _QUALIFIED_AT_C

SAMPLES = {}
for _s in _S:
    if _s.id in SAMPLES:
        raise RegistryError("duplicate sample id %r" % _s.id)
    SAMPLES[_s.id] = _s
for _s in _S:                      # foreign keys resolve
    for _ref in tuple(_s.supersedes) + ((_s.superseded_by,) if _s.superseded_by else ()):
        if _ref not in SAMPLES:
            raise RegistryError("%s references unknown sample %r" % (_s.id, _ref))
del _S, _s


# ─────────────────────────────────────────────────────────────────────────────
# LAYOUT — the thing that makes "double" vs "triple" a single integer.
# ─────────────────────────────────────────────────────────────────────────────
STUDIO_PITCH = 14.0   # the +/-7 station convention: TF channels, VD fins, PF bores all use it.


def stations(count, pitch=STUDIO_PITCH, center=0.0):
    """Symmetric feature stations for a `count`-up joint.

    The studio convention is +/-7 (pitch 14) and every qualified multi-feature joint uses it —
    TF channels, VD fins, PF bores. Deriving spacing by hand is how a "double dovetail" and a
    "triple dovetail" end up with unrelated geometry.

        stations(2) -> (-7.0, 7.0)          stations(3) -> (-14.0, 0.0, 14.0)
    """
    if not isinstance(count, int) or count < 1:
        raise ValueError("count must be a positive int, got %r" % (count,))
    span = pitch * (count - 1)
    return tuple(round(center - span / 2.0 + i * pitch, 4) for i in range(count))


def span_required(count, pitch=STUDIO_PITCH, feature_w=0.0, edge_margin=0.0):
    """Total width a `count`-up layout consumes, so a spec can be checked against the part."""
    return pitch * (count - 1) + feature_w + 2 * edge_margin


# ─────────────────────────────────────────────────────────────────────────────
# LOOKUP + INVARIANTS — the checks `joint_check.py` runs and generators assert on.
# ─────────────────────────────────────────────────────────────────────────────
def qualified_in(pattern, context, statuses=("qualified",)):
    """Samples of `pattern` proven in `context`. EMPTY is the correct answer for an unproven
    material — never fall back to the PLA numbers (rule R3)."""
    pid = pattern.id if isinstance(pattern, Pattern) else pattern
    return tuple(s for s in SAMPLES.values()
                 if s.pattern.id == pid and s.context == context and s.status in statuses)


def resolve(sample_id):
    """Look up a sample, refusing silently-wrong answers for retired/superseded entries."""
    s = SAMPLES.get(sample_id)
    if s is None:
        raise KeyError("no registry sample %r — a joint without a registry entry is not "
                       "qualified (rule R4)" % (sample_id,))
    return s


def check_amplitude(amp, captured_clearance, strict=True):
    """RULE R1. Returns (ok, message).

    `strict` requires amp < clearance. Non-strict allows equality, which is where the VW20/VDF30
    pairing sits — flagged rather than silently blessed, because amp == clearance leaves zero
    room for the layer-height quantization that R2 warns about.
    """
    if amp is None or captured_clearance is None:
        return False, "R1 needs both a wave amplitude and the joint's captured clearance"
    if amp < captured_clearance:
        return True, "amp %.3f < captured clearance %.3f" % (amp, captured_clearance)
    if amp == captured_clearance and not strict:
        return True, ("amp %.3f EQUALS captured clearance %.3f — allowed but marginal; "
                      "no room for layer quantization" % (amp, captured_clearance))
    return False, ("R1 VIOLATED: wave amp %.3f is not under the captured clearance %.3f — this "
                   "is a geometric jam, the mate cannot lift to cam (the VD R1 failure)"
                   % (amp, captured_clearance))


def retention_location(retention, override=None):
    """Where a retention sample's teeth sit: 'captured' (R1 binds) or 'shoulder' (it does not).

    QZ shoulder teeth live on compression faces OUTSIDE the dovetail and are governed by shoulder
    preload, not by the dovetail's depth clearance — applying R1 to them would reject the
    PASS_PERFECT corner. Waves default to 'captured' precisely because FXW's open-lap amplitude
    got reused inside a captured dovetail and jammed. Override when a wave train genuinely sits
    on an open lap (FXW's qualified application).
    """
    if override is not None:
        return override
    r = retention if isinstance(retention, Sample) else resolve(retention)
    return r.pattern.retention_location or "captured"


# The captured-wave envelope, now bounded on BOTH sides by physical results.
#
#   face interference 0.30, 8 stations over 18mm  -> JAM   (VD R1)
#   face interference 0.20, 8 stations over 18mm  -> JAM   (VD R3, both clearances alike)
#   face interference 0.20, 2 stations over 3.6mm -> BEST  (VD R4, 2026-07-25)
#
# The R3 and R4 arms are the same profile, the same amplitude and the same ZERO face gap; only
# the station count differs. So the governing quantity is NOT interference magnitude — it is how
# many stations cam simultaneously across how much travel (rule R1b). Interference sets the
# per-station force; station count multiplies it.
#
# This is why the earlier "unproven, not proven-bad" branch mattered: had the gate hard-blocked
# everything at 0.20, it would have forbidden the coupon that overturned its own rule.
KNOWN_JAMMING_FACE_INTERFERENCE = 0.20
KNOWN_JAMMING_STATIONS = 4
QUALIFIED_FACE_INTERFERENCE = 0.20     # proven good at...
QUALIFIED_STATIONS = 2                 # ...this many stations (VD R4)


def check_retention(joint, retention, location=None, strict=True):
    """RULE R1, applied to the right surface pair. Returns (ok, message).

    For a captured joint the quantity is FACE INTERFERENCE = ridge amp - face_gap, where face_gap
    is the nominal gap between the two flat faces carrying the train. The joint's depth clearance
    is a DIFFERENT surface pair (fin crest to groove roof) and does not create room on the faces:
    that conflation is what passed the VD R3 coupons through the old check and into a jam.
    """
    j = joint if isinstance(joint, Sample) else resolve(joint)
    r = retention if isinstance(retention, Sample) else resolve(retention)
    where = retention_location(r, location)
    if where not in ("captured", "shoulder"):
        return False, "retention location must be 'captured' or 'shoulder', got %r" % (where,)
    if where == "shoulder":
        return True, ("%s sits on compression shoulders outside %s — R1 does not bind; shoulder "
                      "preload governs, and the coupon is the evidence" % (r.id, j.id))
    if not j.pattern.captured:
        return True, "%s is not a captured joint — the mate can lift to cam" % j.id

    amp = r.m.get("amp") or r.m.get("depth")
    gap = r.m.get("face_gap")
    if gap is None:
        return False, ("%s declares no face_gap, so its captured face interference is unknown. "
                       "It was qualified on an OPEN lap where the parts lift freely; reusing it "
                       "captured is the exact VD R1 mistake (rule R1)." % r.id)
    interference = amp - gap
    if interference <= 0:
        return True, ("face interference %.3f (amp %.3f - gap %.3f) is non-positive: free travel, "
                      "detent only where the divots align" % (interference, amp, gap))
    n = r.m.get("stations")
    long_train = n is None or n >= KNOWN_JAMMING_STATIONS
    if interference >= KNOWN_JAMMING_FACE_INTERFERENCE and long_train:
        return False, ("R1b VIOLATED: face interference %.3f (amp %.3f - face_gap %.3f) across "
                       "%s stations JAMMED physically in VD rounds 1 and 3 — every ridge cams "
                       "simultaneously and the mate cannot pass. The SAME interference over %d "
                       "stations is qualified (VW20E), so shorten the train rather than "
                       "reducing the amplitude"
                       % (interference, amp, gap,
                          n if n is not None else "an undeclared number of", QUALIFIED_STATIONS))
    if (n is not None and n <= QUALIFIED_STATIONS
            and interference <= QUALIFIED_FACE_INTERFERENCE):
        return True, ("face interference %.3f over %d stations is inside the qualified envelope "
                      "(VD R4: 0.20 over 2 stations fit best)" % (interference, n))
    return (not strict), ("face interference %.3f over %s stations sits between the qualified "
                          "envelope (<=%.2f over <=%d) and the known jam (>=%.2f over >=%d) — "
                          "UNPROVEN, so coupon it"
                          % (interference, n, QUALIFIED_FACE_INTERFERENCE, QUALIFIED_STATIONS,
                             KNOWN_JAMMING_FACE_INTERFERENCE, KNOWN_JAMMING_STATIONS))


def check_context(sample, context):
    """RULE R2/R3. A sample used outside its qualified context is unproven, not wrong."""
    if sample.context == context:
        return True, "in qualified context %s" % context.id
    return False, ("%s was qualified on %s, not %s — fits do not transfer across materials, "
                   "printers, or process (rules R2/R3). Re-coupon before use."
                   % (sample.id, sample.context.id, context.id))


def check_orientation(sample, orientation):
    """RULE R2. An orientation change on a mating surface re-opens the coupon gate."""
    if sample.orientation == orientation:
        return True, "printed %s as qualified" % orientation
    return False, ("%s was qualified printed %s, not %s — flat-printed overhung flanks sag "
                   "undersize, standing walls print true plus elephant foot, bed-face voids "
                   "squish at the mouth (rule R2). Re-coupon."
                   % (sample.id, sample.orientation, orientation))


def check_lever_scale(sample, engagement, lever_length, lever_evidence=None):
    """RULE LEVER-SCALE. Slack at a short coupon underestimates slack at a long lever.

    QV5 passed PASS_SNUG on a coupon and showed ~0.6mm of slack on the real 180mm upright at
    20mm engagement — a 9x arm — costing a production reprint and producing VC05.

    WHAT DISCHARGES IT (corrected 2026-07-25, after this check misfired on PCC2):
    an `in-service` basis, OR a declared `lever_evidence` naming what covers the risk. The first
    draft accepted only `in-service`, which is circular whenever the mating geometry has changed:
    "gauge against the real printed part" is impossible when no such part exists yet and printing
    it is the only way to make one. A gate must not demand a precondition that only the gated
    action can create — that turns a real rule into a blocker on the work that would satisfy it.

    `lever_evidence` is deliberately free text, not a boolean: the author must SAY what covers
    the lever, so a reviewer can judge it. Silence still warns.

    Deliberately predicts no slack figure — one data point is not a model.
    """
    if not lever_length or not engagement:
        return True, "no lever declared"
    arm = float(lever_length) / float(engagement)
    if arm < 3.0:
        return True, "lever arm %.1fx is short enough that coupon scale carries" % arm
    if sample.basis == "in-service":
        return True, ("%s was gauged in service, so its %.1fx lever arm is already proven"
                      % (sample.id, arm))
    if lever_evidence:
        return True, ("%.1fx lever on %s-basis evidence, discharged by: %s"
                      % (arm, sample.basis, lever_evidence))
    return False, ("LEVER-SCALE: %s is %s-basis (coupon scale) and drives a %.1fx lever "
                   "(%.0fmm held on %.0fmm of engagement); slack is amplified by that factor at "
                   "the far end. QV5 was coupon-SNUG and lever-LOOSE at 9x, which is why VC05 "
                   "exists. Either gauge against a real printed part, or declare lever_evidence "
                   "saying what covers it (a production-orientation coupon, or a geometry change "
                   "made for this load case)."
                   % (sample.id, sample.basis, arm, float(lever_length), float(engagement)))


def registry_rows(status=None):
    """Flat rows for rendering docs/joinery.md — the doc is generated FROM here."""
    out = []
    for s in sorted(SAMPLES.values(), key=lambda x: (x.pattern.id, x.id)):
        if status and s.status != status:
            continue
        out.append({"sample": s.id, "pattern": s.pattern.id, "status": s.status,
                    "context": s.context.id, "behaviour": s.behaviour,
                    "orientation": s.orientation, "use_when": s.use_when,
                    "measures": dict(s.measures), "evidence": list(s.evidence),
                    "superseded_by": s.superseded_by, "notes": s.notes})
    return out
