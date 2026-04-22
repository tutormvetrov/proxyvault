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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from app.db import AuthenticationError, DatabaseManager
from app.models import AppSettings, QROptions
from app.ui.dialogs import PasswordDialog
from app.ui.theme import apply_button_icon, make_form_label, set_widget_status


class SettingsDialog(QDialog):
    def __init__(self, db: DatabaseManager, settings: AppSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.setWindowTitle("ProxyVault Settings")
        self.resize(620, 420)
        self._build_ui()
        self._load_settings()
        self._refresh_password_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        general_group = QFrame()
        general_group.setObjectName("formGroup")
        general_layout = QVBoxLayout(general_group)
        general_layout.setContentsMargins(12, 12, 12, 12)
        general_layout.setSpacing(10)
        general_title = QLabel("General")
        general_title.setProperty("role", "subSectionTitle")
        general_layout.addWidget(general_title)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        output_row = QHBoxLayout()
        self.output_folder_edit = QLineEdit()
        browse_button = QPushButton("Browse")
        browse_button.setProperty("variant", "subtle")
        browse_button.clicked.connect(self.browse_folder)
        apply_button_icon(browse_button, "folder", color="#D8943C")
        output_row.addWidget(self.output_folder_edit, 1)
        output_row.addWidget(browse_button)
        form.addRow(make_form_label("Output folder"), self._wrap(output_row))

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["system", "light", "dark"])
        form.addRow(make_form_label("Theme"), self.theme_combo)

        self.refresh_combo = QComboBox()
        self.refresh_combo.addItems(["never", "daily", "weekly"])
        form.addRow(make_form_label("Auto-refresh", min_width=92), self.refresh_combo)
        self.allow_insecure_http_check = QCheckBox("Allow insecure HTTP subscription URLs")
        self.allow_insecure_http_check.setToolTip(
            "HTTPS is safer. Enable this only when you trust the subscription source."
        )
        form.addRow(make_form_label(""), self.allow_insecure_http_check)

        self.error_combo = QComboBox()
        self.error_combo.addItems(["L", "M", "Q", "H"])
        self.version_spin = QSpinBox()
        self.version_spin.setRange(0, 40)
        self.version_spin.setSpecialValueText("Auto")
        self.box_spin = QSpinBox()
        self.box_spin.setRange(1, 40)
        self.border_spin = QSpinBox()
        self.border_spin.setRange(0, 20)
        self.fg_edit = QLineEdit()
        self.bg_edit = QLineEdit()

        form.addRow(make_form_label("Error level"), self.error_combo)
        form.addRow(make_form_label("QR version"), self.version_spin)
        form.addRow(make_form_label("Box size"), self.box_spin)
        form.addRow(make_form_label("Border"), self.border_spin)
        form.addRow(make_form_label("Foreground"), self.fg_edit)
        form.addRow(make_form_label("Background"), self.bg_edit)
        general_layout.addLayout(form)
        root.addWidget(general_group)

        password_group = QFrame()
        password_group.setObjectName("actionGroup")
        password_box = QVBoxLayout(password_group)
        password_box.setContentsMargins(12, 12, 12, 12)
        password_box.setSpacing(10)
        password_title = QLabel("Master Password")
        password_title.setProperty("role", "subSectionTitle")
        password_box.addWidget(password_title)
        self.password_status = QLabel("")
        self.password_status.setObjectName("statusPill")
        password_box.addWidget(self.password_status)
        button_row = QHBoxLayout()
        set_button = QPushButton("Set")
        set_button.setProperty("variant", "subtle")
        set_button.clicked.connect(self.set_password)
        apply_button_icon(set_button, "lock", color="#D8943C")
        change_button = QPushButton("Change")
        change_button.setProperty("variant", "subtle")
        change_button.clicked.connect(self.change_password)
        apply_button_icon(change_button, "unlock", color="#D8943C")
        remove_button = QPushButton("Remove")
        remove_button.setProperty("variant", "destructive")
        remove_button.clicked.connect(self.remove_password)
        apply_button_icon(remove_button, "delete", color="#C77768")
        button_row.addWidget(set_button)
        button_row.addWidget(change_button)
        button_row.addWidget(remove_button)
        password_box.addLayout(button_row)
        root.addWidget(password_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button:
            save_button.setProperty("variant", "primary")
            apply_button_icon(save_button, "save", color="#3A2B1C")
        if cancel_button:
            cancel_button.setProperty("variant", "subtle")
        root.addWidget(buttons)

    def _wrap(self, layout: QHBoxLayout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _load_settings(self) -> None:
        self.output_folder_edit.setText(self.settings.output_folder)
        self.theme_combo.setCurrentText(self.settings.theme)
        self.refresh_combo.setCurrentText(self.settings.subscription_refresh_interval)
        self.allow_insecure_http_check.setChecked(self.settings.allow_insecure_subscription_http)
        self.error_combo.setCurrentText(self.settings.default_qr.error_correction)
        self.version_spin.setValue(self.settings.default_qr.version)
        self.box_spin.setValue(self.settings.default_qr.box_size)
        self.border_spin.setValue(self.settings.default_qr.border)
        self.fg_edit.setText(self.settings.default_qr.fg_color)
        self.bg_edit.setText(self.settings.default_qr.bg_color)

    def browse_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose Output Folder", self.output_folder_edit.text() or str(Path.home()))
        if selected:
            self.output_folder_edit.setText(selected)

    def _refresh_password_status(self) -> None:
        if self.db.has_master_password():
            status = "Configured"
            tone = "success"
            if self.db.is_locked:
                status += " (locked)"
                tone = "warning"
        else:
            status = "Not set"
            tone = "muted"
        self.password_status.setText(status)
        set_widget_status(self.password_status, "statusTone", tone)

    def set_password(self) -> None:
        dialog = PasswordDialog("Set Master Password", ask_current=False, confirm_new=True, parent=self)
        if dialog.exec():
            try:
                self.db.set_master_password(dialog.password)
                self._refresh_password_status()
                QMessageBox.information(self, "Master Password", "Master password has been enabled.")
            except AuthenticationError as exc:
                QMessageBox.warning(self, "Master Password", str(exc))

    def change_password(self) -> None:
        if not self.db.has_master_password():
            return self.set_password()
        dialog = PasswordDialog("Change Master Password", ask_current=True, confirm_new=True, parent=self)
        if dialog.exec():
            try:
                self.db.change_master_password(dialog.current_password, dialog.password)
                self._refresh_password_status()
                QMessageBox.information(self, "Master Password", "Master password updated.")
            except AuthenticationError as exc:
                QMessageBox.warning(self, "Master Password", str(exc))

    def remove_password(self) -> None:
        if not self.db.has_master_password():
            return
        dialog = PasswordDialog("Remove Master Password", ask_current=True, confirm_new=False, parent=self)
        if dialog.exec():
            try:
                self.db.remove_master_password(dialog.current_password)
                self._refresh_password_status()
                QMessageBox.information(self, "Master Password", "Master password removed. URIs are stored in plaintext again.")
            except AuthenticationError as exc:
                QMessageBox.warning(self, "Master Password", str(exc))

    def accept(self) -> None:
        output_folder = self.output_folder_edit.text().strip()
        if not output_folder:
            QMessageBox.warning(self, "Settings", "Output folder cannot be empty.")
            return
        try:
            Path(output_folder).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Settings",
                f"Could not create the output folder:\n{output_folder}\n\n{exc}\n\n"
                "Check that the path is valid and that ProxyVault has permission to write there.",
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
            theme=self.theme_combo.currentText(),
            subscription_refresh_interval=self.refresh_combo.currentText(),
            allow_insecure_subscription_http=self.allow_insecure_http_check.isChecked(),
            has_seen_welcome=self.settings.has_seen_welcome,
        )
