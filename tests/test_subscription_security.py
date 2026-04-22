from __future__ import annotations

import unittest

from app.subscriptions import (
    SubscriptionSecurityError,
    fetch_subscription_url_payload,
    validate_subscription_response_url,
    validate_subscription_url,
)


class FakeResponse:
    def __init__(self, text: str, url: str, status_code: int = 200):
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class SubscriptionSecurityTests(unittest.TestCase):
    def test_https_url_is_allowed_by_default(self) -> None:
        validated = validate_subscription_url("https://example.com/subscription")
        self.assertEqual(validated, "https://example.com/subscription")

    def test_http_url_is_blocked_by_default(self) -> None:
        with self.assertRaises(SubscriptionSecurityError):
            validate_subscription_url("http://example.com/subscription")

    def test_http_url_is_allowed_when_override_enabled(self) -> None:
        validated = validate_subscription_url(
            "http://example.com/subscription",
            allow_insecure_http=True,
        )
        self.assertEqual(validated, "http://example.com/subscription")

    def test_https_redirect_to_http_is_blocked_even_with_override(self) -> None:
        with self.assertRaises(SubscriptionSecurityError):
            validate_subscription_response_url(
                "https://example.com/subscription",
                "http://mirror.example.com/feed",
                allow_insecure_http=True,
            )

    def test_fetch_payload_blocks_downgrade_redirect(self) -> None:
        def fake_get(url: str, **_kwargs) -> FakeResponse:
            return FakeResponse(
                "trojan://secret@trojan.example.com:443#Node",
                "http://mirror.example.com/feed",
            )

        with self.assertRaises(SubscriptionSecurityError):
            fetch_subscription_url_payload(
                "https://example.com/subscription",
                allow_insecure_http=True,
                request_get=fake_get,
            )

    def test_fetch_payload_allows_http_when_override_enabled(self) -> None:
        def fake_get(url: str, **_kwargs) -> FakeResponse:
            return FakeResponse(
                "trojan://secret@trojan.example.com:443#Node",
                "http://mirror.example.com/feed",
            )

        payload = fetch_subscription_url_payload(
            "http://example.com/subscription",
            allow_insecure_http=True,
            request_get=fake_get,
        )

        self.assertEqual(payload["format_name"], "plain_uri_list")
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["final_url"], "http://mirror.example.com/feed")


if __name__ == "__main__":
    unittest.main()
