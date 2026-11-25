"""Installed runtime byte/license inventory WITHOUT importing CAD.

This is local evaluation identity, not a frozen image or redistribution audit.
Read only a caller-selected installed environment and explicit system binaries.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def tree_inventory(root):
    root = Path(root)
    files = {}
    for path in sorted(root.rglob("*")):
        name = str(path.relative_to(root))
        if path.is_symlink():
            # Record links, never recursively follow a directory link into another tree.
            files[name] = {"symlink": str(path.readlink())}
        elif path.is_file():
            files[name] = {"sha256": file_hash(path), "bytes": path.stat().st_size}
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"root": str(root), "tree_sha256": hashlib.sha256(encoded).hexdigest(), "files": files}


def inventory(root):
    root = Path(root)
    sites = sorted(root.glob("lib/python*/site-packages"))
    packages = []
    for distribution in importlib.metadata.distributions(path=[str(p) for p in sites]):
        metadata = distribution.metadata
        licenses = {}
        for relative in distribution.files or ():
            if any("license" in p.lower() or "copying" in p.lower() for p in relative.parts):
                path = distribution.locate_file(relative)
                if path.is_file():
                    licenses[str(relative)] = file_hash(path)
        packages.append({"name": metadata["Name"], "version": distribution.version,
                         "license": metadata.get("License-Expression") or metadata.get("License"),
                         "license_classifiers": [v for v in metadata.get_all("Classifier", []) if v.startswith("License")],
                         "requires": metadata.get_all("Requires-Dist", []), "license_files": licenses})
    paths = [Path("/usr/bin/python3").resolve(), Path("/usr/bin/freecadcmd").resolve(),
             Path("/usr/lib/freecad/lib/FreeCAD.so"), Path("/usr/lib/freecad/lib/Part.so"),
             Path("/usr/lib/freecad/lib/Mesh.so"), Path("/usr/bin/bwrap"),
             Path("/usr/share/licenses/opencascade/LICENSE_LGPL_21.txt"),
             Path("/usr/share/licenses/opencascade/OCCT_LGPL_EXCEPTION.txt"),
             Path("/usr/share/licenses/spdx/LGPL-2.0-only.txt")]
    return {"scope": "local installed evaluation; not production pin or redistribution clearance",
            "environment": tree_inventory(root), "packages": sorted(packages, key=lambda p: p["name"].lower()),
            "system_files": {str(p): file_hash(p) for p in paths}}
