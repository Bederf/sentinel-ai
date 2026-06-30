from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime
from urllib.parse import urlencode

import httpx

from app.adapters.residential.base import ResidentialEnergyAdapter
from app.adapters.residential.schemas import AlarmEvent, DeviceManifest, EnergySnapshot
from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from app.services.encryption_service import get_encryption_service

logger = logging.getLogger(__name__)

_REGION_BASE_URLS = {
    "cn": "https://openapi.tuyacn.com",
    "us": "https://openapi.tuyaus.com",
    "ueaz": "https://openapi-ueaz.tuyaus.com",
    "eu": "https://openapi.tuyaeu.com",
    "weaz": "https://openapi-weaz.tuyaeu.com",
    "in": "https://openapi.tuyain.com",
    "sg": "https://openapi-sg.iotbing.com",
}

_AIRCON_CATEGORIES = {"kt", "air_conditioner", "air_conditioning", "climate"}
_STATUS_POWER_CODES = ("switch", "switch_1", "switch_2")
_STATUS_TARGET_TEMP_CODES = ("temp_set", "temp_set_f", "temp_set_c")
_STATUS_CURRENT_TEMP_CODES = ("temp_current", "temp_current_f", "temp_current_c", "va_temperature")
_STATUS_MODE_CODES = ("mode", "mode_1")


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TuyaCloudAdapter(ResidentialEnergyAdapter):
    """
    Read-only Tuya Cloud API adapter for WiFi-enabled appliances.

    The adapter intentionally does not expose Tuya command/write endpoints.
    Appliance alerts are derived in residential AEGIS from read-only status.
    """

    def __init__(
        self,
        site_config: dict,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_region: str | None = None,
    ) -> None:
        self._site_config = site_config
        self._client_id = client_id or settings.tuya_client_id
        self._client_secret = client_secret or settings.tuya_client_secret
        self._api_region = (api_region or settings.tuya_api_region or "eu").lower()
        self._base_url = _REGION_BASE_URLS.get(self._api_region, _REGION_BASE_URLS["eu"])
        self._access_token: str | None = site_config.get("tuya_access_token") or site_config.get("access_token")
        self._token_expire_at: float = float(site_config.get("tuya_token_expire_at") or 0)
        self._token_lock = threading.Lock()

    # ── Signing and token management ──────────────────────────────────────────

    def _body_hash(self, body: str) -> str:
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def _canonical_url(self, path: str, params: dict | None) -> str:
        if not params:
            return path
        return f"{path}?{urlencode(sorted(params.items()))}"

    def _signature_headers(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: str = "",
        access_token: str | None = None,
    ) -> dict[str, str]:
        timestamp_ms = str(int(time.time() * 1000))
        canonical = self._canonical_url(path, params)
        string_to_sign = f"{method.upper()}\n{self._body_hash(body)}\n\n{canonical}"
        sign_payload = f"{self._client_id}{access_token or ''}{timestamp_ms}{string_to_sign}"
        sign = (
            hmac.new(
                self._client_secret.encode("utf-8"),
                sign_payload.encode("utf-8"),
                hashlib.sha256,
            )
            .hexdigest()
            .upper()
        )
        headers = {
            "client_id": self._client_id,
            "sign": sign,
            "t": timestamp_ms,
            "sign_method": "HMAC-SHA256",
        }
        if access_token:
            headers["access_token"] = access_token
        return headers

    def _refresh_token(self) -> None:
        if not self._client_id or not self._client_secret:
            raise RuntimeError("Tuya client credentials are not configured")

        path = "/v1.0/token"
        params = {"grant_type": "1"}
        headers = self._signature_headers("GET", path, params=params)
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{self._base_url}{path}", params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        result = body.get("result") or body
        access_token = result.get("access_token")
        if not access_token:
            raise RuntimeError("Tuya token response did not include access_token")
        expire_seconds = int(result.get("expire_time") or result.get("expires_in") or 7200)
        self._access_token = access_token
        self._token_expire_at = time.time() + max(60, expire_seconds - 60)
        if result.get("uid"):
            self._site_config["tuya_uid"] = result.get("uid")
        self._site_config["tuya_access_token"] = access_token
        self._site_config["tuya_token_expire_at"] = self._token_expire_at
        self._persist_site_config()

    def _get_token(self) -> str:
        if self._access_token and time.time() < self._token_expire_at:
            return self._access_token
        with self._token_lock:
            if self._access_token and time.time() < self._token_expire_at:
                return self._access_token
            self._refresh_token()
        return self._access_token  # type: ignore[return-value]

    async def _request(
        self, method: str, path: str, *, params: dict | None = None, json_body: dict | None = None
    ) -> dict:
        body = json.dumps(json_body, separators=(",", ":"), ensure_ascii=False) if json_body is not None else ""
        token = self._get_token()
        headers = self._signature_headers(method, path, params=params, body=body, access_token=token)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )
            if resp.status_code == 401:
                with self._token_lock:
                    self._access_token = None
                    self._token_expire_at = 0
                token = self._get_token()
                headers = self._signature_headers(method, path, params=params, body=body, access_token=token)
                resp = await client.request(
                    method,
                    f"{self._base_url}{path}",
                    params=params,
                    json=json_body,
                    headers=headers,
                )
            resp.raise_for_status()
            return resp.json()

    def _persist_site_config(self) -> None:
        site_id = self._site_config.get("site_id")
        if not site_id:
            return
        try:
            encrypted = get_encryption_service().encrypt(json.dumps(self._site_config))
            get_supabase_client().table("residential_sites").update({"site_config": encrypted}).eq(
                "site_id", site_id
            ).execute()
        except Exception as exc:
            logger.warning("Tuya site_config persistence failed for site_id=%s: %s", site_id, exc)

    # ── ResidentialEnergyAdapter interface ────────────────────────────────────

    async def authenticate(self) -> bool:
        try:
            with self._token_lock:
                self._access_token = None
                self._token_expire_at = 0
                self._refresh_token()
            return True
        except Exception as exc:
            logger.warning("Tuya auth failed: %s", exc)
            return False

    async def discover_devices(self) -> list[DeviceManifest]:
        devices: list[dict] = []
        last_id: str | None = None
        for _ in range(10):
            params: dict[str, int | str] = {"page_size": 20}
            if last_id:
                params["last_id"] = last_id
            data = await self._request("GET", "/v2.0/cloud/thing/device", params=params)
            batch = data.get("result") or []
            if not isinstance(batch, list) or not batch:
                break
            devices.extend(batch)
            if len(batch) < 20:
                break
            next_id = batch[-1].get("id")
            if not next_id or next_id == last_id:
                break
            last_id = str(next_id)
        manifests: list[DeviceManifest] = []
        for device in devices:
            category = str(device.get("category") or device.get("category_code") or "").lower()
            name = device.get("name") or device.get("device_name") or "Tuya appliance"
            device_id = device.get("id") or device.get("device_id")
            if not device_id:
                continue
            if category and category not in _AIRCON_CATEGORIES:
                continue
            manifests.append(
                DeviceManifest(
                    device_id=str(device_id),
                    device_name=name,
                    device_type="aircon",
                    source_system="tuya",
                    capabilities=["appliance_status", "temperature", "runtime"],
                )
            )
        return manifests

    async def get_realtime(self, device_id: str) -> EnergySnapshot:
        data = await self._request("GET", f"/v1.0/iot-03/devices/{device_id}/status")
        raw_status = data.get("result") or data.get("status") or []
        status = {item.get("code"): item.get("value") for item in raw_status if isinstance(item, dict)}

        power_state = self._power_state(status)
        return EnergySnapshot(
            site_id=self._site_config.get("site_id", ""),
            device_id=device_id,
            timestamp=datetime.utcnow(),
            pv_power_w=None,
            battery_soc_pct=None,
            battery_power_w=None,
            grid_power_w=None,
            load_power_w=None,
            grid_voltage_v=None,
            source_system="tuya",
            appliance_power_state=power_state,
            appliance_target_temp_c=self._first_float(status, _STATUS_TARGET_TEMP_CODES),
            appliance_current_temp_c=self._first_float(status, _STATUS_CURRENT_TEMP_CODES),
            appliance_mode=self._first_str(status, _STATUS_MODE_CODES),
            appliance_runtime_minutes=self._runtime_minutes(device_id, power_state),
        )

    async def get_historical(self, device_id: str, start: datetime, end: datetime) -> list[EnergySnapshot]:
        logger.info(
            "Tuya historical data unavailable for device_id=%s; relying on SENTINEL retained history", device_id
        )
        return []

    async def get_alarms(self, device_id: str) -> list[AlarmEvent]:
        return []

    # ── Status parsing ─────────────────────────────────────────────────────────

    def _first_float(self, status: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = _safe_float(status.get(key))
            if value is not None:
                return value
        return None

    def _first_str(self, status: dict, keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = status.get(key)
            if value is not None:
                return str(value).lower()
        return None

    def _power_state(self, status: dict) -> str | None:
        for key in _STATUS_POWER_CODES:
            value = status.get(key)
            if isinstance(value, bool):
                return "on" if value else "off"
            if isinstance(value, str):
                normalised = value.strip().lower()
                if normalised in {"true", "1", "on"}:
                    return "on"
                if normalised in {"false", "0", "off"}:
                    return "off"
        return None

    def _runtime_minutes(self, device_id: str, power_state: str | None) -> float | None:
        appliance_state = self._site_config.setdefault("appliance_state", {})
        device_state = appliance_state.setdefault(device_id, {})
        now = datetime.utcnow()
        last_on_raw = device_state.get("last_on_at")

        if power_state == "on":
            if not last_on_raw:
                device_state["last_on_at"] = now.isoformat()
                self._persist_site_config()
                return 0.0
            try:
                last_on = datetime.fromisoformat(str(last_on_raw))
            except ValueError:
                device_state["last_on_at"] = now.isoformat()
                self._persist_site_config()
                return 0.0
            return max(0.0, (now - last_on).total_seconds() / 60)

        if power_state == "off":
            if last_on_raw:
                device_state.pop("last_on_at", None)
                self._persist_site_config()
            return 0.0

        return None
