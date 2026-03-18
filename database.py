"""
SQLite Database for Order Tracker
Tables: parcels, tracking_history, daily_summary
"""
import sqlite3
import os
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(__file__))
DB_PATH = os.path.join(DATA_DIR, "tracker.db")


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS parcels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_no TEXT UNIQUE NOT NULL,
            courier TEXT NOT NULL,
            courier_key TEXT NOT NULL,
            product_name TEXT DEFAULT '',
            price REAL DEFAULT 0,
            status TEXT DEFAULT 'UNKNOWN',
            last_event TEXT DEFAULT '',
            added_date TEXT NOT NULL,
            updated_date TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS tracking_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_no TEXT NOT NULL,
            status TEXT NOT NULL,
            event TEXT NOT NULL,
            checked_date TEXT NOT NULL,
            FOREIGN KEY (tracking_no) REFERENCES parcels(tracking_no)
        );

        CREATE TABLE IF NOT EXISTS scan_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL,
            total_scanned INTEGER DEFAULT 0,
            new_count INTEGER DEFAULT 0,
            changed_count INTEGER DEFAULT 0,
            unchanged_count INTEGER DEFAULT 0
        );
    """)

    conn.commit()
    conn.close()
    logger.info("Database initialized")


# ===== Parcel CRUD =====

def add_parcel(tracking_no: str, courier: str, courier_key: str,
               product_name: str = "", price: float = 0) -> bool:
    """Add a new parcel to track."""
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO parcels (tracking_no, courier, courier_key, product_name, price, added_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tracking_no, courier, courier_key, product_name, price,
             datetime.now().isoformat())
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Parcel {tracking_no} already exists")
        return False
    finally:
        conn.close()


def remove_parcel(tracking_no: str) -> bool:
    """Remove a parcel from tracking."""
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM parcels WHERE tracking_no = ?", (tracking_no,)
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_parcel(tracking_no: str) -> dict | None:
    """Get a single parcel by tracking number."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM parcels WHERE tracking_no = ?", (tracking_no,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_parcels() -> list[dict]:
    """Get all active (not delivered/cancelled) parcels."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM parcels WHERE is_active = 1 ORDER BY added_date DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_parcels() -> list[dict]:
    """Get all parcels."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM parcels ORDER BY added_date DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_parcel_status(tracking_no: str, status: str, last_event: str) -> str | None:
    """
    Update parcel status. Returns old status if changed, None if same.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT status FROM parcels WHERE tracking_no = ?", (tracking_no,)
    ).fetchone()

    if not row:
        conn.close()
        return None

    old_status = row["status"]
    now = datetime.now().isoformat()

    # Update parcel
    conn.execute(
        """UPDATE parcels SET status = ?, last_event = ?, updated_date = ?
           WHERE tracking_no = ?""",
        (status, last_event, now, tracking_no)
    )

    # Mark as inactive if delivered
    if status in ("ON_DELIVERED", "DELIVERED"):
        conn.execute(
            "UPDATE parcels SET is_active = 0 WHERE tracking_no = ?",
            (tracking_no,)
        )

    # Log to history
    conn.execute(
        """INSERT INTO tracking_history (tracking_no, status, event, checked_date)
           VALUES (?, ?, ?, ?)""",
        (tracking_no, status, last_event, now)
    )

    conn.commit()
    conn.close()

    return old_status if old_status != status else None


# ===== Summary Stats =====

def get_summary_stats() -> dict:
    """Get summary statistics for active parcels."""
    conn = get_db()

    stats = {
        "shipping": 0,      # กำลังจัดส่ง
        "need_check": 0,     # ต้องเช็ค
        "cancelled": 0,      # ยกเลิก
        "delayed": 0,        # ค้างนาน
        "completed": 0,      # ปิดงาน (delivered)
        "total_price": 0.0,  # ยอดชำระรวม
        "cancelled_items": [],  # รายการที่ยกเลิก
    }

    rows = conn.execute("SELECT * FROM parcels").fetchall()

    for row in rows:
        r = dict(row)
        status = r.get("status", "UNKNOWN")

        if status in ("ON_SHIPPING", "ON_PICKED_UP", "UNKNOWN"):
            stats["shipping"] += 1
        elif status in ("ON_UNABLE_TO_SEND", "ON_OTHER_STATUS"):
            stats["need_check"] += 1
        elif status == "CANCELLED":
            stats["cancelled"] += 1
            if r.get("product_name"):
                stats["cancelled_items"].append({
                    "name": r["product_name"],
                    "tracking": r["tracking_no"],
                })
        elif status in ("ON_DELIVERED", "DELIVERED"):
            stats["completed"] += 1

        stats["total_price"] += r.get("price", 0) or 0

    conn.close()
    return stats


def get_parcels_by_courier() -> dict[str, list]:
    """Group active parcels by courier."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM parcels WHERE is_active = 1 ORDER BY courier"
    ).fetchall()
    conn.close()

    by_courier = {}
    for row in rows:
        r = dict(row)
        courier = r["courier"]
        if courier not in by_courier:
            by_courier[courier] = []
        by_courier[courier].append(r)

    return by_courier


def log_scan(total: int, new: int, changed: int, unchanged: int):
    """Log a scan result."""
    conn = get_db()
    conn.execute(
        """INSERT INTO scan_logs (scan_date, total_scanned, new_count, changed_count, unchanged_count)
           VALUES (?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), total, new, changed, unchanged)
    )
    conn.commit()
    conn.close()


def search_parcels(query: str) -> list[dict]:
    """Search parcels by tracking number or product name."""
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM parcels
           WHERE tracking_no LIKE ? OR product_name LIKE ?
           ORDER BY added_date DESC LIMIT 20""",
        (f"%{query}%", f"%{query}%")
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_today_deliveries() -> list[dict]:
    """Get parcels that are being delivered today (ON_SHIPPING with today's update)."""
    today = date.today().isoformat()
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM parcels
           WHERE is_active = 1
             AND status = 'ON_SHIPPING'
             AND updated_date LIKE ?
           ORDER BY updated_date DESC""",
        (f"{today}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_delivered_today() -> list[dict]:
    """Get parcels that were delivered today."""
    today = date.today().isoformat()
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM parcels
           WHERE status = 'ON_DELIVERED'
             AND updated_date LIKE ?
           ORDER BY updated_date DESC""",
        (f"{today}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Initialize database on import
init_db()
