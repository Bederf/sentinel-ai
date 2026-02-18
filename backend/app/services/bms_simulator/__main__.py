"""
BMS Simulator CLI

Command-line interface for generating mock BMS data.

Usage:
    # Generate all data for site-002 with Siemens Desigo format
    python -m app.services.bms_simulator generate --site site-002 --vendor desigo

    # Generate only point list export
    python -m app.services.bms_simulator export-points --site site-002 --vendor niagara

    # Generate trends for specific equipment
    python -m app.services.bms_simulator generate-trends --equipment S002-CHILLER-B1-001 --days 90

    # Generate with Rickard DALI format (for diffusers)
    python -m app.services.bms_simulator generate --site site-002 --vendor rickard

    # Generate with Durban climate profile for site-004 hospital
    python -m app.services.bms_simulator generate --site site-004 --vendor niagara --climate durban

    # Generate specific alarm scenario
    python -m app.services.bms_simulator generate-scenario --scenario cold-room-excursion
"""

import argparse
import json
import logging
import sys
from datetime import datetime

from .models import SimulationConfig, VendorType
from .simulator import BMSSimulator


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_vendor(vendor_str: str) -> VendorType:
    """Parse vendor string to VendorType enum."""
    vendor_map = {
        "desigo": VendorType.SIEMENS_DESIGO,
        "siemens": VendorType.SIEMENS_DESIGO,
        "siemens_desigo": VendorType.SIEMENS_DESIGO,
        "niagara": VendorType.NIAGARA,
        "tridium": VendorType.NIAGARA,
        "rickard": VendorType.RICKARD,
        "dali": VendorType.RICKARD,
    }
    return vendor_map.get(vendor_str.lower(), VendorType.SIEMENS_DESIGO)


def cmd_generate(args: argparse.Namespace) -> int:
    """Generate complete BMS simulation data."""
    config = SimulationConfig(
        site_id=args.site,
        vendor=parse_vendor(args.vendor),
        days=args.days,
        interval_minutes=args.interval,
        include_degradation=not args.no_degradation,
        degradation_equipment=args.degrade.split(",") if args.degrade else ["S002-CHILLER-B1-001"],
        include_diffusers=not args.no_diffusers,
        seed=args.seed,
    )

    simulator = BMSSimulator(config)
    result = simulator.generate(
        site_id=args.site,
        include_diffusers=not args.no_diffusers,
        include_trends=not args.no_trends,
        include_alarms=not args.no_alarms,
    )

    print("\n" + "=" * 60)
    print("BMS Simulation Complete")
    print("=" * 60)
    print(f"\nSite: {result['site_id']}")
    print(f"Vendor: {config.vendor}")
    print(f"Elapsed: {result['elapsed_seconds']:.2f}s")

    print("\nGenerated Files:")
    for file_type, path in result["files"].items():
        if isinstance(path, list):
            for p in path:
                print(f"  - {file_type}: {p}")
        else:
            print(f"  - {file_type}: {path}")

    print("\nSummary:")
    if "points" in result["summary"]:
        points = result["summary"]["points"]
        print(f"  - Total devices: {points.get('total_devices', 0)}")
        print(f"  - Total points: {points.get('total_points', 0)}")
        print("  - Devices by type:")
        for dtype, count in points.get("devices_by_type", {}).items():
            print(f"      {dtype}: {count}")

    if "alarms" in result["summary"]:
        alarms = result["summary"]["alarms"]
        print(f"  - Total alarms: {alarms.get('total_alarms', 0)}")
        print("  - By severity:")
        for sev, count in alarms.get("by_severity", {}).items():
            print(f"      {sev}: {count}")

    print("\n" + "=" * 60)
    return 0


def cmd_export_points(args: argparse.Namespace) -> int:
    """Export point list only."""
    config = SimulationConfig(
        site_id=args.site,
        vendor=parse_vendor(args.vendor),
        include_diffusers=not args.no_diffusers,
    )

    simulator = BMSSimulator(config)
    path = simulator.export_points(
        site_id=args.site,
        vendor=parse_vendor(args.vendor),
    )

    print(f"\nPoint list exported to: {path}")

    # Print summary
    summary = simulator.point_exporter.get_point_summary(args.site)
    print(f"\nTotal devices: {summary['total_devices']}")
    print(f"Total points: {summary['total_points']}")
    print("\nDevices by type:")
    for dtype, count in summary.get("devices_by_type", {}).items():
        print(f"  {dtype}: {count} ({summary['points_by_type'].get(dtype, 0)} points)")

    return 0


def cmd_generate_trends(args: argparse.Namespace) -> int:
    """Generate trend data."""
    config = SimulationConfig(
        site_id=args.site,
        days=args.days,
        interval_minutes=args.interval,
        include_degradation=not args.no_degradation,
        degradation_equipment=args.degrade.split(",") if args.degrade else ["S002-CHILLER-B1-001"],
        include_diffusers=not args.no_diffusers,
        seed=args.seed,
    )

    simulator = BMSSimulator(config)
    paths = simulator.generate_trends(
        site_id=args.site,
        equipment_id=args.equipment,
        days=args.days,
    )

    print("\nTrend data generated:")
    for path in paths:
        print(f"  - {path}")

    n_intervals = args.days * 24 * 60 // args.interval
    print(f"\nDays: {args.days}")
    print(f"Interval: {args.interval} minutes")
    print(f"Total intervals: {n_intervals}")

    return 0


def cmd_generate_alarms(args: argparse.Namespace) -> int:
    """Generate alarm events."""
    config = SimulationConfig(
        site_id=args.site,
        days=args.days,
        include_degradation=not args.no_degradation,
        degradation_equipment=args.degrade.split(",") if args.degrade else ["S002-CHILLER-B1-001"],
        include_diffusers=not args.no_diffusers,
        seed=args.seed,
    )

    simulator = BMSSimulator(config)
    path = simulator.generate_alarms(site_id=args.site)

    print(f"\nAlarm events exported to: {path}")

    # Load and summarize
    with open(path, "r") as f:
        alarms = json.load(f)

    summary = simulator.alarm_generator.get_alarm_summary(alarms)
    print(f"\nTotal alarms: {summary['total_alarms']}")
    print("\nBy severity:")
    for sev, count in summary.get("by_severity", {}).items():
        print(f"  {sev}: {count}")
    print("\nBy equipment type:")
    for eq_type, count in summary.get("by_equipment_type", {}).items():
        print(f"  {eq_type}: {count}")

    return 0


def cmd_list_diffusers(args: argparse.Namespace) -> int:
    """List generated Rickard diffusers."""
    config = SimulationConfig(site_id=args.site)
    simulator = BMSSimulator(config)
    diffusers = simulator.get_diffusers(args.site)

    print(f"\nGenerated Rickard Diffusers for {args.site}:")
    print("=" * 80)

    for diff in diffusers:
        eq = diff.get("equipment", {})
        meta = diff.get("metadata", {})
        print(f"\n{diff['id']}")
        print(f"  Name: {diff['name']}")
        print(f"  Connected VAV: {meta.get('connected_vav', 'N/A')}")
        print(f"  Floor/Zone: {diff['device_location']['floor']} / {diff['device_location']['zone']}")
        print(f"  Controller: {eq.get('controller_type', 'N/A')} ({eq.get('mlm_role', 'N/A')})")
        print(f"  Gateway: {eq.get('gateway', 'N/A')}")
        print(f"  Network: {meta.get('network', 'N/A')}")

    print(f"\nTotal diffusers: {len(diffusers)}")
    return 0


def cmd_generate_scenario(args: argparse.Namespace) -> int:
    """Generate a hospital-specific alarm scenario."""
    from pathlib import Path
    from .generators.alarm_events import AlarmEventGenerator

    config = SimulationConfig(site_id=args.site)
    generator = AlarmEventGenerator(config)

    print(f"\nGenerating scenario: {args.scenario}")
    print("=" * 60)

    try:
        alarms = generator.generate_scenario_alarms(args.scenario)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = generator.OUTPUT_DIR / f"scenario_{args.scenario}_{timestamp_str}.json"

    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON
    with open(output_path, "w") as f:
        json.dump(alarms, f, indent=2)

    print(f"\nScenario: {args.scenario}")
    print(f"Site: {args.site}")
    print(f"Events: {len(alarms)}")
    print(f"\nOutput: {output_path}")

    # Print alarm sequence
    print("\nAlarm Sequence:")
    print("-" * 60)
    for alarm in alarms:
        ts = alarm.get("timestamp", "")[:19]  # Trim microseconds
        code = alarm.get("alarm_code", "")
        sev = alarm.get("severity", "")
        equip = alarm.get("equipment_id", "")
        status = ""
        if alarm.get("cleared"):
            status = " [CLEARED]"
        elif alarm.get("acknowledged"):
            status = " [ACK]"
        print(f"  {ts} | {sev:8} | {equip:20} | {code}{status}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="BMS Simulator - Generate mock BMS data for SIMBIOT pipeline testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full simulation with Siemens Desigo format
  python -m app.services.bms_simulator generate --site site-002 --vendor desigo

  # Export point list in Niagara format
  python -m app.services.bms_simulator export-points --vendor niagara

  # Generate 90 days of trends for a specific chiller
  python -m app.services.bms_simulator generate-trends --equipment S002-CHILLER-B1-001 --days 90

  # Generate with Rickard DALI format
  python -m app.services.bms_simulator generate --vendor rickard

  # List generated Rickard diffusers
  python -m app.services.bms_simulator list-diffusers
        """,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate complete BMS simulation")
    gen_parser.add_argument("--site", default="site-002", help="Site ID (default: site-002)")
    gen_parser.add_argument("--vendor", default="desigo", help="Vendor format: desigo, niagara, rickard (default: desigo)")
    gen_parser.add_argument("--days", type=int, default=30, help="Days of trend data (default: 30)")
    gen_parser.add_argument("--interval", type=int, default=15, help="Trend interval in minutes (default: 15)")
    gen_parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    gen_parser.add_argument("--degrade", help="Equipment IDs for degradation (comma-separated)")
    gen_parser.add_argument("--no-degradation", action="store_true", help="Disable degradation patterns")
    gen_parser.add_argument("--no-diffusers", action="store_true", help="Exclude Rickard diffusers")
    gen_parser.add_argument("--no-trends", action="store_true", help="Skip trend generation")
    gen_parser.add_argument("--no-alarms", action="store_true", help="Skip alarm generation")
    gen_parser.add_argument(
        "--climate",
        choices=["johannesburg", "durban", "cape_town", "pretoria"],
        default=None,
        help="Climate profile for weather-based variations"
    )
    gen_parser.add_argument(
        "--pattern",
        choices=["diurnal", "exponential", "stepped", "linear", "seasonal", "intermittent"],
        default=None,
        help="Degradation pattern type override"
    )
    gen_parser.set_defaults(func=cmd_generate)

    # export-points command
    export_parser = subparsers.add_parser("export-points", help="Export point list only")
    export_parser.add_argument("--site", default="site-002", help="Site ID (default: site-002)")
    export_parser.add_argument("--vendor", default="desigo", help="Vendor format (default: desigo)")
    export_parser.add_argument("--no-diffusers", action="store_true", help="Exclude Rickard diffusers")
    export_parser.set_defaults(func=cmd_export_points)

    # generate-trends command
    trends_parser = subparsers.add_parser("generate-trends", help="Generate trend data")
    trends_parser.add_argument("--site", default="site-002", help="Site ID (default: site-002)")
    trends_parser.add_argument("--equipment", help="Specific equipment ID (optional)")
    trends_parser.add_argument("--days", type=int, default=30, help="Days of trend data (default: 30)")
    trends_parser.add_argument("--interval", type=int, default=15, help="Trend interval in minutes (default: 15)")
    trends_parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    trends_parser.add_argument("--degrade", help="Equipment IDs for degradation (comma-separated)")
    trends_parser.add_argument("--no-degradation", action="store_true", help="Disable degradation patterns")
    trends_parser.add_argument("--no-diffusers", action="store_true", help="Exclude Rickard diffusers")
    trends_parser.add_argument(
        "--climate",
        choices=["johannesburg", "durban", "cape_town", "pretoria"],
        default=None,
        help="Climate profile for weather-based variations"
    )
    trends_parser.set_defaults(func=cmd_generate_trends)

    # generate-alarms command
    alarms_parser = subparsers.add_parser("generate-alarms", help="Generate alarm events")
    alarms_parser.add_argument("--site", default="site-002", help="Site ID (default: site-002)")
    alarms_parser.add_argument("--days", type=int, default=30, help="Days of simulation (default: 30)")
    alarms_parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    alarms_parser.add_argument("--degrade", help="Equipment IDs for degradation (comma-separated)")
    alarms_parser.add_argument("--no-degradation", action="store_true", help="Disable degradation patterns")
    alarms_parser.add_argument("--no-diffusers", action="store_true", help="Exclude Rickard diffusers")
    alarms_parser.set_defaults(func=cmd_generate_alarms)

    # list-diffusers command
    diff_parser = subparsers.add_parser("list-diffusers", help="List generated Rickard diffusers")
    diff_parser.add_argument("--site", default="site-002", help="Site ID (default: site-002)")
    diff_parser.set_defaults(func=cmd_list_diffusers)

    # generate-scenario command (hospital-specific alarm scenarios)
    scenario_parser = subparsers.add_parser("generate-scenario", help="Generate hospital alarm scenario")
    scenario_parser.add_argument(
        "--scenario",
        required=True,
        choices=[
            "cold-room-excursion",
            "chiller-cascade",
            "theatre-hepa-life",
            "generator-fuel",
            "icu-humidity",
        ],
        help="Scenario to generate"
    )
    scenario_parser.add_argument("--site", default="site-004", help="Site ID (default: site-004)")
    scenario_parser.add_argument("--output", help="Output JSON file path (optional)")
    scenario_parser.set_defaults(func=cmd_generate_scenario)

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
