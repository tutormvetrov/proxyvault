from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import format_proxy_type, tr
from app.models import ProxyType, TYPE_COLORS
from app.ui.i18n_patch import ensure_ui_translations
from app.ui.theme import apply_button_icon


class Sidebar(QWidget):
    filtersChanged = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        ensure_ui_translations()
        self.type_checkboxes: dict[ProxyType, QCheckBox] = {}
        self.type_rows: dict[ProxyType, QFrame] = {}
        self.tag_buttons: dict[str, QToolButton] = {}
        self.title_label: QLabel | None = None
        self.summary_title: QLabel | None = None
        self.summary_body: QLabel | None = None
        self.summary_meta: QLabel | None = None
        self.favorite_only: QCheckBox | None = None
        self.type_title: QLabel | None = None
        self.tag_title: QLabel | None = None
        self.clear_button: QPushButton | None = None
        self.reset_button: QPushButton | None = None
        self._tags_placeholder: QLabel | None = None
        self._build_ui()
        self.retranslate_ui()

    def _build_ui(self) -> None:
        self.setMinimumWidth(200)
        self.setMaximumWidth(260)
        self.setObjectName("sidebarPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        self.title_label = QLabel("")
        self.title_label.setProperty("role", "sectionTitle")
        root.addWidget(self.title_label)

        summary_card = QFrame()
        summary_card.setObjectName("sidebarSummaryCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        summary_layout.setSpacing(4)
        self.summary_title = QLabel("")
        self.summary_title.setObjectName("sidebarSummaryTitle")
        self.summary_body = QLabel("")
        self.summary_body.setObjectName("sidebarSummaryBody")
        self.summary_body.setWordWrap(True)
        self.summary_meta = QLabel("")
        self.summary_meta.setObjectName("sidebarSummaryMeta")
        summary_layout.addWidget(self.summary_title)
        summary_layout.addWidget(self.summary_body)
        summary_layout.addWidget(self.summary_meta)
        root.addWidget(summary_card)

        self.favorite_only = QCheckBox("")
        self.favorite_only.toggled.connect(self._emit_filters_changed)
        root.addWidget(self.favorite_only)

        type_frame = QFrame()
        type_frame.setObjectName("sidebarGroup")
        type_layout = QVBoxLayout(type_frame)
        type_layout.setContentsMargins(10, 10, 10, 10)
        type_layout.setSpacing(8)
        self.type_title = QLabel("")
        self.type_title.setProperty("role", "subSectionTitle")
        type_layout.addWidget(self.type_title)
        for proxy_type in ProxyType:
            checkbox = QCheckBox("")
            checkbox.setChecked(True)
            checkbox.toggled.connect(lambda checked, pt=proxy_type: self._on_type_toggled(pt, checked))
            checkbox.setProperty("typeFilter", True)
            row = QFrame()
            row.setObjectName("typeFilterRow")
            row.setProperty("checked", True)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 6, 8, 6)
            row_layout.setSpacing(8)
            dot = QLabel()
            dot.setObjectName("typeDot")
            dot.setStyleSheet(f"QLabel#typeDot {{ background: {TYPE_COLORS[proxy_type]}; }}")
            row_layout.addWidget(dot, 0)
            row_layout.addWidget(checkbox, 1)
            self.type_checkboxes[proxy_type] = checkbox
            self.type_rows[proxy_type] = row
            type_layout.addWidget(row)
        root.addWidget(type_frame)

        tag_header = QHBoxLayout()
        tag_header.setSpacing(8)
        self.tag_title = QLabel("")
        self.tag_title.setProperty("role", "subSectionTitle")
        tag_header.addWidget(self.tag_title)
        self.clear_button = QPushButton("")
        self.clear_button.setProperty("variant", "subtle")
        self.clear_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.clear_button.clicked.connect(self.clear_tags)
        apply_button_icon(self.clear_button, "reset", color="#D8943C")
        tag_header.addWidget(self.clear_button)
        root.addLayout(tag_header)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.tag_host = QWidget()
        self.tag_layout = QVBoxLayout(self.tag_host)
        self.tag_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_layout.setSpacing(6)
        scroll_area.setWidget(self.tag_host)
        root.addWidget(scroll_area, 1)

        self.reset_button = QPushButton("")
        self.reset_button.setProperty("variant", "subtle")
        self.reset_button.clicked.connect(self.reset_filters)
        apply_button_icon(self.reset_button, "filter", color="#D8943C")
        root.addWidget(self.reset_button)

    def retranslate_ui(self) -> None:
        ensure_ui_translations()
        if self.title_label:
            self.title_label.setText(tr("sidebar.filters.title"))
        if self.favorite_only:
            self.favorite_only.setText(tr("sidebar.filters.favorites_only"))
        if self.type_title:
            self.type_title.setText(tr("sidebar.filters.types"))
        if self.tag_title:
            self.tag_title.setText(tr("sidebar.filters.tags"))
        if self.summary_title:
            self.summary_title.setText(tr("sidebar.summary.title"))
        if self.clear_button:
            self.clear_button.setText(tr("sidebar.filters.clear_tags"))
        if self.reset_button:
            self.reset_button.setText(tr("sidebar.filters.reset"))
        for proxy_type, checkbox in self.type_checkboxes.items():
            checkbox.setText(format_proxy_type(proxy_type))
        if self._tags_placeholder is not None:
            self._tags_placeholder.setText(tr("sidebar.filters.no_tags"))
        self._update_summary()

    def update_tags(self, tags: list[str]) -> None:
        while self.tag_layout.count():
            item = self.tag_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.tag_buttons.clear()
        self._tags_placeholder = None

        if not tags:
            placeholder = QLabel(tr("sidebar.filters.no_tags"))
            placeholder.setProperty("role", "muted")
            self.tag_layout.addWidget(placeholder)
            self.tag_layout.addStretch(1)
            self._tags_placeholder = placeholder
            self._update_summary()
            return

        for tag in sorted(tags, key=str.lower):
            button = QToolButton()
            button.setObjectName("tagChip")
            button.setText(tag)
            button.setCheckable(True)
            button.toggled.connect(self._emit_filters_changed)
            self.tag_buttons[tag] = button
            self.tag_layout.addWidget(button)
        self.tag_layout.addStretch(1)
        self._update_summary()

    def _emit_filters_changed(self, _checked: bool = False) -> None:
        self._update_summary()
        self.filtersChanged.emit()

    def _on_type_toggled(self, proxy_type: ProxyType, checked: bool) -> None:
        row = self.type_rows.get(proxy_type)
        if row:
            row.setProperty("checked", checked)
            row.style().unpolish(row)
            row.style().polish(row)
            row.update()
        self.filtersChanged.emit()

    def clear_tags(self) -> None:
        for button in self.tag_buttons.values():
            button.setChecked(False)
        self.filtersChanged.emit()

    def reset_filters(self) -> None:
        if self.favorite_only:
            self.favorite_only.setChecked(False)
        for checkbox in self.type_checkboxes.values():
            checkbox.setChecked(True)
        self.clear_tags()
        self.filtersChanged.emit()

    def selected_types(self) -> set[ProxyType]:
        return {proxy_type for proxy_type, checkbox in self.type_checkboxes.items() if checkbox.isChecked()}

    def selected_tags(self) -> set[str]:
        return {tag for tag, button in self.tag_buttons.items() if button.isChecked()}

    def favorite_filter_enabled(self) -> bool:
        return bool(self.favorite_only and self.favorite_only.isChecked())

    def _update_summary(self) -> None:
        if self.summary_body is None or self.summary_meta is None:
            return
        selected_type_count = len(self.selected_types())
        total_types = len(self.type_checkboxes)
        selected_tag_count = len(self.selected_tags())

        if self.favorite_filter_enabled():
            body = tr("sidebar.summary.favorites")
        elif selected_type_count != total_types or selected_tag_count:
            body = tr("sidebar.summary.filtered")
        else:
            body = tr("sidebar.summary.all_entries")

        self.summary_body.setText(body)
        self.summary_meta.setText(
            tr(
                "sidebar.summary.meta",
                types=selected_type_count,
                total=total_types,
                tags=selected_tag_count,
            )
        )
