from __future__ import annotations

from app.models import ProxyType
from app.runtime.amneziawg_macos_support import AmneziaWGMacOSAssetLocator
from app.runtime.enums import RuntimeEngineKind
from app.runtime.wireguard_support import (
    WIREGUARD_WARNING_MACOS_UNSIGNED,
    WIREGUARD_WARNING_SYSTEM_PROMPT,
    WireGuardAdapterBase,
    WireGuardCommandRunner,
)


class AmneziaWGAdapterMacOS(WireGuardAdapterBase):
    engine_kind = RuntimeEngineKind.AMNEZIAWG_MACOS
    expected_platform = "Darwin"
    platform_slug = "macos"
    protocol_label = "AmneziaWG"
    supported_types = (ProxyType.AMNEZIAWG,)
    prepare_warning_codes = (
        WIREGUARD_WARNING_SYSTEM_PROMPT,
        WIREGUARD_WARNING_MACOS_UNSIGNED,
    )
    start_flags = ("--macos-authorization-flow", "--unsigned-build-check")

    def __init__(
        self,
        *,
        runner: WireGuardCommandRunner | None = None,
        asset_locator: AmneziaWGMacOSAssetLocator | None = None,
        platform_name: str | None = None,
    ) -> None:
        super().__init__(
            runner=runner,
            asset_locator=asset_locator or AmneziaWGMacOSAssetLocator(),
            platform_name=platform_name,
        )
