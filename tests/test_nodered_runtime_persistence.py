"""Prueft die kontrollierte Initialisierung des persistenten Node-RED-Stands."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = (
    ROOT
    / "scenarios/serve_ft_nns_external_broker/x86_64/node_red/entrypoint.sh"
)


class NodeRedRuntimePersistenceTests(unittest.TestCase):
    def create_source(self, root: Path, flow_content: str) -> Path:
        source = root / "source"
        for directory in ("config", "lib", "data"):
            (source / directory).mkdir(parents=True, exist_ok=True)
            (source / directory / "marker.txt").write_text(directory, encoding="utf-8")
        (source / "flows.json").write_text(flow_content, encoding="utf-8")
        (source / "settings.js").write_text("module.exports = {};", encoding="utf-8")
        (source / "package.json").write_text("{}", encoding="utf-8")
        return source

    def run_install(
        self,
        source: Path,
        runtime: Path,
        *,
        force: bool = False,
        version: str = "test-version",
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "AI_CPS_RUNTIME_SOURCE": str(source),
            "AI_CPS_RUNTIME_ROOT": str(runtime),
            "AI_CPS_RUNTIME_VERSION": version,
            "AI_CPS_FORCE_RUNTIME_UPDATE": "true" if force else "false",
        }
        return subprocess.run(
            [str(ENTRYPOINT), "install-only"],
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_reuses_runtime_until_explicit_force_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            source = self.create_source(root, "version-one")
            self.run_install(source, runtime)
            self.assertEqual((runtime / "flows.json").read_text(encoding="utf-8"), "version-one")

            (source / "flows.json").write_text("version-two", encoding="utf-8")
            self.run_install(source, runtime)
            self.assertEqual((runtime / "flows.json").read_text(encoding="utf-8"), "version-one")

            self.run_install(source, runtime, force=True)
            self.assertEqual((runtime / "flows.json").read_text(encoding="utf-8"), "version-two")

    def test_reports_stale_persistent_runtime_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runtime = root / "runtime"
            source = self.create_source(root, "version-one")
            self.run_install(source, runtime, version="version-one")

            (source / "flows.json").write_text("version-two", encoding="utf-8")
            result = self.run_install(source, runtime, version="version-two")

            self.assertEqual((runtime / "flows.json").read_text(encoding="utf-8"), "version-one")
            self.assertIn("persistent runtime version-one is older than image version-two", result.stderr)
            self.assertIn("flow-update", result.stderr)


if __name__ == "__main__":
    unittest.main()
