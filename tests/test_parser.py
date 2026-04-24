from __future__ import annotations

import base64
import unittest

from app.models import ProxyType, SubscriptionFormat
from app.parser import ParseError, parse_proxy_text, parse_subscription_payload


class ParserTests(unittest.TestCase):
    def test_parse_vless_xhttp_reality_uri(self) -> None:
        uri = (
            "vless://4d94c6b8-4b93-48b3-949d-9d20f9757f45@45.140.205.4:8443"
            "?type=xhttp&security=reality&pbk=test-public-key&sni=example.com"
            "&path=%2Fgateway#Reality-XHTTP"
        )

        parsed = parse_proxy_text(uri)

        self.assertEqual(parsed.type, ProxyType.VLESS_XHTTP)
        self.assertEqual(parsed.transport, "xhttp+reality")
        self.assertEqual(parsed.server_host, "45.140.205.4")
        self.assertEqual(parsed.server_port, 8443)
        self.assertEqual(parsed.display_name, "Reality-XHTTP")
        self.assertEqual(parsed.params["uuid"], "4d94c6b8-4b93-48b3-949d-9d20f9757f45")
        self.assertEqual(parsed.params["pbk"], "test-public-key")
        self.assertEqual(parsed.params["path"], "/gateway")

    def test_parse_vless_splithttp_tls_uri_as_xhttp(self) -> None:
        uri = (
            "vless://4d94c6b8-4b93-48b3-949d-9d20f9757f45@xh.example.com:24443"
            "?type=splithttp&security=tls&sni=xh.example.com&host=cdn.example.com"
            "&path=%2Fxhttp#SplitHTTP"
        )

        parsed = parse_proxy_text(uri)

        self.assertEqual(parsed.type, ProxyType.VLESS_XHTTP)
        self.assertEqual(parsed.transport, "splithttp+tls")
        self.assertEqual(parsed.server_host, "xh.example.com")
        self.assertEqual(parsed.server_port, 24443)
        self.assertEqual(parsed.display_name, "SplitHTTP")

    def test_parse_wireguard_block(self) -> None:
        config = """
[Interface]
Address = 10.0.0.2/32
DNS = 1.1.1.1
PrivateKey = private-key

[Peer]
PublicKey = public-key
AllowedIPs = 0.0.0.0/0
Endpoint = wg.example.com:51820
PersistentKeepalive = 25
""".strip()

        parsed = parse_proxy_text(config)

        self.assertEqual(parsed.type, ProxyType.WIREGUARD)
        self.assertEqual(parsed.transport, "udp")
        self.assertEqual(parsed.server_host, "wg.example.com")
        self.assertEqual(parsed.server_port, 51820)
        self.assertEqual(parsed.params["endpoint"], "wg.example.com:51820")
        self.assertEqual(parsed.params["public_key"], "public-key")

    def test_parse_amneziawg_block(self) -> None:
        config = """
[Interface]
Address = 10.8.0.2/32
DNS = 1.1.1.1
PrivateKey = private-key
Jc = 3
Jmin = 40
Jmax = 70
S1 = 20
S2 = 40
H1 = 11111111
H2 = 22222222
H3 = 33333333
H4 = 44444444
I1 = <r 2><b 0x01020304>

[Peer]
PublicKey = public-key
AllowedIPs = 0.0.0.0/0
Endpoint = awg.example.com:51820
PersistentKeepalive = 25
""".strip()

        parsed = parse_proxy_text(config)

        self.assertEqual(parsed.type, ProxyType.AMNEZIAWG)
        self.assertEqual(parsed.transport, "udp")
        self.assertEqual(parsed.server_host, "awg.example.com")
        self.assertEqual(parsed.server_port, 51820)
        self.assertEqual(parsed.params["endpoint"], "awg.example.com:51820")
        self.assertEqual(parsed.params["jc"], "3")
        self.assertEqual(parsed.params["h4"], "44444444")
        self.assertEqual(parsed.params["i1"], "<r 2><b 0x01020304>")

    def test_parse_base64_subscription_payload(self) -> None:
        ss_auth = base64.urlsafe_b64encode(b"aes-128-gcm:secret").decode("utf-8").rstrip("=")
        payload = "\n".join(
            [
                f"ss://{ss_auth}@ss.example.com:8388#SS Node",
                "trojan://secret@trojan.example.com:443?sni=cdn.example.com#Trojan Node",
            ]
        )
        encoded = base64.b64encode(payload.encode("utf-8")).decode("utf-8")

        fmt, items = parse_subscription_payload(encoded)

        self.assertEqual(fmt, SubscriptionFormat.BASE64_URI_LIST)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].parsed.type, ProxyType.SHADOWSOCKS)
        self.assertEqual(items[1].parsed.type, ProxyType.TROJAN)

    def test_parse_clash_yaml_payload(self) -> None:
        payload = """
proxies:
  - name: Clash Trojan
    type: trojan
    server: trojan.example.com
    port: 443
    password: secret
    sni: edge.example.com
""".strip()

        fmt, items = parse_subscription_payload(payload)

        self.assertEqual(fmt, SubscriptionFormat.CLASH_YAML)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "Clash Trojan")
        self.assertEqual(items[0].parsed.type, ProxyType.TROJAN)
        self.assertEqual(items[0].parsed.server_host, "trojan.example.com")

    def test_malformed_uri_raises_parse_error_not_foreign_exception(self) -> None:
        with self.assertRaises(ParseError):
            parse_proxy_text("ss://broken-base64@127.0.0.1:8388#bad")

        with self.assertRaises(ParseError):
            parse_proxy_text("trojan://secret@example.com:not-a-port#bad")

    def test_subscription_skips_malformed_lines(self) -> None:
        payload = "\n".join(
            [
                "ss://broken-base64@127.0.0.1:8388#bad",
                "trojan://secret@trojan.example.com:443?sni=cdn.example.com#Trojan Node",
                "vless://uuid@example.com:not-a-port#bad",
            ]
        )

        fmt, items = parse_subscription_payload(payload)

        self.assertEqual(fmt, SubscriptionFormat.PLAIN_URI_LIST)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "Trojan Node")


if __name__ == "__main__":
    unittest.main()
