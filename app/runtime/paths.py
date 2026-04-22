from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.paths import resolve_app_dir


RUNTIME_DIRNAME = "runtime"
GENERATED_DIRNAME = "generated"
LOGS_DIRNAME = "logs"
ENGINES_DIRNAME = "engines"
SING_BOX_DIRNAME = "sing-box"


@dataclass(frozen=True, slots=True)
class SingBoxAssetLayout:
    engine_root: Path
    platform_name: str
    binary_path: Path
    support_files: tuple[Path, ...] = ()

    @property
    def binary_dir(self) -> Path:
        return self.binary_path.parent


def runtime_root_dir() -> Path:
    return resolve_app_dir() / RUNTIME_DIRNAME


def runtime_generated_dir() -> Path:
    return runtime_root_dir() / GENERATED_DIRNAME


def runtime_logs_dir() -> Path:
    return runtime_root_dir() / LOGS_DIRNAME


def _current_platform_name(platform_name: str | None = None) -> str:
    normalized = (platform_name or sys.platform).lower()
    if normalized.startswith("win"):
        return "windows"
    if normalized == "darwin":
        return "macos"
    if normalized.startswith("linux"):
        return "linux"
    return normalized


def _repo_root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _frozen_executable_path(
    *,
    executable_path: Path | str | None = None,
    frozen: bool | None = None,
) -> Path | None:
    frozen_state = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen_state:
        return None
    return Path(executable_path or sys.executable).resolve()


def default_engine_root_candidates(
    *,
    executable_path: Path | str | None = None,
    frozen: bool | None = None,
) -> list[Path]:
    executable = _frozen_executable_path(executable_path=executable_path, frozen=frozen)
    candidates: list[Path] = []
    if executable is not None:
        candidates.append(executable.parent / ENGINES_DIRNAME)
        candidates.append(executable.parent / "_internal" / ENGINES_DIRNAME)
        for parent in executable.parents:
            if parent.name != "Contents":
                continue
            candidates.insert(0, parent / "Resources" / ENGINES_DIRNAME)
            app_bundle_dir = parent.parent
            if app_bundle_dir.suffix.lower() == ".app":
                candidates.append(app_bundle_dir.parent / ENGINES_DIRNAME)
            else:
                candidates.append(app_bundle_dir / ENGINES_DIRNAME)
            break
    else:
        candidates.extend(
            [
                _repo_root_dir() / ENGINES_DIRNAME,
                resolve_app_dir() / ENGINES_DIRNAME,
            ]
        )

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)
    return unique_candidates


def default_engine_root_dir(
    *,
    executable_path: Path | str | None = None,
    frozen: bool | None = None,
) -> Path:
    candidates = default_engine_root_candidates(executable_path=executable_path, frozen=frozen)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def sing_box_binary_name(platform_name: str | None = None) -> str:
    if _current_platform_name(platform_name) == "windows":
        return "sing-box.exe"
    return "sing-box"


def sing_box_support_asset_names(platform_name: str | None = None) -> tuple[str, ...]:
    platform_key = _current_platform_name(platform_name)
    if platform_key == "windows":
        return ("libcronet.dll",)
    if platform_key == "linux":
        return ("libcronet.so",)
    return ()


def sing_box_binary_candidates(
    *,
    engine_root_dir: Path | str | None = None,
    platform_name: str | None = None,
) -> list[Path]:
    engine_root = Path(engine_root_dir) if engine_root_dir is not None else default_engine_root_dir()
    platform_key = _current_platform_name(platform_name)
    binary_name = sing_box_binary_name(platform_key)
    candidates = [
        engine_root / SING_BOX_DIRNAME / platform_key / binary_name,
        engine_root / platform_key / binary_name,
        engine_root / binary_name,
    ]
    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)
    return unique_candidates


def _support_asset_candidates(
    asset_name: str,
    *,
    engine_root_dir: Path | str | None = None,
    platform_name: str | None = None,
) -> list[Path]:
    candidates = sing_box_binary_candidates(
        engine_root_dir=engine_root_dir,
        platform_name=platform_name,
    )
    engine_root = Path(engine_root_dir) if engine_root_dir is not None else default_engine_root_dir()
    platform_key = _current_platform_name(platform_name)
    roots: list[Path] = [candidate.parent for candidate in candidates]
    roots.extend(
        [
            engine_root / SING_BOX_DIRNAME / platform_key,
            engine_root / platform_key,
            engine_root,
        ]
    )
    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_roots.append(root)
    return [root / asset_name for root in unique_roots]


def _pick_existing_path(candidates: Iterable[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_sing_box_asset_layout(
    *,
    engine_root_dir: Path | str | None = None,
    platform_name: str | None = None,
    required_support_files: Iterable[str] | None = None,
) -> SingBoxAssetLayout:
    engine_root = Path(engine_root_dir) if engine_root_dir is not None else default_engine_root_dir()
    platform_key = _current_platform_name(platform_name)
    binary_path = _pick_existing_path(
        sing_box_binary_candidates(engine_root_dir=engine_root, platform_name=platform_key)
    )
    if binary_path is None:
        searched = ", ".join(
            str(path)
            for path in sing_box_binary_candidates(
                engine_root_dir=engine_root,
                platform_name=platform_key,
            )
        )
        raise FileNotFoundError(f"Bundled sing-box binary was not found. Searched: {searched}")

    support_files: list[Path] = []
    for asset_name in required_support_files or ():
        asset_path = _pick_existing_path(
            _support_asset_candidates(
                asset_name,
                engine_root_dir=engine_root,
                platform_name=platform_key,
            )
        )
        if asset_path is None:
            raise FileNotFoundError(
                f"Required sing-box runtime asset '{asset_name}' was not found under {engine_root}"
            )
        support_files.append(asset_path)

    return SingBoxAssetLayout(
        engine_root=engine_root,
        platform_name=platform_key,
        binary_path=binary_path,
        support_files=tuple(support_files),
    )


def ensure_runtime_dirs() -> dict[str, Path]:
    directories = {
        "runtime_root": runtime_root_dir(),
        "generated": runtime_generated_dir(),
        "logs": runtime_logs_dir(),
        "engines": default_engine_root_dir(),
    }
    for key in ("runtime_root", "generated", "logs"):
        path = directories[key]
        path.mkdir(parents=True, exist_ok=True)
    return directories
