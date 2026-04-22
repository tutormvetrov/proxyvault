# ProxyVault Client Mode

Russian version: [README.md](README.md)

## What It Is

ProxyVault Client Mode is a desktop app for keeping proxy and VPN profiles on your own device, starting the profile you need, and optionally making that connection the system-wide route.

The intended everyday flow is simple:

1. Add a config or subscription.
2. Select the profile in the library.
3. Click `Connect`.
4. If you want all system traffic to use it, click `Make Primary`.
5. Check the status, ports, recent activity, and guidance in the right panel.

ProxyVault is local-first. Your library, notes, QR assets, and imported entries stay on your machine.

## How To Launch

### Ready-made release archive

If you already have a release build:

1. Download the archive for your platform.
2. Extract it to a normal folder.
3. Start `ProxyVault.exe` on Windows or `ProxyVault.app` on macOS.
4. On first launch, add your connection and follow the quick start in the welcome window.

### Run from source

You need Python `3.11+`.

```bash
pip install -r requirements.txt
python main.py
```

### Where data is stored

By default, ProxyVault keeps its library inside your local app directory. In portable mode, the database and QR assets can live next to the app itself.

## How To Add a Connection

ProxyVault can store and import common config and subscription formats including `vless://`, `hysteria2://`, `ss://`, `trojan://`, `naive+https://`, and WireGuard config blocks.

For real Client Mode launches in v1, the supported runtime path is limited to the `sing-box`-based profiles and WireGuard. Unsupported types and generic `OTHER` entries can stay in the library, but Connect may remain unavailable for them.

The easiest path is:

1. Open the add dialog.
2. Paste the URI, WireGuard block, or subscription content.
3. Review the name and add a note if helpful.
4. Save the entry.

If the config is already in your clipboard, ProxyVault can prefill it automatically.

## How To Connect

After the profile is in your library:

1. Select it in the list or card grid.
2. Click `Connect`.
3. Wait for the status to become `Connected`.
4. If you want it to drive your system traffic, click `Make Primary`.

Important distinctions:

- `Connected` means the profile is running locally and has working local ports.
- `Make Primary` means ProxyVault binds the system proxy to that running connection.
- If a profile is active but not primary, you can still use its local address manually from another app.
- WireGuard follows a separate route path and should not be treated like a normal proxy session.
- In a clean Windows release, ProxyVault already ships bundled `sing-box`, a bundled AmneziaWG runtime, and a pinned WireGuard bootstrap payload. The first WireGuard launch may require only OS/UAC approval, not a manual client installation step.
- On macOS, the turnkey path is currently complete only for `sing-box` profiles. WireGuard and AmneziaWG still depend on platform tools such as `wg-quick` / `awg-quick`.

## How To Tell It Is Working

Use the right panel as your main source of truth:

- the status should be `Connected` or `Primary`
- local HTTP and SOCKS ports should be visible
- start time and recent activity should not be empty
- the human explanation area should not show an active error

The TCP check is a separate network diagnostic. It helps confirm whether the remote server responds, but it does not replace the real runtime status.

## How To Disconnect

1. Select the active connection.
2. Click `Disconnect`.
3. Confirm the status changes to `Disconnected`.

If that connection was primary, ProxyVault should clear the system proxy automatically.

## If Something Does Not Work

Start with the simplest checks:

1. Make sure you pasted the full config without cut lines or extra junk.
2. Check whether the local port is already used by another app.
3. Read the short explanation in the right panel, then open the technical log.
4. If needed, stop the profile and start it again.

Common cases:

- `Server is not responding`
  Check the address, port, internet access, and whether the remote server is reachable.
- `Could not start the engine`
  This usually means the config is invalid, a runtime component is missing, or the process exited immediately.
- `Port is already in use`
  Close the conflicting app or choose another local port in the profile settings.
- `Authentication details were rejected`
  Review the username, password, UUID, keys, and TLS-related fields.
- `Could not apply the system proxy`
  The local session may be running, but the operating system did not accept it as the primary route.
- `WireGuard needs confirmation`
  Windows or macOS may require elevation or an explicit system approval step.

## Which File To Download For Mac

When choosing a macOS release:

- `ProxyVault-macos-arm64.zip` is for Apple Silicon Macs such as M1, M2, and M3
- `ProxyVault-macos-x64.zip` is for Intel Macs
- `ProxyVault-macos-universal2.zip` is the universal option when available

To check your Mac:

1. Open the Apple menu.
2. Click `About This Mac`.
3. Look at the `Chip` or `Processor` field.

If you see `Apple M1`, `Apple M2`, `Apple M3`, or similar, choose `arm64`.
If you see `Intel`, choose `x64`.

## Release Builds

### Windows

```powershell
./build-windows.ps1
```

To build a portable archive with preloaded library data, use explicit opt-in:

```powershell
./build-windows.ps1 -IncludeLocalData
```

### macOS

```bash
./build-macos.sh
```

For macOS, bundled portable seed data is also explicit:

```bash
INCLUDE_LOCAL_DATA=1 ./build-macos.sh
```

Archives and checksums are produced in `release/`.

## What Else ProxyVault Can Do

- keep a local library of connection profiles
- import subscription payloads
- generate and export QR codes
- save notes, tags, and favorites
- protect stored URIs with a master password
- build a portable archive with preloaded library data

## Good To Know

- ProxyVault is local-first and does not require cloud sync.
- Raw technical logs may still contain English text from the underlying engines.
- macOS may ask for confirmation the first time you launch the app.
- Unsigned macOS builds may need right-click -> `Open` on first launch.
