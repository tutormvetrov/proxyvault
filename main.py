from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.db import DEFAULT_DB_PATH, DatabaseInitError, DatabaseManager, harden_private_storage_paths
from app.i18n import SupportedLocale, set_locale, tr
from app.runtime.bootstrap import build_runtime_manager
from app.ui.i18n_patch import ensure_ui_translations
from app.ui.main_window import MainWindow


def backup_and_reset_database_file(db_path: Path) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = db_path.with_name(f"{db_path.stem}.backup.db")
    if db_path.exists():
        shutil.copy2(db_path, backup_path)
        harden_private_storage_paths(db_path.parent, backup_path)
        db_path.unlink(missing_ok=True)
    return backup_path


def _show_database_recovery_prompt(exc: Exception) -> QMessageBox.StandardButton:
    return QMessageBox.question(
        None,
        tr("startup.database_error.title"),
        tr("startup.database_error.recovery_prompt", details=exc),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )


def _show_database_fatal_error(backup_path: Path, exc: Exception) -> None:
    QMessageBox.critical(
        None,
        tr("startup.database_error.title"),
        tr("startup.database_error.recovery_failed", backup=backup_path, details=exc),
    )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ProxyVault")
    app.setOrganizationName("ProxyVault")

    set_locale(SupportedLocale.default())
    ensure_ui_translations()

    try:
        db = DatabaseManager()
    except DatabaseInitError as exc:
        if _show_database_recovery_prompt(exc) != QMessageBox.StandardButton.Yes:
            return 1
        backup_path = backup_and_reset_database_file(DEFAULT_DB_PATH)
        try:
            db = DatabaseManager()
        except DatabaseInitError as retry_exc:
            _show_database_fatal_error(backup_path, retry_exc)
            return 1

    settings = db.load_settings()
    set_locale(SupportedLocale.coerce(settings.ui_language))
    ensure_ui_translations()

    runtime_manager = build_runtime_manager(db, settings=settings)
    window = MainWindow(db, runtime_manager=runtime_manager)

    def shutdown() -> None:
        window.shutdown()
        db.close()

    app.aboutToQuit.connect(shutdown)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
