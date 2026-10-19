"""Exercise routing without sockets or real queue delivery."""
import json
import subprocess
from uuid import uuid4

import pytest

from change_requests.catalogue import CATALOGUE
from change_requests.store import Store
from change_requests.bridge import QueueBridge
from change_requests.server import Application


@pytest.fixture
def app(tmp_path):
    store = Store(tmp_path / "requests.db", CATALOGUE)
    store.setting("thread_id", str(uuid4()))
    bridge = QueueBridge(store, tmp_path, executable="/bin/echo",
                         runner=lambda *a, **kw: subprocess.CompletedProcess(a, 0, "Queued message", ""))
    return Application(store, bridge, port=8877)


def call(app, method, path, data=None, **headers):
    h = {"Host": "127.0.0.1:8877", "Origin": "http://127.0.0.1:8877",
         "Content-Type": "application/json", "X-CR-Token": app.csrf_token, **headers}
    status, mime, body = app.handle(method, path, h, json.dumps(data).encode() if data is not None else b"")
    return status, json.loads(body) if mime.startswith("application/json") else body


def draft(app):
    return call(app, "POST", "/api/notes", {"view": "boardroom", "kind": "card", "area": "agent",
                                           "text": "Literal <script> and $(echo nope)\nSecond line"})[1]


def submit(app):
    note = draft(app)
    body = {"request_id": str(uuid4()), "notes": [{"id": note["id"], "version": note["version"]}]}
    return body, call(app, "POST", "/api/batches", body)


def test_full_lifecycle_and_replay_only_queues_once(app):
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "Queued message", "")
    app.bridge.runner = run
    body, (status, batch) = submit(app)
    assert status == 201 and batch["status"] == "sent"
    assert call(app, "POST", "/api/batches", body)[0] == 200
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[:4] == ["/bin/echo", "queue", "--thread", app.store.setting("thread_id")]
    assert "--message" in argv and batch["id"] in argv[-1]
    assert kwargs.get("shell", False) is False and kwargs["timeout"] == 20
    assert call(app, "GET", "/api/state")[1]["archive"] == []
    app.store.claim(batch["id"])
    app.store.complete(batch["id"], "Grouped card fix", "2 checks passed", "abc123")
    state = call(app, "GET", "/api/state")[1]
    assert state["active_batch"] is None and state["archive"][0]["summary"] == "Grouped card fix"
    assert "<script>" in state["archive"][0]["notes"][0]["text"]


@pytest.mark.parametrize("headers", [{"Host": "evil.example:8877"},
    {"Origin": "https://evil.example"}, {"X-CR-Token": "bad"}, {"Content-Type": "text/plain"}])
def test_external_mutations_rejected_without_changing_drafts(app, headers):
    status, _ = call(app, "POST", "/api/notes", {}, **headers)
    assert status in (403, 415)
    assert app.store.state()["drafts"] == []


@pytest.mark.parametrize("failure,expected", [(subprocess.TimeoutExpired("codex", 20), "uncertain"),
                                             (OSError("not running"), "failed")])
def test_delivery_problem_remains_visible_retryable_and_not_archived(app, failure, expected):
    def fail(*a, **kw): raise failure
    app.bridge.runner = fail
    _, (_, batch) = submit(app)
    assert batch["status"] == expected and batch["error"]
    assert app.store.state()["archive"] == []
    app.bridge.runner = lambda *a, **kw: subprocess.CompletedProcess(a, 0, "Queued message", "")
    status, retry = call(app, "POST", f'/api/batches/{batch["id"]}/retry', {})
    assert status == 200 and retry["status"] == "sent" and retry["notes"] == batch["notes"]


def test_missing_session_does_not_freeze_drafts(app):
    app.store.setting("thread_id", "")
    body, (status, error) = submit(app)
    assert status == 409 and error["error"] == "session_missing"
    assert len(app.store.state()["drafts"]) == 1


def test_validation_and_private_paths(app):
    assert call(app, "GET", "/../../.env")[0] == 404
    assert call(app, "GET", "/api/batches/arbitrary/complete")[0] == 404
    assert call(app, "POST", "/api/notes", ["not an object"])[0] == 400
    assert call(app, "PATCH", "/api/notes/missing", {})[0] in (400, 404)
    status, _, body = app.handle("POST", "/api/notes", {"Host":"127.0.0.1:8877",
        "Origin":"http://127.0.0.1:8877","Content-Type":"application/json","X-CR-Token":app.csrf_token}, b"{")
    assert status == 400


def test_nonzero_queue_result_is_not_completion(app):
    app.bridge.runner = lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", "daemon unavailable")
    _, (_, batch) = submit(app)
    assert batch["status"] == "failed"
    assert app.store.state()["archive"] == []


def test_delivery_ack_does_not_overwrite_fast_processing(app):
    def receive(*args, **kwargs):
        batch = app.store.state()["active_batch"]
        app.store.claim(batch["id"])
        app.store.complete(batch["id"], "Processed", "Validated")
        return subprocess.CompletedProcess(args, 0, "Queued", "")
    app.bridge.runner = receive
    _, (_, batch) = submit(app)
    assert batch["status"] == "completed"
    assert app.store.state()["active_batch"] is None


def test_bound_static_assets_are_served_without_filesystem_traversal(app):
    for path in ("/", "/static/app.js", "/static/style.css"):
        status, body = call(app, "GET", path)
        assert status == 200 and body
    assert call(app, "GET", "/static/../store.py")[0] == 404


def test_boardroom_catalogue_includes_each_current_slot():
    from maxpane_dashboard.widgets.surfboard.rack import SLOTS
    entry = next(v for v in CATALOGUE if v["id"] == "boardroom")
    assert {a["id"] for a in entry["areas"]["card"]} == {s[0] for s in SLOTS}
