#!/usr/bin/env python3
"""Bounded preparation, using existing stages. No send stage, approval, or physical attestation.

prepare.sh --root <canonical checkout> <part>/prepare.yaml [--preflight]
A failure permits ONE repair with --repair-reason. Further attempts need --escalate-reason.
READY is terminal: present the handoff and await separate human approval.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import yaml

HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent
sys.path[:0] = [str(PIPELINE / "verify"), str(PIPELINE / "generate"), str(PIPELINE)]
from plate_scope import require_open, ScopeHeld
import plate_inventory
import source_scope as scope
import build_provenance as producer
from qualification_check import evaluate_part

VIEWS = ("iso", "iso_back", "top", "front", "back")


def code_hash(*directories):
    files = [p for directory in directories for p in directory.rglob("*")
             if p.is_file() and p.suffix in {".py", ".sh"}
             and not p.name.startswith(("test_", "cadquery_test_")) and not p.name.endswith("_fixture.py")]
    files += [HERE / "prepare.py", PIPELINE / "stamp.sh", PIPELINE / "plate_scope.py"]
    return {str(p): scope.digest(p) for p in sorted(set(files))}


def resource_hash(paths):
    result = {}
    for name in paths:
        p = Path(name).expanduser().absolute()
        if not p.exists():
            raise ValueError(f"missing tool/profile resource: {p}")
        files = [p] if p.is_file() else sorted(f for f in p.rglob("*") if f.is_file())
        # Include the directory itself: an empty user-preset directory is meaningful too.
        result[str(p)] = {str(f.relative_to(p)) if p.is_dir() else p.name: scope.digest(f)
                          for f in files}
    return result


def executable(name, flag="--version"):
    path = shutil.which(name)
    if not path:
        raise ValueError(f"missing executable: {name}")
    result = subprocess.run([path, flag], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError(f"cannot identify {name}: {result.stderr[-500:]}")
    return {"path": path, "sha256": scope.digest(path),
            "version": result.stdout + result.stderr}


def cache_valid(record, key, artifacts):
    if not isinstance(record, dict) or record.get("key") != scope.fingerprint(key):
        return False
    expected = {str(p) for p in artifacts}
    if set(record.get("outputs", {})) != expected:
        return False
    return all(p.is_file() and p.stat().st_size and scope.digest(p) == record["outputs"][str(p)]
               for p in artifacts)


def attempt_allowed(state, repair=None, escalation=None, changed=True):
    failures = state.get("failed_attempts", 0)
    if not failures:
        return
    if not changed:
        raise ValueError("no relevant input/artifact changed after the blocker; do not repeat the same pass")
    if failures == 1 and (repair or escalation):
        return
    if failures > 1 and escalation:
        return
    raise ValueError("blocked preparation needs --repair-reason (one repair only), then "
                     "--escalate-reason naming the concrete blocker/change/next action")


def validate_slice_args(args, colour_paths=()):
    """`colour_paths`: the part's declared build outputs (repo-relative). A --colour region decides
    which filament prints where, so it must be one of them: the producer binds its bytes and the slice
    stage's key covers it. A path from anywhere else would be an unbound input."""
    valued = {"--support-angle", "--brim", "--infill", "--rotate-x", "--rotate-y", "--rotate-z",
              "--process", "--machine", "--filament", "--set", "--colour", "--colour-names"}
    flags = {"--support", "--support=normal", "--support=tree", "--on-build-plate-only"}
    index = 0
    while index < len(args):
        option = args[index]; index += 1
        if option in flags:
            continue
        if option not in valued or index == len(args):
            raise ValueError(f"invalid/positional slice argument: {option}; prepare owns all output/model paths")
        value = args[index]; index += 1
        if "\n" in value or "\r" in value or (option == "--set" and "=" not in value):
            raise ValueError(f"invalid value for {option}")
        if option == "--set" and value.split("=", 1)[0] == "post_process":
            raise ValueError("declare post_hooks; do not hide an unbound postprocessor in --set")
        if option == "--colour-names" and not all(n.isalnum() for n in value.split(",")):
            raise ValueError(f"--colour-names wants short words separated by commas, got {value}")
        if option == "--colour":
            path, sep, num = value.rpartition("=")
            if not sep or not num.isdigit() or int(num) < 2:
                raise ValueError(f"--colour wants <region stl>=<filament 2..>, got {value}")
            if path not in colour_paths:
                raise ValueError(f"--colour region {path} is not one of this part's declared build outputs")


def check_input_snapshot(root, part, recipe, python):
    paths = {scope.local_path(root, n) for n in recipe.get("check_inputs", [])}
    substitutions = {"part": str(part), "root": str(root), "cadquery": python}
    for command in recipe.get("checks", []):
        for arg in command:
            name = arg.format(**substitutions)
            p = Path(name); p = p if p.is_absolute() else root / p
            if p.exists() and p.resolve().is_relative_to(root) and p.resolve() != root:
                paths.add(scope.local_path(root, str(p.relative_to(root))))
    return scope.snapshot(root, {root: paths})


def preflight(root, recipe_path):
    issues = []; tools = {}
    root = root.resolve(); recipe_path = recipe_path.resolve(); part = recipe_path.parent
    if scope.repo_root(root) != root or scope.canonical_root(root) != root:
        issues.append("wrong root: deliver from the canonical owning checkout, never a linked worktree")
    if not part.is_relative_to(root / "parts") or scope.repo_root(part) != root:
        issues.append("recipe/part must belong to this canonical checkout's parts/")
    recipe = yaml.safe_load(recipe_path.read_text())
    if not isinstance(recipe, dict) or recipe.get("schema") != 1:
        raise ValueError("prepare.yaml requires schema: 1")
    if recipe.get("kind") not in {"bench-experiment", "prototype", "release"}:
        issues.append("kind must be bench-experiment, prototype or release (not a gate bypass)")
    for field in ("objective", "stop_condition"):
        if not isinstance(recipe.get(field), str) or not recipe[field].strip():
            issues.append(f"declare a bounded {field}")
    out = scope.local_path(root, recipe.get("plate"), exists=False)
    if not out.is_relative_to(root / "build"):
        issues.append("plate must be inside this checkout's build/")
    else:
        require_open(out)  # an intent stop, before tools, repairs, locks or stale-output cleanup
        try:
            plate_inventory.inputs(out)
        except plate_inventory.ERRORS as exc:
            issues.append(f'plate inventory: {exc}. Capture the brief with plate_inventory.py request and register source models with catalog.')
    spec = producer.load_spec(part)
    # Surface the same design/status errors handoff would reject before paying for CAD/slicing.
    # This read-only early check neither writes a qualification manifest nor replaces final handoff.
    issues.extend(f"design/status qualification: {e}" for e in evaluate_part(str(part))["errors"])
    try:
        inputs = producer.build_inputs(root, part, spec)
        scope.assert_committed(root, inputs["files"] + [{"repository": ".", "files": {
            str(recipe_path.relative_to(root)): scope.digest(recipe_path)}}])
    except (ValueError, OSError) as exc:
        issues.append(str(exc))
    args = recipe.get("slice_args")
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        issues.append("slice_args must be an explicit list of option/value strings")
    elif any(a in args for a in ("--spec", "--post")):
        issues.append("prepare owns --spec; declare post_hooks separately for content-keyed reuse")
    else:
        try:
            outs = ((spec.get("build") or {}).get("outputs") or []) if isinstance(spec, dict) else []
            validate_slice_args(args, {str((part / o).relative_to(root)) for o in outs})
        except ValueError as exc:
            issues.append(str(exc))
        for option in ("--machine", "--process", "--filament"):
            if option not in args or args.index(option) + 1 >= len(args):
                issues.append(f"slice_args must explicitly declare {option}")
    if not isinstance(recipe.get("profile_resources"), list) or not recipe["profile_resources"]:
        issues.append("profile_resources must cover the slicer's preset store and tool deployment")
    try:
        tools["profiles"] = resource_hash(recipe.get("profile_resources", []))
        tools["resources"] = resource_hash(recipe.get("tool_resources", []))
        tools["python"] = producer.interpreter_identity(sys.executable)
        tools["cadquery"] = producer.interpreter_identity(
            os.environ.get("CADQUERY_PY", str(Path.home() / "cadquery-env/bin/python")))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        issues.append(str(exc))
    for key, default, flag in (("openscad", "openscad", "--version"),
                               ("freecadcmd", "freecadcmd", "--version"),
                               ("prusa_slicer", "prusa-slicer", "--help")):
        try:
            tools[key] = executable(os.environ.get(key.upper(), default), flag)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            issues.append(str(exc))
    for name in recipe.get("post_hooks", []):
        try:
            p = scope.local_path(root, name)
            scope.assert_committed(root, [{"repository": ".", "files": {name: scope.digest(p)}}])
        except (ValueError, OSError) as exc:
            issues.append(str(exc))
    if not isinstance(recipe.get("checks", []), list) or not all(
            isinstance(c, list) and c and all(isinstance(v, str) for v in c)
            for c in recipe.get("checks", [])):
        issues.append("checks must be argument arrays, not shell strings")
    try:
        rows = check_input_snapshot(root, part, recipe,
            tools.get("cadquery", {}).get("executable", "python"))
        scope.assert_committed(root, rows)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        issues.append(str(exc))
    if issues:
        raise ValueError("PREFLIGHT BLOCKERS:\n - " + "\n - ".join(issues))
    return recipe, part, out, spec, tools


class Preparation:
    def __init__(self, root, recipe, part, out, spec, tools):
        self.root, self.recipe, self.part, self.out = root, recipe, part, out
        self.spec, self.tools = spec, tools
        self.path = out / "preparation.json"
        self.state = json.loads(self.path.read_text()) if self.path.is_file() else {}
        if self.state and (self.state.get("owner_root") != str(root) or self.state.get("part") != str(part)):
            raise ValueError("relocated preparation record: rebuild in the frozen owning checkout")
        # `kind` reaches the plate because handoff.sh has to know what it is presenting. A verify
        # verdict of DEBT may be crossed by a prototype and never by a release, and the recipe is
        # the only place that distinction is declared. Recorded here rather than re-read from the
        # recipe downstream, so the plate carries the kind it was actually prepared under.
        self.state.update(schema=1, owner_root=str(root), part=str(part),
                          kind=recipe.get("kind"))
        self.state.setdefault("stages", {})
        if self.state.get("status") == "PREPARING":
            self.state["status"] = "BLOCKED"
            self.state["failed_attempts"] = self.state.get("failed_attempts", 0) + 1
            self.state["problems"] = ["interrupted pass; inspect logs before an explicit repair"]
        self.events = []; self.problems = []
        self.env = {k: v for k, v in os.environ.items()
                    if k not in {"APPROVED", "FORCE"} and not k.endswith("_OK")}
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.env["LABEL_MAX"] = "14"

    def save(self):
        producer.atomic_json(self.path, self.state)

    def invalidate_handoff(self):
        for name in ("handoff.txt", "qualification_manifest.json"):
            (self.out / name).unlink(missing_ok=True)

    def stage(self, name, key, commands, artifacts):
        previous = self.state["stages"].get(name)
        if cache_valid(previous, key, artifacts):
            print(f"REUSE {name} — inputs/tools/config and {len(artifacts)} artifacts match", flush=True)
            self.events.append({"stage": name, "action": "reuse"})
            return True
        self.state["stages"].pop(name, None); self.save()
        # A best-effort producer must not inherit yesterday's missing/failed review outputs.
        for artifact in artifacts:
            artifact.unlink(missing_ok=True)
        log = self.out / f"prepare-{name}.log"; start = time.monotonic()
        print(f"RUN   {name} — {log}", flush=True)
        with log.open("w") as stream:
            for command in commands:
                stream.write("COMMAND: " + json.dumps(list(map(str, command))) + "\n"); stream.flush()
                result = subprocess.run(list(map(str, command)), cwd=self.root, env=self.env,
                                        stdout=stream, stderr=subprocess.STDOUT)
                if result.returncode:
                    self.problems.append(f"{name}: exit {result.returncode}; {log}")
                    return False
        missing = [str(p) for p in artifacts if not p.is_file() or not p.stat().st_size]
        if missing:
            self.problems.append(f"{name}: missing required outputs: {', '.join(missing)}; {log}")
            return False
        self.state["stages"][name] = {"key": scope.fingerprint(key),
            "outputs": {str(p): scope.digest(p) for p in artifacts}}
        self.events.append({"stage": name, "action": "run", "seconds": round(time.monotonic() - start, 3)})
        self.save(); return True

    def attempt_identity(self):
        exported = scope.outputs(self.part, self.spec)
        checkpoint = {}
        for p in exported:
            try:
                checkpoint[str(p)] = scope.git(self.root, "rev-parse", f"HEAD:{p.relative_to(self.root)}")
            except ValueError:
                checkpoint[str(p)] = None
        paths = list(self.out.glob("*")) + exported
        return scope.fingerprint({"inputs": producer.build_inputs(self.root, self.part, self.spec),
            "recipe": self.recipe, "tools": self.tools, "checkpoint": checkpoint,
            "checks": check_input_snapshot(self.root, self.part, self.recipe,
                self.tools.get("cadquery", {}).get("executable", "python")),
            "stage_code": code_hash(*(PIPELINE / n for n in
                ("generate", "verify", "preview", "slice", "prepare"))),
            "post_hooks": {n: scope.digest(scope.local_path(self.root, n))
                           for n in self.recipe.get("post_hooks", [])},
            "artifacts": {str(p): scope.digest(p) for p in paths if p.is_file()
                and p.suffix != ".log" and p.name not in
                {"preparation.json", ".prepare.lock", "handoff.txt", "qualification_manifest.json"}}})

    def run(self, repair=None, escalation=None):
        started = self.started = time.monotonic()
        pipeline_code = code_hash(PIPELINE)
        inputs = producer.build_inputs(self.root, self.part, self.spec)
        # Global HEAD/unrelated files cannot manufacture a changed-input repair.
        attempt = self.attempt_identity()
        attempt_allowed(self.state, repair, escalation, changed=attempt != self.state.get("blocked_identity"))
        self.invalidate_handoff()
        self.state.update(status="PREPARING", last_reason=escalation or repair)
        self.save()
        source = self.part / self.spec["build"]["source"]
        try:
            prod, _ = producer.validate(self.part)
            if prod["interpreter"] != self.tools["cadquery"]:
                raise ValueError("configured generator interpreter changed")
            print("REUSE build — current producer/input/output identity", flush=True)
            self.events.append({"stage": "build", "action": "reuse"})
        except (ValueError, OSError, KeyError, TypeError):
            self.state["stages"].pop("build", None)  # an invalid producer is never cacheable
            ok = self.stage("build", {"inputs": inputs, "tool": self.tools["cadquery"]},
                [[PIPELINE / "generate/build.sh", source, self.part / "stl"]],
                scope.outputs(self.part, self.spec) + [scope.producer_path(self.root, self.part)])
            if not ok:
                return self.finish(started, attempt)
            prod, _ = producer.validate(self.part)
        model = self.part / self.spec["primary_stl"]
        geometry = {"producer_inputs": prod["inputs"], "outputs": prod["outputs"]}
        expected = (self.spec.get("test_article") or {}).get("physical_samples")
        if expected is not None and expected != prod["physical_samples"]:
            self.problems.append(f"physical sample count: expected {expected}, STEP has {prod['physical_samples']}")
        self.state["physical_samples"] = prod["physical_samples"]
        py = self.tools["cadquery"]["executable"]
        substitutions = {"part": str(self.part), "root": str(self.root), "cadquery": py}
        checks = [[arg.format(**substitutions) for arg in command] for command in self.recipe.get("checks", [])]
        check_inputs = check_input_snapshot(self.root, self.part, self.recipe, py)
        common = {"geometry": geometry, "tool_resources": self.tools["resources"]}
        verify_key = {**common, "checks": checks, "check_inputs": check_inputs,
            "code": code_hash(PIPELINE / "verify"), "freecad": self.tools["freecadcmd"],
            "python": self.tools["python"], "cadquery": self.tools["cadquery"]}
        verify_ok = self.stage("verify", verify_key,
            [[PIPELINE / "verify/verify.sh", self.part], *checks], [self.part / "verify.stamp"])
        preview = self.part / "preview"; stem = model.stem
        renders = [preview / f"{stem}_{v}.png" for v in VIEWS] + [preview / f"{stem}.stamp"]
        renders += [preview / f"{stem}_{v}_labelled.png" for v in ("top", "front", "side")]
        renders += [preview / f"{stem}.labelmap.json"]
        self.stage("render", {**common, "code": code_hash(PIPELINE / "preview"),
            "tools": {k: self.tools[k] for k in ("openscad", "freecadcmd", "python")}},
            [[PIPELINE / "preview/render.sh", model, preview]], renders)
        hooks = [scope.local_path(self.root, n) for n in self.recipe.get("post_hooks", [])]
        slice_key = {**common, "code": code_hash(PIPELINE / "slice", PIPELINE / "preview"),
            "args": self.recipe["slice_args"], "profiles": self.tools["profiles"],
            "slicer": self.tools["prusa_slicer"], "python": self.tools["python"],
            "hooks": {str(p): scope.digest(p) for p in hooks}}
        command = [PIPELINE / "slice/slice.sh", *self.recipe["slice_args"], "--spec", self.part]
        for hook in hooks: command += ["--post", hook]
        slice_outputs = [self.out / n for n in ("plate.3mf", "plate_1.gcode", ".overrides.ini",
            "plate_geom.txt", "plate_parts.txt", "slice_meta.json", "gcode_manifest.json", "slice_exit.txt")]
        if verify_ok and self.stage("slice", slice_key, [command + [self.out, model]], slice_outputs):
            final = {str(p): scope.digest(p) for p in slice_outputs}
            self.stage("verify-slice", {"final": final, "verify": verify_key},
                [[PIPELINE / "verify/verify-slice.sh", "--spec", self.part, self.out, model]],
                [self.out / "verify_slice.txt"])
            self.stage("supports", {"gcode": final[str(self.out / "plate_1.gcode")],
                "code": code_hash(PIPELINE / "preview"), "python": self.tools["python"],
                "resources": self.tools["resources"]},
                [[sys.executable, PIPELINE / "preview/plot-supports.py", self.out / "plate_1.gcode",
                  self.out / "supports.png", f"{prod['physical_samples']} physical samples"]],
                [self.out / "supports.png"])
        if not self.problems:
            try:
                producer.validate(self.part, require_committed=True)
                # Inputs must not change during the pass (also catches tools/preset edits).
                producer.interpreter_identity.cache_clear()
                now_recipe, _, _, _, now_tools = preflight(self.root, self.part / "prepare.yaml")
                if inputs != producer.build_inputs(self.root, self.part, producer.load_spec(self.part)) \
                        or now_tools != self.tools or now_recipe != self.recipe \
                        or code_hash(PIPELINE) != pipeline_code \
                        or check_input_snapshot(self.root, self.part, self.recipe, py) != check_inputs:
                    raise ValueError("inputs/checks/tools/presets changed during preparation")
                if (self.out / "verify_slice.txt").read_text().strip() != "PASS":
                    raise ValueError("deterministic verify-slice is not PASS")
            except (ValueError, OSError) as exc:
                self.problems.append(str(exc))
        if not self.problems:
            # Always run the cheap final readiness/identity gate. Never cache human approval.
            self.state["stages"].pop("handoff", None)
            self.stage("handoff", {"fresh_gate": True},
                [[PIPELINE / "handoff/handoff.sh", self.out, self.part]],
                [self.out / n for n in ("handoff.txt", "qualification_manifest.json", "verify_report.txt", "plate-inventory.json")])
        return self.finish(started, attempt)

    def finish(self, started, attempt):
        seconds = round(time.monotonic() - started, 3)
        self.state.update(status="BLOCKED" if self.problems else "READY", events=self.events,
                          problems=self.problems, elapsed_seconds=seconds)
        if self.problems:
            self.invalidate_handoff()
            self.state["failed_attempts"] = self.state.get("failed_attempts", 0) + 1
            try:
                self.state["blocked_identity"] = self.attempt_identity()
            except (ValueError, OSError):
                self.state["blocked_identity"] = "invalid-source-or-output"
        else:
            self.state["failed_attempts"] = 0
        self.state.setdefault("attempts", []).append({"status": self.state["status"], "seconds": seconds,
            "events": self.events, "reason": self.state.get("last_reason"), "problems": self.problems})
        self.save()
        if self.problems:
            print("BLOCKED — one diagnosis, no automatic repair loop:\n - " + "\n - ".join(self.problems))
            return 1
        print(f"READY — {self.state['physical_samples']} physical samples; {seconds}s preparation")
        print(f"Present {self.out / 'handoff.txt'} and its artifacts. STOP for human approval. No send performed.")
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("recipe", type=Path)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--repair-reason"); parser.add_argument("--escalate-reason")
    args = parser.parse_args()
    job = None
    try:
        recipe, part, out, spec, tools = preflight(args.root, args.recipe)
        print(f"PREFLIGHT PASS — owner={args.root.resolve()} part={part} plate={out}", flush=True)
        if args.preflight:
            return 0
        out.mkdir(parents=True, exist_ok=True)
        with (out / ".prepare.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("another preparation owns this plate; do not run stages concurrently")
            require_open(out)
            job = Preparation(args.root.resolve(), recipe, part, out, spec, tools)
            return job.run(args.repair_reason, args.escalate_reason)
    except ScopeHeld as exc:
        print(f"PREPARATION ON HOLD — {exc}", file=sys.stderr)
        return 18
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        if job is not None and job.state.get("status") == "PREPARING":
            job.problems.append(str(exc))
            return job.finish(job.started, "failed")
        print(f"PREPARATION BLOCKED — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
