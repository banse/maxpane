"""Assistant acknowledgement and session binding; no server or CLI subprocesses."""
import json
from pathlib import Path
from uuid import uuid4

import pytest

from change_requests import __main__ as cli
from change_requests.catalogue import CATALOGUE
from change_requests.store import Store


def run(monkeypatch, capsys, data, *args):
    monkeypatch.setattr("sys.argv", ["change_requests", "--data-dir", str(data), *args])
    cli.main()
    return capsys.readouterr().out


def test_assistant_reads_claims_and_closes_exact_round(tmp_path, monkeypatch, capsys):
    store = Store(tmp_path / "requests.db", CATALOGUE)
    note = store.create(dict(view="boardroom", kind="card", area="agent", text="A request"))
    batch, _ = store.submit(str(uuid4()), [{"id": note["id"], "version": 1}])
    assert json.loads(run(monkeypatch, capsys, tmp_path, "read", batch["id"]))["notes"] == [note]
    assert json.loads(run(monkeypatch, capsys, tmp_path, "claim", batch["id"]))["status"] == "processing"
    result = json.loads(run(monkeypatch, capsys, tmp_path, "complete", batch["id"],
                           "--summary", "Done by area", "--validation", "Verified", "--commit", "abc"))
    assert result["status"] == "completed" and result["commit"] == "abc"
    with pytest.raises(SystemExit):
        run(monkeypatch, capsys, tmp_path, "claim", batch["id"])


@pytest.mark.parametrize("interrupted", ["queued", "delivering"])
def test_serve_persists_exact_thread_and_recovers_interrupted_delivery(tmp_path, monkeypatch, capsys, interrupted):
    root_thread, unrelated_thread = str(uuid4()), str(uuid4())
    monkeypatch.setenv("CODEX_THREAD_ID", root_thread)
    apps = []
    monkeypatch.setattr(cli, "serve", apps.append)
    run(monkeypatch, capsys, tmp_path, "serve")
    assert apps[-1].store.setting("thread_id") == root_thread
    store = apps[-1].store
    note = store.create(dict(view="boardroom", kind="card", area="agent", text="Request"))
    batch, _ = store.submit(str(uuid4()), [{"id":note["id"],"version":1}])
    if interrupted == "delivering":
        store.delivery(batch["id"], "delivering")
    monkeypatch.setenv("CODEX_THREAD_ID", unrelated_thread)
    run(monkeypatch, capsys, tmp_path, "serve")
    assert apps[-1].store.setting("thread_id") == root_thread
    assert store.get_batch(batch["id"])["status"] == "uncertain"
    with pytest.raises(SystemExit):
        run(monkeypatch, capsys, tmp_path, "serve", "--thread", unrelated_thread)
    assert store.setting("thread_id") == root_thread


def test_invalid_thread_is_rejected_without_starting_server(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "serve", lambda app: pytest.fail("should not start"))
    with pytest.raises(SystemExit):
        run(monkeypatch, capsys, tmp_path, "serve", "--thread", "--latest")
