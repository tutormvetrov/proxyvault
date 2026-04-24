from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.paths as app_paths
from app.paths import (
    PORTABLE_MARKER_NAME,
    default_db_path,
    detect_portable_app_dir,
    portable_root_candidates,
    resolve_app_dir,
    resolve_app_dir_with_seed,
)


class PortablePathTests(unittest.TestCase):
    def test_windows_frozen_candidate_uses_executable_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected_root = root.resolve()
            exe_path = root / "ProxyVault.exe"
            exe_path.write_text("", encoding="utf-8")
            (root / PORTABLE_MARKER_NAME).write_text("", encoding="utf-8")

            candidates = portable_root_candidates(executable_path=exe_path, frozen=True)
            detected = detect_portable_app_dir(executable_path=exe_path, frozen=True)

            self.assertEqual(candidates[0], expected_root)
            self.assertEqual(detected, expected_root)
            self.assertEqual(default_db_path(executable_path=exe_path, frozen=True), expected_root / "proxyvault.db")

    def test_macos_bundle_candidate_uses_parent_of_app_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage_root = Path(tmp) / "ProxyVault-macos-universal2"
            expected_stage_root = stage_root.resolve()
            macos_dir = stage_root / "ProxyVault.app" / "Contents" / "MacOS"
            macos_dir.mkdir(parents=True, exist_ok=True)
            exe_path = macos_dir / "ProxyVault"
            exe_path.write_text("", encoding="utf-8")
            (stage_root / PORTABLE_MARKER_NAME).write_text("", encoding="utf-8")

            detected = detect_portable_app_dir(executable_path=exe_path, frozen=True)

            self.assertEqual(detected, expected_stage_root)

    def test_macos_bundle_seed_bootstraps_home_database_when_sidecar_data_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage_root = Path(tmp) / "ProxyVault-macos-universal2"
            resources_dir = stage_root / "ProxyVault.app" / "Contents" / "Resources"
            macos_dir = resources_dir.parent / "MacOS"
            seed_dir = resources_dir / app_paths.BUNDLED_PORTABLE_SEED_DIRNAME
            macos_dir.mkdir(parents=True, exist_ok=True)
            seed_dir.mkdir(parents=True, exist_ok=True)

            exe_path = macos_dir / "ProxyVault"
            exe_path.write_text("", encoding="utf-8")
            (seed_dir / app_paths.DB_FILENAME).write_text("seed-db", encoding="utf-8")
            (seed_dir / app_paths.QR_DIRNAME).mkdir(parents=True, exist_ok=True)
            (seed_dir / app_paths.QR_DIRNAME / "seed.txt").write_text("seed-qr", encoding="utf-8")

            seeded_home = Path(tmp) / "SeededHome"
            with patch.object(app_paths, "HOME_APP_DIR", seeded_home):
                self.assertIsNone(detect_portable_app_dir(executable_path=exe_path, frozen=True))
                resolved = resolve_app_dir_with_seed(executable_path=exe_path, frozen=True)

            self.assertEqual(resolved, seeded_home)
            self.assertTrue((seeded_home / app_paths.DB_FILENAME).exists())
            self.assertFalse((seeded_home / app_paths.QR_DIRNAME / "seed.txt").exists())

    def test_windows_portable_seed_bootstraps_portable_storage_when_database_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_path = root / "ProxyVault.exe"
            seed_dir = root / app_paths.BUNDLED_PORTABLE_SEED_DIRNAME
            seed_dir.mkdir(parents=True, exist_ok=True)
            exe_path.write_text("", encoding="utf-8")
            (root / PORTABLE_MARKER_NAME).write_text("", encoding="utf-8")
            (seed_dir / app_paths.DB_FILENAME).write_text("seed-db", encoding="utf-8")

            resolved = resolve_app_dir_with_seed(executable_path=exe_path, frozen=True)

            self.assertEqual(resolved, root.resolve())
            self.assertEqual((root / app_paths.DB_FILENAME).read_text(encoding="utf-8"), "seed-db")

    def test_resolve_app_dir_does_not_seed_until_explicitly_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_path = root / "ProxyVault.exe"
            seed_dir = root / app_paths.BUNDLED_PORTABLE_SEED_DIRNAME
            seed_dir.mkdir(parents=True, exist_ok=True)
            exe_path.write_text("", encoding="utf-8")
            (root / PORTABLE_MARKER_NAME).write_text("", encoding="utf-8")
            (seed_dir / app_paths.DB_FILENAME).write_text("seed-db", encoding="utf-8")

            resolved = resolve_app_dir(executable_path=exe_path, frozen=True)

            self.assertEqual(resolved, root.resolve())
            self.assertFalse((root / app_paths.DB_FILENAME).exists())


if __name__ == "__main__":
    unittest.main()
