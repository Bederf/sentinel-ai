#!/usr/bin/env python3
"""
SENTINEL Health Monitor

Monitors building equipment health, alerts, and safety status.
Can run as a standalone script or integration point for external monitoring systems.

Usage:
    python scripts/health_monitor.py                    # Monitor all sites
    python scripts/health_monitor.py --site S002        # Monitor specific site
    python scripts/health_monitor.py --critical-only    # Show critical items only
    python scripts/health_monitor.py --json             # Output as JSON
    python scripts/health_monitor.py --log-file monitor.log  # Write to file

JWT Authentication (for individual equipment details):
    python scripts/health_monitor.py --login admin      # Login as admin (prompts for password)
    python scripts/health_monitor.py --login admin --password secret123 --critical-only

Authentication Priority:
    1. JWT token (--login) - Access individual equipment ✓
    2. SUPABASE_SERVICE_ROLE_KEY (.env) - Backend access (site summaries only)
    3. API_KEY (.env) - Limited access (site summaries only)
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

import os

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:9095")
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
API_KEY = os.getenv("API_KEY")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class SentinelHealthMonitor:
    """Monitor SENTINEL BMS equipment health and alerts."""

    def __init__(
        self,
        api_url: str = API_URL,
        service_role_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize health monitor.

        Args:
            api_url: Backend API URL
            service_role_key: Supabase service role key for backend-to-backend auth
            username: Username for JWT login (if service role unavailable)
            password: Password for JWT login (if service role unavailable)
        """
        self.api_url = api_url.rstrip("/")
        self.service_role_key = service_role_key or SERVICE_ROLE_KEY
        self.username = username
        self.password = password
        self.jwt_token: Optional[str] = None
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        headers = {"Content-Type": "application/json"}

        if self.jwt_token:
            # Use JWT token (highest priority - authenticated user)
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        elif self.service_role_key:
            # Use service role key (backend-to-backend, no individual equipment access)
            headers["Authorization"] = f"Bearer {self.service_role_key}"
        elif API_KEY:
            # Use API key (limited access - site summaries only)
            headers["X-API-Key"] = API_KEY

        return headers

    async def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Authenticate with username/password to get JWT token.

        Args:
            username: Username (uses self.username if not provided)
            password: Password (uses self.password if not provided)

        Returns:
            True if login successful, False otherwise
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        username = username or self.username
        password = password or self.password

        if not username or not password:
            logger.error("Username and password required for JWT login")
            return False

        try:
            url = f"{self.api_url}/api/auth/login"
            payload = {"username": username, "password": password}

            logger.info(f"Attempting login for user: {username}")
            response = await self.client.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                self.jwt_token = data.get("access_token")
                logger.info(f"✓ Login successful - JWT token obtained")
                return True
            elif response.status_code == 401:
                logger.error("Login failed - invalid username/password")
                return False
            else:
                logger.error(f"Login error ({response.status_code}): {response.text}")
                return False

        except httpx.HTTPError as e:
            logger.error(f"Login request failed: {e}")
            return False

    async def get_site_summary(self, site_code: Optional[str] = None) -> List[Dict]:
        """
        Fetch site summary with alerts and health overview.

        Args:
            site_code: Optional filter (e.g., "S002")

        Returns:
            List of site summaries
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        try:
            url = f"{self.api_url}/api/sites"
            if site_code:
                url += f"?code={site_code}"

            logger.info(f"Fetching site summary from {url}")
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()

            data = response.json()
            sites = data.get("sites", [])
            logger.info(f"Retrieved {len(sites)} site(s)")
            return sites

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch site summary: {e}")
            raise

    async def get_equipment_details(self, equipment_id: str) -> Dict[str, Any]:
        """
        Fetch individual equipment details.

        Args:
            equipment_id: Equipment UUID or code

        Returns:
            Equipment details including health_score, status, alerts
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        try:
            url = f"{self.api_url}/api/equipment/{equipment_id}"
            logger.debug(f"Fetching equipment from {url}")
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()

            return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning(
                    f"Authentication failed for {equipment_id}. "
                    "Try:\n"
                    "  1. Set SUPABASE_SERVICE_ROLE_KEY in .env (backend auth), OR\n"
                    "  2. Use --login with --password to get JWT token (user auth)"
                )
            elif e.response.status_code == 404:
                logger.warning(f"Equipment {equipment_id} not found")
            else:
                logger.error(f"Failed to fetch equipment {equipment_id}: {e}")
            raise

    async def get_alerts_by_site(self, site_id: str, limit: int = 50) -> List[Dict]:
        """
        Fetch alerts for a site.

        Args:
            site_id: Site UUID
            limit: Maximum alerts to retrieve

        Returns:
            List of alerts
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        try:
            url = f"{self.api_url}/api/alerts?site_id={site_id}&limit={limit}"
            logger.debug(f"Fetching alerts from {url}")
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()

            data = response.json()
            alerts = data.get("alerts", [])
            logger.info(f"Retrieved {len(alerts)} alert(s) for site {site_id}")
            return alerts

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch alerts: {e}")
            return []

    async def monitor_health(
        self,
        site_code: Optional[str] = None,
        critical_only: bool = False,
        output_format: str = "text",
    ) -> Dict[str, Any]:
        """
        Comprehensive health monitoring.

        Args:
            site_code: Optional site filter (e.g., "S002")
            critical_only: Only show critical/warning items
            output_format: "text" or "json"

        Returns:
            Monitoring results as dict
        """
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "sites": [],
            "summary": {"total_critical": 0, "total_warning": 0, "total_healthy": 0},
        }

        try:
            # Fetch site summaries
            sites = await self.get_site_summary(site_code)

            for site in sites:
                site_result = {
                    "code": site.get("code"),
                    "name": site.get("name"),
                    "generators": site.get("generator_count", 0),
                    "equipment": site.get("equipment_count", 0),
                    "alerts": {
                        "critical": site.get("critical_alerts", 0),
                        "warning": site.get("warning_alerts", 0),
                    },
                    "safety_status": {
                        "in_alarm": site.get("equipment_in_alarm_state", 0),
                        "in_warning": site.get("equipment_in_warning_state", 0),
                    },
                    "equipment_details": [],
                }

                # Update summary
                results["summary"]["total_critical"] += site.get("critical_alerts", 0)
                results["summary"]["total_warning"] += site.get("warning_alerts", 0)
                results["summary"]["total_healthy"] += (
                    site.get("equipment_count", 0)
                    - site.get("critical_alerts", 0)
                    - site.get("warning_alerts", 0)
                )

                # Optionally fetch detailed equipment if critical only
                if critical_only and site.get("critical_alerts", 0) > 0:
                    logger.info(
                        f"Fetching critical equipment for site {site.get('code')}"
                    )
                    site_id = site.get("id")
                    if site_id:
                        alerts = await self.get_alerts_by_site(site_id)

                        # Get unique critical/warning equipment
                        critical_equipment = set()
                        for alert in alerts:
                            if alert.get("severity") in ("critical", "warning"):
                                eq_id = alert.get("equipment_id")
                                if eq_id and eq_id not in critical_equipment:
                                    critical_equipment.add(eq_id)

                        # Fetch details for each critical equipment
                        for eq_id in list(critical_equipment)[:10]:  # Limit to 10
                            try:
                                details = await self.get_equipment_details(eq_id)
                                site_result["equipment_details"].append(
                                    {
                                        "code": details.get("code"),
                                        "name": details.get("name"),
                                        "type": details.get("type"),
                                        "health_score": details.get("health_score"),
                                        "status": details.get("status"),
                                    }
                                )
                            except httpx.HTTPError:
                                pass  # Continue on error

                results["sites"].append(site_result)

            return results

        except Exception as e:
            logger.error(f"Health monitoring failed: {e}")
            results["error"] = str(e)
            return results


async def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="SENTINEL BMS Health Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/health_monitor.py                    # Monitor all sites
  python scripts/health_monitor.py --site S002        # Monitor site S002
  python scripts/health_monitor.py --critical-only    # Critical items only
  python scripts/health_monitor.py --json             # JSON output
  python scripts/health_monitor.py --log-file out.log # Log to file
        """,
    )

    parser.add_argument("--site", help="Filter by site code (e.g., S002)")
    parser.add_argument(
        "--critical-only", action="store_true", help="Show only critical/warning items"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON instead of text"
    )
    parser.add_argument("--log-file", help="Write output to file instead of stdout")
    parser.add_argument(
        "--api-url", default=API_URL, help="Backend API URL (default: $API_URL)"
    )
    parser.add_argument(
        "--login",
        metavar="USERNAME",
        help="Login with username (will prompt for password)",
    )
    parser.add_argument(
        "--password",
        help="Password (use with --login)",
    )

    args = parser.parse_args()

    # Setup file logging if requested
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prepare authentication
    username = args.login
    password = args.password

    # If login requested without password, prompt for it
    if username and not password:
        import getpass
        password = getpass.getpass(f"Password for {username}: ")

    # Run health monitor
    async with SentinelHealthMonitor(
        api_url=args.api_url,
        service_role_key=SERVICE_ROLE_KEY,
        username=username,
        password=password,
    ) as monitor:
        # Attempt JWT login if credentials provided
        if username and password:
            login_success = await monitor.login(username, password)
            if not login_success:
                logger.error("Failed to authenticate. Continuing with API key fallback...")
                # Continue anyway - might still have API key access for site summaries

        results = await monitor.monitor_health(
            site_code=args.site,
            critical_only=args.critical_only,
            output_format="json" if args.json else "text",
        )

        # Format output
        if args.json:
            output = json.dumps(results, indent=2)
        else:
            output = _format_text_output(results)

        # Write output
        if args.log_file:
            with open(args.log_file, "a") as f:
                f.write(output + "\n")
            logger.info(f"Results written to {args.log_file}")
        else:
            print(output)

        # Exit with error code if critical items found
        if results.get("summary", {}).get("total_critical", 0) > 0:
            sys.exit(1)


def _format_text_output(results: Dict[str, Any]) -> str:
    """Format monitoring results as human-readable text."""
    lines = [
        f"\n{'='*70}",
        f"SENTINEL Health Monitor - {results.get('timestamp', 'N/A')}",
        f"{'='*70}",
        "",
        "Summary:",
        f"  Critical: {results['summary'].get('total_critical', 0):>3}",
        f"  Warning:  {results['summary'].get('total_warning', 0):>3}",
        f"  Healthy:  {results['summary'].get('total_healthy', 0):>3}",
        "",
    ]

    for site in results.get("sites", []):
        lines.extend([
            f"Site: {site['code']} - {site['name']}",
            f"  Equipment: {site['equipment']} | Generators: {site['generators']}",
            f"  Alerts: {site['alerts']['critical']} critical, {site['alerts']['warning']} warning",
            f"  Safety: {site['safety_status']['in_alarm']} in alarm, {site['safety_status']['in_warning']} in warning",
        ])

        if site.get("equipment_details"):
            lines.append("  Critical Equipment:")
            for eq in site["equipment_details"]:
                lines.append(
                    f"    - {eq['code']} ({eq['type']}): "
                    f"Health={eq['health_score']:.0f}% Status={eq['status']}"
                )
        lines.append("")

    if results.get("error"):
        lines.extend(["Error:", f"  {results['error']}", ""])

    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())
