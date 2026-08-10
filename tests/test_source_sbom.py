"""Tests for the deterministic source dependency inventory."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import build_source_sbom as sbom


class SourceSbomTests(unittest.TestCase):
    def test_sbom_combines_pinned_python_and_node_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "configs").mkdir()
            (root / "configs/runtime_release.json").write_text(
                json.dumps(
                    {
                        "release": "runtime-v1.1.0",
                        "repository": "ma-ho-git/ai-cps-runtime",
                    }
                ),
                encoding="utf-8",
            )
            for relative in sbom.PYTHON_LOCKS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "Example_Pkg==1.2.3 \\\n    --hash=sha256:test\n",
                    encoding="utf-8",
                )
            node_lock = root / sbom.NODE_LOCK
            node_lock.parent.mkdir(parents=True, exist_ok=True)
            node_lock.write_text(
                json.dumps(
                    {
                        "packages": {
                            "": {"name": "root", "version": "1.0.0"},
                            "node_modules/example": {
                                "version": "4.5.6",
                                "license": "MIT",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            document = sbom.build_sbom(root)

        self.assertEqual(document["bomFormat"], "CycloneDX")
        self.assertEqual(document["metadata"]["component"]["version"], "1.1.0")
        components = {item["purl"]: item for item in document["components"]}
        self.assertIn("pkg:pypi/example-pkg@1.2.3", components)
        self.assertEqual(
            components["pkg:npm/example@4.5.6"]["licenses"],
            [{"license": {"id": "MIT"}}],
        )
