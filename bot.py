"""
bot.py — User-facing Telegram bot built with Telethon.

Handler table:
  /start (registered user)  → welcome back + prompt for locations (no code needed)
  /start [code] (new user)  → register if code matches, then prompt for locations
  /start (new user, no code)→ silent drop (fast-fail)
  /edit (registered)        → prompt for new location list
  /list (registered)        → return bare comma-joined location string
  <text while awaiting>     → parse (comma-separated OR single location), save to DB
  <any other> (unregistered)→ silent drop (fast-fail)
"""

import os
import logging

from telethon import TelegramClient, events

from database import (
    is_registered,
    register_user,
    set_locations,
    get_locations,
)

logger = logging.getLogger(__name__)

# Sentinel: users who are mid-flow waiting to send a location list
_awaiting_locations: set[int] = set()


def create_bot_client(api_id: int, api_hash: str, bot_token: str) -> TelegramClient:
    """Create and configure the Telethon bot client with all event handlers."""
    bot = TelegramClient("bot", api_id, api_hash)
    secret_code = os.environ["SECRET_INVITE_CODE"]

    # ------------------------------------------------------------------ /start
    @bot.on(events.NewMessage(pattern=r"^/start(.*)$"))
    async def start_handler(event: events.NewMessage.Event) -> None:
        chat_id: int = event.chat_id
        already_registered = await is_registered(chat_id)

        if already_registered:
            # Returning user — no code required, just welcome back
            _awaiting_locations.add(chat_id)
            await event.respond(
                "ברוך שובך! 👋\n"
                "שלח/י יישוב אחד או רשימה מופרדת בפסיקים כדי לעדכן את המיקומים שלך.\n"
                "לדוגמה: `תל אביב` או `תל אביב, רמת גן, פתח תקווה`"
            )
            raise events.StopPropagation

        # New user — validate the secret code
        provided_code = event.pattern_match.group(1).strip()
        if provided_code != secret_code:
            # Fast-fail: no response to unrecognised attempts
            raise events.StopPropagation

        # Valid code → register and prompt
        await register_user(chat_id)
        _awaiting_locations.add(chat_id)
        await event.respond(
            "ברוך הבא! ✅ נרשמת בהצלחה.\n"
            "שלח/י יישוב אחד או רשימה מופרדת בפסיקים כדי לקבל התרעות.\n"
            "לדוגמה: `תל אביב` או `תל אביב, רמת גן, פתח תקווה`"
        )
        raise events.StopPropagation

    # ------------------------------------------------------------------ /edit
    @bot.on(events.NewMessage(pattern=r"^/edit$"))
    async def edit_handler(event: events.NewMessage.Event) -> None:
        chat_id: int = event.chat_id
        if not await is_registered(chat_id):
            raise events.StopPropagation  # fast-fail

        _awaiting_locations.add(chat_id)
        await event.respond(
            "שלח/י יישוב אחד או רשימה מופרדת בפסיקים — זה יחליף את הרשימה הקיימת."
        )
        raise events.StopPropagation

    # ------------------------------------------------------------------ /list
    @bot.on(events.NewMessage(pattern=r"^/list$"))
    async def list_handler(event: events.NewMessage.Event) -> None:
        chat_id: int = event.chat_id
        if not await is_registered(chat_id):
            raise events.StopPropagation  # fast-fail

        locations = await get_locations(chat_id)
        if locations:
            await event.respond(", ".join(locations))
        else:
            await event.respond("אין מיקומים שמורים עדיין.")
        raise events.StopPropagation

    # ------------------------------------------------------------------ text
    @bot.on(events.NewMessage())
    async def text_handler(event: events.NewMessage.Event) -> None:
        chat_id: int = event.chat_id
        text: str = event.raw_text.strip()

        # Fast-fail for unregistered users
        if not await is_registered(chat_id):
            return

        # Accept any non-empty text while user is in the location-entry flow.
        # Split by comma if present; otherwise treat the whole message as one location.
        if chat_id in _awaiting_locations and text:
            locations = [loc.strip() for loc in text.split(",") if loc.strip()]
            await set_locations(chat_id, locations)
            _awaiting_locations.discard(chat_id)
            await event.respond(
                f"✅ המיקומים עודכנו: {', '.join(locations)}"
            )

    return bot
