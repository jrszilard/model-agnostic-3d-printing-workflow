"""Import-safe geometry interface tests using stubs, not CAD claims."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class GeometryAPI(unittest.TestCase):
    def setUp(self):
        self.part = Mock()
        self.mesh = Mock()
        spec = importlib.util.spec_from_file_location("geometry_test_instance", Path(__file__).with_name("geometry.py"))
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"Part": self.part, "Mesh": self.mesh}):
            spec.loader.exec_module(self.module)
        self.part.Shape.assert_not_called()
        self.mesh.Mesh.assert_not_called()

    def test_no_cli_or_registry_imports(self):
        self.assertNotIn("main", vars(self.module))
        self.assertEqual(set(k for k, v in vars(self.module).items() if isinstance(v, types.ModuleType)), {"os"})

    def test_missing_step_is_not_validity_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            checks, step, stl = self.module.cad_integrity(directory, {})
        self.assertEqual(checks, {"step_present": False})
        self.assertIsNone(step)
        self.assertIsNone(stl)

    def test_all_solids_and_faces_checked_without_mesh_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "candidate.step").write_text("owned text not STEP")
            shape = self.part.Shape.return_value
            shape.isValid.return_value = True
            shape.Solids = [Mock(), Mock()]
            shape.Solids[0].isClosed.return_value = True
            shape.Solids[1].isClosed.return_value = False
            shape.Faces = [Mock(isValid=Mock(return_value=False))]
            checks, _, _ = self.module.cad_integrity(directory, {"primary_step": "candidate.step"})
            self.assertFalse(checks["closed"])
            self.assertFalse(checks["single_solid"])
            self.assertFalse(checks["no_bad_faces"])
            shape.tessellate.assert_not_called()
            self.assertIs(self.module._read_step(Path(directory, "candidate.step")), shape)
            self.part.Shape.assert_called_once()
