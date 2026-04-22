from __future__ import annotations

import os
import tempfile
import unittest
import gc
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from app.db import DatabaseManager
from app.i18n import SupportedLocale, set_locale, tr
from app.models import ProxyType
from app.ui.card_view import CardView, EntryCardWidget
from app.ui.detail_panel import DetailPanel
from app.ui.dialogs import HelpDialog, WelcomeDialog
from app.ui.main_window import MainWindow
from app.ui.settings import SettingsDialog
from tests.runtime.fakes import make_entry


def collect_visible_texts(widget) -> list[str]:
    texts: list[str] = []
    for child in widget.findChildren((QLabel, QPushButton)):
        text = child.text().strip()
        if text:
            texts.append(text)
    return texts


def collect_action_texts(widget) -> list[str]:
    texts: list[str] = []
    for action in widget.findChildren(QAction):
        text = action.text().strip()
        if text:
            texts.append(text)
    return texts


def assert_no_missing_markers(test_case: unittest.TestCase, texts: list[str]) -> None:
    markers = [text for text in texts if "!!missing:" in text or "!!format:" in text]
    test_case.assertEqual(markers, [], markers)


class UiSmokeSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        app = getattr(cls, "app", None)
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            widget.close()
        app.processEvents()
        app.quit()
        cls.app = None
        gc.collect()

    def setUp(self) -> None:
        set_locale(SupportedLocale.default())
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "proxyvault.db"
        self.db = DatabaseManager(self.db_path)
        settings = self.db.load_settings()
        settings.output_folder = self.temp_dir.name
        settings.has_seen_welcome = True
        self.db.save_settings(settings)
        self.settings = settings

    def tearDown(self) -> None:
        for widget in self.app.topLevelWidgets():
            widget.close()
        self.db.close()
        self.temp_dir.cleanup()

    def test_main_window_builds_shell_without_showing_welcome_dialog(self) -> None:
        window = MainWindow(self.db)

        self.assertEqual(window.windowTitle(), "ProxyVault")
        self.assertIsNotNone(window.sidebar)
        self.assertIsNotNone(window.card_view)
        self.assertIsNotNone(window.detail_panel)
        self.assertEqual(len(window.menuBar().actions()), 6)
        self.assertTrue(window.search_edit.placeholderText())
        self.assertTrue(window.workspace_title_label.text())
        self.assertTrue(window.workspace_scope_pill.text())
        self.assertTrue(window.workspace_mode_pill.text())
        self.assertEqual(window.card_view.list_widget.count(), 0)
        self.assertIn(window.stop_all_action, window.toolbar.actions())

    def test_detail_panel_clear_state_is_disabled_and_safe(self) -> None:
        panel = DetailPanel()

        self.assertIsNone(panel.current_entry)
        self.assertEqual(panel.title_label.text(), tr("detail.clear.title"))
        self.assertFalse(panel.entry_type_pill.isVisible())
        self.assertFalse(panel.save_button.isEnabled())
        self.assertFalse(panel.delete_button.isEnabled())
        self.assertFalse(panel.check_now_button.isEnabled())
        self.assertFalse(panel.reachability_toggle_button.isEnabled())
        self.assertFalse(panel.reachability_details_frame.isVisible())
        self.assertEqual(panel.params_table.rowCount(), 0)

    def test_settings_dialog_loads_current_settings_into_controls(self) -> None:
        dialog = SettingsDialog(self.db, self.settings)

        self.assertEqual(dialog.windowTitle(), tr("settings.title"))
        self.assertEqual(dialog.overview_title.text(), tr("settings.title"))
        self.assertTrue(dialog.client_mode_metric_value.text())
        self.assertEqual(dialog.output_folder_edit.text(), self.temp_dir.name)
        self.assertEqual(dialog.theme_combo.currentData(), self.settings.theme)
        self.assertEqual(dialog.refresh_combo.currentData(), self.settings.subscription_refresh_interval)
        self.assertEqual(dialog.language_combo.currentData(), self.settings.ui_language)
        self.assertEqual(dialog.client_mode_check.isChecked(), self.settings.client_mode_enabled)
        self.assertEqual(dialog.values().output_folder, self.temp_dir.name)

    def test_welcome_dialog_builds_quick_start_shell(self) -> None:
        dialog = WelcomeDialog()

        self.assertIn("ProxyVault", dialog.windowTitle())
        self.assertTrue(dialog.summary_label.text())
        self.assertTrue(dialog.quick_start_pill.text())
        assert_no_missing_markers(self, collect_visible_texts(dialog))

    def test_help_dialog_builds_navigation_and_content_shell(self) -> None:
        dialog = HelpDialog()

        self.assertIn("ProxyVault", dialog.windowTitle())
        self.assertGreater(dialog.section_list.count(), 0)
        self.assertTrue(dialog.navigation_title.text())
        self.assertTrue(dialog.current_section_hint.text())
        self.assertTrue(dialog.current_section_label.text())
        assert_no_missing_markers(self, collect_visible_texts(dialog))

    def test_other_entry_card_does_not_suggest_fake_runtime_actions(self) -> None:
        card_view = CardView()
        other_entry = make_entry("other-entry", ProxyType.OTHER, name="Legacy Config")

        card_view.set_entries([other_entry])
        item = card_view.list_widget.item(0)
        widget = card_view.list_widget.itemWidget(item)

        self.assertIsInstance(widget, EntryCardWidget)
        texts = collect_visible_texts(widget)
        self.assertFalse(any(text in {"Connect", "Disconnect", "Make Primary"} for text in texts), texts)

    def test_main_window_switches_locale_without_missing_key_markers(self) -> None:
        window = MainWindow(self.db)

        self.assertEqual(window.file_menu.title(), "Файл")
        self.assertEqual(window.connect_action.text(), "Подключить выбранный")
        assert_no_missing_markers(self, collect_visible_texts(window) + collect_action_texts(window))

        window.apply_ui_language("en")

        self.assertEqual(window.file_menu.title(), "File")
        self.assertEqual(window.connect_action.text(), "Connect Selected")
        self.assertIn("Search", window.search_edit.placeholderText())
        assert_no_missing_markers(self, collect_visible_texts(window) + collect_action_texts(window))

    def test_entry_card_localizes_support_labels_in_both_locales(self) -> None:
        entry = make_entry("mirror", ProxyType.VLESS_WS, name="mirror.example.com")
        card_view = CardView()

        card_view.set_entries([entry])
        widget = card_view.list_widget.itemWidget(card_view.list_widget.item(0))
        self.assertIsInstance(widget, EntryCardWidget)
        self.assertIn("Порт 443", collect_visible_texts(widget))
        self.assertNotIn("Port 443", collect_visible_texts(widget))

        set_locale(SupportedLocale.EN)
        card_view.retranslate_ui()
        widget = card_view.list_widget.itemWidget(card_view.list_widget.item(0))
        self.assertIsInstance(widget, EntryCardWidget)
        self.assertIn("Port 443", collect_visible_texts(widget))
        self.assertNotIn("Порт 443", collect_visible_texts(widget))

    def test_runtime_settings_copy_stays_neutral_about_saved_preferences(self) -> None:
        dialog = SettingsDialog(self.db, self.settings)

        self.assertNotIn("будущ", dialog.minimize_to_tray_check.toolTip().lower())
        self.assertNotIn("будущ", dialog.auto_reconnect_check.toolTip().lower())
        self.assertNotIn("future", dialog.minimize_to_tray_check.toolTip().lower())
        self.assertNotIn("future", dialog.auto_reconnect_check.toolTip().lower())


if __name__ == "__main__":
    unittest.main()
