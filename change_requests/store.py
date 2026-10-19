"""SQLite persistence for change-request drafts and immutable batches."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4


class Error(Exception):
    def __init__(self, code: str, status: int = 400, current=None):
        super().__init__(code.replace("_", " "))
        self.code, self.status, self.current = code, status, current


def _uuid(value):
    if not isinstance(value, str):
        raise Error("invalid_id")
    try:
        return str(UUID(value))
    except ValueError:
        raise Error("invalid_id") from None


def _version(value):
    if type(value) is not int or value < 1:
        raise Error("invalid_version")
    return value


def _text(value, field="text"):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 20000:
        raise Error(f"invalid_{field}")
    return value.strip()


def _now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, db: Path, catalogue: list):
        self.db = Path(db)
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.areas = {(view["id"], kind, area["id"])
                      for view in catalogue for kind in ("card", "content")
                      for area in view["areas"].get(kind, [])}
        with self._transaction() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            conn.execute("""CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                selection TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL)""")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_active_batch
                ON batches ((1)) WHERE status != 'completed'""")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    @contextmanager
    def _transaction(self):
        # A connection belongs to one operation, including calls from other threads/processes.
        conn = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _content(self, data):
        if not isinstance(data, dict):
            raise Error("invalid_note")
        values = tuple(data.get(key) for key in ("view", "kind", "area"))
        if not all(isinstance(value, str) for value in values) or values not in self.areas:
            raise Error("invalid_area")
        return dict(zip(("view", "kind", "area"), values), text=_text(data.get("text")))

    @staticmethod
    def _note(conn, note_id, version):
        row = conn.execute("SELECT data FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise Error("note_not_found", 404)
        note = json.loads(row["data"])
        if note["version"] != version:
            raise Error("version_conflict", 409, note)
        return note

    @staticmethod
    def _batch(conn, batch_id):
        row = conn.execute("SELECT data FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if row is None:
            raise Error("batch_not_found", 404)
        return json.loads(row["data"])

    @staticmethod
    def _save_batch(conn, batch):
        conn.execute("UPDATE batches SET status = ?, data = ? WHERE id = ?",
                     (batch["status"], json.dumps(batch), batch["id"]))
        return batch

    def state(self):
        with self._transaction() as conn:
            drafts = [json.loads(row["data"]) for row in conn.execute("SELECT data FROM notes ORDER BY rowid")]
            batches = [json.loads(row["data"]) for row in conn.execute("SELECT data FROM batches ORDER BY rowid DESC")]
            return {"drafts": drafts,
                    "active_batch": next((b for b in batches if b["status"] != "completed"), None),
                    "archive": [b for b in batches if b["status"] == "completed"]}

    def create(self, data):
        note = {"id": str(uuid4()), **self._content(data), "version": 1}
        with self._transaction() as conn:
            conn.execute("INSERT INTO notes (id, data) VALUES (?, ?)", (note["id"], json.dumps(note)))
        return note

    def update(self, note_id, data):
        note_id = _uuid(note_id)
        if not isinstance(data, dict):
            raise Error("invalid_note")
        version = _version(data.get("version"))
        content = self._content(data)
        with self._transaction() as conn:
            self._note(conn, note_id, version)
            note = {"id": note_id, **content, "version": version + 1}
            conn.execute("UPDATE notes SET data = ? WHERE id = ?", (json.dumps(note), note_id))
            return note

    def delete(self, note_id, version):
        note_id, version = _uuid(note_id), _version(version)
        with self._transaction() as conn:
            self._note(conn, note_id, version)
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    def submit(self, request_id, noteslist):
        request_id = _uuid(request_id)
        if not isinstance(noteslist, list) or not noteslist:
            raise Error("invalid_selection")
        selected = []
        for item in noteslist:
            if not isinstance(item, dict) or set(item) != {"id", "version"}:
                raise Error("invalid_selection")
            selected.append({"id": _uuid(item["id"]), "version": _version(item["version"])})
        if len({item["id"] for item in selected}) != len(selected):
            raise Error("duplicate_note")
        canonical = json.dumps(sorted(selected, key=lambda item: item["id"]), sort_keys=True)
        with self._transaction() as conn:
            previous = conn.execute("SELECT selection, data FROM batches WHERE request_id = ?", (request_id,)).fetchone()
            if previous is not None:
                if previous["selection"] != canonical:
                    raise Error("request_conflict", 409)
                return json.loads(previous["data"]), False
            if conn.execute("SELECT 1 FROM batches WHERE status != 'completed' LIMIT 1").fetchone():
                raise Error("active_batch", 409)
            notes = [self._note(conn, item["id"], item["version"]) for item in selected]
            groups = {}
            for note in notes:
                key = (note["view"], note["kind"], note["area"])
                groups.setdefault(key, {"view": key[0], "kind": key[1], "area": key[2], "note_ids": []})["note_ids"].append(note["id"])
            batch = {"id": str(uuid4()), "status": "queued", "notes": notes,
                     "groups": list(groups.values()), "error": None, "created_at": _now(),
                     "completed_at": None, "summary": "", "validation": "", "commit": ""}
            conn.execute("INSERT INTO batches (id, request_id, selection, status, data) VALUES (?, ?, ?, ?, ?)",
                         (batch["id"], request_id, canonical, batch["status"], json.dumps(batch)))
            conn.executemany("DELETE FROM notes WHERE id = ?", [(note["id"],) for note in notes])
            return batch, True

    def get_batch(self, batch_id):
        batch_id = _uuid(batch_id)
        with self._transaction() as conn:
            return self._batch(conn, batch_id)

    def delivery(self, batch_id, status, error=None):
        batch_id = _uuid(batch_id)
        if status not in ("delivering", "sent", "failed", "uncertain"):
            raise Error("invalid_delivery_status")
        with self._transaction() as conn:
            batch = self._batch(conn, batch_id)
            # The receiver may claim and finish before the bridge acknowledges delivery.
            if batch["status"] in ("processing", "completed"):
                return batch
            batch.update(status=status, error=error)
            return self._save_batch(conn, batch)

    def claim(self, batch_id):
        batch_id = _uuid(batch_id)
        with self._transaction() as conn:
            batch = self._batch(conn, batch_id)
            if batch["status"] in ("processing", "completed"):
                raise Error("already_claimed", 409)
            batch.update(status="processing", error=None)
            return self._save_batch(conn, batch)

    def complete(self, batch_id, summary, validation, commit=""):
        batch_id = _uuid(batch_id)
        summary, validation = _text(summary, "summary"), _text(validation, "validation")
        if not isinstance(commit, str):
            raise Error("invalid_commit")
        with self._transaction() as conn:
            batch = self._batch(conn, batch_id)
            if batch["status"] != "processing":
                raise Error("not_processing", 409)
            batch.update(status="completed", completed_at=_now(), summary=summary,
                         validation=validation, commit=commit.strip(), error=None)
            return self._save_batch(conn, batch)

    def setting(self, key, value=None):
        with self._transaction() as conn:
            if value is not None:
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
