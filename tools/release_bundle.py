from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
RUNTIME_MANIFEST_PATH = REPO_ROOT / "tools" / "runtime_assets" / "manifest.json"
NOTICE_SOURCE = REPO_ROOT / "tools" / "runtime_assets" / "THIRD_PARTY_NOTICES.md"
LICENSES_SOURCE_DIR = REPO_ROOT / "tools" / "runtime_assets" / "LICENSES"
PORTABLE_SEED_SOURCE_DIR = REPO_ROOT / "portable-seed"


class ReleaseBundleError(RuntimeError):
    pass


def load_runtime_manifest() -> dict[str, object]:
    return json.loads(RUNTIME_MANIFEST_PATH.read_text(encoding="utf-8"))


def _wireguard_windows_bootstrap(manifest: dict[str, object]) -> dict[str, str]:
    payload = manifest["wireguard"]["windows_amd64"]
    return {
        "version": str(payload["version"]),
        "installer_name": str(payload["archive_name"]),
        "sha256": str(payload["sha256"]).lower(),
        "url": str(payload["url"]),
    }


def _amneziawg_windows_runtime(manifest: dict[str, object]) -> dict[str, object]:
    payload = manifest["amneziawg"]["windows_amd64"]
    base_dir = PurePosixPath(str(payload["runtime_dir"]))
    file_entries = payload["files"]
    if not isinstance(file_entries, dict):
        raise ReleaseBundleError("AmneziaWG manifest payload is malformed: files must be an object.")
    files: dict[PurePosixPath, str] = {}
    for file_name, metadata in file_entries.items():
        if not isinstance(metadata, dict):
            raise ReleaseBundleError(f"AmneziaWG manifest payload for {file_name} is malformed.")
        sha256 = str(metadata.get("sha256", "")).lower()
        if not sha256:
            raise ReleaseBundleError(f"AmneziaWG manifest payload for {file_name} is missing sha256.")
        files[base_dir / str(file_name)] = sha256
    return {
        "version": str(payload["version"]),
        "files": files,
    }


def _license_stage_relpaths() -> tuple[PurePosixPath, ...]:
    relpaths: list[PurePosixPath] = []
    for path in sorted(LICENSES_SOURCE_DIR.rglob("*")):
        if path.is_file():
            relpaths.append(PurePosixPath("LICENSES") / path.relative_to(LICENSES_SOURCE_DIR).as_posix())
    return tuple(relpaths)


def _portable_seed_relpaths(*, stage_prefix: PurePosixPath = PurePosixPath("")) -> tuple[PurePosixPath, ...]:
    if not PORTABLE_SEED_SOURCE_DIR.exists():
        return ()
    relpaths: list[PurePosixPath] = []
    for path in sorted(PORTABLE_SEED_SOURCE_DIR.rglob("*")):
        if path.is_file() and _is_portable_seed_payload_file(path):
            relpaths.append(stage_prefix / PORTABLE_SEED_SOURCE_DIR.name / path.relative_to(PORTABLE_SEED_SOURCE_DIR).as_posix())
    return tuple(relpaths)


def windows_repo_payload_relpaths(manifest: dict[str, object] | None = None) -> tuple[PurePosixPath, ...]:
    manifest = manifest or load_runtime_manifest()
    amneziawg = _amneziawg_windows_runtime(manifest)
    bootstrap = _wireguard_windows_bootstrap(manifest)
    return (
        PurePosixPath("engines/sing-box/windows/sing-box.exe"),
        PurePosixPath("engines/sing-box/windows/libcronet.dll"),
        PurePosixPath("engines/wireguard/windows/proxyvault-wireguard-windows.exe"),
        PurePosixPath("engines/wireguard/windows/wireguard-bootstrap.json"),
        PurePosixPath("engines/wireguard/windows") / bootstrap["installer_name"],
        PurePosixPath("engines/amneziawg/windows/proxyvault-amneziawg-windows.exe"),
        *tuple(amneziawg["files"].keys()),
    )


def windows_stage_required_relpaths(manifest: dict[str, object] | None = None) -> tuple[PurePosixPath, ...]:
    return (
        PurePosixPath("README.md"),
        PurePosixPath("THIRD_PARTY_NOTICES.md"),
        PurePosixPath("proxyvault.portable"),
        *windows_repo_payload_relpaths(manifest),
        *_license_stage_relpaths(),
        *_portable_seed_relpaths(),
    )


def macos_stage_required_relpaths() -> tuple[PurePosixPath, ...]:
    return (
        PurePosixPath("README.md"),
        PurePosixPath("THIRD_PARTY_NOTICES.md"),
        PurePosixPath("ProxyVault.app/Contents/Resources/engines/sing-box/macos/sing-box"),
        PurePosixPath("ProxyVault.app/Contents/Resources/engines/wireguard/macos/proxyvault-wireguard-macos"),
        PurePosixPath("ProxyVault.app/Contents/Resources/engines/amneziawg/macos/proxyvault-amneziawg-macos"),
        *_license_stage_relpaths(),
        *_portable_seed_relpaths(stage_prefix=PurePosixPath("ProxyVault.app/Contents/Resources")),
    )


def _macos_engine_source_to_stage_relpaths() -> tuple[tuple[PurePosixPath, PurePosixPath], ...]:
    return (
        (
            PurePosixPath("engines/sing-box/macos/sing-box"),
            PurePosixPath("ProxyVault.app/Contents/Resources/engines/sing-box/macos/sing-box"),
        ),
        (
            PurePosixPath("engines/wireguard/macos/proxyvault-wireguard-macos"),
            PurePosixPath("ProxyVault.app/Contents/Resources/engines/wireguard/macos/proxyvault-wireguard-macos"),
        ),
        (
            PurePosixPath("engines/amneziawg/macos/proxyvault-amneziawg-macos"),
            PurePosixPath("ProxyVault.app/Contents/Resources/engines/amneziawg/macos/proxyvault-amneziawg-macos"),
        ),
    )


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_tree_contents(source_dir: Path, destination_dir: Path) -> None:
    if not source_dir.exists():
        return
    for path in source_dir.rglob("*"):
        if not path.is_file() or not _is_portable_seed_payload_file(path):
            continue
        _copy_file(path, destination_dir / path.relative_to(source_dir))


def _is_portable_seed_payload_file(path: Path) -> bool:
    return path.name.lower() == "proxyvault.db"


def copy_release_payload(*, platform_name: str, stage_dir: Path, repo_root: Path | None = None) -> None:
    repo_root = repo_root or REPO_ROOT
    manifest = load_runtime_manifest()
    _copy_file(repo_root / "README.md", stage_dir / "README.md")
    _copy_file(NOTICE_SOURCE, stage_dir / "THIRD_PARTY_NOTICES.md")
    for license_path in LICENSES_SOURCE_DIR.rglob("*"):
        if not license_path.is_file():
            continue
        relative = license_path.relative_to(LICENSES_SOURCE_DIR)
        _copy_file(license_path, stage_dir / "LICENSES" / relative)

    if platform_name == "windows":
        for relpath in windows_repo_payload_relpaths(manifest):
            _copy_file(repo_root / relpath, stage_dir / relpath)
        _copy_tree_contents(repo_root / "portable-seed", stage_dir / "portable-seed")
        return
    if platform_name == "macos":
        for source_relpath, stage_relpath in _macos_engine_source_to_stage_relpaths():
            _copy_file(repo_root / source_relpath, stage_dir / stage_relpath)
        _copy_tree_contents(
            repo_root / "portable-seed",
            stage_dir / "ProxyVault.app" / "Contents" / "Resources" / "portable-seed",
        )
        return
    raise ReleaseBundleError(f"Unsupported platform for release payload copy: {platform_name}")


def _stage_files(stage_dir: Path) -> set[PurePosixPath]:
    return {
        PurePosixPath(path.relative_to(stage_dir).as_posix())
        for path in stage_dir.rglob("*")
        if path.is_file()
    }


def _zip_files(archive_path: Path) -> set[PurePosixPath]:
    with zipfile.ZipFile(archive_path) as archive:
        entries = [
            PurePosixPath(name)
            for name in archive.namelist()
            if name and not name.endswith("/")
        ]
    if not entries:
        return set()
    prefixes = {entry.parts[0] for entry in entries if len(entry.parts) > 1}
    if len(prefixes) == 1:
        root_prefix = next(iter(prefixes))
        return {
            PurePosixPath(*entry.parts[1:])
            for entry in entries
            if len(entry.parts) > 1 and entry.parts[0] == root_prefix
        }
    return set(entries)


def _stage_required_relpaths(platform_name: str) -> tuple[PurePosixPath, ...]:
    if platform_name == "windows":
        return windows_stage_required_relpaths()
    if platform_name == "macos":
        return macos_stage_required_relpaths()
    raise ReleaseBundleError(f"Unsupported platform for stage validation: {platform_name}")


def _is_disallowed(platform_name: str, relpath: PurePosixPath) -> bool:
    reltext = relpath.as_posix()
    if platform_name == "windows":
        return any(
            reltext.startswith(prefix)
            for prefix in (
                "engines/sing-box/macos/",
                "engines/wireguard/macos/",
                "engines/amneziawg/macos/",
                "ProxyVault.app/",
            )
        )
    if platform_name == "macos":
        return (
            reltext.startswith("engines/")
            or reltext.startswith("ProxyVault.app/Contents/Resources/engines/sing-box/windows/")
            or reltext.startswith("ProxyVault.app/Contents/Resources/engines/wireguard/windows/")
            or reltext.startswith("ProxyVault.app/Contents/Resources/engines/amneziawg/windows/")
        )
    return False


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_wireguard_bootstrap_from_stage(stage_dir: Path, manifest: dict[str, object]) -> None:
    bootstrap_dir = stage_dir / "engines" / "wireguard" / "windows"
    bootstrap_manifest_path = bootstrap_dir / "wireguard-bootstrap.json"
    if not bootstrap_manifest_path.exists():
        raise ReleaseBundleError(f"Missing staged WireGuard bootstrap manifest: {bootstrap_manifest_path}")
    payload = json.loads(bootstrap_manifest_path.read_text(encoding="utf-8"))
    expected = _wireguard_windows_bootstrap(manifest)
    installer_name = str(payload.get("installer_name", ""))
    installer_path = bootstrap_dir / installer_name
    if not installer_path.exists():
        raise ReleaseBundleError(f"Missing staged WireGuard bootstrap payload: {installer_path}")
    if str(payload.get("sha256", "")).lower() != expected["sha256"]:
        raise ReleaseBundleError("Staged WireGuard bootstrap manifest does not match the pinned checksum.")
    if installer_name != expected["installer_name"]:
        raise ReleaseBundleError("Staged WireGuard bootstrap manifest does not match the pinned installer name.")
    if _sha256_path(installer_path) != expected["sha256"]:
        raise ReleaseBundleError("Staged WireGuard bootstrap payload checksum does not match the pinned manifest.")


def _validate_wireguard_bootstrap_from_archive(archive_path: Path, manifest: dict[str, object]) -> None:
    expected = _wireguard_windows_bootstrap(manifest)
    with zipfile.ZipFile(archive_path) as archive:
        names = [name for name in archive.namelist() if name and not name.endswith("/")]
        if not names:
            raise ReleaseBundleError(f"Release archive is empty: {archive_path}")
        prefix = ""
        prefixes = {PurePosixPath(name).parts[0] for name in names if len(PurePosixPath(name).parts) > 1}
        if len(prefixes) == 1:
            prefix = next(iter(prefixes)) + "/"
        manifest_name = prefix + "engines/wireguard/windows/wireguard-bootstrap.json"
        if manifest_name not in names:
            raise ReleaseBundleError(f"Missing WireGuard bootstrap manifest inside archive: {manifest_name}")
        payload = json.loads(archive.read(manifest_name).decode("utf-8"))
        installer_name = str(payload.get("installer_name", ""))
        installer_archive_name = prefix + "engines/wireguard/windows/" + installer_name
        if installer_archive_name not in names:
            raise ReleaseBundleError(f"Missing WireGuard bootstrap payload inside archive: {installer_archive_name}")
        if installer_name != expected["installer_name"]:
            raise ReleaseBundleError("Archived WireGuard bootstrap manifest does not match the pinned installer name.")
        if str(payload.get("sha256", "")).lower() != expected["sha256"]:
            raise ReleaseBundleError("Archived WireGuard bootstrap manifest does not match the pinned checksum.")
        if _sha256_bytes(archive.read(installer_archive_name)) != expected["sha256"]:
            raise ReleaseBundleError("Archived WireGuard bootstrap payload checksum does not match the pinned manifest.")


def _validate_amneziawg_payload_from_stage(stage_dir: Path, manifest: dict[str, object]) -> None:
    payload = _amneziawg_windows_runtime(manifest)
    for relpath, expected_sha in payload["files"].items():
        file_path = stage_dir / Path(relpath.as_posix())
        if not file_path.exists():
            raise ReleaseBundleError(f"Missing staged AmneziaWG runtime payload: {file_path}")
        if _sha256_path(file_path) != expected_sha:
            raise ReleaseBundleError(
                f"Staged AmneziaWG runtime payload checksum does not match the pinned manifest: {relpath.as_posix()}"
            )


def _validate_amneziawg_payload_from_archive(archive_path: Path, manifest: dict[str, object]) -> None:
    payload = _amneziawg_windows_runtime(manifest)
    with zipfile.ZipFile(archive_path) as archive:
        names = [name for name in archive.namelist() if name and not name.endswith("/")]
        if not names:
            raise ReleaseBundleError(f"Release archive is empty: {archive_path}")
        prefix = ""
        prefixes = {PurePosixPath(name).parts[0] for name in names if len(PurePosixPath(name).parts) > 1}
        if len(prefixes) == 1:
            prefix = next(iter(prefixes)) + "/"
        for relpath, expected_sha in payload["files"].items():
            archive_name = prefix + relpath.as_posix()
            if archive_name not in names:
                raise ReleaseBundleError(f"Missing AmneziaWG runtime payload inside archive: {archive_name}")
            if _sha256_bytes(archive.read(archive_name)) != expected_sha:
                raise ReleaseBundleError(
                    "Archived AmneziaWG runtime payload checksum does not match the pinned manifest: "
                    + relpath.as_posix()
                )


def validate_release_stage(*, platform_name: str, stage_dir: Path) -> None:
    manifest = load_runtime_manifest()
    actual = _stage_files(stage_dir)
    required = set(_stage_required_relpaths(platform_name))
    missing = sorted(required - actual)
    disallowed = sorted(path for path in actual if _is_disallowed(platform_name, path))
    if missing:
        raise ReleaseBundleError("Missing required staged files:\n" + "\n".join(path.as_posix() for path in missing))
    if disallowed:
        raise ReleaseBundleError("Staged release contains wrong-platform payloads:\n" + "\n".join(path.as_posix() for path in disallowed))
    if platform_name == "windows":
        _validate_wireguard_bootstrap_from_stage(stage_dir, manifest)
        _validate_amneziawg_payload_from_stage(stage_dir, manifest)


def validate_release_archive(*, platform_name: str, archive_path: Path) -> None:
    manifest = load_runtime_manifest()
    actual = _zip_files(archive_path)
    required = set(_stage_required_relpaths(platform_name))
    missing = sorted(required - actual)
    disallowed = sorted(path for path in actual if _is_disallowed(platform_name, path))
    if missing:
        raise ReleaseBundleError("Release archive is missing required files:\n" + "\n".join(path.as_posix() for path in missing))
    if disallowed:
        raise ReleaseBundleError("Release archive contains wrong-platform payloads:\n" + "\n".join(path.as_posix() for path in disallowed))
    if platform_name == "windows":
        _validate_wireguard_bootstrap_from_archive(archive_path, manifest)
        _validate_amneziawg_payload_from_archive(archive_path, manifest)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy and validate ProxyVault release payloads.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    copy_parser = subparsers.add_parser("copy-payload")
    copy_parser.add_argument("--platform", choices=("windows", "macos"), required=True)
    copy_parser.add_argument("--stage-dir", required=True)

    validate_stage_parser = subparsers.add_parser("validate-stage")
    validate_stage_parser.add_argument("--platform", choices=("windows", "macos"), required=True)
    validate_stage_parser.add_argument("--stage-dir", required=True)

    validate_archive_parser = subparsers.add_parser("validate-archive")
    validate_archive_parser.add_argument("--platform", choices=("windows", "macos"), required=True)
    validate_archive_parser.add_argument("--archive-path", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "copy-payload":
            copy_release_payload(platform_name=args.platform, stage_dir=Path(args.stage_dir))
        elif args.command == "validate-stage":
            validate_release_stage(platform_name=args.platform, stage_dir=Path(args.stage_dir))
        elif args.command == "validate-archive":
            validate_release_archive(platform_name=args.platform, archive_path=Path(args.archive_path))
        else:
            raise ReleaseBundleError(f"Unsupported command: {args.command}")
    except ReleaseBundleError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
