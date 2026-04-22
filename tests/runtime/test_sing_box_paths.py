from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.runtime.paths import resolve_sing_box_asset_layout


class SingBoxPathResolutionTests(unittest.TestCase):
    def test_windows_layout_resolves_binary_and_support_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine_root = Path(tmp) / "engines"
            binary_dir = engine_root / "sing-box" / "windows"
            binary_dir.mkdir(parents=True, exist_ok=True)
            binary_path = binary_dir / "sing-box.exe"
            cronet_path = binary_dir / "libcronet.dll"
            binary_path.write_text("", encoding="utf-8")
            cronet_path.write_text("", encoding="utf-8")

            layout = resolve_sing_box_asset_layout(
                engine_root_dir=engine_root,
                platform_name="windows",
                required_support_files=("libcronet.dll",),
            )

            self.assertEqual(layout.binary_path, binary_path)
            self.assertEqual(layout.support_files, (cronet_path,))
            self.assertEqual(layout.binary_dir, binary_dir)

    def test_macos_layout_accepts_platform_scoped_binary_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine_root = Path(tmp) / "engines"
            binary_dir = engine_root / "macos"
            binary_dir.mkdir(parents=True, exist_ok=True)
            binary_path = binary_dir / "sing-box"
            binary_path.write_text("", encoding="utf-8")

            layout = resolve_sing_box_asset_layout(
                engine_root_dir=engine_root,
                platform_name="darwin",
            )

            self.assertEqual(layout.binary_path, binary_path)
            self.assertEqual(layout.platform_name, "macos")
            self.assertEqual(layout.support_files, ())

    def test_missing_required_support_asset_raises_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine_root = Path(tmp) / "engines"
            binary_dir = engine_root / "sing-box" / "windows"
            binary_dir.mkdir(parents=True, exist_ok=True)
            (binary_dir / "sing-box.exe").write_text("", encoding="utf-8")

            with self.assertRaises(FileNotFoundError) as context:
                resolve_sing_box_asset_layout(
                    engine_root_dir=engine_root,
                    platform_name="windows",
                    required_support_files=("libcronet.dll",),
                )

            self.assertIn("libcronet.dll", str(context.exception))


if __name__ == "__main__":
    unittest.main()
