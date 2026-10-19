"""Persistent draft ownership and batch transitions, without external services."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest


CATALOGUE = [
    {"id": "boardroom", "label": "BOARDROOM", "areas": {
        "card": [{"id": "agent", "label": "AGENT"}],
        "content": [{"id": "layout", "label": "Layout"}],
    }},
    {"id": "market", "label": "MARKET", "areas": {
        "card": [{"id": "agent", "label": "Agent"}],
        "content": [{"id": "layout", "label": "Layout"}],
    }},
]


@pytest.fixture
def api():
    try:
        from change_requests.store import Error, Store
    except ModuleNotFoundError:
        pytest.fail("The persistent change-request store is not implemented")
    return Store, Error


@pytest.fixture
def store(tmp_path, api):
    return api[0](tmp_path / "data" / "requests.sqlite3", CATALOGUE)


def draft(store, **changes):
    return store.create({"view": "boardroom", "kind": "card", "area": "agent",
                         "text": "Make the seat state clearer", **changes})


def selected(*notes):
    return [{"id": note["id"], "version": note["version"]} for note in notes]


def submit(store, *notes, request_id=None):
    return store.submit(request_id or str(uuid4()), selected(*notes))[0]


def test_drafts_persist_plain_text_across_store_instances(tmp_path, api):
    path = tmp_path / "nested" / "requests.sqlite3"
    first = api[0](path, CATALOGUE)
    note = draft(first, text="  <script>alert('x')</script>\n[bold]literal[/bold]  ")
    assert note == {"id": note["id"], "view": "boardroom", "kind": "card",
                    "area": "agent", "text": "<script>alert('x')</script>\n[bold]literal[/bold]",
                    "version": 1}
    assert api[0](path, CATALOGUE).state() == {
        "drafts": [note], "active_batch": None, "archive": []}


@pytest.mark.parametrize("changes", [
    {"view": "unknown"}, {"kind": "bug"}, {"area": "unknown"},
    {"kind": "content", "area": "agent"}, {"text": " \n "},
    {"text": "x" * 20001}, {"text": 10}, {"view": []}, {"area": {}},
])
def test_invalid_draft_input_does_not_persist(store, api, changes):
    with pytest.raises(api[1]) as failure:
        draft(store, **changes)
    assert failure.value.status == 400
    assert failure.value.code
    assert store.state()["drafts"] == []


def test_text_limit_is_in_characters(store):
    assert len(draft(store, text="é" * 20000)["text"]) == 20000


def test_optimistic_edit_rejects_stale_other_connection(tmp_path, api):
    path = tmp_path / "requests.sqlite3"
    first, second = api[0](path, CATALOGUE), api[0](path, CATALOGUE)
    original = draft(first)
    edited = first.update(original["id"], {**original, "text": "New wording"})
    with pytest.raises(api[1]) as failure:
        second.update(original["id"], {**original, "text": "Stale wording"})
    assert failure.value.status == 409
    assert failure.value.current == edited
    assert edited["version"] == 2
    assert second.state()["drafts"] == [edited]


@pytest.mark.parametrize("version", [True, False, 0, -1, "1", 1.0, None])
def test_versions_must_be_positive_integers(store, api, version):
    note = draft(store)
    for operation in (
        lambda: store.update(note["id"], {**note, "version": version}),
        lambda: store.delete(note["id"], version),
        lambda: store.submit(str(uuid4()), [{"id": note["id"], "version": version}]),
    ):
        with pytest.raises(api[1]) as failure:
            operation()
        assert failure.value.status == 400
    assert store.state()["drafts"] == [note]


def test_delete_requires_current_version(store, api):
    original = draft(store)
    edited = store.update(original["id"], {**original, "text": "Changed"})
    with pytest.raises(api[1]) as failure:
        store.delete(original["id"], original["version"])
    assert failure.value.current == edited
    store.delete(edited["id"], edited["version"])
    assert store.state()["drafts"] == []


def test_missing_draft_returns_not_found(store, api):
    with pytest.raises(api[1]) as failure:
        store.delete(str(uuid4()), 1)
    assert failure.value.status == 404


def test_submit_freezes_selected_drafts_and_retains_unselected(store):
    first, second, retained = draft(store), draft(store, text="Second"), draft(store, text="Later")
    batch = submit(store, first, second)
    assert batch["status"] == "queued"
    assert batch["notes"] == [first, second]
    assert batch["groups"] == [{"view": "boardroom", "kind": "card", "area": "agent",
                                 "note_ids": [first["id"], second["id"]]}]
    assert batch["created_at"] and batch["completed_at"] is None
    assert batch["error"] is None
    assert store.state() == {"drafts": [retained], "active_batch": batch, "archive": []}


def test_stale_submission_is_atomic(store, api):
    first, second = draft(store), draft(store, text="Second")
    edited = store.update(second["id"], {**second, "text": "Updated"})
    with pytest.raises(api[1]) as failure:
        submit(store, first, second)
    assert failure.value.status == 409
    assert failure.value.current == edited
    assert store.state() == {"drafts": [first, edited], "active_batch": None, "archive": []}


@pytest.mark.parametrize("selection", [[], None, {}, [{"id": "no-uuid", "version": 1}]])
def test_invalid_selections_are_rejected(store, api, selection):
    with pytest.raises(api[1]) as failure:
        store.submit(str(uuid4()), selection)
    assert failure.value.status == 400
    assert store.state()["active_batch"] is None


def test_duplicate_selected_note_is_rejected(store, api):
    note = draft(store)
    with pytest.raises(api[1]) as failure:
        store.submit(str(uuid4()), selected(note, note))
    assert failure.value.status == 400
    assert store.state()["drafts"] == [note]


def test_missing_selected_note_does_not_remove_other_drafts(store, api):
    note = draft(store)
    with pytest.raises(api[1]) as failure:
        store.submit(str(uuid4()), [*selected(note), {"id": str(uuid4()), "version": 1}])
    assert failure.value.status in {404, 409}
    assert store.state()["drafts"] == [note]


@pytest.mark.parametrize("request_id", [None, "", "arbitrary", 12, True])
def test_submission_requires_uuid_request_id(store, api, request_id):
    note = draft(store)
    with pytest.raises(api[1]) as failure:
        store.submit(request_id, selected(note))
    assert failure.value.status == 400
    assert store.state()["drafts"] == [note]


def test_replay_returns_same_batch_before_and_after_completion(store):
    first, second = draft(store), draft(store, text="Second")
    request_id = str(uuid4())
    batch, created = store.submit(request_id.upper(), selected(first, second))
    assert created is True
    replay, created = store.submit(request_id, selected(second, first))
    assert replay == batch and created is False
    store.claim(batch["id"])
    completed = store.complete(batch["id"], "Implemented", "Unit tests passed")
    replay, created = store.submit(request_id, selected(first, second))
    assert replay == completed and created is False
    assert len(store.state()["archive"]) == 1


def test_request_id_cannot_be_reused_with_different_selection(store, api):
    note = draft(store)
    request_id = str(uuid4())
    batch = submit(store, note, request_id=request_id)
    with pytest.raises(api[1]) as failure:
        store.submit(request_id, [{"id": note["id"], "version": 2}])
    assert failure.value.status == 409
    assert store.get_batch(batch["id"]) == batch


def test_batch_snapshots_do_not_follow_input_or_return_value_mutations(store):
    note = draft(store)
    batch = submit(store, note)
    note["text"] = "Changed outside store"
    batch["notes"][0]["text"] = "Tampered return value"
    batch["groups"][0]["note_ids"].clear()
    persisted = store.get_batch(batch["id"])
    assert persisted["notes"][0]["text"] == "Make the seat state clearer"
    assert persisted["groups"][0]["note_ids"] == [note["id"]]


def test_groups_preserve_view_kind_and_area_boundaries(store):
    notes = [draft(store), draft(store, kind="content", area="layout"),
             draft(store, view="market"), draft(store, text="Another same-area note")]
    assert submit(store, *notes)["groups"] == [
        {"view": "boardroom", "kind": "card", "area": "agent", "note_ids": [notes[0]["id"], notes[3]["id"]]},
        {"view": "boardroom", "kind": "content", "area": "layout", "note_ids": [notes[1]["id"]]},
        {"view": "market", "kind": "card", "area": "agent", "note_ids": [notes[2]["id"]]},
    ]


def test_active_batch_blocks_submit_but_allows_new_drafts(store, api):
    batch = submit(store, draft(store))
    later = draft(store, text="Next batch")
    with pytest.raises(api[1]) as failure:
        submit(store, later)
    assert failure.value.status == 409
    assert store.state()["drafts"] == [later]
    assert store.state()["active_batch"] == batch
    store.claim(batch["id"])
    store.complete(batch["id"], "Applied", "Tests passed")
    assert submit(store, later)["notes"] == [later]


def test_concurrent_claim_has_exactly_one_winner(tmp_path, api):
    path = tmp_path / "requests.sqlite3"
    first, second = api[0](path, CATALOGUE), api[0](path, CATALOGUE)
    batch = submit(first, draft(first))
    barrier = Barrier(2)

    def claim(instance):
        barrier.wait(timeout=5)
        try:
            return instance.claim(batch["id"])["status"]
        except api[1] as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, [first, second]))
    assert sorted(results, key=str) == [409, "processing"]


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_submissions_create_only_one_active_batch(tmp_path, api, same_request):
    path = tmp_path / "requests.sqlite3"
    stores = [api[0](path, CATALOGUE), api[0](path, CATALOGUE)]
    notes = [draft(stores[0]), draft(stores[1], text="Second note")]
    request_id = str(uuid4())
    barrier = Barrier(2)

    def send(index):
        barrier.wait(timeout=5)
        try:
            return stores[index].submit(
                request_id if same_request or index == 0 else str(uuid4()),
                selected(notes[0] if same_request else notes[index]),
            )
        except api[1] as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(send, [0, 1]))
    successful = [result for result in results if isinstance(result, tuple)]
    assert sum(created for _, created in successful) == 1
    if same_request:
        assert len(successful) == 2
        assert successful[0][0] == successful[1][0]
    else:
        assert len(successful) == 1
        assert [result.status for result in results if isinstance(result, api[1])] == [409]
    state = stores[0].state()
    assert state["active_batch"] == successful[0][0]
    assert len(state["drafts"]) == 1
    assert state["archive"] == []


@pytest.mark.parametrize("status", ["queued", "delivering", "sent", "failed", "uncertain"])
def test_claim_accepts_delivery_acknowledgement_races(store, status):
    batch = submit(store, draft(store))
    if status != "queued":
        store.delivery(batch["id"], status, "Bridge unavailable" if status == "failed" else None)
    assert store.claim(batch["id"])["status"] == "processing"


def test_completion_requires_claim_and_evidence(store, api):
    batch = submit(store, draft(store))
    with pytest.raises(api[1]) as failure:
        store.complete(batch["id"], "Applied", "Tests passed")
    assert failure.value.status == 409
    store.claim(batch["id"])
    for summary, validation in [("", "Tests"), ("Work", " \n "), (None, "Tests")]:
        with pytest.raises(api[1]):
            store.complete(batch["id"], summary, validation)
    assert store.state()["archive"] == []
    completed = store.complete(batch["id"], " Applied ", " 52 tests passed ", "abc123")
    assert completed["status"] == "completed"
    assert completed["summary"] == "Applied"
    assert completed["validation"] == "52 tests passed"
    assert completed["commit"] == "abc123"
    assert completed["completed_at"]
    assert store.state() == {"drafts": [], "active_batch": None, "archive": [completed]}
    for operation in (lambda: store.claim(batch["id"]),
                      lambda: store.complete(batch["id"], "Again", "Again")):
        with pytest.raises(api[1]) as failure:
            operation()
        assert failure.value.status == 409


@pytest.mark.parametrize("status", ["delivering", "sent", "failed", "uncertain"])
def test_late_delivery_result_never_clobbers_processing_or_completed(store, status):
    batch = submit(store, draft(store))
    claimed = store.claim(batch["id"])
    assert store.delivery(batch["id"], status, "Late result") == claimed
    completed = store.complete(batch["id"], "Applied", "Validated")
    assert store.delivery(batch["id"], status, "Late result") == completed
    assert store.state()["archive"] == [completed]


def test_failed_delivery_keeps_snapshot_active_and_can_retry(store):
    note = draft(store)
    batch = submit(store, note)
    failed = store.delivery(batch["id"], "failed", "Executable missing")
    assert failed["error"] == "Executable missing"
    assert failed["notes"] == [note]
    assert store.state()["active_batch"] == failed
    assert store.state()["drafts"] == []
    retrying = store.delivery(batch["id"], "delivering")
    assert retrying["error"] is None


def test_delivery_cannot_mark_a_batch_completed(store, api):
    batch = submit(store, draft(store))
    with pytest.raises(api[1]) as failure:
        store.delivery(batch["id"], "completed")
    assert failure.value.status == 400
    assert store.state()["archive"] == []


def test_settings_persist_across_connections(tmp_path, api):
    path = tmp_path / "requests.sqlite3"
    first, second = api[0](path, CATALOGUE), api[0](path, CATALOGUE)
    assert first.setting("thread_id") is None
    first.setting("thread_id", "thread-123")
    second.setting("codex_path", "/Applications/Codex.app/Contents/Resources/codex")
    assert second.setting("thread_id") == "thread-123"
    assert first.setting("codex_path") == "/Applications/Codex.app/Contents/Resources/codex"
