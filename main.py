"""
Order Tracker Bot — Main Entry Point
เริ่มบอท Telegram + Scheduler
"""
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram.ext import Application
from config import TELEGRAM_BOT_TOKEN
from bot.handlers import setup_handlers

# Setup logging
logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("OrderTracker")


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        logger.error(
            "❌ TELEGRAM_BOT_TOKEN ไม่ได้ตั้งค่า!\n"
            "1. สร้าง bot ที่ @BotFather บน Telegram\n"
            "2. Copy token มาใส่ในไฟล์ .env\n"
            "3. รัน py main.py อีกครั้ง"
        )
        sys.exit(1)

    logger.info("🚀 Starting Order Tracker Bot...")

    # Build application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    setup_handlers(app)

    logger.info("✅ Bot is running! Press Ctrl+C to stop.")
    logger.info("📱 เปิด Telegram แล้วส่ง /start ให้บอท")

    # Start polling
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
