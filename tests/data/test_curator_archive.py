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
    archive_and_write,
)
from maxpane_dashboard.data.curator_list_source import load_export_list
from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS


NOW = 1787900000.0
VERSION = "2026-08-25-sybilkit-0.2.0"
OLD_VERSION = "2026-08-19-sybilkit-0.1.1"


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


def _seed_exports(root: Path, *, names: dict[str, str] | None = None) -> dict[str, bytes]:
    """Write the seven superseded export files.  Returns their exact bytes."""
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
        path = root / name
        path.write_text(text, encoding="utf-8")
        written[name] = path.read_bytes()
    return written


def _run(root: Path, **over):
    kwargs = {
        "version_id": VERSION,
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

    archive = tmp_path / "archive" / VERSION
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

    archive = tmp_path / "archive" / VERSION
    for name, inode in inodes.items():
        assert (archive / name).stat().st_ino == inode, f"{name} was copied, not moved"


def test_a_missing_file_is_not_an_error(tmp_path):
    (tmp_path / "curator_lists.json").write_text("{}", encoding="utf-8")

    result = _run(tmp_path)

    assert result.failed == ()
    assert result.archived == ("curator_lists.json", "clusters_slot.json")
    assert (tmp_path / "archive" / VERSION / "curator_lists.json").exists()


def test_the_superseded_slot_is_written_into_the_archive(tmp_path):
    result = _run(tmp_path, previous_slot=_slot())

    stored = _read(tmp_path / "archive" / VERSION / "clusters_slot.json")
    assert stored == _slot()
    assert "clusters_slot.json" in result.archived


def test_no_slot_is_written_when_there_is_nothing_to_supersede(tmp_path):
    result = _run(tmp_path, previous_slot=None)

    assert not (tmp_path / "archive" / VERSION / "clusters_slot.json").exists()
    assert "clusters_slot.json" not in result.archived


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


def test_the_manifest_records_what_moved_and_what_it_superseded(tmp_path):
    before = _seed_exports(tmp_path)

    _run(tmp_path)

    manifest = _read(tmp_path / "archive" / VERSION / "manifest.json")
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

    manifest = _read(tmp_path / "archive" / VERSION / "manifest.json")
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


def test_a_row_whose_address_will_not_parse_costs_the_row(tmp_path):
    rows = _rows()
    rows.append(_published_row(11, address="0xNOTHEX" + "0" * 35))

    _run(tmp_path, rows=rows)

    written = _read(tmp_path / "curator_raw_list.json")
    assert [row["rank"] for row in written] == list(range(1, 11))


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

    second = _run(tmp_path, previous_slot=_slot(archived_version=VERSION))

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
# The two hard rules, asserted structurally
# ---------------------------------------------------------------------------


def _module_attributes() -> set[str]:
    """Every attribute NAME the module's code touches.

    Walked from the AST rather than grepped from the text so the module may
    write down the rules it obeys in its own docstrings -- a prose ban that
    reddens when the prose explains itself is a ban nobody can document.
    """
    import ast
    import inspect

    from maxpane_dashboard.data import curator_archive

    tree = ast.parse(inspect.getsource(curator_archive))
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def _module_imports() -> set[str]:
    import ast
    import inspect

    from maxpane_dashboard.data import curator_archive

    tree = ast.parse(inspect.getsource(curator_archive))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_the_module_can_never_reach_a_real_home_directory():
    import inspect

    from maxpane_dashboard.data import curator_archive

    touched = _module_attributes()
    for forbidden in ("home", "expanduser", "environ", "getenv"):
        assert forbidden not in touched, f"curator_archive reaches for .{forbidden}"

    signature = inspect.signature(curator_archive.archive_and_write)
    assert (
        signature.parameters["root"].default is inspect.Parameter.empty
    ), "root must be a required parameter with no default"


def test_the_module_never_deletes_and_never_reads_the_clock():
    touched = _module_attributes()
    for forbidden in ("unlink", "rmtree", "remove", "rmdir", "truncate"):
        assert forbidden not in touched, f"curator_archive calls .{forbidden}"
    assert "time" not in _module_imports(), "the clock is injected, never read"
