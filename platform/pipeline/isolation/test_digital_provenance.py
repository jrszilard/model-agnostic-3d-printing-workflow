"""The actual manufacturing validator must reject a digital record (no CAD)."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluate


class DigitalProvenance(unittest.TestCase):
    def test_existing_validator_rejects_digital_schema_before_build_inputs(self):
        path = Path(__file__).resolve().parents[1] / "generate/build_provenance.py"
        spec = importlib.util.spec_from_file_location("evaluation_test_producer", path)
        producer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(producer)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            part = root / "part"
            part.mkdir()
            (part / "spec.yaml").write_text("{}\n")
            record_path = root / "digital.json"
            record_path.write_text(json.dumps({"schema": evaluate.SCHEMA, "owner_root": str(root),
                                               "part": "part", "manufacturing_qualified": False}))
            # Test-only repository discovery stubs, never used by a real worker or record.
            with patch.object(producer.scope, "repo_root", return_value=root), \
                 patch.object(producer.scope, "producer_path", return_value=record_path), \
                 patch.object(producer, "build_inputs") as inputs:
                with self.assertRaisesRegex(ValueError, "invalid or relocated build provenance"):
                    producer.validate(part)
                inputs.assert_not_called()
