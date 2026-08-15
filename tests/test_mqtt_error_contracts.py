"""Regression tests for correlatable MQTT error responses.

The tests intentionally use only the Python standard library. They can run
without TensorFlow, NumPy, Paho MQTT or model files and protect the response
contract at the three active inference entry points.
"""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

INFERENCE_FILES = [
    ROOT / "scenarios/serve_ft_nns_external_broker/x86_64/code_base_storage/mqtt_infer.py",
    ROOT / "scenarios/serve_ft_nns_external_broker/x86_64/code_base_vgr/mqtt_infer.py",
    ROOT / "scenarios/serve_ft_nns_external_broker/x86_64/code_base_hbw/mqtt_infer.py",
]


def function_node(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{path}: function {name} not found")


def calls_named(node: ast.AST, name: str) -> list[ast.Call]:
    return [
        candidate
        for candidate in ast.walk(node)
        if isinstance(candidate, ast.Call)
        and isinstance(candidate.func, ast.Name)
        and candidate.func.id == name
    ]


def uses_correlating_error_response(path: Path) -> bool:
    on_message = function_node(path, "on_message")
    candidates = calls_named(on_message, "response_payload")
    helper_calls = calls_named(on_message, "_publish_error")
    if helper_calls:
        candidates.extend(calls_named(function_node(path, "_publish_error"), "response_payload"))
    return any(
        call.args
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "req"
        and any(keyword.arg == "error" for keyword in call.keywords)
        for call in candidates
    )


class MqttErrorContractTests(unittest.TestCase):
    def test_all_changed_entry_points_are_valid_python(self):
        for path in INFERENCE_FILES:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_inference_error_responses_keep_request_id(self):
        for path in INFERENCE_FILES:
            self.assertTrue(
                uses_correlating_error_response(path),
                f"{path}: inference errors do not use the correlating response helper",
            )

if __name__ == "__main__":
    unittest.main()
