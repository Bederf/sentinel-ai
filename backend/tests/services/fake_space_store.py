from __future__ import annotations

from copy import deepcopy


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeSpaceSupabase:
    def __init__(self) -> None:
        self.tables = {
            "space_occupancy_events": [],
            "ghost_findings": [],
            "space_rightsizing_findings": [],
            "space_focus_room_sessions": [],
        }

    def table(self, name: str) -> FakeTableQuery:
        if name not in self.tables:
            self.tables[name] = []
        return FakeTableQuery(self.tables[name])


class FakeTableQuery:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self._selected = False
        self._filters: list[tuple[str, str, object]] = []
        self._order_by: str | None = None
        self._limit: int | None = None
        self._payload: dict | None = None
        self._upsert_payload: dict | None = None
        self._upsert_key: str | None = None
        self._insert_payload: dict | None = None
        self._delete = False

    def select(self, *_args, **_kwargs):
        self._selected = True
        return self

    def insert(self, payload: dict):
        self._insert_payload = deepcopy(payload)
        return self

    def upsert(self, payload: dict, on_conflict: str | None = None):
        self._upsert_payload = deepcopy(payload)
        self._upsert_key = on_conflict or "id"
        return self

    def update(self, payload: dict):
        self._payload = deepcopy(payload)
        return self

    def delete(self):
        self._delete = True
        return self

    def eq(self, field: str, value):
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field: str, values):
        self._filters.append(("in", field, list(values)))
        return self

    def gte(self, field: str, value):
        self._filters.append(("gte", field, value))
        return self

    def lte(self, field: str, value):
        self._filters.append(("lte", field, value))
        return self

    def is_(self, field: str, value):
        self._filters.append(("is", field, value))
        return self

    def order(self, field: str):
        self._order_by = field
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    def execute(self):
        if self._insert_payload is not None:
            self.rows.append(deepcopy(self._insert_payload))
            return FakeResponse([deepcopy(self._insert_payload)])

        if self._upsert_payload is not None:
            key = self._upsert_key or "id"
            for index, row in enumerate(self.rows):
                if row.get(key) == self._upsert_payload.get(key):
                    merged = deepcopy(row)
                    merged.update(deepcopy(self._upsert_payload))
                    self.rows[index] = merged
                    return FakeResponse([deepcopy(merged)])
            self.rows.append(deepcopy(self._upsert_payload))
            return FakeResponse([deepcopy(self._upsert_payload)])

        filtered = [deepcopy(row) for row in self.rows if self._matches(row)]

        if self._payload is not None:
            updated = []
            for index, row in enumerate(self.rows):
                if self._matches(row):
                    merged = deepcopy(row)
                    merged.update(deepcopy(self._payload))
                    self.rows[index] = merged
                    updated.append(deepcopy(merged))
            return FakeResponse(updated)

        if self._delete:
            kept = []
            deleted = []
            for row in self.rows:
                if self._matches(row):
                    deleted.append(deepcopy(row))
                else:
                    kept.append(row)
            self.rows[:] = kept
            return FakeResponse(deleted)

        if self._order_by:
            filtered.sort(key=lambda row: row.get(self._order_by))
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return FakeResponse(filtered)

    def _matches(self, row: dict) -> bool:
        for op, field, value in self._filters:
            field_value = row.get(field)
            if op == "eq" and field_value != value:
                return False
            if op == "in" and field_value not in value:
                return False
            if op == "gte" and (field_value is None or field_value < value):
                return False
            if op == "lte" and (field_value is None or field_value > value):
                return False
            if op == "is":
                if value == "null" and field_value is not None:
                    return False
                if value != "null" and field_value is not value:
                    return False
        return True
