from __future__ import annotations

import platform
from pathlib import Path

from app.db import DatabaseManager
from app.models import AppSettings
from app.runtime.adapters.amneziawg_macos import AmneziaWGAdapterMacOS
from app.runtime.adapters.amneziawg_windows import AmneziaWGAdapterWindows
from app.runtime.adapters.sing_box import SingBoxAdapter
from app.runtime.adapters.wireguard_macos import WireGuardAdapterMacOS
from app.runtime.adapters.wireguard_windows import WireGuardAdapterWindows
from app.runtime.amneziawg_macos_support import AmneziaWGMacOSAssetLocator
from app.runtime.amneziawg_windows_support import AmneziaWGWindowsAssetLocator
from app.runtime.manager import RuntimeManager
from app.runtime.routing.macos import MacOSSystemProxyBackend
from app.runtime.routing.system_proxy import NoopSystemProxyController, SubprocessCommandRunner, SystemProxyController
from app.runtime.routing.windows import WindowsSystemProxyBackend
from app.runtime.wireguard_macos_support import WireGuardMacOSAssetLocator
from app.runtime.wireguard_windows_support import WireGuardWindowsAssetLocator


def _platform_system(platform_name: str | None = None) -> str:
    value = (platform_name or platform.system()).strip().lower()
    if value.startswith("win"):
        return "Windows"
    if value in {"darwin", "macos", "mac"}:
        return "Darwin"
    if value.startswith("linux"):
        return "Linux"
    return platform_name or platform.system()


def _engine_root(settings: AppSettings) -> Path:
    configured = str(settings.engine_root_dir or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(AppSettings.default().engine_root_dir).expanduser()


def build_runtime_manager(
    db: DatabaseManager,
    *,
    settings: AppSettings | None = None,
    platform_name: str | None = None,
) -> RuntimeManager:
    resolved_settings = settings or db.load_settings()
    engine_root_dir = _engine_root(resolved_settings)
    system_name = _platform_system(platform_name)

    adapters = [
        SingBoxAdapter(
            engine_root_dir=engine_root_dir,
            platform_name=system_name,
        )
    ]
    if system_name == "Windows":
        adapters.append(
            WireGuardAdapterWindows(
                platform_name=system_name,
                asset_locator=WireGuardWindowsAssetLocator(engine_root_dir=engine_root_dir),
            )
        )
        adapters.append(
            AmneziaWGAdapterWindows(
                platform_name=system_name,
                asset_locator=AmneziaWGWindowsAssetLocator(engine_root_dir=engine_root_dir),
            )
        )
        route_controller = SystemProxyController(WindowsSystemProxyBackend(SubprocessCommandRunner()))
    elif system_name == "Darwin":
        adapters.append(
            WireGuardAdapterMacOS(
                platform_name=system_name,
                asset_locator=WireGuardMacOSAssetLocator(engine_root_dir=engine_root_dir),
            )
        )
        adapters.append(
            AmneziaWGAdapterMacOS(
                platform_name=system_name,
                asset_locator=AmneziaWGMacOSAssetLocator(engine_root_dir=engine_root_dir),
            )
        )
        route_controller = SystemProxyController(MacOSSystemProxyBackend(SubprocessCommandRunner()))
    else:
        route_controller = NoopSystemProxyController()

    return RuntimeManager(
        db,
        adapters=adapters,
        route_controller=route_controller,
    )
