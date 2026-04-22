from __future__ import annotations

from app.runtime.routing.system_proxy import CommandRunner, ProxyEndpoint, SystemProxyCommandError


class WindowsSystemProxyBackend:
    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def apply(self, endpoint: ProxyEndpoint) -> None:
        result = self._runner.run(_powershell_command(_apply_script(endpoint)))
        if result.returncode != 0:
            raise SystemProxyCommandError(result.stderr.strip() or "Unable to apply the Windows system proxy.")

    def clear(self) -> None:
        result = self._runner.run(_powershell_command(_clear_script()))
        if result.returncode != 0:
            raise SystemProxyCommandError(result.stderr.strip() or "Unable to clear the Windows system proxy.")


def _powershell_command(script: str) -> list[str]:
    return [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]


def _apply_script(endpoint: ProxyEndpoint) -> str:
    proxy_server = f"{endpoint.host}:{endpoint.port}"
    return (
        "$settings='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'; "
        f"Set-ItemProperty -Path $settings -Name ProxyServer -Value '{proxy_server}'; "
        "Set-ItemProperty -Path $settings -Name ProxyEnable -Type DWord -Value 1; "
        "Set-ItemProperty -Path $settings -Name ProxyOverride -Value 'localhost;127.*;<local>'; "
        "Add-Type -Namespace ProxyVault -Name WinInet -MemberDefinition "
        "\"[System.Runtime.InteropServices.DllImport('wininet.dll', SetLastError=true)] "
        "public static extern bool InternetSetOption(System.IntPtr hInternet, int dwOption, "
        "System.IntPtr lpBuffer, int dwBufferLength);\"; "
        "[ProxyVault.WinInet]::InternetSetOption([System.IntPtr]::Zero, 39, [System.IntPtr]::Zero, 0) | Out-Null; "
        "[ProxyVault.WinInet]::InternetSetOption([System.IntPtr]::Zero, 37, [System.IntPtr]::Zero, 0) | Out-Null"
    )


def _clear_script() -> str:
    return (
        "$settings='HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'; "
        "Set-ItemProperty -Path $settings -Name ProxyEnable -Type DWord -Value 0; "
        "Set-ItemProperty -Path $settings -Name ProxyServer -Value ''; "
        "Set-ItemProperty -Path $settings -Name ProxyOverride -Value ''; "
        "Add-Type -Namespace ProxyVault -Name WinInet -MemberDefinition "
        "\"[System.Runtime.InteropServices.DllImport('wininet.dll', SetLastError=true)] "
        "public static extern bool InternetSetOption(System.IntPtr hInternet, int dwOption, "
        "System.IntPtr lpBuffer, int dwBufferLength);\"; "
        "[ProxyVault.WinInet]::InternetSetOption([System.IntPtr]::Zero, 39, [System.IntPtr]::Zero, 0) | Out-Null; "
        "[ProxyVault.WinInet]::InternetSetOption([System.IntPtr]::Zero, 37, [System.IntPtr]::Zero, 0) | Out-Null"
    )
