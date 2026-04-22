from __future__ import annotations

import socket
import unittest

from app.runtime.ports import PortAllocationError, reserve_local_ports


class PortAllocationTests(unittest.TestCase):
    def test_override_ports_are_reserved_and_distinct(self) -> None:
        reservation = reserve_local_ports(http_override=18080, socks_override=11080)
        self.addCleanup(reservation.close)

        self.assertEqual(reservation.http_port, 18080)
        self.assertEqual(reservation.socks_port, 11080)
        self.assertNotEqual(reservation.http_port, reservation.socks_port)

    def test_busy_override_port_raises_explicit_error(self) -> None:
        busy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy_socket.bind(("127.0.0.1", 18081))
        busy_socket.listen(1)
        self.addCleanup(busy_socket.close)

        with self.assertRaises(PortAllocationError):
            reserve_local_ports(http_override=18081, socks_override=11081)

    def test_auto_selected_ports_remain_reserved_until_released(self) -> None:
        reservation = reserve_local_ports()
        self.assertNotEqual(reservation.http_port, reservation.socks_port)

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(probe.close)
        with self.assertRaises(OSError):
            probe.bind(("127.0.0.1", reservation.http_port))

        reservation.close()
        rebound = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(rebound.close)
        rebound.bind(("127.0.0.1", reservation.http_port))


if __name__ == "__main__":
    unittest.main()
