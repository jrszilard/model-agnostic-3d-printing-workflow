"""Run only as a contained evaluation worker, after non-CAD controls pass."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

family = json.loads(Path("/inputs/request.json").read_text())["family"]
if family == "cadquery":
    import cadquery
    import OCP
    versions = {"cadquery": cadquery.__version__, "ocp": OCP.__version__}
elif family == "freecad":
    import FreeCAD
    import Part
    import Mesh
    versions = {"freecad": FreeCAD.Version(), "occt": Part.OCC_VERSION}
else:
    raise ValueError("unknown runtime")

libraries = {}
for line in Path("/proc/self/maps").read_text().splitlines():
    fields = line.split(maxsplit=5)
    if len(fields) == 6 and fields[5].startswith(("/usr/", "/runtime/")) and ".so" in fields[5]:
        libraries[fields[5]] = None
assert len(libraries) <= 512
for name in libraries:
    h = hashlib.sha256()
    with open(name, "rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    libraries[name] = h.hexdigest()

report = {"family": family, "versions": versions, "python": sys.version,
          "prefix": sys.prefix, "native_libraries": libraries,
          "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
          "limits": "local installed-runtime observation, not an immutable production image"}
Path("/work/output/runtime.json").write_text(json.dumps(report, sort_keys=True) + "\n")
