# Order Tracker Bot
# ระบบติดตามออเดอร์ + แจ้งเตือน Telegram

## Setup
1. Copy `.env.example` to `.env` and fill in your credentials
2. Install dependencies: `py -m pip install -r requirements.txt`
3. Run: `py main.py`

## Environment Variables
- `TELEGRAM_BOT_TOKEN` - Get from @BotFather on Telegram
- `ETRACKINGS_API_KEY` - Your eTrackings API key
- `ETRACKINGS_KEY_SECRET` - Your eTrackings key secret
- `SCAN_INTERVAL_MINUTES` - How often to scan (default: 30)
