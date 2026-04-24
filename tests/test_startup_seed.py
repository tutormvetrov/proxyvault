from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from app.db import DatabaseManager
from app.paths import DB_FILENAME


class StartupSeedTests(unittest.TestCase):
    def test_first_launch_can_start_empty_without_copying_seed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / DB_FILENAME

            with (
                patch.object(main, "_bundled_seed_database_exists", return_value=True),
                patch.object(main, "_show_first_launch_seed_prompt", return_value=False),
            ):
                prepared = main.prepare_first_launch_storage(db_path)

            self.assertTrue(prepared)
            self.assertTrue(db_path.parent.exists())
            self.assertFalse(db_path.exists())

    def test_empty_database_copies_seed_when_preinstalled_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / DB_FILENAME

            def seed_copy(app_dir: Path) -> Path:
                app_dir.mkdir(parents=True, exist_ok=True)
                seeded = DatabaseManager(app_dir / DB_FILENAME)
                seeded.close()
                return app_dir

            with (
                patch.object(main, "_bundled_seed_database_exists", return_value=True),
                patch.object(main, "_show_first_launch_seed_prompt", return_value=True),
                patch.object(main, "seed_app_dir_from_bundle", side_effect=seed_copy),
            ):
                db = DatabaseManager(db_path)
                seeded_db = main.install_preinstalled_seed_if_available(db)

            self.assertIsNotNone(seeded_db)
            assert seeded_db is not None
            seeded_db.close()
            self.assertTrue(db_path.exists())

    def test_empty_database_remembers_own_config_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / DB_FILENAME
            db = DatabaseManager(db_path)

            with (
                patch.object(main, "_bundled_seed_database_exists", return_value=True),
                patch.object(main, "_show_first_launch_seed_prompt", return_value=False),
            ):
                same_db = main.install_preinstalled_seed_if_available(db)

            self.assertIs(same_db, db)
            self.assertEqual(db.get_metadata(main.SEED_CHOICE_METADATA_KEY), "own")
            db.close()

    def test_startup_unlock_uses_cached_password_without_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / DB_FILENAME
            db = DatabaseManager(db_path)
            db.set_master_password("seed password")
            db.close()

            db = DatabaseManager(db_path)
            with (
                patch.object(main, "_load_cached_startup_password", return_value="seed password"),
                patch.object(main, "PasswordDialog") as dialog_class,
            ):
                unlocked = main.unlock_database_on_startup(db)

            self.assertTrue(unlocked)
            self.assertFalse(db.is_locked)
            dialog_class.assert_not_called()
            db.close()

    def test_startup_unlock_saves_password_after_prompt(self) -> None:
        class FakePasswordDialog:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def exec(self) -> bool:
                return True

            @property
            def password(self) -> str:
                return "seed password"

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / DB_FILENAME
            db = DatabaseManager(db_path)
            db.set_master_password("seed password")
            db.close()

            db = DatabaseManager(db_path)
            with (
                patch.object(main, "_load_cached_startup_password", return_value=""),
                patch.object(main, "_save_cached_startup_password") as save_cached,
                patch.object(main, "PasswordDialog", FakePasswordDialog),
            ):
                unlocked = main.unlock_database_on_startup(db)

            self.assertTrue(unlocked)
            self.assertFalse(db.is_locked)
            save_cached.assert_called_once_with(db, "seed password")
            db.close()


if __name__ == "__main__":
    unittest.main()
