#!/usr/bin/env python3
"""Execute a declared generator once and bind inputs/tool/outputs. No physical verdict.

Used by build.sh for spec-owned generators. A missing/stale producer manifest requires a rebuild,
not re-attesting yesterday's mesh. Python imports/read paths are checked against declared scopes;
native/C++ reads must be declared by the generator author. No import closure is guessed from text.
"""
from __future__ import annotations
import argparse
import functools
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "verify"))
import source_scope as scope  # noqa: E402


def load_spec(part):
    value = yaml.safe_load((part / "spec.yaml").read_text())
    if not isinstance(value, dict):
        raise ValueError("spec must be a mapping")
    return value


def tool_files():
    return [HERE / name for name in ("build.sh", "build_provenance.py", "c14n_stl.py", "c14n_step.py")] \
        + [HERE.parent / "verify/source_scope.py"]


def tools_snapshot(root):
    return scope.snapshot(root, {scope.PLATFORM: set(tool_files())})


def environment():
    versions = {}
    for package in ("cadquery", "cadquery-ocp", "numpy", "PyYAML"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    # OCCT font geometry depends on installed glyph bytes, not just the CadQuery version.
    fonts = {str(p): scope.digest(p) for p in Path("/usr/share/fonts").rglob("*")
             if p.is_file() and p.suffix.lower() in {".ttf", ".otf", ".ttc"}}
    return {"python": sys.version, "packages": versions, "fonts": fonts}


@functools.lru_cache(maxsize=None)
def interpreter_identity(executable):
    resolved = Path(os.path.abspath(shutil.which(str(executable)) or executable))
    if not resolved.is_file():
        raise ValueError(f"missing generator interpreter: {executable}")
    if resolved == Path(sys.executable).absolute():
        data = environment()
    else:
        result = subprocess.run([str(resolved), str(Path(__file__).resolve()), "environment"],
                                capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    return {"executable": str(resolved), "sha256": scope.digest(resolved), **data}


def build_inputs(root, part, spec):
    resources = {}
    names = (spec.get("build") or {}).get("tool_resources", [])
    if not isinstance(names, list):
        raise ValueError("build.tool_resources must list installed tool resource files")
    for name in names:
        if not isinstance(name, str):
            raise ValueError("tool resource must be a path string")
        p = Path(name).expanduser().resolve()
        if not p.is_file():
            raise ValueError(f"missing installed tool resource: {p}")
        try:
            scope.repo_root(p)
        except ValueError:
            resources[str(p)] = scope.digest(p)
        else:
            raise ValueError(f"repository inputs need source_dependencies, not tool_resources: {p}")
    return {"files": scope.snapshot(root, scope.declarations(root, part, spec)),
            "producer_tools": tools_snapshot(root), "tool_resources": resources}


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def validate(part, *, require_committed=False):
    part = Path(part).resolve(); root = scope.repo_root(part)
    path = scope.producer_path(root, part)
    if not path.is_file():
        raise ValueError("missing build provenance; run build.sh/prepare.sh for this part")
    record = json.loads(path.read_text())
    spec = load_spec(part)
    if record.get("schema") != 1 or record.get("owner_root") != str(root) \
            or record.get("part") != str(part.relative_to(root)):
        raise ValueError("invalid or relocated build provenance")
    current = build_inputs(root, part, spec)
    if current != record.get("inputs"):
        raise ValueError("generator/spec/dependency changed since build; rebuild this part")
    actual_interpreter = interpreter_identity(record.get("interpreter", {}).get("executable", ""))
    if actual_interpreter != record.get("interpreter"):
        raise ValueError("generator interpreter/package identity changed; rebuild this part")
    expected_outputs = {str(p.relative_to(root)) for p in scope.outputs(part, spec)}
    if set(record.get("outputs", {})) != expected_outputs:
        raise ValueError("producer output declaration is incomplete")
    for name, digest in record["outputs"].items():
        p = scope.local_path(root, name)
        if not p.is_file() or scope.digest(p) != digest:
            raise ValueError(f"export changed since its producer ran: {name}")
    if type(record.get("physical_samples")) is not int or record["physical_samples"] < 1:
        raise ValueError("producer has no physical solid/sample count")
    identity = {"commit": scope.git(root, "rev-parse", "HEAD"), "dirty": False,
                "scope": "part-and-dependencies", "producer": {
                    "path": str(path.relative_to(root)), "sha256": scope.digest(path),
                    "record": record}}  # immutable evidence even when the next build replaces its cache
    if require_committed:
        # Include the preparation recipe (if present), and exact deliverable outputs. Neither
        # unrelated part files nor generic README/QA writeups enter another part's source scope.
        local = dict(record["outputs"])
        recipe = part / "prepare.yaml"
        if recipe.is_file():
            local[str(recipe.relative_to(root))] = scope.digest(recipe)
        identity["repositories"] = scope.assert_committed(root, current["files"]
            + [{"repository": ".", "files": local}])
        # Tool source is bound by exact content, like installed compiler binaries. This is not
        # a whole-platform cleanliness assertion; declared CAD libraries above ARE checkpointed.
        identity["producer_tools"] = current["producer_tools"]
    return record, identity


def run(source, out):
    source = Path(source).resolve(); part = source.parent.parent
    root = scope.repo_root(part); spec = load_spec(part)
    if scope.canonical_root(root) != root:
        raise ValueError("build requires the canonical owning checkout, not a linked worktree")
    if not Path(out).resolve().is_relative_to(part):
        raise ValueError("declared generator outputs must stay under their owning part")
    declared = scope.local_path(part, (spec.get("build") or {}).get("source"))
    if source != declared:
        raise ValueError("requested generator differs from spec build.source")
    manifest = scope.producer_path(root, part)
    manifest.unlink(missing_ok=True)  # a failed build must not retain yesterday's authority
    inputs = build_inputs(root, part, spec)
    outputs = scope.outputs(part, spec)
    before = time.monotonic()
    interpreter = interpreter_identity(sys.executable)
    observed = set()
    allowed = {str((root / row["repository"] / name).resolve())
               for row in inputs["files"] + inputs["producer_tools"] for name in row["files"]}
    allowed.update(inputs["tool_resources"])
    if any(str(p) in allowed for p in outputs):
        raise ValueError("an output is also a declared input; separate the frozen reference from the export")
    repository_cache = {}

    def observe(path):
        if not isinstance(path, (str, bytes, os.PathLike)):
            return
        p = Path(os.fsdecode(path)).resolve()
        if p.suffix in {".pyc", ".pyo"}:
            try:
                import importlib.util
                p = Path(importlib.util.source_from_cache(str(p)))
            except ValueError:
                return
        if not p.is_file():
            return
        observed.add(str(p))

    def audit(event, args):
        if event == "open":
            name, mode, flags = args
            if isinstance(mode, str) and ("w" in mode or "a" in mode or "+" in mode):
                return
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                return
            observe(name)

    for p in outputs:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.unlink(missing_ok=True)  # old exports cannot be re-attested by a no-op generator
    # A fresh process runs this command. The audit hook lasts only for this generator process.
    if source.suffix != ".py":
        raise ValueError("producer capture currently requires a Python/CadQuery generator; no unproven cache for other generators")
    sys.addaudithook(audit)
    sys.path.insert(0, str(source.parent))
    sys.argv = [str(source)]
    runpy.run_path(str(source), run_name="__main__")
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path:
            observe(path)
    # Stop recording before the validation reads its own tooling and exported outputs.
    captured = observed.copy()
    for name in sorted(captured):
        if name in allowed:
            continue
        p = Path(name)
        # Site packages/stdlib outside repositories belong to the interpreter identity. A local
        # module or data file inside ANY git repo needs an explicit source dependency.
        ancestor = p.parent
        while ancestor != ancestor.parent and not (ancestor / ".git").exists():
            ancestor = ancestor.parent
        if not (ancestor / ".git").exists():
            if any(p.is_relative_to(Path(prefix).resolve()) for prefix in
                   (sys.prefix, sys.base_prefix, "/usr", "/lib")):
                continue  # installed runtime; package/binary/font identity above
            if str(p) in {"/dev/null", "/dev/urandom", "/dev/random"} or str(p).startswith("/proc/"):
                continue
        repository_cache[name] = ancestor
    if repository_cache:
        raise ValueError("undeclared repository reads/imports; add actual source_dependencies:\n  "
                         + "\n  ".join(sorted(repository_cache)))
    for p in outputs:
        if not p.is_file() or not p.stat().st_size:
            raise ValueError(f"generator did not produce a nonempty declared output: {p}")
        if p.suffix == ".step":
            subprocess.run([sys.executable, str(HERE / "c14n_step.py"), str(p)], check=True)
        elif p.suffix == ".stl":
            subprocess.run([sys.executable, str(HERE / "c14n_stl.py"), str(p)], check=True)
    if build_inputs(root, part, load_spec(part)) != inputs:
        raise ValueError("source/dependency changed while generator ran; refusing provenance")
    import cadquery as cq
    step = cq.importers.importStep(str(part / spec["primary_step"])).val()
    count = len(step.Solids())
    if count < 1 or not step.isValid():
        raise ValueError("exported STEP is empty or invalid")
    record = {"schema": 1, "owner_root": str(root), "part": str(part.relative_to(root)),
              "source": str(source.relative_to(root)), "inputs": inputs,
              "interpreter": interpreter, "outputs": {
                  str(p.relative_to(root)): scope.digest(p) for p in outputs},
              "observed_repository_inputs": sorted(name for name in captured if name in allowed),
              "physical_samples": count, "elapsed_seconds": round(time.monotonic() - before, 3)}
    atomic_json(manifest, record)
    print(f"BUILD_PROVENANCE_RESULT: PASS — {count} solids — {manifest}")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("environment")
    p = sub.add_parser("run"); p.add_argument("source"); p.add_argument("out")
    p = sub.add_parser("check"); p.add_argument("part"); p.add_argument("--committed", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "environment":
            print(json.dumps(environment(), sort_keys=True))
        elif args.action == "run":
            run(args.source, args.out)
        else:
            record, _ = validate(args.part, require_committed=args.committed)
            print(f"BUILD_PROVENANCE_RESULT: PASS — {record['physical_samples']} solids")
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"BUILD_PROVENANCE_RESULT: FAIL — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
