from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from app.models import ProxyEntry, ProxyType, QROptions
from app.qr_gen import build_qr, build_qr_svg, export_clash_yaml


class QrGenerationTests(unittest.TestCase):
    def test_build_qr_returns_image(self) -> None:
        image = build_qr("https://example.com", QROptions(box_size=6, border=2))
        self.assertGreater(image.width, 0)
        self.assertGreater(image.height, 0)

    def test_svg_output_keeps_configured_colors(self) -> None:
        options = QROptions(fg_color="#123456", bg_color="#F5E9DA")
        svg = build_qr_svg("https://example.com", options).decode("utf-8")

        self.assertIn('fill_color="#123456"', svg)
        self.assertIn('back_color="#F5E9DA"', svg)

    def test_clash_export_keeps_lan_access_disabled(self) -> None:
        entry = ProxyEntry(
            id="trojan",
            name="Trojan",
            uri="trojan://secret@trojan.example.com:443?sni=cdn.example.com#Trojan",
            type=ProxyType.TROJAN,
            transport="tcp+tls",
            server_host="trojan.example.com",
            server_port=443,
        )
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "proxyvault.yaml"
            export_clash_yaml([entry], str(destination))

            payload = destination.read_text(encoding="utf-8")

        self.assertIn("allow-lan: false", payload)


if __name__ == "__main__":
    unittest.main()
