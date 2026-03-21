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

    # Listener client — authenticated as a user, monitors the target channel.
    # Prefer a StringSession (env var) so no .session file is needed on cloud.
    session_string: str = os.environ.get("SESSION_STRING", "").strip()
    using_string_session = bool(session_string)

    if using_string_session:
        logger.info("Using StringSession from SESSION_STRING env var.")
        listener = TelegramClient(StringSession(session_string), api_id, api_hash)
    else:
        logger.info("SESSION_STRING not set — using file-based 'listener' session.")
        listener = TelegramClient("listener", api_id, api_hash)

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

        # After a fresh file-based login, print the session string so you can
        # copy it into SESSION_STRING for future deployments (avoids re-auth).
        if not using_string_session:
            saved = listener.session.save()
            if saved:
                print("\n" + "=" * 60)
                print("SESSION STRING (save this for cloud deployments):")
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
