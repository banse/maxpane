"""Archiving the superseded curator exports and writing the published ones.

Every test here runs against ``tmp_path``.  Nothing in this file may name a
real home directory: ``archive_and_write`` takes ``root`` as a required
parameter precisely so a test cannot reach one by accident, and
``test_the_module_can_never_reach_a_real_home_directory`` scans the module's
source to keep it that way.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from maxpane_dashboard.data.curator_archive import (
    _ARCHIVED,
    ArchiveResult,
    CLEANED_LIST_NAME,
    MANIFEST_NAME,
    RAW_LIST_NAME,
    SLOT_NAME,
    archive_and_write,
    archive_key,
)
from maxpane_dashboard.data.curator_list_source import load_export_list
from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS


NOW = 1787900000.0
VERSION = "2026-08-25-sybilkit-0.2.0"
OLD_VERSION = "2026-08-19-sybilkit-0.1.1"
#: The other half of a published analysis's identity.  The archive directory
#: is named for BOTH, so a republish under one id cannot be mistaken for the
#: analysis it replaces -- see `archive_key`.
CONTENT_HASH = "486c7787fded341765b11c178916b237b46dc7c09e486931758c179af3bf2f9f"
REPUBLISHED_HASH = "9c5a1ef4882e84328bfc13da235b4d7d08f7c9fa3eebd4cf8eaab92ecc4ac616"
KEY = archive_key(VERSION, CONTENT_HASH)
REPUBLISHED_KEY = archive_key(VERSION, REPUBLISHED_HASH)


def _address(number: int) -> str:
    return f"0x{number:040x}"


def _published_row(rank: int, *, status: str = "clean", **over) -> dict:
    """One row of the published ``/list/export`` payload.

    ``link_conf`` defaults to the 0.1.1 legacy standing that *contradicts*
    ``status`` on a quarter of the live clean list, and ``name`` is always
    populated -- both are payload fields this module must never copy.
    """
    row = {
        "rank": rank,
        "address": _address(rank),
        "points": 100_000 - rank,
        "credit_eth": float(rank),
        "tx_count": rank,
        "flagged": status != "clean",
        "name": "payload.eth",
        "weight_eth": float(rank) * 2.0,
        "first_hour": rank % 24,
        "first_index": rank,
        "link_conf": "high",
        "version": VERSION,
        "cluster_id": None if status == "clean" else 1,
        "status": status,
        "risk": "independent" if status == "clean" else "critical",
        "evidence_band": "none" if status == "clean" else "high",
        "member_families": [],
        "member_family_count": 0,
        "under_review": status == "review",
    }
    row.update(over)
    return row


def _rows() -> list[dict]:
    """Ten published rows: 1,3,5,7,9 clean; 2,6,10 flagged; 4,8 review."""
    statuses = {
        1: "clean", 2: "flagged", 3: "clean", 4: "review", 5: "clean",
        6: "flagged", 7: "clean", 8: "review", 9: "clean", 10: "flagged",
    }
    return [_published_row(rank, status=status) for rank, status in statuses.items()]


def _bands() -> dict[str, str]:
    """What ``bands_by_address`` would return for :func:`_rows`."""
    return {
        _address(2): "high",
        _address(4): "review",
        _address(6): "low",
        _address(8): "review",
        _address(10): "high",
        _address(1): "clean",
        _address(3): "clean",
        _address(5): "clean",
        _address(7): "clean",
        _address(9): "clean",
    }


def _slot(*, archived_version: str | None = None) -> dict:
    published = {"version_id": OLD_VERSION, "content_hash": "deadbeef"}
    if archived_version is not None:
        published["archived_version"] = archived_version
    return {"groups": [], "clean_ranks": {}, "published": published}


def _seed_exports(
    root: Path,
    *,
    names: dict[str, str] | None = None,
    skip: tuple[str, ...] = (),
) -> dict[str, bytes]:
    """Write the seven superseded export files.  Returns their exact bytes.

    *skip* leaves a name unwritten, which is how a test reaches the archive
    steps that sit BEHIND the published pair's own gate.
    """
    names = names or {}
    old_raw = [
        {
            "rank": rank,
            "address": _address(rank),
            "points": 1,
            "credit_eth": 1.0,
            "tx_count": 1,
            "flagged": False,
            "name": None,
            "weight_eth": 1.0,
            "first_hour": 0,
            "first_index": rank,
            "link_conf": "clean",
        }
        for rank in range(1, 11)
    ]
    old_raw_enriched = [
        {**row, "name": names.get(row["address"])} for row in old_raw
    ]
    old_clean = [
        {
            "clean_rank": index,
            "address": _address(rank),
            "points": 1,
            "credit_eth": 1.0,
            "name": None,
            "weight_eth": 1.0,
            "tx_count": 1,
            "first_hour": 0,
            "first_index": rank,
        }
        for index, rank in enumerate((1, 2, 3, 4), start=1)
    ]
    old_clean_enriched = [
        {**row, "name": names.get(row["address"])} for row in old_clean
    ]
    contents = {
        "curator_cleaned_list.json": json.dumps(old_clean, indent=1),
        "curator_cleaned_list.enriched.json": json.dumps(old_clean_enriched, indent=1),
        "curator_raw_list.json": json.dumps(old_raw, indent=1),
        "curator_raw_list.enriched.json": json.dumps(old_raw_enriched, indent=1),
        "curator_clean_list.json": json.dumps(old_clean, indent=1),
        "curator_clean_list.csv": "clean_rank,address\n1,0x0\n",
        "curator_lists.json": json.dumps({"legacy": True}, indent=1),
    }
    written: dict[str, bytes] = {}
    for name, text in contents.items():
        if name in skip:
            continue
        path = root / name
        path.write_text(text, encoding="utf-8")
        written[name] = path.read_bytes()
    return written


def _run(root: Path, **over):
    kwargs = {
        "version_id": VERSION,
        "content_hash": CONTENT_HASH,
        "rows": _rows(),
        "bands": _bands(),
        "previous_slot": _slot(),
        "now": NOW,
    }
    kwargs.update(over)
    return archive_and_write(root, **kwargs)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Move, never delete
# ---------------------------------------------------------------------------


#: The two names the archive vacates and this module immediately refills.
REWRITTEN = ("curator_raw_list.json", "curator_cleaned_list.json")


def test_the_old_exports_are_moved_and_still_exist_afterwards(tmp_path):
    before = _seed_exports(tmp_path)

    result = _run(tmp_path)

    archive = tmp_path / "archive" / KEY
    for name, payload in before.items():
        if name not in REWRITTEN:
            assert not (tmp_path / name).exists(), f"{name} was left behind in the root"
        assert (archive / name).read_bytes() == payload, f"{name} is not byte-identical"
        assert name in result.archived
    for name in REWRITTEN:
        assert (tmp_path / name).read_bytes() != before[name], f"{name} was not rewritten"
    assert result.failed == ()


def test_the_archived_copy_is_the_same_file_not_a_copy(tmp_path):
    """A move preserves the inode; a copy-then-delete does not.

    This is the mechanism assertion the byte-identity test deliberately does
    not make -- it is what a ``shutil.copy`` + ``os.unlink`` rewrite reddens.
    """
    _seed_exports(tmp_path)
    inodes = {
        name: (tmp_path / name).stat().st_ino
        for name in _ARCHIVED
        if (tmp_path / name).exists()
    }
    assert inodes, "the fixture seeded nothing"

    _run(tmp_path)

    archive = tmp_path / "archive" / KEY
    for name, inode in inodes.items():
        assert (archive / name).stat().st_ino == inode, f"{name} was copied, not moved"


def test_a_missing_file_is_not_an_error(tmp_path):
    (tmp_path / "curator_lists.json").write_text("{}", encoding="utf-8")

    result = _run(tmp_path)

    assert result.failed == ()
    assert result.archived == ("curator_lists.json", "clusters_slot.json")
    assert (tmp_path / "archive" / KEY / "curator_lists.json").exists()


def test_the_superseded_slot_is_written_into_the_archive(tmp_path):
    result = _run(tmp_path, previous_slot=_slot())

    stored = _read(tmp_path / "archive" / KEY / "clusters_slot.json")
    assert stored == _slot()
    assert "clusters_slot.json" in result.archived


def test_no_slot_is_written_when_there_is_nothing_to_supersede(tmp_path):
    result = _run(tmp_path, previous_slot=None)

    assert not (tmp_path / "archive" / KEY / "clusters_slot.json").exists()
    assert "clusters_slot.json" not in result.archived


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


def test_the_manifest_records_what_moved_and_what_it_superseded(tmp_path):
    before = _seed_exports(tmp_path)

    _run(tmp_path)

    manifest = _read(tmp_path / "archive" / KEY / "manifest.json")
    assert manifest["archived_at"] == NOW
    assert manifest["new_version"] == VERSION
    assert manifest["superseded_version"] == OLD_VERSION

    entries = {entry["name"]: entry for entry in manifest["files"]}
    assert set(before) <= set(entries)
    for name, payload in before.items():
        assert entries[name]["bytes"] == len(payload)
        assert entries[name]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert "manifest.json" not in entries


def test_the_manifest_supersedes_nothing_when_the_slot_names_no_version(tmp_path):
    _run(tmp_path, previous_slot=None)

    manifest = _read(tmp_path / "archive" / KEY / "manifest.json")
    assert manifest["superseded_version"] is None


# ---------------------------------------------------------------------------
# The new lists
# ---------------------------------------------------------------------------


def test_the_new_cleaned_list_is_ranked_contiguously_from_one(tmp_path):
    _run(tmp_path)

    rows = _read(tmp_path / "curator_cleaned_list.json")
    assert [row["clean_rank"] for row in rows] == [1, 2, 3, 4, 5]
    assert [row["address"] for row in rows] == [_address(n) for n in (1, 3, 5, 7, 9)]


def test_the_new_cleaned_list_is_accepted_by_load_export_list(tmp_path):
    _run(tmp_path)

    written = _read(tmp_path / "curator_cleaned_list.json")
    result = load_export_list(
        tmp_path,
        cleaned=True,
        expected_count=len(written),
        live_rows=[],
        you_row=None,
    )

    assert result.complete is True, f"rejected: {result.reason}"
    assert result.reason is None
    assert [row["clean_rank"] for row in result.rows] == [1, 2, 3, 4, 5]


def test_the_new_raw_list_is_accepted_by_load_export_list(tmp_path):
    _run(tmp_path)

    written = _read(tmp_path / "curator_raw_list.json")
    result = load_export_list(
        tmp_path,
        cleaned=False,
        expected_count=len(written),
        live_rows=[],
        you_row=None,
    )

    assert result.complete is True, f"rejected: {result.reason}"
    assert [row["rank"] for row in result.rows] == list(range(1, 11))


def test_the_raw_rows_carry_our_band_and_never_the_payloads_link_conf(tmp_path):
    _run(tmp_path)

    rows = {row["address"]: row for row in _read(tmp_path / "curator_raw_list.json")}
    assert all(row["link_conf"] == "high" for row in _rows()), "fixture lost its trap"

    assert rows[_address(1)]["link_conf"] == "clean"
    assert rows[_address(2)]["link_conf"] == "high"
    assert rows[_address(4)]["link_conf"] == "review"
    assert rows[_address(6)]["link_conf"] == "low"


def test_a_band_we_do_not_hold_is_none_and_never_the_payloads_word(tmp_path):
    bands = _bands()
    del bands[_address(3)]

    _run(tmp_path, bands=bands)

    rows = {row["address"]: row for row in _read(tmp_path / "curator_raw_list.json")}
    assert rows[_address(3)]["link_conf"] is None


def test_row_fields_are_exactly_the_frozen_column_tuples(tmp_path):
    _run(tmp_path)

    raw = _read(tmp_path / "curator_raw_list.json")
    cleaned = _read(tmp_path / "curator_cleaned_list.json")
    assert raw and cleaned

    for row in raw:
        assert tuple(row) == CURATOR_ROW_KEYS["leaderboard_rows"]
    for row in cleaned:
        assert tuple(row) == CURATOR_ROW_KEYS["clean_list_rows"]


def test_nothing_is_archived_when_the_published_rows_yield_no_list(tmp_path):
    before = _seed_exports(tmp_path)

    result = _run(tmp_path, rows=[])

    assert result.archived == ()
    assert result.written == ()
    for name, payload in before.items():
        assert (tmp_path / name).read_bytes() == payload
    assert not (tmp_path / "archive").exists()


# ---------------------------------------------------------------------------
# ENS carry-across
# ---------------------------------------------------------------------------


def test_ens_names_are_carried_across_by_address(tmp_path):
    _seed_exports(
        tmp_path,
        names={_address(1): "one.eth", _address(3): "three.eth"},
    )

    _run(tmp_path)

    raw = {row["address"]: row for row in _read(tmp_path / "curator_raw_list.json")}
    cleaned = {row["address"]: row for row in _read(tmp_path / "curator_cleaned_list.json")}
    assert raw[_address(1)]["name"] == "one.eth"
    assert raw[_address(3)]["name"] == "three.eth"
    assert cleaned[_address(1)]["name"] == "one.eth"


def test_a_name_that_matches_no_address_is_dropped_not_guessed(tmp_path):
    _seed_exports(tmp_path, names={_address(1): "one.eth"})
    stray = tmp_path / "curator_raw_list.enriched.json"
    rows = _read(stray)
    rows.append({**rows[0], "address": _address(999), "name": "stranger.eth"})
    stray.write_text(json.dumps(rows, indent=1), encoding="utf-8")

    _run(tmp_path)

    written = _read(tmp_path / "curator_raw_list.json")
    names = {row["address"]: row["name"] for row in written}
    assert names[_address(1)] == "one.eth"
    assert _address(999) not in names
    assert all(name is None for address, name in names.items() if address != _address(1))


# ---------------------------------------------------------------------------
# Idempotence and failure
# ---------------------------------------------------------------------------


def test_running_twice_for_one_version_archives_and_writes_nothing_the_second_time(tmp_path):
    _seed_exports(tmp_path)

    first = _run(tmp_path)
    assert first.written

    fingerprints = {
        path: path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    }

    second = _run(tmp_path, previous_slot=_slot(archived_version=KEY))

    assert second == ArchiveResult((), (), ())
    assert {
        path: path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    } == fingerprints


def test_a_version_id_that_would_escape_the_archive_is_refused(tmp_path):
    """The id names a directory and arrives from an HTTP service."""
    before = _seed_exports(tmp_path)

    for hostile in ("../../escaped", "..", "sybilkit/0.2.0", "", None):
        result = _run(tmp_path, version_id=hostile)

        assert result.archived == ()
        assert result.written == ()
        assert "curator_raw_list.json" in result.failed
        for name, payload in before.items():
            assert (tmp_path / name).read_bytes() == payload

    assert not (tmp_path / "archive").exists()
    assert not (tmp_path.parent / "escaped").exists()


def test_a_content_hash_that_would_escape_the_archive_is_refused(tmp_path):
    """The hash is joined onto the same path the id is, so it is checked the
    same way.

    Without this half, a service answering ``content_hash: "../../escaped"``
    would name the directory ``2026-08-25-sybilkit-0.2.0-../../escape``. The
    id guard cannot see it: the id is perfectly valid.
    """
    before = _seed_exports(tmp_path)

    for hostile in ("../../escaped", "..", "a/b", "", None, "short", "x" * 200):
        result = _run(tmp_path, content_hash=hostile)

        assert result.archived == ()
        assert result.written == ()
        assert "curator_raw_list.json" in result.failed
        for name, payload in before.items():
            assert (tmp_path / name).read_bytes() == payload

    assert not (tmp_path / "archive").exists()
    assert not (tmp_path.parent / "escaped").exists()


def test_one_version_id_republished_is_two_analyses_and_two_archives(tmp_path):
    """**The keystone.**  A rebuild under the same id is a different analysis.

    Keyed on the id alone, run 2 saw ``archived_version == version_id``,
    returned three empty tuples, and left ``root`` holding run 1's exports
    while the dashboard's analysis panels showed run 2's rows -- a stale list
    answering ``complete=True`` with no marker.  Keyed on the id AND the hash,
    run 2 gets its own directory, archives run 1's output into it and rewrites
    both lists.

    The `points` column is the discriminator: the two runs publish different
    numbers for the same wallet, so this asserts the ROWS moved, not merely
    that a function was called.
    """
    _seed_exports(tmp_path)

    first = _run(tmp_path)
    assert first.written == REWRITTEN
    assert _read(tmp_path / RAW_LIST_NAME)[0]["points"] == 99_999

    rebuilt = [dict(row, points=row["points"] + 1) for row in _rows()]
    second = _run(
        tmp_path,
        content_hash=REPUBLISHED_HASH,
        rows=rebuilt,
        previous_slot=_slot(archived_version=KEY),
    )

    assert second.written == REWRITTEN, "a republish is archived and rewritten"
    assert _read(tmp_path / RAW_LIST_NAME)[0]["points"] == 100_000
    # Two directories, and run 1's output is preserved inside the second.
    assert (tmp_path / "archive" / KEY).is_dir()
    assert (tmp_path / "archive" / REPUBLISHED_KEY).is_dir()
    assert (
        _read(tmp_path / "archive" / REPUBLISHED_KEY / RAW_LIST_NAME)[0]["points"]
        == 99_999
    )


def test_the_same_analysis_twice_is_still_archived_only_once(tmp_path):
    """The idempotence the compound key must not cost.

    Same id AND same hash is the SAME analysis, so the second call moves
    nothing and writes nothing -- exactly as it did when the key was the id
    alone.  This is the guard the republish fix could have disarmed, kept
    separate from the republish test so each can fail on its own.
    """
    _seed_exports(tmp_path)
    _run(tmp_path)
    fingerprints = {
        path: path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    }

    again = _run(tmp_path, previous_slot=_slot(archived_version=KEY))

    assert again == ArchiveResult((), (), ())
    assert {
        path: path.read_bytes()
        for path in sorted(tmp_path.rglob("*"))
        if path.is_file()
    } == fingerprints


def test_the_manifest_names_the_whole_content_hash(tmp_path):
    """The directory name carries twelve characters; the record carries all
    of them, so the archive identifies the exact bytes it holds."""
    _seed_exports(tmp_path)
    _run(tmp_path)

    manifest = _read(tmp_path / "archive" / KEY / MANIFEST_NAME)
    assert manifest["new_version"] == VERSION
    assert manifest["new_content_hash"] == CONTENT_HASH
    assert KEY.endswith(CONTENT_HASH[:12])


def test_a_second_run_without_the_slot_flag_never_touches_the_archived_originals(tmp_path):
    """The crash-between-archive-and-slot-save case.

    Nothing in this module writes ``archived_version``; a caller does, one
    task later.  A crash in between means run 2 sees the same version with the
    flag still absent -- and ``os.replace`` would silently move the NEWLY
    written published lists on top of the originals run 1 archived.
    """
    before = _seed_exports(tmp_path)
    archive = tmp_path / "archive" / KEY

    first = _run(tmp_path)
    assert first.written == REWRITTEN
    assert (archive / "curator_raw_list.json").read_bytes() == before["curator_raw_list.json"]
    archived_after_first = {
        path.name: path.read_bytes() for path in archive.iterdir() if path.is_file()
    }

    # No `archived_version` in the slot: the caller never got to record it.
    second = _run(tmp_path, previous_slot=_slot())

    assert {
        path.name: path.read_bytes() for path in archive.iterdir() if path.is_file()
    } == archived_after_first, "run 2 overwrote what run 1 archived"
    assert second.archived == ()
    assert second.written == ()
    for name in REWRITTEN:
        assert name in second.failed


def test_a_second_run_leaves_the_manifest_of_the_first_intact(tmp_path):
    """Reaches the manifest's own guard, which sits behind the pair gate.

    Seeded WITHOUT the published pair, so run 1 archives no
    ``curator_raw_list.json`` / ``curator_cleaned_list.json`` and run 2's pair
    gate stays open -- which is the only way the manifest's ``_claim`` is
    exercised rather than shadowed.
    """
    _seed_exports(tmp_path, skip=REWRITTEN)
    manifest_path = tmp_path / "archive" / KEY / MANIFEST_NAME

    _run(tmp_path)
    first = manifest_path.read_bytes()

    result = _run(tmp_path, previous_slot=_slot())

    assert manifest_path.read_bytes() == first
    assert MANIFEST_NAME in result.failed


def test_a_second_run_leaves_the_superseded_slot_of_the_first_intact(tmp_path):
    slot_path = tmp_path / "archive" / KEY / SLOT_NAME

    _run(tmp_path, previous_slot=_slot())
    first = slot_path.read_bytes()

    # The slot the caller would hand over on run 2 is the NEW one -- writing it
    # would replace the superseded payload the archive exists to preserve.
    _run(tmp_path, previous_slot={"published": {"version_id": VERSION}, "groups": []})

    assert slot_path.read_bytes() == first


def _pre_claim(tmp_path: Path, name: str) -> bytes:
    """Put an earlier archive of *name* in the way, and return its bytes."""
    archive = tmp_path / "archive" / KEY
    archive.mkdir(parents=True, exist_ok=True)
    path = archive / name
    path.write_text(f"an earlier archive of {name}", encoding="utf-8")
    return path.read_bytes()


def _assert_pair_refused(tmp_path: Path, before: dict[str, bytes], result) -> None:
    assert result.archived == (), "something moved"
    assert result.written == (), "something was written"
    assert set(result.failed) == set(REWRITTEN)
    for name, payload in before.items():
        assert (tmp_path / name).read_bytes() == payload, f"{name} changed"


def test_a_claimed_raw_destination_refuses_the_whole_pair(tmp_path):
    """The two lists are one dataset: neither moves if either cannot.

    With only the raw destination taken, a per-name guard refuses the raw move
    and allows the cleaned one -- leaving the OLD raw list in root beside a
    NEWLY written cleaned list, both of which ``load_export_list`` reports as
    complete.  Two halves that disagree and neither says so.
    """
    before = _seed_exports(tmp_path)
    guard = _pre_claim(tmp_path, RAW_LIST_NAME)

    result = _run(tmp_path)

    _assert_pair_refused(tmp_path, before, result)
    archive = tmp_path / "archive" / KEY
    assert (archive / RAW_LIST_NAME).read_bytes() == guard
    assert not (archive / CLEANED_LIST_NAME).exists()


def test_a_claimed_cleaned_destination_refuses_the_whole_pair(tmp_path):
    before = _seed_exports(tmp_path)
    guard = _pre_claim(tmp_path, CLEANED_LIST_NAME)

    result = _run(tmp_path)

    _assert_pair_refused(tmp_path, before, result)
    archive = tmp_path / "archive" / KEY
    assert (archive / CLEANED_LIST_NAME).read_bytes() == guard
    assert not (archive / RAW_LIST_NAME).exists()


def test_the_refused_pair_leaves_root_readable_as_one_coherent_dataset(tmp_path):
    """The point of refusing: what root still serves is the OLD pair, together."""
    _seed_exports(tmp_path)
    _pre_claim(tmp_path, RAW_LIST_NAME)

    _run(tmp_path)

    raw = _read(tmp_path / RAW_LIST_NAME)
    cleaned = _read(tmp_path / CLEANED_LIST_NAME)
    # The seeded pair is the old sweep's: 10 raw rows and 4 cleaned.
    assert len(raw) == 10 and len(cleaned) == 4
    for is_clean, count in ((False, len(raw)), (True, len(cleaned))):
        result = load_export_list(
            tmp_path,
            cleaned=is_clean,
            expected_count=count,
            live_rows=[],
            you_row=None,
        )
        assert result.complete is True, f"cleaned={is_clean}: {result.reason}"
    # Both halves come from the same sweep: every cleaned address is a raw one.
    assert {row["address"] for row in cleaned} <= {row["address"] for row in raw}


def _assert_recovered_pair(tmp_path: Path, result) -> None:
    """The run proceeded and root serves a coherent NEW pair."""
    assert result.written == REWRITTEN, result.failed
    raw = _read(tmp_path / RAW_LIST_NAME)
    cleaned = _read(tmp_path / CLEANED_LIST_NAME)
    assert len(raw) == 10 and len(cleaned) == 5, "not the published pair"
    for is_clean, count in ((False, len(raw)), (True, len(cleaned))):
        loaded = load_export_list(
            tmp_path,
            cleaned=is_clean,
            expected_count=count,
            live_rows=[],
            you_row=None,
        )
        assert loaded.complete is True, f"cleaned={is_clean}: {loaded.reason}"


def test_a_run_interrupted_after_the_cleaned_move_recovers_a_coherent_pair(tmp_path):
    """A taken destination is only a hazard while root still holds that name.

    ``_ARCHIVED`` moves the cleaned list FIRST, so this is where every natural
    interruption lands.  Root no longer holds the cleaned list, so nothing is
    left to move and no split is possible -- refusing here would strand the
    retry forever and leave a stale raw list presented as current with its
    counterpart missing, which is the very harm the gate exists to prevent.
    """
    before = _seed_exports(tmp_path)
    archive = tmp_path / "archive" / KEY
    archive.mkdir(parents=True)
    (tmp_path / CLEANED_LIST_NAME).rename(archive / CLEANED_LIST_NAME)

    result = _run(tmp_path)

    _assert_recovered_pair(tmp_path, result)
    assert result.failed == ()
    # The half the interrupted run had already saved is untouched, and the
    # half it had not is archived now.
    assert (archive / CLEANED_LIST_NAME).read_bytes() == before[CLEANED_LIST_NAME]
    assert (archive / RAW_LIST_NAME).read_bytes() == before[RAW_LIST_NAME]
    assert RAW_LIST_NAME in result.archived


def test_a_run_interrupted_after_the_whole_archive_step_recovers_both_lists(tmp_path):
    """Both destinations taken, root holding neither: still nothing to split."""
    before = _seed_exports(tmp_path)
    archive = tmp_path / "archive" / KEY
    archive.mkdir(parents=True)
    for name in _ARCHIVED:
        if (tmp_path / name).exists():
            (tmp_path / name).rename(archive / name)

    result = _run(tmp_path)

    _assert_recovered_pair(tmp_path, result)
    for name, payload in before.items():
        assert (archive / name).read_bytes() == payload, f"{name} was overwritten"


def test_an_already_archived_file_outside_the_pair_is_never_overwritten(tmp_path):
    """Reaches the move loop's own guard, which the pair gate otherwise shadows.

    Seeded without the published pair, so the pair gate stays open on run 2 and
    the per-name ``_claim`` is what has to stop the enriched file -- regenerated
    in ``root`` by ``load_export_list`` between the two runs -- from landing on
    top of the copy run 1 archived.
    """
    _seed_exports(tmp_path, skip=REWRITTEN)
    archive = tmp_path / "archive" / KEY
    name = "curator_raw_list.enriched.json"

    _run(tmp_path)
    archived_original = (archive / name).read_bytes()

    (tmp_path / name).write_text("a newer enrichment pass", encoding="utf-8")
    result = _run(tmp_path, previous_slot=_slot())

    assert (archive / name).read_bytes() == archived_original, "the archived copy moved"
    assert name in result.failed
    assert name not in result.archived
    # Refused, not lost: the newer file is still in root for the next attempt.
    assert (tmp_path / name).read_text(encoding="utf-8") == "a newer enrichment pass"


def test_a_mid_list_dropped_row_refuses_rather_than_voiding_the_raw_list(tmp_path):
    """A gap anywhere but the tail voids the whole complete raw list."""
    before = _seed_exports(tmp_path)
    rows = _rows()
    rows[4]["address"] = "0xNOTHEX" + "0" * 35  # rank 5, mid-list

    result = _run(tmp_path, rows=rows)

    assert result.archived == ()
    assert result.written == ()
    assert set(result.failed) == set(REWRITTEN)
    for name, payload in before.items():
        assert (tmp_path / name).read_bytes() == payload
    assert not (tmp_path / "archive").exists()


def test_two_rows_sharing_a_rank_are_refused(tmp_path):
    rows = _rows()
    rows[4]["rank"] = 4

    result = _run(tmp_path, rows=rows)

    assert result.written == ()
    assert set(result.failed) == set(REWRITTEN)


def test_a_payload_with_no_clean_status_never_writes_an_empty_cleaned_list(tmp_path):
    """What a renamed ``status`` field looks like from here."""
    before = _seed_exports(tmp_path)
    rows = [{k: v for k, v in row.items() if k != "status"} for row in _rows()]

    result = _run(tmp_path, rows=rows)

    assert result.written == ()
    assert "curator_cleaned_list.json" in result.failed
    for name, payload in before.items():
        assert (tmp_path / name).read_bytes() == payload


def test_a_dropped_tail_row_costs_the_row_and_still_leaves_a_usable_list(tmp_path):
    """The counterpart to the mid-list drop: a gap-free drop still publishes."""
    rows = _rows()
    rows.append(_published_row(11, address="0xNOTHEX" + "0" * 35))

    result = _run(tmp_path, rows=rows)

    assert result.written == REWRITTEN
    written = _read(tmp_path / "curator_raw_list.json")
    assert [row["rank"] for row in written] == list(range(1, 11))


def test_an_unwritable_archive_directory_does_not_raise(tmp_path):
    before = _seed_exports(tmp_path)
    (tmp_path / "archive").write_text("not a directory", encoding="utf-8")

    result = _run(tmp_path)

    assert isinstance(result, ArchiveResult)
    assert result.archived == ()
    assert set(before) <= set(result.failed)
    for name, payload in before.items():
        assert (tmp_path / name).read_bytes() == payload


def test_an_old_export_that_could_not_be_moved_is_never_overwritten(tmp_path):
    before = _seed_exports(tmp_path)
    (tmp_path / "archive").write_text("not a directory", encoding="utf-8")

    result = _run(tmp_path)

    assert (tmp_path / "curator_raw_list.json").read_bytes() == before["curator_raw_list.json"]
    assert (
        tmp_path / "curator_cleaned_list.json"
    ).read_bytes() == before["curator_cleaned_list.json"]
    assert result.written == ()
    assert "curator_raw_list.json" in result.failed
    assert "curator_cleaned_list.json" in result.failed


# ---------------------------------------------------------------------------
# The real published fixture, across the T5 -> T9 seam
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent.parent / "fixtures" / "curator" / "published"


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _analysis_payload() -> dict:
    """The slot-shaped analysis the manager hands to ``bands_by_address``.

    Assembled from the published fixture pair the way the real pipeline does:
    one group per cluster, its band from the publisher's own word, its review
    members indexed into it, and every ``status == "clean"`` address in
    ``clean_ranks``.
    """
    from maxpane_dashboard.data import curator_clusters as cc

    overview, export = _fixture("overview_trimmed.json"), _fixture("export_trimmed.json")
    rows = export["rows"]

    members: dict[int, list[str]] = {}
    reviews: dict[int, dict[str, list[str]]] = {}
    for row in rows:
        cluster_id = row.get("cluster_id")
        if not isinstance(cluster_id, int):
            continue
        members.setdefault(cluster_id, []).append(row["address"].lower())
        if row.get("status") == "review":
            reviews.setdefault(cluster_id, {})[row["address"].lower()] = []

    groups = [
        {
            "members": members.get(cluster["id"], []),
            "conf": cc.published_band(cluster),
            "review_members": reviews.get(cluster["id"], {}),
        }
        for cluster in overview["clusters"]
    ]
    clean_ranks = {
        row["address"].lower(): row["rank"] for row in rows if row.get("status") == "clean"
    }
    return {"groups": groups, "clean_ranks": clean_ranks}


def test_the_real_published_fixture_never_paints_the_legacy_standing_onto_the_clean_list(
    tmp_path,
):
    """The assertion this whole module exists for.

    The published rows carry a ``link_conf`` that is the 0.1.1 legacy standing.
    On the live dataset it calls 1,727 ``status: clean`` wallets ``high``; the
    trimmed fixture keeps 20 of exactly that contradiction.  Copying it would
    paint marks across a quarter of the new clean list.
    """
    from maxpane_dashboard.data import curator_clusters as cc

    rows = _fixture("export_trimmed.json")["rows"]
    bands = cc.bands_by_address(_analysis_payload())

    contradicting = [
        row for row in rows
        if row["status"] == "clean" and row["link_conf"] in ("high", "low")
    ]
    assert len(contradicting) == 20, "the fixture lost its contradiction trap"

    result = _run(tmp_path, rows=rows, bands=bands)
    assert result.written == REWRITTEN, result.failed

    written = {row["address"]: row for row in _read(tmp_path / "curator_raw_list.json")}
    for row in contradicting:
        assert written[row["address"]]["link_conf"] == "clean", (
            f"{row['address']} took the payload's {row['link_conf']!r}"
        )

    cleaned = {row["address"] for row in _read(tmp_path / "curator_cleaned_list.json")}
    assert {row["address"] for row in contradicting} <= cleaned


def test_the_real_published_fixture_round_trips_through_load_export_list(tmp_path):
    from maxpane_dashboard.data import curator_clusters as cc

    rows = _fixture("export_trimmed.json")["rows"]
    _run(tmp_path, rows=rows, bands=cc.bands_by_address(_analysis_payload()))

    raw = _read(tmp_path / "curator_raw_list.json")
    cleaned = _read(tmp_path / "curator_cleaned_list.json")
    assert len(raw) == len(rows)
    assert 0 < len(cleaned) < len(raw)

    for is_clean, count in ((False, len(raw)), (True, len(cleaned))):
        result = load_export_list(
            tmp_path,
            cleaned=is_clean,
            expected_count=count,
            live_rows=[],
            you_row=None,
        )
        assert result.complete is True, f"cleaned={is_clean} rejected: {result.reason}"

    assert [row["clean_rank"] for row in cleaned] == list(range(1, len(cleaned) + 1))
    assert [row["rank"] for row in raw] == [row["rank"] for row in rows]


# ---------------------------------------------------------------------------
# The two hard rules, asserted structurally
# ---------------------------------------------------------------------------


def _module_tree():
    import ast
    import inspect

    from maxpane_dashboard.data import curator_archive

    return ast.parse(inspect.getsource(curator_archive))


def _module_symbols() -> set[str]:
    """Every attribute name AND every bare name the module's code touches.

    Walked from the AST rather than grepped from the text so the module may
    write down the rules it obeys in its own docstrings -- a prose ban that
    reddens when the prose explains itself is a ban nobody can document.

    Bare ``ast.Name`` ids are in the set because attribute names alone are
    defeated by an import alias: ``from os import unlink; unlink(p)`` never
    produces an ``ast.Attribute`` at all.  ``getattr`` is itself banned below,
    which is what closes the ``getattr(os, "unlink")(p)`` spelling -- a string
    constant no name-based guard can see.
    """
    import ast

    symbols: set[str] = set()
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Attribute):
            symbols.add(node.attr)
        elif isinstance(node, ast.Name):
            symbols.add(node.id)
    return symbols


def _module_imports() -> set[str]:
    """Every module imported AND every symbol imported out of one.

    ``from os.path import expanduser`` names no module the old version of this
    helper would have recorded, and ``from os import environ`` names none
    either -- both were invisible to it.
    """
    import ast

    names: set[str] = set()
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
            names.update(alias.asname for alias in node.names if alias.asname)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
            names.update(alias.asname for alias in node.names if alias.asname)
    return names


def test_the_module_can_never_reach_a_real_home_directory():
    import inspect

    from maxpane_dashboard.data import curator_archive

    reachable = _module_symbols() | _module_imports()
    for forbidden in ("home", "expanduser", "environ", "getenv", "getattr"):
        assert forbidden not in reachable, f"curator_archive reaches for {forbidden}"

    signature = inspect.signature(curator_archive.archive_and_write)
    assert (
        signature.parameters["root"].default is inspect.Parameter.empty
    ), "root must be a required parameter with no default"


def test_the_module_never_deletes_and_never_reads_the_clock():
    reachable = _module_symbols() | _module_imports()
    for forbidden in ("unlink", "rmtree", "remove", "rmdir", "truncate", "getattr"):
        assert forbidden not in reachable, f"curator_archive calls {forbidden}"
    for clock in ("time", "datetime"):
        assert clock not in reachable, "the clock is injected, never read"
