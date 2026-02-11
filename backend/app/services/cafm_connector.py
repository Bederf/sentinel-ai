from typing import Dict, List, Optional
from enum import Enum
import asyncio
from datetime import datetime
import httpx
import logging

logger = logging.getLogger(__name__)


class CAFMSystem(Enum):
    ARCHIBUS = "archibus"
    PLANON = "planon"
    MAXIMO = "maximo"


class CAFMConnector:
    """Connector for integrating with CAFM systems (Archibus, Planon, Maximo)"""

    def __init__(self, system: CAFMSystem, config: Dict):
        self.system = system
        self.config = config
        self.client = None  # Initialized based on system
        self.session: Optional[httpx.AsyncClient] = None

    async def connect(self) -> bool:
        """Establish connection to CAFM system"""
        try:
            if self.system == CAFMSystem.ARCHIBUS:
                await self._connect_archibus()
            elif self.system == CAFMSystem.PLANON:
                await self._connect_planon()
            elif self.system == CAFMSystem.MAXIMO:
                await self._connect_maximo()
            logger.info(f"Successfully connected to {self.system.value}")
            return True
        except Exception as e:
            logger.error(f"CAFM connection failed: {e}")
            return False

    async def _connect_archibus(self) -> None:
        """Connect to Archibus REST API"""
        api_url = self.config.get("api_url", "")
        username = self.config.get("username", "")
        password = self.config.get("password", "")

        if not api_url:
            raise ValueError("Archibus API URL not configured")

        # Create session with basic auth
        auth = (username, password) if username and password else None
        self.session = httpx.AsyncClient(
            base_url=api_url,
            auth=auth,
            timeout=30.0
        )

        # Test connection
        try:
            response = await self.session.get("/api/v1/system/info")
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ValueError(f"Archibus connection test failed: {e}")

    async def _connect_planon(self) -> None:
        """Connect to Planon REST API"""
        api_url = self.config.get("api_url", "")
        api_key = self.config.get("api_key", "")

        if not api_url or not api_key:
            raise ValueError("Planon API URL and API key required")

        # Create session with API key header
        self.session = httpx.AsyncClient(
            base_url=api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=30.0
        )

        # Test connection
        try:
            response = await self.session.get("/api/v1/info")
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ValueError(f"Planon connection test failed: {e}")

    async def _connect_maximo(self) -> None:
        """Connect to Maximo REST API"""
        api_url = self.config.get("api_url", "")
        username = self.config.get("username", "")
        password = self.config.get("password", "")

        if not api_url:
            raise ValueError("Maximo API URL not configured")

        # Create session with basic auth
        auth = (username, password) if username and password else None
        self.session = httpx.AsyncClient(
            base_url=api_url,
            auth=auth,
            timeout=30.0
        )

        # Test connection
        try:
            response = await self.session.get("/api/v1/system")
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise ValueError(f"Maximo connection test failed: {e}")

    async def sync_work_orders(self, since: Optional[datetime] = None) -> List[Dict]:
        """
        Sync work orders from CAFM to SENTINEL.

        Pulls new/updated work orders from CAFM.
        Returns list of work orders in SENTINEL format.
        """
        if not self.session:
            logger.warning("CAFM session not initialized")
            return []

        try:
            if self.system == CAFMSystem.ARCHIBUS:
                return await self._fetch_archibus_work_orders(since)
            elif self.system == CAFMSystem.PLANON:
                return await self._fetch_planon_work_orders(since)
            elif self.system == CAFMSystem.MAXIMO:
                return await self._fetch_maximo_work_orders(since)
        except Exception as e:
            logger.error(f"Failed to sync work orders from {self.system.value}: {e}")

        return []

    async def _fetch_archibus_work_orders(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch work orders from Archibus"""
        try:
            params = {}
            if since:
                params["filter"] = f"lastModified >= '{since.isoformat()}'"

            response = await self.session.get("/api/v1/workorders", params=params)
            response.raise_for_status()

            work_orders = response.json().get("data", [])
            return [self._transform_archibus_wo(wo) for wo in work_orders]
        except Exception as e:
            logger.error(f"Archibus work order fetch failed: {e}")
            return []

    async def _fetch_planon_work_orders(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch work orders from Planon"""
        try:
            params = {"include": "details"}
            if since:
                params["filter"] = f"createdDate >= {since.timestamp()}"

            response = await self.session.get("/api/v1/maintenance/work-orders", params=params)
            response.raise_for_status()

            work_orders = response.json().get("items", [])
            return [self._transform_planon_wo(wo) for wo in work_orders]
        except Exception as e:
            logger.error(f"Planon work order fetch failed: {e}")
            return []

    async def _fetch_maximo_work_orders(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch work orders from Maximo"""
        try:
            params = {"oslc.select": "*"}
            if since:
                params["oslc.where"] = f"lastmoddate>={since.isoformat()}"

            response = await self.session.get("/api/v1/workorder", params=params)
            response.raise_for_status()

            work_orders = response.json().get("rdfs:member", [])
            return [self._transform_maximo_wo(wo) for wo in work_orders]
        except Exception as e:
            logger.error(f"Maximo work order fetch failed: {e}")
            return []

    async def push_work_order_to_cafm(self, order: Dict) -> Dict:
        """
        Push work order created in SENTINEL to CAFM system.

        Creates work order in CAFM with all details.
        Returns CAFM work order ID.
        """
        if not self.session:
            logger.warning("CAFM session not initialized")
            return {}

        try:
            if self.system == CAFMSystem.ARCHIBUS:
                return await self._create_archibus_wo(order)
            elif self.system == CAFMSystem.PLANON:
                return await self._create_planon_wo(order)
            elif self.system == CAFMSystem.MAXIMO:
                return await self._create_maximo_wo(order)
        except Exception as e:
            logger.error(f"Failed to push work order to {self.system.value}: {e}")

        return {}

    async def _create_archibus_wo(self, order: Dict) -> Dict:
        """Create work order in Archibus"""
        try:
            payload = {
                "title": order.get("title", ""),
                "description": order.get("description", ""),
                "priority": order.get("priority", "MEDIUM"),
                "assignedTo": order.get("assigned_to", ""),
                "equipment_code": order.get("equipment_code", ""),
                "expectedHours": order.get("estimated_hours", 0),
            }

            response = await self.session.post("/api/v1/workorders", json=payload)
            response.raise_for_status()

            result = response.json()
            return {
                "cafm_id": result.get("id", ""),
                "status": "created",
                "cafm_system": "archibus"
            }
        except Exception as e:
            logger.error(f"Archibus work order creation failed: {e}")
            return {}

    async def _create_planon_wo(self, order: Dict) -> Dict:
        """Create work order in Planon"""
        try:
            payload = {
                "title": order.get("title", ""),
                "description": order.get("description", ""),
                "priority": order.get("priority", "medium"),
                "assignee": order.get("assigned_to", ""),
                "assetId": order.get("equipment_code", ""),
                "estimatedDuration": order.get("estimated_hours", 0),
            }

            response = await self.session.post("/api/v1/maintenance/work-orders", json=payload)
            response.raise_for_status()

            result = response.json()
            return {
                "cafm_id": result.get("id", ""),
                "status": "created",
                "cafm_system": "planon"
            }
        except Exception as e:
            logger.error(f"Planon work order creation failed: {e}")
            return {}

    async def _create_maximo_wo(self, order: Dict) -> Dict:
        """Create work order in Maximo"""
        try:
            payload = {
                "wonum": order.get("number", ""),
                "description": order.get("description", ""),
                "priority": order.get("priority", "3"),
                "assigneename": order.get("assigned_to", ""),
                "assetnum": order.get("equipment_code", ""),
                "estdur": order.get("estimated_hours", 0),
            }

            response = await self.session.post("/api/v1/workorder", json=payload)
            response.raise_for_status()

            result = response.json()
            return {
                "cafm_id": result.get("wonum", ""),
                "status": "created",
                "cafm_system": "maximo"
            }
        except Exception as e:
            logger.error(f"Maximo work order creation failed: {e}")
            return {}

    async def sync_assets(self, site_id: str) -> List[Dict]:
        """
        Sync asset catalog from CAFM to SENTINEL.

        Pulls asset register for site.
        Returns list of assets in SENTINEL format.
        """
        if not self.session:
            logger.warning("CAFM session not initialized")
            return []

        try:
            if self.system == CAFMSystem.ARCHIBUS:
                return await self._fetch_archibus_assets(site_id)
            elif self.system == CAFMSystem.PLANON:
                return await self._fetch_planon_assets(site_id)
            elif self.system == CAFMSystem.MAXIMO:
                return await self._fetch_maximo_assets(site_id)
        except Exception as e:
            logger.error(f"Failed to sync assets from {self.system.value}: {e}")

        return []

    async def _fetch_archibus_assets(self, site_id: str) -> List[Dict]:
        """Fetch assets from Archibus"""
        try:
            response = await self.session.get(
                "/api/v1/assets",
                params={"filter": f"building='{site_id}'"}
            )
            response.raise_for_status()

            assets = response.json().get("data", [])
            return [self._transform_archibus_asset(asset) for asset in assets]
        except Exception as e:
            logger.error(f"Archibus asset fetch failed: {e}")
            return []

    async def _fetch_planon_assets(self, site_id: str) -> List[Dict]:
        """Fetch assets from Planon"""
        try:
            response = await self.session.get(
                "/api/v1/assets",
                params={"site": site_id}
            )
            response.raise_for_status()

            assets = response.json().get("items", [])
            return [self._transform_planon_asset(asset) for asset in assets]
        except Exception as e:
            logger.error(f"Planon asset fetch failed: {e}")
            return []

    async def _fetch_maximo_assets(self, site_id: str) -> List[Dict]:
        """Fetch assets from Maximo"""
        try:
            response = await self.session.get(
                "/api/v1/asset",
                params={"oslc.where": f"siteid='{site_id}'"}
            )
            response.raise_for_status()

            assets = response.json().get("rdfs:member", [])
            return [self._transform_maximo_asset(asset) for asset in assets]
        except Exception as e:
            logger.error(f"Maximo asset fetch failed: {e}")
            return []

    async def update_cafm_status(self, order_id: str, status: str, resolution: str) -> Dict:
        """
        Update work order status in CAFM system.

        Called when technician completes or updates job.
        Returns confirmation.
        """
        if not self.session:
            logger.warning("CAFM session not initialized")
            return {}

        try:
            if self.system == CAFMSystem.ARCHIBUS:
                return await self._update_archibus_status(order_id, status, resolution)
            elif self.system == CAFMSystem.PLANON:
                return await self._update_planon_status(order_id, status, resolution)
            elif self.system == CAFMSystem.MAXIMO:
                return await self._update_maximo_status(order_id, status, resolution)
        except Exception as e:
            logger.error(f"Failed to update status in {self.system.value}: {e}")

        return {}

    async def _update_archibus_status(self, order_id: str, status: str, resolution: str) -> Dict:
        """Update work order status in Archibus"""
        try:
            payload = {
                "status": status,
                "resolution": resolution,
                "completedDate": datetime.now().isoformat()
            }

            response = await self.session.put(f"/api/v1/workorders/{order_id}", json=payload)
            response.raise_for_status()

            return {
                "success": True,
                "order_id": order_id,
                "cafm_system": "archibus",
                "status": status
            }
        except Exception as e:
            logger.error(f"Archibus status update failed: {e}")
            return {}

    async def _update_planon_status(self, order_id: str, status: str, resolution: str) -> Dict:
        """Update work order status in Planon"""
        try:
            payload = {
                "status": status,
                "resolution": resolution,
                "completionDate": datetime.now().isoformat()
            }

            response = await self.session.put(
                f"/api/v1/maintenance/work-orders/{order_id}",
                json=payload
            )
            response.raise_for_status()

            return {
                "success": True,
                "order_id": order_id,
                "cafm_system": "planon",
                "status": status
            }
        except Exception as e:
            logger.error(f"Planon status update failed: {e}")
            return {}

    async def _update_maximo_status(self, order_id: str, status: str, resolution: str) -> Dict:
        """Update work order status in Maximo"""
        try:
            payload = {
                "status": status,
                "description": resolution,
                "completiondate": datetime.now().isoformat()
            }

            response = await self.session.put(f"/api/v1/workorder/{order_id}", json=payload)
            response.raise_for_status()

            return {
                "success": True,
                "order_id": order_id,
                "cafm_system": "maximo",
                "status": status
            }
        except Exception as e:
            logger.error(f"Maximo status update failed: {e}")
            return {}

    # Transformation helpers

    def _transform_archibus_wo(self, wo: Dict) -> Dict:
        """Transform Archibus work order to SENTINEL format"""
        return {
            "cafm_id": wo.get("id", ""),
            "title": wo.get("title", ""),
            "description": wo.get("description", ""),
            "status": wo.get("status", "").lower(),
            "priority": wo.get("priority", "").lower(),
            "assigned_to": wo.get("assignedTo", ""),
            "equipment_code": wo.get("equipment_code", ""),
            "created_date": wo.get("createdDate", ""),
            "cafm_system": "archibus"
        }

    def _transform_planon_wo(self, wo: Dict) -> Dict:
        """Transform Planon work order to SENTINEL format"""
        return {
            "cafm_id": wo.get("id", ""),
            "title": wo.get("title", ""),
            "description": wo.get("description", ""),
            "status": wo.get("status", "").lower(),
            "priority": wo.get("priority", "").lower(),
            "assigned_to": wo.get("assignee", ""),
            "equipment_code": wo.get("assetId", ""),
            "created_date": wo.get("createdDate", ""),
            "cafm_system": "planon"
        }

    def _transform_maximo_wo(self, wo: Dict) -> Dict:
        """Transform Maximo work order to SENTINEL format"""
        return {
            "cafm_id": wo.get("wonum", ""),
            "title": wo.get("description", ""),
            "description": wo.get("description", ""),
            "status": wo.get("status", "").lower(),
            "priority": wo.get("priority", "").lower(),
            "assigned_to": wo.get("assigneename", ""),
            "equipment_code": wo.get("assetnum", ""),
            "created_date": wo.get("createdate", ""),
            "cafm_system": "maximo"
        }

    def _transform_archibus_asset(self, asset: Dict) -> Dict:
        """Transform Archibus asset to SENTINEL format"""
        return {
            "cafm_id": asset.get("id", ""),
            "equipment_code": asset.get("code", ""),
            "name": asset.get("name", ""),
            "type": asset.get("type", ""),
            "location": asset.get("location", ""),
            "manufacturer": asset.get("manufacturer", ""),
            "model": asset.get("model", ""),
            "installation_date": asset.get("installationDate", ""),
            "cafm_system": "archibus"
        }

    def _transform_planon_asset(self, asset: Dict) -> Dict:
        """Transform Planon asset to SENTINEL format"""
        return {
            "cafm_id": asset.get("id", ""),
            "equipment_code": asset.get("code", ""),
            "name": asset.get("name", ""),
            "type": asset.get("assetType", ""),
            "location": asset.get("location", ""),
            "manufacturer": asset.get("manufacturer", ""),
            "model": asset.get("modelNumber", ""),
            "installation_date": asset.get("dateInstalled", ""),
            "cafm_system": "planon"
        }

    def _transform_maximo_asset(self, asset: Dict) -> Dict:
        """Transform Maximo asset to SENTINEL format"""
        return {
            "cafm_id": asset.get("assetnum", ""),
            "equipment_code": asset.get("assetnum", ""),
            "name": asset.get("description", ""),
            "type": asset.get("assettype", ""),
            "location": asset.get("location", ""),
            "manufacturer": asset.get("manufacturer", ""),
            "model": asset.get("model", ""),
            "installation_date": asset.get("dateinstalled", ""),
            "cafm_system": "maximo"
        }

    async def close(self) -> None:
        """Close CAFM connection"""
        if self.session:
            await self.session.aclose()
            self.session = None
            logger.info(f"Closed connection to {self.system.value}")
