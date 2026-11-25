#!/usr/bin/env python3
"""adoption.py — how much of this platform's machinery is actually switched on.

WHY THIS EXISTS
The 2026-08-21 audit found the same defect at every gate: the mechanism existed, was tested, was
documented — and nothing used it. Dimension provenance was recorded on 0 of 16 specs. The solid
probe library was imported by 1 of 84 generators. The revision model's `green/*` and `passed/*`
tags had never been created, not once. Every one of those landed green and stayed at zero, and
nobody could see it, because a test suite answers "does the mechanism work?" and never "is anyone
using it?".

So this counts adoption, and prints it at the bottom of the command already run on every
checkpoint and every land. It is a THERMOMETER, NOT A GATE: it exits 0 always and blocks nothing.
Making it fail would be one more mechanism to route around; making it visible is the point.

Read the DEBT lines as the ones that should shrink, and the ratios as the ones that should grow.
A ratio that has not moved in a month is a mechanism nobody wanted.

Usage: adoption.py [repo_root]        always exits 0
"""
from __future__ import annotations

import os
import re
import subprocess
import sys


_EXCLUDED_DIRS = {".git", "build", "vendor", "research", "__pycache__", "_TEMPLATE"}
_AI_GENERATED_DIRS = {"corpus", "index", "out", "results"}


def _prune_dirs(root, base, dirs):
    """Keep generated/local AI artifacts out of repository-adoption counts.

    ``platform/ai/corpus`` can contain complete, locally generated example parts with ``src/`` and
    ``spec.yaml``. Counting those makes the ledger depend on one operator's ignored files; the audit
    host had 12 such examples. They measure corpus construction, not adoption by a printable
    repository part.
    """
    kept = [d for d in dirs if d not in _EXCLUDED_DIRS and not d.startswith(".venv")]
    if os.path.realpath(base) == os.path.realpath(os.path.join(root, "platform", "ai")):
        kept = [d for d in kept if d not in _AI_GENERATED_DIRS]
    return kept


def _run(args, cwd):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
        return out.stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def _specs(root):
    """Every spec.yaml that belongs to a part, wherever it lives.

    Deliberately not `parts/*/*/spec.yaml`: decor/topo-coaster is a registered, verified part that
    sits outside parts/, and every count in the audit that used that glob silently missed it.
    """
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = _prune_dirs(root, base, dirs)
        if "spec.yaml" in files:
            found.append(os.path.join(base, "spec.yaml"))
    return sorted(found)


def _generators(root):
    """Every authored generator, wherever it sits under a src/ tree.

    The first version required basename(dir) == "src", which silently dropped the 15 generators in
    revision subdirectories (parts/lighting/bottle-lamp-base/src/b1/… and friends) and everything
    under decor/. A ledger whose denominator is wrong is worse than no ledger, because it reports
    progress that is really a shrinking sample.
    """
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = _prune_dirs(root, base, dirs)
        if os.sep + "src" not in base + os.sep:
            continue
        out += [os.path.join(base, f) for f in files if f.endswith(".py")]
    return sorted(out)


def _read(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return stream.read()
    except OSError:
        return ""


def _load(path):
    """One malformed spec.yaml used to blank the WHOLE ledger via the outer except. Count it as
    unparseable and keep going — a broken spec is a fact worth printing, not a reason to go dark."""
    import yaml
    try:
        return yaml.safe_load(_read(path)) or {}, None
    except yaml.YAMLError as exc:
        return {}, str(exc).splitlines()[0] if str(exc) else "unparseable"


def collect(root):
    import yaml

    rows = []
    specs = _specs(root)
    parsed, broken = {}, []
    for path in specs:
        data, err = _load(path)
        parsed[path] = data
        if err:
            broken.append((path, err))

    def spec_dims(path):
        return parsed.get(path, {}).get("dimensions") or []

    dims = [d for path in specs for d in spec_dims(path)]

    def needs_probes(path):
        spec = parsed.get(path, {})
        return bool(spec.get("fit_core") or spec.get("joints") or spec.get("fasteners")
                    or any(isinstance(d, dict) and d.get("fit_critical")
                           for d in spec_dims(path)))

    probe_required = [s for s in specs if needs_probes(s)]
    probe_covered = [s for s in probe_required if parsed.get(s, {}).get("probes")]
    rows.append(("fit-bearing specs declaring B-rep probes",
                 len(probe_covered), len(probe_required)))

    fully = [s for s in specs
             if spec_dims(s) and all(d.get("provenance") for d in spec_dims(s))]
    rows.append(("specs with provenance on every dimension", len(fully), len(specs)))
    rows.append(("dimensions carrying provenance",
                 sum(1 for d in dims if d.get("provenance")), len(dims)))
    rows.append(("dimensions declared fit_critical",
                 sum(1 for d in dims if d.get("fit_critical")), len(dims)))
    rows.append(("dimensions with a machine measure: recipe",
                 sum(1 for d in dims if d.get("measure")), len(dims)))

    design_specs = [s for s in specs if isinstance(parsed.get(s, {}).get("design"), dict)]
    rows.append(("specs declaring Restore/Originate design intent",
                 len(design_specs), len(specs)))
    non_draft = [s for s in specs if parsed.get(s, {}).get("status") in
                 {"printed", "dim-verified", "released"}]
    status_linked = [s for s in non_draft
                     if isinstance(parsed.get(s, {}).get("qualification"), dict)
                     and parsed[s]["qualification"].get("current")]
    rows.append(("non-draft specs naming a physical evidence record",
                 len(status_linked), len(non_draft)))

    # Prospective only: these records exist for prints attempted after the qualification contract
    # was adopted. Their absence does not rewrite or downgrade archived prints.
    qdir = os.path.join(root, "platform", "pipeline", "verify")
    if os.path.isfile(os.path.join(qdir, "qualification_check.py")):
        if qdir not in sys.path:
            sys.path.insert(0, qdir)
        from qualification_check import collect_metrics
        metrics = collect_metrics(root)
        rows.append(("structured future print/coupon iterations", metrics["records"], None))
        rows.append(("human-evaluated future iterations", metrics["evaluated"],
                     metrics["records"]))
        rows.append(("first-pass full-part successes", metrics["first_pass_parts"],
                     metrics["parts_with_full_attempts"]))
        rows.append(("repeated recorded failure classes", metrics["repeated_failure_count"], None))

    gens = _generators(root)
    probe = [g for g in gens if re.search(r"^\s*from probe import|^\s*import probe",
                                          _read(g), re.M)]
    rows.append(("generators importing parts/_lib/probe.py", len(probe), len(gens)))
    reads_spec = [g for g in gens if "spec.yaml" in _read(g)]
    rows.append(("generators that read their own spec.yaml", len(reads_spec), len(gens)))

    index = yaml.safe_load(_read(os.path.join(root, "parts", "index.yaml"))) or {}
    listed = [p.get("id") for p in (index.get("parts") or []) if p.get("id")]

    def resolve(part_id):
        """A part id is not always parts/<id>: decor/topo-coaster is registered in the index and
        lives at the repo root. Looking only under parts/ reported it as spec-less when it has one."""
        for candidate in (os.path.join(root, "parts", part_id), os.path.join(root, part_id)):
            if os.path.exists(os.path.join(candidate, "spec.yaml")):
                return candidate
        return None

    with_spec = [p for p in listed if resolve(p)]
    rows.append(("parts in index.yaml that have a spec.yaml", len(with_spec), len(listed)))
    # The other direction, which nothing measured: a part with a spec that the manifest never
    # lists is invisible to every consumer that enumerates from index.yaml.
    indexed_dirs = {resolve(p) for p in listed if resolve(p)}
    unindexed = [s for s in specs if os.path.dirname(s) not in indexed_dirs]
    rows.append(("specs registered in parts/index.yaml",
                 len(specs) - len(unindexed), len(specs)))

    def has_step(spec_path):
        step_dir = os.path.join(os.path.dirname(spec_path), "step")
        if not os.path.isdir(step_dir):
            return False
        return any(f.endswith(".step") for f in os.listdir(step_dir))

    with_step = [s for s in specs if has_step(s)]
    rows.append(("parts whose B-rep validity is provable (has a STEP)", len(with_step), len(specs)))

    tags = _run(["git", "tag"], root).split()
    rows.append(("green/* tags — digital loop pinned", len([t for t in tags if t.startswith("green/")]), None))
    rows.append(("passed/* tags — physical gate pinned", len([t for t in tags if t.startswith("passed/")]), None))

    debt = []
    allow = os.path.join(root, ".spec-truth.allow")
    if os.path.exists(allow):
        debt.append(("specs on the .spec-truth.allow ratchet",
                     len([l for l in _read(allow).splitlines()
                          if l.split("#", 1)[0].strip()])))
    refs = os.path.join(root, "platform", "pipeline", "verify", "generator_refs.allow")
    if os.path.exists(refs):
        debt.append(("entries on the generator_refs.allow ratchet",
                     len([l for l in _read(refs).splitlines()
                          if l.strip() and not l.strip().startswith("#")])))
    spec_source = os.path.join(root, "platform", "pipeline", "verify", "spec_source_check.py")
    if os.path.exists(spec_source):
        out = _run([sys.executable, spec_source, root, "--count-only"], root)
        if out.strip().isdigit():
            debt.append(("active spec-vs-source constant conflicts", int(out.strip())))
        allow = os.path.join(root, ".spec-source.allow")
        if os.path.exists(allow):
            debt.append(("entries on the .spec-source.allow ratchet",
                         len([l for l in _read(allow).splitlines()
                              if l.split("#", 1)[0].strip()])))
    return rows, debt, broken


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = argv[0] if argv else _run(["git", "rev-parse", "--show-toplevel"], ".").strip() or "."
    try:
        rows, debt, broken = collect(root)
    except Exception as exc:                                  # never break the suite over a count
        print("adoption: could not measure (%s: %s)" % (type(exc).__name__, exc))
        print("  the ledger is advisory, so this does not fail the run — but it is now blind.")
        return 0

    print("\n=== adoption — is the machinery switched on? (counts only, blocks nothing) ===")
    for label, have, total in rows:
        if total is None:
            print("  %-52s %s" % (label, have))
        else:
            pct = (100.0 * have / total) if total else 0.0
            print("  %-52s %3d/%-3d  %3.0f%%" % (label, have, total, pct))
    for label, count in debt:
        print("  %-52s %3d      DEBT — this number should only fall" % (label, count))
    for path, err in broken:
        print("  [UNPARSEABLE] %s — %s" % (os.path.relpath(path, root), err))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
