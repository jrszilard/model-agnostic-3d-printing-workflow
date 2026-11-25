#!/usr/bin/env python3
"""Create an annotated orthographic decision drawing from the REAL exported STL.

Perspective answers form. This answers “which edge/face/side?” in a shared coordinate frame.
Annotations are JSON/YAML:
  [{"text":"15 mm bore", "at":[0,0], "label":[-25,10]},
   {"text":"Edge B", "at":[-10.5,-6]}]
Coordinates are the two axes shown by --view, in mm. Output may be PNG or SVG.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import numpy as np


VIEWS = {
    "top": {"plane": (0, 1), "depth": 2, "axes": ("X", "Y"), "look": "-Z", "name": "PLAN"},
    "front": {"plane": (0, 2), "depth": 1, "axes": ("X", "Z"), "look": "-Y", "name": "FRONT"},
    "side": {"plane": (1, 2), "depth": 0, "axes": ("Y", "Z"), "look": "-X", "name": "SIDE"},
}


def load_stl(path):
    with open(path, "rb") as stream:
        data = stream.read()
    if len(data) >= 84:
        count = struct.unpack("<I", data[80:84])[0]
        if len(data) == 84 + count * 50:
            raw = np.frombuffer(data[84:], dtype=np.dtype([
                ("normal", "<3f4"), ("vertices", "<3f4", 3), ("attr", "<u2")]))
            return raw["vertices"].astype(np.float64)
    text = data.decode("ascii", errors="ignore")
    vertices = [[float(n) for n in match] for match in
                re.findall(r"\bvertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)", text)]
    if not vertices or len(vertices) % 3:
        raise ValueError("not a binary or parseable ASCII STL")
    return np.asarray(vertices, dtype=np.float64).reshape((-1, 3, 3))


def project(triangles, view):
    spec = VIEWS[view]
    plane, depth = spec["plane"], spec["depth"]
    projected = triangles[:, :, plane]
    order = np.argsort(triangles[:, :, depth].mean(axis=1))  # far first, near last
    return projected[order], triangles[order, :, depth].mean(axis=1)


def load_annotations(path):
    if not path:
        return []
    with open(path) as stream:
        if path.lower().endswith(".json"):
            data = json.load(stream)
        else:
            import yaml
            data = yaml.safe_load(stream)
    if not isinstance(data, list):
        raise ValueError("annotations must be a list")
    for item in data:
        if not isinstance(item, dict) or not item.get("text") or len(item.get("at", [])) != 2:
            raise ValueError("each annotation needs text and at:[u,v]")
    return data


def _dimension(ax, p0, p1, text, text_offset=(0, 0)):
    ax.annotate("", xy=p1, xytext=p0,
                arrowprops=dict(arrowstyle="<->", color="#1f2937", lw=1.0))
    mid = ((p0[0] + p1[0]) / 2 + text_offset[0], (p0[1] + p1[1]) / 2 + text_offset[1])
    ax.text(*mid, text, ha="center", va="center", fontsize=9, color="#111827",
            bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.92))


def draw(triangles, output, view="top", title=None, annotations=()):
    spec = VIEWS[view]
    projected, depth = project(triangles, view)
    d1, d2 = projected[:, 1] - projected[:, 0], projected[:, 2] - projected[:, 0]
    area2 = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
    polygons = projected[area2 > 1e-10]
    all_points = projected.reshape((-1, 2))
    lo, hi = all_points.min(axis=0), all_points.max(axis=0)
    width, height = hi - lo
    span = max(width, height, 1.0)
    pad = span * 0.12

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.add_collection(PolyCollection(polygons, facecolors="#dfe6ea", edgecolors="none",
                                     linewidths=0, antialiased=True))
    # A faint second pass on non-degenerate facet boundaries makes holes/steps legible without
    # turning the drawing into a tessellation map.
    ax.add_collection(PolyCollection(polygons, facecolors="none", edgecolors="#6b7280",
                                     linewidths=0.08, alpha=0.22))

    # Overall dimensions live outside the object.
    ydim = lo[1] - pad * 0.48
    xdim = lo[0] - pad * 0.48
    _dimension(ax, (lo[0], ydim), (hi[0], ydim), f"{spec['axes'][0]} {width:.2f} mm")
    _dimension(ax, (xdim, lo[1]), (xdim, hi[1]), f"{spec['axes'][1]} {height:.2f} mm",
               text_offset=(-pad * 0.10, 0))

    for item in annotations:
        target = tuple(float(v) for v in item["at"])
        label = tuple(float(v) for v in item.get("label", (target[0] + pad * 0.35,
                                                            target[1] + pad * 0.35)))
        ax.annotate(str(item["text"]), xy=target, xytext=label, fontsize=10, color="#0f3b5f",
                    ha=item.get("ha", "left"), va="center",
                    arrowprops=dict(arrowstyle="->", color="#0f3b5f", lw=1.1),
                    bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="#9fb3c2", alpha=0.96))

    # Coordinate-frame legend: the crucial difference from an unlabeled render.
    origin = (lo[0] + pad * 0.10, hi[1] + pad * 0.35)
    xtip, ytip = (origin[0] + pad * 0.45, origin[1]), (origin[0], origin[1] + pad * 0.45)
    ax.annotate("", xy=xtip, xytext=origin, arrowprops=dict(arrowstyle="->", lw=1))
    ax.annotate("", xy=ytip, xytext=origin, arrowprops=dict(arrowstyle="->", lw=1))
    ax.text(xtip[0] + pad * 0.05, xtip[1], "+" + spec["axes"][0], va="center", fontsize=9)
    ax.text(ytip[0], ytip[1] + pad * 0.05, "+" + spec["axes"][1], ha="center", fontsize=9)

    heading = title or os.path.basename(output).rsplit(".", 1)[0]
    ax.set_title(f"{heading}\n{spec['name']} — looking toward {spec['look']} · real exported mesh",
                 fontsize=13)
    ax.set_xlabel(spec["axes"][0] + " (mm)"); ax.set_ylabel(spec["axes"][1] + " (mm)")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(lo[0] - pad, hi[0] + pad); ax.set_ylim(lo[1] - pad, hi[1] + pad)
    ax.grid(True, color="#d1d5db", linewidth=0.4, alpha=0.55)
    fig.tight_layout(); fig.savefig(output, dpi=150); plt.close(fig)
    return {"width": float(width), "height": float(height), "view": view,
            "annotations": len(annotations)}


def write_stamp(stl, output):
    # Hash the file as it stands -- do NOT canonicalise it first. This used to import c14n_stl and
    # rewrite the input here, once per view, and c14n_stl.py:48-51 writes in place and
    # non-atomically: polling a 3.5 MB STL through that rewrite catches it at 0 bytes, so a sibling
    # view (or one of the five OpenSCAD readers render.sh points at the same file) could hash a
    # truncated file and record that sha256 as this drawing's identity. render.sh canonicalises
    # once up front now, so these are already the canonical bytes stamp.sh:23-24 hashes; run
    # standalone on a raw export, the stamp names the bytes the drawing was actually made from.
    with open(stl, "rb") as stream:
        digest = hashlib.sha256(stream.read()).hexdigest()
    try:
        branch = subprocess.run(["git", "branch", "--show-current"], text=True,
                                capture_output=True, check=False).stdout.strip() or "?"
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], text=True,
                                capture_output=True, check=False).stdout.strip() or "?"
        version = branch + "@" + commit
    except OSError:
        version = "?"
    stamp = os.path.splitext(output)[0] + ".stamp"
    with open(stamp, "w") as stream:
        stream.write("geom=%s\nsha256=%s\nsource=%s\nversion=%s\nview=%s\n" %
                     (digest[:8], digest, os.path.realpath(stl), version,
                      os.path.basename(output)))
    return stamp


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("stl"); parser.add_argument("output")
    parser.add_argument("--view", choices=sorted(VIEWS), default="top")
    parser.add_argument("--title")
    parser.add_argument("--annotations", help="JSON/YAML callout list")
    args = parser.parse_args(argv)
    result = draw(load_stl(args.stl), args.output, args.view, args.title,
                  load_annotations(args.annotations))
    stamp = write_stamp(args.stl, args.output)
    print("drawing -> %s  |  %s %.2f x %.2f mm  |  %d callout(s)  |  %s" %
          (args.output, result["view"], result["width"], result["height"],
           result["annotations"], stamp))


if __name__ == "__main__":
    main()
