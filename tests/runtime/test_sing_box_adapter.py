from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models import ProxyEntry
from app.parser import parse_proxy_text
from app.runtime.adapters.sing_box import SingBoxAdapter, SingBoxAssetError
from app.runtime.enums import RuntimeState, SessionStopReason
from app.runtime.models import RuntimePrefs
from app.runtime.paths import SingBoxAssetLayout


def _entry_from_uri(uri: str, *, name: str = "entry") -> ProxyEntry:
    parsed = parse_proxy_text(uri)
    return ProxyEntry(
        id=name,
        name=name,
        uri=uri,
        type=parsed.type,
        transport=parsed.transport,
        server_host=parsed.server_host,
        server_port=parsed.server_port,
    )


class FakeProcess:
    def __init__(self, *, pid: int = 4242, exit_code: int | None = None) -> None:
        self.pid = pid
        self.exit_code = exit_code
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls: list[float | None] = []

    def poll(self) -> int | None:
        return self.exit_code

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        return 0 if self.exit_code is None else self.exit_code

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.exit_code = 0

    def kill(self) -> None:
        self.kill_calls += 1
        self.exit_code = 0


class FakeProcessRunner:
    def __init__(self, *processes: FakeProcess) -> None:
        self.processes = list(processes)
        self.calls: list[tuple[list[str], str]] = []

    def popen(self, command, *, cwd, env=None):
        self.calls.append((list(command), str(cwd)))
        return self.processes.pop(0)


class SingBoxAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime_root = self.root / "runtime"
        self.generated_dir = self.runtime_root / "generated"
        self.logs_dir = self.runtime_root / "logs"
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.binary_dir = self.root / "engines" / "sing-box" / "windows"
        self.binary_dir.mkdir(parents=True, exist_ok=True)
        self.binary_path = self.binary_dir / "sing-box.exe"
        self.binary_path.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _patch_runtime_dirs(self):
        return patch(
            "app.runtime.adapters.sing_box.ensure_runtime_dirs",
            return_value={
                "runtime_root": self.runtime_root,
                "generated": self.generated_dir,
                "logs": self.logs_dir,
                "engines": self.root / "engines",
            },
        )

    def _patch_assets(self, *, with_cronet: bool = False):
        support_files = ()
        if with_cronet:
            cronet = self.binary_dir / "libcronet.dll"
            cronet.write_text("", encoding="utf-8")
            support_files = (cronet,)

        def _resolver(*, engine_root_dir=None, platform_name=None, required_support_files=None):
            if required_support_files and not with_cronet:
                raise FileNotFoundError("Required sing-box runtime asset 'libcronet.dll' was not found.")
            return SingBoxAssetLayout(
                engine_root=self.root / "engines",
                platform_name="windows",
                binary_path=self.binary_path,
                support_files=support_files,
            )

        return patch(
            "app.runtime.adapters.sing_box.resolve_sing_box_asset_layout",
            side_effect=_resolver,
        )

    def test_prepare_launch_writes_config_and_uses_override_ports(self) -> None:
        process_runner = FakeProcessRunner(FakeProcess())
        adapter = SingBoxAdapter(process_runner=process_runner, platform_name="windows")
        entry = _entry_from_uri(
            "vless://11111111-1111-1111-1111-111111111111@ws.example.com:443"
            "?type=ws&security=tls&host=cdn.example.com&path=%2Fws&sni=cdn.example.com"
            "#ws"
        )
        prefs = RuntimePrefs(entry_id=entry.id, http_port_override=18080, socks_port_override=11080)

        with self._patch_runtime_dirs(), self._patch_assets():
            launch_spec = adapter.prepare_launch(entry, prefs, make_primary=True)
            adapter._reserved_ports_by_session_id.pop(launch_spec.session_id).close()

        self.assertTrue(Path(launch_spec.config_path).exists())
        self.assertEqual(launch_spec.http_port, 18080)
        self.assertEqual(launch_spec.socks_port, 11080)
        config_text = Path(launch_spec.config_path).read_text(encoding="utf-8")
        self.assertIn('"listen_port": 18080', config_text)
        self.assertIn('"listen_port": 11080', config_text)

    def test_start_poll_and_stop_session_with_fake_process_runner(self) -> None:
        process = FakeProcess()
        process_runner = FakeProcessRunner(process)
        adapter = SingBoxAdapter(process_runner=process_runner, platform_name="windows")
        entry = _entry_from_uri(
            "trojan://secret@trojan.example.com:443?sni=trojan.example.com#trojan"
        )

        with self._patch_runtime_dirs(), self._patch_assets():
            launch_spec = adapter.prepare_launch(entry, RuntimePrefs(entry_id=entry.id), make_primary=False)
            Path(launch_spec.log_path).write_text(
                "+0000 2026-04-22 10:00:00 INFO sing-box started (0.00s)\n",
                encoding="utf-8",
            )
            started = adapter.start(launch_spec)
            polled = adapter.poll(started)
            stopped = adapter.stop(polled, reason=SessionStopReason.USER_REQUEST)

        self.assertEqual(process_runner.calls[0][0][:3], [str(self.binary_path), "run", "-c"])
        self.assertEqual(started.pid, 4242)
        self.assertEqual(polled.runtime_state, RuntimeState.RUNNING)
        self.assertEqual(stopped.runtime_state, RuntimeState.DISCONNECTED)
        self.assertEqual(process.terminate_calls, 1)
        self.assertFalse(Path(launch_spec.config_path).exists())

    def test_start_marks_immediate_process_exit_as_error(self) -> None:
        process = FakeProcess(exit_code=1)
        process_runner = FakeProcessRunner(process)
        adapter = SingBoxAdapter(process_runner=process_runner, platform_name="windows")
        entry = _entry_from_uri(
            "trojan://secret@trojan.example.com:443?sni=trojan.example.com#trojan"
        )

        with self._patch_runtime_dirs(), self._patch_assets():
            launch_spec = adapter.prepare_launch(entry, RuntimePrefs(entry_id=entry.id), make_primary=False)
            Path(launch_spec.log_path).write_text(
                "+0000 2026-04-22 10:00:04 ERROR outbound/trojan[proxy-out]: connection refused\n",
                encoding="utf-8",
            )
            session = adapter.start(launch_spec)

        self.assertEqual(session.runtime_state, RuntimeState.ERROR)
        self.assertEqual(session.failure_reason, "runtime.error.server_unreachable")
        self.assertFalse(Path(launch_spec.config_path).exists())

    def test_naive_proxy_requires_cronet_runtime_asset(self) -> None:
        process_runner = FakeProcessRunner(FakeProcess())
        adapter = SingBoxAdapter(process_runner=process_runner, platform_name="windows")
        entry = _entry_from_uri("https://user:pass@naive.example.com:443#naive")

        with self._patch_runtime_dirs(), self._patch_assets(with_cronet=False):
            with self.assertRaises(SingBoxAssetError):
                adapter.prepare_launch(entry, RuntimePrefs(entry_id=entry.id), make_primary=False)


if __name__ == "__main__":
    unittest.main()
