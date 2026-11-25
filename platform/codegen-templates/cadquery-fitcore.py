"""One module owns mating inputs; final variants prove the output inside frozen ROIs."""
from pathlib import Path
import sys

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "parts" / "_lib").is_dir())
sys.path.insert(0, str(ROOT / "parts" / "_lib"))
from fitcore import assert_fit_regions, assert_variants_share_core, fingerprint, report  # noqa: E402

# Explicit order preserves sha256-kv-repr-v1 across Python refactors and existing fit records.
FIT_VALUES = [
    ("shaft_d", 8.0),
    ("throat", 7.6),
    ("mount_pitch", 20.0),
]
FIT_ID = fingerprint(FIT_VALUES)


def print_fit_identity():
    print(report(FIT_VALUES, "fit"))


def prove_variants(variant_values, final_solids, frozen_regions):
    """Call before export.

    variant_values: {name: ordered FIT_VALUES}
    final_solids:   {name: completed CadQuery solid}
    frozen_regions: {name: (reference solid, exact ROI solid)}
    """
    assert_variants_share_core(variant_values, expected=FIT_ID)
    return assert_fit_regions(final_solids, frozen_regions, volume_tol=1e-5, bbox_tol=1e-5)


# spec.yaml declaration:
# fit_core:
#   algorithm: sha256-kv-repr-v1
#   fingerprint: <FIT_ID>
#   source: src/fit_critical.py
#   variants: {faithful: <FIT_ID>, expressive: <FIT_ID>}
#   regions: [shaft, mounting-face]
