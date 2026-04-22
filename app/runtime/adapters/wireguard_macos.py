from __future__ import annotations

from app.runtime.enums import RuntimeEngineKind
from app.runtime.wireguard_support import (
    WIREGUARD_WARNING_MACOS_UNSIGNED,
    WIREGUARD_WARNING_SYSTEM_PROMPT,
    WireGuardAdapterBase,
    WireGuardCommandRunner,
)
from app.runtime.wireguard_macos_support import WireGuardMacOSAssetLocator


class WireGuardAdapterMacOS(WireGuardAdapterBase):
    engine_kind = RuntimeEngineKind.WIREGUARD_MACOS
    expected_platform = "Darwin"
    platform_slug = "macos"
    protocol_label = "WireGuard"
    prepare_warning_codes = (
        WIREGUARD_WARNING_SYSTEM_PROMPT,
        WIREGUARD_WARNING_MACOS_UNSIGNED,
    )
    start_flags = ("--macos-authorization-flow", "--unsigned-build-check")

    def __init__(
        self,
        *,
        runner: WireGuardCommandRunner | None = None,
        asset_locator: WireGuardMacOSAssetLocator | None = None,
        platform_name: str | None = None,
    ) -> None:
        super().__init__(
            runner=runner,
            asset_locator=asset_locator or WireGuardMacOSAssetLocator(),
            platform_name=platform_name,
        )
