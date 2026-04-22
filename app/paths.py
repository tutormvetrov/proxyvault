from __future__ import annotations

import shutil
import sys
from pathlib import Path


APP_NAME = "ProxyVault"
PORTABLE_MARKER_NAME = "proxyvault.portable"
DB_FILENAME = "proxyvault.db"
QR_DIRNAME = "qrcodes"
BUNDLED_PORTABLE_SEED_DIRNAME = "portable-seed"
HOME_APP_DIR = Path.home() / APP_NAME


def portable_root_candidates(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> list[Path]:
    frozen_state = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen_state:
        return []
    exe_path = Path(executable_path or sys.executable).resolve()
    candidates: list[Path] = [exe_path.parent]
    for parent in exe_path.parents:
        if parent.suffix.lower() == ".app":
            candidates.append(parent.parent)
            break
    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)
    return unique_candidates


def detect_portable_app_dir(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path | None:
    for candidate in portable_root_candidates(executable_path=executable_path, frozen=frozen):
        marker_path = candidate / PORTABLE_MARKER_NAME
        db_path = candidate / DB_FILENAME
        if marker_path.exists() or db_path.exists():
            return candidate
    return None


def bundled_portable_seed_dir(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path | None:
    frozen_state = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen_state:
        return None
    exe_path = Path(executable_path or sys.executable).resolve()
    for parent in exe_path.parents:
        if parent.name != "MacOS":
            continue
        contents_dir = parent.parent
        if contents_dir.name != "Contents":
            continue
        return contents_dir / "Resources" / BUNDLED_PORTABLE_SEED_DIRNAME
    return None


def seed_home_app_dir_from_bundle(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path | None:
    seed_dir = bundled_portable_seed_dir(executable_path=executable_path, frozen=frozen)
    if seed_dir is None or not seed_dir.exists():
        return None

    db_source = seed_dir / DB_FILENAME
    qr_source = seed_dir / QR_DIRNAME
    if not db_source.exists() and not qr_source.exists():
        return None

    try:
        HOME_APP_DIR.mkdir(parents=True, exist_ok=True)
        db_target = HOME_APP_DIR / DB_FILENAME
        qr_target = HOME_APP_DIR / QR_DIRNAME
        if db_source.exists() and not db_target.exists():
            shutil.copy2(db_source, db_target)
        if qr_source.exists() and not qr_target.exists():
            shutil.copytree(qr_source, qr_target)
    except OSError:
        return HOME_APP_DIR
    return HOME_APP_DIR


def resolve_app_dir(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path:
    portable_dir = detect_portable_app_dir(executable_path=executable_path, frozen=frozen)
    if portable_dir is not None:
        return portable_dir
    seeded_home_dir = seed_home_app_dir_from_bundle(executable_path=executable_path, frozen=frozen)
    if seeded_home_dir is not None:
        return seeded_home_dir
    return HOME_APP_DIR


def default_db_path(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path:
    return resolve_app_dir(executable_path=executable_path, frozen=frozen) / DB_FILENAME


def default_qr_output_dir(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path:
    return resolve_app_dir(executable_path=executable_path, frozen=frozen) / QR_DIRNAME


def is_portable_runtime(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> bool:
    return detect_portable_app_dir(executable_path=executable_path, frozen=frozen) is not None
