#!/usr/bin/env python3
"""dfm_check.py — mesh heuristics: wall thickness, overhang, and nozzle-scale gaps.

WHY
`verify` proves conformance to the spec. It cannot see that the spec itself asks for something FDM
will not give you. Two failures this repo has actually paid for:

  * A relief cutter written for a straight envelope, reused behind a tapered one, produced a wall
    that measured 0.50 mm at the mouth and 9.75 mm at the floor. It passed mesh, verify-slice and
    handoff, because every one of them checks the model against the spec and none measures the
    solid. `docs/workflow.md` answers this with "probe the solid before you slice an internal
    mechanism" -- a manual step, remembered or not. This measures it every time.
  * Auto-support on leaning-wall geometry wrapped 40% of the filament as support (39m -> 1h41m).
    Knowing the unsupported area BEFORE slicing is what makes that a design decision.
  * Twelve fir-tree barbs left a 0.234 mm valley (0.58 of a 0.4 mm nozzle), so the slicer fused
    them into ribs. Injection-moulded repeating detail has a nozzle-imposed gap floor in FDM.

GATE POLICY (AGENTS.md): these are mesh heuristics, so they WARN and never block. Only
deterministic checks -- bed fit, slicer exit, bad gcode -- may block. Exit is 0 unless --strict.

Method: thickness is ray-cast -- from a sampled facet's centroid, inward along -normal, to the
nearest opposing surface. That is the number calipers would read, not a shell parameter.

LIMITS, so the number is not over-read:
  * Overhang measures DOWNWARD-FACING area, not area with nothing beneath it. A tabletop over two
    legs reports its whole underside, legs included -- deciding what is actually unsupported needs
    a layer-by-layer projection, which is the slicer's job. Read this as "how much of the surface
    points down steeply", an upper bound and an early warning, then confirm in supports.png.
  * Thickness and gaps are sampled, not exhaustive. Gap rays leave a surface along its OUTWARD
    normal and require an opposing-facing hit; they can still report intentional micro-slots or
    tessellation slivers. Raise --samples around small repeating detail.

Usage: dfm_check.py <part.stl> [--min-wall 0.8] [--nozzle-width 0.4]
                    [--overhang-deg 45] [--samples 3000] [--strict]
"""
import argparse, struct, sys
import numpy as np

def load(path):
    with open(path, 'rb') as stream:
        d = stream.read()
    if len(d) < 84:
        raise ValueError('too short to be an STL')
    n = struct.unpack('<I', d[80:84])[0]
    if len(d) != 84 + n * 50:
        raise ValueError('not a binary STL')
    raw = np.frombuffer(d[84:], dtype=np.dtype([('n', '<3f4'), ('v', '<3f4', 3), ('a', '<u2')]))
    return raw['v'].astype(np.float64)          # (n, 3, 3)

def normals_areas(tri):
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    cr = np.cross(e1, e2)
    ln = np.linalg.norm(cr, axis=1)
    ok = ln > 1e-12
    nrm = np.zeros_like(cr)
    nrm[ok] = cr[ok] / ln[ok, None]
    return nrm, 0.5 * ln

def overhangs(tri, nrm, area, deg):
    """Downward faces steeper than `deg` from the bed, excluding the first layer."""
    zmin = tri[:, :, 2].min()
    nz = nrm[:, 2]
    down = nz < -1e-9
    # angle the SURFACE makes with the bed: 0 = flat underside (worst), 90 = vertical wall (fine)
    ang = np.degrees(np.arccos(np.clip(-nz, 0, 1)))
    on_bed = tri[:, :, 2].max(axis=1) <= zmin + 1e-6
    bad = down & (ang < deg) & ~on_bed
    return bad, ang, area[bad].sum(), area.sum()

def thickness(tri, nrm, area, samples, rng):
    """Ray-cast inward from sampled facets to the nearest opposing surface (Moller-Trumbore)."""
    n = len(tri)
    if n == 0:
        return np.array([]), np.zeros((0, 3))
    k = min(samples, n)
    # area-weighted: a big face matters more than a sliver
    w = area / area.sum() if area.sum() > 0 else None
    idx = rng.choice(n, size=k, replace=False, p=w) if w is not None else np.arange(k)
    orig = tri[idx].mean(axis=1) - nrm[idx] * 1e-4      # just inside the surface
    dirs = -nrm[idx]

    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    out = np.full(k, np.inf)
    for i in range(k):
        p = np.cross(dirs[i], e2)
        det = np.einsum('ij,ij->i', e1, p)
        live = np.abs(det) > 1e-12
        inv = np.zeros_like(det); inv[live] = 1.0 / det[live]
        t0 = orig[i] - v0
        u = np.einsum('ij,ij->i', t0, p) * inv
        q = np.cross(t0, e1)
        v = np.einsum('j,ij->i', dirs[i], q) * inv
        t = np.einsum('ij,ij->i', e2, q) * inv
        hit = live & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (t > 1e-3)
        if hit.any():
            out[i] = t[hit].min()
    good = np.isfinite(out)
    return out[good], orig[good]

def gaps(tri, nrm, samples, rng):
    """Ray-cast OUTWARD to an opposing-facing surface: external void/valley width heuristic."""
    count = len(tri)
    if count == 0:
        return np.array([]), np.zeros((0, 3))
    k = min(samples, count)
    # Uniform by facet, not area: repeated micro-detail has little area but many intentional faces.
    idx = rng.choice(count, size=k, replace=False) if k < count else np.arange(count)
    orig = tri[idx].mean(axis=1) + nrm[idx] * 1e-4
    dirs = nrm[idx]
    v0, v1, v2 = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    out = np.full(k, np.inf)
    for i in range(k):
        p = np.cross(dirs[i], e2)
        det = np.einsum('ij,ij->i', e1, p)
        live = np.abs(det) > 1e-12
        inv = np.zeros_like(det); inv[live] = 1.0 / det[live]
        t0 = orig[i] - v0
        u = np.einsum('ij,ij->i', t0, p) * inv
        q = np.cross(t0, e1)
        v = np.einsum('j,ij->i', dirs[i], q) * inv
        t = np.einsum('ij,ij->i', e2, q) * inv
        # A valley/bore wall must FACE the origin. Same-facing hits are unrelated layers of one
        # surface and create false micro-gaps at tessellation seams.
        opposing = np.einsum('ij,j->i', nrm, dirs[i]) < -0.2
        hit = (live & opposing & (u >= -1e-9) & (v >= -1e-9)
               & (u + v <= 1 + 1e-9) & (t > 1e-3))
        if hit.any():
            out[i] = t[hit].min()
    good = np.isfinite(out)
    return out[good], orig[good]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stl'); ap.add_argument('--min-wall', type=float, default=0.8)
    ap.add_argument('--nozzle-width', type=float, default=0.4)
    ap.add_argument('--overhang-deg', type=float, default=45.0)
    ap.add_argument('--samples', type=int, default=1000)   # ~4 s on a 65k-facet part
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()

    tri = load(a.stl)
    nrm, area = normals_areas(tri)
    warn = []
    print(f'=== DFM: {a.stl} ===')
    print(f'  facets {len(tri)}   surface {area.sum():.1f} mm2')

    bad, ang, oa, ta = overhangs(tri, nrm, area, a.overhang_deg)
    pct = 100 * oa / ta if ta else 0
    print(f'\n  OVERHANG (< {a.overhang_deg:g} deg from the bed, first layer excluded)')
    print(f'    unsupported area  {oa:9.1f} mm2  ({pct:.1f}% of surface)')
    if bad.any():
        worst = ang[bad].min()
        zs = tri[bad][:, :, 2].mean(axis=1)
        print(f'    shallowest facet  {worst:9.1f} deg   spanning Z {zs.min():.2f}..{zs.max():.2f} mm')
        if pct >= 5.0:
            warn.append(f'{pct:.1f}% of the surface needs support — check removal access before slicing')

    th, pts = thickness(tri, nrm, area, a.samples, np.random.default_rng(0))
    print(f'\n  WALL THICKNESS (ray-cast, {len(th)} samples)')
    if len(th) == 0:
        print('    no measurable thickness (open or degenerate mesh)')
        warn.append('thickness unmeasurable — mesh may be open')
    else:
        p1, p5 = np.percentile(th, 1), np.percentile(th, 5)
        print(f'    min {th.min():.3f}   p1 {p1:.3f}   p5 {p5:.3f}   median {np.median(th):.3f} mm')
        if th.min() < a.min_wall:
            j = int(np.argmin(th))
            x, y, z = pts[j]
            print(f'    thinnest at  x={x:.2f} y={y:.2f} z={z:.2f}')
            warn.append(f'thinnest wall {th.min():.3f} mm < {a.min_wall} mm minimum')
        span = th.max() - th.min()
        if span > 2.0 and th.min() < a.min_wall * 2:
            warn.append(f'thickness varies {th.min():.2f}..{th.max():.2f} mm — '
                        'a constant offset against a non-parallel face diverges like this')

    gap, gap_pts = gaps(tri, nrm, a.samples, np.random.default_rng(1))
    print(f'\n  EXTERNAL GAP / REPEATING-FEATURE RESOLUTION '
          f'(outward ray-cast, {len(gap)} hits; nozzle {a.nozzle_width:g} mm)')
    if len(gap) == 0:
        print('    no opposing external surface found in the sample')
    else:
        print(f'    min {gap.min():.3f}   p1 {np.percentile(gap, 1):.3f}   '
              f'p5 {np.percentile(gap, 5):.3f} mm')
        if gap.min() < a.nozzle_width:
            j = int(np.argmin(gap)); x, y, z = gap_pts[j]
            print(f'    narrowest at  x={x:.2f} y={y:.2f} z={z:.2f}')
            warn.append(f'narrowest external gap {gap.min():.3f} mm < {a.nozzle_width:g} mm '
                        'nozzle width — repeating valleys/slots may fuse')

    print()
    if warn:
        for w in warn:
            print(f'  WARN: {w}')
        print('\n  Advisory only (mesh heuristic) — see AGENTS.md gate policy.')
    else:
        print('  no DFM warnings')
    sys.exit(1 if (warn and a.strict) else 0)

if __name__ == '__main__':
    main()
