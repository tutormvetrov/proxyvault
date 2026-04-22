from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse

import requests

from app.parser import parse_subscription_payload


class SubscriptionSecurityError(ValueError):
    pass


def looks_like_subscription_url_candidate(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("http://", "https://")) and "\n" not in stripped


def validate_subscription_url(url: str, *, allow_insecure_http: bool = False) -> str:
    stripped = url.strip()
    if not looks_like_subscription_url_candidate(stripped):
        raise SubscriptionSecurityError("Enter a valid subscription URL.")
    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SubscriptionSecurityError("Enter a valid subscription URL.")
    if parsed.scheme == "http" and not allow_insecure_http:
        raise SubscriptionSecurityError(
            "HTTP subscription URLs are blocked by default. Enable "
            "'Allow insecure HTTP subscription URLs' in Settings to use one."
        )
    return stripped


def validate_subscription_response_url(
    requested_url: str,
    final_url: str,
    *,
    allow_insecure_http: bool = False,
) -> str:
    requested = urlparse(requested_url.strip())
    parsed_final = urlparse(final_url.strip())
    if parsed_final.scheme not in {"http", "https"} or not parsed_final.netloc:
        raise SubscriptionSecurityError("Subscription fetch was redirected to an unsupported destination.")
    if requested.scheme == "https" and parsed_final.scheme == "http":
        raise SubscriptionSecurityError("Subscription fetch was blocked because an HTTPS URL redirected to HTTP.")
    if parsed_final.scheme == "http" and not allow_insecure_http:
        raise SubscriptionSecurityError(
            "Subscription fetch was blocked because the final URL uses insecure HTTP. "
            "Enable 'Allow insecure HTTP subscription URLs' in Settings to allow it."
        )
    return final_url.strip()


def fetch_subscription_url_payload(
    url: str,
    *,
    allow_insecure_http: bool = False,
    timeout: int = 12,
    request_get: Callable[..., Any] = requests.get,
    progress_callback=None,
) -> dict[str, Any]:
    _ = progress_callback
    normalized_url = validate_subscription_url(url, allow_insecure_http=allow_insecure_http)
    response = request_get(normalized_url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    final_url = validate_subscription_response_url(
        normalized_url,
        str(getattr(response, "url", normalized_url) or normalized_url),
        allow_insecure_http=allow_insecure_http,
    )
    fmt, items = parse_subscription_payload(response.text)
    return {"format_name": fmt.value, "items": items, "final_url": final_url}
