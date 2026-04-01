"""
listener.py — Telethon user-client that monitors a Telegram channel for
              Pikud HaOref alerts and forwards personalised notifications
              to registered users via the bot client.

Event classification (priority order):
  "בדקות הקרובות צפויות להתקבל התרעות באזורך" → Event: "התרעה מקדימה",         Emoji: 🟠
  "ירי רקטות וטילים"                           → Event: "ירי רקטות וטילים",     Emoji: 🔴
  "חדירת כלי טיס עוין"                         → Event: "חדירת כלי טיס עוין",  Emoji: ✈️
  "האירוע הסתיים"                              → Event: "האירוע הסתיים",        Emoji: 🟢
  (default)                                    → Event: "התרעה",                Emoji: 🟡

Message format: "{Emoji} {location1}, {location2} — {Event}"
"""

import os
import re
import time
import logging

from telethon import TelegramClient, events

from database import get_all_users

logger = logging.getLogger(__name__)

# מילון לשמירת המשתמשים שנמצאים בסטטוס "התרעה פעילה"
# מבנה: {chat_id: expiration_timestamp}
active_alert_users: dict[int, float] = {}


def _classify_message(text: str) -> tuple[str, str]:
    """Return (emoji, event_name) based on exact Pikud HaOref message keywords."""
    if "בדקות הקרובות צפויות להתקבל התרעות באזורך" in text:
        return "🟠", "התרעה מקדימה"
    if "ירי רקטות וטילים" in text:
        return "🔴", "ירי רקטות וטילים"
    if "חדירת כלי טיס עוין" in text:
        return "✈️", "חדירת כלי טיס עוין"
    if "האירוע הסתיים" in text:
        return "🟢", "האירוע הסתיים"
    return "🟡", "התרעה"


def setup_listener(
    listener_client: TelegramClient,
    bot_client: TelegramClient,
) -> None:
    """Register the NewMessage handler on the listener (user) client."""
    target_channel: str = os.environ["TARGET_CHANNEL"]
    # משיכת שם ערוץ צפי ההגעה ממשתנה סביבה (עם ברירת מחדל)
    eta_channel: str = os.environ.get("ETA_CHANNEL", "pkpoi")

    @listener_client.on(events.NewMessage(chats=[target_channel, eta_channel]))
    async def on_channel_message(event: events.NewMessage.Event) -> None:
        message_text: str = event.raw_text or ""
        if not message_text:
            return

        chat = await event.get_chat()
        chat_username: str = getattr(chat, "username", "") or ""

        # =========================================================
        # 1. טיפול בהתרעות פיקוד העורף הרשמיות
        # =========================================================
        if chat_username.lower() == target_channel.replace("@", "").lower():
            emoji, event_name = _classify_message(message_text)

            users = await get_all_users()

            for chat_id, locations in users:
                if not locations:
                    continue

                # בדיקה האם אחד מהיישובים של המשתמש מופיע בהודעה
                matched_locations = [
                    loc for loc in locations if loc in message_text
                ]

                if not matched_locations:
                    continue

                # בניית ושליחת הודעת ההתרעה
                locations_str = ", ".join(matched_locations)
                notification = f"{emoji} {locations_str} — {event_name}"

                try:
                    await bot_client.send_message(chat_id, notification)
                    
                    # --- לוגיקת ה-State החדשה ---
                    
                    # א. הכנסה לרשימה רק ב"התרעה מקדימה"
                    if event_name == "התרעה מקדימה":
                        active_alert_users[chat_id] = time.time() + 1800
                        logger.info("User %s added to ETA tracking (Early Warning)", chat_id)

                    # ב. הוצאה מהרשימה ב"האירוע הסתיים"
                    elif event_name == "האירוע הסתיים":
                        if chat_id in active_alert_users:
                            active_alert_users.pop(chat_id, None)
                            logger.info("User %s removed from ETA tracking (Event Ended)", chat_id)
                        
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to notify chat_id=%s: %s", chat_id, exc
                    )

        # =========================================================
        # 2. טיפול בהודעות "צפי הגעה" (למי שנמצא ברשימה הפעילה)
        # =========================================================
        elif chat_username.lower() == eta_channel.lower():
            if "פרטי האיום" not in message_text:
                return

            # חילוץ נתונים
            issuer_match = re.search(r"גורם משגר:\s*(.*)", message_text)
            area_match = re.search(r"מרחב:\s*(.*)", message_text)
            focus_match = re.search(r"מיקוד:\s*(.*)", message_text)
            threat_count_match = re.search(r"מספר איומים:\s*(.*)", message_text)
            eta_match = re.search(r"צפי הגעה:\s*([\d: -]+)", message_text)

            if issuer_match and area_match and eta_match:
                issuer = issuer_match.group(1).strip()
                area = area_match.group(1).strip()
                focus = focus_match.group(1).strip() if focus_match else "לא צוין"
                threat_count = threat_count_match.group(1).strip() if threat_count_match else "לא צוין"
                eta = eta_match.group(1).strip()

                summary_msg = (
                    f"{issuer} -> {area} ({focus}) | {eta} | איומים: {threat_count}\n\n"
                    f"_*מידע משוער בלבד, יש להישמע להנחיות פיקוד העורף.*_"
                )

                current_time = time.time()
                
                # שליחה רק למשתמשים שנמצאים כרגע ב-active_alert_users (ולא פג תוקפם)
                for uid, expiration in list(active_alert_users.items()):
                    if current_time > expiration:
                        active_alert_users.pop(uid, None)
                    else:
                        try:
                            await bot_client.send_message(uid, summary_msg)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Failed to send ETA to chat_id=%s: %s", uid, exc)

    logger.info("Listener registered on channels: %s, @%s", target_channel, eta_channel)
