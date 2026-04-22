from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.db import DatabaseManager
from app.models import AppSettings, QROptions


class RuntimeSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "proxyvault.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_load_settings_from_legacy_payload_adds_runtime_defaults(self) -> None:
        legacy_payload = {
            "output_folder": self.temp_dir.name,
            "default_qr": {"error_correction": "H", "version": 4, "box_size": 8, "border": 2},
            "theme": "dark",
            "subscription_refresh_interval": "daily",
            "allow_insecure_subscription_http": True,
            "has_seen_welcome": True,
        }
        self.db._set_setting("app_settings", json.dumps(legacy_payload))

        settings = self.db.load_settings()

        self.assertEqual(settings.output_folder, self.temp_dir.name)
        self.assertTrue(settings.client_mode_enabled)
        self.assertFalse(settings.restore_sessions_on_launch)
        self.assertTrue(settings.clear_system_proxy_on_exit)
        self.assertFalse(settings.minimize_to_tray)
        self.assertFalse(settings.auto_reconnect_enabled)
        self.assertEqual(settings.log_retention_lines, 400)
        self.assertTrue(settings.engine_root_dir)
        self.assertEqual(settings.ui_language, "ru")

    def test_app_settings_round_trip_includes_runtime_fields(self) -> None:
        settings = AppSettings(
            output_folder=self.temp_dir.name,
            default_qr=QROptions(box_size=6),
            theme="light",
            subscription_refresh_interval="weekly",
            allow_insecure_subscription_http=True,
            has_seen_welcome=True,
            client_mode_enabled=False,
            restore_sessions_on_launch=True,
            clear_system_proxy_on_exit=False,
            minimize_to_tray=True,
            auto_reconnect_enabled=True,
            log_retention_lines=250,
            engine_root_dir=str(Path(self.temp_dir.name) / "engines"),
            ui_language="en",
        )

        self.db.save_settings(settings)
        loaded = self.db.load_settings()

        self.assertEqual(loaded.to_dict(), settings.to_dict())


if __name__ == "__main__":
    unittest.main()
