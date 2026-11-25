#!/usr/bin/env python3
"""spec_primary_check.py — the artifact a part is verified against may not be gitignored, and may
not be absent.

WHY
`primary_stl` / `primary_step` name the artifact the rest of the pipeline treats as THE part:
verify.py:125-126 reads them for the B-rep verdict, and A1's stamped verdict is keyed on that
STEP's bytes. Seven specs named a `--draft-` variant as their primary, and `.gitignore:102-109`
untracks that whole namespace, so one one-line spec edit produced three failures at once: no
tracked STEP (B-rep validity UNPROVEN, and nothing said so), no DFM (verify.sh:20 skips
`*--draft-*` by name), and a "released" artifact a clean clone cannot rebuild. Nothing reported
any of it — the drafts were on the author's disk, so every local run looked fine.

This is the ratchet that makes that edit visible the same day. It is not the fix; A3 is.

ASK GIT, DO NOT RE-IMPLEMENT .gitignore
`.gitignore:100-101` records what a hand-written rule costs: `parts/**/stl/*--draft-*.stl` does
not match a nested directory, so 202 draft variants in `stl/coil-set/` and `stl/b2b-r4/` stayed
tracked while everyone believed they were not. A regex here would repeat that, and would also miss
the `--opt[0-9]` / `--test[0-9]` / `--proto` infixes that share the namespace. One
`git check-ignore --stdin` over every resolved path settles all four for the price of one process.

`--no-index` is deliberate. Without it git answers "is this path ignored *given the index*", so a
file force-added before a rule landed reports clean — which is exactly the 202-file state, and it
would make this gate's verdict depend on local index history. The question here is whether the
path lives in the regenerable-and-untracked namespace, and it does whether or not one copy slipped
into the index: verify.sh:20 skips DFM on the NAME, not on tracking.

`-v` PRINTS NEGATED PATTERNS TOO, AND THEY MEAN THE OPPOSITE
Reading every `-v` line as "ignored" is wrong, and this repo has the counter-example on disk:
`.gitignore:131-137` re-includes `!**/releases/**/*.stl` etc., because `.gitignore:97` makes a
shipped revision an immutable record rather than a rebuild. Measured on this tree, 2026-09-04:
`git check-ignore --no-index -v -z` on `parts/media/disc-tower-e1/releases/r1/stl/x--draft-a.stl`
prints ``.gitignore:131 `!**/releases/**/*.stl` `` for a path git does NOT ignore. Worse, the exit
code cannot be used to tell the difference — `-q` on that path is rc 1 ("none are ignored") while
`-v` on the same path is rc 0, because -v counts "matched a pattern", negated or not, and the man
page's EXIT STATUS text does not say so. The `!` on the pattern is the only signal there is, so
`!`-prefixed matches are dropped. Without that, a shipped revision named as a primary is refused
with a re-include rule quoted as the reason a clone will not have it — the sort of message that
teaches people to stop reading refusals.

THE PATH WE ASK ABOUT IS THE DECLARED ONE, NOT ITS SYMLINK TARGET
`os.path.realpath` here would have been an evasion: a symlink named `x--draft-a.stl` pointing at a
released `x.stl` resolves to a clean path, so the gate passed (measured 2026-09-04) while git's own
verdict on the declared name was IGNORED — and it is the declared name a clone does not get, since
the link itself matches the rule. `.gitignore` matching is lexical, so the question is asked
lexically: `normpath`, never `realpath`. Existence still follows the link, which is right — a
dangling primary is MISSING.

A MISSING primary is the same defect wearing different clothes — a spec pointing at geometry that
is not there — so it blocks too, and the report names which of the two (or both) applies.

AN UNDECLARED PRIMARY IS NOT AN ABSENT ONE — IT IS AN IMPLICIT ONE
The first cut of this gate passed the 13 specs that declare no primary and said so in the summary.
That is the door the whole failure class walks through: verify.py:125-126 does not skip a part with
no `primary_step`, it falls back to `_pick()`, and `_pick` takes the FIRST non-coupon file in
`step/` — draft or not. Measured 2026-09-04 against Justin's working checkout: five parts that
declare nothing (`bottle-lamp-base`, `bottle-lamp-stopper`, `body-outline-pen-holder`,
`market-card-rack`, `photo-calibration-corner`) resolve to a `--draft-` STL *and* STEP that way,
with every consequence above and no line of output about it. `bottle-lamp-carrier` is on the plan's
list of seven offenders and declares nothing on this branch, so a gate that only reads declarations
cannot see the very part it was written for. And `parts/_TEMPLATE/spec.yaml` declares no primary
either — so "undeclared" is the state every new part is born in, and coverage would decay toward
zero as parts are added.

So the fallback is resolved and checked with the same authority, per key (verify.py falls back one
key at a time — `window-fan-adapter` declares only `primary_stl`). It is reported as a distinct
offense with its own fix, because the action differs: declare a tracked primary, rather than rename
one. Declaring nothing remains legal; declaring nothing *while the only export is a draft* does not.

NO ALLOW-LIST, BY DIRECTIVE
Justin, 2026-09-03: "those ones that were done in the past without a geometric check or verify were
errors that got through without checking ... we don't want to make exceptions for past parts."
There is no `.allow` file, no seeded ratchet, no skipped slug, and none should be added. On run one
this goes RED on `disc-tower-e1`, `market-card-rack-lf-coupon` and `social-media-sign` (measured on
`perf/pipeline-speed`, 2026-09-03) — that is the check working on the day it lands, not a bug and
not a reason for a hatch. Those three are being fixed under A3, on a revision branch, because
regenerating geometry is not a pipeline change.

FINDING NOTHING IS NOT PASSING
An empty corpus used to print "0 spec(s)" and then PASS. This repo's recorded disease is machinery
that nobody adopts — a provenance gate at 0/16 specs, `green/*` tags at 0 created — and a green
line over an empty list is how a gate joins that list without anyone noticing. Zero specs is a FAIL.

Usage: python3 platform/pipeline/verify/spec_primary_check.py [root]   exit 0 = clean, 1 = defects
"""
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))

PRIMARY_KEYS = ("primary_stl", "primary_step")
# (key, verify.py's _pick() sub-directory, extension) — the fallback verify.py:125-126 takes.
FALLBACK_SOURCES = (("primary_stl", "stl", ".stl"), ("primary_step", "step", ".step"))

# Only dirs that cannot hold a part's spec.yaml. `_TEMPLATE` is NOT pruned: parts/clips/hose-clip
# is a verbatim copy of the template, so a defect seeded there ships into the next part.
_PRUNE = {".git", "__pycache__", "node_modules"}

FIX = {
    "declared": ("rename the variant out of the draft/opt/test/proto namespace in spec.yaml AND in",
                 "the generator's VARIANTS key, regenerate, then commit the export (plan A3)"),
    "fallback": ("declare %s in spec.yaml naming an artifact a clone gets, or promote this",
                 "variant out of the draft/opt/test/proto namespace and commit it (plan A3)"),
}


def find_specs(root):
    """Every parts/**/spec.yaml (and examples/**/spec.yaml) under root, sorted. Accepts a repo root or a single part dir."""
    roots = [d for d in (os.path.join(root, "parts"), os.path.join(root, "examples")) if os.path.isdir(d)]
    if not roots:
        roots = [root]
    found = []
    for base in roots:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _PRUNE]
            if "spec.yaml" in filenames:
                found.append(os.path.join(dirpath, "spec.yaml"))
    return sorted(found)


# Byte-for-byte verify.py:114-120. Duplicated rather than imported because verify.py imports
# FreeCAD's Part/Mesh at module scope and this stage runs under plain python3 in test.sh; the
# drift verify.sh:20-22 warns about is held off by test_pick_mirrors_verify_py, which compares
# both ASTs and fails the moment verify.py's rule changes.
def _pick(part_dir, sub, ext):
    d = os.path.join(part_dir, sub)
    if not os.path.isdir(d):
        return None
    cands = sorted(f for f in os.listdir(d)
                   if f.lower().endswith(ext) and "coupon" not in f.lower() and not f.startswith("_"))
    return os.path.join(d, cands[0]) if cands else None


def declared_primaries(spec_path):
    """-> ({key: value}, error_or_None) for the primary keys this spec actually sets."""
    import yaml
    # libyaml when the build has it: 177 ms -> 15.9 ms over this repo's 19 specs (re-measured
    # 2026-09-04), identical parse on every one and the same ParserError on a malformed spec.
    # It is the whole cost of this stage; the git call it exists for is 2.3 ms.
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    try:
        with open(spec_path, encoding="utf-8") as stream:
            spec = yaml.load(stream, Loader=loader) or {}
    except (OSError, yaml.YAMLError) as exc:
        return {}, "%s: cannot read spec: %s" % (spec_path, exc)
    if not isinstance(spec, dict):
        return {}, "%s: spec is not a mapping" % spec_path
    return {k: spec[k] for k in PRIMARY_KEYS if spec.get(k) is not None}, None


def git_toplevel(root):
    """The work tree root git resolves paths against. One extra process (~3 ms) so that a primary
    escaping the repo becomes a named offense instead of a fatal 128 that takes the gate with it."""
    proc = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("not a git work tree: %s (%s)" % (root, proc.stderr.strip()))
    return os.path.realpath(proc.stdout.strip())


def git_ignored(top, rels):
    """{path: "source:line `pattern`"} for the paths git's own ignore rules actually exclude.

    One process for every path: `--stdin`, NUL-framed (`-z`) so a primary whose name contains a
    space survives the round trip, `-v` so the refusal can name the rule that did it. The verdict
    is read off the PATTERN, never the exit code: under `-v` git returns 0 for "matched something",
    re-includes included, so 0 and 1 both mean "no defect found here". Anything else is git
    failing, which must not read as clean. A `!`-prefixed pattern is a re-include — `-v` prints it,
    and it means the path is NOT ignored (module docstring, measured 2026-09-04).
    """
    if not rels:
        return {}
    proc = subprocess.run(
        ["git", "-C", top, "check-ignore", "--no-index", "-v", "-z", "--stdin"],
        input="\0".join(rels) + "\0", capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError("git check-ignore failed (rc=%d): %s"
                           % (proc.returncode, proc.stderr.strip()))
    fields = proc.stdout.split("\0")
    out = {}
    for i in range(0, len(fields) - 3, 4):          # source, linenum, pattern, pathname
        source, linenum, pattern, pathname = fields[i:i + 4]
        if pattern.startswith("!"):
            continue
        out[pathname] = "%s:%s `%s`" % (source, linenum, pattern)
    return out


def _row(spec_path, key, declared, abspath, top, source):
    """A resolved candidate in the three forms the report needs, or None with an error."""
    # normpath, NOT realpath: .gitignore matches the name on the path, so a symlink standing in
    # the draft namespace must be asked about under the name it was declared with.
    abspath = os.path.normpath(abspath)
    rel = os.path.relpath(abspath, top)
    if rel.split(os.sep)[0] == os.pardir:
        return None, ("%s: %s resolves to %s, outside the repository — git cannot vouch for a "
                      "path a clone will never contain" % (spec_path, key, abspath))
    return {"spec": spec_path, "key": key, "declared": declared,
            "abs": abspath, "rel": rel, "source": source}, None


def _resolve_declared(spec_path, key, value, top):
    if not isinstance(value, str) or not value.strip():
        return None, ("%s: %s is %r — a primary must be a path relative to the part dir"
                      % (spec_path, key, value))
    return _row(spec_path, key, value, os.path.join(os.path.dirname(spec_path), value),
                top, "declared")


def evaluate(root=None):
    """Resolve every primary — declared, or the one verify.py would fall back to — and report the
    ones git ignores or the disk lacks."""
    root = os.path.realpath(os.path.abspath(root or DEFAULT_ROOT))
    top = git_toplevel(root)
    specs = find_specs(root)
    rows, errors, undeclared = [], [], 0
    for spec_path in specs:
        declared, err = declared_primaries(spec_path)
        if err:
            errors.append(err)
            continue
        if not declared:
            undeclared += 1
        for key, sub, ext in FALLBACK_SOURCES:
            if key in declared:
                row, err = _resolve_declared(spec_path, key, declared[key], top)
            else:
                picked = _pick(os.path.dirname(spec_path), sub, ext)
                if picked is None:
                    continue                    # nothing exported yet: A1's exit 14 owns that
                row, err = _row(spec_path, key, os.path.relpath(picked,
                                                                os.path.dirname(spec_path)),
                                picked, top, "fallback")
            (errors.append(err) if err else rows.append(row))

    ignored = git_ignored(top, sorted({r["rel"] for r in rows}))
    offenses = []
    for row in rows:
        why = []
        if row["rel"] in ignored:
            why.append("IGNORED by %s — a clean clone will not have it" % ignored[row["rel"]])
        # A fallback path came out of os.listdir, so it exists by construction; only a declared
        # primary can be a promise about a file nobody exported.
        if row["source"] == "declared" and not os.path.isfile(row["abs"]):
            why.append("MISSING — no file at %s" % os.path.relpath(row["abs"], top))
        if why:
            offenses.append(dict(row, why=why,
                                 kinds=[w.split(" ", 1)[0] for w in why]))
    declared_rows = [r for r in rows if r["source"] == "declared"]
    return {"root": root, "top": top, "specs": len(specs), "declared": len(declared_rows),
            "fallbacks": len(rows) - len(declared_rows), "undeclared": undeclared,
            "offenses": offenses, "errors": errors,
            "passed": bool(specs) and not offenses and not errors}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        result = evaluate(argv[0] if argv else None)
    except RuntimeError as exc:
        # A gate that cannot run must not print PASS: the whole point of this file is that a
        # missing answer looked identical to a good one for seven specs.
        print("  [FAIL] %s" % exc)
        print("SPEC_PRIMARY_RESULT: FAIL")
        return 1
    print("spec primary artifacts: %d spec(s), %d declared path(s), %d spec(s) declare none "
          "(%d path(s) resolved by verify.py's fallback)"
          % (result["specs"], result["declared"], result["undeclared"], result["fallbacks"]))
    if not result["specs"]:
        print("  [FAIL] no spec.yaml found under %s — this gate checked nothing, which is not a "
              "pass" % result["root"])
    for off in result["offenses"]:
        spec_rel = os.path.relpath(off["spec"], result["top"])
        if off["source"] == "declared":
            print("  [FAIL] %s: %s -> %s" % (spec_rel, off["key"], off["declared"]))
            fix = FIX["declared"]
        else:
            print("  [FAIL] %s: no %s declared, so verify.py:125 uses -> %s"
                  % (spec_rel, off["key"], off["declared"]))
            fix = (FIX["fallback"][0] % off["key"], FIX["fallback"][1])
        for why in off["why"]:
            print("           %s" % why)
        print("           fix: %s" % fix[0])
        print("                %s" % fix[1])
    for err in result["errors"]:
        print("  [FAIL] %s" % err)
    if result["passed"]:
        print("  every primary — declared or fallen back to — is tracked-namespace and present")
    print("SPEC_PRIMARY_RESULT: %s" % ("PASS" if result["passed"] else "FAIL"))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
