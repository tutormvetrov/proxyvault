from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol, Sequence

from app.runtime.enums import SessionStopReason, SystemProxyState
from app.runtime.models import RunningSession
import subprocess


class SystemProxyCommandError(RuntimeError):
    """Raised when ProxyVault cannot apply or clear the system proxy."""


@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(self, command: Sequence[str]) -> CommandResult: ...


class SubprocessCommandRunner:
    def run(self, command: Sequence[str]) -> CommandResult:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class SystemProxyBackend(Protocol):
    def apply(self, endpoint: ProxyEndpoint) -> None: ...

    def clear(self) -> None: ...


class NoopSystemProxyController:
    def apply_primary_proxy(self, session: RunningSession) -> SystemProxyState:
        if session.http_port is None:
            return SystemProxyState.ERROR
        return SystemProxyState.APPLIED

    def clear_system_proxy(self, *, reason: SessionStopReason) -> SystemProxyState:
        return SystemProxyState.CLEAR

    def shutdown(self) -> SystemProxyState | None:
        return SystemProxyState.CLEAR


class SystemProxyController:
    def __init__(self, backend: SystemProxyBackend) -> None:
        self._backend = backend
        self._current_endpoint: ProxyEndpoint | None = None
        self._current_session_id = ""

    def apply_primary_proxy(self, session: RunningSession) -> SystemProxyState:
        if session.http_port is None:
            return SystemProxyState.ERROR
        endpoint = ProxyEndpoint(host="127.0.0.1", port=session.http_port)
        try:
            self._backend.apply(endpoint)
        except Exception as exc:
            raise SystemProxyCommandError(str(exc)) from exc
        self._current_endpoint = endpoint
        self._current_session_id = session.session_id
        return SystemProxyState.APPLIED

    def clear_system_proxy(self, *, reason: SessionStopReason) -> SystemProxyState:
        try:
            self._backend.clear()
        except Exception as exc:
            raise SystemProxyCommandError(str(exc)) from exc
        self._current_endpoint = None
        self._current_session_id = ""
        return SystemProxyState.CLEAR

    def shutdown(self) -> SystemProxyState | None:
        if self._current_endpoint is None:
            return SystemProxyState.CLEAR
        return SystemProxyState.APPLIED


def create_system_proxy_controller(
    *,
    platform_name: str | None = None,
    runner: CommandRunner | None = None,
) -> SystemProxyController | NoopSystemProxyController:
    platform_key = (platform_name or sys.platform).lower()
    runner = runner or SubprocessCommandRunner()
    if platform_key.startswith("win"):
        from app.runtime.routing.windows import WindowsSystemProxyBackend

        return SystemProxyController(WindowsSystemProxyBackend(runner))
    if platform_key == "darwin":
        from app.runtime.routing.macos import MacOSSystemProxyBackend

        return SystemProxyController(MacOSSystemProxyBackend(runner))
    return NoopSystemProxyController()
