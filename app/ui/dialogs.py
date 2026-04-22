from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QFrame,
)

from app.models import QROptions, SubscriptionImportItem, TYPE_LABELS
from app.parser import ParseError, is_wireguard_block, parse_proxy_text, parse_subscription_payload
from app.qr_gen import copy_pixmap_to_clipboard, qr_pixmap
from app.subscriptions import (
    SubscriptionSecurityError,
    fetch_subscription_url_payload,
    looks_like_subscription_url_candidate,
    validate_subscription_url,
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

class AddEntryDialog(QDialog):
    def __init__(
        self,
        default_options: QROptions,
        prefill_text: str = "",
        prefill_name: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Proxy Entry")
        self.resize(900, 720)
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
            self.source_label.setText("Configuration loaded from clipboard.")
        self.update_preview()

    def _build_ui(self) -> None:
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
        self.expiry_edit.setPlaceholderText("YYYY-MM-DD")
        self.favorite_check = QCheckBox("Favorite")
        self.uri_edit = QPlainTextEdit()
        self.uri_edit.setPlaceholderText("Paste a proxy URI or a WireGuard config block")
        self.uri_edit.setMinimumHeight(160)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setObjectName("notesEdit")
        self.notes_edit.setPlaceholderText("Notes")
        self.notes_edit.setMinimumHeight(90)

        form.addRow(make_form_label("Name"), self.name_edit)
        form.addRow(make_form_label("Tags"), self.tags_edit)
        form.addRow(make_form_label("Expiry"), self.expiry_edit)
        form.addRow(make_form_label(""), self.favorite_check)
        form.addRow(make_form_label("URI / Config", min_width=92), self.uri_edit)
        form.addRow(make_form_label("Notes"), self.notes_edit)
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
        parsed_title = QLabel("Parsed Parameters")
        parsed_title.setProperty("role", "subSectionTitle")
        preview_layout.addWidget(parsed_title, 0, 0)
        qr_title = QLabel("Live QR Preview")
        qr_title.setProperty("role", "subSectionTitle")
        preview_layout.addWidget(qr_title, 0, 1)

        self.params_table = QTableWidget(0, 2)
        self.params_table.setObjectName("parsedTable")
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Value"])
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

        self.copy_qr_button = QPushButton("Copy QR Image")
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
        self.version_spin.setSpecialValueText("Auto")
        self.box_spin = QSpinBox()
        self.box_spin.setRange(1, 40)
        self.border_spin = QSpinBox()
        self.border_spin.setRange(0, 20)
        self.fg_edit = QLineEdit()
        self.bg_edit = QLineEdit()
        fg_button = QPushButton("Pick")
        fg_button.clicked.connect(lambda: self.pick_color(self.fg_edit))
        bg_button = QPushButton("Pick")
        bg_button.clicked.connect(lambda: self.pick_color(self.bg_edit))
        fg_row = QHBoxLayout()
        fg_row.addWidget(self.fg_edit)
        fg_row.addWidget(fg_button)
        bg_row = QHBoxLayout()
        bg_row.addWidget(self.bg_edit)
        bg_row.addWidget(bg_button)
        options_form.addRow(make_form_label("Error level"), self.error_combo)
        options_form.addRow(make_form_label("Version"), self.version_spin)
        options_form.addRow(make_form_label("Box size"), self.box_spin)
        options_form.addRow(make_form_label("Border"), self.border_spin)
        options_form.addRow(make_form_label("Foreground"), self._wrap_layout(fg_row))
        options_form.addRow(make_form_label("Background"), self._wrap_layout(bg_row))
        right_column.addLayout(options_form)

        preview_layout.addLayout(right_column, 1, 1)
        preview_group_layout.addLayout(preview_layout)
        root.addWidget(preview_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button:
            ok_button.setProperty("variant", "primary")
            apply_button_icon(ok_button, "add", color="#3A2B1C")
        if cancel_button:
            cancel_button.setProperty("variant", "subtle")
        root.addWidget(buttons)

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
        color = QColorDialog.getColor(QColor(target.text() or "#111111"), self, "Choose Color")
        if color.isValid():
            target.setText(color.name())
            self.update_preview()

    def update_preview(self) -> None:
        text = self.uri_edit.toPlainText().strip()
        if not text:
            self.validation_label.setText("Paste a URI or config to generate a QR code.")
            self.validation_label.setVisible(True)
            self.uri_edit.setProperty("invalid", False)
            refresh_widget_style(self.uri_edit)
            self.qr_label.setObjectName("emptyQrState")
            refresh_widget_style(self.qr_label)
            self.qr_label.setText("Waiting for input")
            self.params_table.setRowCount(0)
            self.copy_qr_button.setEnabled(False)
            return

        try:
            parsed = parse_proxy_text(text)
            rows = [
                ("Type", TYPE_LABELS.get(parsed.type, parsed.type.value)),
                ("Transport", parsed.transport or "n/a"),
                ("Server host", parsed.server_host or "n/a"),
                ("Server port", str(parsed.server_port or "")),
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
                suggested = parsed.display_name or parsed.server_host or TYPE_LABELS.get(parsed.type, parsed.type.value)
                self.name_edit.setText(suggested)
        except Exception as exc:
            self.validation_label.setText(str(exc))
            self.validation_label.setVisible(True)
            self.uri_edit.setProperty("invalid", True)
            refresh_widget_style(self.uri_edit)
            self.qr_label.setObjectName("emptyQrState")
            refresh_widget_style(self.qr_label)
            self.qr_label.setPixmap(QPixmap())
            self.qr_label.setText("Invalid configuration")
            self.params_table.setRowCount(0)
            self.copy_qr_button.setEnabled(False)

    def copy_qr(self) -> None:
        pixmap = self.qr_label.pixmap()
        if pixmap:
            copy_pixmap_to_clipboard(pixmap)

    def _accept(self) -> None:
        text = self.uri_edit.toPlainText().strip()
        if not text:
            self.validation_label.setText("A URI or WireGuard block is required.")
            self.validation_label.setVisible(True)
            return
        expiry = self.expiry_edit.text().strip()
        if expiry and len(expiry.split("-")) != 3:
            self.validation_label.setText("Expiry date must use YYYY-MM-DD.")
            self.validation_label.setVisible(True)
            return
        try:
            parse_proxy_text(text)
        except ParseError as exc:
            self.validation_label.setText(str(exc))
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
        self.setWindowTitle("Import Subscription")
        self.resize(880, 560)
        self.default_refresh_interval = default_refresh_interval
        self.allow_insecure_http = allow_insecure_http
        self._items: list[SubscriptionImportItem] = []
        self._thread_pool = QThreadPool.globalInstance()
        self._fetch_worker: FunctionWorker | None = None
        self._fetch_source_message = ""
        self._build_ui()
        self._autofill_from_clipboard()

    def _build_ui(self) -> None:
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
        self.url_edit.setPlaceholderText("https://example.com/subscription")
        self.fetch_button = QPushButton("Fetch")
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
        self.refresh_combo.addItems(["never", "daily", "weekly"])
        self.refresh_combo.setCurrentText(self.default_refresh_interval)
        self.format_label = QLabel("Format: waiting")
        controls.addRow(make_form_label("Auto-refresh", min_width=92), self.refresh_combo)
        controls.addRow(make_form_label("Detected format", min_width=92), self.format_label)
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
        self.table.setHorizontalHeaderLabels(["Import", "Name", "Type", "Host", "Port"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setShowGrid(False)
        root.addWidget(self.table, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._accept)
        button_box.rejected.connect(self.reject)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button:
            ok_button.setProperty("variant", "primary")
            apply_button_icon(ok_button, "add", color="#3A2B1C")
        if cancel_button:
            cancel_button.setProperty("variant", "subtle")
        root.addWidget(button_box)

    def _set_items(self, items: list[SubscriptionImportItem], format_name: str, source_message: str = "") -> None:
        self._items = items
        self._populate_table(items)
        self.format_label.setText(f"Format: {format_name}")
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
                self.error_label.setText(str(exc))
                self.error_label.setVisible(True)
                self.source_label.setText("Subscription URL loaded from clipboard.")
                return
            self.fetch_subscription(source_message="Subscription URL loaded from clipboard.")
            return
        try:
            fmt, items = parse_subscription_payload(text)
        except ParseError:
            return
        self._set_items(items, fmt.value, "Subscription content loaded from clipboard.")

    def fetch_subscription(self, _checked: bool = False, source_message: str = "") -> None:
        source_text = self.url_edit.text().strip()
        if not source_text:
            self.error_label.setText("Enter a subscription URL or keep a supported payload in the clipboard.")
            self.error_label.setVisible(True)
            return

        if not looks_like_subscription_url_candidate(source_text):
            try:
                fmt, items = parse_subscription_payload(source_text)
                self._set_items(items, fmt.value, source_message or "Parsed subscription content from the input field.")
                return
            except ParseError:
                self.error_label.setText("Enter a valid subscription URL or paste supported subscription content.")
                self.error_label.setVisible(True)
                return
        try:
            validated_url = validate_subscription_url(source_text, allow_insecure_http=self.allow_insecure_http)
        except SubscriptionSecurityError as exc:
            self.error_label.setText(str(exc))
            self.error_label.setVisible(True)
            self.format_label.setText("Format: waiting")
            return

        self.error_label.clear()
        self.error_label.setVisible(False)
        self.fetch_button.setEnabled(False)
        self.format_label.setText("Format: loading...")
        self._fetch_source_message = source_message
        self.source_label.setText(source_message or "Fetching subscription from URL...")
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
            self._fetch_source_message or "Fetched subscription from URL.",
        )
        self._finish_fetch()

    def _handle_fetch_error(self, exc: object) -> None:
        message = str(exc)
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.format_label.setText("Format: waiting")
        QToolTip.showText(self.mapToGlobal(self.rect().center()), message, self)
        QMessageBox.warning(self, "Subscription Error", message)
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
            self.table.setItem(row_index, 2, QTableWidgetItem(TYPE_LABELS.get(item.parsed.type, item.parsed.type.value)))
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
            self.error_label.setText("Select at least one entry to import.")
            self.error_label.setVisible(True)
            return
        self.accept()

    @property
    def refresh_interval(self) -> str:
        return self.refresh_combo.currentText()

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
        self.setWindowTitle(title)
        self.resize(420, 220)
        self.ask_current = ask_current
        self.confirm_new = confirm_new
        self._build_ui()

    def _build_ui(self) -> None:
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
        if self.ask_current:
            form.addRow(make_form_label("Current password", min_width=110), self.current_edit)
        form.addRow(make_form_label("Password", min_width=110), self.password_edit)
        if self.confirm_new:
            form.addRow(make_form_label("Confirm password", min_width=110), self.confirm_edit)
        root.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setObjectName("inlineValidation")
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button:
            ok_button.setProperty("variant", "primary")
            apply_button_icon(ok_button, "lock", color="#3A2B1C")
        if cancel_button:
            cancel_button.setProperty("variant", "subtle")
        root.addWidget(buttons)

    def _accept(self) -> None:
        if not self.password:
            self.error_label.setText("Password cannot be empty.")
            self.error_label.setVisible(True)
            return
        if self.confirm_new and self.password != self.confirm_password:
            self.error_label.setText("Passwords do not match.")
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
        self.setWindowTitle("Welcome to ProxyVault")
        self.resize(520, 260)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        title = QLabel("Welcome to ProxyVault")
        title.setProperty("role", "windowTitle")
        body = QLabel(
            "ProxyVault keeps your proxy and VPN QR codes entirely local.\n\n"
            "Start by adding a single URI or a WireGuard config block, and the app will parse it, generate QR assets, and save it in your local library."
        )
        body.setProperty("role", "muted")
        body.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(body, 1)

        buttons = QDialogButtonBox()
        add_button = buttons.addButton("Add your first proxy", QDialogButtonBox.ButtonRole.AcceptRole)
        add_button.setProperty("variant", "primary")
        apply_button_icon(add_button, "add", color="#3A2B1C")
        later_button = buttons.addButton("Maybe later", QDialogButtonBox.ButtonRole.RejectRole)
        later_button.setProperty("variant", "subtle")
        add_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


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
        label.setPixmap(self.pixmap.scaled(900, 900, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        root.addWidget(label)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.showFullScreen()
