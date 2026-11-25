"""Render the registry table in `docs/joinery.md` FROM `joints.py`.

`joints.py` is authoritative; the doc is its mirror. Prose (architecture, rationale, coupon
protocol) stays hand-written outside the markers — only the numbers are generated, because
numbers are what drift.

    python3 parts/_lib/render_registry.py          # rewrite the block in place
    python3 parts/_lib/render_registry.py --check   # exit 1 if the doc is stale
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from joints import MATERIALS, SAMPLES, UNKNOWN  # noqa: E402
from rules import RULES, rules_for  # noqa: E402

BEGIN = "<!-- BEGIN GENERATED REGISTRY — edit parts/_lib/joints.py, then run render_registry.py -->"
END = "<!-- END GENERATED REGISTRY -->"

DOC = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "..", "docs", "joinery.md"))

# Which measures to surface per pattern, in the order a human reads them.
_SHOW = {
    "TRIANGLE_KEY": ("mid_w", "tip_w", "interference", "key_len", "taper_len", "tight_zone"),
    "TRIANGLE_CHANNEL": ("base_w", "height", "depth", "skin", "section_t"),
    "DOVETAIL": ("width_clearance", "depth_clearance"),
    "SHOULDER_RATCHET": ("pitch", "groove_w", "land", "depth", "phase"),
    "WAVE_TRAIN": ("amp", "width", "pitch"),
    "TWIN_DOVETAIL": ("neck", "crest", "proud", "width_clearance", "depth_clearance"),
    "SPIRAL_DOWEL": ("peg_d", "bore_d", "interference", "length", "groove_depth"),
}
_ORDER = ("qualified", "coupon-gate", "reference", "superseded", "rejected")


def _measures(s):
    keys = _SHOW.get(s.pattern.id, tuple(sorted(s.measures)))
    return " · ".join("%s %s" % (k, _fmt(s.measures[k])) for k in keys if k in s.measures)


def _fmt(v):
    if v is UNKNOWN:
        return "*not recorded*"
    if isinstance(v, float):
        return ("%.3f" % v).rstrip("0").rstrip(".")
    return str(v)


def render():
    out = [BEGIN, ""]
    out.append("> Generated from `parts/_lib/joints.py` — **do not hand-edit this block.**")
    out.append("> A sample is a *(pattern × context)* qualification: the numbers below are only")
    out.append("> valid in the context column. `qualified_in(PATTERN, CONTEXT)` returns nothing")
    out.append("> for an unproven material rather than handing back these values.")
    out.append("")
    out.append("**Materials on record**")
    out.append("")
    out.append("| Material | Class | Creep | Friction on glass | Profile |")
    out.append("|---|---|---|---|---|")
    for m in MATERIALS.values():
        out.append("| **%s** | %s | %s | %s | %s |"
                   % (m.id, m.klass, m.creep, m.friction_on_glass, m.profile_status))
    out.append("")
    for status in _ORDER:
        rows = [s for s in SAMPLES.values() if s.status == status]
        if not rows:
            continue
        out.append("**%s**" % status.upper())
        out.append("")
        out.append("| Sample | Pattern | Context | Infill | Key measures | Behaviour | Basis | Print | Use when |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for s in sorted(rows, key=lambda x: (x.pattern.id, x.id)):
            use = s.use_when or (("→ %s" % s.superseded_by) if s.superseded_by else "—")
            basis = s.basis + ("(%d)" % s.cycles if s.cycles else "")
            out.append("| **%s** | %s | %s | %s | %s | %s | %s | %s | %s |"
                       % (s.id, s.pattern.id, s.context.id,
                          ("%d%%" % s.infill) if s.infill else "—",
                          _measures(s), s.behaviour, basis, s.orientation, use))
        out.append("")
    out.append("**Learned rules** — full structure in `parts/_lib/rules.py`. The `naive fix`")
    out.append("column is the trap: what you would otherwise reach for, and why it fails.")
    out.append("")
    out.append("| Rule | Scope | Gated | What actually governs it | The naive fix that fails |")
    out.append("|---|---|---|---|---|")
    for r in sorted(RULES.values(), key=lambda x: (x.scope, x.id)):
        gated = "yes (`%s`)" % r.gate if r.enforcement == "gated" else "advisory"
        naive = (r.naive_fix or "—").replace("\n", " ")
        out.append("| **%s** %s | %s | %s | %s | %s |"
                   % (r.id, r.title, r.scope, gated, r.governing, naive))
    out.append("")
    out.append(END)
    return "\n".join(out)


def splice(doc_text, block):
    if BEGIN not in doc_text or END not in doc_text:
        raise SystemExit("markers not found in docs/joinery.md — add %s / %s" % (BEGIN, END))
    head = doc_text.split(BEGIN)[0]
    tail = doc_text.split(END, 1)[1]
    return head + block + tail


def main(argv):
    with open(DOC) as fh:
        current = fh.read()
    updated = splice(current, render())
    if "--check" in argv:
        if current != updated:
            print("docs/joinery.md is STALE — run: python3 parts/_lib/render_registry.py")
            return 1
        print("docs/joinery.md matches the registry")
        return 0
    with open(DOC, "w") as fh:
        fh.write(updated)
    print("rendered %d samples into docs/joinery.md" % len(SAMPLES))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
