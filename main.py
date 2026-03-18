"""
Order Tracker Bot — Main Entry Point
เริ่มบอท Telegram + Scheduler
"""
import logging
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- Interactive Setup for EXE/First-time users ----
def check_setup():
    from dotenv import load_dotenv, set_key
    
    # CRITICAL: For PyInstaller, we need the folder where the .exe is.
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
        
    os.environ["DATA_DIR"] = application_path
    env_path = os.path.join(application_path, ".env")
    
    # Create empty .env if it doesn't exist to allow set_key
    if not os.path.exists(env_path):
        open(env_path, 'a', encoding="utf-8").close()
        
    load_dotenv(env_path)
    
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    et_key = os.environ.get("ETRACKINGS_API_KEY", "").strip()
    
    if not tg_token or tg_token == "your_bot_token_here" or not et_key:
        print("\n" + "="*60)
        print("   📦 ยินดีต้อนรับสู่ระบบ Parcel Tracker Bot 📦")
        print("   ระบบตรวจพบว่าคุณยังไม่ได้ตั้งค่า API หรือเป็นการใช้งานครั้งแรก")
        print("="*60 + "\n")
        
        if not tg_token or tg_token == "your_bot_token_here":
            tg_token = input("1. กรุณาใส่รหัส TELEGRAM_BOT_TOKEN (จาก @BotFather): ").strip()
            set_key(env_path, "TELEGRAM_BOT_TOKEN", tg_token)
            os.environ["TELEGRAM_BOT_TOKEN"] = tg_token
            
        if not et_key or et_key == "your_etrackings_api_key_here":
            print("\n[หา eTrackings API ได้ฟรีที่: https://etrackings.com]")
            et_key = input("2. กรุณาใส่ ETRACKINGS_API_KEY: ").strip()
            set_key(env_path, "ETRACKINGS_API_KEY", et_key)
            os.environ["ETRACKINGS_API_KEY"] = et_key
            
            et_sec = input("3. กรุณาใส่ ETRACKINGS_KEY_SECRET: ").strip()
            set_key(env_path, "ETRACKINGS_KEY_SECRET", et_sec)
            os.environ["ETRACKINGS_KEY_SECRET"] = et_sec
            
        print("\n✅ บันทึกข้อมูลตั้งค่าลงในไฟล์ .env เรียบร้อยแล้ว!\n")

# Run setup BEFORE importing other modules that depend on config
check_setup()

# Now safe to import the rest
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
