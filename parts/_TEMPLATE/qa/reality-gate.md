# Physical reality / functional gate — TEMPLATE

> This is the human-readable worksheet. The machine authority is one structured
> `qa/iterations/*.yaml` record initialized from the handoff manifest; see [`iteration.yaml`](iteration.yaml).
> Leave the verdict **NOT EVALUATED** until a named person tests the physical print. An agent may
> prepare rows or flag omissions; it must not enter readings, choose PASS, add the human
> attestation, or run `CONFIRMED=1 bench.sh passed`.

## Artifact identity

| Field | Value |
|---|---|
| part / revision | TODO |
| source git commit | TODO |
| printed STL path + geom id / SHA-256 | TODO |
| plate gcode SHA-256 | TODO |
| slice / handoff directory | TODO |
| printer | TODO |
| material, brand, lot, dry state | TODO |
| nozzle / layer height | TODO |
| machine / process / filament preset names | TODO |
| slicer version + profile/config hash | TODO |
| build plate / orientation | TODO |
| ambient temperature / RH | TODO |
| print date / operator | TODO |
| actual duration / material used (if observed) | TODO |
| photos | TODO |

## Actual mate / application

Identify the physical object or service condition used for the test. Record asset/serial/lot where
variation matters; do not write only "the real part".

- **Mate / application:** TODO
- **Relevant condition or wear:** TODO
- **Reference measurement source:** TODO

## Dimensional observations

Keep raw repeated readings. `measured` is not synonymous with one caliper display, and model-space
checks do not belong in this table.

| spec dimension / location | nominal + tolerance | raw readings (mm) | summary | instrument ID + resolution | uncertainty / basis | result |
|---|---:|---|---:|---|---|---|
| TODO | TODO | TODO | TODO | TODO | TODO | NOT EVALUATED |

## Reality-gate checks

Copy the acceptance criteria from `spec.yaml` without weakening them. Include failed attempts; do not
retain only the selected coupon.

| check ID / criterion | test method | repeats / cycles | raw observation or evidence path | result |
|---|---|---:|---|---|
| TODO | TODO | TODO | TODO | NOT EVALUATED |

## Functional / service checks

Record loads, durations, cycle counts, temperature, humidity, and safety constraints when relevant.
If the functional gate is intentionally skipped, state why the part has no meaningful service risk.

| check ID / criterion | load / condition / duration | observation | result |
|---|---|---|---|
| TODO | TODO | TODO | NOT EVALUATED |

## Deviations and disposition

- **Deviations from the qualified slice/process:** TODO
- **Damage, post-processing, conditioning, or rework:** TODO
- **Failure analysis / next revision:** TODO

## Human verdict

Select exactly one only after the checks above are complete:

- [x] **NOT EVALUATED**
- [ ] **FAIL** — do not promote or tag as physically passed
- [ ] **PASS for the stated scope and process context**

**Human name:** TODO

**Date/time:** TODO

**Scope limitations:** TODO

A PASS is evidence only for the identified artifact, mate/application, and process context. It does
not certify a population, establish a standards tolerance class, or transfer automatically to a new
printer, material, profile, orientation, geometry revision, or service condition.
