from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.i18n import format_proxy_type, format_route_owner, format_runtime_state, format_ui_error, tr
from app.models import QROptions, SubscriptionImportItem
from app.parser import ParseError, is_wireguard_block, parse_proxy_text, parse_subscription_payload
from app.qr_gen import copy_pixmap_to_clipboard, qr_pixmap
from app.runtime.models import SessionHistoryRecord
from app.subscriptions import (
    SubscriptionSecurityError,
    fetch_subscription_url_payload,
    looks_like_subscription_url_candidate,
    validate_subscription_url,
)
from app.ui.i18n_patch import (
    ensure_ui_translations,
    load_help_markdown,
    runtime_engine_label,
    runtime_error_display,
    ui_error_message,
)
from app.ui.theme import apply_button_icon, make_form_label, refresh_widget_style
from app.ui.workers import FunctionWorker


def populate_params_table(table: QTableWidget, rows: list[tuple[str, str]]) -> None:
    table.setRowCount(len(rows))
    for row_index, (key, value) in enumerate(rows):
        table.setItem(row_index, 0, QTableWidgetItem(key))
        table.setItem(row_index, 1, QTableWidgetItem(value))


def clipboard_text() -> str:
    clipboard = QApplication.clipboard()
    if not clipboard:
        return ""
    return clipboard.text().strip()


def extract_proxy_config_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    if is_wireguard_block(stripped):
        return stripped
    try:
        parse_proxy_text(stripped)
    except ParseError:
        return ""
    return stripped


def _localized_buttons(button_box: QDialogButtonBox, *, accept_text: str, cancel_text: str) -> None:
    ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
    save_button = button_box.button(QDialogButtonBox.StandardButton.Save)
    cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
    if ok_button:
        ok_button.setText(accept_text)
        ok_button.setProperty("variant", "primary")
    if save_button:
        save_button.setText(accept_text)
        save_button.setProperty("variant", "primary")
    if cancel_button:
        cancel_button.setText(cancel_text)
        cancel_button.setProperty("variant", "subtle")


def _split_markdown_sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    lines = markdown.splitlines()
    title = ""
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            if current_title:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = line[3:].strip()
            current_lines = [line]
            continue
        if current_title:
            current_lines.append(line)
    if current_title:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return title, sections


def _strip_markdown_title(markdown: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    return "\n".join(lines).strip()


def _strip_leading_section_heading(markdown: str) -> str:
    lines = markdown.splitlines()
    while lines and not lines[0].strip():
        lines = lines[1:]
    if lines and lines[0].lstrip().startswith("## "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    return "\n".join(lines).strip()


def _count_markdown_numbered_steps(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if re.match(r"^\s*\d+\.\s", line))


class AddEntryDialog(QDialog):
    def __init__(
        self,
        default_options: QROptions,
        prefill_text: str = "",
        prefill_name: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        ensure_ui_translations()
        self.default_options = default_options
        self._result_payload: dict[str, Any] = {}
        self._build_ui()
        self._load_default_options()
        safe_prefill_text = prefill_text if isinstance(prefill_text, str) else ""
        safe_prefill_name = prefill_name if isinstance(prefill_name, str) else ""
        auto_prefill = safe_prefill_text.strip() or extract_proxy_config_text(clipboard_text())
        self.name_edit.setText(safe_prefill_name)
        self.uri_edit.setPlainText(auto_prefill)
        if auto_prefill and not safe_prefill_text.strip():
            self.source_label.setText(tr("dialog.add_entry.source.clipboard_config"))
        self.retranslate_ui()
        self.update_preview()

    def _build_ui(self) -> None:
        self.resize(900, 720)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        form_group = QFrame()
        form_group.setObjectName("formGroup")
        form_group_layout = QVBoxLayout(form_group)
        form_group_layout.setContentsMargins(12, 12, 12, 12)
        form_group_layout.setSpacing(10)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.name_edit = QLineEdit()
        self.tags_edit = QLineEdit()
        self.expiry_edit = QLineEdit()
        self.expiry_edit.setObjectName("expiryField")
        self.favorite_check = QCheckBox("")
        self.uri_edit = QPlainTextEdit()
        self.uri_edit.setMinimumHeight(160)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setObjectName("notesEdit")
        self.notes_edit.setMinimumHeight(90)

        self.name_label = make_form_label("")
        self.tags_label = make_form_label("")
        self.expiry_label = make_form_label("")
        self.uri_label = make_form_label("", min_width=92)
        self.notes_label = make_form_label("")
        form.addRow(self.name_label, self.name_edit)
        form.addRow(self.tags_label, self.tags_edit)
        form.addRow(self.expiry_label, self.expiry_edit)
        form.addRow(make_form_label(""), self.favorite_check)
        form.addRow(self.uri_label, self.uri_edit)
        form.addRow(self.notes_label, self.notes_edit)
        form_group_layout.addLayout(form)
        root.addWidget(form_group)

        self.validation_label = QLabel("")
        self.validation_label.setObjectName("inlineValidation")
        self.validation_label.setVisible(False)
        root.addWidget(self.validation_label)
        self.source_label = QLabel("")
        self.source_label.setObjectName("dialogSourceLabel")
        root.addWidget(self.source_label)

        preview_group = QFrame()
        preview_group.setObjectName("previewGroup")
        preview_group_layout = QVBoxLayout(preview_group)
        preview_group_layout.setContentsMargins(12, 12, 12, 12)
        preview_group_layout.setSpacing(10)
        preview_layout = QGridLayout()
        preview_layout.setHorizontalSpacing(12)
        preview_layout.setVerticalSpacing(8)
        self.parsed_title = QLabel("")
        self.parsed_title.setProperty("role", "subSectionTitle")
        preview_layout.addWidget(self.parsed_title, 0, 0)
        self.qr_title = QLabel("")
        self.qr_title.setProperty("role", "subSectionTitle")
        preview_layout.addWidget(self.qr_title, 0, 1)

        self.params_table = QTableWidget(0, 2)
        self.params_table.setObjectName("parsedTable")
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.horizontalHeader().setStretchLastSection(True)
        self.params_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.params_table.setShowGrid(False)
        preview_layout.addWidget(self.params_table, 1, 0)

        right_column = QVBoxLayout()
        self.qr_label = QLabel()
        self.qr_label.setObjectName("qrCanvas")
        self.qr_label.setMinimumSize(260, 260)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_column.addWidget(self.qr_label)

        self.copy_qr_button = QPushButton("")
        self.copy_qr_button.setProperty("variant", "subtle")
        self.copy_qr_button.clicked.connect(self.copy_qr)
        apply_button_icon(self.copy_qr_button, "qr", color="#D8943C")
        right_column.addWidget(self.copy_qr_button)

        options_form = QFormLayout()
        options_form.setContentsMargins(0, 4, 0, 0)
        options_form.setHorizontalSpacing(12)
        options_form.setVerticalSpacing(8)
        options_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.error_combo = QComboBox()
        self.error_combo.addItems(["L", "M", "Q", "H"])
        self.version_spin = QSpinBox()
        self.version_spin.setRange(0, 40)
        self.box_spin = QSpinBox()
        self.box_spin.setRange(1, 40)
        self.border_spin = QSpinBox()
        self.border_spin.setRange(0, 20)
        self.fg_edit = QLineEdit()
        self.bg_edit = QLineEdit()
        self.fg_button = QPushButton("")
        self.fg_button.clicked.connect(lambda: self.pick_color(self.fg_edit))
        self.bg_button = QPushButton("")
        self.bg_button.clicked.connect(lambda: self.pick_color(self.bg_edit))
        fg_row = QHBoxLayout()
        fg_row.addWidget(self.fg_edit)
        fg_row.addWidget(self.fg_button)
        bg_row = QHBoxLayout()
        bg_row.addWidget(self.bg_edit)
        bg_row.addWidget(self.bg_button)
        self.error_field_label = make_form_label("")
        self.version_field_label = make_form_label("")
        self.box_field_label = make_form_label("")
        self.border_field_label = make_form_label("")
        self.fg_field_label = make_form_label("")
        self.bg_field_label = make_form_label("")
        options_form.addRow(self.error_field_label, self.error_combo)
        options_form.addRow(self.version_field_label, self.version_spin)
        options_form.addRow(self.box_field_label, self.box_spin)
        options_form.addRow(self.border_field_label, self.border_spin)
        options_form.addRow(self.fg_field_label, self._wrap_layout(fg_row))
        options_form.addRow(self.bg_field_label, self._wrap_layout(bg_row))
        right_column.addLayout(options_form)

        preview_layout.addLayout(right_column, 1, 1)
        preview_group_layout.addLayout(preview_layout)
        root.addWidget(preview_group)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.uri_edit.textChanged.connect(self.update_preview)
        self.name_edit.textChanged.connect(self.update_preview)
        for widget in [
            self.error_combo,
            self.version_spin,
            self.box_spin,
            self.border_spin,
            self.fg_edit,
            self.bg_edit,
        ]:
            if hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self.update_preview)
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self.update_preview)
            if hasattr(widget, "textChanged"):
                widget.textChanged.connect(self.update_preview)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("dialog.add_entry.title"))
        self.name_label.setText(tr("common.field.name"))
        self.tags_label.setText(tr("common.field.tags"))
        self.expiry_label.setText(tr("common.field.expiry"))
        self.uri_label.setText(tr("common.field.result"))
        self.notes_label.setText(tr("common.field.notes"))
        self.expiry_edit.setPlaceholderText(tr("dialog.add_entry.placeholder.expiry"))
        self.favorite_check.setText(tr("sidebar.filters.favorites_only"))
        self.uri_edit.setPlaceholderText(tr("dialog.add_entry.placeholder.uri_or_config"))
        self.notes_edit.setPlaceholderText(tr("dialog.add_entry.placeholder.notes"))
        self.parsed_title.setText(tr("section.parsed_parameters"))
        self.qr_title.setText(tr("section.qr_preview"))
        self.params_table.setHorizontalHeaderLabels([tr("common.field.name"), tr("common.field.result")])
        self.copy_qr_button.setText(tr("action.copy_qr"))
        self.error_field_label.setText(tr("common.field.error_level"))
        self.version_field_label.setText(tr("common.field.qr_version"))
        self.version_spin.setSpecialValueText(tr("common.auto"))
        self.box_field_label.setText(tr("common.field.box_size"))
        self.border_field_label.setText(tr("common.field.border"))
        self.fg_field_label.setText(tr("common.field.foreground"))
        self.bg_field_label.setText(tr("common.field.background"))
        self.fg_button.setText(tr("action.browse"))
        self.bg_button.setText(tr("action.browse"))
        _localized_buttons(self.buttons, accept_text=tr("common.ok"), cancel_text=tr("common.cancel"))
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            apply_button_icon(ok_button, "add", color="#3A2B1C")
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setProperty("variant", "subtle")

    def _wrap_layout(self, layout: QHBoxLayout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _load_default_options(self) -> None:
        self.error_combo.setCurrentText(self.default_options.error_correction)
        self.version_spin.setValue(self.default_options.version)
        self.box_spin.setValue(self.default_options.box_size)
        self.border_spin.setValue(self.default_options.border)
        self.fg_edit.setText(self.default_options.fg_color)
        self.bg_edit.setText(self.default_options.bg_color)

    def current_qr_options(self) -> QROptions:
        return QROptions(
            error_correction=self.error_combo.currentText(),
            version=self.version_spin.value(),
            box_size=self.box_spin.value(),
            border=self.border_spin.value(),
            fg_color=self.fg_edit.text().strip() or "#111111",
            bg_color=self.bg_edit.text().strip() or "#FFFFFF",
        )

    def pick_color(self, target: QLineEdit) -> None:
        color = QColorDialog.getColor(QColor(target.text() or "#111111"), self, tr("common.field.foreground"))
        if color.isValid():
            target.setText(color.name())
            self.update_preview()

    def update_preview(self) -> None:
        text = self.uri_edit.toPlainText().strip()
        if not text:
            self.validation_label.setText(tr("dialog.add_entry.validation.paste_uri"))
            self.validation_label.setVisible(True)
            self.uri_edit.setProperty("invalid", False)
            refresh_widget_style(self.uri_edit)
            self.qr_label.setObjectName("emptyQrState")
            refresh_widget_style(self.qr_label)
            self.qr_label.setText(tr("dialog.add_entry.preview.waiting"))
            self.params_table.setRowCount(0)
            self.copy_qr_button.setEnabled(False)
            return

        try:
            parsed = parse_proxy_text(text)
            rows = [
                (tr("common.field.type"), format_proxy_type(parsed.type)),
                (tr("common.field.transport"), parsed.transport or tr("common.not_available")),
                (tr("common.field.server_host"), parsed.server_host or tr("common.not_available")),
                (tr("common.field.server_port"), str(parsed.server_port or "")),
            ]
            rows.extend((key, value) for key, value in parsed.params.items())
            populate_params_table(self.params_table, rows)
            pixmap = qr_pixmap(text, self.current_qr_options(), max_size=300)
            self.qr_label.setPixmap(pixmap)
            self.qr_label.setText("")
            self.validation_label.clear()
            self.validation_label.setVisible(False)
            self.uri_edit.setProperty("invalid", False)
            refresh_widget_style(self.uri_edit)
            self.qr_label.setObjectName("qrCanvas")
            refresh_widget_style(self.qr_label)
            self.copy_qr_button.setEnabled(True)
            if not self.name_edit.text().strip():
                suggested = parsed.display_name or parsed.server_host or format_proxy_type(parsed.type)
                self.name_edit.setText(suggested)
        except Exception as exc:
            self.validation_label.setText(ui_error_message("dialog.add_entry.validation.invalid_configuration", exc))
            self.validation_label.setVisible(True)
            self.uri_edit.setProperty("invalid", True)
            refresh_widget_style(self.uri_edit)
            self.qr_label.setObjectName("emptyQrState")
            refresh_widget_style(self.qr_label)
            self.qr_label.setPixmap(QPixmap())
            self.qr_label.setText(tr("dialog.add_entry.preview.invalid"))
            self.params_table.setRowCount(0)
            self.copy_qr_button.setEnabled(False)

    def copy_qr(self) -> None:
        pixmap = self.qr_label.pixmap()
        if pixmap:
            copy_pixmap_to_clipboard(pixmap)

    def _accept(self) -> None:
        text = self.uri_edit.toPlainText().strip()
        if not text:
            self.validation_label.setText(tr("dialog.add_entry.validation.uri_required"))
            self.validation_label.setVisible(True)
            return
        expiry = self.expiry_edit.text().strip()
        if expiry and len(expiry.split("-")) != 3:
            self.validation_label.setText(tr("dialog.add_entry.validation.expiry_format"))
            self.validation_label.setVisible(True)
            return
        try:
            parse_proxy_text(text)
        except ParseError as exc:
            self.validation_label.setText(format_ui_error("dialog.add_entry.validation.invalid_configuration", detail=exc))
            self.validation_label.setVisible(True)
            return
        self._result_payload = {
            "name": self.name_edit.text().strip(),
            "uri": text,
            "tags": self.tags_edit.text().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
            "expiry_date": expiry,
            "is_favorite": self.favorite_check.isChecked(),
            "qr_options": self.current_qr_options(),
        }
        self.accept()

    @property
    def payload(self) -> dict[str, Any]:
        return self._result_payload


class ImportSubscriptionDialog(QDialog):
    def __init__(
        self,
        default_refresh_interval: str,
        allow_insecure_http: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        ensure_ui_translations()
        self.default_refresh_interval = default_refresh_interval
        self.allow_insecure_http = allow_insecure_http
        self._items: list[SubscriptionImportItem] = []
        self._thread_pool = QThreadPool.globalInstance()
        self._fetch_worker: FunctionWorker | None = None
        self._fetch_source_message = ""
        self._build_ui()
        self.retranslate_ui()
        self._autofill_from_clipboard()

    def _build_ui(self) -> None:
        self.resize(880, 560)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        info_group = QFrame()
        info_group.setObjectName("subscriptionInfoGroup")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setSpacing(10)
        top_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.fetch_button = QPushButton("")
        self.fetch_button.setProperty("variant", "primary")
        self.fetch_button.clicked.connect(self.fetch_subscription)
        apply_button_icon(self.fetch_button, "import", color="#3A2B1C")
        top_row.addWidget(self.url_edit, 1)
        top_row.addWidget(self.fetch_button)
        info_layout.addLayout(top_row)

        controls = QFormLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(12)
        controls.setVerticalSpacing(10)
        controls.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.refresh_combo = QComboBox()
        self.format_label = QLabel("")
        self.refresh_label = make_form_label("")
        self.format_field_label = make_form_label("")
        controls.addRow(self.refresh_label, self.refresh_combo)
        controls.addRow(self.format_field_label, self.format_label)
        info_layout.addLayout(controls)
        root.addWidget(info_group)

        self.error_label = QLabel("")
        self.error_label.setObjectName("inlineValidation")
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)
        self.source_label = QLabel("")
        self.source_label.setObjectName("dialogSourceLabel")
        root.addWidget(self.source_label)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("subscriptionPreviewTable")
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setShowGrid(False)
        root.addWidget(self.table, 1)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self._accept)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("dialog.subscription.title"))
        self.url_edit.setPlaceholderText(tr("dialog.subscription.placeholder.url"))
        self.fetch_button.setText(tr("action.fetch"))
        self.refresh_label.setText(tr("common.field.auto_refresh"))
        self.format_field_label.setText(tr("common.field.detected_format"))
        self._populate_refresh_combo(self.refresh_combo.currentData() or self.default_refresh_interval)
        if not self.format_label.text():
            self.format_label.setText(tr("dialog.subscription.status.waiting"))
        self.table.setHorizontalHeaderLabels(
            [
                tr("action.add"),
                tr("common.field.name"),
                tr("common.field.type"),
                tr("common.field.server_host"),
                tr("common.field.server_port"),
            ]
        )
        _localized_buttons(self.button_box, accept_text=tr("common.ok"), cancel_text=tr("common.cancel"))
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            apply_button_icon(ok_button, "add", color="#3A2B1C")

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

    def _set_items(self, items: list[SubscriptionImportItem], format_name: str, source_message: str = "") -> None:
        self._items = items
        self._populate_table(items)
        self.format_label.setText(f"{tr('common.field.detected_format')}: {format_name}")
        self.error_label.clear()
        self.error_label.setVisible(False)
        self.source_label.setText(source_message)

    def _autofill_from_clipboard(self) -> None:
        text = clipboard_text()
        if not text:
            return
        if looks_like_subscription_url_candidate(text):
            self.url_edit.setText(text)
            try:
                validate_subscription_url(text, allow_insecure_http=self.allow_insecure_http)
            except SubscriptionSecurityError as exc:
                self.error_label.setText(ui_error_message("dialog.subscription.validation.invalid_source", exc))
                self.error_label.setVisible(True)
                self.source_label.setText(tr("dialog.subscription.source.clipboard_url"))
                return
            self.fetch_subscription(source_message=tr("dialog.subscription.source.clipboard_url"))
            return
        try:
            fmt, items = parse_subscription_payload(text)
        except ParseError:
            return
        self._set_items(items, fmt.value, tr("dialog.subscription.source.clipboard_content"))

    def fetch_subscription(self, _checked: bool = False, source_message: str = "") -> None:
        source_text = self.url_edit.text().strip()
        if not source_text:
            self.error_label.setText(tr("dialog.subscription.validation.enter_source"))
            self.error_label.setVisible(True)
            return

        if not looks_like_subscription_url_candidate(source_text):
            try:
                fmt, items = parse_subscription_payload(source_text)
                self._set_items(items, fmt.value, source_message or tr("dialog.subscription.source.input_content"))
                return
            except ParseError:
                self.error_label.setText(tr("dialog.subscription.validation.invalid_source"))
                self.error_label.setVisible(True)
                return
        try:
            validated_url = validate_subscription_url(source_text, allow_insecure_http=self.allow_insecure_http)
        except SubscriptionSecurityError as exc:
            self.error_label.setText(ui_error_message("dialog.subscription.validation.invalid_source", exc))
            self.error_label.setVisible(True)
            self.format_label.setText(tr("dialog.subscription.status.waiting"))
            return

        self.error_label.clear()
        self.error_label.setVisible(False)
        self.fetch_button.setEnabled(False)
        self.format_label.setText(tr("dialog.subscription.status.loading"))
        self._fetch_source_message = source_message
        self.source_label.setText(source_message or tr("dialog.subscription.source.fetching"))
        worker = FunctionWorker(
            fetch_subscription_url_payload,
            validated_url,
            allow_insecure_http=self.allow_insecure_http,
        )
        self._fetch_worker = worker
        worker.signals.finished.connect(self._handle_fetch_success)
        worker.signals.error.connect(self._handle_fetch_error)
        self._thread_pool.start(worker)

    def _handle_fetch_success(self, payload: dict[str, Any]) -> None:
        self._set_items(
            payload.get("items", []),
            str(payload.get("format_name", "unknown")),
            self._fetch_source_message or tr("dialog.subscription.source.fetched"),
        )
        self._finish_fetch()

    def _handle_fetch_error(self, exc: object) -> None:
        message = ui_error_message("ui.error.subscription_failed", exc)
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.format_label.setText(tr("dialog.subscription.status.waiting"))
        QToolTip.showText(self.mapToGlobal(self.rect().center()), message, self)
        QMessageBox.warning(self, tr("dialog.subscription.error.title"), message)
        self._finish_fetch()

    def _finish_fetch(self) -> None:
        self._fetch_source_message = ""
        self._fetch_worker = None
        self.fetch_button.setEnabled(True)

    def _populate_table(self, items: list[SubscriptionImportItem]) -> None:
        self.table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            checkbox_item = QTableWidgetItem()
            checkbox_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row_index, 0, checkbox_item)
            self.table.setItem(row_index, 1, QTableWidgetItem(item.name))
            self.table.setItem(row_index, 2, QTableWidgetItem(format_proxy_type(item.parsed.type)))
            self.table.setItem(row_index, 3, QTableWidgetItem(item.parsed.server_host))
            self.table.setItem(row_index, 4, QTableWidgetItem(str(item.parsed.server_port or "")))

    def selected_items(self) -> list[SubscriptionImportItem]:
        chosen: list[SubscriptionImportItem] = []
        for row_index, item in enumerate(self._items):
            check_item = self.table.item(row_index, 0)
            if check_item and check_item.checkState() == Qt.CheckState.Checked:
                chosen.append(item)
        return chosen

    def _accept(self) -> None:
        if not self.selected_items():
            self.error_label.setText(tr("dialog.subscription.validation.select_one"))
            self.error_label.setVisible(True)
            return
        self.accept()

    @property
    def refresh_interval(self) -> str:
        return str(self.refresh_combo.currentData() or "never")

    @property
    def url(self) -> str:
        value = self.url_edit.text().strip()
        try:
            return validate_subscription_url(value, allow_insecure_http=self.allow_insecure_http)
        except SubscriptionSecurityError:
            return ""


class PasswordDialog(QDialog):
    def __init__(
        self,
        title: str,
        ask_current: bool = False,
        confirm_new: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        ensure_ui_translations()
        self._title_text = title
        self.ask_current = ask_current
        self.confirm_new = confirm_new
        self._build_ui()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        self.resize(420, 220)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.current_edit = QLineEdit()
        self.current_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.current_label = make_form_label("", min_width=110)
        self.password_label = make_form_label("", min_width=110)
        self.confirm_label = make_form_label("", min_width=110)
        if self.ask_current:
            form.addRow(self.current_label, self.current_edit)
        form.addRow(self.password_label, self.password_edit)
        if self.confirm_new:
            form.addRow(self.confirm_label, self.confirm_edit)
        root.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("inlineValidation")
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self._title_text)
        self.current_label.setText(tr("common.field.current_password"))
        self.password_label.setText(tr("common.field.password"))
        self.confirm_label.setText(tr("common.field.confirm_password"))
        _localized_buttons(self.buttons, accept_text=tr("common.ok"), cancel_text=tr("common.cancel"))
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            apply_button_icon(ok_button, "lock", color="#3A2B1C")

    def _accept(self) -> None:
        if not self.password:
            self.error_label.setText(tr("dialog.password.validation.empty"))
            self.error_label.setVisible(True)
            return
        if self.confirm_new and self.password != self.confirm_password:
            self.error_label.setText(tr("dialog.password.validation.mismatch"))
            self.error_label.setVisible(True)
            return
        self.accept()

    @property
    def current_password(self) -> str:
        return self.current_edit.text()

    @property
    def password(self) -> str:
        return self.password_edit.text()

    @property
    def confirm_password(self) -> str:
        return self.confirm_edit.text()


class WelcomeDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        ensure_ui_translations()
        self.setObjectName("dialogShell")
        self._build_ui()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        self.resize(660, 540)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        self.hero_card = QFrame()
        self.hero_card.setObjectName("dialogHeroCard")
        hero_layout = QVBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(14, 14, 14, 14)
        hero_layout.setSpacing(10)
        hero_top = QHBoxLayout()
        hero_top.setSpacing(12)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(6)
        self.title_label = QLabel("")
        self.title_label.setProperty("role", "windowTitle")
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("dialogHeroSummary")
        self.summary_label.setWordWrap(True)
        hero_copy.addWidget(self.title_label)
        hero_copy.addWidget(self.summary_label)
        hero_top.addLayout(hero_copy, 1)
        self.quick_start_pill = QLabel("")
        self.quick_start_pill.setObjectName("dialogHeroPill")
        hero_top.addWidget(self.quick_start_pill, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(hero_top)
        root.addWidget(self.hero_card)

        self.body_card = QFrame()
        self.body_card.setObjectName("dialogSectionCard")
        body_layout = QVBoxLayout(self.body_card)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(0)
        self.body_view = QTextBrowser()
        self.body_view.setObjectName("welcomeBodyView")
        self.body_view.setOpenExternalLinks(False)
        self.body_view.setReadOnly(True)
        body_layout.addWidget(self.body_view)
        root.addWidget(self.body_card, 1)

        buttons = QDialogButtonBox()
        self.add_button = buttons.addButton("", QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_button.setProperty("variant", "primary")
        apply_button_icon(self.add_button, "add", color="#3A2B1C")
        self.later_button = buttons.addButton("", QDialogButtonBox.ButtonRole.RejectRole)
        self.later_button.setProperty("variant", "subtle")
        self.add_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def retranslate_ui(self) -> None:
        markdown = load_help_markdown("welcome")
        title, _sections = _split_markdown_sections(markdown)
        self.setWindowTitle(title or tr("dialog.welcome.title"))
        self.title_label.setText(title or tr("dialog.welcome.title"))
        self.summary_label.setText(tr("dialog.welcome.subtitle"))
        self.quick_start_pill.setText(
            tr("dialog.welcome.quick_start_steps", count=_count_markdown_numbered_steps(markdown))
        )
        self.body_view.setMarkdown(_strip_markdown_title(markdown) or tr("dialog.welcome.body"))
        self.add_button.setText(tr("onboarding.welcome.primary_cta"))
        self.later_button.setText(tr("onboarding.welcome.secondary_cta"))


class HelpDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        ensure_ui_translations()
        self.setObjectName("dialogShell")
        self.sections: list[tuple[str, str]] = []
        self._build_ui()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        self.resize(980, 700)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        self.hero_card = QFrame()
        self.hero_card.setObjectName("dialogHeroCard")
        hero_layout = QVBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(14, 14, 14, 14)
        hero_layout.setSpacing(10)
        hero_top = QHBoxLayout()
        hero_top.setSpacing(12)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(6)
        self.title_label = QLabel("")
        self.title_label.setProperty("role", "windowTitle")
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("dialogHeroSummary")
        self.summary_label.setWordWrap(True)
        hero_copy.addWidget(self.title_label)
        hero_copy.addWidget(self.summary_label)
        hero_top.addLayout(hero_copy, 1)
        self.section_count_pill = QLabel("")
        self.section_count_pill.setObjectName("dialogHeroPill")
        hero_top.addWidget(self.section_count_pill, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(hero_top)
        root.addWidget(self.hero_card)

        content_row = QHBoxLayout()
        content_row.setSpacing(12)
        self.navigation_card = QFrame()
        self.navigation_card.setObjectName("dialogSectionCard")
        navigation_layout = QVBoxLayout(self.navigation_card)
        navigation_layout.setContentsMargins(12, 12, 12, 12)
        navigation_layout.setSpacing(8)
        self.navigation_title = QLabel("")
        self.navigation_title.setObjectName("dialogSectionTitle")
        navigation_layout.addWidget(self.navigation_title)
        self.section_list = QListWidget()
        self.section_list.setObjectName("helpSectionList")
        self.section_list.setMinimumWidth(240)
        self.section_list.currentRowChanged.connect(self._show_section)
        navigation_layout.addWidget(self.section_list, 1)
        content_row.addWidget(self.navigation_card, 0)

        self.content_card = QFrame()
        self.content_card.setObjectName("dialogSectionCard")
        content_layout = QVBoxLayout(self.content_card)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(8)
        self.current_section_hint = QLabel("")
        self.current_section_hint.setObjectName("dialogSectionTitle")
        content_layout.addWidget(self.current_section_hint)
        self.current_section_label = QLabel("")
        self.current_section_label.setObjectName("dialogCurrentSection")
        self.current_section_label.setWordWrap(True)
        content_layout.addWidget(self.current_section_label)
        self.section_view = QTextBrowser()
        self.section_view.setObjectName("helpContentView")
        self.section_view.setReadOnly(True)
        self.section_view.setOpenExternalLinks(False)
        content_layout.addWidget(self.section_view, 1)
        content_row.addWidget(self.content_card, 1)
        root.addLayout(content_row, 1)

        self.close_button = QPushButton("")
        self.close_button.setProperty("variant", "subtle")
        self.close_button.clicked.connect(self.accept)
        root.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)

    def retranslate_ui(self) -> None:
        markdown = load_help_markdown("content")
        title, sections = _split_markdown_sections(markdown)
        self.sections = sections
        self.setWindowTitle(title or tr("dialog.help.title"))
        self.title_label.setText(title or tr("dialog.help.title"))
        self.summary_label.setText(tr("dialog.help.subtitle"))
        self.section_count_pill.setText(tr("dialog.help.sections", count=len(self.sections)))
        self.navigation_title.setText(tr("dialog.help.navigation"))
        self.current_section_hint.setText(tr("dialog.help.current_section"))
        previous_row = self.section_list.currentRow()
        self.section_list.clear()
        for section_title, _body in self.sections:
            self.section_list.addItem(QListWidgetItem(section_title))
        if self.sections:
            target_row = previous_row if 0 <= previous_row < len(self.sections) else 0
            self.section_list.setCurrentRow(target_row)
        else:
            self.current_section_label.clear()
            self.section_view.setMarkdown(_strip_markdown_title(markdown) or "")
        self.close_button.setText(tr("common.close"))

    def _show_section(self, row: int) -> None:
        if row < 0 or row >= len(self.sections):
            self.current_section_label.clear()
            self.section_view.clear()
            return
        title, body = self.sections[row]
        self.current_section_label.setText(title)
        self.section_view.setMarkdown(_strip_leading_section_heading(body) or body)


class RuntimeLogDialog(QDialog):
    def __init__(
        self,
        entry_name: str,
        *,
        log_text: str,
        log_path: str = "",
        path_message: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        ensure_ui_translations()
        self.entry_name = entry_name
        self.log_text = log_text
        self.log_path = log_path
        self.path_message = path_message
        self._build_ui()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        self.resize(820, 560)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        self.title_label = QLabel("")
        self.title_label.setProperty("role", "windowTitle")
        root.addWidget(self.title_label)
        self.path_label = QLabel("")
        self.path_label.setProperty("role", "muted")
        self.path_label.setWordWrap(True)
        root.addWidget(self.path_label)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        root.addWidget(self.log_view, 1)
        self.close_button = QPushButton("")
        self.close_button.setProperty("variant", "subtle")
        self.close_button.clicked.connect(self.accept)
        root.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("dialog.logs.title"))
        self.title_label.setText(f"{tr('dialog.logs.title')} - {self.entry_name}")
        if self.log_path:
            self.path_label.setText(f"{tr('common.field.log_path')}: {self.log_path}")
        elif self.path_message:
            self.path_label.setText(self.path_message)
        else:
            self.path_label.setText(tr("dialog.runtime_log.path_missing"))
        self.log_view.setPlainText(self.log_text or tr("dialog.runtime_log.empty"))
        self.close_button.setText(tr("common.close"))


class SessionHistoryDialog(QDialog):
    def __init__(self, entry_name: str, records: list[SessionHistoryRecord], parent: QWidget | None = None):
        super().__init__(parent)
        ensure_ui_translations()
        self.entry_name = entry_name
        self.records = records
        self._build_ui()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        self.resize(940, 560)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)
        self.title_label = QLabel("")
        self.title_label.setProperty("role", "windowTitle")
        root.addWidget(self.title_label)
        self.summary_label = QLabel("")
        self.summary_label.setProperty("role", "muted")
        root.addWidget(self.summary_label)
        self.table = QTableWidget(0, 7)
        self.table.setObjectName("sessionHistoryTable")
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        root.addWidget(self.table, 1)
        self.close_button = QPushButton("")
        self.close_button.setProperty("variant", "subtle")
        self.close_button.clicked.connect(self.accept)
        root.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("dialog.sessions.title"))
        self.title_label.setText(f"{tr('dialog.sessions.title')} - {self.entry_name}")
        if self.records:
            self.summary_label.setText(tr("main.runtime.active_sessions", count=len(self.records)))
        else:
            self.summary_label.setText(tr("dialog.sessions.empty"))
        self.table.setHorizontalHeaderLabels(
            [
                tr("common.field.started"),
                tr("common.field.stopped"),
                tr("common.field.history_state"),
                tr("common.field.primary_flag"),
                tr("common.field.route_owner"),
                tr("common.field.engine"),
                tr("common.field.result"),
            ]
        )
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            result_text = (
                runtime_error_display(record.failure_reason, record.short_log_excerpt)
                if record.failure_reason or record.short_log_excerpt
                else tr("common.value.none")
            )
            values = [
                record.started_at,
                record.stopped_at,
                format_runtime_state(record.state),
                tr("common.value.yes") if record.primary_flag else tr("common.value.no"),
                format_route_owner(record.route_owner_kind),
                runtime_engine_label(record.engine_kind),
                result_text,
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.close_button.setText(tr("common.close"))


class FullScreenQrDialog(QDialog):
    def __init__(self, title: str, pixmap: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.pixmap = pixmap
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(
            self.pixmap.scaled(
                900,
                900,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        root.addWidget(label)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.showFullScreen()
