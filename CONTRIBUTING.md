# Contributing to Model-Agnostic 3D Printing Workflow

Thanks for helping improve this workflow! This repository is built to stay lean, model-agnostic, and safe around real hardware.

## Core principles to preserve

1. **Human approval is a hard boundary.** Nothing in a PR may auto-upload, auto-start, or bypass `APPROVED=1` / `CONFIRMED=1` gates.
2. **Deterministic gates block; heuristics warn.** Only exact, reproducible facts (B-rep validity, declared probes, bed fit, artifact SHA-256 identity, per-ID inventory) may block a plate. Sampled mesh/DFM heuristics stay advisory.
3. **Model-agnostic by design.** Never couple pipeline stages to a single AI provider, editor, or proprietary memory service.
4. **No private data or print dumps.** Use minimal synthetic fixtures in tests, never raw printer logs with credentials/IPs, local home-directory paths, or large binary print outputs.

## Development setup

```bash
git clone https://github.com/jrszilard/model-agnostic-3d-printing-workflow.git
cd model-agnostic-3d-printing-workflow

# Install the local pre-push guard (runs scripts/check-public.py)
scripts/install-hooks.sh

# Run all unit and gate tests
platform/pipeline/test.sh

# Run the public hygiene & secret guard
python3 scripts/check-public.py --all
```

If you have CadQuery installed (e.g. in `~/cadquery-env/bin/python` or `$CADQUERY_PY`), `platform/pipeline/test.sh` automatically runs the CadQuery suites too. Pass `--require-cadquery` to fail if CadQuery is missing.

## Updating specific areas

- **Adding or modifying a gate (`*_RESULT`):** update `platform/pipeline/gates.txt` and ensure `platform/pipeline/test_gates.py` passes. Any flag-dependent checker must call `gates.declare_mode()`.
- **Editing `parts/_lib/joints.py`:** regenerate the mirror with `python3 parts/_lib/render_registry.py` (tested by `test.sh`).
- **Adding a worked example:** place small, self-contained, AGPL-3.0-compatible examples under `examples/<name>/` (source, `spec.yaml`, README, and compact exports well under the 2 MiB file limit — no `.gcode` files).
- **Adding a printer/slicer adapter:** keep credentials in an external env file (with only a `.env.example` placeholder in the repo), preserve `handoff.txt` + `qualification_manifest.json` + `APPROVED=1` checks, and add offline unit tests using mocks/fixtures.

## Pull request checklist

- [ ] `platform/pipeline/test.sh` passes
- [ ] `python3 scripts/check-public.py` passes
- [ ] New behavior includes offline unit tests (covering both pass and fail/refusal paths)
- [ ] Relevant docs (`platform/pipeline/README.md`, `docs/workflow.md`, etc.) are updated
- [ ] No credentials, local paths, or unapproved large artifacts are included
