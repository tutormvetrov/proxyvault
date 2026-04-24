from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "tools" / "runtime_assets" / "amneziawg_helper_windows.py"


def load_helper_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_amneziawg_helper_windows_module", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module from {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AmneziaWGHelperWindowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_helper_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.config_path = self.temp_path / "pvawg-deadbeef-123456.conf"
        self.config_path.write_text("[Interface]\nPrivateKey=test\nAddress=10.0.0.2/32\n", encoding="utf-8")
        self.log_path = self.temp_path / "pvawg-deadbeef-123456.log"
        self.captured: dict[str, object] = {}

        def fake_emit(payload: dict[str, object], *, exit_code: int = 0) -> int:
            self.captured["payload"] = payload
            self.captured["exit_code"] = exit_code
            return exit_code

        self.module.emit = fake_emit

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_decode_output_falls_back_to_cp866_for_russian_console_text(self) -> None:
        original_getpreferredencoding = self.module.locale.getpreferredencoding
        self.module.locale.getpreferredencoding = lambda _do_setlocale=False: "ascii"
        try:
            decoded = self.module._decode_output("Состояние : 4 RUNNING".encode("cp866"))
        finally:
            self.module.locale.getpreferredencoding = original_getpreferredencoding

        self.assertIn("Состояние", decoded)
        self.assertIn("RUNNING", decoded)

    def test_query_service_reads_structured_cim_json(self) -> None:
        self.module._run_powershell = lambda command: self.module.CommandResult(
            exit_code=0,
            stdout='{"Name":"AmneziaWGTunnel$pvawg-deadbeef-123456","State":"Start Pending","ProcessId":4567,"Status":"OK"}',
            stderr="",
        )

        service_state = self.module.query_service("AmneziaWGTunnel$pvawg-deadbeef-123456")

        self.assertIsNotNone(service_state)
        assert service_state is not None
        self.assertEqual(service_state.state, "START_PENDING")
        self.assertEqual(service_state.pid, 4567)

    def test_cmd_up_returns_error_when_service_never_appears(self) -> None:
        self.module.locate_amneziawg_exe = lambda: Path("C:/Program Files/AmneziaWG/amneziawg.exe")
        self.module.query_service = lambda service_name: None
        self.module.find_reusable_running_tunnel = lambda tunnel_name, config_path: None
        self.module.cleanup_stopped_matching_tunnel_services = lambda tunnel_name: ""
        self.module.configure_service_manual = lambda service_name: ""
        self.module.run_command = lambda command: self.module.CommandResult(exit_code=0, stdout="", stderr="")
        self.module.run_elevated_command = lambda command: self.module.CommandResult(exit_code=0, stdout="", stderr="")
        self.module.wait_for_service = lambda service_name, desired_state, timeout=10.0: None
        self.module.latest_handshake_status = lambda handle: self.module.HandshakeStatus()
        self.module.collect_install_failure_diagnostics = lambda **kwargs: self.module.InstallFailureDiagnostics(
            reason_code="tunnel_exited_early",
            message="AmneziaWG tunnel service disappeared right after install.",
            log_excerpt="Expected service query (AmneziaWGTunnel$pvawg-deadbeef-123456): service missing.",
        )

        args = argparse.Namespace(
            config=str(self.config_path),
            log=str(self.log_path),
            tunnel_name="pvawg-deadbeef-123456",
            elevation_flow=False,
        )

        exit_code = self.module.cmd_up(args)

        self.assertEqual(exit_code, 1)
        payload = self.captured["payload"]
        self.assertEqual(payload["runtime_state"], "ERROR")
        self.assertEqual(payload["reason_code"], "tunnel_exited_early")
        self.assertIn("disappeared right after install", payload["last_error"])

    def test_cmd_up_reuses_matching_running_tunnel(self) -> None:
        self.module.locate_amneziawg_exe = lambda: Path("C:/Program Files/AmneziaWG/amneziawg.exe")
        self.module.query_service = lambda service_name: None
        self.module.find_reusable_running_tunnel = lambda tunnel_name, config_path: self.module.ServiceState(
            state="RUNNING",
            pid=6789,
            service_name="AmneziaWGTunnel$pvawg-deadbeef-654321",
            config_path=str(self.config_path),
        )
        self.module.latest_handshake_status = lambda handle: self.module.HandshakeStatus(
            last_handshake_at="2026-04-23T11:00:00"
        )
        self.module.run_command = lambda command: self.fail("cmd_up should not install a duplicate service")

        args = argparse.Namespace(
            config=str(self.config_path),
            log=str(self.log_path),
            tunnel_name="pvawg-deadbeef-123456",
            elevation_flow=False,
        )

        exit_code = self.module.cmd_up(args)

        self.assertEqual(exit_code, 0)
        payload = self.captured["payload"]
        self.assertEqual(payload["runtime_state"], "RUNNING")
        self.assertEqual(payload["handle"], "pvawg-deadbeef-654321")
        self.assertEqual(payload["pid"], 6789)

    def test_cmd_up_elevated_install_sequence_cleans_and_configures_once(self) -> None:
        calls: list[tuple[str, Path, Path]] = []
        self.module.locate_amneziawg_exe = lambda: Path("C:/Program Files/AmneziaWG/amneziawg.exe")
        self.module.query_service = lambda service_name: None
        self.module.find_reusable_running_tunnel = lambda tunnel_name, config_path: None
        self.module._is_process_elevated = lambda: False
        self.module.run_elevated_install_sequence = (
            lambda *, tunnel_name, config_path, amneziawg_exe: (
                calls.append((tunnel_name, config_path, amneziawg_exe))
                or self.module.CommandResult(exit_code=0, stdout="installed", stderr="")
            )
        )
        self.module.wait_for_service = lambda service_name, desired_state, timeout=10.0: self.module.ServiceState(
            state="RUNNING",
            pid=1234,
            service_name=service_name,
            config_path=str(self.config_path),
        )
        self.module.latest_handshake_status = lambda handle: self.module.HandshakeStatus()

        args = argparse.Namespace(
            config=str(self.config_path),
            log=str(self.log_path),
            tunnel_name="pvawg-deadbeef",
            elevation_flow=True,
        )

        exit_code = self.module.cmd_up(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, [("pvawg-deadbeef", self.config_path, Path("C:/Program Files/AmneziaWG/amneziawg.exe"))])
        self.assertEqual(self.captured["payload"]["runtime_state"], "RUNNING")

    def test_latest_handshake_status_marks_permission_denied_as_unavailable(self) -> None:
        self.module.locate_awg_exe = lambda: Path("C:/Program Files/AmneziaWG/awg.exe")
        self.module.run_command = lambda command: self.module.CommandResult(
            exit_code=1,
            stdout="",
            stderr="Unable to access interface pvawg-deadbeef: Permission denied",
        )

        status = self.module.latest_handshake_status("pvawg-deadbeef")

        self.assertEqual(status.last_handshake_at, "")
        self.assertIn(self.module.HANDSHAKE_UNAVAILABLE_WARNING, status.warning_codes)

    def test_cmd_up_returns_bundle_incomplete_when_bundled_runtime_is_missing(self) -> None:
        helper_dir = self.temp_path / "helper"
        helper_dir.mkdir(parents=True)
        self.module._helper_directory = lambda: helper_dir
        self.module.locate_amneziawg_exe = lambda: None

        args = argparse.Namespace(
            config=str(self.config_path),
            log=str(self.log_path),
            tunnel_name="pvawg-deadbeef-123456",
            elevation_flow=False,
        )

        exit_code = self.module.cmd_up(args)

        self.assertEqual(exit_code, 1)
        payload = self.captured["payload"]
        self.assertEqual(payload["reason_code"], "bundle_incomplete")
        self.assertIn("bundled AmneziaWG runtime files are missing", payload["last_error"])

    def test_collect_install_failure_diagnostics_detects_split_tunnel_conflict(self) -> None:
        self.module.query_service_text = lambda service_name: "OpenService FAILED 1060: The specified service does not exist."
        self.module.list_related_services_text = lambda: (
            "Running  AmneziaVPN-service         AmneziaVPN-service\n"
            "Running  AmneziaWGTunnel$AmneziaVPN Amnezia VPN (tunnel)"
        )
        self.module.recent_event_log_text = lambda **kwargs: (
            "Service Control Manager\n"
            "Amnezia Split Tunnel Service failed to start because the file already exists."
        )

        diagnostics = self.module.collect_install_failure_diagnostics(
            tunnel_name="pvawg-deadbeef-123456",
            service_name="AmneziaWGTunnel$pvawg-deadbeef-123456",
            amneziawg_exe=Path("C:/Program Files/AmneziaWG/amneziawg.exe"),
            install_output="",
            service_state=None,
        )

        self.assertEqual(diagnostics.reason_code, "service_conflict")
        self.assertIn("Split Tunnel", diagnostics.message)
        self.assertIn("AmneziaWGTunnel$AmneziaVPN", diagnostics.message)

    def test_collect_install_failure_diagnostics_detects_object_already_exists_conflict(self) -> None:
        self.module.query_service_text = lambda service_name: (
            "SERVICE_NAME: AmneziaWGTunnel$pvawg-deadbeef-123456\n"
            "        STATE              : 1  STOPPED\n"
            "        WIN32_EXIT_CODE    : 5010  (0x1392)\n"
        )
        self.module.list_related_services_text = lambda: (
            "Running  AmneziaWGTunnel$pvawg-deadbeef-654321 AmneziaWG Tunnel: pvawg-deadbeef-654321"
        )
        self.module.recent_event_log_text = lambda **kwargs: (
            "Service Control Manager\n"
            "The AmneziaWG Tunnel: pvawg-deadbeef-123456 service terminated with the following error:\n"
            "The object already exists."
        )

        diagnostics = self.module.collect_install_failure_diagnostics(
            tunnel_name="pvawg-deadbeef-123456",
            service_name="AmneziaWGTunnel$pvawg-deadbeef-123456",
            amneziawg_exe=Path("C:/Program Files/AmneziaWG/amneziawg.exe"),
            install_output="",
            service_state=self.module.ServiceState(state="STOPPED", pid=0),
        )

        self.assertEqual(diagnostics.reason_code, "service_conflict")
        self.assertIn("object already exists", diagnostics.message.lower())

    def test_cmd_status_keeps_foreign_amnezia_tunnel_from_looking_alive(self) -> None:
        self.module.query_service = lambda service_name: None
        self.module.locate_amneziawg_exe = lambda: Path("C:/Program Files/AmneziaWG/amneziawg.exe")
        self.module.note_install_attempt(self.log_path, "pvawg-deadbeef-123456", self.config_path)
        self.module.collect_install_failure_diagnostics = lambda **kwargs: self.module.InstallFailureDiagnostics(
            reason_code="tunnel_exited_early",
            message=(
                "AmneziaWG tunnel service disappeared right after install.\n\n"
                "Related Amnezia services:\n"
                "Running  AmneziaWGTunnel$AmneziaVPN Amnezia VPN (tunnel)"
            ),
            log_excerpt="Related Amnezia services:\nRunning  AmneziaWGTunnel$AmneziaVPN Amnezia VPN (tunnel)",
        )

        args = argparse.Namespace(
            handle="pvawg-deadbeef-123456",
            config="",
            log=str(self.log_path),
        )

        exit_code = self.module.cmd_status(args)

        self.assertEqual(exit_code, 0)
        payload = self.captured["payload"]
        self.assertEqual(payload["runtime_state"], "ERROR")
        self.assertEqual(payload["reason_code"], "tunnel_exited_early")
        self.assertIn("AmneziaWGTunnel$AmneziaVPN", payload["log_excerpt"])


if __name__ == "__main__":
    unittest.main()
