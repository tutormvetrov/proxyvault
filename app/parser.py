from __future__ import annotations

import base64
import binascii
import configparser
import io
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from app.models import ParsedConfig, ProxyType, SubscriptionFormat, SubscriptionImportItem


class ParseError(ValueError):
    """Raised when a proxy configuration cannot be parsed."""


AMNEZIAWG_INTERFACE_KEYS = frozenset(
    {
        "jc",
        "jmin",
        "jmax",
        "s1",
        "s2",
        "s3",
        "s4",
        "h1",
        "h2",
        "h3",
        "h4",
        "i1",
        "i2",
        "i3",
        "i4",
        "i5",
    }
)

VLESS_HTTP_TRANSPORT_ALIASES = frozenset({"xhttp", "splithttp", "split-http", "http", "h2"})


def is_wireguard_block(text: str) -> bool:
    lowered = text.lower()
    return "[interface]" in lowered and ("[peer]" in lowered or "privatekey" in lowered)


def load_wireguard_config(text: str) -> configparser.ConfigParser:
    config = configparser.ConfigParser(strict=False)
    config.optionxform = str
    try:
        config.read_string(text)
    except configparser.Error as exc:
        raise ParseError(str(exc)) from exc
    return config


def is_amneziawg_config(config: configparser.ConfigParser) -> bool:
    if not config.has_section("Interface"):
        return False
    keys = {str(key).strip().lower() for key in config["Interface"].keys()}
    return bool(keys & AMNEZIAWG_INTERFACE_KEYS)


def detect_type(text: str) -> ProxyType:
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.startswith("vless://"):
        parsed = urlparse(stripped)
        query = parse_qs(parsed.query)
        transport = query.get("type", [""])[0].lower()
        if transport in VLESS_HTTP_TRANSPORT_ALIASES:
            return ProxyType.VLESS_XHTTP
        if query.get("security", [""])[0].lower() == "reality" or "reality" in stripped:
            return ProxyType.VLESS_REALITY
        if transport == "ws":
            return ProxyType.VLESS_WS
        return ProxyType.OTHER
    if lowered.startswith("hysteria2://") or lowered.startswith("hy2://"):
        return ProxyType.HYSTERIA2
    if lowered.startswith("https://") and "@" in stripped:
        return ProxyType.NAIVE_PROXY
    if is_wireguard_block(stripped):
        try:
            config = load_wireguard_config(stripped)
        except ParseError:
            return ProxyType.WIREGUARD
        if is_amneziawg_config(config):
            return ProxyType.AMNEZIAWG
        return ProxyType.WIREGUARD
    if lowered.startswith("ss://"):
        return ProxyType.SHADOWSOCKS
    if lowered.startswith("trojan://"):
        return ProxyType.TROJAN
    return ProxyType.OTHER


def parse_proxy_text(text: str) -> ParsedConfig:
    stripped = text.strip()
    if not stripped:
        raise ParseError("Configuration is empty")
    proxy_type = detect_type(stripped)
    if proxy_type in {
        ProxyType.VLESS_REALITY,
        ProxyType.VLESS_WS,
        ProxyType.VLESS_XHTTP,
        ProxyType.OTHER,
    } and stripped.lower().startswith("vless://"):
        return parse_vless(stripped)
    if proxy_type == ProxyType.HYSTERIA2:
        return parse_hysteria2(stripped)
    if proxy_type == ProxyType.NAIVE_PROXY:
        return parse_naive(stripped)
    if proxy_type == ProxyType.WIREGUARD:
        return parse_wireguard(stripped, proxy_type=ProxyType.WIREGUARD)
    if proxy_type == ProxyType.AMNEZIAWG:
        return parse_wireguard(stripped, proxy_type=ProxyType.AMNEZIAWG)
    if proxy_type == ProxyType.SHADOWSOCKS:
        return parse_shadowsocks(stripped)
    if proxy_type == ProxyType.TROJAN:
        return parse_trojan(stripped)
    if "://" in stripped:
        parsed = urlparse(stripped)
        if parsed.scheme and parsed.hostname:
            return ParsedConfig(
                type=ProxyType.OTHER,
                transport=parsed.scheme,
                server_host=parsed.hostname or "",
                server_port=parsed.port,
                params={"scheme": parsed.scheme, "path": parsed.path or ""},
            )
    raise ParseError("Unsupported or invalid proxy configuration")


def parse_vless(uri: str) -> ParsedConfig:
    parsed = urlparse(uri)
    if not parsed.username or not parsed.hostname or not parsed.port:
        raise ParseError("Invalid VLESS URI")
    query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
    params = {
        "uuid": unquote(parsed.username or ""),
        "host": parsed.hostname or "",
        "port": str(parsed.port or ""),
        "network": query.get("type", ""),
        "security": query.get("security", ""),
        "flow": query.get("flow", ""),
        "sni": query.get("sni", ""),
        "pbk": query.get("pbk", ""),
        "fp": query.get("fp", ""),
        "sid": query.get("sid", ""),
        "path": query.get("path", ""),
        "serviceName": query.get("serviceName", ""),
        "authority": query.get("authority", ""),
        "alpn": query.get("alpn", ""),
    }
    params = {k: v for k, v in params.items() if v}
    proxy_type = detect_type(uri)
    network = query.get("type", "tcp")
    security = query.get("security", "")
    transport = network
    if security:
        transport = f"{network}+{security}"
    return ParsedConfig(
        type=proxy_type,
        transport=transport,
        server_host=parsed.hostname or "",
        server_port=parsed.port,
        params=params,
        display_name=unquote(parsed.fragment or ""),
    )


def parse_hysteria2(uri: str) -> ParsedConfig:
    normalized = uri
    if uri.lower().startswith("hy2://"):
        normalized = "hysteria2://" + uri[6:]
    parsed = urlparse(normalized)
    if not parsed.hostname or not parsed.port:
        raise ParseError("Invalid Hysteria2 URI")
    query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
    params = {
        "password": unquote(parsed.username or parsed.password or ""),
        "host": parsed.hostname or "",
        "port": str(parsed.port or ""),
        "obfs": query.get("obfs", ""),
        "obfs-password": query.get("obfs-password", ""),
        "sni": query.get("sni", ""),
        "insecure": query.get("insecure", ""),
    }
    params = {k: v for k, v in params.items() if v}
    obfs = query.get("obfs", "")
    transport = "udp+tls"
    if obfs:
        transport = f"{transport}+{obfs}"
    return ParsedConfig(
        type=ProxyType.HYSTERIA2,
        transport=transport,
        server_host=parsed.hostname or "",
        server_port=parsed.port,
        params=params,
        display_name=unquote(parsed.fragment or ""),
    )


def parse_naive(uri: str) -> ParsedConfig:
    parsed = urlparse(uri)
    if not parsed.hostname or not parsed.port or not parsed.username:
        raise ParseError("Invalid NaiveProxy URI")
    params = {
        "username": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname or "",
        "port": str(parsed.port or ""),
        "path": parsed.path or "",
    }
    params = {k: v for k, v in params.items() if v}
    return ParsedConfig(
        type=ProxyType.NAIVE_PROXY,
        transport="https",
        server_host=parsed.hostname or "",
        server_port=parsed.port,
        params=params,
    )


def parse_wireguard(text: str, *, proxy_type: ProxyType = ProxyType.WIREGUARD) -> ParsedConfig:
    config = load_wireguard_config(text)
    peer = config["Peer"] if config.has_section("Peer") else {}
    endpoint = str(peer.get("Endpoint", "")).strip()
    host = ""
    port: int | None = None
    if endpoint:
        if endpoint.count(":") >= 1:
            host, _, port_text = endpoint.rpartition(":")
            host = host.strip("[]")
            try:
                port = int(port_text)
            except ValueError:
                port = None
    params = {
        "address": config.get("Interface", "Address", fallback=""),
        "dns": config.get("Interface", "DNS", fallback=""),
        "mtu": config.get("Interface", "MTU", fallback=""),
        "public_key": peer.get("PublicKey", ""),
        "endpoint": endpoint,
        "allowed_ips": peer.get("AllowedIPs", ""),
        "persistent_keepalive": peer.get("PersistentKeepalive", ""),
    }
    if proxy_type == ProxyType.AMNEZIAWG and config.has_section("Interface"):
        interface = config["Interface"]
        for key in (
            "Jc",
            "Jmin",
            "Jmax",
            "S1",
            "S2",
            "S3",
            "S4",
            "H1",
            "H2",
            "H3",
            "H4",
            "I1",
            "I2",
            "I3",
            "I4",
            "I5",
        ):
            value = str(interface.get(key, "")).strip()
            if value:
                params[key.lower()] = value
    params = {k: v for k, v in params.items() if v}
    return ParsedConfig(
        type=proxy_type,
        transport="udp",
        server_host=host,
        server_port=port,
        params=params,
    )


def _decode_ss_auth(payload: str) -> tuple[str, str]:
    decoded = decode_base64_padded(payload)
    if ":" not in decoded:
        raise ParseError("Invalid Shadowsocks credentials")
    cipher, password = decoded.split(":", 1)
    return cipher, password


def parse_shadowsocks(uri: str) -> ParsedConfig:
    parsed = urlparse(uri)
    host = parsed.hostname or ""
    port = parsed.port
    method = ""
    password = ""
    if parsed.username:
        method, password = _decode_ss_auth(parsed.username)
    else:
        payload = parsed.netloc
        if "@" in payload:
            auth, _, host_port = payload.rpartition("@")
            method, password = _decode_ss_auth(auth)
            if ":" in host_port:
                host, port_text = host_port.rsplit(":", 1)
                port = int(port_text)
        else:
            raise ParseError("Invalid Shadowsocks URI")
    params = {
        "method": method,
        "password": password,
        "plugin": parse_qs(parsed.query).get("plugin", [""])[0],
        "host": host,
        "port": str(port or ""),
    }
    params = {k: v for k, v in params.items() if v}
    return ParsedConfig(
        type=ProxyType.SHADOWSOCKS,
        transport="tcp",
        server_host=host,
        server_port=port,
        params=params,
        display_name=unquote(parsed.fragment or ""),
    )


def parse_trojan(uri: str) -> ParsedConfig:
    parsed = urlparse(uri)
    if not parsed.hostname or not parsed.port or not parsed.username:
        raise ParseError("Invalid Trojan URI")
    query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
    network = query.get("type", "tcp")
    security = "tls"
    params = {
        "password": unquote(parsed.username or ""),
        "host": parsed.hostname or "",
        "port": str(parsed.port or ""),
        "sni": query.get("sni", ""),
        "alpn": query.get("alpn", ""),
        "path": query.get("path", ""),
        "type": network,
    }
    params = {k: v for k, v in params.items() if v}
    return ParsedConfig(
        type=ProxyType.TROJAN,
        transport=f"{network}+{security}",
        server_host=parsed.hostname or "",
        server_port=parsed.port,
        params=params,
        display_name=unquote(parsed.fragment or ""),
    )


def decode_base64_padded(value: str) -> str:
    padding = len(value) % 4
    if padding:
        value += "=" * (4 - padding)
    return base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8")


def parse_subscription_payload(text: str) -> tuple[SubscriptionFormat, list[SubscriptionImportItem]]:
    stripped = text.strip()
    if not stripped:
        raise ParseError("Empty subscription response")

    if stripped.startswith("proxies:") or "\nproxies:" in stripped:
        items = parse_clash_yaml(stripped)
        return SubscriptionFormat.CLASH_YAML, items

    decoded = try_decode_base64_subscription(stripped)
    if decoded:
        return SubscriptionFormat.BASE64_URI_LIST, parse_uri_lines(decoded)

    return SubscriptionFormat.PLAIN_URI_LIST, parse_uri_lines(stripped)


def try_decode_base64_subscription(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text)
    if not compact or re.search(r"[^A-Za-z0-9+/=_-]", compact):
        return None
    try:
        decoded = decode_base64_padded(compact)
    except (UnicodeDecodeError, binascii.Error, ValueError):
        return None
    if "://" not in decoded:
        return None
    return decoded


def parse_uri_lines(text: str) -> list[SubscriptionImportItem]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items: list[SubscriptionImportItem] = []
    for index, line in enumerate(lines, start=1):
        try:
            parsed = parse_proxy_text(line)
        except ParseError:
            continue
        name = parsed.display_name or f"{parsed.type.value.lower()}-{index}"
        items.append(SubscriptionImportItem(name=name, uri=line, parsed=parsed))
    if not items:
        raise ParseError("No valid proxy URIs found in subscription payload")
    return items


def parse_clash_yaml(text: str) -> list[SubscriptionImportItem]:
    try:
        payload = yaml.safe_load(io.StringIO(text))
    except yaml.YAMLError as exc:
        raise ParseError(f"Invalid Clash YAML: {exc}") from exc
    proxies = payload.get("proxies") if isinstance(payload, dict) else None
    if not isinstance(proxies, list):
        raise ParseError("No proxies block found in Clash YAML")
    items: list[SubscriptionImportItem] = []
    for index, proxy in enumerate(proxies, start=1):
        if not isinstance(proxy, dict):
            continue
        item = clash_proxy_to_item(proxy, index)
        if item:
            items.append(item)
    if not items:
        raise ParseError("No supported proxies found in Clash YAML")
    return items


def clash_proxy_to_item(proxy: dict[str, Any], index: int) -> SubscriptionImportItem | None:
    proxy_name = str(proxy.get("name", f"proxy-{index}"))
    proxy_type = str(proxy.get("type", "")).lower()
    server = str(proxy.get("server", ""))
    port = proxy.get("port")

    if proxy_type in {"ss", "shadowsocks"}:
        cipher = str(proxy.get("cipher", ""))
        password = str(proxy.get("password", ""))
        auth = base64.urlsafe_b64encode(f"{cipher}:{password}".encode("utf-8")).decode("utf-8")
        uri = f"ss://{auth}@{server}:{port}#{proxy_name}"
    elif proxy_type == "trojan":
        sni = str(proxy.get("servername", proxy.get("sni", "")))
        uri = f"trojan://{proxy.get('password', '')}@{server}:{port}"
        if sni:
            uri += f"?sni={sni}"
        uri += f"#{proxy_name}"
    elif proxy_type in {"hysteria2", "hy2"}:
        password = str(proxy.get("password", ""))
        uri = f"hysteria2://{password}@{server}:{port}"
        params = []
        if proxy.get("sni"):
            params.append(f"sni={proxy['sni']}")
        if proxy.get("obfs"):
            params.append(f"obfs={proxy['obfs']}")
        if params:
            uri += "?" + "&".join(params)
        uri += f"#{proxy_name}"
    elif proxy_type in {"vless"}:
        uuid_value = str(proxy.get("uuid", ""))
        network = str(proxy.get("network", "tcp"))
        params = [f"type={network}"]
        if proxy.get("servername"):
            params.append(f"sni={proxy['servername']}")
        tls_enabled = proxy.get("tls") or proxy.get("security") == "tls"
        if tls_enabled:
            params.append("security=tls")
        if proxy.get("flow"):
            params.append(f"flow={proxy['flow']}")
        uri = f"vless://{uuid_value}@{server}:{port}"
        if params:
            uri += "?" + "&".join(params)
        uri += f"#{proxy_name}"
    else:
        return None

    parsed = parse_proxy_text(uri)
    return SubscriptionImportItem(name=proxy_name, uri=uri, parsed=parsed)


def build_clash_proxy(entry_name: str, uri: str) -> dict[str, Any]:
    parsed = parse_proxy_text(uri)
    if parsed.type == ProxyType.SHADOWSOCKS:
        auth = urlparse(uri).username or ""
        cipher, password = _decode_ss_auth(auth)
        return {
            "name": entry_name,
            "type": "ss",
            "server": parsed.server_host,
            "port": parsed.server_port,
            "cipher": cipher,
            "password": password,
        }
    if parsed.type == ProxyType.TROJAN:
        return {
            "name": entry_name,
            "type": "trojan",
            "server": parsed.server_host,
            "port": parsed.server_port,
            "password": parsed.params.get("password", ""),
            "sni": parsed.params.get("sni", ""),
        }
    if parsed.type == ProxyType.HYSTERIA2:
        return {
            "name": entry_name,
            "type": "hysteria2",
            "server": parsed.server_host,
            "port": parsed.server_port,
            "password": parsed.params.get("password", ""),
            "sni": parsed.params.get("sni", ""),
            "obfs": parsed.params.get("obfs", ""),
        }
    if parsed.type in {ProxyType.VLESS_REALITY, ProxyType.VLESS_WS, ProxyType.VLESS_XHTTP}:
        proxy: dict[str, Any] = {
            "name": entry_name,
            "type": "vless",
            "server": parsed.server_host,
            "port": parsed.server_port,
            "uuid": parsed.params.get("uuid", ""),
            "network": parsed.params.get("network", "tcp"),
        }
        if parsed.params.get("sni"):
            proxy["servername"] = parsed.params["sni"]
        if parsed.params.get("security"):
            proxy["security"] = parsed.params["security"]
        if parsed.params.get("flow"):
            proxy["flow"] = parsed.params["flow"]
        if parsed.params.get("path"):
            proxy["ws-opts"] = {"path": parsed.params["path"]}
        return proxy
    return {
        "name": entry_name,
        "type": parsed.type.value.lower(),
        "server": parsed.server_host,
        "port": parsed.server_port,
        "transport": parsed.transport,
        "uri": uri,
    }
