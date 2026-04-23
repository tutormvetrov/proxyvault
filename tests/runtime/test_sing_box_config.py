from __future__ import annotations

import base64
import unittest
from dataclasses import replace

from app.models import ProxyEntry
from app.parser import parse_proxy_text
from app.runtime.adapters.sing_box import SingBoxConfigError, build_sing_box_config


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


def _ss_uri(method: str = "chacha20-ietf-poly1305", password: str = "secret") -> str:
    payload = base64.urlsafe_b64encode(f"{method}:{password}".encode("utf-8")).decode("utf-8")
    return (
        "ss://"
        f"{payload}@ss.example.com:8388"
        "?plugin=v2ray-plugin%3Bmode%3Dwebsocket%3Bhost%3Dcdn.example.com"
        "#shadowsocks"
    )


class SingBoxConfigBuilderTests(unittest.TestCase):
    def test_build_vless_reality_config(self) -> None:
        entry = _entry_from_uri(
            "vless://11111111-1111-1111-1111-111111111111@reality.example.com:443"
            "?security=reality&pbk=testpublickey&sni=www.example.com&fp=chrome&sid=1a2b3c4d"
            "#reality"
        )

        config = build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")
        outbound = config["outbounds"][0]

        self.assertEqual(outbound["type"], "vless")
        self.assertEqual(outbound["tls"]["reality"]["public_key"], "testpublickey")
        self.assertEqual(outbound["tls"]["utls"]["fingerprint"], "chrome")
        self.assertNotIn("transport", outbound)

    def test_build_vless_ws_config(self) -> None:
        entry = _entry_from_uri(
            "vless://11111111-1111-1111-1111-111111111111@ws.example.com:443"
            "?type=ws&security=tls&host=cdn.example.com&path=%2Fwebsocket&sni=cdn.example.com"
            "#ws"
        )

        outbound = build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")[
            "outbounds"
        ][0]

        self.assertEqual(outbound["transport"]["type"], "ws")
        self.assertEqual(outbound["transport"]["path"], "/websocket")
        self.assertEqual(outbound["transport"]["headers"]["Host"], "cdn.example.com")

    def test_build_vless_xhttp_config_maps_to_http_transport(self) -> None:
        entry = _entry_from_uri(
            "vless://11111111-1111-1111-1111-111111111111@xh.example.com:443"
            "?type=xhttp&security=tls&host=cdn.example.com&path=%2Fxhttp&sni=cdn.example.com"
            "#xhttp"
        )

        outbound = build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")[
            "outbounds"
        ][0]

        self.assertEqual(outbound["transport"]["type"], "http")
        self.assertEqual(outbound["transport"]["host"], ["cdn.example.com"])
        self.assertEqual(outbound["transport"]["path"], "/xhttp")

    def test_build_vless_splithttp_config_maps_to_http_transport(self) -> None:
        entry = _entry_from_uri(
            "vless://11111111-1111-1111-1111-111111111111@xh.example.com:24443"
            "?type=splithttp&security=tls&host=cdn.example.com&path=%2Fxhttp&sni=cdn.example.com"
            "#xhttp"
        )

        outbound = build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")[
            "outbounds"
        ][0]

        self.assertEqual(outbound["transport"]["type"], "http")
        self.assertEqual(outbound["transport"]["host"], ["cdn.example.com"])
        self.assertEqual(outbound["transport"]["path"], "/xhttp")

    def test_build_hysteria2_config(self) -> None:
        entry = _entry_from_uri(
            "hysteria2://secret@hy.example.com:8443"
            "?sni=hy.example.com&obfs=salamander&obfs-password=mask&upmbps=20&downmbps=80"
            "#hy2"
        )

        outbound = build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")[
            "outbounds"
        ][0]

        self.assertEqual(outbound["type"], "hysteria2")
        self.assertEqual(outbound["obfs"]["type"], "salamander")
        self.assertEqual(outbound["up_mbps"], 20)
        self.assertEqual(outbound["down_mbps"], 80)

    def test_build_shadowsocks_config(self) -> None:
        entry = _entry_from_uri(_ss_uri())

        outbound = build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")[
            "outbounds"
        ][0]

        self.assertEqual(outbound["type"], "shadowsocks")
        self.assertEqual(outbound["plugin"], "v2ray-plugin")
        self.assertIn("host=cdn.example.com", outbound["plugin_opts"])

    def test_build_trojan_config(self) -> None:
        entry = _entry_from_uri(
            "trojan://secret@trojan.example.com:443"
            "?sni=trojan.example.com&type=ws&host=cdn.example.com&path=%2Ftrojan"
            "#trojan"
        )

        outbound = build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")[
            "outbounds"
        ][0]

        self.assertEqual(outbound["type"], "trojan")
        self.assertEqual(outbound["transport"]["type"], "ws")
        self.assertEqual(outbound["transport"]["path"], "/trojan")

    def test_build_naive_proxy_config(self) -> None:
        entry = _entry_from_uri("https://user:pass@naive.example.com:443#naive")

        outbound = build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")[
            "outbounds"
        ][0]

        self.assertEqual(outbound["type"], "naive")
        self.assertEqual(outbound["username"], "user")
        self.assertEqual(outbound["tls"]["server_name"], "naive.example.com")

    def test_other_entries_are_rejected(self) -> None:
        entry = replace(
            _entry_from_uri("https://user:pass@naive.example.com:443#naive"),
            type=parse_proxy_text("http://example.com").type,
            uri="http://example.com",
        )

        with self.assertRaises(SingBoxConfigError):
            build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")

    def test_xhttp_extra_payload_is_rejected_explicitly(self) -> None:
        entry = _entry_from_uri(
            "vless://11111111-1111-1111-1111-111111111111@xh.example.com:443"
            "?type=xhttp&security=tls&host=cdn.example.com&path=%2Fxhttp&extra=%7B%7D"
            "#xhttp"
        )

        with self.assertRaises(SingBoxConfigError):
            build_sing_box_config(entry, http_port=18080, socks_port=11080, log_path="runtime.log")


if __name__ == "__main__":
    unittest.main()
