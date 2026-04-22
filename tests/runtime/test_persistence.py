from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import DatabaseManager
from app.runtime.models import RuntimePrefs, SessionHistoryRecord
from tests.runtime.fakes import make_entry
from app.models import ProxyType


class RuntimePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "proxyvault.db"
        self.db = DatabaseManager(self.db_path)
        self.entry = make_entry("entry-runtime", ProxyType.VLESS_WS)
        self.db.save_entry(self.entry)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_runtime_tables_are_created(self) -> None:
        tables = {
            row["name"]
            for row in self.db._connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index')"
            ).fetchall()
        }

        self.assertIn("entry_runtime_prefs", tables)
        self.assertIn("session_history", tables)
        self.assertIn("idx_session_history_entry_started", tables)
        self.assertIn("idx_session_history_session_id", tables)

    def test_runtime_prefs_round_trip(self) -> None:
        prefs = RuntimePrefs(
            entry_id=self.entry.id,
            auto_launch=True,
            preferred_primary=True,
            http_port_override=18080,
            socks_port_override=11080,
            last_used_at="2026-04-22T10:00:00",
            last_error="runtime.error.sample",
        )

        self.db.save_runtime_prefs(prefs)
        loaded = self.db.load_runtime_prefs(self.entry.id)
        listed = self.db.list_runtime_prefs()

        self.assertEqual(loaded.to_dict(), prefs.to_dict())
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].entry_id, self.entry.id)

    def test_session_history_round_trip(self) -> None:
        first = SessionHistoryRecord(
            session_id="session-1",
            entry_id=self.entry.id,
            entry_name=self.entry.name,
            engine_kind="SING_BOX",
            state="RUNNING",
            primary_flag=True,
            route_owner_kind="PROXY",
            http_port=8080,
            socks_port=1080,
            pid_or_handle="1234",
            started_at="2026-04-22T10:00:00",
            stopped_at="2026-04-22T10:05:00",
            latency_ms=42,
            last_handshake_at="2026-04-22T10:04:00",
            last_activity_at="2026-04-22T10:04:30",
            exit_code=0,
            failure_reason="",
            short_log_excerpt="ok",
            log_path="C:/ProxyVault/runtime/logs/session-1.log",
        )
        second = SessionHistoryRecord(
            session_id="session-2",
            entry_id=self.entry.id,
            entry_name=self.entry.name,
            engine_kind="SING_BOX",
            state="ERROR",
            primary_flag=False,
            route_owner_kind="NONE",
            pid_or_handle="5678",
            started_at="2026-04-23T10:00:00",
            stopped_at="2026-04-23T10:01:00",
            failure_reason="runtime.error.failed",
            short_log_excerpt="boom",
            log_path="C:/ProxyVault/runtime/logs/session-2.log",
        )

        self.db.record_session_history(first)
        self.db.record_session_history(second)
        history = self.db.list_session_history(self.entry.id, limit=10)

        self.assertEqual([record.session_id for record in history], ["session-2", "session-1"])
        self.assertEqual(history[0].failure_reason, "runtime.error.failed")
        self.assertEqual(history[0].log_path, "C:/ProxyVault/runtime/logs/session-2.log")
        self.assertEqual(history[1].http_port, 8080)

    def test_clear_runtime_metadata_for_entry_removes_prefs_and_history(self) -> None:
        self.db.save_runtime_prefs(RuntimePrefs(entry_id=self.entry.id, auto_launch=True))
        self.db.record_session_history(
            SessionHistoryRecord(
                session_id="session-1",
                entry_id=self.entry.id,
                entry_name=self.entry.name,
                engine_kind="SING_BOX",
            )
        )

        self.db.clear_runtime_metadata_for_entry(self.entry.id)

        self.assertEqual(self.db.load_runtime_prefs(self.entry.id).entry_id, self.entry.id)
        self.assertEqual(self.db.list_session_history(self.entry.id), [])


if __name__ == "__main__":
    unittest.main()
