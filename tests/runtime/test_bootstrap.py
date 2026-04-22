from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import DatabaseManager
from app.runtime.bootstrap import build_runtime_manager
from app.runtime.adapters.amneziawg_macos import AmneziaWGAdapterMacOS
from app.runtime.adapters.amneziawg_windows import AmneziaWGAdapterWindows
from app.runtime.adapters.sing_box import SingBoxAdapter
from app.runtime.adapters.wireguard_macos import WireGuardAdapterMacOS
from app.runtime.adapters.wireguard_windows import WireGuardAdapterWindows
from app.runtime.routing.system_proxy import NoopSystemProxyController, SystemProxyController


class RuntimeBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = DatabaseManager(Path(self.temp_dir.name) / "proxyvault.db")
        settings = self.db.load_settings()
        settings.engine_root_dir = str(Path(self.temp_dir.name) / "engines")
        self.db.save_settings(settings)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_windows_bootstrap_registers_sing_box_and_wireguard_with_system_proxy_controller(self) -> None:
        manager = build_runtime_manager(self.db, platform_name="Windows")

        adapter_types = {type(adapter) for adapter in manager._adapters}
        self.assertIn(SingBoxAdapter, adapter_types)
        self.assertIn(WireGuardAdapterWindows, adapter_types)
        self.assertIn(AmneziaWGAdapterWindows, adapter_types)
        self.assertIsInstance(manager._route_controller, SystemProxyController)

    def test_macos_bootstrap_registers_platform_specific_wireguard_adapter(self) -> None:
        manager = build_runtime_manager(self.db, platform_name="Darwin")

        adapter_types = {type(adapter) for adapter in manager._adapters}
        self.assertIn(SingBoxAdapter, adapter_types)
        self.assertIn(WireGuardAdapterMacOS, adapter_types)
        self.assertIn(AmneziaWGAdapterMacOS, adapter_types)
        self.assertIsInstance(manager._route_controller, SystemProxyController)

    def test_linux_bootstrap_uses_noop_system_proxy_controller(self) -> None:
        manager = build_runtime_manager(self.db, platform_name="Linux")

        adapter_types = {type(adapter) for adapter in manager._adapters}
        self.assertIn(SingBoxAdapter, adapter_types)
        self.assertNotIn(WireGuardAdapterWindows, adapter_types)
        self.assertNotIn(WireGuardAdapterMacOS, adapter_types)
        self.assertNotIn(AmneziaWGAdapterWindows, adapter_types)
        self.assertNotIn(AmneziaWGAdapterMacOS, adapter_types)
        self.assertIsInstance(manager._route_controller, NoopSystemProxyController)


if __name__ == "__main__":
    unittest.main()
