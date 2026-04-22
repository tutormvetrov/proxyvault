from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_plus(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.8))
    p.drawLine(QPointF(9, 4.5), QPointF(9, 13.5))
    p.drawLine(QPointF(4.5, 9), QPointF(13.5, 9))


def _draw_download(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.8))
    p.drawLine(QPointF(9, 3.5), QPointF(9, 10.5))
    p.drawLine(QPointF(6.2, 7.9), QPointF(9, 10.7))
    p.drawLine(QPointF(11.8, 7.9), QPointF(9, 10.7))
    p.drawLine(QPointF(4.2, 13.2), QPointF(13.8, 13.2))


def _draw_upload(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.8))
    p.drawLine(QPointF(9, 12.8), QPointF(9, 5.5))
    p.drawLine(QPointF(6.2, 8.2), QPointF(9, 5.3))
    p.drawLine(QPointF(11.8, 8.2), QPointF(9, 5.3))
    p.drawLine(QPointF(4.2, 13.5), QPointF(13.8, 13.5))


def _draw_lock(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4.4, 8.2, 9.2, 6.6), 2.4, 2.4)
    path = QPainterPath()
    path.moveTo(6.2, 8.3)
    path.cubicTo(6.2, 5.3, 7.4, 3.8, 9, 3.8)
    path.cubicTo(10.6, 3.8, 11.8, 5.3, 11.8, 8.3)
    p.drawPath(path)


def _draw_unlock(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(4.4, 8.2, 9.2, 6.6), 2.4, 2.4)
    path = QPainterPath()
    path.moveTo(6.2, 8.3)
    path.cubicTo(6.2, 5.4, 7.3, 4.1, 8.8, 4.1)
    path.cubicTo(10.1, 4.1, 10.9, 4.8, 11.6, 5.8)
    p.drawPath(path)


def _draw_sun(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    p.drawEllipse(QRectF(5.4, 5.4, 7.2, 7.2))
    rays = [
        (9, 1.8, 9, 3.5),
        (9, 14.5, 9, 16.2),
        (1.8, 9, 3.5, 9),
        (14.5, 9, 16.2, 9),
        (4.1, 4.1, 5.2, 5.2),
        (12.8, 12.8, 13.9, 13.9),
        (12.8, 5.2, 13.9, 4.1),
        (4.1, 13.9, 5.2, 12.8),
    ]
    for x1, y1, x2, y2 in rays:
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _draw_search(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.8))
    p.drawEllipse(QRectF(3.5, 3.5, 7.8, 7.8))
    p.drawLine(QPointF(10.0, 10.0), QPointF(14.0, 14.0))


def _draw_grid(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.5))
    for x in (3.8, 9.3):
        for y in (3.8, 9.3):
            p.drawRoundedRect(QRectF(x, y, 4.7, 4.7), 1.2, 1.2)


def _draw_list(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    for y in (5.2, 9.0, 12.8):
        p.drawLine(QPointF(4.0, y), QPointF(13.8, y))
        p.drawPoint(QPointF(2.5, y))


def _draw_reset(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    path = QPainterPath()
    path.moveTo(13.6, 6.9)
    path.cubicTo(12.6, 4.6, 10.6, 3.6, 8.6, 3.8)
    path.cubicTo(5.5, 4.1, 3.3, 6.5, 3.4, 9.3)
    path.cubicTo(3.6, 12.3, 5.8, 14.3, 8.8, 14.3)
    path.cubicTo(10.5, 14.3, 12.0, 13.6, 13.2, 12.3)
    p.drawPath(path)
    p.drawLine(QPointF(13.7, 6.9), QPointF(13.4, 3.7))
    p.drawLine(QPointF(13.7, 6.9), QPointF(10.6, 6.4))


def _draw_copy(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(6.2, 3.6, 7.0, 8.2), 1.8, 1.8)
    p.drawRoundedRect(QRectF(3.4, 6.2, 7.0, 8.2), 1.8, 1.8)


def _draw_qr(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(2.8, 2.8, 4.2, 4.2), 1.0, 1.0)
    p.drawRoundedRect(QRectF(11.0, 2.8, 4.2, 4.2), 1.0, 1.0)
    p.drawRoundedRect(QRectF(2.8, 11.0, 4.2, 4.2), 1.0, 1.0)
    p.drawPoint(QPointF(10.5, 10.5))
    p.drawPoint(QPointF(12.6, 10.5))
    p.drawPoint(QPointF(10.5, 12.6))
    p.drawPoint(QPointF(13.7, 13.7))


def _draw_pulse(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    path = QPainterPath()
    path.moveTo(2.4, 9.2)
    path.lineTo(5.0, 9.2)
    path.lineTo(6.6, 6.1)
    path.lineTo(8.8, 12.6)
    path.lineTo(10.6, 8.1)
    path.lineTo(13.4, 8.1)
    p.drawPath(path)


def _draw_trash(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(5.0, 4.8), QPointF(13.0, 4.8))
    p.drawLine(QPointF(6.4, 4.8), QPointF(7.0, 3.6))
    p.drawLine(QPointF(11.6, 4.8), QPointF(11.0, 3.6))
    p.drawRoundedRect(QRectF(5.8, 5.0, 6.4, 9.0), 1.6, 1.6)
    p.drawLine(QPointF(8.0, 7.0), QPointF(8.0, 11.8))
    p.drawLine(QPointF(10.0, 7.0), QPointF(10.0, 11.8))


def _draw_save(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3.3, 3.3, 11.4, 11.4), 2.0, 2.0)
    p.drawLine(QPointF(5.5, 5.7), QPointF(11.7, 5.7))
    p.drawLine(QPointF(6.2, 11.5), QPointF(11.8, 11.5))
    p.drawLine(QPointF(11.6, 3.8), QPointF(11.6, 7.2))


def _draw_folder(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(3.0, 6.0)
    path.lineTo(7.0, 6.0)
    path.lineTo(8.2, 4.5)
    path.lineTo(14.2, 4.5)
    path.lineTo(14.2, 13.6)
    path.lineTo(3.0, 13.6)
    path.closeSubpath()
    p.drawPath(path)


def _draw_star(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    path.moveTo(9.0, 2.7)
    path.lineTo(10.9, 6.7)
    path.lineTo(15.2, 7.2)
    path.lineTo(12.0, 10.1)
    path.lineTo(12.8, 14.3)
    path.lineTo(9.0, 12.2)
    path.lineTo(5.2, 14.3)
    path.lineTo(6.0, 10.1)
    path.lineTo(2.8, 7.2)
    path.lineTo(7.1, 6.7)
    path.closeSubpath()
    p.drawPath(path)


def _draw_filter(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.7))
    path = QPainterPath()
    path.moveTo(3.0, 4.2)
    path.lineTo(15.0, 4.2)
    path.lineTo(10.4, 9.0)
    path.lineTo(10.4, 13.4)
    path.lineTo(7.6, 12.0)
    path.lineTo(7.6, 9.0)
    path.closeSubpath()
    p.drawPath(path)


def _draw_settings(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.55))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(6.0, 6.0, 6.0, 6.0))
    spokes = [
        (9.0, 1.9, 9.0, 4.0),
        (9.0, 14.0, 9.0, 16.1),
        (1.9, 9.0, 4.0, 9.0),
        (14.0, 9.0, 16.1, 9.0),
        (4.1, 4.1, 5.5, 5.5),
        (12.5, 12.5, 13.9, 13.9),
        (12.5, 5.5, 13.9, 4.1),
        (4.1, 13.9, 5.5, 12.5),
    ]
    for x1, y1, x2, y2 in spokes:
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _draw_panel(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.55))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(2.8, 3.3, 12.4, 11.4), 2.0, 2.0)
    p.drawLine(QPointF(10.6, 3.9), QPointF(10.6, 14.1))
    p.drawLine(QPointF(4.5, 6.2), QPointF(8.7, 6.2))
    p.drawLine(QPointF(4.5, 9.0), QPointF(8.7, 9.0))
    p.drawLine(QPointF(4.5, 11.8), QPointF(7.4, 11.8))


def _draw_info(p: QPainter, c: QColor) -> None:
    p.setPen(_pen(c, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(3.0, 3.0, 12.0, 12.0))
    p.drawPoint(QPointF(9.0, 5.6))
    p.drawLine(QPointF(9.0, 8.0), QPointF(9.0, 12.3))


DRAWERS = {
    "add": _draw_plus,
    "import": _draw_download,
    "export": _draw_upload,
    "lock": _draw_lock,
    "unlock": _draw_unlock,
    "theme": _draw_sun,
    "search": _draw_search,
    "grid": _draw_grid,
    "list": _draw_list,
    "reset": _draw_reset,
    "copy": _draw_copy,
    "qr": _draw_qr,
    "reachability": _draw_pulse,
    "delete": _draw_trash,
    "save": _draw_save,
    "folder": _draw_folder,
    "favorite": _draw_star,
    "filter": _draw_filter,
    "settings": _draw_settings,
    "details": _draw_panel,
    "info": _draw_info,
}


@lru_cache(maxsize=256)
def icon(name: str, color: str = "#6E6258", size: int = 18) -> QIcon:
    painter_fn = DRAWERS.get(name)
    if painter_fn is None:
        raise ValueError(f"Unsupported icon name: {name}")
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 18.0, size / 18.0)
    painter_fn(painter, QColor(color))
    painter.end()
    return QIcon(pixmap)
