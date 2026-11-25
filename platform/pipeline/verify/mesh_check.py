# platform/pipeline/verify/mesh_check.py
# Run: MESH=/path/part.stl freecadcmd mesh_check.py   (env var, not argv — freecadcmd opens argv paths)
# Batch: MESH_LIST=$'/a.stl\n/b.stl' freecadcmd mesh_check.py — one process for a whole plate (T1.6).
# Rotation: MESH_ROT="x y z" (degrees) turns the mesh as the slicer will before the bed-fit check.
#   verify-slice.sh passes the plate's recorded rotation (slice_meta.json). Until 2026-09-18 the raw
#   STL was measured, which refused a 1 ft segment that fits turned 49 deg, and would have passed a
#   240 x 20 part turned 90 deg onto the 220 axis. Applied x, then y, then z: the order slice.sh
#   hands them to PrusaSlicer, which applies transforms in argv order.
#
# Gate policy (project decision): ONLY bed-fit (bbox oversize) is a HARD fail. Geometry heuristics —
# non-manifold, self-intersection, disconnected islands — are advisory WARN: this project's hand-rolled
# twist-extruded threads are self-intersecting/non-manifold by construction yet slice + print fine, and
# a legit multi-object plate has one island per part.
import math, os, sys
import FreeCAD
import Mesh
BED = (250.0, 220.0, 270.0)   # Prusa Core One X x Y x Z
USAGE = "usage: MESH=<stl> [MESH_ROT='x y z'] freecadcmd mesh_check.py"


def rotation():
    """(x, y, z) degrees from MESH_ROT, (0, 0, 0) when unset. Raises ValueError when unreadable:
    a rotation we cannot read must not quietly become "unturned"."""
    raw = os.environ.get("MESH_ROT", "").strip()
    if not raw:
        return (0.0, 0.0, 0.0)
    parts = [float(v) for v in raw.split()]
    if len(parts) != 3 or not all(math.isfinite(v) for v in parts):
        raise ValueError(raw)
    return tuple(parts)


def turned(m, rot):
    """A copy of the mesh turned about x, then y, then z, by the given degrees."""
    m = m.copy()
    for turn, deg in zip(("rotateX", "rotateY", "rotateZ"), rot):
        if deg:
            mat = FreeCAD.Matrix()
            getattr(mat, turn)(math.radians(deg))
            m.transform(mat)
    return m


def check(p):
    """The whole of this script's old module body. Prints the report; returns True on PASS."""
    m = Mesh.Mesh(p); hard = []; warn = []
    try:
        rot = rotation()
    except ValueError as e:
        rot = (0.0, 0.0, 0.0)
        hard.append("unreadable MESH_ROT %r: the sliced pose, and so the bed fit, is unknown" % str(e))
    b = turned(m, rot).BoundBox
    if b.XLength > BED[0] or b.YLength > BED[1] or b.ZLength > BED[2]:
        hard.append("oversize %.1fx%.1fx%.1f vs bed %s" % (b.XLength, b.YLength, b.ZLength, BED))
    if m.hasNonManifolds():      warn.append("non-manifold mesh")
    if m.hasSelfIntersections(): warn.append("self-intersecting mesh")
    try:
        comps = m.getSeparateComponents()               # list of disconnected bodies
        if len(comps) > 1:
            warn.append("%d disconnected components (multi-object plate or floating islands)" % len(comps))
    except Exception as e:
        print("island check skipped:", e)
    print("bbox %.1f x %.1f x %.1f%s" % (b.XLength, b.YLength, b.ZLength,
          "  (turned %g/%g/%g deg as sliced)" % rot if any(rot) else ""))
    for w in warn: print("  [WARN]", w)
    for h in hard: print("  [HARD]", h)
    print("MESH_RESULT:", "PASS" if not hard else "FAIL")
    return not hard


batch = os.environ.get("MESH_LIST")
if batch is not None:
    # T1.6: FreeCAD costs ~80 ms to start and ~8 ms to check a mesh, so a plate used to pay for a
    # whole interpreter per placed copy — 20 rows over one STL in six of build/'s plates. One
    # process for the list; verify-slice.sh splits the stream on these markers.
    # The leading "\n" is load-bearing: FreeCAD's own progress bars are block-buffered on the same
    # fd and flush mid-run once the list is long enough, so without it a marker (or a bbox line)
    # can be glued to the tail of a "(47 %)" chunk and stop starting its own line.
    # Every file is wrapped in try/except: the pre-T1.6 loop got a fresh process per file, so a mesh
    # that raises must not take the meshes queued behind it with it.
    # A path is bytes, not text. An STL whose filename is not valid UTF-8 made the handler below
    # raise UnicodeEncodeError inside print(), and freecadcmd replayed its whole buffered stream:
    # verify-slice.sh then reported every earlier STL on the plate a second time on its own line
    # (measured: 4 STLs, one with a \xff byte in the name -> items 0 and 1 emitted twice). One
    # process means one framing channel, and a filename must not be able to break it.
    sys.stdout.reconfigure(errors="backslashreplace")
    ok = True
    for i, p in enumerate(batch.split("\n")):
        print("\nMESH_ITEM_BEGIN %d" % i)
        try:
            if not p or not os.path.exists(p):
                print(USAGE); ok = False
            elif not check(p):
                ok = False
        except Exception as e:
            # Same shape freecadcmd prints when a single-MESH run dies on a bad mesh. It matches
            # verify-slice.sh's grep no better than freecadcmd's line did, so the file reports empty
            # and blocks — identical to what the per-process loop produced.
            print("Exception while processing file: %s [%s]" % (p, e)); ok = False
        print("\nMESH_ITEM_END %d" % i)
        sys.stdout.flush()
    sys.exit(0 if ok else 1)

p = os.environ.get("MESH")
if not p or not os.path.exists(p):
    print(USAGE); sys.stdout.flush(); sys.exit(2)
ok = check(p)
sys.stdout.flush()
sys.exit(0 if ok else 1)
