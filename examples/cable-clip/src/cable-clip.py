#!/usr/bin/env python3
"""Minimal worked example: print-flat desk cable clip for a 6.0 mm cord.

Prints flat on Z=0 with zero supports and zero overhangs. Demonstrates:
- reading dimensions directly from spec.yaml (no duplicate magic numbers)
- deterministic STL + STEP export via platform/pipeline/generate/build.sh
- exact B-rep verification with final-solid probes via verify.sh
"""
from __future__ import annotations

import os
import sys

import cadquery as cq
import yaml

HERE = os.path.dirname(os.path.realpath(__file__))
PART_DIR = os.path.realpath(os.path.join(HERE, ".."))
SPEC_PATH = os.path.join(PART_DIR, "spec.yaml")


def load_dims(spec_path: str = SPEC_PATH) -> dict[str, float]:
    with open(spec_path, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    return {row["name"]: float(row["nominal"]) for row in spec["dimensions"]}


def build(dims: dict[str, float] | None = None) -> cq.Workplane:
    d = dims or load_dims()
    width = d["overall_width"]
    depth = d["overall_depth"]
    height = d["clip_height"]
    bore_d = d["cable_bore_diameter"]
    slot_w = d["entry_slot_width"]
    back_wall = d["back_wall_thickness"]

    bore_r = bore_d / 2.0
    # Place back wall at Y = -depth/2 .. (-depth/2 + back_wall); bore directly in front of it.
    y_back = -depth / 2.0
    bore_y = y_back + back_wall + bore_r
    slot_len = (depth / 2.0) - bore_y + 2.0

    # Assert key geometric invariants before exporting.
    assert bore_d > slot_w > 0, "entry slot must be narrower than cable bore for retention"
    assert width - bore_d >= 6.0, "side arms must stay >= 3.0 mm thick each"
    assert bore_y + bore_r < depth / 2.0, "cable bore must stay inside the clip depth"

    body = (
        cq.Workplane("XY")
        .box(width, depth, height, centered=(True, True, False))
        .edges("|Z")
        .fillet(1.5)
    )

    bore = (
        cq.Workplane("XY")
        .center(0.0, bore_y)
        .circle(bore_r)
        .extrude(height + 2.0)
        .translate((0.0, 0.0, -1.0))
    )

    slot = (
        cq.Workplane("XY")
        .center(0.0, bore_y + slot_len / 2.0)
        .rect(slot_w, slot_len)
        .extrude(height + 2.0)
        .translate((0.0, 0.0, -1.0))
    )

    clip = body.cut(bore).cut(slot)
    return clip


def main() -> None:
    outdir = sys.argv[1] if len(sys.argv) > 1 else PART_DIR
    stl_dir = os.path.join(outdir, "stl")
    step_dir = os.path.join(outdir, "step")
    os.makedirs(stl_dir, exist_ok=True)
    os.makedirs(step_dir, exist_ok=True)

    solid = build()
    cq.exporters.export(solid, os.path.join(stl_dir, "cable-clip.stl"))
    cq.exporters.export(solid, os.path.join(step_dir, "cable-clip.step"))


if __name__ == "__main__":
    main()
