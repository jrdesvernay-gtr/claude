"""Minimal in-memory fake of the supabase-py client surface used by
pipeline/db.py: client.table(name).select/insert/update/upsert/eq/limit().execute().
No network, no real credentials -- just enough to test payload shaping and
the load_filing_to_db orchestration.
"""
from __future__ import annotations

import uuid


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table: "_Table", op: str, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self._eq_filters: list[tuple[str, object]] = []
        self._not_null_field = None
        self._limit = None
        self._select_cols = None
        self._on_conflict = None

    def select(self, cols):
        self._select_cols = None if cols == "*" else [c.strip() for c in cols.split(",")]
        return self

    def eq(self, field, value):
        # Chainable, like real supabase-py -- .eq(a, 1).eq(b, 2) means
        # both must match, not "the last .eq() call wins".
        self._eq_filters.append((field, value))
        return self

    def _apply_eq_filters(self, rows):
        for field, value in self._eq_filters:
            rows = [r for r in rows if r.get(field) == value]
        return rows

    @property
    def not_(self):
        return self

    def is_(self, field, value):
        # Only "null" is used anywhere in this codebase (load_persisted_handlers).
        if value == "null":
            self._not_null_field = field
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        if self.op == "select" and self.table.name == "franchisee_units_view":
            rows = self.table.client.compute_franchisee_units_view()
            rows = self._apply_eq_filters(rows)
            if self._limit:
                rows = rows[: self._limit]
            return _Result(rows)

        if self.op == "delete":
            eq_field, eq_value = self._eq_filters[0] if self._eq_filters else (None, None)
            remaining, removed = [], []
            for r in self.table.rows:
                if eq_field and r.get(eq_field) == eq_value:
                    removed.append(r)
                else:
                    remaining.append(r)
            self.table.rows[:] = remaining
            return _Result(removed)

        if self.op == "select":
            rows = self._apply_eq_filters(self.table.rows)
            if self._not_null_field:
                rows = [r for r in rows if r.get(self._not_null_field) is not None]
            if self._limit:
                rows = rows[: self._limit]
            if self._select_cols:
                rows = [{c: r.get(c) for c in self._select_cols} for r in rows]
            return _Result(rows)

        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            inserted = []
            for item in items:
                row = dict(item)
                row.setdefault("id", str(uuid.uuid4()))
                self.table.rows.append(row)
                inserted.append(row)
            return _Result(inserted)

        if self.op == "update":
            matched = self._apply_eq_filters(self.table.rows)
            for row in matched:
                row.update(self.payload)
            return _Result(matched)

        if self.op == "upsert":
            key_fields = self.table.on_conflict_keys.get(self.table.name, ["id"])
            for existing in self.table.rows:
                if all(existing.get(k) == self.payload.get(k) for k in key_fields):
                    existing.update(self.payload)
                    return _Result([existing])
            row = dict(self.payload)
            row.setdefault("id", str(uuid.uuid4()))
            self.table.rows.append(row)
            return _Result([row])

        raise ValueError(f"unsupported op {self.op}")


class _Table:
    def __init__(self, client: "FakeSupabaseClient", name: str):
        self.client = client
        self.name = name
        self.rows = client.data.setdefault(name, [])
        self.on_conflict_keys = client.on_conflict_keys

    def select(self, cols="*"):
        return _Query(self, "select").select(cols)

    def insert(self, payload):
        return _Query(self, "insert", payload)

    def delete(self):
        return _Query(self, "delete")

    def update(self, payload):
        return _Query(self, "update", payload)

    def upsert(self, payload, on_conflict=None):
        if on_conflict:
            self.on_conflict_keys[self.name] = on_conflict.split(",")
        return _Query(self, "upsert", payload)


class FakeSupabaseClient:
    def __init__(self):
        self.data: dict[str, list[dict]] = {}
        self.on_conflict_keys: dict[str, list[str]] = {}

    def table(self, name: str) -> _Table:
        return _Table(self, name)

    def compute_franchisee_units_view(self) -> list[dict]:
        """Mirrors sql/schema.sql's franchisee_units_view: units inner-
        joined to their resolved franchisee and franchisor. Like the real
        view, a unit with no matching franchisee/franchisor row (e.g.
        franchisee_id left null) is excluded, not returned with nulls.
        """
        franchisees = {f["id"]: f for f in self.data.get("franchisees", [])}
        franchisors = {fr["id"]: fr for fr in self.data.get("franchisors", [])}
        rows = []
        for u in self.data.get("units", []):
            f = franchisees.get(u.get("franchisee_id"))
            fr = franchisors.get(u.get("franchisor_id"))
            if f is None or fr is None:
                continue
            rows.append(
                {
                    "franchisee_id": f["id"],
                    "legal_name": f["legal_name"],
                    "unit_id": u["id"],
                    "franchisor_id": u["franchisor_id"],
                    "brand_name": fr["name"],
                    "address": u.get("address"),
                    "city": u.get("city"),
                    "state": u.get("state"),
                    "zip": u.get("zip"),
                    "phone": u.get("phone"),
                    "status": u.get("status"),
                }
            )
        return rows
