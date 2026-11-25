"""SYNTHETIC TEST FIXTURES ONLY. Never used by production build/handoff.

Existing gate tests use deliberately fake STL/STEP and stubbed kernel verdicts. Add equally
synthetic producer records so those tests can isolate the gate they target. Real producer execution
is exercised separately; this does not constitute a production attestation entrypoint.
"""
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generate"))
import build_provenance as producer
import source_scope as scope


def fixture_producer(root, part):
    root, part = Path(root), Path(part)
    spec_path = part / "spec.yaml"
    spec = yaml.safe_load(spec_path.read_text()) or {}
    models = sorted(part.rglob("*.stl"))
    if not models:
        return
    steps = sorted(part.rglob("*.step"))
    if not steps:
        dummy = part / "step/fixture.step"
        dummy.parent.mkdir(parents=True, exist_ok=True)
        dummy.write_text("SYNTHETIC TEST STEP; NO CAD VERDICT\n")
        steps = [dummy]
    spec.setdefault("primary_stl", str(models[0].relative_to(part)))
    spec.setdefault("primary_step", str(steps[0].relative_to(part)))
    spec.setdefault("build", {"source": "src/fixture.py", "outputs": [
        str(p.relative_to(part)) for p in models]})
    src = part / spec["build"]["source"]
    src.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        src.write_text("# SYNTHETIC TEST INPUT; NOT A GENERATOR\n")
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False))
    record = {"schema": 1, "owner_root": str(root), "part": str(part.relative_to(root)),
              "inputs": producer.build_inputs(root, part, spec),
              "interpreter": producer.interpreter_identity(sys.executable),
              "outputs": {str(p.relative_to(root)): scope.digest(p)
                          for p in scope.outputs(part, spec) if p.is_file()},
              "physical_samples": 1}
    producer.atomic_json(scope.producer_path(root, part), record)
