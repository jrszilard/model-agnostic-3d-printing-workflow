#!/usr/bin/env python3
"""Requested vs sliced part IDs. No CAD, provider, printer connection, or physical claims.

request and catalog capture independent inputs. check is read-only; record writes the comparison
for the handoff. bound verifies its byte bindings, never grants approval. Exit 19 = stop.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

HERE = Path(__file__).resolve().parent
REQUEST = "plate-request.json"
CATALOG = "inventory-catalog.json"
REPORT = "plate-inventory.json"
REFS = "inventory-models"
GCODE = "plate_1.gcode"
PROJECT = "plate.3mf"
META = "slice_meta.json"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,95}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
ERRORS = (
    ValueError,
    OSError,
    KeyError,
    TypeError,
    IndexError,
    OverflowError,
    RecursionError,
    ParseError,
    BadZipFile,
    ImportError,
)


def sha(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{path.name}: missing or not a regular local file")
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def unique(rows):
    out = {}
    for k, v in rows:
        if k in out:
            raise ValueError(f"duplicate field or ID: {k}")
        out[k] = v
    return out


def load(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{path.name}: missing or not a regular local file")
    data = json.loads(path.read_bytes(), object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise TypeError(f"{path.name}: expected JSON object")
    return data


def dump(data):
    return json.dumps(data, indent=2, allow_nan=False, sort_keys=True) + "\n"


def mapping(data, name):
    if (
        type(data.get("schema")) is not int
        or data["schema"] != 1
        or not isinstance(data.get(name), dict)
        or not data[name]
    ):
        raise ValueError(f"expected schema 1 and nonempty {name} mapping")
    if any(not ID.fullmatch(k) for k in data[name]):
        raise ValueError("invalid part ID")
    return data[name]


def counts(data):
    wants = mapping(data, "requested")
    if any(type(n) is not int or not 1 <= n <= 10000 for n in wants.values()):
        raise ValueError("quantities must be positive whole numbers")
    return wants


def refs(p, cat):
    models = mapping(cat, "models")
    result = {}
    if cat.get("placement") not in ("center-bed", "as-saved"):
        raise ValueError("unknown project-to-G-code registration")
    if (p / REFS).is_symlink():
        raise ValueError("reference folder must be local")
    for code, digest in models.items():
        if not isinstance(digest, str) or not HEX.fullmatch(digest):
            raise ValueError(f"{code}: invalid catalog digest")
        path = p / REFS / (digest + ".stl")
        if sha(path) != digest:
            raise ValueError(f"{code}: catalog mesh changed")
        result[code] = path
    return result


def inputs(p):
    wants = counts(load(p / REQUEST))
    catalog = load(p / CATALOG)
    sources = refs(p, catalog)
    missing = sorted(wants.keys() - sources.keys())
    if missing:
        raise ValueError("missing named source mesh for " + ", ".join(missing))
    return wants, catalog["placement"], sources


def pairs(args):
    result = unique(tuple(v.split("=", 1)) for v in args)
    if not result or any(not ID.fullmatch(k) or not v.strip() for k, v in result.items()):
        raise ValueError("use explicit ID=value pairs")
    return result


def capture(p, command, entries, placement):
    from plate_scope import require_open

    require_open(p)
    if any(os.path.lexists(p / n) for n in ("sent.json", "handoff.txt")):
        raise ValueError("existing sent/presented packet: use a fresh output directory")
    filename = REQUEST if command == "request" else CATALOG
    dst = p / filename
    if os.path.lexists(dst):
        raise ValueError(f"{filename} already exists; preserve this request and use a new revision")
    data = pairs(entries)
    p.mkdir(parents=True, exist_ok=True)
    if command == "request":
        doc = {"schema": 1, "requested": {k: int(v) for k, v in data.items()}}
        counts(doc)
        if os.path.lexists(p / GCODE) or os.path.lexists(p / PROJECT):
            raise ValueError("capture the brief before slicing; do not infer intent from finished output")
    else:
        counts(load(p / REQUEST))
        store = p / REFS
        if store.is_symlink():
            raise ValueError("reference folder must be local")
        store.mkdir(exist_ok=True)
        models = {}
        for code, v in data.items():
            path = Path(v)
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            dest = store / (digest + ".stl")
            if not os.path.lexists(dest):
                with dest.open("xb") as stream:
                    stream.write(raw)
            if sha(dest) != digest:
                raise ValueError(f"{code}: conflicting reference file")
            models[code] = digest
        doc = {"schema": 1, "placement": placement, "models": models}
    with dst.open("x", encoding="utf-8") as f:
        f.write(dump(doc))
    return str(dst)


def identities(p):
    return {n: sha(p / n) for n in (REQUEST, CATALOG, PROJECT, GCODE, META)}


def compare(p):
    r = {
        "schema": 1,
        "verdict": "UNPROVEN",
        "requested": {},
        "project_counts": {},
        "sliced": {},
        "missing": {},
        "extra": {},
        "instances": [],
        "problems": [],
        "read_project": False,
        "read_paths": False,
    }
    try:
        r["requested"] = counts(load(p / REQUEST))
        ids = identities(p)
        wants, placement, sources = inputs(p)
        r["requested"] = wants
        r["sha256"] = ids
        meta = load(p / META)
        if meta.get("schema") != 2:
            raise ValueError("unknown slice_meta.json schema")
        a = meta["artifacts"]
        if not isinstance(a, dict):
            raise TypeError("invalid slice artifact identities")
        if (a.get("gcode_sha256"), a.get("project_3mf_sha256")) != (ids[GCODE], ids[PROJECT]):
            raise ValueError("slice_meta.json does not bind these G-code AND 3MF bytes")
        if str(HERE / "verify") not in sys.path:
            sys.path.insert(0, str(HERE / "verify"))
        from inventory_geometry import bodies, same_mesh, stl
        from inventory_paths import witnesses

        meshes = bodies(p / PROJECT)
        catalog = {k: stl(ref.read_bytes()) for k, ref in sources.items()}
        project = Counter()
        observed = Counter()
        for i, m in enumerate(meshes):
            candidates = [k for k, a in catalog.items() if same_mesh(a, m)]
            label = candidates[0] if len(candidates) == 1 else None
            r["instances"].append({"instance": i + 1, "part_id": label, "triangles": len(m)})
            if label is None:
                r["problems"].append(
                    f"instance {i + 1}: "
                    + ("ambiguous IDs " + ", ".join(candidates) if candidates else "uncatalogued geometry")
                )
            else:
                project[label] += 1
        r["project_counts"] = dict(project)
        r["read_project"] = True
        paths, stats = witnesses(meshes, p / GCODE, placement)
        r["deposition"] = stats
        r["read_paths"] = True
        for row, proof in zip(r["instances"], paths, strict=True):
            row.update(proof)
            k = row["part_id"]
            if k and proof["through_height"]:
                observed[k] += 1
            elif not proof["through_height"]:
                r["problems"].append(
                    f"instance {row['instance']} ({k or '?'}): no exclusive model extrusion across its printed height"
                )
        if stats["unassigned_model_moves"]:
            r["problems"].append("model extrusion outside the identified pieces")
        if stats["ambiguous_model_moves"]:
            r["problems"].append("model extrusion ambiguously assigned to multiple pieces")
        r["sliced"] = dict(observed)
        r["missing"] = dict(Counter(wants) - observed)
        r["extra"] = dict(observed - Counter(wants))
        if ids != identities(p):
            raise ValueError("inventory or slice inputs changed during check")
        if r["problems"]:
            return r
        r["verdict"] = "MISMATCH" if r["missing"] or r["extra"] else "PASS"
    except ERRORS as e:
        r["problems"].append(str(e))
    return r


def record(p, result):
    with tempfile.NamedTemporaryFile(dir=p, mode="w", prefix=".inventory-", delete=False) as f:
        f.write(dump(result))
    os.replace(f.name, p / REPORT)


def bound(p, fields=None, gcode=None):
    if fields is None:
        lines = (p / "handoff.txt").read_text().splitlines()
        key = "inventory_sha"
        fields = {key: [s[len(key) + 1 :] for s in lines if s.startswith(key + "=")]}
    wants, _, _ = inputs(p)
    r = load(p / REPORT)
    ids = identities(p)
    if gcode is not None and sha(gcode) != ids[GCODE]:
        raise ValueError("file selected for upload is not the inventory-checked G-code")
    if (
        fields.get("inventory_sha") != [sha(p / REPORT)]
        or type(r.get("schema")) is not int
        or r["schema"] != 1
        or r.get("verdict") != "PASS"
        or r.get("sha256") != ids
        or (r.get("project_counts"), r.get("requested"), r.get("sliced")) != (wants, wants, wants)
        or r.get("problems") != []
    ):
        raise ValueError(
            "inventory evidence missing, changed or not PASS; fresh check and handoff required"
        )
    return wants


def render(r):
    keys = sorted(set(r["requested"]) | set(r["project_counts"]) | set(r["sliced"]))
    rows = ["Part ID                requested    in 3MF   in G-code"]
    for k in keys:
        project = r["project_counts"].get(k, 0) if r["read_project"] else "?"
        confirmed = r["sliced"].get(k, 0) if r["read_paths"] else "?"
        rows.append(f"{k:<22} {r['requested'].get(k, 0):>9} {project:>9} {confirmed:>11}")
    for key in ("missing", "extra"):
        if r[key]:
            rows.append(key + ": " + ", ".join(f"{k} x{v}" for k, v in sorted(r[key].items())))
    rows.extend("  " + s for s in r["problems"])
    rows.append("INVENTORY_RESULT: " + r["verdict"])
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("request", "catalog", "check", "record", "bound"):
        q = sub.add_parser(name)
        q.add_argument("plate", type=Path)
        if name in ("request", "catalog"):
            q.add_argument("entries", nargs="+", metavar="ID=VALUE")
        if name == "catalog":
            q.add_argument("--placement", choices=("center-bed", "as-saved"), default="center-bed")
        if name == "bound":
            q.add_argument("--gcode", type=Path, help="also bind the exact file selected for upload")
        if name in ("check", "record"):
            q.add_argument("--json", action="store_true")
    a = parser.parse_args()
    p = a.plate.resolve()
    try:
        if a.cmd in ("request", "catalog"):
            print(capture(p, a.cmd, a.entries, getattr(a, "placement", None)))
        elif a.cmd == "bound":
            bound(p, gcode=a.gcode)
            print("inventory bindings OK (not approval)")
        else:
            if a.cmd == "record":
                from plate_scope import require_open

                require_open(p)
                if os.path.lexists(p / "sent.json"):
                    raise ValueError("sent packet: preserve historical evidence; inspect read-only")
            r = compare(p)
            if a.cmd == "record":
                record(p, r)
            print(dump(r) if a.json else render(r))
            return 0 if r["verdict"] == "PASS" else 19
    except ERRORS as e:
        print(f"inventory: {e}", file=sys.stderr)
        return 19
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
