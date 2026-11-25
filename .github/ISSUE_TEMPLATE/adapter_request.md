---
name: Printer or slicer adapter proposal
about: Propose support for another slicer, printer transport, or CAD backend
labels: enhancement
---

## Target tool / hardware
- Slicer / CAD / printer transport:

## How it preserves the workflow contract
- How does it keep deterministic slicing/verification identity?
- How does it preserve the `handoff.sh` + `APPROVED=1` upload boundary (if it adds a `send` transport)?
- What offline tests/fixtures will cover pass and refusal paths?
