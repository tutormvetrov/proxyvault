from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.db import DatabaseManager
from app.models import ProxyEntry, ProxyType
from app.runtime.adapters.amneziawg_windows import AmneziaWGAdapterWindows
from app.runtime.adapters.wireguard_windows import WireGuardAdapterWindows
from app.runtime.amneziawg_windows_support import AmneziaWGWindowsAssetLocator
from app.runtime.enums import RouteOwnerKind, RuntimeEngineKind, RuntimeState, SessionStopReason, SystemProxyState
from app.runtime.manager import RuntimeManager
from app.runtime.wireguard_support import (
    WIREGUARD_FAILURE_SYSTEM_PROMPT_DENIED,
    WireGuardCommandResult,
)
from app.runtime.wireguard_windows_support import WireGuardWindowsAssetLocator
from tests.runtime.fakes import FakeAdapter, FakeRouteController
from tests.runtime.test_wireguard_adapters import AMNEZIAWG_URI, FakeWireGuardRunner, WIREGUARD_URI


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


class WireGuardManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "proxyvault.db"
        self.db = DatabaseManager(self.db_path)
        self.helper_path = self.temp_path / "proxyvault-wireguard-windows.exe"
        self.helper_path.write_text("helper", encoding="utf-8")
        self.generated_dir = self.temp_path / "generated"
        self.logs_dir = self.temp_path / "logs"
        self.route_controller = FakeRouteController()
        self.proxy_adapter = FakeAdapter(
            engine_kind=RuntimeEngineKind.SING_BOX,
            supported_types={ProxyType.VLESS_WS},
            route_owner_kind=RouteOwnerKind.PROXY,
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def _make_windows_adapter(self, runner: FakeWireGuardRunner) -> WireGuardAdapterWindows:
        return WireGuardAdapterWindows(
            runner=runner,
            asset_locator=WireGuardWindowsAssetLocator(
                helper_path=self.helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )

    def _make_awg_windows_adapter(self, runner: FakeWireGuardRunner) -> AmneziaWGAdapterWindows:
        return AmneziaWGAdapterWindows(
            runner=runner,
            asset_locator=AmneziaWGWindowsAssetLocator(
                helper_path=self.helper_path,
                generated_dir=self.generated_dir,
                logs_dir=self.logs_dir,
            ),
            platform_name="Windows",
        )

    def test_wireguard_clears_proxy_route_and_history_keeps_wireguard_engine(self) -> None:
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "wg-main-handle",
                        "pid": 5000,
                        "runtime_state": "RUNNING",
                        "last_activity_at": "2026-04-22T10:05:00",
                    }
                ),
            ),
        )
        runner.queue(
            "down",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps({"runtime_state": "DISCONNECTED", "exit_code": 0}),
            ),
        )
        manager = RuntimeManager(
            self.db,
            adapters=[self.proxy_adapter, self._make_windows_adapter(runner)],
            route_controller=self.route_controller,
        )

        self.db.save_entry(
            ProxyEntry(
                id="proxy-main",
                name="proxy-main",
                uri="vless://uuid@example.com:443?type=ws#proxy-main",
                type=ProxyType.VLESS_WS,
                transport="ws",
                server_host="example.com",
                server_port=443,
            )
        )
        self.db.save_entry(make_wireguard_entry("wg-main"))

        manager.start_entry("proxy-main", make_primary=True)
        manager.start_entry("wg-main")
        snapshot = manager.snapshot()

        self.assertEqual(snapshot.route_owner_kind, RouteOwnerKind.WIREGUARD)
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.CLEAR)
        self.assertIn(SessionStopReason.ROUTE_TAKEN_BY_WIREGUARD, self.route_controller.clear_calls)

        manager.stop_entry("wg-main")
        after_stop = manager.snapshot()
        history = manager.history_for_entry("wg-main")

        self.assertEqual(after_stop.route_owner_kind, RouteOwnerKind.NONE)
        self.assertEqual(after_stop.system_proxy_state, SystemProxyState.CLEAR)
        self.assertEqual(self.route_controller.apply_calls, ["proxy-main"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].engine_kind, RuntimeEngineKind.WIREGUARD_WINDOWS.value)
        self.assertEqual(history[0].state, RuntimeState.DISCONNECTED.value)
        self.assertEqual(history[0].route_owner_kind, RouteOwnerKind.WIREGUARD.value)

    def test_wireguard_start_failure_is_saved_with_normalized_reason(self) -> None:
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=1,
                stderr="Authorization was canceled by the user.",
            ),
        )
        manager = RuntimeManager(
            self.db,
            adapters=[self._make_windows_adapter(runner)],
            route_controller=self.route_controller,
        )
        self.db.save_entry(make_wireguard_entry("wg-denied"))

        manager.start_entry("wg-denied")
        history = manager.history_for_entry("wg-denied")
        prefs = self.db.load_runtime_prefs("wg-denied")

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].failure_reason, WIREGUARD_FAILURE_SYSTEM_PROMPT_DENIED)
        self.assertEqual(history[0].engine_kind, RuntimeEngineKind.WIREGUARD_WINDOWS.value)
        self.assertEqual(prefs.last_error, WIREGUARD_FAILURE_SYSTEM_PROMPT_DENIED)

    def test_amneziawg_clears_proxy_route_and_history_keeps_awg_engine(self) -> None:
        self.helper_path.write_text("helper", encoding="utf-8")
        runner = FakeWireGuardRunner()
        runner.queue(
            "up",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {
                        "handle": "awg-main-handle",
                        "pid": 5500,
                        "runtime_state": "RUNNING",
                        "last_activity_at": "2026-04-22T10:35:00",
                    }
                ),
            ),
        )
        runner.queue(
            "down",
            WireGuardCommandResult(
                exit_code=0,
                stdout=json.dumps({"runtime_state": "DISCONNECTED", "exit_code": 0}),
            ),
        )
        manager = RuntimeManager(
            self.db,
            adapters=[self.proxy_adapter, self._make_awg_windows_adapter(runner)],
            route_controller=self.route_controller,
        )

        self.db.save_entry(
            ProxyEntry(
                id="proxy-main",
                name="proxy-main",
                uri="vless://uuid@example.com:443?type=ws#proxy-main",
                type=ProxyType.VLESS_WS,
                transport="ws",
                server_host="example.com",
                server_port=443,
            )
        )
        self.db.save_entry(make_amneziawg_entry("awg-main"))

        manager.start_entry("proxy-main", make_primary=True)
        manager.start_entry("awg-main")
        snapshot = manager.snapshot()

        self.assertEqual(snapshot.route_owner_kind, RouteOwnerKind.WIREGUARD)
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.CLEAR)
        self.assertIn(SessionStopReason.ROUTE_TAKEN_BY_WIREGUARD, self.route_controller.clear_calls)

        manager.stop_entry("awg-main")
        after_stop = manager.snapshot()
        history = manager.history_for_entry("awg-main")

        self.assertEqual(after_stop.route_owner_kind, RouteOwnerKind.NONE)
        self.assertEqual(after_stop.system_proxy_state, SystemProxyState.CLEAR)
        self.assertEqual(self.route_controller.apply_calls, ["proxy-main"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].engine_kind, RuntimeEngineKind.AMNEZIAWG_WINDOWS.value)
        self.assertEqual(history[0].state, RuntimeState.DISCONNECTED.value)
        self.assertEqual(history[0].route_owner_kind, RouteOwnerKind.WIREGUARD.value)


if __name__ == "__main__":
    unittest.main()
