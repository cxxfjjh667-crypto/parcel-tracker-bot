"""
Telegram Bot Handlers
Commands, inline keyboards, and callback handlers
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes,
)

import database as db
from api.etrackings_client import ETrackingsClient
from bot.messages import (
    format_summary, format_tracking_status, format_parcel_list,
    format_by_courier, format_carrier_anomaly, format_status_thai,
)
from tracker.scanner import Scanner
from config import CARRIERS, CARRIER_PATTERNS, CARRIER_ALIASES, ANOMALY_MIN, ANOMALY_MAX

logger = logging.getLogger(__name__)

# Conversation states
WAITING_TRACKING = 1
WAITING_PRODUCT_NAME = 2
WAITING_SEARCH = 3

# Scanner instance
scanner = Scanner()
etrackings = ETrackingsClient()


# ===== Menu Keyboard =====

def get_main_menu() -> InlineKeyboardMarkup:
    """Create the inline menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📦 ดูสรุปรายรอบ", callback_data="summary"),
            InlineKeyboardButton("📦 ของมาวันนี้", callback_data="today"),
        ],
        [
            InlineKeyboardButton("📋 รายการทั้งหมด", callback_data="all_parcels"),
            InlineKeyboardButton("✅ ส่งสำเร็จวันนี้", callback_data="delivered_today"),
        ],
        [
            InlineKeyboardButton("🔍 ค้นหา", callback_data="search"),
            InlineKeyboardButton("📋 แยกขนส่ง", callback_data="by_courier"),
        ],
        [
            InlineKeyboardButton("🔄 Scan ตอนนี้", callback_data="scan_now"),
            InlineKeyboardButton("➕ เพิ่มพัสดุ", callback_data="add"),
        ],
        [
            InlineKeyboardButton("📊 API เหลือกี่ครั้ง", callback_data="api_usage"),
            InlineKeyboardButton("🎲 สุ่มที่อยู่", callback_data="random_addr"),
        ],
        [
            InlineKeyboardButton("📋 เมนู", callback_data="menu"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_bottom_menu() -> ReplyKeyboardMarkup:
    """Create the persistent bottom keyboard."""
    keyboard = [
        [KeyboardButton("📦 สรุป"), KeyboardButton("🚚 ของมาวันนี้"), KeyboardButton("📋 รายการ")],
        [KeyboardButton("✅ ส่งสำเร็จวันนี้"), KeyboardButton("📋 แยกขนส่ง"), KeyboardButton("📋 เมนู")],
        [KeyboardButton("🔄 Scan"), KeyboardButton("📊 API"), KeyboardButton("🎲 สุ่มที่อยู่")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)


# ===== Command Handlers =====

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — show welcome + both menus."""
    chat_id = update.effective_chat.id
    logger.info(f"User started bot, chat_id: {chat_id}")

    # Send bottom keyboard first
    await update.message.reply_text(
        "🤖 Order Tracker Bot พร้อมใช้งาน!\n"
        f"📌 Chat ID: {chat_id}\n\n"
        "กดปุ่มด้านล่างได้เลย ⬇️",
        reply_markup=get_bottom_menu()
    )


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add <tracking_no> [ชื่อสินค้า] [ค่ายขนส่ง]"""
    args = context.args

    if not args:
        await update.message.reply_text(
            "📦 วิธีเพิ่มพัสดุ:\n"
            "/add <เลขพัสดุ> [ชื่อสินค้า] [ค่ายขนส่ง]\n\n"
            "ตัวอย่าง:\n"
            "/add 820148026547\n"
            "/add 820148026547 เสื้อยืดดำ\n"
            "/add 793378072631 เสื้อสีเขียว J&T\n\n"
            "ค่ายที่รองรับ: J&T, Flash, SPX, Kerry, Best, ThaiPost, DHL"
        )
        return

    tracking_no = args[0].strip()
    extra_args = args[1:] if len(args) > 1 else []

    # Try to detect carrier from text (e.g. "J&T", "flash", "เจแอนด์ที")
    courier_id = None
    product_parts = []

    for word in extra_args:
        alias_match = detect_carrier_from_text(word)
        if alias_match:
            courier_id = alias_match
        else:
            product_parts.append(word)

    product_name = " ".join(product_parts)

    # If not found from text, try auto-detect from tracking number
    if not courier_id:
        courier_id = detect_carrier(tracking_no)

    if not courier_id:
        carriers_list = "J&T, Flash, SPX, Kerry, Best, ThaiPost, DHL"
        await update.message.reply_text(
            f"❌ ไม่สามารถตรวจจับค่ายขนส่งจากเลข {tracking_no}\n\n"
            f"ลองระบุค่ายขนส่งด้วย เช่น:\n"
            f"/add {tracking_no} เสื้อยืด J&T\n\n"
            f"ค่ายที่รองรับ: {carriers_list}"
        )
        return

    carrier_info = CARRIERS[courier_id]

    # Add to database
    success = db.add_parcel(
        tracking_no=tracking_no,
        courier=carrier_info["name"],
        courier_key=carrier_info["key"],
        product_name=product_name,
    )

    if success:
        msg = (
            f"✅ เพิ่มพัสดุสำเร็จ!\n"
            f"📦 {tracking_no}\n"
            f"🚛 {carrier_info['name']}\n"
        )
        if product_name:
            msg += f"🏷️ {product_name}\n"

        # Try to fetch initial status
        result = etrackings.track(tracking_no, carrier_info["key"])
        if result.get("success"):
            status = etrackings.get_tracking_status(result)
            event = etrackings.get_latest_event(result)
            db.update_parcel_status(tracking_no, status, event)
            msg += f"📋 สถานะ: {format_status_thai(status)}\n"
            msg += f"📝 ล่าสุด: {event}"
        else:
            msg += "⏳ จะเช็คสถานะในรอบถัดไป"

        await update.message.reply_text(msg)
    else:
        await update.message.reply_text(f"⚠️ พัสดุ {tracking_no} มีอยู่ในระบบแล้ว")


async def cmd_addcarrier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addcarrier <carrier> <tracking_no> [product_name]"""
    args = context.args

    if len(args) < 2:
        carriers_list = "\n".join(
            f"  {k} = {v['name']}" for k, v in CARRIERS.items()
        )
        await update.message.reply_text(
            "📦 วิธีใช้:\n"
            "/addcarrier <ค่าย> <เลขพัสดุ> [ชื่อสินค้า]\n\n"
            f"ค่ายที่รองรับ:\n{carriers_list}\n\n"
            "ตัวอย่าง:\n"
            "/addcarrier jt 820148026547 เสื้อยืด"
        )
        return

    carrier_id = args[0].lower()
    tracking_no = args[1].strip()
    product_name = " ".join(args[2:]) if len(args) > 2 else ""

    if carrier_id not in CARRIERS:
        await update.message.reply_text(f"❌ ไม่รู้จักค่ายขนส่ง: {carrier_id}")
        return

    carrier_info = CARRIERS[carrier_id]
    success = db.add_parcel(
        tracking_no=tracking_no,
        courier=carrier_info["name"],
        courier_key=carrier_info["key"],
        product_name=product_name,
    )

    if success:
        await update.message.reply_text(
            f"✅ เพิ่มพัสดุสำเร็จ!\n"
            f"📦 {tracking_no}\n"
            f"🚛 {carrier_info['name']}"
        )
    else:
        await update.message.reply_text(f"⚠️ พัสดุ {tracking_no} มีอยู่ในระบบแล้ว")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove <tracking_no>"""
    if not context.args:
        await update.message.reply_text("ใช้: /remove <เลขพัสดุ>")
        return

    tracking_no = context.args[0].strip()
    if db.remove_parcel(tracking_no):
        await update.message.reply_text(f"✅ ลบ {tracking_no} แล้ว")
    else:
        await update.message.reply_text(f"❌ ไม่พบ {tracking_no}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status <tracking_no> — check single parcel status."""
    if not context.args:
        await update.message.reply_text("ใช้: /status <เลขพัสดุ>")
        return

    tracking_no = context.args[0].strip()
    parcel = db.get_parcel(tracking_no)

    if not parcel:
        await update.message.reply_text(f"❌ ไม่พบ {tracking_no} ในระบบ")
        return

    # Fetch latest tracking data
    result = etrackings.track(tracking_no, parcel["courier_key"])
    staff = None
    timelines = None

    if result.get("success"):
        status = etrackings.get_tracking_status(result)
        event = etrackings.get_latest_event(result)
        db.update_parcel_status(tracking_no, status, event)
        parcel = db.get_parcel(tracking_no)  # Refresh

        # Extract delivery staff and timelines
        staff = etrackings.get_delivery_staff(result)
        timelines = etrackings.get_tracking_timelines(result)

    msg = format_tracking_status(parcel, result, staff=staff, timelines=timelines)
    await update.message.reply_text(msg)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /menu — show menu buttons."""
    await update.message.reply_text(
        "📋 เมนูหลัก",
        reply_markup=get_main_menu()
    )


# ===== Callback Query Handlers =====

def get_parcel_buttons(parcels: list) -> InlineKeyboardMarkup:
    """Create per-parcel action buttons."""
    keyboard = []
    for p in parcels:
        tn = p["tracking_no"]
        name = p.get("product_name", "")
        status_emoji = {
            "ON_PICKED_UP": "📥", "ON_SHIPPING": "🚚",
            "ON_DELIVERED": "✅", "UNKNOWN": "⏳",
        }.get(p.get("status", "UNKNOWN"), "❓")

        label = f"{status_emoji} {tn}"
        if name:
            label += f" | {name}"

        # Row 1: parcel label (shows status)
        keyboard.append([InlineKeyboardButton(label, callback_data=f"s:{tn}")])
        # Row 2: action buttons
        row2 = [
            InlineKeyboardButton("📞 เช็คเบอร์", callback_data=f"p:{tn}"),
            InlineKeyboardButton("📜 ประวัติ", callback_data=f"h:{tn}"),
        ]
        
        row3 = []
        if p.get("status") == "ON_DELIVERED":
            row3.append(InlineKeyboardButton("📸 ดูรูปพัสดุ", callback_data=f"img:{tn}"))
        row3.append(InlineKeyboardButton("🗑 ลบ", callback_data=f"d:{tn}"))

        keyboard.append(row2)
        keyboard.append(row3)

    # Back to menu
    keyboard.append([InlineKeyboardButton("🔙 กลับเมนูหลัก", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def get_back_buttons(tracking_no: str = None) -> InlineKeyboardMarkup:
    """Back buttons after viewing detail."""
    buttons = []
    if tracking_no:
        parcel = db.get_parcel(tracking_no)
        buttons.append([
            InlineKeyboardButton("📞 เช็คเบอร์", callback_data=f"p:{tracking_no}"),
            InlineKeyboardButton("📜 ประวัติ", callback_data=f"h:{tracking_no}"),
        ])
        if parcel and parcel.get("status") == "ON_DELIVERED":
            buttons.append([InlineKeyboardButton("📸 ดูรูปพัสดุ", callback_data=f"img:{tracking_no}")])
    buttons.append([
        InlineKeyboardButton("📋 รายการทั้งหมด", callback_data="all_parcels"),
        InlineKeyboardButton("🔙 เมนูหลัก", callback_data="menu"),
    ])
    return InlineKeyboardMarkup(buttons)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # ===== Main Menu =====
    if data == "menu":
        await query.edit_message_text(
            "📋 เมนูหลัก",
            reply_markup=get_main_menu()
        )

    elif data == "summary":
        stats = db.get_summary_stats()
        scan_info = scanner.last_scan_info
        msg = format_summary(stats, scan_info if scan_info else None)
        await query.edit_message_text(msg, reply_markup=get_main_menu())

    elif data == "all_parcels":
        parcels = db.get_active_parcels()
        if not parcels:
            await query.edit_message_text(
                "📭 ยังไม่มีพัสดุในระบบ\n\nเพิ่มพัสดุด้วย:\n/add <เลขพัสดุ> [ชื่อสินค้า] [ค่าย]",
                reply_markup=get_main_menu()
            )
            return
        msg = f"📋 รายการพัสดุ ({len(parcels)} ชิ้น)\nกดปุ่มด้านล่างได้เลย ⬇️"
        await query.edit_message_text(msg, reply_markup=get_parcel_buttons(parcels))

    elif data == "by_courier":
        by_courier = db.get_parcels_by_courier()
        msg = format_by_courier(by_courier)
        await query.edit_message_text(msg, reply_markup=get_main_menu())

    elif data == "search":
        await query.edit_message_text(
            "🔍 พิมพ์เลขพัสดุหรือชื่อสินค้าที่ต้องการค้นหา:\n"
            "(พิมพ์ /search ตามด้วยคำค้นหา)\n\n"
            "ตัวอย่าง: /search 82014",
            reply_markup=get_main_menu()
        )

    elif data == "add":
        await query.edit_message_text(
            "➕ เพิ่มพัสดุ — พิมพ์คำสั่ง:\n"
            "/add <เลขพัสดุ> [ชื่อสินค้า] [ค่ายขนส่ง]\n\n"
            "ตัวอย่าง:\n"
            "/add 820148026547 เสื้อยืดดำ\n"
            "/add 793378072631 เสื้อ J&T",
            reply_markup=get_main_menu()
        )

    elif data == "api_usage":
        count = etrackings.call_count
        remaining = max(0, 50 - count)
        if remaining > 20:
            emoji = "🟢"
        elif remaining > 5:
            emoji = "🟡"
        else:
            emoji = "🔴"
        await query.edit_message_text(
            f"📊 สถานะ API eTrackings\n\n"
            f"{emoji} ใช้ไปแล้ว: {count}/50 ครั้ง\n"
            f"📦 เหลือ: {remaining} ครั้ง\n"
            f"🔑 Key: {etrackings.api_key[:8]}...{etrackings.api_key[-4:]}\n\n"
            f"💡 ถ้าหมด ให้สมัครใหม่แล้วพิมพ์:\n"
            f"/setapi <KEY_ใหม่> <SECRET_ใหม่>",
            reply_markup=get_main_menu()
        )

    elif data == "scan_now":
        await query.edit_message_text("🔄 กำลัง Scan...")

        chat_id = update.effective_chat.id

        async def send_notification(msg):
            await context.bot.send_message(chat_id=chat_id, text=msg)

        scan_info = await scanner.scan_all(notify_callback=send_notification)

        # Check anomalies
        anomalies = scanner.check_anomalies()
        if anomalies:
            anomaly_msg = format_carrier_anomaly(anomalies, ANOMALY_MIN, ANOMALY_MAX)
            await context.bot.send_message(chat_id=chat_id, text=anomaly_msg)

        # Show updated summary
        stats = db.get_summary_stats()
        msg = format_summary(stats, scan_info)
        await context.bot.send_message(
            chat_id=chat_id, text=msg, reply_markup=get_main_menu()
        )

    # ===== ของมาวันนี้ =====
    elif data == "today":
        today_parcels = db.get_today_deliveries()
        if not today_parcels:
            await query.edit_message_text(
                "📦 ของมาวันนี้\n\n"
                "ยังไม่มีพัสดุที่กำลังจัดส่งวันนี้\n"
                "💡 ลองกด 🔄 Scan ตอนนี้ เพื่ออัพเดทสถานะล่าสุด",
                reply_markup=get_main_menu()
            )
            return

        from datetime import date as date_mod
        today_str = date_mod.today().strftime("%Y-%m-%d")
        msg = (
            f"📦 ของมาวันนี้ ({today_str})\n"
            f"🚚 มีของกำลังจัดส่ง {len(today_parcels)} ชิ้น\n"
            f"กดปุ่มด้านล่างเพื่อดูรายละเอียด ⬇️"
        )
        await query.edit_message_text(msg, reply_markup=get_parcel_buttons(today_parcels))

    # ===== ส่งสำเร็จวันนี้ =====
    elif data == "delivered_today":
        delivered_parcels = db.get_delivered_today()
        if not delivered_parcels:
            await query.edit_message_text(
                "✅ ส่งสำเร็จวันนี้\n\n"
                "ยังไม่มีพัสดุที่ปิดยอดส่งสำเร็จในวันนี้ครับ",
                reply_markup=get_main_menu()
            )
            return

        from datetime import date as date_mod
        today_str = date_mod.today().strftime("%Y-%m-%d")
        msg = (
            f"✅ ส่งสำเร็จวันนี้ ({today_str})\n"
            f"📦 ปิดยอดส่งแล้ว {len(delivered_parcels)} ชิ้น\n"
            f"กดปุ่มด้านล่างเพื่อดูรายละเอียดรูปถ่าย ⬇️"
        )
        await query.edit_message_text(msg, reply_markup=get_parcel_buttons(delivered_parcels))

    # ===== Per-Parcel: เช็คเบอร์ =====
    elif data.startswith("p:"):
        tracking_no = data[2:]
        parcel = db.get_parcel(tracking_no)
        if not parcel:
            await query.edit_message_text(f"❌ ไม่พบ {tracking_no}",
                                          reply_markup=get_main_menu())
            return

        result = etrackings.track(tracking_no, parcel["courier_key"])
        staff = etrackings.get_delivery_staff(result) if result.get("success") else None

        name = parcel.get("product_name", "")
        lines = [
            f"📞 ข้อมูลพนักงานส่ง",
            f"📦 {tracking_no}",
        ]
        if name:
            lines.append(f"🏷️ {name}")
        lines.append("")

        if staff:
            if staff.get("name"):
                lines.append(f"👤 พนักงาน: {staff['name']}")
            if staff.get("phone"):
                lines.append(f"📞 เบอร์: {staff['phone']}")
            if staff.get("branch_phone"):
                lines.append(f"🏢 เบอร์สาขา: {staff['branch_phone']}")
        else:
            lines.append("⏳ ยังไม่มีข้อมูลพนักงาน (รอสถานะ กำลังจัดส่ง)")

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=get_back_buttons(tracking_no)
        )

    # ===== Per-Parcel: ดูประวัติ =====
    elif data.startswith("h:"):
        tracking_no = data[2:]
        parcel = db.get_parcel(tracking_no)
        if not parcel:
            await query.edit_message_text(f"❌ ไม่พบ {tracking_no}",
                                          reply_markup=get_main_menu())
            return

        result = etrackings.track(tracking_no, parcel["courier_key"])
        timelines = etrackings.get_tracking_timelines(result) if result.get("success") else []

        name = parcel.get("product_name", "")
        lines = [
            f"📜 ประวัติพัสดุ",
            f"📦 {tracking_no}",
        ]
        if name:
            lines.append(f"🏷️ {name}")
        lines.append(f"📋 สถานะ: {format_status_thai(parcel.get('status', 'UNKNOWN'))}")
        lines.append("")

        if timelines:
            for t in timelines[:8]:
                lines.append(f"• {t['date']} {t['time']} - {t['description']}")
        else:
            lines.append("⏳ ยังไม่มีข้อมูลประวัติ")

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=get_back_buttons(tracking_no)
        )

    # ===== Per-Parcel: ดูรูปพัสดุ =====
    elif data.startswith("img:"):
        tracking_no = data[4:]
        parcel = db.get_parcel(tracking_no)
        if not parcel:
            await query.edit_message_text(f"❌ ไม่พบ {tracking_no}", reply_markup=get_main_menu())
            return

        result = etrackings.track(tracking_no, parcel["courier_key"])
        
        image_urls = []
        if result.get("success"):
            detail = result.get("data", {}).get("detail", {})
            signer_img = detail.get("signerImageURL", "")
            if signer_img:
                # API sometimes returns multiple URLs separated by comma
                image_urls = [url.strip() for url in signer_img.split(",") if url.strip()]
        
        if not image_urls:
            await query.edit_message_text(
                f"❌ ไม่พบรูปถ่ายการจัดส่งของ {tracking_no}",
                reply_markup=get_back_buttons(tracking_no)
            )
            return
            
        # Send the first image found
        try:
            await query.edit_message_text(f"⏳ กำลังโหลดรูปถ่ายสำหรับ {tracking_no} ...")
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=image_urls[0],
                caption=f"📸 รูปถ่ายการจัดส่งพัสดุ\n📦 {tracking_no}\n✅ {parcel.get('product_name', '')}",
                reply_markup=get_back_buttons(tracking_no)
            )
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
            await query.edit_message_text(
                f"❌ โหลดรูปล้มเหลว หรือลิงก์รูปหมดอายุ",
                reply_markup=get_back_buttons(tracking_no)
            )

    # ===== Per-Parcel: สถานะ (กดที่ชื่อ) =====
    elif data.startswith("s:"):
        tracking_no = data[2:]
        parcel = db.get_parcel(tracking_no)
        if not parcel:
            await query.edit_message_text(f"❌ ไม่พบ {tracking_no}",
                                          reply_markup=get_main_menu())
            return

        result = etrackings.track(tracking_no, parcel["courier_key"])
        staff = None
        timelines = None
        if result.get("success"):
            status = etrackings.get_tracking_status(result)
            event = etrackings.get_latest_event(result)
            db.update_parcel_status(tracking_no, status, event)
            parcel = db.get_parcel(tracking_no)
            staff = etrackings.get_delivery_staff(result)
            timelines = etrackings.get_tracking_timelines(result)

        msg = format_tracking_status(parcel, result, staff=staff, timelines=timelines)
        await query.edit_message_text(msg, reply_markup=get_back_buttons(tracking_no))

    # ===== Per-Parcel: ลบ =====
    elif data.startswith("d:"):
        tracking_no = data[2:]
        if db.remove_parcel(tracking_no):
            await query.edit_message_text(
                f"✅ ลบ {tracking_no} แล้ว",
                reply_markup=get_main_menu()
            )
        else:
            await query.edit_message_text(
                f"❌ ไม่พบ {tracking_no}",
                reply_markup=get_main_menu()
            )

    # ===== สุ่มที่อยู่ =====
    elif data == "random_addr":
        await send_random_address(query.message)
        
    else:
        await query.answer()


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search <query>"""
    if not context.args:
        await update.message.reply_text("ใช้: /search <เลขพัสดุหรือชื่อสินค้า>")
        return

    query = " ".join(context.args)
    results = db.search_parcels(query)
    msg = format_parcel_list(results, f"ผลค้นหา '{query}'")
    await update.message.reply_text(msg)


# ===== Helpers =====

def detect_carrier(tracking_no: str) -> str | None:
    """Auto-detect carrier from tracking number prefix."""
    tracking_upper = tracking_no.upper()

    # Check longest prefixes first
    for prefix in sorted(CARRIER_PATTERNS.keys(), key=len, reverse=True):
        if tracking_upper.startswith(prefix):
            return CARRIER_PATTERNS[prefix]

    return None


def detect_carrier_from_text(text: str) -> str | None:
    """Detect carrier from user-typed text like 'J&T', 'flash', 'เจแอนด์ที'."""
    text_lower = text.lower().strip()
    return CARRIER_ALIASES.get(text_lower)


# ===== Scheduler Job =====

async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job to scan all parcels."""
    chat_id = context.job.data.get("chat_id")
    if not chat_id:
        return

    async def send_notification(msg):
        await context.bot.send_message(chat_id=chat_id, text=msg)

    scan_info = await scanner.scan_all(notify_callback=send_notification)

    # Check anomalies
    anomalies = scanner.check_anomalies()
    if anomalies:
        anomaly_msg = format_carrier_anomaly(anomalies, ANOMALY_MIN, ANOMALY_MAX)
        await context.bot.send_message(chat_id=chat_id, text=anomaly_msg)

    # Only send summary if there are changes
    if scan_info.get("changed", 0) > 0 or scan_info.get("new", 0) > 0:
        stats = db.get_summary_stats()
        msg = format_summary(stats, scan_info)
        await context.bot.send_message(
            chat_id=chat_id, text=msg, reply_markup=get_main_menu()
        )


async def cmd_setscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setscan — start automated scanning for this chat."""
    from config import SCAN_INTERVAL_MINUTES

    chat_id = update.effective_chat.id

    # Remove existing jobs for this chat
    current_jobs = context.job_queue.get_jobs_by_name(f"scan_{chat_id}")
    for job in current_jobs:
        job.schedule_removal()

    # Add new scheduled job
    context.job_queue.run_repeating(
        scheduled_scan,
        interval=SCAN_INTERVAL_MINUTES * 60,
        first=10,  # Start first scan after 10 seconds
        name=f"scan_{chat_id}",
        data={"chat_id": chat_id},
    )

    await update.message.reply_text(
        f"✅ เปิด Scan อัตโนมัติ ทุกๆ {SCAN_INTERVAL_MINUTES} นาที\n"
        f"จะแจ้งเตือนเมื่อสถานะพัสดุเปลี่ยน\n\n"
        f"หยุด Scan: /stopscan"
    )


async def cmd_stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stopscan — stop automated scanning."""
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(f"scan_{chat_id}")

    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
        await update.message.reply_text("⏹️ หยุด Scan อัตโนมัติแล้ว")
    else:
        await update.message.reply_text("ℹ️ ยังไม่ได้เปิด Scan อัตโนมัติ")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages from bottom keyboard buttons."""
    text = update.message.text.strip()

    if text == "📦 สรุป":
        stats = db.get_summary_stats()
        scan_info = scanner.last_scan_info
        msg = format_summary(stats, scan_info if scan_info else None)
        await update.message.reply_text(msg, reply_markup=get_main_menu())

    elif text == "🚚 ของมาวันนี้":
        today_parcels = db.get_today_deliveries()
        if not today_parcels:
            await update.message.reply_text(
                "📦 ของมาวันนี้\n\n"
                "ยังไม่มีพัสดุที่กำลังจัดส่งวันนี้\n"
                "💡 ลองกด 🔄 Scan เพื่ออัพเดทสถานะล่าสุด"
            )
            return
        from datetime import date as date_mod
        today_str = date_mod.today().strftime("%Y-%m-%d")
        msg = (
            f"📦 ของมาวันนี้ ({today_str})\n"
            f"🚚 มีของกำลังจัดส่ง {len(today_parcels)} ชิ้น\n"
            f"กดปุ่มด้านล่างเพื่อดูรายละเอียด ⬇️"
        )
        await update.message.reply_text(msg, reply_markup=get_parcel_buttons(today_parcels))

    elif text == "✅ ส่งสำเร็จวันนี้":
        delivered_parcels = db.get_delivered_today()
        if not delivered_parcels:
            await update.message.reply_text(
                "✅ ส่งสำเร็จวันนี้\n\n"
                "ยังไม่มีพัสดุที่ปิดยอดส่งสำเร็จในวันนี้ครับ"
            )
            return
        from datetime import date as date_mod
        today_str = date_mod.today().strftime("%Y-%m-%d")
        msg = (
            f"✅ ส่งสำเร็จวันนี้ ({today_str})\n"
            f"📦 ปิดยอดส่งแล้ว {len(delivered_parcels)} ชิ้น\n"
            f"กดปุ่มด้านล่างเพื่อดูรายละเอียดรูปถ่าย ⬇️"
        )
        await update.message.reply_text(msg, reply_markup=get_parcel_buttons(delivered_parcels))

    elif text == "📋 รายการ":
        parcels = db.get_active_parcels()
        if not parcels:
            await update.message.reply_text("📭 ยังไม่มีพัสดุ")
            return
        msg = f"📋 รายการพัสดุ ({len(parcels)} ชิ้น)\nกดปุ่มด้านล่าง ⬇️"
        await update.message.reply_text(msg, reply_markup=get_parcel_buttons(parcels))

    elif text == "🔄 Scan":
        await update.message.reply_text("🔄 กำลัง Scan...")
        chat_id = update.effective_chat.id

        async def send_notification(msg):
            await context.bot.send_message(chat_id=chat_id, text=msg)

        scan_info = await scanner.scan_all(notify_callback=send_notification)

        anomalies = scanner.check_anomalies()
        if anomalies:
            anomaly_msg = format_carrier_anomaly(anomalies, ANOMALY_MIN, ANOMALY_MAX)
            await context.bot.send_message(chat_id=chat_id, text=anomaly_msg)

        stats = db.get_summary_stats()
        msg = format_summary(stats, scan_info)
        await context.bot.send_message(
            chat_id=chat_id, text=msg, reply_markup=get_main_menu()
        )

    elif text == "📋 แยกขนส่ง":
        by_courier = db.get_parcels_by_courier()
        msg = format_by_courier(by_courier)
        await update.message.reply_text(msg)

    elif text == "📋 เมนู":
        await update.message.reply_text(
            "📋 เมนูหลัก",
            reply_markup=get_main_menu()
        )

    elif text == "📊 API":
        import os
        count = etrackings.call_count
        remaining = max(0, 50 - count)
        
        saved_str = os.environ.get("SAVED_ETRACKINGS_KEYS", "")
        keys = [tuple(k.split(':', 1)) for k in saved_str.split('|') if ':' in k]
        main_key = (etrackings.api_key, etrackings.key_secret)
        if main_key[0] and main_key not in keys:
            keys.insert(0, main_key)
            
        total_keys = max(1, len(keys))
        
        if remaining > 20:
            emoji = "🟢"
        elif remaining > 5:
            emoji = "🟡"
        else:
            emoji = "🔴"
            
        await update.message.reply_text(
            f"📊 สถานะ API eTrackings\n\n"
            f"{emoji} โควต้าชุดปัจจุบัน: ใช้ไป {count}/50 ครั้ง\n"
            f"📦 ชุดปัจจุบันเหลือ: {remaining} ครั้ง\n"
            f"🔑 Key ปัจจุบัน: {etrackings.api_key[:8]}...{etrackings.api_key[-4:]}\n\n"
            f"📚 คลัง API สำรองทั้งหมด: {total_keys} ชุด\n"
            f"🚀 สแกนต่อเนื่องสูงสุด: {total_keys * 50} พัสดุ/วัน\n\n"
            f"💡 เติมโควต้าเข้าคลัง พิมพ์คำสั่ง:\n"
            f"/setapi <KEY_ใหม่> <SECRET_ใหม่>"
        )

    elif text == "🎲 สุ่มที่อยู่":
        await send_random_address(update.message)

async def cmd_setapi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setapi <api_key> <key_secret> — hot-swap API credentials."""
    args = context.args

    if not args or len(args) < 2:
        await update.message.reply_text(
            "🔑 วิธีเปลี่ยน API Key:\n"
            "/setapi <API_KEY> <KEY_SECRET>\n\n"
            "ตัวอย่าง:\n"
            "/setapi 95ad286b... 1a5e12ed...\n\n"
            f"📊 ใช้ไปแล้ว: {etrackings.call_count}/50 ครั้ง"
        )
        return

    new_api_key = args[0].strip()
    new_key_secret = args[1].strip()

    # 1. Update the etrackings client (in memory)
    etrackings.update_credentials(new_api_key, new_key_secret)
    scanner.client.update_credentials(new_api_key, new_key_secret)
    
    # 2. Add to SAVED_ETRACKINGS_KEYS and write to .env so the Server remembers it
    import os
    from dotenv import set_key
    DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(DATA_DIR, ".env")
    
    if not os.path.exists(env_path):
        open(env_path, 'a', encoding="utf-8").close()
        
    set_key(env_path, "ETRACKINGS_API_KEY", new_api_key)
    set_key(env_path, "ETRACKINGS_KEY_SECRET", new_key_secret)
    os.environ["ETRACKINGS_API_KEY"] = new_api_key
    os.environ["ETRACKINGS_KEY_SECRET"] = new_key_secret
    
    saved_str = os.environ.get("SAVED_ETRACKINGS_KEYS", "")
    keys = [tuple(k.split(':', 1)) for k in saved_str.split('|') if ':' in k]
    new_pair = (new_api_key, new_key_secret)
    if new_pair not in keys:
        keys.append(new_pair)
        new_saved_str = "|".join([f"{k}:{s}" for k, s in keys])
        set_key(env_path, "SAVED_ETRACKINGS_KEYS", new_saved_str)
        os.environ["SAVED_ETRACKINGS_KEYS"] = new_saved_str

    await update.message.reply_text(
        "✅ บันทึก API Key และเพิ่มลงในคิวสำรองเรียบร้อย!\n\n"
        f"🔑 Key ปัจจุบัน: {new_api_key[:8]}...{new_api_key[-4:]}\n"
        f"📚 จำนวน Key สำรองในระบบ Server: {len(keys)} ชุด\n"
        f"📊 รีเซ็ตตัวนับการใช้งาน\n\n"
        "💡 ต่อจากนี้ถ้าระบบเช็คพัสดุเยอะจนทะลุโควต้า 50 ครั้ง บอทจะพยายามสลับไปใช้ชุดสำรองในคิวให้เองอัตโนมัติ!"
    )


async def cmd_apiusage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /apiusage — show current API usage."""
    import os
    count = etrackings.call_count
    remaining = max(0, 50 - count)
    
    saved_str = os.environ.get("SAVED_ETRACKINGS_KEYS", "")
    keys = [tuple(k.split(':', 1)) for k in saved_str.split('|') if ':' in k]
    main_key = (etrackings.api_key, etrackings.key_secret)
    if main_key[0] and main_key not in keys:
        keys.insert(0, main_key)
        
    total_keys = max(1, len(keys))

    if remaining > 20:
        emoji = "🟢"
    elif remaining > 5:
        emoji = "🟡"
    else:
        emoji = "🔴"

    await update.message.reply_text(
        f"📊 สถานะ API eTrackings\n\n"
        f"{emoji} โควต้าชุดปัจจุบัน: ใช้ไป {count}/50 ครั้ง\n"
        f"📦 ชุดปัจจุบันเหลือ: {remaining} ครั้ง\n"
        f"🔑 Key ปัจจุบัน: {etrackings.api_key[:8]}...{etrackings.api_key[-4:]}\n\n"
        f"📚 คลัง API สำรองทั้งหมด: {total_keys} ชุด\n"
        f"🚀 สแกนต่อเนื่องสูงสุด: {total_keys * 50} พัสดุ/วัน\n\n"
        f"💡 เติมโควต้าเข้าคลัง พิมพ์คำสั่ง:\n"
        f"/setapi <KEY_ใหม่> <SECRET_ใหม่>"
    )


async def send_random_address(message):
    import os
    import random
    import string
    
    part1 = os.environ.get("RANDOM_ADDR_P1", "กะลุวอ")
    part2 = os.environ.get("RANDOM_ADDR_P2", "อ.เมือง จ.นราธิวาส 96000")
    
    def rand_str(length):
        return ''.join(random.choices(string.ascii_lowercase, k=length))
    
    def rand_symbols(length):
        symbols = "{?_+(฿^$.'"
        return ''.join(random.choices(symbols, k=length))
        
    s1 = rand_str(random.randint(7, 10))
    h1 = random.randint(1, 999)
    h2 = random.randint(1, 999)
    s2 = rand_str(random.randint(6, 10))
    s3 = rand_str(random.randint(6, 10))
    
    sym1 = rand_symbols(random.randint(3, 5))
    sym2 = rand_symbols(random.randint(3, 5))
    
    # 10 digit phone number starting with '08', '09', '06'
    prefix = random.choice(['08', '09', '06'])
    phone = prefix + ''.join([str(random.randint(0, 9)) for _ in range(8)])
    
    address = f"{s1} {h1}/{h2} {s2} {s3} {sym1}{part1}{sym2} {part2}"
    result = f"`{address}`\n\nเบอร์: `{phone}`"
    
    await message.reply_markdown(
        f"🎲 **สุ่มที่อยู่จัดส่งใหม่แล้ว:**\n\n"
        f"{result}\n\n"
        f"💡 (แตะที่ข้อความเพื่อก๊อปปี้ได้เลย)\n"
        f"⚙️ เปลี่ยนตำบล/จังหวัด พิมพ์:\n"
        f"`/setaddress <ตำบล> | <อำเภอ จังหวัด รหัสไปรษณีย์>`"
    )

async def cmd_setaddress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setaddress <part1> | <part2>."""
    text = " ".join(context.args)
    if "|" not in text:
        await update.message.reply_markdown(
            "❌ รูปแบบผิด!\n\n"
            "วิธีตั้งค่าที่อยู่คงที่สำหรับสุ่ม:\n"
            "`/setaddress ตำบล | อำเภอ จังหวัด รหัสไปรษณีย์`\n\n"
            "ตัวอย่าง:\n"
            "`/setaddress กะลุวอ | อ.เมือง จ.นราธิวาส 96000`"
        )
        return
        
    part1, part2 = text.split("|", 1)
    part1 = part1.strip()
    part2 = part2.strip()
    
    import os
    from dotenv import set_key
    DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(DATA_DIR, ".env")
    
    if not os.path.exists(env_path):
        open(env_path, 'a', encoding="utf-8").close()
        
    set_key(env_path, "RANDOM_ADDR_P1", part1)
    set_key(env_path, "RANDOM_ADDR_P2", part2)
    os.environ["RANDOM_ADDR_P1"] = part1
    os.environ["RANDOM_ADDR_P2"] = part2
    
    await update.message.reply_text(
        f"✅ บันทึกที่อยู่ตั้งต้นสำเร็จ!\n\n"
        f"ส่วนที่ 1: {part1}\n"
        f"ส่วนที่ 2: {part2}\n\n"
        f"ลองกดปุ่ม 🎲 สุ่มที่อยู่ ดูได้เลยครับ"
    )

def setup_handlers(app: Application):
    """Register all handlers to the application."""
    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("addcarrier", cmd_addcarrier))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("setscan", cmd_setscan))
    app.add_handler(CommandHandler("stopscan", cmd_stopscan))
    app.add_handler(CommandHandler("setapi", cmd_setapi))
    app.add_handler(CommandHandler("apiusage", cmd_apiusage))
    app.add_handler(CommandHandler("setaddress", cmd_setaddress))

    # Callback queries (inline keyboard)
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Text messages (bottom keyboard buttons)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Bot handlers registered")
