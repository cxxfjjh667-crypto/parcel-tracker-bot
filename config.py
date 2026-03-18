import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# eTrackings API
ETRACKINGS_API_KEY = os.getenv("ETRACKINGS_API_KEY", "")
ETRACKINGS_KEY_SECRET = os.getenv("ETRACKINGS_KEY_SECRET", "")
ETRACKINGS_BASE_URL = "https://api.etrackings.com/api/v3"

# Scanner settings
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "30"))
ANOMALY_MIN = int(os.getenv("ANOMALY_MIN", "5"))
ANOMALY_MAX = int(os.getenv("ANOMALY_MAX", "300"))

# Supported carriers (eTrackings courier keys — verified from API)
CARRIERS = {
    "jt": {"name": "J&T Express", "key": "jt-express"},
    "flash": {"name": "Flash Express", "key": "flash-express"},
    "spx": {"name": "Shopee Express", "key": "shopee-express"},
    "kerry": {"name": "Kerry Express", "key": "kex-express"},
    "best": {"name": "Best Express", "key": "best-express"},
    "thaipost": {"name": "Thailand Post", "key": "thailand-post"},
    "dhl": {"name": "DHL eCommerce", "key": "dhl-ecommerce"},
    "nim": {"name": "Nim Express", "key": "nim-express"},
    "speedd": {"name": "Speed-D", "key": "speed-d"},
}

# Auto-detect carrier from tracking number prefix
CARRIER_PATTERNS = {
    "82": "jt",        # J&T
    "83": "jt",
    "80": "jt",
    "79": "jt",
    "69": "jt",
    "66": "jt",
    "60": "jt",
    "88": "jt",
    "TH": "flash",     # Flash starts with TH
    "SPXTH": "spx",    # Shopee Express
    "SPX": "spx",
    "KEX": "kerry",    # Kerry
    "SDOF": "best",    # Best Express
    "E": "thaipost",   # Thailand Post EMS
    "R": "thaipost",   # Thailand Post registered
}

# Aliases for carrier names (user might type these)
CARRIER_ALIASES = {
    "jt": "jt", "j&t": "jt", "jnt": "jt", "เจแอนด์ที": "jt",
    "flash": "flash", "แฟลช": "flash",
    "spx": "spx", "shopee": "spx", "ช้อปปี้": "spx",
    "kerry": "kerry", "เคอรี่": "kerry",
    "best": "best", "เบสท์": "best",
    "thaipost": "thaipost", "ไปรษณีย์": "thaipost", "ems": "thaipost",
    "dhl": "dhl",
}
