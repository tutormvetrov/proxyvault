from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from app.i18n import (
    SupportedLocale,
    Translator,
    build_reachability_copy,
    catalog_parity_report,
    describe_human_error,
    format_proxy_type,
    format_relative_time,
)
from app.i18n.catalog_en import CATALOG_EN
from app.i18n.catalog_ru import CATALOG_RU
from app.i18n.keys import KEY_REGISTRY, REQUIRED_NAMESPACE_PREFIXES
from app.models import ProxyEntry, ProxyType, ReachabilityState
from app.ui.i18n_patch import EXTRA_UI_KEY_REGISTRY, extra_ui_catalog_parity_report


def build_entry(**overrides) -> ProxyEntry:
    payload = {
        "id": "entry-1",
        "name": "Reachability Node",
        "uri": "vless://123e4567-e89b-12d3-a456-426614174000@edge.example.com:443?type=ws&security=tls#Node",
        "type": ProxyType.VLESS_WS,
        "transport": "ws+tls",
        "server_host": "edge.example.com",
        "server_port": 443,
        "uri_fingerprint": "fingerprint-current",
        "reachability_status": ReachabilityState.REACHABLE,
        "reachability_checked_at": datetime.utcnow().isoformat(),
        "reachability_latency_ms": 92,
        "reachability_duration_ms": 92,
        "reachability_method": "TCP probe",
        "reachability_endpoint": "edge.example.com:443",
        "reachability_config_fingerprint": "fingerprint-current",
    }
    payload.update(overrides)
    return ProxyEntry(**payload)


class TranslatorTests(unittest.TestCase):
    def test_default_locale_is_russian(self) -> None:
        translator = Translator()

        self.assertEqual(translator.locale, SupportedLocale.RU)
        self.assertEqual(translator.tr("menu.file"), "Файл")

    def test_switching_to_english_changes_strings(self) -> None:
        translator = Translator()

        translator.set_locale("en")

        self.assertEqual(translator.locale, SupportedLocale.EN)
        self.assertEqual(translator.tr("menu.file"), "File")
        self.assertEqual(translator.tr("action.connect"), "Connect")

    def test_parameterized_string_formats_values(self) -> None:
        translator = Translator()

        message = translator.tr("toast.saved_entry", name="Core Node")

        self.assertEqual(message, "Профиль «Core Node» сохранён.")

    def test_missing_key_is_explicit(self) -> None:
        translator = Translator()

        message = translator.tr("missing.namespace.key")

        self.assertEqual(message, "!!missing:missing.namespace.key!!")
        self.assertIn("missing.namespace.key", translator.missing_keys)

    def test_missing_format_param_is_explicit(self) -> None:
        translator = Translator()

        message = translator.tr("toast.saved_entry")

        self.assertEqual(message, "!!format:toast.saved_entry:name!!")

    def test_catalogs_have_strict_key_parity(self) -> None:
        self.assertEqual(set(CATALOG_RU.keys()), set(CATALOG_EN.keys()))
        self.assertEqual(catalog_parity_report(), {
            "missing_in_en": set(),
            "missing_in_ru": set(),
            "unexpected_in_en": set(),
            "unexpected_in_ru": set(),
        })
        self.assertEqual(
            extra_ui_catalog_parity_report(),
            {
                "missing_in_en": set(),
                "missing_in_ru": set(),
                "unexpected_in_en": set(),
                "unexpected_in_ru": set(),
            },
        )

    def test_required_taxonomy_prefixes_are_present(self) -> None:
        registry = KEY_REGISTRY

        for prefix in REQUIRED_NAMESPACE_PREFIXES:
            self.assertTrue(any(key.startswith(prefix) for key in registry), prefix)
        allowed_extra_prefixes = (
            "action.",
            "common.",
            "dialog.",
            "runtime.",
            "reachability.",
            "settings.",
            "sidebar.",
            "startup.",
            "card.",
            "detail.",
            "main.",
            "status.",
            "toast.",
            "onboarding.",
            "ui.",
        )
        for key in EXTRA_UI_KEY_REGISTRY:
            self.assertTrue(key.startswith(allowed_extra_prefixes), key)
        self.assertTrue(any(key.startswith("onboarding.") for key in EXTRA_UI_KEY_REGISTRY))


class FormatterTests(unittest.TestCase):
    def test_relative_time_is_localized_for_russian(self) -> None:
        translator = Translator()
        value = datetime(2026, 4, 22, 11, 55, 0)
        now = value + timedelta(minutes=3)

        message = format_relative_time(value, translator=translator, now=now)

        self.assertEqual(message, "3 минуты назад")

    def test_relative_time_is_localized_for_english(self) -> None:
        translator = Translator(locale="en")
        value = datetime(2026, 4, 22, 11, 55, 0)
        now = value + timedelta(hours=2)

        message = format_relative_time(value, translator=translator, now=now)

        self.assertEqual(message, "2 hours ago")

    def test_proxy_type_formatter_avoids_model_display_labels(self) -> None:
        translator = Translator(locale="en")

        self.assertEqual(format_proxy_type(ProxyType.SHADOWSOCKS, translator=translator), "Shadowsocks")
        self.assertEqual(format_proxy_type(ProxyType.OTHER, translator=translator), "Other")

    def test_reachability_copy_is_localized_and_outside_models(self) -> None:
        stale_time = datetime(2026, 4, 21, 10, 0, 0)
        entry = build_entry(
            reachability_checked_at=stale_time.isoformat(),
            reachability_config_fingerprint="fingerprint-old",
        )
        translator = Translator()

        copy = build_reachability_copy(
            entry,
            translator=translator,
            now=datetime(2026, 4, 22, 12, 0, 0),
        )

        self.assertEqual(copy.status_label, "Устарело")
        self.assertEqual(copy.freshness_label, "Нужна новая проверка после изменения конфигурации")
        self.assertEqual(copy.card_hint, "Конфигурация изменилась")
        self.assertIn("конфигурация изменилась", copy.detail_summary.lower())

    def test_udp_reachability_copy_explains_runtime_based_verification(self) -> None:
        entry = build_entry(
            type=ProxyType.WIREGUARD,
            transport="udp",
            server_port=51820,
            reachability_status=ReachabilityState.FAILED,
            reachability_checked_at=datetime.utcnow().isoformat(),
            reachability_method="Runtime and Handshake",
            reachability_failure_reason="Таймаут подключения",
        )
        translator = Translator()

        copy = build_reachability_copy(entry, translator=translator)

        self.assertEqual(copy.status_label, "Ошибка")
        self.assertEqual(copy.card_label, "Ошибка")
        self.assertIn("таймаут", copy.detail_summary.lower())
        self.assertIn("таймаут", copy.reason_text.lower())

    def test_wireguard_runtime_errors_are_humanized(self) -> None:
        helper_missing = describe_human_error("runtime.error.wireguard.helper_not_found", translator=Translator())
        bundle_incomplete = describe_human_error("runtime.error.wireguard.bundle_incomplete", translator=Translator())
        invalid_config = describe_human_error("runtime.error.wireguard.invalid_config", translator=Translator())
        handshake_missing = describe_human_error("runtime.error.wireguard.handshake_missing", translator=Translator())

        self.assertIn("компонента", helper_missing.title.lower())
        self.assertIn("сборк", bundle_incomplete.title.lower())
        self.assertIn("конфигурац", invalid_config.title.lower())
        self.assertIn("рукопожат", handshake_missing.title.lower())

    def test_human_error_dictionary_is_bilingual(self) -> None:
        ru_error = describe_human_error("port_in_use", translator=Translator())
        en_error = describe_human_error("port_in_use", translator=Translator(locale="en"))

        self.assertIn("порт", ru_error.title.lower())
        self.assertIn("port", en_error.title.lower())
        self.assertNotEqual(ru_error.summary, en_error.summary)


if __name__ == "__main__":
    unittest.main()
