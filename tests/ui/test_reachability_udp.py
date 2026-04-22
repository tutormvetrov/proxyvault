from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from app.db import DatabaseManager
from app.i18n import tr
from app.models import ProxyEntry, ProxyType, ReachabilityCheck, ReachabilityState
from app.runtime.enums import RouteOwnerKind, RuntimeEngineKind, RuntimeState, SessionStopReason
from app.runtime.manager import RuntimeManager
from app.runtime.models import LaunchSpec, RunningSession, RuntimePrefs, SessionHistoryRecord
from app.ui.main_window import MainWindow


class FakeAmneziaAdapter:
    engine_kind = RuntimeEngineKind.AMNEZIAWG_WINDOWS

    def __init__(self) -> None:
        self.prepared_uri = ""

    def supports(self, entry: ProxyEntry) -> bool:
        return entry.type == ProxyType.AMNEZIAWG

    def prepare_launch(
        self,
        entry: ProxyEntry,
        prefs: RuntimePrefs,
        *,
        make_primary: bool,
    ) -> LaunchSpec:
        del prefs
        del make_primary
        self.prepared_uri = entry.uri
        return LaunchSpec(entry_id=entry.id, display_name=entry.name)

    def start(self, launch_spec: LaunchSpec) -> RunningSession:
        return RunningSession(
            session_id="session-awg",
            entry_id=launch_spec.entry_id,
            entry_name=launch_spec.display_name,
            engine_kind=self.engine_kind,
            runtime_state=RuntimeState.RUNNING,
            route_owner_kind=RouteOwnerKind.WIREGUARD,
            last_handshake_at="2026-04-22T12:00:00",
        )

    def stop(self, session: RunningSession, *, reason: SessionStopReason) -> RunningSession:
        del reason
        updated = RunningSession.from_dict(session.to_dict())
        updated.runtime_state = RuntimeState.DISCONNECTED
        return updated

    def poll(self, session: RunningSession) -> RunningSession:
        return RunningSession.from_dict(session.to_dict())

    def read_log_excerpt(self, session: RunningSession, max_lines: int) -> str:
        del session
        del max_lines
        return ""


class FakeHysteriaAdapter:
    engine_kind = RuntimeEngineKind.SING_BOX

    def supports(self, entry: ProxyEntry) -> bool:
        return entry.type == ProxyType.HYSTERIA2

    def prepare_launch(
        self,
        entry: ProxyEntry,
        prefs: RuntimePrefs,
        *,
        make_primary: bool,
    ) -> LaunchSpec:
        del entry
        del prefs
        del make_primary
        return LaunchSpec(entry_id="hy2-1", display_name="Hysteria2-Salama", http_port=18080)

    def start(self, launch_spec: LaunchSpec) -> RunningSession:
        return RunningSession(
            session_id="session-hy2",
            entry_id=launch_spec.entry_id,
            entry_name=launch_spec.display_name,
            engine_kind=self.engine_kind,
            runtime_state=RuntimeState.RUNNING,
            route_owner_kind=RouteOwnerKind.NONE,
            http_port=launch_spec.http_port,
            started_at="2026-04-22T12:00:00",
            last_activity_at="2026-04-22T12:00:00",
        )

    def stop(self, session: RunningSession, *, reason: SessionStopReason) -> RunningSession:
        del reason
        updated = RunningSession.from_dict(session.to_dict())
        updated.runtime_state = RuntimeState.DISCONNECTED
        return updated

    def poll(self, session: RunningSession) -> RunningSession:
        updated = RunningSession.from_dict(session.to_dict())
        updated.last_activity_at = "2026-04-22T12:00:02"
        updated.latency_ms = 145
        return updated

    def read_log_excerpt(self, session: RunningSession, max_lines: int) -> str:
        del session
        del max_lines
        return ""


class UdpReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        app = getattr(cls, "app", None)
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            widget.close()
            widget.deleteLater()
        app.processEvents()
        cls.app = None

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "proxyvault.db"
        self.db = DatabaseManager(self.db_path)
        self.windows: list[MainWindow] = []
        settings = self.db.load_settings()
        settings.has_seen_welcome = True
        self.db.save_settings(settings)

    def tearDown(self) -> None:
        for window in reversed(self.windows):
            window.close()
            window.deleteLater()
        for widget in list(self.app.topLevelWidgets()):
            widget.close()
            widget.deleteLater()
        self.app.processEvents()
        self.db.close()
        self.temp_dir.cleanup()

    def _create_window(self, *, runtime_manager: RuntimeManager | None = None) -> MainWindow:
        window = MainWindow(self.db, runtime_manager=runtime_manager, auto_show_welcome=False)
        self.windows.append(window)
        return window

    def test_amneziawg_probe_uses_runtime_handshake_check(self) -> None:
        adapter = FakeAmneziaAdapter()
        runtime_manager = RuntimeManager(self.db, adapters=[adapter])
        window = self._create_window(runtime_manager=runtime_manager)
        entry = ProxyEntry(
            id="awg-1",
            name="45.140.205.4",
            uri=(
                "[Interface]\n"
                "PrivateKey=test\n"
                "Address=10.66.66.2/32\n"
                "DNS=1.1.1.1,1.0.0.1\n"
                "Jc=5\n"
                "Jmin=50\n"
                "Jmax=1000\n"
                "H1=288474209-388474208\n"
                "H2=807868225-907868224\n"
                "H3=1129538851-1229538850\n"
                "H4=1897672324-1997672323\n"
                "\n"
                "[Peer]\n"
                "PublicKey=peer\n"
                "AllowedIPs=0.0.0.0/0,::/0\n"
                "Endpoint=45.140.205.4:51820\n"
            ),
            type=ProxyType.AMNEZIAWG,
            transport="udp",
            server_host="45.140.205.4",
            server_port=51820,
        )

        result = window._run_tcp_probe(entry)

        self.assertEqual(result.status, ReachabilityState.REACHABLE)
        self.assertIn("runtime", result.method.lower())
        self.assertIn("handshake", result.method.lower())
        self.assertIn("runtime", result.failure_reason.lower())
        self.assertIn("AllowedIPs = 0.0.0.0/0,::/0", adapter.prepared_uri)
        self.assertNotIn("DNS=", adapter.prepared_uri)
        self.assertIn("Jc = 5", adapter.prepared_uri)
        self.assertIn("Table = off", adapter.prepared_uri)
        self.assertIn("PersistentKeepalive = 5", adapter.prepared_uri)

    def test_hysteria2_probe_uses_runtime_activity_check(self) -> None:
        runtime_manager = RuntimeManager(self.db, adapters=[FakeHysteriaAdapter()])
        window = self._create_window(runtime_manager=runtime_manager)
        entry = ProxyEntry(
            id="hy2-1",
            name="Hysteria2-Salama",
            uri="hysteria2://secret@45.140.205.4:443?sni=example.com#hy2",
            type=ProxyType.HYSTERIA2,
            transport="udp+tls+salamander",
            server_host="45.140.205.4",
            server_port=443,
        )

        result = window._run_tcp_probe(entry)

        self.assertEqual(result.status, ReachabilityState.REACHABLE)
        self.assertIn("runtime", result.method.lower())
        self.assertEqual(result.latency_ms, 145)

    def test_runtime_log_payload_prefers_latest_runtime_reachability_check(self) -> None:
        entry = ProxyEntry(
            id="awg-log-priority",
            name="45.140.205.4",
            uri="[Interface]\nPrivateKey=test\n[Peer]\nEndpoint=45.140.205.4:51820\n",
            type=ProxyType.AMNEZIAWG,
            transport="udp",
            server_host="45.140.205.4",
            server_port=51820,
        )
        self.db.save_entry(entry)
        self.db.record_session_history(
            SessionHistoryRecord(
                session_id="old-session",
                entry_id=entry.id,
                entry_name=entry.name,
                engine_kind=RuntimeEngineKind.AMNEZIAWG_WINDOWS.value,
                state=RuntimeState.ERROR.value,
                failure_reason="runtime.error.wireguard.helper_not_found",
                short_log_excerpt="old stale helper_not_found excerpt",
            )
        )
        saved_entry = self.db.get_entry(entry.id)
        assert saved_entry is not None
        log_path = Path(self.temp_dir.name) / "pvawg-priority.log"
        log_path.write_text("fresh helper log for reachability check", encoding="utf-8")
        self.db.record_reachability_check(
            entry.id,
            ReachabilityCheck(
                checked_at="2026-04-22T19:28:15",
                status=ReachabilityState.FAILED,
                endpoint="45.140.205.4:51820",
                method="Runtime and Handshake",
                failure_reason="Process exited right after start.",
                error_category="process_exited_early",
                details="fresh reachability details",
                log_path=str(log_path),
                config_fingerprint=saved_entry.uri_fingerprint,
            ),
        )

        window = self._create_window()
        stored_entry = self.db.get_entry(entry.id)
        assert stored_entry is not None

        log_text, resolved_log_path, path_message = window._runtime_log_payload(stored_entry)

        self.assertEqual(log_text, "fresh helper log for reachability check")
        self.assertEqual(resolved_log_path, str(log_path))
        self.assertEqual(path_message, "")

    def test_runtime_log_payload_uses_saved_runtime_details_when_file_is_unavailable(self) -> None:
        entry = ProxyEntry(
            id="awg-log-fallback",
            name="45.140.205.4",
            uri="[Interface]\nPrivateKey=test\n[Peer]\nEndpoint=45.140.205.4:51820\n",
            type=ProxyType.AMNEZIAWG,
            transport="udp",
            server_host="45.140.205.4",
            server_port=51820,
        )
        saved_entry = self.db.save_entry(entry)
        self.db.record_reachability_check(
            entry.id,
            ReachabilityCheck(
                checked_at="2026-04-22T19:28:16",
                status=ReachabilityState.FAILED,
                endpoint="45.140.205.4:51820",
                method="Runtime и handshake",
                failure_reason="Процесс завершился сразу после запуска",
                error_category="process_exited_early",
                details="saved runtime diagnostic excerpt",
                log_path="",
                config_fingerprint=saved_entry.uri_fingerprint,
            ),
        )

        window = self._create_window()
        stored_entry = self.db.get_entry(entry.id)
        assert stored_entry is not None

        log_text, resolved_log_path, path_message = window._runtime_log_payload(stored_entry)

        self.assertEqual(log_text, "saved runtime diagnostic excerpt")
        self.assertEqual(resolved_log_path, "")
        self.assertEqual(path_message, tr("dialog.runtime_log.path_unavailable"))


if __name__ == "__main__":
    unittest.main()
