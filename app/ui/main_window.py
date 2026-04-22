from __future__ import annotations

import shutil
import socket
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QThreadPool
from PyQt6.QtGui import QAction, QKeyEvent, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QVBoxLayout,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QTextEdit,
    QToolBar,
    QToolTip,
    QComboBox,
    QWidget,
    QStyleFactory,
)

from app.db import AuthenticationError, DatabaseManager
from app.models import (
    ProxyEntry,
    ProxyType,
    ReachabilityCheck,
    ReachabilityState,
    SubscriptionImportItem,
    SubscriptionRecord,
    TYPE_LABELS,
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
from app.subscriptions import fetch_subscription_url_payload
from app.ui.card_view import CardView
from app.ui.detail_panel import DetailPanel
from app.ui.dialogs import AddEntryDialog, FullScreenQrDialog, ImportSubscriptionDialog, PasswordDialog, WelcomeDialog
from app.ui.icons import icon
from app.ui.settings import SettingsDialog
from app.ui.sidebar import Sidebar
from app.ui.theme import apply_action_icon, apply_app_theme, set_widget_status
from app.ui.workers import FunctionWorker


class MainWindow(QMainWindow):
    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db
        self.settings = self.db.load_settings()
        self.entries: list[ProxyEntry] = []
        self.filtered_entries: list[ProxyEntry] = []
        self.last_deleted_entries: list[ProxyEntry] = []
        self.current_entry: ProxyEntry | None = None
        self._thread_pool = QThreadPool.globalInstance()
        self._active_workers: list[FunctionWorker] = []
        self._worker_contexts: dict[int, dict[str, Any]] = {}
        self._active_reachability_ids: set[str] = set()
        self._batch_reachability_active = False
        self._subscription_refresh_worker: FunctionWorker | None = None

        self.setWindowTitle("ProxyVault")
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

        self.apply_theme(self.settings.theme)
        QApplication.instance().installEventFilter(self)

        self.refresh_library()
        self.auto_refresh_subscriptions()
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
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.card_view)
        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([220, 920, 340])

        canvas = QWidget()
        canvas.setObjectName("workspaceCanvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(12, 6, 12, 12)
        canvas_layout.setSpacing(0)
        canvas_layout.addWidget(splitter)
        self.setCentralWidget(canvas)

    def _build_actions(self) -> None:
        self.add_action = QAction("Add", self)
        self.add_action.setShortcut(QKeySequence.StandardKey.New)
        self.add_action.triggered.connect(self.open_add_dialog)

        self.import_uri_action = QAction("Import URI", self)
        self.import_uri_action.triggered.connect(self.open_add_dialog)

        self.import_subscription_action = QAction("Import Subscription", self)
        self.import_subscription_action.triggered.connect(self.import_subscription)

        self.export_png_action = QAction("Export Current PNG", self)
        self.export_png_action.triggered.connect(lambda: self.export_single("png"))

        self.export_svg_action = QAction("Export Current SVG", self)
        self.export_svg_action.triggered.connect(lambda: self.export_single("svg"))

        self.export_pdf_action = QAction("Export Current PDF", self)
        self.export_pdf_action.triggered.connect(lambda: self.export_single("pdf"))

        self.export_zip_action = QAction("Export Selection ZIP", self)
        self.export_zip_action.setShortcut("Ctrl+E")
        self.export_zip_action.triggered.connect(self.export_selection_zip)

        self.export_booklet_action = QAction("Export PDF Booklet", self)
        self.export_booklet_action.triggered.connect(self.export_booklet)

        self.export_clash_action = QAction("Export Clash YAML", self)
        self.export_clash_action.triggered.connect(self.export_clash)

        self.regenerate_action = QAction("Regenerate All QR Codes", self)
        self.regenerate_action.triggered.connect(self.regenerate_all)

        self.check_current_action = QAction("Check Selected Entry", self)
        self.check_current_action.triggered.connect(self.check_current_entry_reachability)

        self.check_filtered_action = QAction("Check Filtered Entries", self)
        self.check_filtered_action.triggered.connect(self.check_filtered_entries)

        self.delete_action = QAction("Delete Selected", self)
        self.delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_action.triggered.connect(self.delete_selected)

        self.undo_delete_action = QAction("Undo Last Delete", self)
        self.undo_delete_action.triggered.connect(self.undo_last_delete)
        self.undo_delete_action.setEnabled(False)

        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.open_settings)

        self.grid_view_action = QAction("Grid View", self)
        self.grid_view_action.triggered.connect(lambda: self.set_view_mode("grid"))

        self.list_view_action = QAction("List View", self)
        self.list_view_action.triggered.connect(lambda: self.set_view_mode("list"))

        self.toggle_details_action = QAction("Toggle Details Panel", self)
        self.toggle_details_action.triggered.connect(self.toggle_details_panel)

        self.lock_action = QAction("Lock", self)
        self.lock_action.triggered.connect(self.toggle_lock_state)

        self.theme_toggle_action = QAction("Toggle Theme", self)
        self.theme_toggle_action.triggered.connect(self.toggle_theme)

        self.quick_start_action = QAction("Quick Start", self)
        self.quick_start_action.triggered.connect(self.show_welcome_dialog)

        self.about_action = QAction("About ProxyVault", self)
        self.about_action.triggered.connect(self.show_about)

        self.focus_search_action = QAction("Focus Search", self)
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
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.import_uri_action)
        file_menu.addAction(self.import_subscription_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_png_action)
        file_menu.addAction(self.export_svg_action)
        file_menu.addAction(self.export_pdf_action)
        file_menu.addAction(self.export_zip_action)
        file_menu.addAction(self.export_booklet_action)
        file_menu.addAction(self.export_clash_action)
        file_menu.addSeparator()
        file_menu.addAction(self.regenerate_action)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.add_action)
        edit_menu.addAction(self.undo_delete_action)
        edit_menu.addAction(self.delete_action)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.grid_view_action)
        view_menu.addAction(self.list_view_action)
        view_menu.addAction(self.toggle_details_action)
        view_menu.addAction(self.theme_toggle_action)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction(self.check_current_action)
        tools_menu.addAction(self.check_filtered_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.regenerate_action)

        settings_menu = self.menuBar().addMenu("Settings")
        settings_menu.addAction(self.settings_action)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.quick_start_action)
        help_menu.addAction(self.about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText("Search name, host, tags, notes...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.apply_filters)
        self.search_edit.setMinimumWidth(340)
        self.search_edit.addAction(icon("search", size=16), QLineEdit.ActionPosition.LeadingPosition)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Name", "Created Date", "Type", "Expiry Date"])
        self.sort_combo.currentTextChanged.connect(self.apply_filters)
        self.sort_combo.setMinimumWidth(148)

        self.view_toggle = QComboBox()
        self.view_toggle.addItems(["Grid", "List"])
        self.view_toggle.currentTextChanged.connect(
            lambda text: self.set_view_mode("grid" if text.lower() == "grid" else "list")
        )
        self.view_toggle.setMinimumWidth(108)

        toolbar.addWidget(self.search_edit)
        toolbar.addSeparator()
        toolbar.addAction(self.add_action)
        toolbar.addAction(self.import_subscription_action)

        self.export_button = toolbar.addAction("Export")
        self.export_button.triggered.connect(self.export_selection_zip)
        apply_action_icon(self.export_button, "export", color="#D8943C")
        toolbar.addAction(self.lock_action)
        toolbar.addAction(self.theme_toggle_action)
        toolbar.addWidget(self.sort_combo)
        toolbar.addWidget(self.view_toggle)

        self._set_toolbar_button_variant(toolbar, self.add_action, "primary")
        self._set_toolbar_button_variant(toolbar, self.import_subscription_action, "secondary")
        self._set_toolbar_button_variant(toolbar, self.export_button, "secondary")
        self._set_toolbar_button_variant(toolbar, self.lock_action, "subtle")
        self._set_toolbar_button_variant(toolbar, self.theme_toggle_action, "subtle")

    def _build_status_bar(self) -> None:
        self.statusBar().setSizeGripEnabled(False)
        self.entry_count_label = QLabel("0 entries")
        self.entry_count_label.setObjectName("statusPill")
        self.last_import_label = QLabel("Last import: never")
        self.last_import_label.setObjectName("statusPill")
        self.lock_status_label = QLabel("Unlocked")
        self.lock_status_label.setObjectName("statusPill")
        self.statusBar().addPermanentWidget(self.entry_count_label)
        self.statusBar().addPermanentWidget(self.last_import_label)
        self.statusBar().addPermanentWidget(self.lock_status_label)

    def _connect_signals(self) -> None:
        self.sidebar.filtersChanged.connect(self.apply_filters)
        self.card_view.entrySelected.connect(self.show_entry)
        self.card_view.entryActivated.connect(self.show_fullscreen_qr)
        self.detail_panel.saveRequested.connect(self.save_detail_changes)
        self.detail_panel.deleteRequested.connect(lambda _: self.delete_selected())
        self.detail_panel.saveQrRequested.connect(self.save_current_qr)
        self.detail_panel.reachabilityRequested.connect(self.check_entry_reachability)

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

        entries = []
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
                    TYPE_LABELS.get(entry.type, entry.type.value),
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
        self.update_status_bar()

    def sort_entries(self, entries: list[ProxyEntry]) -> list[ProxyEntry]:
        mode = self.sort_combo.currentText() if hasattr(self, "sort_combo") else "Created Date"
        if mode == "Name":
            return sorted(entries, key=lambda entry: entry.name.lower())
        if mode == "Type":
            return sorted(entries, key=lambda entry: (entry.type.value, entry.name.lower()))
        if mode == "Expiry Date":
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
        self.update_status_bar()

    def open_add_dialog(self, _checked: bool = False, prefill_text: str = "") -> None:
        if not self.ensure_unlocked("add or import entries"):
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
            self.show_toast(f"Saved {entry.name}")
        except (AuthenticationError, ParseError, OSError) as exc:
            QMessageBox.warning(self, "Save Entry", str(exc))

    def import_subscription(self) -> None:
        if not self.ensure_unlocked("import subscription entries"):
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
            self.show_toast(f"Imported {count} entries from subscription")

    def import_items(self, items) -> int:
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
            QMessageBox.information(self, "TCP Reachability", "Select an entry first.")
            return
        self.check_entry_reachability(self.current_entry.id)

    def check_entry_reachability(self, entry_id: str) -> None:
        if not entry_id:
            return
        if entry_id in self._active_reachability_ids:
            self.show_toast("A TCP probe for this entry is already running.")
            return
        entry = self.db.get_entry(entry_id, include_uri=False)
        if not entry:
            return
        self._active_reachability_ids.add(entry_id)
        self.statusBar().showMessage(f"Checking TCP reachability: {entry.name}")
        worker = FunctionWorker(self._probe_entry_task, entry)
        worker.signals.finished.connect(self._handle_probe_entry_finished)
        worker.signals.error.connect(self._handle_probe_error)
        self._start_worker(worker, {"entry_ids": [entry_id], "kind": "probe_single"})

    def check_filtered_entries(self) -> None:
        if self._batch_reachability_active:
            self.show_toast("A batch TCP reachability check is already running.")
            return
        visible_entries = list(self.filtered_entries)
        if not visible_entries:
            QMessageBox.information(self, "TCP Reachability", "No filtered entries are available.")
            return
        entries = [entry for entry in visible_entries if entry.id not in self._active_reachability_ids]
        if not entries:
            self.show_toast("Visible entries are already being checked.")
            return
        self._batch_reachability_active = True
        active_ids = [entry.id for entry in entries]
        self._active_reachability_ids.update(active_ids)
        worker = FunctionWorker(self._probe_entries_task, entries)
        worker.signals.progress.connect(self._handle_batch_probe_progress)
        worker.signals.finished.connect(self._handle_batch_probe_finished)
        worker.signals.error.connect(self._handle_probe_error)
        self._start_worker(worker, {"entry_ids": active_ids, "kind": "probe_batch"})

    def _probe_entry_task(self, entry: ProxyEntry, progress_callback=None) -> dict[str, Any]:
        _ = progress_callback
        return {"entry_id": entry.id, "entry_name": entry.name, "result": self._run_tcp_probe(entry)}

    def _probe_entries_task(self, entries: list[ProxyEntry], progress_callback=None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            if progress_callback is not None:
                progress_callback.emit({"index": index, "total": total, "entry_name": entry.name})
            results.append({"entry_id": entry.id, "entry_name": entry.name, "result": self._run_tcp_probe(entry)})
        return results

    def _handle_probe_entry_finished(self, payload: dict[str, Any]) -> None:
        context = self._take_worker_context()
        for entry_id in context.get("entry_ids", []):
            self._active_reachability_ids.discard(entry_id)
        entry_id = str(payload["entry_id"])
        entry_name = str(payload.get("entry_name", "Entry"))
        result = payload["result"]
        if not isinstance(result, ReachabilityCheck):
            raise TypeError("Unexpected reachability result payload.")
        self.db.record_reachability_check(entry_id, result)
        self.refresh_library(select_id=entry_id)
        self.show_toast(f"{entry_name}: {self._reachability_summary(result)}")

    def _handle_batch_probe_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        index = int(payload.get("index", 0))
        total = int(payload.get("total", 0))
        entry_name = str(payload.get("entry_name", ""))
        self.statusBar().showMessage(f"Checking TCP reachability {index}/{total}: {entry_name}")

    def _handle_batch_probe_finished(self, payloads: object) -> None:
        context = self._take_worker_context()
        for entry_id in context.get("entry_ids", []):
            self._active_reachability_ids.discard(entry_id)
        results = payloads if isinstance(payloads, list) else []
        reachable = 0
        failed = 0
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
            else:
                failed += 1
        self._batch_reachability_active = False
        current_id = self.current_entry.id if self.current_entry else ""
        self.refresh_library(select_id=current_id)
        self.show_toast(f"Checked {reachable + failed} entries: {reachable} reachable, {failed} failed")

    def _handle_probe_error(self, exc: object) -> None:
        context = self._take_worker_context()
        for entry_id in context.get("entry_ids", []):
            self._active_reachability_ids.discard(entry_id)
        if context.get("kind") == "probe_batch":
            self._batch_reachability_active = False
        self.show_toast(f"TCP reachability check failed: {exc}", error=True)

    def _reachability_summary(self, result: ReachabilityCheck) -> str:
        if result.status == ReachabilityState.REACHABLE and result.latency_ms is not None:
            return f"reachable in {result.latency_ms} ms"
        if result.failure_reason:
            return result.failure_reason
        return result.status.value.lower()

    def _run_tcp_probe(self, entry: ProxyEntry) -> ReachabilityCheck:
        checked_at = utc_now_iso()
        endpoint = entry.display_host_port
        if not entry.server_host or not entry.server_port:
            return ReachabilityCheck(
                checked_at=checked_at,
                status=ReachabilityState.FAILED,
                endpoint=endpoint,
                method="TCP probe",
                failure_reason="This configuration does not expose a host and port for a TCP probe.",
                error_category="unavailable",
                details=(
                    "TCP probe skipped.\n"
                    f"Entry: {entry.name}\n"
                    f"Endpoint: {endpoint}\n"
                    "ProxyVault could not run a TCP reachability check because the parsed host or port is missing."
                ),
                config_fingerprint=entry.uri_fingerprint,
            )

        start = perf_counter()
        try:
            with socket.create_connection((entry.server_host, int(entry.server_port)), timeout=3):
                duration_ms = max(int((perf_counter() - start) * 1000), 1)
            return ReachabilityCheck(
                checked_at=checked_at,
                status=ReachabilityState.REACHABLE,
                endpoint=endpoint,
                method="TCP probe",
                latency_ms=duration_ms,
                duration_ms=duration_ms,
                details=(
                    "TCP probe succeeded.\n"
                    f"Entry: {entry.name}\n"
                    f"Endpoint: {endpoint}\n"
                    f"Duration: {duration_ms} ms\n"
                    "Method: socket.create_connection(timeout=3)"
                ),
                config_fingerprint=entry.uri_fingerprint,
            )
        except socket.timeout:
            duration_ms = max(int((perf_counter() - start) * 1000), 3000)
            return ReachabilityCheck(
                checked_at=checked_at,
                status=ReachabilityState.FAILED,
                endpoint=endpoint,
                method="TCP probe",
                duration_ms=duration_ms,
                failure_reason="The TCP connection timed out after 3 seconds.",
                error_category="timeout",
                details=(
                    "TCP probe failed.\n"
                    f"Entry: {entry.name}\n"
                    f"Endpoint: {endpoint}\n"
                    f"Duration: {duration_ms} ms\n"
                    "Failure: timeout after 3 seconds"
                ),
                config_fingerprint=entry.uri_fingerprint,
            )
        except ConnectionRefusedError:
            duration_ms = max(int((perf_counter() - start) * 1000), 1)
            return ReachabilityCheck(
                checked_at=checked_at,
                status=ReachabilityState.FAILED,
                endpoint=endpoint,
                method="TCP probe",
                duration_ms=duration_ms,
                failure_reason="The endpoint refused the TCP connection.",
                error_category="refused",
                details=(
                    "TCP probe failed.\n"
                    f"Entry: {entry.name}\n"
                    f"Endpoint: {endpoint}\n"
                    f"Duration: {duration_ms} ms\n"
                    "Failure: connection refused"
                ),
                config_fingerprint=entry.uri_fingerprint,
            )
        except OSError as exc:
            duration_ms = max(int((perf_counter() - start) * 1000), 1)
            failure_reason = str(exc) or "The TCP connection could not be established."
            return ReachabilityCheck(
                checked_at=checked_at,
                status=ReachabilityState.FAILED,
                endpoint=endpoint,
                method="TCP probe",
                duration_ms=duration_ms,
                failure_reason=failure_reason,
                error_category="network_error",
                details=(
                    "TCP probe failed.\n"
                    f"Entry: {entry.name}\n"
                    f"Endpoint: {endpoint}\n"
                    f"Duration: {duration_ms} ms\n"
                    f"Failure: {failure_reason}"
                ),
                config_fingerprint=entry.uri_fingerprint,
            )

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
        self.show_toast("Entry updated")

    def delete_selected(self) -> None:
        selected_ids = self.card_view.selected_ids() or ([self.current_entry.id] if self.current_entry else [])
        if not selected_ids:
            return
        if self.db.is_locked:
            QMessageBox.information(self, "Locked", "Unlock ProxyVault before deleting encrypted entries.")
            return
        prompt = "Delete the selected entries?" if len(selected_ids) > 1 else "Delete this entry?"
        if QMessageBox.question(self, "Confirm Delete", prompt) != QMessageBox.StandardButton.Yes:
            return
        deleted_entries: list[ProxyEntry] = []
        for entry_id in selected_ids:
            deleted = self.db.delete_entry(entry_id)
            if deleted:
                deleted_entries.append(deleted)
        self.last_deleted_entries = deleted_entries
        self.undo_delete_action.setEnabled(bool(self.last_deleted_entries))
        self.refresh_library()
        self.show_toast(f"Deleted {len(deleted_entries)} entr{'y' if len(deleted_entries) == 1 else 'ies'}")

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
        self.show_toast("Last delete has been undone")

    def save_current_qr(self, entry_id: str) -> None:
        entry = self.db.get_entry(entry_id, include_uri=not self.db.is_locked)
        if not entry:
            return
        default_name = f"{entry.name}.png"
        destination, _ = QFileDialog.getSaveFileName(self, "Save QR PNG", default_name, "PNG Image (*.png)")
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
                raise FileNotFoundError("No QR asset is available for this entry.")
            self.show_toast(f"Saved QR to {destination}")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Save QR",
                f"Could not write the QR assets to:\n{destination}\n\nCheck folder permissions and try again.\n\n{exc}",
            )

    def export_single(self, fmt: str) -> None:
        if not self.current_entry:
            QMessageBox.information(self, "Export", "Select an entry first.")
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
            f"Export {fmt.upper()}",
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
                    raise FileNotFoundError("PNG asset is unavailable while the vault is locked.")
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
                    raise FileNotFoundError("SVG asset is unavailable while the vault is locked.")
            elif fmt == "pdf":
                if entry.is_locked or not entry.uri:
                    raise AuthenticationError("Unlock ProxyVault to export a PDF with a live QR code.")
                export_entry_pdf(entry, self.settings.default_qr, destination)
            self.show_toast(f"Exported {entry.name}")
        except (AuthenticationError, OSError) as exc:
            QMessageBox.warning(self, "Export", str(exc))

    def export_selection_zip(self) -> None:
        entries = self.selected_or_visible_entries()
        if not entries:
            QMessageBox.information(self, "Export", "No entries are available to export.")
            return
        destination, _ = QFileDialog.getSaveFileName(self, "Export ZIP", "proxyvault-export.zip", "ZIP Archive (*.zip)")
        if not destination:
            return
        try:
            export_zip(entries, destination)
            self.show_toast("ZIP export created")
        except OSError as exc:
            QMessageBox.warning(self, "Export ZIP", str(exc))

    def export_booklet(self) -> None:
        if not self.ensure_unlocked("export a PDF booklet"):
            return
        entries = [entry for entry in self.selected_or_visible_entries(include_uri=True) if entry.uri]
        if not entries:
            QMessageBox.information(self, "Export Booklet", "No unlocked entries are available.")
            return
        destination, _ = QFileDialog.getSaveFileName(self, "Export PDF Booklet", "proxyvault-booklet.pdf", "PDF Document (*.pdf)")
        if not destination:
            return
        export_booklet_pdf(entries, self.settings.default_qr, destination)
        self.show_toast("PDF booklet exported")

    def export_clash(self) -> None:
        if not self.ensure_unlocked("export Clash YAML"):
            return
        entries = [entry for entry in self.selected_or_visible_entries(include_uri=True) if entry.uri]
        if not entries:
            QMessageBox.information(self, "Export Clash YAML", "No unlocked entries are available.")
            return
        destination, _ = QFileDialog.getSaveFileName(self, "Export Clash YAML", "proxyvault.yaml", "YAML File (*.yaml *.yml)")
        if not destination:
            return
        export_clash_yaml(entries, destination)
        self.show_toast("Clash YAML exported")

    def regenerate_all(self) -> None:
        if not self.ensure_unlocked("regenerate QR codes"):
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
        self.show_toast(f"Regenerated {count} QR code assets")

    def toggle_lock_state(self) -> None:
        if not self.db.has_master_password():
            QMessageBox.information(
                self,
                "Master Password",
                "Set a master password from Settings to enable encrypted storage and locking.",
            )
            self.open_settings()
            return
        if self.db.is_locked:
            if self.ensure_unlocked("unlock the vault"):
                current_id = self.current_entry.id if self.current_entry else ""
                self.refresh_library(select_id=current_id)
                self.show_toast("ProxyVault unlocked")
        else:
            self.db.lock()
            self.current_entry = None
            self.detail_panel.clear_panel()
            self.refresh_library()
            self.show_toast("ProxyVault locked")

    def ensure_unlocked(self, reason: str) -> bool:
        if not self.db.has_master_password() or not self.db.is_locked:
            return True
        dialog = PasswordDialog(f"Unlock ProxyVault to {reason}", ask_current=False, confirm_new=False, parent=self)
        if not dialog.exec():
            return False
        try:
            self.db.unlock(dialog.password)
            return True
        except AuthenticationError as exc:
            QMessageBox.warning(self, "Unlock Failed", str(exc))
            return False

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.db, self.settings, self)
        if dialog.exec():
            self.settings = dialog.values()
            self.db.save_settings(self.settings)
            self.apply_theme(self.settings.theme)
            self.refresh_library(select_id=self.current_entry.id if self.current_entry else "")
            self.show_toast("Settings saved")

    def set_view_mode(self, mode: str) -> None:
        self.card_view.set_mode(mode)
        self.view_toggle.setCurrentText("Grid" if mode == "grid" else "List")

    def toggle_details_panel(self) -> None:
        self.detail_panel.setVisible(not self.detail_panel.isVisible())

    def toggle_theme(self) -> None:
        next_theme = "dark" if self.settings.theme in {"system", "light"} else "light"
        self.settings.theme = next_theme
        self.db.save_settings(self.settings)
        self.apply_theme(next_theme)
        self.show_toast(f"Theme switched to {next_theme}")

    def apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if not app:
            return
        resolved_theme = "dark" if theme == "dark" else "light"
        app.setStyle(QStyleFactory.create("Fusion"))
        apply_app_theme(app, resolved_theme)

    def update_status_bar(self) -> None:
        self.entry_count_label.setText(f"{len(self.filtered_entries)} shown / {len(self.entries)} total")
        set_widget_status(self.entry_count_label, "statusTone", "muted")
        last_import = self.db.get_metadata("last_import_date", "never")
        self.last_import_label.setText(f"Last import: {last_import}")
        set_widget_status(self.last_import_label, "statusTone", "muted" if last_import == "never" else "success")
        if not self.db.has_master_password():
            self.lock_status_label.setText("Lock: disabled")
            set_widget_status(self.lock_status_label, "statusTone", "muted")
        else:
            self.lock_status_label.setText("Lock: locked" if self.db.is_locked else "Lock: unlocked")
            set_widget_status(self.lock_status_label, "statusTone", "warning" if self.db.is_locked else "success")
        self._update_lock_action()

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

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "About ProxyVault",
            "ProxyVault is a local-first desktop QR manager for proxy and VPN configurations.\n\nEverything is stored locally, with optional encrypted URI storage at rest.",
        )

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
            QMessageBox.information(self, "QR Preview", "No QR code is available for this entry.")
            return
        dialog = FullScreenQrDialog(entry.name, pixmap, self)
        dialog.exec()

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
                results.append({"url": subscription.url, "status": "error", "error": str(exc)})
        return results

    def _handle_subscription_refresh_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        index = int(payload.get("index", 0))
        total = int(payload.get("total", 0))
        url = str(payload.get("url", ""))
        self.statusBar().showMessage(f"Refreshing subscriptions {index}/{total}: {url}")

    def _handle_subscription_refresh_finished(self, payloads: object) -> None:
        self._take_worker_context()
        self._finish_subscription_refresh()
        results = payloads if isinstance(payloads, list) else []
        if self.db.has_master_password() and self.db.is_locked:
            if any(isinstance(item, dict) and item.get("status") == "ok" for item in results):
                self.show_toast("Unlock ProxyVault to apply auto-refreshed subscriptions.")
            return
        imported_urls: list[str] = []
        failure_messages: list[str] = []
        for payload in results:
            if not isinstance(payload, dict):
                continue
            url = str(payload.get("url", ""))
            if payload.get("status") != "ok":
                failure_messages.append(f"{url}: {payload.get('error', 'Unknown error')}")
                continue
            items = payload.get("items", [])
            if not isinstance(items, list):
                failure_messages.append(f"{url}: Invalid parsed subscription payload.")
                continue
            typed_items = [item for item in items if isinstance(item, SubscriptionImportItem)]
            imported = self.import_items(typed_items)
            self.db.update_subscription_fetch_time(url)
            if imported:
                imported_urls.append(url)
        if imported_urls:
            self.show_toast(
                f"Auto-refreshed {len(imported_urls)} subscription"
                f"{'' if len(imported_urls) == 1 else 's'}."
            )
        for message in failure_messages:
            self.show_toast(f"Subscription refresh failed: {message}", error=True)

    def _handle_subscription_refresh_error(self, exc: object) -> None:
        self._take_worker_context()
        self._finish_subscription_refresh()
        self.show_toast(f"Subscription refresh failed: {exc}", error=True)

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
                    QMessageBox.warning(self, "File Import", f"Could not read {local_path}:\n{exc}")
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
            if not self.ensure_unlocked("import dropped entries"):
                return False
            count = self.import_items(items)
            self.show_toast(f"Imported {count} dropped entries")
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

    def _set_toolbar_button_variant(self, toolbar: QToolBar, action: QAction, variant: str) -> None:
        button = toolbar.widgetForAction(action)
        if button:
            button.setProperty("variant", variant)

    def _apply_action_icons(self) -> None:
        for action, (icon_name, color) in self._action_icon_specs.items():
            apply_action_icon(action, icon_name, color=color)
        self._update_lock_action()

    def _update_lock_action(self) -> None:
        if not self.db.has_master_password():
            self.lock_action.setText("Lock")
            apply_action_icon(self.lock_action, "lock", color="#9A8A7A")
            return
        if self.db.is_locked:
            self.lock_action.setText("Unlock")
            apply_action_icon(self.lock_action, "unlock", color="#D3A247")
            return
        self.lock_action.setText("Lock")
        apply_action_icon(self.lock_action, "lock", color="#7EA67B")
