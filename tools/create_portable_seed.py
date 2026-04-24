from __future__ import annotations

import argparse
import getpass
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import AuthenticationError, DatabaseManager, harden_private_storage_paths
from app.paths import DB_FILENAME, QR_DIRNAME, default_db_path


class SeedBuildError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an encrypted portable-seed/proxyvault.db for private ProxyVault builds.",
    )
    parser.add_argument(
        "--source-db",
        type=Path,
        default=default_db_path(),
        help="Database to encrypt and copy. Defaults to the local ProxyVault database.",
    )
    parser.add_argument(
        "--from-git-head",
        action="store_true",
        help="Use portable-seed/proxyvault.db from the current Git HEAD as the source.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "portable-seed",
        help="Directory that will receive proxyvault.db.",
    )
    parser.add_argument(
        "--password",
        default="",
        help="New seed master password. Omit to enter it securely.",
    )
    parser.add_argument(
        "--current-password",
        default="",
        help="Current password if the source database is already encrypted. Omit to enter it securely.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing portable-seed/proxyvault.db.",
    )
    return parser.parse_args()


def _new_password(args: argparse.Namespace) -> str:
    if args.password:
        return str(args.password)
    password = getpass.getpass("New seed master password: ")
    confirm = getpass.getpass("Repeat seed master password: ")
    if password != confirm:
        raise SeedBuildError("Passwords do not match.")
    return password


def _current_password(args: argparse.Namespace) -> str:
    if args.current_password:
        return str(args.current_password)
    return getpass.getpass("Current source database password: ")


def _prepare_seed_database(source_db: Path, work_db: Path, password: str, args: argparse.Namespace) -> None:
    shutil.copy2(source_db, work_db)
    db = DatabaseManager(work_db)
    try:
        try:
            if db.has_master_password():
                db.change_master_password(_current_password(args), password)
            else:
                db.set_master_password(password)
        except AuthenticationError as exc:
            raise SeedBuildError("Current source database password is incorrect.") from exc

        db._connection.execute("UPDATE entries SET qr_png_path = ''")
        db._commit()
        plaintext_count = db._connection.execute(
            "SELECT COUNT(*) FROM entries WHERE uri_plaintext IS NOT NULL AND uri_plaintext != ''"
        ).fetchone()[0]
        if plaintext_count:
            raise SeedBuildError("Seed database still contains plaintext profile URIs.")
    finally:
        db.close()


def _write_git_head_seed(target_db: Path) -> None:
    result = subprocess.run(
        ["git", "show", f"HEAD:portable-seed/{DB_FILENAME}"],
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SeedBuildError(f"Git HEAD does not contain portable-seed/{DB_FILENAME}. {detail}")
    target_db.write_bytes(result.stdout)


def create_seed(args: argparse.Namespace) -> Path:
    source_db = args.source_db.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    target_db = output_dir / DB_FILENAME

    if target_db.exists() and not args.force:
        raise SeedBuildError(f"Target already exists, rerun with --force to overwrite: {target_db}")

    password = _new_password(args)
    if not password:
        raise SeedBuildError("Seed master password cannot be empty.")

    with tempfile.TemporaryDirectory(prefix="proxyvault-seed-") as tmp:
        if args.from_git_head:
            source_db = Path(tmp) / "git-head-source.db"
            _write_git_head_seed(source_db)
        if not source_db.exists():
            raise SeedBuildError(f"Source database does not exist: {source_db}")
        work_db = Path(tmp) / DB_FILENAME
        _prepare_seed_database(source_db, work_db, password, args)
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(work_db, target_db)

    qr_dir = output_dir / QR_DIRNAME
    if qr_dir.exists():
        shutil.rmtree(qr_dir)
    harden_private_storage_paths(output_dir, target_db)
    return target_db


def main() -> int:
    args = parse_args()
    try:
        target_db = create_seed(args)
    except SeedBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Created encrypted seed database: {target_db}")
    print("QR assets were not copied. The app regenerates QR previews after unlock.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
