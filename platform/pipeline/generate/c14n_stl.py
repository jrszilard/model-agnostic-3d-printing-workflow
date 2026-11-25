#!/usr/bin/env python3
"""c14n_stl.py — canonicalise a binary STL so identical geometry gives identical bytes.

WHY
OpenSCAD emits facets in nondeterministic order. Building cable-clip.scad twice here produced two
94484-byte files that differ from byte 488 — same geometry, different bytes. Committed, that is a
fresh ~100 KB blob in git on every rebuild, and `git status` claims a part changed when it did not.
NopSCADlib hit this years ago and solved it the same way (scripts/c14n_stl.py).

Canonical form: within each facet rotate the vertices so the smallest comes first (a rotation, not
a sort — it preserves winding and therefore the normal); then sort facets by their vertex tuple;
then zero the 80-byte header and normalise -0.0 to 0.0. Geometry is untouched: slicers do not care
about facet order, and the vertex set is identical.

CadQuery's STL export does not need this (verified byte-deterministic); its STEP export does —
see c14n_step.py.

Usage: c14n_stl.py <file.stl> [...]     rewrites in place, only if the bytes change
"""
import struct, sys

def canonicalise(path):
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < 84:
        return False
    if data[:5].lstrip().lower().startswith(b'solid') and b'facet' in data[:512]:
        return False  # ASCII STL — OpenSCAD writes binary here; leave it alone
    count = struct.unpack('<I', data[80:84])[0]
    if len(data) != 84 + count * 50:
        return False  # not a well-formed binary STL; do not touch it

    facets = []
    for i in range(count):
        off = 84 + i * 50
        vals = struct.unpack('<12fH', data[off:off + 50])
        vals = tuple(0.0 if v == 0 else v for v in vals[:12]) + (vals[12],)
        verts = [vals[3:6], vals[6:9], vals[9:12]]
        lo = min(range(3), key=lambda k: verts[k])
        verts = verts[lo:] + verts[:lo]          # rotate: winding, and thus the normal, preserved
        facets.append((tuple(verts), vals[0:3], vals[12]))
    facets.sort(key=lambda t: t[0])

    out = bytearray(b'\0' * 80) + struct.pack('<I', count)
    for verts, normal, attr in facets:
        out += struct.pack('<12fH', *normal, *verts[0], *verts[1], *verts[2], attr)
    out = bytes(out)
    if out == data:
        return False
    with open(path, 'wb') as f:
        f.write(out)
    return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        try:
            print(f"c14n: {'rewrote' if canonicalise(p) else 'unchanged'} {p}")
        except Exception as e:
            print(f"c14n: skipped {p} ({e})", file=sys.stderr)
