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
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import (
    build_reachability_copy,
    format_duration_ms,
    format_proxy_type,
    format_relative_time,
    tr,
)
from app.models import ProxyEntry, QROptions, ReachabilityCheck, ReachabilityState, parse_iso_datetime
from app.parser import ParseError, parse_proxy_text
from app.qr_gen import copy_pixmap_to_clipboard, qr_pixmap
from app.runtime.models import RunningSession, RuntimeHumanStatus, RuntimeSnapshot
from app.ui.i18n_patch import (
    ensure_ui_translations,
    local_address_text,
    present_runtime_state,
    route_owner_text,
    runtime_error_action,
    runtime_error_display,
    runtime_error_summary,
    runtime_technical_detail,
    runtime_engine_label,
    runtime_supports_entry_type,
    system_proxy_status_text,
    tooltip_text,
)
from app.ui.theme import apply_button_icon, make_form_label, refresh_widget_style, set_widget_status


class DetailPanel(QWidget):
    saveRequested = pyqtSignal(dict)
    deleteRequested = pyqtSignal(str)
    saveQrRequested = pyqtSignal(str)
    reachabilityRequested = pyqtSignal(str)
    connectRequested = pyqtSignal(str)
    disconnectRequested = pyqtSignal(str)
    makePrimaryRequested = pyqtSignal(str)
    openRuntimeLogRequested = pyqtSignal(str)
    copyLocalAddressRequested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        ensure_ui_translations()
        self.current_entry: ProxyEntry | None = None
        self.current_options = QROptions()
        self.current_history: list[ReachabilityCheck] = []
        self.runtime_session: RunningSession | None = None
        self.runtime_snapshot: RuntimeSnapshot | None = None
        self.runtime_human_status: RuntimeHumanStatus | None = None
        self.runtime_failure_reason = ""
        self.client_mode_enabled = True
        self.original_pixmap = QPixmap()
        self.setObjectName("detailPanel")
        self._build_ui()
        self.clear_panel()

    def _build_ui(self) -> None:
        self.setMinimumWidth(0)
        self.setMaximumWidth(560)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(self.scroll)

        self.content = QWidget()
        self.content.setMinimumWidth(340)
        self.scroll.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.header_card = QFrame()
        self.header_card.setObjectName("detailHeaderCard")
        header_layout = QVBoxLayout(self.header_card)
        header_layout.setContentsMargins(12, 12, 12, 12)
        header_layout.setSpacing(8)
        self.title_label = QLabel("")
        self.title_label.setProperty("role", "windowTitle")
        self.title_label.setObjectName("detailHeaderTitle")
        header_layout.addWidget(self.title_label)

        self.entry_context = QLabel("")
        self.entry_context.setObjectName("detailHeaderBody")
        self.entry_context.setProperty("role", "muted")
        self.entry_context.setWordWrap(True)
        header_layout.addWidget(self.entry_context)

        header_pills = QHBoxLayout()
        header_pills.setSpacing(6)
        self.entry_type_pill = QLabel("")
        self.entry_type_pill.setObjectName("detailHeaderPill")
        self.entry_endpoint_pill = QLabel("")
        self.entry_endpoint_pill.setObjectName("detailHeaderPill")
        self.entry_transport_pill = QLabel("")
        self.entry_transport_pill.setObjectName("detailHeaderPill")
        header_pills.addWidget(self.entry_type_pill, 0, Qt.AlignmentFlag.AlignLeft)
        header_pills.addWidget(self.entry_endpoint_pill, 0, Qt.AlignmentFlag.AlignLeft)
        header_pills.addWidget(self.entry_transport_pill, 0, Qt.AlignmentFlag.AlignLeft)
        header_pills.addStretch(1)
        header_layout.addLayout(header_pills)
        layout.addWidget(self.header_card)

        self.form_group = QFrame()
        self.form_group.setObjectName("formGroup")
        form_group_layout = QVBoxLayout(self.form_group)
        form_group_layout.setContentsMargins(12, 12, 12, 12)
        form_group_layout.setSpacing(10)

        self.form_title = QLabel("")
        self.form_title.setProperty("role", "subSectionTitle")
        form_group_layout.addWidget(self.form_title)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.name_edit = QLineEdit()
        self.tags_edit = QLineEdit()
        self.expiry_edit = QLineEdit()
        self.expiry_edit.setObjectName("expiryField")
        self.favorite_check = QCheckBox("")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setObjectName("notesEdit")
        self.notes_edit.setMaximumHeight(96)
        self.validation_label = QLabel("")
        self.validation_label.setObjectName("inlineValidation")
        self.validation_label.setVisible(False)

        form.addRow(make_form_label(""), self.name_edit)
        form.addRow(make_form_label(""), self.tags_edit)
        form.addRow(make_form_label(""), self.expiry_edit)
        form.addRow(make_form_label(""), self.favorite_check)
        form.addRow(make_form_label(""), self.notes_edit)
        form_group_layout.addLayout(form)
        self.metadata_labels = {
            "name": form.itemAt(0, QFormLayout.ItemRole.LabelRole).widget(),
            "tags": form.itemAt(1, QFormLayout.ItemRole.LabelRole).widget(),
            "expiry": form.itemAt(2, QFormLayout.ItemRole.LabelRole).widget(),
            "notes": form.itemAt(4, QFormLayout.ItemRole.LabelRole).widget(),
        }
        form_group_layout.addWidget(self.validation_label)
        layout.addWidget(self.form_group)

        self.runtime_block = QFrame()
        self.runtime_block.setObjectName("detailGroup")
        runtime_layout = QVBoxLayout(self.runtime_block)
        runtime_layout.setContentsMargins(12, 12, 12, 12)
        runtime_layout.setSpacing(10)

        self.runtime_title = QLabel("")
        self.runtime_title.setProperty("role", "subSectionTitle")
        runtime_layout.addWidget(self.runtime_title)

        runtime_summary_row = QHBoxLayout()
        runtime_summary_row.setSpacing(8)
        self.runtime_status_pill = QLabel("")
        self.runtime_status_pill.setObjectName("statusPill")
        runtime_summary_row.addWidget(self.runtime_status_pill, 0, Qt.AlignmentFlag.AlignLeft)
        self.runtime_status_hint = QLabel("")
        self.runtime_status_hint.setObjectName("reachabilityMeta")
        runtime_summary_row.addWidget(self.runtime_status_hint, 1)
        runtime_layout.addLayout(runtime_summary_row)

        runtime_highlights_row = QHBoxLayout()
        runtime_highlights_row.setSpacing(8)
        self.runtime_highlight_labels: dict[str, QLabel] = {}
        self.runtime_highlight_values: dict[str, QLabel] = {}
        for key in ("engine", "current_route", "local_address"):
            card = QFrame()
            card.setObjectName("runtimeMetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 10, 10, 10)
            card_layout.setSpacing(4)
            label = QLabel("")
            label.setObjectName("runtimeMetricLabel")
            value = QLabel("")
            value.setObjectName("runtimeMetricValue")
            value.setWordWrap(True)
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            self.runtime_highlight_labels[key] = label
            self.runtime_highlight_values[key] = value
            runtime_highlights_row.addWidget(card, 1)
        runtime_layout.addLayout(runtime_highlights_row)

        self.runtime_summary_frame = QFrame()
        self.runtime_summary_frame.setObjectName("runtimeSummaryCard")
        runtime_summary_box = QVBoxLayout(self.runtime_summary_frame)
        runtime_summary_box.setContentsMargins(10, 10, 10, 10)
        runtime_summary_box.setSpacing(6)
        self.runtime_summary_title = QLabel("")
        self.runtime_summary_title.setProperty("role", "subSectionTitle")
        self.runtime_summary_body = QLabel("")
        self.runtime_summary_body.setWordWrap(True)
        self.runtime_summary_action_title = QLabel("")
        self.runtime_summary_action_title.setProperty("role", "caption")
        self.runtime_summary_action_body = QLabel("")
        self.runtime_summary_action_body.setWordWrap(True)
        self.runtime_summary_action_body.setProperty("role", "muted")
        runtime_summary_box.addWidget(self.runtime_summary_title)
        runtime_summary_box.addWidget(self.runtime_summary_body)
        runtime_summary_box.addWidget(self.runtime_summary_action_title)
        runtime_summary_box.addWidget(self.runtime_summary_action_body)
        runtime_layout.addWidget(self.runtime_summary_frame)

        self.runtime_meta_grid = QFormLayout()
        self.runtime_meta_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_meta_grid.setHorizontalSpacing(10)
        self.runtime_meta_grid.setVerticalSpacing(8)
        self.runtime_meta_grid.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.runtime_labels: dict[str, QLabel] = {}
        self.runtime_values: dict[str, QLabel] = {}
        runtime_fields = [
            ("engine", 100),
            ("runtime_state", 100),
            ("current_route", 100),
            ("system_proxy_state", 100),
            ("http_port", 100),
            ("socks_port", 100),
            ("local_address", 100),
            ("started_at", 100),
            ("last_activity", 100),
            ("last_handshake", 100),
            ("last_error", 100),
        ]
        for key, min_width in runtime_fields:
            label = make_form_label("", min_width=min_width)
            value = QLabel("")
            value.setObjectName("reachabilityValue")
            value.setWordWrap(True)
            self.runtime_labels[key] = label
            self.runtime_values[key] = value
            self.runtime_meta_grid.addRow(label, value)
        runtime_layout.addLayout(self.runtime_meta_grid)

        self.runtime_log_title = QLabel("")
        self.runtime_log_title.setProperty("role", "caption")
        runtime_layout.addWidget(self.runtime_log_title)
        self.runtime_log = QPlainTextEdit()
        self.runtime_log.setObjectName("runtimeLog")
        self.runtime_log.setReadOnly(True)
        self.runtime_log.setMaximumHeight(118)
        runtime_layout.addWidget(self.runtime_log)

        runtime_buttons_top = QHBoxLayout()
        runtime_buttons_top.setSpacing(8)
        self.connect_button = QPushButton("")
        self.connect_button.setProperty("variant", "primary")
        self.connect_button.clicked.connect(self._emit_connect)
        apply_button_icon(self.connect_button, "reachability", color="#3A2B1C")
        self.disconnect_button = QPushButton("")
        self.disconnect_button.setProperty("variant", "subtle")
        self.disconnect_button.clicked.connect(self._emit_disconnect)
        apply_button_icon(self.disconnect_button, "reset", color="#D8943C")
        self.make_primary_button = QPushButton("")
        self.make_primary_button.setProperty("variant", "secondary")
        self.make_primary_button.clicked.connect(self._emit_make_primary)
        apply_button_icon(self.make_primary_button, "favorite", color="#D8943C")
        runtime_buttons_top.addWidget(self.connect_button)
        runtime_buttons_top.addWidget(self.disconnect_button)
        runtime_buttons_top.addWidget(self.make_primary_button)
        runtime_layout.addLayout(runtime_buttons_top)

        runtime_buttons_bottom = QHBoxLayout()
        runtime_buttons_bottom.setSpacing(8)
        self.open_log_button = QPushButton("")
        self.open_log_button.setProperty("variant", "subtle")
        self.open_log_button.clicked.connect(self._emit_open_runtime_log)
        apply_button_icon(self.open_log_button, "details", color="#D8943C")
        self.copy_local_address_button = QPushButton("")
        self.copy_local_address_button.setProperty("variant", "subtle")
        self.copy_local_address_button.clicked.connect(self._emit_copy_local_address)
        apply_button_icon(self.copy_local_address_button, "copy", color="#D8943C")
        runtime_buttons_bottom.addWidget(self.open_log_button)
        runtime_buttons_bottom.addWidget(self.copy_local_address_button)
        runtime_layout.addLayout(runtime_buttons_bottom)

        layout.addWidget(self.runtime_block)

        self.reachability_block = QFrame()
        self.reachability_block.setObjectName("detailGroup")
        reachability_layout = QVBoxLayout(self.reachability_block)
        reachability_layout.setContentsMargins(12, 12, 12, 12)
        reachability_layout.setSpacing(10)

        reachability_header = QHBoxLayout()
        reachability_header.setSpacing(8)
        self.reachability_title = QLabel("")
        self.reachability_title.setProperty("role", "subSectionTitle")
        reachability_header.addWidget(self.reachability_title)
        reachability_header.addStretch(1)
        self.reachability_toggle_button = QPushButton("")
        self.reachability_toggle_button.setProperty("variant", "subtle")
        self.reachability_toggle_button.setCheckable(True)
        self.reachability_toggle_button.clicked.connect(self._toggle_reachability_details)
        apply_button_icon(self.reachability_toggle_button, "details", color="#D8943C")
        reachability_header.addWidget(self.reachability_toggle_button)
        reachability_layout.addLayout(reachability_header)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(8)
        self.reachability_status_pill = QLabel("")
        self.reachability_status_pill.setObjectName("statusPill")
        summary_row.addWidget(self.reachability_status_pill, 0, Qt.AlignmentFlag.AlignLeft)
        self.reachability_checked_hint = QLabel("")
        self.reachability_checked_hint.setObjectName("reachabilityMeta")
        summary_row.addWidget(self.reachability_checked_hint, 1)
        self.check_now_button = QPushButton("")
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

        self.reachability_meta_labels = {
            "last_checked": make_form_label("", min_width=88),
            "freshness": make_form_label("", min_width=88),
            "endpoint": make_form_label("", min_width=88),
            "method": make_form_label("", min_width=88),
            "latency": make_form_label("", min_width=88),
            "reason": make_form_label("", min_width=88),
        }
        self.reachability_meta_grid.addRow(self.reachability_meta_labels["last_checked"], self.reachability_last_value)
        self.reachability_meta_grid.addRow(self.reachability_meta_labels["freshness"], self.reachability_freshness_value)
        self.reachability_meta_grid.addRow(self.reachability_meta_labels["endpoint"], self.reachability_endpoint_value)
        self.reachability_meta_grid.addRow(self.reachability_meta_labels["method"], self.reachability_method_value)
        self.reachability_meta_grid.addRow(self.reachability_meta_labels["latency"], self.reachability_latency_value)
        self.reachability_meta_grid.addRow(self.reachability_meta_labels["reason"], self.reachability_reason_value)
        reachability_layout.addLayout(self.reachability_meta_grid)

        self.reachability_details_frame = QFrame()
        self.reachability_details_frame.setObjectName("reachabilityDetails")
        reachability_details_layout = QVBoxLayout(self.reachability_details_frame)
        reachability_details_layout.setContentsMargins(10, 10, 10, 10)
        reachability_details_layout.setSpacing(8)

        self.diagnostics_title = QLabel("")
        self.diagnostics_title.setProperty("role", "caption")
        reachability_details_layout.addWidget(self.diagnostics_title)
        self.reachability_log = QPlainTextEdit()
        self.reachability_log.setObjectName("reachabilityLog")
        self.reachability_log.setReadOnly(True)
        self.reachability_log.setMaximumHeight(98)
        reachability_details_layout.addWidget(self.reachability_log)

        self.recent_probes_title = QLabel("")
        self.recent_probes_title.setProperty("role", "caption")
        reachability_details_layout.addWidget(self.recent_probes_title)
        self.reachability_history_table = QTableWidget(0, 4)
        self.reachability_history_table.setObjectName("reachabilityHistoryTable")
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
        self.qr_title = QLabel("")
        self.qr_title.setProperty("role", "subSectionTitle")
        qr_layout.addWidget(self.qr_title)
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
        self.table_title = QLabel("")
        self.table_title.setProperty("role", "subSectionTitle")
        table_layout.addWidget(self.table_title)

        self.params_table = QTableWidget(0, 2)
        self.params_table.setObjectName("parsedTable")
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
        self.action_title = QLabel("")
        self.action_title.setProperty("role", "subSectionTitle")
        action_layout.addWidget(self.action_title)

        utility_row = QHBoxLayout()
        self.copy_uri_button = QPushButton("")
        self.copy_uri_button.setProperty("variant", "subtle")
        self.copy_uri_button.clicked.connect(self.copy_uri)
        apply_button_icon(self.copy_uri_button, "copy", color="#D8943C")
        self.copy_qr_button = QPushButton("")
        self.copy_qr_button.setProperty("variant", "subtle")
        self.copy_qr_button.clicked.connect(self.copy_qr)
        apply_button_icon(self.copy_qr_button, "qr", color="#D8943C")
        utility_row.addWidget(self.copy_uri_button)
        utility_row.addWidget(self.copy_qr_button)
        action_layout.addLayout(utility_row)

        export_row = QHBoxLayout()
        self.save_qr_button = QPushButton("")
        self.save_qr_button.setProperty("variant", "subtle")
        self.save_qr_button.clicked.connect(self._emit_save_qr)
        apply_button_icon(self.save_qr_button, "save", color="#D8943C")
        export_row.addWidget(self.save_qr_button)
        export_row.addStretch(1)
        action_layout.addLayout(export_row)

        commit_row = QHBoxLayout()
        self.save_button = QPushButton("")
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self._emit_save)
        apply_button_icon(self.save_button, "save", color="#3A2B1C")
        self.delete_button = QPushButton("")
        self.delete_button.setProperty("variant", "destructive")
        self.delete_button.clicked.connect(self._emit_delete)
        apply_button_icon(self.delete_button, "delete", color="#C77768")
        commit_row.addWidget(self.save_button)
        commit_row.addWidget(self.delete_button)
        action_layout.addLayout(commit_row)
        layout.addWidget(action_group)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        ensure_ui_translations()
        self.form_title.setText(tr("section.metadata"))
        self.metadata_labels["name"].setText(tr("common.field.name"))
        self.metadata_labels["tags"].setText(tr("common.field.tags"))
        self.metadata_labels["expiry"].setText(tr("common.field.expiry"))
        self.metadata_labels["notes"].setText(tr("common.field.notes"))
        self.expiry_edit.setPlaceholderText(tr("dialog.add_entry.placeholder.expiry"))
        self.favorite_check.setText(tr("sidebar.filters.favorites_only"))
        self.notes_edit.setPlaceholderText(tr("dialog.add_entry.placeholder.notes"))

        self.runtime_title.setText(tr("section.connection"))
        self.runtime_summary_action_title.setText(tr("detail.runtime.next_step.title"))
        self.runtime_log_title.setText(tr("section.technical_log"))
        self.runtime_status_pill.setToolTip(tooltip_text("runtime.status.hint"))
        self.runtime_status_hint.setToolTip(tooltip_text("runtime.status.hint"))
        self.runtime_summary_frame.setToolTip(tooltip_text("runtime.human_summary.tooltip"))
        self.runtime_summary_title.setToolTip(tooltip_text("runtime.human_summary.tooltip"))
        self.runtime_summary_body.setToolTip(tooltip_text("runtime.human_summary.tooltip"))
        self.runtime_summary_action_body.setToolTip(tooltip_text("runtime.human_summary.tooltip"))
        self.runtime_log_title.setToolTip(tooltip_text("runtime.technical_log.tooltip"))
        self.runtime_log.setToolTip(tooltip_text("runtime.technical_log.tooltip"))
        highlight_label_keys = {
            "engine": "common.field.engine",
            "current_route": "common.field.current_route",
            "local_address": "common.field.local_address",
        }
        for key, label in self.runtime_highlight_labels.items():
            label.setText(tr(highlight_label_keys[key]))
        runtime_label_keys = {
            "engine": "common.field.engine",
            "runtime_state": "common.field.runtime_state",
            "current_route": "common.field.current_route",
            "system_proxy_state": "common.field.system_proxy_state",
            "http_port": "common.field.http_port",
            "socks_port": "common.field.socks_port",
            "local_address": "common.field.local_address",
            "started_at": "common.field.started_at",
            "last_activity": "common.field.last_activity",
            "last_handshake": "common.field.last_handshake",
            "last_error": "common.field.last_error",
        }
        for key, label in self.runtime_labels.items():
            label.setText(tr(runtime_label_keys[key]))

        self.connect_button.setText(tr("action.connect"))
        self.connect_button.setToolTip(tooltip_text("action.connect.tooltip"))
        self.disconnect_button.setText(tr("action.disconnect"))
        self.disconnect_button.setToolTip(tooltip_text("action.disconnect.tooltip"))
        self.make_primary_button.setText(tr("action.make_primary"))
        self.make_primary_button.setToolTip(tooltip_text("action.make_primary.tooltip"))
        self.open_log_button.setText(tr("action.open_full_log"))
        self.copy_local_address_button.setText(tr("action.copy_local_address"))

        self.reachability_title.setText(tr("section.connection_diagnostics"))
        self.reachability_title.setToolTip(tooltip_text("reachability.tooltip"))
        self.reachability_status_pill.setToolTip(tooltip_text("reachability.tooltip"))
        self.reachability_checked_hint.setToolTip(tooltip_text("reachability.tooltip"))
        self.reachability_toggle_button.setText(
            tr("action.hide_details") if self.reachability_toggle_button.isChecked() else tr("action.show_details")
        )
        self.check_now_button.setText(tr("action.run_tcp_probe"))
        self.diagnostics_title.setText(tr("section.diagnostics"))
        self.recent_probes_title.setText(tr("section.recent_probes"))
        self.reachability_history_table.setHorizontalHeaderLabels(
            [
                tr("common.field.last_checked"),
                tr("common.field.history_state"),
                tr("common.field.method"),
                tr("common.field.result"),
            ]
        )
        self.reachability_meta_labels["last_checked"].setText(tr("common.field.last_checked"))
        self.reachability_meta_labels["freshness"].setText(tr("common.field.freshness"))
        self.reachability_meta_labels["endpoint"].setText(tr("common.field.endpoint"))
        self.reachability_meta_labels["method"].setText(tr("common.field.method"))
        self.reachability_meta_labels["latency"].setText(tr("common.field.latency"))
        self.reachability_meta_labels["reason"].setText(tr("common.field.reason"))

        self.qr_title.setText(tr("section.qr_preview"))
        self.table_title.setText(tr("section.parsed_parameters"))
        self.params_table.setHorizontalHeaderLabels([tr("common.field.name"), tr("common.field.result")])
        self.action_title.setText(tr("section.actions"))
        self.copy_uri_button.setText(tr("action.copy_uri"))
        self.copy_qr_button.setText(tr("action.copy_qr"))
        self.save_qr_button.setText(tr("action.save_qr_png"))
        self.save_button.setText(tr("action.save_changes"))
        self.delete_button.setText(tr("action.delete_entry"))

        if self.current_entry is None:
            self.clear_panel()
            return
        self._refresh_context_text()
        self._set_reachability_view(self.current_entry, self.current_history)
        self._set_runtime_view()

    def clear_panel(self) -> None:
        self.current_entry = None
        self.current_history = []
        self.runtime_session = None
        self.runtime_snapshot = None
        self.runtime_human_status = None
        self.runtime_failure_reason = ""
        self.original_pixmap = QPixmap()
        self.name_edit.clear()
        self.tags_edit.clear()
        self.expiry_edit.clear()
        self.notes_edit.clear()
        self.favorite_check.setChecked(False)
        self.qr_label.setObjectName("qrCanvas")
        refresh_widget_style(self.qr_label)
        self.qr_label.setText(tr("detail.clear.select_entry"))
        self.qr_label.setPixmap(QPixmap())
        self._refresh_context_text()
        self._set_runtime_view()
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
            self.connect_button,
            self.disconnect_button,
            self.make_primary_button,
            self.open_log_button,
            self.copy_local_address_button,
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
            self.open_log_button,
        ]:
            widget.setEnabled(True)
        self.copy_uri_button.setEnabled(bool(entry.uri) and not entry.is_locked)
        self.name_edit.setText(entry.name)
        self.tags_edit.setText(entry.tags)
        self.expiry_edit.setText(entry.expiry_date)
        self.notes_edit.setPlainText(entry.notes)
        self.favorite_check.setChecked(entry.is_favorite)
        self.validation_label.clear()
        self.validation_label.setVisible(False)
        self.expiry_edit.setProperty("invalid", False)
        refresh_widget_style(self.expiry_edit)
        self._refresh_context_text()
        self._populate_params(entry)
        self._load_preview(entry)
        self._set_reachability_view(entry, self.current_history)
        self._set_runtime_view()

    def set_runtime_context(
        self,
        *,
        session: RunningSession | None,
        snapshot: RuntimeSnapshot | None,
        human_status: RuntimeHumanStatus | None,
        failure_reason: str = "",
        client_mode_enabled: bool = True,
    ) -> None:
        self.runtime_session = session
        self.runtime_snapshot = snapshot
        self.runtime_human_status = human_status
        self.runtime_failure_reason = failure_reason
        self.client_mode_enabled = client_mode_enabled
        self._set_runtime_view()

    def _refresh_context_text(self) -> None:
        if self.current_entry is None:
            self.title_label.setText(tr("detail.clear.title"))
            self.entry_context.setText(tr("detail.clear.context"))
            for pill in (self.entry_type_pill, self.entry_endpoint_pill, self.entry_transport_pill):
                pill.clear()
                pill.setVisible(False)
            return
        self.title_label.setText(self.current_entry.name or self.current_entry.display_host_port or tr("detail.clear.title"))
        self.entry_context.setText(
            tr(
                "detail.context.entry",
                type_label=format_proxy_type(self.current_entry.type),
                endpoint=self.current_entry.display_host_port,
                transport=self.current_entry.transport or tr("detail.context.transport_unknown"),
            )
        )
        self.entry_type_pill.setText(format_proxy_type(self.current_entry.type))
        self.entry_endpoint_pill.setText(self.current_entry.display_host_port or tr("common.not_available"))
        self.entry_endpoint_pill.setToolTip(self.current_entry.display_host_port)
        self.entry_transport_pill.setText(self.current_entry.transport or tr("detail.context.transport_unknown"))
        for pill in (self.entry_type_pill, self.entry_endpoint_pill, self.entry_transport_pill):
            pill.setVisible(True)

    def _populate_params(self, entry: ProxyEntry) -> None:
        rows: list[tuple[str, str]] = [
            (tr("common.field.type"), format_proxy_type(entry.type)),
            (tr("common.field.transport"), entry.transport or tr("common.not_available")),
            (tr("common.field.server_host"), entry.server_host or tr("common.not_available")),
            (tr("common.field.server_port"), str(entry.server_port or "")),
        ]
        if entry.uri and not entry.is_locked:
            try:
                parsed = parse_proxy_text(entry.uri)
                for key, value in parsed.params.items():
                    rows.append((key, value))
            except ParseError:
                rows.append((tr("common.field.result"), tr("detail.param.warning_unparsed")))
        elif entry.is_locked:
            rows.append((tr("common.field.runtime_state"), tr("detail.param.status_unlock")))
        self.params_table.setRowCount(len(rows))
        for row_index, (key, value) in enumerate(rows):
            self.params_table.setItem(row_index, 0, QTableWidgetItem(key))
            self.params_table.setItem(row_index, 1, QTableWidgetItem(value))

    def _load_preview(self, entry: ProxyEntry) -> None:
        self.original_pixmap = QPixmap()
        if entry.uri and not entry.is_locked:
            self.original_pixmap = qr_pixmap(entry.uri, self.current_options, max_size=720)
        elif not entry.is_locked and entry.qr_png_path and Path(entry.qr_png_path).exists():
            self.original_pixmap = QPixmap(entry.qr_png_path)
        if self.original_pixmap.isNull():
            self.qr_label.setObjectName("emptyQrState")
            refresh_widget_style(self.qr_label)
            self.qr_label.setText(tr("detail.qr.unavailable"))
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

    def _set_runtime_view(self) -> None:
        entry = self.current_entry
        unsupported = bool(entry and not runtime_supports_entry_type(entry.type))
        runtime_copy = present_runtime_state(
            session=self.runtime_session,
            snapshot=self.runtime_snapshot,
            human_status=self.runtime_human_status,
            failure_reason=self.runtime_failure_reason,
            client_mode_enabled=self.client_mode_enabled,
            unsupported=unsupported,
        )
        self.runtime_status_pill.setText(runtime_copy.status_label)
        set_widget_status(self.runtime_status_pill, "statusTone", runtime_copy.tone)
        self.runtime_status_hint.setText(runtime_copy.hint)
        self.runtime_summary_title.setText(runtime_copy.title)
        self.runtime_summary_body.setText(runtime_copy.summary)
        self.runtime_summary_action_body.setText(runtime_copy.action)

        session = self.runtime_session
        self.runtime_values["engine"].setText(runtime_engine_label(getattr(session, "engine_kind", None)))
        self.runtime_values["runtime_state"].setText(runtime_copy.status_label)
        self.runtime_values["current_route"].setText(route_owner_text(session, self.runtime_snapshot))
        self.runtime_values["system_proxy_state"].setText(system_proxy_status_text(self.runtime_snapshot))
        self.runtime_values["http_port"].setText(str(session.http_port) if session and session.http_port else tr("common.not_available"))
        self.runtime_values["socks_port"].setText(str(session.socks_port) if session and session.socks_port else tr("common.not_available"))
        self.runtime_values["local_address"].setText(local_address_text(session))
        self.runtime_values["started_at"].setText(self._format_absolute_time(session.started_at if session else ""))
        self.runtime_values["last_activity"].setText(self._format_relative_label(session.last_activity_at if session else ""))
        self.runtime_values["last_handshake"].setText(self._format_relative_label(session.last_handshake_at if session else ""))
        self.runtime_highlight_values["engine"].setText(runtime_engine_label(getattr(session, "engine_kind", None)))
        self.runtime_highlight_values["current_route"].setText(route_owner_text(session, self.runtime_snapshot))
        self.runtime_highlight_values["local_address"].setText(local_address_text(session))
        failure_reason = self.runtime_failure_reason or (session.failure_reason if session else "")
        technical_error = session.last_error if session else ""
        human_error_text = runtime_error_display(failure_reason, technical_error)
        self.runtime_values["last_error"].setText(human_error_text or tr("common.value.none_long"))

        technical_log = runtime_technical_detail(
            failure_reason,
            technical_error,
            session.log_excerpt if session else "",
        ) or tr("detail.runtime.log_placeholder")
        self.runtime_log.setPlainText(technical_log)

        if failure_reason or technical_error:
            self.runtime_summary_title.setText(runtime_error_display(failure_reason, technical_error))
            self.runtime_summary_body.setText(runtime_error_summary(failure_reason, technical_error))
            self.runtime_summary_action_body.setText(runtime_error_action(failure_reason, technical_error))

        has_entry = entry is not None
        can_connect = has_entry and self.client_mode_enabled and not unsupported and (
            session is None or session.runtime_state.value in {"DISCONNECTED", "ERROR"}
        )
        can_disconnect = bool(session and session.runtime_state.value in {"STARTING", "RUNNING", "STOPPING"})
        can_make_primary = bool(
            session and not unsupported and session.runtime_state.value == "RUNNING" and not session.is_primary
        )
        can_copy_local = bool(session and (session.local_http_url or session.local_socks_url))

        self.connect_button.setEnabled(can_connect)
        self.disconnect_button.setEnabled(can_disconnect)
        self.make_primary_button.setEnabled(can_make_primary)
        self.open_log_button.setEnabled(has_entry)
        self.copy_local_address_button.setEnabled(can_copy_local)

        if not has_entry:
            for button in [
                self.connect_button,
                self.disconnect_button,
                self.make_primary_button,
                self.open_log_button,
                self.copy_local_address_button,
            ]:
                button.setEnabled(False)

    def _format_absolute_time(self, value: str) -> str:
        dt = parse_iso_datetime(value)
        if dt is None:
            return tr("common.not_available")
        return dt.strftime("%Y-%m-%d %H:%M")

    def _format_relative_label(self, value: str) -> str:
        dt = parse_iso_datetime(value)
        if dt is None:
            return tr("common.not_available")
        return format_relative_time(dt)

    def copy_uri(self) -> None:
        if not self.current_entry or not self.current_entry.uri or self.current_entry.is_locked:
            QMessageBox.information(self, tr("dialog.locked.title"), tr("detail.copy_uri.locked"))
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
            self.validation_label.setText(tr("detail.validation.expiry_format"))
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

    def _emit_connect(self) -> None:
        if self.current_entry:
            self.connectRequested.emit(self.current_entry.id)

    def _emit_disconnect(self) -> None:
        if self.current_entry:
            self.disconnectRequested.emit(self.current_entry.id)

    def _emit_make_primary(self) -> None:
        if self.current_entry:
            self.makePrimaryRequested.emit(self.current_entry.id)

    def _emit_open_runtime_log(self) -> None:
        if self.current_entry:
            self.openRuntimeLogRequested.emit(self.current_entry.id)

    def _emit_copy_local_address(self) -> None:
        if self.current_entry:
            self.copyLocalAddressRequested.emit(self.current_entry.id)

    def _toggle_reachability_details(self, checked: bool) -> None:
        self.reachability_toggle_button.setText(tr("action.hide_details") if checked else tr("action.show_details"))
        self.reachability_details_frame.setVisible(checked)

    def _set_reachability_view(self, entry: ProxyEntry | None, history: list[ReachabilityCheck]) -> None:
        if not entry:
            self.reachability_status_pill.setText(tr("reachability.state.not_tested"))
            set_widget_status(self.reachability_status_pill, "statusTone", "muted")
            self.reachability_checked_hint.setText(tr("reachability.hint.none"))
            self.reachability_summary.setText(tr("reachability.summary.none"))
            self.check_now_button.setText(tr("action.refresh_diagnostics"))
            self.reachability_last_value.setText(tr("reachability.last_checked.never"))
            self.reachability_freshness_value.setText(tr("reachability.freshness.no_result"))
            self.reachability_endpoint_value.setText(tr("common.not_available"))
            self.reachability_method_value.setText(tr("common.not_available"))
            self.reachability_latency_value.setText(tr("common.not_available"))
            self.reachability_reason_value.setText(tr("reachability.reason.none"))
            self.reachability_log.setPlainText(tr("reachability.details.none"))
            self.reachability_history_table.setRowCount(0)
            self.reachability_toggle_button.setChecked(False)
            self.reachability_toggle_button.setEnabled(False)
            self.reachability_toggle_button.setText(tr("action.show_details"))
            self.reachability_details_frame.setVisible(False)
            return

        reachability_copy = build_reachability_copy(entry)
        self.reachability_status_pill.setText(reachability_copy.status_label)
        set_widget_status(self.reachability_status_pill, "statusTone", entry.reachability_tone)
        self.reachability_checked_hint.setText(reachability_copy.last_checked_label)
        self.reachability_summary.setText(reachability_copy.detail_summary)
        self.check_now_button.setText(
            tr("action.check_again")
            if entry.reachability_has_result
            else (tr("action.run_config_check") if not entry.reachability_supports_tcp_probe else tr("action.run_tcp_probe"))
        )
        self.reachability_last_value.setText(reachability_copy.last_checked_label)
        self.reachability_freshness_value.setText(reachability_copy.freshness_label)
        self.reachability_endpoint_value.setText(entry.reachability_endpoint or entry.display_host_port)
        self.reachability_method_value.setText(
            entry.reachability_method
            or (tr("reachability.method.protocol_note") if not entry.reachability_supports_tcp_probe else tr("reachability.method.tcp_probe"))
        )
        latency_value = None
        if entry.reachability_supports_tcp_probe or entry.reachability_status != ReachabilityState.NOT_APPLICABLE:
            latency_value = entry.reachability_latency_ms or entry.reachability_duration_ms
        self.reachability_latency_value.setText(format_duration_ms(latency_value))
        self.reachability_reason_value.setText(reachability_copy.reason_text)
        details_text = entry.reachability_details or (
            tr(
                "reachability.details.not_applicable",
                name=entry.name,
                endpoint=entry.reachability_endpoint or entry.display_host_port,
                transport=entry.transport or tr("common.not_available"),
            )
            if not entry.reachability_supports_tcp_probe and entry.reachability_status == ReachabilityState.NOT_APPLICABLE
            else reachability_copy.detail_summary
        ) or tr("reachability.details.none")
        self.reachability_log.setPlainText(details_text)

        visible_history = (
            [
                probe
                for probe in history
                if probe.status == ReachabilityState.NOT_APPLICABLE
                or str(probe.method or "").strip().lower() not in {"tcp probe", "tcp-проверка"}
            ]
            if not entry.reachability_supports_tcp_probe
            else history
        )
        self.reachability_history_table.setRowCount(len(visible_history))
        for row_index, probe in enumerate(visible_history):
            when_text = probe.checked_at_obj.strftime("%Y-%m-%d %H:%M") if probe.checked_at_obj else probe.checked_at
            if probe.status == ReachabilityState.REACHABLE and probe.latency_ms is not None:
                result_text = format_duration_ms(probe.latency_ms)
            elif probe.failure_reason:
                result_text = probe.failure_reason
            else:
                result_text = tr("reachability.reason.no_detail")
            status_label = {
                ReachabilityState.REACHABLE: tr("reachability.state.reachable"),
                ReachabilityState.NOT_APPLICABLE: tr("reachability.state.not_applicable"),
            }.get(probe.status, tr("reachability.state.failed"))
            default_method = (
                tr("reachability.method.protocol_note")
                if probe.status == ReachabilityState.NOT_APPLICABLE
                else tr("reachability.method.tcp_probe")
            )
            values = [when_text, status_label, probe.method or default_method, result_text]
            for column_index, value in enumerate(values):
                self.reachability_history_table.setItem(row_index, column_index, QTableWidgetItem(value))

        details_enabled = entry.reachability_display_state == "not_applicable" or entry.reachability_has_result or bool(visible_history)
        self.reachability_toggle_button.setEnabled(details_enabled)
        if details_enabled and entry.reachability_tone in {"danger", "warning"}:
            self.reachability_toggle_button.setChecked(True)
        if not details_enabled:
            self.reachability_toggle_button.setChecked(False)
        self.reachability_toggle_button.setText(
            tr("action.hide_details") if self.reachability_toggle_button.isChecked() else tr("action.show_details")
        )
        self.reachability_details_frame.setVisible(self.reachability_toggle_button.isChecked() and details_enabled)
