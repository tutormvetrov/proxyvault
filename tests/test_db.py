from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from app.db import DatabaseManager, harden_private_storage_paths
from app.models import ProxyEntry, ProxyType, ReachabilityCheck, ReachabilityState, utc_now_iso


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "proxyvault.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_save_get_and_find_entry(self) -> None:
        entry = ProxyEntry(
            id="entry-1",
            name="Reality Node",
            uri="vless://123e4567-e89b-12d3-a456-426614174000@node.example.com:443?type=ws&security=tls#Node",
            type=ProxyType.VLESS_WS,
            transport="ws+tls",
            server_host="node.example.com",
            server_port=443,
            tags="prod,edge",
            notes="Primary node",
            is_favorite=True,
        )

        self.db.save_entry(entry)
        fetched = self.db.get_entry("entry-1")
        found = self.db.find_by_uri(entry.uri)

        self.assertIsNotNone(fetched)
        self.assertIsNotNone(found)
        assert fetched is not None
        self.assertEqual(fetched.name, "Reality Node")
        self.assertEqual(fetched.server_host, "node.example.com")
        self.assertTrue(fetched.is_favorite)
        self.assertEqual(fetched.tag_list, ["prod", "edge"])
        self.assertEqual(found.id, "entry-1")
        self.assertTrue(fetched.uri_fingerprint)

    def test_record_reachability_check_persists_summary_and_history(self) -> None:
        entry = ProxyEntry(
            id="entry-2",
            name="TCP Node",
            uri="trojan://secret@trojan.example.com:443?sni=cdn.example.com#Node",
            type=ProxyType.TROJAN,
            transport="tcp+tls",
            server_host="trojan.example.com",
            server_port=443,
        )
        self.db.save_entry(entry)

        result = ReachabilityCheck(
            checked_at=utc_now_iso(),
            status=ReachabilityState.REACHABLE,
            endpoint="trojan.example.com:443",
            method="TCP probe",
            latency_ms=84,
            duration_ms=84,
            details="TCP probe succeeded.",
            config_fingerprint=entry.uri_fingerprint,
        )

        self.db.record_reachability_check(entry.id, result)
        updated = self.db.get_entry(entry.id)
        history = self.db.list_reachability_checks(entry.id)

        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.reachability_status, ReachabilityState.REACHABLE)
        self.assertEqual(updated.reachability_latency_ms, 84)
        self.assertEqual(updated.reachability_endpoint, "trojan.example.com:443")
        self.assertEqual(updated.reachability_config_fingerprint, entry.uri_fingerprint)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].status, ReachabilityState.REACHABLE)
        self.assertEqual(history[0].method, "TCP probe")

    def test_encrypted_storage_keeps_uri_ciphertext_at_rest(self) -> None:
        self.db.set_master_password("correct horse battery staple")
        entry = ProxyEntry(
            id="entry-3",
            name="Encrypted Node",
            uri="ss://YWVzLTEyOC1nY206c2VjcmV0@ss.example.com:8388#Encrypted",
            type=ProxyType.SHADOWSOCKS,
            transport="tcp",
            server_host="ss.example.com",
            server_port=8388,
        )

        self.db.save_entry(entry)
        row = self.db._connection.execute(
            "SELECT uri_plaintext, uri_encrypted, uri_nonce FROM entries WHERE id = ?",
            (entry.id,),
        ).fetchone()

        self.assertIsNotNone(row)
        assert row is not None
        self.assertIsNone(row["uri_plaintext"])
        self.assertIsNotNone(row["uri_encrypted"])
        self.assertIsNotNone(row["uri_nonce"])

        self.db.lock()
        locked_entry = self.db.get_entry(entry.id, include_uri=True)
        self.assertIsNotNone(locked_entry)
        assert locked_entry is not None
        self.assertTrue(locked_entry.is_locked)
        self.assertEqual(locked_entry.uri, "")

        self.db.unlock("correct horse battery staple")
        unlocked_entry = self.db.get_entry(entry.id, include_uri=True)
        self.assertIsNotNone(unlocked_entry)
        assert unlocked_entry is not None
        self.assertEqual(unlocked_entry.uri, entry.uri)

    def test_harden_private_storage_paths_sets_posix_modes(self) -> None:
        if os.name != "posix":
            self.skipTest("POSIX file permissions are not available on this platform.")

        app_dir = Path(self.temp_dir.name) / "portable"
        db_path = app_dir / "proxyvault.db"
        app_dir.mkdir(parents=True, exist_ok=True)
        db_path.write_text("placeholder", encoding="utf-8")

        harden_private_storage_paths(app_dir, db_path)

        self.assertEqual(stat.S_IMODE(app_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(db_path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
