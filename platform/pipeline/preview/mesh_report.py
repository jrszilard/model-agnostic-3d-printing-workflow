"""Passive SVG projection of bounded numeric mesh reports; stdlib, no CAD or I/O.

Diagnostic only: not an STL/STEP reader, verifier, manufacturing render/stamp or
hidden-surface proof. Triangles are back-face culled and centroid depth sorted;
complex intersecting surfaces need a proper renderer. Coordinates are not changed
in the caller; only the camera projection is fitted to the view.
"""
import math

MAX_ITEMS = 500
MAX_COORD = 1_000_000
VIEWS = {
    "iso": ((2**-.5, 2**-.5, 0), (6**-.5, -6**-.5, -2*6**-.5), (3**-.5, -3**-.5, 3**-.5)),
    "top": ((1, 0, 0), (0, -1, 0), (0, 0, 1)),
    "side": ((0, 1, 0), (0, 0, -1), (1, 0, 0)),
}
TITLES = {"iso": "Isometric: from +X, -Y, +Z", "top": "Top: from +Z", "side": "Side: from +X"}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def validate(points, facets):
    """Copy bounded plain numeric triangles; no format/capability claim."""
    for rows in (points, facets):
        require(type(rows) in (list, tuple) and 1 <= len(rows) <= MAX_ITEMS, "mesh count")
        require(all(type(row) in (list, tuple) and len(row) == 3 for row in rows), "mesh triples")
    require(all(type(x) in (int, float) and abs(x) <= MAX_COORD and math.isfinite(x)
                for p in points for x in p), "mesh coordinates")
    require(all(type(i) is int and 0 <= i < len(points) for f in facets for i in f), "facet index")
    require(all(len(set(f)) == 3 for f in facets), "repeated facet index")
    return tuple(tuple(p) for p in points), tuple(tuple(f) for f in facets)


def unit_normal(points, facet):
    a, b, c = [points[i] for i in facet]
    u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
    n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    length = math.sqrt(dot(n, n))
    return tuple(x/length for x in n) if length else (0, 0, 0)


def mesh_svg(points, facets, *, view):
    """Return one 360x240 passive SVG; accepted views are iso/top/side only."""
    require(type(view) is str and view in VIEWS, "unknown view")
    points, facets = validate(points, facets)
    right, down, depth = VIEWS[view]
    projected = [(dot(p, right), dot(p, down), dot(p, depth)) for p in points]
    low = [min(p[i] for p in projected) for i in (0, 1)]
    high = [max(p[i] for p in projected) for i in (0, 1)]
    span = [high[i]-low[i] for i in (0, 1)]
    require(all(x > 1e-9 for x in span), "degenerate projection")
    scale = min(280/span[0], 150/span[1])
    center = [(low[i]+high[i])/2 for i in (0, 1)]
    xy = [(180+(p[0]-center[0])*scale, 112+(p[1]-center[1])*scale) for p in projected]
    rows, edge_normals = [], {}
    normals = [unit_normal(points, f) for f in facets]
    for f, normal in zip(facets, normals):
        for a, b in zip(f, f[1:]+f[:1]):
            edge_normals.setdefault(tuple(sorted((a, b))), []).append(normal)
    light = (-.3, -.5, 1)
    light_length = math.sqrt(dot(light, light))
    for f, normal in zip(facets, normals):
        if dot(normal, depth) <= 0:
            continue
        shade = .45 + .55*max(0, dot(normal, light)/light_length)
        color = '#' + ''.join(f'{round(channel*shade):02x}' for channel in (145, 194, 220))
        polygon = ' '.join(f'{xy[i][0]:.3f},{xy[i][1]:.3f}' for i in f)
        drawn = f'<polygon points="{polygon}" fill="{color}" stroke="{color}" stroke-width="0.3"/>'
        for a, b in zip(f, f[1:]+f[:1]):
            neighbors = edge_normals[tuple(sorted((a, b)))]
            # Hide internal coplanar triangulation only; never remove/alter a face.
            if len(neighbors) == 2 and dot(neighbors[0], neighbors[1]) > 1-1e-9:
                continue
            drawn += (f'<line x1="{xy[a][0]:.3f}" y1="{xy[a][1]:.3f}" '
                      f'x2="{xy[b][0]:.3f}" y2="{xy[b][1]:.3f}" stroke="#315065" stroke-width="0.7"/>')
        rows.append((sum(projected[i][2] for i in f)/3, drawn))
    require(bool(rows), "no visible triangles")
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 240" role="img">',
           f'<title>{TITLES[view]}</title>', '<rect width="360" height="240" fill="#f5f8fa"/>',
           f'<text x="12" y="20" font-size="12" font-family="sans-serif">{TITLES[view]}</text>']
    svg.extend(row[1] for row in sorted(rows, key=lambda row: row[0]))
    for i, (label, color) in enumerate(zip(('X', 'Y', 'Z'), ('#ad3943', '#23764a', '#315fbd'))):
        dx, dy = right[i]*22, down[i]*22
        if abs(dx)+abs(dy) < 1e-9:  # axis normal to view is named by the view title
            continue
        x, y = 40+dx, 213+dy
        svg += [f'<line x1="40" y1="213" x2="{x:.3f}" y2="{y:.3f}" stroke="{color}" stroke-width="2"/>',
                f'<text x="{x+3:.3f}" y="{y+3:.3f}" fill="{color}" font-family="sans-serif" font-size="10">+{label}</text>']
    svg.append('</svg>')
    return '\n'.join(svg)
