from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.i18n.catalog_en import CATALOG_EN
from app.i18n.catalog_ru import CATALOG_RU


ROOT = Path(__file__).resolve().parents[1]
README_RU = ROOT / "README.md"
README_EN = ROOT / "README.en.md"
HELP_RU = ROOT / "app" / "help" / "content_ru.md"
HELP_EN = ROOT / "app" / "help" / "content_en.md"
WELCOME_RU = ROOT / "app" / "help" / "welcome_ru.md"
WELCOME_EN = ROOT / "app" / "help" / "welcome_en.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_h2_titles(markdown: str) -> list[str]:
    return re.findall(r"^##\s+(.+)$", markdown, flags=re.MULTILINE)


def extract_numbered_steps(markdown: str) -> list[str]:
    return re.findall(r"^\d+\.\s+(.+)$", markdown, flags=re.MULTILINE)


def normalize(text: str) -> str:
    cleaned = (
        text.lower()
        .replace("ё", "е")
        .replace("`", "")
        .replace("«", "")
        .replace("»", "")
        .replace('"', "")
    )
    return " ".join(cleaned.split())


def assert_step_contains(test_case: unittest.TestCase, step: str, tokens: tuple[str, ...]) -> None:
    normalized = normalize(step)
    test_case.assertTrue(any(token in normalized for token in tokens), step)


class HelpContentTests(unittest.TestCase):
    def test_readme_files_exist_and_cross_link_each_other(self) -> None:
        readme_ru = read_text(README_RU)
        readme_en = read_text(README_EN)

        self.assertIn("[README.en.md](README.en.md)", readme_ru)
        self.assertIn("[README.md](README.md)", readme_en)

    def test_russian_readme_covers_required_release_sections(self) -> None:
        readme = read_text(README_RU)
        headings = extract_h2_titles(readme)

        self.assertEqual(
            headings,
            [
                "Что это",
                "Как запустить",
                "Как добавить подключение",
                "Как подключиться",
                "Как понять, что всё работает",
                "Как отключиться",
                "Если что-то не работает",
                "Какой файл скачать для Mac",
                "Сборка релизов",
                "Что ещё умеет ProxyVault",
                "Важно знать",
            ],
        )

    def test_help_content_exists_in_russian_and_english_with_required_sections(self) -> None:
        expected_ru = [
            "С чего начать",
            "Как работает подключение",
            "Что значит “Сделать основным”",
            "Что показывают статусы",
            "Что такое TCP-проверка",
            "Что делать, если соединение не запускается",
            "Как понять, что у меня Mac на Apple Silicon или Intel",
        ]
        expected_en = [
            "Getting Started",
            "How the Connection Works",
            "What “Make Primary” Means",
            "What the Statuses Mean",
            "What the TCP Check Is",
            "What To Do If the Connection Does Not Start",
            "How To Tell Whether Your Mac Is Apple Silicon or Intel",
        ]

        self.assertEqual(extract_h2_titles(read_text(HELP_RU)), expected_ru)
        self.assertEqual(extract_h2_titles(read_text(HELP_EN)), expected_en)

    def test_quick_start_steps_stay_semantically_aligned_across_help_surfaces(self) -> None:
        ru_token_sets = [
            ("добав",),
            ("выбер", "выбира"),
            ("подключ",),
            ("основн",),
            ("панел", "состояни", "журнал"),
        ]
        en_token_sets = [
            ("add",),
            ("select",),
            ("connect",),
            ("primary",),
            ("right panel", "status", "log"),
        ]

        ru_sources = {
            "README.ru": extract_numbered_steps(read_text(README_RU))[:5],
            "help.ru": extract_numbered_steps(read_text(HELP_RU))[:5],
            "welcome.ru": extract_numbered_steps(read_text(WELCOME_RU))[:5],
        }
        en_sources = {
            "README.en": extract_numbered_steps(read_text(README_EN))[:5],
            "help.en": extract_numbered_steps(read_text(HELP_EN))[:5],
            "welcome.en": extract_numbered_steps(read_text(WELCOME_EN))[:5],
        }

        for label, steps in ru_sources.items():
            self.assertEqual(len(steps), 5, label)
            for step, tokens in zip(steps, ru_token_sets):
                assert_step_contains(self, step, tokens)

        for label, steps in en_sources.items():
            self.assertEqual(len(steps), 5, label)
            for step, tokens in zip(steps, en_token_sets):
                assert_step_contains(self, step, tokens)

    def test_welcome_quick_start_matches_onboarding_catalog_intent(self) -> None:
        ru_token_sets = [
            ("добав",),
            ("выбер",),
            ("подключ",),
            ("основн",),
            ("панел", "состояни"),
        ]
        en_token_sets = [
            ("add",),
            ("select",),
            ("connect",),
            ("primary",),
            ("right panel", "status"),
        ]
        expected_ru = [CATALOG_RU[f"onboarding.quick_start.step_{index}"] for index in range(1, 6)]
        expected_en = [CATALOG_EN[f"onboarding.quick_start.step_{index}"] for index in range(1, 6)]
        welcome_ru_steps = extract_numbered_steps(read_text(WELCOME_RU))[:5]
        welcome_en_steps = extract_numbered_steps(read_text(WELCOME_EN))[:5]

        for welcome_step, catalog_step, tokens in zip(welcome_ru_steps, expected_ru, ru_token_sets):
            assert_step_contains(self, welcome_step, tokens)
            assert_step_contains(self, catalog_step, tokens)

        for welcome_step, catalog_step, tokens in zip(welcome_en_steps, expected_en, en_token_sets):
            assert_step_contains(self, welcome_step, tokens)
            assert_step_contains(self, catalog_step, tokens)

    def test_readme_and_help_cover_wireguard_and_tcp_diagnostics_in_both_languages(self) -> None:
        for path in (README_RU, README_EN, HELP_RU, HELP_EN, WELCOME_RU, WELCOME_EN):
            text = read_text(path)
            self.assertIn("WireGuard", text, str(path))
            self.assertIn("TCP", text, str(path))


if __name__ == "__main__":
    unittest.main()
