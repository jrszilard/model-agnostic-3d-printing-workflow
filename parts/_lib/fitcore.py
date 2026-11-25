"""Semantic identity for mating geometry across cosmetic/structural variants.

`geom id` hashes an exported STL. `fitcore.fingerprint` hashes only the values that define mating
geometry, so two visibly different variants can inherit one physical fit confirmation — but only
when final-solid ROI probes also prove neighboring geometry did not invade that core.

The v1 payload intentionally matches the established consumer convention:
    key=repr(value);key=repr(value)
with an explicit pair order. Do not silently switch algorithms; existing fit evidence names
`40ccf5aca833a2cd`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping

ALGORITHM = "sha256-kv-repr-v1"
_FINGERPRINT = re.compile(r"^[0-9a-f]{16}$")


class FitCoreError(RuntimeError):
    pass


def ordered_pairs(values):
    if isinstance(values, Mapping):
        return [(key, values[key]) for key in sorted(values)]
    pairs = list(values)
    if any(not isinstance(item, (list, tuple)) or len(item) != 2 for item in pairs):
        raise TypeError("fit-core values must be a mapping or sequence of (name, value) pairs")
    return [(str(key), value) for key, value in pairs]


def payload(values):
    return ";".join("%s=%r" % (key, value) for key, value in ordered_pairs(values))


def fingerprint(values, length=16):
    if length < 8 or length > 64:
        raise ValueError("fingerprint length must be 8..64")
    return hashlib.sha256(payload(values).encode("utf-8")).hexdigest()[:length]


def report(values, label="fit"):
    ident = fingerprint(values)
    return "%s[%s]: %s" % (label, ident, payload(values))


def _as_fingerprint(value):
    return value if isinstance(value, str) else fingerprint(value)


def assert_variants_share_core(variants, expected=None):
    found = {name: _as_fingerprint(value) for name, value in variants.items()}
    if not found:
        raise FitCoreError("no variants supplied for fit-core comparison")
    baseline = expected or next(iter(found.values()))
    bad = {name: ident for name, ident in found.items() if ident != baseline}
    if bad:
        raise FitCoreError("fit-core mismatch: expected %s; %s" %
                           (baseline, ", ".join("%s=%s" % item for item in bad.items())))
    return {"fingerprint": baseline, "variants": found}


def assert_fit_regions(variants, regions, volume_tol=1e-5, bbox_tol=None):
    """Prove every final variant equals each frozen reference inside its exact ROI.

    `regions` maps label -> (reference_solid, roi_solid). Imported lazily so this module stays
    dependency-free for verify/registry use.
    """
    from probe import assert_frozen_region
    results = {}
    for variant, solid in variants.items():
        results[variant] = {}
        for label, (reference, roi) in regions.items():
            results[variant][label] = assert_frozen_region(
                solid, reference, roi, volume_tol=volume_tol, bbox_tol=bbox_tol,
                label="%s %s" % (variant, label))
    return results


def declaration(values, variants, source, regions=()):
    core = fingerprint(values)
    agreement = assert_variants_share_core(variants, expected=core)
    return {"algorithm": ALGORITHM, "fingerprint": core, "source": source,
            "variants": agreement["variants"], "regions": list(regions)}


def write_manifest(path, values, variants, source, regions=()):
    data = declaration(values, variants, source, regions)
    os.makedirs(os.path.dirname(os.path.realpath(path)), exist_ok=True)
    with open(path, "w") as stream:
        json.dump(data, stream, indent=2, sort_keys=True); stream.write("\n")
    return data


def evaluate_declaration(data):
    if not data:
        return {"passed": True, "declared": False, "fingerprint": None,
                "variants": {}, "rows": []}
    rows, failed = [], False
    algorithm = data.get("algorithm")
    core = data.get("fingerprint")
    source = data.get("source")
    if algorithm != ALGORITHM:
        rows.append(("FAIL", "algorithm", "expected %s, got %r" % (ALGORITHM, algorithm)))
        failed = True
    if not isinstance(core, str) or not _FINGERPRINT.fullmatch(core):
        rows.append(("FAIL", "fingerprint", "must be 16 lowercase hex characters"))
        failed = True
    if not source:
        rows.append(("FAIL", "source", "fit_core must name its owning source module"))
        failed = True
    variants = data.get("variants") or {}
    if not isinstance(variants, dict):
        rows.append(("FAIL", "variants", "must be a name -> fingerprint mapping"))
        variants = {}
        failed = True
    for name, ident in variants.items():
        if not isinstance(ident, str) or not _FINGERPRINT.fullmatch(ident):
            rows.append(("FAIL", str(name), "invalid variant fingerprint %r" % ident))
            failed = True
        elif isinstance(core, str) and ident != core:
            rows.append(("FAIL", str(name), "variant %s does not match core %s" % (ident, core)))
            failed = True
        else:
            rows.append(("PASS", str(name), "fit-identical to core"))
    return {"passed": not failed, "declared": True, "fingerprint": core,
            "variants": variants, "source": source, "rows": rows}
