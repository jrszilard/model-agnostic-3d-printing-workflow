#!/usr/bin/env python3
"""Guardrails for the public workflow repository.

Blocks the three classes of accidental leaks before a commit or push leaves the machine:
  1. Secrets & credentials (.env files, private keys, API tokens, non-placeholder printer
     passwords, RFC1918 private LAN IPv4 addresses).
  2. Local machine paths (/home/<user>/, /Users/<user>/, C:\\Users\\, private workspace roots).
  3. Repo scope / print-job bloat (personal parts/<category>/, build/, photoref/, vendor/,
     sell-details/, .gcode, videos, or files larger than the size cap).

Name, email, and curated example prints under examples/ are explicitly allowed.

Usage:
    python3 scripts/check-public.py [--root <dir>] [--all] [--max-bytes N]
        default: scans git-tracked + staged files (falls back to walking tree if not a git repo)
        --all:   scans all non-ignored files in the working tree
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB per tracked file

ALLOWED_ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "VERSION",
    "prusalink.env.example",
}

ALLOWED_PREFIXES = (
    ".github/",
    "docs/",
    "examples/",
    "parts/_TEMPLATE/",
    "parts/_lib/",
    "platform/",
    "scripts/",
    "slicer-profiles/",
)

BLOCKED_BASENAMES = {
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "prusalink.env",
}

BLOCKED_EXTENSIONS = {
    ".avi",
    ".gcode",
    ".gco",
    ".key",
    ".mov",
    ".mp4",
    ".p12",
    ".pem",
    ".pfx",
}

TEXT_CHECK_SKIP_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".stl",
    ".webp",
    ".zip",
}

# Build regexes cleanly so this file does not match its own literal secret patterns.
_PK_HDR = "-----BEGIN " + r"(?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
_PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "example",
    "fake",
    "none",
    "password",
    "placeholder",
    "replace-me",
    "replace_me",
    "secret",
    "test",
    "your-api-key",
    "your-password",
    "your_api_key",
    "your_password",
    "<api-key>",
    "<api key>",
    "<password>",
}

SECRET_PATTERNS = [
    ("private key block", re.compile(_PK_HDR)),
    ("OpenAI/Anthropic API key", re.compile(r"\bsk-(?:proj|ant)-[A-Za-z0-9_-]{16,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("OpenRouter API key", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{20,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}")),
    (
        "private LAN IPv4 address",
        re.compile(
            r"(?<![0-9.])(?:192\.168\.\d{1,3}\.\d{1,3}"
            r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![0-9.])"
        ),
    ),
]

ENV_SECRET_ASSIGN = re.compile(
    r"^\s*(?:export\s+)?(PRUSALINK_(?:PASSWORD|KEY|API_KEY)|[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD))\s*=\s*([^\s#]+)"
)

LOCAL_PATH_PATTERNS = [
    ("local Linux home path", re.compile(r"/home/[A-Za-z0-9._-]+/")),
    ("local macOS home path", re.compile(r"/Users/[A-Za-z0-9._-]+/")),
    ("local Windows home path", re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\")),
    ("private workspace directory", re.compile(r"lakeshore" + r"-studio")),
    ("private consumer sibling path", re.compile(r"\.\./3d-car-parts" + r"-maker")),
    ("private knowledge-base path", re.compile(r"knowledge-base/" + r"projects/")),
    ("private config directory", re.compile(r"\.config/" + r"lakeshore/")),
]

IGNORE_MARKER = "check-public: allow-line"
MARKER_ALLOWED_FILES = {"scripts/check-public.py", "scripts/test_check_public.py"}


def list_files(root: Path, scan_all: bool = False) -> list[str]:
    """Return sorted repo-relative POSIX paths to scan."""
    git_dir = root / ".git"
    if git_dir.exists():
        cmd = ["git", "-C", str(root), "ls-files", "-z"]
        if scan_all:
            cmd = ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        out = subprocess.check_output(cmd)
        rels = [p for p in out.decode("utf-8", errors="surrogateescape").split("\0") if p]
        return sorted(set(rels))

    rels = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".venv", "node_modules"}]
        for name in names:
            rel = Path(base, name).relative_to(root).as_posix()
            rels.append(rel)
    return sorted(rels)


def _is_env_secret_file(rel: str) -> bool:
    name = os.path.basename(rel).lower()
    if name.endswith(".env.example") or name.endswith(".env.sample") or name.endswith(".env.template"):
        return False
    return name == ".env" or name.endswith(".env") or name.startswith(".env.")


def check_path(rel: str) -> list[str]:
    issues = []
    if "/" not in rel:
        if rel not in ALLOWED_ROOT_FILES:
            issues.append(f"{rel}: unexpected root file (add to allowlist or remove)")
    else:
        if not rel.startswith(ALLOWED_PREFIXES):
            issues.append(
                f"{rel}: outside allowed public folders ({', '.join(ALLOWED_PREFIXES)})"
            )

    base = os.path.basename(rel).lower()
    ext = os.path.splitext(base)[1]
    if base in BLOCKED_BASENAMES or _is_env_secret_file(rel):
        issues.append(f"{rel}: blocked credential/environment file")
    if ext in BLOCKED_EXTENSIONS:
        if ext == ".gcode" and re.match(r"^platform/pipeline/[^/]+/testdata/[^/]+\.gcode$", rel):
            pass
        else:
            issues.append(f"{rel}: blocked file extension ({ext})")
    return issues


def _looks_like_placeholder(raw: str) -> bool:
    val = raw.strip().strip("\"'").strip()
    if not val:
        return True
    if val.startswith(("$", "${", "<", "{{")):
        return True
    if val.lower() in _PLACEHOLDER_VALUES:
        return True
    return False


def check_content(rel: str, path: Path, max_bytes: int) -> list[str]:
    issues = []
    if not path.is_file() or path.is_symlink():
        if path.is_symlink():
            issues.append(f"{rel}: symlinks are not allowed in the public workflow tree")
        return issues

    size = path.stat().st_size
    if size > max_bytes:
        issues.append(f"{rel}: {size} bytes exceeds public size cap ({max_bytes} bytes)")

    ext = os.path.splitext(rel)[1].lower()
    if ext in TEXT_CHECK_SKIP_EXTENSIONS:
        return issues

    data = path.read_bytes()
    if b"\x00" in data[:8192]:
        return issues

    text = data.decode("utf-8", errors="replace")
    allow_marker = rel in MARKER_ALLOWED_FILES
    for lineno, line in enumerate(text.splitlines(), start=1):
        if allow_marker and IGNORE_MARKER in line:
            continue
        for label, rx in SECRET_PATTERNS:
            if rx.search(line):
                issues.append(f"{rel}:{lineno}: potential {label}")
        for label, rx in LOCAL_PATH_PATTERNS:
            if rx.search(line):
                issues.append(f"{rel}:{lineno}: {label}")
        m = ENV_SECRET_ASSIGN.match(line)
        if m:
            var, val = m.group(1), m.group(2)
            if not _looks_like_placeholder(val) and not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*\(", val):
                # Allow short code/test identifiers like `token = foo` only when not an env file;
                # in .env / shell-style ALL_CAPS assignments, flag literal values >= 8 chars.
                cleaned = val.strip().strip("\"'")
                if len(cleaned) >= 8 and not cleaned.startswith(("os.", "args.", "env.", "cfg.")):
                    issues.append(f"{rel}:{lineno}: literal value assigned to {var}")
    return issues


def scan_tree(root: Path, scan_all: bool = False, max_bytes: int = DEFAULT_MAX_BYTES) -> list[str]:
    issues: list[str] = []
    for rel in list_files(root, scan_all=scan_all):
        full = root / rel
        if not full.exists() and not full.is_symlink():
            continue  # deleted in worktree
        issues.extend(check_path(rel))
        issues.extend(check_content(rel, full, max_bytes=max_bytes))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--all", action="store_true", help="also scan untracked non-ignored files")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    issues = scan_tree(root, scan_all=args.all, max_bytes=args.max_bytes)
    if issues:
        for item in issues:
            print(f"  [FAIL] {item}", file=sys.stderr)
        print(f"PUBLIC_GUARD_RESULT: FAIL ({len(issues)} issue(s))", file=sys.stderr)
        return 1
    print("PUBLIC_GUARD_RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
