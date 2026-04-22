from __future__ import annotations

from pathlib import Path

from app.runtime.paths import default_engine_root_dir, runtime_generated_dir, runtime_logs_dir
from app.runtime.wireguard_support import (
    WIREGUARD_FAILURE_HELPER_NOT_FOUND,
    WireGuardAdapterError,
    WireGuardRuntimeAssets,
)


class WireGuardMacOSAssetLocator:
    def __init__(
        self,
        *,
        helper_path: Path | str | None = None,
        engine_root_dir: Path | str | None = None,
        generated_dir: Path | str | None = None,
        logs_dir: Path | str | None = None,
    ) -> None:
        self._helper_path = Path(helper_path) if helper_path is not None else None
        self._engine_root_dir = Path(engine_root_dir) if engine_root_dir is not None else default_engine_root_dir()
        self._generated_dir = (
            Path(generated_dir) if generated_dir is not None else runtime_generated_dir() / "wireguard" / "macos"
        )
        self._logs_dir = Path(logs_dir) if logs_dir is not None else runtime_logs_dir() / "wireguard" / "macos"

    def locate(self) -> WireGuardRuntimeAssets:
        helper_path = self._helper_path or (
            self._engine_root_dir / "wireguard" / "macos" / "proxyvault-wireguard-macos"
        )
        if not helper_path.exists():
            raise WireGuardAdapterError(
                WIREGUARD_FAILURE_HELPER_NOT_FOUND,
                last_error=f"WireGuard macOS helper was not found at {helper_path}.",
                log_excerpt=f"WireGuard macOS helper was not found at {helper_path}.",
            )
        self._generated_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)
        return WireGuardRuntimeAssets(
            helper_path=helper_path,
            generated_dir=self._generated_dir,
            logs_dir=self._logs_dir,
        )
