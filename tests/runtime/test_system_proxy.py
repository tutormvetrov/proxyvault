from __future__ import annotations

import unittest

from app.runtime.enums import RuntimeEngineKind, RuntimeState, SessionStopReason
from app.runtime.models import RunningSession
from app.runtime.routing.system_proxy import CommandResult, create_system_proxy_controller


class RecordingCommandRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, command):
        self.calls.append(list(command))
        if command[:2] == ["networksetup", "-listallnetworkservices"]:
            return CommandResult(
                returncode=0,
                stdout="An asterisk (*) denotes that a network service is disabled.\nWi-Fi\nEthernet\n",
            )
        return CommandResult(returncode=0, stdout="", stderr="")


def _session() -> RunningSession:
    return RunningSession(
        session_id="proxy-session",
        entry_id="entry-1",
        entry_name="Entry 1",
        engine_kind=RuntimeEngineKind.SING_BOX,
        runtime_state=RuntimeState.RUNNING,
        http_port=18080,
    )


class SystemProxyControllerTests(unittest.TestCase):
    def test_windows_controller_builds_powershell_commands(self) -> None:
        runner = RecordingCommandRunner()
        controller = create_system_proxy_controller(platform_name="win32", runner=runner)

        controller.apply_primary_proxy(_session())
        controller.clear_system_proxy(reason=SessionStopReason.PRIMARY_SWITCH)

        self.assertEqual(runner.calls[0][0], "powershell")
        self.assertIn("ProxyServer", runner.calls[0][-1])
        self.assertIn("127.0.0.1:18080", runner.calls[0][-1])
        self.assertIn("ProxyEnable -Type DWord -Value 0", runner.calls[1][-1])

    def test_macos_controller_targets_each_enabled_network_service(self) -> None:
        runner = RecordingCommandRunner()
        controller = create_system_proxy_controller(platform_name="darwin", runner=runner)

        controller.apply_primary_proxy(_session())
        controller.clear_system_proxy(reason=SessionStopReason.ENGINE_CRASH)

        expected_prefixes = [
            ["networksetup", "-listallnetworkservices"],
            ["networksetup", "-setwebproxy", "Wi-Fi", "127.0.0.1", "18080"],
            ["networksetup", "-setsecurewebproxy", "Wi-Fi", "127.0.0.1", "18080"],
            ["networksetup", "-setwebproxystate", "Wi-Fi", "on"],
            ["networksetup", "-setsecurewebproxystate", "Wi-Fi", "on"],
            ["networksetup", "-setwebproxy", "Ethernet", "127.0.0.1", "18080"],
            ["networksetup", "-setsecurewebproxy", "Ethernet", "127.0.0.1", "18080"],
            ["networksetup", "-setwebproxystate", "Ethernet", "on"],
            ["networksetup", "-setsecurewebproxystate", "Ethernet", "on"],
        ]

        self.assertEqual(runner.calls[:9], expected_prefixes)
        self.assertIn(["networksetup", "-setwebproxystate", "Wi-Fi", "off"], runner.calls)
        self.assertIn(["networksetup", "-setsecurewebproxystate", "Ethernet", "off"], runner.calls)


if __name__ == "__main__":
    unittest.main()
