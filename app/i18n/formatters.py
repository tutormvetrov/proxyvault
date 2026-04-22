from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.help.glossary_en import ERROR_GLOSSARY_EN
from app.help.glossary_ru import ERROR_GLOSSARY_RU
from app.models import ProxyEntry, ProxyType, ReachabilityState

from app.i18n.locales import SupportedLocale
from app.i18n.service import get_service
from app.i18n.translator import Translator


@dataclass(slots=True)
class ReachabilityCopy:
    status_label: str
    freshness_label: str
    last_checked_label: str
    card_hint: str
    card_label: str
    detail_summary: str
    reason_text: str


@dataclass(slots=True)
class HumanErrorCopy:
    title: str
    summary: str
    action: str


def _translator(translator: Translator | None) -> Translator:
    return translator or get_service()


def _plural_form(locale: SupportedLocale, count: int) -> str:
    if locale == SupportedLocale.RU:
        remainder_10 = count % 10
        remainder_100 = count % 100
        if remainder_10 == 1 and remainder_100 != 11:
            return "one"
        if remainder_10 in {2, 3, 4} and remainder_100 not in {12, 13, 14}:
            return "few"
        return "many"
    return "one" if count == 1 else "many"


def format_duration_ms(value: int | None, *, translator: Translator | None = None) -> str:
    tx = _translator(translator)
    if value is None:
        return tx.tr("common.not_available")
    if value >= 1000:
        return tx.tr("common.duration.seconds", value=f"{value / 1000:.1f}")
    return tx.tr("common.duration.ms", value=value)


def format_relative_time(
    value: datetime | None,
    *,
    translator: Translator | None = None,
    now: datetime | None = None,
) -> str:
    tx = _translator(translator)
    if value is None:
        return tx.tr("common.not_available")
    now_value = now or datetime.utcnow()
    delta = now_value - value
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return tx.tr("common.relative_time.just_now")
    minutes = seconds // 60
    if minutes < 60:
        form = _plural_form(tx.locale, minutes)
        return tx.tr(f"common.relative_time.minute_ago.{form}", count=minutes)
    hours = minutes // 60
    if hours < 24:
        form = _plural_form(tx.locale, hours)
        return tx.tr(f"common.relative_time.hour_ago.{form}", count=hours)
    days = hours // 24
    if days < 7:
        form = _plural_form(tx.locale, days)
        return tx.tr(f"common.relative_time.day_ago.{form}", count=days)
    return value.strftime("%Y-%m-%d %H:%M")


def format_last_checked(
    value: datetime | None,
    *,
    translator: Translator | None = None,
    now: datetime | None = None,
) -> str:
    tx = _translator(translator)
    if value is None:
        return tx.tr("reachability.last_checked.never")
    return tx.tr("common.relative_time.checked_prefix", value=format_relative_time(value, translator=tx, now=now))


def format_proxy_type(value: ProxyType | str, *, translator: Translator | None = None) -> str:
    tx = _translator(translator)
    proxy_type = value if isinstance(value, ProxyType) else _coerce_proxy_type(value)
    mapping = {
        ProxyType.VLESS_REALITY: "proxy_type.vless_reality",
        ProxyType.VLESS_WS: "proxy_type.vless_ws",
        ProxyType.VLESS_XHTTP: "proxy_type.vless_xhttp",
        ProxyType.HYSTERIA2: "proxy_type.hysteria2",
        ProxyType.NAIVE_PROXY: "proxy_type.naive_proxy",
        ProxyType.WIREGUARD: "proxy_type.wireguard",
        ProxyType.AMNEZIAWG: "proxy_type.amneziawg",
        ProxyType.SHADOWSOCKS: "proxy_type.shadowsocks",
        ProxyType.TROJAN: "proxy_type.trojan",
        ProxyType.OTHER: "proxy_type.other",
    }
    return tx.tr(mapping[proxy_type])


def format_runtime_state(value: str, *, translator: Translator | None = None) -> str:
    tx = _translator(translator)
    key = {
        "DISCONNECTED": "runtime.state.disconnected",
        "STARTING": "runtime.state.starting",
        "RUNNING": "runtime.state.running",
        "STOPPING": "runtime.state.stopping",
        "ERROR": "runtime.state.error",
        "PRIMARY": "runtime.state.primary",
        "WIREGUARD_ACTIVE": "runtime.state.wireguard_active",
    }.get(str(value).upper(), "")
    return tx.tr(key) if key else tx.tr("common.unknown")


def format_route_owner(value: str, *, translator: Translator | None = None) -> str:
    tx = _translator(translator)
    key = {
        "NONE": "runtime.route.none",
        "PROXY": "runtime.route.proxy",
        "WIREGUARD": "runtime.route.wireguard",
    }.get(str(value).upper(), "")
    return tx.tr(key) if key else tx.tr("common.unknown")


def normalize_human_error_code(code: str, *, detail: str = "") -> str:
    normalized = str(code or "").strip().lower()
    detail_text = str(detail or "").strip().lower()

    alias_map = {
        "runtime.error.launch_prepare_failed": "engine_failed_to_start",
        "runtime.error.launch_start_failed": "engine_failed_to_start",
        "runtime.error.stop_failed": "process_exited_early",
        "runtime.error.poll_failed": "process_exited_early",
        "runtime.error.engine_crash": "process_exited_early",
        "runtime.error.system_proxy_apply_failed": "system_proxy_apply_failed",
        "runtime.error.primary_requires_running_session": "engine_failed_to_start",
        "runtime.error.unsupported_entry_type": "engine_failed_to_start",
        "runtime.error.adapter_not_found": "engine_failed_to_start",
        "runtime.error.entry_not_found": "unknown",
        "runtime.error.wireguard.helper_not_found": "runtime_component_missing",
        "runtime.error.wireguard.bundle_incomplete": "runtime_bundle_incomplete",
        "runtime.error.wireguard.invalid_config": "invalid_configuration",
        "runtime.error.wireguard.handshake_missing": "handshake_missing",
        "runtime.error.wireguard.privileges_required": "wireguard_confirmation_required",
        "runtime.error.wireguard.system_prompt_denied": "wireguard_confirmation_required",
        "runtime.error.wireguard.tunnel_exited_early": "process_exited_early",
        "runtime.error.wireguard.system_conflict": "system_conflict",
        "service_conflict": "system_conflict",
        "wireguard_confirmation_required": "wireguard_confirmation_required",
        "wireguard_elevation_required": "wireguard_confirmation_required",
    }
    if normalized in alias_map:
        return alias_map[normalized]

    known_codes = {
        "server_unreachable",
        "engine_failed_to_start",
        "port_in_use",
        "authentication_failed",
        "system_proxy_apply_failed",
        "wireguard_confirmation_required",
        "runtime_component_missing",
        "runtime_bundle_incomplete",
        "invalid_configuration",
        "handshake_missing",
        "handshake_stale",
        "system_conflict",
        "process_exited_early",
        "unknown",
    }
    if normalized in known_codes:
        return normalized

    detection_tokens = (
        ("port_in_use", ("address already in use", "port already in use", "only one usage", "занят")),
        (
            "authentication_failed",
            ("authentication", "forbidden", "unauthorized", "invalid key", "invalid password", "auth"),
        ),
        (
            "wireguard_confirmation_required",
            ("access is denied", "permission denied", "authorization", "elevation", "administrator"),
        ),
        (
            "system_conflict",
            ("split tunnel", "file already exists", "already exists", "невозможно создать файл"),
        ),
        (
            "runtime_bundle_incomplete",
            (
                "build is incomplete",
                "bundled wireguard",
                "bootstrap metadata is missing",
                "bootstrap payload is missing",
                "checksum mismatch",
                "hash mismatch",
            ),
        ),
        ("runtime_component_missing", ("install the official", "not installed", "helper not found", "missing helper")),
        ("invalid_configuration", ("parse", "invalid config", "raw wireguard profile", "[interface]", "[peer]")),
        ("handshake_missing", ("handshake not established", "handshake missing", "no handshake")),
        ("handshake_stale", ("handshake", "рукопожат")),
        ("server_unreachable", ("timed out", "timeout", "refused", "unreachable", "network is unreachable")),
    )
    for candidate, tokens in detection_tokens:
        if any(token in detail_text for token in tokens):
            return candidate
    return "unknown"


def describe_human_error(code: str, *, detail: str = "", translator: Translator | None = None) -> HumanErrorCopy:
    tx = _translator(translator)
    safe_code = normalize_human_error_code(code, detail=detail)
    glossary = ERROR_GLOSSARY_RU if tx.locale == SupportedLocale.RU else ERROR_GLOSSARY_EN
    glossary_payload = glossary.get(safe_code)
    if glossary_payload:
        return HumanErrorCopy(
            title=glossary_payload["title"],
            summary=glossary_payload["summary"],
            action=glossary_payload["next_step"],
        )
    catalog_safe_code = {
        "engine_failed_to_start": "process_exited_early",
        "wireguard_confirmation_required": "wireguard_elevation_required",
    }.get(safe_code, safe_code)
    return HumanErrorCopy(
        title=tx.tr(f"error.{catalog_safe_code}.title"),
        summary=tx.tr(f"error.{catalog_safe_code}.summary"),
        action=tx.tr(f"error.{catalog_safe_code}.action"),
    )


def format_ui_error(
    summary_key: str,
    *,
    detail: object = "",
    translator: Translator | None = None,
) -> str:
    tx = _translator(translator)
    summary = tx.tr(summary_key)
    detail_text = str(detail or "").strip()
    if not detail_text or detail_text == summary or detail_text.startswith("!!missing:"):
        return summary
    return tx.tr("ui.error.with_detail", summary=summary, detail=detail_text)


def build_reachability_copy(
    entry: ProxyEntry,
    *,
    translator: Translator | None = None,
    now: datetime | None = None,
) -> ReachabilityCopy:
    tx = _translator(translator)
    display_state = _reachability_display_state(entry)

    if display_state == "not_applicable":
        checked_at = entry.reachability_checked_at_obj
        detail_summary = tx.tr(
            "reachability.summary.not_applicable",
            type_label=format_proxy_type(entry.type, translator=tx),
            transport=entry.transport or tx.tr("common.not_available"),
        )
        return ReachabilityCopy(
            status_label=tx.tr("reachability.state.not_applicable"),
            freshness_label=tx.tr("reachability.freshness.not_applicable"),
            last_checked_label=(
                format_last_checked(checked_at, translator=tx, now=now)
                if checked_at is not None
                else tx.tr("reachability.last_checked.not_applicable")
            ),
            card_hint=tx.tr("reachability.hint.not_applicable"),
            card_label=tx.tr("reachability.card.not_applicable"),
            detail_summary=detail_summary,
            reason_text=tx.tr("reachability.reason.not_applicable"),
        )

    if not entry.reachability_has_result:
        return ReachabilityCopy(
            status_label=tx.tr("reachability.state.not_tested"),
            freshness_label=tx.tr("reachability.freshness.never"),
            last_checked_label=tx.tr("reachability.last_checked.never"),
            card_hint=tx.tr("reachability.hint.none"),
            card_label=tx.tr("reachability.card.pending"),
            detail_summary=tx.tr("reachability.summary.none"),
            reason_text=tx.tr("reachability.reason.no_result"),
        )

    checked_at = entry.reachability_checked_at_obj
    last_checked_label = format_last_checked(checked_at, translator=tx, now=now)

    if display_state == "stale":
        freshness_label = (
            tx.tr("reachability.freshness.config_changed")
            if entry.reachability_is_config_changed
            else tx.tr("reachability.freshness.stale")
        )
        detail_summary = (
            tx.tr(
                "reachability.summary.config_changed"
                if entry.reachability_supports_tcp_probe
                else "reachability.summary.runtime_config_changed"
            )
            if entry.reachability_is_config_changed
            else tx.tr(
                "reachability.summary.stale"
                if entry.reachability_supports_tcp_probe
                else "reachability.summary.runtime_stale"
            )
        )
        reason_text = (
            tx.tr(
                "reachability.reason.config_changed"
                if entry.reachability_supports_tcp_probe
                else "reachability.reason.runtime_config_changed"
            )
            if entry.reachability_is_config_changed
            else entry.reachability_failure_reason or tx.tr("reachability.reason.failure_default")
        )
    elif display_state == "reachable":
        freshness_label = tx.tr("reachability.freshness.fresh")
        detail_summary = tx.tr(
            "reachability.summary.success"
            if entry.reachability_supports_tcp_probe
            else "reachability.summary.runtime_success",
            type_label=format_proxy_type(entry.type, translator=tx),
            endpoint=entry.reachability_endpoint or entry.display_host_port,
            latency_suffix=_latency_suffix(entry.reachability_latency_ms, translator=tx),
        )
        reason_text = entry.reachability_failure_reason or tx.tr(
            "reachability.reason.success"
            if entry.reachability_supports_tcp_probe
            else "reachability.reason.runtime_success"
        )
    else:
        freshness_label = tx.tr("reachability.freshness.fresh")
        detail_summary = entry.reachability_failure_reason or tx.tr(
            "reachability.summary.failure_default"
            if entry.reachability_supports_tcp_probe
            else "reachability.summary.runtime_failure_default",
            type_label=format_proxy_type(entry.type, translator=tx),
            endpoint=entry.reachability_endpoint or entry.display_host_port,
        )
        reason_text = entry.reachability_failure_reason or tx.tr(
            "reachability.reason.failure_default"
            if entry.reachability_supports_tcp_probe
            else "reachability.reason.runtime_failure_default"
        )

    return ReachabilityCopy(
        status_label=_reachability_status_label(entry, translator=tx),
        freshness_label=freshness_label,
        last_checked_label=last_checked_label,
        card_hint=_reachability_card_hint(entry, translator=tx, now=now),
        card_label=_reachability_card_label(entry, translator=tx),
        detail_summary=detail_summary,
        reason_text=reason_text,
    )


def _coerce_proxy_type(value: str) -> ProxyType:
    try:
        return ProxyType(str(value))
    except ValueError:
        return ProxyType.OTHER


def _reachability_display_state(entry: ProxyEntry) -> str:
    if not entry.reachability_supports_tcp_probe and (
        not entry.reachability_has_result or entry.reachability_status == ReachabilityState.NOT_APPLICABLE
    ):
        return "not_applicable"
    if not entry.reachability_has_result:
        return "not_tested"
    if entry.reachability_is_stale:
        return "stale"
    if entry.reachability_status == ReachabilityState.REACHABLE:
        return "reachable"
    if entry.reachability_status == ReachabilityState.FAILED:
        return "failed"
    return "not_tested"


def _reachability_status_label(entry: ProxyEntry, *, translator: Translator) -> str:
    state = _reachability_display_state(entry)
    return translator.tr(
        {
            "reachable": "reachability.state.reachable",
            "failed": "reachability.state.failed",
            "stale": "reachability.state.stale",
            "not_applicable": "reachability.state.not_applicable",
        }.get(state, "reachability.state.not_tested")
    )


def _reachability_card_hint(
    entry: ProxyEntry,
    *,
    translator: Translator,
    now: datetime | None = None,
) -> str:
    if not entry.reachability_supports_tcp_probe and (
        not entry.reachability_has_result or entry.reachability_status == ReachabilityState.NOT_APPLICABLE
    ):
        return translator.tr("reachability.hint.not_applicable")
    if not entry.reachability_has_result:
        return translator.tr("reachability.hint.none")
    if entry.reachability_is_config_changed:
        return translator.tr("reachability.hint.config_changed")
    return format_relative_time(entry.reachability_checked_at_obj, translator=translator, now=now)


def _reachability_card_label(entry: ProxyEntry, *, translator: Translator) -> str:
    state = _reachability_display_state(entry)
    latency_text = format_duration_ms(entry.reachability_latency_ms, translator=translator)
    if state == "not_applicable":
        return translator.tr("reachability.card.not_applicable")
    if state == "stale":
        if entry.reachability_latency_ms is not None and entry.reachability_status == ReachabilityState.REACHABLE:
            return translator.tr("reachability.card.stale_with_latency", latency=latency_text)
        return translator.tr("reachability.card.stale")
    if state == "reachable":
        if entry.reachability_latency_ms is not None:
            return translator.tr("reachability.card.reachable_with_latency", latency=latency_text)
        return translator.tr("reachability.card.reachable")
    if state == "failed":
        return translator.tr("reachability.card.failed")
    return translator.tr("reachability.card.pending")


def _latency_suffix(latency_ms: int | None, *, translator: Translator) -> str:
    if latency_ms is None:
        return ""
    return f" ({format_duration_ms(latency_ms, translator=translator)})"
