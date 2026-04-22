from __future__ import annotations

from app.i18n.locales import SupportedLocale
from app.i18n.translator import Translator


class LocalizationService(Translator):
    """App-level translator with a stable ru-first default policy."""


_SERVICE = LocalizationService(locale=SupportedLocale.default())


def get_service() -> LocalizationService:
    return _SERVICE


def get_locale() -> SupportedLocale:
    return _SERVICE.locale


def set_locale(locale: SupportedLocale | str | None) -> SupportedLocale:
    return _SERVICE.set_locale(locale)


def tr(key: str, **params: object) -> str:
    return _SERVICE.tr(key, **params)
