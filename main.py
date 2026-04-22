from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.db import DEFAULT_DB_PATH, DatabaseInitError, DatabaseManager, harden_private_storage_paths
from app.ui.main_window import MainWindow


def backup_and_reset_database_file(db_path: Path) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = db_path.with_name(f"{db_path.stem}.backup.db")
    if db_path.exists():
        shutil.copy2(db_path, backup_path)
        harden_private_storage_paths(db_path.parent, backup_path)
        db_path.unlink(missing_ok=True)
    return backup_path


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ProxyVault")
    app.setOrganizationName("ProxyVault")

    try:
        db = DatabaseManager()
    except DatabaseInitError as exc:
        response = QMessageBox.question(
            None,
            "ProxyVault Database Error",
            "ProxyVault could not open its SQLite database.\n\n"
            "You can reset the local database now. A backup copy will be created first if possible.\n\n"
            f"Details: {exc}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response != QMessageBox.StandardButton.Yes:
            return 1
        backup_path = backup_and_reset_database_file(DEFAULT_DB_PATH)
        try:
            db = DatabaseManager()
        except DatabaseInitError as retry_exc:
            QMessageBox.critical(
                None,
                "ProxyVault Database Error",
                f"ProxyVault still could not recover the database.\n\nBackup: {backup_path}\n\nDetails: {retry_exc}",
            )
            return 1

    window = MainWindow(db)
    app.aboutToQuit.connect(db.close)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
