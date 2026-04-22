from __future__ import annotations

import argparse
import hashlib
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
    lowered = str(message or "").lower()
    if any(
        token in lowered
        for token in (
            "build is incomplete",
            "bundled wireguard",
            "bootstrap metadata is missing",
            "bootstrap payload is missing",
            "checksum mismatch",
            "hash mismatch",
            "wireguard bootstrap payload checksum",
            "wireguard bootstrap completed, but wireguard.exe is still unavailable",
        )
    ):
        return "bundle_incomplete"
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


def locate_wireguard_exe() -> Path | None:
    helper_dir = _helper_directory()
    candidates = [
        helper_dir / "wireguard.exe",
        helper_dir / "WireGuard" / "wireguard.exe",
    ]
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name, "")
        if root:
            candidates.append(Path(root) / "WireGuard" / "wireguard.exe")
    installed = _existing_path(candidates)
    if installed is not None:
        return installed
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not path_dir:
            continue
        candidate = Path(path_dir) / "wireguard.exe"
        if candidate.exists():
            return candidate
    return None


def locate_wg_exe() -> Path | None:
    helper_dir = _helper_directory()
    candidates = [
        helper_dir / "wg.exe",
        helper_dir / "WireGuard" / "wg.exe",
    ]
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name, "")
        if root:
            candidates.append(Path(root) / "WireGuard" / "wg.exe")
    installed = _existing_path(candidates)
    if installed is not None:
        return installed
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if not path_dir:
            continue
        candidate = Path(path_dir) / "wg.exe"
        if candidate.exists():
            return candidate
    return None


@dataclass(slots=True)
class WireGuardBootstrapPayload:
    installer_path: Path
    installer_name: str
    version: str
    sha256: str
    url: str = ""


@dataclass(slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class BootstrapInstallResult:
    exit_code: int
    output: str
    installer_log_excerpt: str


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
        return path.read_text(encoding="utf-8")
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
    stdout_fd, stdout_name = tempfile.mkstemp(prefix="proxyvault-wireguard-", suffix="-stdout.txt")
    stderr_fd, stderr_name = tempfile.mkstemp(prefix="proxyvault-wireguard-", suffix="-stderr.txt")
    script_fd, script_name = tempfile.mkstemp(prefix="proxyvault-wireguard-", suffix="-elevated.ps1")
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


@dataclass(slots=True)
class ServiceState:
    state: str
    pid: int | None = None


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


def query_service(service_name: str) -> ServiceState | None:
    script = "\n".join(
        [
            "$ErrorActionPreference = 'SilentlyContinue'",
            f"$Name = {_powershell_quote(service_name)}",
            "$FilterName = $Name.Replace(\"'\", \"''\")",
            "$service = Get-CimInstance Win32_Service -Filter (\"Name = '$FilterName'\") | Select-Object -First 1 Name, State, ProcessId, Status",
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
    return ServiceState(state=state, pid=pid)


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


def latest_handshake_iso(handle: str) -> str:
    wg_exe = locate_wg_exe()
    if wg_exe is None:
        return ""
    result = run_command([str(wg_exe), "show", handle, "latest-handshakes"])
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_wireguard_bootstrap_payload() -> WireGuardBootstrapPayload | None:
    helper_dir = _helper_directory()
    manifest_path = helper_dir / "wireguard-bootstrap.json"
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    installer_name = str(payload.get("installer_name", "")).strip()
    sha256 = str(payload.get("sha256", "")).strip().lower()
    version = str(payload.get("version", "")).strip()
    if not installer_name or not sha256:
        return None
    return WireGuardBootstrapPayload(
        installer_path=helper_dir / installer_name,
        installer_name=installer_name,
        version=version,
        sha256=sha256,
        url=str(payload.get("url", "")).strip(),
    )


def _tail_text(text: str, *, max_lines: int = 80) -> str:
    lines = [line.rstrip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-max(max_lines, 1) :])


def validate_wireguard_bootstrap_payload(payload: WireGuardBootstrapPayload | None) -> tuple[bool, str]:
    if payload is None:
        return False, "ProxyVault build is incomplete: bundled WireGuard bootstrap metadata is missing."
    if not payload.installer_path.exists():
        return False, "ProxyVault build is incomplete: bundled WireGuard bootstrap payload is missing."
    actual_sha = _sha256_file(payload.installer_path).lower()
    if actual_sha != payload.sha256:
        return False, "ProxyVault build is incomplete: bundled WireGuard bootstrap payload checksum mismatch."
    return True, ""


def install_wireguard_bootstrap_payload(
    payload: WireGuardBootstrapPayload,
    *,
    log_path: Path | None,
    elevation_flow: bool,
) -> BootstrapInstallResult:
    installer_log_fd, installer_log_name = tempfile.mkstemp(prefix="proxyvault-wireguard-", suffix="-msi.log")
    os.close(installer_log_fd)
    installer_log_path = Path(installer_log_name)
    command = [
        "msiexec.exe",
        "/i",
        str(payload.installer_path),
        "/qn",
        "/norestart",
        "/L*v",
        str(installer_log_path),
    ]
    write_log(
        log_path,
        f"Installing bundled WireGuard system component {payload.version or payload.installer_name}",
        f"Installer: {payload.installer_path}",
    )
    try:
        if elevation_flow and not _is_process_elevated():
            result = run_elevated_command(command)
        else:
            result = run_command(command)
        installer_log_excerpt = _tail_text(_read_optional_text(installer_log_path))
        output = "\n".join(
            part.strip()
            for part in (result.stdout, result.stderr, installer_log_excerpt)
            if part and part.strip()
        ).strip()
        return BootstrapInstallResult(
            exit_code=result.exit_code,
            output=output,
            installer_log_excerpt=installer_log_excerpt,
        )
    finally:
        try:
            installer_log_path.unlink()
        except OSError:
            pass


def ensure_wireguard_exe(*, log_path: Path | None, elevation_flow: bool) -> tuple[Path | None, str, str]:
    wireguard_exe = locate_wireguard_exe()
    if wireguard_exe is not None:
        return wireguard_exe, "", ""

    payload = load_wireguard_bootstrap_payload()
    valid_payload, validation_message = validate_wireguard_bootstrap_payload(payload)
    if not valid_payload:
        return None, "bundle_incomplete", validation_message

    assert payload is not None
    install_result = install_wireguard_bootstrap_payload(
        payload,
        log_path=log_path,
        elevation_flow=elevation_flow,
    )
    if install_result.exit_code != 0:
        if install_result.exit_code == 1223 and "cancel" not in install_result.output.lower():
            install_output = "WireGuard Windows bootstrap was cancelled by the user."
        else:
            install_output = install_result.output or "WireGuard Windows bootstrap failed."
        write_log(log_path, install_output)
        return None, normalize_reason(install_output), install_output

    wireguard_exe = locate_wireguard_exe()
    if wireguard_exe is None:
        message = "WireGuard bootstrap completed, but wireguard.exe is still unavailable."
        if install_result.installer_log_excerpt:
            message = f"{message}\n\n{install_result.installer_log_excerpt}"
        write_log(log_path, message)
        return None, "bundle_incomplete", message

    write_log(log_path, f"Using WireGuard executable: {wireguard_exe}")
    return wireguard_exe, "", install_result.output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ProxyVault WireGuard helper for Windows.")
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
            message=f"WireGuard config was not found at {config_path}.",
            log_path=log_path,
        )

    wireguard_exe, reason_code, bootstrap_output = ensure_wireguard_exe(
        log_path=log_path,
        elevation_flow=bool(args.elevation_flow),
    )
    if wireguard_exe is None:
        return fail(
            reason_code=reason_code or "helper_not_found",
            message=bootstrap_output or "WireGuard for Windows is unavailable.",
            log_path=log_path,
            log_excerpt=bootstrap_output or "WireGuard for Windows is unavailable.",
        )

    write_log(log_path, f"Installing tunnel service via {wireguard_exe}", f"Config: {config_path}")
    command = [str(wireguard_exe), "/installtunnelservice", str(config_path)]
    if args.elevation_flow and not _is_process_elevated():
        result = run_elevated_command(command)
    else:
        result = run_command(command)
    output = "\n".join(part.strip() for part in (bootstrap_output, result.stdout, result.stderr) if part and part.strip()).strip()
    if result.exit_code != 0:
        return fail(
            reason_code=normalize_reason(output or "WireGuard tunnel installation failed."),
            message=output or "WireGuard tunnel installation failed.",
            log_path=log_path,
            exit_code=result.exit_code,
        )

    service_name = f"WireGuardTunnel${args.tunnel_name}"
    service_state = wait_for_service(service_name, desired_state="RUNNING")
    runtime_state = "RUNNING"
    if service_state is None:
        runtime_state = "STARTING"
    elif service_state.state not in {"RUNNING", "START_PENDING"}:
        runtime_state = "ERROR"

    payload: dict[str, object] = {
        "runtime_state": runtime_state,
        "handle": args.tunnel_name,
        "pid": service_state.pid if service_state is not None else None,
        "last_activity_at": utc_now_iso(),
        "last_handshake_at": latest_handshake_iso(args.tunnel_name),
        "log_excerpt": output,
    }
    if runtime_state == "ERROR":
        query_text = query_service_text(service_name)
        message = (
            f"WireGuard tunnel service is {service_state.state if service_state else 'unavailable'}."
            + (f"\n\n{query_text}" if query_text else "")
        )
        payload["reason_code"] = "tunnel_exited_early"
        payload["last_error"] = message
        payload["log_excerpt"] = _tail_text(message)
    write_log(log_path, output)
    return emit(payload)


def cmd_down(args: argparse.Namespace) -> int:
    log_path = Path(args.log) if args.log else None
    service_name = f"WireGuardTunnel${args.handle}"
    service_state = query_service(service_name)
    if service_state is None:
        write_log(log_path, f"Tunnel service {service_name} was already absent.")
        return emit(
            {
                "runtime_state": "DISCONNECTED",
                "handle": args.handle,
                "last_activity_at": utc_now_iso(),
            }
        )

    wireguard_exe, reason_code, bootstrap_output = ensure_wireguard_exe(
        log_path=log_path,
        elevation_flow=bool(args.elevation_flow),
    )
    if wireguard_exe is None:
        return fail(
            reason_code=reason_code or "helper_not_found",
            message=bootstrap_output or "WireGuard for Windows is unavailable.",
            log_path=log_path,
            log_excerpt=bootstrap_output or "WireGuard for Windows is unavailable.",
        )

    command = [str(wireguard_exe), "/uninstalltunnelservice", args.handle]
    if args.elevation_flow and not _is_process_elevated():
        result = run_elevated_command(command)
    else:
        result = run_command(command)
    output = "\n".join(part.strip() for part in (bootstrap_output, result.stdout, result.stderr) if part and part.strip()).strip()
    if result.exit_code != 0 and "does not exist" not in output.lower():
        return fail(
            reason_code=normalize_reason(output or "WireGuard tunnel removal failed."),
            message=output or "WireGuard tunnel removal failed.",
            log_path=log_path,
            exit_code=result.exit_code,
        )
    write_log(log_path, output or f"Uninstalled tunnel service {service_name}.")
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
    service_name = f"WireGuardTunnel${args.handle}"
    service_state = query_service(service_name)
    if service_state is None:
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

    query_text = query_service_text(service_name)
    message = f"WireGuard tunnel service is {service_state.state}."
    if query_text:
        message = f"{message}\n\n{query_text}"
    write_log(log_path, message)
    payload.update(
        {
            "runtime_state": "ERROR",
            "reason_code": "tunnel_exited_early",
            "last_error": message,
            "log_excerpt": _tail_text(message),
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
