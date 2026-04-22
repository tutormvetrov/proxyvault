from __future__ import annotations

from app.runtime.enums import RuntimeEngineKind
from app.runtime.wireguard_support import (
    WIREGUARD_WARNING_SYSTEM_PROMPT,
    WIREGUARD_WARNING_WINDOWS_ELEVATION,
    WireGuardAdapterBase,
    WireGuardCommandRunner,
)
from app.runtime.wireguard_windows_support import WireGuardWindowsAssetLocator


class WireGuardAdapterWindows(WireGuardAdapterBase):
    engine_kind = RuntimeEngineKind.WIREGUARD_WINDOWS
    expected_platform = "Windows"
    platform_slug = "windows"
    protocol_label = "WireGuard"
    prepare_warning_codes = (
        WIREGUARD_WARNING_SYSTEM_PROMPT,
        WIREGUARD_WARNING_WINDOWS_ELEVATION,
    )
    start_flags = ("--elevation-flow",)

    def __init__(
        self,
        *,
        runner: WireGuardCommandRunner | None = None,
        asset_locator: WireGuardWindowsAssetLocator | None = None,
        platform_name: str | None = None,
    ) -> None:
        super().__init__(
            runner=runner,
            asset_locator=asset_locator or WireGuardWindowsAssetLocator(),
            platform_name=platform_name,
        )
