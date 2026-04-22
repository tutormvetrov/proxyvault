from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "release_bundle.py"


def load_release_bundle_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_release_bundle_module", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load release bundle module from {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_release_bundle_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _runtime_manifest(self) -> dict[str, object]:
        installer_bytes = b"wireguard-msi-payload"
        installer_hash = hashlib.sha256(installer_bytes).hexdigest()
        amneziawg_bytes = {
            "amneziawg.exe": b"amneziawg-runtime",
            "awg.exe": b"awg-runtime",
            "wintun.dll": b"wintun-runtime",
        }
        return {
            "wireguard": {
                "windows_amd64": {
                    "version": "test",
                    "archive_name": "wireguard-test.msi",
                    "sha256": installer_hash,
                    "url": "https://example.com/wireguard-test.msi",
                }
            },
            "amneziawg": {
                "windows_amd64": {
                    "version": "test",
                    "runtime_dir": "engines/amneziawg/windows/AmneziaWG",
                    "files": {
                        name: {"sha256": hashlib.sha256(payload).hexdigest()}
                        for name, payload in amneziawg_bytes.items()
                    },
                }
            }
        }

    def _populate_windows_stage(self, stage_dir: Path) -> None:
        manifest = self._runtime_manifest()
        installer_name = manifest["wireguard"]["windows_amd64"]["archive_name"]
        installer_hash = manifest["wireguard"]["windows_amd64"]["sha256"]
        amneziawg_dir = manifest["amneziawg"]["windows_amd64"]["runtime_dir"]
        amneziawg_payloads = {
            f"{amneziawg_dir}/amneziawg.exe": b"amneziawg-runtime",
            f"{amneziawg_dir}/awg.exe": b"awg-runtime",
            f"{amneziawg_dir}/wintun.dll": b"wintun-runtime",
        }
        for relpath in self.module.windows_stage_required_relpaths(manifest):
            target = stage_dir / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            if relpath.as_posix() == f"engines/wireguard/windows/{installer_name}":
                target.write_bytes(b"wireguard-msi-payload")
            elif relpath.as_posix() == "engines/wireguard/windows/wireguard-bootstrap.json":
                target.write_text(
                    json.dumps(
                        {
                            "version": "test",
                            "installer_name": installer_name,
                            "sha256": installer_hash,
                            "url": "https://example.com/wireguard-test.msi",
                        }
                    ),
                    encoding="utf-8",
                )
            elif relpath.as_posix() in amneziawg_payloads:
                target.write_bytes(amneziawg_payloads[relpath.as_posix()])
            elif relpath.name == "proxyvault.portable":
                target.write_text("", encoding="utf-8")
            else:
                target.write_text("stub", encoding="utf-8")

    def _populate_macos_stage(self, stage_dir: Path) -> None:
        for relpath in self.module.macos_stage_required_relpaths():
            target = stage_dir / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("stub", encoding="utf-8")

    def test_validate_release_stage_passes_for_complete_windows_stage(self) -> None:
        stage_dir = self.temp_path / "ProxyVault-win-x64"
        stage_dir.mkdir(parents=True)
        self._populate_windows_stage(stage_dir)
        self.module.load_runtime_manifest = self._runtime_manifest

        self.module.validate_release_stage(platform_name="windows", stage_dir=stage_dir)

    def test_validate_release_stage_rejects_wrong_platform_payloads(self) -> None:
        stage_dir = self.temp_path / "ProxyVault-win-x64"
        stage_dir.mkdir(parents=True)
        self._populate_windows_stage(stage_dir)
        self.module.load_runtime_manifest = self._runtime_manifest
        wrong_platform = stage_dir / "engines" / "sing-box" / "macos" / "sing-box"
        wrong_platform.parent.mkdir(parents=True, exist_ok=True)
        wrong_platform.write_text("bad", encoding="utf-8")

        with self.assertRaises(self.module.ReleaseBundleError) as error:
            self.module.validate_release_stage(platform_name="windows", stage_dir=stage_dir)

        self.assertIn("wrong-platform payloads", str(error.exception))

    def test_validate_release_archive_checks_zip_contents(self) -> None:
        stage_dir = self.temp_path / "ProxyVault-win-x64"
        stage_dir.mkdir(parents=True)
        self._populate_windows_stage(stage_dir)
        self.module.load_runtime_manifest = self._runtime_manifest
        archive_path = self.temp_path / "ProxyVault-win-x64.zip"

        with zipfile.ZipFile(archive_path, "w") as archive:
            for path in stage_dir.rglob("*"):
                if path.is_file():
                    archive.write(path, arcname=f"{stage_dir.name}/{path.relative_to(stage_dir).as_posix()}")

        self.module.validate_release_archive(platform_name="windows", archive_path=archive_path)

    def test_validate_release_stage_rejects_corrupt_amneziawg_payload(self) -> None:
        stage_dir = self.temp_path / "ProxyVault-win-x64"
        stage_dir.mkdir(parents=True)
        self._populate_windows_stage(stage_dir)
        self.module.load_runtime_manifest = self._runtime_manifest
        corrupt = stage_dir / "engines" / "amneziawg" / "windows" / "AmneziaWG" / "amneziawg.exe"
        corrupt.write_bytes(b"corrupt")

        with self.assertRaises(self.module.ReleaseBundleError) as error:
            self.module.validate_release_stage(platform_name="windows", stage_dir=stage_dir)

        self.assertIn("AmneziaWG runtime payload checksum", str(error.exception))

    def test_validate_release_stage_rejects_windows_payload_inside_macos_bundle(self) -> None:
        stage_dir = self.temp_path / "ProxyVault-macos-universal2"
        stage_dir.mkdir(parents=True)
        self._populate_macos_stage(stage_dir)
        wrong_platform = (
            stage_dir
            / "ProxyVault.app"
            / "Contents"
            / "Resources"
            / "engines"
            / "wireguard"
            / "windows"
            / "proxyvault-wireguard-windows.exe"
        )
        wrong_platform.parent.mkdir(parents=True, exist_ok=True)
        wrong_platform.write_text("bad", encoding="utf-8")

        with self.assertRaises(self.module.ReleaseBundleError) as error:
            self.module.validate_release_stage(platform_name="macos", stage_dir=stage_dir)

        self.assertIn("wrong-platform payloads", str(error.exception))


if __name__ == "__main__":
    unittest.main()
