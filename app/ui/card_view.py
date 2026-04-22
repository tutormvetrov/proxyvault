from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models import ProxyEntry, TYPE_COLORS, TYPE_LABELS, TYPE_SOFT_COLORS, TYPE_TEXT_COLORS
from app.ui.theme import refresh_widget_style


def _placeholder_pixmap(text: str, size: int = 96) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#F7F0E6"))
    painter.setPen(QColor("#DED2C4"))
    painter.drawRoundedRect(0, 0, size - 1, size - 1, 16, 16)
    painter.setPen(QColor("#6E6258"))
    font = painter.font()
    font.setPointSize(17)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), text[:2].upper())
    painter.end()
    return pixmap


def _compact_text(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "..."


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _primary_support_text(entry: ProxyEntry) -> str:
    title = _normalized(entry.name)
    host = _normalized(entry.server_host)
    host_port = _normalized(entry.display_host_port)
    if not title:
        return entry.display_host_port
    if title == host and entry.server_port:
        return f"Port {entry.server_port}"
    if title == host_port and entry.server_host:
        return f"Host {entry.server_host}"
    return entry.display_host_port


class EntryCardWidget(QFrame):
    def __init__(self, entry: ProxyEntry, mode: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.entry = entry
        self.mode = mode
        self.setObjectName("entryCard")
        self.setProperty("selected", False)
        self.setProperty("problem", entry.expires_soon)
        self.setProperty("muted", entry.is_locked)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._hovered = False
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 4)
        self.setGraphicsEffect(self._shadow)
        self._build_ui()
        self._update_shadow()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        thumb_frame = QFrame()
        thumb_frame.setObjectName("cardQrWell")
        thumb_frame.setFixedSize(108, 96)
        thumb_layout = QVBoxLayout(thumb_frame)
        thumb_layout.setContentsMargins(9, 9, 9, 9)
        thumb_layout.setSpacing(0)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setObjectName("cardQrImage")
        thumb.setFixedSize(78, 78)
        pixmap = (
            QPixmap(self.entry.qr_png_path)
            if self.entry.qr_png_path and Path(self.entry.qr_png_path).exists()
            else _placeholder_pixmap(self.entry.type.value)
        )
        thumb.setPixmap(
            pixmap.scaled(78, 78, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        thumb_layout.addWidget(thumb)
        header_row.addWidget(thumb_frame, 0, Qt.AlignmentFlag.AlignTop)

        header_info = QVBoxLayout()
        header_info.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        display_name = _compact_text(self.entry.name or self.entry.display_host_port, 28 if self.mode == "grid" else 44)
        name_label = QLabel(display_name)
        name_label.setObjectName("cardTitle")
        name_label.setToolTip(self.entry.name)
        top_row.addWidget(name_label, 1)

        if self.entry.is_favorite:
            star = QLabel("★")
            star.setObjectName("favoritePill")
            star.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top_row.addWidget(star)
        header_info.addLayout(top_row)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        chip_row.setContentsMargins(0, 0, 0, 0)

        badge = QLabel(TYPE_LABELS.get(self.entry.type, self.entry.type.value))
        badge.setObjectName("typeBadge")
        badge.setStyleSheet(
            "QLabel#typeBadge {"
            "padding: 1px 8px;"
            "min-height: 20px;"
            "border-radius: 10px;"
            "font-size: 11px;"
            "font-weight: 700;"
            f"background: {TYPE_SOFT_COLORS[self.entry.type]};"
            f"color: {TYPE_TEXT_COLORS[self.entry.type]};"
            f"border: 1px solid {TYPE_COLORS[self.entry.type]};"
            "}"
        )
        chip_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        chip_row.addStretch(1)
        header_info.addLayout(chip_row)

        primary_support = QLabel(_compact_text(_primary_support_text(self.entry), 28 if self.mode == "grid" else 42))
        primary_support.setObjectName("cardEndpoint")
        primary_support.setToolTip(self.entry.display_host_port)
        header_info.addWidget(primary_support)

        transport = QLabel(_compact_text(self.entry.transport or "transport unknown", 24 if self.mode == "grid" else 36))
        transport.setObjectName("cardMetaPrimary")
        transport.setToolTip(self.entry.transport or "transport unknown")
        header_info.addWidget(transport)

        if self.entry.tags:
            tags = QLabel(_compact_text(self.entry.tags, 26 if self.mode == "grid" else 42))
            tags.setToolTip(self.entry.tags)
            tags.setObjectName("cardTags")
            header_info.addWidget(tags)

        header_row.addLayout(header_info, 1)
        root.addLayout(header_row)

        reachability_row = QHBoxLayout()
        reachability_row.setSpacing(8)
        reachability = QLabel(self.entry.reachability_card_label)
        reachability.setObjectName("cardStatusPill")
        reachability.setProperty("statusTone", self.entry.reachability_tone)
        reachability_row.addWidget(reachability, 0, Qt.AlignmentFlag.AlignLeft)

        freshness = QLabel(self.entry.reachability_card_hint)
        freshness.setObjectName("cardStatusHint")
        reachability_row.addWidget(freshness, 1)
        root.addLayout(reachability_row)

        if self.entry.expires_soon:
            warning = QLabel(f"Expires soon: {self.entry.expiry_date}")
            warning.setObjectName("warningPill")
            root.addWidget(warning, 0, Qt.AlignmentFlag.AlignLeft)
        elif self.entry.expiry_date:
            expiry = QLabel(f"Expiry: {self.entry.expiry_date}")
            expiry.setObjectName("cardMetaSecondary")
            root.addWidget(expiry)

        root.addStretch(1)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        refresh_widget_style(self)
        self._update_shadow()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self._update_shadow()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self._update_shadow()
        super().leaveEvent(event)

    def _update_shadow(self) -> None:
        if self.property("selected"):
            self._shadow.setBlurRadius(30)
            self._shadow.setOffset(0, 12)
            self._shadow.setColor(QColor(226, 162, 74, 54))
            return
        if self._hovered:
            self._shadow.setBlurRadius(24)
            self._shadow.setOffset(0, 8)
            self._shadow.setColor(QColor(86, 58, 30, 28))
            return
        self._shadow.setBlurRadius(18)
        self._shadow.setOffset(0, 4)
        self._shadow.setColor(QColor(86, 58, 30, 18))


class CardView(QWidget):
    entrySelected = pyqtSignal(str)
    entryActivated = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = "grid"
        self.entries: list[ProxyEntry] = []
        self.setObjectName("cardViewRoot")
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("cardList")
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.itemSelectionChanged.connect(self._emit_selection)
        self.list_widget.itemDoubleClicked.connect(self._emit_activation)
        self._configure_list()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list_widget)

    def _configure_list(self) -> None:
        if self.mode == "grid":
            self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setSpacing(14)
            self.list_widget.setWrapping(True)
            self.list_widget.setMovement(QListWidget.Movement.Static)
        else:
            self.list_widget.setViewMode(QListWidget.ViewMode.ListMode)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setSpacing(10)
            self.list_widget.setWrapping(False)
            self.list_widget.setMovement(QListWidget.Movement.Static)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._configure_list()
        current_ids = self.selected_ids()
        self.set_entries(self.entries, selected_ids=current_ids)

    def set_entries(self, entries: list[ProxyEntry], selected_ids: list[str] | None = None) -> None:
        self.entries = list(entries)
        selected_ids = selected_ids or []
        self.list_widget.clear()
        for entry in entries:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setSizeHint(QSize(286, 168) if self.mode == "grid" else QSize(448, 124))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, EntryCardWidget(entry, self.mode))
            if entry.id in selected_ids:
                item.setSelected(True)
        self._sync_selection_states()

    def selected_ids(self) -> list[str]:
        return [str(item.data(Qt.ItemDataRole.UserRole)) for item in self.list_widget.selectedItems()]

    def current_id(self) -> str:
        item = self.list_widget.currentItem()
        if not item:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole))

    def select_entry(self, entry_id: str) -> None:
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole)) != entry_id:
                continue
            self.list_widget.setCurrentItem(item)
            item.setSelected(True)
            self._sync_selection_states()
            return

    def _emit_selection(self) -> None:
        self._sync_selection_states()
        current_id = self.current_id()
        if current_id:
            self.entrySelected.emit(current_id)

    def _emit_activation(self, item: QListWidgetItem) -> None:
        self.entryActivated.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    def _sync_selection_states(self) -> None:
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            widget = self.list_widget.itemWidget(item)
            if isinstance(widget, EntryCardWidget):
                widget.set_selected(item.isSelected())
