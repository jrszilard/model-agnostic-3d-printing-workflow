"""Generator-side entrypoint for the platform's dimension provenance gate.

Usage before exporting a fitting part:

    from provenance import require_fit_provenance
    require_fit_provenance(spec["dimensions"], "arm interface")

Review forms/gauges should carry their estimated/placeholder labels physically instead of weakening
this gate. The authoritative policy lives in platform/pipeline/verify/dim_provenance.py.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_VERIFY = os.path.realpath(os.path.join(_HERE, "../../platform/pipeline/verify"))
sys.path.insert(0, _VERIFY)

from dim_provenance import (FIT_TRUSTED, PROVENANCE_VALUES, ProvenanceError,  # noqa: E402,F401
                            evaluate_provenance, require_fit_provenance)       # noqa: E402,F401
