"""
ServiceNow Integration Service — Read-Only Client.

Phase 138: ITSM integration for incident/work-order intelligence.
Starts idle and produces zero network calls until credentials are provided.

Uses httpx.AsyncClient (project standard — never requests).
All methods return graceful empty responses on failure, never raise.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

logger = logging.getLogger("sentinel.servicenow")


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class ServiceNowConfig:
    """Loads ServiceNow connection settings from environment variables."""

    domain: str = ""
    user: str = ""
    password: str = ""
    timeout: int = 30
    page_size: int = 100

    @classmethod
    def from_env(cls) -> "ServiceNowConfig":
        """Create config from SERVICENOW_* environment variables."""
        return cls(
            domain=os.getenv("SERVICENOW_DOMAIN", ""),
            user=os.getenv("SERVICENOW_USER", ""),
            password=os.getenv("SERVICENOW_PASSWORD", ""),
            timeout=int(os.getenv("SERVICENOW_TIMEOUT", "30")),
            page_size=int(os.getenv("SERVICENOW_PAGE_SIZE", "100")),
        )

    @property
    def is_configured(self) -> bool:
        """True when all required credentials are present."""
        return bool(self.domain and self.user and self.password)

    @property
    def base_url(self) -> str:
        """ServiceNow instance base URL."""
        domain = self.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        return domain


# =============================================================================
# Status Types
# =============================================================================


class ConnectionStatus(StrEnum):
    """ServiceNow connectivity state."""

    NOT_CONFIGURED = "not_configured"
    CONNECTED = "connected"
    AUTH_FAILED = "auth_failed"
    UNREACHABLE = "unreachable"
    ERROR = "error"


@dataclass
class ServiceNowStatus:
    """Represents current connection status with discovery results."""

    status: ConnectionStatus
    message: str = ""
    instance_name: str = ""
    discovered_tables: list[str] = field(default_factory=list)
    last_checked: str = ""


# =============================================================================
# Query Builder
# =============================================================================


class SysparmQuery:
    """Fluent builder for ServiceNow encoded query strings.

    Usage:
        query = (SysparmQuery()
            .field("priority").less_than("3")
            .and_field("state").equals("1")
            .order_by_desc("sys_created_on")
            .build())
    """

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._current_field: str = ""
        self._order: str = ""

    def field(self, name: str) -> "SysparmQuery":
        """Set the current field for the next condition."""
        self._current_field = name
        return self

    def and_field(self, name: str) -> "SysparmQuery":
        """Add AND connector and set next field."""
        self._current_field = name
        return self

    def or_field(self, name: str) -> "SysparmQuery":
        """Add OR connector and set next field."""
        if self._parts:
            self._parts.append("^OR")
        self._current_field = name
        return self

    def equals(self, value: str) -> "SysparmQuery":
        """Exact match."""
        self._parts.append(f"{self._current_field}={value}")
        return self

    def not_equals(self, value: str) -> "SysparmQuery":
        """Not equal."""
        self._parts.append(f"{self._current_field}!={value}")
        return self

    def less_than(self, value: str) -> "SysparmQuery":
        """Less than comparison."""
        self._parts.append(f"{self._current_field}<{value}")
        return self

    def greater_than(self, value: str) -> "SysparmQuery":
        """Greater than comparison."""
        self._parts.append(f"{self._current_field}>{value}")
        return self

    def contains(self, value: str) -> "SysparmQuery":
        """String contains."""
        self._parts.append(f"{self._current_field}LIKE{value}")
        return self

    def starts_with(self, value: str) -> "SysparmQuery":
        """String starts with."""
        self._parts.append(f"{self._current_field}STARTSWITH{value}")
        return self

    def is_empty(self) -> "SysparmQuery":
        """Field is empty."""
        self._parts.append(f"{self._current_field}ISEMPTY")
        return self

    def is_not_empty(self) -> "SysparmQuery":
        """Field is not empty."""
        self._parts.append(f"{self._current_field}ISNOTEMPTY")
        return self

    def in_list(self, values: list[str]) -> "SysparmQuery":
        """Field value in list."""
        self._parts.append(f"{self._current_field}IN{','.join(values)}")
        return self

    def order_by(self, field_name: str) -> "SysparmQuery":
        """Ascending sort."""
        self._order = f"ORDERBY{field_name}"
        return self

    def order_by_desc(self, field_name: str) -> "SysparmQuery":
        """Descending sort."""
        self._order = f"ORDERBYDESC{field_name}"
        return self

    def build(self) -> str:
        """Produce the encoded query string."""
        query = "^".join(self._parts)
        if self._order:
            query = f"{query}^{self._order}" if query else self._order
        return query


# =============================================================================
# Default Fields Per Table
# =============================================================================

DEFAULT_FIELDS: dict[str, str] = {
    "incident": "sys_id,number,short_description,description,priority,state,category,subcategory,"
    "assigned_to,assignment_group,opened_at,closed_at,resolved_at,impact,urgency",
    "sc_task": "sys_id,number,short_description,state,priority,assigned_to,assignment_group,"
    "opened_at,closed_at,work_start,work_end",
    "change_request": "sys_id,number,short_description,state,priority,type,risk,category,"
    "assigned_to,start_date,end_date",
    "cmdb_ci": "sys_id,name,sys_class_name,operational_status,install_status,location,"
    "asset_tag,serial_number,manufacturer",
    "cmn_location": "sys_id,name,full_name,street,city,state,country,latitude,longitude",
    "sys_user": "sys_id,user_name,first_name,last_name,email,active,department",
    "sys_user_group": "sys_id,name,description,manager,email,active",
    "fm_expense_line": "sys_id,number,cost,cost_center,gl_account,state",
    "wm_order": "sys_id,number,short_description,state,priority,assigned_to,location,opened_at,closed_at",
    "alm_asset": "sys_id,display_name,asset_tag,serial_number,model,install_status,assigned_to,location",
    "pm_schedule": "sys_id,name,active,frequency,next_run_date,last_run_date",
    "sn_si_incident": "sys_id,number,short_description,state,priority",
    "kb_knowledge": "sys_id,number,short_description,text,topic,category",
    "sla_condition": "sys_id,name,target,percentage,stage",
    "contract": "sys_id,number,short_description,state,starts,ends,vendor",
}

# FM-relevant tables to discover on connection check
FM_TABLES: list[str] = [
    "incident",
    "sc_task",
    "change_request",
    "cmdb_ci",
    "cmn_location",
    "sys_user",
    "sys_user_group",
    "fm_expense_line",
    "wm_order",
    "alm_asset",
    "pm_schedule",
    "sn_si_incident",
    "kb_knowledge",
    "sla_condition",
    "contract",
]


# =============================================================================
# Service
# =============================================================================


class ServiceNowService:
    """Read-only ServiceNow REST client for SENTINEL.

    Connects to a ServiceNow instance via Table API and Aggregate API.
    Designed for FM intelligence — incidents, work orders, assets, and CMDB.
    """

    def __init__(self) -> None:
        self.config = ServiceNowConfig.from_env()
        self._client: httpx.AsyncClient | None = None
        self._status = ServiceNowStatus(
            status=ConnectionStatus.NOT_CONFIGURED if not self.config.is_configured else ConnectionStatus.ERROR,
            message="Credentials not provided" if not self.config.is_configured else "Not yet connected",
        )
        self._schema_cache: dict[str, list[dict[str, Any]]] = {}

    # ---- Properties --------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """True when ServiceNow credentials are available."""
        return self.config.is_configured

    @property
    def status(self) -> ServiceNowStatus:
        """Current connection status."""
        return self._status

    # ---- HTTP Client -------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily initialise httpx client with Basic auth."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                auth=(self.config.user, self.config.password),
                timeout=httpx.Timeout(self.config.timeout),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    # ---- Connection Check --------------------------------------------------

    async def check_connection(self) -> ServiceNowStatus:
        """Test connectivity, authenticate, and discover available tables."""
        if not self.is_configured:
            self._status = ServiceNowStatus(
                status=ConnectionStatus.NOT_CONFIGURED,
                message="ServiceNow credentials not configured. "
                "Set SERVICENOW_DOMAIN, SERVICENOW_USER, SERVICENOW_PASSWORD.",
            )
            return self._status

        try:
            client = self._get_client()
            # Quick auth test: fetch 1 record from sys_properties
            response = await client.get(
                "/api/now/table/sys_properties",
                params={"sysparm_limit": "1", "sysparm_fields": "sys_id"},
            )

            if response.status_code == 401:
                self._status = ServiceNowStatus(
                    status=ConnectionStatus.AUTH_FAILED,
                    message="Authentication failed. Check SERVICENOW_USER and SERVICENOW_PASSWORD.",
                )
                return self._status

            if response.status_code >= 400:
                self._status = ServiceNowStatus(
                    status=ConnectionStatus.ERROR,
                    message=f"ServiceNow returned HTTP {response.status_code}",
                )
                return self._status

            # Discover FM-relevant tables
            discovered = await self._discover_tables()
            from datetime import datetime

            self._status = ServiceNowStatus(
                status=ConnectionStatus.CONNECTED,
                message=f"Connected — {len(discovered)} FM tables available",
                instance_name=self.config.domain,
                discovered_tables=discovered,
                last_checked=datetime.utcnow().isoformat() + "Z",
            )
            return self._status

        except httpx.ConnectError:
            self._status = ServiceNowStatus(
                status=ConnectionStatus.UNREACHABLE,
                message=f"Cannot reach {self.config.domain}. Check network and domain.",
            )
            return self._status
        except Exception as e:
            logger.error("ServiceNow connection check failed: %s", e)
            self._status = ServiceNowStatus(
                status=ConnectionStatus.ERROR,
                message=f"Connection check failed: {type(e).__name__}",
            )
            return self._status

    async def _discover_tables(self) -> list[str]:
        """Probe FM_TABLES in parallel batches of 5 to find which exist."""
        discovered: list[str] = []
        batch_size = 5

        for i in range(0, len(FM_TABLES), batch_size):
            batch = FM_TABLES[i : i + batch_size]
            results = await asyncio.gather(
                *(self._probe_table(table) for table in batch),
                return_exceptions=True,
            )
            for table, result in zip(batch, results, strict=False):
                if result is True:
                    discovered.append(table)

        return discovered

    async def _probe_table(self, table: str) -> bool:
        """Return True if a table exists and is accessible."""
        try:
            client = self._get_client()
            response = await client.get(
                f"/api/now/table/{table}",
                params={"sysparm_limit": "1", "sysparm_fields": "sys_id"},
            )
            return response.status_code == 200
        except Exception:
            return False

    # ---- Generic Table Query -----------------------------------------------

    async def query_table(
        self,
        table: str,
        query: str = "",
        fields: str = "",
        limit: int = 0,
        offset: int = 0,
        order_by: str = "",
    ) -> dict[str, Any]:
        """Execute a read-only GET on the Table API.

        Args:
            table: ServiceNow table name
            query: Encoded query string (use SysparmQuery.build())
            fields: Comma-separated field names (defaults to DEFAULT_FIELDS)
            limit: Max records (0 = use config page_size)
            offset: Pagination offset
            order_by: Sort field (prefix with '-' for descending)

        Returns:
            {"result": [...], "count": N} or empty response on error
        """
        if not self.is_configured:
            return self._empty_response("ServiceNow not configured")

        try:
            client = self._get_client()
            params: dict[str, str] = {
                "sysparm_limit": str(limit or self.config.page_size),
                "sysparm_display_value": "true",
            }

            if query:
                params["sysparm_query"] = query
            if fields:
                params["sysparm_fields"] = fields
            elif table in DEFAULT_FIELDS:
                params["sysparm_fields"] = DEFAULT_FIELDS[table]
            if offset:
                params["sysparm_offset"] = str(offset)
            if order_by:
                if order_by.startswith("-"):
                    params["sysparm_query"] = (f"{params.get('sysparm_query', '')}^ORDERBYDESC{order_by[1:]}").lstrip(
                        "^"
                    )
                else:
                    params["sysparm_query"] = (f"{params.get('sysparm_query', '')}^ORDERBY{order_by}").lstrip("^")

            response = await client.get(f"/api/now/table/{table}", params=params)

            if response.status_code != 200:
                logger.warning("ServiceNow table query failed: %s %d", table, response.status_code)
                return self._empty_response(f"HTTP {response.status_code}")

            data = response.json()
            result = data.get("result", [])
            total_count = int(response.headers.get("X-Total-Count", len(result)))

            return {"result": result, "count": total_count}

        except Exception as e:
            logger.error("ServiceNow query_table(%s) error: %s", table, e)
            return self._empty_response(str(e))

    # ---- Aggregate API -----------------------------------------------------

    async def get_aggregate(
        self,
        table: str,
        query: str = "",
        group_by: str = "",
        agg_fields: str = "",
    ) -> dict[str, Any]:
        """Stats API for counts and breakdowns.

        Args:
            table: ServiceNow table name
            query: Encoded query string
            group_by: Comma-separated fields to group by
            agg_fields: Fields to aggregate (default: COUNT)

        Returns:
            {"result": [...]} or empty response on error
        """
        if not self.is_configured:
            return self._empty_response("ServiceNow not configured")

        try:
            client = self._get_client()
            params: dict[str, str] = {"sysparm_count": "true"}

            if query:
                params["sysparm_query"] = query
            if group_by:
                params["sysparm_group_by"] = group_by
            if agg_fields:
                params["sysparm_avg_fields"] = agg_fields

            response = await client.get(f"/api/now/stats/{table}", params=params)

            if response.status_code != 200:
                logger.warning("ServiceNow aggregate failed: %s %d", table, response.status_code)
                return self._empty_response(f"HTTP {response.status_code}")

            return response.json()

        except Exception as e:
            logger.error("ServiceNow get_aggregate(%s) error: %s", table, e)
            return self._empty_response(str(e))

    # ---- Schema Inspection -------------------------------------------------

    async def get_table_schema(self, table: str) -> dict[str, Any]:
        """Inspect table columns via sys_dictionary. Results are session-cached.

        Args:
            table: ServiceNow table name

        Returns:
            {"result": [column definitions]} or empty response on error
        """
        if not self.is_configured:
            return self._empty_response("ServiceNow not configured")

        # Return cached schema if available
        if table in self._schema_cache:
            return {"result": self._schema_cache[table]}

        try:
            client = self._get_client()
            query = f"name={table}^elementISNOTEMPTY"
            params = {
                "sysparm_query": query,
                "sysparm_fields": "element,column_label,internal_type,max_length,mandatory,reference",
                "sysparm_limit": "500",
            }

            response = await client.get("/api/now/table/sys_dictionary", params=params)

            if response.status_code != 200:
                return self._empty_response(f"HTTP {response.status_code}")

            data = response.json()
            columns = data.get("result", [])
            self._schema_cache[table] = columns
            return {"result": columns}

        except Exception as e:
            logger.error("ServiceNow get_table_schema(%s) error: %s", table, e)
            return self._empty_response(str(e))

    # ---- Record History / Audit Trail --------------------------------------

    async def get_record_history(self, table: str, sys_id: str) -> dict[str, Any]:
        """Fetch audit trail for a specific record.

        Args:
            table: Source table name
            sys_id: Record sys_id

        Returns:
            {"result": [history entries]} or empty response on error
        """
        if not self.is_configured:
            return self._empty_response("ServiceNow not configured")

        try:
            client = self._get_client()
            query = f"tablename={table}^documentkey={sys_id}"
            params = {
                "sysparm_query": query + "^ORDERBYDESCsys_created_on",
                "sysparm_fields": "sys_id,fieldname,oldvalue,newvalue,sys_created_on,user",
                "sysparm_limit": "100",
            }

            response = await client.get("/api/now/table/sys_audit", params=params)

            if response.status_code != 200:
                return self._empty_response(f"HTTP {response.status_code}")

            return response.json()

        except Exception as e:
            logger.error("ServiceNow get_record_history(%s/%s) error: %s", table, sys_id, e)
            return self._empty_response(str(e))

    # ---- Convenience Methods -----------------------------------------------

    async def get_open_incidents(
        self,
        priority: int | None = None,
        category: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch open incidents with optional filters.

        Args:
            priority: Filter by priority (1=Critical, 2=High, 3=Medium, 4=Low)
            category: Filter by category
            limit: Max records

        Returns:
            Query result dict
        """
        qb = SysparmQuery().field("state").not_equals("6").and_field("state").not_equals("7")

        if priority is not None:
            qb.and_field("priority").equals(str(priority))
        if category:
            qb.and_field("category").equals(category)

        qb.order_by_desc("sys_created_on")

        return await self.query_table(
            table="incident",
            query=qb.build(),
            limit=limit,
        )

    async def get_work_orders(
        self,
        state: str | None = None,
        priority: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch work orders / service tasks.

        Args:
            state: Filter by state value
            priority: Filter by priority
            limit: Max records

        Returns:
            Query result dict
        """
        qb = SysparmQuery()
        has_condition = False

        if state:
            qb.field("state").equals(state)
            has_condition = True
        if priority is not None:
            if has_condition:
                qb.and_field("priority").equals(str(priority))
            else:
                qb.field("priority").equals(str(priority))

        qb.order_by_desc("opened_at")

        return await self.query_table(
            table="wm_order",
            query=qb.build(),
            limit=limit,
        )

    async def get_incident_summary(self) -> dict[str, Any]:
        """Aggregate incident counts by priority and state.

        Returns:
            {"by_priority": {...}, "by_state": {...}, "total_open": N}
        """
        if not self.is_configured:
            return self._empty_response("ServiceNow not configured")

        try:
            by_priority = await self.get_aggregate(
                table="incident",
                query="stateNOT IN6,7",
                group_by="priority",
            )
            by_state = await self.get_aggregate(
                table="incident",
                query="stateNOT IN6,7",
                group_by="state",
            )

            priority_result = by_priority.get("result", [])
            total_open = sum(int(r.get("stats", {}).get("count", 0)) for r in priority_result)

            return {
                "by_priority": priority_result,
                "by_state": by_state.get("result", []),
                "total_open": total_open,
            }
        except Exception as e:
            logger.error("ServiceNow get_incident_summary error: %s", e)
            return self._empty_response(str(e))

    # ---- Helpers -----------------------------------------------------------

    @staticmethod
    def _empty_response(reason: str = "") -> dict[str, Any]:
        """Graceful empty result — never throws."""
        return {"result": [], "count": 0, "error": reason}

    # ---- Lifecycle ---------------------------------------------------------

    async def close(self) -> None:
        """Close the httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("ServiceNow client closed")


# =============================================================================
# Singleton
# =============================================================================

_service: ServiceNowService | None = None


def get_servicenow_service() -> ServiceNowService:
    """Return the module-level ServiceNow service singleton."""
    global _service
    if _service is None:
        _service = ServiceNowService()
    return _service


async def shutdown_servicenow_service() -> None:
    """Graceful cleanup — called from app shutdown handler."""
    global _service
    if _service is not None:
        await _service.close()
        _service = None
        logger.info("ServiceNow service shut down")
