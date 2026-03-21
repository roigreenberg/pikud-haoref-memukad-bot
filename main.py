"""
main.py — Entry point. Loads environment, initialises DB, and runs both
           the bot client (BotClient) and the user listener client concurrently.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

from database import init_db
from bot import create_bot_client
from listener import setup_listener

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    load_dotenv()

    api_id: int = int(os.environ["API_ID"])
    api_hash: str = os.environ["API_HASH"]
    bot_token: str = os.environ["BOT_TOKEN"]

    # Initialise the database (creates tables if they don't exist)
    logger.info("Initialising database...")
    await init_db()

    # Bot client — authenticated as a bot via BOT_TOKEN
    bot = create_bot_client(api_id, api_hash, bot_token)

    # Listener client.
    # • If SESSION_STRING env var is set → use it (ideal for cloud, no file needed).
    # • Otherwise → fall back to the existing file-based "listener" session.
    session_string: str = os.environ.get("SESSION_STRING", "").strip()

    if session_string:
        logger.info("Using StringSession from SESSION_STRING env var.")
        listener = TelegramClient(StringSession(session_string), api_id, api_hash)
        is_file_session = False
    else:
        logger.info("SESSION_STRING not set — using file-based 'listener' session.")
        listener = TelegramClient("listener", api_id, api_hash)
        is_file_session = True

    # Register the channel listener; notifications are sent via the bot client
    setup_listener(listener, bot)

    # ---------------------------------------------------------------------------
    # Start explicitly in the right order:
    #   1. Bot MUST be started with its token first (token auth, not user auth).
    #   2. Listener (user auth) starts second.
    # ---------------------------------------------------------------------------
    try:
        logger.info("Starting bot client (bot token auth)...")
        await bot.start(bot_token=bot_token)

        logger.info("Starting listener client (user auth)...")
        await listener.start()

        # After a file-based login, export and print the session string so it
        # can be set as SESSION_STRING for cloud / future runs (no re-auth).
        # SQLiteSession.save() writes to disk and returns None, so we build a
        # temporary StringSession from the live session's auth data instead.
        if is_file_session:
            tmp = StringSession()
            tmp.set_dc(
                listener.session.dc_id,
                listener.session.server_address,
                listener.session.port,
            )
            tmp.auth_key = listener.session.auth_key
            saved = tmp.save()
            print("\n" + "=" * 60)
            print("SESSION STRING (copy this into your SESSION_STRING env var):")
            print(saved)
            print("=" * 60 + "\n")

        logger.info("Both clients are running. Press Ctrl+C to stop.")
        await asyncio.gather(
            bot.run_until_disconnected(),
            listener.run_until_disconnected(),
        )
    finally:
        await bot.disconnect()
        await listener.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
