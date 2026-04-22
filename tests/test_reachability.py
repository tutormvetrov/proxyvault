from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from app.models import ProxyEntry, ProxyType, ReachabilityState


def build_entry(**overrides) -> ProxyEntry:
    payload = {
        "id": "entry-1",
        "name": "Reachability Node",
        "uri": "vless://123e4567-e89b-12d3-a456-426614174000@edge.example.com:443?type=ws&security=tls#Node",
        "type": ProxyType.VLESS_WS,
        "transport": "ws+tls",
        "server_host": "edge.example.com",
        "server_port": 443,
        "uri_fingerprint": "fingerprint-current",
        "reachability_status": ReachabilityState.REACHABLE,
        "reachability_checked_at": datetime.utcnow().isoformat(),
        "reachability_latency_ms": 92,
        "reachability_duration_ms": 92,
        "reachability_method": "TCP probe",
        "reachability_endpoint": "edge.example.com:443",
        "reachability_config_fingerprint": "fingerprint-current",
    }
    payload.update(overrides)
    return ProxyEntry(**payload)


class ReachabilityModelTests(unittest.TestCase):
    def test_fresh_reachable_state_has_success_tone(self) -> None:
        entry = build_entry()

        self.assertTrue(entry.reachability_has_result)
        self.assertFalse(entry.reachability_is_stale)
        self.assertEqual(entry.reachability_display_state, "reachable")
        self.assertEqual(entry.reachability_tone, "success")
        self.assertEqual(entry.reachability_card_label, "Reachable · 92 ms")
        self.assertEqual(entry.reachability_freshness_label, "Fresh result")

    def test_old_probe_becomes_stale(self) -> None:
        stale_time = (datetime.utcnow() - timedelta(hours=13)).isoformat()
        entry = build_entry(reachability_checked_at=stale_time)

        self.assertTrue(entry.reachability_is_stale)
        self.assertEqual(entry.reachability_display_state, "stale")
        self.assertEqual(entry.reachability_tone, "warning")
        self.assertEqual(entry.reachability_freshness_label, "Stale result")
        self.assertEqual(entry.reachability_card_label, "Stale · 92 ms")

    def test_config_change_marks_result_stale_even_if_recent(self) -> None:
        entry = build_entry(reachability_config_fingerprint="fingerprint-old")

        self.assertTrue(entry.reachability_is_config_changed)
        self.assertTrue(entry.reachability_is_stale)
        self.assertEqual(entry.reachability_freshness_label, "Needs recheck after config change")
        self.assertIn("configuration changed", entry.reachability_detail_summary.lower())


if __name__ == "__main__":
    unittest.main()
