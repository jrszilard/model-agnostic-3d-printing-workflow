# Fasteners in FDM parts — selection, design, and evidence gate

**Status:** required practice for every new threaded/load-bearing joint (2026-07-23).
This is a design-and-evaluation guide, not a table of universal hole sizes. FDM strength and
fit vary with polymer, layer orientation, wall count, slicer, nozzle, and the exact hardware.
A vendor drawing plus a coupon beats a remembered diameter.

## Decision order

1. **Can both sides be reached at assembly and service?** Use an **external through-bolt + nut**.
   It is the simplest and least printer-sensitive choice; declare access for the tool, nut, and
   washer. Do not hide a nut where it cannot be held or recovered.
2. **Does the existing mate already provide the metal thread, while the printed part needs a
   controlled clamp stack?** Use a **threaded-substrate compression limiter**. The bolt engages
   the existing metal substrate; a metal sleeve carries clamp load through the plastic. This is
   neither a through-nut nor a printed thread: record pitch, tapped depth, sleeve stack, and a
   positive anti-bottom-out assertion before selecting bolt length.
3. **Must the joint be serviceable but the receiving side is inaccessible?** Use a
   **side-entry, roof-captured hex nut**. The nut slides through an exterior slit into a hex
   pocket; a printed roof retains it and the pocket prevents rotation.
4. **Repeated service in a compact boss with a selected insert and installation tool?** Use a
   **heat-set insert**. The pilot is insert-vendor/material specific; coupon it before freezing CAD.
5. **One-time/light-duty closure into fresh plastic?** A vendor-specified **thread-forming screw**
   can be appropriate. It is not the default for a structural, frequently opened joint.
6. **Large/coarse, low-cycle mechanism with ample engagement?** A **printed thread** may work.
   Do not treat M3-scale printed threads as a structural/serviceable default.

The preferred order is not a strength ranking. It is a way to expose the constraints: assembly
access, service cycles, load direction, installation tooling, heat exposure, and the cost of a
failed joint.

## Method cards

### External through-bolt + nut

- Best when both faces are genuinely reachable after neighboring parts are installed.
- Provide wrench/finger/washer clearance; account for head height, not merely shank length.
- Use a clearance hole in the printed part; the metal nut carries the thread.
- Coupon only when the hole is fit-critical, the part is thin, the load is consequential, or the
  tool access is uncertain. Reality gate: assemble, tighten, remove, and reassemble.

### Threaded substrate + compression limiter

Use this when a bolt clamps a printed adapter to an **existing metal threaded mate** and a metal
sleeve (compression limiter) prevents the plastic stack from taking the clamp load. Do not declare
this as `external-through-nut`: there is no nut to access, and that fiction hides the actual
bottom-out risk.

- Measure and declare the substrate material, thread size/pitch, and usable tapped depth. A bolt
  cannot be selected from overall stack thickness alone.
- Select the actual limiter by OD, ID, length, and undercut; declare the clearance bore and every
  under-head stack contribution from the head-bearing datum.
- Assert in source that the limiter seats before the screw bottoms and that enough thread
  engagement remains afterward. This is a geometry/stack assertion, not an assumed screw length.
- Coupon the *actual* substrate/hardware/printed section and production material. Reality gate:
  torque, release, re-torque, inspect the limiter seat and plastic for splitting, and verify tool
  access. Treat vehicle/load/cycle validation separately.

### Side-entry, roof-captured nut

This is B2B's standard because the crown and battery tray need serviceable metal threads without
access behind the structural frame.

- Model **one parameterized local feature** (pocket + slit + coaxial bore) and rotate/instantiate
  it. Never independently copy three nominally identical nut joints.
- Use the actual nut's across-flats and thickness. The pocket and entry slit require deliberate
  clearance; B2B starts at M3 nominal 5.5 AF × 2.4 thick → 5.8 AF × 2.7 pocket/slit, but this is a
  coupon starting point, not a global constant.
- The screw bore is **coaxial** with the pocket. At the nut elevation it lies inside the pocket
  void; it must not cut a retaining wall or constrict the side entry. Assert this in source.
- Give the nut a real printed roof (B2B: 3.7/3.8 mm) rather than relying on the mating cover to
  keep it in place. Make the entry slit face an accessible exterior and assess support removal.
- Calculate the entire axial stack from the head-bearing datum: cover/ear thickness + gap +
  required nut engagement + deliberate tip relief. Declare the actual screw length; do not infer
  it from an “M3 screw” label.
- Coupon the exact stack: load the nut, tighten, verify anti-rotation, check roof/pad splitting,
  confirm no bottom-out, remove/reassemble. A CAD boolean cannot prove these.

### Heat-set insert

- Select the exact insert first: thread, outer diameter, length, knurl style, and material
  compatibility. “M3 insert” is not a standardized outer diameter.
- Put the bore/boss where the insert can be pressed straight with controlled heat; make a short
  lead-in. Keep adequate wall and avoid a seam/weak layer plane at the expansion path.
- Print a **multi-pilot coupon** with the production material, orientation, and wall count. Choose
  the smallest pilot that seats squarely without split/whitening or excessive force, then record
  the SKU and chosen pilot.
- Reality gate: insertion quality, pull/twist by hand or fixture as stakes require, screw clamp,
  and at least the intended service cycles. Never substitute an unmeasured marketplace insert.

### Thread-forming screw in printed plastic

- Use a screw family explicitly intended for plastic and its maker's pilot/boss guidance.
- Limit to the stated service cycle and load; thread-forming plastic is a consumable receiver,
  not a metal thread.
- Coupon installation torque/feel and inspect for hoop splitting, stripping, and first-layer
  flare. For a one-time light cover this can be the least complex choice; for B2B's loaded,
  serviceable interfaces it is rejected.

### Printed thread

- Favor coarse, large-diameter, low-cycle threads with generous lead-in and enough axial
  engagement. Print orientation, clearance, and cleanup dominate outcome.
- Run a mating coupon first. Record the mating clearance and cycle target.
- Do not use as a silent fallback for small structural fasteners; choose a metal nut/insert instead.

## Required contract and automated checks

Every new threaded/load-bearing joint gets a `fasteners:` entry in `spec.yaml`; copy the annotated
schema in `parts/_TEMPLATE/spec.yaml`.

`platform/pipeline/verify/fastener_check.py` is deliberately a **declaration gate**, not a false
strength oracle. It blocks incomplete/contradictory metadata:

- valid method, metric size, quantity, and named physical gate;
- captive nut: actual nut + pocket dimensions, slit, clearance bore, roof, source assertion, and coupon;
- heat-set insert: selected vendor/SKU, pilot, boss wall, and coupon;
- thread-forming screw: vendor, pilot, and coupon;
- external nut: declared assembly access; printed thread: declared cycle limit;
- threaded substrate + limiter: substrate thread/pitch/depth, limiter OD/ID/length/undercut,
  under-head stack, clearance bore/access, coupon, and both source + anti-bottom-out assertions.

The CAD generator must additionally assert its own feature geometry (concentricity, roof, stack-up,
and tip relief). The physical coupon remains the fit/function evidence.

## Build and evaluation sequence

1. **Spec:** select method and hardware; add BOM + `fasteners:` contract before CAD.
2. **CAD:** parameterize the local joint; assert stack-up and critical containment. Preview the
   assembly and the accessible nut/insert entry path.
3. **Digital verify:** run `verify.sh`; it checks the declaration. Run the generator assertion and
   inspect the real STL/STEP preview. Slice the coupon in its production orientation.
4. **Fastener coupon:** install the actual hardware. Record material, printer, layer height,
   orientation, vendor/SKU, nominal/actual pilot or pocket, screw length, result, and failure mode
   in `research/results/measurements.csv` (or a part QA CSV with the same fields).
5. **Full-part reality gate:** repeat assembly with the actual mating geometry and intended service
   motion/load. Release requires the joint's stated physical gate, not just a green slice.

## Sources and scope

These sources establish method categories and installation constraints; none supplies a universal
FDM pilot dimension. B2B dimensions are bench hypotheses and remain coupon-gated.

- Prusa Knowledge Base, *Inserting heat-set inserts* — installation should be straight and
  controlled; cited in the existing B2B research. https://help.prusa3d.com/article/inserting-heatset-inserts_110135
- Prusa Research, *3D printing threads and threaded parts* — metal threaded inserts vs printed
  threads are different use cases. https://blog.prusa3d.com/3d-printing-threads-and-threaded-parts_4319/
- ISO 4032, *Hexagon regular nuts (style 1)* — nominal hex-nut geometry reference; measure the
  purchased hardware rather than assuming its tolerance class. https://www.iso.org/obp/ui/#iso:std:iso:4032:ed-3:v1:en
- McMaster-Carr, *Heat-set inserts* catalog — reinforces that insert families vary by body/knurl
  geometry and are selected as specific components. https://www.mcmaster.com/products/heat-set-inserts/
- Bench evidence: `parts/lighting/bottle-lamp-base/B2B-FASTENER-RESEARCH.md` and the B2B clamp
  coupons are the only authority for this printer/material/joint.
