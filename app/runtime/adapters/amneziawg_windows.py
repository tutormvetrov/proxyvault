from __future__ import annotations

from app.models import ProxyType
from app.runtime.amneziawg_windows_support import AmneziaWGWindowsAssetLocator
from app.runtime.enums import RuntimeEngineKind
from app.runtime.wireguard_support import (
    WIREGUARD_WARNING_SYSTEM_PROMPT,
    WIREGUARD_WARNING_WINDOWS_ELEVATION,
    WireGuardAdapterBase,
    WireGuardCommandRunner,
)


class AmneziaWGAdapterWindows(WireGuardAdapterBase):
    engine_kind = RuntimeEngineKind.AMNEZIAWG_WINDOWS
    expected_platform = "Windows"
    platform_slug = "windows"
    protocol_label = "AmneziaWG"
    supported_types = (ProxyType.AMNEZIAWG,)
    prepare_warning_codes = (
        WIREGUARD_WARNING_SYSTEM_PROMPT,
        WIREGUARD_WARNING_WINDOWS_ELEVATION,
    )
    start_flags = ("--elevation-flow",)

    def __init__(
        self,
        *,
        runner: WireGuardCommandRunner | None = None,
        asset_locator: AmneziaWGWindowsAssetLocator | None = None,
        platform_name: str | None = None,
    ) -> None:
        super().__init__(
            runner=runner,
            asset_locator=asset_locator or AmneziaWGWindowsAssetLocator(),
            platform_name=platform_name,
        )
