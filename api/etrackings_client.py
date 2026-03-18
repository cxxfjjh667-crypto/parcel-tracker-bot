"""
eTrackings API v3 Client
https://api.etrackings.com/api/v3
"""
import requests
import logging
from config import ETRACKINGS_API_KEY, ETRACKINGS_KEY_SECRET, ETRACKINGS_BASE_URL

logger = logging.getLogger(__name__)


class ETrackingsClient:
    """Wrapper for eTrackings API v3"""

    def __init__(self):
        self.base_url = ETRACKINGS_BASE_URL
        self.api_key = ETRACKINGS_API_KEY
        self.key_secret = ETRACKINGS_KEY_SECRET
        self.call_count = 0
        self._update_headers()

    def _update_headers(self):
        """Update headers with current credentials."""
        self.headers = {
            "Etrackings-Api-Key": self.api_key,
            "Etrackings-Key-Secret": self.key_secret,
            "Content-Type": "application/json",
        }

    def update_credentials(self, api_key: str, key_secret: str):
        """Hot-swap API credentials without restarting the bot."""
        self.api_key = api_key
        self.key_secret = key_secret
        self.call_count = 0
        self._update_headers()
        logger.info("API credentials updated successfully")

    def track(self, tracking_no: str, courier: str) -> dict:
        """
        Track a parcel by tracking number and courier.
        
        Args:
            tracking_no: The tracking/waybill number
            courier: eTrackings courier key (e.g. 'j-t-express', 'flash-express')
            
        Returns:
            dict with tracking data or error info
        """
        url = f"{self.base_url}/tracks/find"
        payload = {
            "trackingNo": tracking_no,
            "courier": courier,
        }

        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=15)
            self.call_count += 1
            data = resp.json()

            if resp.status_code == 200:
                return {"success": True, "data": data.get("data", {})}
            elif resp.status_code == 404:
                return {"success": False, "error": "ไม่พบพัสดุนี้ในระบบ"}
            else:
                msg = data.get("meta", {}).get("message", f"Error {resp.status_code}")
                return {"success": False, "error": msg}

        except requests.exceptions.Timeout:
            logger.error(f"Timeout tracking {tracking_no}")
            return {"success": False, "error": "หมดเวลาเชื่อมต่อ"}
        except Exception as e:
            logger.error(f"Error tracking {tracking_no}: {e}")
            return {"success": False, "error": str(e)}

    def get_tracking_status(self, tracking_data: dict) -> str:
        """
        Extract the latest status from tracking data.
        
        Returns status string like:
            ON_PICKED_UP, ON_SHIPPING, ON_DELIVERED, 
            ON_UNABLE_TO_SEND, ON_OTHER_STATUS
        """
        if not tracking_data.get("success"):
            return "UNKNOWN"

        data = tracking_data.get("data", {})
        
        # eTrackings returns status in the track data
        status = data.get("status", "UNKNOWN")
        return status

    def get_latest_event(self, tracking_data: dict) -> str:
        """Extract the latest tracking event description."""
        if not tracking_data.get("success"):
            return "ไม่สามารถดึงข้อมูลได้"

        data = tracking_data.get("data", {})
        
        # eTrackings uses "currentStatus" for latest event
        current = data.get("currentStatus", "")
        if current:
            updated = data.get("lastUpdatedStatusAt", "")
            if updated:
                time_part = updated.split("T")[1][:5] if "T" in updated else ""
                return f"{current}" if not time_part else current
            return current

        # Fallback: look in timelines
        timelines = data.get("timelines", [])
        if timelines:
            first_day = timelines[0]
            details = first_day.get("details", [])
            if details:
                latest = details[0]
                return latest.get("description", "ไม่มีข้อมูล")

        return "ไม่มีข้อมูลอัพเดท"

    def get_delivery_staff(self, tracking_data: dict) -> dict | None:
        """Extract delivery staff info (name, phone, branch phone)."""
        if not tracking_data.get("success"):
            return None

        detail = tracking_data.get("data", {}).get("detail", {})
        if not detail:
            return None

        name = detail.get("deliveryStaffName", "").strip()
        phone = detail.get("deliveryStaffPhoneNumber", "").strip()
        branch_phone = detail.get("deliveryStaffBranchPhoneNumber", "").strip()

        if not name and not phone:
            return None

        return {
            "name": name,
            "phone": phone,
            "branch_phone": branch_phone,
        }

    def get_tracking_timelines(self, tracking_data: dict) -> list:
        """Extract timeline events for display."""
        if not tracking_data.get("success"):
            return []

        timelines = tracking_data.get("data", {}).get("timelines", [])
        events = []
        for day in timelines:
            for detail in day.get("details", []):
                events.append({
                    "time": detail.get("time", ""),
                    "date": detail.get("date", ""),
                    "status": detail.get("status", ""),
                    "description": detail.get("description", ""),
                })
        return events

    def list_couriers(self) -> list:
        """Get list of supported couriers."""
        url = f"{self.base_url}/couriers"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
        except Exception as e:
            logger.error(f"Error listing couriers: {e}")
        return []
