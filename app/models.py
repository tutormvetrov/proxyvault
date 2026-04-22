from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

from app.paths import default_qr_output_dir


class ProxyType(str, Enum):
    VLESS_REALITY = "VLESS_REALITY"
    VLESS_WS = "VLESS_WS"
    VLESS_XHTTP = "VLESS_XHTTP"
    HYSTERIA2 = "HYSTERIA2"
    NAIVE_PROXY = "NAIVE_PROXY"
    WIREGUARD = "WIREGUARD"
    SHADOWSOCKS = "SHADOWSOCKS"
    TROJAN = "TROJAN"
    OTHER = "OTHER"


TYPE_LABELS = {
    ProxyType.VLESS_REALITY: "VLESS Reality",
    ProxyType.VLESS_WS: "VLESS WS",
    ProxyType.VLESS_XHTTP: "VLESS XHTTP",
    ProxyType.HYSTERIA2: "Hysteria2",
    ProxyType.NAIVE_PROXY: "NaiveProxy",
    ProxyType.WIREGUARD: "WireGuard",
    ProxyType.SHADOWSOCKS: "Shadowsocks",
    ProxyType.TROJAN: "Trojan",
    ProxyType.OTHER: "Other",
}


TYPE_COLORS = {
    ProxyType.VLESS_REALITY: "#7EA7A4",
    ProxyType.VLESS_WS: "#79AEC7",
    ProxyType.VLESS_XHTTP: "#89B58D",
    ProxyType.HYSTERIA2: "#D08E66",
    ProxyType.NAIVE_PROXY: "#90A8D7",
    ProxyType.WIREGUARD: "#9FB37D",
    ProxyType.SHADOWSOCKS: "#C98579",
    ProxyType.TROJAN: "#8EA4AA",
    ProxyType.OTHER: "#B39E88",
}


TYPE_SOFT_COLORS = {
    ProxyType.VLESS_REALITY: "#E6F0EF",
    ProxyType.VLESS_WS: "#E8F2F8",
    ProxyType.VLESS_XHTTP: "#EAF3EB",
    ProxyType.HYSTERIA2: "#F7EADF",
    ProxyType.NAIVE_PROXY: "#EAF0FB",
    ProxyType.WIREGUARD: "#EEF3E4",
    ProxyType.SHADOWSOCKS: "#F7E8E4",
    ProxyType.TROJAN: "#EAF0F1",
    ProxyType.OTHER: "#F1E8DE",
}


TYPE_TEXT_COLORS = {
    ProxyType.VLESS_REALITY: "#496766",
    ProxyType.VLESS_WS: "#4F7084",
    ProxyType.VLESS_XHTTP: "#5E765F",
    ProxyType.HYSTERIA2: "#8A6149",
    ProxyType.NAIVE_PROXY: "#5F7096",
    ProxyType.WIREGUARD: "#64724E",
    ProxyType.SHADOWSOCKS: "#835C54",
    ProxyType.TROJAN: "#5B6A70",
    ProxyType.OTHER: "#6F6152",
}


class SubscriptionFormat(str, Enum):
    BASE64_URI_LIST = "base64_uri_list"
    PLAIN_URI_LIST = "plain_uri_list"
    CLASH_YAML = "clash_yaml"


class ReachabilityState(str, Enum):
    NOT_TESTED = "NOT_TESTED"
    REACHABLE = "REACHABLE"
    FAILED = "FAILED"


REACHABILITY_STALE_AFTER = timedelta(hours=12)


@dataclass(slots=True)
class ReachabilityCheck:
    checked_at: str
    status: ReachabilityState
    endpoint: str = ""
    method: str = "TCP probe"
    latency_ms: int | None = None
    duration_ms: int | None = None
    failure_reason: str = ""
    error_category: str = ""
    details: str = ""
    config_fingerprint: str = ""
    id: int = 0

    @property
    def checked_at_obj(self) -> datetime | None:
        return parse_iso_datetime(self.checked_at)

    @property
    def tone(self) -> str:
        if self.status == ReachabilityState.REACHABLE:
            return "success"
        if self.status == ReachabilityState.FAILED:
            return "danger"
        return "muted"

    @property
    def status_label(self) -> str:
        if self.status == ReachabilityState.REACHABLE:
            return "Reachable"
        if self.status == ReachabilityState.FAILED:
            return "Failed"
        return "Not tested"


@dataclass(slots=True)
class ParsedConfig:
    type: ProxyType
    transport: str
    server_host: str
    server_port: int | None
    params: dict[str, str] = field(default_factory=dict)
    display_name: str = ""


@dataclass(slots=True)
class ProxyEntry:
    id: str
    name: str
    uri: str
    type: ProxyType
    transport: str
    server_host: str
    server_port: int | None
    tags: str = ""
    notes: str = ""
    qr_png_path: str = ""
    created_at: str = ""
    updated_at: str = ""
    is_favorite: bool = False
    expiry_date: str = ""
    is_locked: bool = False
    uri_fingerprint: str = ""
    reachability_status: ReachabilityState = ReachabilityState.NOT_TESTED
    reachability_checked_at: str = ""
    reachability_latency_ms: int | None = None
    reachability_duration_ms: int | None = None
    reachability_method: str = ""
    reachability_endpoint: str = ""
    reachability_failure_reason: str = ""
    reachability_error_category: str = ""
    reachability_details: str = ""
    reachability_config_fingerprint: str = ""

    @property
    def tag_list(self) -> list[str]:
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

    @property
    def display_host_port(self) -> str:
        if self.server_host and self.server_port:
            return f"{self.server_host}:{self.server_port}"
        if self.server_host:
            return self.server_host
        return "Unknown endpoint"

    @property
    def expiry_date_obj(self) -> date | None:
        if not self.expiry_date:
            return None
        try:
            return date.fromisoformat(self.expiry_date)
        except ValueError:
            return None

    @property
    def expires_soon(self) -> bool:
        expiry = self.expiry_date_obj
        if not expiry:
            return False
        return (expiry - date.today()).days < 14

    @property
    def reachability_checked_at_obj(self) -> datetime | None:
        return parse_iso_datetime(self.reachability_checked_at)

    @property
    def reachability_has_result(self) -> bool:
        return bool(self.reachability_checked_at) and self.reachability_status != ReachabilityState.NOT_TESTED

    @property
    def reachability_is_stale(self) -> bool:
        checked_at = self.reachability_checked_at_obj
        if not checked_at or not self.reachability_has_result:
            return False
        if self.reachability_is_config_changed:
            return True
        return datetime.utcnow() - checked_at >= REACHABILITY_STALE_AFTER

    @property
    def reachability_is_config_changed(self) -> bool:
        return (
            bool(self.reachability_config_fingerprint)
            and bool(self.uri_fingerprint)
            and self.reachability_config_fingerprint != self.uri_fingerprint
        )

    @property
    def reachability_display_state(self) -> str:
        if not self.reachability_has_result:
            return "not_tested"
        if self.reachability_is_stale:
            return "stale"
        if self.reachability_status == ReachabilityState.REACHABLE:
            return "reachable"
        if self.reachability_status == ReachabilityState.FAILED:
            return "failed"
        return "not_tested"

    @property
    def reachability_tone(self) -> str:
        return {
            "reachable": "success",
            "failed": "danger",
            "stale": "warning",
            "not_tested": "muted",
        }[self.reachability_display_state]

    @property
    def reachability_status_label(self) -> str:
        state = self.reachability_display_state
        if state == "reachable":
            return "Reachable"
        if state == "failed":
            return "Failed"
        if state == "stale":
            return "Stale"
        return "Not tested"

    @property
    def reachability_freshness_label(self) -> str:
        if not self.reachability_has_result:
            return "Never checked"
        if self.reachability_is_stale:
            if self.reachability_is_config_changed:
                return "Needs recheck after config change"
            return "Stale result"
        return "Fresh result"

    @property
    def reachability_last_checked_label(self) -> str:
        checked_at = self.reachability_checked_at_obj
        if not checked_at:
            return "Never checked"
        return f"Checked {format_relative_time(checked_at)}"

    @property
    def reachability_card_hint(self) -> str:
        if not self.reachability_has_result:
            return "No probe yet"
        if self.reachability_is_config_changed:
            return "Config changed"
        checked_at = self.reachability_checked_at_obj
        if not checked_at:
            return self.reachability_freshness_label
        return format_relative_time(checked_at)

    @property
    def reachability_card_label(self) -> str:
        state = self.reachability_display_state
        if state == "not_tested":
            return "Pending"
        if state == "stale":
            if self.reachability_latency_ms is not None and self.reachability_status == ReachabilityState.REACHABLE:
                return f"Stale · {format_duration_ms(self.reachability_latency_ms)}"
            return "Stale"
        if state == "reachable":
            if self.reachability_latency_ms is not None:
                return f"Reachable · {format_duration_ms(self.reachability_latency_ms)}"
            return "Reachable"
        return "Failed"

    @property
    def reachability_detail_summary(self) -> str:
        if not self.reachability_has_result:
            return "No TCP probe has been run for this entry yet."
        if self.reachability_display_state == "stale":
            if self.reachability_is_config_changed:
                return "The configuration changed after the last TCP probe. Run a fresh check before trusting the old result."
            return "The last TCP probe is stale. Run a fresh check before trusting this result."
        if self.reachability_status == ReachabilityState.REACHABLE:
            latency = (
                f" in {format_duration_ms(self.reachability_latency_ms)}"
                if self.reachability_latency_ms is not None
                else ""
            )
            return f"TCP connection to {self.reachability_endpoint or self.display_host_port} succeeded{latency}."
        failure_reason = self.reachability_failure_reason or "The TCP connection could not be established."
        return failure_reason


@dataclass(slots=True)
class QROptions:
    error_correction: str = "M"
    version: int = 0
    box_size: int = 10
    border: int = 4
    fg_color: str = "#111111"
    bg_color: str = "#FFFFFF"

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_correction": self.error_correction,
            "version": self.version,
            "box_size": self.box_size,
            "border": self.border,
            "fg_color": self.fg_color,
            "bg_color": self.bg_color,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "QROptions":
        payload = payload or {}
        return cls(
            error_correction=str(payload.get("error_correction", "M")),
            version=int(payload.get("version", 0)),
            box_size=int(payload.get("box_size", 10)),
            border=int(payload.get("border", 4)),
            fg_color=str(payload.get("fg_color", "#111111")),
            bg_color=str(payload.get("bg_color", "#FFFFFF")),
        )


@dataclass(slots=True)
class AppSettings:
    output_folder: str
    default_qr: QROptions = field(default_factory=QROptions)
    theme: str = "system"
    subscription_refresh_interval: str = "never"
    allow_insecure_subscription_http: bool = False
    has_seen_welcome: bool = False

    @classmethod
    def default(cls) -> "AppSettings":
        return cls(
            output_folder=str(default_qr_output_dir()),
            default_qr=QROptions(),
            theme="system",
            subscription_refresh_interval="never",
            allow_insecure_subscription_http=False,
            has_seen_welcome=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_folder": self.output_folder,
            "default_qr": self.default_qr.to_dict(),
            "theme": self.theme,
            "subscription_refresh_interval": self.subscription_refresh_interval,
            "allow_insecure_subscription_http": self.allow_insecure_subscription_http,
            "has_seen_welcome": self.has_seen_welcome,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "AppSettings":
        payload = payload or {}
        default = cls.default()
        return cls(
            output_folder=str(payload.get("output_folder", default.output_folder)),
            default_qr=QROptions.from_dict(payload.get("default_qr")),
            theme=str(payload.get("theme", default.theme)),
            subscription_refresh_interval=str(
                payload.get(
                    "subscription_refresh_interval",
                    default.subscription_refresh_interval,
                )
            ),
            allow_insecure_subscription_http=bool(
                payload.get("allow_insecure_subscription_http", default.allow_insecure_subscription_http)
            ),
            has_seen_welcome=bool(payload.get("has_seen_welcome", False)),
        )


@dataclass(slots=True)
class SubscriptionRecord:
    id: str
    url: str
    refresh_interval: str = "never"
    last_fetched: str = ""
    created_at: str = ""


@dataclass(slots=True)
class SubscriptionImportItem:
    name: str
    uri: str
    parsed: ParsedConfig
    selected: bool = True


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def format_duration_ms(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value >= 1000:
        seconds = value / 1000
        return f"{seconds:.1f} s"
    return f"{value} ms"


def format_relative_time(value: datetime) -> str:
    delta = datetime.utcnow() - value
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} h ago"
    days = hours // 24
    if days < 7:
        return f"{days} d ago"
    return value.strftime("%Y-%m-%d %H:%M")


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()
