#!/usr/bin/env python3
"""Forward-only design/print qualification records.

This module never creates a physical verdict. It can:
  * validate a part's Restore/Originate intent and status-to-evidence link;
  * write a machine-only handoff manifest bound to geometry, G-code and slicer settings;
  * initialize a `planned` iteration record whose human fields are deliberately null;
  * write down what the person said about a print (`report`), which evaluates nothing;
  * validate a human-completed record and report prospective iteration metrics.

Historical files are not scanned by a blocking global gate. `handoff.sh` invokes `part` only for
parts on the next plate, which makes the next design/print the migration boundary.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

_HERE = Path(__file__).resolve().parent
_SLICE_DIR = _HERE.parent / "slice"
sys.path.insert(0, str(_SLICE_DIR))
import slice_identity  # noqa: E402
sys.path.insert(0, str(_HERE.parent / "generate"))
import build_provenance  # noqa: E402
import source_scope  # noqa: E402

SCHEMA = 1
MANIFEST_SCHEMA = 1
MODES = {"restore", "originate"}
REFERENCE_ROLES = {"source", "interface", "standard"}
STATES = {"planned", "reported", "printed", "failed", "passed"}
# What the recorder took the person's words to mean. A reading is never a pass: it evaluates no check.
READINGS = {"works", "does-not-work", "mixed"}
KINDS = {"coupon", "full-part"}
STATUSES = {"draft", "printed", "dim-verified", "released"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_GEOM = re.compile(r"^[0-9a-f]{8}$")
_PLACEHOLDER = re.compile(r"^(?:todo|tbd|unknown|none|null|<.*>)$", re.IGNORECASE)
_NON_HUMAN_IDENTITIES = {"ai", "agent", "assistant", "llm", "model", "claude", "chatgpt",
                         "gpt", "gemini", "copilot", "qwen"}


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _meaningful(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not _PLACEHOLDER.fullmatch(value.strip())


def _human_identity(value: Any) -> bool:
    return _meaningful(value) and value.strip().lower() not in _NON_HUMAN_IDENTITIES


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _timestamp(value: Any) -> bool:
    if not _meaningful(value):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _load_yaml(path: str | os.PathLike[str]) -> Any:
    with open(path, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _repo_root(path: str | os.PathLike[str]) -> str:
    start = path if os.path.isdir(path) else os.path.dirname(os.path.realpath(path))
    proc = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True)
    if proc.returncode:
        raise ValueError(f"not inside a git work tree: {path}")
    return os.path.realpath(proc.stdout.strip())


def _repo_rel(path: str | os.PathLike[str], root: str) -> str:
    real = os.path.realpath(path)
    rel = os.path.relpath(real, root)
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        raise ValueError(f"path is outside repository: {real}")
    return rel


def _git(root: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    if proc.returncode:
        raise ValueError(proc.stderr.strip() or "git command failed")
    return proc.stdout.strip()


def evaluate_design(spec: Any) -> dict:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return {"passed": False, "mode": None, "errors": ["spec is not a mapping"]}
    if not _meaningful(spec.get("part_id")):
        errors.append("part_id is required")
    design = spec.get("design")
    if not isinstance(design, dict):
        return {"passed": False, "mode": None,
                "errors": ["design block is required at the next design/print boundary"]}
    if design.get("schema") != SCHEMA:
        errors.append(f"design.schema must be {SCHEMA}")
    mode = design.get("mode")
    if mode not in MODES:
        errors.append("design.mode must be restore or originate")
    if not _meaningful(design.get("purpose")):
        errors.append("design.purpose must state the part's intended job")

    refs = design.get("references", [])
    if not isinstance(refs, list):
        errors.append("design.references must be a list")
        refs = []
    source_refs = 0
    seen_refs: set[str] = set()
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            errors.append(f"design.references[{index}] must be a mapping")
            continue
        rid, role, evidence = ref.get("id"), ref.get("role"), ref.get("evidence")
        if not _meaningful(rid):
            errors.append(f"design.references[{index}].id is missing")
        elif rid in seen_refs:
            errors.append(f"duplicate design reference id: {rid}")
        else:
            seen_refs.add(rid)
        if role not in REFERENCE_ROLES:
            errors.append(f"design.references[{index}].role must be source, interface, or standard")
        if role == "source":
            source_refs += 1
        if not isinstance(evidence, list) or not evidence \
                or not all(_meaningful(item) for item in evidence):
            errors.append(f"design.references[{index}].evidence needs stable non-placeholder refs")

    dimensions = spec.get("dimensions", [])
    if not isinstance(dimensions, list):
        errors.append("dimensions must be a list")
        dimensions = []
    relationships: list[tuple[str, Any]] = []
    for index, dimension in enumerate(dimensions):
        if not isinstance(dimension, dict):
            errors.append(f"dimensions[{index}] must be a mapping")
            continue
        name = dimension.get("name") or f"dimensions[{index}]"
        relationship = dimension.get("reference")
        if relationship not in {"replicate", "deviate", "originate"}:
            errors.append(f"dimension {name!r} must declare reference: replicate|deviate|originate")
        relationships.append((str(name), relationship))

    if mode == "restore":
        if source_refs == 0:
            errors.append("restore design needs at least one role: source reference")
        if not relationships or not any(rel in {"replicate", "deviate"}
                                        for _, rel in relationships):
            errors.append("restore design needs at least one replicated or deliberately deviated dimension")
    elif mode == "originate":
        if source_refs:
            errors.append("originate design may cite interfaces/standards, but not a source part")
        copied = [name for name, rel in relationships if rel in {"replicate", "deviate"}]
        if copied:
            errors.append("originate design declares source-part relationships on: " + ", ".join(copied))

    acceptance = spec.get("acceptance")
    printed = acceptance.get("printed") if isinstance(acceptance, dict) else None
    if not isinstance(printed, list) or not printed or not all(_meaningful(item) for item in printed):
        errors.append("acceptance.printed needs one or more stable criterion ids")
    elif len(set(printed)) != len(printed):
        errors.append("acceptance.printed criterion ids must be unique")
    return {"passed": not errors, "mode": mode if mode in MODES else None, "errors": errors}


def _read_stamp(path: str) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                key, sep, value = line.rstrip("\n").partition("=")
                if sep and key not in result:
                    result[key] = value
    except OSError:
        pass
    return result


def _parse_plate_geoms(outdir: str, repo_root: str) -> list[dict]:
    path = os.path.join(outdir, "plate_geom.txt")
    rows: list[dict] = []
    with open(path, encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, 1):
            fields = line.rstrip("\n").split(None, 2)
            if not fields or fields[0].startswith("version="):
                continue
            if len(fields) != 3:
                raise ValueError(f"plate_geom.txt:{lineno}: malformed model row")
            geom_id, recorded, raw_path = fields
            model_path = raw_path if os.path.isabs(raw_path) else os.path.join(repo_root, raw_path)
            model_path = os.path.realpath(model_path)
            if not os.path.isfile(model_path):
                raise ValueError(f"plated model is missing: {raw_path}")
            actual = sha256_file(model_path)
            if recorded != actual or geom_id != actual[:8]:
                raise ValueError(f"plated model identity is stale: {raw_path}")
            rows.append({"path": _repo_rel(model_path, repo_root),
                         "geom_id": geom_id, "sha256": actual,
                         "absolute": model_path})
    if not rows:
        raise ValueError("plate records no geometry")
    return rows


def _parse_estimates(gcode: str) -> dict:
    grams, seconds, raw_time = None, None, None
    with open(gcode, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("; filament used [g]"):
                try: grams = float(line.split("=", 1)[1].strip())
                except (IndexError, ValueError): pass
            elif line.startswith("; estimated printing time (normal"):
                try: raw_time = line.split("=", 1)[1].strip()
                except IndexError: pass
    if raw_time:
        units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        found = re.findall(r"(\d+(?:\.\d+)?)\s*([dhms])", raw_time)
        if found:
            seconds = sum(float(value) * units[unit] for value, unit in found)
    return {"filament_g": grams, "print_time": raw_time, "print_time_seconds": seconds}


def build_handoff_manifest(outdir: str, part_dirs: list[str]) -> dict:
    outdir = os.path.realpath(outdir)
    root = _repo_root(outdir)
    if source_scope.canonical_root(Path(root)) != Path(root):
        raise ValueError("handoff requires the canonical owning checkout, not a linked worktree")
    if not Path(outdir).is_relative_to(Path(root) / "build"):
        raise ValueError("plate must live under the owning checkout's build/")
    models = _parse_plate_geoms(outdir, root)
    gcode = os.path.join(outdir, "plate_1.gcode")
    project = os.path.join(outdir, "plate.3mf")
    overrides = os.path.join(outdir, ".overrides.ini")
    meta_path = os.path.join(outdir, "slice_meta.json")
    identity = slice_identity.load_and_evaluate(meta_path, gcode=gcode, project=project,
                                                overrides_path=overrides)
    if not identity["passed"]:
        raise ValueError("slice identity failed: " + "; ".join(identity["errors"]))
    with open(meta_path, encoding="utf-8") as stream:
        slice_meta = json.load(stream)
    if not os.path.isfile(gcode):
        raise ValueError("final G-code is missing")

    # What kind of plate this is, from the recipe via preparation.json. Absent or unreadable reads
    # as a release, which is the strict answer: a plate that cannot say what it is does not get the
    # prototype's latitude.
    plate_kind = None
    try:
        with open(os.path.join(outdir, "preparation.json"), encoding="utf-8") as stream:
            plate_kind = json.load(stream).get("kind")
    except (OSError, ValueError):
        plate_kind = None
    debt_crossable = plate_kind in ("prototype", "bench-experiment")

    resolved_parts: list[str] = []
    for part in part_dirs:
        real = os.path.realpath(part)
        if real not in resolved_parts:
            resolved_parts.append(real)
    part_rows = []
    assigned: set[str] = set()
    for part in resolved_parts:
        spec_path = os.path.join(part, "spec.yaml")
        if not os.path.isfile(spec_path):
            raise ValueError(f"part has no spec.yaml: {part}")
        if _repo_root(part) != root:
            raise ValueError(f"part and plate are in different repositories: {part}")
        spec = _load_yaml(spec_path)
        design = evaluate_design(spec)
        if not design["passed"]:
            raise ValueError(f"{spec_path}: " + "; ".join(design["errors"]))
        part_models = []
        prefix = part + os.sep
        for model in models:
            if model["absolute"].startswith(prefix):
                part_models.append({key: model[key] for key in ("path", "geom_id", "sha256")})
                assigned.add(model["absolute"])
        if not part_models:
            continue
        stamp_path = os.path.join(part, "verify.stamp")
        stamp = _read_stamp(stamp_path)
        verdict = stamp.get("verdict")
        # The same rule handoff.sh applies at exit 14, applied again here because this is a separate
        # gate that reached the same conclusion independently — patching only one of them moves the
        # deadlock rather than clearing it. DEBT means every answerable check passed and a
        # fit-critical nominal is declared unproven, dated, with the iteration that closes it; the
        # prototype whose whole job is to produce that measurement may be built, a release may not.
        if verdict not in ("PASS", "DEBT") or (verdict == "DEBT" and not debt_crossable):
            raise ValueError(
                f"part has no PASS verify stamp: {part}" if verdict != "DEBT" else
                f"part carries declared measurement debt and this plate is "
                f"'{plate_kind or 'unknown'}': a release cannot be bound to an unproven "
                f"fit-critical nominal: {part}")
        part_rel = _repo_rel(part, root)
        producer, source = build_provenance.validate(part, require_committed=True)
        for model in part_models:
            if producer["outputs"].get(model["path"]) != model["sha256"]:
                raise ValueError(f"plated model lacks current producer coverage: {model['path']}")
        primary_model = str(Path(part_rel) / spec["primary_stl"])
        physical_samples = (producer["physical_samples"] * len(part_models)
                            if all(m["path"] == primary_model for m in part_models) else None)
        part_rows.append({
            "part_id": spec.get("part_id"), "part_dir": part_rel,
            "status_at_handoff": spec.get("status"), "design_mode": design["mode"],
            "source": source,
            "physical_samples": physical_samples,
            "spec": {"path": _repo_rel(spec_path, root), "sha256": sha256_file(spec_path)},
            # The stamp's OWN verdict, not a constant. This read "PASS" because the check above it
            # could not let anything else through, so the two were the same string — but the
            # manifest is the record of what a human approved, and a record that always says PASS
            # is not evidence of anything. It now says DEBT when that is what was approved.
            "verify": {"path": _repo_rel(stamp_path, root),
                       "sha256": sha256_file(stamp_path), "verdict": verdict,
                       "step_sha256": stamp.get("sha256") or None},
            "models": part_models,
        })
    unassigned = [{key: row[key] for key in ("path", "geom_id", "sha256")}
                  for row in models if row["absolute"] not in assigned]
    authored_unassigned = [row["path"] for row in unassigned
                           if row["path"] == "parts" or row["path"].startswith("parts/")]
    if authored_unassigned:
        raise ValueError("authored plated models were not assigned to a part: "
                         + ", ".join(authored_unassigned))
    # A build-only analysis plate (for example a support blocker) has no authored part by design.
    # Preserve handoff's existing unchecked-build policy; it gets an identity manifest but cannot
    # initialize or earn a part qualification record.

    verify_report = os.path.join(outdir, "verify_report.txt")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "kind": "print-candidate",
        "created_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "human_evaluation": "not-evaluated",
        "repository": {"name": os.path.basename(root), "commit": _git(root, "rev-parse", "HEAD"),
                       "branch": _git(root, "branch", "--show-current") or None},
        "plate": {
            "outdir": _repo_rel(outdir, root),
            "gcode": {"path": _repo_rel(gcode, root), "sha256": sha256_file(gcode)},
            "project_3mf": {"path": _repo_rel(project, root), "sha256": sha256_file(project)},
            "slice_meta": {"path": _repo_rel(meta_path, root), "sha256": sha256_file(meta_path),
                           "identity": slice_meta},
            "verify_report": {"path": _repo_rel(verify_report, root),
                              "sha256": sha256_file(verify_report)},
            "estimate": _parse_estimates(gcode),
            "unchecked_build_models": unassigned,
        },
        "parts": part_rows,
    }
    return manifest


def write_handoff_manifest(outdir: str, part_dirs: list[str]) -> str:
    manifest = build_handoff_manifest(outdir, part_dirs)
    path = os.path.join(os.path.realpath(outdir), "qualification_manifest.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(tmp, path)
    return path


def _validate_reports(record: dict, state: Any) -> list[str]:
    """`reports`: what the person who handled the print SAID about it, written down by someone else.

    Justin, 2026-11-11, asked whether an agent may put his exact words ("3 works well") in the part's
    test record: yes. Until then only he could fill a record, and none of sixty-one was filled. A
    report is his words, where he said them and who wrote them down. It evaluates nothing: the
    checks stay not-evaluated, nothing physical is filled in, and no status or tag accepts it.
    """
    errors: list[str] = []
    reports = record.get("reports")
    if reports in (None, []):
        if state == "reported":
            errors.append("reported record needs one or more reports of what the person said")
        return errors
    if state == "planned":
        errors.append("planned record must not carry reports")
    if not isinstance(reports, list):
        return errors + ["reports must be a list"]
    for index, row in enumerate(reports):
        where = f"reports[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{where} must be a mapping"); continue
        if not _human_identity(row.get("by")):
            errors.append(f"{where}.by must name the person who handled the print")
        if not _meaningful(row.get("said")):
            errors.append(f"{where}.said must hold the person's own words")
        if not _timestamp(row.get("at")):
            errors.append(f"{where}.at must be ISO-8601 with timezone")
        if not _meaningful(row.get("recorded_by")):
            errors.append(f"{where}.recorded_by must say who wrote the words down")
        if not _meaningful(row.get("source")):
            errors.append(f"{where}.source must say where the words can be found")
        if row.get("reading") not in READINGS:
            errors.append(f"{where}.reading must be works, does-not-work, or mixed")
        if row.get("next_change") is not None and not _meaningful(row.get("next_change")):
            errors.append(f"{where}.next_change must be null or say what changes next")
        extra = set(row) - {"by", "said", "at", "recorded_by", "source", "reading", "next_change"}
        if extra:
            errors.append(f"{where} has fields a report may not carry: " + ", ".join(sorted(extra)))
    return errors


def _criterion_map(record: dict) -> tuple[dict[str, dict], list[str]]:
    errors: list[str] = []
    checks = (record.get("outcome") or {}).get("checks")
    if not isinstance(checks, list):
        return {}, ["outcome.checks must be a list"]
    result: dict[str, dict] = {}
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or not _meaningful(check.get("id")):
            errors.append(f"outcome.checks[{index}] needs an id")
            continue
        cid = check["id"]
        if cid in result:
            errors.append(f"duplicate outcome check id: {cid}")
        result[cid] = check
    return result, errors


def _validate_measurements(record: dict, spec: dict) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    spec_dimensions = spec.get("dimensions")
    if not isinstance(spec_dimensions, list):
        spec_dimensions = []
    dimensions = {d.get("name"): d for d in spec_dimensions if isinstance(d, dict)}
    rows = (record.get("outcome") or {}).get("measurements")
    if not isinstance(rows, list):
        return {}, ["outcome.measurements must be a list"]
    covered: dict[str, str] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"outcome.measurements[{index}] must be a mapping"); continue
        name = row.get("dimension")
        if name not in dimensions:
            errors.append(f"measurement names unknown spec dimension: {name!r}"); continue
        if name in covered:
            errors.append(f"duplicate measurement dimension: {name}"); continue
        readings = row.get("raw_readings_mm")
        if not isinstance(readings, list) or len(readings) < 2 or not all(_finite(v) for v in readings):
            errors.append(f"measurement {name} needs at least two finite raw_readings_mm"); continue
        instrument = row.get("instrument")
        if not isinstance(instrument, dict) or not _meaningful(instrument.get("id")) \
                or not _finite(instrument.get("resolution_mm")) or instrument["resolution_mm"] <= 0:
            errors.append(f"measurement {name} needs instrument id and positive resolution_mm")
        uncertainty = row.get("uncertainty")
        if not isinstance(uncertainty, dict) or not _finite(uncertainty.get("value_mm")) \
                or uncertainty["value_mm"] < 0 or not _meaningful(uncertainty.get("basis")):
            errors.append(f"measurement {name} needs nonnegative uncertainty.value_mm and basis")
            continue
        dim = dimensions[name]
        nominal, tolerance = dim.get("nominal"), dim.get("tol")
        if not _finite(nominal) or not _finite(tolerance) or tolerance < 0:
            errors.append(f"spec dimension {name} lacks numeric nominal/tol"); continue
        u = uncertainty["value_mm"]
        calculated = "pass" if (min(readings) - u >= nominal - tolerance
                                and max(readings) + u <= nominal + tolerance) else "fail"
        if row.get("result") != calculated:
            errors.append(f"measurement {name} result must be {calculated} from readings + uncertainty")
        covered[name] = calculated
    return covered, errors


def evaluate_record(record: Any, spec: Any, *, repo_root: str | None = None,
                    require_state: str | None = None, check_files: bool = True) -> dict:
    errors: list[str] = []
    if not isinstance(record, dict):
        return {"passed": False, "state": None, "errors": ["record is not a mapping"]}
    if not isinstance(spec, dict):
        return {"passed": False, "state": None, "errors": ["spec is not a mapping"]}
    design = evaluate_design(spec)
    errors.extend("design: " + error for error in design["errors"])
    if record.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if not _meaningful(record.get("iteration_id")):
        errors.append("iteration_id is missing")
    if record.get("part_id") != spec.get("part_id"):
        errors.append("record part_id does not match spec")
    if record.get("design_mode") != design.get("mode"):
        errors.append("record design_mode does not match spec design.mode")
    if record.get("attempt_kind") not in KINDS:
        errors.append("attempt_kind must be coupon or full-part")
    if not _meaningful(record.get("objective")):
        errors.append("objective must name the question this iteration answers")

    artifact = record.get("artifact")
    if not isinstance(artifact, dict):
        errors.append("artifact must be a mapping"); artifact = {}
    source = artifact.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("commit"), str) \
            or not _SHA40.fullmatch(source["commit"]):
        errors.append("artifact.source.commit must be a full 40-hex git commit")
    if not isinstance(source, dict) or not isinstance(source.get("dirty"), bool):
        errors.append("artifact.source.dirty must be boolean")
    manifest_ref = artifact.get("handoff_manifest")
    if not isinstance(manifest_ref, dict) or not _meaningful(manifest_ref.get("path")) \
            or not isinstance(manifest_ref.get("sha256"), str) \
            or not _SHA256.fullmatch(manifest_ref["sha256"]):
        errors.append("artifact.handoff_manifest needs path and SHA-256")
    models = artifact.get("models")
    if not isinstance(models, list) or not models:
        errors.append("artifact.models must identify at least one plated model"); models = []
    seen_models: set[str] = set()
    for index, model in enumerate(models):
        if not isinstance(model, dict):
            errors.append(f"artifact.models[{index}] must be a mapping"); continue
        path, geom, digest = model.get("path"), model.get("geom_id"), model.get("sha256")
        if not _meaningful(path): errors.append(f"artifact.models[{index}].path is missing")
        digest_valid = isinstance(digest, str) and bool(_SHA256.fullmatch(digest))
        if not digest_valid:
            errors.append(f"artifact.models[{index}].sha256 is invalid")
        if not isinstance(geom, str) or not _GEOM.fullmatch(geom) \
                or not digest_valid or digest[:8] != geom:
            errors.append(f"artifact.models[{index}].geom_id does not match SHA-256")
        if isinstance(path, str) and path in seen_models:
            errors.append(f"duplicate artifact model path: {path}")
        seen_models.add(path)
        if check_files and repo_root and isinstance(path, str) and isinstance(digest, str):
            absolute = os.path.join(repo_root, path)
            if not os.path.isfile(absolute):
                errors.append(f"qualified model is missing: {path}")
            elif sha256_file(absolute) != digest:
                errors.append(f"qualified model bytes moved: {path}")
    for key in ("spec_sha256", "verify_stamp_sha256", "verify_step_sha256",
                "verify_report_sha256", "gcode_sha256", "project_3mf_sha256",
                "slice_meta_sha256"):
        digest = artifact.get(key)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            errors.append(f"artifact.{key} is invalid")
    config_sha = artifact.get("effective_config_sha256")
    if not isinstance(config_sha, str) or not _SHA256.fullmatch(config_sha):
        errors.append("artifact.effective_config_sha256 is invalid")
    profiles = artifact.get("profiles")
    if not isinstance(profiles, dict) or any(not _meaningful(profiles.get(key))
                                             for key in ("machine", "process", "filament")):
        errors.append("artifact.profiles must name machine, process, and filament")
    slicer = artifact.get("slicer")
    if not isinstance(slicer, dict) or not _meaningful(slicer.get("reported_by_gcode")):
        errors.append("artifact.slicer must preserve the generator identity from G-code")
    if not isinstance(artifact.get("overrides"), list) \
            or not all(isinstance(item, str) for item in artifact.get("overrides", [])):
        errors.append("artifact.overrides must be a list of exact key=value strings")
    hooks = artifact.get("post_hooks")
    if not isinstance(hooks, list):
        errors.append("artifact.post_hooks must be a list")
    else:
        for index, hook in enumerate(hooks):
            if not isinstance(hook, dict) or not _meaningful(hook.get("path")) \
                    or not isinstance(hook.get("sha256"), str) \
                    or not _SHA256.fullmatch(hook["sha256"]):
                errors.append(f"artifact.post_hooks[{index}] needs path and SHA-256")
    rotation = artifact.get("rotation")
    if not isinstance(rotation, dict) or any(not _finite(rotation.get(axis))
                                              for axis in ("x", "y", "z")):
        errors.append("artifact.rotation must contain finite x/y/z values")
    if not isinstance(artifact.get("support_requested"), bool):
        errors.append("artifact.support_requested must be boolean")

    execution = record.get("execution")
    if not isinstance(execution, dict):
        errors.append("execution must be a mapping"); execution = {}

    outcome = record.get("outcome")
    if not isinstance(outcome, dict):
        errors.append("outcome must be a mapping"); outcome = {}
    state = outcome.get("state")
    if state not in STATES:
        errors.append("outcome.state must be planned, reported, printed, failed, or passed")
    if require_state and state != require_state:
        errors.append(f"outcome.state must be {require_state}")
    checks, check_errors = _criterion_map(record)
    errors.extend(check_errors)
    for cid, check in checks.items():
        if check.get("result") not in {"not-evaluated", "pass", "fail"}:
            errors.append(f"outcome check {cid} has invalid result")
    expected = ((spec.get("acceptance") or {}).get("printed")
                if isinstance(spec.get("acceptance"), dict) else []) or []
    missing = [criterion for criterion in expected if criterion not in checks]
    if missing:
        errors.append("missing printed acceptance checks: " + ", ".join(missing))

    execution_required = {
        "printer_id": _meaningful,
        "material": _meaningful,
        "material_brand": _meaningful,
        "filament_lot": _meaningful,
        "dry_state": _meaningful,
        "build_plate": _meaningful,
        "nozzle_mm": lambda value: _finite(value) and value > 0,
        "layer_height_mm": lambda value: _finite(value) and value > 0,
        "ambient_c": lambda value: _finite(value) and -40 <= value <= 100,
        "ambient_rh_pct": lambda value: _finite(value) and 0 <= value <= 100,
    }
    errors.extend(_validate_reports(record, state))
    if state in {"planned", "reported"}:
        # A reported record is a planned one plus the person's words: nothing physical is filled in
        # by whoever wrote them down, and no check is evaluated by a sentence.
        for field in ("printed_at", "operator", "evaluated_at", "evaluator", "mate_or_application"):
            if outcome.get(field) not in (None, ""):
                errors.append(f"{state} record must leave outcome.{field} null")
        if any(value not in (None, [], "") for value in execution.values()):
            errors.append(f"{state} record must leave physical execution fields null/empty")
        if any(check.get("result") != "not-evaluated" for check in checks.values()):
            errors.append(f"{state} record checks must remain not-evaluated")
        if any(check.get("observation") not in (None, "") or check.get("evidence") not in (None, [])
               for check in checks.values()):
            errors.append(f"{state} record checks must leave observations/evidence empty")
        if outcome.get("measurements") not in (None, []):
            errors.append(f"{state} record must not contain physical measurements")
        if record.get("attestation") not in (None, {}):
            errors.append(f"{state} record must not carry a human attestation")
    elif state in {"printed", "failed", "passed"}:
        if not _timestamp(outcome.get("printed_at")) or not _human_identity(outcome.get("operator")):
            errors.append("printed attempt needs ISO-8601 printed_at with timezone and a human operator")
        for field, predicate in execution_required.items():
            if not predicate(execution.get(field)):
                errors.append(f"printed attempt needs valid execution.{field}")
        for field in ("deviations", "post_processing"):
            values = execution.get(field)
            if not isinstance(values, list) or not all(_meaningful(item) for item in values):
                errors.append(f"execution.{field} must be a list of observations (empty means none)")
        for field in ("actual_material_g", "actual_print_time_minutes"):
            value = execution.get(field)
            if value is not None and (not _finite(value) or value < 0):
                errors.append(f"execution.{field} must be null or a nonnegative number")
    if state in {"failed", "passed"}:
        if not _timestamp(outcome.get("evaluated_at")):
            errors.append("evaluated attempt needs ISO-8601 outcome.evaluated_at with timezone")
        if not _human_identity(outcome.get("evaluator")):
            errors.append("evaluated attempt needs a human identity in outcome.evaluator")
        if not _meaningful(outcome.get("mate_or_application")):
            errors.append("evaluated attempt needs outcome.mate_or_application")
        attestation = record.get("attestation")
        if not isinstance(attestation, dict) or attestation.get("statement") != "physical-observation" \
                or not _human_identity(attestation.get("by")) or not _timestamp(attestation.get("at")):
            errors.append("evaluated attempt needs a human physical-observation attestation with "
                          "an ISO-8601 timestamp + timezone")
        elif attestation.get("by") != outcome.get("evaluator"):
            errors.append("attestation.by must match outcome.evaluator")
        if isinstance(source, dict) and source.get("dirty") is not False:
            errors.append("evaluated qualification cannot promote an uncommitted source tree")
        results = [checks[c].get("result") for c in expected if c in checks]
        if state == "passed" and (not results or any(result != "pass" for result in results)
                                  or any(check.get("result") != "pass"
                                         for check in checks.values())):
            errors.append("passed attempt requires every recorded and required printed check to pass")
        if state == "failed" and not any(check.get("result") == "fail" for check in checks.values()):
            errors.append("failed attempt needs at least one failed check")
        for cid, check in checks.items():
            if check.get("result") in {"pass", "fail"}:
                if not _meaningful(check.get("observation")):
                    errors.append(f"evaluated check {cid} needs a raw observation")
                evidence = check.get("evidence")
                if not isinstance(evidence, list) or not evidence \
                        or not all(_meaningful(item) for item in evidence):
                    errors.append(f"evaluated check {cid} needs one or more evidence refs")

    covered, measurement_errors = _validate_measurements(record, spec)
    errors.extend(measurement_errors)
    if state == "passed" and "all_dimensions_within_tol" in expected:
        spec_dimensions = spec.get("dimensions") if isinstance(spec.get("dimensions"), list) else []
        needed = [d.get("name") for d in spec_dimensions
                  if isinstance(d, dict) and d.get("fit_critical") is True]
        absent = [name for name in needed if covered.get(name) != "pass"]
        if absent:
            errors.append("fit-critical dimensions lack passing repeated measurements: "
                          + ", ".join(str(name) for name in absent))

    learning = record.get("learning")
    if not isinstance(learning, dict):
        errors.append("learning must be a mapping"); learning = {}
    if state in {"planned", "reported"} and any(value not in (None, "") for value in learning.values()):
        errors.append(f"{state} record must leave observed learning fields null")
    if state in {"failed", "passed"} and not _meaningful(learning.get("observation")):
        errors.append("evaluated attempt needs learning.observation")
    if state == "failed":
        if not _meaningful(learning.get("failure_class")):
            errors.append("failed attempt needs learning.failure_class")
        if not _meaningful(learning.get("next_change")):
            errors.append("failed attempt needs learning.next_change")
    return {"passed": not errors, "state": state if state in STATES else None,
            "errors": errors, "measurements": covered}


def init_record(manifest_path: str, part_dir: str, *, iteration_id: str, attempt_kind: str,
                objective: str, parent: str | None = None) -> dict:
    root = _repo_root(part_dir)
    with open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    spec_path = os.path.join(part_dir, "spec.yaml")
    spec = _load_yaml(spec_path)
    design = evaluate_design(spec)
    if not design["passed"]:
        raise ValueError("; ".join(design["errors"]))
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("human_evaluation") != "not-evaluated":
        raise ValueError("handoff manifest is malformed or already claims human evaluation")
    part = next((row for row in manifest.get("parts", [])
                 if row.get("part_id") == spec.get("part_id")), None)
    if not part:
        raise ValueError("part is not present in the handoff manifest")
    if attempt_kind not in KINDS:
        raise ValueError("attempt_kind must be coupon or full-part")
    if not _meaningful(iteration_id) or not _meaningful(objective):
        raise ValueError("iteration id and objective must be non-placeholder text")
    identity = manifest["plate"]["slice_meta"]["identity"]
    criteria = (spec.get("acceptance") or {}).get("printed") or []
    return {
        "schema": SCHEMA, "iteration_id": iteration_id, "part_id": spec.get("part_id"),
        "parent": parent, "attempt_kind": attempt_kind, "objective": objective,
        "design_mode": design["mode"],
        "artifact": {
            "handoff_manifest": {"path": _repo_rel(manifest_path, root),
                                 "sha256": sha256_file(manifest_path)},
            "source": part["source"], "models": part["models"],
            "spec_sha256": part["spec"]["sha256"],
            "verify_stamp_sha256": part["verify"]["sha256"],
            "verify_step_sha256": part["verify"]["step_sha256"],
            "verify_report_sha256": manifest["plate"]["verify_report"]["sha256"],
            "gcode_sha256": manifest["plate"]["gcode"]["sha256"],
            "project_3mf_sha256": manifest["plate"]["project_3mf"]["sha256"],
            "slice_meta_sha256": manifest["plate"]["slice_meta"]["sha256"],
            "effective_config_sha256": identity["artifacts"]["effective_config_sha256"],
            "profiles": identity["profiles"], "slicer": identity["slicer"],
            "overrides": identity["overrides"], "post_hooks": identity["post_hooks"],
            "rotation": identity["rotation"],
            "support_requested": identity["support_requested"],
            "estimate": manifest["plate"].get("estimate"),
        },
        "execution": {
            "printer_id": None, "material": None, "material_brand": None,
            "filament_lot": None, "dry_state": None, "build_plate": None,
            "nozzle_mm": None, "layer_height_mm": None,
            "ambient_c": None, "ambient_rh_pct": None,
            "actual_material_g": None, "actual_print_time_minutes": None,
            "deviations": [], "post_processing": [],
        },
        "outcome": {
            "state": "planned", "printed_at": None, "operator": None,
            "evaluated_at": None, "evaluator": None, "mate_or_application": None,
            "checks": [{"id": criterion, "result": "not-evaluated",
                        "observation": None, "evidence": []} for criterion in criteria],
            "measurements": [],
        },
        "learning": {"failure_class": None, "observation": None,
                     "next_change": None, "promoted_sample": None},
        "attestation": None,
    }


def write_record(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(os.path.realpath(path)), exist_ok=True)
    if os.path.exists(path):
        raise ValueError(f"refusing to overwrite iteration record: {path}")
    with open(path, "w", encoding="utf-8") as stream:
        yaml.safe_dump(record, stream, sort_keys=False, allow_unicode=True)


def _spec_as_recorded(record: Any, spec: Any) -> Any:
    """The spec with the printed criteria THIS record was planned with.

    A coupon's spec gains criteria as it iterates, so an earlier iteration's record lacks the later
    ones (27 of 61 records on 2026-11-11). That makes it unfit to carry an evaluation against today's
    spec, and it stays counted as malformed for that. It does not make the person's words about that
    print unrecordable: a report evaluates no criterion, so it is checked against the record's own.
    """
    if not isinstance(record, dict) or not isinstance(spec, dict):
        return spec
    checks = (record.get("outcome") or {}).get("checks") if isinstance(record.get("outcome"), dict) else None
    own = [check.get("id") for check in checks or [] if isinstance(check, dict)]
    bound = dict(spec)
    acceptance = spec.get("acceptance") if isinstance(spec.get("acceptance"), dict) else {}
    bound["acceptance"] = dict(acceptance, printed=own)
    return bound


def add_report(record: dict, *, by: str, said: str, reading: str, source: str, recorded_by: str,
               at: str | None = None, next_change: str | None = None) -> dict:
    """Append the person's words to a record that nobody has evaluated yet, and mark it `reported`.

    A record the person has filled in (`printed`, `failed`, `passed`) is theirs: this refuses it.
    """
    outcome = record.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("state") not in {"planned", "reported"}:
        raise ValueError("only a planned or reported record takes a report; a record the person "
                         "has filled in is theirs to change")
    if at is None:
        at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    row = {"by": by, "said": said, "at": at, "recorded_by": recorded_by, "source": source,
           "reading": reading, "next_change": next_change}
    reports = record.get("reports")
    record["reports"] = (list(reports) if isinstance(reports, list) else []) + [row]
    outcome["state"] = "reported"
    return record


def rewrite_record(path: str, record: dict) -> None:
    """Replace an existing record in one step (the report command's only write)."""
    if not os.path.isfile(path):
        raise ValueError(f"no iteration record to update: {path}")
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        yaml.safe_dump(record, stream, sort_keys=False, allow_unicode=True)
    os.replace(temporary, path)


def matching_passed_tag(root: str, record_path: str) -> str | None:
    """Return a passed/* tag that names and contains these exact committed evidence bytes.

    `bench.sh passed` is the human-only bridge. A status field pointing at a plausible YAML file
    is not equivalent: the annotated tag is the independent, immutable confirmation that the
    observing human invoked that bridge for this record. Both path and hash are matched, and the
    tagged commit must contain those bytes. The tag need not be an ancestor: `bench.sh land`
    deliberately squash-merges revision branches while preserving their passed tags.
    """
    rel = _repo_rel(record_path, root)
    digest = sha256_file(record_path)
    proc = subprocess.run(
        ["git", "-C", root, "for-each-ref", "--format=%(refname:short)%00%(contents)%00",
         "refs/tags/passed/"], capture_output=True, text=True)
    if proc.returncode:
        raise ValueError(proc.stderr.strip() or "cannot inspect passed tags")
    fields = proc.stdout.split("\0")
    for index in range(0, len(fields) - 1, 2):
        tag, body = fields[index].strip(), fields[index + 1]
        values = {}
        for line in body.splitlines():
            key, sep, value = line.partition("=")
            if sep and key not in values:
                values[key] = value
        if values.get("evidence") != rel or values.get("evidence_sha256") != digest:
            continue
        tagged = subprocess.run(["git", "-C", root, "show", f"{tag}:{rel}"],
                                capture_output=True)
        if tagged.returncode == 0 and hashlib.sha256(tagged.stdout).hexdigest() == digest:
            return tag
    return None


def evaluate_part(part_dir: str) -> dict:
    errors: list[str] = []
    part_dir = os.path.realpath(part_dir)
    spec_path = os.path.join(part_dir, "spec.yaml")
    try:
        spec = _load_yaml(spec_path)
    except (OSError, yaml.YAMLError) as exc:
        return {"passed": False, "errors": [f"cannot read spec: {exc}"]}
    design = evaluate_design(spec)
    errors.extend(design["errors"])
    status = spec.get("status") if isinstance(spec, dict) else None
    if status not in STATUSES:
        errors.append("status must be draft, printed, dim-verified, or released")
    qualification = spec.get("qualification") if isinstance(spec, dict) else None
    current = qualification.get("current") if isinstance(qualification, dict) else None
    if status != "draft" and not _meaningful(current):
        errors.append(f"status {status!r} needs qualification.current pointing at exact QA evidence")
    if _meaningful(current):
        record_path = os.path.realpath(os.path.join(part_dir, current))
        iteration_root = os.path.realpath(os.path.join(part_dir, "qa", "iterations"))
        if not (record_path.startswith(iteration_root + os.sep) and record_path.endswith(".yaml")):
            errors.append("qualification.current must stay under qa/iterations/ and name a YAML record")
            record_path = ""
        try:
            record = _load_yaml(record_path) if record_path else None
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"cannot read qualification.current {current}: {exc}")
        else:
            if record is None:
                return {"passed": False, "status": status, "mode": design.get("mode"),
                        "errors": errors}
            try: root = _repo_root(part_dir)
            except ValueError as exc: errors.append(str(exc)); root = None
            checked = evaluate_record(record, spec, repo_root=root, check_files=bool(root))
            errors.extend("qualification.current: " + error for error in checked["errors"])
            state = checked["state"]
            if status == "printed" and state not in {"printed", "failed", "passed"}:
                errors.append("status printed needs a record whose physical print is recorded")
            if status in {"dim-verified", "released"} and state != "passed":
                errors.append(f"status {status} needs a passed physical record")
            if status == "dim-verified":
                spec_dimensions = (spec.get("dimensions")
                                   if isinstance(spec.get("dimensions"), list) else [])
                needed = [d.get("name") for d in spec_dimensions
                          if isinstance(d, dict) and d.get("fit_critical") is True]
                absent = [name for name in needed if checked["measurements"].get(name) != "pass"]
                if absent:
                    errors.append("dim-verified status lacks passing fit-critical measurements: "
                                  + ", ".join(str(name) for name in absent))
            # `printed` records an observed attempt, including a failed one. The stronger statuses
            # claim accepted evidence and therefore require the separate human-only passed/* tag.
            if status in {"dim-verified", "released"} and root:
                try:
                    passed_tag = matching_passed_tag(root, record_path)
                except (OSError, ValueError) as exc:
                    errors.append(f"cannot verify human passed/* tag: {exc}")
                else:
                    if not passed_tag:
                        errors.append("accepted status needs a human passed/* tag bound to and "
                                      "containing qualification.current path + SHA-256")
    return {"passed": not errors, "status": status, "mode": design.get("mode"), "errors": errors}


def collect_metrics(root: str) -> dict:
    records, malformed = [], 0
    for path in Path(root).glob("parts/**/qa/iterations/*.yaml"):
        try:
            record = _load_yaml(path)
            part_dir = path.parent.parent.parent
            spec = _load_yaml(part_dir / "spec.yaml")
            # Never let a half-filled or internally contradictory YAML row improve the dashboard.
            # Old attempts remain byte records, but if they no longer validate against the current
            # spec/schema they are counted as malformed rather than guessed into an outcome.
            reported = isinstance(record, dict) and isinstance(record.get("outcome"), dict) \
                and record["outcome"].get("state") == "reported"
            checked = evaluate_record(record, _spec_as_recorded(record, spec) if reported else spec,
                                      check_files=False)
            if not checked["passed"]:
                malformed += 1; continue
            records.append(record)
        except (OSError, yaml.YAMLError):
            malformed += 1
    states = collections.Counter((r.get("outcome") or {}).get("state") for r in records)
    kinds = collections.Counter(r.get("attempt_kind") for r in records)
    failures = collections.Counter((r.get("learning") or {}).get("failure_class")
                                   for r in records
                                   if (r.get("outcome") or {}).get("state") == "failed")
    failures.pop(None, None)
    # A reported record counts by the reading of its latest report. It is never an evaluation:
    # `evaluated`, the pass rate and the loops below look at failed and passed records only.
    readings = collections.Counter(((r.get("reports") or [{}])[-1]).get("reading")
                                   for r in records
                                   if (r.get("outcome") or {}).get("state") == "reported")
    evaluated = states["failed"] + states["passed"]
    by_part: dict[str, list[dict]] = collections.defaultdict(list)
    for record in records:
        if record.get("attempt_kind") == "full-part" \
                and (record.get("outcome") or {}).get("state") in {"failed", "passed"}:
            by_part[record.get("part_id")].append(record)
    first_pass = 0
    loops_to_pass: list[int] = []
    accepted_material: list[float] = []
    accepted_time: list[float] = []
    accepted_actual_material: list[float] = []
    accepted_actual_time: list[float] = []
    for attempts in by_part.values():
        # Iteration ids are required stable identifiers and normally date-prefixed; parent chains
        # remain in each record for deeper analysis without guessing chronology from mtime.
        attempts.sort(key=lambda row: str(row.get("iteration_id")))
        if attempts and attempts[0]["outcome"]["state"] == "passed":
            first_pass += 1
        for index, attempt in enumerate(attempts):
            if attempt["outcome"]["state"] == "passed":
                loops_to_pass.append(index + 1)
                prefix = attempts[:index + 1]
                grams = [(r.get("artifact") or {}).get("estimate", {}).get("filament_g")
                         for r in prefix]
                seconds = [(r.get("artifact") or {}).get("estimate", {}).get("print_time_seconds")
                           for r in prefix]
                actual_grams = [(r.get("execution") or {}).get("actual_material_g")
                                for r in prefix]
                actual_minutes = [(r.get("execution") or {}).get("actual_print_time_minutes")
                                  for r in prefix]
                if all(_finite(value) for value in grams): accepted_material.append(sum(grams))
                if all(_finite(value) for value in seconds): accepted_time.append(sum(seconds))
                if all(_finite(value) for value in actual_grams):
                    accepted_actual_material.append(sum(actual_grams))
                if all(_finite(value) for value in actual_minutes):
                    accepted_actual_time.append(sum(actual_minutes))
                break
    return {
        "records": len(records), "malformed": malformed, "states": dict(states),
        "kinds": dict(kinds), "evaluated": evaluated, "reported_readings": dict(readings),
        "evaluated_pass_rate": states["passed"] / evaluated if evaluated else None,
        "parts_with_full_attempts": len(by_part), "first_pass_parts": first_pass,
        "first_pass_rate": first_pass / len(by_part) if by_part else None,
        "mean_full_part_loops_to_pass": (sum(loops_to_pass) / len(loops_to_pass)
                                         if loops_to_pass else None),
        "failure_classes": dict(failures),
        "repeated_failure_count": sum(max(0, count - 1) for count in failures.values()),
        "mean_plate_estimated_material_g_per_accept": (
            sum(accepted_material) / len(accepted_material) if accepted_material else None),
        "mean_plate_estimated_minutes_per_accept": (
            sum(accepted_time) / 60 / len(accepted_time) if accepted_time else None),
        "mean_actual_material_g_per_accept": (
            sum(accepted_actual_material) / len(accepted_actual_material)
            if accepted_actual_material else None),
        "mean_actual_minutes_per_accept": (
            sum(accepted_actual_time) / len(accepted_actual_time)
            if accepted_actual_time else None),
    }


def _print_result(label: str, result: dict) -> int:
    for error in result.get("errors", []):
        print(f"  [FAIL] {error}")
    print(f"{label}: {'PASS' if result['passed'] else 'FAIL'}")
    return 0 if result["passed"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    design = sub.add_parser("design"); design.add_argument("part")
    part = sub.add_parser("part"); part.add_argument("part")
    manifest = sub.add_parser("manifest"); manifest.add_argument("--outdir", required=True)
    manifest.add_argument("--part", action="append", default=[])
    init = sub.add_parser("init"); init.add_argument("--manifest", required=True)
    init.add_argument("--part", required=True); init.add_argument("--id", required=True)
    init.add_argument("--kind", required=True, choices=sorted(KINDS))
    init.add_argument("--objective", required=True); init.add_argument("--parent")
    init.add_argument("--output", required=True)
    record = sub.add_parser("record"); record.add_argument("record"); record.add_argument("--spec")
    record.add_argument("--require-state", choices=sorted(STATES))
    record.add_argument("--require-current", action="store_true")
    report = sub.add_parser("report", help="write down what the person said about a print")
    report.add_argument("--record", required=True); report.add_argument("--spec")
    report.add_argument("--by", required=True, help="the person who handled the print")
    report.add_argument("--said", required=True, help="their own words, not a paraphrase")
    report.add_argument("--reading", required=True, choices=sorted(READINGS))
    report.add_argument("--source", required=True, help="where the words can be found")
    report.add_argument("--recorded-by", required=True, help="who is writing them down")
    report.add_argument("--at", help="when they said it, ISO-8601 with timezone (default: now)")
    report.add_argument("--next-change", help="what changes next, as the recorder understands it")
    metrics = sub.add_parser("metrics"); metrics.add_argument("root", nargs="?", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "design":
            spec = _load_yaml(os.path.join(args.part, "spec.yaml"))
            return _print_result("DESIGN_INTENT_RESULT", evaluate_design(spec))
        if args.command == "part":
            return _print_result("QUALIFICATION_RESULT", evaluate_part(args.part))
        if args.command == "manifest":
            path = write_handoff_manifest(args.outdir, args.part)
            print(f"qualification manifest -> {path}")
            print("QUALIFICATION_MANIFEST_RESULT: PASS")
            return 0
        if args.command == "init":
            record = init_record(args.manifest, args.part, iteration_id=args.id,
                                 attempt_kind=args.kind, objective=args.objective,
                                 parent=args.parent)
            write_record(args.output, record)
            print(f"planned iteration -> {args.output}")
            print("No physical result or human attestation was created.")
            return 0
        if args.command == "record":
            record_path = os.path.realpath(args.record)
            spec_path = args.spec
            if not spec_path:
                cursor = Path(record_path).parent
                while cursor != cursor.parent and not (cursor / "spec.yaml").is_file():
                    cursor = cursor.parent
                spec_path = str(cursor / "spec.yaml")
            spec = _load_yaml(spec_path)
            result = evaluate_record(_load_yaml(record_path), spec,
                                     repo_root=_repo_root(record_path),
                                     require_state=args.require_state)
            if args.require_current:
                part_dir = os.path.dirname(os.path.realpath(spec_path))
                current = ((spec.get("qualification") or {}).get("current")
                           if isinstance(spec, dict) else None)
                resolved = (os.path.realpath(os.path.join(part_dir, current))
                            if isinstance(current, str) and current else None)
                iteration_root = os.path.realpath(os.path.join(part_dir, "qa", "iterations"))
                if not record_path.startswith(iteration_root + os.sep):
                    result["errors"].append("physical record must live under the part's qa/iterations/")
                    result["passed"] = False
                if resolved != record_path:
                    result["errors"].append(
                        "spec qualification.current does not point at this record")
                    result["passed"] = False
            return _print_result("QUALIFICATION_RECORD_RESULT", result)
        if args.command == "report":
            record_path = os.path.realpath(args.record)
            spec_path = args.spec
            if not spec_path:
                cursor = Path(record_path).parent
                while cursor != cursor.parent and not (cursor / "spec.yaml").is_file():
                    cursor = cursor.parent
                spec_path = str(cursor / "spec.yaml")
            record = add_report(_load_yaml(record_path), by=args.by, said=args.said,
                                reading=args.reading, source=args.source,
                                recorded_by=args.recorded_by, at=args.at,
                                next_change=args.next_change)
            # Structure only: the artifact bytes were bound when the record was planned, and a
            # report must still be recordable after the source has moved on to the next version.
            result = evaluate_record(record, _spec_as_recorded(record, _load_yaml(spec_path)),
                                     check_files=False, require_state="reported")
            if result["passed"]:
                rewrite_record(record_path, record)
                print(f"reported -> {args.record}")
                print("The person's words were recorded. No check was evaluated and no status changes.")
            return _print_result("QUALIFICATION_REPORT_RESULT", result)
        if args.command == "metrics":
            report = collect_metrics(args.root)
            print(json.dumps(report, indent=2, sort_keys=True))
            print("Metrics describe recorded future attempts only; absence is not success.")
            print("A reported record is the person's words, not an evaluation.")
            return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"{args.command}: FAIL — {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
