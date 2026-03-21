"""
listener.py — Telethon user-client that monitors a Telegram channel for
              Pikud HaOref alerts and forwards personalised notifications
              to registered users via the bot client.

Event classification (priority order):
  "התרעה מקדימה"          → Event: "התרעה מקדימה",  Emoji: 🟠
  "טילים" OR "רקטות"      → Event: "ירי טילים",      Emoji: 🔴
  "הסתיים" OR "חזרה לשגרה"→ Event: "האירוע הסתיים", Emoji: 🟢
  (default)                → Event: "התרעה",          Emoji: 🟡

Message format: "{Emoji} {location1}, {location2} {Event}"
"""

import os
import logging

from telethon import TelegramClient, events

from database import get_all_users

logger = logging.getLogger(__name__)


def _classify_message(text: str) -> tuple[str, str]:
    """Return (emoji, event_name) based on message keywords."""
    if "התרעה מקדימה" in text:
        return "🟠", "התרעה מקדימה"
    if "טילים" in text or "רקטות" in text:
        return "🔴", "ירי טילים"
    if "הסתיים" in text or "חזרה לשגרה" in text:
        return "🟢", "האירוע הסתיים"
    return "🟡", "התרעה"


def setup_listener(
    listener_client: TelegramClient,
    bot_client: TelegramClient,
) -> None:
    """Register the NewMessage handler on the listener (user) client."""
    target_channel: str = os.environ["TARGET_CHANNEL"]

    @listener_client.on(events.NewMessage(chats=target_channel))
    async def on_channel_message(event: events.NewMessage.Event) -> None:
        message_text: str = event.raw_text or ""
        if not message_text:
            return

        emoji, event_name = _classify_message(message_text)

        users = await get_all_users()

        for chat_id, locations in users:
            if not locations:
                continue

            # Collect all of the user's locations that appear in the message
            matched_locations = [
                loc for loc in locations if loc in message_text
            ]

            if not matched_locations:
                continue

            # Explicit join — never passes a raw list into the f-string
            locations_str = ", ".join(matched_locations)
            notification = f"{emoji} {locations_str} {event_name}"

            try:
                await bot_client.send_message(chat_id, notification)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to notify chat_id=%s: %s", chat_id, exc
                )

    logger.info("Listener registered on channel: %s", target_channel)
