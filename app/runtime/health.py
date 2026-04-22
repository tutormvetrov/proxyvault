from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from app.models import utc_now_iso
from app.runtime.enums import RuntimeState
from app.runtime.models import RunningSession


TIMESTAMP_PATTERN = re.compile(
    r"(?P<stamp>\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2})"
)
LATENCY_PATTERN = re.compile(r"\[(?:\d+\s+)?(?P<latency>\d+)ms\]")

START_MARKERS = ("sing-box started",)
ACTIVITY_MARKERS = ("inbound/", "outbound/", "router:", "connection", "packet connection")
HANDSHAKE_MARKERS = ("handshake", "reality", "authenticated", "connected")


@dataclass(frozen=True, slots=True)
class HealthSignals:
    started: bool = False
    last_activity_at: str = ""
    last_handshake_at: str = ""
    latency_ms: int | None = None
    failure_reason: str = ""
    last_error: str = ""


def extract_health_signals(log_text: str) -> HealthSignals:
    started = False
    last_activity_at = ""
    last_handshake_at = ""
    latency_ms: int | None = None
    last_error = ""
    failure_reason = ""

    for raw_line in log_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        timestamp = extract_log_timestamp(line)
        latency = extract_log_latency(line)
        if latency is not None:
            latency_ms = latency

        if any(marker in lowered for marker in START_MARKERS):
            started = True
            if timestamp:
                last_activity_at = timestamp

        if any(marker in lowered for marker in ACTIVITY_MARKERS) and timestamp:
            last_activity_at = timestamp

        if any(marker in lowered for marker in HANDSHAKE_MARKERS):
            if timestamp:
                last_handshake_at = timestamp
                last_activity_at = timestamp

        if _looks_like_error_line(lowered):
            last_error = line
            failure_reason = normalize_failure_reason(line)
            if timestamp:
                last_activity_at = timestamp

    return HealthSignals(
        started=started,
        last_activity_at=last_activity_at,
        last_handshake_at=last_handshake_at,
        latency_ms=latency_ms,
        failure_reason=failure_reason,
        last_error=last_error,
    )


def extract_log_timestamp(line: str) -> str:
    match = TIMESTAMP_PATTERN.search(line)
    if not match:
        return ""
    stamp = match.group("stamp").replace("/", "-").replace(" ", "T")
    try:
        return datetime.fromisoformat(stamp).replace(microsecond=0).isoformat()
    except ValueError:
        return ""


def extract_log_latency(line: str) -> int | None:
    match = LATENCY_PATTERN.search(line)
    if not match:
        return None
    try:
        return int(match.group("latency"))
    except (TypeError, ValueError):
        return None


def normalize_failure_reason(line: str) -> str:
    lowered = line.lower()
    if "address already in use" in lowered or "only one usage of each socket address" in lowered:
        return "runtime.error.port_in_use"
    if "authentication failed" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
        return "runtime.error.authentication_failed"
    if (
        "connection refused" in lowered
        or "timed out" in lowered
        or "timeout" in lowered
        or "deadline exceeded" in lowered
        or "no route to host" in lowered
        or "network is unreachable" in lowered
    ):
        return "runtime.error.server_unreachable"
    return "runtime.error.engine_crash"


def _looks_like_error_line(line: str) -> bool:
    if " error " in f" {line} " or line.startswith("error") or " fatal " in f" {line} ":
        return True
    return any(
        marker in line
        for marker in (
            "failed",
            "failure",
            "refused",
            "timed out",
            "timeout",
            "unauthorized",
            "forbidden",
        )
    )


def apply_health_to_session(
    session: RunningSession,
    *,
    log_text: str,
    exit_code: int | None = None,
) -> RunningSession:
    updated = RunningSession.from_dict(session.to_dict())
    signals = extract_health_signals(log_text)

    updated.log_excerpt = log_text
    if signals.last_activity_at:
        updated.last_activity_at = signals.last_activity_at
    elif updated.runtime_state in {RuntimeState.STARTING, RuntimeState.RUNNING} and not updated.last_activity_at:
        updated.last_activity_at = updated.started_at or utc_now_iso()
    if signals.last_handshake_at:
        updated.last_handshake_at = signals.last_handshake_at
    if signals.latency_ms is not None:
        updated.latency_ms = signals.latency_ms
    if signals.last_error:
        updated.last_error = signals.last_error
    if signals.failure_reason:
        updated.failure_reason = signals.failure_reason

    if exit_code is None:
        if signals.started:
            updated.runtime_state = RuntimeState.RUNNING
        elif updated.runtime_state == RuntimeState.DISCONNECTED:
            updated.runtime_state = RuntimeState.STARTING
        return updated

    updated.exit_code = exit_code
    updated.stopped_at = updated.stopped_at or signals.last_activity_at or utc_now_iso()
    if exit_code == 0:
        updated.runtime_state = RuntimeState.DISCONNECTED
        return updated

    updated.runtime_state = RuntimeState.ERROR
    if not updated.failure_reason:
        updated.failure_reason = "runtime.error.engine_crash"
    if not updated.last_error:
        updated.last_error = f"sing-box exited with code {exit_code}"
    return updated
