# ProxyVault

Local-first desktop app for storing proxy and VPN configs, previewing them as QR codes, and exporting or sharing a ready-to-use portable library.

## What It Does

- Saves proxy/VPN entries in a local SQLite database.
- Detects common formats such as `vless://`, `hysteria2://`, `ss://`, `trojan://`, `https://user:pass@host:port`, and WireGuard blocks.
- Generates QR previews and exports PNG, SVG, PDF, ZIP, and Clash YAML.
- Imports subscription payloads from URI lists or Clash YAML.
- Supports optional AES-256-GCM encryption at rest for saved URIs.
- Can package a preloaded portable archive so another person gets a working app on first launch.

## Runtime Requirements

- Python `3.11+`
- Windows `10+`
- macOS `12+`
- Ubuntu `22.04+`

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## Main Features

### Library

- Searchable catalog with grid and list views
- Favorites, tags, expiry warnings, and sorting
- Right-side inspector with QR preview and parsed parameters
- Reachability checks per entry

### QR Workflow

- Live QR preview while editing
- PNG and SVG export
- Clipboard copy
- Batch regeneration

### Security

- Optional master password
- AES-256-GCM encrypted URI storage
- PBKDF2-derived key
- HTTPS-only subscription fetching by default
- HTTP allowed only through an explicit settings override

### Sharing / Portable Mode

- Windows portable archive can carry `proxyvault.db` and `qrcodes/` next to `ProxyVault.exe`
- macOS portable archive embeds seeded data inside `ProxyVault.app`
- On first launch, macOS can bootstrap the local library from the embedded seed

## Install Dependencies

Runtime dependencies:

```bash
pip install -r requirements.txt
```

Pinned build dependencies:

```bash
pip install -r requirements-build.txt
```

## Release Builds

### Windows

```powershell
./build-windows.ps1
```

Output:

- `release/ProxyVault-win-x64.zip`
- `release/SHA256SUMS.txt`

### macOS

Run on a Mac:

```bash
./build-macos.sh
```

Output:

- `release/ProxyVault-macos-universal2.zip`
- `release/SHA256SUMS.txt`

### If You Do Not Have a Mac

Use the bundled GitHub Actions workflow:

- Workflow file: `.github/workflows/release-artifacts.yml`
- It builds the Windows archive plus two macOS archives
- `ProxyVault-macos-arm64.zip` for Apple Silicon Macs
- `ProxyVault-macos-x64.zip` for Intel Macs
- This avoids fragile `universal2` packaging failures on GitHub-hosted runners

If the recipient has a recent MacBook on modern macOS, `arm64` is the most likely match.

## Portable Seed Data

For reproducible preloaded builds, place your current library in:

- `portable-seed/proxyvault.db`
- `portable-seed/qrcodes/...`

The build scripts prefer `portable-seed/` over the current user profile when it exists.

Refresh that seed folder from your local Windows app data:

```powershell
./prepare-portable-seed.ps1
```

## Data Locations

Default local storage:

- Database: `~/ProxyVault/proxyvault.db`
- QR output: `~/ProxyVault/qrcodes/...`

In portable mode:

- Windows uses sidecar files near `ProxyVault.exe`
- macOS can restore seeded data from `ProxyVault.app/Contents/Resources/portable-seed`

## Build Pipeline Notes

Both build entrypoints:

- run `pip-audit` against `requirements-build.txt`
- run the test suite before packaging
- produce archives under `release/`
- generate `release/SHA256SUMS.txt`

If `audit-waivers.txt` exists, every non-comment line is passed to `pip-audit --ignore-vuln`.

## Project Structure

```text
main.py
app/
  __init__.py
  db.py
  models.py
  parser.py
  paths.py
  qr_gen.py
  subscriptions.py
  ui/
    __init__.py
    card_view.py
    detail_panel.py
    dialogs.py
    main_window.py
    settings.py
    sidebar.py
    theme.py
    workers.py
tests/
requirements.txt
requirements-build.txt
README.md
```

## Notes

- If the database is corrupted, ProxyVault offers a backup-and-reset flow on launch.
- Parsed sensitive values such as passwords, UUIDs, and login values remain visible after unlock by product decision.
- macOS archives in this pass are unsigned and not notarized.
- If Gatekeeper blocks first launch on macOS, open the app with right-click -> Open once.
