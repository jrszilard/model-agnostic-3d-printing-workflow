# Worked Example: `examples/cable-clip`

A minimal, AGPL-3.0-licensed parametric CadQuery part demonstrating the digital verification loop end-to-end.

- **Geometry:** Print-flat desk clip for a nominal 6.0 mm cord (24 × 16 × 10 mm, zero overhangs, zero supports, flat on Z=0).
- **Contract:** `spec.yaml` declares `design.mode: originate`, dimension provenance, bounding-box measurement recipes, and three exact B-rep probes (`cable-bore-clear`, `entry-slot-open`, `back-wall-solid`).

## Try it locally

```bash
# 1. Regenerate deterministic STL + STEP from CadQuery source
platform/pipeline/generate/build.sh examples/cable-clip/src/cable-clip.py examples/cable-clip

# 2. Verify CAD B-rep integrity, spec dimensions, provenance, and probes
platform/pipeline/verify/verify.sh examples/cable-clip

# 3. Check forward qualification contract (draft part, ready for prototype print)
python3 platform/pipeline/verify/qualification_check.py part examples/cable-clip
```
