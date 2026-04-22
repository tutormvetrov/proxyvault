#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

RELEASE_DIR="$ROOT/release"
STAGE_DIR="$RELEASE_DIR/ProxyVault-macos-universal2"
ARCHIVE_PATH="$RELEASE_DIR/ProxyVault-macos-universal2.zip"
DIST_DIR="$ROOT/dist-macos"
BUILD_DIR="$ROOT/build-macos"
DEFAULT_PORTABLE_SOURCE_DIR="$ROOT/portable-seed"
if [[ -d "$DEFAULT_PORTABLE_SOURCE_DIR" ]]; then
  PORTABLE_SOURCE_DIR="${PORTABLE_SOURCE_DIR:-$DEFAULT_PORTABLE_SOURCE_DIR}"
else
  PORTABLE_SOURCE_DIR="${PORTABLE_SOURCE_DIR:-$(python3 -c 'from app.paths import HOME_APP_DIR; print(HOME_APP_DIR)')}"
fi

rm -rf "$STAGE_DIR" "$ARCHIVE_PATH" "$DIST_DIR" "$BUILD_DIR"
mkdir -p "$RELEASE_DIR"

python3 -m pip install -r requirements-build.txt

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
  python3 -m unittest discover -s tests -v
fi

python3 -m PyInstaller --noconfirm --clean "./proxyvault-macos.spec" --distpath "$DIST_DIR" --workpath "$BUILD_DIR"

mkdir -p "$STAGE_DIR"
cp "README.md" "$STAGE_DIR/README.md"
cp -R "$DIST_DIR/ProxyVault.app" "$STAGE_DIR/ProxyVault.app"

if [[ "${INCLUDE_LOCAL_DATA:-1}" == "1" && -n "$PORTABLE_SOURCE_DIR" ]]; then
  APP_SEED_DIR="$STAGE_DIR/ProxyVault.app/Contents/Resources/portable-seed"
  mkdir -p "$APP_SEED_DIR"
  if [[ -f "$PORTABLE_SOURCE_DIR/proxyvault.db" ]]; then
    cp "$PORTABLE_SOURCE_DIR/proxyvault.db" "$APP_SEED_DIR/proxyvault.db"
  fi
  if [[ -d "$PORTABLE_SOURCE_DIR/qrcodes" ]]; then
    cp -R "$PORTABLE_SOURCE_DIR/qrcodes" "$APP_SEED_DIR/qrcodes"
  fi
fi

ditto -c -k --keepParent "$STAGE_DIR" "$ARCHIVE_PATH"

checksum_file="$RELEASE_DIR/SHA256SUMS.txt"
: > "$checksum_file"
while IFS= read -r -d '' archive; do
  shasum -a 256 "$archive" >> "$checksum_file"
done < <(find "$RELEASE_DIR" -maxdepth 1 -name '*.zip' -print0 | sort -z)

echo "Built macOS release archive: $ARCHIVE_PATH"
