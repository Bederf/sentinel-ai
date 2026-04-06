"""Persistence layer for BookingRecord and BlockBookingAlert.

Follows the 3-tier fallback pattern: Supabase -> JSON fallback.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.database.supabase_client import get_supabase_client
from app.models.booking_record import BlockBookingAlert, BookingRecord

logger = logging.getLogger(__name__)
_LOCAL_TIMEZONE = ZoneInfo("Africa/Johannesburg")

DATA_DIR = Path(__file__).parent.parent.parent / "data"
BOOKINGS_JSON = DATA_DIR / "block_bookings.json"
ALERTS_JSON = DATA_DIR / "block_booking_alerts.json"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _record_to_dict(r: BookingRecord) -> dict[str, Any]:
    def _booking_dt(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=_LOCAL_TIMEZONE)
        return value.isoformat()

    return {
        "id": r.id,
        "site_id": r.site_id,
        "organiser_email": r.organiser_email,
        "organiser_name": r.organiser_name,
        "room_id": r.room_id,
        "room_name": r.room_name,
        "booking_date": r.booking_date.isoformat(),
        "start_time": _booking_dt(r.start_time),
        "end_time": _booking_dt(r.end_time),
        "raw_email_hash": r.raw_email_hash,
        "ingested_at": r.ingested_at.isoformat(),
        "flagged": r.flagged,
    }


def _alert_to_dict(a: BlockBookingAlert) -> dict[str, Any]:
    return {
        "id": a.id,
        "site_id": a.site_id,
        "organiser_email": a.organiser_email,
        "organiser_name": a.organiser_name,
        "overlap_window_start": a.overlap_window_start.isoformat(),
        "overlap_window_end": a.overlap_window_end.isoformat(),
        "rooms": a.rooms,
        "room_count": a.room_count,
        "booking_ids": a.booking_ids,
        "detected_at": a.detected_at.isoformat(),
        "notification_sent": a.notification_sent,
        "notification_sent_at": (a.notification_sent_at.isoformat() if a.notification_sent_at else None),
        "dismissed": a.dismissed,
        "dismissed_at": (a.dismissed_at.isoformat() if a.dismissed_at else None),
        "dismissed_by": a.dismissed_by,
    }


def _dict_to_record(d: dict[str, Any]) -> BookingRecord:
    return BookingRecord(
        id=d["id"],
        site_id=d.get("site_id", ""),
        organiser_email=d.get("organiser_email", ""),
        organiser_name=d.get("organiser_name", ""),
        room_id=d.get("room_id", ""),
        room_name=d.get("room_name", ""),
        booking_date=date.fromisoformat(d["booking_date"])
        if isinstance(d.get("booking_date"), str)
        else d.get("booking_date", date.today()),
        start_time=datetime.fromisoformat(d["start_time"])
        if isinstance(d.get("start_time"), str)
        else d.get("start_time", datetime.utcnow()),
        end_time=datetime.fromisoformat(d["end_time"])
        if isinstance(d.get("end_time"), str)
        else d.get("end_time", datetime.utcnow()),
        raw_email_hash=d.get("raw_email_hash", ""),
        ingested_at=datetime.fromisoformat(d["ingested_at"])
        if isinstance(d.get("ingested_at"), str)
        else datetime.utcnow(),
        flagged=d.get("flagged", False),
    )


def _dict_to_alert(d: dict[str, Any]) -> BlockBookingAlert:
    return BlockBookingAlert(
        id=d["id"],
        site_id=d.get("site_id", ""),
        organiser_email=d.get("organiser_email", ""),
        organiser_name=d.get("organiser_name", ""),
        overlap_window_start=datetime.fromisoformat(d["overlap_window_start"])
        if isinstance(d.get("overlap_window_start"), str)
        else datetime.utcnow(),
        overlap_window_end=datetime.fromisoformat(d["overlap_window_end"])
        if isinstance(d.get("overlap_window_end"), str)
        else datetime.utcnow(),
        rooms=d.get("rooms", []),
        room_count=d.get("room_count", 0),
        booking_ids=d.get("booking_ids", []),
        detected_at=datetime.fromisoformat(d["detected_at"])
        if isinstance(d.get("detected_at"), str)
        else datetime.utcnow(),
        notification_sent=d.get("notification_sent", False),
        notification_sent_at=datetime.fromisoformat(d["notification_sent_at"])
        if d.get("notification_sent_at")
        else None,
        dismissed=d.get("dismissed", False),
        dismissed_at=datetime.fromisoformat(d["dismissed_at"]) if d.get("dismissed_at") else None,
        dismissed_by=d.get("dismissed_by"),
    )


class BookingStore:
    """Persistence for booking records and block booking alerts."""

    def __init__(self) -> None:
        self.client = None
        try:
            self.client = get_supabase_client()
        except Exception as exc:
            logger.warning("BookingStore: Supabase unavailable: %s", exc)

    # ------------------------------------------------------------------
    # BookingRecord CRUD
    # ------------------------------------------------------------------

    def save_booking(self, record: BookingRecord) -> BookingRecord:
        """Persist a booking record. Returns the saved record."""
        row = _record_to_dict(record)
        row.setdefault("created_at", _now_iso())

        if self.client:
            try:
                result = self.client.table("block_booking_records").insert(row).execute()
                if result.data:
                    return _dict_to_record(result.data[0])
            except Exception as exc:
                logger.error("BookingStore.save_booking Supabase failed: %s", exc)

        # JSON fallback
        return self._save_booking_json(row)

    def booking_exists(self, email_hash: str) -> bool:
        """Check if a booking with this email hash already exists (dedup)."""
        if self.client:
            try:
                result = (
                    self.client.table("block_booking_records")
                    .select("id")
                    .eq("raw_email_hash", email_hash)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return True
            except Exception as exc:
                logger.error("BookingStore.booking_exists Supabase failed: %s", exc)

        # JSON fallback
        return self._booking_exists_json(email_hash)

    def get_bookings_for_site(self, site_id: str, target_date: date) -> list[BookingRecord]:
        """Get all bookings for a site on a given date."""
        date_str = target_date.isoformat()
        if self.client:
            try:
                result = (
                    self.client.table("block_booking_records")
                    .select("*")
                    .eq("site_id", site_id)
                    .eq("booking_date", date_str)
                    .execute()
                )
                if result.data:
                    return [_dict_to_record(d) for d in result.data]
                return []
            except Exception as exc:
                logger.error("BookingStore.get_bookings_for_site Supabase failed: %s", exc)

        return self._get_bookings_for_site_json(site_id, date_str)

    def count_all_bookings_for_site(self, site_id: str) -> int:
        """Count ALL ingested bookings for a site (no date filter)."""
        if self.client:
            try:
                result = (
                    self.client.table("block_booking_records")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .execute()
                )
                return result.count if result.count is not None else 0
            except Exception as exc:
                logger.error("BookingStore.count_all_bookings_for_site Supabase failed: %s", exc)

        # JSON fallback
        records = self._load_json(BOOKINGS_JSON)
        return sum(1 for r in records if r.get("site_id") == site_id)

    def get_all_bookings_for_site(self, site_id: str) -> list[BookingRecord]:
        """Get ALL ingested bookings for a site (no date filter)."""
        if self.client:
            try:
                result = (
                    self.client.table("block_booking_records")
                    .select("*")
                    .eq("site_id", site_id)
                    .order("booking_date", desc=True)
                    .execute()
                )
                if result.data:
                    return [_dict_to_record(d) for d in result.data]
                return []
            except Exception as exc:
                logger.error("BookingStore.get_all_bookings_for_site Supabase failed: %s", exc)

        # JSON fallback
        records = self._load_json(BOOKINGS_JSON)
        return [_dict_to_record(r) for r in records if r.get("site_id") == site_id]

    def get_bookings_by_organiser(
        self,
        site_id: str,
        organiser_email: str,
        from_date: date,
        to_date: date,
    ) -> list[BookingRecord]:
        """Get bookings for a specific organiser within a date range."""
        if self.client:
            try:
                result = (
                    self.client.table("block_booking_records")
                    .select("*")
                    .eq("site_id", site_id)
                    .eq("organiser_email", organiser_email)
                    .gte("booking_date", from_date.isoformat())
                    .lte("booking_date", to_date.isoformat())
                    .execute()
                )
                if result.data:
                    return [_dict_to_record(d) for d in result.data]
                return []
            except Exception as exc:
                logger.error(
                    "BookingStore.get_bookings_by_organiser Supabase failed: %s",
                    exc,
                )

        return self._get_bookings_by_organiser_json(
            site_id, organiser_email, from_date.isoformat(), to_date.isoformat()
        )

    def remove_booking(
        self,
        site_id: str,
        organiser_email: str,
        room_name: str,
        start_time: datetime | None = None,
    ) -> bool:
        """Remove a booking (used for cancellation handling). Returns True if removed."""
        if self.client:
            try:
                q = (
                    self.client.table("block_booking_records")
                    .delete()
                    .eq("site_id", site_id)
                    .eq("organiser_email", organiser_email)
                    .eq("room_name", room_name)
                )
                if start_time:
                    q = q.eq("start_time", start_time.isoformat())
                result = q.execute()
                return bool(result.data)
            except Exception as exc:
                logger.error("BookingStore.remove_booking Supabase failed: %s", exc)

        return self._remove_booking_json(site_id, organiser_email, room_name, start_time)

    def flag_bookings(self, booking_ids: list[str]) -> None:
        """Mark bookings as flagged after an anomaly has been raised."""
        if not booking_ids:
            return

        if self.client:
            try:
                self.client.table("block_booking_records").update({"flagged": True}).in_("id", booking_ids).execute()
                return
            except Exception as exc:
                logger.error("BookingStore.flag_bookings Supabase failed: %s", exc)

        self._flag_bookings_json(booking_ids)

    # ------------------------------------------------------------------
    # BlockBookingAlert CRUD
    # ------------------------------------------------------------------

    def save_alert(self, alert: BlockBookingAlert) -> BlockBookingAlert:
        """Persist a new alert."""
        row = _alert_to_dict(alert)
        row.setdefault("created_at", _now_iso())

        if self.client:
            try:
                result = self.client.table("block_booking_alerts").insert(row).execute()
                if result.data:
                    return _dict_to_alert(result.data[0])
            except Exception as exc:
                logger.error("BookingStore.save_alert Supabase failed: %s", exc)

        return self._save_alert_json(row)

    def get_open_alerts(self, site_id: str) -> list[BlockBookingAlert]:
        """Get all undismissed alerts for a site."""
        if self.client:
            try:
                result = (
                    self.client.table("block_booking_alerts")
                    .select("*")
                    .eq("site_id", site_id)
                    .eq("dismissed", False)
                    .order("detected_at", desc=True)
                    .execute()
                )
                if result.data:
                    return [_dict_to_alert(d) for d in result.data]
                return []
            except Exception as exc:
                logger.error("BookingStore.get_open_alerts Supabase failed: %s", exc)

        return self._get_open_alerts_json(site_id)

    def get_alert_by_id(self, alert_id: str) -> BlockBookingAlert | None:
        """Get a single alert by ID."""
        if self.client:
            try:
                result = self.client.table("block_booking_alerts").select("*").eq("id", alert_id).limit(1).execute()
                if result.data:
                    return _dict_to_alert(result.data[0])
            except Exception as exc:
                logger.error("BookingStore.get_alert_by_id Supabase failed: %s", exc)
        return self._get_alert_by_id_json(alert_id)

    def dismiss_alert(self, alert_id: str, dismissed_by: str) -> BlockBookingAlert | None:
        """Mark an alert as dismissed."""
        now = _now_iso()
        if self.client:
            try:
                result = (
                    self.client.table("block_booking_alerts")
                    .update(
                        {
                            "dismissed": True,
                            "dismissed_at": now,
                            "dismissed_by": dismissed_by,
                        }
                    )
                    .eq("id", alert_id)
                    .execute()
                )
                if result.data:
                    return _dict_to_alert(result.data[0])
            except Exception as exc:
                logger.error("BookingStore.dismiss_alert Supabase failed: %s", exc)

        return self._dismiss_alert_json(alert_id, dismissed_by, now)

    def mark_alert_notified(self, alert_id: str) -> None:
        """Mark an alert's notification as sent."""
        now = _now_iso()
        if self.client:
            try:
                self.client.table("block_booking_alerts").update(
                    {"notification_sent": True, "notification_sent_at": now}
                ).eq("id", alert_id).execute()
                return
            except Exception as exc:
                logger.error("BookingStore.mark_alert_notified Supabase failed: %s", exc)

        self._mark_alert_notified_json(alert_id, now)

    def has_open_alert_for(
        self,
        site_id: str,
        organiser_email: str,
        booking_date: date,
        overlap_start: datetime,
        overlap_end: datetime,
    ) -> bool:
        """Check if an undismissed alert already exists for this organiser+slot."""
        date_str = booking_date.isoformat()
        overlap_start_iso = overlap_start.isoformat()
        overlap_end_iso = overlap_end.isoformat()
        if self.client:
            try:
                result = (
                    self.client.table("block_booking_alerts")
                    .select("id")
                    .eq("site_id", site_id)
                    .eq("organiser_email", organiser_email)
                    .eq("dismissed", False)
                    .eq("overlap_window_start", overlap_start_iso)
                    .eq("overlap_window_end", overlap_end_iso)
                    .limit(1)
                    .execute()
                )
                return bool(result.data)
            except Exception as exc:
                logger.error("BookingStore.has_open_alert_for Supabase failed: %s", exc)

        return self._has_open_alert_for_json(
            site_id,
            organiser_email,
            date_str,
            overlap_start_iso,
            overlap_end_iso,
        )

    # ------------------------------------------------------------------
    # JSON fallback helpers
    # ------------------------------------------------------------------

    def _load_json(self, path: Path) -> list[dict]:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                return []
        return []

    def _save_json(self, path: Path, data: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))

    # Bookings JSON
    def _save_booking_json(self, row: dict) -> BookingRecord:
        records = self._load_json(BOOKINGS_JSON)
        records.append(row)
        self._save_json(BOOKINGS_JSON, records)
        return _dict_to_record(row)

    def _booking_exists_json(self, email_hash: str) -> bool:
        records = self._load_json(BOOKINGS_JSON)
        return any(r.get("raw_email_hash") == email_hash for r in records)

    def _get_bookings_for_site_json(self, site_id: str, date_str: str) -> list[BookingRecord]:
        records = self._load_json(BOOKINGS_JSON)
        return [
            _dict_to_record(r) for r in records if r.get("site_id") == site_id and r.get("booking_date") == date_str
        ]

    def _get_bookings_by_organiser_json(
        self,
        site_id: str,
        organiser_email: str,
        from_date: str,
        to_date: str,
    ) -> list[BookingRecord]:
        records = self._load_json(BOOKINGS_JSON)
        return [
            _dict_to_record(r)
            for r in records
            if r.get("site_id") == site_id
            and r.get("organiser_email") == organiser_email
            and from_date <= r.get("booking_date", "") <= to_date
        ]

    def _remove_booking_json(
        self,
        site_id: str,
        organiser_email: str,
        room_name: str,
        start_time: datetime | None,
    ) -> bool:
        records = self._load_json(BOOKINGS_JSON)
        original_len = len(records)
        start_iso = start_time.isoformat() if start_time else None
        records = [
            r
            for r in records
            if not (
                r.get("site_id") == site_id
                and r.get("organiser_email") == organiser_email
                and r.get("room_name") == room_name
                and (start_iso is None or r.get("start_time") == start_iso)
            )
        ]
        if len(records) < original_len:
            self._save_json(BOOKINGS_JSON, records)
            return True
        return False

    def _flag_bookings_json(self, booking_ids: list[str]) -> None:
        records = self._load_json(BOOKINGS_JSON)
        booking_id_set = set(booking_ids)
        changed = False
        for record in records:
            if record.get("id") in booking_id_set and not record.get("flagged", False):
                record["flagged"] = True
                changed = True
        if changed:
            self._save_json(BOOKINGS_JSON, records)

    # Alerts JSON
    def _save_alert_json(self, row: dict) -> BlockBookingAlert:
        alerts = self._load_json(ALERTS_JSON)
        alerts.append(row)
        self._save_json(ALERTS_JSON, alerts)
        return _dict_to_alert(row)

    def _get_open_alerts_json(self, site_id: str) -> list[BlockBookingAlert]:
        alerts = self._load_json(ALERTS_JSON)
        return [_dict_to_alert(a) for a in alerts if a.get("site_id") == site_id and not a.get("dismissed", False)]

    def _get_alert_by_id_json(self, alert_id: str) -> BlockBookingAlert | None:
        alerts = self._load_json(ALERTS_JSON)
        for a in alerts:
            if a.get("id") == alert_id:
                return _dict_to_alert(a)
        return None

    def _dismiss_alert_json(self, alert_id: str, dismissed_by: str, now: str) -> BlockBookingAlert | None:
        alerts = self._load_json(ALERTS_JSON)
        for a in alerts:
            if a.get("id") == alert_id:
                a["dismissed"] = True
                a["dismissed_at"] = now
                a["dismissed_by"] = dismissed_by
                self._save_json(ALERTS_JSON, alerts)
                return _dict_to_alert(a)
        return None

    def _mark_alert_notified_json(self, alert_id: str, now: str) -> None:
        alerts = self._load_json(ALERTS_JSON)
        for a in alerts:
            if a.get("id") == alert_id:
                a["notification_sent"] = True
                a["notification_sent_at"] = now
        self._save_json(ALERTS_JSON, alerts)

    def _has_open_alert_for_json(
        self,
        site_id: str,
        organiser_email: str,
        date_str: str,
        overlap_start_iso: str,
        overlap_end_iso: str,
    ) -> bool:
        alerts = self._load_json(ALERTS_JSON)
        for a in alerts:
            if (
                a.get("site_id") == site_id
                and a.get("organiser_email") == organiser_email
                and not a.get("dismissed", False)
                and a.get("overlap_window_start", "").startswith(date_str)
                and a.get("overlap_window_start") == overlap_start_iso
                and a.get("overlap_window_end") == overlap_end_iso
            ):
                return True
        return False


# Module-level singleton
_store: BookingStore | None = None


def get_booking_store() -> BookingStore:
    """Get or create the module-level BookingStore singleton."""
    global _store
    if _store is None:
        _store = BookingStore()
    return _store
