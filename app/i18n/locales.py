from __future__ import annotations

from enum import Enum


class SupportedLocale(str, Enum):
    RU = "ru"
    EN = "en"

    @classmethod
    def default(cls) -> "SupportedLocale":
        return cls.RU

    @classmethod
    def coerce(cls, value: "SupportedLocale | str | None") -> "SupportedLocale":
        if isinstance(value, cls):
            return value
        normalized = str(value or cls.default().value).strip().lower()
        normalized = normalized.split("-", maxsplit=1)[0]
        for locale in cls:
            if locale.value == normalized:
                return locale
        return cls.default()

    @property
    def label_key(self) -> str:
        return f"common.locale.{self.value}"


SUPPORTED_LOCALES = tuple(SupportedLocale)
