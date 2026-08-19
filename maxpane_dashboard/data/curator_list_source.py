"""Select a complete local curator list export when it is trustworthy."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS


RAW_LIST_BASENAME = "curator_raw_list"
CLEANED_LIST_BASENAME = "curator_cleaned_list"


@dataclass(frozen=True)
class ExportListResult:
    """Rows selected for display and how that selection was made."""

    rows: Any
    complete: bool
    source_path: Path | None
    enriched_path: Path | None
    reason: str | None


def _fallback(rows: Any, reason: str) -> ExportListResult:
    return ExportListResult(rows, False, None, None, reason)


def _is_rank(value: Any, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _valid_address(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        return False
    try:
        int(value[2:], 16)
    except ValueError:
        return False
    return True


def _normalise_rows(
    value: Any,
    *,
    columns: tuple[str, ...],
    rank_key: str,
) -> list[dict] | None:
    if not isinstance(value, list):
        return None

    rows: list[dict] = []
    for expected_rank, value_row in enumerate(value, start=1):
        if not isinstance(value_row, dict):
            return None
        if not set(columns).issubset(value_row):
            return None
        if not _is_rank(value_row.get(rank_key), expected_rank):
            return None
        if not _valid_address(value_row.get("address")):
            return None
        rows.append({column: value_row[column] for column in columns})
    return rows


def _enrichment_by_address(
    rows: Any,
    you_row: Any,
    *,
    cleaned: bool,
    columns: tuple[str, ...],
    rank_key: str,
) -> dict[str, dict]:
    candidates = list(rows) if isinstance(rows, list) else []
    if isinstance(you_row, dict):
        candidates.append(you_row)

    enrichment: dict[str, dict] = {}
    for row in candidates:
        if not isinstance(row, dict) or not _valid_address(row.get("address")):
            continue
        if cleaned and not _is_rank(row.get(rank_key), row.get(rank_key)):
            continue
        address = row["address"].lower()
        enrichment[address] = {
            column: row[column]
            for column in columns
            if column not in (rank_key, "address")
            and column in row
            and row[column] is not None
        }
    return enrichment


def _write_enriched(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(rows, indent=1), encoding="utf-8")
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def load_export_list(
    directory: Path,
    *,
    cleaned: bool,
    expected_count: Any,
    live_rows: Any,
    you_row: Any,
) -> ExportListResult:
    """Return an enriched complete export, or the live slice unchanged."""
    if (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count < 0
    ):
        return _fallback(live_rows, "invalid_count")

    basename = CLEANED_LIST_BASENAME if cleaned else RAW_LIST_BASENAME
    source_path = directory / f"{basename}.json"
    try:
        exported = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _fallback(live_rows, "missing")
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _fallback(live_rows, "invalid_json")

    if not isinstance(exported, list):
        return _fallback(live_rows, "invalid_rows")
    if len(exported) > expected_count or (expected_count > 0 and not exported):
        return _fallback(live_rows, "count_mismatch")

    row_key = "clean_list_rows" if cleaned else "leaderboard_rows"
    rank_key = "clean_rank" if cleaned else "rank"
    columns = CURATOR_ROW_KEYS[row_key]
    rows = _normalise_rows(exported, columns=columns, rank_key=rank_key)
    if rows is None:
        return _fallback(live_rows, "invalid_rows")

    enrichment = _enrichment_by_address(
        live_rows,
        you_row,
        cleaned=cleaned,
        columns=columns,
        rank_key=rank_key,
    )
    for row in rows:
        row.update(enrichment.get(row["address"].lower(), {}))

    enriched_path = directory / f"{basename}.enriched.json"
    try:
        _write_enriched(enriched_path, rows)
    except OSError:
        return ExportListResult(rows, True, source_path, None, "write_failed")
    return ExportListResult(rows, True, source_path, enriched_path, None)


__all__ = [
    "CLEANED_LIST_BASENAME",
    "ExportListResult",
    "RAW_LIST_BASENAME",
    "load_export_list",
]
