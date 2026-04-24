from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.db import AuthenticationError, DatabaseManager
from app.i18n import SUPPORTED_LOCALES, SupportedLocale, format_ui_error, tr
from app.models import AppSettings, QROptions
from app.ui.dialogs import PasswordDialog
from app.ui.i18n_patch import ensure_ui_translations, tooltip_text
from app.ui.theme import apply_button_icon, make_form_label, set_widget_status


class SettingsDialog(QDialog):
    def __init__(self, db: DatabaseManager, settings: AppSettings, parent: QWidget | None = None):
        super().__init__(parent)
        ensure_ui_translations()
        self.db = db
        self.settings = settings
        self.setObjectName("dialogShell")
        self.resize(720, 680)
        self._build_ui()
        self._bind_overview_events()
        self._load_settings()
        self._refresh_password_status()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        self.overview_card = QFrame()
        self.overview_card.setObjectName("dialogHeroCard")
        overview_layout = QVBoxLayout(self.overview_card)
        overview_layout.setContentsMargins(14, 14, 14, 14)
        overview_layout.setSpacing(10)
        self.overview_title = QLabel("")
        self.overview_title.setProperty("role", "windowTitle")
        overview_layout.addWidget(self.overview_title)
        self.overview_summary = QLabel("")
        self.overview_summary.setObjectName("dialogHeroSummary")
        self.overview_summary.setWordWrap(True)
        overview_layout.addWidget(self.overview_summary)
        overview_metrics = QHBoxLayout()
        overview_metrics.setSpacing(10)
        (
            self.client_mode_metric_card,
            self.client_mode_metric_label,
            self.client_mode_metric_value,
        ) = self._make_overview_metric()
        (
            self.language_metric_card,
            self.language_metric_label,
            self.language_metric_value,
        ) = self._make_overview_metric()
        (
            self.theme_metric_card,
            self.theme_metric_label,
            self.theme_metric_value,
        ) = self._make_overview_metric()
        overview_metrics.addWidget(self.client_mode_metric_card, 1)
        overview_metrics.addWidget(self.language_metric_card, 1)
        overview_metrics.addWidget(self.theme_metric_card, 1)
        overview_layout.addLayout(overview_metrics)
        root.addWidget(self.overview_card)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self.scroll, 1)

        self.body = QWidget()
        self.scroll.setWidget(self.body)
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 4, 0)
        body_layout.setSpacing(12)

        self.general_group = QFrame()
        self.general_group.setObjectName("formGroup")
        general_layout = QVBoxLayout(self.general_group)
        general_layout.setContentsMargins(12, 12, 12, 12)
        general_layout.setSpacing(10)
        self.general_title = QLabel("")
        self.general_title.setProperty("role", "subSectionTitle")
        general_layout.addWidget(self.general_title)
        general_form = QFormLayout()
        general_form.setContentsMargins(0, 0, 0, 0)
        general_form.setHorizontalSpacing(12)
        general_form.setVerticalSpacing(10)
        general_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.output_folder_edit = QLineEdit()
        browse_button = QPushButton("")
        browse_button.setProperty("variant", "subtle")
        browse_button.clicked.connect(self.browse_output_folder)
        apply_button_icon(browse_button, "folder", color="#D8943C")
        self.output_browse_button = browse_button
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(browse_button)
        self.output_label = make_form_label("")
        general_form.addRow(self.output_label, self._wrap(output_row))

        self.theme_combo = QComboBox()
        self.theme_label = make_form_label("")
        general_form.addRow(self.theme_label, self.theme_combo)

        self.refresh_combo = QComboBox()
        self.refresh_label = make_form_label("")
        general_form.addRow(self.refresh_label, self.refresh_combo)

        self.allow_insecure_http_check = QCheckBox("")
        self.allow_insecure_label = make_form_label("")
        general_form.addRow(self.allow_insecure_label, self.allow_insecure_http_check)

        self.language_combo = QComboBox()
        self.language_label = make_form_label("")
        general_form.addRow(self.language_label, self.language_combo)

        self.error_combo = QComboBox()
        self.error_combo.addItems(["L", "M", "Q", "H"])
        self.error_label = make_form_label("")
        general_form.addRow(self.error_label, self.error_combo)

        self.version_spin = QSpinBox()
        self.version_spin.setRange(0, 40)
        self.version_label = make_form_label("")
        general_form.addRow(self.version_label, self.version_spin)

        self.box_spin = QSpinBox()
        self.box_spin.setRange(1, 40)
        self.box_label = make_form_label("")
        general_form.addRow(self.box_label, self.box_spin)

        self.border_spin = QSpinBox()
        self.border_spin.setRange(0, 20)
        self.border_label = make_form_label("")
        general_form.addRow(self.border_label, self.border_spin)

        self.fg_edit = QLineEdit()
        self.fg_label = make_form_label("")
        general_form.addRow(self.fg_label, self.fg_edit)

        self.bg_edit = QLineEdit()
        self.bg_label = make_form_label("")
        general_form.addRow(self.bg_label, self.bg_edit)
        general_layout.addLayout(general_form)
        body_layout.addWidget(self.general_group)

        self.runtime_group = QFrame()
        self.runtime_group.setObjectName("formGroup")
        runtime_layout = QVBoxLayout(self.runtime_group)
        runtime_layout.setContentsMargins(12, 12, 12, 12)
        runtime_layout.setSpacing(10)
        self.runtime_title = QLabel("")
        self.runtime_title.setProperty("role", "subSectionTitle")
        runtime_layout.addWidget(self.runtime_title)
        runtime_form = QFormLayout()
        runtime_form.setContentsMargins(0, 0, 0, 0)
        runtime_form.setHorizontalSpacing(12)
        runtime_form.setVerticalSpacing(10)
        runtime_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self.client_mode_check = QCheckBox("")
        self.client_mode_check.setToolTip("")
        self.client_mode_label = make_form_label("")
        runtime_form.addRow(self.client_mode_label, self.client_mode_check)

        self.restore_sessions_check = QCheckBox("")
        self.restore_sessions_check.setToolTip("")
        self.restore_sessions_label = make_form_label("")
        runtime_form.addRow(self.restore_sessions_label, self.restore_sessions_check)

        self.clear_proxy_check = QCheckBox("")
        self.clear_proxy_check.setToolTip("")
        self.clear_proxy_label = make_form_label("")
        runtime_form.addRow(self.clear_proxy_label, self.clear_proxy_check)

        self.minimize_to_tray_check = QCheckBox("")
        self.minimize_to_tray_check.setToolTip("")
        self.minimize_to_tray_label = make_form_label("")
        runtime_form.addRow(self.minimize_to_tray_label, self.minimize_to_tray_check)

        self.auto_reconnect_check = QCheckBox("")
        self.auto_reconnect_check.setToolTip("")
        self.auto_reconnect_label = make_form_label("")
        runtime_form.addRow(self.auto_reconnect_label, self.auto_reconnect_check)

        self.log_retention_spin = QSpinBox()
        self.log_retention_spin.setRange(50, 5000)
        self.log_retention_spin.setSingleStep(50)
        self.log_retention_spin.setToolTip("")
        self.log_retention_label = make_form_label("")
        runtime_form.addRow(self.log_retention_label, self.log_retention_spin)

        self.engine_root_edit = QLineEdit()
        self.engine_root_edit.setToolTip("")
        self.engine_root_browse_button = QPushButton("")
        self.engine_root_browse_button.setProperty("variant", "subtle")
        self.engine_root_browse_button.clicked.connect(self.browse_engine_root)
        apply_button_icon(self.engine_root_browse_button, "folder", color="#D8943C")
        engine_row = QHBoxLayout()
        engine_row.addWidget(self.engine_root_edit, 1)
        engine_row.addWidget(self.engine_root_browse_button)
        self.engine_root_label = make_form_label("")
        runtime_form.addRow(self.engine_root_label, self._wrap(engine_row))
        runtime_layout.addLayout(runtime_form)
        body_layout.addWidget(self.runtime_group)

        self.password_group = QFrame()
        self.password_group.setObjectName("actionGroup")
        password_box = QVBoxLayout(self.password_group)
        password_box.setContentsMargins(12, 12, 12, 12)
        password_box.setSpacing(10)
        self.password_title = QLabel("")
        self.password_title.setProperty("role", "subSectionTitle")
        password_box.addWidget(self.password_title)
        self.password_status = QLabel("")
        self.password_status.setObjectName("statusPill")
        password_box.addWidget(self.password_status)
        button_row = QHBoxLayout()
        self.set_password_button = QPushButton("")
        self.set_password_button.setProperty("variant", "subtle")
        self.set_password_button.clicked.connect(self.set_password)
        apply_button_icon(self.set_password_button, "lock", color="#D8943C")
        self.change_password_button = QPushButton("")
        self.change_password_button.setProperty("variant", "subtle")
        self.change_password_button.clicked.connect(self.change_password)
        apply_button_icon(self.change_password_button, "unlock", color="#D8943C")
        self.remove_password_button = QPushButton("")
        self.remove_password_button.setProperty("variant", "destructive")
        self.remove_password_button.clicked.connect(self.remove_password)
        apply_button_icon(self.remove_password_button, "delete", color="#C77768")
        button_row.addWidget(self.set_password_button)
        button_row.addWidget(self.change_password_button)
        button_row.addWidget(self.remove_password_button)
        password_box.addLayout(button_row)
        body_layout.addWidget(self.password_group)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button:
            save_button.setProperty("variant", "primary")
            apply_button_icon(save_button, "save", color="#3A2B1C")
        if cancel_button:
            cancel_button.setProperty("variant", "subtle")
        root.addWidget(self.buttons)

    def _wrap(self, layout: QHBoxLayout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _make_overview_metric(self) -> tuple[QFrame, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("runtimeMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        label = QLabel("")
        label.setObjectName("runtimeMetricLabel")
        value = QLabel("")
        value.setObjectName("runtimeMetricValue")
        value.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(value)
        return card, label, value

    def _bind_overview_events(self) -> None:
        self.client_mode_check.toggled.connect(self._update_overview_card)
        self.language_combo.currentIndexChanged.connect(self._update_overview_card)
        self.theme_combo.currentIndexChanged.connect(self._update_overview_card)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("settings.title"))
        self.overview_title.setText(tr("settings.title"))
        self.overview_summary.setText(tr("settings.hero.subtitle"))
        self.client_mode_metric_label.setText(tr("settings.client_mode.label"))
        self.language_metric_label.setText(tr("settings.language.label"))
        self.theme_metric_label.setText(tr("common.field.theme"))
        self.general_title.setText(tr("section.general"))
        self.output_label.setText(tr("common.field.output_folder"))
        self.output_browse_button.setText(tr("action.browse"))
        self.theme_label.setText(tr("common.field.theme"))
        self.refresh_label.setText(tr("common.field.auto_refresh"))
        self.allow_insecure_label.setText(tr("common.empty"))
        self.allow_insecure_http_check.setText(tr("settings.security.allow_insecure_http"))
        self.allow_insecure_http_check.setToolTip(tr("settings.security.allow_insecure_http.tooltip"))
        self.language_label.setText(tr("settings.language.label"))
        self.language_combo.setToolTip(tooltip_text("settings.language.tooltip"))
        self.error_label.setText(tr("common.field.error_level"))
        self.version_label.setText(tr("common.field.qr_version"))
        self.version_spin.setSpecialValueText(tr("common.auto"))
        self.box_label.setText(tr("common.field.box_size"))
        self.border_label.setText(tr("common.field.border"))
        self.fg_label.setText(tr("common.field.foreground"))
        self.bg_label.setText(tr("common.field.background"))

        self.runtime_title.setText(tr("settings.section.runtime"))
        self.client_mode_label.setText(tr("settings.client_mode.label"))
        self.client_mode_check.setText(tr("common.empty"))
        self.client_mode_check.setToolTip(tr("settings.client_mode.tooltip"))
        self.restore_sessions_label.setText(tr("settings.restore_sessions_on_launch.label"))
        self.restore_sessions_check.setText(tr("common.empty"))
        self.restore_sessions_check.setToolTip(tr("settings.restore_sessions_on_launch.tooltip"))
        self.clear_proxy_label.setText(tr("settings.clear_system_proxy_on_exit.label"))
        self.clear_proxy_check.setText(tr("common.empty"))
        self.clear_proxy_check.setToolTip(tr("settings.clear_system_proxy_on_exit.tooltip"))
        self.minimize_to_tray_label.setText(tr("settings.minimize_to_tray.label"))
        self.minimize_to_tray_check.setText(tr("common.empty"))
        self.minimize_to_tray_check.setToolTip(tr("settings.minimize_to_tray.tooltip"))
        self.auto_reconnect_label.setText(tr("settings.auto_reconnect_enabled.label"))
        self.auto_reconnect_check.setText(tr("common.empty"))
        self.auto_reconnect_check.setToolTip(tr("settings.auto_reconnect_enabled.tooltip"))
        self.log_retention_label.setText(tr("settings.log_retention_lines.label"))
        self.log_retention_spin.setToolTip(tr("settings.log_retention_lines.tooltip"))
        self.engine_root_label.setText(tr("settings.engine_root_dir.label"))
        self.engine_root_edit.setToolTip(tr("settings.engine_root_dir.tooltip"))
        self.engine_root_browse_button.setText(tr("action.browse"))

        self.password_title.setText(tr("section.master_password"))
        self.set_password_button.setText(tr("action.set"))
        self.change_password_button.setText(tr("action.change"))
        self.remove_password_button.setText(tr("action.remove"))
        self._populate_theme_combo(self.theme_combo.currentData() or self.settings.theme)
        self._populate_refresh_combo(self.refresh_combo.currentData() or self.settings.subscription_refresh_interval)
        self._populate_language_combo(self.language_combo.currentData() or self.settings.ui_language)
        self._update_overview_card()

    def _populate_theme_combo(self, selected: str) -> None:
        options = [
            ("system", tr("settings.theme.system")),
            ("light", tr("settings.theme.light")),
            ("dark", tr("settings.theme.dark")),
        ]
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        for value, label in options:
            self.theme_combo.addItem(label, value)
        index = max(self.theme_combo.findData(selected), 0)
        self.theme_combo.setCurrentIndex(index)
        self.theme_combo.blockSignals(False)

    def _populate_refresh_combo(self, selected: str) -> None:
        options = [
            ("never", tr("settings.refresh.never")),
            ("daily", tr("settings.refresh.daily")),
            ("weekly", tr("settings.refresh.weekly")),
        ]
        self.refresh_combo.blockSignals(True)
        self.refresh_combo.clear()
        for value, label in options:
            self.refresh_combo.addItem(label, value)
        index = max(self.refresh_combo.findData(selected), 0)
        self.refresh_combo.setCurrentIndex(index)
        self.refresh_combo.blockSignals(False)

    def _populate_language_combo(self, selected: str) -> None:
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        for locale in SUPPORTED_LOCALES:
            self.language_combo.addItem(tr(locale.label_key), locale.value)
        index = max(self.language_combo.findData(SupportedLocale.coerce(selected).value), 0)
        self.language_combo.setCurrentIndex(index)
        self.language_combo.blockSignals(False)

    def _load_settings(self) -> None:
        self.output_folder_edit.setText(self.settings.output_folder)
        self._populate_theme_combo(self.settings.theme)
        self._populate_refresh_combo(self.settings.subscription_refresh_interval)
        self.allow_insecure_http_check.setChecked(self.settings.allow_insecure_subscription_http)
        self._populate_language_combo(self.settings.ui_language)
        self.error_combo.setCurrentText(self.settings.default_qr.error_correction)
        self.version_spin.setValue(self.settings.default_qr.version)
        self.box_spin.setValue(self.settings.default_qr.box_size)
        self.border_spin.setValue(self.settings.default_qr.border)
        self.fg_edit.setText(self.settings.default_qr.fg_color)
        self.bg_edit.setText(self.settings.default_qr.bg_color)
        self.client_mode_check.setChecked(self.settings.client_mode_enabled)
        self.restore_sessions_check.setChecked(self.settings.restore_sessions_on_launch)
        self.clear_proxy_check.setChecked(self.settings.clear_system_proxy_on_exit)
        self.minimize_to_tray_check.setChecked(self.settings.minimize_to_tray)
        self.auto_reconnect_check.setChecked(self.settings.auto_reconnect_enabled)
        self.log_retention_spin.setValue(self.settings.log_retention_lines)
        self.engine_root_edit.setText(self.settings.engine_root_dir)

    def browse_output_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            tr("common.field.output_folder"),
            self.output_folder_edit.text() or str(Path.home()),
        )
        if selected:
            self.output_folder_edit.setText(selected)

    def browse_engine_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            tr("settings.engine_root_dir.label"),
            self.engine_root_edit.text() or str(Path.home()),
        )
        if selected:
            self.engine_root_edit.setText(selected)

    def _refresh_password_status(self) -> None:
        if self.db.has_master_password():
            status = tr("settings.password.configured")
            tone = "success"
            if self.db.is_locked:
                status = tr("settings.password.configured_locked")
                tone = "warning"
        else:
            status = tr("settings.password.not_set")
            tone = "muted"
        self.password_status.setText(status)
        set_widget_status(self.password_status, "statusTone", tone)

    def _update_overview_card(self) -> None:
        client_enabled = self.client_mode_check.isChecked()
        self.client_mode_metric_value.setText(
            tr("settings.hero.client_mode.on") if client_enabled else tr("settings.hero.client_mode.off")
        )
        set_widget_status(
            self.client_mode_metric_value,
            "statusTone",
            "success" if client_enabled else "warning",
        )
        self.language_metric_value.setText(
            self.language_combo.currentText().strip()
            or tr(SupportedLocale.coerce(self.settings.ui_language).label_key)
        )
        set_widget_status(self.language_metric_value, "statusTone", "muted")
        self.theme_metric_value.setText(
            self.theme_combo.currentText().strip() or tr("settings.theme.system")
        )
        set_widget_status(self.theme_metric_value, "statusTone", "muted")

    def set_password(self) -> None:
        dialog = PasswordDialog(tr("dialog.password.title.set"), ask_current=False, confirm_new=True, parent=self)
        if dialog.exec():
            try:
                self.db.set_master_password(dialog.password)
                self._refresh_password_status()
                QMessageBox.information(self, tr("section.master_password"), tr("settings.password.enabled"))
            except AuthenticationError as exc:
                QMessageBox.warning(
                    self,
                    tr("section.master_password"),
                    format_ui_error("ui.error.auth_failed", detail=exc),
                )

    def change_password(self) -> None:
        if not self.db.has_master_password():
            self.set_password()
            return
        dialog = PasswordDialog(
            tr("dialog.password.title.change"),
            ask_current=self.db.is_locked,
            confirm_new=True,
            parent=self,
        )
        if dialog.exec():
            try:
                self.db.change_master_password(dialog.current_password, dialog.password)
                self._refresh_password_status()
                QMessageBox.information(self, tr("section.master_password"), tr("settings.password.updated"))
            except AuthenticationError as exc:
                QMessageBox.warning(
                    self,
                    tr("section.master_password"),
                    format_ui_error("ui.error.auth_failed", detail=exc),
                )

    def remove_password(self) -> None:
        if not self.db.has_master_password():
            return
        current_password = ""
        if self.db.is_locked:
            dialog = PasswordDialog(
                tr("dialog.password.title.remove"),
                ask_current=False,
                confirm_new=False,
                parent=self,
            )
            if not dialog.exec():
                return
            current_password = dialog.password
        try:
            self.db.remove_master_password(current_password)
            self._refresh_password_status()
            QMessageBox.information(self, tr("section.master_password"), tr("settings.password.removed_plaintext"))
        except AuthenticationError as exc:
            QMessageBox.warning(
                self,
                tr("section.master_password"),
                format_ui_error("ui.error.auth_failed", detail=exc),
            )

    def accept(self) -> None:
        output_folder = self.output_folder_edit.text().strip()
        if not output_folder:
            QMessageBox.warning(self, tr("settings.title"), tr("settings.validation.output_folder_empty"))
            return
        try:
            Path(output_folder).mkdir(parents=True, exist_ok=True)
            engine_folder = self.engine_root_edit.text().strip()
            if engine_folder:
                Path(engine_folder).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self,
                tr("settings.title"),
                tr("settings.validation.output_folder_create_failed", path=output_folder, error=exc),
            )
            return
        super().accept()

    def values(self) -> AppSettings:
        return AppSettings(
            output_folder=self.output_folder_edit.text().strip(),
            default_qr=QROptions(
                error_correction=self.error_combo.currentText(),
                version=self.version_spin.value(),
                box_size=self.box_spin.value(),
                border=self.border_spin.value(),
                fg_color=self.fg_edit.text().strip() or "#111111",
                bg_color=self.bg_edit.text().strip() or "#FFFFFF",
            ),
            theme=str(self.theme_combo.currentData() or self.settings.theme),
            subscription_refresh_interval=str(self.refresh_combo.currentData() or self.settings.subscription_refresh_interval),
            allow_insecure_subscription_http=self.allow_insecure_http_check.isChecked(),
            has_seen_welcome=self.settings.has_seen_welcome,
            client_mode_enabled=self.client_mode_check.isChecked(),
            restore_sessions_on_launch=self.restore_sessions_check.isChecked(),
            clear_system_proxy_on_exit=self.clear_proxy_check.isChecked(),
            minimize_to_tray=self.minimize_to_tray_check.isChecked(),
            auto_reconnect_enabled=self.auto_reconnect_check.isChecked(),
            log_retention_lines=self.log_retention_spin.value(),
            engine_root_dir=self.engine_root_edit.text().strip() or self.settings.engine_root_dir,
            ui_language=str(self.language_combo.currentData() or self.settings.ui_language),
        )
