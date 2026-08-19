"""Selection and enrichment of local complete curator-list exports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maxpane_dashboard.data.curator_list_source import load_export_list


RAW_COLUMNS = (
    "rank",
    "address",
    "points",
    "credit_eth",
    "tx_count",
    "flagged",
    "name",
    "weight_eth",
    "first_hour",
    "first_index",
    "link_conf",
)
CLEAN_COLUMNS = (
    "clean_rank",
    "address",
    "points",
    "credit_eth",
    "name",
    "weight_eth",
    "tx_count",
    "first_hour",
    "first_index",
)


def _address(number: int) -> str:
    return f"0x{number:040x}"


def _raw_row(rank: int) -> dict:
    return {
        "rank": rank,
        "address": _address(rank),
        "points": rank * 100,
        "credit_eth": float(rank),
        "tx_count": rank,
        "flagged": False,
        "name": None,
        "weight_eth": float(rank * 2),
        "first_hour": rank - 1,
        "first_index": rank,
        "link_conf": None,
    }


def _clean_row(rank: int) -> dict:
    raw = _raw_row(rank)
    return {
        "clean_rank": rank,
        "address": raw["address"],
        "points": raw["points"],
        "credit_eth": raw["credit_eth"],
        "name": raw["name"],
        "weight_eth": raw["weight_eth"],
        "tx_count": raw["tx_count"],
        "first_hour": raw["first_hour"],
        "first_index": raw["first_index"],
    }


@pytest.mark.parametrize(
    ("cleaned", "basename", "row_factory", "columns", "rank_key"),
    (
        (False, "curator_raw_list", _raw_row, RAW_COLUMNS, "rank"),
        (True, "curator_cleaned_list", _clean_row, CLEAN_COLUMNS, "clean_rank"),
    ),
)
def test_valid_matching_export_is_enriched_without_changing_the_original(
    tmp_path: Path,
    cleaned: bool,
    basename: str,
    row_factory,
    columns: tuple[str, ...],
    rank_key: str,
) -> None:
    exported = [row_factory(rank) for rank in range(1, 4)]
    original_path = tmp_path / f"{basename}.json"
    original_path.write_text(json.dumps(exported, indent=1), encoding="utf-8")
    original_bytes = original_path.read_bytes()

    live = row_factory(1)
    live.update(points=999, name="first.eth")
    you = row_factory(3)
    you.update(points=777, name="you.eth")

    result = load_export_list(
        tmp_path,
        cleaned=cleaned,
        expected_count=3,
        live_rows=[live],
        you_row=you,
    )

    assert result.complete is True
    assert result.reason is None
    assert result.source_path == original_path
    assert result.enriched_path == tmp_path / f"{basename}.enriched.json"
    assert result.rows[0]["points"] == 999
    assert result.rows[0]["name"] == "first.eth"
    assert result.rows[2]["points"] == 777
    assert result.rows[2]["name"] == "you.eth"
    assert [row[rank_key] for row in result.rows] == [1, 2, 3]
    assert all(tuple(row) == columns for row in result.rows)
    assert json.loads(result.enriched_path.read_text(encoding="utf-8")) == result.rows
    assert original_path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    ("file_value", "expected_count", "reason"),
    (
        (None, 3, "missing"),
        ("not json", 3, "invalid_json"),
        ({"rank": 1}, 3, "invalid_rows"),
        ([_raw_row(1), _raw_row(2)], 3, "count_mismatch"),
        ([_raw_row(1), _raw_row(3), _raw_row(2)], 3, "invalid_rows"),
        ([{key: value for key, value in _raw_row(1).items() if key != "points"}], 1, "invalid_rows"),
    ),
)
def test_invalid_or_incomplete_export_keeps_the_live_slice(
    tmp_path: Path,
    file_value,
    expected_count: int,
    reason: str,
) -> None:
    if file_value is not None:
        path = tmp_path / "curator_raw_list.json"
        if isinstance(file_value, str):
            path.write_text(file_value, encoding="utf-8")
        else:
            path.write_text(json.dumps(file_value), encoding="utf-8")
    live_rows = [_raw_row(1)]

    result = load_export_list(
        tmp_path,
        cleaned=False,
        expected_count=expected_count,
        live_rows=live_rows,
        you_row=None,
    )

    assert result.rows is live_rows
    assert result.complete is False
    assert result.reason == reason
    assert result.enriched_path is None
    assert not (tmp_path / "curator_raw_list.enriched.json").exists()


@pytest.mark.parametrize("expected_count", (None, True, -1, 3.0, "3"))
def test_untrusted_authoritative_count_never_selects_an_export(
    tmp_path: Path,
    expected_count,
) -> None:
    (tmp_path / "curator_raw_list.json").write_text(
        json.dumps([_raw_row(rank) for rank in range(1, 4)]),
        encoding="utf-8",
    )
    live_rows = [_raw_row(1)]

    result = load_export_list(
        tmp_path,
        cleaned=False,
        expected_count=expected_count,
        live_rows=live_rows,
        you_row=None,
    )

    assert result.rows is live_rows
    assert result.complete is False
    assert result.reason == "invalid_count"


def test_clean_export_ignores_a_you_row_that_did_not_survive_cleaning(
    tmp_path: Path,
) -> None:
    rows = [_clean_row(rank) for rank in range(1, 3)]
    (tmp_path / "curator_cleaned_list.json").write_text(
        json.dumps(rows), encoding="utf-8"
    )
    you = _raw_row(2)
    you.update(points=999, name="removed.eth")

    result = load_export_list(
        tmp_path,
        cleaned=True,
        expected_count=2,
        live_rows=[],
        you_row=you,
    )

    assert result.complete is True
    assert result.rows[1]["points"] == rows[1]["points"]
    assert result.rows[1]["name"] is None


def test_export_enrichment_never_copies_unknown_live_fields(tmp_path: Path) -> None:
    exported = [_raw_row(1)]
    (tmp_path / "curator_raw_list.json").write_text(
        json.dumps(exported), encoding="utf-8"
    )
    live = {**_raw_row(1), "private_note": "not part of the frozen schema"}

    result = load_export_list(
        tmp_path,
        cleaned=False,
        expected_count=1,
        live_rows=[live],
        you_row=None,
    )

    assert set(result.rows[0]) == set(RAW_COLUMNS)
    assert "private_note" not in result.rows[0]
