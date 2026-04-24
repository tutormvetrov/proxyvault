from __future__ import annotations

import argparse
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import DatabaseManager
from app.models import ProxyEntry, ProxyType
from tools import create_portable_seed


class CreatePortableSeedTests(unittest.TestCase):
    def test_create_seed_encrypts_profiles_and_drops_qr_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            source_db = temp_root / "source.db"
            output_dir = temp_root / "portable-seed"
            qr_dir = output_dir / "qrcodes"
            qr_dir.mkdir(parents=True)
            (qr_dir / "old.svg").write_text("secret qr", encoding="utf-8")

            db = DatabaseManager(source_db)
            db.save_entry(
                ProxyEntry(
                    id="entry-1",
                    name="Seed Node",
                    uri="trojan://secret@example.com:443#Seed",
                    type=ProxyType.TROJAN,
                    transport="tcp+tls",
                    server_host="example.com",
                    server_port=443,
                    qr_png_path=str(qr_dir / "old.svg"),
                )
            )
            db.close()

            args = argparse.Namespace(
                source_db=source_db,
                output_dir=output_dir,
                password="long seed password",
                current_password="",
                force=True,
                from_git_head=False,
            )

            target_db = create_portable_seed.create_seed(args)

            self.assertEqual(target_db, output_dir / "proxyvault.db")
            self.assertFalse(qr_dir.exists())

            seed_db = DatabaseManager(target_db)
            try:
                self.assertTrue(seed_db.has_master_password())
                row = seed_db._connection.execute(
                    "SELECT uri_plaintext, qr_png_path FROM entries WHERE id = ?",
                    ("entry-1",),
                ).fetchone()
                self.assertIsNotNone(row)
                assert row is not None
                self.assertIsNone(row["uri_plaintext"])
                self.assertEqual(row["qr_png_path"], "")

                seed_db.unlock("long seed password")
                entry = seed_db.get_entry("entry-1", include_uri=True)
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertEqual(entry.uri, "trojan://secret@example.com:443#Seed")
            finally:
                seed_db.close()

    def test_create_seed_can_use_database_from_git_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            source_db = temp_root / "source.db"
            output_dir = temp_root / "portable-seed"

            db = DatabaseManager(source_db)
            db.save_entry(
                ProxyEntry(
                    id="entry-1",
                    name="Git Seed Node",
                    uri="trojan://secret@example.com:443#GitSeed",
                    type=ProxyType.TROJAN,
                    transport="tcp+tls",
                    server_host="example.com",
                    server_port=443,
                )
            )
            db.close()

            args = argparse.Namespace(
                source_db=temp_root / "unused.db",
                output_dir=output_dir,
                password="long seed password",
                current_password="",
                force=True,
                from_git_head=True,
            )
            completed = subprocess.CompletedProcess(
                args=["git"],
                returncode=0,
                stdout=source_db.read_bytes(),
                stderr=b"",
            )

            with patch.object(create_portable_seed.subprocess, "run", return_value=completed):
                target_db = create_portable_seed.create_seed(args)

            seed_db = DatabaseManager(target_db)
            try:
                seed_db.unlock("long seed password")
                entry = seed_db.get_entry("entry-1", include_uri=True)
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertEqual(entry.uri, "trojan://secret@example.com:443#GitSeed")
            finally:
                seed_db.close()


if __name__ == "__main__":
    unittest.main()
