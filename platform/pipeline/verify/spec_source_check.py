#!/usr/bin/env python3
"""Spec↔source consistency (A2 of docs/llm-in-the-loop-plan.md).

The card tower's generator ran 118.0 while spec.yaml said 110.10 for two revisions, and verify
passed, because the provenance gate checks the LABELS on a number, not whether the generator
uses it. Pro-CAD names the same failure "assigns conflicting values to the same feature".

This check is the deterministic half of that trigger: compare each numeric spec dimension
against module-level Python constants in the part's generators. Match rule, deliberately strict:

  * module-level assignments only (top-level constants — function-local values are not
    reachable statically without running the code);
  * case-insensitive exact name match after lowering (outer_across_flats <-> OUTER_ACROSS_FLATS);
  * last definition wins (Python semantics);
  * tolerance = the dimension's own `tol` (default 0.0). A conflict is
    |constant - nominal| > tol.

A name that does not appear in the source is NOT a finding: params may be derived, read from
the spec at runtime, or named differently by design. Fuzzy matching would invent conflicts and
teach the operator to ignore the gate.

Status (2026-09-02): standalone checker + CLI, wired into the test suite and the adoption
ledger. It is NOT yet in verify.py's blocking path — the existing back catalogue needs a
conflict inventory first. Promote after the inventory is either zero or ratcheted, mirroring
the A1b (step_stl_agree) sequence.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys

_IGNORE_DIRS = {".git", "build", "vendor", "research", "__pycache__", "_TEMPLATE", "preview"}

ALLOW_FILENAME = ".spec-source.allow"


def _numeric(node):
    """ast literal number, or unary minus of one. Returns float or None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float))):
        return -float(node.operand.value)
    return None


def scan_constants(path):
    """Module-level numeric constants in one Python file: {lower_name: (value, path)}."""
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            tree = ast.parse(stream.read(), filename=path)
    except (OSError, SyntaxError):
        return {}
    constants = {}
    for node in tree.body:
        targets, value_node = [], None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            targets, value_node = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value_node = [node.target], node.value
        if not targets or not isinstance(targets[0], ast.Name):
            continue
        value = _numeric(value_node)
        if value is None:
            continue
        constants[targets[0].id.lower()] = (value, path)     # last definition wins
    return constants


def part_constants(part_dir):
    """Constants across a part's generators: its src/ tree (any revision subdirs included)."""
    merged = {}
    src_root = os.path.join(part_dir, "src")
    if not os.path.isdir(src_root):
        return merged
    for base, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for filename in sorted(files):
            if filename.endswith(".py"):
                merged.update(scan_constants(os.path.join(base, filename)))
    return merged


def spec_dimensions(spec):
    """Numeric spec dimensions: {name: {nominal, tol}}."""
    dims = {}
    for dim in spec.get("dimensions") or []:
        nominal = dim.get("nominal")
        if not isinstance(nominal, (int, float)) or isinstance(nominal, bool):
            continue
        tol = dim.get("tol")
        dims[dim.get("name", "<unnamed>")] = {
            "nominal": float(nominal),
            "tol": float(tol) if isinstance(tol, (int, float)) else 0.0,
        }
    return dims


def evaluate_part(part_dir):
    """Conflicts between spec nominals and generator constants for one part dir."""
    import yaml
    spec_path = os.path.join(part_dir, "spec.yaml")
    try:
        with open(spec_path, encoding="utf-8") as stream:
            spec = yaml.safe_load(stream) or {}
    except (OSError, yaml.YAMLError) as exc:
        return {"conflicts": [], "errors": ["%s: cannot read spec: %s" % (spec_path, exc)],
                "checked": 0, "part": part_dir}
    dims = spec_dimensions(spec)
    constants = part_constants(part_dir)
    conflicts, checked = [], 0
    for name, info in sorted(dims.items()):
        match = constants.get(name.lower())
        if match is None:
            continue
        checked += 1
        value, source = match
        if abs(value - info["nominal"]) > info["tol"] + 1e-9:
            conflicts.append({
                "name": name, "nominal": info["nominal"], "tol": info["tol"],
                "constant": value, "source": os.path.relpath(source, part_dir),
                "message": ("%s: source has %.4g but spec nominal is %.4g (tol %.4g)"
                            % (name, value, info["nominal"], info["tol"])),
            })
    return {"conflicts": conflicts, "errors": [], "checked": checked, "part": part_dir}


def _repo_relative(path, root):
    return os.path.relpath(os.path.abspath(path), os.path.abspath(root))


def read_allow(path):
    """Ratchet file: one `<part_dir>::<dimension>` entry per line, '#' comments, blanks ignored.
    (`::` rather than `#` as the separator — `#` is the comment character, and splitting it out
    of an entry is the exact parser bug dim_provenance.read_allow was written to avoid.)
    An entry retires one specific known conflict with a recorded reason; it never hides a new one.
    Returns the empty set when the file is absent."""
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


def find_part_dirs(root):
    """Every dir containing a spec.yaml under root (same exclusions as the adoption ledger)."""
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        if "spec.yaml" in files:
            found.append(base)
    return sorted(found)


def evaluate(root, allow_path=None):
    root = os.path.abspath(root)
    if os.path.isfile(os.path.join(root, "spec.yaml")):
        parts = [root]
    else:
        parts = find_part_dirs(root)
    allow_path = allow_path or os.path.join(root, ALLOW_FILENAME)
    allowed = read_allow(allow_path)
    conflicts, debt, errors, checked = [], [], [], 0
    for part in parts:
        result = evaluate_part(part)
        for conflict in result["conflicts"]:
            entry = "%s::%s" % (_repo_relative(result["part"], root), conflict["name"])
            (debt if entry in allowed else conflicts).append(dict(conflict, entry=entry))
        errors.extend(result["errors"])
        checked += result["checked"]
    return {"root": root, "parts": len(parts), "checked": checked,
            "conflicts": conflicts, "debt": debt, "errors": errors,
            "passed": not conflicts and not errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", help="a part dir (contains spec.yaml) or a repo root to scan")
    parser.add_argument("--count-only", action="store_true",
                        help="print just the conflict count and always exit 0 (for ledgers)")
    parser.add_argument("--allow", default=None,
                        help="ratchet file of known conflicts (default: %s at the scan root)"
                        % ALLOW_FILENAME)
    args = parser.parse_args(argv)
    result = evaluate(args.root, allow_path=args.allow)
    if args.count_only:
        print(len(result["conflicts"]))
        return 0
    print("spec-source consistency: %d parts, %d matchable dimension(s)" %
          (result["parts"], result["checked"]))
    for conflict in result["conflicts"]:
        print("  [CONFLICT] %s (%s)" % (conflict["message"],
                                        os.path.relpath(conflict["source"], result["root"])))
    for conflict in result["debt"]:
        print("  [DEBT] %s — on the %s ratchet; resolve which number is true, then delete the line"
              % (conflict["message"], ALLOW_FILENAME))
    for error in result["errors"]:
        print("  [FAIL] %s" % error)
    if not result["conflicts"] and not result["errors"]:
        print("  no spec nominal is contradicted by a generator constant")
    print("SPEC_SOURCE_RESULT:", "PASS" if result["passed"] else "FAIL")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
