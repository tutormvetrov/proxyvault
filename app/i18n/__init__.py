from __future__ import annotations

from app.i18n.formatters import (
    HumanErrorCopy,
    ReachabilityCopy,
    build_reachability_copy,
    describe_human_error,
    format_duration_ms,
    format_ui_error,
    format_last_checked,
    format_proxy_type,
    format_relative_time,
    format_route_owner,
    format_runtime_state,
    normalize_human_error_code,
)
from app.i18n.keys import KEY_REGISTRY, KEY_TAXONOMY, REQUIRED_NAMESPACE_PREFIXES, catalog_parity_report
from app.i18n.locales import SUPPORTED_LOCALES, SupportedLocale
from app.i18n.service import LocalizationService, get_locale, get_service, set_locale, tr
from app.i18n.translator import Translator

__all__ = [
    "HumanErrorCopy",
    "KEY_REGISTRY",
    "KEY_TAXONOMY",
    "LocalizationService",
    "REQUIRED_NAMESPACE_PREFIXES",
    "ReachabilityCopy",
    "SUPPORTED_LOCALES",
    "SupportedLocale",
    "Translator",
    "build_reachability_copy",
    "catalog_parity_report",
    "describe_human_error",
    "format_duration_ms",
    "format_last_checked",
    "format_proxy_type",
    "format_relative_time",
    "format_route_owner",
    "format_runtime_state",
    "format_ui_error",
    "get_locale",
    "get_service",
    "normalize_human_error_code",
    "set_locale",
    "tr",
]
