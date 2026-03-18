import hashlib
import hmac
import logging

from flask import current_app, request

logger = logging.getLogger(__name__)


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

    app_secret: str = current_app.config["WA_APP_SECRET"]

    expected = hmac.new(
        app_secret.encode(),
        request.get_data(),
        hashlib.sha256,
    ).hexdigest()

    received = signature_header.removeprefix("sha256=")

    if not hmac.compare_digest(expected, received):
        logger.warning("Webhook signature mismatch – possible spoofed request")
        return False

    return True
