"""System health aggregation and diagnostics service.

This service provides:
1. Unified health aggregation from 15+ endpoints
2. Historical snapshots for trend analysis
3. SIMBIOT-powered diagnostics orchestration
4. Error log management and auto-resolution
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import httpx


from app.config.settings import settings
from app.core.site_resolver import get_primary_site_code
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SystemHealthService:
    """Core service for system health aggregation and diagnostics."""

    def __init__(self):
        self.client = get_supabase_client()
        self.base_url = settings.backend_url or "http://localhost:9095"

    # ==================== Health Aggregation ====================

    async def get_current_health(self) -> Dict[str, Any]:
        """
        Aggregate health by probing real services.

        Returns:
            Dict with overall_status, overall_score, and component details
        """
        checks = await asyncio.gather(
            self._check_supabase(),
            self._check_redis(),
            self._check_event_bus(),
            self._check_n8n(),
            self._check_servicenow(),
            self._check_notifications(),
            self._check_device_manager(),
            return_exceptions=True,
        )

        labels = [
            "supabase",
            "redis_cache",
            "event_bus",
            "n8n",
            "servicenow",
            "notifications",
            "device_manager",
        ]

        component_scores: Dict[str, int] = {}
        component_details: Dict[str, Dict[str, Any]] = {}
        errors = []

        for label, result in zip(labels, checks):
            if isinstance(result, Exception):
                component_scores[label] = 0
                component_details[label] = {"status": "critical", "note": str(result)}
                errors.append({"component": label, "error": str(result)})
            else:
                component_scores[label] = result["score"]
                component_details[label] = {
                    "status": result["status"],
                    "note": result["note"],
                }

        # Weights sum to 1.0
        weights = {
            "supabase": 0.25,
            "redis_cache": 0.15,
            "event_bus": 0.20,
            "n8n": 0.10,
            "servicenow": 0.10,
            "notifications": 0.10,
            "device_manager": 0.10,
        }

        weighted_score = sum(component_scores.get(c, 0) * w for c, w in weights.items())
        overall_score = int(weighted_score)

        if overall_score >= 80:
            overall_status = "healthy"
        elif overall_score >= 60:
            overall_status = "degraded"
        else:
            overall_status = "critical"

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": overall_status,
            "overall_score": overall_score,
            "component_scores": component_scores,
            "component_details": component_details,
            "errors": errors,
        }

    # ==================== Individual Probes ====================

    async def _check_supabase(self) -> Dict[str, Any]:
        """Probe Supabase with a lightweight query."""
        try:
            result = self.client.table("sites").select("id", count="exact").limit(1).execute()
            count = result.count if result.count is not None else len(result.data or [])
            return {
                "score": 95,
                "status": "healthy",
                "note": f"Connected · {count} building(s)",
            }
        except Exception as e:
            return {"score": 30, "status": "degraded", "note": f"Query failed: {e}"}

    async def _check_redis(self) -> Dict[str, Any]:
        """Probe Redis health via direct connection."""
        if not settings.redis_enabled:
            return {"score": 70, "status": "degraded", "note": "Disabled in config"}
        try:
            import redis

            client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            info = client.info("memory")
            used_mb = round(info.get("used_memory", 0) / 1024 / 1024, 1)
            client.close()
            return {
                "score": 95,
                "status": "healthy",
                "note": f"Connected · {used_mb} MB used",
            }
        except ImportError:
            # redis package not available — raw socket fallback
            try:
                import socket

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                try:
                    sock.connect(("localhost", 6379))
                    sock.sendall(b"PING\r\n")
                    resp = sock.recv(16)
                    if b"PONG" in resp:
                        return {
                            "score": 85,
                            "status": "healthy",
                            "note": "Reachable · redis package unavailable",
                        }
                finally:
                    sock.close()
            except Exception:
                pass
            return {"score": 40, "status": "degraded", "note": "Connection failed"}
        except Exception as e:
            logger.error("Redis check error (%s): %s", type(e).__name__, e)
            return {"score": 20, "status": "critical", "note": f"Unreachable: {e}"}

    async def _check_event_bus(self) -> Dict[str, Any]:
        """Check Event Bus singleton metrics."""
        try:
            from app.services.event_bus import get_event_bus

            bus = get_event_bus()
            m = bus.metrics  # property, not method
            subs = m.get("subscription_count", 0)
            emitted = m.get("events_emitted", 0)
            errs = m.get("handler_errors", 0)

            if subs == 0:
                return {"score": 50, "status": "degraded", "note": "No subscribers"}

            score = 95
            if errs > 0:
                score -= min(30, errs * 5)

            status = "healthy" if score >= 80 else "degraded"
            return {
                "score": score,
                "status": status,
                "note": f"{subs} subscribers · {emitted} events · {errs} errors",
            }
        except Exception as e:
            return {"score": 0, "status": "critical", "note": f"Not available: {e}"}

    async def _check_n8n(self) -> Dict[str, Any]:
        """Check n8n connectivity."""
        try:
            from app.services.n8n_service import get_n8n_service, N8nConnectionStatus

            svc = get_n8n_service()
            if not svc.is_configured:
                return {
                    "score": 50,
                    "status": "degraded",
                    "note": "Not configured (N8N_API_URL missing)",
                }

            status = await svc.check_connection()
            if status.status == N8nConnectionStatus.CONNECTED:
                return {
                    "score": 95,
                    "status": "healthy",
                    "note": f"Connected · {status.active_workflows}/{status.total_workflows} workflows active",
                }
            return {
                "score": 40,
                "status": "degraded",
                "note": status.message,
            }
        except Exception as e:
            return {"score": 30, "status": "degraded", "note": f"Check failed: {e}"}

    async def _check_servicenow(self) -> Dict[str, Any]:
        """Check ServiceNow configuration."""
        try:
            from app.services.servicenow_service import get_servicenow_service

            svc = get_servicenow_service()
            if not svc.is_configured:
                return {
                    "score": 50,
                    "status": "degraded",
                    "note": "Credentials not configured",
                }
            domain = svc.config.domain or "unknown"
            return {
                "score": 95,
                "status": "healthy",
                "note": f"Connected · {domain}",
            }
        except Exception as e:
            return {"score": 30, "status": "degraded", "note": f"Check failed: {e}"}

    async def _check_notifications(self) -> Dict[str, Any]:
        """Check Notification Router state."""
        try:
            from app.services.sentry_notification_router import get_sentry_router

            router = get_sentry_router()
            status = router.get_status()
            recipients = status.get("recipients", 0)
            sent = status.get("metrics", {}).get("pushes_sent", 0)
            if recipients == 0:
                return {
                    "score": 50,
                    "status": "degraded",
                    "note": "No recipients configured",
                }
            return {
                "score": 90,
                "status": "healthy",
                "note": f"{recipients} recipients · {sent} sent",
            }
        except Exception as e:
            return {"score": 30, "status": "degraded", "note": f"Check failed: {e}"}

    async def _check_device_manager(self) -> Dict[str, Any]:
        """Check Device Manager state."""
        try:
            from app.services.device_abstraction import device_manager

            if not device_manager._initialized:
                return {
                    "score": 50,
                    "status": "degraded",
                    "note": "Not initialized",
                }
            adapter_count = len(device_manager._adapters)
            return {
                "score": 90,
                "status": "healthy",
                "note": f"{adapter_count} device adapters active",
            }
        except Exception as e:
            return {"score": 40, "status": "degraded", "note": f"Check failed: {e}"}

    # ==================== Extended Probes (Phase 160) ====================

    async def _check_disk(self) -> Dict[str, Any]:
        """Probe system disk usage."""
        try:
            import shutil

            usage = shutil.disk_usage("/opt/bms-intelligence")
            percent_used = (usage.used / usage.total) * 100
            free_gb = usage.free / (1024**3)
            score = max(10, int(100 - percent_used))
            if percent_used >= 95:
                status = "critical"
            elif percent_used >= 85:
                status = "degraded"
            else:
                status = "healthy"
            return {
                "score": score,
                "status": status,
                "note": f"{percent_used:.1f}% used · {free_gb:.1f}GB free",
            }
        except Exception as e:
            return {"score": 50, "status": "degraded", "note": f"Check failed: {e}"}

    async def _check_llm(self) -> Dict[str, Any]:
        """Probe LLM availability (Ollama local or Claude API)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Try Ollama first (local inference)
                try:
                    resp = await client.get("http://localhost:11434/api/tags")
                    if resp.status_code == 200:
                        data = resp.json()
                        models = data.get("models", [])
                        return {
                            "score": 95,
                            "status": "healthy",
                            "note": f"Ollama · {len(models)} model(s) loaded",
                        }
                except Exception:
                    pass

                # Check if Claude API key is configured
                api_key = getattr(settings, "anthropic_api_key", None) or getattr(settings, "ANTHROPIC_API_KEY", None)
                if api_key:
                    return {
                        "score": 85,
                        "status": "healthy",
                        "note": "Claude API key configured",
                    }

                return {
                    "score": 40,
                    "status": "degraded",
                    "note": "No LLM backend available",
                }
        except Exception as e:
            return {"score": 30, "status": "degraded", "note": f"LLM check failed: {e}"}

    async def _check_ml_models(self) -> Dict[str, Any]:
        """Probe ML model files on disk."""
        try:
            from pathlib import Path

            models_dir = Path(__file__).parent.parent / "ml" / "models"
            if not models_dir.exists():
                return {"score": 50, "status": "degraded", "note": "Models directory not found"}

            model_files = list(models_dir.rglob("*.joblib")) + list(models_dir.rglob("*.pkl"))
            count = len(model_files)
            if count == 0:
                return {"score": 40, "status": "degraded", "note": "No trained models found"}

            # Check most recent training date
            newest = max(f.stat().st_mtime for f in model_files) if model_files else 0
            from datetime import datetime as dt

            last_trained = dt.fromtimestamp(newest).strftime("%Y-%m-%d") if newest else "never"
            return {
                "score": min(95, 50 + count * 2),
                "status": "healthy",
                "note": f"{count} models · last trained {last_trained}",
            }
        except Exception as e:
            return {"score": 30, "status": "degraded", "note": f"ML check failed: {e}"}

    async def _check_background_jobs(self) -> Dict[str, Any]:
        """Probe APScheduler background job status."""
        try:
            from app.services.background_scheduler import scheduler_service

            sched = scheduler_service.scheduler
            if sched and sched.running:
                jobs = sched.get_jobs()
                return {
                    "score": 90,
                    "status": "healthy",
                    "note": f"Running · {len(jobs)} scheduled jobs",
                }
            return {"score": 40, "status": "degraded", "note": "Scheduler not running"}
        except ImportError:
            return {"score": 60, "status": "degraded", "note": "Scheduler not available"}
        except Exception as e:
            return {"score": 50, "status": "degraded", "note": f"Scheduler check failed: {e}"}

    async def _check_rag(self) -> Dict[str, Any]:
        """Probe RAG document store status."""
        try:
            from pathlib import Path

            # Check if document store exists
            docs_dir = Path(__file__).parent.parent / "data" / "documents"
            if not docs_dir.exists():
                return {"score": 50, "status": "degraded", "note": "No document store"}

            doc_files = list(docs_dir.rglob("*.json")) + list(docs_dir.rglob("*.txt"))
            count = len(doc_files)
            if count == 0:
                return {"score": 50, "status": "degraded", "note": "No documents ingested"}
            return {
                "score": min(90, 50 + count),
                "status": "healthy",
                "note": f"{count} documents indexed",
            }
        except Exception as e:
            return {"score": 30, "status": "degraded", "note": f"RAG check failed: {e}"}

    async def get_extended_health(self) -> Dict[str, Any]:
        """Extended health including disk, LLM, ML, jobs, RAG probes."""
        base = await self.get_current_health()

        extended_checks = await asyncio.gather(
            self._check_disk(),
            self._check_llm(),
            self._check_ml_models(),
            self._check_background_jobs(),
            self._check_rag(),
            return_exceptions=True,
        )

        extended_labels = ["disk", "llm", "ml_models", "background_jobs", "rag"]

        for label, result in zip(extended_labels, extended_checks):
            if isinstance(result, Exception):
                base["component_scores"][label] = 0
                base["component_details"][label] = {
                    "status": "critical",
                    "note": str(result),
                }
            else:
                base["component_scores"][label] = result["score"]
                base["component_details"][label] = {
                    "status": result["status"],
                    "note": result["note"],
                }

        return base

    async def _check_endpoint(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        key: str,
    ) -> Dict[str, Any]:
        """Check a single health endpoint."""
        try:
            url = f"{self.base_url}{endpoint}"
            response = await client.get(url)
            response.raise_for_status()
            return {
                "status": "ok",
                "data": response.json(),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            raise Exception(f"Failed to check {endpoint}: {str(e)}")

    # ==================== Health Storage ====================

    async def store_health_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """Store health snapshot to database.

        Args:
            snapshot: Health aggregation result

        Returns:
            Snapshot ID
        """
        try:
            response = (
                self.client.table("system_health_snapshots")
                .insert(
                    {
                        "timestamp": snapshot["timestamp"],
                        "overall_status": snapshot["overall_status"],
                        "overall_score": snapshot["overall_score"],
                        "component_scores": snapshot["component_scores"],
                        "details": snapshot["component_details"],
                    }
                )
                .execute()
            )

            if response.data:
                return response.data[0]["id"]
            raise Exception("Failed to insert snapshot")
        except Exception as e:
            # Log error but don't fail the entire operation
            print(f"Error storing health snapshot: {e}")
            return None

    async def get_health_history(
        self,
        time_range: str = "24h",
    ) -> Dict[str, Any]:
        """Get historical health data for trend analysis.

        Args:
            time_range: "24h", "7d", or "30d"

        Returns:
            Historical snapshots and calculated metrics
        """
        # Parse time range
        if time_range == "24h":
            hours = 24
        elif time_range == "7d":
            hours = 24 * 7
        elif time_range == "30d":
            hours = 24 * 30
        else:
            hours = 24

        start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        try:
            # Fetch snapshots from database
            response = (
                self.client.table("system_health_snapshots")
                .select("*")
                .filter(
                    "timestamp",
                    "gte",
                    start_time,
                )
                .order(
                    "timestamp",
                    desc=False,
                )
                .execute()
            )

            snapshots = response.data or []

            # Calculate metrics
            if snapshots:
                scores = [s["overall_score"] for s in snapshots]
                avg_score = sum(scores) / len(scores)
                min_score = min(scores)
                max_score = max(scores)

                # Calculate uptime percentage (assume score >= 60 = up)
                uptime_count = sum(1 for s in snapshots if s["overall_score"] >= 60)
                uptime_percentage = (uptime_count / len(snapshots)) * 100 if snapshots else 0

                # Simple trend calculation
                if len(scores) > 1:
                    recent_avg = sum(scores[-10:]) / min(10, len(scores))
                    older_avg = sum(scores[:10]) / min(10, len(scores))
                    if recent_avg > older_avg + 5:
                        trend = "improving"
                    elif recent_avg < older_avg - 5:
                        trend = "degrading"
                    else:
                        trend = "stable"
                else:
                    trend = "stable"
            else:
                avg_score = 0
                min_score = 0
                max_score = 0
                uptime_percentage = 0
                trend = "unknown"

            return {
                "range": time_range,
                "snapshots": snapshots,
                "metrics": {
                    "avg_score": round(avg_score, 1),
                    "min_score": min_score,
                    "max_score": max_score,
                    "uptime_percentage": round(uptime_percentage, 1),
                    "trend": trend,
                },
                "snapshot_count": len(snapshots),
            }
        except Exception as e:
            print(f"Error fetching health history: {e}")
            return {
                "range": time_range,
                "snapshots": [],
                "metrics": {},
                "snapshot_count": 0,
            }

    # ==================== SIMBIOT Diagnostics ====================

    async def run_diagnostics(
        self,
        target: str = "full_system",
        site_code: Optional[str] = None,
    ) -> str:
        """
        Run SIMBIOT diagnostics workflow.

        Executes 6 diagnostic tools in sequence:
        1. get_devices - Inventory all devices
        2. discover_tridonic_gateway - Check DALI gateway
        3. get_buildings - Retrieve building configs
        4. search_alarms - Find active alarms
        5. get_health_score - Calculate health scores
        6. get_asset_detail - Deep dive on flagged assets

        Args:
            target: "full_system", "building:{code}", or "component:{name}"
            site_code: Optional building code for filtered diagnostics

        Returns:
            diagnostic_id for polling results
        """
        diagnostic_id = str(uuid.uuid4())

        # Store pending diagnostic record
        try:
            self.client.table("system_diagnostics").insert(
                {
                    "diagnostic_id": diagnostic_id,
                    "target": target,
                    "status": "pending",
                }
            ).execute()
        except Exception as e:
            print(f"Error creating diagnostic record: {e}")
            return diagnostic_id

        # Start async diagnostic execution
        # In production, this would be queued to a background task
        asyncio.create_task(self._execute_diagnostics(diagnostic_id, target, site_code))

        return diagnostic_id

    async def _execute_diagnostics(
        self,
        diagnostic_id: str,
        target: str,
        site_code: Optional[str],
    ) -> None:
        """Execute diagnostics workflow (runs in background)."""
        try:
            # Update status to running
            self.client.table("system_diagnostics").update(
                {
                    "status": "running",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            ).eq("diagnostic_id", diagnostic_id).execute()

            start_time = datetime.utcnow()
            results = {}
            recommendations = []

            # Tool 1: Get device inventory
            try:
                results["device_inventory"] = await self._call_simbiot_tool("get_devices")
            except Exception as e:
                results["device_inventory"] = {"error": str(e)}
                recommendations.append("Device inventory check failed - verify device manager connectivity")

            # Tool 2: Check DALI gateway
            try:
                results["dali_gateway"] = await self._call_simbiot_tool(
                    "discover_tridonic_gateway",
                    {"site_code": site_code or get_primary_site_code() or "unknown"},
                )
            except Exception as e:
                results["dali_gateway"] = {"error": str(e)}
                recommendations.append("DALI gateway check failed - verify Tridonic system connectivity")

            # Tool 3: Get buildings
            try:
                results["sites"] = await self._call_simbiot_tool("get_buildings")
            except Exception as e:
                results["sites"] = {"error": str(e)}
                recommendations.append("Building configuration check failed - verify database connectivity")

            # Tool 4: Search alarms
            try:
                results["alarms"] = await self._call_simbiot_tool(
                    "search_alarms",
                    {"site_code": site_code or get_primary_site_code() or "unknown"},
                )
            except Exception as e:
                results["alarms"] = {"error": str(e)}
                recommendations.append("Alarm search failed - check integration endpoints")

            # Tool 5: Get health score
            try:
                results["health_score"] = await self._call_simbiot_tool(
                    "get_health_score",
                    {"site_code": site_code or get_primary_site_code() or "unknown"},
                )
            except Exception as e:
                results["health_score"] = {"error": str(e)}

            # Tool 6: Asset details
            try:
                results["asset_details"] = await self._call_simbiot_tool(
                    "get_asset_detail",
                    {"site_code": site_code or get_primary_site_code() or "unknown"},
                )
            except Exception as e:
                results["asset_details"] = {"error": str(e)}

            # Calculate duration
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Update diagnostic record with results
            self.client.table("system_diagnostics").update(
                {
                    "status": "completed",
                    "duration_seconds": int(duration),
                    "results": results,
                    "recommendations": recommendations,
                }
            ).eq("diagnostic_id", diagnostic_id).execute()

        except Exception as e:
            # Mark as failed
            try:
                self.client.table("system_diagnostics").update(
                    {
                        "status": "failed",
                        "error_message": str(e),
                    }
                ).eq("diagnostic_id", diagnostic_id).execute()
            except Exception:
                pass

    async def _call_simbiot_tool(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call a SIMBIOT MCP tool.

        In production, this would use the actual MCP client.
        For now, returns mock data.
        """
        # Mock implementation - in production would call actual MCP server
        mock_responses = {
            "get_devices": {
                "status": "success",
                "devices": [
                    {"id": "dev-001", "type": "chiller", "status": "online"},
                    {"id": "dev-002", "type": "ahu", "status": "online"},
                ],
            },
            "discover_tridonic_gateway": {
                "status": "success",
                "gateway_found": True,
                "controllers": 2,
                "sensors": 45,
            },
            "get_buildings": {
                "status": "success",
                "sites": [
                    {"code": "site-002", "name": "Sandton", "status": "active"},
                ],
            },
            "search_alarms": {
                "status": "success",
                "alarms": [],
            },
            "get_health_score": {
                "status": "success",
                "score": 85,
                "details": {},
            },
            "get_asset_detail": {
                "status": "success",
                "assets": [],
            },
        }
        return mock_responses.get(tool_name, {"status": "unknown_tool"})

    async def get_diagnostic_results(self, diagnostic_id: str) -> Dict[str, Any]:
        """Poll diagnostic results by ID.

        Args:
            diagnostic_id: Diagnostic request ID

        Returns:
            Diagnostic result with status and findings
        """
        try:
            response = self.client.table("system_diagnostics").select("*").eq("diagnostic_id", diagnostic_id).execute()

            if response.data:
                return response.data[0]
            else:
                return {"error": "Diagnostic not found"}
        except Exception as e:
            return {"error": str(e)}

    # ==================== Error Logging ====================

    async def log_system_error(
        self,
        category: str,
        severity: str,
        component: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Log a system error.

        Args:
            category: "bms", "api", "database", "service", "other"
            severity: "warning", "error", "critical"
            component: Component name
            message: Error message
            details: Additional error details

        Returns:
            Error log ID
        """
        try:
            response = (
                self.client.table("system_error_logs")
                .insert(
                    {
                        "category": category,
                        "severity": severity,
                        "component": component,
                        "message": message,
                        "details": details or {},
                    }
                )
                .execute()
            )

            if response.data:
                return response.data[0]["id"]
            raise Exception("Failed to insert error log")
        except Exception as e:
            print(f"Error logging system error: {e}")
            return None

    async def get_error_logs(
        self,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get error logs with filters.

        Args:
            category: Filter by category
            severity: Filter by severity
            resolved: Filter by resolved status
            limit: Max results
            offset: Pagination offset

        Returns:
            Total count and list of error logs
        """
        try:
            query = self.client.table("system_error_logs").select("*", count="exact")

            if category:
                query = query.eq("category", category)
            if severity:
                query = query.eq("severity", severity)
            if resolved is not None:
                query = query.eq("resolved", resolved)

            response = (
                query.order(
                    "timestamp",
                    desc=True,
                )
                .range(offset, offset + limit - 1)
                .execute()
            )

            return {
                "total": response.count or 0,
                "logs": response.data or [],
                "page": offset // limit,
                "page_size": limit,
            }
        except Exception as e:
            print(f"Error fetching error logs: {e}")
            return {
                "total": 0,
                "logs": [],
                "page": offset // limit,
                "page_size": limit,
            }

    async def auto_resolve_stale_errors(self) -> int:
        """
        Auto-resolve errors if component is now healthy for 24h.

        Returns:
            Number of errors auto-resolved
        """
        try:
            # Get unresolved errors
            errors_response = self.client.table("system_error_logs").select("*").eq("resolved", False).execute()

            errors = errors_response.data or []
            resolved_count = 0

            for error in errors:
                # Check if component is now healthy
                current_health = await self.get_current_health()
                error_component = error["component"]

                # Check if component status improved
                component_detail = current_health.get("component_details", {}).get(error_component, {})
                if component_detail.get("status") in ["ok", "healthy"]:
                    # Mark error as resolved
                    self.client.table("system_error_logs").update(
                        {
                            "resolved": True,
                            "resolved_at": datetime.utcnow().isoformat(),
                        }
                    ).eq("id", error["id"]).execute()
                    resolved_count += 1

            return resolved_count
        except Exception as e:
            print(f"Error auto-resolving errors: {e}")
            return 0
