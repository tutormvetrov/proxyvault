from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import DatabaseManager
from app.models import ProxyType
from app.runtime.enums import RouteOwnerKind, RuntimeEngineKind, RuntimeState, SystemProxyState
from app.runtime.manager import ERROR_SYSTEM_PROXY_APPLY_FAILED, RuntimeManager
from tests.runtime.fakes import FakeAdapter, FakeRouteController, make_entry


class RuntimeAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "proxyvault.db"
        self.db = DatabaseManager(self.db_path)
        settings = self.db.load_settings()
        settings.has_seen_welcome = True
        settings.log_retention_lines = 32
        self.db.save_settings(settings)
        self.proxy_adapter = FakeAdapter(
            engine_kind=RuntimeEngineKind.SING_BOX,
            supported_types={ProxyType.VLESS_WS, ProxyType.TROJAN, ProxyType.SHADOWSOCKS},
            route_owner_kind=RouteOwnerKind.PROXY,
        )
        self.wireguard_adapter = FakeAdapter(
            engine_kind=RuntimeEngineKind.WIREGUARD_WINDOWS,
            supported_types={ProxyType.WIREGUARD},
            route_owner_kind=RouteOwnerKind.WIREGUARD,
        )
        self.amneziawg_adapter = FakeAdapter(
            engine_kind=RuntimeEngineKind.AMNEZIAWG_WINDOWS,
            supported_types={ProxyType.AMNEZIAWG},
            route_owner_kind=RouteOwnerKind.WIREGUARD,
        )
        self.route_controller = FakeRouteController()
        self.manager = RuntimeManager(
            self.db,
            adapters=[self.proxy_adapter, self.wireguard_adapter, self.amneziawg_adapter],
            route_controller=self.route_controller,
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def _save_entry(self, entry_id: str, proxy_type: ProxyType) -> None:
        self.db.save_entry(make_entry(entry_id, proxy_type))

    def _history_states(self, entry_id: str) -> list[str]:
        return [item.state for item in self.manager.history_for_entry(entry_id)]

    def test_stop_all_flushes_active_sessions_to_history(self) -> None:
        self._save_entry("proxy-1", ProxyType.VLESS_WS)
        self._save_entry("proxy-2", ProxyType.TROJAN)

        self.manager.start_entry("proxy-1", make_primary=True)
        self.manager.start_entry("proxy-2")
        self.manager.stop_all()
        snapshot = self.manager.snapshot()

        self.assertEqual(snapshot.sessions, [])
        self.assertEqual(snapshot.active_session_count, 0)
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.CLEAR)
        self.assertEqual(self._history_states("proxy-1"), [RuntimeState.DISCONNECTED.value])
        self.assertEqual(self._history_states("proxy-2"), [RuntimeState.DISCONNECTED.value])

    def test_shutdown_clears_primary_proxy_and_shuts_route_controller_once(self) -> None:
        self._save_entry("proxy-main", ProxyType.VLESS_WS)

        self.manager.start_entry("proxy-main", make_primary=True)
        self.manager.shutdown()
        snapshot = self.manager.snapshot()

        self.assertEqual(snapshot.sessions, [])
        self.assertEqual(snapshot.primary_session_id, "")
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.CLEAR)
        self.assertIn("APP_EXIT", {reason.value for reason in self.route_controller.clear_calls})
        self.assertEqual(self.route_controller.shutdown_calls, 1)
        self.assertEqual(self._history_states("proxy-main"), [RuntimeState.DISCONNECTED.value])

    def test_shutdown_respects_clear_system_proxy_on_exit_setting(self) -> None:
        settings = self.db.load_settings()
        settings.clear_system_proxy_on_exit = False
        self.db.save_settings(settings)
        self._save_entry("proxy-main", ProxyType.VLESS_WS)

        self.manager.start_entry("proxy-main", make_primary=True)
        self.manager.shutdown()
        snapshot = self.manager.snapshot()
        prefs = self.db.load_runtime_prefs("proxy-main")

        self.assertEqual(snapshot.sessions, [])
        self.assertEqual(snapshot.primary_session_id, "")
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.APPLIED)
        self.assertEqual(snapshot.system_proxy_entry_id, "proxy-main")
        self.assertNotIn("APP_EXIT", {reason.value for reason in self.route_controller.clear_calls})
        self.assertEqual(self.route_controller.shutdown_calls, 1)
        self.assertTrue(prefs.auto_launch)
        self.assertTrue(prefs.preferred_primary)

    def test_system_proxy_apply_failure_is_recorded_without_crashing_session_start(self) -> None:
        failures: list[tuple[str, str]] = []
        self.manager.operationFailed.connect(lambda entry_id, reason: failures.append((entry_id, reason)))
        self.route_controller.apply_state = SystemProxyState.ERROR
        self._save_entry("proxy-error", ProxyType.SHADOWSOCKS)

        self.manager.start_entry("proxy-error", make_primary=True)
        snapshot = self.manager.snapshot()
        prefs = self.db.load_runtime_prefs("proxy-error")

        self.assertEqual(snapshot.active_session_count, 1)
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.ERROR)
        self.assertEqual(snapshot.system_proxy_entry_id, "")
        self.assertEqual(snapshot.route_owner_kind, RouteOwnerKind.NONE)
        self.assertEqual(prefs.last_error, ERROR_SYSTEM_PROXY_APPLY_FAILED)
        self.assertEqual(failures, [("proxy-error", ERROR_SYSTEM_PROXY_APPLY_FAILED)])

    def test_multiple_proxy_sessions_keep_single_primary_owner(self) -> None:
        self._save_entry("proxy-a", ProxyType.VLESS_WS)
        self._save_entry("proxy-b", ProxyType.TROJAN)

        self.manager.start_entry("proxy-a", make_primary=True)
        self.manager.start_entry("proxy-b", make_primary=False)
        snapshot = self.manager.snapshot()
        primary_sessions = [session for session in snapshot.sessions if session.is_primary]

        self.assertEqual(snapshot.active_session_count, 2)
        self.assertEqual(len(primary_sessions), 1)
        self.assertEqual(primary_sessions[0].entry_id, "proxy-a")
        self.assertEqual(snapshot.route_owner_kind, RouteOwnerKind.PROXY)


if __name__ == "__main__":
    unittest.main()
