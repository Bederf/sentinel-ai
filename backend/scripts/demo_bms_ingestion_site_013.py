#!/usr/bin/env python3
"""
Demo: Complete BMS Ingestion Workflow for site-013

This script demonstrates the full automated BMS discovery workflow:
1. Trigger point discovery and AI classification
2. Review generated equipment mappings
3. Apply corrections if needed
4. Approve and activate the building

Usage:
    python3 demo_bms_ingestion_site_013.py

Prerequisites:
    - Backend server running on http://localhost:9095
    - Backend environment variables configured (.env)
"""

import json
import sys
from pathlib import Path
from typing import Optional

import httpx

# Configuration
API_BASE = "http://localhost:9095"
SITE_ID = "site-013"
DEVICE_IP = "192.168.1.100"
DEMO_MODE = True


class BmsIngestionDemo:
    """Orchestrates the full BMS ingestion workflow."""

    def __init__(self, base_url: str = API_BASE):
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url, timeout=30.0)
        self.discovery_id: Optional[str] = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    # =========================================================================
    # Step 1: Trigger Discovery & Classification
    # =========================================================================

    def step_1_discover(self):
        """Step 1: Trigger point discovery and AI classification."""
        print("\n" + "=" * 75)
        print("STEP 1: Trigger Point Discovery & Classification")
        print("=" * 75)

        request_data = {
            "device_ip": DEVICE_IP,
            "site_id": SITE_ID,
            "use_demo": DEMO_MODE,
            "demo_site_id": "site-002",
            "bms_vendor": "niagara",
        }

        print(f"\nPOST {self.base_url}/api/niagara/discover-and-classify")
        print(f"Request: {json.dumps(request_data, indent=2)}")

        response = self.client.post("/api/niagara/discover-and-classify", json=request_data)

        if response.status_code != 200:
            print(f"\n❌ Discovery failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False

        result = response.json()
        self.discovery_id = result.get("discovery_id")

        print("\n✓ Discovery successful!")
        print(f"  Discovery ID: {self.discovery_id}")
        print(f"  Points discovered: {result.get('points_count')}")
        print(f"  Equipment identified: {result.get('equipment_count')}")
        print(f"  Status: {result.get('status')}")

        # Print summary
        summary = result.get("summary", {})
        if summary:
            print("\nClassification Summary:")
            unique_equipment = summary.get("unique_equipment", {})
            print("  Equipment types discovered:")
            equipment_types = {}
            for eq_id, eq_type in unique_equipment.items():
                if eq_type not in equipment_types:
                    equipment_types[eq_type] = []
                equipment_types[eq_type].append(eq_id)

            for eq_type in sorted(equipment_types.keys()):
                count = len(equipment_types[eq_type])
                print(f"    - {eq_type}: {count}")

            confidence = summary.get("confidence_breakdown", {})
            print("\n  Confidence breakdown:")
            print(f"    - High: {confidence.get('high', 0)}")
            print(f"    - Medium: {confidence.get('medium', 0)}")
            print(f"    - Low: {confidence.get('low', 0)}")

        return True

    # =========================================================================
    # Step 2: Review Equipment Mappings
    # =========================================================================

    def step_2_review(self):
        """Step 2: Review AI-generated equipment mappings."""
        if not self.discovery_id:
            print("❌ No discovery_id available. Run step 1 first.")
            return False

        print("\n" + "=" * 75)
        print("STEP 2: Review Equipment Mappings")
        print("=" * 75)

        print(f"\nGET {self.base_url}/api/niagara/mappings/{self.discovery_id}")

        response = self.client.get(f"/api/niagara/mappings/{self.discovery_id}")

        if response.status_code != 200:
            print(f"\n❌ Failed to get mappings: {response.status_code}")
            print(f"Response: {response.text}")
            return False

        result = response.json()

        print("\n✓ Mappings retrieved!")
        print(f"  Total equipment: {result.get('equipment_count')}")
        print(f"  Total points: {result.get('total_points')}")
        print(f"  Status: {result.get('status')}")

        # Print equipment list
        equipment_list = result.get("equipment", [])
        print(f"\nEquipment Mappings ({len(equipment_list)} total):")
        print(f"{'Equipment ID':<20} {'Type':<12} {'Confidence':<12} {'Points':<8}")
        print("-" * 60)

        for eq in sorted(equipment_list, key=lambda x: x.get("equipment_id", "")):
            eq_id = eq.get("equipment_id", "UNKNOWN")[:18]
            eq_type = eq.get("equipment_type", "unknown")[:10]
            confidence = eq.get("confidence", "unknown")[:10]
            point_count = len(eq.get("points", []))

            print(f"{eq_id:<20} {eq_type:<12} {confidence:<12} {point_count:<8}")

        # Print validation results
        validation = result.get("validation", {})
        print("\nValidation Results:")
        print(f"  Valid: {validation.get('valid', True)}")
        orphan_count = len(validation.get("orphan_points", []))
        if orphan_count > 0:
            print(f"  ⚠ Orphan points: {orphan_count}")
        if validation.get("warnings"):
            print(f"  ⚠ Warnings: {len(validation.get('warnings', []))}")
        if validation.get("errors"):
            print(f"  ❌ Errors: {len(validation.get('errors', []))}")

        return True

    # =========================================================================
    # Step 3: Approve & Activate
    # =========================================================================

    def step_3_approve(self):
        """Step 3: Approve mappings and activate building."""
        if not self.discovery_id:
            print("❌ No discovery_id available. Run step 1 first.")
            return False

        print("\n" + "=" * 75)
        print("STEP 3: Approve & Activate Building")
        print("=" * 75)

        print(f"\nPOST {self.base_url}/api/niagara/mappings/{self.discovery_id}/approve")

        response = self.client.post(
            f"/api/niagara/mappings/{self.discovery_id}/approve", params={"approved_by": "demo_script"}
        )

        if response.status_code != 200:
            print(f"\n❌ Approval failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False

        result = response.json()

        print("\n✓ Approval successful!")
        print(f"  Equipment created: {result.get('equipment_created')}")
        print(f"  Message: {result.get('message')}")

        return True

    # =========================================================================
    # Step 4: Verify Building Created
    # =========================================================================

    def step_4_verify(self):
        """Step 4: Verify building was created successfully."""
        print("\n" + "=" * 75)
        print("STEP 4: Verify Building Created")
        print("=" * 75)

        # Check if building endpoint is available
        print(f"\nGET {self.base_url}/api/buildings/{SITE_ID}")

        try:
            response = self.client.get(f"/api/buildings/{SITE_ID}")

            if response.status_code == 200:
                building = response.json()
                print("\n✓ Building found!")
                print(f"  Name: {building.get('name')}")
                print(f"  Address: {building.get('address')}")
                print(f"  Equipment count: {building.get('equipment_count')}")
                return True
            elif response.status_code == 404:
                print("\n⚠ Building not in API yet, checking filesystem...")
        except Exception as e:
            print(f"\n⚠ API check failed: {e}, checking filesystem...")

        # Check filesystem
        building_file = Path(__file__).parent.parent / "app" / "data" / "sites" / SITE_ID / "building.json"
        equipment_dir = building_file.parent / "equipment"

        if building_file.exists():
            print(f"\n✓ building.json exists: {building_file}")
            with open(building_file) as f:
                building = json.load(f)
            print(f"  Name: {building.get('name')}")
            print(f"  Address: {building.get('address')}")
        else:
            print(f"\n❌ building.json not found: {building_file}")
            return False

        if equipment_dir.exists():
            equipment_files = list(equipment_dir.glob("*.json"))
            print(f"\n✓ Equipment directory exists with {len(equipment_files)} equipment files")

            # Count by type
            type_counts = {}
            for eq_file in equipment_files:
                try:
                    with open(eq_file) as f:
                        eq_data = json.load(f)
                    eq_type = eq_data.get("equipment_type", "unknown")
                    type_counts[eq_type] = type_counts.get(eq_type, 0) + 1
                except Exception as e:
                    print(f"    Warning: Could not read {eq_file.name}: {e}")

            if type_counts:
                print("  Equipment by type:")
                for eq_type in sorted(type_counts.keys()):
                    print(f"    - {eq_type}: {type_counts[eq_type]}")

            # Show sample equipment
            if equipment_files:
                sample_file = equipment_files[0]
                with open(sample_file) as f:
                    sample_eq = json.load(f)
                print(f"\n  Sample equipment file: {sample_file.name}")
                print(f"    ID: {sample_eq.get('id')}")
                print(f"    Name: {sample_eq.get('name')}")
                print(f"    Type: {sample_eq.get('equipment_type')}")
                print(f"    Points: {len(sample_eq.get('points', {}))}")

            return True
        else:
            print(f"\n❌ Equipment directory not found: {equipment_dir}")
            return False

    # =========================================================================
    # Main workflow
    # =========================================================================

    def run_full_workflow(self):
        """Execute the complete BMS ingestion workflow."""
        print("\n" + "=" * 75)
        print("BMS INGESTION DEMO - site-013 (Rosebank Corporate Park - Block B)")
        print("=" * 75)
        print("\nConfiguration:")
        print(f"  Site ID: {SITE_ID}")
        print(f"  Device IP: {DEVICE_IP}")
        print(f"  Demo mode: {DEMO_MODE}")
        print(f"  API Base: {self.base_url}")

        steps = [
            ("Discovery & Classification", self.step_1_discover),
            ("Review Equipment Mappings", self.step_2_review),
            ("Approve & Activate", self.step_3_approve),
            ("Verify Building Created", self.step_4_verify),
        ]

        results = {}
        for step_name, step_func in steps:
            try:
                success = step_func()
                results[step_name] = "✓ PASS" if success else "❌ FAIL"
                if not success:
                    print(f"\n⚠ Stopping at {step_name}")
                    break
            except Exception as e:
                print(f"\n❌ Exception in {step_name}: {e}")
                import traceback

                traceback.print_exc()
                results[step_name] = f"❌ ERROR: {e}"
                break

        # Summary
        print("\n" + "=" * 75)
        print("WORKFLOW SUMMARY")
        print("=" * 75)
        for step_name, result in results.items():
            print(f"{step_name:<40} {result}")

        all_passed = all("✓" in r for r in results.values())
        if all_passed:
            print("\n✓ All steps completed successfully!")
            print("\nNext steps:")
            print("  1. Access the frontend: http://localhost:9096")
            print("  2. Select 'Rosebank Corporate Park - Block B' from the site dropdown")
            print(f"  3. Verify {self.discovery_id and 'equipment' or 'building'} display")
            print("  4. Check Integration Monitoring dashboard for BMS data")
            return True
        else:
            print("\n❌ Workflow completed with errors. See details above.")
            return False


def main():
    """Main entry point."""
    try:
        with BmsIngestionDemo() as demo:
            success = demo.run_full_workflow()
            sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
