from __future__ import annotations

from app.i18n.catalog_en import CATALOG_EN
from app.i18n.catalog_ru import CATALOG_RU


REQUIRED_NAMESPACE_PREFIXES: tuple[str, ...] = (
    "app.",
    "menu.",
    "toolbar.",
    "action.",
    "common.",
    "settings.",
    "runtime.",
    "reachability.",
    "dialog.",
    "onboarding.",
    "help.",
    "error.",
    "toast.",
)

KEY_TAXONOMY: dict[str, str] = {
    "app.*": "Application identity and fatal startup flows.",
    "menu.*": "Top-level menu labels.",
    "toolbar.*": "Toolbar labels, placeholders, sort options, and status pills.",
    "action.*": "Reusable action labels for menus, buttons, and shortcuts.",
    "common.*": "Shared nouns, fields, durations, locale names, and relative-time phrases.",
    "section.*": "Section headers shared across screens.",
    "proxy_type.*": "User-facing labels for proxy kinds.",
    "subscription.*": "Subscription format labels.",
    "reachability.*": "Reachability states, summaries, and diagnostics copy.",
    "runtime.*": "Runtime states, route ownership labels, and connection summaries.",
    "dialog.*": "Dialog titles, placeholders, validation messages, and welcome copy.",
    "settings.*": "Settings-specific labels, options, and validation strings.",
    "onboarding.*": "Short quick-start copy blocks.",
    "help.*": "Structured help-center titles and body copy.",
    "error.*": "Human-readable normalized error dictionary.",
    "toast.*": "Transient success and failure notifications.",
    "detail.*": "Detail-panel-specific strings that do not fit the shared namespaces.",
}

KEY_REGISTRY = frozenset(CATALOG_RU.keys())


def missing_keys(reference: dict[str, str], candidate: dict[str, str]) -> set[str]:
    return set(reference.keys()) - set(candidate.keys())


def unexpected_keys(reference: dict[str, str], candidate: dict[str, str]) -> set[str]:
    return set(candidate.keys()) - set(reference.keys())


def catalog_parity_report() -> dict[str, set[str]]:
    return {
        "missing_in_en": missing_keys(CATALOG_RU, CATALOG_EN),
        "missing_in_ru": missing_keys(CATALOG_EN, CATALOG_RU),
        "unexpected_in_en": unexpected_keys(CATALOG_RU, CATALOG_EN),
        "unexpected_in_ru": unexpected_keys(CATALOG_EN, CATALOG_RU),
    }
