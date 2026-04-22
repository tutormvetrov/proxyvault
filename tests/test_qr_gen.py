from __future__ import annotations

import unittest

from app.models import QROptions
from app.qr_gen import build_qr, build_qr_svg


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


if __name__ == "__main__":
    unittest.main()
