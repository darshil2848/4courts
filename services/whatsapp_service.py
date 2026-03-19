"""WhatsApp Cloud API – outbound messaging service.

Provides generic methods to send:
    - Text messages
    - Image messages  (by URL or pre-uploaded media ID)
    - Video messages  (by URL or pre-uploaded media ID)
    - Document files  (by URL or pre-uploaded media ID)
    - Template messages (utility helper)

All methods raise ``WhatsAppError`` on non-2xx responses so callers can
handle errors in a consistent way.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import requests
from flask import current_app

logger = logging.getLogger(__name__)


def _normalize_secret(secret: str) -> str:
    cleaned = secret.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        return cleaned[1:-1]
    return cleaned


def _build_appsecret_proof(access_token: str, app_secret: str) -> str:
    return hmac.new(
        app_secret.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Custom exception
# ─────────────────────────────────────────────────────────────────────────────
class WhatsAppError(Exception):
    """Raised when the WhatsApp Cloud API returns an error response."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"WhatsApp API error {status_code}: {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helper
# ─────────────────────────────────────────────────────────────────────────────
def _post(payload: dict) -> dict:
    """Execute a POST to the WhatsApp messages endpoint."""
    access_token: str = current_app.config["WA_ACCESS_TOKEN"]
    app_secret: str = _normalize_secret(current_app.config["WA_APP_SECRET"])
    url: str = current_app.config["WA_BASE_URL"]
    appsecret_proof: str = _build_appsecret_proof(access_token, app_secret)

    response = requests.post(
        url,
        params={"appsecret_proof": appsecret_proof},
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )

    if not response.ok:
        try:
            detail: Any = response.json()
        except ValueError:
            detail = response.text
        raise WhatsAppError(response.status_code, detail)

    return response.json()


def _base_payload(to: str) -> dict:
    return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}


def _media_object(
    *,
    media_id: str | None = None,
    link: str | None = None,
    caption: str | None = None,
    filename: str | None = None,
) -> dict:
    """Build a media object accepting either a media_id or a public URL link."""
    if not media_id and not link:
        raise ValueError("Provide either media_id or link")

    obj: dict = {}
    if media_id:
        obj["id"] = media_id
    if link:
        obj["link"] = link
    if caption:
        obj["caption"] = caption
    if filename:
        obj["filename"] = filename
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def send_text(to: str, body: str, *, preview_url: bool = False) -> dict:
    """Send a plain text message.

    Args:
        to:          Recipient phone number in E.164 format (e.g. "15551234567").
        body:        Message text (up to 4096 characters).
        preview_url: Whether to render a link preview if the body contains a URL.

    Returns:
        The raw API response dict.
    """
    payload = {
        **_base_payload(to),
        "type": "text",
        "text": {"preview_url": preview_url, "body": body},
    }
    logger.debug("send_text to=%s", to)
    return _post(payload)


def send_image(
    to: str,
    *,
    media_id: str | None = None,
    link: str | None = None,
    caption: str | None = None,
) -> dict:
    """Send an image message.

    Supply **either** ``media_id`` (from a previous media upload) or a
    publicly accessible ``link``.  The image must be JPEG or PNG and under
    5 MB when using a link.

    Args:
        to:       Recipient phone number in E.164 format.
        media_id: WhatsApp media ID returned by the media upload endpoint.
        link:     Publicly accessible URL of the image.
        caption:  Optional caption text (up to 1024 characters).

    Returns:
        The raw API response dict.
    """
    payload = {
        **_base_payload(to),
        "type": "image",
        "image": _media_object(media_id=media_id, link=link, caption=caption),
    }
    logger.debug("send_image to=%s", to)
    return _post(payload)


def send_video(
    to: str,
    *,
    media_id: str | None = None,
    link: str | None = None,
    caption: str | None = None,
) -> dict:
    """Send a video message.

    Supported formats: MP4 (H.264 video / AAC audio).  Max size is 16 MB when
    using a publicly accessible link.

    Args:
        to:       Recipient phone number in E.164 format.
        media_id: WhatsApp media ID.
        link:     Publicly accessible URL of the video.
        caption:  Optional caption text.

    Returns:
        The raw API response dict.
    """
    payload = {
        **_base_payload(to),
        "type": "video",
        "video": _media_object(media_id=media_id, link=link, caption=caption),
    }
    logger.debug("send_video to=%s", to)
    return _post(payload)


def send_document(
    to: str,
    *,
    media_id: str | None = None,
    link: str | None = None,
    caption: str | None = None,
    filename: str | None = None,
) -> dict:
    """Send a document file.

    Common supported types: PDF, DOC/DOCX, XLS/XLSX, PPT/PPTX.  Max size is
    100 MB when using a publicly accessible link.

    Args:
        to:       Recipient phone number in E.164 format.
        media_id: WhatsApp media ID.
        link:     Publicly accessible URL of the document.
        caption:  Optional caption text.
        filename: Displayed filename shown to the recipient.

    Returns:
        The raw API response dict.
    """
    payload = {
        **_base_payload(to),
        "type": "document",
        "document": _media_object(
            media_id=media_id, link=link, caption=caption, filename=filename
        ),
    }
    logger.debug("send_document to=%s filename=%s", to, filename)
    return _post(payload)


def send_template(
    to: str,
    template_name: str,
    language_code: str = "en_US",
    components: list[dict] | None = None,
) -> dict:
    """Send an approved message template.

    Args:
        to:            Recipient phone number in E.164 format.
        template_name: Name of the approved template.
        language_code: BCP-47 language code (default "en_US").
        components:    Optional list of template component objects
                       (header, body, button variables).

    Returns:
        The raw API response dict.
    """
    template: dict = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if components:
        template["components"] = components

    payload = {
        **_base_payload(to),
        "type": "template",
        "template": template,
    }
    logger.debug("send_template to=%s template=%s", to, template_name)
    return _post(payload)
