# Model-Agnostic 3D Printing Workflow

**A model-agnostic, human-approved verification and print-handoff workflow for parametric 3D-printed parts.**

Bring any AI coding/CAD agent (Claude, Codex, Gemini, Pi, local models) — or write CadQuery/OpenSCAD by hand. The workflow checks exported geometry, specs, slices, and plate inventory with deterministic gates and **always stops for explicit human approval before anything touches a printer**.

## Why this exists

AI models can write decent parametric CAD, but they cannot physically measure a mating part, verify that a slicer respected supports/bed bounds, or safely authorize a printer upload. This workflow separates:

- **Propose & iterate (AI or human):** write parametric CAD (`src/`), render five views + face-labelled drawings, refine in the fast digital loop.
- **Verify deterministically (code):** check OCCT B-rep validity, dimension provenance, final-solid probes, slice/toolpath integrity, per-ID plate inventory, and artifact SHA-256 bindings.
- **Decide & attest (human only):** approve every upload (`APPROVED=1`), inspect real prints, record physical measurements, and confirm releases (`CONFIRMED=1`).

```text
idea / measurements ─► spec.yaml ─► build (STL + STEP) ─► render (5 views + face labels)
                                          ▲                        │
                                          │    fast digital loop   ▼
                                          └────── refine ◄─── verify (B-rep + probes + spec)
                                                                   │
                                                                   ▼
                        plate_inventory ─► slice ─► verify-slice ─► handoff ─► [HUMAN STOP]
                                                                                     │
                                                                          APPROVED=1 ▼
                                        measure & record ◄── print ◄─────────── send.sh
```

## Architecture: keep your parts separate from the workflow

This repository is the **reusable workflow engine only**. Your personal, studio, or commercial parts live in your own **consumer repository** (private or public), which invokes this repo through thin wrappers — zero duplicated pipeline scripts, zero syncing headaches:

```text
model-agnostic-3d-printing-workflow   (this repo — engine, shared _lib, templates, docs, examples)
        ▲                                      ▲
        │ consumes                             │ consumes
        │                                      │
  your-personal-parts                    your-product-parts
  (your private/public parts,            (another venture or project,
   build/, photos, QA records)            pinned via PLATFORM_VERSION)
```

Wire any parts repo to this workflow in one command:

```bash
# Clone this workflow next to your parts repo (or add it as a git submodule)
git clone https://github.com/jrszilard/model-agnostic-3d-printing-workflow.git

# Scaffold consumer wrappers inside your parts repo
../model-agnostic-3d-printing-workflow/scripts/init-consumer.sh /path/to/your-parts-repo
```

That creates `platform.consumer.yaml`, `PLATFORM_VERSION`, and thin `scripts/platform/*.sh` wrappers (`prepare.sh`, `build.sh`, `render.sh`, `verify.sh`, `slice.sh`, `verify-slice.sh`, `handoff.sh`, `qualification.sh`, `next-action.sh`, `plate-inventory.sh`, `plate-scope.sh`, `send.sh`). See [`docs/consumer-contract.md`](docs/consumer-contract.md).

## Quickstart

### 1. Run the workflow test suite (no printer required)

```bash
# Runs all pure-Python / Bash gate & contract suites (and CadQuery suites if ~/cadquery-env exists)
platform/pipeline/test.sh

# Run the public-repo hygiene & secret guard
python3 scripts/check-public.py

# Install the local pre-push hook so check-public.py runs automatically before every push
scripts/install-hooks.sh
```

### 2. Inspect a worked example

See [`examples/cable-clip/`](examples/cable-clip/README.md) for a minimal, open-source parametric CadQuery part with a `spec.yaml`, B-rep probes, and passing `verify.sh` output.

If you have CadQuery (`~/cadquery-env/bin/python`, or set `CADQUERY_PY`) installed:

```bash
platform/pipeline/generate/build.sh examples/cable-clip/src/cable-clip.py examples/cable-clip
platform/pipeline/verify/verify.sh examples/cable-clip
```

### 3. Configure a printer (optional, outside the repo)

Copy `prusalink.env.example` to `~/.config/3d-printing-workflow/prusalink.env` (or point `PRUSALINK_ENV` at your own file outside git). Never commit real printer credentials.

```bash
mkdir -p ~/.config/3d-printing-workflow
cp prusalink.env.example ~/.config/3d-printing-workflow/prusalink.env
$EDITOR ~/.config/3d-printing-workflow/prusalink.env
```

## Key components

| Path | What it provides |
|---|---|
| `AGENTS.md` & `platform/AGENTS.md` | Model-agnostic agent contract (works with any AI client) |
| `platform/pipeline/AGENT-START.md` | Cold-start & mid-task model-switch resume card |
| `platform/pipeline/next_action.py` | Read-only state inspector (`--json`) with citations and explicit `stop` bit |
| `platform/pipeline/gates.txt` & `gates.py` | Machine-checked gate & exit-code registry (`gates.py list`, `gates.py exit 15`) |
| `platform/pipeline/plate_inventory.py` | Requested-vs-3MF-vs-G-code per-ID piece count verification |
| `platform/pipeline/plate_scope.py` | Explicit scope-hold marker when a ready plate does not match the current brief |
| `platform/pipeline/{generate,preview,verify,slice,handoff,send,prepare}/` | End-to-end deterministic pipeline stages |
| `platform/codegen-templates/` | Tested CadQuery idioms and OCCT traps |
| `platform/consumer-template/` & `scripts/init-consumer.sh` | One-command consumer repo wiring |
| `parts/_lib/` | Shared CAD helpers: qualified joint registry (`joints.py`), probes, fit-core fingerprints, debossed stamps |
| `parts/_TEMPLATE/` | Starter part template with intentionally failing defaults until filled |
| `slicer-profiles/` | Reference slicer profiles (PrusaSlicer / Core One, OrcaSlicer layout) |
| `docs/` | Canonical process ([`workflow.md`](docs/workflow.md), [`preparation.md`](docs/preparation.md), [`consumer-contract.md`](docs/consumer-contract.md), [`versioning.md`](docs/versioning.md), [`text-to-cad.md`](docs/text-to-cad.md)) |
| `examples/` | Curated open-source worked examples |
| `scripts/check-public.py` | Automated guard blocking credentials, local machine paths, and personal print clutter |

## Current hardware & toolchain scope

Proven in daily use with:
- **CAD:** CadQuery (OCP/OCCT), OpenSCAD
- **Slicer:** PrusaSlicer CLI (tested on Prusa Core One / HF0.4 profiles; OrcaSlicer profile layout included)
- **Printer upload:** PrusaLink HTTP Digest / API key (`send.sh`, upload-only by default, guarded `--start`)

## Contributing

Contributions are welcome! High-value areas include:
- **Printer & slicer adapters** (OrcaSlicer CLI, Bambu, Klipper/Moonraker, OctoPrint) preserving the exact handoff and `APPROVED=1` safety boundary
- **Deterministic verification checks & CAD probes**
- **Slicer profiles & hardware calibration notes**
- **Small, self-contained worked examples** under `examples/`

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`SECURITY.md`](SECURITY.md) before opening a PR.

## License

[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).

AGPL-3.0 applies to the workflow tooling in this repository and any modified or network-hosted versions of it so improvements stay open source. Running the CLI tools on your own parts does **not** place your CAD models, STLs, STEP files, or physical prints under AGPL-3.0 — your designs remain yours under whatever license you choose.
