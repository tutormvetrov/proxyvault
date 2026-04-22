from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.models import ProxyEntry, ProxyType
from app.runtime.adapters.amneziawg_macos import AmneziaWGAdapterMacOS
from app.runtime.adapters.amneziawg_windows import AmneziaWGAdapterWindows
from app.runtime.adapters.wireguard_macos import WireGuardAdapterMacOS
from app.runtime.adapters.wireguard_windows import WireGuardAdapterWindows
from app.runtime.models import RuntimePrefs
from app.runtime.amneziawg_macos_support import AmneziaWGMacOSAssetLocator
from app.runtime.amneziawg_windows_support import AmneziaWGWindowsAssetLocator
from app.runtime.wireguard_macos_support import WireGuardMacOSAssetLocator
from app.runtime.wireguard_support import (
    WIREGUARD_FAILURE_BUNDLE_INCOMPLETE,
    WIREGUARD_FAILURE_HANDSHAKE_MISSING,
    WIREGUARD_FAILURE_HELPER_NOT_FOUND,
    WIREGUARD_FAILURE_PRIVILEGES_REQUIRED,
    WIREGUARD_FAILURE_SYSTEM_CONFLICT,
    WIREGUARD_WARNING_MACOS_UNSIGNED,
    WIREGUARD_WARNING_SYSTEM_PROMPT,
    WIREGUARD_WARNING_WINDOWS_ELEVATION,
    WIREGUARD_META_WARNING_CODES,
    WireGuardAdapterError,
    WireGuardCommandResult,
    build_tunnel_name,
)
from app.runtime.enums import RuntimeEngineKind
from app.runtime.wireguard_windows_support import WireGuardWindowsAssetLocator


WIREGUARD_URI = """
[Interface]
PrivateKey = test-private-key
Address = 10.0.0.2/32
DNS = 1.1.1.1

[Peer]
PublicKey = test-public-key
AllowedIPs = 0.0.0.0/0
Endpoint = 198.51.100.1:51820
PersistentKeepalive = 25
""".strip()

AMNEZIAWG_URI = """
[Interface]
PrivateKey = test-private-key
Address = 10.8.0.2/32
DNS = 1.1.1.1
Jc = 4
Jmin = 30
Jmax = 80
S1 = 15
S2 = 30
H1 = 11111111
H2 = 22222222
H3 = 33333333
H4 = 44444444
I1 = <r 2><b 0x01020304>

[Peer]
PublicKey = test-public-key
AllowedIPs = 0.0.0.0/0
Endpoint = 198.51.100.2:51820
PersistentKeepalive = 25
""".strip()


class FakeWireGuardRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._queued_results: dict[str, list[WireGuardCommandResult]] = {}

    def queue(self, action: str, result: WireGuardCommandResult) -> None:
        self._queued_results.setdefault(action, []).append(result)

    def run(self, command, *, cwd: Path, env=None, timeout=None) -> WireGuardCommandResult:
        del env
        del timeout
        self.calls.append([str(part) for part in command])
        action = str(command[1])
        queued = self._queued_results.get(action, [])
        if queued:
            return queued.pop(0)
        return WireGuardCommandResult(exit_code=0, stdout="{}")


def make_wireguard_entry(entry_id: str) -> ProxyEntry:
    return ProxyEntry(
        id=entry_id,
        name=f"{entry_id}-name",
        uri=WIREGUARD_URI,
        type=ProxyType.WIREGUARD,
        transport="udp",
        server_host="198.51.100.1",
        server_port=51820,
    )


def make_amneziawg_entry(entry_id: str) -> ProxyEntry:
    return ProxyEntry(
        id=entry_id,
        name=f"{entry_id}-name",
        uri=AMNEZIAWG_URI,
        type=ProxyType.AMNEZIAWG,
        transport="udp",
        server_host="198.51.100.2",
        server_port=51820,
    )


class WireGuardAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.generated_dir = self.temp_path / "generated"
        self.logs_dir = self.temp_path / "logs"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_helper(self, name: str) -> Path:
        helper_path = self.temp_path / name
        helper_path.parent.mkdir(parents=True, exist_ok=True)
        helper_path.write_text("helper", encoding="utf-8")
        return helper_path

    def test_windows_adapter_prepare_and_start_use_raw_uri_and_helper_flow(self) -> None:
        helper_path = self._create_helper("proxyvault-wireguard-windows.exe")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "wg-win-1",
                        "pid": 4321,
                        "runtime_state": "RUNNING",
                        "last_activity_at": "2026-04-22T10:00:01",
                        "last_handshake_at": "2026-04-22T10:00:00",
                    }
                ),
            ),
        )
        adapter = WireGuardAdapterWindows(
            runner=runner,
            asset_locator=WireGuardWindowsAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )

        launch_spec = adapter.prepare_launch(make_wireguard_entry("wg-win"), RuntimePrefs(entry_id="wg-win"), make_primary=False)
        session = adapter.start(launch_spec)

        self.assertTrue(Path(launch_spec.config_path).exists())
        self.assertEqual(Path(launch_spec.config_path).read_text(encoding="utf-8"), WIREGUARD_URI + "\n")
        self.assertEqual(session.handle, "wg-win-1")
        self.assertEqual(session.pid, 4321)
        self.assertEqual(
            session.metadata[WIREGUARD_META_WARNING_CODES],
            [WIREGUARD_WARNING_SYSTEM_PROMPT, WIREGUARD_WARNING_WINDOWS_ELEVATION],
        )
        self.assertIn("--elevation-flow", runner.calls[0])
        self.assertEqual(runner.calls[0][0], str(helper_path))

    def test_macos_adapter_prepare_and_start_exposes_unsigned_warning(self) -> None:
        helper_path = self._create_helper("proxyvault-wireguard-macos")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "wg-mac-1",
                        "pid": 987,
                        "runtime_state": "RUNNING",
                        "last_activity_at": "2026-04-22T11:00:01",
                    }
                ),
            ),
        )
        adapter = WireGuardAdapterMacOS(
            runner=runner,
            asset_locator=WireGuardMacOSAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Darwin",
        )

        launch_spec = adapter.prepare_launch(make_wireguard_entry("wg-mac"), RuntimePrefs(entry_id="wg-mac"), make_primary=False)
        session = adapter.start(launch_spec)

        self.assertEqual(session.handle, "wg-mac-1")
        self.assertEqual(
            session.metadata[WIREGUARD_META_WARNING_CODES],
            [WIREGUARD_WARNING_SYSTEM_PROMPT, WIREGUARD_WARNING_MACOS_UNSIGNED],
        )
        self.assertIn("--macos-authorization-flow", runner.calls[0])
        self.assertIn("--unsigned-build-check", runner.calls[0])

    def test_amneziawg_windows_adapter_prepare_and_start_use_awg_helper(self) -> None:
        helper_path = self._create_helper("proxyvault-amneziawg-windows.exe")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "awg-win-1",
                        "pid": 6789,
                        "runtime_state": "RUNNING",
                        "last_activity_at": "2026-04-22T12:00:01",
                    }
                ),
            ),
        )
        adapter = AmneziaWGAdapterWindows(
            runner=runner,
            asset_locator=AmneziaWGWindowsAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )

        launch_spec = adapter.prepare_launch(make_amneziawg_entry("awg-win"), RuntimePrefs(entry_id="awg-win"), make_primary=False)
        session = adapter.start(launch_spec)

        self.assertEqual(Path(launch_spec.config_path).read_text(encoding="utf-8"), AMNEZIAWG_URI + "\n")
        self.assertEqual(session.handle, "awg-win-1")
        self.assertEqual(session.pid, 6789)
        self.assertEqual(runner.calls[0][0], str(helper_path))
        self.assertIn("--elevation-flow", runner.calls[0])

    def test_amneziawg_windows_prepare_launch_uses_short_handle_name(self) -> None:
        helper_path = self._create_helper("proxyvault-amneziawg-windows.exe")
        adapter = AmneziaWGAdapterWindows(
            runner=FakeWireGuardRunner(),
            asset_locator=AmneziaWGWindowsAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )

        launch_spec = adapter.prepare_launch(
            make_amneziawg_entry("awg-win-with-a-very-long-entry-id"),
            RuntimePrefs(entry_id="awg-win-with-a-very-long-entry-id"),
            make_primary=False,
        )
        tunnel_name = launch_spec.metadata["wireguard_tunnel_name"]

        self.assertTrue(str(tunnel_name).startswith("pvawg-"))
        self.assertLessEqual(len(str(tunnel_name)), 21)
        self.assertEqual(Path(launch_spec.config_path).stem, tunnel_name)

    def test_build_tunnel_name_uses_short_hash_for_amneziawg_windows(self) -> None:
        tunnel_name = build_tunnel_name(
            "entry-with-uuid-like-8a8fe697-25e0-4b7b-8928",
            "session-with-uuid-like-0186f950-5c93",
            engine_kind=RuntimeEngineKind.AMNEZIAWG_WINDOWS,
        )

        self.assertRegex(tunnel_name, r"^pvawg-[0-9a-f]{8}-[0-9a-f]{6}$")
        self.assertLessEqual(len(tunnel_name), 21)
        self.assertNotIn("8a8fe697-25e0", tunnel_name)

    def test_windows_adapter_stop_reuses_elevation_flow_for_cleanup(self) -> None:
        helper_path = self._create_helper("proxyvault-wireguard-windows.exe")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "wg-cleanup-1",
                        "pid": 4321,
                        "runtime_state": "RUNNING",
                        "last_activity_at": "2026-04-22T10:00:01",
                    }
                ),
            ),
        )
        runner.queue(
            "down",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "wg-cleanup-1",
                        "runtime_state": "DISCONNECTED",
                        "last_activity_at": "2026-04-22T10:00:10",
                    }
                ),
            ),
        )
        adapter = WireGuardAdapterWindows(
            runner=runner,
            asset_locator=WireGuardWindowsAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )

        launch_spec = adapter.prepare_launch(make_wireguard_entry("wg-cleanup"), RuntimePrefs(entry_id="wg-cleanup"), make_primary=False)
        session = adapter.start(launch_spec)
        adapter.stop(session, reason=None)

        self.assertEqual(runner.calls[1][1], "down")
        self.assertIn("--elevation-flow", runner.calls[1])

    def test_amneziawg_macos_adapter_prepare_and_start_exposes_unsigned_warning(self) -> None:
        helper_path = self._create_helper("proxyvault-amneziawg-macos")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "utun7",
                        "runtime_state": "RUNNING",
                        "last_activity_at": "2026-04-22T12:30:01",
                    }
                ),
            ),
        )
        adapter = AmneziaWGAdapterMacOS(
            runner=runner,
            asset_locator=AmneziaWGMacOSAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Darwin",
        )

        launch_spec = adapter.prepare_launch(make_amneziawg_entry("awg-mac"), RuntimePrefs(entry_id="awg-mac"), make_primary=False)
        session = adapter.start(launch_spec)

        self.assertEqual(session.handle, "utun7")
        self.assertEqual(
            session.metadata[WIREGUARD_META_WARNING_CODES],
            [WIREGUARD_WARNING_SYSTEM_PROMPT, WIREGUARD_WARNING_MACOS_UNSIGNED],
        )
        self.assertIn("--macos-authorization-flow", runner.calls[0])
        self.assertIn("--unsigned-build-check", runner.calls[0])

    def test_start_normalizes_privilege_errors(self) -> None:
        helper_path = self._create_helper("proxyvault-wireguard-windows.exe")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=1,
                stderr="Access is denied. Administrator privileges are required.",
            ),
        )
        adapter = WireGuardAdapterWindows(
            runner=runner,
            asset_locator=WireGuardWindowsAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )
        launch_spec = adapter.prepare_launch(make_wireguard_entry("wg-priv"), RuntimePrefs(entry_id="wg-priv"), make_primary=False)

        with self.assertRaises(WireGuardAdapterError) as ctx:
            adapter.start(launch_spec)

        self.assertEqual(ctx.exception.failure_reason, WIREGUARD_FAILURE_PRIVILEGES_REQUIRED)

    def test_start_maps_helper_service_conflict_into_human_reason(self) -> None:
        helper_path = self._create_helper("proxyvault-amneziawg-windows.exe")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=1,
                stdout=json.dumps(
                    {
                        "runtime_state": "ERROR",
                        "reason_code": "service_conflict",
                        "last_error": "Amnezia Split Tunnel Service failed: file already exists.",
                        "log_excerpt": "Split Tunnel Service failed because the file already exists.",
                        "exit_code": 1,
                    }
                ),
            ),
        )
        adapter = AmneziaWGAdapterWindows(
            runner=runner,
            asset_locator=AmneziaWGWindowsAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )
        launch_spec = adapter.prepare_launch(make_amneziawg_entry("awg-conflict"), RuntimePrefs(entry_id="awg-conflict"), make_primary=False)

        with self.assertRaises(WireGuardAdapterError) as ctx:
            adapter.start(launch_spec)

        self.assertEqual(ctx.exception.failure_reason, WIREGUARD_FAILURE_SYSTEM_CONFLICT)

    def test_start_maps_bundle_incomplete_into_human_reason(self) -> None:
        helper_path = self._create_helper("proxyvault-wireguard-windows.exe")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=1,
                stdout=json.dumps(
                    {
                        "runtime_state": "ERROR",
                        "reason_code": "bundle_incomplete",
                        "last_error": "Bundled WireGuard bootstrap payload is missing from this build.",
                        "log_excerpt": "wireguard-bootstrap.json was not found next to the helper.",
                        "exit_code": 1,
                    }
                ),
            ),
        )
        adapter = WireGuardAdapterWindows(
            runner=runner,
            asset_locator=WireGuardWindowsAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )
        launch_spec = adapter.prepare_launch(
            make_wireguard_entry("wg-bundle-incomplete"),
            RuntimePrefs(entry_id="wg-bundle-incomplete"),
            make_primary=False,
        )

        with self.assertRaises(WireGuardAdapterError) as ctx:
            adapter.start(launch_spec)

        self.assertEqual(ctx.exception.failure_reason, WIREGUARD_FAILURE_BUNDLE_INCOMPLETE)

    def test_start_maps_object_already_exists_conflict_into_human_reason(self) -> None:
        helper_path = self._create_helper("proxyvault-amneziawg-windows.exe")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=1,
                stdout=json.dumps(
                    {
                        "runtime_state": "ERROR",
                        "reason_code": "tunnel_exited_early",
                        "last_error": (
                            "Expected service query (AmneziaWGTunnel$pvawg-deadbeef-123456):\n"
                            "STATE              : 1  STOPPED\n"
                            "WIN32_EXIT_CODE    : 5010  (0x1392)\n\n"
                            "Recent system events:\n"
                            "The AmneziaWG Tunnel: pvawg-deadbeef-123456 service terminated with the following error:\n"
                            "The object already exists."
                        ),
                        "log_excerpt": "The object already exists.",
                        "exit_code": 1,
                    }
                ),
            ),
        )
        adapter = AmneziaWGAdapterWindows(
            runner=runner,
            asset_locator=AmneziaWGWindowsAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )
        launch_spec = adapter.prepare_launch(make_amneziawg_entry("awg-object-exists"), RuntimePrefs(entry_id="awg-object-exists"), make_primary=False)

        with self.assertRaises(WireGuardAdapterError) as ctx:
            adapter.start(launch_spec)

        self.assertEqual(ctx.exception.failure_reason, WIREGUARD_FAILURE_SYSTEM_CONFLICT)

    def test_poll_preserves_handshake_missing_state(self) -> None:
        helper_path = self._create_helper("proxyvault-wireguard-macos")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps({"handle": "wg-status-1", "runtime_state": "RUNNING"}),
            ),
        )
        runner.queue(
            "status",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "wg-status-1",
                        "runtime_state": "ERROR",
                        "reason_code": "handshake_missing",
                        "last_error": "Handshake not established.",
                        "exit_code": 1,
                    }
                ),
            ),
        )
        adapter = WireGuardAdapterMacOS(
            runner=runner,
            asset_locator=WireGuardMacOSAssetLocator(
                helper_path=helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Darwin",
        )
        launch_spec = adapter.prepare_launch(make_wireguard_entry("wg-status"), RuntimePrefs(entry_id="wg-status"), make_primary=False)
        session = adapter.start(launch_spec)
        updated = adapter.poll(session)

        self.assertEqual(updated.failure_reason, WIREGUARD_FAILURE_HANDSHAKE_MISSING)
        self.assertEqual(updated.exit_code, 1)

    def test_prepare_launch_fails_when_helper_is_missing(self) -> None:
        adapter = WireGuardAdapterMacOS(
            runner=FakeWireGuardRunner(),
            asset_locator=WireGuardMacOSAssetLocator(
                helper_path=self.temp_path / "missing-helper",
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Darwin",
        )

        with self.assertRaises(WireGuardAdapterError) as ctx:
            adapter.prepare_launch(make_wireguard_entry("wg-missing"), RuntimePrefs(entry_id="wg-missing"), make_primary=False)

        self.assertEqual(ctx.exception.failure_reason, WIREGUARD_FAILURE_HELPER_NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
