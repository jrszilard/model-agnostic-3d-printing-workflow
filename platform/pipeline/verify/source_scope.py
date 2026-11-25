"""Per-part, explicit dependency scopes. Unrelated working files are never touched.

Declarations cover non-Python/C++ file reads too; build provenance additionally checks observed
Python imports/reads. This is not a claim to infer arbitrary dynamic/native dependency closure.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess


PIPELINE = Path(__file__).resolve().parents[1]
PLATFORM = PIPELINE.parents[1]
IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache"}


def git(root, *args, binary=False):
    # Hooks export repository-local variables; -C alone does not override those.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                       text=not binary, env=env)
    if p.returncode:
        error = p.stderr.decode(errors="replace") if binary else p.stderr
        raise ValueError(error.strip() or "source identity git command failed")
    return p.stdout if binary else p.stdout.strip()


def repo_root(path):
    path = Path(path).resolve()
    return Path(git(path if path.is_dir() else path.parent, "rev-parse", "--show-toplevel")).resolve()


def canonical_root(root):
    """First worktree is the owning checkout; linked worktrees are not delivery roots."""
    rows = git(root, "worktree", "list", "--porcelain").splitlines()
    first = next((line[9:] for line in rows if line.startswith("worktree ")), None)
    if not first:
        raise ValueError("cannot resolve the canonical owning checkout")
    return Path(first).resolve()


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def local_path(root, name, *, exists=True):
    if not isinstance(name, str) or not name or name.startswith(":") \
            or any(c in name for c in "*?[]\n\r\0"):
        raise ValueError(f"expected a literal relative path: {name!r}")
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"path must stay inside its repository: {name}")
    absolute = root / p
    # Do not let an in-tree symlink conceal a different input or output namespace.
    if any(q.is_symlink() for q in (absolute, *absolute.parents) if q != root.parent):
        raise ValueError(f"symlink is not a source/output declaration: {name}")
    resolved = absolute.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError(f"path escapes or selects entire repository: {name}")
    if exists and not resolved.exists():
        raise ValueError(f"missing declared input: {name}")
    return resolved


def files_in(path):
    if path.is_file():
        return [path]
    result = []
    for base, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        for name in dirs:
            if (Path(base) / name).is_symlink():
                raise ValueError(f"symlink source directory: {Path(base) / name}")
        for name in sorted(files):
            p = Path(base) / name
            if p.suffix in {".pyc", ".pyo"}:
                continue
            if p.is_symlink() or not p.is_file():
                raise ValueError(f"non-regular source dependency: {p}")
            result.append(p)
    if not result:
        raise ValueError(f"empty declared source directory: {path}")
    return result


def declarations(root, part, spec):
    """Return source inputs only. Outputs and unrelated part docs are not build inputs."""
    build = spec.get("build") or {}
    if not isinstance(build, dict) or not isinstance(build.get("source"), str):
        raise ValueError("spec build.source must name its generator relative to the part")
    source = local_path(part, build["source"])
    if not source.is_relative_to(part / "src") or source.suffix != ".py":
        raise ValueError("build.source currently requires Python/CadQuery under the part's src/; legacy generators remain buildable, not cacheable")
    scopes = {root: {part / "spec.yaml", part / "src"}}
    # Local shared library is a conservative implicit dependency for ordinary platform parts.
    # Consumers declare external shared/cross-part inputs explicitly below.
    if (root / "parts/_lib").is_dir():
        scopes[root].add(root / "parts/_lib")
    deps = spec.get("source_dependencies", [])
    if not isinstance(deps, list):
        raise ValueError("source_dependencies must be a list")
    for dep in deps:
        if not isinstance(dep, dict) or set(dep) != {"repository", "paths"}:
            raise ValueError("source_dependencies entries need exactly repository and paths")
        location, paths = dep["repository"], dep["paths"]
        if not isinstance(location, str) or not location or Path(location).is_absolute():
            raise ValueError("dependency repository must be relative to the owning checkout")
        other = (root / location).resolve()
        if repo_root(other) != other:
            raise ValueError(f"dependency repository must name a git root: {location}")
        if not isinstance(paths, list) or not paths:
            raise ValueError("dependency paths must be a nonempty list")
        scopes.setdefault(other, set()).update(local_path(other, p) for p in paths)
    return scopes


def snapshot(root, scopes):
    rows = []
    for repository, paths in sorted(scopes.items(), key=lambda item: str(item[0])):
        files = sorted({f for path in paths for f in files_in(path)})
        rows.append({"repository": os.path.relpath(repository, root),
                     "files": {str(f.relative_to(repository)): digest(f) for f in files}})
    return rows


def assert_committed(root, rows):
    """Compare actual bytes to HEAD (also catches assume-unchanged and ignored source files)."""
    identities = []
    for row in rows:
        repository = (root / row["repository"]).resolve()
        commit = git(repository, "rev-parse", "HEAD")
        errors = []
        for name, expected in row["files"].items():
            path = local_path(repository, name)
            if digest(path) != expected:
                errors.append(f"changed since build: {name}")
                continue
            try:
                committed = git(repository, "show", f"{commit}:{name}", binary=True)
            except ValueError:
                errors.append(f"not committed: {name}")
                continue
            if hashlib.sha256(committed).hexdigest() != expected:
                errors.append(f"uncommitted change: {name}")
        if errors:
            raise ValueError("part/dependency source checkpoint required in " + str(repository)
                             + ":\n  " + "\n  ".join(errors))
        identities.append({**row, "commit": commit, "dirty": False})
    return identities


def outputs(part, spec):
    names = [spec.get("primary_stl"), spec.get("primary_step")]
    extra = (spec.get("build") or {}).get("outputs", [])
    if not isinstance(extra, list):
        raise ValueError("build.outputs must be a list")
    names += extra
    if not all(isinstance(p, str) and p for p in names):
        raise ValueError("build provenance requires explicit primary_stl and primary_step")
    result = [local_path(part, name, exists=False) for name in dict.fromkeys(names)]
    for p in result:
        if p.is_relative_to(part / "src") or p.name in {"spec.yaml", "prepare.yaml", ".gitignore"}:
            raise ValueError(f"generator output cannot overwrite its source/contract: {p}")
    if not names[0].endswith(".stl") or not names[1].endswith(".step"):
        raise ValueError("primary_stl/primary_step must name .stl/.step exports")
    return result


def producer_path(root, part):
    return root / "build/.producers" / part.relative_to(root) / "build_manifest.json"
