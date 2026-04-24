from __future__ import annotations

import base64
import shutil
import sys
import subprocess
from pathlib import Path


def _bootstrap_dev_runtime() -> None:
    if getattr(sys, "frozen", False):
        return
    try:
        from importlib.util import find_spec

        if find_spec("PyQt6") is not None:
            return
    except Exception:
        pass

    root = Path(__file__).resolve().parent
    if sys.platform.startswith("win"):
        venv_python = root / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = root / ".venv" / "bin" / "python"

    if not venv_python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(root / ".venv")], check=True)

    deps_check = subprocess.run(
        [str(venv_python), "-c", "import PyQt6, qrcode, PIL, cryptography, requests, yaml"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if deps_check.returncode != 0:
        subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(root / "requirements.txt")], check=True)

    if Path(sys.executable).resolve() != venv_python.resolve():
        raise SystemExit(subprocess.run([str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]]).returncode)


if __name__ == "__main__":
    try:
        _bootstrap_dev_runtime()
    except Exception as exc:
        print("")
        print("ProxyVault startup bootstrap failed:")
        print(exc)
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to close this window")
        raise SystemExit(1)

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.db import (
    DEFAULT_DB_PATH,
    AuthenticationError,
    DatabaseInitError,
    DatabaseManager,
    harden_private_storage_paths,
)
from app.i18n import SupportedLocale, format_ui_error, set_locale, tr
from app.paths import DB_FILENAME, bundled_portable_seed_dir, seed_app_dir_from_bundle
from app.runtime.bootstrap import build_runtime_manager
from app.ui.dialogs import PasswordDialog
from app.ui.i18n_patch import ensure_ui_translations
from app.ui.main_window import MainWindow


SEED_CHOICE_METADATA_KEY = "startup_seed_choice"
STARTUP_UNLOCK_CACHE_METADATA_KEY = "startup_unlock_cache_v1"


def _windows_dpapi_protect(data: bytes) -> str:
    if not sys.platform.startswith("win"):
        return ""
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DataBlob(
        len(data),
        ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    output_blob = DataBlob()
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "ProxyVault startup unlock",
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        return ""
    try:
        protected = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return "dpapi:" + base64.b64encode(protected).decode("ascii")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _windows_dpapi_unprotect(value: str) -> str:
    if not sys.platform.startswith("win") or not value.startswith("dpapi:"):
        return ""
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    try:
        protected = base64.b64decode(value.removeprefix("dpapi:").encode("ascii"), validate=True)
    except ValueError:
        return ""

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    input_buffer = ctypes.create_string_buffer(protected)
    input_blob = DataBlob(
        len(protected),
        ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    output_blob = DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(output_blob),
    ):
        return ""
    try:
        password = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return password.decode("utf-8")
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _load_cached_startup_password(db: DatabaseManager) -> str:
    return _windows_dpapi_unprotect(db.get_metadata(STARTUP_UNLOCK_CACHE_METADATA_KEY))


def _save_cached_startup_password(db: DatabaseManager, password: str) -> None:
    protected = _windows_dpapi_protect(password.encode("utf-8"))
    if protected:
        db.set_metadata(STARTUP_UNLOCK_CACHE_METADATA_KEY, protected)


def _clear_cached_startup_password(db: DatabaseManager) -> None:
    if db.get_metadata(STARTUP_UNLOCK_CACHE_METADATA_KEY):
        db.set_metadata(STARTUP_UNLOCK_CACHE_METADATA_KEY, "")


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


def _bundled_seed_database_exists() -> bool:
    seed_dir = bundled_portable_seed_dir()
    return bool(seed_dir and (seed_dir / DB_FILENAME).exists())


def _show_first_launch_seed_prompt() -> bool | None:
    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(tr("startup.seed_choice.title"))
    box.setText(tr("startup.seed_choice.body"))
    preinstalled_button = box.addButton(
        tr("startup.seed_choice.use_preinstalled"),
        QMessageBox.ButtonRole.AcceptRole,
    )
    own_button = box.addButton(
        tr("startup.seed_choice.use_own"),
        QMessageBox.ButtonRole.NoRole,
    )
    cancel_button = box.addButton(tr("common.cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(preinstalled_button)
    box.exec()

    clicked = box.clickedButton()
    if clicked == preinstalled_button:
        return True
    if clicked == own_button:
        return False
    if clicked == cancel_button:
        return None
    return None


def prepare_first_launch_storage(db_path: Path = DEFAULT_DB_PATH) -> bool:
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        QMessageBox.critical(
            None,
            tr("startup.database_error.title"),
            tr("startup.database_error.recovery_failed", backup=db_path.parent, details="Cannot create storage folder."),
        )
        return False


def install_preinstalled_seed_if_available(db: DatabaseManager) -> DatabaseManager | None:
    if not _bundled_seed_database_exists():
        return db
    if db.list_entries(include_uri=False):
        return db
    if db.get_metadata(SEED_CHOICE_METADATA_KEY) == "own":
        return db

    use_preinstalled = _show_first_launch_seed_prompt()
    if use_preinstalled is None:
        return None
    if not use_preinstalled:
        db.set_metadata(SEED_CHOICE_METADATA_KEY, "own")
        return db

    db_path = db.db_path
    backup_path = db_path.with_name(f"{db_path.stem}.empty-before-seed.db")
    db.close()
    if db_path.exists():
        shutil.copy2(db_path, backup_path)
        harden_private_storage_paths(db_path.parent, backup_path)
        db_path.unlink(missing_ok=True)
    seed_app_dir_from_bundle(db_path.parent)
    if not db_path.exists():
        QMessageBox.critical(
            None,
            tr("startup.seed_choice.copy_failed_title"),
            tr("startup.seed_choice.copy_failed_body"),
        )
        return None
    return DatabaseManager(db_path)


def unlock_database_on_startup(db: DatabaseManager) -> bool:
    if not db.has_master_password() or not db.is_locked:
        return True

    cached_password = _load_cached_startup_password(db)
    if cached_password:
        try:
            db.unlock(cached_password)
            return True
        except AuthenticationError:
            _clear_cached_startup_password(db)

    while db.is_locked:
        dialog = PasswordDialog(
            tr("startup.seed_password.title"),
            ask_current=False,
            confirm_new=False,
            parent=None,
        )
        if not dialog.exec():
            return False
        try:
            db.unlock(dialog.password)
            _save_cached_startup_password(db, dialog.password)
        except AuthenticationError as exc:
            QMessageBox.warning(None, tr("action.unlock"), format_ui_error("ui.error.unlock_failed", detail=exc))
            continue
    return True


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ProxyVault")
    app.setOrganizationName("ProxyVault")

    set_locale(SupportedLocale.default())
    ensure_ui_translations()

    if not prepare_first_launch_storage(DEFAULT_DB_PATH):
        return 1

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

    db = install_preinstalled_seed_if_available(db)
    if db is None:
        return 1

    if not unlock_database_on_startup(db):
        db.close()
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
