from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from app.models import utc_now_iso
from app.runtime.enums import (
    RouteOwnerKind,
    RuntimeEngineKind,
    RuntimeState,
    SessionStopReason,
    SystemProxyState,
)


def new_session_id() -> str:
    return str(uuid4())


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> str:
    return "" if value is None else str(value)


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _coerce_enum(enum_type: type, value: Any, default: Enum) -> Enum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class RuntimePrefs:
    entry_id: str = ""
    auto_launch: bool = False
    preferred_primary: bool = False
    http_port_override: int | None = None
    socks_port_override: int | None = None
    last_used_at: str = ""
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "auto_launch": self.auto_launch,
            "preferred_primary": self.preferred_primary,
            "http_port_override": self.http_port_override,
            "socks_port_override": self.socks_port_override,
            "last_used_at": self.last_used_at,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RuntimePrefs":
        payload = payload or {}
        return cls(
            entry_id=_coerce_str(payload.get("entry_id")),
            auto_launch=_coerce_bool(payload.get("auto_launch")),
            preferred_primary=_coerce_bool(payload.get("preferred_primary")),
            http_port_override=_coerce_int(payload.get("http_port_override")),
            socks_port_override=_coerce_int(payload.get("socks_port_override")),
            last_used_at=_coerce_str(payload.get("last_used_at")),
            last_error=_coerce_str(payload.get("last_error")),
        )


@dataclass(slots=True)
class LaunchSpec:
    session_id: str = field(default_factory=new_session_id)
    entry_id: str = ""
    engine_kind: RuntimeEngineKind = RuntimeEngineKind.UNSUPPORTED
    route_owner_kind: RouteOwnerKind = RouteOwnerKind.NONE
    requested_primary: bool = False
    resolved_primary: bool = False
    http_port: int | None = None
    socks_port: int | None = None
    config_path: str = ""
    log_path: str = ""
    working_dir: str = ""
    display_name: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "entry_id": self.entry_id,
            "engine_kind": self.engine_kind.value,
            "route_owner_kind": self.route_owner_kind.value,
            "requested_primary": self.requested_primary,
            "resolved_primary": self.resolved_primary,
            "http_port": self.http_port,
            "socks_port": self.socks_port,
            "config_path": self.config_path,
            "log_path": self.log_path,
            "working_dir": self.working_dir,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LaunchSpec":
        payload = payload or {}
        return cls(
            session_id=_coerce_str(payload.get("session_id")) or new_session_id(),
            entry_id=_coerce_str(payload.get("entry_id")),
            engine_kind=_coerce_enum(
                RuntimeEngineKind,
                payload.get("engine_kind"),
                RuntimeEngineKind.UNSUPPORTED,
            ),
            route_owner_kind=_coerce_enum(
                RouteOwnerKind,
                payload.get("route_owner_kind"),
                RouteOwnerKind.NONE,
            ),
            requested_primary=_coerce_bool(payload.get("requested_primary")),
            resolved_primary=_coerce_bool(payload.get("resolved_primary")),
            http_port=_coerce_int(payload.get("http_port")),
            socks_port=_coerce_int(payload.get("socks_port")),
            config_path=_coerce_str(payload.get("config_path")),
            log_path=_coerce_str(payload.get("log_path")),
            working_dir=_coerce_str(payload.get("working_dir")),
            display_name=_coerce_str(payload.get("display_name")),
            created_at=_coerce_str(payload.get("created_at")) or utc_now_iso(),
            metadata=_coerce_mapping(payload.get("metadata")),
        )


@dataclass(slots=True)
class RunningSession:
    session_id: str = field(default_factory=new_session_id)
    entry_id: str = ""
    entry_name: str = ""
    engine_kind: RuntimeEngineKind = RuntimeEngineKind.UNSUPPORTED
    runtime_state: RuntimeState = RuntimeState.DISCONNECTED
    route_owner_kind: RouteOwnerKind = RouteOwnerKind.NONE
    is_primary: bool = False
    http_port: int | None = None
    socks_port: int | None = None
    pid: int | None = None
    handle: str = ""
    started_at: str = ""
    stopped_at: str = ""
    last_activity_at: str = ""
    last_handshake_at: str = ""
    latency_ms: int | None = None
    exit_code: int | None = None
    failure_reason: str = ""
    last_error: str = ""
    log_excerpt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.runtime_state in {
            RuntimeState.STARTING,
            RuntimeState.RUNNING,
            RuntimeState.STOPPING,
        }

    @property
    def is_terminal(self) -> bool:
        return self.runtime_state in {RuntimeState.DISCONNECTED, RuntimeState.ERROR}

    @property
    def pid_or_handle(self) -> str:
        if self.pid is not None:
            return str(self.pid)
        return self.handle

    @property
    def local_http_url(self) -> str:
        if self.http_port is None:
            return ""
        return f"http://127.0.0.1:{self.http_port}"

    @property
    def local_socks_url(self) -> str:
        if self.socks_port is None:
            return ""
        return f"socks5://127.0.0.1:{self.socks_port}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "entry_id": self.entry_id,
            "entry_name": self.entry_name,
            "engine_kind": self.engine_kind.value,
            "runtime_state": self.runtime_state.value,
            "route_owner_kind": self.route_owner_kind.value,
            "is_primary": self.is_primary,
            "http_port": self.http_port,
            "socks_port": self.socks_port,
            "pid": self.pid,
            "handle": self.handle,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "last_activity_at": self.last_activity_at,
            "last_handshake_at": self.last_handshake_at,
            "latency_ms": self.latency_ms,
            "exit_code": self.exit_code,
            "failure_reason": self.failure_reason,
            "last_error": self.last_error,
            "log_excerpt": self.log_excerpt,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RunningSession":
        payload = payload or {}
        return cls(
            session_id=_coerce_str(payload.get("session_id")) or new_session_id(),
            entry_id=_coerce_str(payload.get("entry_id")),
            entry_name=_coerce_str(payload.get("entry_name")),
            engine_kind=_coerce_enum(
                RuntimeEngineKind,
                payload.get("engine_kind"),
                RuntimeEngineKind.UNSUPPORTED,
            ),
            runtime_state=_coerce_enum(
                RuntimeState,
                payload.get("runtime_state"),
                RuntimeState.DISCONNECTED,
            ),
            route_owner_kind=_coerce_enum(
                RouteOwnerKind,
                payload.get("route_owner_kind"),
                RouteOwnerKind.NONE,
            ),
            is_primary=_coerce_bool(payload.get("is_primary")),
            http_port=_coerce_int(payload.get("http_port")),
            socks_port=_coerce_int(payload.get("socks_port")),
            pid=_coerce_int(payload.get("pid")),
            handle=_coerce_str(payload.get("handle")),
            started_at=_coerce_str(payload.get("started_at")),
            stopped_at=_coerce_str(payload.get("stopped_at")),
            last_activity_at=_coerce_str(payload.get("last_activity_at")),
            last_handshake_at=_coerce_str(payload.get("last_handshake_at")),
            latency_ms=_coerce_int(payload.get("latency_ms")),
            exit_code=_coerce_int(payload.get("exit_code")),
            failure_reason=_coerce_str(payload.get("failure_reason")),
            last_error=_coerce_str(payload.get("last_error")),
            log_excerpt=_coerce_str(payload.get("log_excerpt")),
            metadata=_coerce_mapping(payload.get("metadata")),
        )

    def to_history_record(self, *, log_path: str = "") -> "SessionHistoryRecord":
        return SessionHistoryRecord.from_session(self, log_path=log_path)


@dataclass(slots=True)
class RuntimeSnapshot:
    sessions: list[RunningSession] = field(default_factory=list)
    primary_session_id: str = ""
    route_owner_kind: RouteOwnerKind = RouteOwnerKind.NONE
    system_proxy_state: SystemProxyState = SystemProxyState.CLEAR
    system_proxy_entry_id: str = ""
    wireguard_session_id: str = ""
    updated_at: str = field(default_factory=utc_now_iso)

    @property
    def active_session_count(self) -> int:
        return len(self.sessions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": [session.to_dict() for session in self.sessions],
            "primary_session_id": self.primary_session_id,
            "route_owner_kind": self.route_owner_kind.value,
            "system_proxy_state": self.system_proxy_state.value,
            "system_proxy_entry_id": self.system_proxy_entry_id,
            "wireguard_session_id": self.wireguard_session_id,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RuntimeSnapshot":
        payload = payload or {}
        return cls(
            sessions=[
                RunningSession.from_dict(session_payload)
                for session_payload in payload.get("sessions", [])
            ],
            primary_session_id=_coerce_str(payload.get("primary_session_id")),
            route_owner_kind=_coerce_enum(
                RouteOwnerKind,
                payload.get("route_owner_kind"),
                RouteOwnerKind.NONE,
            ),
            system_proxy_state=_coerce_enum(
                SystemProxyState,
                payload.get("system_proxy_state"),
                SystemProxyState.CLEAR,
            ),
            system_proxy_entry_id=_coerce_str(payload.get("system_proxy_entry_id")),
            wireguard_session_id=_coerce_str(payload.get("wireguard_session_id")),
            updated_at=_coerce_str(payload.get("updated_at")) or utc_now_iso(),
        )


@dataclass(slots=True)
class SessionHistoryRecord:
    session_id: str = ""
    entry_id: str = ""
    entry_name: str = ""
    engine_kind: str = RuntimeEngineKind.UNSUPPORTED.value
    state: str = RuntimeState.DISCONNECTED.value
    primary_flag: bool = False
    route_owner_kind: str = RouteOwnerKind.NONE.value
    http_port: int | None = None
    socks_port: int | None = None
    pid_or_handle: str = ""
    started_at: str = ""
    stopped_at: str = ""
    latency_ms: int | None = None
    last_handshake_at: str = ""
    last_activity_at: str = ""
    exit_code: int | None = None
    failure_reason: str = ""
    short_log_excerpt: str = ""
    log_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "entry_id": self.entry_id,
            "entry_name": self.entry_name,
            "engine_kind": self.engine_kind,
            "state": self.state,
            "primary_flag": self.primary_flag,
            "route_owner_kind": self.route_owner_kind,
            "http_port": self.http_port,
            "socks_port": self.socks_port,
            "pid_or_handle": self.pid_or_handle,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "latency_ms": self.latency_ms,
            "last_handshake_at": self.last_handshake_at,
            "last_activity_at": self.last_activity_at,
            "exit_code": self.exit_code,
            "failure_reason": self.failure_reason,
            "short_log_excerpt": self.short_log_excerpt,
            "log_path": self.log_path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "SessionHistoryRecord":
        payload = payload or {}
        return cls(
            session_id=_coerce_str(payload.get("session_id")),
            entry_id=_coerce_str(payload.get("entry_id")),
            entry_name=_coerce_str(payload.get("entry_name")),
            engine_kind=_coerce_str(payload.get("engine_kind")) or RuntimeEngineKind.UNSUPPORTED.value,
            state=_coerce_str(payload.get("state")) or RuntimeState.DISCONNECTED.value,
            primary_flag=_coerce_bool(payload.get("primary_flag")),
            route_owner_kind=_coerce_str(payload.get("route_owner_kind")) or RouteOwnerKind.NONE.value,
            http_port=_coerce_int(payload.get("http_port")),
            socks_port=_coerce_int(payload.get("socks_port")),
            pid_or_handle=_coerce_str(payload.get("pid_or_handle")),
            started_at=_coerce_str(payload.get("started_at")),
            stopped_at=_coerce_str(payload.get("stopped_at")),
            latency_ms=_coerce_int(payload.get("latency_ms")),
            last_handshake_at=_coerce_str(payload.get("last_handshake_at")),
            last_activity_at=_coerce_str(payload.get("last_activity_at")),
            exit_code=_coerce_int(payload.get("exit_code")),
            failure_reason=_coerce_str(payload.get("failure_reason")),
            short_log_excerpt=_coerce_str(payload.get("short_log_excerpt")),
            log_path=_coerce_str(payload.get("log_path")),
        )

    @classmethod
    def from_session(cls, session: RunningSession, *, log_path: str = "") -> "SessionHistoryRecord":
        return cls(
            session_id=session.session_id,
            entry_id=session.entry_id,
            entry_name=session.entry_name,
            engine_kind=session.engine_kind.value,
            state=session.runtime_state.value,
            primary_flag=session.is_primary,
            route_owner_kind=session.route_owner_kind.value,
            http_port=session.http_port,
            socks_port=session.socks_port,
            pid_or_handle=session.pid_or_handle,
            started_at=session.started_at,
            stopped_at=session.stopped_at,
            latency_ms=session.latency_ms,
            last_handshake_at=session.last_handshake_at,
            last_activity_at=session.last_activity_at,
            exit_code=session.exit_code,
            failure_reason=session.failure_reason,
            short_log_excerpt=session.log_excerpt,
            log_path=log_path,
        )


@dataclass(slots=True)
class RuntimeHumanStatus:
    entry_id: str = ""
    session_id: str = ""
    tone: str = "muted"
    title_key: str = "runtime.state.disconnected"
    summary_key: str = "runtime.summary.disconnected"
    params: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "session_id": self.session_id,
            "tone": self.tone,
            "title_key": self.title_key,
            "summary_key": self.summary_key,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RuntimeHumanStatus":
        payload = payload or {}
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        return cls(
            entry_id=_coerce_str(payload.get("entry_id")),
            session_id=_coerce_str(payload.get("session_id")),
            tone=_coerce_str(payload.get("tone")) or "muted",
            title_key=_coerce_str(payload.get("title_key")) or "runtime.state.disconnected",
            summary_key=_coerce_str(payload.get("summary_key")) or "runtime.summary.disconnected",
            params={str(key): _coerce_str(value) for key, value in params.items()},
        )
