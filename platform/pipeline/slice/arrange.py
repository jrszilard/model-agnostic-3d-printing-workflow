"""arrange.py — lay several STLs out on one plate and emit a single merged STL.

WHY THIS EXISTS (PrusaSlicer 2.9.6 CLI):
Handing the CLI several STLs does NOT put them on one plate. It runs the action once PER FILE,
each overwriting `--output`, so a 6-part plate silently becomes whichever file came last — no
warning, exit code 0. (A 6-coupon plate came out at 2.83 g, less than one coupon.) The documented
fix, `--merge`, SEGFAULTS (exit 139). OrcaSlicer's `--arrange 1` had covered this for free.

So the plate is built before the slicer sees it: parts are shelf-packed into a grid and combined
into one STL via OpenSCAD, which the CLI then slices as a single object. PrusaSlicer still
auto-centers it on the bed, so only relative placement matters here.

Usage: arrange.py --out <plate.stl> [--bed 250x220] [--gap 6] <part.stl>...
"""
import os
import struct
import subprocess
import sys

BED = (250.0, 220.0)   # Prusa Core One X x Y
GAP = 6.0              # mm between parts and around the plate edge


def stl_bbox(path):
    """(xmin,ymin,zmin,xmax,ymax,zmax) for a binary or ASCII STL. Stdlib only."""
    with open(path, "rb") as fh:
        head = fh.read(84)
        if len(head) < 84:
            raise ValueError(f"{path}: too short to be an STL")
        ntri = struct.unpack("<I", head[80:84])[0]
        # An 80-byte header + 4-byte count + 50 bytes/triangle is the binary layout; if the file
        # size matches exactly, trust that over the leading "solid" (binary STLs may start with it).
        if os.path.getsize(path) == 84 + 50 * ntri:
            lo = [float("inf")] * 3
            hi = [float("-inf")] * 3
            for _ in range(ntri):
                tri = fh.read(50)
                for v in range(3):
                    for a in range(3):
                        c = struct.unpack_from("<f", tri, 12 + v * 12 + a * 4)[0]
                        lo[a] = min(lo[a], c); hi[a] = max(hi[a], c)
            return tuple(lo) + tuple(hi)
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    with open(path, errors="ignore") as fh:
        for line in fh:
            p = line.split()
            if len(p) == 4 and p[0] == "vertex":
                for a in range(3):
                    c = float(p[a + 1])
                    lo[a] = min(lo[a], c); hi[a] = max(hi[a], c)
    if lo[0] == float("inf"):
        raise ValueError(f"{path}: no vertices found")
    return tuple(lo) + tuple(hi)


def shelf_pack(sizes, bed=BED, gap=GAP):
    """Row ("shelf") packing, tallest-first. -> [(x,y) offsets], (width,height) of the plate."""
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i][1])
    usable = bed[0] - gap
    place = [None] * len(sizes)
    x = gap; y = gap; row_h = 0.0; used_w = 0.0
    for i in order:
        w, h = sizes[i]
        if x + w + gap > usable and row_h > 0:          # start a new shelf
            y += row_h + gap; x = gap; row_h = 0.0
        place[i] = (x, y)
        x += w + gap
        used_w = max(used_w, x)
        row_h = max(row_h, h)
    return place, (used_w, y + row_h + gap)


def choose_orientation(boxes, rots, bed=BED, gap=GAP):
    """Pack with the portrait rule; if that overflows the bed, try every part as modelled.

    Portrait is right for a long strip beside a big part, and wrong for many copies of one long,
    short part. Twelve 103 x 25.5 mm keychains stand as 103 mm columns, two shelves deep: 224 mm
    on a 220 mm bed. Laid as modelled, they pack two to a shelf, six shelves: 224 x 195. The
    portrait packing is kept whenever it fits, so existing plates lay out exactly as before.
    """
    def pack(rs):
        sizes = [((b[4]-b[1], b[3]-b[0]) if r else (b[3]-b[0], b[4]-b[1]))
                 for b, r in zip(boxes, rs)]
        offsets, plate = shelf_pack(sizes, bed, gap)
        return rs, sizes, offsets, plate
    first = pack(rots)
    if first[3][0] <= bed[0] and first[3][1] <= bed[1]:
        return first
    flat = pack([False] * len(boxes))
    if flat[3][0] <= bed[0] and flat[3][1] <= bed[1]:
        return flat
    return first


def read_tris(path):
    """[(normal, v0, v1, v2)] from a binary or ASCII STL. Stdlib only."""
    tris = []
    with open(path, "rb") as fh:
        head = fh.read(84)
        ntri = struct.unpack("<I", head[80:84])[0] if len(head) >= 84 else 0
        if len(head) >= 84 and os.path.getsize(path) == 84 + 50 * ntri:
            for _ in range(ntri):
                d = struct.unpack("<12fH", fh.read(50))
                tris.append((d[0:3], d[3:6], d[6:9], d[9:12]))
            return tris
    normal = (0.0, 0.0, 0.0); verts = []
    with open(path, errors="ignore") as fh:
        for line in fh:
            p = line.split()
            if not p:
                continue
            if p[0] == "facet" and len(p) >= 5:
                normal = tuple(float(v) for v in p[2:5]); verts = []
            elif p[0] == "vertex" and len(p) == 4:
                verts.append(tuple(float(v) for v in p[1:4]))
                if len(verts) == 3:
                    tris.append((normal, verts[0], verts[1], verts[2]))
    return tris


def _place(pt, rot, b, ox, oy):
    """Map an original vertex to its plate position. rot=90deg CCW about Z when True."""
    x, y, z = pt
    if rot:                                    # (x,y)->(-y,x); rotated min corner = (-y1, x0)
        return (-y+ox+b[4], x+oy-b[0], z-b[2])
    return (x+ox-b[0], y+oy-b[1], z-b[2])


def _place_n(n, rot):
    return (-n[1], n[0], n[2]) if rot else n   # same proper rotation for the facet normal


def merge_stls(stls, offsets, boxes, rots, out):
    """Translate/rotate each part onto its cell and concatenate into ONE binary STL.

    Deliberately a triangle-soup merge, NOT a CGAL union. These plates carry compounds of many
    separate solids (e.g. a white substrate plus ~170 black graphic tiles); they are individually
    closed but not 2-manifold where tiles meet the substrate, so OpenSCAD refuses them with
    "The given mesh is not closed" and writes nothing while still exiting 0. PrusaSlicer unions
    per-layer in 2D and does not care, so concatenation is both sufficient and more robust.

    rots[i] rotates part i 90deg about Z so a long strip can pack in portrait beside a big part
    (shelf packing is row-based; a landscape strip would otherwise start a new row and overflow).
    """
    total = 0
    with open(out, "wb") as fh:
        fh.write(b"lakeshore arrange plate".ljust(80, b"\0"))
        fh.write(struct.pack("<I", 0))                      # patched below
        for stl, (ox, oy), b, rot in zip(stls, offsets, boxes, rots):
            for n, v0, v1, v2 in read_tris(stl):
                fh.write(struct.pack("<12fH", *_place_n(n, rot),
                                     *_place(v0, rot, b, ox, oy),
                                     *_place(v1, rot, b, ox, oy),
                                     *_place(v2, rot, b, ox, oy), 0))
                total += 1
        fh.seek(80); fh.write(struct.pack("<I", total))
    return total


def build_scad(stls, offsets, boxes, rots=None):
    """Human-inspectable record of the plate layout (the real merge is merge_stls)."""
    rots = rots or [False]*len(stls)
    out = []
    for stl, (ox, oy), b, r in zip(stls, offsets, boxes, rots):
        if r:
            out.append('translate([%.4f, %.4f, %.4f]) rotate([0,0,90]) import("%s");'
                       % (ox+b[4], oy-b[0], -b[2], os.path.abspath(stl)))
        else:
            out.append('translate([%.4f, %.4f, %.4f]) import("%s");'
                       % (ox-b[0], oy-b[1], -b[2], os.path.abspath(stl)))
    return "\n".join(out) + "\n"


def main(argv):
    out = None; bed = BED; gap = GAP; stls = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out":
            i += 1; out = argv[i]
        elif a == "--bed":
            i += 1; bed = tuple(float(v) for v in argv[i].lower().split("x")[:2])
        elif a == "--gap":
            i += 1; gap = float(argv[i])
        else:
            stls.append(a)
        i += 1
    if not out or not stls:
        print("usage: arrange.py --out <plate.stl> [--bed 250x220] [--gap 6] <stl>...",
              file=sys.stderr)
        return 2

    boxes = [stl_bbox(s) for s in stls]
    # Orient each part portrait (long side along Y) so the row packer seats long strips beside a
    # big part instead of starting a new, overflowing row -- but only when the long side still
    # fits the Y span, else a genuinely long single part is left landscape along the wider X bed.
    rots = [(b[3]-b[0]) > (b[4]-b[1]) and (b[3]-b[0]) <= bed[1]-2*gap for b in boxes]
    rots, sizes, offsets, (pw, ph) = choose_orientation(boxes, rots, bed, gap)
    print("arrange: %d parts -> plate %.1f x %.1f mm (bed %.0f x %.0f, gap %.1f)"
          % (len(stls), pw, ph, bed[0], bed[1], gap))
    for s, (ox, oy), (w, h), r in zip(stls, offsets, sizes, rots):
        print("  %-46s %6.1f x %-6.1f @ (%.1f, %.1f)%s"
              % (os.path.basename(s), w, h, ox, oy, "  [rot 90]" if r else ""))
    if pw > bed[0] or ph > bed[1]:
        print("arrange: FAIL — packed plate %.1fx%.1f exceeds bed %.0fx%.0f"
              % (pw, ph, bed[0], bed[1]), file=sys.stderr)
        return 1

    scad = os.path.splitext(out)[0] + ".scad"          # kept as a human-inspectable record
    with open(scad, "w") as f:
        f.write(build_scad(stls, offsets, boxes, rots))

    ntri = merge_stls(stls, offsets, boxes, rots, out)
    # Never trust a merge step to have produced something: an empty plate slices to an empty
    # gcode and the symptom only shows up as a suspiciously small weight at the handoff.
    if ntri == 0 or not os.path.exists(out) or os.path.getsize(out) <= 84:
        print("arrange: FAIL — merged plate is empty (%d triangles)" % ntri, file=sys.stderr)
        return 1
    print("arrange: plate -> %s (%d triangles)" % (out, ntri))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
