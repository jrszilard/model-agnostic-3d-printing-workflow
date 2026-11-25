# Passive numeric mesh-report projection

Sanctioned import-safe entrypoint: `mesh_report.mesh_svg(points, facets, *, view)`.
Returns one standalone passive SVG string; fixed views `iso` (+X,−Y,+Z), `top` (+Z),
`side` (+X), axes explicitly labelled. No I/O, CAD imports, file parsing, subprocess,
normalization, manufacturing stamp or serving/fit/print authority.

This is a small diagnostic complement to the bounded local evaluation API in
[isolation/EVALUATION.md](../isolation/EVALUATION.md), **not** a replacement for
`render.sh`, a STEP/STL reader or a general hidden-surface renderer. Manufacturing
rendering remains unchanged and may canonicalize STL; do not invoke it on exact
retained originals or as an uncounted evaluation fallback.

## Contract

- Plain list/tuple triples: 1–500 points and 1–500 triangles. Finite numeric coordinates
  with magnitude ≤1,000,000; booleans/subclasses rejected. Integer indexes must be in
  range and each triangle must name three distinct points. These are diagnostic input
  bounds, not a geometry-support/upload promise. Degenerate/no-visible projections fail.
- Copy inputs; never modify them. Fit each camera to the projected bounds. This is a
  display transform, not normalization of source bytes or a shared pixel-length scale.
- Back-face cull by supplied triangle winding; centroid-sort visible triangles. Shade
  with a fixed directional light. Suppress only coplanar internal feature-edge strokes;
  all visible faces remain. Raster triangle seams may still appear.
- Complex/intersecting surfaces and every hidden feature are **not** resolved/proven by
  this painter. Callers must keep actual geometry checks separate and choose appropriate
  views/sections for their domain. An exterior side projection cannot show an internal pocket.
- Caller owns byte-report linkage and authorization: receive/hash actual artifacts,
  require admitted fresh-check reports, bind exact report/producer/input IDs and preserve
  originals. Record tool/view hashes and **actually inspect** emitted views. A renderer
  does not prove that supplied numeric arrays came from a named model or a truthful check.

Studio's thin `scripts/preview-evaluation.py` supplies that selected-case linkage and
passive local HTML/manifest. Its first owned specimen evaluation has six positive saved
STEP/STL checks but an incomplete negative suite; previews must retain that distinction.
No web framework, service or CAD execution is needed for numeric projection.

## Offline tests

```sh
python3 -m unittest discover -s platform/pipeline/preview -p test_mesh_report.py -v
```

Ten tests: passive XML, purity/determinism, counts/triples, finite/huge/non-numeric
coordinates, indexes, view injection, degenerate/no-visible cases, camera orientation,
and coplanar-edge presentation. Ordinary `test.sh` already discovers `preview/test_*.py`;
**full pipeline runner remains unrun** for this increment (it includes broad CAD/corpus).
These numeric tests are not real CAD checks or visual inspection.
