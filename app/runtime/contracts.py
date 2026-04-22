from __future__ import annotations

from typing import Protocol

from app.models import ProxyEntry
from app.runtime.enums import RuntimeEngineKind, SessionStopReason, SystemProxyState
from app.runtime.models import LaunchSpec, RunningSession, RuntimePrefs


class EngineAdapter(Protocol):
    engine_kind: RuntimeEngineKind

    def supports(self, entry: ProxyEntry) -> bool: ...

    def prepare_launch(
        self,
        entry: ProxyEntry,
        prefs: RuntimePrefs,
        *,
        make_primary: bool,
    ) -> LaunchSpec: ...

    def start(self, launch_spec: LaunchSpec) -> RunningSession: ...

    def stop(self, session: RunningSession, *, reason: SessionStopReason) -> RunningSession: ...

    def poll(self, session: RunningSession) -> RunningSession: ...

    def read_log_excerpt(self, session: RunningSession, max_lines: int) -> str: ...


class RuntimeRouteController(Protocol):
    def apply_primary_proxy(self, session: RunningSession) -> SystemProxyState: ...

    def clear_system_proxy(self, *, reason: SessionStopReason) -> SystemProxyState: ...

    def shutdown(self) -> SystemProxyState | None: ...
