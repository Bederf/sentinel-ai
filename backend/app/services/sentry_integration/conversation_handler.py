"""
WO Conversation Handler for Sentry Bot.

This script should be placed in $SENTRY_HOME/handlers/

Handles the conversation flow AFTER technician replies "done":
1. Receives "done" from technician
2. Gets first data collection prompt from BMS
3. Shows prompt to technician
4. Receives file/photo/audio reply
5. Sends to BMS, gets next prompt
6. Repeats until all items collected
"""

import requests
import json
import os
from typing import Dict, Any, Optional, List
from enum import Enum


BMS_API_URL = os.getenv("SENTINEL_API_URL", "http://localhost:9095")  # SENTINEL BMS Backend
SENTRY_SECRET = (os.getenv("SENTRY_WEBHOOK_SECRET", "") or "").strip()
SENTRY_API_KEY = (os.getenv("SENTRY_BOT_API_KEY", "") or "").strip()


def _auth_headers() -> dict[str, str]:
    if not SENTRY_SECRET:
        raise RuntimeError("SENTRY_WEBHOOK_SECRET is required for /api/sentry requests")
    headers = {"X-Sentry-Secret": SENTRY_SECRET}
    if SENTRY_API_KEY:
        headers["X-Sentry-API-Key"] = SENTRY_API_KEY
    return headers


class ReplyType(Enum):
    TEXT = "text"
    PHOTO = "photo"
    AUDIO = "audio"
    DOCUMENT = "file"


class WOConversationHandler:
    """Handles WO "done" reply and sequential data collection."""

    def __init__(self, service_record_code: str, telegram_user_id: str):
        self.service_record_code = service_record_code
        self.telegram_user_id = telegram_user_id
        self.collected_items: List[str] = []

    def handle_initial_done(self) -> Optional[str]:
        """Handle technician's "done" reply - get first prompt.

        Returns:
            Next prompt message to show technician, or None if error
        """
        try:
            # Send "done" response to BMS
            response = requests.post(
                f"{BMS_API_URL}/api/sentry/work-order/response",
                json={
                    "service_record_code": self.service_record_code,
                    "telegram_user_id": self.telegram_user_id,
                    "message_type": "text",
                    "content": "done",
                },
                headers=_auth_headers(),
                timeout=10,
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success") and result.get("next_prompt"):
                    return (
                        f"✅ Service completed!\n\nFor ML training data, "
                        f"please provide items one by one:\n\n{result['next_prompt']}"
                    )
                else:
                    print(f"❌ Unexpected response: {result}")
                    return None
            else:
                print(f"❌ BMS API error {response.status_code}: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error handling 'done': {e}")
            return None

    def handle_file_reply(self, file_info: Dict[str, Any], message_type: str) -> Optional[str]:
        """Handle file/photo/audio reply from technician.

        Args:
            file_info: File information dict
                - file_id: Telegram file ID
                - file_name: Original filename
                - file_size: File size in bytes
                - mime_type: MIME type
                - file_path: Local path (after download)
            message_type: Type of message (photo/audio/file)

        Returns:
            Next prompt or completion message, or None if error
        """
        try:
            # Send file to BMS
            response = requests.post(
                f"{BMS_API_URL}/api/sentry/work-order/response",
                json={
                    "service_record_code": self.service_record_code,
                    "telegram_user_id": self.telegram_user_id,
                    "message_type": message_type,
                    "content": file_info,
                },
                headers=_auth_headers(),
                timeout=30,  # Allow longer for file uploads
            )

            if response.status_code == 200:
                result = response.json()

                # Check if collection is complete
                if result.get("is_complete"):
                    completion_msg = (
                        f"✅ All data collected!\n\n"
                        f"Items: {result['progress']}\n"
                        f"ML processing initiated.\n\n"
                        f"Thank you for your submission!"
                    )
                    return completion_msg

                # Check if there are still items to collect
                elif result.get("next_prompt"):
                    self.collected_items.append(result.get("attachment_type"))
                    progress = result.get("progress", "")
                    percent = result.get("completion_percentage", 0)

                    return f"✅ Received! Progress: {progress} ({percent:.0f}%)\n\n{result['next_prompt']}"

                else:
                    return "✅ Received! Waiting for next instruction..."

            else:
                print(f"❌ BMS API error {response.status_code}: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error handling file reply: {e}")
            return None

    def get_collection_status(self) -> Optional[Dict[str, Any]]:
        """Get current collection status.

        Returns:
            Status dict with progress, missing items, etc.
        """
        try:
            response = requests.get(
                f"{BMS_API_URL}/api/sentry/work-order/status/{self.service_record_code}",
                headers=_auth_headers(),
                timeout=10,
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ BMS API error {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Error getting status: {e}")
            return None

    def format_status_message(self) -> str:
        """Format collection status for Telegram display.

        Returns:
            Formatted status message
        """
        status = self.get_collection_status()
        if not status or "error" in status:
            return "❌ Could not get status."

        msg = f"📋 Service Record: {status['service_record_code']}\n"
        msg += f"Status: {status['status']}\n"
        msg += f"Progress: {status['progress']}\n\n"

        # Show collected items
        if status.get("collected_items"):
            msg += "✅ Collected:\n"
            for item in status["collected_items"]:
                msg += f"  • {self.format_item_name(item)}\n"

        # Show missing items
        if status.get("missing_items"):
            msg += "\n⏳ Still needed:\n"
            for item in status["missing_items"]:
                msg += f"  • {self.format_item_name(item)}\n"

        # Show next prompt
        if status.get("next_prompt"):
            msg += f"\n📝 Next: {status['next_prompt']}"

        return msg

    @staticmethod
    def format_item_name(item: str) -> str:
        """Format item name for display."""
        item_names = {
            "service_sheet": "Service sheet photo",
            "audio_recording": "Audio recording",
            "oil_sample": "Oil sample photo",
            "diesel_sample": "Diesel sample photo",
            "thermal_image": "Thermal image",
            "issue_photo": "Issue photo",
            "before_photo": "Before photo",
            "after_photo": "After photo",
            "load_test_video": "Load test video",
            "oil_analysis_report": "Oil analysis report",
            "observation": "Text observation",
        }
        return item_names.get(item, item)


def cli():
    """Test CLI for conversation handler."""
    print("WO Conversation Handler Test")
    print("=" * 40)

    # Test 1: Simulate "done" reply
    print("\n1. Testing 'done' reply...")
    handler = WOConversationHandler("SR-2026-TEST123", "@test_user")
    response = handler.handle_initial_done()
    if response:
        print(f"Response:\n{response}\n")
    else:
        print("❌ Failed\n")

    # Test 2: Get status
    print("\n2. Testing status fetch...")
    status = handler.get_collection_status()
    if status:
        print(json.dumps(status, indent=2))
    else:
        print("❌ Failed\n")

    # Test 3: Format status message
    print("\n3. Testing status formatting...")
    formatted = handler.format_status_message()
    print(formatted)


if __name__ == "__main__":
    cli()
