from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.runtime.enums import RuntimeState
from app.runtime.health import apply_health_to_session, extract_health_signals
from app.runtime.logs import read_log_excerpt
from app.runtime.models import RunningSession


class LogsAndHealthTests(unittest.TestCase):
    def test_read_log_excerpt_returns_last_lines_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "sing-box.log"
            log_path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

            excerpt = read_log_excerpt(log_path, max_lines=2)

        self.assertEqual(excerpt, "three\nfour")

    def test_extract_health_signals_parses_activity_handshake_latency_and_error(self) -> None:
        log_text = "\n".join(
            [
                "+0000 2026-04-22 10:00:00 INFO sing-box started (0.00s)",
                "+0000 2026-04-22 10:00:03 INFO [2222 48ms] outbound/vless[proxy-out]: outbound connection to example.com:443",
                "+0000 2026-04-22 10:00:05 INFO [3333 51ms] outbound/vless[proxy-out]: REALITY handshake completed",
                "+0000 2026-04-22 10:00:08 ERROR outbound/vless[proxy-out]: connection refused",
            ]
        )

        signals = extract_health_signals(log_text)

        self.assertTrue(signals.started)
        self.assertEqual(signals.last_activity_at, "2026-04-22T10:00:08")
        self.assertEqual(signals.last_handshake_at, "2026-04-22T10:00:05")
        self.assertEqual(signals.latency_ms, 51)
        self.assertEqual(signals.failure_reason, "runtime.error.server_unreachable")
        self.assertIn("connection refused", signals.last_error)

    def test_apply_health_to_session_marks_exit_code_failure(self) -> None:
        session = RunningSession(
            session_id="session-1",
            runtime_state=RuntimeState.STARTING,
            started_at="2026-04-22T10:00:00",
        )
        log_text = "+0000 2026-04-22 10:00:04 ERROR outbound/trojan[proxy-out]: authentication failed"

        updated = apply_health_to_session(session, log_text=log_text, exit_code=1)

        self.assertEqual(updated.runtime_state, RuntimeState.ERROR)
        self.assertEqual(updated.failure_reason, "runtime.error.authentication_failed")
        self.assertEqual(updated.exit_code, 1)
        self.assertEqual(updated.stopped_at, "2026-04-22T10:00:04")


if __name__ == "__main__":
    unittest.main()
