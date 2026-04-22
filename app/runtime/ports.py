from __future__ import annotations

import socket
from dataclasses import dataclass, field


LOOPBACK_HOST = "127.0.0.1"


class PortAllocationError(RuntimeError):
    """Raised when ProxyVault cannot reserve a deterministic local port pair."""


@dataclass(slots=True)
class PortReservation:
    http_port: int
    socks_port: int
    host: str = LOOPBACK_HOST
    _sockets: list[socket.socket] = field(default_factory=list, repr=False)

    def close(self) -> None:
        while self._sockets:
            sock = self._sockets.pop()
            try:
                sock.close()
            except OSError:
                continue


def reserve_local_ports(
    *,
    http_override: int | None = None,
    socks_override: int | None = None,
    host: str = LOOPBACK_HOST,
) -> PortReservation:
    if http_override is not None and socks_override is not None and http_override == socks_override:
        raise PortAllocationError("HTTP and SOCKS local ports must be different.")

    reserved_sockets: list[socket.socket] = []
    try:
        http_socket, http_port = _reserve_port(http_override, host=host)
        reserved_sockets.append(http_socket)

        socks_socket, socks_port = _reserve_port(socks_override, host=host)
        if socks_port == http_port:
            socks_socket.close()
            socks_socket, socks_port = _reserve_port(None, host=host)
        reserved_sockets.append(socks_socket)
        return PortReservation(
            http_port=http_port,
            socks_port=socks_port,
            host=host,
            _sockets=reserved_sockets,
        )
    except Exception:
        for sock in reserved_sockets:
            try:
                sock.close()
            except OSError:
                continue
        raise


def _reserve_port(port: int | None, *, host: str) -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, int(port or 0)))
        sock.listen(1)
    except OSError as exc:
        requested = f"override port {port}" if port else "an auto-selected port"
        sock.close()
        raise PortAllocationError(f"Unable to reserve {requested} on {host}: {exc}") from exc
    return sock, int(sock.getsockname()[1])
