"""Move THE LIST's superseded exports aside and write the published ones.

The old ``curator_*_list`` files on disk were produced by the locally computed
sweep.  The published, immutable analysis disagrees with them -- it re-judges
thousands of wallets -- so the moment a new published version lands, the old
files are relocated into ``<root>/archive/<version-id>/`` and the complete
lists are rewritten from the published rows.  The record view is then complete
the moment it opens, and ``e`` re-exports the new data.

**Two rules govern this module, and both are about somebody's real files.**

*Every path is injected.*  ``root`` is a required parameter with no default:
this module never asks where a home directory is, never reads an environment
variable, and never assembles a cache path of its own.  A default here is how
a test written six months from now silently rewrites a real export.

*Relocate, never destroy.*  Files are moved -- ``os.replace`` within a
filesystem, ``shutil.move`` across one -- and no deletion primitive appears
anywhere below.  That alone is not enough, because ``os.replace`` *overwrites*
its destination without a word: a rename is a way to destroy a file as surely
as removing one.  So the rule is stated as a destination rule and enforced on
both sides -- **no file this module writes ever lands on top of one that is
already there**, in ``root`` or in the archive directory, with the single
named exception of its own ``.tmp`` scratch file.  Three consequences follow
deliberately:

* nothing already inside ``<root>/archive/<version-id>/`` is replaced.  A
  second run for a version whose ``archived_version`` never reached the slot
  -- a crash between the archive step and the slot save -- would otherwise
  move the freshly written published lists straight on top of the originals
  it archived a moment earlier.  See :func:`_claim`.
* an old export that could **not** be moved is never overwritten by its
  replacement.  The archive step and the write step share one filename, so a
  failed move would otherwise turn housekeeping into data loss; the write is
  skipped instead, the name is reported in ``failed``, and the user still has
  the file the old sweep left them.
* a write that fails part-way leaves its ``.tmp`` beside the destination
  rather than clearing it away.  The next attempt overwrites that temporary,
  and a stray temporary is a smaller price than a module that has learned how
  to delete.

Archiving is housekeeping; the analysis is the deliverable.  Nothing here
raises: every failure is logged, named in ``ArchiveResult.failed``, and
returned to a caller that carries on.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS

logger = logging.getLogger(__name__)


#: The superseded files, moved in this order into ``<root>/archive/<version>/``.
#: A file that is not there is not an error.
_ARCHIVED = (
    "curator_cleaned_list.json",
    "curator_cleaned_list.enriched.json",
    "curator_raw_list.json",
    "curator_raw_list.enriched.json",
    "curator_clean_list.json",
    "curator_clean_list.csv",
    "curator_lists.json",
)

#: Written into the archive rather than moved into it: the superseded slot
#: payload lives inside ``curator_cache.json``, not in a file of its own.
SLOT_NAME = "clusters_slot.json"

#: The record of the supersession.  Never listed among the files it records.
MANIFEST_NAME = "manifest.json"

ARCHIVE_DIRNAME = "archive"

RAW_LIST_NAME = "curator_raw_list.json"
CLEANED_LIST_NAME = "curator_cleaned_list.json"

#: Where the carried-over ENS names are read from, in precedence order.  These
#: are the files ``load_export_list`` writes, and they hold every name the
#: dashboard has *verified* -- 21 across the raw list and 9 across the cleaned
#: one on the live install.  Read before the archive step moves them.
_ENRICHED_SOURCES = (
    "curator_raw_list.enriched.json",
    "curator_cleaned_list.enriched.json",
)

#: A published version id NAMES A DIRECTORY under ``<root>/archive/``, and it
#: arrives from an HTTP service -- so it is checked before it is ever joined
#: onto a path.  One component, no separators, no walk upward: the leading
#: character must be alphanumeric, which is what rules out ``..`` and ``.``.
#: A version id that fails this is refused outright rather than sanitised,
#: because the only thing worse than not archiving is moving somebody's
#: exports to a directory a payload chose.
_SAFE_VERSION = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

#: The only band words a row may carry off this module.  ``bands_by_address``
#: emits exactly these; anything else is bad data and renders ``?`` (``None``)
#: rather than reaching a widget's glyph map as an unknown word.
_BAND_WORDS = ("high", "low", "review", "clean")


@dataclass(frozen=True)
class ArchiveResult:
    """What landed where.

    ``archived`` names the files placed into ``<root>/archive/<version>/`` --
    the moved exports plus :data:`SLOT_NAME`, never :data:`MANIFEST_NAME` (the
    record is not one of the things it records).  ``written`` names the new
    complete lists written into ``root``.  ``failed`` names everything that
    should have been one of those two and is not.
    """

    archived: tuple[str, ...] = ()
    written: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Value coercion.  Every input below is third-party: an HTTP payload, or an
# export file read back off disk after somebody may have edited it.
# ---------------------------------------------------------------------------


def _opt_int(value: Any) -> int | None:
    """An ``int`` or ``None``.  ``bool`` is not an int here."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _opt_float(value: Any) -> float | None:
    """A ``float`` or ``None``.  ``bool`` is not a number here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _opt_bool(value: Any) -> bool | None:
    """A ``bool`` or ``None`` -- never ``False`` for a value we could not read.

    ``flagged`` renders as a mark beside a wallet.  Coercing a missing or
    malformed value to ``False`` would draw the confident negative "this
    wallet is clean" out of a read that did not happen.
    """
    return value if isinstance(value, bool) else None


def _valid_address(value: Any) -> str | None:
    """Lowercased ``0x``-prefixed 40-hex address, or ``None``.

    A row whose address will not parse costs the ROW, never the write -- the
    rule ``curator_list_source`` and ``curator_clusters`` already apply to the
    same payload from their own side.
    """
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        return None
    try:
        int(value[2:], 16)
    except ValueError:
        return None
    return value.lower()


# ---------------------------------------------------------------------------
# The new lists, built from the published rows
# ---------------------------------------------------------------------------


def _valid_rows(rows: Any) -> list[tuple[int, str, Mapping]]:
    """``(rank, address, row)`` for every published row that parses, rank-ordered."""
    out: list[tuple[int, str, Mapping]] = []
    for row in rows if isinstance(rows, (list, tuple)) else ():
        if not isinstance(row, Mapping):
            continue
        address = _valid_address(row.get("address"))
        rank = _opt_int(row.get("rank"))
        if address is None or rank is None or rank < 1:
            continue
        out.append((rank, address, row))
    out.sort(key=lambda item: item[0])
    return out


def _band(bands: Any, address: str) -> str | None:
    """OUR band for *address*, or ``None``.

    Never the payload's own ``link_conf``: that field is the 0.1.1 legacy
    standing, and it disagrees with 0.2.0's ``status`` on 4,641 wallets --
    1,727 of them rows it calls ``high`` that the published analysis calls
    clean.  Copying it would paint marks across a quarter of the new clean
    list.  The band comes from ``curator_clusters.bands_by_address``, which is
    what every other surface in the dashboard grades off.
    """
    if not isinstance(bands, Mapping):
        return None
    value = bands.get(address)
    return value if value in _BAND_WORDS else None


def _raw_rows(
    valid: list[tuple[int, str, Mapping]],
    bands: Any,
    names: Mapping[str, str],
) -> list[dict]:
    """Every published row, with the published ``rank`` preserved.

    The rank is **not** renumbered around a dropped row.  A published rank is
    a wallet's real standing among 19,522, and shifting 19,000 of them up by
    one to close a gap would put a wrong number on the screen for almost
    everybody.  If a drop does break contiguity, ``_normalise_rows`` rejects
    the file and the view falls back to the capped live rows -- a visible
    degradation, which is the honest outcome for a payload we could not read
    whole.
    """
    columns = CURATOR_ROW_KEYS["leaderboard_rows"]
    out: list[dict] = []
    for rank, address, row in valid:
        values = {
            "rank": rank,
            "address": address,
            "points": _opt_int(row.get("points")),
            "credit_eth": _opt_float(row.get("credit_eth")),
            "tx_count": _opt_int(row.get("tx_count")),
            "flagged": _opt_bool(row.get("flagged")),
            "name": names.get(address),
            "weight_eth": _opt_float(row.get("weight_eth")),
            "first_hour": _opt_int(row.get("first_hour")),
            "first_index": _opt_int(row.get("first_index")),
            "link_conf": _band(bands, address),
        }
        out.append({column: values[column] for column in columns})
    return out


def _clean_rows(
    valid: list[tuple[int, str, Mapping]],
    names: Mapping[str, str],
) -> list[dict]:
    """The ``status == "clean"`` rows, renumbered ``1..N`` in published rank order.

    Re-ranking is mandatory rather than cosmetic: the published ``rank`` is the
    RAW rank and is full of gaps on the clean subset, and
    ``curator_list_source._normalise_rows`` requires ``clean_rank`` to equal
    its own ``enumerate(..., start=1)`` position for **every** row.  One gap
    and the whole file is rejected as ``count_mismatch``, silently falling back
    to the capped live rows.

    ``clean_rank`` is the survivor rank and is not a claim about raw standing:
    the two are rendered side by side ("#412 raw, #47 clean"), which is why the
    frozen column tuples give them separate names.
    """
    columns = CURATOR_ROW_KEYS["clean_list_rows"]
    out: list[dict] = []
    for _rank, address, row in valid:
        if row.get("status") != "clean":
            continue
        values = {
            "clean_rank": len(out) + 1,
            "address": address,
            "points": _opt_int(row.get("points")),
            "credit_eth": _opt_float(row.get("credit_eth")),
            "name": names.get(address),
            "weight_eth": _opt_float(row.get("weight_eth")),
            "tx_count": _opt_int(row.get("tx_count")),
            "first_hour": _opt_int(row.get("first_hour")),
            "first_index": _opt_int(row.get("first_index")),
        }
        out.append({column: values[column] for column in columns})
    return out


# ---------------------------------------------------------------------------
# Carrying the verified ENS names across
# ---------------------------------------------------------------------------


def _archive_dir(root: Path, version_id: str) -> Path:
    """``<root>/archive/<version-id>/``.  Only ever called with a checked id."""
    return root / ARCHIVE_DIRNAME / version_id


def _pair_blocked(directory: Path) -> str | None:
    """Is either half of the published pair already archived?  Then refuse both.

    ``_claim`` is per-NAME, and that is not enough on its own: the raw and the
    cleaned list are **one dataset**, written from one payload and read as a
    pair.  If one destination is taken and the other is free, the per-name
    guard refuses one move and allows the other -- so the old raw list stays in
    ``root`` beside a newly written cleaned list, and ``load_export_list``
    answers ``complete=True, reason=None`` for **both**.  That is a stale list
    presented as current, with no marker, and it is worse than a stale number
    on its own because the two halves disagree with each other and neither
    says so.

    Checked here, before anything moves, because refusing up front is the only
    version of this that cannot leave a half-state: a partial move cannot be
    unwound afterwards without this module learning to remove files.  ``root``
    keeps its previous coherent pair and the next sweep retries.
    """
    taken = [
        name
        for name in (RAW_LIST_NAME, CLEANED_LIST_NAME)
        if (directory / name).exists()
    ]
    if not taken:
        return None
    return f"{' and '.join(taken)} already archived under {directory.name}"


def _unusable(raw_rows: list[dict], clean_rows: list[dict]) -> str | None:
    """Why these lists must not replace the ones on disk -- or ``None``.

    Checked BEFORE anything moves, because the alternative is that the
    superseded exports are already in the archive by the time anyone notices.

    ``curator_list_source._normalise_rows`` enforces ``rank == enumerate(...,
    start=1)`` on the **raw** list too, not only ``clean_rank`` on the cleaned
    one.  So a single dropped row anywhere but the tail voids the entire
    complete raw list: the file is written, ``written`` names it a success, and
    ``load_export_list`` then rejects the whole thing as ``invalid_rows`` and
    falls back to the capped live rows -- with the previous complete list
    already moved away.  The gap is free to see from here, so it is seen here.

    The same assertion catches a duplicated rank, which would otherwise pass a
    length check and fail the same way.

    An empty cleaned list gets the raw list's own "no rows is a failure"
    treatment rather than being written: with a five-figure raw population,
    zero survivors is what a renamed ``status`` field looks like, not a
    result.  The two lists are one dataset, so half of it being unreadable
    means the pair on disk stays as it is.
    """
    if not raw_rows:
        return "the export yielded no rows at all"
    ranks = [row["rank"] for row in raw_rows]
    if ranks != list(range(1, len(ranks) + 1)):
        return "the ranks are not contiguous from 1 (a row was dropped or duplicated)"
    if not clean_rows:
        return "no row carries status 'clean'"
    return None


def _carried_names(root: Path) -> dict[str, str]:
    """Lowercase address -> verified ENS name, read off the enriched exports.

    Merged into the new files so hydration does not start over from zero on the
    next launch.  A name whose address matches nothing in the published rows is
    simply never looked up -- dropped, not guessed.  The payload's own ``name``
    field is not a source here: it is unverified third-party text, and an ENS
    name that has not passed the forward check lets any address claim
    ``vitalik.eth``.
    """
    names: dict[str, str] = {}
    for name in _ENRICHED_SOURCES:
        path = root / name
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.warning("curator archive: cannot read %s: %s", path, exc)
            continue
        if not isinstance(payload, list):
            continue
        for row in payload:
            if not isinstance(row, Mapping):
                continue
            address = _valid_address(row.get("address"))
            value = row.get("name")
            if address is None or not isinstance(value, str) or not value:
                continue
            names.setdefault(address, value)
    return names


# ---------------------------------------------------------------------------
# The archive step
# ---------------------------------------------------------------------------


def _safe_version(version_id: Any) -> bool:
    """Is *version_id* a name this module may join onto a path?"""
    return isinstance(version_id, str) and bool(_SAFE_VERSION.match(version_id))


def _archived_version(previous_slot: Any) -> str | None:
    """``published.archived_version`` from the held slot, or ``None``."""
    if not isinstance(previous_slot, Mapping):
        return None
    published = previous_slot.get("published")
    if not isinstance(published, Mapping):
        return None
    value = published.get("archived_version")
    return value if isinstance(value, str) else None


def _superseded_version(previous_slot: Any) -> str | None:
    """``published.version_id`` from the held slot -- the version being replaced."""
    if not isinstance(previous_slot, Mapping):
        return None
    published = previous_slot.get("published")
    if not isinstance(published, Mapping):
        return None
    value = published.get("version_id")
    return value if isinstance(value, str) else None


def _relocate(source: Path, destination: Path) -> None:
    """Move *source* onto *destination*.  Same filesystem, then across one."""
    try:
        os.replace(source, destination)
    except OSError:
        # EXDEV and friends: ``root`` and its archive subdirectory are the same
        # filesystem in every real install, so this is the belt for the case
        # where somebody has mounted one inside the other.
        shutil.move(str(source), str(destination))


def _digest(path: Path) -> tuple[int | None, str | None]:
    """``(bytes, sha256)`` for *path*, or ``(None, None)`` when it cannot be read."""
    digest = hashlib.sha256()
    size = 0
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(1 << 20):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        logger.warning("curator archive: cannot fingerprint %s: %s", path, exc)
        return None, None
    return size, digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    """Write *payload* as JSON, atomically against whatever is already there.

    The temporary lands beside the destination so the rename is within one
    directory, and a failure leaves the temporary rather than clearing it: this
    module does not take files away, and the next attempt overwrites it.
    """
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    os.replace(temporary, path)


def _claim(destination: Path, failed: list[str]) -> bool:
    """Is *destination* free to be written?  Records the refusal when it is not.

    **Nothing already inside the archive directory is ever overwritten.**
    ``os.replace`` clobbers an existing destination silently, and
    ``mkdir(exist_ok=True)`` lets this module refill a directory it already
    filled -- so without this guard a second run for a version whose
    ``archived_version`` never reached the slot (a crash between the archive
    and the slot save) would move the NEWLY WRITTEN published lists on top of
    the superseded originals, rewrite the manifest that recorded the other
    five, and report ``failed == ()``.

    On the live install those two originals are 5,284,457 and 2,043,639 bytes
    with no other copy: the ``.enriched.json`` siblings differ by SHA-256 and
    are not a backup.

    Applied uniformly to the moves, the slot and the manifest rather than as a
    ``mkdir(exist_ok=False)`` short-circuit, because a directory that exists is
    not proof that it is *complete* -- a run that crashed mid-archive leaves
    one behind with files still to move, and this guard lets that run finish
    without ever putting a byte on top of what the first one saved.
    """
    if not destination.exists():
        return True
    logger.warning(
        "curator archive: %s is already archived under %s; refusing to overwrite it",
        destination.name,
        destination.parent,
    )
    if destination.name not in failed:
        failed.append(destination.name)
    return False


def _archive(
    root: Path,
    version_id: str,
    previous_slot: Any,
    now: float,
) -> tuple[list[str], list[str]]:
    """Move the superseded files aside.  Returns ``(archived, failed)``."""
    archived: list[str] = []
    failed: list[str] = []
    entries: list[dict] = []

    present = [name for name in _ARCHIVED if (root / name).exists()]
    directory = _archive_dir(root, version_id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("curator archive: cannot create %s: %s", directory, exc)
        failed.extend(present)
        if previous_slot is not None:
            failed.append(SLOT_NAME)
        failed.append(MANIFEST_NAME)
        return archived, failed

    for name in present:
        destination = directory / name
        if not _claim(destination, failed):
            continue
        try:
            _relocate(root / name, destination)
        except Exception as exc:  # noqa: BLE001 -- housekeeping never escapes
            logger.warning("curator archive: cannot archive %s: %s", name, exc)
            failed.append(name)
            continue
        archived.append(name)
        size, sha256 = _digest(destination)
        entries.append({"name": name, "bytes": size, "sha256": sha256})

    if previous_slot is not None and _claim(directory / SLOT_NAME, failed):
        destination = directory / SLOT_NAME
        try:
            _write_json(destination, previous_slot)
        except Exception as exc:  # noqa: BLE001
            logger.warning("curator archive: cannot write %s: %s", destination, exc)
            failed.append(SLOT_NAME)
        else:
            archived.append(SLOT_NAME)
            size, sha256 = _digest(destination)
            entries.append({"name": SLOT_NAME, "bytes": size, "sha256": sha256})

    manifest = {
        "archived_at": now,
        "superseded_version": _superseded_version(previous_slot),
        "new_version": version_id,
        "files": entries,
    }
    if _claim(directory / MANIFEST_NAME, failed):
        try:
            _write_json(directory / MANIFEST_NAME, manifest)
        except Exception as exc:  # noqa: BLE001
            logger.warning("curator archive: cannot write the manifest: %s", exc)
            failed.append(MANIFEST_NAME)

    return archived, failed


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def archive_and_write(
    root: Path,
    *,
    version_id: str,
    rows: Any,
    bands: Any,
    previous_slot: Any,
    now: float,
) -> ArchiveResult:
    """Archive the superseded exports and write the published lists into *root*.

    *root* is the cache directory the caller owns -- there is no default, and
    nothing in this module computes one.  *now* is the caller's clock.

    Idempotent by version id: the caller records ``archived_version`` in the
    slot's ``published`` block, so a second call for a version already archived
    moves nothing and writes nothing and returns three empty tuples.

    Never raises.  A failed archive is logged, named in ``failed``, and the
    caller's sweep still succeeded.
    """
    if not _safe_version(version_id):
        logger.warning(
            "curator archive: %r is not a usable version id; nothing archived, "
            "nothing written",
            version_id,
        )
        return ArchiveResult(failed=(RAW_LIST_NAME, CLEANED_LIST_NAME))

    if _archived_version(previous_slot) == version_id:
        return ArchiveResult()

    names = _carried_names(root)
    valid = _valid_rows(rows)
    raw_rows = _raw_rows(valid, bands, names)
    clean_rows = _clean_rows(valid, names)

    unusable = _unusable(raw_rows, clean_rows) or _pair_blocked(
        _archive_dir(root, version_id)
    )
    if unusable is not None:
        # Built BEFORE anything moves, and checked before it too: moving the
        # user's usable lists aside to replace them with lists no consumer
        # will accept is the one irreversible thing this module could do.
        logger.warning(
            "curator archive: the published rows for %s are not a usable list "
            "(%s); nothing archived, nothing written",
            version_id,
            unusable,
        )
        return ArchiveResult(failed=(RAW_LIST_NAME, CLEANED_LIST_NAME))

    archived, failed = _archive(root, version_id, previous_slot, now)

    written: list[str] = []
    for name, payload in ((RAW_LIST_NAME, raw_rows), (CLEANED_LIST_NAME, clean_rows)):
        path = root / name
        if path.exists():
            # The superseded export is still sitting here, which means its move
            # failed.  Writing now would destroy the very file this module
            # exists to preserve.
            logger.warning(
                "curator archive: %s was not archived; leaving it rather than "
                "overwriting it",
                name,
            )
            if name not in failed:
                failed.append(name)
            continue
        try:
            _write_json(path, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("curator archive: cannot write %s: %s", name, exc)
            if name not in failed:
                failed.append(name)
        else:
            written.append(name)

    return ArchiveResult(tuple(archived), tuple(written), tuple(failed))


__all__ = [
    "ARCHIVE_DIRNAME",
    "ArchiveResult",
    "CLEANED_LIST_NAME",
    "MANIFEST_NAME",
    "RAW_LIST_NAME",
    "SLOT_NAME",
    "archive_and_write",
]
