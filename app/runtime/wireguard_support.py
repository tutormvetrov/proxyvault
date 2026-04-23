from __future__ import annotations

import configparser
import hashlib
import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

from app.models import ProxyEntry, ProxyType, utc_now_iso
from app.runtime.enums import RouteOwnerKind, RuntimeEngineKind, RuntimeState, SessionStopReason
from app.runtime.models import LaunchSpec, RunningSession, RuntimePrefs, new_session_id
from app.runtime.paths import runtime_generated_dir, runtime_logs_dir


WIREGUARD_FAILURE_PRIVILEGES_REQUIRED = "runtime.error.wireguard.privileges_required"
WIREGUARD_FAILURE_HELPER_NOT_FOUND = "runtime.error.wireguard.helper_not_found"
WIREGUARD_FAILURE_BUNDLE_INCOMPLETE = "runtime.error.wireguard.bundle_incomplete"
WIREGUARD_FAILURE_SYSTEM_PROMPT_DENIED = "runtime.error.wireguard.system_prompt_denied"
WIREGUARD_FAILURE_INVALID_CONFIG = "runtime.error.wireguard.invalid_config"
WIREGUARD_FAILURE_HANDSHAKE_MISSING = "runtime.error.wireguard.handshake_missing"
WIREGUARD_FAILURE_TUNNEL_EXITED_EARLY = "runtime.error.wireguard.tunnel_exited_early"
WIREGUARD_FAILURE_SYSTEM_CONFLICT = "runtime.error.wireguard.system_conflict"

WIREGUARD_WARNING_SYSTEM_PROMPT = "runtime.warning.wireguard.system_prompt_expected"
WIREGUARD_WARNING_WINDOWS_ELEVATION = "runtime.warning.wireguard.windows_elevation_possible"
WIREGUARD_WARNING_MACOS_UNSIGNED = "runtime.warning.wireguard.macos_unsigned_build_check"

WIREGUARD_META_PLATFORM = "wireguard_platform"
WIREGUARD_META_TUNNEL_NAME = "wireguard_tunnel_name"
WIREGUARD_META_HELPER_PATH = "wireguard_helper_path"
WIREGUARD_META_CONFIG_PATH = "wireguard_config_path"
WIREGUARD_META_LOG_PATH = "wireguard_log_path"
WIREGUARD_META_WARNING_CODES = "wireguard_warning_codes"

_RAW_REASON_MAP = {
    "privileges_required": WIREGUARD_FAILURE_PRIVILEGES_REQUIRED,
    "permission_denied": WIREGUARD_FAILURE_PRIVILEGES_REQUIRED,
    "helper_not_found": WIREGUARD_FAILURE_HELPER_NOT_FOUND,
    "bundle_incomplete": WIREGUARD_FAILURE_BUNDLE_INCOMPLETE,
    "system_prompt_denied": WIREGUARD_FAILURE_SYSTEM_PROMPT_DENIED,
    "prompt_denied": WIREGUARD_FAILURE_SYSTEM_PROMPT_DENIED,
    "invalid_config": WIREGUARD_FAILURE_INVALID_CONFIG,
    "handshake_missing": WIREGUARD_FAILURE_HANDSHAKE_MISSING,
    "tunnel_exited_early": WIREGUARD_FAILURE_TUNNEL_EXITED_EARLY,
    "service_conflict": WIREGUARD_FAILURE_SYSTEM_CONFLICT,
}

_TERMINAL_STATES = {RuntimeState.DISCONNECTED, RuntimeState.ERROR}


@dataclass(slots=True)
class WireGuardRuntimeAssets:
    helper_path: Path
    generated_dir: Path
    logs_dir: Path


@dataclass(slots=True)
class WireGuardCommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class WireGuardCommandRunner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> WireGuardCommandResult: ...


class WireGuardAssetLocator(Protocol):
    def locate(self) -> WireGuardRuntimeAssets: ...


class SubprocessWireGuardCommandRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> WireGuardCommandResult:
        completed = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return WireGuardCommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class WireGuardAdapterError(RuntimeError):
    def __init__(
        self,
        failure_reason: str,
        *,
        last_error: str = "",
        log_excerpt: str = "",
        exit_code: int | None = None,
        warning_codes: Sequence[str] | None = None,
    ) -> None:
        super().__init__(last_error or failure_reason)
        self.failure_reason = failure_reason
        self.last_error = last_error
        self.log_excerpt = log_excerpt
        self.exit_code = exit_code
        self.warning_codes = tuple(_coerce_warning_codes(warning_codes))


@dataclass(slots=True)
class WireGuardProfile:
    raw_config: str
    interface_address: str
    private_key: str
    public_key: str
    endpoint: str
    allowed_ips: str
    dns: str = ""
    mtu: str = ""


@dataclass(slots=True)
class WireGuardStatus:
    runtime_state: RuntimeState
    handle: str = ""
    pid: int | None = None
    last_activity_at: str = ""
    last_handshake_at: str = ""
    exit_code: int | None = None
    failure_reason: str = ""
    last_error: str = ""
    log_excerpt: str = ""
    warning_codes: tuple[str, ...] = field(default_factory=tuple)


class WireGuardAdapterBase:
    engine_kind: RuntimeEngineKind = RuntimeEngineKind.UNSUPPORTED
    expected_platform: str = ""
    platform_slug: str = ""
    prepare_warning_codes: tuple[str, ...] = ()
    start_flags: tuple[str, ...] = ()
    supported_types: tuple[ProxyType, ...] = (ProxyType.WIREGUARD,)
    protocol_label: str = "WireGuard"

    def __init__(
        self,
        *,
        runner: WireGuardCommandRunner | None = None,
        asset_locator: WireGuardAssetLocator,
        platform_name: str | None = None,
    ) -> None:
        self._runner = runner or SubprocessWireGuardCommandRunner()
        self._asset_locator = asset_locator
        self._platform_name = platform_name or platform.system()

    def supports(self, entry: ProxyEntry) -> bool:
        return entry.type in self.supported_types and self._platform_name == self.expected_platform

    def prepare_launch(
        self,
        entry: ProxyEntry,
        prefs: RuntimePrefs,
        *,
        make_primary: bool,
    ) -> LaunchSpec:
        del prefs
        del make_primary

        profile = load_wireguard_profile(
            entry,
            expected_types=self.supported_types,
            protocol_label=self.protocol_label,
        )
        assets = self._asset_locator.locate()
        session_id = new_session_id()
        tunnel_name = self._build_tunnel_name(entry, session_id)
        config_path = assets.generated_dir / f"{tunnel_name}.conf"
        log_path = assets.logs_dir / f"{tunnel_name}.log"
        write_wireguard_config(config_path, profile.raw_config)
        ensure_log_file(log_path)

        metadata = build_wireguard_metadata(
            platform_slug=self.platform_slug,
            tunnel_name=tunnel_name,
            helper_path=assets.helper_path,
            config_path=config_path,
            log_path=log_path,
            warning_codes=self.prepare_warning_codes,
        )
        return LaunchSpec(
            session_id=session_id,
            entry_id=entry.id,
            engine_kind=self.engine_kind,
            route_owner_kind=RouteOwnerKind.WIREGUARD,
            requested_primary=False,
            resolved_primary=False,
            http_port=None,
            socks_port=None,
            config_path=str(config_path),
            log_path=str(log_path),
            working_dir=str(assets.generated_dir),
            display_name=entry.name,
            created_at=utc_now_iso(),
            metadata=metadata,
        )

    def start(self, launch_spec: LaunchSpec) -> RunningSession:
        command = self._build_up_command(launch_spec)
        result = self._runner.run(command, cwd=Path(launch_spec.working_dir))
        status = status_from_command_result(
            result,
            default_state=RuntimeState.RUNNING,
            default_reason=WIREGUARD_FAILURE_TUNNEL_EXITED_EARLY,
        )
        session = RunningSession(
            session_id=launch_spec.session_id,
            entry_id=launch_spec.entry_id,
            entry_name=launch_spec.display_name,
            engine_kind=self.engine_kind,
            runtime_state=status.runtime_state,
            route_owner_kind=RouteOwnerKind.WIREGUARD,
            is_primary=False,
            handle=status.handle or str(launch_spec.metadata.get(WIREGUARD_META_TUNNEL_NAME, "")),
            pid=status.pid,
            started_at=launch_spec.created_at,
            last_activity_at=status.last_activity_at or launch_spec.created_at,
            last_handshake_at=status.last_handshake_at,
            exit_code=status.exit_code,
            failure_reason=status.failure_reason,
            last_error=status.last_error,
            log_excerpt=status.log_excerpt,
            metadata=merge_wireguard_metadata(launch_spec.metadata, status.warning_codes),
        )
        if not session.log_excerpt:
            session.log_excerpt = self.read_log_excerpt(session, max_lines=20)
        return session

    def stop(self, session: RunningSession, *, reason: SessionStopReason) -> RunningSession:
        del reason
        handle = str(
            session.handle
            or session.metadata.get(WIREGUARD_META_TUNNEL_NAME, "")
        ).strip()
        if handle:
            command = self._build_down_command(session, handle)
            result = self._runner.run(command, cwd=_session_working_dir(session))
            status = status_from_command_result(
                result,
                default_state=RuntimeState.DISCONNECTED,
                default_reason=WIREGUARD_FAILURE_TUNNEL_EXITED_EARLY,
            )
            warning_codes = status.warning_codes
            last_error = status.last_error
            failure_reason = status.failure_reason
            exit_code = status.exit_code
        else:
            warning_codes = ()
            last_error = ""
            failure_reason = ""
            exit_code = 0

        updated = RunningSession.from_dict(session.to_dict())
        updated.runtime_state = RuntimeState.DISCONNECTED
        updated.route_owner_kind = RouteOwnerKind.NONE
        updated.is_primary = False
        updated.stopped_at = utc_now_iso()
        updated.last_activity_at = updated.stopped_at
        updated.exit_code = 0 if exit_code is None else exit_code
        updated.failure_reason = failure_reason
        updated.last_error = last_error
        updated.metadata = merge_wireguard_metadata(updated.metadata, warning_codes)
        updated.log_excerpt = self.read_log_excerpt(updated, max_lines=20)
        return updated

    def poll(self, session: RunningSession) -> RunningSession:
        handle = str(
            session.handle
            or session.metadata.get(WIREGUARD_META_TUNNEL_NAME, "")
        ).strip()
        if not handle:
            return RunningSession.from_dict(session.to_dict())

        command = self._build_status_command(session, handle)
        result = self._runner.run(command, cwd=_session_working_dir(session))
        status = status_from_command_result(
            result,
            default_state=RuntimeState.RUNNING,
            default_reason=WIREGUARD_FAILURE_TUNNEL_EXITED_EARLY,
        )

        updated = RunningSession.from_dict(session.to_dict())
        updated.runtime_state = status.runtime_state
        updated.route_owner_kind = (
            RouteOwnerKind.WIREGUARD if status.runtime_state not in _TERMINAL_STATES else RouteOwnerKind.NONE
        )
        updated.handle = status.handle or updated.handle
        updated.pid = status.pid if status.pid is not None else updated.pid
        updated.last_activity_at = status.last_activity_at or utc_now_iso()
        updated.last_handshake_at = status.last_handshake_at or updated.last_handshake_at
        updated.exit_code = status.exit_code
        updated.failure_reason = status.failure_reason
        updated.last_error = status.last_error
        updated.metadata = merge_wireguard_metadata(updated.metadata, status.warning_codes)
        updated.log_excerpt = status.log_excerpt or self.read_log_excerpt(updated, max_lines=20)
        if updated.runtime_state in _TERMINAL_STATES and not updated.stopped_at:
            updated.stopped_at = utc_now_iso()
        return updated

    def read_log_excerpt(self, session: RunningSession, max_lines: int) -> str:
        log_path = _session_log_path(session)
        if log_path is None:
            return ""
        return read_log_excerpt(log_path, max_lines=max_lines)

    def _build_up_command(self, launch_spec: LaunchSpec) -> list[str]:
        helper_path = str(launch_spec.metadata[WIREGUARD_META_HELPER_PATH])
        tunnel_name = str(launch_spec.metadata[WIREGUARD_META_TUNNEL_NAME])
        return [
            helper_path,
            "up",
            "--config",
            launch_spec.config_path,
            "--log",
            launch_spec.log_path,
            "--tunnel-name",
            tunnel_name,
            *self.start_flags,
        ]

    def _build_tunnel_name(self, entry: ProxyEntry, session_id: str) -> str:
        return build_tunnel_name(
            entry.id or entry.name,
            session_id,
            engine_kind=self.engine_kind,
        )

    def _build_down_command(self, session: RunningSession, handle: str) -> list[str]:
        helper_path = str(session.metadata[WIREGUARD_META_HELPER_PATH])
        command = [
            helper_path,
            "down",
            "--handle",
            handle,
            *self.start_flags,
        ]
        config_path = session.metadata.get(WIREGUARD_META_CONFIG_PATH)
        if isinstance(config_path, str) and config_path:
            command.extend(["--config", config_path])
        log_path = session.metadata.get(WIREGUARD_META_LOG_PATH)
        if isinstance(log_path, str) and log_path:
            command.extend(["--log", log_path])
        return command

    def _build_status_command(self, session: RunningSession, handle: str) -> list[str]:
        helper_path = str(session.metadata[WIREGUARD_META_HELPER_PATH])
        command = [
            helper_path,
            "status",
            "--handle",
            handle,
        ]
        config_path = session.metadata.get(WIREGUARD_META_CONFIG_PATH)
        if isinstance(config_path, str) and config_path:
            command.extend(["--config", config_path])
        log_path = session.metadata.get(WIREGUARD_META_LOG_PATH)
        if isinstance(log_path, str) and log_path:
            command.extend(["--log", log_path])
        return command


def build_tunnel_name(
    entry_id: str,
    session_id: str,
    *,
    engine_kind: RuntimeEngineKind | str | None = None,
) -> str:
    if _uses_short_amneziawg_name(engine_kind):
        return _build_short_amneziawg_tunnel_name(entry_id, session_id)
    entry_token = sanitize_runtime_name(entry_id)[:24]
    session_token = sanitize_runtime_name(session_id)[:12]
    return f"proxyvault-{entry_token}-{session_token}".strip("-")


def _uses_short_amneziawg_name(engine_kind: RuntimeEngineKind | str | None) -> bool:
    if isinstance(engine_kind, RuntimeEngineKind):
        return engine_kind == RuntimeEngineKind.AMNEZIAWG_WINDOWS
    return str(engine_kind or "").strip().upper() == RuntimeEngineKind.AMNEZIAWG_WINDOWS.value


def _build_short_amneziawg_tunnel_name(entry_id: str, session_id: str) -> str:
    del session_id
    entry_token = _stable_hex_token(entry_id, 8)
    return f"pvawg-{entry_token}"


def _stable_hex_token(value: str, length: int) -> str:
    digest = hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()
    return digest[:length]


def sanitize_runtime_name(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    sanitized = sanitized.strip(".-")
    return sanitized or "wireguard"


def build_wireguard_metadata(
    *,
    platform_slug: str,
    tunnel_name: str,
    helper_path: Path,
    config_path: Path,
    log_path: Path,
    warning_codes: Sequence[str],
) -> dict[str, Any]:
    return {
        WIREGUARD_META_PLATFORM: platform_slug,
        WIREGUARD_META_TUNNEL_NAME: tunnel_name,
        WIREGUARD_META_HELPER_PATH: str(helper_path),
        WIREGUARD_META_CONFIG_PATH: str(config_path),
        WIREGUARD_META_LOG_PATH: str(log_path),
        WIREGUARD_META_WARNING_CODES: list(_coerce_warning_codes(warning_codes)),
    }


def merge_wireguard_metadata(existing: dict[str, Any], warning_codes: Sequence[str] | None) -> dict[str, Any]:
    metadata = dict(existing or {})
    merged_warning_codes = list(
        dict.fromkeys(
            [
                *_coerce_warning_codes(metadata.get(WIREGUARD_META_WARNING_CODES)),
                *_coerce_warning_codes(warning_codes),
            ]
        )
    )
    metadata[WIREGUARD_META_WARNING_CODES] = merged_warning_codes
    return metadata


def load_wireguard_profile(
    entry: ProxyEntry,
    *,
    expected_types: Sequence[ProxyType] | None = None,
    protocol_label: str = "WireGuard",
) -> WireGuardProfile:
    raw_uri = entry.uri.strip()
    if not raw_uri:
        raise WireGuardAdapterError(
            WIREGUARD_FAILURE_INVALID_CONFIG,
            last_error=f"Raw {protocol_label} profile is unavailable for this entry.",
            log_excerpt=f"Raw {protocol_label} profile is unavailable for this entry.",
        )

    if expected_types and entry.type not in expected_types:
        raise WireGuardAdapterError(
            WIREGUARD_FAILURE_INVALID_CONFIG,
            last_error=f"{protocol_label} adapter cannot launch entries of type {entry.type.value}.",
            log_excerpt=f"{protocol_label} adapter cannot launch entries of type {entry.type.value}.",
        )

    parser = configparser.ConfigParser(strict=False)
    parser.optionxform = str
    try:
        parser.read_string(raw_uri)
    except configparser.Error as exc:
        raise WireGuardAdapterError(
            WIREGUARD_FAILURE_INVALID_CONFIG,
            last_error=str(exc),
            log_excerpt=str(exc),
        ) from exc

    if not parser.has_section("Interface"):
        raise WireGuardAdapterError(
            WIREGUARD_FAILURE_INVALID_CONFIG,
            last_error=f"{protocol_label} config is missing the [Interface] section.",
            log_excerpt=f"{protocol_label} config is missing the [Interface] section.",
        )
    if not parser.has_section("Peer"):
        raise WireGuardAdapterError(
            WIREGUARD_FAILURE_INVALID_CONFIG,
            last_error=f"{protocol_label} config is missing the [Peer] section.",
            log_excerpt=f"{protocol_label} config is missing the [Peer] section.",
        )

    interface = parser["Interface"]
    peer = parser["Peer"]
    private_key = str(interface.get("PrivateKey", "")).strip()
    address = str(interface.get("Address", "")).strip()
    public_key = str(peer.get("PublicKey", "")).strip()
    allowed_ips = str(peer.get("AllowedIPs", "")).strip()
    endpoint = str(peer.get("Endpoint", "")).strip()

    required_pairs = {
        "Interface.PrivateKey": private_key,
        "Interface.Address": address,
        "Peer.PublicKey": public_key,
        "Peer.AllowedIPs": allowed_ips,
        "Peer.Endpoint": endpoint,
    }
    missing_fields = [name for name, value in required_pairs.items() if not value]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise WireGuardAdapterError(
            WIREGUARD_FAILURE_INVALID_CONFIG,
            last_error=f"{protocol_label} config is missing required fields: {missing}.",
            log_excerpt=f"{protocol_label} config is missing required fields: {missing}.",
        )

    normalized_raw = raw_uri
    if not normalized_raw.endswith("\n"):
        normalized_raw += "\n"

    return WireGuardProfile(
        raw_config=normalized_raw,
        interface_address=address,
        private_key=private_key,
        public_key=public_key,
        endpoint=endpoint,
        allowed_ips=allowed_ips,
        dns=str(interface.get("DNS", "")).strip(),
        mtu=str(interface.get("MTU", "")).strip(),
    )


def ensure_log_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    _apply_private_permissions(path)


def write_wireguard_config(path: Path, raw_config: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw_config, encoding="utf-8")
    _apply_private_permissions(path)


def read_log_excerpt(path: Path, *, max_lines: int) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = [line.rstrip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-max(max_lines, 1) :])


def status_from_command_result(
    result: WireGuardCommandResult,
    *,
    default_state: RuntimeState,
    default_reason: str,
) -> WireGuardStatus:
    payload = _parse_command_payload(result.stdout)
    message = _first_text(
        payload.get("last_error"),
        payload.get("log_excerpt"),
        result.stderr,
        result.stdout,
    )
    warning_codes = tuple(_coerce_warning_codes(payload.get("warning_codes")))
    if result.exit_code != 0:
        raise WireGuardAdapterError(
            normalize_wireguard_failure_reason(
                payload.get("failure_reason") or payload.get("reason_code"),
                message,
                default_reason=default_reason,
            ),
            last_error=message,
            log_excerpt=_first_text(payload.get("log_excerpt"), message),
            exit_code=result.exit_code,
            warning_codes=warning_codes,
        )

    runtime_state = _coerce_runtime_state(payload.get("runtime_state"), default_state)
    failure_reason = normalize_wireguard_failure_reason(
        payload.get("failure_reason") or payload.get("reason_code"),
        message,
        default_reason="" if runtime_state not in _TERMINAL_STATES else default_reason,
    )
    last_error = _first_text(payload.get("last_error"), result.stderr)
    log_excerpt = _first_text(payload.get("log_excerpt"), result.stderr)
    exit_code = _coerce_int(payload.get("exit_code"))
    if runtime_state in _TERMINAL_STATES and not failure_reason and (last_error or log_excerpt or exit_code not in (None, 0)):
        failure_reason = normalize_wireguard_failure_reason("", last_error or log_excerpt, default_reason=default_reason)

    return WireGuardStatus(
        runtime_state=runtime_state,
        handle=_coerce_str(payload.get("handle") or payload.get("tunnel_name")),
        pid=_coerce_int(payload.get("pid")),
        last_activity_at=_coerce_str(payload.get("last_activity_at")),
        last_handshake_at=_coerce_str(payload.get("last_handshake_at")),
        exit_code=exit_code,
        failure_reason=failure_reason,
        last_error=last_error,
        log_excerpt=log_excerpt,
        warning_codes=warning_codes,
    )


def normalize_wireguard_failure_reason(reason_code: Any, message: str, *, default_reason: str) -> str:
    reason_text = _coerce_str(reason_code).strip()
    lowered = message.lower()
    if (
        any(
            token in lowered
            for token in (
                "already exists",
                "file already exists",
                "object already exists",
                "the object already exists",
                "cannot create a file",
                "невозможно создать файл",
                "win32_exit_code    : 5010",
                "win32 exit code    : 5010",
                "win32_exit_code: 5010",
                "win32 exit code: 5010",
            )
        )
        and any(
            token in lowered
            for token in (
                "split tunnel",
                "amneziawg",
                "amneziawgtunnel$",
                "service terminated with the following error",
            )
        )
    ):
        return WIREGUARD_FAILURE_SYSTEM_CONFLICT
    if reason_text in _RAW_REASON_MAP:
        return _RAW_REASON_MAP[reason_text]
    if reason_text in _RAW_REASON_MAP.values():
        return reason_text

    if any(token in lowered for token in ("access is denied", "administrator", "permission denied", "operation not permitted", "must be run as root")):
        return WIREGUARD_FAILURE_PRIVILEGES_REQUIRED
    if any(token in lowered for token in ("authorization was canceled", "authorization cancelled", "user canceled", "user cancelled", "prompt denied")):
        return WIREGUARD_FAILURE_SYSTEM_PROMPT_DENIED
    if any(
        token in lowered
        for token in (
            "build is incomplete",
            "bundled wireguard",
            "bootstrap metadata is missing",
            "bootstrap payload is missing",
            "checksum mismatch",
            "hash mismatch",
            "wireguard bootstrap completed, but wireguard.exe is still unavailable",
        )
    ):
        return WIREGUARD_FAILURE_BUNDLE_INCOMPLETE
    if any(token in lowered for token in ("no such file", "not found", "unable to locate helper", "missing helper", "cannot find the file")):
        return WIREGUARD_FAILURE_HELPER_NOT_FOUND
    if (
        any(
            token in lowered
            for token in (
                "already exists",
                "file already exists",
                "object already exists",
                "the object already exists",
                "cannot create a file",
                "невозможно создать файл",
                "win32_exit_code    : 5010",
                "win32 exit code    : 5010",
                "win32_exit_code: 5010",
                "win32 exit code: 5010",
            )
        )
        and any(
            token in lowered
            for token in (
                "split tunnel",
                "amneziawg",
                "amneziawgtunnel$",
                "service terminated with the following error",
            )
        )
    ):
        return WIREGUARD_FAILURE_SYSTEM_CONFLICT
    if any(token in lowered for token in ("invalid config", "parse error", "privatekey", "publickey", "allowedips", "endpoint", "[interface]", "[peer]")):
        return WIREGUARD_FAILURE_INVALID_CONFIG
    if any(token in lowered for token in ("handshake not established", "handshake missing", "no handshake")):
        return WIREGUARD_FAILURE_HANDSHAKE_MISSING
    if any(token in lowered for token in ("exited immediately", "terminated immediately", "tunnel exited", "closed immediately")):
        return WIREGUARD_FAILURE_TUNNEL_EXITED_EARLY
    return default_reason


def _parse_command_payload(stdout: str) -> dict[str, Any]:
    payload_text = stdout.strip()
    if not payload_text:
        return {}
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return {"log_excerpt": payload_text}
    if isinstance(payload, dict):
        return payload
    return {"log_excerpt": payload_text}


def _coerce_runtime_state(value: Any, default: RuntimeState) -> RuntimeState:
    if isinstance(value, RuntimeState):
        return value
    try:
        return RuntimeState(str(value).upper())
    except ValueError:
        pass
    normalized = str(value or "").strip().lower()
    mapping = {
        "running": RuntimeState.RUNNING,
        "starting": RuntimeState.STARTING,
        "stopping": RuntimeState.STOPPING,
        "disconnected": RuntimeState.DISCONNECTED,
        "stopped": RuntimeState.DISCONNECTED,
        "error": RuntimeState.ERROR,
        "failed": RuntimeState.ERROR,
    }
    return mapping.get(normalized, default)


def _coerce_warning_codes(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Sequence):
        values = list(value)
    else:
        return []
    cleaned: list[str] = []
    for item in values:
        text = str(item).strip()
        if not text or text in cleaned:
            continue
        cleaned.append(text)
    return cleaned


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> str:
    return "" if value is None else str(value)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _coerce_str(value).strip()
        if text:
            return text
    return ""


def _session_log_path(session: RunningSession) -> Path | None:
    log_path = session.metadata.get(WIREGUARD_META_LOG_PATH)
    if not isinstance(log_path, str) or not log_path:
        return None
    return Path(log_path)


def _session_working_dir(session: RunningSession) -> Path:
    log_path = _session_log_path(session)
    if log_path is not None:
        return log_path.parent
    return runtime_generated_dir()


def _apply_private_permissions(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        return
