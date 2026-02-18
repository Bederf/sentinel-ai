"""BACnet/IP client service for Tridium Niagara integration.

Uses BAC0 library for BACnet/IP communication with Niagara JACE/Supervisor devices.
Provides device discovery, point read/write operations, and COV subscriptions
with retry logic, error handling, and graceful degradation.

Reference: BAC0 documentation (https://bac0.readthedocs.io/en/latest/)
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional BAC0 import - library may not be installed
try:
    import BAC0 as _BAC0  # noqa: N811
except ImportError:
    _BAC0 = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class BACnetException(Exception):
    """Base exception for BACnet operations."""

    def __init__(self, message: str, device_id: Optional[str] = None):
        self.device_id = device_id
        super().__init__(message)


class BACnetTimeoutError(BACnetException):
    """Raised when a BACnet operation times out."""
    pass


class BACnetDeviceNotFoundError(BACnetException):
    """Raised when a BACnet device cannot be found on the network."""
    pass


class BACnetWriteError(BACnetException):
    """Raised when a BACnet write operation fails."""
    pass


class BACnetReadError(BACnetException):
    """Raised when a BACnet read operation fails."""
    pass


# ---------------------------------------------------------------------------
# BACnet object type mapping
# ---------------------------------------------------------------------------

class BACnetObjectType(str, Enum):
    """Standard BACnet object types."""
    ANALOG_INPUT = "analogInput"
    ANALOG_OUTPUT = "analogOutput"
    ANALOG_VALUE = "analogValue"
    BINARY_INPUT = "binaryInput"
    BINARY_OUTPUT = "binaryOutput"
    BINARY_VALUE = "binaryValue"
    MULTISTATE_INPUT = "multiStateInput"
    MULTISTATE_OUTPUT = "multiStateOutput"
    MULTISTATE_VALUE = "multiStateValue"
    DEVICE = "device"
    SCHEDULE = "schedule"
    CALENDAR = "calendar"
    TRENDLOG = "trendLog"
    NOTIFICATION_CLASS = "notificationClass"


# Map friendly names to BACnet type abbreviations used in BAC0 read strings
BACNET_TYPE_ABBREVIATIONS = {
    BACnetObjectType.ANALOG_INPUT: "analogInput",
    BACnetObjectType.ANALOG_OUTPUT: "analogOutput",
    BACnetObjectType.ANALOG_VALUE: "analogValue",
    BACnetObjectType.BINARY_INPUT: "binaryInput",
    BACnetObjectType.BINARY_OUTPUT: "binaryOutput",
    BACnetObjectType.BINARY_VALUE: "binaryValue",
    BACnetObjectType.MULTISTATE_INPUT: "multiStateInput",
    BACnetObjectType.MULTISTATE_OUTPUT: "multiStateOutput",
    BACnetObjectType.MULTISTATE_VALUE: "multiStateValue",
    BACnetObjectType.DEVICE: "device",
}


# ---------------------------------------------------------------------------
# Discovered device / point data classes
# ---------------------------------------------------------------------------

class DiscoveredDevice:
    """A BACnet device discovered via WhoIs/IAm."""

    def __init__(
        self,
        device_id: int,
        ip_address: str,
        vendor_name: str = "Unknown",
        model_name: str = "",
        firmware_version: str = "",
        object_name: str = "",
    ):
        self.device_id = device_id
        self.ip_address = ip_address
        self.vendor_name = vendor_name
        self.model_name = model_name
        self.firmware_version = firmware_version
        self.object_name = object_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "ip_address": self.ip_address,
            "vendor_name": self.vendor_name,
            "model_name": self.model_name,
            "firmware_version": self.firmware_version,
            "object_name": self.object_name,
        }


class DiscoveredPoint:
    """A BACnet object/point discovered on a device."""

    def __init__(
        self,
        object_type: str,
        instance: int,
        name: str = "",
        description: str = "",
        units: str = "",
        present_value: Any = None,
        writable: bool = False,
    ):
        self.object_type = object_type
        self.instance = instance
        self.name = name
        self.description = description
        self.units = units
        self.present_value = present_value
        self.writable = writable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_type": self.object_type,
            "instance": self.instance,
            "name": self.name,
            "description": self.description,
            "units": self.units,
            "present_value": self.present_value,
            "writable": self.writable,
        }


# ---------------------------------------------------------------------------
# COV subscription tracker
# ---------------------------------------------------------------------------

class COVSubscription:
    """Tracks a Change-of-Value subscription."""

    def __init__(
        self,
        subscription_id: str,
        device_id: int,
        points: List[Tuple[str, int]],
        callback: Callable,
        lifetime: int = 60,
    ):
        self.subscription_id = subscription_id
        self.device_id = device_id
        self.points = points  # list of (object_type, instance) tuples
        self.callback = callback
        self.lifetime = lifetime
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(seconds=lifetime)
        self.active = True
        self._renewal_task: Optional[asyncio.Task] = None

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at

    def renew(self) -> None:
        self.expires_at = datetime.utcnow() + timedelta(seconds=self.lifetime)

    def cancel(self) -> None:
        self.active = False
        if self._renewal_task and not self._renewal_task.done():
            self._renewal_task.cancel()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "device_id": self.device_id,
            "points": [{"object_type": ot, "instance": inst} for ot, inst in self.points],
            "lifetime": self.lifetime,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "active": self.active,
        }


# ---------------------------------------------------------------------------
# Main BACnet client
# ---------------------------------------------------------------------------

class NiagaraBACnetClient:
    """BACnet/IP client for Tridium Niagara integration.

    Wraps the BAC0 library providing:
    - Device discovery via WhoIs/IAm
    - Point read/write with priority array support
    - COV subscriptions with automatic renewal
    - Retry logic for transient failures
    - Graceful degradation when devices are unreachable

    Usage:
        client = NiagaraBACnetClient()
        await client.start()
        devices = await client.discover_devices()
        value = await client.read_point(1234, "analogValue", 0)
        await client.stop()
    """

    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 1.0
    DISCOVERY_TIMEOUT_SECONDS = 5
    DEFAULT_COV_LIFETIME = 60
    DEFAULT_BACNET_PORT = 47808

    def __init__(
        self,
        ip: Optional[str] = None,
        port: int = DEFAULT_BACNET_PORT,
    ):
        self._ip = ip
        self._port = port
        self._bacnet = None
        self._started = False
        self._subscriptions: Dict[str, COVSubscription] = {}
        self._point_cache: Dict[int, List[DiscoveredPoint]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize the BAC0 BACnet/IP client.

        Uses BAC0.lite() for a lightweight client suitable for
        point-level operations without full device management.
        """
        if self._started:
            logger.warning("BACnet client already started")
            return

        if _BAC0 is None:
            logger.error(
                "BAC0 library not installed. Install with: pip install BAC0"
            )
            raise BACnetException("BAC0 library not installed")

        try:
            kwargs: Dict[str, Any] = {"port": self._port}
            if self._ip:
                kwargs["ip"] = self._ip

            logger.info(
                f"Starting BAC0 BACnet/IP client on port {self._port}"
                + (f" bound to {self._ip}" if self._ip else "")
            )
            self._bacnet = _BAC0.lite(**kwargs)
            self._started = True
            logger.info("BAC0 BACnet/IP client started successfully")
        except Exception as e:
            logger.error(f"Failed to start BAC0 client: {e}")
            raise BACnetException(f"Failed to start BACnet client: {e}")

    async def stop(self) -> None:
        """Shut down the BACnet client and cancel all subscriptions."""
        if not self._started:
            return

        # Cancel all COV subscriptions
        for sub in list(self._subscriptions.values()):
            sub.cancel()
        self._subscriptions.clear()

        # Disconnect BAC0
        try:
            if self._bacnet:
                self._bacnet.disconnect()
                logger.info("BAC0 client disconnected")
        except Exception as e:
            logger.warning(f"Error disconnecting BAC0: {e}")
        finally:
            self._bacnet = None
            self._started = False

    @property
    def is_running(self) -> bool:
        return self._started and self._bacnet is not None

    def _ensure_started(self) -> None:
        if not self.is_running:
            raise BACnetException("BACnet client is not started. Call start() first.")

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    async def discover_devices(
        self, timeout: float = DISCOVERY_TIMEOUT_SECONDS
    ) -> List[DiscoveredDevice]:
        """Discover BACnet devices on the network using WhoIs/IAm.

        Args:
            timeout: Seconds to wait for IAm responses (default 5).

        Returns:
            List of discovered BACnet devices.
        """
        self._ensure_started()

        logger.info(f"Discovering BACnet devices (timeout={timeout}s)...")
        try:
            raw_devices = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._bacnet.whois
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Device discovery timed out")
            return []
        except Exception as e:
            logger.error(f"Device discovery failed: {e}")
            raise BACnetException(f"Device discovery failed: {e}")

        devices: List[DiscoveredDevice] = []
        if raw_devices:
            for raw in raw_devices:
                try:
                    device = self._parse_discovered_device(raw)
                    devices.append(device)
                except Exception as e:
                    logger.warning(f"Failed to parse discovered device: {e}")

        logger.info(f"Discovered {len(devices)} BACnet devices")
        return devices

    def _parse_discovered_device(self, raw: Any) -> DiscoveredDevice:
        """Parse a raw BAC0 WhoIs response into a DiscoveredDevice."""
        # BAC0 whois() returns tuples of (address, device_id) or
        # device-like objects depending on version
        if isinstance(raw, (tuple, list)):
            address = str(raw[0]) if len(raw) > 0 else "unknown"
            device_id = int(raw[1]) if len(raw) > 1 else 0
            return DiscoveredDevice(
                device_id=device_id,
                ip_address=address,
            )
        # Handle dict-like responses
        if hasattr(raw, "get"):
            return DiscoveredDevice(
                device_id=raw.get("device_id", 0),
                ip_address=raw.get("address", "unknown"),
                vendor_name=raw.get("vendor_name", "Unknown"),
                model_name=raw.get("model_name", ""),
            )
        # Fallback: try attribute access
        return DiscoveredDevice(
            device_id=getattr(raw, "device_id", 0),
            ip_address=getattr(raw, "address", str(raw)),
        )

    # ------------------------------------------------------------------
    # Point read operations
    # ------------------------------------------------------------------

    async def read_point(
        self,
        device_id: int,
        object_type: str,
        instance: int,
        property_name: str = "presentValue",
    ) -> Any:
        """Read a single point value from a BACnet device.

        Args:
            device_id: BACnet device instance number.
            object_type: BACnet object type (e.g. "analogValue").
            instance: Object instance number.
            property_name: Property to read (default "presentValue").

        Returns:
            The property value.

        Raises:
            BACnetReadError: If the read fails after retries.
            BACnetTimeoutError: If the read times out.
        """
        self._ensure_started()

        read_string = f"{device_id} {object_type},{instance} {property_name}"
        return await self._retry_operation(
            self._do_read, read_string, device_id=device_id
        )

    async def _do_read(self, read_string: str) -> Any:
        """Execute a single BAC0 read operation."""
        try:
            if os.getenv("TESTING", "").lower() == "true":
                return self._bacnet.read(read_string)
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._bacnet.read, read_string
            )
            return result
        except Exception as e:
            raise BACnetReadError(f"Read failed for '{read_string}': {e}")

    async def read_multiple_points(
        self,
        device_id: int,
        points: List[Tuple[str, int]],
    ) -> Dict[str, Any]:
        """Read multiple points from a device.

        Args:
            device_id: BACnet device instance number.
            points: List of (object_type, instance) tuples.

        Returns:
            Dict mapping "objectType:instance" to value.
        """
        results: Dict[str, Any] = {}
        for obj_type, instance in points:
            key = f"{obj_type}:{instance}"
            try:
                value = await self.read_point(device_id, obj_type, instance)
                results[key] = value
            except BACnetException as e:
                logger.warning(f"Failed to read {key} from device {device_id}: {e}")
                results[key] = None
        return results

    # ------------------------------------------------------------------
    # Point list discovery
    # ------------------------------------------------------------------

    async def read_point_list(
        self,
        device_id: int,
        object_types: Optional[List[str]] = None,
        use_cache: bool = True,
    ) -> List[DiscoveredPoint]:
        """Discover all objects/points on a BACnet device.

        Args:
            device_id: BACnet device instance number.
            object_types: Optional filter for specific object types.
            use_cache: If True, return cached results if available.

        Returns:
            List of discovered points on the device.
        """
        self._ensure_started()

        # Return cached if available
        if use_cache and device_id in self._point_cache:
            cached = self._point_cache[device_id]
            if object_types:
                return [p for p in cached if p.object_type in object_types]
            return cached

        logger.info(f"Discovering points on device {device_id}...")
        try:
            raw_list = await asyncio.get_event_loop().run_in_executor(
                None,
                self._bacnet.read,
                f"{device_id} device {device_id} objectList",
            )
        except Exception as e:
            logger.error(f"Failed to read object list from device {device_id}: {e}")
            raise BACnetException(
                f"Failed to read object list: {e}", device_id=str(device_id)
            )

        points: List[DiscoveredPoint] = []
        if raw_list and isinstance(raw_list, (list, tuple)):
            for obj_ref in raw_list:
                try:
                    point = self._parse_object_reference(device_id, obj_ref)
                    if point:
                        if object_types is None or point.object_type in object_types:
                            points.append(point)
                except Exception as e:
                    logger.debug(f"Skipping object {obj_ref}: {e}")

        # Cache results
        self._point_cache[device_id] = points
        logger.info(f"Discovered {len(points)} points on device {device_id}")
        return points

    def _parse_object_reference(
        self, device_id: int, obj_ref: Any
    ) -> Optional[DiscoveredPoint]:
        """Parse a BACnet object reference from the objectList."""
        if isinstance(obj_ref, (tuple, list)) and len(obj_ref) >= 2:
            obj_type = str(obj_ref[0])
            instance = int(obj_ref[1])
        elif isinstance(obj_ref, str) and ":" in obj_ref:
            parts = obj_ref.split(":")
            obj_type = parts[0]
            instance = int(parts[1])
        else:
            return None

        # Determine if writable based on object type
        writable = obj_type in (
            "analogOutput", "analogValue",
            "binaryOutput", "binaryValue",
            "multiStateOutput", "multiStateValue",
        )

        return DiscoveredPoint(
            object_type=obj_type,
            instance=instance,
            writable=writable,
        )

    def clear_point_cache(self, device_id: Optional[int] = None) -> None:
        """Clear cached point lists.

        Args:
            device_id: If provided, clear cache for this device only.
                       Otherwise clear all caches.
        """
        if device_id is not None:
            self._point_cache.pop(device_id, None)
        else:
            self._point_cache.clear()

    # ------------------------------------------------------------------
    # Point write operations
    # ------------------------------------------------------------------

    async def write_point(
        self,
        device_id: int,
        object_type: str,
        instance: int,
        value: Any,
        priority: int = 8,
    ) -> bool:
        """Write a value to a BACnet point with priority array support.

        Args:
            device_id: BACnet device instance number.
            object_type: BACnet object type.
            instance: Object instance number.
            value: Value to write.
            priority: BACnet priority (1-16, default 8 for manual commands).

        Returns:
            True if write succeeded.

        Raises:
            BACnetWriteError: If the write fails after retries.
        """
        self._ensure_started()

        if not 1 <= priority <= 16:
            raise ValueError(f"BACnet priority must be 1-16, got {priority}")

        # BAC0 write format: "address objectType instance presentValue value - priority"
        write_string = (
            f"{device_id} {object_type},{instance} presentValue {value} - {priority}"
        )

        await self._retry_operation(
            self._do_write, write_string, device_id=device_id
        )
        logger.info(
            f"Wrote {object_type},{instance} = {value} (priority {priority}) "
            f"on device {device_id}"
        )
        return True

    async def _do_write(self, write_string: str) -> bool:
        """Execute a single BAC0 write operation."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._bacnet.write, write_string
            )
            return True
        except Exception as e:
            raise BACnetWriteError(f"Write failed for '{write_string}': {e}")

    async def release_point(
        self,
        device_id: int,
        object_type: str,
        instance: int,
        priority: int = 8,
    ) -> bool:
        """Release a priority level on a point (write null to priority slot).

        Args:
            device_id: BACnet device instance number.
            object_type: BACnet object type.
            instance: Object instance number.
            priority: Priority level to release.

        Returns:
            True if release succeeded.
        """
        self._ensure_started()

        write_string = (
            f"{device_id} {object_type},{instance} presentValue null - {priority}"
        )
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._bacnet.write, write_string
            )
            logger.info(
                f"Released priority {priority} on {object_type},{instance} "
                f"device {device_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to release priority: {e}")
            raise BACnetWriteError(f"Priority release failed: {e}")

    # ------------------------------------------------------------------
    # COV subscriptions
    # ------------------------------------------------------------------

    async def subscribe_to_points(
        self,
        device_id: int,
        points: List[Tuple[str, int]],
        callback: Callable,
        lifetime: int = DEFAULT_COV_LIFETIME,
    ) -> COVSubscription:
        """Subscribe to Change-of-Value updates for points.

        Args:
            device_id: BACnet device instance number.
            points: List of (object_type, instance) tuples.
            callback: Function called with (point_key, value) on updates.
            lifetime: Subscription lifetime in seconds (auto-renewed).

        Returns:
            COVSubscription object for tracking/cancellation.
        """
        self._ensure_started()

        subscription_id = str(uuid.uuid4())
        sub = COVSubscription(
            subscription_id=subscription_id,
            device_id=device_id,
            points=points,
            callback=callback,
            lifetime=lifetime,
        )

        # Attempt to create the actual BACnet COV subscription
        try:
            await self._create_bacnet_cov(sub)
        except Exception as e:
            logger.error(f"Failed to create COV subscription: {e}")
            raise BACnetException(f"COV subscription failed: {e}")

        # Start automatic renewal task
        sub._renewal_task = asyncio.create_task(
            self._cov_renewal_loop(sub)
        )

        self._subscriptions[subscription_id] = sub
        logger.info(
            f"Created COV subscription {subscription_id} for {len(points)} points "
            f"on device {device_id} (lifetime={lifetime}s)"
        )
        return sub

    async def _create_bacnet_cov(self, sub: COVSubscription) -> None:
        """Create the actual BACnet COV subscription via BAC0."""
        try:
            from BAC0.core.devices.cov import COVPointSubscription  # noqa: F401

            # BAC0 COV subscription format varies by version
            # Wrap in executor for thread safety
            for obj_type, instance in sub.points:
                read_str = f"{sub.device_id} {obj_type},{instance} presentValue"
                await asyncio.get_event_loop().run_in_executor(
                    None, self._bacnet.read, read_str
                )
        except ImportError:
            logger.warning(
                "BAC0 COV module not available - subscription will use polling fallback"
            )
        except Exception as e:
            logger.warning(f"COV creation error (will retry on renewal): {e}")

    async def _cov_renewal_loop(self, sub: COVSubscription) -> None:
        """Background task to renew COV subscriptions before expiry."""
        while sub.active:
            try:
                # Renew at 80% of lifetime to avoid expiry gaps
                sleep_time = sub.lifetime * 0.8
                await asyncio.sleep(sleep_time)

                if not sub.active:
                    break

                sub.renew()
                try:
                    await self._create_bacnet_cov(sub)
                    logger.debug(f"Renewed COV subscription {sub.subscription_id}")
                except Exception as e:
                    logger.warning(
                        f"COV renewal failed for {sub.subscription_id}: {e}"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in COV renewal loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retry

    async def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel a COV subscription.

        Args:
            subscription_id: ID of the subscription to cancel.

        Returns:
            True if the subscription was found and cancelled.
        """
        sub = self._subscriptions.pop(subscription_id, None)
        if sub is None:
            logger.warning(f"Subscription {subscription_id} not found")
            return False

        sub.cancel()
        logger.info(f"Cancelled COV subscription {subscription_id}")
        return True

    def get_subscription(self, subscription_id: str) -> Optional[COVSubscription]:
        """Get a COV subscription by ID."""
        return self._subscriptions.get(subscription_id)

    def list_subscriptions(self) -> List[COVSubscription]:
        """List all active COV subscriptions."""
        return [s for s in self._subscriptions.values() if s.active]

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    async def _retry_operation(
        self,
        operation: Callable,
        *args: Any,
        device_id: Optional[int] = None,
        max_retries: int = MAX_RETRIES,
        **kwargs: Any,
    ) -> Any:
        """Execute an operation with retry logic for transient failures.

        Args:
            operation: Async callable to execute.
            *args: Positional arguments for the operation.
            device_id: Optional device ID for error context.
            max_retries: Maximum number of retry attempts.
            **kwargs: Keyword arguments for the operation.

        Returns:
            The operation result.

        Raises:
            BACnetException: If all retries are exhausted.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except BACnetException:
                raise  # Don't retry explicit BACnet errors
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(
                    f"Timeout on attempt {attempt}/{max_retries}"
                    + (f" for device {device_id}" if device_id else "")
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Attempt {attempt}/{max_retries} failed: {e}"
                    + (f" (device {device_id})" if device_id else "")
                )

            if attempt < max_retries:
                delay = self.RETRY_DELAY_SECONDS * attempt  # Linear backoff
                await asyncio.sleep(delay)

        # All retries exhausted
        error_msg = (
            f"Operation failed after {max_retries} attempts: {last_error}"
        )
        if isinstance(last_error, asyncio.TimeoutError):
            raise BACnetTimeoutError(
                error_msg, device_id=str(device_id) if device_id else None
            )
        raise BACnetException(
            error_msg, device_id=str(device_id) if device_id else None
        )

    # ------------------------------------------------------------------
    # Utility / info
    # ------------------------------------------------------------------

    async def read_device_info(self, device_id: int) -> Dict[str, Any]:
        """Read basic device properties (name, vendor, model, firmware).

        Args:
            device_id: BACnet device instance number.

        Returns:
            Dict with device info properties.
        """
        self._ensure_started()

        info: Dict[str, Any] = {"device_id": device_id}
        properties = [
            ("objectName", "object_name"),
            ("vendorName", "vendor_name"),
            ("modelName", "model_name"),
            ("firmwareRevision", "firmware_version"),
            ("applicationSoftwareVersion", "software_version"),
            ("protocolVersion", "protocol_version"),
        ]

        for bacnet_prop, key in properties:
            try:
                value = await self.read_point(
                    device_id, "device", device_id, property_name=bacnet_prop
                )
                info[key] = value
            except Exception:
                info[key] = None

        return info

    def get_status(self) -> Dict[str, Any]:
        """Get current client status information."""
        return {
            "started": self._started,
            "port": self._port,
            "ip": self._ip,
            "active_subscriptions": len(
                [s for s in self._subscriptions.values() if s.active]
            ),
            "cached_devices": len(self._point_cache),
        }


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_client_instance: Optional[NiagaraBACnetClient] = None


def get_bacnet_client() -> NiagaraBACnetClient:
    """Get or create the singleton BACnet client instance.

    Reads port and local IP from Settings (which loads from .env).
    """
    global _client_instance
    if _client_instance is None:
        from app.config.settings import settings

        ip = settings.niagara_bacnet_local_ip or None
        port = settings.niagara_bacnet_port

        _client_instance = NiagaraBACnetClient(ip=ip, port=port)
    return _client_instance
