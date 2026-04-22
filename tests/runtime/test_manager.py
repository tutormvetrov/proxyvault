from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import DatabaseManager
from app.models import ProxyType
from app.runtime.enums import (
    RouteOwnerKind,
    RuntimeEngineKind,
    RuntimeState,
    SessionStopReason,
    SystemProxyState,
)
from app.runtime.manager import (
    ERROR_UNSUPPORTED_ENTRY,
    RuntimeManager,
)
from app.runtime.models import RuntimePrefs
from tests.runtime.fakes import FakeAdapter, FakeRouteController, make_entry


class RuntimeManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "proxyvault.db"
        self.db = DatabaseManager(self.db_path)
        settings = self.db.load_settings()
        settings.log_retention_lines = 40
        self.db.save_settings(settings)
        self.proxy_adapter = FakeAdapter(
            engine_kind=RuntimeEngineKind.SING_BOX,
            supported_types={ProxyType.VLESS_WS, ProxyType.TROJAN},
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

    def _snapshot_session(self, entry_id: str):
        snapshot = self.manager.snapshot()
        for session in snapshot.sessions:
            if session.entry_id == entry_id:
                return session
        return None

    def test_start_and_stop_single_session(self) -> None:
        self._save_entry("proxy-1", ProxyType.VLESS_WS)

        self.manager.start_entry("proxy-1", make_primary=True)
        snapshot = self.manager.snapshot()
        session = self._snapshot_session("proxy-1")

        self.assertEqual(len(snapshot.sessions), 1)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(snapshot.primary_session_id, session.session_id)
        self.assertEqual(snapshot.route_owner_kind, RouteOwnerKind.PROXY)
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.APPLIED)
        self.assertEqual(session.runtime_state, RuntimeState.RUNNING)
        self.assertEqual(session.log_excerpt, "log:proxy-1")

        self.manager.stop_entry("proxy-1")
        stopped_snapshot = self.manager.snapshot()
        history = self.manager.history_for_entry("proxy-1")

        self.assertEqual(stopped_snapshot.sessions, [])
        self.assertEqual(stopped_snapshot.primary_session_id, "")
        self.assertEqual(stopped_snapshot.system_proxy_state, SystemProxyState.CLEAR)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].state, RuntimeState.DISCONNECTED.value)

    def test_terminal_start_persists_history_log_path_from_launch_spec(self) -> None:
        self._save_entry("awg-terminal", ProxyType.AMNEZIAWG)
        failing_adapter = FakeAdapter(
            engine_kind=RuntimeEngineKind.AMNEZIAWG_WINDOWS,
            supported_types={ProxyType.AMNEZIAWG},
            route_owner_kind=RouteOwnerKind.WIREGUARD,
            start_state=RuntimeState.ERROR,
        )
        manager = RuntimeManager(self.db, adapters=[failing_adapter], route_controller=self.route_controller)

        manager.start_entry("awg-terminal")
        history = manager.history_for_entry("awg-terminal")

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].state, RuntimeState.ERROR.value)
        self.assertEqual(history[0].log_path, "/tmp/awg-terminal.log")

    def test_switch_primary_keeps_single_primary_session(self) -> None:
        self._save_entry("proxy-a", ProxyType.VLESS_WS)
        self._save_entry("proxy-b", ProxyType.TROJAN)

        self.manager.start_entry("proxy-a", make_primary=True)
        self.manager.start_entry("proxy-b", make_primary=False)
        self.manager.make_primary("proxy-b")
        snapshot = self.manager.snapshot()
        session_a = self._snapshot_session("proxy-a")
        session_b = self._snapshot_session("proxy-b")

        self.assertIsNotNone(session_a)
        self.assertIsNotNone(session_b)
        assert session_a is not None
        assert session_b is not None
        self.assertFalse(session_a.is_primary)
        self.assertTrue(session_b.is_primary)
        self.assertEqual(snapshot.primary_session_id, session_b.session_id)
        self.assertEqual(self.route_controller.apply_calls, ["proxy-a", "proxy-b"])
        self.assertIn(SessionStopReason.PRIMARY_SWITCH, self.route_controller.clear_calls)

    def test_wireguard_takes_route_ownership_without_restoring_proxy(self) -> None:
        self._save_entry("proxy-main", ProxyType.VLESS_WS)
        self._save_entry("wg-main", ProxyType.WIREGUARD)

        self.manager.start_entry("proxy-main", make_primary=True)
        proxy_session = self._snapshot_session("proxy-main")
        self.manager.start_entry("wg-main")
        snapshot = self.manager.snapshot()

        self.assertIsNotNone(proxy_session)
        assert proxy_session is not None
        self.assertEqual(snapshot.route_owner_kind, RouteOwnerKind.WIREGUARD)
        self.assertEqual(snapshot.primary_session_id, proxy_session.session_id)
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.CLEAR)
        self.assertEqual(snapshot.system_proxy_entry_id, "")
        self.assertIn(SessionStopReason.ROUTE_TAKEN_BY_WIREGUARD, self.route_controller.clear_calls)

        self.manager.stop_entry("wg-main")
        after_stop = self.manager.snapshot()

        self.assertEqual(after_stop.route_owner_kind, RouteOwnerKind.NONE)
        self.assertEqual(after_stop.primary_session_id, proxy_session.session_id)
        self.assertEqual(after_stop.system_proxy_state, SystemProxyState.CLEAR)
        self.assertEqual(self.route_controller.apply_calls, ["proxy-main"])

    def test_amneziawg_takes_route_ownership_without_restoring_proxy(self) -> None:
        self._save_entry("proxy-main", ProxyType.VLESS_WS)
        self._save_entry("awg-main", ProxyType.AMNEZIAWG)

        self.manager.start_entry("proxy-main", make_primary=True)
        proxy_session = self._snapshot_session("proxy-main")
        self.manager.start_entry("awg-main")
        snapshot = self.manager.snapshot()

        self.assertIsNotNone(proxy_session)
        assert proxy_session is not None
        self.assertEqual(snapshot.route_owner_kind, RouteOwnerKind.WIREGUARD)
        self.assertEqual(snapshot.primary_session_id, proxy_session.session_id)
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.CLEAR)
        self.assertEqual(snapshot.system_proxy_entry_id, "")
        self.assertIn(SessionStopReason.ROUTE_TAKEN_BY_WIREGUARD, self.route_controller.clear_calls)

        self.manager.stop_entry("awg-main")
        after_stop = self.manager.snapshot()

        self.assertEqual(after_stop.route_owner_kind, RouteOwnerKind.NONE)
        self.assertEqual(after_stop.primary_session_id, proxy_session.session_id)
        self.assertEqual(after_stop.system_proxy_state, SystemProxyState.CLEAR)
        self.assertEqual(self.route_controller.apply_calls, ["proxy-main"])

    def test_primary_crash_clears_system_proxy_and_records_history(self) -> None:
        self._save_entry("proxy-crash", ProxyType.VLESS_WS)

        self.manager.start_entry("proxy-crash", make_primary=True)
        session = self._snapshot_session("proxy-crash")
        assert session is not None
        self.proxy_adapter.set_poll_terminal_error(session.session_id)

        self.manager.poll_sessions()
        snapshot = self.manager.snapshot()
        history = self.manager.history_for_entry("proxy-crash")

        self.assertEqual(snapshot.sessions, [])
        self.assertEqual(snapshot.primary_session_id, "")
        self.assertEqual(snapshot.system_proxy_state, SystemProxyState.CLEAR)
        self.assertIn(SessionStopReason.ENGINE_CRASH, self.route_controller.clear_calls)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].failure_reason, "runtime.error.engine_crash")

    def test_other_entry_emits_failure_and_history(self) -> None:
        failures: list[tuple[str, str]] = []
        self.manager.operationFailed.connect(lambda entry_id, reason: failures.append((entry_id, reason)))
        self._save_entry("other-1", ProxyType.OTHER)

        self.manager.start_entry("other-1")
        snapshot = self.manager.snapshot()
        history = self.manager.history_for_entry("other-1")

        self.assertEqual(snapshot.sessions, [])
        self.assertEqual(failures, [("other-1", ERROR_UNSUPPORTED_ENTRY)])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].engine_kind, RuntimeEngineKind.UNSUPPORTED.value)
        self.assertEqual(history[0].state, RuntimeState.ERROR.value)

    def test_restore_sessions_on_launch_uses_runtime_prefs(self) -> None:
        settings = self.db.load_settings()
        settings.restore_sessions_on_launch = True
        self.db.save_settings(settings)
        self._save_entry("proxy-restore", ProxyType.VLESS_WS)
        self.db.save_runtime_prefs(
            RuntimePrefs.from_dict(
                {
                    "entry_id": "proxy-restore",
                    "auto_launch": True,
                    "preferred_primary": True,
                }
            )
        )

        self.manager.restore_sessions_on_launch()
        snapshot = self.manager.snapshot()
        session = self._snapshot_session("proxy-restore")

        self.assertEqual(len(snapshot.sessions), 1)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertTrue(session.is_primary)
        self.assertEqual(snapshot.primary_session_id, session.session_id)


if __name__ == "__main__":
    unittest.main()
