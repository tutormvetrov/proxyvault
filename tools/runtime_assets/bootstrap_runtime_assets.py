from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
MANIFEST_PATH = SCRIPT_DIR / "manifest.json"
CACHE_DIR = REPO_ROOT / ".cache" / "runtime-assets"
ENGINES_DIR = REPO_ROOT / "engines"
WINDOWS_HELPER_SOURCE = SCRIPT_DIR / "wireguard_helper_windows.py"
MACOS_HELPER_SOURCE = SCRIPT_DIR / "wireguard_helper_macos.sh"
AMNEZIAWG_WINDOWS_HELPER_SOURCE = SCRIPT_DIR / "amneziawg_helper_windows.py"
AMNEZIAWG_MACOS_HELPER_SOURCE = SCRIPT_DIR / "amneziawg_helper_macos.sh"
WIREGUARD_WINDOWS_BOOTSTRAP_DIR = ENGINES_DIR / "wireguard" / "windows"
WIREGUARD_WINDOWS_BOOTSTRAP_MANIFEST_OUTPUT = WIREGUARD_WINDOWS_BOOTSTRAP_DIR / "wireguard-bootstrap.json"
WINDOWS_HELPER_OUTPUT = ENGINES_DIR / "wireguard" / "windows" / "proxyvault-wireguard-windows.exe"
MACOS_HELPER_OUTPUT = ENGINES_DIR / "wireguard" / "macos" / "proxyvault-wireguard-macos"
AMNEZIAWG_WINDOWS_HELPER_OUTPUT = ENGINES_DIR / "amneziawg" / "windows" / "proxyvault-amneziawg-windows.exe"
AMNEZIAWG_MACOS_HELPER_OUTPUT = ENGINES_DIR / "amneziawg" / "macos" / "proxyvault-amneziawg-macos"

MACHO_MAGIC_64 = 0xFEEDFACF
FAT_MAGIC = 0xCAFEBABE
FAT_SLICE_ALIGN = 12


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(asset: dict[str, str], *, force: bool) -> Path:
    ensure_directory(CACHE_DIR)
    archive_path = CACHE_DIR / asset["archive_name"]
    expected_sha = asset["sha256"]
    if archive_path.exists() and not force and sha256_file(archive_path) == expected_sha:
        print(f"Reusing cached asset: {archive_path.name}")
        return archive_path

    print(f"Downloading {archive_path.name} ...")
    with urllib.request.urlopen(asset["url"], timeout=120) as response, archive_path.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)

    actual_sha = sha256_file(archive_path)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Checksum mismatch for {archive_path.name}: expected {expected_sha}, got {actual_sha}"
        )
    return archive_path


def _extract_member_from_zip(archive_path: Path, suffix: str) -> bytes:
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if name.endswith(suffix):
                return archive.read(name)
    raise FileNotFoundError(f"{suffix} was not found in {archive_path.name}")


def _extract_member_from_tar(archive_path: Path, suffix: str) -> bytes:
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            if member.name.endswith(suffix):
                extracted = archive.extractfile(member)
                if extracted is None:
                    break
                return extracted.read()
    raise FileNotFoundError(f"{suffix} was not found in {archive_path.name}")


def _write_bytes(path: Path, payload: bytes, *, executable: bool = False) -> None:
    ensure_directory(path.parent)
    path.write_bytes(payload)
    if executable:
        current_mode = path.stat().st_mode
        path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def prepare_windows_sing_box(manifest: dict[str, Any], *, force: bool) -> None:
    archive = download_asset(manifest["sing_box"]["windows_amd64"], force=force)
    sing_box_bytes = _extract_member_from_zip(archive, "/sing-box.exe")
    cronet_bytes = _extract_member_from_zip(archive, "/libcronet.dll")
    target_dir = ENGINES_DIR / "sing-box" / "windows"
    _write_bytes(target_dir / "sing-box.exe", sing_box_bytes, executable=True)
    _write_bytes(target_dir / "libcronet.dll", cronet_bytes)
    print(f"Prepared Windows sing-box assets in {target_dir}")


def prepare_windows_wireguard_bootstrap(manifest: dict[str, Any], *, force: bool) -> None:
    asset = manifest["wireguard"]["windows_amd64"]
    archive = download_asset(asset, force=force)
    ensure_directory(WIREGUARD_WINDOWS_BOOTSTRAP_DIR)
    target_path = WIREGUARD_WINDOWS_BOOTSTRAP_DIR / asset["archive_name"]
    shutil.copy2(archive, target_path)
    bootstrap_manifest = {
        "version": asset["version"],
        "installer_name": asset["archive_name"],
        "sha256": asset["sha256"],
        "url": asset["url"],
    }
    WIREGUARD_WINDOWS_BOOTSTRAP_MANIFEST_OUTPUT.write_text(
        json.dumps(bootstrap_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Prepared Windows WireGuard bootstrap payload in {WIREGUARD_WINDOWS_BOOTSTRAP_DIR}")


def _read_macho_header(binary: bytes) -> tuple[int, int]:
    if len(binary) < 12:
        raise ValueError("Mach-O payload is too small.")
    magic, cpu_type, cpu_subtype = struct.unpack("<III", binary[:12])
    if magic != MACHO_MAGIC_64:
        raise ValueError(f"Unsupported Mach-O magic: {magic:#x}")
    return cpu_type, cpu_subtype


def _align(offset: int, exponent: int) -> int:
    boundary = 1 << exponent
    return (offset + boundary - 1) & ~(boundary - 1)


def build_universal_macho(x86_64_payload: bytes, arm64_payload: bytes) -> bytes:
    slices = []
    for payload in (x86_64_payload, arm64_payload):
        cpu_type, cpu_subtype = _read_macho_header(payload)
        slices.append(
            {
                "payload": payload,
                "cpu_type": cpu_type,
                "cpu_subtype": cpu_subtype,
            }
        )

    header_size = 8 + len(slices) * 20
    offset = _align(header_size, FAT_SLICE_ALIGN)
    header = bytearray(struct.pack(">II", FAT_MAGIC, len(slices)))
    data = bytearray()

    for index, slice_info in enumerate(slices):
        if len(data) == 0:
            current_offset = offset
        else:
            current_offset = _align(offset + len(data), FAT_SLICE_ALIGN)
        padding_size = current_offset - (offset + len(data))
        if padding_size > 0:
            data.extend(b"\0" * padding_size)

        payload = slice_info["payload"]
        header.extend(
            struct.pack(
                ">IIIII",
                slice_info["cpu_type"],
                slice_info["cpu_subtype"],
                current_offset,
                len(payload),
                FAT_SLICE_ALIGN,
            )
        )
        data.extend(payload)

    if len(header) < offset:
        header.extend(b"\0" * (offset - len(header)))
    return bytes(header + data)


def prepare_macos_sing_box(manifest: dict[str, Any], *, force: bool) -> None:
    amd64_archive = download_asset(manifest["sing_box"]["darwin_amd64"], force=force)
    arm64_archive = download_asset(manifest["sing_box"]["darwin_arm64"], force=force)
    amd64_binary = _extract_member_from_tar(amd64_archive, "/sing-box")
    arm64_binary = _extract_member_from_tar(arm64_archive, "/sing-box")
    universal_binary = build_universal_macho(amd64_binary, arm64_binary)
    target_path = ENGINES_DIR / "sing-box" / "macos" / "sing-box"
    _write_bytes(target_path, universal_binary, executable=True)
    print(f"Prepared macOS universal sing-box asset in {target_path}")


def _find_pyinstaller() -> list[str]:
    executable = shutil.which("pyinstaller")
    if executable:
        return [executable]
    return [sys.executable, "-m", "PyInstaller"]


def build_windows_helper(
    *,
    source_path: Path,
    output_path: Path,
    helper_name: str,
    helper_label: str,
    force: bool,
) -> None:
    if output_path.exists() and not force:
        print(f"Reusing existing Windows {helper_label} helper: {output_path}")
        return

    build_root = REPO_ROOT / "build-wireguard-helper" / helper_name
    dist_dir = output_path.parent
    if build_root.exists():
        shutil.rmtree(build_root)
    ensure_directory(build_root)
    ensure_directory(dist_dir)

    pyinstaller_cmd = [
        *_find_pyinstaller(),
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        helper_name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_root / "work"),
        "--specpath",
        str(build_root / "spec"),
        str(source_path),
    ]
    completed = subprocess.run(pyinstaller_cmd, cwd=str(REPO_ROOT), check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"PyInstaller failed while building the Windows {helper_label} helper ({completed.returncode})."
        )
    if not output_path.exists():
        raise FileNotFoundError(f"Windows {helper_label} helper was not created at {output_path}")
    print(f"Built Windows {helper_label} helper at {output_path}")


def prepare_macos_helper(*, source_path: Path, output_path: Path, helper_label: str) -> None:
    _write_bytes(output_path, source_path.read_bytes(), executable=True)
    print(f"Prepared macOS {helper_label} helper at {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare bundled runtime assets for ProxyVault.")
    parser.add_argument(
        "--target",
        action="append",
        choices=("windows", "macos", "all"),
        help="Limit preparation to one or more targets. Defaults to all.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download remote archives even if the checksum-verified cache already exists.",
    )
    parser.add_argument(
        "--rebuild-helper",
        action="store_true",
        help="Force rebuilding or recopying WireGuard helpers even if they already exist.",
    )
    return parser.parse_args()


def resolve_targets(raw_targets: list[str] | None) -> set[str]:
    if not raw_targets or "all" in raw_targets:
        return {"windows", "macos"}
    return set(raw_targets)


def main() -> int:
    args = parse_args()
    manifest = load_manifest()
    targets = resolve_targets(args.target)

    if "windows" in targets:
        prepare_windows_sing_box(manifest, force=args.force_download)
        prepare_windows_wireguard_bootstrap(manifest, force=args.force_download)
        build_windows_helper(
            source_path=WINDOWS_HELPER_SOURCE,
            output_path=WINDOWS_HELPER_OUTPUT,
            helper_name="proxyvault-wireguard-windows",
            helper_label="WireGuard",
            force=args.rebuild_helper,
        )
        build_windows_helper(
            source_path=AMNEZIAWG_WINDOWS_HELPER_SOURCE,
            output_path=AMNEZIAWG_WINDOWS_HELPER_OUTPUT,
            helper_name="proxyvault-amneziawg-windows",
            helper_label="AmneziaWG",
            force=args.rebuild_helper,
        )
    if "macos" in targets:
        prepare_macos_sing_box(manifest, force=args.force_download)
        prepare_macos_helper(
            source_path=MACOS_HELPER_SOURCE,
            output_path=MACOS_HELPER_OUTPUT,
            helper_label="WireGuard",
        )
        prepare_macos_helper(
            source_path=AMNEZIAWG_MACOS_HELPER_SOURCE,
            output_path=AMNEZIAWG_MACOS_HELPER_OUTPUT,
            helper_label="AmneziaWG",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
