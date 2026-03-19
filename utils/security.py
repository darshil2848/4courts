import hashlib
import hmac
import logging

from flask import current_app, request

logger = logging.getLogger(__name__)


def _normalize_secret(secret: str) -> str:
    cleaned = secret.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        return cleaned[1:-1]
    return cleaned


def _parse_signature_header(signature_header: str) -> str | None:
    """Extract sha256 digest from X-Hub-Signature-256 header.

    Accepts case-insensitive algorithm prefix and trims surrounding whitespace.
    Returns None when the header is malformed or uses a non-sha256 algorithm.
    """
    header = signature_header.strip()
    if not header or "=" not in header:
        return None

    algorithm, _, digest = header.partition("=")
    if algorithm.strip().lower() != "sha256":
        return None

    cleaned_digest = digest.strip().lower()
    return cleaned_digest or None


def verify_webhook_signature() -> bool:
    """Validate the X-Hub-Signature-256 header sent by Meta.

    Meta signs every webhook POST with HMAC-SHA256 using the App Secret.
    Reject requests whose signature does not match to prevent spoofing.

    Returns:
        True  – signature present and valid.
        False – signature missing or invalid (request should be rejected).
    """
    signature_header: str | None = request.headers.get("X-Hub-Signature-256")
    if not signature_header:
        logger.warning("Webhook request missing X-Hub-Signature-256 header")
        return False

    app_secret: str = _normalize_secret(current_app.config["WA_APP_SECRET"])
    received = _parse_signature_header(signature_header)
    if not received:
        logger.warning("Webhook signature header malformed or non-sha256")
        return False

    expected = hmac.new(
        app_secret.encode(),
        request.get_data(cache=True, as_text=False),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, received):
        logger.warning(
            "Webhook signature mismatch – possible spoofed request (expected_len=%d received_len=%d body_len=%d expected_prefix=%s received_prefix=%s)",
            len(expected),
            len(received),
            len(request.get_data(cache=True, as_text=False)),
            expected[:8],
            received[:8],
        )
        return False

    return True
