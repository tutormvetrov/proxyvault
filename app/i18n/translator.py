from __future__ import annotations

from collections.abc import Mapping

from app.i18n.catalog_en import CATALOG_EN
from app.i18n.catalog_ru import CATALOG_RU
from app.i18n.locales import SupportedLocale


class Translator:
    def __init__(
        self,
        locale: SupportedLocale | str | None = None,
        *,
        catalogs: Mapping[SupportedLocale, Mapping[str, str]] | None = None,
        default_locale: SupportedLocale = SupportedLocale.RU,
        fallback_locale: SupportedLocale = SupportedLocale.EN,
    ) -> None:
        self._catalogs: dict[SupportedLocale, dict[str, str]] = {
            SupportedLocale.RU: dict(CATALOG_RU),
            SupportedLocale.EN: dict(CATALOG_EN),
        }
        if catalogs:
            self._catalogs.update({SupportedLocale.coerce(key): dict(value) for key, value in catalogs.items()})
        self._default_locale = SupportedLocale.coerce(default_locale)
        self._fallback_locale = SupportedLocale.coerce(fallback_locale)
        self._locale = SupportedLocale.coerce(locale or self._default_locale)
        self._missing_keys: set[tuple[SupportedLocale, str]] = set()

    @property
    def locale(self) -> SupportedLocale:
        return self._locale

    @property
    def default_locale(self) -> SupportedLocale:
        return self._default_locale

    @property
    def fallback_locale(self) -> SupportedLocale:
        return self._fallback_locale

    @property
    def missing_keys(self) -> frozenset[str]:
        return frozenset(key for _locale, key in self._missing_keys)

    def clear_missing_keys(self) -> None:
        self._missing_keys.clear()

    def available_locales(self) -> tuple[SupportedLocale, ...]:
        return tuple(self._catalogs.keys())

    def set_locale(self, locale: SupportedLocale | str | None) -> SupportedLocale:
        self._locale = SupportedLocale.coerce(locale)
        return self._locale

    def catalog_for(self, locale: SupportedLocale | str | None = None) -> dict[str, str]:
        return self._catalogs[SupportedLocale.coerce(locale or self._locale)]

    def has_key(self, key: str, locale: SupportedLocale | str | None = None) -> bool:
        return key in self.catalog_for(locale)

    def tr(self, key: str, **params: object) -> str:
        value, lookup_locale = self._lookup(key)
        if value is None:
            self._missing_keys.add((self._locale, key))
            return self._missing_marker(key)

        if lookup_locale != self._locale:
            self._missing_keys.add((self._locale, key))
            value = f"{self._missing_marker(key)} {value}"

        if "{" not in value:
            return value

        try:
            return value.format(**params)
        except KeyError as exc:
            missing_param = exc.args[0]
            return f"!!format:{key}:{missing_param}!!"

    def _lookup(self, key: str) -> tuple[str | None, SupportedLocale | None]:
        for locale in self._lookup_chain():
            catalog = self._catalogs.get(locale, {})
            if key in catalog:
                return catalog[key], locale
        return None, None

    def _lookup_chain(self) -> tuple[SupportedLocale, ...]:
        ordered = [self._locale, self._fallback_locale, self._default_locale]
        unique: list[SupportedLocale] = []
        for locale in ordered:
            if locale not in unique:
                unique.append(locale)
        return tuple(unique)

    @staticmethod
    def _missing_marker(key: str) -> str:
        return f"!!missing:{key}!!"
