from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.models import (
    AppSettings,
    ProxyEntry,
    ProxyType,
    ReachabilityCheck,
    ReachabilityState,
    SubscriptionRecord,
    utc_now_iso,
)
from app.paths import HOME_APP_DIR, default_db_path, default_qr_output_dir, is_portable_runtime, resolve_app_dir
from app.parser import parse_proxy_text


DEFAULT_APP_DIR = resolve_app_dir()
DEFAULT_DB_PATH = default_db_path()
ENTRY_SELECT_COLUMNS = """
    id, name, uri_plaintext, uri_encrypted, uri_nonce, uri_fingerprint, type, transport,
    server_host, server_port, tags, notes, qr_png_path, created_at, updated_at, is_favorite,
    expiry_date, reachability_status, reachability_checked_at, reachability_latency_ms,
    reachability_duration_ms, reachability_method, reachability_endpoint,
    reachability_failure_reason, reachability_error_category, reachability_details,
    reachability_config_fingerprint
"""


def apply_private_path_permissions(path: Path, *, directory: bool) -> None:
    if os.name != "posix":
        return
    try:
        os.chmod(path, 0o700 if directory else 0o600)
    except OSError:
        return


def harden_private_storage_paths(app_dir: Path, *file_paths: Path) -> None:
    if os.name != "posix":
        return
    try:
        app_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    apply_private_path_permissions(app_dir, directory=True)
    for file_path in file_paths:
        if file_path.exists():
            apply_private_path_permissions(file_path, directory=False)


class DatabaseInitError(RuntimeError):
    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class AuthenticationError(ValueError):
    pass


class DatabaseManager:
    PBKDF2_ROUNDS = 600_000

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._harden_storage_permissions()
        self._connection = self._connect()
        self._session_key: bytes | None = None
        self._initialize()
        self._harden_storage_permissions()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.db_path)
        except sqlite3.DatabaseError as exc:
            raise DatabaseInitError("Unable to open the ProxyVault database.", exc) from exc
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        try:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    uri_plaintext TEXT,
                    uri_encrypted BLOB,
                    uri_nonce BLOB,
                    uri_fingerprint TEXT NOT NULL,
                    type TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    server_host TEXT NOT NULL,
                    server_port INTEGER,
                    tags TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    qr_png_path TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_favorite INTEGER NOT NULL DEFAULT 0,
                    expiry_date TEXT NOT NULL DEFAULT '',
                    reachability_status TEXT NOT NULL DEFAULT 'NOT_TESTED',
                    reachability_checked_at TEXT NOT NULL DEFAULT '',
                    reachability_latency_ms INTEGER,
                    reachability_duration_ms INTEGER,
                    reachability_method TEXT NOT NULL DEFAULT '',
                    reachability_endpoint TEXT NOT NULL DEFAULT '',
                    reachability_failure_reason TEXT NOT NULL DEFAULT '',
                    reachability_error_category TEXT NOT NULL DEFAULT '',
                    reachability_details TEXT NOT NULL DEFAULT '',
                    reachability_config_fingerprint TEXT NOT NULL DEFAULT ''
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_fingerprint
                    ON entries (uri_fingerprint);

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL UNIQUE,
                    refresh_interval TEXT NOT NULL DEFAULT 'never',
                    last_fetched TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reachability_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    method TEXT NOT NULL DEFAULT 'TCP probe',
                    endpoint TEXT NOT NULL DEFAULT '',
                    latency_ms INTEGER,
                    duration_ms INTEGER,
                    failure_reason TEXT NOT NULL DEFAULT '',
                    error_category TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '',
                    config_fingerprint TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_reachability_checks_entry_id
                    ON reachability_checks (entry_id, checked_at DESC);
                """
            )
            self._ensure_entry_columns()
            self._commit()
        except sqlite3.DatabaseError as exc:
            raise DatabaseInitError("ProxyVault could not initialize its database schema.", exc) from exc

    def _table_columns(self, table_name: str) -> set[str]:
        rows = self._connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_entry_columns(self) -> None:
        columns = self._table_columns("entries")
        required_columns = {
            "reachability_status": "TEXT NOT NULL DEFAULT 'NOT_TESTED'",
            "reachability_checked_at": "TEXT NOT NULL DEFAULT ''",
            "reachability_latency_ms": "INTEGER",
            "reachability_duration_ms": "INTEGER",
            "reachability_method": "TEXT NOT NULL DEFAULT ''",
            "reachability_endpoint": "TEXT NOT NULL DEFAULT ''",
            "reachability_failure_reason": "TEXT NOT NULL DEFAULT ''",
            "reachability_error_category": "TEXT NOT NULL DEFAULT ''",
            "reachability_details": "TEXT NOT NULL DEFAULT ''",
            "reachability_config_fingerprint": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, definition in required_columns.items():
            if column_name in columns:
                continue
            self._connection.execute(f"ALTER TABLE entries ADD COLUMN {column_name} {definition}")

    def _harden_storage_permissions(self, *extra_paths: Path) -> None:
        harden_private_storage_paths(self.db_path.parent, self.db_path, *extra_paths)

    def _commit(self) -> None:
        self._connection.commit()
        self._harden_storage_permissions()

    @property
    def is_locked(self) -> bool:
        return self.has_master_password() and self._session_key is None

    def backup_and_reset(self) -> Path:
        timestamp = utc_now_iso().replace(":", "-")
        backup_path = self.db_path.with_name(f"{self.db_path.stem}.backup-{timestamp}.db")
        self.close()
        shutil.copy2(self.db_path, backup_path)
        self._harden_storage_permissions(backup_path)
        self.db_path.unlink(missing_ok=True)
        self._connection = self._connect()
        self._initialize()
        self._harden_storage_permissions(backup_path)
        return backup_path

    def close(self) -> None:
        self._connection.close()

    def _set_setting(self, key: str, value: str) -> None:
        self._connection.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._commit()

    def _get_setting(self, key: str, default: str = "") -> str:
        row = self._connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row else default

    def set_metadata(self, key: str, value: str) -> None:
        self._set_setting(f"meta::{key}", value)

    def get_metadata(self, key: str, default: str = "") -> str:
        return self._get_setting(f"meta::{key}", default)

    def load_settings(self) -> AppSettings:
        raw = self._get_setting("app_settings", "")
        if not raw:
            settings = AppSettings.default()
            self.save_settings(settings)
            return settings
        settings = AppSettings.from_dict(json.loads(raw))
        normalized = self._normalize_runtime_settings(settings)
        if normalized.to_dict() != settings.to_dict():
            self.save_settings(normalized)
        return normalized

    def save_settings(self, settings: AppSettings) -> None:
        self._set_setting("app_settings", json.dumps(self._normalize_runtime_settings(settings).to_dict()))

    def _normalize_runtime_settings(self, settings: AppSettings) -> AppSettings:
        if not is_portable_runtime():
            return settings
        portable_output = default_qr_output_dir()
        current_output = Path(settings.output_folder).expanduser() if settings.output_folder else portable_output
        if not settings.output_folder or not current_output.exists():
            settings.output_folder = str(portable_output)
        return settings

    def has_master_password(self) -> bool:
        return bool(self._get_setting("master_salt"))

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.PBKDF2_ROUNDS,
        )
        return kdf.derive(password.encode("utf-8"))

    def _key_hash(self, key: bytes) -> str:
        return hashlib.sha256(key).hexdigest()

    def unlock(self, password: str) -> None:
        salt_b64 = self._get_setting("master_salt")
        expected = self._get_setting("master_key_hash")
        if not salt_b64 or not expected:
            self._session_key = None
            return
        salt = base64.b64decode(salt_b64.encode("ascii"))
        key = self._derive_key(password, salt)
        if self._key_hash(key) != expected:
            raise AuthenticationError("Incorrect master password")
        self._session_key = key

    def lock(self) -> None:
        self._session_key = None

    def set_master_password(self, password: str, current_password: str = "") -> None:
        previous_entries = self.list_entries(include_uri=True)
        if self.has_master_password():
            if self.is_locked:
                self.unlock(current_password)
            elif current_password:
                self.unlock(current_password)
        salt = os.urandom(16)
        key = self._derive_key(password, salt)
        self._set_setting("master_salt", base64.b64encode(salt).decode("ascii"))
        self._set_setting("master_key_hash", self._key_hash(key))
        self._session_key = key
        self._rewrite_entry_uris(previous_entries)

    def change_master_password(self, current_password: str, new_password: str) -> None:
        self.unlock(current_password)
        entries = self.list_entries(include_uri=True)
        salt = os.urandom(16)
        key = self._derive_key(new_password, salt)
        self._set_setting("master_salt", base64.b64encode(salt).decode("ascii"))
        self._set_setting("master_key_hash", self._key_hash(key))
        self._session_key = key
        self._rewrite_entry_uris(entries)

    def remove_master_password(self, current_password: str = "") -> None:
        if self.has_master_password():
            if self.is_locked:
                self.unlock(current_password)
            elif current_password:
                self.unlock(current_password)
        entries = self.list_entries(include_uri=True)
        self._connection.execute(
            "DELETE FROM settings WHERE key IN ('master_salt', 'master_key_hash')"
        )
        self._commit()
        self._session_key = None
        self._rewrite_entry_uris(entries)

    def _rewrite_entry_uris(self, entries: list[ProxyEntry]) -> None:
        for entry in entries:
            self.save_entry(entry)

    def _fingerprint(self, uri: str) -> str:
        return hashlib.sha256(uri.encode("utf-8")).hexdigest()

    def _encrypt_uri(self, uri: str) -> tuple[bytes | None, bytes | None, str | None]:
        if not self.has_master_password():
            return None, None, uri
        if self._session_key is None:
            raise AuthenticationError("Unlock ProxyVault before saving encrypted entries")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._session_key).encrypt(nonce, uri.encode("utf-8"), None)
        return ciphertext, nonce, None

    def _decrypt_uri(self, row: sqlite3.Row) -> str:
        plaintext = row["uri_plaintext"]
        if plaintext is not None:
            return str(plaintext)
        if self._session_key is None:
            raise AuthenticationError("Unlock ProxyVault to access encrypted URIs")
        ciphertext = row["uri_encrypted"]
        nonce = row["uri_nonce"]
        if ciphertext is None or nonce is None:
            return ""
        return AESGCM(self._session_key).decrypt(bytes(nonce), bytes(ciphertext), None).decode("utf-8")

    def _row_to_entry(self, row: sqlite3.Row, include_uri: bool = False) -> ProxyEntry:
        uri = ""
        is_locked = False
        if include_uri:
            try:
                uri = self._decrypt_uri(row)
            except AuthenticationError:
                is_locked = True
        else:
            is_locked = row["uri_encrypted"] is not None and row["uri_plaintext"] is None
        return ProxyEntry(
            id=str(row["id"]),
            name=str(row["name"]),
            uri=uri,
            type=ProxyType(str(row["type"])),
            transport=str(row["transport"]),
            server_host=str(row["server_host"]),
            server_port=row["server_port"],
            tags=str(row["tags"]),
            notes=str(row["notes"]),
            qr_png_path=str(row["qr_png_path"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            is_favorite=bool(row["is_favorite"]),
            expiry_date=str(row["expiry_date"]),
            is_locked=is_locked,
            uri_fingerprint=str(row["uri_fingerprint"]),
            reachability_status=ReachabilityState(str(row["reachability_status"] or ReachabilityState.NOT_TESTED.value)),
            reachability_checked_at=str(row["reachability_checked_at"]),
            reachability_latency_ms=row["reachability_latency_ms"],
            reachability_duration_ms=row["reachability_duration_ms"],
            reachability_method=str(row["reachability_method"]),
            reachability_endpoint=str(row["reachability_endpoint"]),
            reachability_failure_reason=str(row["reachability_failure_reason"]),
            reachability_error_category=str(row["reachability_error_category"]),
            reachability_details=str(row["reachability_details"]),
            reachability_config_fingerprint=str(row["reachability_config_fingerprint"]),
        )

    def list_entries(self, include_uri: bool = False) -> list[ProxyEntry]:
        rows = self._connection.execute(
            """
            SELECT
            """
            + ENTRY_SELECT_COLUMNS
            + """
            FROM entries
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [self._row_to_entry(row, include_uri=include_uri) for row in rows]

    def get_entry(self, entry_id: str, include_uri: bool = True) -> ProxyEntry | None:
        row = self._connection.execute(
            """
            SELECT
            """
            + ENTRY_SELECT_COLUMNS
            + """
            FROM entries
            WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_entry(row, include_uri=include_uri)

    def save_entry(self, entry: ProxyEntry) -> ProxyEntry:
        if not entry.id:
            entry.id = str(uuid.uuid4())
        now = utc_now_iso()
        if not entry.created_at:
            entry.created_at = now
        entry.updated_at = now
        fingerprint = self._fingerprint(entry.uri)
        existing = self.get_entry(entry.id, include_uri=False) if entry.id else None
        if existing:
            if not entry.reachability_checked_at and existing.reachability_checked_at:
                entry.reachability_status = existing.reachability_status
                entry.reachability_checked_at = existing.reachability_checked_at
                entry.reachability_latency_ms = existing.reachability_latency_ms
                entry.reachability_duration_ms = existing.reachability_duration_ms
                entry.reachability_method = existing.reachability_method
                entry.reachability_endpoint = existing.reachability_endpoint
                entry.reachability_failure_reason = existing.reachability_failure_reason
                entry.reachability_error_category = existing.reachability_error_category
                entry.reachability_details = existing.reachability_details
                entry.reachability_config_fingerprint = (
                    existing.reachability_config_fingerprint or existing.uri_fingerprint
                )
        entry.uri_fingerprint = fingerprint
        ciphertext, nonce, plaintext = self._encrypt_uri(entry.uri)
        self._connection.execute(
            """
            INSERT INTO entries (
                id, name, uri_plaintext, uri_encrypted, uri_nonce, uri_fingerprint, type,
                transport, server_host, server_port, tags, notes, qr_png_path,
                created_at, updated_at, is_favorite, expiry_date, reachability_status,
                reachability_checked_at, reachability_latency_ms, reachability_duration_ms,
                reachability_method, reachability_endpoint, reachability_failure_reason,
                reachability_error_category, reachability_details, reachability_config_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                uri_plaintext = excluded.uri_plaintext,
                uri_encrypted = excluded.uri_encrypted,
                uri_nonce = excluded.uri_nonce,
                uri_fingerprint = excluded.uri_fingerprint,
                type = excluded.type,
                transport = excluded.transport,
                server_host = excluded.server_host,
                server_port = excluded.server_port,
                tags = excluded.tags,
                notes = excluded.notes,
                qr_png_path = excluded.qr_png_path,
                updated_at = excluded.updated_at,
                is_favorite = excluded.is_favorite,
                expiry_date = excluded.expiry_date,
                reachability_status = excluded.reachability_status,
                reachability_checked_at = excluded.reachability_checked_at,
                reachability_latency_ms = excluded.reachability_latency_ms,
                reachability_duration_ms = excluded.reachability_duration_ms,
                reachability_method = excluded.reachability_method,
                reachability_endpoint = excluded.reachability_endpoint,
                reachability_failure_reason = excluded.reachability_failure_reason,
                reachability_error_category = excluded.reachability_error_category,
                reachability_details = excluded.reachability_details,
                reachability_config_fingerprint = excluded.reachability_config_fingerprint
            """,
            (
                entry.id,
                entry.name,
                plaintext,
                ciphertext,
                nonce,
                fingerprint,
                entry.type.value,
                entry.transport,
                entry.server_host,
                entry.server_port,
                entry.tags,
                entry.notes,
                entry.qr_png_path,
                entry.created_at,
                entry.updated_at,
                int(entry.is_favorite),
                entry.expiry_date,
                entry.reachability_status.value,
                entry.reachability_checked_at,
                entry.reachability_latency_ms,
                entry.reachability_duration_ms,
                entry.reachability_method,
                entry.reachability_endpoint,
                entry.reachability_failure_reason,
                entry.reachability_error_category,
                entry.reachability_details,
                entry.reachability_config_fingerprint,
            ),
        )
        self._commit()
        return entry

    def delete_entry(self, entry_id: str) -> ProxyEntry | None:
        entry = self.get_entry(entry_id, include_uri=not self.is_locked)
        self._connection.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        self._commit()
        return entry

    def find_by_uri(self, uri: str) -> ProxyEntry | None:
        row = self._connection.execute(
            """
            SELECT
            """
            + ENTRY_SELECT_COLUMNS
            + """
            FROM entries
            WHERE uri_fingerprint = ?
            """,
            (self._fingerprint(uri),),
        ).fetchone()
        if not row:
            return None
        return self._row_to_entry(row, include_uri=not self.is_locked)

    def record_reachability_check(self, entry_id: str, result: ReachabilityCheck) -> None:
        entry = self.get_entry(entry_id, include_uri=False)
        if not entry:
            return
        config_fingerprint = result.config_fingerprint or entry.uri_fingerprint
        self._connection.execute(
            """
            INSERT INTO reachability_checks (
                entry_id, checked_at, status, method, endpoint, latency_ms, duration_ms,
                failure_reason, error_category, details, config_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                result.checked_at,
                result.status.value,
                result.method,
                result.endpoint,
                result.latency_ms,
                result.duration_ms,
                result.failure_reason,
                result.error_category,
                result.details,
                config_fingerprint,
            ),
        )
        self._connection.execute(
            """
            UPDATE entries
            SET reachability_status = ?,
                reachability_checked_at = ?,
                reachability_latency_ms = ?,
                reachability_duration_ms = ?,
                reachability_method = ?,
                reachability_endpoint = ?,
                reachability_failure_reason = ?,
                reachability_error_category = ?,
                reachability_details = ?,
                reachability_config_fingerprint = ?
            WHERE id = ?
            """,
            (
                result.status.value,
                result.checked_at,
                result.latency_ms,
                result.duration_ms,
                result.method,
                result.endpoint,
                result.failure_reason,
                result.error_category,
                result.details,
                config_fingerprint,
                entry_id,
            ),
        )
        self._commit()

    def list_reachability_checks(self, entry_id: str, limit: int = 5) -> list[ReachabilityCheck]:
        rows = self._connection.execute(
            """
            SELECT id, checked_at, status, method, endpoint, latency_ms, duration_ms,
                   failure_reason, error_category, details, config_fingerprint
            FROM reachability_checks
            WHERE entry_id = ?
            ORDER BY checked_at DESC
            LIMIT ?
            """,
            (entry_id, limit),
        ).fetchall()
        return [
            ReachabilityCheck(
                id=int(row["id"]),
                checked_at=str(row["checked_at"]),
                status=ReachabilityState(str(row["status"])),
                method=str(row["method"]),
                endpoint=str(row["endpoint"]),
                latency_ms=row["latency_ms"],
                duration_ms=row["duration_ms"],
                failure_reason=str(row["failure_reason"]),
                error_category=str(row["error_category"]),
                details=str(row["details"]),
                config_fingerprint=str(row["config_fingerprint"]),
            )
            for row in rows
        ]

    def save_subscription(self, url: str, refresh_interval: str) -> SubscriptionRecord:
        record = SubscriptionRecord(
            id=str(uuid.uuid4()),
            url=url,
            refresh_interval=refresh_interval,
            created_at=utc_now_iso(),
            last_fetched=utc_now_iso(),
        )
        self._connection.execute(
            """
            INSERT INTO subscriptions (id, url, refresh_interval, last_fetched, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                refresh_interval = excluded.refresh_interval,
                last_fetched = excluded.last_fetched
            """,
            (record.id, record.url, record.refresh_interval, record.last_fetched, record.created_at),
        )
        self._commit()
        row = self._connection.execute(
            "SELECT id, url, refresh_interval, last_fetched, created_at FROM subscriptions WHERE url = ?",
            (url,),
        ).fetchone()
        return SubscriptionRecord(
            id=str(row["id"]),
            url=str(row["url"]),
            refresh_interval=str(row["refresh_interval"]),
            last_fetched=str(row["last_fetched"]),
            created_at=str(row["created_at"]),
        )

    def list_subscriptions(self) -> list[SubscriptionRecord]:
        rows = self._connection.execute(
            "SELECT id, url, refresh_interval, last_fetched, created_at FROM subscriptions ORDER BY created_at DESC"
        ).fetchall()
        return [
            SubscriptionRecord(
                id=str(row["id"]),
                url=str(row["url"]),
                refresh_interval=str(row["refresh_interval"]),
                last_fetched=str(row["last_fetched"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def update_subscription_fetch_time(self, url: str) -> None:
        self._connection.execute(
            "UPDATE subscriptions SET last_fetched = ? WHERE url = ?",
            (utc_now_iso(), url),
        )
        self._commit()

    def upsert_parsed_entry(
        self,
        *,
        name: str,
        uri: str,
        tags: str = "",
        notes: str = "",
        expiry_date: str = "",
        is_favorite: bool = False,
        qr_png_path: str = "",
        existing_id: str = "",
    ) -> ProxyEntry:
        parsed = parse_proxy_text(uri)
        entry = ProxyEntry(
            id=existing_id or str(uuid.uuid4()),
            name=name or parsed.display_name or parsed.server_host or parsed.type.value,
            uri=uri,
            type=parsed.type,
            transport=parsed.transport,
            server_host=parsed.server_host,
            server_port=parsed.server_port,
            tags=tags,
            notes=notes,
            qr_png_path=qr_png_path,
            expiry_date=expiry_date,
            is_favorite=is_favorite,
        )
        existing = self.find_by_uri(uri)
        if existing and not existing_id:
            entry.id = existing.id
            entry.created_at = existing.created_at
            entry.uri_fingerprint = existing.uri_fingerprint
            entry.reachability_status = existing.reachability_status
            entry.reachability_checked_at = existing.reachability_checked_at
            entry.reachability_latency_ms = existing.reachability_latency_ms
            entry.reachability_duration_ms = existing.reachability_duration_ms
            entry.reachability_method = existing.reachability_method
            entry.reachability_endpoint = existing.reachability_endpoint
            entry.reachability_failure_reason = existing.reachability_failure_reason
            entry.reachability_error_category = existing.reachability_error_category
            entry.reachability_details = existing.reachability_details
            entry.reachability_config_fingerprint = existing.reachability_config_fingerprint
        return self.save_entry(entry)

    def update_entry_metadata(
        self,
        entry_id: str,
        *,
        name: str,
        tags: str,
        notes: str,
        expiry_date: str,
        is_favorite: bool,
    ) -> None:
        self._connection.execute(
            """
            UPDATE entries
            SET name = ?, tags = ?, notes = ?, expiry_date = ?, is_favorite = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, tags, notes, expiry_date, int(is_favorite), utc_now_iso(), entry_id),
        )
        self._commit()
