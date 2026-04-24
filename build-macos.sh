#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MACOS_RELEASE_TAG="${MACOS_RELEASE_TAG:-universal2}"
PYINSTALLER_TARGET_ARCH="${PYINSTALLER_TARGET_ARCH:-universal2}"

RELEASE_DIR="$ROOT/release"
STAGE_DIR="$RELEASE_DIR/ProxyVault-macos-${MACOS_RELEASE_TAG}"
ARCHIVE_PATH="$RELEASE_DIR/ProxyVault-macos-${MACOS_RELEASE_TAG}.zip"
DIST_DIR="$ROOT/dist-macos"
BUILD_DIR="$ROOT/build-macos"
DEFAULT_PORTABLE_SOURCE_DIR="$ROOT/portable-seed"
PORTABLE_SOURCE_DIR="${PORTABLE_SOURCE_DIR:-}"
INCLUDE_LOCAL_DATA="${INCLUDE_LOCAL_DATA:-0}"
if [[ -z "$PORTABLE_SOURCE_DIR" && -d "$DEFAULT_PORTABLE_SOURCE_DIR" ]]; then
  PORTABLE_SOURCE_DIR="$DEFAULT_PORTABLE_SOURCE_DIR"
fi

assert_file_exists() {
  local file_path="$1"
  local description="$2"
  if [[ ! -f "$file_path" ]]; then
    echo "$description is missing: $file_path" >&2
    exit 1
  fi
}

if [[ -n "$PORTABLE_SOURCE_DIR" && ! -d "$PORTABLE_SOURCE_DIR" ]]; then
  echo "Portable source directory does not exist: $PORTABLE_SOURCE_DIR" >&2
  exit 1
fi

rm -rf "$STAGE_DIR" "$ARCHIVE_PATH" "$DIST_DIR" "$BUILD_DIR"
mkdir -p "$RELEASE_DIR"

export PYINSTALLER_TARGET_ARCH

echo "Building macOS release tag=${MACOS_RELEASE_TAG} target_arch=${PYINSTALLER_TARGET_ARCH}"

REPO_SING_BOX="$ROOT/engines/sing-box/macos/sing-box"
REPO_WIREGUARD_HELPER="$ROOT/engines/wireguard/macos/proxyvault-wireguard-macos"
REPO_AMNEZIAWG_HELPER="$ROOT/engines/amneziawg/macos/proxyvault-amneziawg-macos"
REPO_THIRD_PARTY_NOTICES="$ROOT/tools/runtime_assets/THIRD_PARTY_NOTICES.md"
REPO_LICENSE_README="$ROOT/tools/runtime_assets/LICENSES/README.md"

python3 -m pip install -r requirements-build.txt
python3 "./tools/runtime_assets/bootstrap_runtime_assets.py" --target macos --rebuild-helper

assert_file_exists "$REPO_SING_BOX" "Bundled sing-box executable"
assert_file_exists "$REPO_WIREGUARD_HELPER" "Bundled WireGuard macOS helper"
assert_file_exists "$REPO_AMNEZIAWG_HELPER" "Bundled AmneziaWG macOS helper"
assert_file_exists "$REPO_THIRD_PARTY_NOTICES" "Third-party notices bundle"
assert_file_exists "$REPO_LICENSE_README" "Third-party license bundle"

python3 -c "from app.runtime.paths import resolve_sing_box_asset_layout; resolve_sing_box_asset_layout(platform_name='darwin', required_support_files=()); print('Validated bundled sing-box assets for macOS.')"

if [[ "${SKIP_AUDIT:-0}" != "1" ]]; then
  audit_cmd=(python3 -m pip_audit -r requirements-build.txt)
  if [[ -f audit-waivers.txt ]]; then
    while IFS= read -r line; do
      waiver="$(echo "$line" | xargs)"
      if [[ -n "$waiver" && ! "$waiver" =~ ^# ]]; then
        audit_cmd+=(--ignore-vuln "$waiver")
      fi
    done < audit-waivers.txt
  fi
  "${audit_cmd[@]}"
fi

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  python3 "./tools/run_unittest_shards.py" --root tests --verbose
fi

python3 -m PyInstaller --noconfirm --clean "./proxyvault-macos.spec" --distpath "$DIST_DIR" --workpath "$BUILD_DIR"

mkdir -p "$STAGE_DIR"
cp -R "$DIST_DIR/ProxyVault.app" "$STAGE_DIR/ProxyVault.app"
python3 "./tools/release_bundle.py" copy-payload --platform macos --stage-dir "$STAGE_DIR"

STAGED_SING_BOX="$STAGE_DIR/ProxyVault.app/Contents/Resources/engines/sing-box/macos/sing-box"
STAGED_WIREGUARD_HELPER="$STAGE_DIR/ProxyVault.app/Contents/Resources/engines/wireguard/macos/proxyvault-wireguard-macos"
STAGED_AMNEZIAWG_HELPER="$STAGE_DIR/ProxyVault.app/Contents/Resources/engines/amneziawg/macos/proxyvault-amneziawg-macos"
STAGED_THIRD_PARTY_NOTICES="$STAGE_DIR/THIRD_PARTY_NOTICES.md"
STAGED_LICENSE_README="$STAGE_DIR/LICENSES/README.md"

assert_file_exists "$STAGED_SING_BOX" "Staged sing-box executable"
assert_file_exists "$STAGED_WIREGUARD_HELPER" "Staged WireGuard macOS helper"
assert_file_exists "$STAGED_AMNEZIAWG_HELPER" "Staged AmneziaWG macOS helper"
assert_file_exists "$STAGED_THIRD_PARTY_NOTICES" "Staged third-party notices bundle"
assert_file_exists "$STAGED_LICENSE_README" "Staged third-party license bundle"
chmod +x "$STAGED_SING_BOX"
chmod +x "$STAGED_WIREGUARD_HELPER"
chmod +x "$STAGED_AMNEZIAWG_HELPER"
python3 "./tools/release_bundle.py" validate-stage --platform macos --stage-dir "$STAGE_DIR"

if [[ "$INCLUDE_LOCAL_DATA" == "1" ]]; then
  if [[ -z "$PORTABLE_SOURCE_DIR" ]]; then
    echo "INCLUDE_LOCAL_DATA=1 was requested, but no portable seed directory was provided or found." >&2
    exit 1
  fi
  APP_SEED_DIR="$STAGE_DIR/ProxyVault.app/Contents/Resources/portable-seed"
  mkdir -p "$APP_SEED_DIR"
  if [[ -f "$PORTABLE_SOURCE_DIR/proxyvault.db" ]]; then
    cp "$PORTABLE_SOURCE_DIR/proxyvault.db" "$APP_SEED_DIR/proxyvault.db"
  fi
  if [[ -d "$PORTABLE_SOURCE_DIR/qrcodes" ]]; then
    cp -R "$PORTABLE_SOURCE_DIR/qrcodes" "$APP_SEED_DIR/qrcodes"
  fi
else
  echo "Staging macOS release. Private portable-seed payload is bundled when present."
fi

ditto -c -k --keepParent "$STAGE_DIR" "$ARCHIVE_PATH"
python3 "./tools/release_bundle.py" validate-archive --platform macos --archive-path "$ARCHIVE_PATH"

checksum_file="$RELEASE_DIR/SHA256SUMS.txt"
: > "$checksum_file"
while IFS= read -r -d '' archive; do
  shasum -a 256 "$archive" >> "$checksum_file"
done < <(find "$RELEASE_DIR" -maxdepth 1 -name '*.zip' -print0 | sort -z)

echo "Built macOS release archive: $ARCHIVE_PATH"
