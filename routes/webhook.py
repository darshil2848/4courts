import logging
import re
from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request

from services.whatsapp_service import (
    WhatsAppError,
    send_interactive_list,
    send_reply_buttons,
    send_text,
)
from services.playo_service import PlayoError, get_slots_for_band
from utils.security import verify_webhook_signature

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__)

_GREETING_PATTERN = re.compile(r"\b(hi|hello|hey|hii|helo|hola)\b", re.IGNORECASE)
_WELCOME_PROMPT = "Welcome to 4courts! Please select an option:"
_WELCOME_BUTTONS = [
    {"id": "today_slots", "title": "Today's slots"},
    {"id": "tomorrow_slots", "title": "Tomorrow's slots"},
]
_SLOT_LABELS = {
    "today_slots": "today",
    "tomorrow_slots": "tomorrow",
}
_TIME_BANDS = [
    ("morning", "Morning", "6am - 12pm"),
    ("afternoon", "Afternoon", "12pm - 5pm"),
    ("evening", "Evening", "5pm - 9pm"),
    ("night", "Night", "9pm - 1am"),
]
_TIME_BAND_CONFIRMATIONS = {
    "morning": "Morning (6am - 12pm)",
    "afternoon": "Afternoon (12pm - 5pm)",
    "evening": "Evening (5pm - 9pm)",
    "night": "Night (9pm - 1am)",
}


def _get_first_query_value(*keys: str) -> str | None:
    for key in keys:
        value = request.args.get(key)
        if value is not None:
            return value
    return None


def _is_greeting(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    return bool(_GREETING_PATTERN.search(normalized))


def _send_slot_response(sender: str, button_id: str) -> None:
    day_label = _SLOT_LABELS.get(button_id)
    if not day_label:
        return

    rows = [
        {
            "id": f"{button_id}:{band_id}",
            "title": band_title,
            "description": band_window,
        }
        for band_id, band_title, band_window in _TIME_BANDS
    ]

    send_interactive_list(
        sender,
        body=f"Choose a time range for {day_label}:",
        button_text="Select time",
        section_title="Available time ranges",
        rows=rows,
    )
    logger.info("Sent time-range list to %s for button_id=%s", sender, button_id)


def _send_time_band_confirmation(sender: str, row_id: str) -> None:
    if ":" not in row_id:
        return

    day_key, band_key = row_id.split(":", 1)
    day_label = _SLOT_LABELS.get(day_key)
    band_label = _TIME_BAND_CONFIRMATIONS.get(band_key)
    if not day_label or not band_label:
        return

    # Compute date based on day selection
    today = datetime.now().date()
    if day_key == "today_slots":
        target_date = today
    elif day_key == "tomorrow_slots":
        target_date = today + timedelta(days=1)
    else:
        send_text(sender, "Invalid date selection. Please try again.")
        return

    date_str = target_date.strftime("%Y-%m-%d")

    # Fetch slots from Playo for the selected band
    try:
        slots = get_slots_for_band(date_str, band_key)
        logger.info(
            "Fetched %d slots for %s/%s",
            len(slots),
            day_label,
            band_label,
        )

        if not slots:
            send_text(
                sender,
                f"No slots available for {band_label} on {day_label}.",
            )
            return

        # Build interactive list from slots
        rows = []
        for slot in slots[:10]:  # Limit to 10 (WhatsApp list max)
            start_time = slot.get("startTime", "N/A")
            end_time = slot.get("endTime", "N/A")
            price = slot.get("price", "N/A")
            slot_id = slot.get("id", "")

            if not slot_id:
                continue

            rows.append(
                {
                    "id": f"{day_key}:{band_key}:{slot_id}",
                    "title": f"{start_time} - {end_time}",
                    "description": f"₹{price}",
                }
            )

        if not rows:
            send_text(sender, "Could not parse available slots.")
            return

        send_interactive_list(
            sender,
            body=f"Available slots for {band_label} on {day_label}:",
            button_text="Pick a slot",
            section_title="Time slots",
            rows=rows,
        )
        logger.info("Sent slot list to %s (%d slots)", sender, len(rows))

    except PlayoError as exc:
        logger.exception(
            "Playo API error for %s/%s (status=%s)",
            day_label,
            band_key,
            exc.status_code,
        )
        send_text(
            sender,
            f"Could not fetch slots. Please try again later.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# GET /webhook  – Meta verification handshake
# ─────────────────────────────────────────────────────────────────────────────
@webhook_bp.get("", strict_slashes=False)
@webhook_bp.get("/", strict_slashes=False)
def verify():
    """Meta calls this once when you register the webhook URL.

    It sends three query params:
        hub.mode           – must be "subscribe"
        hub.verify_token   – must match WHATSAPP_WEBHOOK_VERIFY_TOKEN
        hub.challenge      – echo this value back to confirm
    """
    mode: str | None = _get_first_query_value("hub.mode", "hub_mode", "hub[mode]")
    token: str | None = _get_first_query_value(
        "hub.verify_token",
        "hub_verify_token",
        "hub[verify_token]",
    )
    challenge: str | None = _get_first_query_value(
        "hub.challenge",
        "hub_challenge",
        "hub[challenge]",
    )

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
@webhook_bp.post("", strict_slashes=False)
@webhook_bp.post("/", strict_slashes=False)
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

            if sender and _is_greeting(text):
                try:
                    send_reply_buttons(
                        sender,
                        body=_WELCOME_PROMPT,
                        buttons=_WELCOME_BUTTONS,
                    )
                    logger.info("Sent welcome reply buttons to %s", sender)
                except WhatsAppError as exc:
                    logger.exception(
                        "Failed to send welcome options to %s (status=%s)",
                        sender,
                        exc.status_code,
                    )

        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "button_reply":
                button_reply = interactive.get("button_reply", {})
                button_id = button_reply.get("id", "")
                button_title = button_reply.get("title", "")
                logger.info(
                    "Button reply from %s: id=%s title=%s",
                    sender,
                    button_id,
                    button_title,
                )

                if sender and button_id:
                    try:
                        _send_slot_response(sender, button_id)
                    except WhatsAppError as exc:
                        logger.exception(
                            "Failed to send slot response to %s (status=%s)",
                            sender,
                            exc.status_code,
                        )
            elif interactive.get("type") == "list_reply":
                list_reply = interactive.get("list_reply", {})
                row_id = list_reply.get("id", "")
                row_title = list_reply.get("title", "")
                logger.info(
                    "List reply from %s: id=%s title=%s",
                    sender,
                    row_id,
                    row_title,
                )

                if sender and row_id:
                    # Check if this is a time-band selection (2 parts) or slot selection (3 parts)
                    parts = row_id.split(":")
                    if len(parts) == 2:
                        # Time-band selection – fetch and show slots
                        try:
                            _send_time_band_confirmation(sender, row_id)
                        except WhatsAppError as exc:
                            logger.exception(
                                "Failed to send time-range confirmation to %s (status=%s)",
                                sender,
                                exc.status_code,
                            )
                    elif len(parts) == 3:
                        # Specific slot selection – confirm booking
                        day_key, band_key, slot_id = parts
                        day_label = _SLOT_LABELS.get(day_key, "")
                        band_label = _TIME_BAND_CONFIRMATIONS.get(band_key, "")
                        slot_time = row_title  # e.g. "10:00 - 11:00"
                        logger.info(
                            "Slot selection from %s: day=%s band=%s slot=%s time=%s",
                            sender,
                            day_key,
                            band_key,
                            slot_id,
                            slot_time,
                        )
                        try:
                            send_text(
                                sender,
                                f"Great! You've selected {slot_time} for {band_label} on {day_label}.\n\nTo complete your booking, please share the following details:\n1. Your name\n2. Number of players\n3. Any special requirements",
                            )
                            logger.info("Sent booking confirmation to %s", sender)
                        except WhatsAppError as exc:
                            logger.exception(
                                "Failed to send booking confirmation to %s (status=%s)",
                                sender,
                                exc.status_code,
                            )

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
