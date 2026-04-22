from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models import AppSettings
from app.runtime.amneziawg_macos_support import AmneziaWGMacOSAssetLocator
from app.runtime.amneziawg_windows_support import AmneziaWGWindowsAssetLocator
from app.runtime.paths import default_engine_root_candidates, default_engine_root_dir, ensure_runtime_dirs
from app.runtime.wireguard_macos_support import WireGuardMacOSAssetLocator
from app.runtime.wireguard_support import WIREGUARD_FAILURE_HELPER_NOT_FOUND, WireGuardAdapterError
from app.runtime.wireguard_windows_support import WireGuardWindowsAssetLocator


ROOT = Path(__file__).resolve().parents[1]


class ReleaseLayoutTests(unittest.TestCase):
    def test_runtime_directory_helpers_create_expected_portable_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            with patch("app.runtime.paths.resolve_app_dir", return_value=fake_root):
                directories = ensure_runtime_dirs()

            self.assertEqual(set(directories.keys()), {"runtime_root", "generated", "logs", "engines"})
            self.assertEqual(directories["runtime_root"], fake_root / "runtime")
            self.assertEqual(directories["generated"], fake_root / "runtime" / "generated")
            self.assertEqual(directories["logs"], fake_root / "runtime" / "logs")
            self.assertTrue(directories["engines"].name == "engines")
            for key in ("runtime_root", "generated", "logs"):
                path = directories[key]
                self.assertTrue(path.exists(), path)
                self.assertTrue(path.is_dir(), path)
            self.assertEqual(directories["engines"], default_engine_root_dir())

    def test_default_engine_root_candidates_prefer_bundled_paths_for_frozen_layouts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            windows_executable = Path(temp_dir) / "ProxyVault" / "ProxyVault.exe"
            windows_candidates = default_engine_root_candidates(
                executable_path=windows_executable,
                frozen=True,
            )
            self.assertEqual(windows_candidates[0], windows_executable.parent / "engines")
            self.assertIn(windows_executable.parent / "_internal" / "engines", windows_candidates)

            fake_app = Path(temp_dir) / "ProxyVault.app"
            macos_executable = fake_app / "Contents" / "MacOS" / "ProxyVault"
            macos_candidates = default_engine_root_candidates(
                executable_path=macos_executable,
                frozen=True,
            )
            self.assertEqual(
                macos_candidates[0],
                fake_app / "Contents" / "Resources" / "engines",
            )
            self.assertIn(fake_app / "Contents" / "MacOS" / "engines", macos_candidates)
            self.assertIn(Path(temp_dir) / "engines", macos_candidates)

    def test_default_settings_point_engine_root_to_bundled_engines_directory(self) -> None:
        settings = AppSettings.default()

        self.assertTrue(settings.engine_root_dir)
        self.assertTrue(Path(settings.engine_root_dir).name == "engines")
        self.assertEqual(settings.ui_language, "ru")

    def test_wireguard_windows_asset_locator_uses_bundled_helper_and_creates_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            helper_path = fake_root / "engines" / "wireguard" / "windows" / "proxyvault-wireguard-windows.exe"
            helper_path.parent.mkdir(parents=True)
            helper_path.write_text("stub", encoding="utf-8")
            generated_dir = fake_root / "runtime" / "generated"
            logs_dir = fake_root / "runtime" / "logs"

            assets = WireGuardWindowsAssetLocator(
                engine_root_dir=fake_root / "engines",
                generated_dir=generated_dir,
                logs_dir=logs_dir,
            ).locate()

            self.assertEqual(assets.helper_path, helper_path)
            self.assertTrue(generated_dir.exists())
            self.assertTrue(logs_dir.exists())

    def test_wireguard_macos_asset_locator_uses_bundled_helper_and_creates_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            helper_path = fake_root / "engines" / "wireguard" / "macos" / "proxyvault-wireguard-macos"
            helper_path.parent.mkdir(parents=True)
            helper_path.write_text("stub", encoding="utf-8")
            generated_dir = fake_root / "runtime" / "generated"
            logs_dir = fake_root / "runtime" / "logs"

            assets = WireGuardMacOSAssetLocator(
                engine_root_dir=fake_root / "engines",
                generated_dir=generated_dir,
                logs_dir=logs_dir,
            ).locate()

            self.assertEqual(assets.helper_path, helper_path)
            self.assertTrue(generated_dir.exists())
            self.assertTrue(logs_dir.exists())

    def test_wireguard_asset_locators_fail_with_clear_helper_message_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_engine_root = Path(temp_dir) / "engines"
            for locator_cls in (WireGuardWindowsAssetLocator, WireGuardMacOSAssetLocator):
                with self.subTest(locator=locator_cls.__name__):
                    with self.assertRaises(WireGuardAdapterError) as error:
                        locator_cls(engine_root_dir=fake_engine_root).locate()
                    self.assertEqual(error.exception.failure_reason, WIREGUARD_FAILURE_HELPER_NOT_FOUND)
                    self.assertIn("WireGuard", error.exception.last_error)

    def test_amneziawg_asset_locators_use_bundled_helpers_and_create_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_root = Path(temp_dir)
            windows_helper = fake_root / "engines" / "amneziawg" / "windows" / "proxyvault-amneziawg-windows.exe"
            macos_helper = fake_root / "engines" / "amneziawg" / "macos" / "proxyvault-amneziawg-macos"
            windows_helper.parent.mkdir(parents=True)
            macos_helper.parent.mkdir(parents=True)
            windows_helper.write_text("stub", encoding="utf-8")
            macos_helper.write_text("stub", encoding="utf-8")

            windows_assets = AmneziaWGWindowsAssetLocator(
                engine_root_dir=fake_root / "engines",
                generated_dir=fake_root / "runtime" / "generated" / "awg-win",
                logs_dir=fake_root / "runtime" / "logs" / "awg-win",
            ).locate()
            macos_assets = AmneziaWGMacOSAssetLocator(
                engine_root_dir=fake_root / "engines",
                generated_dir=fake_root / "runtime" / "generated" / "awg-mac",
                logs_dir=fake_root / "runtime" / "logs" / "awg-mac",
            ).locate()

            self.assertEqual(windows_assets.helper_path, windows_helper)
            self.assertEqual(macos_assets.helper_path, macos_helper)

    def test_amneziawg_asset_locators_fail_with_clear_helper_message_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_engine_root = Path(temp_dir) / "engines"
            for locator_cls in (AmneziaWGWindowsAssetLocator, AmneziaWGMacOSAssetLocator):
                with self.subTest(locator=locator_cls.__name__):
                    with self.assertRaises(WireGuardAdapterError) as error:
                        locator_cls(engine_root_dir=fake_engine_root).locate()
                    self.assertEqual(error.exception.failure_reason, WIREGUARD_FAILURE_HELPER_NOT_FOUND)
                    self.assertIn("AmneziaWG", error.exception.last_error)

    def test_windows_build_script_requires_clean_local_data_opt_in_and_helper_checks(self) -> None:
        script = (ROOT / "build-windows.ps1").read_text(encoding="utf-8")

        self.assertIn("[switch]$IncludeLocalData", script)
        self.assertIn("[string]$PortableSourceDir", script)
        self.assertNotIn("[switch]$SkipLocalData", script)
        self.assertIn("bootstrap_runtime_assets.py\" --target windows --rebuild-helper", script)
        self.assertIn("tools\\release_bundle.py\" copy-payload --platform windows", script)
        self.assertIn("tools\\release_bundle.py\" validate-stage --platform windows", script)
        self.assertIn("tools\\release_bundle.py\" validate-archive --platform windows", script)
        self.assertIn("tools\\run_unittest_shards.py\" --root tests --verbose", script)
        self.assertIn("resolve_sing_box_asset_layout", script)
        self.assertIn("sing_box_support_asset_names('windows')", script)
        self.assertNotIn("HOME_APP_DIR", script)
        self.assertIn("proxyvault.portable", script)
        self.assertIn("ProxyVault-win-x64.zip", script)
        self.assertIn("engines\\wireguard\\windows\\proxyvault-wireguard-windows.exe", script)
        self.assertIn("engines\\wireguard\\windows\\wireguard-bootstrap.json", script)
        self.assertIn("engines\\wireguard\\windows\\wireguard-amd64-0.6.1.msi", script)
        self.assertIn("engines\\amneziawg\\windows\\proxyvault-amneziawg-windows.exe", script)
        self.assertIn("tools\\runtime_assets\\THIRD_PARTY_NOTICES.md", script)
        self.assertIn("tools\\runtime_assets\\LICENSES\\README.md", script)
        self.assertIn("IncludeLocalData was requested, but no portable seed directory was provided or found.", script)
        self.assertIn(
            "Staging a clean Windows release without local data. Use -IncludeLocalData to bundle portable seed data explicitly.",
            script,
        )
        self.assertIn("if ($IncludeLocalData) {", script)
        self.assertIn("if (-not $IncludeLocalData) {", script)
        self.assertIn("Clean Windows release unexpectedly contains staged local data", script)
        self.assertIn("Assert-FileExists -LiteralPath $repoWireGuardHelper", script)
        self.assertIn("Assert-FileExists -LiteralPath $stagedWireGuardHelper", script)
        self.assertIn("Assert-FileExists -LiteralPath $repoAmneziaWGHelper", script)
        self.assertIn("Assert-FileExists -LiteralPath $stagedAmneziaWGHelper", script)
        self.assertIn("Assert-FileExists -LiteralPath $repoWireGuardBootstrapManifest", script)
        self.assertIn("Assert-FileExists -LiteralPath $repoWireGuardBootstrapMsi", script)
        self.assertIn("Assert-FileExists -LiteralPath $stagedWireGuardBootstrapManifest", script)
        self.assertIn("Assert-FileExists -LiteralPath $stagedWireGuardBootstrapMsi", script)
        self.assertIn("THIRD_PARTY_NOTICES.md", script)
        self.assertIn("LICENSES\\README.md", script)
        self.assertIn("Invoke-ProcessChecked -FilePath \"python\" -ArgumentList @(", script)
        self.assertIn("Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -PassThru -NoNewWindow", script)
        self.assertIn("\"--distpath\",", script)
        self.assertIn("('\"{0}\"' -f $distDir),", script)
        self.assertIn("\"--workpath\",", script)
        self.assertIn("('\"{0}\"' -f $buildDir)", script)
        self.assertNotIn("\"--distpath=$distDir\"", script)
        self.assertNotIn("\"--workpath=$buildDir\"", script)
        self.assertIn("engines\\sing-box\\windows\\sing-box.exe", script)
        self.assertIn("engines\\sing-box\\windows\\libcronet.dll", script)
        self.assertIn("SHA256SUMS.txt", script)
        self.assertIn("exit 0", script)

    def test_macos_build_script_requires_clean_local_data_opt_in_and_helper_checks(self) -> None:
        script = (ROOT / "build-macos.sh").read_text(encoding="utf-8")

        self.assertIn("bootstrap_runtime_assets.py\" --target macos --rebuild-helper", script)
        self.assertIn("tools/release_bundle.py\" copy-payload --platform macos", script)
        self.assertIn("tools/release_bundle.py\" validate-stage --platform macos", script)
        self.assertIn("tools/release_bundle.py\" validate-archive --platform macos", script)
        self.assertIn("tools/run_unittest_shards.py\" --root tests --verbose", script)
        self.assertIn("resolve_sing_box_asset_layout(platform_name='darwin'", script)
        self.assertNotIn("HOME_APP_DIR", script)
        self.assertIn("PORTABLE_SOURCE_DIR=\"${PORTABLE_SOURCE_DIR:-}\"", script)
        self.assertIn("INCLUDE_LOCAL_DATA=\"${INCLUDE_LOCAL_DATA:-0}\"", script)
        self.assertIn("ProxyVault-macos-${MACOS_RELEASE_TAG}.zip", script)
        self.assertIn("ProxyVault.app", script)
        self.assertIn("engines/wireguard/macos/proxyvault-wireguard-macos", script)
        self.assertIn("engines/amneziawg/macos/proxyvault-amneziawg-macos", script)
        self.assertIn("tools/runtime_assets/THIRD_PARTY_NOTICES.md", script)
        self.assertIn("tools/runtime_assets/LICENSES/README.md", script)
        self.assertIn("INCLUDE_LOCAL_DATA=1 was requested, but no portable seed directory was provided or found.", script)
        self.assertIn(
            "Staging a clean macOS release without local data. Use INCLUDE_LOCAL_DATA=1 to bundle portable seed data explicitly.",
            script,
        )
        self.assertIn("Clean macOS release unexpectedly contains bundled portable seed data", script)
        self.assertIn("assert_file_exists \"$REPO_WIREGUARD_HELPER\"", script)
        self.assertIn("assert_file_exists \"$STAGED_WIREGUARD_HELPER\"", script)
        self.assertIn("assert_file_exists \"$REPO_AMNEZIAWG_HELPER\"", script)
        self.assertIn("assert_file_exists \"$STAGED_AMNEZIAWG_HELPER\"", script)
        self.assertIn("Contents/Resources/engines/sing-box/macos/sing-box", script)
        self.assertIn("THIRD_PARTY_NOTICES.md", script)
        self.assertIn("LICENSES/README.md", script)
        self.assertIn("SHA256SUMS.txt", script)

    def test_pyinstaller_specs_keep_main_entrypoint_and_named_app_bundles(self) -> None:
        windows_spec = (ROOT / "proxyvault-windows.spec").read_text(encoding="utf-8")
        macos_spec = (ROOT / "proxyvault-macos.spec").read_text(encoding="utf-8")

        self.assertIn("['main.py']", windows_spec)
        self.assertIn("name='ProxyVault'", windows_spec)
        self.assertNotIn("Tree(str(ENGINE_TREE_ROOT), prefix=\"engines\")", windows_spec)
        self.assertNotIn("WINDOWS_RELEASE_REQUIRED_RELATIVE_PATHS", windows_spec)
        self.assertIn("['main.py']", macos_spec)
        self.assertIn("name='ProxyVault.app'", macos_spec)
        self.assertNotIn("Tree(str(ENGINE_TREE_ROOT), prefix=\"engines\")", macos_spec)
        self.assertNotIn("MACOS_RELEASE_REQUIRED_RELATIVE_PATHS", macos_spec)
        self.assertIn("bundle_identifier='com.proxyvault.app'", macos_spec)

    def test_runtime_asset_manifest_is_pinned_to_official_sing_box_releases(self) -> None:
        manifest_path = ROOT / "tools" / "runtime_assets" / "manifest.json"
        manifest = manifest_path.read_text(encoding="utf-8")

        self.assertIn("\"version\": \"1.13.10\"", manifest)
        self.assertIn("https://github.com/SagerNet/sing-box/releases/download/v1.13.10/", manifest)
        self.assertIn("\"windows_amd64\"", manifest)
        self.assertIn("\"darwin_amd64\"", manifest)
        self.assertIn("\"darwin_arm64\"", manifest)
        self.assertIn("\"sha256\"", manifest)
        self.assertIn("\"wireguard\"", manifest)
        self.assertIn("\"version\": \"0.6.1\"", manifest)
        self.assertIn("\"archive_name\": \"wireguard-amd64-0.6.1.msi\"", manifest)
        self.assertIn("https://download.wireguard.com/windows-client/wireguard-amd64-0.6.1.msi", manifest)
        self.assertIn("3721a8f12b0b8ed4d9a3120b0438ebc034ea36057d8256a88e57a773e6f46ff8", manifest)
        self.assertIn("\"amneziawg\"", manifest)
        self.assertIn("\"version\": \"2.0.0\"", manifest)
        self.assertIn("\"runtime_dir\": \"engines/amneziawg/windows/AmneziaWG\"", manifest)
        self.assertIn("5b00905ed02619fe149ceafc898e79993d4455a0cdfa92072b3bb9aee7b2d537", manifest)
        self.assertIn("26ac0be14a8353eacf2f933736f6f7912f89ec7c59c4190cc990492934c74537", manifest)
        self.assertIn("e5da8447dc2c320edc0fc52fa01885c103de8c118481f683643cacc3220dafce", manifest)

    def test_gitignore_keeps_amneziawg_runtime_payload_trackable(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("!engines/amneziawg/windows/AmneziaWG/amneziawg.exe", gitignore)
        self.assertIn("!engines/amneziawg/windows/AmneziaWG/awg.exe", gitignore)
        self.assertIn("!engines/amneziawg/windows/AmneziaWG/wintun.dll", gitignore)

    def test_release_workflow_does_not_duplicate_release_runs(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-artifacts.yml").read_text(encoding="utf-8")

        self.assertIn("push:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("\n  release:\n", workflow)
        self.assertNotIn("github.event_name == 'release'", workflow)

    def test_manual_acceptance_checklist_covers_release_layout_and_helper_review(self) -> None:
        checklist = (ROOT / "docs" / "client-mode-ru-rollout" / "80-manual-acceptance-checklist.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("## Windows Manual Acceptance", checklist)
        self.assertIn("## macOS Manual Acceptance", checklist)
        self.assertIn("## UX and Copy Review", checklist)
        self.assertIn("## Release Artifact Review", checklist)
        self.assertIn("## Known Manual-Only Areas", checklist)
        self.assertIn("чистой установке и на обновлении", checklist)
        self.assertIn("clean release", checklist.lower())
        self.assertIn("proxyvault-wireguard-windows.exe", checklist)
        self.assertIn("proxyvault-wireguard-macos", checklist)
        self.assertIn("proxyvault-amneziawg-windows.exe", checklist)
        self.assertIn("proxyvault-amneziawg-macos", checklist)
        self.assertIn("SHA256SUMS.txt", checklist)
        self.assertIn("THIRD_PARTY_NOTICES.md", checklist)
        self.assertIn("LICENSES/README.md", checklist)
        self.assertIn("wireguard-bootstrap.json", checklist)
        self.assertIn("wireguard-amd64-0.6.1.msi", checklist)
        self.assertIn("wg-quick", checklist)
        self.assertIn("awg-quick", checklist)
        self.assertNotIn("официальный Windows-client", checklist)


if __name__ == "__main__":
    unittest.main()
