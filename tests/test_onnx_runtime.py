"""Optional real ONNX execution, separate from base JSON/protocol tests.

No weights are downloaded. Each test builds a tiny self-contained numerical
graph and executes it through the application's actual ONNX Runtime adapter.
"""

import base64
import hashlib
import importlib.util
import math
import tempfile
import unittest
from pathlib import Path

from hypothesis_lab.models import infer_uploaded, inspect_uploaded

HAS_RUNTIME = all(importlib.util.find_spec(name) is not None for name in ("onnx", "onnxruntime"))
SKIP_REASON = (
    "Optional native ONNX tests require both onnx and onnxruntime; base workflows need neither"
)


def graph_bytes():
    import onnx
    from onnx import TensorProto, helper

    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["features", "weights"], ["linear"]),
            helper.make_node("Add", ["linear", "bias"], ["score"]),
            helper.make_node("Sigmoid", ["score"], ["probability"]),
        ],
        "local-numeric-test-only",
        [helper.make_tensor_value_info("features", TensorProto.FLOAT, [1, 2])],
        [helper.make_tensor_value_info("probability", TensorProto.FLOAT, [1, 1])],
        initializer=[
            helper.make_tensor("weights", TensorProto.FLOAT, [2, 1], [1.0, -2.0]),
            helper.make_tensor("bias", TensorProto.FLOAT, [1], [0.5]),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
    model.ir_version = 10
    onnx.checker.check_model(model)
    return model.SerializeToString()


@unittest.skipUnless(HAS_RUNTIME, SKIP_REASON)
class NativeONNXTests(unittest.TestCase):
    def setUp(self):
        self.graph = graph_bytes()
        self.rows = [
            {"metric_one": 0.0, "metric_two": 0.0},
            {"metric_one": 2.0, "metric_two": 0.25},
            {"metric_one": -2.0, "metric_two": 1.0},
        ]
        self.configuration = {
            "feature_names": ["metric_one", "metric_two"],
            "output_name": "probability",
            "output_column": 0,
            "output_kind": "probability",
        }

    def assert_expected_probabilities(self, predictions):
        expected = [
            1 / (1 + math.exp(-(row["metric_one"] - 2 * row["metric_two"] + 0.5)))
            for row in self.rows
        ]
        self.assertEqual(len(predictions), len(expected))
        for actual, wanted in zip(predictions, expected):
            self.assertAlmostEqual(actual, wanted, places=6)

    def test_uploaded_graph_inspection_and_actual_fixed_batch_inference(self):
        artifact = {"format": "onnx", "data_base64": base64.b64encode(self.graph).decode()}
        description = inspect_uploaded(artifact)
        self.assertEqual(description["inputs"][0]["shape"], [1, 2])
        self.assertEqual(description["outputs"][0]["name"], "probability")
        predictions, model = infer_uploaded(artifact, self.rows, self.configuration)
        self.assert_expected_probabilities(predictions)
        self.assertEqual(model["output_kind"], "probability")
        self.assertEqual(model["sha256"], hashlib.sha256(self.graph).hexdigest())

    def test_explicit_local_graph_path_uses_actual_file_hash_and_same_inference(self):
        temporary_root = Path(__file__).resolve().parents[1] / "work" / "test-optional-onnx"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            path = Path(directory) / "numeric.onnx"
            path.write_bytes(self.graph)
            artifact = {"format": "onnx", "model_path": str(path), "allow_local_file": True}
            description = inspect_uploaded(artifact)
            predictions, model = infer_uploaded(artifact, self.rows, self.configuration)
        self.assert_expected_probabilities(predictions)
        self.assertEqual(description["sha256"], hashlib.sha256(self.graph).hexdigest())
        self.assertEqual(model["sha256"], description["sha256"])


if __name__ == "__main__":
    unittest.main()
