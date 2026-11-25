#!/usr/bin/env python3
"""Minimal part generator skeleton — copy into parts/<category>/<part>/src/ and rename."""
from pathlib import Path
import sys

import cadquery as cq
import yaml

HERE = Path(__file__).resolve().parent
PART = HERE.parent
ROOT = next(parent for parent in HERE.parents if (parent / "parts" / "_lib").is_dir())
sys.path.insert(0, str(ROOT / "parts" / "_lib"))
from probe import assert_single_solid, assert_valid, assert_volume_range  # noqa: E402
from provenance import require_fit_provenance                              # noqa: E402


def telemetry(label, workplane):
    shape = workplane.val()
    assert_valid(shape, label); assert_single_solid(shape, label)
    box = shape.BoundingBox()
    print("%-16s volume %9.2f mm3 · bbox %.2f x %.2f x %.2f · solids 1" %
          (label, shape.Volume(), box.xlen, box.ylen, box.zlen))
    return workplane


def build():
    # Explicit datum: never replace this with faces(">Z") after adding another feature.
    base = cq.Workplane("XY").box(40, 24, 4, centered=(True, True, False))
    telemetry("base", base)
    boss = cq.Workplane("XY").workplane(offset=4).circle(5).extrude(8)
    result = telemetry("base + boss", base.union(boss))
    assert_volume_range(result, minimum=40 * 24 * 4, label="final")
    return result


def main():
    with open(PART / "spec.yaml") as stream:
        spec = yaml.safe_load(stream) or {}
    require_fit_provenance(spec.get("dimensions") or [], spec.get("part_id", "part"))
    result = build()
    (PART / "stl").mkdir(exist_ok=True); (PART / "step").mkdir(exist_ok=True)
    stem = PART.name
    cq.exporters.export(result, str(PART / "stl" / (stem + ".stl")))
    cq.exporters.export(result, str(PART / "step" / (stem + ".step")))
    print("exported", stem)


if __name__ == "__main__":
    main()
