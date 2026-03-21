"""
main.py — Entry point. Loads environment, initialises DB, and runs both
           the bot client (BotClient) and the user listener client concurrently.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from telethon import TelegramClient

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

    # Bot client — uses bot_token, handles user interactions
    bot = create_bot_client(api_id, api_hash, bot_token)

    # Listener client — uses user credentials, monitors the target channel
    listener = TelegramClient("listener", api_id, api_hash)

    # Register the channel listener; it sends messages through the bot client
    setup_listener(listener, bot)

    logger.info("Starting bot and listener clients...")
    async with bot, listener:
        await bot.start(bot_token=bot_token)
        await listener.start()

        logger.info("Both clients are running. Press Ctrl+C to stop.")
        await asyncio.gather(
            bot.run_until_disconnected(),
            listener.run_until_disconnected(),
        )


if __name__ == "__main__":
    asyncio.run(main())
