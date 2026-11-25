# Naming — one-pager

Enforced summary of the naming convention. Full rationale, examples, and the migration table live in
`docs/superpowers/specs/2026-07-07-naming-convention-design.md` — read that for the "why."

## Identity model (4 levels)
| Level | Form | Example |
|---|---|---|
| Repo / venture | `<repo>:` (omitted in-repo) | `3d-printing:`, `car-parts:` |
| Category | kebab folder | `vent`, `clips`, `tools` |
| Part | `category/[qualifier-]thing` | `vent/k1c-elbow` |
| Component | `part:component` (chat/prose only — never a filename) | `k1c-elbow:filter-collar` |

Qualifiers (`printer`, `duct`, `mounts`, `fan`, …) are `spec.yaml` fields — deep context, NOT part of the name.

## Canonical part name — `category/[qualifier-]thing`
- Lowercase **kebab-case** everywhere (dirs, part names, file stems). No `Caps`, no `snake_case`, no `build_` prefix.
- One distinguishing qualifier + the noun; must be **self-documenting enough to stand alone as a filename**
  (files get detached — copied to `build/`, sent to the printer, shared).
- Exact dims/model/duct size → `spec.yaml` qualifier fields, never the name.

## Chat handle
- The shortest unambiguous form — usually the noun (`elbow`, `fan-adapter`).
- **Auto-qualify on collision:** the moment a second one exists, expand to the distinguishing qualifier
  (`k1c-elbow` vs `e30-elbow`). Uniqueness enforced by `parts/index.yaml`.

## Component handle — `part:component`
- Kebab, namespaced under the part: `k1c-elbow:filter-collar`, `window-fan-adapter:bolt-pattern`.
- No own geometry file — a named region of the part, listed in the spec, referenced by coupons/QA.

## Variant keys + part marking (REQUIRED)
Every variant of a part has a short **key** used in exactly three places — the SAME key,
so a physical print always traces back to its source:

| Place | Form | Example |
|---|---|---|
| Generator `VARIANTS` dict | UPPERCASE | `"C1PF": dict(...)` |
| STL filename | lowercase, `part--<status>-<key>-<slug>.stl` | `bottle-lamp-carrier--draft-c1pf-corkscrew-d14-pla.stl` |
| **Debossed on the part's bed face** | UPPERCASE | `C1PF` |

The deboss is cut with `parts/_lib/deboss.py` (mirror-in-Y so it reads when flipped;
cut from a plain primitive BEFORE fusing into complex solids; start 0.2mm below the
face). New parts MUST include it — when a pile of prints exists, the bottom face is
the version history.

**Physical legibility baseline (R5 evidence):** where the face permits, use `legible_deboss`: 6mm
DejaVu Sans Bold with a true 1.0mm recess, and assert at least 15mm³ removed. R4's 3mm regular text
at a shallow recess was nearly unreadable. A smaller part may use smaller text only with its own
physical legibility evidence. A duplicate normal-reading top-face key is allowed for handling, but
never replaces the authoritative mirrored bed-face key.

## Build tree
`build/` mirrors the part hierarchy, never a flat dump:

- **Single-part plate** → `build/<category>/<part-id>/<slug>/`
  (e.g. `build/lighting/bottle-lamp-carrier/c3c/`)
- **Multi-part plate** → `build/plates/<slug>/` (e.g. `build/plates/base-plus-stopper/`)
  - Slicing experiments that retain the same part geometry nest beneath that plate as
    `support-variants/<strategy>/` (with a README recording settings, result, and status);
    they are not new part variants or upload candidates.
- Anything unidentifiable from older sessions → `build/_legacy/`

## The rule: `:` is chat-only, NEVER in a path
`:` is illegal in Windows filenames, is the legacy macOS path separator, trips `scp`/`rsync`/`PATH`, and
is ambiguous in YAML (`foo:bar` scalar vs `foo: bar` mapping). On disk, components appear only as:
- **bare names** in `spec.yaml` — `components: [filter-collar, k1c-notches]` (no `part:` prefix — implicit
  inside the part's own spec), or
- the **`--` variant form** if a component ever needs its own file — `k1c-elbow--coupon-filter-collar.stl`.

## File & artifact naming
- **Stem = the canonical part name:** `k1c-elbow.scad`, `k1c-elbow.py`, `k1c-elbow.stl`, `k1c-elbow.step`.
- **Variants** append `--` from a controlled vocabulary:
  - `--coupon-<region>` (`k1c-elbow--coupon-base`, `window-fan-adapter--coupon-face`)
  - `--print` / `--print-<orientation>` (orientation baked into the STL)
  - `--test-<what>` (`window-fan-adapter--test-thread`)
- **Build outputs:** `build/<part>[--variant]/` holds `plate_1.gcode`, `plate.3mf`, previews,
  `verify_slice.txt`, `verify_report.txt`. G-code shipped to the printer = `<part>[--variant].gcode` —
  never `Unnamed`, never an embedded space.
