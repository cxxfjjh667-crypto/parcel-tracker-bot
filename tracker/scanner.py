"""
Scanner — Automated parcel status checker
Runs on schedule, checks all active parcels via eTrackings API
"""
import time
import logging
from datetime import datetime

import database as db
from api.etrackings_client import ETrackingsClient
from config import ANOMALY_MIN, ANOMALY_MAX

logger = logging.getLogger(__name__)


class Scanner:
    """Scans all active parcels and detects status changes."""

    def __init__(self):
        self.client = ETrackingsClient()
        self.last_scan_info = {}

    async def scan_all(self, notify_callback=None):
        """
        Scan all active parcels.
        
        Args:
            notify_callback: async function(message: str) to send notifications
            
        Returns:
            dict with scan results
        """
        parcels = db.get_active_parcels()
        
        if not parcels:
            logger.info("No active parcels to scan")
            return {"total": 0, "new": 0, "changed": 0, "unchanged": 0}

        total = len(parcels)
        new_count = 0
        changed_count = 0
        unchanged_count = 0
        changed_parcels = []

        logger.info(f"Scanning {total} active parcels...")

        for parcel in parcels:
            tracking_no = parcel["tracking_no"]
            courier_key = parcel["courier_key"]

            # Fetch tracking data
            result = self.client.track(tracking_no, courier_key)

            if result.get("success"):
                new_status = self.client.get_tracking_status(result)
                new_event = self.client.get_latest_event(result)

                # Update database and check for change
                old_status = db.update_parcel_status(
                    tracking_no, new_status, new_event
                )

                if old_status is not None:
                    # Status changed!
                    changed_count += 1
                    changed_parcels.append({
                        "tracking_no": tracking_no,
                        "courier": parcel["courier"],
                        "product_name": parcel.get("product_name", ""),
                        "old_status": old_status,
                        "new_status": new_status,
                        "event": new_event,
                    })
                    
                    if parcel.get("status") == "UNKNOWN":
                        new_count += 1
                    
                    logger.info(
                        f"Status changed: {tracking_no} "
                        f"{old_status} -> {new_status}"
                    )
                else:
                    unchanged_count += 1
            else:
                unchanged_count += 1
                logger.warning(
                    f"Failed to track {tracking_no}: {result.get('error')}"
                )

            # Rate limit: wait 1 second between calls to be safe
            time.sleep(1)

        # Save scan log
        scan_info = {
            "total": total,
            "new": new_count,
            "changed": changed_count,
            "unchanged": unchanged_count,
        }
        db.log_scan(total, new_count, changed_count, unchanged_count)
        self.last_scan_info = scan_info

        # Send notifications for changed parcels
        if notify_callback and changed_parcels:
            from bot.messages import format_status_thai
            
            for cp in changed_parcels:
                msg = (
                    f"🔔 สถานะเปลี่ยน!\n"
                    f"📦 {cp['tracking_no']}\n"
                    f"🚛 {cp['courier']}\n"
                )
                if cp.get("product_name"):
                    msg += f"🏷️ {cp['product_name']}\n"
                msg += (
                    f"📋 {format_status_thai(cp['old_status'])} "
                    f"→ {format_status_thai(cp['new_status'])}\n"
                    f"📝 {cp['event']}"
                )
                await notify_callback(msg)

        logger.info(
            f"Scan complete: {total} total, {new_count} new, "
            f"{changed_count} changed, {unchanged_count} unchanged"
        )

        return scan_info

    def check_anomalies(self) -> dict:
        """
        Check for carrier anomalies (unusual parcel counts per carrier).
        
        Returns:
            dict of carriers with anomalous counts
        """
        by_courier = db.get_parcels_by_courier()
        anomalies = {}

        for courier, parcels in by_courier.items():
            count = len(parcels)
            if count < ANOMALY_MIN or count > ANOMALY_MAX:
                anomalies[courier] = count

        return anomalies
