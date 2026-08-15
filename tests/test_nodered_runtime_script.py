"""Kleine Vertragstests fuer die modusspezifische Runtime-CLI."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_nodered_orchestration.sh"


def write_executable(root: Path, name: str, content: str) -> Path:
    """Kleines CLI-Testprogramm anlegen."""
    path = root / name
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def run_fake_runtime(
    fake_bin: Path,
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Runtime mit isolierten Testprogrammen ausfuehren."""
    env = {"PATH": f"{fake_bin}:/usr/bin:/bin"}
    env.update(extra_env or {})
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def install_ready_cli(fake_bin: Path) -> tuple[Path, Path]:
    """CLI-Doubles fuer frischen Ready-Status anlegen."""
    counter = fake_bin / "sub-count"
    publish_log = fake_bin / "publish.log"
    write_executable(fake_bin, "docker", "#!/usr/bin/env bash\nexit 0\n")
    write_executable(fake_bin, "mosquitto_sub", (
        "#!/usr/bin/env bash\n"
        f"counter={counter!s}\n"
        "count=0\n"
        "[[ -f \"$counter\" ]] && count=$(cat \"$counter\")\n"
        "count=$((count + 1))\n"
        "printf '%s' \"$count\" > \"$counter\"\n"
        "if [[ $count -eq 1 ]]; then\n"
        "  printf '%s\\n' '{\"state\":\"ready\",\"ts_ms\":1}'\n"
        "else\n"
        "  printf '%s\\n' '{\"state\":\"ready\",\"ts_ms\":9999999999999}'\n"
        "fi\n"
    ))
    write_executable(
        fake_bin, "mosquitto_pub",
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {publish_log!s}\n",
    )
    return counter, publish_log


def install_hmi_cli(fake_bin: Path, curl_exit: int = 0) -> Path:
    """CLI-Doubles fuer HMI-Bereitschaft anlegen."""
    publish_log = fake_bin / "publish.log"
    write_executable(fake_bin, "docker", "#!/usr/bin/env bash\nexit 0\n")
    write_executable(fake_bin, "mosquitto_sub", (
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' '{\"state\":\"ready\",\"ts_ms\":9999999999999}'\n"
    ))
    write_executable(
        fake_bin, "mosquitto_pub",
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {publish_log!s}\n",
    )
    write_executable(fake_bin, "curl", f"#!/usr/bin/env bash\nexit {curl_exit}\n")
    return publish_log


def install_flow_update_docker(fake_bin: Path) -> Path:
    """Docker-Double mit aktiver Laufkonfiguration anlegen."""
    docker_log = fake_bin / "docker.log"
    content = """#!/usr/bin/env bash
if [[ "$1" == "compose" && "$*" == *"ps -q node_red"* ]]; then
  printf '%s\n' 'node-red-test-id'
  exit 0
fi
if [[ "$1" == "inspect" ]]; then
  cat <<'EOF'
COMMAND_OUTPUT_ENABLED=true
TRACE_PROFILE=full-storage-attempt
LIVE_TRACE_PAYLOADS=/trace/attempt.jsonl
FACTORY_SEED=77
FACTORY_VGR_BASE_RUNTIME_MS=110
FACTORY_HBW_BASE_RUNTIME_MS=120
FACTORY_MPO_BASE_RUNTIME_MS=130
FACTORY_SLD_BASE_RUNTIME_MS=140
EOF
  exit 0
fi
"""
    values = "${COMMAND_OUTPUT_ENABLED:-unset}|${TRACE_PROFILE:-unset}|"
    values += "${LIVE_TRACE_PAYLOADS:-unset}|${FACTORY_SEED:-unset}|"
    values += "${FACTORY_VGR_BASE_RUNTIME_MS:-unset}|${FACTORY_HBW_BASE_RUNTIME_MS:-unset}|"
    values += "${FACTORY_MPO_BASE_RUNTIME_MS:-unset}|${FACTORY_SLD_BASE_RUNTIME_MS:-unset}|$*"
    content += f"printf '%s\\n' \"{values}\" >> {docker_log!s}\nexit 0\n"
    write_executable(fake_bin, "docker", content)
    return docker_log


class NodeRedRuntimeScriptTests(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_help_lists_mode_specific_commands_and_virtual_aliases(self) -> None:
        env = os.environ.copy()
        env.update({
            "STORAGE_IMAGE": "registry.example/storage@sha256:" + "1" * 64,
            "VGR_IMAGE": "registry.example/vgr@sha256:" + "2" * 64,
            "HBW_IMAGE": "registry.example/hbw@sha256:" + "3" * 64,
            "NODE_RED_IMAGE": "registry.example/node-red@sha256:" + "4" * 64,
        })
        result = subprocess.run(
            [str(SCRIPT), "help"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        expected_fragments = (
            "physical-preflight",
            "virtual-preflight",
            "physical-status",
            "virtual-status",
            "physical-down",
            "virtual-down",
            "Alias fuer virtual-status", "VGR_MODEL_DIR", "VGR_IMAGE",
            "manage_model_candidates.py", "Kein Hot-Swap",
            "--command-output-enabled", "--trace-profile", "full-storage-attempt",
            "FACTORY_VGR_BASE_RUNTIME_MS", "FACTORY_HBW_BASE_RUNTIME_MS",
            "FACTORY_MPO_BASE_RUNTIME_MS", "FACTORY_SLD_BASE_RUNTIME_MS",
            "Standard jeweils 100", "virtual-hmi", "/dashboard/betrieb",
        )
        for fragment in expected_fragments:
            self.assertIn(fragment, result.stdout)

    def test_diagnosis_is_rejected_for_physical_mode_before_docker_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text("VGR_IMAGE=registry.example/vgr:test\n", encoding="utf-8")
            result = self.run_script(
                "physical-up",
                "--diagnosis",
                "--skip-preflight",
                "--env-file",
                str(env_file),
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bereits Diagnosebetrieb", result.stderr)

    def test_physical_command_output_requires_explicit_switch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir)
            docker_log = fake_bin / "docker.log"
            (fake_bin / "docker").write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s|%s\\n' \"${{COMMAND_OUTPUT_ENABLED:-unset}}\" \"$*\" >> {docker_log!s}\n"
                "if [[ \"$1\" == \"ps\" ]]; then exit 0; fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            (fake_bin / "docker").chmod(0o755)
            env = {"PATH": f"{fake_bin}:/usr/bin:/bin"}

            result = subprocess.run(
                [
                    str(SCRIPT),
                    "physical-up",
                    "--skip-preflight",
                    "--no-build",
                    "--command-output-enabled",
                    "--env-file",
                    str(fake_bin / "missing.env"),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            docker_calls = docker_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Command-Output=true", result.stdout)
        self.assertIn("true|compose", docker_calls)

    def test_complete_image_reference_requires_explicit_images_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text("VGR_IMAGE=registry.example/vgr:test\n", encoding="utf-8")
            result = self.run_script(
                "physical-up",
                "--skip-preflight",
                "--env-file",
                str(env_file),
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nur mit --images", result.stderr)

    def test_status_accepts_release_images_without_images_switch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir)
            docker_log = fake_bin / "docker.log"
            env_file = fake_bin / ".env"
            env_file.write_text(
                "VGR_IMAGE=registry.example/vgr@sha256:" + "2" * 64 + "\n",
                encoding="utf-8",
            )
            (fake_bin / "docker").write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s\\n' \"$*\" >> {docker_log!s}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            (fake_bin / "docker").chmod(0o755)
            env = {"PATH": f"{fake_bin}:/usr/bin:/bin"}

            result = subprocess.run(
                [str(SCRIPT), "physical-status", "--env-file", str(env_file)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            docker_calls = docker_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("compose", docker_calls)
        self.assertIn("ps", docker_calls)

    def test_virtual_run_ignores_stale_retained_ready_before_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir)
            counter, publish_log = install_ready_cli(fake_bin)
            result = run_fake_runtime(
                fake_bin, "virtual-run", "--skip-preflight", "--no-build",
                "--env-file", str(fake_bin / "missing.env"),
                extra_env={
                "READY_TIMEOUT_S": "5",
                "REPORT_ROOT_HOST": str(fake_bin / "reports"),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(counter.read_text(encoding="utf-8"), "2")
            published = publish_log.read_text(encoding="utf-8")
            self.assertGreaterEqual(published.count('{"cmd":"reset"}'), 2)
            self.assertEqual(published.count('"cmd":"start"'), 1)
            self.assertIn('"model_profile":"deployment-current"', published)

    def test_virtual_hmi_waits_for_ready_without_starting_a_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir)
            publish_log = install_hmi_cli(fake_bin)
            result = run_fake_runtime(
                fake_bin, "virtual-hmi", "--skip-preflight", "--no-build",
                "--env-file", str(fake_bin / "missing.env"),
                extra_env={
                    "READY_TIMEOUT_S": "5",
                    "REPORT_ROOT_HOST": str(fake_bin / "reports"),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("/dashboard/betrieb", result.stdout)
            published = publish_log.read_text(encoding="utf-8")
            self.assertIn('{"cmd":"reset"}', published)
            self.assertNotIn('{"cmd":"start"}', published)

    def test_virtual_hmi_fails_when_dashboard_route_is_not_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir)
            for name, content in {
                "docker": "#!/usr/bin/env bash\nexit 0\n",
                "mosquitto_sub": (
                    "#!/usr/bin/env bash\n"
                    "printf '%s\\n' '{\"state\":\"ready\",\"ts_ms\":9999999999999}'\n"
                ),
                "mosquitto_pub": "#!/usr/bin/env bash\nexit 0\n",
                "curl": "#!/usr/bin/env bash\nexit 22\n",
            }.items():
                path = fake_bin / name
                path.write_text(content, encoding="utf-8")
                path.chmod(0o755)

            result = subprocess.run(
                [
                    str(SCRIPT),
                    "virtual-hmi",
                    "--skip-preflight",
                    "--no-build",
                    "--env-file",
                    str(fake_bin / "missing.env"),
                ],
                cwd=ROOT,
                env={
                    "PATH": f"{fake_bin}:/usr/bin:/bin",
                    "READY_TIMEOUT_S": "5",
                    "HMI_READY_TIMEOUT_S": "1",
                    "REPORT_ROOT_HOST": str(fake_bin / "reports"),
                },
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("flow-update", result.stderr)

    def test_flow_update_preserves_running_virtual_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir)
            docker_log = install_flow_update_docker(fake_bin)
            result = run_fake_runtime(
                fake_bin, "flow-update", "--env-file", str(fake_bin / "missing.env"),
            )
            docker_calls = docker_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("aktive virtuelle Laufkonfiguration", result.stdout)
        self.assertIn(
            "true|full-storage-attempt|/trace/attempt.jsonl|77|110|120|130|140",
            docker_calls,
        )

    def test_full_storage_trace_profile_is_forwarded_to_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir)
            docker_log = fake_bin / "docker.log"
            (fake_bin / "docker").write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s|%s\\n' \"${{LIVE_TRACE_PAYLOADS:-unset}}\" \"$*\" >> {docker_log!s}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            (fake_bin / "docker").chmod(0o755)
            env = {
                "PATH": f"{fake_bin}:/usr/bin:/bin",
                "REPORT_ROOT_HOST": str(fake_bin / "reports"),
            }
            result = subprocess.run(
                [
                    str(SCRIPT),
                    "virtual-up",
                    "--skip-preflight",
                    "--no-build",
                    "--trace-profile",
                    "full-storage-attempt",
                    "--env-file",
                    str(fake_bin / "missing.env"),
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            docker_calls = docker_log.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Testszenario=full-storage-attempt", result.stdout)
        self.assertIn("/opt/ai-cps-node-red/data/live_plc_full_storage_attempt/payloads.jsonl", docker_calls)

    def test_historical_model_profile_is_forwarded_only_in_virtual_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_bin = Path(tmp_dir)
            docker_log = fake_bin / "docker.log"
            (fake_bin / "docker").write_text(
                "#!/usr/bin/env bash\n"
                f"printf '%s|%s\\n' \"${{MODEL_PROFILE:-unset}}\" \"$*\" >> {docker_log!s}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            (fake_bin / "docker").chmod(0o755)
            result = subprocess.run(
                [
                    str(SCRIPT), "virtual-up", "--skip-preflight", "--no-build",
                    "--model-profile", "historical-full-storage-error",
                    "--env-file", str(fake_bin / "missing.env"),
                ],
                cwd=ROOT,
                env={"PATH": f"{fake_bin}:/usr/bin:/bin", "REPORT_ROOT_HOST": str(fake_bin / "reports")},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("historical-full-storage-error", docker_log.read_text(encoding="utf-8"))

            physical = self.run_script(
                "physical-up", "--model-profile", "historical-full-storage-error",
                "--skip-preflight", "--env-file", str(fake_bin / "missing.env"),
            )
            self.assertNotEqual(physical.returncode, 0)
            self.assertIn("gilt nur fuer virtual-up/virtual-hmi/virtual-run", physical.stderr)

    def test_trace_profile_is_rejected_for_physical_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / ".env"
            env_file.write_text("VGR_IMAGE=registry.example/vgr:test\n", encoding="utf-8")
            result = self.run_script(
                "physical-up",
                "--trace-profile",
                "full-storage-attempt",
                "--skip-preflight",
                "--env-file",
                str(env_file),
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gilt nur fuer virtual-up/virtual-hmi/virtual-run", result.stderr)


if __name__ == "__main__":
    unittest.main()
