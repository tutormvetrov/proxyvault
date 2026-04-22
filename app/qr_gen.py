from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Iterable

import qrcode
import qrcode.image.svg
from PIL import Image
from PyQt6.QtCore import QMarginsF, QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter, QPageLayout, QPageSize, QPdfWriter, QPixmap

from app.models import ProxyEntry, QROptions, TYPE_LABELS
from app.parser import build_clash_proxy


ERROR_LEVELS = {
    "L": qrcode.constants.ERROR_CORRECT_L,
    "M": qrcode.constants.ERROR_CORRECT_M,
    "Q": qrcode.constants.ERROR_CORRECT_Q,
    "H": qrcode.constants.ERROR_CORRECT_H,
}


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return cleaned.strip("._") or "proxy"


def default_qr_path(output_folder: str, entry: ProxyEntry) -> Path:
    filename = sanitize_filename(entry.name)
    return Path(output_folder) / entry.type.value.lower() / f"{filename}.png"


def build_qr(uri: str, options: QROptions) -> Image.Image:
    qr = qrcode.QRCode(
        version=options.version or None,
        error_correction=ERROR_LEVELS.get(options.error_correction, qrcode.constants.ERROR_CORRECT_M),
        box_size=options.box_size,
        border=options.border,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    return qr.make_image(fill_color=options.fg_color, back_color=options.bg_color).convert("RGBA")


def build_qr_svg(uri: str, options: QROptions) -> bytes:
    qr = qrcode.QRCode(
        version=options.version or None,
        error_correction=ERROR_LEVELS.get(options.error_correction, qrcode.constants.ERROR_CORRECT_M),
        box_size=options.box_size,
        border=options.border,
        image_factory=qrcode.image.svg.SvgImage,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    image = qr.make_image(fill_color=options.fg_color, back_color=options.bg_color)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue()


def save_qr_assets(entry: ProxyEntry, options: QROptions, output_folder: str, target_path: str = "") -> tuple[str, str]:
    png_path = Path(target_path) if target_path else default_qr_path(output_folder, entry)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    image = build_qr(entry.uri, options)
    image.save(png_path, format="PNG")
    svg_path = png_path.with_suffix(".svg")
    svg_path.write_bytes(build_qr_svg(entry.uri, options))
    return str(png_path), str(svg_path)


def pil_to_qimage(image: Image.Image) -> QImage:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    return QImage(data, image.width, image.height, QImage.Format.Format_RGBA8888).copy()


def qr_pixmap(uri: str, options: QROptions, max_size: int = 240) -> QPixmap:
    qimage = pil_to_qimage(build_qr(uri, options))
    pixmap = QPixmap.fromImage(qimage)
    return pixmap.scaled(max_size, max_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def copy_pixmap_to_clipboard(pixmap: QPixmap) -> None:
    clipboard = QGuiApplication.clipboard()
    clipboard.setPixmap(pixmap)


def export_entry_pdf(entry: ProxyEntry, options: QROptions, destination: str) -> str:
    writer = QPdfWriter(destination)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(14, 14, 14, 14))
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    render_pdf_card(painter, entry, options, writer.width(), writer.height())
    painter.end()
    return destination


def export_booklet_pdf(entries: Iterable[ProxyEntry], options: QROptions, destination: str) -> str:
    writer = QPdfWriter(destination)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait, QMarginsF(14, 14, 14, 14)))
    painter = QPainter(writer)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    width = writer.width()
    height = writer.height()
    for index, entry in enumerate(entries):
        if index:
            writer.newPage()
        render_pdf_card(painter, entry, options, width, height)
    painter.end()
    return destination


def render_pdf_card(painter: QPainter, entry: ProxyEntry, options: QROptions, page_width: int, page_height: int) -> None:
    margin = 120
    qr_rect = QRectF(margin, margin, 900, 900)
    qimage = pil_to_qimage(build_qr(entry.uri, options))
    painter.drawImage(qr_rect, qimage)
    text_x = qr_rect.right() + 80
    line_y = margin + 40
    painter.setPen(Qt.GlobalColor.black)
    title_font = painter.font()
    title_font.setPointSize(18)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(int(text_x), int(line_y), entry.name)

    body_font = painter.font()
    body_font.setPointSize(11)
    body_font.setBold(False)
    painter.setFont(body_font)
    line_y += 80
    for line in [
        f"Type: {TYPE_LABELS.get(entry.type, entry.type.value)}",
        f"Endpoint: {entry.display_host_port}",
        f"Transport: {entry.transport or 'n/a'}",
        f"Tags: {entry.tags or 'n/a'}",
        f"Expiry: {entry.expiry_date or 'n/a'}",
        "",
        "Notes:",
        entry.notes or "No notes",
    ]:
        painter.drawText(
            QRectF(text_x, line_y, page_width - text_x - margin, 300),
            int(Qt.AlignmentFlag.AlignLeft),
            line,
        )
        line_y += 48


def export_zip(entries: Iterable[ProxyEntry], destination: str) -> str:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            if not entry.qr_png_path:
                continue
            png_path = Path(entry.qr_png_path)
            if not png_path.exists():
                continue
            archive.write(png_path, arcname=f"{entry.type.value.lower()}/{png_path.name}")
            svg_path = png_path.with_suffix(".svg")
            if svg_path.exists():
                archive.write(svg_path, arcname=f"{entry.type.value.lower()}/{svg_path.name}")
    return destination


def export_clash_yaml(entries: Iterable[ProxyEntry], destination: str) -> str:
    import yaml

    proxies = [build_clash_proxy(entry.name, entry.uri) for entry in entries]
    payload = {
        "mixed-port": 7890,
        "allow-lan": True,
        "mode": "rule",
        "proxies": proxies,
    }
    Path(destination).write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return destination
