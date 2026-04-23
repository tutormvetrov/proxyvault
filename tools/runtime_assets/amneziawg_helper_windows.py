from __future__ import annotations

import argparse
import json
import locale
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "")


def write_log(log_path: Path | None, *messages: str) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now_iso()
    with log_path.open("a", encoding="utf-8") as handle:
        for message in messages:
            text = str(message).strip()
            if text:
                handle.write(f"[{timestamp}] {text}\n")


def emit(payload: dict[str, object], *, exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def fail(
    *,
    reason_code: str,
    message: str,
    log_path: Path | None,
    exit_code: int = 1,
    log_excerpt: str | None = None,
) -> int:
    write_log(log_path, message)
    return emit(
        {
            "runtime_state": "ERROR",
            "reason_code": reason_code,
            "last_error": message,
            "log_excerpt": log_excerpt or message,
            "exit_code": exit_code,
            "last_activity_at": utc_now_iso(),
        },
        exit_code=exit_code,
    )


def normalize_reason(message: str) -> str:
    lowered = message.lower()
    if _looks_like_service_conflict(lowered):
        return "service_conflict"
    if any(
        token in lowered
        for token in (
            "operation was canceled",
            "operation was cancelled",
            "canceled by the user",
            "cancelled by the user",
            "authorization was canceled",
            "authorization was cancelled",
            "user canceled",
            "user cancelled",
            "prompt denied",
        )
    ):
        return "system_prompt_denied"
    if any(token in lowered for token in ("access is denied", "administrator", "permission denied")):
        return "privileges_required"
    if any(token in lowered for token in ("not found", "could not locate", "cannot find the file")):
        return "helper_not_found"
    if any(token in lowered for token in ("parse", "invalid", "configuration")):
        return "invalid_config"
    return "tunnel_exited_early"


def _helper_directory() -> Path:
    return Path(sys.argv[0]).resolve().parent


def _existing_path(candidates: Sequence[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def locate_amneziawg_exe() -> Path | None:
    helper_dir = _helper_directory()
    candidates = [
        helper_dir / "amneziawg.exe",
        helper_dir / "AmneziaWG.exe",
        helper_dir / "AmneziaWG" / "amneziawg.exe",
        helper_dir / "AmneziaWG" / "AmneziaWG.exe",
    ]
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name, "")
        if root:
            candidates.extend(
                [
                    Path(root) / "AmneziaWG" / "amneziawg.exe",
                    Path(root) / "AmneziaWG" / "AmneziaWG.exe",
                ]
            )
    installed = _existing_path(candidates)
    if installed is not None:
        return installed
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not path_dir:
            continue
        for file_name in ("amneziawg.exe", "AmneziaWG.exe"):
            candidate = Path(path_dir) / file_name
            if candidate.exists():
                return candidate
    return None


def locate_awg_exe() -> Path | None:
    helper_dir = _helper_directory()
    candidates = [
        helper_dir / "awg.exe",
        helper_dir / "AmneziaWG" / "awg.exe",
    ]
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name, "")
        if root:
            candidates.append(Path(root) / "AmneziaWG" / "awg.exe")
    installed = _existing_path(candidates)
    if installed is not None:
        return installed
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not path_dir:
            continue
        candidate = Path(path_dir) / "awg.exe"
        if candidate.exists():
            return candidate
    return None


def _bundled_runtime_missing_message() -> str:
    helper_dir = _helper_directory()
    runtime_dir = helper_dir / "AmneziaWG"
    missing = [name for name in ("amneziawg.exe", "awg.exe", "wintun.dll") if not (runtime_dir / name).exists()]
    missing_text = ", ".join(missing) if missing else "amneziawg.exe, awg.exe, wintun.dll"
    return (
        "ProxyVault build is incomplete: bundled AmneziaWG runtime files are missing next to the helper "
        f"({missing_text})."
    )


@dataclass(slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


def _decode_output(raw: bytes | None) -> str:
    if not raw:
        return ""
    encodings: list[str] = []
    preferred = locale.getpreferredencoding(False)
    for candidate in ("utf-8", preferred, "cp866", "cp1251"):
        normalized = str(candidate or "").strip()
        if normalized and normalized.lower() not in {item.lower() for item in encodings}:
            encodings.append(normalized)
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def run_command(command: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        [str(part) for part in command],
        capture_output=True,
        text=False,
        check=False,
    )
    return CommandResult(
        exit_code=completed.returncode,
        stdout=_decode_output(completed.stdout),
        stderr=_decode_output(completed.stderr),
    )


def _powershell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _read_optional_text(path: Path) -> str:
    try:
        return _decode_output(path.read_bytes())
    except OSError:
        return ""


def _is_process_elevated() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_elevated_command(command: Sequence[str]) -> CommandResult:
    command_parts = [str(part) for part in command]
    stdout_fd, stdout_name = tempfile.mkstemp(prefix="proxyvault-amneziawg-", suffix="-stdout.txt")
    stderr_fd, stderr_name = tempfile.mkstemp(prefix="proxyvault-amneziawg-", suffix="-stderr.txt")
    script_fd, script_name = tempfile.mkstemp(prefix="proxyvault-amneziawg-", suffix="-elevated.ps1")
    os.close(stdout_fd)
    os.close(stderr_fd)
    os.close(script_fd)

    stdout_path = Path(stdout_name)
    stderr_path = Path(stderr_name)
    script_path = Path(script_name)
    script_body = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "& "
            + " ".join(_powershell_quote(part) for part in command_parts)
            + f" 1> {_powershell_quote(stdout_name)} 2> {_powershell_quote(stderr_name)}",
            "exit $LASTEXITCODE",
            "",
        ]
    )
    script_path.write_text(script_body, encoding="utf-8")

    launcher_script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "try {",
            "  $proc = Start-Process"
            f" -FilePath {_powershell_quote('powershell.exe')}"
            " -ArgumentList @("
            + ", ".join(
                _powershell_quote(item)
                for item in (
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                )
            )
            + ") -Verb RunAs -PassThru -Wait -ErrorAction Stop",
            "  exit [int]$proc.ExitCode",
            "} catch {",
            "  $message = $_.Exception.Message",
            "  [Console]::Error.WriteLine($message)",
            "  if ($message -match 'operation was cancell?ed|cancell?ed by the user|authorization was cancell?ed|user cancell?ed') {",
            "    exit 1223",
            "  }",
            "  exit 1",
            "}",
            "",
        ]
    )
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                launcher_script,
            ],
            capture_output=True,
            text=False,
            check=False,
        )
        stdout = _read_optional_text(stdout_path)
        stderr = "\n".join(
            part.strip()
            for part in (
                _read_optional_text(stderr_path),
                _decode_output(completed.stderr),
                _decode_output(completed.stdout),
            )
            if part and part.strip()
        ).strip()
        return CommandResult(
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    finally:
        for path in (stdout_path, stderr_path, script_path):
            try:
                path.unlink()
            except OSError:
                pass


def run_elevated_powershell_script(script_body: str) -> CommandResult:
    script_fd, script_name = tempfile.mkstemp(prefix="proxyvault-amneziawg-sequence-", suffix=".ps1")
    os.close(script_fd)
    script_path = Path(script_name)
    try:
        script_path.write_text(script_body, encoding="utf-8")
        return run_elevated_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ]
        )
    finally:
        try:
            script_path.unlink()
        except OSError:
            pass


@dataclass(slots=True)
class ServiceState:
    state: str
    pid: int | None = None
    service_name: str = ""
    config_path: str = ""


@dataclass(slots=True)
class InstallFailureDiagnostics:
    reason_code: str
    message: str
    log_excerpt: str


def query_service(service_name: str) -> ServiceState | None:
    script = "\n".join(
        [
            "$ErrorActionPreference = 'SilentlyContinue'",
            f"$Name = {_powershell_quote(service_name)}",
            "$FilterName = $Name.Replace(\"'\", \"''\")",
            "$service = Get-CimInstance Win32_Service -Filter (\"Name = '$FilterName'\") | Select-Object -First 1 Name, State, ProcessId, PathName, Status",
            "if ($service) { $service | ConvertTo-Json -Compress }",
            "",
        ]
    )
    result = _run_powershell(script)
    payload = _parse_json_payload("\n".join(part for part in (result.stdout, result.stderr) if part).strip())
    if not isinstance(payload, dict):
        return None
    state = _normalize_service_state(str(payload.get("State", "")))
    pid_value = payload.get("ProcessId")
    try:
        pid = int(pid_value) if pid_value not in (None, "") else None
    except (TypeError, ValueError):
        pid = None
    return ServiceState(
        state=state,
        pid=pid,
        service_name=str(payload.get("Name", "")),
        config_path=_extract_config_path_from_service_path(str(payload.get("PathName", ""))),
    )


def _service_handle_from_name(service_name: str) -> str:
    prefix = "AmneziaWGTunnel$"
    if service_name.startswith(prefix):
        return service_name[len(prefix) :]
    return service_name


def _short_tunnel_entry_prefix(tunnel_name: str) -> str:
    parts = str(tunnel_name or "").split("-")
    if len(parts) >= 2 and parts[0] == "pvawg":
        return f"{parts[0]}-{parts[1]}"
    return ""


def _extract_config_path_from_service_path(path_name: str) -> str:
    match = re.search(r"([A-Za-z]:\\[^\"\r\n]+?\.conf)", str(path_name or ""))
    return match.group(1) if match else ""


def _same_config_text(left: Path, right_text: str) -> bool:
    right = Path(right_text) if right_text else None
    if right is None or not left.exists() or not right.exists():
        return False
    try:
        return left.read_text(encoding="utf-8") == right.read_text(encoding="utf-8")
    except OSError:
        return False


def list_matching_tunnel_services(tunnel_name: str) -> list[ServiceState]:
    entry_prefix = _short_tunnel_entry_prefix(tunnel_name)
    if not entry_prefix:
        return []
    pattern = f"AmneziaWGTunnel${entry_prefix}*"
    script = "\n".join(
        [
            "$ErrorActionPreference = 'SilentlyContinue'",
            f"$Pattern = {_powershell_quote(pattern)}",
            "$services = Get-CimInstance Win32_Service | Where-Object { $_.Name -like $Pattern } | Select-Object Name, State, ProcessId, PathName",
            "if ($services) { $services | ConvertTo-Json -Compress }",
            "",
        ]
    )
    result = _run_powershell(script)
    payload = _parse_json_payload("\n".join(part for part in (result.stdout, result.stderr) if part).strip())
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = [item for item in payload if isinstance(item, dict)]
    else:
        items = []

    services: list[ServiceState] = []
    for item in items:
        try:
            pid = int(item.get("ProcessId")) if item.get("ProcessId") not in (None, "") else None
        except (TypeError, ValueError):
            pid = None
        services.append(
            ServiceState(
                state=_normalize_service_state(str(item.get("State", ""))),
                pid=pid,
                service_name=str(item.get("Name", "")),
                config_path=_extract_config_path_from_service_path(str(item.get("PathName", ""))),
            )
        )
    return services


def find_reusable_running_tunnel(tunnel_name: str, config_path: Path) -> ServiceState | None:
    for service in list_matching_tunnel_services(tunnel_name):
        if service.state not in {"RUNNING", "START_PENDING"}:
            continue
        if _same_config_text(config_path, service.config_path):
            return service
    return None


def cleanup_stopped_matching_tunnel_services(tunnel_name: str) -> str:
    removed: list[str] = []
    for service in list_matching_tunnel_services(tunnel_name):
        if service.state in {"RUNNING", "START_PENDING"}:
            continue
        service_name = service.service_name
        if not service_name:
            continue
        result = run_command(["sc.exe", "delete", service_name])
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()).strip()
        removed.append(f"{service_name}: {output or result.exit_code}")
    return "\n".join(removed)


def configure_service_manual(service_name: str) -> str:
    result = run_command(["sc.exe", "config", service_name, "start=", "demand"])
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()).strip()


def run_elevated_install_sequence(
    *,
    tunnel_name: str,
    config_path: Path,
    amneziawg_exe: Path,
) -> CommandResult:
    service_name = f"AmneziaWGTunnel${tunnel_name}"
    entry_prefix = _short_tunnel_entry_prefix(tunnel_name)
    service_pattern = f"AmneziaWGTunnel${entry_prefix}*" if entry_prefix else service_name
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Continue'",
            f"$ServicePattern = {_powershell_quote(service_pattern)}",
            f"$ServiceName = {_powershell_quote(service_name)}",
            "$stale = Get-CimInstance Win32_Service | Where-Object {",
            "  $_.Name -like $ServicePattern -and $_.State -notin @('Running', 'Start Pending')",
            "}",
            "foreach ($service in $stale) {",
            "  Write-Output \"Deleting stale ProxyVault AmneziaWG service: $($service.Name)\"",
            "  & sc.exe delete $service.Name | Write-Output",
            "}",
            "& "
            + " ".join(
                _powershell_quote(part)
                for part in (str(amneziawg_exe), "/installtunnelservice", str(config_path))
            ),
            "$installExit = $LASTEXITCODE",
            "if ($installExit -eq 0) {",
            "  & sc.exe config $ServiceName start= demand | Write-Output",
            "}",
            "exit $installExit",
            "",
        ]
    )
    return run_elevated_powershell_script(_powershell_utf8_script(script))


def query_service_text(service_name: str) -> str:
    script = "\n".join(
        [
            "$ErrorActionPreference = 'SilentlyContinue'",
            f"$Name = {_powershell_quote(service_name)}",
            "& sc.exe queryex $Name | Out-String -Width 240",
            "",
        ]
    )
    result = _run_powershell(script)
    return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()


def wait_for_service(service_name: str, *, desired_state: str, timeout: float = 10.0) -> ServiceState | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = query_service(service_name)
        if state is not None and state.state == desired_state:
            return state
        time.sleep(0.35)
    return query_service(service_name)


def _parse_json_payload(text: str) -> object | None:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    candidates = [stripped]
    candidates.extend(
        line.strip()
        for line in reversed(stripped.splitlines())
        if line.strip().startswith(("{", "["))
    )
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _normalize_service_state(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z]+", "_", str(value or "").strip().upper())
    return normalized.strip("_") or "UNKNOWN"


def _powershell_utf8_script(command: str) -> str:
    return "\n".join(
        [
            "[Console]::InputEncoding = [System.Text.Encoding]::UTF8",
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
            "$OutputEncoding = [System.Text.Encoding]::UTF8",
            str(command or ""),
        ]
    )


def _run_powershell(command: str) -> CommandResult:
    return run_command(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _powershell_utf8_script(command),
        ]
    )


def list_related_services_text() -> str:
    script = "\n".join(
        [
            "$ErrorActionPreference = 'SilentlyContinue'",
            "$services = Get-Service | Where-Object {",
            "  $_.Name -like 'AmneziaWGTunnel$*' -or $_.Name -like 'Amnezia*' -or $_.DisplayName -like 'Amnezia*'",
            "} | Select-Object Status, Name, DisplayName",
            "if ($services) {",
            "  $services | Format-Table -AutoSize | Out-String -Width 240",
            "}",
            "",
        ]
    )
    result = _run_powershell(script)
    return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()


def recent_event_log_text(
    *,
    tunnel_name: str,
    amneziawg_exe: Path | None,
    max_entries: int = 8,
) -> str:
    script = "\n".join(
        [
            "$ErrorActionPreference = 'SilentlyContinue'",
            f"$TunnelName = {_powershell_quote(tunnel_name)}",
            f"$ExePath = {_powershell_quote(str(amneziawg_exe) if amneziawg_exe is not None else '')}",
            f"$MaxEntries = {max_entries}",
            "$TunnelPattern = [regex]::Escape($TunnelName)",
            "$ExePattern = if ($ExePath) { [regex]::Escape($ExePath) } else { '' }",
            "$events = Get-WinEvent -LogName System,Application -MaxEvents 400 | Where-Object {",
            "  $_.ProviderName -match 'AmneziaWG|Service Control Manager|Application Error|Windows Error Reporting' -or",
            "  $_.Message -match $TunnelPattern -or $_.Message -match 'Split Tunnel' -or $_.Message -match 'AmneziaWG' -or",
            "  ($ExePattern -and $_.Message -match $ExePattern)",
            "} | Select-Object -First $MaxEntries TimeCreated, ProviderName, Id, LevelDisplayName, Message",
            "if ($events) {",
            "  $events | Format-List | Out-String -Width 240",
            "}",
            "",
        ]
    )
    result = _run_powershell(script)
    return "\n".join(part for part in (result.stdout, result.stderr) if part).strip()


def _install_attempt_marker(tunnel_name: str) -> str:
    return f"ProxyVault install attempt: {tunnel_name}"


def _uninstall_marker(tunnel_name: str) -> str:
    return f"ProxyVault uninstall: {tunnel_name}"


def note_install_attempt(log_path: Path | None, tunnel_name: str, config_path: Path) -> None:
    write_log(log_path, _install_attempt_marker(tunnel_name), f"ProxyVault config path: {config_path}")


def note_uninstall(log_path: Path | None, tunnel_name: str) -> None:
    write_log(log_path, _uninstall_marker(tunnel_name))


def has_pending_install_attempt(log_path: Path | None, tunnel_name: str) -> bool:
    if log_path is None or not log_path.exists():
        return False
    try:
        content = log_path.read_text(encoding="utf-8")
    except OSError:
        return False
    pending = False
    install_marker = _install_attempt_marker(tunnel_name)
    uninstall_marker = _uninstall_marker(tunnel_name)
    for line in content.splitlines():
        if install_marker in line:
            pending = True
        elif uninstall_marker in line:
            pending = False
    return pending


def _looks_like_service_conflict(text: str) -> bool:
    lowered = text.lower()
    exists_tokens = (
        "already exists",
        "file already exists",
        "object already exists",
        "the object already exists",
        "cannot create a file",
        "невозможно создать файл",
        "win32_exit_code    : 5010",
        "win32 exit code    : 5010",
        "win32_exit_code: 5010",
        "win32 exit code: 5010",
    )
    has_exists_marker = any(token in lowered for token in exists_tokens)
    return has_exists_marker and any(
        token in lowered
        for token in (
            "split tunnel",
            "amneziawg tunnel",
            "amneziawg",
            "amneziawgtunnel$",
            "service terminated with the following error",
        )
    )


def collect_install_failure_diagnostics(
    *,
    tunnel_name: str,
    service_name: str,
    amneziawg_exe: Path | None,
    install_output: str = "",
    service_state: ServiceState | None = None,
) -> InstallFailureDiagnostics:
    service_query_text = query_service_text(service_name)
    services_text = list_related_services_text()
    events_text = recent_event_log_text(tunnel_name=tunnel_name, amneziawg_exe=amneziawg_exe)

    detail_blocks: list[str] = []
    if install_output:
        detail_blocks.append(f"Install output:\n{install_output}")
    if service_query_text:
        detail_blocks.append(f"Expected service query ({service_name}):\n{service_query_text}")
    if services_text:
        detail_blocks.append(f"Related Amnezia services:\n{services_text}")
    if events_text:
        detail_blocks.append(f"Recent system events:\n{events_text}")

    detail_text = "\n\n".join(block.strip() for block in detail_blocks if block.strip())
    combined_text = detail_text or install_output or service_query_text
    if _looks_like_service_conflict(combined_text):
        summary = "AmneziaWG encountered a conflicting Split Tunnel service or helper while starting the tunnel."
        reason_code = "service_conflict"
    elif service_query_text and any(token in service_query_text.lower() for token in ("1060", "does not exist", "not been started")):
        summary = "AmneziaWG tunnel service disappeared right after install."
        reason_code = "tunnel_exited_early"
    else:
        state_text = service_state.state if service_state is not None else "unavailable"
        summary = f"AmneziaWG tunnel service is {state_text}."
        reason_code = "tunnel_exited_early"

    message = summary if not detail_text else f"{summary}\n\n{detail_text}"
    return InstallFailureDiagnostics(
        reason_code=reason_code,
        message=message,
        log_excerpt=detail_text or summary,
    )


def latest_handshake_iso(handle: str) -> str:
    awg_exe = locate_awg_exe()
    if awg_exe is None:
        return ""
    result = run_command([str(awg_exe), "show", handle, "latest-handshakes"])
    if result.exit_code != 0:
        return ""
    max_epoch = 0
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        try:
            epoch = int(parts[1])
        except ValueError:
            continue
        if epoch > max_epoch:
            max_epoch = epoch
    if max_epoch <= 0:
        return ""
    return datetime.fromtimestamp(max_epoch, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ProxyVault AmneziaWG helper for Windows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    up_parser = subparsers.add_parser("up")
    up_parser.add_argument("--config", required=True)
    up_parser.add_argument("--log", required=False, default="")
    up_parser.add_argument("--tunnel-name", required=True)
    up_parser.add_argument("--elevation-flow", action="store_true")

    down_parser = subparsers.add_parser("down")
    down_parser.add_argument("--handle", required=True)
    down_parser.add_argument("--config", required=False, default="")
    down_parser.add_argument("--log", required=False, default="")
    down_parser.add_argument("--elevation-flow", action="store_true")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--handle", required=True)
    status_parser.add_argument("--config", required=False, default="")
    status_parser.add_argument("--log", required=False, default="")

    return parser.parse_args()


def cmd_up(args: argparse.Namespace) -> int:
    log_path = Path(args.log) if args.log else None
    config_path = Path(args.config)
    if not config_path.exists():
        return fail(
            reason_code="invalid_config",
            message=f"AmneziaWG config was not found at {config_path}.",
            log_path=log_path,
        )

    amneziawg_exe = locate_amneziawg_exe()
    if amneziawg_exe is None:
        return fail(
            reason_code="bundle_incomplete",
            message=_bundled_runtime_missing_message(),
            log_path=log_path,
        )

    service_name = f"AmneziaWGTunnel${args.tunnel_name}"
    existing_state = query_service(service_name)
    if existing_state is not None and existing_state.state in {"RUNNING", "START_PENDING"}:
        write_log(log_path, f"Reusing already running tunnel service {service_name}.")
        return emit(
            {
                "runtime_state": "RUNNING" if existing_state.state == "RUNNING" else "STARTING",
                "handle": args.tunnel_name,
                "pid": existing_state.pid,
                "last_activity_at": utc_now_iso(),
                "last_handshake_at": latest_handshake_iso(args.tunnel_name),
                "log_excerpt": f"Reusing already running tunnel service {service_name}.",
            }
        )

    reusable_service = find_reusable_running_tunnel(args.tunnel_name, config_path)
    if reusable_service is not None:
        handle = _service_handle_from_name(reusable_service.service_name)
        message = f"Reusing already running tunnel service {reusable_service.service_name}."
        write_log(log_path, message)
        return emit(
            {
                "runtime_state": "RUNNING" if reusable_service.state == "RUNNING" else "STARTING",
                "handle": handle,
                "pid": reusable_service.pid,
                "last_activity_at": utc_now_iso(),
                "last_handshake_at": latest_handshake_iso(handle),
                "log_excerpt": message,
            }
        )

    note_install_attempt(log_path, args.tunnel_name, config_path)
    write_log(log_path, f"Installing tunnel service via {amneziawg_exe}", f"Config: {config_path}")
    command = [str(amneziawg_exe), "/installtunnelservice", str(config_path)]
    if args.elevation_flow and not _is_process_elevated():
        result = run_elevated_install_sequence(
            tunnel_name=args.tunnel_name,
            config_path=config_path,
            amneziawg_exe=amneziawg_exe,
        )
    else:
        cleanup_output = cleanup_stopped_matching_tunnel_services(args.tunnel_name)
        if cleanup_output:
            write_log(log_path, cleanup_output)
        result = run_command(command)
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()).strip()
    if result.exit_code != 0:
        reason_code = normalize_reason(output or "AmneziaWG tunnel installation failed.")
        return fail(
            reason_code=reason_code,
            message=output or "AmneziaWG tunnel installation failed.",
            log_path=log_path,
            exit_code=result.exit_code,
        )

    if not (args.elevation_flow and not _is_process_elevated()):
        manual_output = configure_service_manual(service_name)
        if manual_output:
            write_log(log_path, manual_output)

    service_state = wait_for_service(service_name, desired_state="RUNNING")
    if service_state is None or service_state.state not in {"RUNNING", "START_PENDING"}:
        diagnostics = collect_install_failure_diagnostics(
            tunnel_name=args.tunnel_name,
            service_name=service_name,
            amneziawg_exe=amneziawg_exe,
            install_output=output,
            service_state=service_state,
        )
        return fail(
            reason_code=diagnostics.reason_code,
            message=diagnostics.message,
            log_path=log_path,
            log_excerpt=diagnostics.log_excerpt,
        )

    payload: dict[str, object] = {
        "runtime_state": "RUNNING" if service_state.state == "RUNNING" else "STARTING",
        "handle": args.tunnel_name,
        "pid": service_state.pid,
        "last_activity_at": utc_now_iso(),
        "last_handshake_at": latest_handshake_iso(args.tunnel_name),
        "log_excerpt": output,
    }
    write_log(log_path, output)
    return emit(payload)


def cmd_down(args: argparse.Namespace) -> int:
    log_path = Path(args.log) if args.log else None
    service_name = f"AmneziaWGTunnel${args.handle}"
    service_state = query_service(service_name)
    if service_state is None:
        write_log(log_path, f"Tunnel service {service_name} was already absent.")
        note_uninstall(log_path, args.handle)
        return emit(
            {
                "runtime_state": "DISCONNECTED",
                "handle": args.handle,
                "last_activity_at": utc_now_iso(),
            }
        )

    amneziawg_exe = locate_amneziawg_exe()
    if amneziawg_exe is None:
        return fail(
            reason_code="bundle_incomplete",
            message=_bundled_runtime_missing_message(),
            log_path=log_path,
        )

    command = [str(amneziawg_exe), "/uninstalltunnelservice", args.handle]
    if args.elevation_flow and not _is_process_elevated():
        result = run_elevated_command(command)
    else:
        result = run_command(command)
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip()).strip()
    if result.exit_code != 0 and "does not exist" not in output.lower():
        return fail(
            reason_code=normalize_reason(output or "AmneziaWG tunnel removal failed."),
            message=output or "AmneziaWG tunnel removal failed.",
            log_path=log_path,
            exit_code=result.exit_code,
        )
    write_log(log_path, output or f"Uninstalled tunnel service {service_name}.")
    note_uninstall(log_path, args.handle)
    return emit(
        {
            "runtime_state": "DISCONNECTED",
            "handle": args.handle,
            "last_activity_at": utc_now_iso(),
            "log_excerpt": output,
        }
    )


def cmd_status(args: argparse.Namespace) -> int:
    log_path = Path(args.log) if args.log else None
    service_name = f"AmneziaWGTunnel${args.handle}"
    service_state = query_service(service_name)
    if service_state is None:
        if has_pending_install_attempt(log_path, args.handle):
            diagnostics = collect_install_failure_diagnostics(
                tunnel_name=args.handle,
                service_name=service_name,
                amneziawg_exe=locate_amneziawg_exe(),
            )
            write_log(log_path, diagnostics.message)
            return emit(
                {
                    "runtime_state": "ERROR",
                    "handle": args.handle,
                    "last_activity_at": utc_now_iso(),
                    "reason_code": diagnostics.reason_code,
                    "last_error": diagnostics.message,
                    "log_excerpt": diagnostics.log_excerpt,
                    "exit_code": 1,
                }
            )
        return emit(
            {
                "runtime_state": "DISCONNECTED",
                "handle": args.handle,
                "last_activity_at": utc_now_iso(),
            }
        )

    payload: dict[str, object] = {
        "handle": args.handle,
        "pid": service_state.pid,
        "last_activity_at": utc_now_iso(),
        "last_handshake_at": latest_handshake_iso(args.handle),
    }
    if service_state.state == "RUNNING":
        payload["runtime_state"] = "RUNNING"
        return emit(payload)
    if service_state.state.endswith("PENDING"):
        payload["runtime_state"] = "STARTING" if service_state.state.startswith("START") else "STOPPING"
        return emit(payload)

    message = f"AmneziaWG tunnel service is {service_state.state}."
    write_log(log_path, message)
    payload.update(
        {
            "runtime_state": "ERROR",
            "reason_code": "tunnel_exited_early",
            "last_error": message,
            "log_excerpt": message,
            "exit_code": 1,
        }
    )
    return emit(payload)


def main() -> int:
    args = parse_args()
    if args.command == "up":
        return cmd_up(args)
    if args.command == "down":
        return cmd_down(args)
    if args.command == "status":
        return cmd_status(args)
    print(f"Unsupported command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
