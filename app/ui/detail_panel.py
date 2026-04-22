from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models import (
    ProxyEntry,
    QROptions,
    ReachabilityCheck,
    ReachabilityState,
    TYPE_LABELS,
    format_duration_ms,
)
from app.parser import ParseError, parse_proxy_text
from app.qr_gen import copy_pixmap_to_clipboard, qr_pixmap
from app.ui.theme import apply_button_icon, make_form_label, refresh_widget_style, set_widget_status


class DetailPanel(QWidget):
    saveRequested = pyqtSignal(dict)
    deleteRequested = pyqtSignal(str)
    saveQrRequested = pyqtSignal(str)
    reachabilityRequested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.current_entry: ProxyEntry | None = None
        self.current_options = QROptions()
        self.current_history: list[ReachabilityCheck] = []
        self.original_pixmap = QPixmap()
        self.setObjectName("detailPanel")
        self._build_ui()
        self.clear_panel()

    def _build_ui(self) -> None:
        self.setMinimumWidth(320)
        self.setMaximumWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = QLabel("Entry Details")
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)

        self.entry_context = QLabel("")
        self.entry_context.setProperty("role", "muted")
        self.entry_context.setWordWrap(True)
        layout.addWidget(self.entry_context)

        self.form_group = QFrame()
        self.form_group.setObjectName("formGroup")
        form_group_layout = QVBoxLayout(self.form_group)
        form_group_layout.setContentsMargins(12, 12, 12, 12)
        form_group_layout.setSpacing(10)

        form_title = QLabel("Metadata")
        form_title.setProperty("role", "subSectionTitle")
        form_group_layout.addWidget(form_title)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.name_edit = QLineEdit()
        self.tags_edit = QLineEdit()
        self.expiry_edit = QLineEdit()
        self.expiry_edit.setObjectName("expiryField")
        self.expiry_edit.setPlaceholderText("YYYY-MM-DD")
        self.favorite_check = QCheckBox("Favorite")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setObjectName("notesEdit")
        self.notes_edit.setPlaceholderText("Notes")
        self.notes_edit.setMaximumHeight(96)
        self.validation_label = QLabel("")
        self.validation_label.setObjectName("inlineValidation")
        self.validation_label.setVisible(False)

        form.addRow(make_form_label("Name"), self.name_edit)
        form.addRow(make_form_label("Tags"), self.tags_edit)
        form.addRow(make_form_label("Expiry"), self.expiry_edit)
        form.addRow(make_form_label(""), self.favorite_check)
        form.addRow(make_form_label("Notes"), self.notes_edit)
        form_group_layout.addLayout(form)
        form_group_layout.addWidget(self.validation_label)
        layout.addWidget(self.form_group)

        self.reachability_block = QFrame()
        self.reachability_block.setObjectName("detailGroup")
        reachability_layout = QVBoxLayout(self.reachability_block)
        reachability_layout.setContentsMargins(12, 12, 12, 12)
        reachability_layout.setSpacing(10)

        reachability_header = QHBoxLayout()
        reachability_header.setSpacing(8)
        reachability_title = QLabel("TCP Reachability")
        reachability_title.setProperty("role", "subSectionTitle")
        reachability_header.addWidget(reachability_title)
        reachability_header.addStretch(1)
        self.reachability_toggle_button = QPushButton("Show details")
        self.reachability_toggle_button.setProperty("variant", "subtle")
        self.reachability_toggle_button.setCheckable(True)
        self.reachability_toggle_button.clicked.connect(self._toggle_reachability_details)
        apply_button_icon(self.reachability_toggle_button, "details", color="#D8943C")
        reachability_header.addWidget(self.reachability_toggle_button)
        reachability_layout.addLayout(reachability_header)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(8)
        self.reachability_status_pill = QLabel("Not tested")
        self.reachability_status_pill.setObjectName("statusPill")
        summary_row.addWidget(self.reachability_status_pill, 0, Qt.AlignmentFlag.AlignLeft)
        self.reachability_checked_hint = QLabel("No TCP probe yet")
        self.reachability_checked_hint.setObjectName("reachabilityMeta")
        summary_row.addWidget(self.reachability_checked_hint, 1)
        self.check_now_button = QPushButton("Run TCP probe")
        self.check_now_button.setProperty("variant", "secondary")
        self.check_now_button.clicked.connect(self._emit_reachability)
        apply_button_icon(self.check_now_button, "reachability", color="#3A2B1C")
        summary_row.addWidget(self.check_now_button)
        reachability_layout.addLayout(summary_row)

        self.reachability_summary = QLabel("")
        self.reachability_summary.setObjectName("reachabilitySummary")
        self.reachability_summary.setWordWrap(True)
        reachability_layout.addWidget(self.reachability_summary)

        self.reachability_meta_grid = QFormLayout()
        self.reachability_meta_grid.setContentsMargins(0, 0, 0, 0)
        self.reachability_meta_grid.setHorizontalSpacing(10)
        self.reachability_meta_grid.setVerticalSpacing(8)
        self.reachability_meta_grid.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.reachability_last_value = QLabel("")
        self.reachability_last_value.setObjectName("reachabilityValue")
        self.reachability_freshness_value = QLabel("")
        self.reachability_freshness_value.setObjectName("reachabilityValue")
        self.reachability_endpoint_value = QLabel("")
        self.reachability_endpoint_value.setObjectName("reachabilityValue")
        self.reachability_endpoint_value.setWordWrap(True)
        self.reachability_method_value = QLabel("")
        self.reachability_method_value.setObjectName("reachabilityValue")
        self.reachability_latency_value = QLabel("")
        self.reachability_latency_value.setObjectName("reachabilityValue")
        self.reachability_reason_value = QLabel("")
        self.reachability_reason_value.setObjectName("reachabilityValue")
        self.reachability_reason_value.setWordWrap(True)

        self.reachability_meta_grid.addRow(make_form_label("Last checked", min_width=88), self.reachability_last_value)
        self.reachability_meta_grid.addRow(make_form_label("Freshness", min_width=88), self.reachability_freshness_value)
        self.reachability_meta_grid.addRow(make_form_label("Endpoint", min_width=88), self.reachability_endpoint_value)
        self.reachability_meta_grid.addRow(make_form_label("Method", min_width=88), self.reachability_method_value)
        self.reachability_meta_grid.addRow(make_form_label("Latency", min_width=88), self.reachability_latency_value)
        self.reachability_meta_grid.addRow(make_form_label("Reason", min_width=88), self.reachability_reason_value)
        reachability_layout.addLayout(self.reachability_meta_grid)

        self.reachability_details_frame = QFrame()
        self.reachability_details_frame.setObjectName("reachabilityDetails")
        reachability_details_layout = QVBoxLayout(self.reachability_details_frame)
        reachability_details_layout.setContentsMargins(10, 10, 10, 10)
        reachability_details_layout.setSpacing(8)

        log_title = QLabel("Diagnostics")
        log_title.setProperty("role", "caption")
        reachability_details_layout.addWidget(log_title)
        self.reachability_log = QPlainTextEdit()
        self.reachability_log.setObjectName("reachabilityLog")
        self.reachability_log.setReadOnly(True)
        self.reachability_log.setMaximumHeight(98)
        reachability_details_layout.addWidget(self.reachability_log)

        history_title = QLabel("Recent probes")
        history_title.setProperty("role", "caption")
        reachability_details_layout.addWidget(history_title)
        self.reachability_history_table = QTableWidget(0, 4)
        self.reachability_history_table.setObjectName("reachabilityHistoryTable")
        self.reachability_history_table.setHorizontalHeaderLabels(["When", "Status", "Method", "Result"])
        self.reachability_history_table.verticalHeader().setVisible(False)
        self.reachability_history_table.horizontalHeader().setStretchLastSection(True)
        self.reachability_history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.reachability_history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.reachability_history_table.setShowGrid(False)
        self.reachability_history_table.setMaximumHeight(148)
        reachability_details_layout.addWidget(self.reachability_history_table)

        reachability_layout.addWidget(self.reachability_details_frame)
        layout.addWidget(self.reachability_block)

        qr_frame = QFrame()
        qr_frame.setObjectName("qrBlock")
        qr_layout = QVBoxLayout(qr_frame)
        qr_layout.setContentsMargins(12, 12, 12, 12)
        qr_layout.setSpacing(10)
        qr_title = QLabel("QR Preview")
        qr_title.setProperty("role", "subSectionTitle")
        qr_layout.addWidget(qr_title)
        self.qr_label = QLabel()
        self.qr_label.setObjectName("qrCanvas")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumHeight(212)
        qr_layout.addWidget(self.qr_label)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(80, 280)
        self.zoom_slider.setValue(160)
        self.zoom_slider.valueChanged.connect(self._apply_zoom)
        qr_layout.addWidget(self.zoom_slider)
        layout.addWidget(qr_frame)

        table_block = QFrame()
        table_block.setObjectName("tableBlock")
        table_layout = QVBoxLayout(table_block)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)
        table_title = QLabel("Parsed Parameters")
        table_title.setProperty("role", "subSectionTitle")
        table_layout.addWidget(table_title)

        self.params_table = QTableWidget(0, 2)
        self.params_table.setObjectName("parsedTable")
        self.params_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.horizontalHeader().setStretchLastSection(True)
        self.params_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.params_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.params_table.setShowGrid(False)
        table_layout.addWidget(self.params_table)
        layout.addWidget(table_block, 1)

        action_group = QFrame()
        action_group.setObjectName("actionGroup")
        action_layout = QVBoxLayout(action_group)
        action_layout.setContentsMargins(12, 12, 12, 12)
        action_layout.setSpacing(8)
        action_title = QLabel("Actions")
        action_title.setProperty("role", "subSectionTitle")
        action_layout.addWidget(action_title)

        utility_row = QHBoxLayout()
        self.copy_uri_button = QPushButton("Copy URI")
        self.copy_uri_button.setProperty("variant", "subtle")
        self.copy_uri_button.clicked.connect(self.copy_uri)
        apply_button_icon(self.copy_uri_button, "copy", color="#D8943C")
        self.copy_qr_button = QPushButton("Copy QR")
        self.copy_qr_button.setProperty("variant", "subtle")
        self.copy_qr_button.clicked.connect(self.copy_qr)
        apply_button_icon(self.copy_qr_button, "qr", color="#D8943C")
        utility_row.addWidget(self.copy_uri_button)
        utility_row.addWidget(self.copy_qr_button)
        action_layout.addLayout(utility_row)

        export_row = QHBoxLayout()
        self.save_qr_button = QPushButton("Save QR PNG")
        self.save_qr_button.setProperty("variant", "subtle")
        self.save_qr_button.clicked.connect(self._emit_save_qr)
        apply_button_icon(self.save_qr_button, "save", color="#D8943C")
        export_row.addWidget(self.save_qr_button)
        export_row.addStretch(1)
        action_layout.addLayout(export_row)

        commit_row = QHBoxLayout()
        self.save_button = QPushButton("Save Changes")
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self._emit_save)
        apply_button_icon(self.save_button, "save", color="#3A2B1C")
        self.delete_button = QPushButton("Delete Entry")
        self.delete_button.setProperty("variant", "destructive")
        self.delete_button.clicked.connect(self._emit_delete)
        apply_button_icon(self.delete_button, "delete", color="#C77768")
        commit_row.addWidget(self.save_button)
        commit_row.addWidget(self.delete_button)
        action_layout.addLayout(commit_row)
        layout.addWidget(action_group)

    def clear_panel(self) -> None:
        self.current_entry = None
        self.current_history = []
        self.original_pixmap = QPixmap()
        self.name_edit.clear()
        self.tags_edit.clear()
        self.expiry_edit.clear()
        self.notes_edit.clear()
        self.favorite_check.setChecked(False)
        self.entry_context.setText("Select a configuration to inspect QR, metadata, and TCP probe details.")
        self.qr_label.setObjectName("qrCanvas")
        refresh_widget_style(self.qr_label)
        self.qr_label.setText("Select an entry")
        self.qr_label.setPixmap(QPixmap())
        self._set_reachability_view(None, [])
        self.params_table.setRowCount(0)
        for widget in [
            self.name_edit,
            self.tags_edit,
            self.expiry_edit,
            self.notes_edit,
            self.favorite_check,
            self.copy_uri_button,
            self.copy_qr_button,
            self.save_qr_button,
            self.check_now_button,
            self.save_button,
            self.delete_button,
        ]:
            widget.setEnabled(False)
        self.validation_label.clear()
        self.validation_label.setVisible(False)
        self.expiry_edit.setProperty("invalid", False)
        refresh_widget_style(self.expiry_edit)

    def set_entry(self, entry: ProxyEntry, options: QROptions, history: list[ReachabilityCheck] | None = None) -> None:
        self.current_entry = entry
        self.current_options = options
        self.current_history = list(history or [])
        for widget in [
            self.name_edit,
            self.tags_edit,
            self.expiry_edit,
            self.notes_edit,
            self.favorite_check,
            self.copy_qr_button,
            self.save_qr_button,
            self.check_now_button,
            self.save_button,
            self.delete_button,
        ]:
            widget.setEnabled(True)
        self.copy_uri_button.setEnabled(bool(entry.uri) and not entry.is_locked)
        self.name_edit.setText(entry.name)
        self.tags_edit.setText(entry.tags)
        self.expiry_edit.setText(entry.expiry_date)
        self.notes_edit.setPlainText(entry.notes)
        self.favorite_check.setChecked(entry.is_favorite)
        self.entry_context.setText(
            f"{TYPE_LABELS.get(entry.type, entry.type.value)} · {entry.display_host_port} · {entry.transport or 'transport unknown'}"
        )
        self.validation_label.clear()
        self.validation_label.setVisible(False)
        self.expiry_edit.setProperty("invalid", False)
        refresh_widget_style(self.expiry_edit)
        self._populate_params(entry)
        self._load_preview(entry)
        self._set_reachability_view(entry, self.current_history)

    def _populate_params(self, entry: ProxyEntry) -> None:
        rows: list[tuple[str, str]] = [
            ("Type", TYPE_LABELS.get(entry.type, entry.type.value)),
            ("Transport", entry.transport or "n/a"),
            ("Server host", entry.server_host or "n/a"),
            ("Server port", str(entry.server_port or "")),
        ]
        if entry.uri and not entry.is_locked:
            try:
                parsed = parse_proxy_text(entry.uri)
                for key, value in parsed.params.items():
                    rows.append((key, value))
            except ParseError:
                rows.append(("Warning", "Unable to parse the stored URI"))
        elif entry.is_locked:
            rows.append(("Status", "Unlock ProxyVault to view the full parsed parameter set"))
        self.params_table.setRowCount(len(rows))
        for row_index, (key, value) in enumerate(rows):
            self.params_table.setItem(row_index, 0, QTableWidgetItem(key))
            self.params_table.setItem(row_index, 1, QTableWidgetItem(value))

    def _load_preview(self, entry: ProxyEntry) -> None:
        self.original_pixmap = QPixmap()
        if entry.uri and not entry.is_locked:
            self.original_pixmap = qr_pixmap(entry.uri, self.current_options, max_size=720)
        elif entry.qr_png_path and Path(entry.qr_png_path).exists():
            self.original_pixmap = QPixmap(entry.qr_png_path)
        if self.original_pixmap.isNull():
            self.qr_label.setObjectName("emptyQrState")
            refresh_widget_style(self.qr_label)
            self.qr_label.setText("QR preview unavailable")
            self.qr_label.setPixmap(QPixmap())
            return
        self.qr_label.setObjectName("qrCanvas")
        refresh_widget_style(self.qr_label)
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        if self.original_pixmap.isNull():
            return
        size = self.zoom_slider.value()
        scaled = self.original_pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.qr_label.setPixmap(scaled)
        self.qr_label.setText("")

    def copy_uri(self) -> None:
        if not self.current_entry or not self.current_entry.uri or self.current_entry.is_locked:
            QMessageBox.information(self, "Locked", "Unlock ProxyVault to copy this URI.")
            return
        QGuiApplication.clipboard().setText(self.current_entry.uri)

    def copy_qr(self) -> None:
        if self.original_pixmap.isNull():
            return
        copy_pixmap_to_clipboard(self.original_pixmap)

    def _emit_save(self) -> None:
        if not self.current_entry:
            return
        expiry = self.expiry_edit.text().strip()
        if expiry and len(expiry.split("-")) != 3:
            self.validation_label.setText("Expiry date must use YYYY-MM-DD.")
            self.validation_label.setVisible(True)
            self.expiry_edit.setProperty("invalid", True)
            refresh_widget_style(self.expiry_edit)
            return
        self.expiry_edit.setProperty("invalid", False)
        refresh_widget_style(self.expiry_edit)
        self.validation_label.clear()
        self.validation_label.setVisible(False)
        self.saveRequested.emit(
            {
                "id": self.current_entry.id,
                "name": self.name_edit.text().strip(),
                "tags": self.tags_edit.text().strip(),
                "notes": self.notes_edit.toPlainText().strip(),
                "expiry_date": expiry,
                "is_favorite": self.favorite_check.isChecked(),
            }
        )

    def _emit_delete(self) -> None:
        if self.current_entry:
            self.deleteRequested.emit(self.current_entry.id)

    def _emit_save_qr(self) -> None:
        if self.current_entry:
            self.saveQrRequested.emit(self.current_entry.id)

    def _emit_reachability(self) -> None:
        if self.current_entry:
            self.reachabilityRequested.emit(self.current_entry.id)

    def _toggle_reachability_details(self, checked: bool) -> None:
        self.reachability_toggle_button.setText("Hide details" if checked else "Show details")
        self.reachability_details_frame.setVisible(checked)

    def _set_reachability_view(self, entry: ProxyEntry | None, history: list[ReachabilityCheck]) -> None:
        if not entry:
            self.reachability_status_pill.setText("Not tested")
            set_widget_status(self.reachability_status_pill, "statusTone", "muted")
            self.reachability_checked_hint.setText("No TCP probe yet")
            self.reachability_summary.setText("Select an entry to inspect per-entry reachability.")
            self.check_now_button.setText("Run TCP probe")
            self.reachability_last_value.setText("Never checked")
            self.reachability_freshness_value.setText("No result")
            self.reachability_endpoint_value.setText("n/a")
            self.reachability_method_value.setText("TCP probe")
            self.reachability_latency_value.setText("n/a")
            self.reachability_reason_value.setText("No diagnostics yet")
            self.reachability_log.setPlainText("No diagnostics available.")
            self.reachability_history_table.setRowCount(0)
            self.reachability_toggle_button.setChecked(False)
            self.reachability_toggle_button.setEnabled(False)
            self.reachability_toggle_button.setText("Show details")
            self.reachability_details_frame.setVisible(False)
            return

        self.reachability_status_pill.setText(entry.reachability_status_label)
        set_widget_status(self.reachability_status_pill, "statusTone", entry.reachability_tone)
        self.reachability_checked_hint.setText(entry.reachability_last_checked_label)
        self.reachability_summary.setText(entry.reachability_detail_summary)
        self.check_now_button.setText("Check again" if entry.reachability_has_result else "Run TCP probe")
        self.reachability_last_value.setText(entry.reachability_last_checked_label)
        self.reachability_freshness_value.setText(entry.reachability_freshness_label)
        self.reachability_endpoint_value.setText(entry.reachability_endpoint or entry.display_host_port)
        self.reachability_method_value.setText(entry.reachability_method or "TCP probe")
        latency_value = entry.reachability_latency_ms or entry.reachability_duration_ms
        self.reachability_latency_value.setText(format_duration_ms(latency_value))
        if not entry.reachability_has_result:
            reason_text = "No probe has been run yet"
        elif entry.reachability_is_config_changed:
            reason_text = "Configuration changed after the last TCP probe"
        elif entry.reachability_is_stale and entry.reachability_failure_reason:
            reason_text = entry.reachability_failure_reason
        elif entry.reachability_status_label == "Failed":
            reason_text = entry.reachability_failure_reason or "The TCP connection could not be established."
        else:
            reason_text = entry.reachability_failure_reason or "Probe succeeded"
        self.reachability_reason_value.setText(reason_text)
        details_text = entry.reachability_details or entry.reachability_detail_summary
        self.reachability_log.setPlainText(details_text)

        self.reachability_history_table.setRowCount(len(history))
        for row_index, probe in enumerate(history):
            when_text = probe.checked_at_obj.strftime("%Y-%m-%d %H:%M") if probe.checked_at_obj else probe.checked_at
            if probe.status == ReachabilityState.REACHABLE and probe.latency_ms is not None:
                result_text = format_duration_ms(probe.latency_ms)
            elif probe.failure_reason:
                result_text = probe.failure_reason
            else:
                result_text = "No detail"
            values = [when_text, probe.status_label, probe.method, result_text]
            for column_index, value in enumerate(values):
                self.reachability_history_table.setItem(row_index, column_index, QTableWidgetItem(value))

        details_enabled = entry.reachability_has_result or bool(history)
        self.reachability_toggle_button.setEnabled(details_enabled)
        if details_enabled and entry.reachability_tone in {"danger", "warning"}:
            self.reachability_toggle_button.setChecked(True)
        if not details_enabled:
            self.reachability_toggle_button.setChecked(False)
        self.reachability_toggle_button.setText("Hide details" if self.reachability_toggle_button.isChecked() else "Show details")
        self.reachability_details_frame.setVisible(self.reachability_toggle_button.isChecked() and details_enabled)
