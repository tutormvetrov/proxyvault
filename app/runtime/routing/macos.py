from __future__ import annotations

from app.runtime.routing.system_proxy import CommandResult, CommandRunner, ProxyEndpoint, SystemProxyCommandError


class MacOSSystemProxyBackend:
    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def apply(self, endpoint: ProxyEndpoint) -> None:
        services = self._network_services()
        for service in services:
            self._checked_run(["networksetup", "-setwebproxy", service, endpoint.host, str(endpoint.port)])
            self._checked_run(["networksetup", "-setsecurewebproxy", service, endpoint.host, str(endpoint.port)])
            self._checked_run(["networksetup", "-setwebproxystate", service, "on"])
            self._checked_run(["networksetup", "-setsecurewebproxystate", service, "on"])

    def clear(self) -> None:
        for service in self._network_services():
            self._checked_run(["networksetup", "-setwebproxystate", service, "off"])
            self._checked_run(["networksetup", "-setsecurewebproxystate", service, "off"])

    def _network_services(self) -> list[str]:
        result = self._runner.run(["networksetup", "-listallnetworkservices"])
        if result.returncode != 0:
            raise SystemProxyCommandError(result.stderr.strip() or "Unable to list macOS network services.")
        services: list[str] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("An asterisk"):
                continue
            if stripped.startswith("*"):
                continue
            services.append(stripped)
        if not services:
            raise SystemProxyCommandError("No enabled macOS network services were found.")
        return services

    def _checked_run(self, command: list[str]) -> CommandResult:
        result = self._runner.run(command)
        if result.returncode != 0:
            raise SystemProxyCommandError(result.stderr.strip() or f"Command failed: {' '.join(command)}")
        return result
