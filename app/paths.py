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


def repo_root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


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
        seed_dir = repo_root_dir() / BUNDLED_PORTABLE_SEED_DIRNAME
        return seed_dir if seed_dir.exists() else None
    exe_path = Path(executable_path or sys.executable).resolve()
    for candidate in (
        exe_path.parent / BUNDLED_PORTABLE_SEED_DIRNAME,
        exe_path.parent / "_internal" / BUNDLED_PORTABLE_SEED_DIRNAME,
    ):
        if candidate.exists():
            return candidate
    for parent in exe_path.parents:
        if parent.name != "MacOS":
            continue
        contents_dir = parent.parent
        if contents_dir.name != "Contents":
            continue
        return contents_dir / "Resources" / BUNDLED_PORTABLE_SEED_DIRNAME
    return None


def seed_app_dir_from_bundle(
    app_dir: Path,
    *,
    executable_path: Path | str | None = None,
    frozen: bool | None = None,
) -> Path | None:
    seed_dir = bundled_portable_seed_dir(executable_path=executable_path, frozen=frozen)
    if seed_dir is None or not seed_dir.exists():
        return None

    db_source = seed_dir / DB_FILENAME
    if not db_source.exists():
        return None

    try:
        app_dir.mkdir(parents=True, exist_ok=True)
        db_target = app_dir / DB_FILENAME
        if db_source.exists() and not db_target.exists():
            shutil.copy2(db_source, db_target)
    except OSError:
        return app_dir
    return app_dir


def seed_home_app_dir_from_bundle(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path | None:
    frozen_state = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen_state:
        return None
    return seed_app_dir_from_bundle(HOME_APP_DIR, executable_path=executable_path, frozen=frozen)


def resolve_app_dir(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path:
    portable_dir = detect_portable_app_dir(executable_path=executable_path, frozen=frozen)
    if portable_dir is not None:
        return portable_dir
    return HOME_APP_DIR


def resolve_app_dir_with_seed(*, executable_path: Path | str | None = None, frozen: bool | None = None) -> Path:
    portable_dir = detect_portable_app_dir(executable_path=executable_path, frozen=frozen)
    if portable_dir is not None:
        seed_app_dir_from_bundle(portable_dir, executable_path=executable_path, frozen=frozen)
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
