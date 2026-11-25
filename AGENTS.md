# Model-Agnostic 3D Printing Workflow — Agent Instructions

> **Model-agnostic single source of truth** for any AI agent or contributor working in this repository.

## Authority & start card

- Read [`platform/AGENTS.md`](platform/AGENTS.md) for the portable hard rules (approval boundary, deterministic vs advisory gates, physical attestation rules).
- Use [`platform/pipeline/AGENT-START.md`](platform/pipeline/AGENT-START.md) when starting a task or switching models mid-task.
- [`docs/workflow.md`](docs/workflow.md) is the canonical part-production process.
- [`docs/consumer-contract.md`](docs/consumer-contract.md) governs how external parts repositories consume this workflow.

## Ask the tree, do not infer from prose

```bash
python3 platform/pipeline/next_action.py <part-or-plate-dir> --json
python3 platform/pipeline/gates.py list
python3 platform/pipeline/gates.py exit 15
```

## Repository scope (important)

This repository holds **reusable workflow software, shared libraries (`parts/_lib/`), templates (`parts/_TEMPLATE/`), docs, slicer profiles, and small curated `examples/`**.

- **Do not add personal or commercial part catalogs under `parts/<category>/`**, `build/` outputs, `photoref/`, `.gcode` files, or credentials. Put personal/product parts in a separate consumer repository wired via `scripts/init-consumer.sh`.
- **Keep `docs/joinery.md` generated:** after editing `parts/_lib/joints.py`, run `python3 parts/_lib/render_registry.py` instead of hand-editing `docs/joinery.md`.
- **Run checks before committing or pushing:**

```bash
platform/pipeline/test.sh
python3 scripts/check-public.py
```

- **Never weaken safety invariants:** `send.sh` must always require an exact verified handoff and explicit human `APPROVED=1`, and physical qualification (`CONFIRMED=1`) must always remain human-attested.
