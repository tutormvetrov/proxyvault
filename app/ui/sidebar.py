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

from app.models import ProxyType, TYPE_COLORS, TYPE_LABELS
from app.ui.theme import apply_button_icon


class Sidebar(QWidget):
    filtersChanged = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.type_checkboxes: dict[ProxyType, QCheckBox] = {}
        self.type_rows: dict[ProxyType, QFrame] = {}
        self.tag_buttons: dict[str, QToolButton] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        self.setMinimumWidth(200)
        self.setMaximumWidth(260)
        self.setObjectName("sidebarPanel")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        title = QLabel("Filters")
        title.setProperty("role", "sectionTitle")
        root.addWidget(title)

        self.favorite_only = QCheckBox("Favorites only")
        self.favorite_only.toggled.connect(self._emit_filters_changed)
        root.addWidget(self.favorite_only)

        type_frame = QFrame()
        type_frame.setObjectName("sidebarGroup")
        type_layout = QVBoxLayout(type_frame)
        type_layout.setContentsMargins(10, 10, 10, 10)
        type_layout.setSpacing(8)
        type_title = QLabel("Types")
        type_title.setProperty("role", "subSectionTitle")
        type_layout.addWidget(type_title)
        for proxy_type in ProxyType:
            checkbox = QCheckBox(TYPE_LABELS[proxy_type])
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
        tag_title = QLabel("Tags")
        tag_title.setProperty("role", "subSectionTitle")
        tag_header.addWidget(tag_title)
        clear_button = QPushButton("Clear")
        clear_button.setProperty("variant", "subtle")
        clear_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        clear_button.clicked.connect(self.clear_tags)
        apply_button_icon(clear_button, "reset", color="#D8943C")
        tag_header.addWidget(clear_button)
        root.addLayout(tag_header)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.tag_host = QWidget()
        self.tag_layout = QVBoxLayout(self.tag_host)
        self.tag_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_layout.setSpacing(6)
        scroll_area.setWidget(self.tag_host)
        root.addWidget(scroll_area, 1)

        reset_button = QPushButton("Reset Filters")
        reset_button.setProperty("variant", "subtle")
        reset_button.clicked.connect(self.reset_filters)
        apply_button_icon(reset_button, "filter", color="#D8943C")
        root.addWidget(reset_button)

    def update_tags(self, tags: list[str]) -> None:
        while self.tag_layout.count():
            item = self.tag_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.tag_buttons.clear()

        if not tags:
            placeholder = QLabel("No tags yet")
            placeholder.setProperty("role", "muted")
            self.tag_layout.addWidget(placeholder)
            self.tag_layout.addStretch(1)
            return

        for tag in sorted(tags, key=str.lower):
            button = QToolButton()
            button.setObjectName("tagChip")
            button.setText(tag)
            button.setCheckable(True)
            button.setToolButtonStyle(button.toolButtonStyle())
            button.toggled.connect(self._emit_filters_changed)
            self.tag_buttons[tag] = button
            self.tag_layout.addWidget(button)
        self.tag_layout.addStretch(1)

    def _emit_filters_changed(self, _checked: bool = False) -> None:
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
        return self.favorite_only.isChecked()
