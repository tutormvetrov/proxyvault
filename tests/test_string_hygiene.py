from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.i18n.catalog_en import CATALOG_EN
from app.i18n.catalog_ru import CATALOG_RU


ROOT = Path(__file__).resolve().parents[1]
UI_FILES = [
    ROOT / "app" / "ui" / "main_window.py",
    ROOT / "app" / "ui" / "detail_panel.py",
    ROOT / "app" / "ui" / "settings.py",
    ROOT / "app" / "ui" / "dialogs.py",
    ROOT / "app" / "ui" / "card_view.py",
    ROOT / "app" / "ui" / "sidebar.py",
]

ROLLOUT_CLIENT_MODE_KEYS = (
    "action.connect",
    "action.disconnect",
    "action.make_primary",
    "action.stop_all_connections",
    "action.logs",
    "action.sessions",
    "action.open_full_log",
    "action.copy_local_address",
    "section.connection",
    "section.technical_log",
    "runtime.state.primary",
    "runtime.state.wireguard_active",
)


def iter_string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.strip()
            if text:
                values.append(text)
    return values


class StringHygieneTests(unittest.TestCase):
    def test_client_mode_labels_exist_in_both_catalogs(self) -> None:
        for key in ROLLOUT_CLIENT_MODE_KEYS:
            self.assertIn(key, CATALOG_RU, key)
            self.assertIn(key, CATALOG_EN, key)
            self.assertTrue(CATALOG_RU[key].strip(), key)
            self.assertTrue(CATALOG_EN[key].strip(), key)

    def test_ui_files_do_not_hardcode_client_mode_english_labels(self) -> None:
        blocked_phrases = {CATALOG_EN[key] for key in ROLLOUT_CLIENT_MODE_KEYS}
        blocked_hits: dict[str, list[str]] = {}

        for path in UI_FILES:
            literals = iter_string_literals(path)
            hits = sorted(phrase for phrase in blocked_phrases if any(phrase == literal for literal in literals))
            if hits:
                blocked_hits[str(path.relative_to(ROOT))] = hits

        self.assertEqual(blocked_hits, {})

    def test_ui_files_do_not_embed_client_mode_russian_copy_directly(self) -> None:
        blocked_phrases = {
            CATALOG_RU["action.connect"],
            CATALOG_RU["action.disconnect"],
            CATALOG_RU["action.make_primary"],
            CATALOG_RU["action.open_full_log"],
            CATALOG_RU["action.copy_local_address"],
            CATALOG_RU["section.connection"],
            CATALOG_RU["section.technical_log"],
        }
        blocked_hits: dict[str, list[str]] = {}

        for path in UI_FILES:
            literals = iter_string_literals(path)
            hits = sorted(phrase for phrase in blocked_phrases if any(phrase == literal for literal in literals))
            if hits:
                blocked_hits[str(path.relative_to(ROOT))] = hits

        self.assertEqual(blocked_hits, {})


if __name__ == "__main__":
    unittest.main()
