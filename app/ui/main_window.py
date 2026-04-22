from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QThreadPool, QTimer
from PyQt6.QtGui import QAction, QKeyEvent, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStyleFactory,
    QTextEdit,
    QToolBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.db import AuthenticationError, DatabaseManager
from app.i18n import (
    SupportedLocale,
    build_reachability_copy,
    describe_human_error,
    format_duration_ms,
    format_ui_error,
    format_proxy_type,
    set_locale,
    tr,
)
from app.models import (
    ProxyEntry,
    ProxyType,
    ReachabilityCheck,
    ReachabilityState,
    SubscriptionImportItem,
    SubscriptionRecord,
    utc_now_iso,
)
from app.parser import ParseError, is_wireguard_block, parse_proxy_text, parse_subscription_payload
from app.qr_gen import (
    export_booklet_pdf,
    export_clash_yaml,
    export_entry_pdf,
    export_zip,
    qr_pixmap,
    save_qr_assets,
)
from app.runtime.manager import RuntimeManager
from app.runtime.models import RunningSession, RuntimeHumanStatus, RuntimeSnapshot, SessionHistoryRecord
from app.runtime.reachability import run_entry_diagnostic
from app.subscriptions import SubscriptionSecurityError, fetch_subscription_url_payload
from app.ui.card_view import CardView
from app.ui.detail_panel import DetailPanel
from app.ui.dialogs import (
    AddEntryDialog,
    FullScreenQrDialog,
    HelpDialog,
    ImportSubscriptionDialog,
    PasswordDialog,
    RuntimeLogDialog,
    SessionHistoryDialog,
    WelcomeDialog,
)
from app.ui.i18n_patch import ensure_ui_translations, present_runtime_state
from app.ui.i18n_patch import tooltip_text, ui_error_message
from app.ui.icons import icon
from app.ui.settings import SettingsDialog
from app.ui.sidebar import Sidebar
from app.ui.theme import apply_action_icon, apply_app_theme, set_widget_status
from app.ui.workers import FunctionWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        db: DatabaseManager,
        runtime_manager: RuntimeManager | None = None,
        *,
        auto_show_welcome: bool = True,
    ):
        super().__init__()
        ensure_ui_translations()
        self.db = db
        self.settings = self.db.load_settings()
        set_locale(self.settings.ui_language)
        ensure_ui_translations()
        self.runtime_manager = runtime_manager or RuntimeManager(self.db)
        self.entries: list[ProxyEntry] = []
        self.filtered_entries: list[ProxyEntry] = []
        self.last_deleted_entries: list[ProxyEntry] = []
        self.current_entry: ProxyEntry | None = None
        self.runtime_snapshot = RuntimeSnapshot()
        self.runtime_sessions_by_entry_id: dict[str, RunningSession] = {}
        self.runtime_sessions_by_id: dict[str, RunningSession] = {}
        self.runtime_human_status_by_session_id: dict[str, RuntimeHumanStatus] = {}
        self.runtime_human_status_by_entry_id: dict[str, RuntimeHumanStatus] = {}
        self.runtime_failures_by_entry_id: dict[str, str] = {}
        self._thread_pool = QThreadPool.globalInstance()
        self._active_workers: list[FunctionWorker] = []
        self._worker_contexts: dict[int, dict[str, Any]] = {}
        self._active_reachability_ids: set[str] = set()
        self._batch_reachability_active = False
        self._subscription_refresh_worker: FunctionWorker | None = None
        self._runtime_poll_timer = QTimer(self)
        self._runtime_poll_timer.setInterval(2500)
        self._runtime_poll_timer.timeout.connect(self._poll_runtime)
        self._did_shutdown = False
        self._auto_show_welcome = auto_show_welcome

        self.setObjectName("mainWindow")
        self.resize(1540, 960)
        self.setAcceptDrops(True)

        self.sidebar = Sidebar()
        self.card_view = CardView()
        self.detail_panel = DetailPanel()

        self._build_layout()
        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_status_bar()
        self._connect_signals()
        self.retranslate_ui()

        self.apply_theme(self.settings.theme)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self.refresh_library()
        self.auto_refresh_subscriptions()
        self._runtime_poll_timer.start()
        self._handle_runtime_snapshot_changed(self.runtime_manager.snapshot())
        if getattr(self.runtime_manager, "_adapters", []):
            self.runtime_manager.restore_sessions_on_launch()
        if self._auto_show_welcome:
            self.show_welcome_if_needed()

    def _start_worker(self, worker: FunctionWorker, context: dict[str, Any] | None = None) -> None:
        self._active_workers.append(worker)
        self._worker_contexts[id(worker.signals)] = {"worker": worker, **(context or {})}
        self._thread_pool.start(worker)

    def _release_worker(self, worker: FunctionWorker) -> None:
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def _take_worker_context(self) -> dict[str, Any]:
        sender = self.sender()
        if sender is None:
            return {}
        context = self._worker_contexts.pop(id(sender), {})
        worker = context.pop("worker", None)
        if isinstance(worker, FunctionWorker):
            self._release_worker(worker)
        return context

    def _build_layout(self) -> None:
        splitter = QSplitter()
        splitter.setObjectName("workspaceSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.card_view)
        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([220, 760, 520])

        canvas = QWidget()
        canvas.setObjectName("workspaceCanvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(12, 10, 12, 12)
        canvas_layout.setSpacing(12)

        self.workspace_header = QWidget()
        self.workspace_header.setObjectName("workspaceHero")
        workspace_header_layout = QHBoxLayout(self.workspace_header)
        workspace_header_layout.setContentsMargins(18, 16, 18, 16)
        workspace_header_layout.setSpacing(16)

        workspace_copy = QVBoxLayout()
        workspace_copy.setSpacing(4)
        self.workspace_eyebrow = QLabel("")
        self.workspace_eyebrow.setObjectName("workspaceEyebrow")
        self.workspace_eyebrow.setVisible(False)
        self.workspace_title_label = QLabel("")
        self.workspace_title_label.setObjectName("workspaceTitle")
        self.workspace_subtitle_label = QLabel("")
        self.workspace_subtitle_label.setObjectName("workspaceSubtitle")
        self.workspace_subtitle_label.setWordWrap(True)
        self.workspace_subtitle_label.setVisible(False)
        workspace_copy.addWidget(self.workspace_eyebrow)
        workspace_copy.addWidget(self.workspace_title_label)
        workspace_copy.addWidget(self.workspace_subtitle_label)
        workspace_header_layout.addLayout(workspace_copy, 1)

        workspace_pills = QVBoxLayout()
        workspace_pills.setSpacing(8)
        workspace_pills.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.workspace_scope_pill = QLabel("")
        self.workspace_scope_pill.setObjectName("workspaceHeroPill")
        self.workspace_selection_pill = QLabel("")
        self.workspace_selection_pill.setObjectName("workspaceHeroPill")
        self.workspace_mode_pill = QLabel("")
        self.workspace_mode_pill.setObjectName("workspaceHeroPill")
        workspace_pills.addWidget(self.workspace_scope_pill, 0, Qt.AlignmentFlag.AlignRight)
        workspace_pills.addWidget(self.workspace_selection_pill, 0, Qt.AlignmentFlag.AlignRight)
        workspace_pills.addWidget(self.workspace_mode_pill, 0, Qt.AlignmentFlag.AlignRight)
        workspace_header_layout.addLayout(workspace_pills)

        canvas_layout.addWidget(self.workspace_header)
        canvas_layout.addWidget(splitter)
        self.setCentralWidget(canvas)

    def _build_actions(self) -> None:
        self.add_action = QAction(self)
        self.add_action.setShortcut(QKeySequence.StandardKey.New)
        self.add_action.triggered.connect(self.open_add_dialog)

        self.import_uri_action = QAction(self)
        self.import_uri_action.triggered.connect(self.open_add_dialog)

        self.import_subscription_action = QAction(self)
        self.import_subscription_action.triggered.connect(self.import_subscription)

        self.export_png_action = QAction(self)
        self.export_png_action.triggered.connect(lambda: self.export_single("png"))

        self.export_svg_action = QAction(self)
        self.export_svg_action.triggered.connect(lambda: self.export_single("svg"))

        self.export_pdf_action = QAction(self)
        self.export_pdf_action.triggered.connect(lambda: self.export_single("pdf"))

        self.export_zip_action = QAction(self)
        self.export_zip_action.setShortcut("Ctrl+E")
        self.export_zip_action.triggered.connect(self.export_selection_zip)

        self.export_booklet_action = QAction(self)
        self.export_booklet_action.triggered.connect(self.export_booklet)

        self.export_clash_action = QAction(self)
        self.export_clash_action.triggered.connect(self.export_clash)

        self.regenerate_action = QAction(self)
        self.regenerate_action.triggered.connect(self.regenerate_all)

        self.check_current_action = QAction(self)
        self.check_current_action.triggered.connect(self.check_current_entry_reachability)

        self.check_filtered_action = QAction(self)
        self.check_filtered_action.triggered.connect(self.check_filtered_entries)

        self.connect_action = QAction(self)
        self.connect_action.triggered.connect(self.connect_selected_entry)

        self.disconnect_action = QAction(self)
        self.disconnect_action.triggered.connect(self.disconnect_selected_entry)

        self.make_primary_action = QAction(self)
        self.make_primary_action.triggered.connect(self.make_selected_primary)

        self.stop_all_action = QAction(self)
        self.stop_all_action.triggered.connect(self.stop_all_runtime_sessions)

        self.logs_action = QAction(self)
        self.logs_action.triggered.connect(self.show_runtime_log_dialog)

        self.sessions_action = QAction(self)
        self.sessions_action.triggered.connect(self.show_session_history_dialog)

        self.help_center_action = QAction(self)
        self.help_center_action.triggered.connect(self.show_help_dialog)

        self.delete_action = QAction(self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(self.delete_selected)

        self.undo_delete_action = QAction(self)
        self.undo_delete_action.triggered.connect(self.undo_last_delete)
        self.undo_delete_action.setEnabled(False)

        self.settings_action = QAction(self)
        self.settings_action.triggered.connect(self.open_settings)

        self.grid_view_action = QAction(self)
        self.grid_view_action.triggered.connect(lambda: self.set_view_mode("grid"))

        self.list_view_action = QAction(self)
        self.list_view_action.triggered.connect(lambda: self.set_view_mode("list"))

        self.toggle_details_action = QAction(self)
        self.toggle_details_action.triggered.connect(self.toggle_details_panel)

        self.lock_action = QAction(self)
        self.lock_action.triggered.connect(self.toggle_lock_state)

        self.theme_toggle_action = QAction(self)
        self.theme_toggle_action.triggered.connect(self.toggle_theme)

        self.quick_start_action = QAction(self)
        self.quick_start_action.triggered.connect(self.show_welcome_dialog)

        self.about_action = QAction(self)
        self.about_action.triggered.connect(self.show_about)

        self.focus_search_action = QAction(self)
        self.focus_search_action.setShortcut(QKeySequence.StandardKey.Find)
        self.focus_search_action.triggered.connect(lambda: self.search_edit.setFocus())
        self.addAction(self.focus_search_action)

        self._action_icon_specs = {
            self.add_action: ("add", "#3A2B1C"),
            self.import_uri_action: ("import", "#D8943C"),
            self.import_subscription_action: ("import", "#D8943C"),
            self.export_png_action: ("save", "#D8943C"),
            self.export_svg_action: ("save", "#D8943C"),
            self.export_pdf_action: ("save", "#D8943C"),
            self.export_zip_action: ("export", "#D8943C"),
            self.export_booklet_action: ("export", "#D8943C"),
            self.export_clash_action: ("export", "#D8943C"),
            self.regenerate_action: ("qr", "#D8943C"),
            self.check_current_action: ("reachability", "#7EA67B"),
            self.check_filtered_action: ("reachability", "#7EA67B"),
            self.connect_action: ("reachability", "#3A2B1C"),
            self.disconnect_action: ("reset", "#D8943C"),
            self.make_primary_action: ("favorite", "#D8943C"),
            self.stop_all_action: ("reset", "#C77768"),
            self.logs_action: ("details", "#D8943C"),
            self.sessions_action: ("list", "#D8943C"),
            self.help_center_action: ("info", "#D8943C"),
            self.delete_action: ("delete", "#C77768"),
            self.undo_delete_action: ("reset", "#D8943C"),
            self.settings_action: ("settings", "#D8943C"),
            self.grid_view_action: ("grid", "#9A8A7A"),
            self.list_view_action: ("list", "#9A8A7A"),
            self.toggle_details_action: ("details", "#9A8A7A"),
            self.theme_toggle_action: ("theme", "#D3A247"),
            self.quick_start_action: ("add", "#D8943C"),
            self.about_action: ("info", "#D8943C"),
        }
        self._apply_action_icons()

        for action in [self.add_action, self.delete_action, self.export_zip_action]:
            self.addAction(action)

    def _build_menu(self) -> None:
        self.file_menu = self.menuBar().addMenu("")
        self.file_menu.addAction(self.import_uri_action)
        self.file_menu.addAction(self.import_subscription_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.export_png_action)
        self.file_menu.addAction(self.export_svg_action)
        self.file_menu.addAction(self.export_pdf_action)
        self.file_menu.addAction(self.export_zip_action)
        self.file_menu.addAction(self.export_booklet_action)
        self.file_menu.addAction(self.export_clash_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.regenerate_action)

        self.edit_menu = self.menuBar().addMenu("")
        self.edit_menu.addAction(self.add_action)
        self.edit_menu.addAction(self.undo_delete_action)
        self.edit_menu.addAction(self.delete_action)

        self.view_menu = self.menuBar().addMenu("")
        self.view_menu.addAction(self.grid_view_action)
        self.view_menu.addAction(self.list_view_action)
        self.view_menu.addAction(self.toggle_details_action)
        self.view_menu.addAction(self.theme_toggle_action)

        self.tools_menu = self.menuBar().addMenu("")
        self.tools_menu.addAction(self.connect_action)
        self.tools_menu.addAction(self.disconnect_action)
        self.tools_menu.addAction(self.make_primary_action)
        self.tools_menu.addAction(self.stop_all_action)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.logs_action)
        self.tools_menu.addAction(self.sessions_action)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.check_current_action)
        self.tools_menu.addAction(self.check_filtered_action)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.regenerate_action)

        self.settings_menu = self.menuBar().addMenu("")
        self.settings_menu.addAction(self.settings_action)

        self.help_menu = self.menuBar().addMenu("")
        self.help_menu.addAction(self.quick_start_action)
        self.help_menu.addAction(self.help_center_action)
        self.help_menu.addSeparator()
        self.help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar(self)
        self.toolbar.setObjectName("mainToolbar")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.apply_filters)
        self.search_edit.setMinimumWidth(340)

        self.sort_combo = QComboBox()
        self.sort_combo.currentIndexChanged.connect(self.apply_filters)
        self.sort_combo.setMinimumWidth(148)

        self.view_toggle = QComboBox()
        self.view_toggle.currentIndexChanged.connect(self._handle_view_combo_changed)
        self.view_toggle.setMinimumWidth(108)

        self.toolbar.addWidget(self.search_edit)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.add_action)
        self.toolbar.addAction(self.import_subscription_action)
        self.toolbar.addAction(self.connect_action)
        self.toolbar.addAction(self.disconnect_action)
        self.toolbar.addAction(self.make_primary_action)
        self.toolbar.addAction(self.stop_all_action)

        self.export_button = self.toolbar.addAction("")
        self.export_button.triggered.connect(self.export_selection_zip)
        apply_action_icon(self.export_button, "export", color="#D8943C")

        self.logs_toolbar_action = self.toolbar.addAction("")
        self.logs_toolbar_action.triggered.connect(self.show_runtime_log_dialog)
        apply_action_icon(self.logs_toolbar_action, "details", color="#D8943C")

        self.sessions_toolbar_action = self.toolbar.addAction("")
        self.sessions_toolbar_action.triggered.connect(self.show_session_history_dialog)
        apply_action_icon(self.sessions_toolbar_action, "list", color="#D8943C")

        self.help_toolbar_action = self.toolbar.addAction("")
        self.help_toolbar_action.triggered.connect(self.show_help_dialog)
        apply_action_icon(self.help_toolbar_action, "info", color="#D8943C")

        self.toolbar.addAction(self.lock_action)
        self.toolbar.addAction(self.theme_toggle_action)
        self.toolbar.addWidget(self.sort_combo)
        self.toolbar.addWidget(self.view_toggle)

        self._set_toolbar_button_variant(self.toolbar, self.add_action, "primary")
        self._set_toolbar_button_variant(self.toolbar, self.import_subscription_action, "secondary")
        self._set_toolbar_button_variant(self.toolbar, self.connect_action, "secondary")
        self._set_toolbar_button_variant(self.toolbar, self.disconnect_action, "subtle")
        self._set_toolbar_button_variant(self.toolbar, self.make_primary_action, "subtle")
        self._set_toolbar_button_variant(self.toolbar, self.stop_all_action, "subtle")
        self._set_toolbar_button_variant(self.toolbar, self.export_button, "secondary")
        self._set_toolbar_button_variant(self.toolbar, self.logs_toolbar_action, "subtle")
        self._set_toolbar_button_variant(self.toolbar, self.sessions_toolbar_action, "subtle")
        self._set_toolbar_button_variant(self.toolbar, self.help_toolbar_action, "subtle")
        self._set_toolbar_button_variant(self.toolbar, self.lock_action, "subtle")
        self._set_toolbar_button_variant(self.toolbar, self.theme_toggle_action, "subtle")

    def _build_status_bar(self) -> None:
        self.statusBar().setSizeGripEnabled(False)
        self.entry_count_label = QLabel("")
        self.entry_count_label.setObjectName("statusPill")
        self.last_import_label = QLabel("")
        self.last_import_label.setObjectName("statusPill")
        self.lock_status_label = QLabel("")
        self.lock_status_label.setObjectName("statusPill")
        self.runtime_status_label = QLabel("")
        self.runtime_status_label.setObjectName("statusPill")
        self.statusBar().addPermanentWidget(self.entry_count_label)
        self.statusBar().addPermanentWidget(self.last_import_label)
        self.statusBar().addPermanentWidget(self.runtime_status_label)
        self.statusBar().addPermanentWidget(self.lock_status_label)

    def _connect_signals(self) -> None:
        self.sidebar.filtersChanged.connect(self.apply_filters)
        self.card_view.entrySelected.connect(self.show_entry)
        self.card_view.entryActivated.connect(self.show_fullscreen_qr)
        self.detail_panel.saveRequested.connect(self.save_detail_changes)
        self.detail_panel.deleteRequested.connect(lambda _: self.delete_selected())
        self.detail_panel.saveQrRequested.connect(self.save_current_qr)
        self.detail_panel.reachabilityRequested.connect(self.check_entry_reachability)
        self.detail_panel.connectRequested.connect(self.start_runtime_for_entry)
        self.detail_panel.disconnectRequested.connect(self.stop_runtime_for_entry)
        self.detail_panel.makePrimaryRequested.connect(self.make_runtime_primary)
        self.detail_panel.openRuntimeLogRequested.connect(self.show_runtime_log_dialog)
        self.detail_panel.copyLocalAddressRequested.connect(self.copy_runtime_local_address)
        self.runtime_manager.snapshotChanged.connect(self._handle_runtime_snapshot_changed)
        self.runtime_manager.sessionUpdated.connect(self._handle_runtime_session_updated)
        self.runtime_manager.humanStatusUpdated.connect(self._handle_runtime_human_status)
        self.runtime_manager.operationFailed.connect(self._handle_runtime_operation_failed)

    def retranslate_ui(self) -> None:
        ensure_ui_translations()
        self.setWindowTitle(tr("app.title"))
        self.sidebar.retranslate_ui()
        self.card_view.retranslate_ui()
        self.detail_panel.retranslate_ui()
        self.file_menu.setTitle(tr("menu.file"))
        self.edit_menu.setTitle(tr("menu.edit"))
        self.view_menu.setTitle(tr("menu.view"))
        self.tools_menu.setTitle(tr("menu.tools"))
        self.settings_menu.setTitle(tr("menu.settings"))
        self.help_menu.setTitle(tr("menu.help"))

        self.add_action.setText(tr("action.add"))
        self.import_uri_action.setText(tr("action.import_uri"))
        self.import_subscription_action.setText(tr("action.import_subscription"))
        self.export_png_action.setText(tr("action.export_current_png"))
        self.export_svg_action.setText(tr("action.export_current_svg"))
        self.export_pdf_action.setText(tr("action.export_current_pdf"))
        self.export_zip_action.setText(tr("action.export_selection_zip"))
        self.export_booklet_action.setText(tr("action.export_pdf_booklet"))
        self.export_clash_action.setText(tr("action.export_clash_yaml"))
        self.regenerate_action.setText(tr("action.regenerate_all_qr"))
        self.check_current_action.setText(tr("action.check_selected_entry"))
        self.check_filtered_action.setText(tr("action.check_filtered_entries"))
        self.connect_action.setText(tr("action.connect_selected"))
        self.connect_action.setToolTip(tooltip_text("action.connect.tooltip"))
        self.disconnect_action.setText(tr("action.disconnect_selected"))
        self.disconnect_action.setToolTip(tooltip_text("action.disconnect.tooltip"))
        self.make_primary_action.setText(tr("action.make_selected_primary"))
        self.make_primary_action.setToolTip(tooltip_text("action.make_primary.tooltip"))
        self.stop_all_action.setText(tr("action.stop_all_connections"))
        self.logs_action.setText(tr("action.logs"))
        self.sessions_action.setText(tr("action.sessions"))
        self.help_center_action.setText(tr("action.help_center"))
        self.delete_action.setText(tr("action.delete_selected"))
        self.undo_delete_action.setText(tr("action.undo_last_delete"))
        self.settings_action.setText(tr("action.settings"))
        self.grid_view_action.setText(tr("action.grid_view"))
        self.list_view_action.setText(tr("action.list_view"))
        self.toggle_details_action.setText(tr("action.toggle_details_panel"))
        self.theme_toggle_action.setText(tr("action.toggle_theme"))
        self.quick_start_action.setText(tr("action.quick_start"))
        self.about_action.setText(tr("action.about"))
        self.focus_search_action.setText(tr("action.focus_search"))
        self.search_edit.setPlaceholderText(tr("toolbar.search.placeholder"))
        self.toolbar.setWindowTitle(tr("toolbar.main"))
        self.export_button.setText(tr("toolbar.export.button"))
        self.logs_toolbar_action.setText(tr("main.runtime.logs_button"))
        self.sessions_toolbar_action.setText(tr("main.runtime.sessions_button"))
        self.help_toolbar_action.setText(tr("main.runtime.help_button"))
        self.workspace_eyebrow.setText(tr("main.hero.eyebrow"))
        self.workspace_title_label.setText(tr("main.hero.title"))
        self.workspace_subtitle_label.setText(tr("main.hero.subtitle"))
        self._populate_sort_combo(self.sort_combo.currentData() or "created")
        self._populate_view_combo(self.view_toggle.currentData() or self.card_view.mode)
        self.update_status_bar()
        self._refresh_current_entry_detail()

    def _populate_sort_combo(self, selected: str) -> None:
        options = [
            ("name", tr("toolbar.sort.name")),
            ("created", tr("toolbar.sort.created_date")),
            ("type", tr("toolbar.sort.type")),
            ("expiry", tr("toolbar.sort.expiry_date")),
        ]
        self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        for value, label in options:
            self.sort_combo.addItem(label, value)
        index = max(self.sort_combo.findData(selected), 0)
        self.sort_combo.setCurrentIndex(index)
        self.sort_combo.blockSignals(False)

    def _populate_view_combo(self, selected: str) -> None:
        options = [
            ("grid", tr("toolbar.view.grid")),
            ("list", tr("toolbar.view.list")),
        ]
        self.view_toggle.blockSignals(True)
        self.view_toggle.clear()
        for value, label in options:
            self.view_toggle.addItem(label, value)
        index = max(self.view_toggle.findData(selected), 0)
        self.view_toggle.setCurrentIndex(index)
        self.view_toggle.blockSignals(False)

    def _handle_view_combo_changed(self) -> None:
        self.set_view_mode(str(self.view_toggle.currentData() or "grid"))

    def refresh_library(self, select_id: str = "") -> None:
        self.entries = self.db.list_entries(include_uri=False)
        tags = sorted({tag for entry in self.entries for tag in entry.tag_list}, key=str.lower)
        self.sidebar.update_tags(tags)
        self.apply_filters(select_id=select_id)
        self.update_status_bar()

    def apply_filters(self, *_args, select_id: str = "") -> None:
        selected_types = self.sidebar.selected_types() or set(ProxyType)
        selected_tags = self.sidebar.selected_tags()
        favorite_only = self.sidebar.favorite_filter_enabled()
        query = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""

        entries: list[ProxyEntry] = []
        for entry in self.entries:
            if entry.type not in selected_types:
                continue
            if favorite_only and not entry.is_favorite:
                continue
            if selected_tags and not (selected_tags & set(entry.tag_list)):
                continue
            haystack = " ".join(
                [
                    entry.name,
                    entry.server_host,
                    entry.tags,
                    entry.notes,
                    entry.transport,
                    format_proxy_type(entry.type),
                ]
            ).lower()
            if query and query not in haystack:
                continue
            entries.append(entry)

        self.filtered_entries = self.sort_entries(entries)
        selected_ids = [select_id] if select_id else self.card_view.selected_ids()
        self.card_view.set_entries(self.filtered_entries, selected_ids=selected_ids)
        current_id = self.card_view.current_id() or select_id
        if current_id and any(entry.id == current_id for entry in self.filtered_entries):
            self.card_view.select_entry(current_id)
            self.show_entry(current_id)
        elif self.filtered_entries:
            first_id = self.filtered_entries[0].id
            self.card_view.select_entry(first_id)
            self.show_entry(first_id)
        else:
            self.current_entry = None
            self.detail_panel.clear_panel()
        self._push_runtime_context_to_cards()
        self.update_status_bar()

    def sort_entries(self, entries: list[ProxyEntry]) -> list[ProxyEntry]:
        mode = str(self.sort_combo.currentData() or "created") if hasattr(self, "sort_combo") else "created"
        if mode == "name":
            return sorted(entries, key=lambda entry: entry.name.lower())
        if mode == "type":
            return sorted(entries, key=lambda entry: (entry.type.value, entry.name.lower()))
        if mode == "expiry":
            return sorted(
                entries,
                key=lambda entry: (entry.expiry_date == "", entry.expiry_date or "9999-12-31", entry.name.lower()),
            )
        return sorted(entries, key=lambda entry: entry.created_at or "", reverse=True)

    def show_entry(self, entry_id: str) -> None:
        entry = self.db.get_entry(entry_id, include_uri=not self.db.is_locked)
        if not entry:
            self.current_entry = None
            self.detail_panel.clear_panel()
            return
        self.current_entry = entry
        history = self.db.list_reachability_checks(entry.id, limit=5)
        self.detail_panel.set_entry(entry, self.settings.default_qr, history)
        self._refresh_current_entry_detail()
        self.update_status_bar()

    def _refresh_current_entry_detail(self) -> None:
        if self.current_entry is None:
            self.detail_panel.set_runtime_context(
                session=None,
                snapshot=self.runtime_snapshot,
                human_status=None,
                failure_reason="",
                client_mode_enabled=self.settings.client_mode_enabled,
            )
            return
        session = self.runtime_sessions_by_entry_id.get(self.current_entry.id)
        human_status = None
        if session is not None:
            human_status = self.runtime_human_status_by_session_id.get(session.session_id)
        failure_reason = self.runtime_failures_by_entry_id.get(self.current_entry.id, "")
        self.detail_panel.set_runtime_context(
            session=session,
            snapshot=self.runtime_snapshot,
            human_status=human_status,
            failure_reason=failure_reason,
            client_mode_enabled=self.settings.client_mode_enabled,
        )

    def _push_runtime_context_to_cards(self) -> None:
        human_by_entry: dict[str, RuntimeHumanStatus] = {}
        for entry_id, session in self.runtime_sessions_by_entry_id.items():
            status = self.runtime_human_status_by_session_id.get(session.session_id)
            if status is not None:
                human_by_entry[entry_id] = status
        self.card_view.set_runtime_context(
            sessions_by_entry_id=self.runtime_sessions_by_entry_id,
            human_status_by_entry_id=human_by_entry,
            failures_by_entry_id=self.runtime_failures_by_entry_id,
            client_mode_enabled=self.settings.client_mode_enabled,
        )

    def open_add_dialog(self, _checked: bool = False, prefill_text: str = "") -> None:
        if not self.ensure_unlocked(tr("main.search.reason.add_import")):
            return
        dialog = AddEntryDialog(self.settings.default_qr, prefill_text=prefill_text, parent=self)
        if dialog.exec():
            self.save_new_entry(dialog.payload)

    def save_new_entry(self, payload: dict) -> None:
        try:
            entry = self.db.upsert_parsed_entry(
                name=payload["name"],
                uri=payload["uri"],
                tags=payload["tags"],
                notes=payload["notes"],
                expiry_date=payload["expiry_date"],
                is_favorite=payload["is_favorite"],
            )
            png_path, _svg_path = save_qr_assets(entry, payload["qr_options"], self.settings.output_folder)
            entry.qr_png_path = png_path
            self.db.save_entry(entry)
            self.db.set_metadata("last_import_date", utc_now_iso())
            self.refresh_library(select_id=entry.id)
            self.show_toast(tr("toast.saved_entry", name=entry.name))
        except (AuthenticationError, ParseError, OSError) as exc:
            QMessageBox.warning(self, tr("action.add"), format_ui_error("ui.error.add_entry_failed", detail=exc))

    def import_subscription(self) -> None:
        if not self.ensure_unlocked(tr("main.search.reason.import_subscription")):
            return
        dialog = ImportSubscriptionDialog(
            self.settings.subscription_refresh_interval,
            allow_insecure_http=self.settings.allow_insecure_subscription_http,
            parent=self,
        )
        if dialog.exec():
            count = self.import_items(dialog.selected_items())
            if dialog.url:
                self.db.save_subscription(dialog.url, dialog.refresh_interval)
            self.db.set_metadata("last_import_date", utc_now_iso())
            self.show_toast(tr("toast.imported_subscription", count=count))

    def import_items(self, items: list[SubscriptionImportItem]) -> int:
        imported = 0
        last_id = ""
        for item in items:
            entry = self.db.upsert_parsed_entry(name=item.name, uri=item.uri)
            png_path, _ = save_qr_assets(entry, self.settings.default_qr, self.settings.output_folder)
            entry.qr_png_path = png_path
            self.db.save_entry(entry)
            imported += 1
            last_id = entry.id
        self.db.set_metadata("last_import_date", utc_now_iso())
        self.refresh_library(select_id=last_id)
        return imported

    def check_current_entry_reachability(self) -> None:
        if not self.current_entry:
            QMessageBox.information(self, tr("section.tcp_reachability"), tr("dialog.runtime.no_current_entry.body"))
            return
        self.check_entry_reachability(self.current_entry.id)

    def check_entry_reachability(self, entry_id: str) -> None:
        if not entry_id:
            return
        if entry_id in self._active_reachability_ids:
            self.show_toast(tr("toast.reachability.entry_running"))
            return
        entry = self.db.get_entry(entry_id, include_uri=not self.db.is_locked)
        if not entry:
            return
        active_session = self.runtime_sessions_by_entry_id.get(entry_id)
        session_payload = RunningSession.from_dict(active_session.to_dict()) if active_session else None
        adapters = self.runtime_manager.adapters_snapshot()
        self._active_reachability_ids.add(entry_id)
        self.statusBar().showMessage(tr("status.reachability.running_single", name=entry.name))
        worker = FunctionWorker(self._probe_entry_task, entry, session_payload, adapters)
        worker.signals.finished.connect(self._handle_probe_entry_finished)
        worker.signals.error.connect(self._handle_probe_error)
        self._start_worker(worker, {"entry_ids": [entry_id], "kind": "probe_single"})

    def check_filtered_entries(self) -> None:
        if self._batch_reachability_active:
            self.show_toast(tr("toast.reachability.batch_running"))
            return
        visible_entries = list(self.filtered_entries)
        if not visible_entries:
            QMessageBox.information(self, tr("section.tcp_reachability"), tr("toast.reachability.no_filtered"))
            return
        entries: list[ProxyEntry] = []
        for visible_entry in visible_entries:
            if visible_entry.id in self._active_reachability_ids:
                continue
            loaded_entry = self.db.get_entry(visible_entry.id, include_uri=not self.db.is_locked)
            if loaded_entry is not None:
                entries.append(loaded_entry)
        if not entries:
            self.show_toast(tr("toast.reachability.visible_busy"))
            return
        self._batch_reachability_active = True
        active_ids = [entry.id for entry in entries]
        self._active_reachability_ids.update(active_ids)
        session_payloads = {
            entry_id: RunningSession.from_dict(session.to_dict())
            for entry_id, session in self.runtime_sessions_by_entry_id.items()
        }
        worker = FunctionWorker(
            self._probe_entries_task,
            entries,
            session_payloads,
            self.runtime_manager.adapters_snapshot(),
        )
        worker.signals.progress.connect(self._handle_batch_probe_progress)
        worker.signals.finished.connect(self._handle_batch_probe_finished)
        worker.signals.error.connect(self._handle_probe_error)
        self._start_worker(worker, {"entry_ids": active_ids, "kind": "probe_batch"})

    def _probe_entry_task(
        self,
        entry: ProxyEntry,
        active_session: RunningSession | None = None,
        adapters: tuple[Any, ...] = (),
        progress_callback=None,
    ) -> dict[str, Any]:
        _ = progress_callback
        return {
            "entry_id": entry.id,
            "entry_name": entry.name,
            "result": self._run_tcp_probe(entry, active_session=active_session, adapters=adapters),
        }

    def _probe_entries_task(
        self,
        entries: list[ProxyEntry],
        active_sessions_by_entry_id: dict[str, RunningSession] | None = None,
        adapters: tuple[Any, ...] = (),
        progress_callback=None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        total = len(entries)
        active_sessions_by_entry_id = active_sessions_by_entry_id or {}
        for index, entry in enumerate(entries, start=1):
            if progress_callback is not None:
                progress_callback.emit({"index": index, "total": total, "entry_name": entry.name})
            results.append(
                {
                    "entry_id": entry.id,
                    "entry_name": entry.name,
                    "result": self._run_tcp_probe(
                        entry,
                        active_session=active_sessions_by_entry_id.get(entry.id),
                        adapters=adapters,
                    ),
                }
            )
        return results

    def _handle_probe_entry_finished(self, payload: dict[str, Any]) -> None:
        context = self._take_worker_context()
        for entry_id in context.get("entry_ids", []):
            self._active_reachability_ids.discard(entry_id)
        entry_id = str(payload["entry_id"])
        entry_name = str(payload.get("entry_name", tr("common.select_entry")))
        result = payload["result"]
        if not isinstance(result, ReachabilityCheck):
            raise TypeError("Unexpected reachability result payload.")
        self.db.record_reachability_check(entry_id, result)
        self.refresh_library(select_id=entry_id)
        self.show_toast(tr("toast.reachability.entry_finished", name=entry_name, result=self._reachability_summary(result)))

    def _handle_batch_probe_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        index = int(payload.get("index", 0))
        total = int(payload.get("total", 0))
        entry_name = str(payload.get("entry_name", ""))
        self.statusBar().showMessage(tr("status.reachability.running_batch", index=index, total=total, name=entry_name))

    def _handle_batch_probe_finished(self, payloads: object) -> None:
        context = self._take_worker_context()
        for entry_id in context.get("entry_ids", []):
            self._active_reachability_ids.discard(entry_id)
        results = payloads if isinstance(payloads, list) else []
        reachable = 0
        failed = 0
        skipped = 0
        for payload in results:
            if not isinstance(payload, dict):
                continue
            entry_id = str(payload.get("entry_id", ""))
            result = payload.get("result")
            if not entry_id or not isinstance(result, ReachabilityCheck):
                continue
            self.db.record_reachability_check(entry_id, result)
            if result.status == ReachabilityState.REACHABLE:
                reachable += 1
            elif result.status == ReachabilityState.NOT_APPLICABLE:
                skipped += 1
            else:
                failed += 1
        self._batch_reachability_active = False
        current_id = self.current_entry.id if self.current_entry else ""
        self.refresh_library(select_id=current_id)
        total = reachable + failed + skipped
        toast_key = "toast.reachability.batch_finished_with_skipped" if skipped else "toast.reachability.batch_finished"
        self.show_toast(tr(toast_key, total=total, reachable=reachable, failed=failed, skipped=skipped))

    def _handle_probe_error(self, exc: object) -> None:
        context = self._take_worker_context()
        for entry_id in context.get("entry_ids", []):
            self._active_reachability_ids.discard(entry_id)
        if context.get("kind") == "probe_batch":
            self._batch_reachability_active = False
        self.show_toast(tr("toast.reachability.failed", error=exc), error=True)

    def _reachability_summary(self, result: ReachabilityCheck) -> str:
        if result.status == ReachabilityState.REACHABLE:
            if result.latency_ms is not None:
                return tr("toast.reachability.reachable_with_latency", latency=format_duration_ms(result.latency_ms))
            return result.failure_reason or tr("reachability.state.reachable")
        if result.status == ReachabilityState.NOT_APPLICABLE:
            return result.failure_reason or tr("reachability.reason.not_applicable")
        if result.failure_reason:
            return result.failure_reason
        return tr("reachability.state.failed")

    def _run_tcp_probe(
        self,
        entry: ProxyEntry,
        *,
        active_session: RunningSession | None = None,
        adapters: tuple[Any, ...] = (),
    ) -> ReachabilityCheck:
        session = active_session
        if session is None:
            current_session = self.runtime_sessions_by_entry_id.get(entry.id)
            if current_session is not None:
                session = RunningSession.from_dict(current_session.to_dict())
        return run_entry_diagnostic(
            entry,
            adapters=adapters or self.runtime_manager.adapters_snapshot(),
            active_session=session,
        )

    def start_runtime_for_entry(self, entry_id: str) -> None:
        if not self.settings.client_mode_enabled:
            self.show_toast(tr("dialog.runtime.client_mode_disabled.body"))
            return
        self.runtime_failures_by_entry_id.pop(entry_id, None)
        self.runtime_manager.start_entry(entry_id)

    def stop_runtime_for_entry(self, entry_id: str) -> None:
        self.runtime_manager.stop_entry(entry_id)

    def make_runtime_primary(self, entry_id: str) -> None:
        self.runtime_manager.make_primary(entry_id)

    def connect_selected_entry(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(self, tr("dialog.runtime.no_current_entry.title"), tr("dialog.runtime.no_current_entry.body"))
            return
        self.start_runtime_for_entry(entry.id)

    def disconnect_selected_entry(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self.stop_runtime_for_entry(entry.id)

    def make_selected_primary(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self.make_runtime_primary(entry.id)

    def stop_all_runtime_sessions(self) -> None:
        self.runtime_manager.stop_all()

    def _selected_entry(self) -> ProxyEntry | None:
        if self.current_entry is not None:
            return self.current_entry
        current_id = self.card_view.current_id()
        if not current_id:
            return None
        return self.db.get_entry(current_id, include_uri=not self.db.is_locked)

    def _poll_runtime(self) -> None:
        if not self.settings.client_mode_enabled:
            return
        self.runtime_manager.poll_sessions()

    def _handle_runtime_session_updated(self, _session_id: str, session: object) -> None:
        if not isinstance(session, RunningSession):
            return
        self.runtime_sessions_by_id[session.session_id] = session
        self.runtime_sessions_by_entry_id[session.entry_id] = session

    def _handle_runtime_human_status(self, session_id: str, status: object) -> None:
        if not isinstance(status, RuntimeHumanStatus):
            return
        self.runtime_human_status_by_session_id[session_id] = status
        if status.entry_id:
            self.runtime_human_status_by_entry_id[status.entry_id] = status
        self._refresh_current_entry_detail()
        self._push_runtime_context_to_cards()

    def _handle_runtime_snapshot_changed(self, snapshot: object) -> None:
        if not isinstance(snapshot, RuntimeSnapshot):
            return
        self.runtime_snapshot = snapshot
        self.runtime_sessions_by_id = {session.session_id: session for session in snapshot.sessions}
        self.runtime_sessions_by_entry_id = {session.entry_id: session for session in snapshot.sessions}
        self.runtime_human_status_by_entry_id = {}
        for session in snapshot.sessions:
            status = self.runtime_human_status_by_session_id.get(session.session_id)
            if status is not None:
                self.runtime_human_status_by_entry_id[session.entry_id] = status
        active_entry_ids = set(self.runtime_sessions_by_entry_id)
        self.runtime_failures_by_entry_id = {
            entry_id: reason
            for entry_id, reason in self.runtime_failures_by_entry_id.items()
            if entry_id not in active_entry_ids
        }
        self._push_runtime_context_to_cards()
        self._refresh_current_entry_detail()
        self._update_runtime_actions()
        self.update_status_bar()

    def _handle_runtime_operation_failed(self, entry_id: str, failure_reason: str) -> None:
        self.runtime_failures_by_entry_id[entry_id] = failure_reason
        self._push_runtime_context_to_cards()
        self._refresh_current_entry_detail()
        self._update_runtime_actions()
        runtime_copy = present_runtime_state(
            session=self.runtime_sessions_by_entry_id.get(entry_id),
            snapshot=self.runtime_snapshot,
            human_status=self.runtime_human_status_by_entry_id.get(entry_id),
            failure_reason=failure_reason,
            client_mode_enabled=self.settings.client_mode_enabled,
            unsupported=False,
        )
        self.show_toast(runtime_copy.summary, error=True)

    def _update_runtime_actions(self) -> None:
        entry = self._selected_entry()
        session = self.runtime_sessions_by_entry_id.get(entry.id) if entry else None
        unsupported = bool(entry and getattr(entry.type, "value", "") == "OTHER")
        can_connect = bool(
            entry
            and self.settings.client_mode_enabled
            and not unsupported
            and (session is None or session.runtime_state.value in {"DISCONNECTED", "ERROR"})
        )
        can_disconnect = bool(session and session.runtime_state.value in {"STARTING", "RUNNING", "STOPPING"})
        can_make_primary = bool(session and session.runtime_state.value == "RUNNING" and not session.is_primary)
        has_entry = entry is not None
        has_sessions = bool(self.runtime_snapshot.sessions)
        self.connect_action.setEnabled(can_connect)
        self.disconnect_action.setEnabled(can_disconnect)
        self.make_primary_action.setEnabled(can_make_primary)
        self.stop_all_action.setEnabled(has_sessions)
        self.logs_action.setEnabled(has_entry)
        self.sessions_action.setEnabled(has_entry)
        self.logs_toolbar_action.setEnabled(has_entry)
        self.sessions_toolbar_action.setEnabled(has_entry)

    def save_detail_changes(self, payload: dict) -> None:
        self.db.update_entry_metadata(
            payload["id"],
            name=payload["name"],
            tags=payload["tags"],
            notes=payload["notes"],
            expiry_date=payload["expiry_date"],
            is_favorite=payload["is_favorite"],
        )
        self.refresh_library(select_id=payload["id"])
        self.show_toast(tr("toast.saved_entry", name=payload["name"]))

    def delete_selected(self) -> None:
        selected_ids = self.card_view.selected_ids() or ([self.current_entry.id] if self.current_entry else [])
        if not selected_ids:
            return
        if self.db.is_locked:
            QMessageBox.information(self, tr("dialog.delete_locked.title"), tr("dialog.delete_locked.body"))
            return
        prompt = tr("dialog.delete.confirm_many") if len(selected_ids) > 1 else tr("dialog.delete.confirm_one")
        if QMessageBox.question(self, tr("dialog.delete.title"), prompt) != QMessageBox.StandardButton.Yes:
            return
        deleted_entries: list[ProxyEntry] = []
        for entry_id in selected_ids:
            deleted = self.db.delete_entry(entry_id)
            if deleted:
                deleted_entries.append(deleted)
        self.last_deleted_entries = deleted_entries
        self.undo_delete_action.setEnabled(bool(self.last_deleted_entries))
        self.refresh_library()
        self.show_toast(tr("toast.entries_deleted", count=len(deleted_entries)))

    def undo_last_delete(self) -> None:
        if not self.last_deleted_entries:
            return
        restored_id = ""
        for entry in self.last_deleted_entries:
            restored = self.db.save_entry(entry)
            restored_id = restored.id
        self.last_deleted_entries = []
        self.undo_delete_action.setEnabled(False)
        self.refresh_library(select_id=restored_id)
        self.show_toast(tr("toast.delete_undone"))

    def save_current_qr(self, entry_id: str) -> None:
        entry = self.db.get_entry(entry_id, include_uri=not self.db.is_locked)
        if not entry:
            return
        default_name = f"{entry.name}.png"
        destination, _ = QFileDialog.getSaveFileName(
            self,
            tr("action.save_qr_png"),
            default_name,
            "PNG Image (*.png)",
        )
        if not destination:
            return
        try:
            if entry.uri and not entry.is_locked:
                save_qr_assets(entry, self.settings.default_qr, self.settings.output_folder, target_path=destination)
            elif entry.qr_png_path and Path(entry.qr_png_path).exists():
                shutil.copy2(entry.qr_png_path, destination)
                svg_src = Path(entry.qr_png_path).with_suffix(".svg")
                if svg_src.exists():
                    shutil.copy2(svg_src, Path(destination).with_suffix(".svg"))
            else:
                raise FileNotFoundError(tr("dialog.runtime_log.empty"))
            self.show_toast(tr("toast.qr_saved", path=destination))
        except OSError as exc:
            QMessageBox.warning(self, tr("action.save_qr_png"), format_ui_error("ui.error.save_qr_failed", detail=exc))

    def export_single(self, fmt: str) -> None:
        if not self.current_entry:
            QMessageBox.information(self, tr("toolbar.export.button"), tr("dialog.export.select_entry"))
            return
        entry = self.db.get_entry(self.current_entry.id, include_uri=not self.db.is_locked)
        if not entry:
            return
        filters = {
            "png": "PNG Image (*.png)",
            "svg": "SVG Image (*.svg)",
            "pdf": "PDF Document (*.pdf)",
        }
        destination, _ = QFileDialog.getSaveFileName(
            self,
            f"{tr('toolbar.export.button')} {fmt.upper()}",
            f"{entry.name}.{fmt}",
            filters[fmt],
        )
        if not destination:
            return
        try:
            if fmt == "png":
                if entry.uri and not entry.is_locked:
                    save_qr_assets(entry, self.settings.default_qr, self.settings.output_folder, target_path=destination)
                elif entry.qr_png_path and Path(entry.qr_png_path).exists():
                    shutil.copy2(entry.qr_png_path, destination)
                else:
                    raise FileNotFoundError(tr("dialog.export.no_unlocked"))
            if fmt == "svg":
                svg_src = Path(entry.qr_png_path).with_suffix(".svg")
                if entry.uri and not entry.is_locked:
                    _png, svg_path = save_qr_assets(
                        entry,
                        self.settings.default_qr,
                        self.settings.output_folder,
                        target_path=str(Path(destination).with_suffix(".png")),
                    )
                    shutil.copy2(svg_path, destination)
                elif svg_src.exists():
                    shutil.copy2(svg_src, destination)
                else:
                    raise FileNotFoundError(tr("dialog.export.no_unlocked"))
            elif fmt == "pdf":
                if entry.is_locked or not entry.uri:
                    raise AuthenticationError(tr("detail.copy_uri.locked"))
                export_entry_pdf(entry, self.settings.default_qr, destination)
            self.show_toast(tr("toast.exported_entry", name=entry.name))
        except (AuthenticationError, OSError) as exc:
            QMessageBox.warning(self, tr("toolbar.export.button"), format_ui_error("ui.error.export_failed", detail=exc))

    def export_selection_zip(self) -> None:
        entries = self.selected_or_visible_entries()
        if not entries:
            QMessageBox.information(self, tr("toolbar.export.button"), tr("dialog.export.no_selection"))
            return
        destination, _ = QFileDialog.getSaveFileName(self, tr("action.export_selection_zip"), "proxyvault-export.zip", "ZIP Archive (*.zip)")
        if not destination:
            return
        try:
            export_zip(entries, destination)
            self.show_toast(tr("toast.zip_export_created"))
        except OSError as exc:
            QMessageBox.warning(self, tr("action.export_selection_zip"), format_ui_error("ui.error.export_failed", detail=exc))

    def export_booklet(self) -> None:
        if not self.ensure_unlocked(tr("main.search.reason.export_booklet")):
            return
        entries = [entry for entry in self.selected_or_visible_entries(include_uri=True) if entry.uri]
        if not entries:
            QMessageBox.information(self, tr("action.export_pdf_booklet"), tr("dialog.export.no_unlocked"))
            return
        destination, _ = QFileDialog.getSaveFileName(self, tr("action.export_pdf_booklet"), "proxyvault-booklet.pdf", "PDF Document (*.pdf)")
        if not destination:
            return
        export_booklet_pdf(entries, self.settings.default_qr, destination)
        self.show_toast(tr("toast.pdf_booklet_exported"))

    def export_clash(self) -> None:
        if not self.ensure_unlocked(tr("main.search.reason.export_clash")):
            return
        entries = [entry for entry in self.selected_or_visible_entries(include_uri=True) if entry.uri]
        if not entries:
            QMessageBox.information(self, tr("action.export_clash_yaml"), tr("dialog.export.no_unlocked"))
            return
        destination, _ = QFileDialog.getSaveFileName(self, tr("action.export_clash_yaml"), "proxyvault.yaml", "YAML File (*.yaml *.yml)")
        if not destination:
            return
        export_clash_yaml(entries, destination)
        self.show_toast(tr("toast.clash_exported"))

    def regenerate_all(self) -> None:
        if not self.ensure_unlocked(tr("main.search.reason.regenerate_qr")):
            return
        entries = self.db.list_entries(include_uri=True)
        count = 0
        for entry in entries:
            if not entry.uri:
                continue
            png_path, _ = save_qr_assets(entry, self.settings.default_qr, self.settings.output_folder)
            entry.qr_png_path = png_path
            self.db.save_entry(entry)
            count += 1
        self.refresh_library(select_id=self.current_entry.id if self.current_entry else "")
        self.show_toast(tr("toast.regenerated_assets", count=count))

    def toggle_lock_state(self) -> None:
        if not self.db.has_master_password():
            QMessageBox.information(self, tr("section.master_password"), tr("settings.password.not_set"))
            self.open_settings()
            return
        if self.db.is_locked:
            if self.ensure_unlocked(tr("main.search.reason.unlock_vault")):
                current_id = self.current_entry.id if self.current_entry else ""
                self.refresh_library(select_id=current_id)
                self.show_toast(tr("toast.unlocked"))
        else:
            self.db.lock()
            self.current_entry = None
            self.detail_panel.clear_panel()
            self.refresh_library()
            self.show_toast(tr("toast.locked"))

    def ensure_unlocked(self, reason: str) -> bool:
        if not self.db.has_master_password() or not self.db.is_locked:
            return True
        dialog = PasswordDialog(tr("dialog.password.title.unlock"), ask_current=False, confirm_new=False, parent=self)
        if not dialog.exec():
            return False
        try:
            self.db.unlock(dialog.password)
            return True
        except AuthenticationError as exc:
            QMessageBox.warning(self, tr("action.unlock"), format_ui_error("ui.error.unlock_failed", detail=exc))
            return False

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.db, self.settings, self)
        if dialog.exec():
            previous_language = self.settings.ui_language
            previous_client_mode = self.settings.client_mode_enabled
            self.settings = dialog.values()
            self.db.save_settings(self.settings)
            if previous_client_mode and not self.settings.client_mode_enabled:
                self.runtime_manager.stop_all()
            if previous_language != self.settings.ui_language:
                self.apply_ui_language(self.settings.ui_language)
            self.apply_theme(self.settings.theme)
            self.refresh_library(select_id=self.current_entry.id if self.current_entry else "")
            self._refresh_current_entry_detail()
            self._update_runtime_actions()
            self.show_toast(tr("toast.settings_saved"))

    def apply_ui_language(self, locale_code: str) -> None:
        set_locale(SupportedLocale.coerce(locale_code))
        ensure_ui_translations()
        self.retranslate_ui()

    def set_view_mode(self, mode: str) -> None:
        self.card_view.set_mode(mode)
        self._populate_view_combo(mode)

    def toggle_details_panel(self) -> None:
        self.detail_panel.setVisible(not self.detail_panel.isVisible())

    def toggle_theme(self) -> None:
        next_theme = "dark" if self.settings.theme in {"system", "light"} else "light"
        self.settings.theme = next_theme
        self.db.save_settings(self.settings)
        self.apply_theme(next_theme)
        self.show_toast(tr("toast.theme_switched", theme=tr(f"settings.theme.{next_theme}")))

    def apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if not app:
            return
        resolved_theme = "dark" if theme == "dark" else "light"
        app.setStyle(QStyleFactory.create("Fusion"))
        apply_app_theme(app, resolved_theme)

    def update_status_bar(self) -> None:
        self.entry_count_label.setText(
            tr("toolbar.status.entries_shown", shown=len(self.filtered_entries), total=len(self.entries))
        )
        set_widget_status(self.entry_count_label, "statusTone", "muted")
        last_import = self.db.get_metadata("last_import_date", tr("common.never"))
        if last_import in {"", "never"}:
            last_import = tr("common.never")
        self.last_import_label.setText(tr("toolbar.status.last_import", value=last_import))
        set_widget_status(self.last_import_label, "statusTone", "muted" if last_import == tr("common.never") else "success")
        if not self.db.has_master_password():
            self.lock_status_label.setText(tr("toolbar.status.lock.disabled"))
            set_widget_status(self.lock_status_label, "statusTone", "muted")
        else:
            self.lock_status_label.setText(
                tr("toolbar.status.lock.locked") if self.db.is_locked else tr("toolbar.status.lock.unlocked")
            )
            set_widget_status(self.lock_status_label, "statusTone", "warning" if self.db.is_locked else "success")
        active_count = len(self.runtime_snapshot.sessions)
        if self.settings.client_mode_enabled:
            self.runtime_status_label.setText(tr("main.runtime.active_sessions", count=active_count))
            set_widget_status(self.runtime_status_label, "statusTone", "success" if active_count else "muted")
        else:
            self.runtime_status_label.setText(tr("main.runtime.client_mode_off"))
            set_widget_status(self.runtime_status_label, "statusTone", "warning")
        self._update_workspace_header()
        self._update_lock_action()
        self._update_runtime_actions()

    def show_welcome_if_needed(self) -> None:
        if self.settings.has_seen_welcome:
            return
        self.settings.has_seen_welcome = True
        self.db.save_settings(self.settings)
        self.show_welcome_dialog()

    def show_welcome_dialog(self) -> None:
        dialog = WelcomeDialog(self)
        if dialog.exec():
            self.open_add_dialog()

    def show_help_dialog(self) -> None:
        dialog = HelpDialog(self)
        dialog.exec()

    def show_about(self) -> None:
        QMessageBox.information(self, tr("app.about.title"), tr("app.about.body"))

    def show_fullscreen_qr(self, entry_id: str) -> None:
        entry = self.db.get_entry(entry_id, include_uri=not self.db.is_locked)
        if not entry:
            return
        pixmap = QPixmap()
        if entry.uri and not entry.is_locked:
            pixmap = qr_pixmap(entry.uri, self.settings.default_qr, max_size=1200)
        elif entry.qr_png_path and Path(entry.qr_png_path).exists():
            pixmap = QPixmap(entry.qr_png_path).scaled(
                1200,
                1200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        else:
            QMessageBox.information(
                self,
                tr("dialog.fullscreen_qr.unavailable.title"),
                tr("dialog.fullscreen_qr.unavailable.body"),
            )
            return
        dialog = FullScreenQrDialog(entry.name, pixmap, self)
        dialog.exec()

    def _read_runtime_log_file(self, log_path: str) -> str | None:
        try:
            return Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def _resolve_runtime_log_view(self, fallback_text: str, *, log_path: str = "") -> tuple[str, str, str]:
        normalized_path = str(log_path or "").strip()
        if normalized_path:
            log_text = self._read_runtime_log_file(normalized_path)
            if log_text is not None:
                return log_text, normalized_path, ""
            return fallback_text, "", tr("dialog.runtime_log.path_unavailable")
        if fallback_text:
            return fallback_text, "", tr("dialog.runtime_log.path_unavailable")
        return "", "", ""

    def _session_log_path(self, session: RunningSession) -> str:
        launch_spec = getattr(self.runtime_manager, "_launch_spec_by_session_id", {}).get(session.session_id)
        log_path = getattr(launch_spec, "log_path", "") if launch_spec is not None else ""
        if log_path:
            return str(log_path)
        metadata_log_path = session.metadata.get("wireguard_log_path")
        if isinstance(metadata_log_path, str) and metadata_log_path.strip():
            return metadata_log_path.strip()
        return ""

    def _is_runtime_reachability_check(self, result: ReachabilityCheck) -> bool:
        method = str(result.method or "").strip().lower()
        return bool(method) and method not in {
            "tcp probe",
            "tcp-проверка",
            "protocol note",
            "протокольная пометка",
        }

    def _runtime_log_payload(self, entry: ProxyEntry) -> tuple[str, str, str]:
        session = self.runtime_sessions_by_entry_id.get(entry.id)
        if session is not None:
            return self._resolve_runtime_log_view(session.log_excerpt, log_path=self._session_log_path(session))

        for result in self.db.list_reachability_checks(entry.id, limit=20):
            if self._is_runtime_reachability_check(result):
                fallback_text = result.details or result.failure_reason
                return self._resolve_runtime_log_view(fallback_text, log_path=result.log_path)

        history = self.runtime_manager.history_for_entry(entry.id, limit=1)
        if history:
            return self._resolve_runtime_log_view(history[0].short_log_excerpt, log_path=history[0].log_path)

        return "", "", ""

    def show_runtime_log_dialog(self, entry_id: str | None = None) -> None:
        entry = self._resolve_entry(entry_id)
        if entry is None:
            QMessageBox.information(self, tr("dialog.runtime_unavailable.title"), tr("dialog.runtime_unavailable.body"))
            return
        log_text, log_path, path_message = self._runtime_log_payload(entry)
        dialog = RuntimeLogDialog(
            entry.name,
            log_text=log_text,
            log_path=log_path,
            path_message=path_message,
            parent=self,
        )
        dialog.exec()

    def show_session_history_dialog(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(self, tr("dialog.runtime_unavailable.title"), tr("dialog.runtime_unavailable.body"))
            return
        records: list[SessionHistoryRecord] = self.runtime_manager.history_for_entry(entry.id, limit=50)
        dialog = SessionHistoryDialog(entry.name, records, self)
        dialog.exec()

    def copy_runtime_local_address(self, entry_id: str) -> None:
        session = self.runtime_sessions_by_entry_id.get(entry_id)
        if session is None:
            self.show_toast(tr("detail.runtime.local_address.unavailable"), error=True)
            return
        address = session.local_http_url or session.local_socks_url
        if not address:
            self.show_toast(tr("detail.runtime.local_address.unavailable"), error=True)
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(address)
        self.show_toast(tr("detail.runtime.local_address.copied", address=address))

    def _resolve_entry(self, entry_id: str | None) -> ProxyEntry | None:
        if entry_id:
            return self.db.get_entry(entry_id, include_uri=not self.db.is_locked)
        return self._selected_entry()

    def selected_or_visible_entries(self, include_uri: bool = False) -> list[ProxyEntry]:
        selected_ids = self.card_view.selected_ids()
        if selected_ids:
            entries: list[ProxyEntry] = []
            for entry_id in selected_ids:
                entry = self.db.get_entry(entry_id, include_uri=include_uri)
                if entry:
                    entries.append(entry)
            return entries
        if include_uri:
            return [
                entry
                for source_entry in self.filtered_entries
                if (entry := self.db.get_entry(source_entry.id, include_uri=True))
            ]
        return list(self.filtered_entries)

    def auto_refresh_subscriptions(self) -> None:
        if self._subscription_refresh_worker is not None:
            return
        due_subscriptions = [
            subscription
            for subscription in self.db.list_subscriptions()
            if self._subscription_is_due(subscription.refresh_interval, subscription.last_fetched)
        ]
        if not due_subscriptions:
            return
        worker = FunctionWorker(self._refresh_subscriptions_task, due_subscriptions)
        self._subscription_refresh_worker = worker
        worker.signals.progress.connect(self._handle_subscription_refresh_progress)
        worker.signals.finished.connect(self._handle_subscription_refresh_finished)
        worker.signals.error.connect(self._handle_subscription_refresh_error)
        self._start_worker(worker, {"kind": "subscription_refresh"})

    def _refresh_subscriptions_task(
        self,
        subscriptions: list[SubscriptionRecord],
        progress_callback=None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        total = len(subscriptions)
        for index, subscription in enumerate(subscriptions, start=1):
            if progress_callback is not None:
                progress_callback.emit({"index": index, "total": total, "url": subscription.url})
            try:
                payload = fetch_subscription_url_payload(
                    subscription.url,
                    allow_insecure_http=self.settings.allow_insecure_subscription_http,
                )
                results.append(
                    {
                        "url": subscription.url,
                        "status": "ok",
                        "format_name": payload["format_name"],
                        "items": payload["items"],
                        "final_url": payload.get("final_url", subscription.url),
                    }
                )
            except Exception as exc:
                results.append({"url": subscription.url, "status": "error", "error": self._format_subscription_refresh_error(exc)})
        return results

    def _handle_subscription_refresh_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        index = int(payload.get("index", 0))
        total = int(payload.get("total", 0))
        url = str(payload.get("url", ""))
        self.statusBar().showMessage(tr("status.subscription.refreshing", index=index, total=total, url=url))

    def _handle_subscription_refresh_finished(self, payloads: object) -> None:
        self._take_worker_context()
        self._finish_subscription_refresh()
        results = payloads if isinstance(payloads, list) else []
        if self.db.has_master_password() and self.db.is_locked:
            if any(isinstance(item, dict) and item.get("status") == "ok" for item in results):
                self.show_toast(tr("toast.unlock_to_apply_auto_refresh"))
            return
        imported_urls: list[str] = []
        failure_messages: list[str] = []
        for payload in results:
            if not isinstance(payload, dict):
                continue
            url = str(payload.get("url", ""))
            if payload.get("status") != "ok":
                failure_messages.append(f"{url}: {payload.get('error', tr('common.unknown'))}")
                continue
            items = payload.get("items", [])
            if not isinstance(items, list):
                failure_messages.append(f"{url}: {tr('dialog.subscription.validation.invalid_source')}")
                continue
            typed_items = [item for item in items if isinstance(item, SubscriptionImportItem)]
            imported = self.import_items(typed_items)
            self.db.update_subscription_fetch_time(url)
            if imported:
                imported_urls.append(url)
        if imported_urls:
            self.show_toast(tr("toast.auto_refreshed_subscriptions", count=len(imported_urls)))
        for message in failure_messages:
            self.show_toast(tr("toast.subscription_refresh_failed", error=message), error=True)

    def _handle_subscription_refresh_error(self, exc: object) -> None:
        self._take_worker_context()
        self._finish_subscription_refresh()
        self.show_toast(tr("toast.subscription_refresh_failed", error=self._format_subscription_refresh_error(exc)), error=True)

    def _finish_subscription_refresh(self) -> None:
        self._subscription_refresh_worker = None

    def _subscription_is_due(self, refresh_interval: str, last_fetched: str) -> bool:
        if refresh_interval == "never":
            return False
        if not last_fetched:
            return True
        try:
            last_dt = datetime.fromisoformat(last_fetched)
        except ValueError:
            return True
        delta = timedelta(days=1 if refresh_interval == "daily" else 7)
        return datetime.utcnow() - last_dt >= delta

    def _format_subscription_refresh_error(self, detail: object) -> str:
        detail_text = str(detail or "").strip()
        lowered = detail_text.lower()
        if isinstance(detail, (ParseError, SubscriptionSecurityError)):
            return format_ui_error("ui.error.subscription_failed", detail=tr("dialog.subscription.validation.invalid_source"))
        if any(token in lowered for token in ("401", "403", "unauthorized", "forbidden", "authentication", "auth")):
            human_summary = describe_human_error("authentication_failed", detail=detail_text).summary
            return format_ui_error("ui.error.subscription_failed", detail=human_summary)
        if any(
            token in lowered
            for token in (
                "timed out",
                "timeout",
                "refused",
                "unreachable",
                "network is unreachable",
                "connection aborted",
                "connection reset",
                "temporary failure",
            )
        ):
            human_summary = describe_human_error("server_unreachable", detail=detail_text).summary
            return format_ui_error("ui.error.subscription_failed", detail=human_summary)
        return tr("ui.error.subscription_failed")

    def show_toast(self, message: str, error: bool = False) -> None:
        self.statusBar().showMessage(message, 5000)
        point = self.mapToGlobal(QPoint(self.width() // 2, 48))
        QToolTip.showText(point, message, self)
        _ = error

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        mime = event.mimeData()
        imported_any = False
        if mime.hasUrls():
            for url in mime.urls():
                local_path = Path(url.toLocalFile())
                if not local_path.exists() or local_path.is_dir():
                    continue
                try:
                    text = local_path.read_text(encoding="utf-8", errors="ignore")
                except OSError as exc:
                    QMessageBox.warning(self, tr("action.import_uri"), ui_error_message("ui.error.import_file_failed", exc))
                    continue
                imported_any |= self.import_text_blob(text)
        elif mime.hasText():
            imported_any = self.import_text_blob(mime.text())
        if imported_any:
            event.acceptProposedAction()

    def import_text_blob(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if is_wireguard_block(stripped):
            self.open_add_dialog(prefill_text=stripped)
            return True
        lines = [line for line in stripped.splitlines() if line.strip()]
        if len(lines) == 1:
            try:
                parse_proxy_text(stripped)
            except ParseError:
                return False
            self.open_add_dialog(prefill_text=stripped)
            return True
        try:
            _fmt, items = parse_subscription_payload(stripped)
            if not self.ensure_unlocked(tr("main.search.reason.import_dropped")):
                return False
            count = self.import_items(items)
            self.show_toast(tr("toast.imported_dropped_entries", count=count))
            return bool(count)
        except ParseError:
            return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override,name-defined]
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            key_event = event
            modifiers = key_event.modifiers()
            key = key_event.key()
            if key == Qt.Key.Key_V and modifiers & Qt.KeyboardModifier.ControlModifier:
                focus = QApplication.focusWidget()
                if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextEdit)):
                    return False
                clipboard_text = QApplication.clipboard().text().strip()
                if clipboard_text:
                    if is_wireguard_block(clipboard_text):
                        self.open_add_dialog(prefill_text=clipboard_text)
                        return True
                    try:
                        parse_proxy_text(clipboard_text)
                    except ParseError:
                        return False
                    self.open_add_dialog(prefill_text=clipboard_text)
                    return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        if self._did_shutdown:
            return
        self._did_shutdown = True
        self._runtime_poll_timer.stop()
        self.runtime_manager.shutdown()

    def _set_toolbar_button_variant(self, toolbar: QToolBar, action: QAction, variant: str) -> None:
        button = toolbar.widgetForAction(action)
        if button:
            button.setProperty("variant", variant)

    def _apply_action_icons(self) -> None:
        for action, (icon_name, color) in self._action_icon_specs.items():
            apply_action_icon(action, icon_name, color=color)
        self._update_lock_action()

    def _update_workspace_header(self) -> None:
        total_entries = len(self.entries)
        visible_entries = len(self.filtered_entries)
        if visible_entries == total_entries:
            self.workspace_scope_pill.setText(tr("main.hero.scope.all", count=total_entries))
        else:
            self.workspace_scope_pill.setText(tr("main.hero.scope.filtered", visible=visible_entries, total=total_entries))
        set_widget_status(self.workspace_scope_pill, "statusTone", "muted")

        selected_ids = self.card_view.selected_ids()
        selected_count = len(selected_ids) if selected_ids else (1 if self.current_entry is not None else 0)
        if selected_count <= 0:
            self.workspace_selection_pill.setText(tr("main.hero.selection.none"))
            self.workspace_selection_pill.setToolTip("")
            selection_tone = "muted"
        elif selected_count == 1:
            self.workspace_selection_pill.setText(tr("main.hero.selection.single"))
            self.workspace_selection_pill.setToolTip(
                self.current_entry.name if self.current_entry is not None else ""
            )
            selection_tone = "success"
        else:
            self.workspace_selection_pill.setText(tr("main.hero.selection.multiple", count=selected_count))
            self.workspace_selection_pill.setToolTip("")
            selection_tone = "success"
        set_widget_status(self.workspace_selection_pill, "statusTone", selection_tone)

        active_count = len(self.runtime_snapshot.sessions)
        if not self.settings.client_mode_enabled:
            self.workspace_mode_pill.setText(tr("main.hero.mode.off"))
            mode_tone = "warning"
        elif active_count:
            self.workspace_mode_pill.setText(tr("main.hero.mode.active", count=active_count))
            mode_tone = "success"
        else:
            self.workspace_mode_pill.setText(tr("main.hero.mode.ready"))
            mode_tone = "muted"
        set_widget_status(self.workspace_mode_pill, "statusTone", mode_tone)

    def _update_lock_action(self) -> None:
        if not self.db.has_master_password():
            self.lock_action.setText(tr("action.lock"))
            apply_action_icon(self.lock_action, "lock", color="#9A8A7A")
            return
        if self.db.is_locked:
            self.lock_action.setText(tr("action.unlock"))
            apply_action_icon(self.lock_action, "unlock", color="#D3A247")
            return
        self.lock_action.setText(tr("action.lock"))
        apply_action_icon(self.lock_action, "lock", color="#7EA67B")
