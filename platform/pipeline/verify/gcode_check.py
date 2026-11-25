"""Parse a sliced gcode and assert basic printability. Stdlib only."""
import re
_NUM = r"[-+]?[0-9]*\.?[0-9]+"
FIRST_LAYER_Z_MAX = 0.35   # first extruding move at/below this Z counts as first-layer laid;
                           # sized for the K1C 0.20mm-Standard profile (first layer ~0.2-0.3mm)
def _f(tok, letter):
    m = re.search(letter + "(" + _NUM + ")", tok)
    return float(m.group(1)) if m else None

def parse_gcode(path):
    layers = 0; noz = bed = None; first_ext = False
    xmin=ymin=zmin= float("inf"); xmax=ymax=zmax= float("-inf")
    cx=cy=cz=0.0; any_ext=False; custom=False
    with open(path, errors="ignore") as fh:
        for line in fh:
            s = line.strip()
            if s.startswith(";") and ("LAYER_CHANGE" in s or s.startswith(";LAYER:")):
                layers += 1; continue
            if s.startswith(";TYPE:"):
                # Slicers wrap start/end gcode in ;TYPE:Custom. Prusa's start block runs a purge
                # line along the front lip of the bed (Y=-2.5, X up to 249) — legitimate machine
                # behaviour that is deliberately OUTSIDE the print area, so counting it as toolpath
                # made every Core One plate fail the off-bed check. Excluding these blocks also
                # stops a purge line from satisfying the first-layer-extrusion check on an
                # otherwise empty plate, so the gate gets stricter, not looser.
                custom = s.startswith(";TYPE:Custom"); continue
            if s.startswith(";"):
                continue
            if s.startswith(("M104","M109")):
                v=_f(s,"S");  noz = v if v else noz
            elif s.startswith(("M140","M190")):
                v=_f(s,"S");  bed = v if v else bed
            elif s.startswith(("G0","G1")):
                x=_f(s,"X"); y=_f(s,"Y"); z=_f(s,"Z"); e=_f(s,"E")
                if x is not None: cx=x
                if y is not None: cy=y
                if z is not None: cz=z
                # position is tracked through custom blocks (so the first real move after the
                # start gcode is not measured from a stale origin), but their extrusion is not.
                if e is not None and e > 0 and not custom:       # extruding move
                    any_ext=True
                    if cz <= FIRST_LAYER_Z_MAX: first_ext = True # first layer laid
                    xmin=min(xmin,cx); ymin=min(ymin,cy); zmin=min(zmin,cz)
                    xmax=max(xmax,cx); ymax=max(ymax,cy); zmax=max(zmax,cz)
    bbox = None if not any_ext else (xmin,ymin,zmin,xmax,ymax,zmax)
    return {"layers": layers, "ext_bbox": bbox, "first_layer_extrudes": first_ext,
            "nozzle_temp": noz, "bed_temp": bed}

def check_gcode(info, bed=(250.0,220.0,270.0)):   # Prusa Core One X x Y x Z
    hard=[]; warn=[]
    if info["layers"] < 2: hard.append("only %d layer(s) — empty/detached slice" % info["layers"])
    if not info["first_layer_extrudes"]: hard.append("no extrusion on the first layer")
    if info["nozzle_temp"] is None: hard.append("no nozzle temperature set")
    b = info["ext_bbox"]
    if b is None:
        hard.append("no extrusion moves at all")
    else:
        xmin,ymin,zmin,xmax,ymax,zmax = b
        if xmin < 0 or ymin < 0 or zmin < 0 or xmax > bed[0] or ymax > bed[1] or zmax > bed[2]:
            hard.append("toolpath off the bed: X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f] vs %s"
                        % (xmin,xmax,ymin,ymax,zmin,zmax,bed))
    return {"passed": len(hard)==0, "hard": hard, "warn": warn}
