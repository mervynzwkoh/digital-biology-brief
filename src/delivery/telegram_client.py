"""Telegram Bot API client for sending digest messages.

Simple wrapper around the Bot API using requests — no heavy SDK dependency.
Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from environment variables.
"""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"


def _get_config() -> tuple[str, str]:
    """Read Telegram config from environment."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    return token, chat_id


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a single message via the Telegram Bot API.

    Args:
        text: Message text (supports HTML formatting).
        parse_mode: Telegram parse mode ("HTML" or "Markdown").

    Returns:
        True if the message was sent successfully.
    """
    token, chat_id = _get_config()

    if not token or not chat_id:
        logger.error("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    url = f"{TELEGRAM_API_BASE.format(token=token)}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            logger.info("Telegram: message sent successfully (%d chars)", len(text))
            return True
        else:
            error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            logger.error(
                "Telegram: failed to send message — status %d, error: %s",
                resp.status_code,
                error_data.get("description", resp.text[:200]),
            )
            return False
    except requests.RequestException as exc:
        logger.error("Telegram: request failed: %s", exc)
        return False


def send_digest(messages: list[str]) -> bool:
    """Send a list of digest messages, with a brief pause between them.

    Args:
        messages: List of formatted message strings.

    Returns:
        True if all messages were sent successfully.
    """
    if not messages:
        logger.warning("Telegram: no messages to send")
        return True

    token, chat_id = _get_config()
    if not token or not chat_id:
        logger.error("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    all_ok = True

    for i, message in enumerate(messages):
        if i > 0:
            time.sleep(1)  # Avoid hitting rate limits

        success = send_message(message)
        if not success:
            all_ok = False
            logger.error("Telegram: failed to send message %d of %d", i + 1, len(messages))

    logger.info("Telegram: sent %d messages, all_ok=%s", len(messages), all_ok)
    return all_ok
