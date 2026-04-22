# Third-Party Notices for ProxyVault Runtime Assets

This release bundles or bootstraps the runtime components below for ProxyVault Client Mode.

## sing-box

- Component: `sing-box` 1.13.10
- License: GNU General Public License v3.0 or later
- Upstream source: <https://github.com/SagerNet/sing-box>
- Upstream release: <https://github.com/SagerNet/sing-box/releases/tag/v1.13.10>

## WireGuard for Windows

- Component: `wireguard-amd64-0.6.1.msi`
- License: MIT
- Upstream source: <https://git.zx2c4.com/wireguard-windows/>
- Official installer payload: <https://download.wireguard.com/windows-client/wireguard-amd64-0.6.1.msi>

## Wintun

- Component: Wintun driver/runtime used by WireGuard and AmneziaWG Windows payloads
- License: GNU General Public License v2.0 only
- Upstream source: <https://git.zx2c4.com/wintun/>
- Official site: <https://www.wintun.net/>

## AmneziaWG for Windows

- Component: bundled `amneziawg.exe`, `awg.exe`, and related Windows runtime files
- License: MIT
- Upstream source: <https://github.com/amnezia-vpn/amneziawg-windows-client>
- Upstream docs: <https://docs.amnezia.org/documentation/amnezia-wg/>

## Notes

- ProxyVault-specific helper binaries are part of this project and are not separate third-party products.
- Python package licenses bundled by PyInstaller remain available inside their respective distribution metadata directories in the release.
