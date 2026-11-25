#!/usr/bin/env python3
"""geom_metrics.py — scalar summary of a binary STL, for comparing two versions of a part.

WHY
The geom id proves two artefacts came from the SAME bytes. It cannot say what changed when they
came from different ones, and "looked right in every render" is how a 9.4 mm alignment error ships.
These five numbers catch the classes a preview does not: a shifted centroid (something moved), a
changed bbox (something grew), a changed volume with an unchanged bbox (something hollowed out or
filled in), and a facet-count jump with everything else equal (a re-tessellation, not a redesign).

Usage: geom_metrics.py <file.stl> [<file.stl> ...]        one JSON object per line
"""
import json, math, struct, sys

def metrics(path):
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < 84:
        raise ValueError('too short to be an STL')
    n = struct.unpack('<I', data[80:84])[0]
    if len(data) != 84 + n * 50:
        raise ValueError('not a binary STL')

    vol = area = 0.0
    cx = cy = cz = 0.0
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for i in range(n):
        a, b, c = (struct.unpack('<9f', data[84 + i * 50 + 12:84 + i * 50 + 48])[j:j + 3]
                   for j in (0, 3, 6))
        for v in (a, b, c):
            for k in range(3):
                if v[k] < lo[k]: lo[k] = v[k]
                if v[k] > hi[k]: hi[k] = v[k]
        # signed tetrahedron volume against the origin; sums to the enclosed volume for a closed mesh
        t = (a[0] * (b[1] * c[2] - b[2] * c[1])
             - a[1] * (b[0] * c[2] - b[2] * c[0])
             + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
        vol += t
        cx += t * (a[0] + b[0] + c[0]) / 4.0
        cy += t * (a[1] + b[1] + c[1]) / 4.0
        cz += t * (a[2] + b[2] + c[2]) / 4.0
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        w = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cr = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        area += 0.5 * math.sqrt(cr[0] ** 2 + cr[1] ** 2 + cr[2] ** 2)

    centroid = [cx / vol, cy / vol, cz / vol] if abs(vol) > 1e-12 else [0.0, 0.0, 0.0]
    return {
        'facets': n,
        'volume_mm3': round(abs(vol), 3),
        'area_mm2': round(area, 3),
        'bbox_min': [round(v, 4) for v in lo],
        'bbox_max': [round(v, 4) for v in hi],
        'size': [round(hi[k] - lo[k], 4) for k in range(3)],
        'centroid': [round(v, 4) for v in centroid],
    }

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        try:
            print(json.dumps({'path': p, **metrics(p)}))
        except Exception as e:
            print(json.dumps({'path': p, 'error': str(e)}))
