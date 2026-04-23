from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence
from urllib.parse import parse_qs, unquote, urlparse
from uuid import UUID

from app.models import ProxyEntry, ProxyType, utc_now_iso
from app.runtime.enums import RouteOwnerKind, RuntimeEngineKind, RuntimeState, SessionStopReason
from app.runtime.health import apply_health_to_session
from app.runtime.logs import read_log_excerpt
from app.runtime.models import LaunchSpec, RunningSession, RuntimePrefs, new_session_id
from app.runtime.paths import (
    ensure_runtime_dirs,
    resolve_sing_box_asset_layout,
    sing_box_support_asset_names,
)
from app.runtime.ports import PortReservation, reserve_local_ports


PROXY_OUTBOUND_TAG = "proxy-out"
HTTP_INBOUND_TAG = "http-in"
SOCKS_INBOUND_TAG = "socks-in"

SUPPORTED_PROXY_TYPES = {
    ProxyType.VLESS_REALITY,
    ProxyType.VLESS_WS,
    ProxyType.VLESS_XHTTP,
    ProxyType.HYSTERIA2,
    ProxyType.SHADOWSOCKS,
    ProxyType.TROJAN,
    ProxyType.NAIVE_PROXY,
}

VLESS_HTTP_TRANSPORT_ALIASES = frozenset({"xhttp", "splithttp", "split-http", "http", "h2"})


class SingBoxConfigError(RuntimeError):
    """Raised when ProxyVault cannot translate an entry into a valid sing-box config."""


class SingBoxAssetError(RuntimeError):
    """Raised when bundled sing-box runtime assets are missing."""


class ManagedProcess(Protocol):
    pid: int | None

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


class ProcessRunner(Protocol):
    def popen(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> ManagedProcess: ...


class SubprocessProcessRunner:
    def popen(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> ManagedProcess:
        return subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=dict(env) if env is not None else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class SingBoxAdapter:
    engine_kind = RuntimeEngineKind.SING_BOX

    def __init__(
        self,
        *,
        engine_root_dir: str | Path | None = None,
        process_runner: ProcessRunner | None = None,
        platform_name: str | None = None,
        terminate_timeout: float = 5.0,
    ) -> None:
        self._engine_root_dir = Path(engine_root_dir) if engine_root_dir is not None else None
        self._process_runner = process_runner or SubprocessProcessRunner()
        self._platform_name = platform_name
        self._terminate_timeout = terminate_timeout
        self._process_by_session_id: dict[str, ManagedProcess] = {}
        self._launch_spec_by_session_id: dict[str, LaunchSpec] = {}
        self._asset_env_by_session_id: dict[str, dict[str, str]] = {}
        self._reserved_ports_by_session_id: dict[str, PortReservation] = {}

    def supports(self, entry: ProxyEntry) -> bool:
        return entry.type in SUPPORTED_PROXY_TYPES

    def prepare_launch(
        self,
        entry: ProxyEntry,
        prefs: RuntimePrefs,
        *,
        make_primary: bool,
    ) -> LaunchSpec:
        if not self.supports(entry):
            raise SingBoxConfigError(f"Entry type {entry.type.value} is not supported by sing-box.")

        runtime_dirs = ensure_runtime_dirs()
        session_id = new_session_id()
        reservation = reserve_local_ports(
            http_override=prefs.http_port_override,
            socks_override=prefs.socks_port_override,
        )
        config_path = runtime_dirs["generated"] / f"{session_id}.json"
        log_path = runtime_dirs["logs"] / f"{session_id}.log"

        try:
            layout = resolve_sing_box_asset_layout(
                engine_root_dir=self._engine_root_dir,
                platform_name=self._platform_name,
                required_support_files=self._required_support_files(entry),
            )
        except FileNotFoundError as exc:
            reservation.close()
            raise SingBoxAssetError(str(exc)) from exc

        try:
            config = build_sing_box_config(
                entry,
                http_port=reservation.http_port,
                socks_port=reservation.socks_port,
                log_path=log_path,
            )
        except Exception:
            reservation.close()
            raise

        config_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch(exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

        launch_spec = LaunchSpec(
            session_id=session_id,
            entry_id=entry.id,
            engine_kind=self.engine_kind,
            route_owner_kind=RouteOwnerKind.PROXY if make_primary else RouteOwnerKind.NONE,
            requested_primary=make_primary,
            resolved_primary=make_primary,
            http_port=reservation.http_port,
            socks_port=reservation.socks_port,
            config_path=str(config_path),
            log_path=str(log_path),
            working_dir=str(layout.binary_dir),
            display_name=entry.name or entry.server_host,
            created_at=utc_now_iso(),
        )

        self._launch_spec_by_session_id[session_id] = launch_spec
        self._reserved_ports_by_session_id[session_id] = reservation
        self._asset_env_by_session_id[session_id] = self._build_process_env(layout)
        return launch_spec

    def start(self, launch_spec: LaunchSpec) -> RunningSession:
        env = self._asset_env_by_session_id.get(launch_spec.session_id)
        if env is None:
            try:
                layout = resolve_sing_box_asset_layout(
                    engine_root_dir=self._engine_root_dir,
                    platform_name=self._platform_name,
                    required_support_files=(),
                )
            except FileNotFoundError as exc:
                raise SingBoxAssetError(str(exc)) from exc
            env = self._build_process_env(layout)

        try:
            binary_path = resolve_sing_box_asset_layout(
                engine_root_dir=self._engine_root_dir,
                platform_name=self._platform_name,
                required_support_files=(),
            ).binary_path
            process = self._process_runner.popen(
                [str(binary_path), "run", "-c", launch_spec.config_path],
                cwd=Path(launch_spec.working_dir),
                env=env,
            )
        finally:
            reservation = self._reserved_ports_by_session_id.pop(launch_spec.session_id, None)
            if reservation is not None:
                reservation.close()

        self._process_by_session_id[launch_spec.session_id] = process

        session = RunningSession(
            session_id=launch_spec.session_id,
            entry_id=launch_spec.entry_id,
            entry_name=launch_spec.display_name,
            engine_kind=self.engine_kind,
            runtime_state=RuntimeState.STARTING,
            route_owner_kind=launch_spec.route_owner_kind,
            is_primary=launch_spec.resolved_primary,
            http_port=launch_spec.http_port,
            socks_port=launch_spec.socks_port,
            pid=getattr(process, "pid", None),
            handle=launch_spec.session_id,
            started_at=utc_now_iso(),
        )

        log_excerpt = read_log_excerpt(launch_spec.log_path, max_lines=20)
        exit_code = process.poll()
        updated = apply_health_to_session(session, log_text=log_excerpt, exit_code=exit_code)
        if exit_code is None and updated.runtime_state != RuntimeState.RUNNING:
            updated.runtime_state = RuntimeState.STARTING
        return updated

    def stop(self, session: RunningSession, *, reason: SessionStopReason) -> RunningSession:
        process = self._process_by_session_id.pop(session.session_id, None)
        launch_spec = self._launch_spec_by_session_id.get(session.session_id)
        updated = RunningSession.from_dict(session.to_dict())

        if process is not None:
            exit_code = process.poll()
            if exit_code is None:
                process.terminate()
                try:
                    exit_code = process.wait(timeout=self._terminate_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    exit_code = process.wait(timeout=self._terminate_timeout)
        else:
            exit_code = 0

        log_excerpt = read_log_excerpt(launch_spec.log_path, max_lines=20) if launch_spec else updated.log_excerpt
        updated = apply_health_to_session(updated, log_text=log_excerpt, exit_code=exit_code)
        updated.runtime_state = RuntimeState.DISCONNECTED
        updated.failure_reason = ""
        updated.last_error = "" if reason != SessionStopReason.UNSUPPORTED else updated.last_error
        updated.stopped_at = updated.stopped_at or utc_now_iso()
        return updated

    def poll(self, session: RunningSession) -> RunningSession:
        process = self._process_by_session_id.get(session.session_id)
        launch_spec = self._launch_spec_by_session_id.get(session.session_id)
        if launch_spec is None:
            raise SingBoxConfigError(f"Launch metadata for session {session.session_id} is missing.")
        if process is None:
            updated = RunningSession.from_dict(session.to_dict())
            updated.runtime_state = RuntimeState.ERROR
            updated.failure_reason = "runtime.error.engine_crash"
            updated.last_error = "sing-box process handle is missing"
            updated.stopped_at = utc_now_iso()
            return updated

        exit_code = process.poll()
        log_excerpt = read_log_excerpt(launch_spec.log_path, max_lines=20)
        updated = apply_health_to_session(session, log_text=log_excerpt, exit_code=exit_code)
        if exit_code is None and updated.runtime_state != RuntimeState.RUNNING:
            updated.runtime_state = RuntimeState.STARTING if not log_excerpt else RuntimeState.RUNNING
        if exit_code is not None:
            self._process_by_session_id.pop(session.session_id, None)
        return updated

    def read_log_excerpt(self, session: RunningSession, max_lines: int) -> str:
        launch_spec = self._launch_spec_by_session_id.get(session.session_id)
        if launch_spec is None:
            return session.log_excerpt
        return read_log_excerpt(launch_spec.log_path, max_lines=max_lines)

    def _required_support_files(self, entry: ProxyEntry) -> tuple[str, ...]:
        if entry.type == ProxyType.NAIVE_PROXY:
            return sing_box_support_asset_names(self._platform_name)
        return ()

    def _build_process_env(self, layout) -> dict[str, str]:
        env = dict(os.environ)
        path_entries = [str(layout.binary_dir)]
        current_path = env.get("PATH", "")
        if current_path:
            path_entries.append(current_path)
        env["PATH"] = os.pathsep.join(path_entries)
        return env


def build_sing_box_config(
    entry: ProxyEntry,
    *,
    http_port: int,
    socks_port: int,
    log_path: str | Path,
) -> dict[str, object]:
    if entry.type not in SUPPORTED_PROXY_TYPES:
        raise SingBoxConfigError(f"Entry type {entry.type.value} is not supported by sing-box.")

    outbound = _build_outbound(entry)
    return {
        "log": {
            "disabled": False,
            "level": "info",
            "output": str(Path(log_path)),
            "timestamp": True,
        },
        "inbounds": [
            {
                "type": "http",
                "tag": HTTP_INBOUND_TAG,
                "listen": "127.0.0.1",
                "listen_port": http_port,
            },
            {
                "type": "socks",
                "tag": SOCKS_INBOUND_TAG,
                "listen": "127.0.0.1",
                "listen_port": socks_port,
            },
        ],
        "outbounds": [outbound],
        "route": {
            "auto_detect_interface": True,
            "final": PROXY_OUTBOUND_TAG,
        },
    }


def _build_outbound(entry: ProxyEntry) -> dict[str, object]:
    if entry.type in {ProxyType.VLESS_REALITY, ProxyType.VLESS_WS, ProxyType.VLESS_XHTTP}:
        return _build_vless_outbound(entry)
    if entry.type == ProxyType.HYSTERIA2:
        return _build_hysteria2_outbound(entry)
    if entry.type == ProxyType.SHADOWSOCKS:
        return _build_shadowsocks_outbound(entry)
    if entry.type == ProxyType.TROJAN:
        return _build_trojan_outbound(entry)
    if entry.type == ProxyType.NAIVE_PROXY:
        return _build_naive_outbound(entry)
    raise SingBoxConfigError(f"Entry type {entry.type.value} is not supported by sing-box.")


def _build_vless_outbound(entry: ProxyEntry) -> dict[str, object]:
    parsed = urlparse(entry.uri)
    query = _query_values(entry.uri)
    uuid_value = unquote(parsed.username or "")
    _validate_uuid(uuid_value)
    host = parsed.hostname or entry.server_host
    port = parsed.port or entry.server_port
    if not host or not port:
        raise SingBoxConfigError("VLESS entries require a server host and port.")

    security = query.get("security", "").lower()
    transport_type = query.get("type", "tcp").lower() or "tcp"
    tls = None
    if security:
        if security not in {"tls", "reality"}:
            raise SingBoxConfigError(f"Unsupported VLESS security mode: {security}")
        tls = _build_tls_section(query, host=host, security=security)
    elif entry.type == ProxyType.VLESS_REALITY:
        raise SingBoxConfigError("VLESS Reality entries require security=reality.")

    outbound: dict[str, object] = {
        "type": "vless",
        "tag": PROXY_OUTBOUND_TAG,
        "server": host,
        "server_port": int(port),
        "uuid": uuid_value,
    }
    if query.get("flow"):
        outbound["flow"] = query["flow"]
    if tls is not None:
        outbound["tls"] = tls

    transport = _build_vless_transport(transport_type, query)
    if transport is not None:
        outbound["transport"] = transport
    return outbound


def _build_hysteria2_outbound(entry: ProxyEntry) -> dict[str, object]:
    parsed = urlparse(_normalize_hysteria2_uri(entry.uri))
    query = _query_values(entry.uri)
    host = parsed.hostname or entry.server_host
    port = parsed.port or entry.server_port
    password = unquote(parsed.username or parsed.password or "")
    if not host or not port or not password:
        raise SingBoxConfigError("Hysteria2 entries require host, port, and password.")

    outbound: dict[str, object] = {
        "type": "hysteria2",
        "tag": PROXY_OUTBOUND_TAG,
        "server": host,
        "server_port": int(port),
        "password": password,
        "tls": _build_tls_section(query, host=host, security="tls"),
    }
    if query.get("network") in {"tcp", "udp"}:
        outbound["network"] = query["network"]
    if query.get("upmbps") or query.get("up_mbps"):
        outbound["up_mbps"] = _coerce_positive_int(query.get("upmbps") or query.get("up_mbps"), "up_mbps")
    if query.get("downmbps") or query.get("down_mbps"):
        outbound["down_mbps"] = _coerce_positive_int(
            query.get("downmbps") or query.get("down_mbps"),
            "down_mbps",
        )
    if query.get("obfs"):
        obfs_password = query.get("obfs-password") or query.get("obfs_password")
        if not obfs_password:
            raise SingBoxConfigError("Hysteria2 obfs requires obfs-password.")
        outbound["obfs"] = {
            "type": query["obfs"],
            "password": obfs_password,
        }
    return outbound


def _build_shadowsocks_outbound(entry: ProxyEntry) -> dict[str, object]:
    parsed = urlparse(entry.uri)
    query = _query_values(entry.uri)
    host = parsed.hostname or entry.server_host
    port = parsed.port or entry.server_port
    method, password = _parse_shadowsocks_auth(parsed)
    if not host or not port:
        raise SingBoxConfigError("Shadowsocks entries require a server host and port.")

    outbound: dict[str, object] = {
        "type": "shadowsocks",
        "tag": PROXY_OUTBOUND_TAG,
        "server": host,
        "server_port": int(port),
        "method": method,
        "password": password,
    }
    plugin_name, plugin_opts = _parse_plugin_value(query.get("plugin", ""))
    if plugin_name:
        if plugin_name not in {"obfs-local", "v2ray-plugin"}:
            raise SingBoxConfigError(f"Unsupported Shadowsocks plugin: {plugin_name}")
        outbound["plugin"] = plugin_name
        if plugin_opts:
            outbound["plugin_opts"] = plugin_opts
    return outbound


def _build_trojan_outbound(entry: ProxyEntry) -> dict[str, object]:
    parsed = urlparse(entry.uri)
    query = _query_values(entry.uri)
    host = parsed.hostname or entry.server_host
    port = parsed.port or entry.server_port
    password = unquote(parsed.username or "")
    if not host or not port or not password:
        raise SingBoxConfigError("Trojan entries require host, port, and password.")

    outbound: dict[str, object] = {
        "type": "trojan",
        "tag": PROXY_OUTBOUND_TAG,
        "server": host,
        "server_port": int(port),
        "password": password,
        "tls": _build_tls_section(query, host=host, security="tls"),
    }
    transport = _build_generic_transport(query)
    if transport is not None:
        outbound["transport"] = transport
    return outbound


def _build_naive_outbound(entry: ProxyEntry) -> dict[str, object]:
    parsed = urlparse(entry.uri)
    query = _query_values(entry.uri)
    host = parsed.hostname or entry.server_host
    port = parsed.port or entry.server_port
    username = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if not host or not port or not username:
        raise SingBoxConfigError("NaiveProxy entries require host, port, and username.")
    if parsed.path not in {"", "/"}:
        raise SingBoxConfigError("NaiveProxy URIs with a non-root path are not supported by sing-box.")

    outbound: dict[str, object] = {
        "type": "naive",
        "tag": PROXY_OUTBOUND_TAG,
        "server": host,
        "server_port": int(port),
        "username": username,
        "password": password,
        "tls": _build_tls_section(query, host=host, security="tls"),
    }
    if _coerce_bool(query.get("quic", "")):
        outbound["quic"] = True
    if query.get("quic_congestion_control"):
        outbound["quic_congestion_control"] = query["quic_congestion_control"]
    return outbound


def _build_vless_transport(transport_type: str, query: dict[str, str]) -> dict[str, object] | None:
    if transport_type in {"", "tcp"}:
        return None
    if transport_type == "ws":
        transport: dict[str, object] = {"type": "ws"}
        if query.get("path"):
            transport["path"] = unquote(query["path"])
        headers = _host_header(query)
        if headers:
            transport["headers"] = headers
        if query.get("ed"):
            transport["max_early_data"] = _coerce_positive_int(query["ed"], "ed")
        if query.get("eh"):
            transport["early_data_header_name"] = query["eh"]
        return transport
    if transport_type in VLESS_HTTP_TRANSPORT_ALIASES:
        if query.get("extra"):
            raise SingBoxConfigError("XHTTP entries with extra transport payload are not supported yet.")
        transport = {"type": "http"}
        if query.get("path"):
            transport["path"] = unquote(query["path"])
        host_value = query.get("host") or query.get("authority")
        if host_value:
            transport["host"] = [value.strip() for value in host_value.split(",") if value.strip()]
        return transport
    raise SingBoxConfigError(f"Unsupported VLESS transport for sing-box: {transport_type}")


def _build_generic_transport(query: dict[str, str]) -> dict[str, object] | None:
    transport_type = query.get("type", "").lower()
    if transport_type in {"", "tcp"}:
        return None
    if transport_type == "ws":
        transport = {"type": "ws"}
        if query.get("path"):
            transport["path"] = unquote(query["path"])
        headers = _host_header(query)
        if headers:
            transport["headers"] = headers
        return transport
    if transport_type in {"httpupgrade", "xhttp"}:
        transport = {"type": "httpupgrade"}
        if query.get("path"):
            transport["path"] = unquote(query["path"])
        host_value = query.get("host") or query.get("authority")
        if host_value:
            transport["host"] = host_value
        return transport
    if transport_type == "grpc":
        service_name = query.get("serviceName") or query.get("service_name")
        if not service_name:
            raise SingBoxConfigError("gRPC transport requires serviceName.")
        return {
            "type": "grpc",
            "service_name": service_name,
        }
    raise SingBoxConfigError(f"Unsupported transport for sing-box: {transport_type}")


def _build_tls_section(query: dict[str, str], *, host: str, security: str) -> dict[str, object]:
    server_name = query.get("sni") or query.get("serverName") or query.get("host") or host
    if not server_name:
        raise SingBoxConfigError("TLS-enabled entries require a server name or SNI.")
    tls: dict[str, object] = {
        "enabled": True,
        "server_name": server_name,
    }
    if _coerce_bool(query.get("allowInsecure", "") or query.get("insecure", "")):
        tls["insecure"] = True
    alpn_values = _split_csv(query.get("alpn", ""))
    if alpn_values:
        tls["alpn"] = alpn_values
    fingerprint = query.get("fp") or query.get("fingerprint")
    if fingerprint:
        tls["utls"] = {
            "enabled": True,
            "fingerprint": fingerprint,
        }
    if security == "reality":
        public_key = query.get("pbk")
        if not public_key:
            raise SingBoxConfigError("REALITY entries require the pbk public key.")
        reality: dict[str, object] = {
            "enabled": True,
            "public_key": public_key,
        }
        if query.get("sid"):
            reality["short_id"] = query["sid"]
        tls["reality"] = reality
    return tls


def _query_values(uri: str) -> dict[str, str]:
    parsed = urlparse(_normalize_hysteria2_uri(uri))
    return {
        key: values[-1]
        for key, values in parse_qs(parsed.query).items()
        if values
    }


def _normalize_hysteria2_uri(uri: str) -> str:
    if uri.lower().startswith("hy2://"):
        return "hysteria2://" + uri[6:]
    return uri


def _validate_uuid(value: str) -> None:
    try:
        UUID(value)
    except (ValueError, TypeError) as exc:
        raise SingBoxConfigError(f"Invalid UUID for VLESS entry: {value}") from exc


def _parse_shadowsocks_auth(parsed) -> tuple[str, str]:
    if parsed.username:
        decoded = _decode_base64_padded(parsed.username)
    else:
        payload = parsed.netloc
        if "@" not in payload:
            raise SingBoxConfigError("Shadowsocks URI is missing credentials.")
        auth, _, _ = payload.rpartition("@")
        decoded = _decode_base64_padded(auth)
    if ":" not in decoded:
        raise SingBoxConfigError("Shadowsocks credentials must be in method:password form.")
    method, password = decoded.split(":", 1)
    if not method or not password:
        raise SingBoxConfigError("Shadowsocks method and password are both required.")
    return method, password


def _decode_base64_padded(value: str) -> str:
    import base64

    padding = len(value) % 4
    if padding:
        value += "=" * (4 - padding)
    try:
        return base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        raise SingBoxConfigError("Unable to decode base64 proxy credentials.") from exc


def _parse_plugin_value(value: str) -> tuple[str, str]:
    decoded = unquote(value or "")
    if not decoded:
        return "", ""
    plugin_name, *rest = decoded.split(";")
    return plugin_name, ";".join(part for part in rest if part)


def _host_header(query: dict[str, str]) -> dict[str, str]:
    host_value = query.get("host") or query.get("authority")
    if not host_value:
        return {}
    return {"Host": host_value}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _coerce_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_positive_int(value: str | None, label: str) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise SingBoxConfigError(f"{label} must be an integer.") from exc
    if parsed <= 0:
        raise SingBoxConfigError(f"{label} must be positive.")
    return parsed
