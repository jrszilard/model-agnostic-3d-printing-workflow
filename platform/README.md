# platform/ — the reusable engine

Everything here is **vertical-agnostic**. `../VERSION`/`../CHANGELOG.md` name the platform, but
consumer pins identify the capability set last re-verified by each venture (a staleness detector,
not a frozen compatibility API; see `../docs/roadmap.md`). Ventures borrow these entrypoints by
visible relative path. Keep marque/product specifics out.

Consumers must read [`AGENTS.md`](AGENTS.md): the handoff/approval, gate-policy, orientation,
artifact-ownership and upstream-feedback rules travel with the scripts even when a venture invokes
them cross-repo. The generic consumer contract is [`../docs/consumer-contract.md`](../docs/consumer-contract.md).

- **`pipeline/`** — the AI-CAD stages: `generate/ preview/ scan-process/ slice/ verify/`.
  See [`pipeline/README.md`](pipeline/README.md) for commands and the render/self-correct loop.
- **`ai/`** — optional advisory model/dataset tooling: curated HF registry, local pattern retrieval,
  CadQuery benchmark execution, and image-intake drafts. It can propose patterns and evidence; it
  cannot approve geometry or a plate. See [`ai/README.md`](ai/README.md) and
  [`../docs/hf-ai-cad-plan.md`](../docs/hf-ai-cad-plan.md).
- **`codegen-templates/`** — tested CadQuery authoring idioms: safe booleans/workplanes,
  Sol→Terra clean transitions, tapered relief/text, fit-core/probes and drawing annotations.
  Start at [`codegen-templates/README.md`](codegen-templates/README.md), not a blank generator.
- **`schemas/`** — the machine-readable contracts:
  - `spec.template.yaml` — Restore/Originate intent, target dimensions/reference relationships,
    tolerances, fits, acceptance checks, and current physical-evidence link.
  - `provenance.template.json` — prompt/model/toolchain/commit/artifact identity; `null` is explicitly
    unrecorded and must never be treated as reproducibility evidence.
  - `fitment.schema.yaml` — structured vehicle-fit metadata (venture-facing; schema here, data in the venture).
  - `../parts/_TEMPLATE/qa/iteration.yaml` — machine-initialized/human-completed physical attempt;
    exact artifact/process intent, human-recorded actual machine/material/lot/environment, repeated
    readings + uncertainty, outcomes, and next-revision learning.

**Design rule (single source of truth):** one geometry source per part. The preview
renders the *actual exported mesh* — never a hand-re-drawn copy. Keep a second parametric
source only when a mesher forces it (e.g. the vent elbow needed OpenSCAD/CGAL because
FreeCAD's mesher self-intersected), and document *why* in that part's README.
