"""
Work Order Notification Tool for Sentry Bot.

This script should be placed in $SENTRY_HOME/tools/

Sends work order notifications to technicians via Telegram,
triggers data collection after "done" reply.
"""

import requests
import sys
import argparse
import json
from typing import Dict, Any

BMS_API_URL = "http://localhost:9095"  # SENTINEL BMS Backend
SENTRY_SECRET = "sentry-bms-phase-41"  # Shared secret with BMS


def send_notification(work_order_data: Dict[str, Any]) -> bool:
    """Send work order notification via Sentry.

    Args:
        work_order_data: Work order information

    Returns:
        True if notification sent successfully
    """
    try:
        payload = {
            "technician_id": work_order_data["technician_id"],
            "technician_name": work_order_data["technician_name"],
            "work_order_id": work_order_data["work_order_id"],
            "equipment_name": work_order_data["equipment_name"],
            "criticality": work_order_data.get("criticality", "MEDIUM"),
            "service_type": work_order_data["service_type"],
            "problem_description": work_order_data.get("description", "Scheduled maintenance"),
            "require_data_collection": True,
            "auto_collect": False,  # Wait for "done" reply
        }

        response = requests.post(
            f"{BMS_API_URL}/api/sentry/work-order/notify",
            json=payload,
            headers={"X-Sentry-Secret": SENTRY_SECRET},
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            print("✅ Work order notification sent successfully")
            print(f"   Service Record: {result.get('service_record_code', 'N/A')}")
            return True
        else:
            print(f"❌ BMS API error: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error sending notification: {e}")
        return False


def get_collection_status(service_record_code: str) -> Dict[str, Any]:
    """Get data collection status for a service record.

    Args:
        service_record_code: Service record code (e.g., SR-2026-ABC123)

    Returns:
        Collection status dictionary
    """
    try:
        response = requests.get(
            f"{BMS_API_URL}/api/sentry/work-order/status/{service_record_code}",
            headers={"X-Sentry-Secret": SENTRY_SECRET},
            timeout=10
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ BMS API error: {response.status_code}")
            return {"error": response.text}

    except Exception as e:
        print(f"❌ Error getting status: {e}")
        return {"error": str(e)}


def mark_complete(service_record_code: str) -> bool:
    """Mark service record as complete.

    Args:
        service_record_code: Service record code

    Returns:
        True if marked complete successfully
    """
    try:
        response = requests.post(
            f"{BMS_API_URL}/api/sentry/work-order/complete/{service_record_code}",
            headers={"X-Sentry-Secret": SENTRY_SECRET},
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            print("✅ Service record marked complete")
            print(f"   ML processing: {result.get('ml_processing_initiated', False)}")
            return True
        else:
            print(f"❌ BMS API error: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error marking complete: {e}")
        return False


def cli():
    """Command-line interface."""
    parser = argparse.ArgumentParser(description="Work Order Notification Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Notify command
    notify_parser = subparsers.add_parser("notify", help="Send WO notification")
    notify_parser.add_argument("--wo-id", required=True, help="Work order ID")
    notify_parser.add_argument("--equipment-id", required=True, help="Equipment ID")
    notify_parser.add_argument("--building-id", required=True, help="Building ID")
    notify_parser.add_argument("--equipment-name", required=True, help="Equipment name")
    notify_parser.add_argument("--service-type", required=True, choices=["minor", "major", "breakdown", "callout"])
    notify_parser.add_argument("--technician-id", required=True, help="Technician Telegram ID")
    notify_parser.add_argument("--technician-name", required=True, help="Technician name")
    notify_parser.add_argument("--criticality", default="MEDIUM", choices=["HIGH", "MEDIUM", "LOW"])
    notify_parser.add_argument("--description", help="Problem description")

    # Status command
    status_parser = subparsers.add_parser("status", help="Get collection status")
    status_parser.add_argument("code", help="Service record code (SR-2026-XXX)")

    # Complete command
    complete_parser = subparsers.add_parser("complete", help="Mark as complete")
    complete_parser.add_argument("code", help="Service record code")

    args = parser.parse_args()

    if args.command == "notify":
        data = {
            "work_order_id": args.wo_id,
            "equipment_id": args.equipment_id,
            "building_id": args.building_id,
            "equipment_name": args.equipment_name,
            "service_type": args.service_type,
            "technician_id": args.technician_id,
            "technician_name": args.technician_name,
            "criticality": args.criticality,
            "description": args.description
        }
        send_notification(data)

    elif args.command == "status":
        status = get_collection_status(args.code)
        if "error" not in status:
            print(f"Service Record: {status['service_record_code']}")
            print(f"Status: {status['status']}")
            print(f"Progress: {status['progress']}")
            print(f"Collected: {status['collected_items']}")
            if status['missing_items']:
                print(f"Missing: {status['missing_items']}")
            if status.get('next_prompt'):
                print(f"\n📋 Next: {status['next_prompt']}")
        else:
            print(f"Error: {status['error']}")

    elif args.command == "complete":
        mark_complete(args.code)

    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
