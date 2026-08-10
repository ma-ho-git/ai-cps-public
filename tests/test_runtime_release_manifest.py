"""Tests for the digest-pinned portable runtime release manifest."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import build_runtime_release_manifest as release_manifest


DIGEST = "sha256:" + "a" * 64


class RuntimeReleaseManifestTests(unittest.TestCase):
    def prepare_root(self, root: Path) -> None:
        (root / "configs").mkdir()
        (root / "configs/runtime_release.json").write_text(
            json.dumps(
                {
                    "release": "runtime-v1.1.0",
                    "repository": "owner/repository",
                    "platform": "linux/amd64",
                    "compose_project": "ai-cps-test",
                    "node_red_runtime_version": "test",
                }
            ),
            encoding="utf-8",
        )
        for relative in release_manifest.PROTECTED_FILES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative, encoding="utf-8")
        for domain in release_manifest.DOMAINS:
            model = root / "model_registry" / domain / "latest"
            model.mkdir(parents=True)
            (model / "model.keras").write_bytes(domain.encode())
            (model / "activation.json").write_text(
                json.dumps({"trained_at": "2026-test"}), encoding="utf-8"
            )
            (model / "metrics.json").write_text("{}", encoding="utf-8")

    def test_manifest_contains_models_images_and_protected_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare_root(root)
            images = {
                key: f"ghcr.io/example/{name}@{DIGEST}"
                for key, name in release_manifest.IMAGE_NAMES.items()
            }
            manifest = release_manifest.build_manifest(
                release="runtime-v1.1.0",
                source_commit="1" * 40,
                images=images,
                root=root,
            )

        self.assertEqual(manifest["images"], images)
        self.assertEqual(set(manifest["models"]), set(release_manifest.DOMAINS))
        self.assertEqual(
            set(manifest["protected_files"]), set(release_manifest.PROTECTED_FILES)
        )
        self.assertTrue(manifest["models"]["vgr"]["model_id"].startswith("vgr:2026-test:"))

    def test_explicit_images_require_all_domains_and_digests(self) -> None:
        with self.assertRaises(release_manifest.ManifestError):
            release_manifest.parse_image_assignments(["vgr=not-a-digest"])
        with self.assertRaisesRegex(release_manifest.ManifestError, "missing image"):
            release_manifest.parse_image_assignments(
                [f"{key}=ghcr.io/example/{key}@{DIGEST}" for key in ("storage", "vgr")]
            )
        with self.assertRaisesRegex(release_manifest.ManifestError, "expects"):
            release_manifest.parse_image_assignments(
                [
                    f"{key}=ghcr.io/example/{key}@sha256:short"
                    for key in release_manifest.IMAGE_NAMES
                ]
            )

    def test_manifest_rejects_short_source_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare_root(root)
            images = {
                key: f"ghcr.io/example/{name}@{DIGEST}"
                for key, name in release_manifest.IMAGE_NAMES.items()
            }
            with self.assertRaisesRegex(release_manifest.ManifestError, "source commit"):
                release_manifest.build_manifest(
                    release="runtime-v1.1.0",
                    source_commit="abc123",
                    images=images,
                    root=root,
                )

    def test_public_release_uses_dedicated_runtime_image_names(self) -> None:
        self.assertEqual(
            release_manifest.IMAGE_NAMES,
            {
                "storage": "ai-cps-runtime-storage-infer",
                "vgr": "ai-cps-runtime-vgr-infer",
                "hbw": "ai-cps-runtime-hbw-infer",
                "node_red": "ai-cps-runtime-node-red",
            },
        )


if __name__ == "__main__":
    unittest.main()
