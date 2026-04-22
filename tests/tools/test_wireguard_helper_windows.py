from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "tools" / "runtime_assets" / "wireguard_helper_windows.py"


def load_helper_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_wireguard_helper_windows_module", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module from {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class WireGuardHelperWindowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_helper_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.config_path = self.temp_path / "proxyvault-entry.conf"
        self.config_path.write_text("[Interface]\nPrivateKey=test\nAddress=10.0.0.2/32\n", encoding="utf-8")
        self.log_path = self.temp_path / "proxyvault-entry.log"
        self.captured: dict[str, object] = {}

        def fake_emit(payload: dict[str, object], *, exit_code: int = 0) -> int:
            self.captured["payload"] = payload
            self.captured["exit_code"] = exit_code
            return exit_code

        self.module.emit = fake_emit

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_query_service_reads_structured_cim_json(self) -> None:
        self.module._run_powershell = lambda command: self.module.CommandResult(
            exit_code=0,
            stdout='{"Name":"WireGuardTunnel$proxyvault-entry","State":"Running","ProcessId":4567,"Status":"OK"}',
            stderr="",
        )

        service_state = self.module.query_service("WireGuardTunnel$proxyvault-entry")

        self.assertIsNotNone(service_state)
        assert service_state is not None
        self.assertEqual(service_state.state, "RUNNING")
        self.assertEqual(service_state.pid, 4567)

    def test_cmd_up_bootstraps_wireguard_before_installing_tunnel_service(self) -> None:
        bootstrap_payload = self.module.WireGuardBootstrapPayload(
            installer_path=self.temp_path / "wireguard-amd64-test.msi",
            installer_name="wireguard-amd64-test.msi",
            version="test",
            sha256="deadbeef",
        )
        locate_calls = iter(
            [
                None,
                Path("C:/Program Files/WireGuard/wireguard.exe"),
            ]
        )
        self.module.locate_wireguard_exe = lambda: next(locate_calls)
        self.module.load_wireguard_bootstrap_payload = lambda: bootstrap_payload
        self.module.validate_wireguard_bootstrap_payload = lambda payload: (True, "")
        self.module.install_wireguard_bootstrap_payload = lambda payload, log_path, elevation_flow: self.module.BootstrapInstallResult(
            exit_code=0,
            output="Installed bundled WireGuard runtime.",
            installer_log_excerpt="",
        )
        self.module.run_command = lambda command: self.module.CommandResult(exit_code=0, stdout="", stderr="")
        self.module.run_elevated_command = lambda command: self.module.CommandResult(exit_code=0, stdout="", stderr="")
        self.module.wait_for_service = lambda service_name, desired_state, timeout=10.0: self.module.ServiceState(
            state="RUNNING",
            pid=4321,
        )
        self.module.latest_handshake_iso = lambda handle: ""

        args = argparse.Namespace(
            config=str(self.config_path),
            log=str(self.log_path),
            tunnel_name="proxyvault-entry",
            elevation_flow=False,
        )

        exit_code = self.module.cmd_up(args)

        self.assertEqual(exit_code, 0)
        payload = self.captured["payload"]
        self.assertEqual(payload["runtime_state"], "RUNNING")
        self.assertEqual(payload["pid"], 4321)
        self.assertIn("Installed bundled WireGuard runtime.", payload["log_excerpt"])

    def test_cmd_up_returns_bundle_incomplete_when_bootstrap_payload_is_invalid(self) -> None:
        bootstrap_payload = self.module.WireGuardBootstrapPayload(
            installer_path=self.temp_path / "wireguard-amd64-test.msi",
            installer_name="wireguard-amd64-test.msi",
            version="test",
            sha256="deadbeef",
        )
        self.module.locate_wireguard_exe = lambda: None
        self.module.load_wireguard_bootstrap_payload = lambda: bootstrap_payload
        self.module.validate_wireguard_bootstrap_payload = lambda payload: (
            False,
            "ProxyVault build is incomplete: bundled WireGuard bootstrap payload checksum mismatch.",
        )

        args = argparse.Namespace(
            config=str(self.config_path),
            log=str(self.log_path),
            tunnel_name="proxyvault-entry",
            elevation_flow=False,
        )

        exit_code = self.module.cmd_up(args)

        self.assertEqual(exit_code, 1)
        payload = self.captured["payload"]
        self.assertEqual(payload["reason_code"], "bundle_incomplete")
        self.assertIn("checksum mismatch", payload["last_error"])

    def test_ensure_wireguard_exe_maps_uac_cancellation_to_system_prompt_denied(self) -> None:
        bootstrap_payload = self.module.WireGuardBootstrapPayload(
            installer_path=self.temp_path / "wireguard-amd64-test.msi",
            installer_name="wireguard-amd64-test.msi",
            version="test",
            sha256="deadbeef",
        )
        self.module.locate_wireguard_exe = lambda: None
        self.module.load_wireguard_bootstrap_payload = lambda: bootstrap_payload
        self.module.validate_wireguard_bootstrap_payload = lambda payload: (True, "")
        self.module.install_wireguard_bootstrap_payload = lambda payload, log_path, elevation_flow: self.module.BootstrapInstallResult(
            exit_code=1223,
            output="",
            installer_log_excerpt="",
        )

        executable, reason_code, message = self.module.ensure_wireguard_exe(
            log_path=self.log_path,
            elevation_flow=True,
        )

        self.assertIsNone(executable)
        self.assertEqual(reason_code, "system_prompt_denied")
        self.assertIn("cancelled", message.lower())


if __name__ == "__main__":
    unittest.main()
