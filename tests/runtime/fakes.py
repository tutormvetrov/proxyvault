from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from app.models import ProxyEntry, ProxyType, utc_now_iso
from app.runtime.enums import (
    RouteOwnerKind,
    RuntimeEngineKind,
    RuntimeState,
    SessionStopReason,
    SystemProxyState,
)
from app.runtime.models import LaunchSpec, RunningSession, RuntimePrefs


def make_entry(entry_id: str, proxy_type: ProxyType, *, name: str | None = None) -> ProxyEntry:
    port = 51820 if proxy_type in {ProxyType.WIREGUARD, ProxyType.AMNEZIAWG} else 443
    transport = "udp" if proxy_type in {ProxyType.WIREGUARD, ProxyType.AMNEZIAWG, ProxyType.HYSTERIA2} else "tcp"
    return ProxyEntry(
        id=entry_id,
        name=name or entry_id,
        uri=f"{proxy_type.value.lower()}://example",
        type=proxy_type,
        transport=transport,
        server_host=f"{entry_id}.example.com",
        server_port=port,
    )


class FakeRouteController:
    def __init__(
        self,
        *,
        apply_state: SystemProxyState = SystemProxyState.APPLIED,
        clear_state: SystemProxyState = SystemProxyState.CLEAR,
    ) -> None:
        self.apply_state = apply_state
        self.clear_state = clear_state
        self.apply_calls: list[str] = []
        self.clear_calls: list[SessionStopReason] = []
        self.shutdown_calls = 0

    def apply_primary_proxy(self, session: RunningSession) -> SystemProxyState:
        self.apply_calls.append(session.entry_id)
        return self.apply_state

    def clear_system_proxy(self, *, reason: SessionStopReason) -> SystemProxyState:
        self.clear_calls.append(reason)
        return self.clear_state

    def shutdown(self) -> SystemProxyState | None:
        self.shutdown_calls += 1
        return self.clear_state


class FakeAdapter:
    def __init__(
        self,
        *,
        engine_kind: RuntimeEngineKind,
        supported_types: Iterable[ProxyType],
        route_owner_kind: RouteOwnerKind,
        start_state: RuntimeState = RuntimeState.RUNNING,
    ) -> None:
        self.engine_kind = engine_kind
        self.supported_types = set(supported_types)
        self.route_owner_kind = route_owner_kind
        self.start_state = start_state
        self.prepared: list[LaunchSpec] = []
        self.stop_reasons: list[SessionStopReason] = []
        self.log_by_session_id: dict[str, str] = {}
        self.poll_updates: dict[str, RunningSession] = {}

    def supports(self, entry: ProxyEntry) -> bool:
        return entry.type in self.supported_types

    def prepare_launch(
        self,
        entry: ProxyEntry,
        prefs: RuntimePrefs,
        *,
        make_primary: bool,
    ) -> LaunchSpec:
        launch_spec = LaunchSpec(
            session_id=f"{entry.id}-session",
            entry_id=entry.id,
            engine_kind=self.engine_kind,
            route_owner_kind=self.route_owner_kind,
            requested_primary=make_primary,
            resolved_primary=make_primary,
            http_port=prefs.http_port_override or (8080 if self.route_owner_kind == RouteOwnerKind.PROXY else None),
            socks_port=prefs.socks_port_override or (1080 if self.route_owner_kind == RouteOwnerKind.PROXY else None),
            config_path=f"/tmp/{entry.id}.json",
            log_path=f"/tmp/{entry.id}.log",
            working_dir="/tmp",
            display_name=entry.name,
            created_at=utc_now_iso(),
        )
        self.prepared.append(launch_spec)
        self.log_by_session_id[launch_spec.session_id] = f"log:{entry.id}"
        return launch_spec

    def start(self, launch_spec: LaunchSpec) -> RunningSession:
        return RunningSession(
            session_id=launch_spec.session_id,
            entry_id=launch_spec.entry_id,
            entry_name=launch_spec.display_name,
            engine_kind=launch_spec.engine_kind,
            runtime_state=self.start_state,
            route_owner_kind=launch_spec.route_owner_kind,
            is_primary=launch_spec.resolved_primary,
            http_port=launch_spec.http_port,
            socks_port=launch_spec.socks_port,
            pid=1234,
            handle=launch_spec.session_id,
            started_at=launch_spec.created_at,
            last_activity_at=launch_spec.created_at,
            last_handshake_at=launch_spec.created_at,
        )

    def stop(self, session: RunningSession, *, reason: SessionStopReason) -> RunningSession:
        self.stop_reasons.append(reason)
        updated = replace(session)
        updated.runtime_state = RuntimeState.DISCONNECTED
        updated.stopped_at = utc_now_iso()
        updated.exit_code = 0
        return updated

    def poll(self, session: RunningSession) -> RunningSession:
        update = self.poll_updates.get(session.session_id)
        if update is None:
            return replace(session)
        return replace(update)

    def read_log_excerpt(self, session: RunningSession, max_lines: int) -> str:
        return self.log_by_session_id.get(session.session_id, "")[: max_lines * 64]

    def set_poll_terminal_error(
        self,
        session_id: str,
        *,
        failure_reason: str = "runtime.error.engine_crash",
        exit_code: int = 1,
    ) -> None:
        current = RunningSession(
            session_id=session_id,
            runtime_state=RuntimeState.ERROR,
            exit_code=exit_code,
            stopped_at=utc_now_iso(),
            failure_reason=failure_reason,
            last_error="fake crash",
        )
        self.poll_updates[session_id] = current
