"""Material and process context — the shared dimension of every qualified measure.

Extracted from `joints.py` because it is not joint-specific: a side-entry captive-nut pocket, a
debossed label, and a dovetail clearance are all qualified *in a context*, and all three rot the
same way if that context is dropped. Joints were simply the first schema to need it.

This is the "dimension table" the rest of the registry references. It is deliberately tiny and
dependency-free — `fastener_check.py` and `joint_check.py` both import it under `freecadcmd`,
which has no cadquery.

    Material  ── the polymer's RECORDED behaviour (creep, friction, profile status)
    Context   ── (printer, material, nozzle, layer_h): the process a measure was proven on

Nothing here is a spec-sheet value. Every field is something this bench actually observed or a
status this bench actually holds, so a designer reading it gets evidence, not marketing.
"""


class RegistryError(Exception):
    """Raised at import when the registry itself is inconsistent."""


class Material:
    __slots__ = ("id", "name", "klass", "creep", "friction_on_glass", "profile_status", "notes")

    def __init__(self, id, name, klass, creep, friction_on_glass, profile_status, notes=""):
        self.id, self.name, self.klass = id, name, klass
        self.creep, self.friction_on_glass = creep, friction_on_glass
        self.profile_status, self.notes = profile_status, notes

    @property
    def printable(self):
        """False when no filament profile exists — nothing can be qualified in it yet."""
        return self.profile_status != "NO-PROFILE-YET"

    def __repr__(self):
        return "Material(%s)" % self.id


PLA = Material(
    "PLA", "Prusament PLA", klass="rigid", creep="yes-under-sustained-load",
    friction_on_glass="low", profile_status="qualified",
    notes="Every joint in the registry is qualified in PLA. Creeps under 24/7 load — the "
          "bottle-cradle fork-A rejection.")
PCTG = Material(
    "PCTG", "PCTG", klass="rigid", creep="less-than-PLA",
    friction_on_glass="low", profile_status="available-no-joint-coupon",
    notes="Preferred over PLA where load is sustained (b2b cradle seat). NO joint or fastener "
          "sample has been qualified in PCTG — every fit must be re-couponed before reuse.")
PETG = Material(
    "PETG", "Overture PETG", klass="rigid", creep="less-than-PLA",
    friction_on_glass="low", profile_status="qualified",
    notes="Prints on Prusa's vendor profile `Overture PETG @COREONE HF0.4` (PrusaResearch.ini), on "
          "the fitted HF0.4: the gutter backstop's clip (2026-09-18, 'the petg clip fits nicely'), "
          "the PVC spool rack's rungs (2026-09-20), its SC7 pin ladder and fr2 rungs. Registered "
          "2026-08-26 as NO-PROFILE-YET (on the shelf, never printed); corrected 2026-10-08 when the "
          "touge road went PETG. The first PETG joints were registered 2026-11-11: the road's push "
          "tabs (TR6-1), its ribbed post sockets (TR7-2) and its battery box's click tabs (TR8-3). "
          "PLA's fit numbers do not carry over: a body that slides free at 0.12 a side in PLA "
          "needs 0.25 in PETG (tr6-i1, all too tight). Same glycol-modified copolyester family as "
          "PCTG; tougher and more heat-tolerant than PLA, about 40 % less stiff.")
SUNLU_TPU_95A = Material(
    "SUNLU-TPU-95A", "SUNLU TPU 95A", klass="compliant", creep="high-in-free-flexure",
    friction_on_glass="high", profile_status="starter-no-joint-coupon",
    notes="Project-local starter profile exists (SUNLU page: TPU95A 190-210C at 50-80mm/s or "
          "210-230C at 80-120mm/s; plate 50-60C; bench start 210C/55C/2.5mm3s cap). No physical "
          "observation or fit coupon has qualified it.")
TPU_95A = Material(
    "TPU-95A", "TPU 95A", klass="compliant", creep="high-in-free-flexure",
    friction_on_glass="high", profile_status="starter-no-joint-coupon",
    notes="Project-local SUNLU TPU 95A @COREONE starter profile exists (210C/55C/2.5mm3s cap, "
          "from SUNLU's product ranges), but no physical observation or fit coupon has qualified it. "
          "Rigid-fit clearances are meaningless here; compliant features are coupon-only, not "
          "CAD-predictable.")

MATERIALS = {m.id: m for m in (PLA, PCTG, PETG, TPU_95A, SUNLU_TPU_95A)}


class Context:
    __slots__ = ("printer", "material", "nozzle", "layer_h", "status", "notes")

    def __init__(self, printer, material, nozzle, layer_h, status="active", notes=""):
        if material not in MATERIALS:
            raise RegistryError("unknown material %r" % material)
        self.printer, self.material = printer, material
        self.nozzle, self.layer_h = nozzle, layer_h
        self.status, self.notes = status, notes

    @property
    def id(self):
        return "%s/%s/%.1f/%.2f" % (self.printer, self.material, self.nozzle, self.layer_h)

    @property
    def mat(self):
        return MATERIALS[self.material]

    def __eq__(self, other):
        return isinstance(other, Context) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return "Context(%s)" % self.id


CORE_ONE_PLA = Context("core-one", "PLA", 0.4, 0.20,
                       notes="The qualified context. Everything is proven here unless said.")
CORE_ONE_PCTG = Context("core-one", "PCTG", 0.4, 0.20, status="unqualified",
                        notes="No joint or fastener coupon run in PCTG yet.")
CORE_ONE_TPU95A = Context("core-one", "SUNLU-TPU-95A", 0.4, 0.20, status="unqualified",
                          notes="SUNLU TPU has a project-local starter profile but no physical "
                                "observation/fit coupon has passed on this bench.")
CORE_ONE_TPU95A_010 = Context("core-one", "SUNLU-TPU-95A", 0.4, 0.10,
                              notes="The touge road's line strips (TR3S i7-i9, 2026-10-07): 0.10 layers "
                                    "(first 0.20), solid rectilinear, 210 C (first layer 215), printed "
                                    "flange-down. Only the T strip is qualified here.")
CORE_ONE_PETG = Context("core-one", "PETG", 0.4, 0.20,
                        notes="The touge road's recipe: Overture PETG @COREONE HF0.4 on the HF0.4 nozzle, "
                              "0.20 BALANCED, 250 C, 3 perimeters, adaptive cubic 15 %. TR6 and TR8 were "
                              "proven here.")
CORE_ONE_PETG_015 = Context("core-one", "PETG", 0.4, 0.15,
                            notes="The same recipe at 0.15 BALANCED (first layer 0.20): TR7's posts and "
                                  "sockets. A face built by layers ends 0.05 lower than at 0.20.")
K1C_PLA = Context("k1c", "PLA", 0.4, 0.20, status="retired",
                  notes="Printer is gone (2026-07). Legacy rows only; do not qualify new work.")

CONTEXTS = {c.id: c for c in (CORE_ONE_PLA, CORE_ONE_PCTG, CORE_ONE_PETG, CORE_ONE_PETG_015,
                                       CORE_ONE_TPU95A, CORE_ONE_TPU95A_010, K1C_PLA)}


def context_from(decl):
    """Build a Context from a spec's ``context:`` mapping. Returns (context, error_message)."""
    if not isinstance(decl, dict):
        return None, "context must be a mapping of printer/material/nozzle/layer_h"
    try:
        return Context(decl["printer"], decl["material"],
                       float(decl["nozzle"]), float(decl["layer_h"])), None
    except KeyError as exc:
        return None, "context missing %s" % exc
    except Exception as exc:                       # unknown material, non-numeric nozzle/layer
        return None, "context invalid: %s" % exc


def material_advisories(ctx, sustained_load=False):
    """Recorded material facts that bear on ANY qualified feature in this context.

    Surfaces what the bench already learned at the point of decision, instead of relying on
    someone remembering it. Returns a list of (severity, message).
    """
    out = []
    mat = ctx.mat
    if not mat.printable:
        out.append(("FAIL", "%s has no filament profile on this bench yet (%s) — nothing can be "
                            "qualified in it until that exists"
                    % (mat.id, mat.profile_status)))
    if ctx.status == "retired":
        out.append(("WARN", "context %s is retired hardware" % ctx.id))
    elif ctx.status == "unqualified":
        out.append(("WARN", "%s: %s" % (ctx.id, mat.notes)))
    if sustained_load and mat.creep.startswith("yes"):
        out.append(("WARN", "%s creeps under sustained load — a joint or fastener holding a "
                            "constant load will relax over weeks (the cradle fork-A lesson); "
                            "PCTG creeps less" % mat.id))
    return out
