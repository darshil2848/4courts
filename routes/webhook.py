import logging

from flask import Blueprint, current_app, jsonify, request

from utils.security import verify_webhook_signature

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# GET /webhook  – Meta verification handshake
# ─────────────────────────────────────────────────────────────────────────────
@webhook_bp.get("/")
def verify():
    """Meta calls this once when you register the webhook URL.

    It sends three query params:
        hub.mode           – must be "subscribe"
        hub.verify_token   – must match WHATSAPP_WEBHOOK_VERIFY_TOKEN
        hub.challenge      – echo this value back to confirm
    """
    mode: str | None = request.args.get("hub.mode")
    token: str | None = request.args.get("hub.verify_token")
    challenge: str | None = request.args.get("hub.challenge")

    expected_token: str = current_app.config["WA_WEBHOOK_VERIFY_TOKEN"]

    if mode != "subscribe":
        logger.warning(
            "Webhook verification failed – unexpected hub.mode='%s' (expected 'subscribe')",
            mode,
        )
        return jsonify({"error": "Forbidden"}), 403

    if token != expected_token:
        logger.warning(
            "Webhook verification failed – hub.verify_token mismatch "
            "(received %d chars, expected %d chars)",
            len(token or ""),
            len(expected_token),
        )
        return jsonify({"error": "Forbidden"}), 403

    if not challenge:
        logger.warning("Webhook verification failed – hub.challenge missing")
        return jsonify({"error": "Forbidden"}), 403

    logger.info("Webhook verified by Meta")
    return challenge, 200


# ─────────────────────────────────────────────────────────────────────────────
# POST /webhook  – Incoming events from Meta
# ─────────────────────────────────────────────────────────────────────────────
@webhook_bp.post("/")
def receive():
    """Receives all WhatsApp event notifications (messages, statuses, etc.)."""
    if not verify_webhook_signature():
        return jsonify({"error": "Forbidden"}), 403

    payload: dict = request.get_json(silent=True) or {}

    if payload.get("object") != "whatsapp_business_account":
        return jsonify({"error": "Unrecognised object type"}), 400

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            _handle_messages(value.get("messages", []))
            _handle_statuses(value.get("statuses", []))

    # Always return 200 quickly so Meta does not retry
    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────
def _handle_messages(messages: list[dict]) -> None:
    for msg in messages:
        msg_type = msg.get("type")
        sender = msg.get("from")

        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
            logger.info("Text message from %s: %s", sender, text)

        elif msg_type == "image":
            media_id = msg.get("image", {}).get("id")
            logger.info("Image from %s, media_id=%s", sender, media_id)

        elif msg_type == "video":
            media_id = msg.get("video", {}).get("id")
            logger.info("Video from %s, media_id=%s", sender, media_id)

        elif msg_type == "document":
            media_id = msg.get("document", {}).get("id")
            filename = msg.get("document", {}).get("filename")
            logger.info("Document from %s, media_id=%s, filename=%s", sender, media_id, filename)

        elif msg_type == "audio":
            media_id = msg.get("audio", {}).get("id")
            logger.info("Audio from %s, media_id=%s", sender, media_id)

        else:
            logger.info("Unhandled message type '%s' from %s", msg_type, sender)


def _handle_statuses(statuses: list[dict]) -> None:
    for status in statuses:
        logger.info(
            "Message status update: id=%s status=%s recipient=%s",
            status.get("id"),
            status.get("status"),
            status.get("recipient_id"),
        )
