from __future__ import annotations

import configparser
import socket
import ssl
import time
import urllib.request
from time import perf_counter
from typing import Sequence

from app.i18n import describe_human_error, normalize_human_error_code, tr
from app.models import ProxyEntry, ProxyType, ReachabilityCheck, ReachabilityState, utc_now_iso
from app.runtime.contracts import EngineAdapter
from app.runtime.enums import RuntimeEngineKind, RuntimeState, SessionStopReason
from app.runtime.models import LaunchSpec, RunningSession, RuntimePrefs
from app.runtime.wireguard_support import (
    WIREGUARD_FAILURE_HANDSHAKE_MISSING,
    WIREGUARD_META_LOG_PATH,
    WIREGUARD_META_WARNING_CODES,
    WIREGUARD_WARNING_HANDSHAKE_UNAVAILABLE,
)

_WIREGUARD_HANDSHAKE_TIMEOUT_SECONDS = 6.0
_AMNEZIAWG_HANDSHAKE_TIMEOUT_SECONDS = 20.0
_RUNTIME_HANDSHAKE_POLL_INTERVAL_SECONDS = 0.5
_RUNTIME_HANDSHAKE_TRAFFIC_INTERVAL_SECONDS = 1.5
_RUNTIME_TRIGGER_ENDPOINTS: tuple[tuple[str, int], ...] = (
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
)
_WIREGUARD_RUNTIME_TYPES = frozenset({ProxyType.WIREGUARD, ProxyType.AMNEZIAWG})
_SING_BOX_RUNTIME_TYPES = frozenset({ProxyType.HYSTERIA2})
_TERMINAL_RUNTIME_STATES = {RuntimeState.DISCONNECTED, RuntimeState.ERROR}
_DIAGNOSTIC_DNS_KEYS = ("DNS", "Dns", "dns")
_PROXY_TRIGGER_URLS: tuple[str, ...] = (
    "http://1.1.1.1/",
    "https://1.1.1.1/",
)


def run_entry_diagnostic(
    entry: ProxyEntry,
    *,
    adapters: Sequence[EngineAdapter] = (),
    active_session: RunningSession | None = None,
) -> ReachabilityCheck:
    if entry.reachability_supports_tcp_probe:
        return run_tcp_probe(entry)
    if entry.type in _WIREGUARD_RUNTIME_TYPES:
        return run_wireguard_runtime_probe(entry, adapters=adapters, active_session=active_session)
    if entry.type in _SING_BOX_RUNTIME_TYPES:
        return run_sing_box_runtime_probe(entry, adapters=adapters, active_session=active_session)
    return build_protocol_note(entry)


def run_tcp_probe(entry: ProxyEntry) -> ReachabilityCheck:
    checked_at = utc_now_iso()
    endpoint = entry.display_host_port
    if not entry.server_host or not entry.server_port:
        return ReachabilityCheck(
            checked_at=checked_at,
            status=ReachabilityState.FAILED,
            endpoint=endpoint,
            method=tr("reachability.method.tcp_probe"),
            failure_reason=tr("reachability.reason.failure_default"),
            error_category="unavailable",
            details=tr("toast.reachability.missing_endpoint", name=entry.name, endpoint=endpoint),
            config_fingerprint=entry.uri_fingerprint,
        )

    start = perf_counter()
    try:
        with socket.create_connection((entry.server_host, int(entry.server_port)), timeout=3):
            duration_ms = max(int((perf_counter() - start) * 1000), 1)
        return ReachabilityCheck(
            checked_at=checked_at,
            status=ReachabilityState.REACHABLE,
            endpoint=endpoint,
            method=tr("reachability.method.tcp_probe"),
            latency_ms=duration_ms,
            duration_ms=duration_ms,
            details=tr("toast.reachability.success_details", name=entry.name, endpoint=endpoint, duration=duration_ms),
            config_fingerprint=entry.uri_fingerprint,
        )
    except socket.timeout:
        duration_ms = max(int((perf_counter() - start) * 1000), 3000)
        return ReachabilityCheck(
            checked_at=checked_at,
            status=ReachabilityState.FAILED,
            endpoint=endpoint,
            method=tr("reachability.method.tcp_probe"),
            duration_ms=duration_ms,
            failure_reason=tr("toast.reachability.timeout"),
            error_category="timeout",
            details=tr("toast.reachability.timeout_details", name=entry.name, endpoint=endpoint, duration=duration_ms),
            config_fingerprint=entry.uri_fingerprint,
        )
    except ConnectionRefusedError:
        duration_ms = max(int((perf_counter() - start) * 1000), 1)
        return ReachabilityCheck(
            checked_at=checked_at,
            status=ReachabilityState.FAILED,
            endpoint=endpoint,
            method=tr("reachability.method.tcp_probe"),
            duration_ms=duration_ms,
            failure_reason=tr("toast.reachability.refused"),
            error_category="refused",
            details=tr("toast.reachability.refused_details", name=entry.name, endpoint=endpoint, duration=duration_ms),
            config_fingerprint=entry.uri_fingerprint,
        )
    except OSError as exc:
        duration_ms = max(int((perf_counter() - start) * 1000), 1)
        failure_reason = describe_human_error("server_unreachable", detail=str(exc)).summary
        return ReachabilityCheck(
            checked_at=checked_at,
            status=ReachabilityState.FAILED,
            endpoint=endpoint,
            method=tr("reachability.method.tcp_probe"),
            duration_ms=duration_ms,
            failure_reason=failure_reason,
            error_category="network_error",
            details=tr(
                "toast.reachability.network_error_details",
                name=entry.name,
                endpoint=endpoint,
                duration=duration_ms,
                error=failure_reason,
            ),
            config_fingerprint=entry.uri_fingerprint,
        )


def build_protocol_note(entry: ProxyEntry) -> ReachabilityCheck:
    checked_at = utc_now_iso()
    endpoint = entry.display_host_port
    return ReachabilityCheck(
        checked_at=checked_at,
        status=ReachabilityState.NOT_APPLICABLE,
        endpoint=endpoint,
        method=tr("reachability.method.protocol_note"),
        failure_reason=tr("reachability.reason.not_applicable"),
        error_category="not_applicable",
        details=tr(
            "reachability.details.not_applicable",
            name=entry.name,
            endpoint=endpoint,
            transport=entry.transport or tr("common.not_available"),
        ),
        config_fingerprint=entry.uri_fingerprint,
    )


def run_wireguard_runtime_probe(
    entry: ProxyEntry,
    *,
    adapters: Sequence[EngineAdapter] = (),
    active_session: RunningSession | None = None,
) -> ReachabilityCheck:
    checked_at = utc_now_iso()
    endpoint = entry.display_host_port
    method = tr("reachability.method.runtime_handshake")
    adapter = _resolve_adapter(entry, adapters)
    if adapter is None:
        return _build_runtime_failure(
            entry,
            checked_at=checked_at,
            endpoint=endpoint,
            method=method,
            reason_code="runtime.error.adapter_not_found",
            technical_detail=f"No runtime adapter is available for {entry.type.value} on this platform.",
        )

    session = _clone_session(active_session) if _is_active_session_for_entry(active_session, entry.id) else None
    launch_spec: LaunchSpec | None = None
    owns_session = False
    diagnostic_started = perf_counter()
    try:
        if session is None:
            diagnostic_entry = _build_wireguard_diagnostic_entry(entry)
            launch_spec = adapter.prepare_launch(diagnostic_entry, RuntimePrefs(entry_id=entry.id), make_primary=False)
            session = adapter.start(launch_spec)
            owns_session = True

        if session.last_handshake_at:
            return _build_runtime_success(
                entry,
                checked_at=checked_at,
                endpoint=endpoint,
                method=method,
                duration_ms=None,
                existing_session=not owns_session,
                log_path=_runtime_log_path(session, launch_spec=launch_spec),
            )

        traffic_started_at = 0.0
        deadline = time.monotonic() + _runtime_handshake_timeout(entry)
        while time.monotonic() < deadline:
            now_monotonic = time.monotonic()
            if now_monotonic - traffic_started_at >= _RUNTIME_HANDSHAKE_TRAFFIC_INTERVAL_SECONDS:
                _stimulate_runtime_handshake()
                traffic_started_at = now_monotonic
            time.sleep(_RUNTIME_HANDSHAKE_POLL_INTERVAL_SECONDS)
            session = adapter.poll(session)
            if session.last_handshake_at:
                duration_ms = max(int((perf_counter() - diagnostic_started) * 1000), 1)
                return _build_runtime_success(
                    entry,
                    checked_at=checked_at,
                    endpoint=endpoint,
                    method=method,
                    duration_ms=duration_ms,
                    existing_session=False,
                    log_path=_runtime_log_path(session, launch_spec=launch_spec),
                )
            if session.runtime_state in _TERMINAL_RUNTIME_STATES:
                return _build_runtime_failure_from_session(
                    entry,
                    checked_at=checked_at,
                    endpoint=endpoint,
                    method=method,
                    session=session,
                )

        session = adapter.poll(session)
        if session.last_handshake_at:
            duration_ms = max(int((perf_counter() - diagnostic_started) * 1000), 1)
            return _build_runtime_success(
                entry,
                checked_at=checked_at,
                endpoint=endpoint,
                method=method,
                duration_ms=duration_ms,
                existing_session=False,
                log_path=_runtime_log_path(session, launch_spec=launch_spec),
            )
        if session.runtime_state in _TERMINAL_RUNTIME_STATES:
            return _build_runtime_failure_from_session(
                entry,
                checked_at=checked_at,
                endpoint=endpoint,
                method=method,
                session=session,
            )
        if _handshake_observation_unavailable(session):
            return _build_runtime_observation_limited(
                entry,
                checked_at=checked_at,
                endpoint=endpoint,
                method=method,
                log_path=_runtime_log_path(session, launch_spec=launch_spec),
            )
        technical_detail = session.last_error or session.log_excerpt or tr("reachability.reason.failure_default")
        return _build_runtime_failure(
            entry,
            checked_at=checked_at,
            endpoint=endpoint,
            method=method,
            reason_code=WIREGUARD_FAILURE_HANDSHAKE_MISSING,
            technical_detail=technical_detail,
            log_path=_runtime_log_path(session, launch_spec=launch_spec),
        )
    except Exception as exc:
        technical_detail = getattr(exc, "log_excerpt", "") or getattr(exc, "last_error", "") or str(exc).strip() or repr(exc)
        reason_code = getattr(exc, "failure_reason", "runtime.error.launch_start_failed")
        return _build_runtime_failure(
            entry,
            checked_at=checked_at,
            endpoint=endpoint,
            method=method,
            reason_code=reason_code,
            technical_detail=technical_detail,
            log_path=_runtime_log_path(session, launch_spec=launch_spec),
        )
    finally:
        if owns_session and session is not None:
            try:
                adapter.stop(session, reason=SessionStopReason.USER_REQUEST)
            except Exception:
                pass


def run_sing_box_runtime_probe(
    entry: ProxyEntry,
    *,
    adapters: Sequence[EngineAdapter] = (),
    active_session: RunningSession | None = None,
) -> ReachabilityCheck:
    checked_at = utc_now_iso()
    endpoint = entry.display_host_port
    method = tr("reachability.method.runtime_handshake")
    adapter = _resolve_adapter(entry, adapters)
    if adapter is None:
        return _build_runtime_failure(
            entry,
            checked_at=checked_at,
            endpoint=endpoint,
            method=method,
            reason_code="runtime.error.adapter_not_found",
            technical_detail=f"No runtime adapter is available for {entry.type.value} on this platform.",
        )

    session = _clone_session(active_session) if _is_active_session_for_entry(active_session, entry.id) else None
    launch_spec: LaunchSpec | None = None
    owns_session = False
    baseline_activity_at = session.last_activity_at if session is not None else ""
    diagnostic_started = perf_counter()
    try:
        if session is None:
            launch_spec = adapter.prepare_launch(entry, RuntimePrefs(entry_id=entry.id), make_primary=False)
            session = adapter.start(launch_spec)
            owns_session = True
            baseline_activity_at = session.last_activity_at

        if session.runtime_state in _TERMINAL_RUNTIME_STATES:
            return _build_runtime_failure_from_session(
                entry,
                checked_at=checked_at,
                endpoint=endpoint,
                method=method,
                session=session,
            )
        if _has_runtime_activity(session, baseline_activity_at=baseline_activity_at):
            return _build_runtime_success(
                entry,
                checked_at=checked_at,
                endpoint=endpoint,
                method=method,
                duration_ms=session.latency_ms,
                existing_session=not owns_session,
                log_path=_runtime_log_path(session, launch_spec=launch_spec),
            )

        traffic_started_at = 0.0
        deadline = time.monotonic() + _WIREGUARD_HANDSHAKE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            now_monotonic = time.monotonic()
            if now_monotonic - traffic_started_at >= _RUNTIME_HANDSHAKE_TRAFFIC_INTERVAL_SECONDS:
                _stimulate_local_proxy_session(session)
                traffic_started_at = now_monotonic
            time.sleep(_RUNTIME_HANDSHAKE_POLL_INTERVAL_SECONDS)
            session = adapter.poll(session)
            if session.runtime_state in _TERMINAL_RUNTIME_STATES:
                return _build_runtime_failure_from_session(
                    entry,
                    checked_at=checked_at,
                    endpoint=endpoint,
                    method=method,
                    session=session,
                )
            if _has_runtime_activity(session, baseline_activity_at=baseline_activity_at):
                duration_ms = session.latency_ms or max(int((perf_counter() - diagnostic_started) * 1000), 1)
                return _build_runtime_success(
                    entry,
                    checked_at=checked_at,
                    endpoint=endpoint,
                    method=method,
                    duration_ms=duration_ms,
                    existing_session=False,
                    log_path=_runtime_log_path(session, launch_spec=launch_spec),
                )

        technical_detail = session.last_error or session.log_excerpt or tr("reachability.reason.failure_default")
        return _build_runtime_failure(
            entry,
            checked_at=checked_at,
            endpoint=endpoint,
            method=method,
            reason_code="runtime.error.server_unreachable",
            technical_detail=technical_detail,
            log_path=_runtime_log_path(session, launch_spec=launch_spec),
        )
    except Exception as exc:
        technical_detail = getattr(exc, "log_excerpt", "") or getattr(exc, "last_error", "") or str(exc).strip() or repr(exc)
        reason_code = getattr(exc, "failure_reason", "runtime.error.launch_start_failed")
        return _build_runtime_failure(
            entry,
            checked_at=checked_at,
            endpoint=endpoint,
            method=method,
            reason_code=reason_code,
            technical_detail=technical_detail,
            log_path=_runtime_log_path(session, launch_spec=launch_spec),
        )
    finally:
        if owns_session and session is not None:
            try:
                adapter.stop(session, reason=SessionStopReason.USER_REQUEST)
            except Exception:
                pass


def _resolve_adapter(entry: ProxyEntry, adapters: Sequence[EngineAdapter]) -> EngineAdapter | None:
    for adapter in adapters:
        try:
            if adapter.supports(entry):
                return adapter
        except Exception:
            continue
    return None


def _clone_session(session: RunningSession | None) -> RunningSession | None:
    if session is None:
        return None
    return RunningSession.from_dict(session.to_dict())


def _is_active_session_for_entry(session: RunningSession | None, entry_id: str) -> bool:
    return bool(
        session
        and session.entry_id == entry_id
        and session.runtime_state not in _TERMINAL_RUNTIME_STATES
    )


def _stimulate_runtime_handshake() -> None:
    for host, port in _RUNTIME_TRIGGER_ENDPOINTS:
        try:
            with socket.create_connection((host, port), timeout=1.2):
                return
        except OSError:
            continue


def _stimulate_local_proxy_session(session: RunningSession) -> None:
    proxy_url = session.local_http_url
    if not proxy_url:
        return
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler(
            {
                "http": proxy_url,
                "https": proxy_url,
            }
        ),
        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
    )
    for target_url in _PROXY_TRIGGER_URLS:
        try:
            request = urllib.request.Request(
                target_url,
                headers={
                    "User-Agent": "ProxyVault-Diagnostic/1.0",
                    "Connection": "close",
                },
            )
            with opener.open(request, timeout=1.5) as response:
                response.read(1)
            return
        except Exception:
            continue


def _has_runtime_activity(session: RunningSession, *, baseline_activity_at: str) -> bool:
    if session.last_handshake_at:
        return True
    if session.engine_kind == RuntimeEngineKind.SING_BOX:
        if session.latency_ms is not None:
            return True
        if session.last_activity_at and session.last_activity_at != baseline_activity_at:
            return True
    return False


def _build_wireguard_diagnostic_entry(entry: ProxyEntry) -> ProxyEntry:
    if entry.type not in _WIREGUARD_RUNTIME_TYPES:
        return entry

    parser = configparser.ConfigParser(strict=False)
    parser.optionxform = str
    try:
        parser.read_string(entry.uri.strip())
    except configparser.Error:
        return entry

    if not parser.has_section("Interface") or not parser.has_section("Peer"):
        return entry

    if entry.type == ProxyType.AMNEZIAWG:
        _prepare_amneziawg_diagnostic_config(parser)
    else:
        _prepare_wireguard_diagnostic_config(parser)

    rendered = _render_parser(parser)

    return ProxyEntry(
        id=entry.id,
        name=entry.name,
        uri=rendered,
        type=entry.type,
        transport=entry.transport,
        server_host=entry.server_host,
        server_port=entry.server_port,
        tags=entry.tags,
        notes=entry.notes,
        qr_png_path=entry.qr_png_path,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        is_favorite=entry.is_favorite,
        expiry_date=entry.expiry_date,
        is_locked=entry.is_locked,
        uri_fingerprint=entry.uri_fingerprint,
        reachability_status=entry.reachability_status,
        reachability_checked_at=entry.reachability_checked_at,
        reachability_latency_ms=entry.reachability_latency_ms,
        reachability_duration_ms=entry.reachability_duration_ms,
        reachability_method=entry.reachability_method,
        reachability_endpoint=entry.reachability_endpoint,
        reachability_failure_reason=entry.reachability_failure_reason,
        reachability_error_category=entry.reachability_error_category,
        reachability_details=entry.reachability_details,
        reachability_config_fingerprint=entry.reachability_config_fingerprint,
    )


def _prepare_wireguard_diagnostic_config(parser: configparser.ConfigParser) -> None:
    peer = parser["Peer"]
    peer["AllowedIPs"] = _diagnostic_allowed_ips()
    if not str(peer.get("PersistentKeepalive", "")).strip():
        peer["PersistentKeepalive"] = "15"
    _remove_interface_dns(parser["Interface"])


def _prepare_amneziawg_diagnostic_config(parser: configparser.ConfigParser) -> None:
    interface = parser["Interface"]
    peer = parser["Peer"]
    _remove_interface_dns(interface)
    peer["AllowedIPs"] = _diagnostic_allowed_ips()
    peer["PersistentKeepalive"] = "5"


def _remove_interface_dns(interface: configparser.SectionProxy) -> None:
    for key in _DIAGNOSTIC_DNS_KEYS:
        if key in interface:
            interface.pop(key, None)


def _render_parser(parser: configparser.ConfigParser) -> str:
    rendered_lines: list[str] = []
    for section_name in parser.sections():
        rendered_lines.append(f"[{section_name}]")
        for key, value in parser.items(section_name):
            rendered_lines.append(f"{key} = {value}")
        rendered_lines.append("")
    return "\n".join(rendered_lines).strip() + "\n"


def _diagnostic_allowed_ips() -> str:
    cidrs: list[str] = []
    for host, _port in _RUNTIME_TRIGGER_ENDPOINTS:
        family = _infer_ip_family(host)
        suffix = "/128" if family == socket.AF_INET6 else "/32"
        cidr = f"{host}{suffix}"
        if cidr not in cidrs:
            cidrs.append(cidr)
    return ",".join(cidrs)


def _infer_ip_family(host: str) -> int:
    try:
        socket.inet_pton(socket.AF_INET6, host)
        return socket.AF_INET6
    except OSError:
        return socket.AF_INET


def _runtime_handshake_timeout(entry: ProxyEntry) -> float:
    if entry.type == ProxyType.AMNEZIAWG:
        return _AMNEZIAWG_HANDSHAKE_TIMEOUT_SECONDS
    return _WIREGUARD_HANDSHAKE_TIMEOUT_SECONDS


def _runtime_log_path(session: RunningSession | None, *, launch_spec: LaunchSpec | None = None) -> str:
    if launch_spec is not None and launch_spec.log_path:
        return launch_spec.log_path
    if session is None:
        return ""
    log_path = session.metadata.get(WIREGUARD_META_LOG_PATH)
    if isinstance(log_path, str) and log_path.strip():
        return log_path.strip()
    return ""


def _handshake_observation_unavailable(session: RunningSession) -> bool:
    warning_codes = session.metadata.get(WIREGUARD_META_WARNING_CODES)
    if isinstance(warning_codes, str):
        values = [warning_codes]
    elif isinstance(warning_codes, Sequence):
        values = list(warning_codes)
    else:
        values = []
    return WIREGUARD_WARNING_HANDSHAKE_UNAVAILABLE in {str(value).strip() for value in values}


def _build_runtime_success(
    entry: ProxyEntry,
    *,
    checked_at: str,
    endpoint: str,
    method: str,
    duration_ms: int | None,
    existing_session: bool,
    log_path: str = "",
) -> ReachabilityCheck:
    details_key = "reachability.details.runtime_success_existing" if existing_session else "reachability.details.runtime_success"
    return ReachabilityCheck(
        checked_at=checked_at,
        status=ReachabilityState.REACHABLE,
        endpoint=endpoint,
        method=method,
        latency_ms=duration_ms,
        duration_ms=duration_ms,
        failure_reason=tr("reachability.reason.runtime_success"),
        details=tr(
            details_key,
            name=entry.name,
            endpoint=endpoint,
            latency_suffix=_latency_suffix(duration_ms),
        ),
        log_path=log_path,
        config_fingerprint=entry.uri_fingerprint,
    )


def _build_runtime_observation_limited(
    entry: ProxyEntry,
    *,
    checked_at: str,
    endpoint: str,
    method: str,
    log_path: str = "",
) -> ReachabilityCheck:
    return ReachabilityCheck(
        checked_at=checked_at,
        status=ReachabilityState.NOT_APPLICABLE,
        endpoint=endpoint,
        method=method,
        failure_reason=tr("reachability.reason.runtime_observation_limited"),
        error_category="handshake_observation_limited",
        details=tr(
            "reachability.details.runtime_observation_limited",
            name=entry.name,
            endpoint=endpoint,
        ),
        log_path=log_path,
        config_fingerprint=entry.uri_fingerprint,
    )


def _build_runtime_failure_from_session(
    entry: ProxyEntry,
    *,
    checked_at: str,
    endpoint: str,
    method: str,
    session: RunningSession,
) -> ReachabilityCheck:
    technical_detail = session.last_error or session.log_excerpt or tr("reachability.reason.failure_default")
    reason_code = session.failure_reason or "runtime.error.launch_start_failed"
    return _build_runtime_failure(
        entry,
        checked_at=checked_at,
        endpoint=endpoint,
        method=method,
        reason_code=reason_code,
        technical_detail=technical_detail,
        duration_ms=session.latency_ms,
        log_path=_runtime_log_path(session),
    )


def _build_runtime_failure(
    entry: ProxyEntry,
    *,
    checked_at: str,
    endpoint: str,
    method: str,
    reason_code: str,
    technical_detail: str,
    duration_ms: int | None = None,
    log_path: str = "",
) -> ReachabilityCheck:
    human = describe_human_error(reason_code, detail=technical_detail)
    technical_text = str(technical_detail or "").strip() or tr("common.not_available")
    return ReachabilityCheck(
        checked_at=checked_at,
        status=ReachabilityState.FAILED,
        endpoint=endpoint,
        method=method,
        duration_ms=duration_ms,
        failure_reason=human.summary,
        error_category=normalize_human_error_code(reason_code, detail=technical_text),
        details=tr(
            "reachability.details.runtime_failure",
            title=human.title,
            summary=human.summary,
            action=human.action,
            technical_detail=technical_text,
        ),
        log_path=log_path,
        config_fingerprint=entry.uri_fingerprint,
    )


def _latency_suffix(duration_ms: int | None) -> str:
    if duration_ms is None:
        return ""
    if duration_ms >= 1000:
        return f" ({tr('common.duration.seconds', value=f'{duration_ms / 1000:.1f}')})"
    return f" ({tr('common.duration.ms', value=duration_ms)})"
