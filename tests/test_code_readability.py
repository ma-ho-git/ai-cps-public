"""Tests fuer die verbindlichen Lesbarkeitsgrenzen."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import check_code_readability as readability


class CodeReadabilityTests(unittest.TestCase):
    def test_current_repository_meets_structural_limits(self) -> None:
        self.assertEqual(readability.check_repository(include_audit=False), [])

    def test_long_main_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "sample.py"
            body = "\n".join(f"    value_{index} = {index}" for index in range(41))
            path.write_text(f"def main():\n{body}\n", encoding="utf-8")
            issues = readability.scan_python_file(root, path)
        self.assertEqual(len(issues), 1)
        self.assertIn("erlaubt 40", issues[0].detail)

    def test_jsonata_reader_finds_typed_values(self) -> None:
        node = {
            "property": "payload.value",
            "propertyType": "jsonata",
            "rules": [{"t": "set", "to": "$number(payload)", "tot": "jsonata"}],
        }
        self.assertEqual(
            readability.iter_jsonata(node),
            ["payload.value", "$number(payload)"],
        )


if __name__ == "__main__":
    unittest.main()
