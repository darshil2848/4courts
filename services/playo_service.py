"""Playo API client for court availability slots."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

_PLAYO_BASE_URL = "https://api.playo.io/controller/ppc/availability"
_PLAYO_AUTH_TOKEN = "0147d6e0-22e0-11f1-b381-154507cf50fa:e64f4a38-dbd5-4271-bb11-1ff140a8ede1"
_PLAYO_ACTIVITY_IDS = [14425]


class PlayoError(Exception):
    """Raised when Playo API call fails."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Playo API error {status_code}: {detail}")


def _get_time_band_range(band_key: str) -> tuple[int, int]:
    """Return (start_hour, end_hour) for a time band.

    Returns 24-hour format: morning 6-12, afternoon 12-17, evening 17-21, night 21-25.
    """
    bands = {
        "morning": (6, 12),
        "afternoon": (12, 17),
        "evening": (17, 21),
        "night": (21, 25),
    }
    return bands.get(band_key, (0, 24))


def _slot_hour(slot_start_time: str) -> int | None:
    """Extract hour from slot start time (format: 'HH:MM' or similar)."""
    try:
        if ":" in slot_start_time:
            hour_str = slot_start_time.split(":")[0]
            return int(hour_str)
        return None
    except (ValueError, IndexError):
        return None


def _filter_slots_by_band(slots: list[dict], band_key: str) -> list[dict]:
    """Filter slots to only those within the given time band."""
    start_hour, end_hour = _get_time_band_range(band_key)
    filtered = []

    for slot in slots:
        slot_time = slot.get("startTime", "")
        slot_hour = _slot_hour(slot_time)

        if slot_hour is not None and start_hour <= slot_hour < end_hour:
            filtered.append(slot)

    return filtered


def fetch_availability(date_str: str) -> list[dict]:
    """Fetch availability slots from Playo for a given date.

    Args:
        date_str: Date in YYYY-MM-DD format (e.g. "2026-03-19").

    Returns:
        List of slot dicts with keys: startTime, endTime, price, etc.

    Raises:
        PlayoError on non-2xx response or parse failure.
    """
    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en-IN;q=0.9,en;q=0.8",
        "authorization": _PLAYO_AUTH_TOKEN,
        "content-type": "application/json",
        "origin": "https://dashboard.playo.club",
        "referer": "https://dashboard.playo.club/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    payload = {
        "activityIds": _PLAYO_ACTIVITY_IDS,
        "activityStartDate": date_str,
        "activityEndDate": date_str,
        "customerStatus": 0,
    }

    try:
        response = requests.post(
            _PLAYO_BASE_URL,
            headers=headers,
            json=payload,
            timeout=10,
        )

        if not response.ok:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise PlayoError(response.status_code, detail)

        data = response.json()
        logger.debug("Playo availability response for %s: %d items", date_str, len(data))
        return data

    except requests.RequestException as exc:
        logger.exception("Playo API request failed: %s", exc)
        raise PlayoError(500, str(exc)) from exc


def get_slots_for_band(date_str: str, band_key: str) -> list[dict]:
    """Fetch and filter slots for a given date and time band.

    Args:
        date_str: Date in YYYY-MM-DD format.
        band_key: One of 'morning', 'afternoon', 'evening', 'night'.

    Returns:
        List of slots within the time band.
    """
    all_slots = fetch_availability(date_str)
    filtered = _filter_slots_by_band(all_slots, band_key)
    logger.info(
        "Filtered %d slots for %s band in %s",
        len(filtered),
        band_key,
        date_str,
    )
    return filtered
