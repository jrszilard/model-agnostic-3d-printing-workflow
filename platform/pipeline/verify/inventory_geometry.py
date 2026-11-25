"""Identify detached physical pieces in the actual Prusa 3MF, irrespective of file/object count.

No CAD reconstruction or nearest-shape guessing. Match every oriented triangle to a pinned
source mesh once, independent of order. The tolerance covers float32 serialization only.
"""

from collections import defaultdict
from itertools import product
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import numpy as np

EPS = 0.0002  # mm, after translation to a common origin
OFFSETS = tuple(product((-1, 0, 1), repeat=3))
NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"


def stl(data):
    n = int.from_bytes(data[80:84], "little")
    if n and len(data) == 84 + 50 * n:
        dtype = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
        a = np.frombuffer(data, dtype, offset=84)["v"].astype(float)
    else:
        v = [
            list(map(float, l.split()[1:]))
            for l in data.decode("ascii").splitlines()
            if l.lstrip().startswith("vertex ")
        ]
        a = np.array(v, dtype=float).reshape(-1, 3, 3)
    if not len(a) or not np.isfinite(a).all():
        raise ValueError("empty or non-finite source STL")
    return a


def connected(v, faces):
    """Surface connectivity through shared edges; coordinate-weld split STL vertex indices."""
    if not len(faces) or faces.min() < 0 or faces.max() >= len(v) or not np.isfinite(v).all():
        raise ValueError("invalid or empty printable 3MF mesh")
    pts, ix = np.unique(v, axis=0, return_inverse=True)
    f = ix.reshape(-1)[faces]
    parents = list(range(len(f)))
    edges = {}

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for i, (a, b, c) in enumerate(f.tolist()):
        for x, y in ((a, b), (b, c), (c, a)):
            e = (min(x, y), max(x, y))
            other = edges.setdefault(e, i)
            if other != i:
                parents[root(i)] = root(other)
    groups = defaultdict(list)
    for i in range(len(f)):
        groups[root(i)].append(i)
    return [pts[f[ix]] for ix in groups.values()]


def transform(elem):
    raw = elem.get("transform")
    m = np.eye(4)
    if raw is not None:
        m[:, :3] = np.array([float(x) for x in raw.split()]).reshape(4, 3)
    if not np.isfinite(m).all():
        raise ValueError("non-finite 3MF transform")
    return m


def bodies(path):
    with ZipFile(path) as z:

        def xml(name):
            entries = [e for e in z.infolist() if e.filename == name]
            if len(entries) != 1 or entries[0].file_size > 256 * 1024**2:
                raise ValueError("missing/duplicate/oversize 3MF entry: " + name)
            return ET.fromstring(z.read(entries[0]))

        r = xml("3D/3dmodel.model")
        if "Metadata/Slic3r_PE_model.config" in z.namelist():
            cfg = xml("Metadata/Slic3r_PE_model.config")
            for m in cfg.iter("metadata"):
                if (m.get("key") == "volume_type" and m.get("value") != "ModelPart") or (
                    m.get("key") == "modifier" and m.get("value") != "0"
                ):
                    raise ValueError(
                        "modifier/negative/support-control volumes need a separately supported identity method"
                    )
    if r.tag != NS + "model" or r.get("unit", "millimeter") != "millimeter" or r.get("requiredextensions"):
        raise ValueError("expected a supported millimetre 3MF core model")
    objs = {}
    seen = 0
    for o in r.findall(f"./{NS}resources/{NS}object"):
        if o.get("id") in objs:
            raise ValueError("duplicate 3MF object id")
        objs[o.attrib["id"]] = o

    def visit(link, placement, ancestry):
        nonlocal seen
        if any(k.endswith("}path") for k in link.attrib):
            raise ValueError("external component not supported")
        idx = link.attrib["objectid"]
        seen += 1
        if idx in ancestry or seen > 10000:
            raise ValueError("cyclic/excessive 3MF build graph")
        o = objs[idx]
        mat = transform(link) @ placement
        if o.get("type", "model") != "model":
            raise ValueError("unsupported active non-model object")
        child = o.find(NS + "components")
        mesh = o.find(NS + "mesh")
        if (child is None) == (mesh is None):
            raise ValueError("ambiguous object geometry")
        if mesh is None:
            for c in child.findall(NS + "component"):
                yield from visit(c, mat, ancestry | {idx})
        else:
            v = np.array(
                [[float(a.attrib[k]) for k in "xyz"] for a in mesh.findall(f"./{NS}vertices/{NS}vertex")]
            )
            f = np.array(
                [
                    [int(a.attrib[k]) for k in ("v1", "v2", "v3")]
                    for a in mesh.findall(f"./{NS}triangles/{NS}triangle")
                ],
                dtype=int,
            )
            yield from connected(v @ mat[:3, :3] + mat[3, :3], f)

    result = []
    for item in r.findall(f"./{NS}build/{NS}item"):
        flag = item.get("printable", "1")
        if flag not in ("0", "1", "true", "false"):
            raise ValueError("invalid printable flag")
        if flag in ("1", "true"):
            result.extend(visit(item, np.eye(4), set()))
    if not result:
        raise ValueError("no printable mesh bodies in 3MF build")
    return result


def same_mesh(a, b):
    if a.shape != b.shape:
        return False
    # Common nominal print pose, plus any of the four bed-plane quarter-turns used by arrange.py.
    target = b - b.min(axis=(0, 1))
    size = target.max(axis=(0, 1))
    pairs = target.tolist()
    cells = np.floor(target.mean(axis=1) * 20).astype(int).tolist()
    for _ in range(4):
        a = np.stack((-a[:, :, 1], a[:, :, 0], a[:, :, 2]), axis=-1)
        ref = a - a.min(axis=(0, 1))
        if np.max(np.abs(ref.max(axis=(0, 1)) - size)) > EPS:
            continue
        grid = defaultdict(list)
        tris = ref.tolist()
        for j, c in enumerate(np.floor(ref.mean(axis=1) * 20).astype(int).tolist()):
            grid[tuple(c)].append(j)

        def find(key, t, grid=grid, tris=tris):
            bucket = grid.get(key, ())
            for j in bucket:
                s = tris[j]
                for k in range(3):
                    if all(abs(s[(i + k) % 3][d] - t[i][d]) <= EPS for i in range(3) for d in range(3)):
                        bucket.remove(j)
                        return True
            return False

        for c, t in zip(cells, pairs):
            x, y, z = c
            if not find(tuple(c), t) and not any(
                find((x + i, y + j, z + k), t) for i, j, k in OFFSETS if i or j or k
            ):
                break
        else:
            return True
    return False
