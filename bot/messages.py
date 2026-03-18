"""
Message formatting for Telegram bot
Formats summaries, alerts, and tracking info with emojis
"""
from datetime import datetime


def format_summary(stats: dict, scan_info: dict = None) -> str:
    """
    Format daily round summary message.
    
    Example output:
    <Order Tracker | สรุปรายรอบ>
    📅 วันที่: 2026-03-16
    
    📦 กำลังจัดส่ง : 11
    🟠 ต้องเช็ค    : 0
    🚫 ยกเลิก      : 1
    ⚠️ ค้างนาน     : 0
    ✅ ปิดงาน      : 0
    💸 ยอดชำระรวม : ฿0.00
    """
    today = datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"<Order Tracker | สรุปรายรอบ>",
        f"📅 วันที่: {today}",
        "",
        f"📦 กำลังจัดส่ง : {stats.get('shipping', 0)}",
        f"🟠 ต้องเช็ค : {stats.get('need_check', 0)}",
        f"🚫 ยกเลิก : {stats.get('cancelled', 0)}",
        f"⚠️ ค้างนาน : {stats.get('delayed', 0)}",
        f"✅ ปิดงาน : {stats.get('completed', 0)}",
        f"💸 ยอดชำระรวม : ฿{stats.get('total_price', 0):,.2f}",
    ]

    # Cancelled items
    cancelled = stats.get("cancelled_items", [])
    if cancelled:
        lines.append("")
        lines.append("🚫 สินค้าที่ยกเลิก")
        for item in cancelled:
            lines.append(f"  • {item['name']}")

    # Scan info
    if scan_info:
        lines.append("")
        new_count = scan_info.get("new", 0)
        changed = scan_info.get("changed", 0)
        lines.append(
            f"🔍 Scan: {scan_info.get('total', 0)} "
            f"| 🆕 +{new_count} "
            f"| 🔄 ~{changed}"
        )
        lines.append(f"⏰ เวลา: {datetime.now().strftime('%H:%M')}")

    return "\n".join(lines)


def format_tracking_status(parcel: dict, tracking_data: dict = None,
                           staff: dict = None, timelines: list = None) -> str:
    """Format single parcel tracking status with delivery staff info."""
    status_emoji = {
        "ON_PICKED_UP": "📥",
        "ON_SHIPPING": "🚚",
        "ON_DELIVERED": "✅",
        "ON_UNABLE_TO_SEND": "❌",
        "ON_OTHER_STATUS": "❓",
        "UNKNOWN": "⏳",
        "CANCELLED": "🚫",
    }

    status = parcel.get("status", "UNKNOWN")
    emoji = status_emoji.get(status, "❓")
    name = parcel.get("product_name", "")
    tracking = parcel.get("tracking_no", "")
    courier = parcel.get("courier", "")
    event = parcel.get("last_event", "ไม่มีข้อมูล")

    lines = [
        f"{emoji} {tracking}",
        f"📦 ขนส่ง: {courier}",
    ]

    if name:
        lines.append(f"🏷️ สินค้า: {name}")

    lines.append(f"📋 สถานะ: {format_status_thai(status)}")

    # Delivery staff info
    if staff:
        lines.append("")
        if staff.get("name"):
            lines.append(f"👤 พนักงาน: {staff['name']}")
        if staff.get("phone"):
            lines.append(f"📞 เบอร์พนักงาน: {staff['phone']}")
        if staff.get("branch_phone"):
            lines.append(f"🏢 เบอร์สาขา: {staff['branch_phone']}")

    # Timeline events
    if timelines:
        lines.append("")
        lines.append("📜 ประวัติ (ล่าสุด 5 รายการ):")
        for t in timelines[:5]:
            date = t.get("date", "")
            time = t.get("time", "")
            desc = t.get("description", "")
            lines.append(f"  • {date} {time} - {desc}")

    return "\n".join(lines)


def format_status_thai(status: str) -> str:
    """Convert status code to Thai text."""
    status_map = {
        "ON_PICKED_UP": "รับสินค้าแล้ว",
        "ON_SHIPPING": "กำลังจัดส่ง",
        "ON_DELIVERED": "จัดส่งสำเร็จ",
        "ON_UNABLE_TO_SEND": "ไม่สามารถจัดส่งได้",
        "ON_OTHER_STATUS": "สถานะอื่น",
        "UNKNOWN": "รอตรวจสอบ",
        "CANCELLED": "ยกเลิก",
    }
    return status_map.get(status, status)


def format_carrier_anomaly(carrier_stats: dict, min_val: int, max_val: int) -> str:
    """Format carrier anomaly alert."""
    lines = [
        "⚠️ <Order Tracker | ปิดพัสดุผิดปกติรายค่าย>",
        f"ช่วงปกติที่ตั้งไว้: {min_val}-{max_val} ชิ้น/ค่าย/รอบ",
    ]

    for carrier, count in carrier_stats.items():
        if count < min_val or count > max_val:
            lines.append(f"  - {carrier}: {count} ชิ้น")

    return "\n".join(lines)


def format_parcel_list(parcels: list, title: str = "รายการพัสดุ") -> str:
    """Format a list of parcels."""
    if not parcels:
        return f"📭 ไม่มี{title}"

    status_emoji = {
        "ON_PICKED_UP": "📥",
        "ON_SHIPPING": "🚚",
        "ON_DELIVERED": "✅",
        "ON_UNABLE_TO_SEND": "❌",
        "UNKNOWN": "⏳",
        "CANCELLED": "🚫",
    }

    lines = [f"📋 {title} ({len(parcels)} รายการ)", ""]

    for p in parcels:
        emoji = status_emoji.get(p.get("status", "UNKNOWN"), "❓")
        name = p.get("product_name", "")
        tracking = p.get("tracking_no", "")
        line = f"{emoji} {tracking}"
        if name:
            line += f" | {name}"
        lines.append(line)

    return "\n".join(lines)


def format_by_courier(parcels_by_courier: dict) -> str:
    """Format parcels grouped by courier for copy."""
    if not parcels_by_courier:
        return "📭 ไม่มีพัสดุ"

    lines = ["📋 คัดลอกสินค้าแยกขนส่ง", ""]

    for courier, parcels in parcels_by_courier.items():
        lines.append(f"🚛 {courier} ({len(parcels)} ชิ้น)")
        for p in parcels:
            lines.append(f"  {p['tracking_no']}")
        lines.append("")

    return "\n".join(lines)
