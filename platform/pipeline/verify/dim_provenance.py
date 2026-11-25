#!/usr/bin/env python3
"""Dimension truth/provenance contract, independent of CAD conformance.

`verify` can prove geometry matches a nominal. This module asks whether that nominal is entitled to
control a fit. A fit-critical dimension must be measured from the real object/gauge or come from a
published interface standard. Estimated/photo-scaled and placeholder values may build review forms
or gauges, never a purported fitting part — or, when the measurement is the very thing the next
physical iteration exists to produce, may be declared as dated measurement debt (see
DEBT_PROVENANCE) that a prototype may cross and a release may not.
"""
from __future__ import annotations

import argparse
import datetime
import os
from collections import Counter

PROVENANCE_VALUES = ("measured", "standard", "estimated", "placeholder", "pending-measurement")
FIT_TRUSTED = ("measured", "standard")

# MEASUREMENT DEBT on the provenance axis.
#
# `deviation.kind: unavailable` below has admitted dated debt on the REFERENCE axis since 2026-08 —
# declared, reviewed, never mistaken for evidence. Provenance had no equivalent, and the gap
# deadlocked every ORIGINATED part: a fit-critical nominal can only become `measured` by putting
# calipers on a printed article, and handoff.sh refuses at exit 14 to fabricate one while the
# recorded verdict is not PASS. Measure the part you are not allowed to print.
#
# Found 2026-09-06 on a consumer repo's wiper adaptor, which had verified FAIL for its whole life
# on 15 placeholder fit-critical rows — including geometry already printed and bench-fitted that
# August — while three consecutive sessions produced CAD and prose instead of a physical article.
# Recorded as platform-feedback/2026-09-06-fit-critical-provenance-deadlock.yaml. The rule was
# not wrong about the numbers; it had no state for the one moment every originated part must pass
# through.
#
# `pending-measurement` is NOT a source and never joins FIT_TRUSTED. It asserts nothing about the
# value. It says: this nominal is unproven, here is the iteration that closes it, here is the date
# I am held to. A prototype plate may cross it, a release plate may not (handoff.sh), and an overdue
# date fails again — so debt cannot be parked and forgotten, which is the failure mode that would
# make a debt state worse than no debt state at all.
DEBT_PROVENANCE = "pending-measurement"

# Relationship to a reference (A3 of docs/llm-in-the-loop-plan.md). Verification follows the
# relationship, not the repo: a `replicate` dimension is checked against the original, a
# `deviate` one is asserted against intent, and an `originate` one has nothing to compare to.
REFERENCE_VALUES = ("replicate", "deviate", "originate")

# Why a nominal departs from the original. The reason changes what evidence closes it:
#   process      — the original process (injection mould, metal form) differs from FDM
#   material     — modulus/creep/UV/layer anisotropy differs
#   unavailable  — no original to measure; derived from the mate. MEASUREMENT DEBT: next_review
#   correction   — the original is defective in service (e.g. the visor clip's entry gullet)
#   improvement  — a deliberate betterment with no defect to point at
# `intentional` (used once, 2026-08) was the union of correction+improvement and is retired.
DEVIATION_KINDS = ("process", "material", "unavailable", "correction", "improvement")

# A spec that declares any of these is claiming the part MATES WITH SOMETHING. At that point
# "we never wrote down where this number came from" stops being a documentation gap and becomes
# an unanswered question about whether the part fits.
FIT_BEARING_KEYS = ("fits", "joints", "fasteners")

ALLOW_FILENAME = ".spec-truth.allow"


class ProvenanceError(RuntimeError):
    pass


def is_fit_bearing(spec):
    """True when the spec claims a mate. Empty lists do not count — `bom: []` is not a claim."""
    return any(spec.get(key) for key in FIT_BEARING_KEYS)


def read_allow(path):
    """Parse a ratchet file: one path per line, '#' comments, blanks ignored.

    Deliberately stricter than generator_refs.py's parser, which strips the line for the value but
    tests `l.startswith('#')` on the RAW line — so an indented comment is read as an entry and a
    trailing comment is read as part of the path. Both are silent, so neither ever surfaced.
    """
    entries = set()
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                line = line.split("#", 1)[0].strip()
                if line:
                    entries.add(line)
    except OSError:
        return set()
    return entries


def _as_date(value):
    """A YAML date is a `datetime.date`; a quoted one is a string. Accept both, guess neither."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def evaluate_debt(dimension, today):
    """Admit a fit-critical `pending-measurement` row only as DATED, CLOSABLE debt.

    Both conditions carry the whole difference between debt and a placeholder with better PR:
    `closes_with` names the physical iteration that will produce the number, and `next_review` is
    the date on which tolerating it stops. Without them the row is an untrusted nominal wearing a
    word that sounds like a plan, and it fails exactly as `placeholder` does.
    """
    closes_with = dimension.get("closes_with")
    review = dimension.get("next_review")
    if not (isinstance(closes_with, str) and closes_with.strip()):
        return "FAIL", ("fit-critical measurement debt must name the iteration that closes it "
                        "(closes_with)")
    if review is None:
        return "FAIL", ("fit-critical measurement debt requires next_review; "
                        "undated debt is a placeholder")
    due = _as_date(review)
    if due is None:
        return "FAIL", "next_review must be a date (YYYY-MM-DD), got %r" % (review,)
    if due < today:
        return "FAIL", ("measurement debt overdue since %s — take the measurement, or move the "
                        "date with a reason" % due.isoformat())
    return "DEBT", ("unproven; closes with %s, due %s — prototype only, never a release"
                    % (closes_with.strip(), due.isoformat()))


def evaluate_provenance(dimensions, require_recorded=False, today=None):
    """Evaluate the truth of a spec's dimensions.

    `require_recorded` is the fit-bearing rule: when the spec declares a fit, joint or fastener,
    a dimension with NO `provenance:` at all is a FAIL rather than a tolerated legacy row. It is a
    parameter and not the default because `verify.py` evaluates every part on every run and 15
    legacy specs carry 144 unrecorded dimensions between them; the gate that matters is the
    handoff, which passes --require-recorded, so the rule bites where a plate is approved without
    turning the whole back catalogue red.

    `today` is injectable so the overdue-debt rule can be tested without waiting for a date to pass;
    callers leave it alone.
    """
    rows, failed, debt = [], False, []
    counts = Counter()
    today = today or datetime.date.today()
    for dimension in dimensions or []:
        name = dimension.get("name", "<unnamed>")
        raw = dimension.get("provenance")
        critical = dimension.get("fit_critical", False)
        status, message = "INFO", ""
        if not isinstance(critical, bool):
            status, message = "FAIL", "fit_critical must be boolean"
        elif raw is None:
            counts["unrecorded"] += 1
            if critical:
                status, message = "FAIL", "fit-critical dimension has no provenance"
            elif require_recorded:
                status, message = ("FAIL",
                                   "spec declares a fit/joint/fastener, so every dimension must "
                                   "record provenance (measured|standard|estimated|placeholder)")
            else:
                status, message = "UNRECORDED", "legacy/non-fit-critical dimension"
        elif raw not in PROVENANCE_VALUES:
            counts["invalid"] += 1
            status, message = "FAIL", "unknown provenance %r" % raw
        else:
            counts[raw] += 1
            if critical and raw == DEBT_PROVENANCE:
                status, message = evaluate_debt(dimension, today)
            elif critical and raw not in FIT_TRUSTED:
                status = "FAIL"
                message = "fit-critical %s value cannot control a fitting part" % raw
            elif critical:
                status, message = "PASS", "fit-critical source is trusted"
            else:
                status, message = "RECORDED", "non-fit-critical source recorded"
        failed = failed or status == "FAIL"
        if status == "DEBT":
            debt.append(name)
        rows.append({"name": name, "provenance": raw or "unrecorded",
                     "fit_critical": critical, "status": status, "message": message})
    for key in (*PROVENANCE_VALUES, "unrecorded", "invalid"):
        counts.setdefault(key, 0)
    # `passed` means "nothing here FAILS", which is not the same as "everything is proven": a DEBT
    # row passes and is still unproven. Callers that decide whether real material gets cut read
    # `debt` as well — see verify.py's verdict and handoff.sh's release refusal. A caller that reads
    # only `passed` treats debt as tolerated, which is correct for anything short of fabrication.
    return {"passed": not failed, "rows": rows, "counts": dict(counts), "debt": debt}


def evaluate_reference(dimensions):
    """Validate relationship-to-reference declarations. Opt-in: dimensions without `reference:`,
    `deviation:` or `oem_nominal:` are untouched, so every legacy spec stays green.

    A FAIL is a *schema* failure (bad value, missing reason, missing review date, or a declared
    contradiction like oem_nominal with no deviation block) — never a judgement about the values.
    """
    rows, failed = [], False
    for dimension in dimensions or []:
        name = dimension.get("name", "<unnamed>")
        reference = dimension.get("reference")
        deviation = dimension.get("deviation")
        has_decl = reference is not None or deviation is not None or dimension.get("oem_nominal") is not None
        errors = []
        if reference is not None and reference not in REFERENCE_VALUES:
            errors.append("reference must be one of %s (got %r)"
                          % ("|".join(REFERENCE_VALUES), reference))
        if deviation is not None:
            if not isinstance(deviation, dict):
                errors.append("deviation must be a mapping {kind, reason, ...}, not a scalar")
            else:
                kind = deviation.get("kind")
                if kind not in DEVIATION_KINDS:
                    errors.append("deviation.kind must be one of %s (got %r)"
                                  % ("|".join(DEVIATION_KINDS), kind))
                elif kind == "unavailable" and not deviation.get("next_review"):
                    errors.append("deviation.kind 'unavailable' is measurement debt; "
                                  "next_review is required")
                if not deviation.get("reason"):
                    errors.append("deviation requires a recorded reason")
            if reference == "replicate":
                errors.append("declares reference: replicate but carries a deviation block")
        if dimension.get("oem_nominal") is not None and deviation is None:
            errors.append("oem_nominal requires a deviation block explaining why nominal differs")
        status = "FAIL" if errors else ("DECLARED" if has_decl else "UNDECLARED")
        failed = failed or bool(errors)
        rows.append({"name": name, "reference": reference, "status": status,
                     "message": "; ".join(errors)})
    return {"passed": not failed, "rows": rows,
            "declared": sum(1 for row in rows if row["status"] == "DECLARED")}


def require_fit_provenance(dimensions, label="spec"):
    result = evaluate_provenance(dimensions)
    if not result["passed"]:
        details = "; ".join("%s: %s" % (row["name"], row["message"])
                            for row in result["rows"] if row["status"] == "FAIL")
        raise ProvenanceError("%s provenance gate: %s" % (label, details))
    return result


def _summary(counts):
    return " · ".join("%s %d" % (key, counts.get(key, 0))
                      for key in (*PROVENANCE_VALUES, "unrecorded", "invalid"))


def _repo_relative(path):
    """Path relative to the enclosing git work tree, so an allow entry is stable across machines."""
    import subprocess
    absolute = os.path.abspath(path)
    try:
        root = subprocess.run(["git", "-C", os.path.dirname(absolute), "rev-parse",
                               "--show-toplevel"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return absolute
    return os.path.relpath(absolute, root) if root else absolute


def _default_allow(spec_path):
    import subprocess
    try:
        root = subprocess.run(["git", "-C", os.path.dirname(os.path.abspath(spec_path)),
                               "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return os.path.join(root, ALLOW_FILENAME) if root else None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    parser.add_argument("--require-recorded", action="store_true",
                        help="a spec declaring fits/joints/fasteners fails on any dimension with "
                             "no provenance; ratcheted by --allow")
    parser.add_argument("--allow", default=None,
                        help="ratchet file of spec paths exempt from --require-recorded "
                             "(default: %s at the git root)" % ALLOW_FILENAME)
    args = parser.parse_args(argv)
    # Say whether THIS run is the gate. Imported lazily and inside main() so the module stays
    # cheap for the callers that import it as a library rather than run it.
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.realpath(__file__)), ".."))
    import gates as _gates
    _gates.declare_mode("PROVENANCE_RESULT", argv if argv is not None else _sys.argv[1:])
    try:
        import yaml
        with open(args.spec) as stream:
            spec = yaml.safe_load(stream) or {}
        require = args.require_recorded and is_fit_bearing(spec)
        exempt = False
        if require:
            allow_path = args.allow or _default_allow(args.spec)
            if allow_path:
                exempt = _repo_relative(args.spec) in read_allow(allow_path)
            require = not exempt
        result = evaluate_provenance(spec.get("dimensions") or [], require_recorded=require)
        reference = evaluate_reference(spec.get("dimensions") or [])
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print("  [FAIL] cannot read spec provenance:", exc)
        print("PROVENANCE_RESULT: FAIL")
        return 1
    if args.require_recorded:
        if exempt:
            print("  [DEBT] %s is on the %s ratchet — the fit-bearing rule is NOT enforced here. "
                  "Backfill provenance and delete the line." % (_repo_relative(args.spec),
                                                                ALLOW_FILENAME))
        elif not is_fit_bearing(spec):
            print("  [NOTE] spec declares no fits/joints/fasteners; the fit-bearing rule does not apply")
    print("dimension provenance:", _summary(result["counts"]))
    for row in result["rows"]:
        if row["status"] in ("FAIL", "PASS", "DEBT"):
            print("  [%s] %-28s %-11s fit_critical=%s — %s" %
                  (row["status"], row["name"], row["provenance"],
                   str(row["fit_critical"]).lower(), row["message"]))
    if reference["declared"] or not reference["passed"]:
        print("reference relationship: %d declared" % reference["declared"])
        for row in reference["rows"]:
            if row["status"] == "FAIL":
                print("  [FAIL] %-28s %s" % (row["name"], row["message"]))
        print("REFERENCE_RESULT:", "PASS" if reference["passed"] else "FAIL")
    # Two tokens, one meaning each. PROVENANCE_RESULT answers "does anything here FAIL", which is
    # what handoff.sh:334 has always greped for and what exit 12 means; declared debt does not fail,
    # so that line and that gate keep their existing behaviour exactly. PROVENANCE_DEBT is the
    # separate question — "what on this spec is admitted as unproven" — and it is what the release
    # refusal reads. Folding debt into the first token would have silently turned exit 12 into a
    # second, differently-worded copy of the deadlock this state exists to break.
    if result["debt"]:
        print("PROVENANCE_DEBT:", " ".join(result["debt"]))
    print("PROVENANCE_RESULT:", "PASS" if result["passed"] else "FAIL")
    return 0 if (result["passed"] and reference["passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
