"""JUST SHIPPED -- deliveries, launch artifacts and published sites (Task 9)."""

from maxpane_dashboard.widgets.address import COPY_GLYPH
from maxpane_dashboard.widgets.surf.swarm_shipped import (
    COMPACT_WIDTH,
    EMPTY_LINE,
    FULL_WIDTH,
    SurfSwarmShipped,
    UNAVAILABLE_LINE,
)
from tests.widgets.surf_compositing import composite_lines

ADDR = "0x086f085ff62b33053bca76a9258380c59b74cdca"
TX = "0xc2cb3be4bf5c1bfc76cd3d6e4cdb62b0361411d758a5b0a2e13c6f83fd2d845b"
ROWS = [
    {"kind": "launch", "job_id": "5cdf977b", "label": "BazaarToken", "commit": "1794f6e6",
     "chain_id": 11155111, "address": ADDR, "tx_hash": TX, "ens_name": None,
     "cid": None, "at_ts": 1_789_000_000.0},
    {"kind": "site", "job_id": "7018907b", "label": "site-7018907b", "commit": None,
     "chain_id": None, "address": None, "tx_hash": TX,
     "ens_name": "site-7018907b.site.identitymd.eth",
     "cid": "bafybeigicvgrkurqm2mmpq7ar7jxdylycscnisdatwd2irigy7mkayprla",
     "at_ts": 1_789_000_500.0},
]


async def _shipped(size=(110, 12), **kwargs):
    kwargs.setdefault("swarm_shipped_rows", ROWS)
    # Fix round 1: a marker is now load-bearing for any content to render
    # (see swarm_shipped.py's own docstring -- it mirrors swarm_field.py's
    # own rule), so every test in this file except the empty/unavailable
    # one needs one present by default, the way swarm_field.py's own
    # ``_field()`` helper already does. The empty/unavailable test passes
    # its own value (or ``None``) explicitly and is unaffected.
    kwargs.setdefault("swarm_scores_as_of_hhmm", "04:06")
    lines = await composite_lines(SurfSwarmShipped, size, **kwargs)
    return "\n".join(lines)


async def test_a_deployed_contract_shows_its_address_with_the_copy_icon():
    text = await _shipped()
    assert COPY_GLYPH in text
    assert ADDR[:6].lower() in text.lower()


async def test_a_transaction_hash_gets_no_icon():
    text = await _shipped(swarm_shipped_rows=[dict(ROWS[0], address=None)])
    assert COPY_GLYPH not in text


async def test_a_site_row_names_its_ens():
    assert "site-7018907b.site" in await _shipped()


async def test_the_chain_is_named_for_a_launch_row():
    assert "SEPOLIA" in await _shipped()


async def test_an_empty_list_and_an_unread_list_differ():
    """Fix round 1 (2026-09-16): amended from the brief's first-draft
    version, which handed the widget ``swarm_shipped_rows=None`` for the
    unavailable case -- a value ``data/surf_swarm.shipped_rows`` can never
    actually produce (it always returns a ``list``, ``[]`` at the least, so
    that draft proved a branch production never reaches). Both calls now
    use the one state the real producer *does* emit for "nothing shipped"
    (``swarm_shipped_rows=[]``) and differ only in the marker
    (``swarm_scores_as_of_hhmm``), which is the actual discriminator
    between "read and empty" and "never read" -- see swarm_shipped.py's own
    docstring.
    """
    assert EMPTY_LINE in await _shipped(swarm_shipped_rows=[], swarm_scores_as_of_hhmm="04:06")
    assert "unavailable" in await _shipped(swarm_shipped_rows=[], swarm_scores_as_of_hhmm=None)


async def test_a_marker_absent_with_rows_still_present_shows_no_rows():
    """Task 11: the real producer can never hand this widget a marker-absent,
    rows-non-empty payload (``data/surf_swarm.shipped_rows`` always returns
    ``[]`` while ``SLOT_SWARM_SCORES`` is cold, per the module docstring's
    own *"Unread is not empty"* section) -- but a hand-edited or partially
    written cache file is third-party input too, and ``_render_rows``'s own
    marker check (mirroring the footer's ``_no_rows_line``) is what stops
    that malformed state from leaking real-looking rows onto the table while
    the footer says ``unavailable`` right next to them.

    This is the positive test that check never had: every other test in this
    file either sets a marker with real rows, or sets no marker with an
    empty list (the one state the real producer *does* emit for "never
    read"). Neither exercises ``_render_rows``'s own gate against a payload
    where the two disagree, which is exactly the shape a corrupted cache
    file could produce. Mutate the gate to drop the marker check (leaving
    only ``isinstance(rows, list)``) and this test reddens: the table would
    show a real row while the footer still says ``unavailable``.
    """
    text = await _shipped(swarm_shipped_rows=ROWS, swarm_scores_as_of_hhmm=None)
    assert "BazaarToken" not in text
    assert "site-7018907b" not in text
    assert "unavailable" in text


async def test_an_empty_string_marker_is_treated_as_no_marker():
    """Task 11 fix round 2: ``swarm_scores_as_of_hhmm=""`` is not a clock --
    treating it as one would let this panel claim a read happened while the
    title shows no time it happened at. Modelled directly on
    ``swarm_field.py``'s own test of the same name (the fix-round-2 bug that
    module already shipped and fixed once): the two panels share one
    ``_has_marker`` predicate shape and must fail for the same reason when
    it is weakened the same way.

    Before this test existed, all twelve other tests in this file stayed
    green against ``_has_marker`` weakened to ``isinstance(as_of, str)``
    (dropping the ``bool(as_of)`` half) -- none of them drove an empty
    string through the marker at all, so the discriminator this panel
    depends on was, in practice, unguarded here even though
    ``swarm_field.py``'s identical predicate already had this exact
    coverage.
    """
    text = await _shipped(swarm_shipped_rows=[], swarm_scores_as_of_hhmm="")
    assert UNAVAILABLE_LINE in text


# ---------------------------------------------------------------------------
# Beyond the brief: the priority order inside the ADDRESS / SITE column, the
# hoisted chain-word helper's own dash case, the no-bracket contract every
# swarm panel proves for its third-party cells, and the width tier -- the
# same four extensions Task 8 added to QUEUE/THROUGHPUT beyond their own
# given tests.
# ---------------------------------------------------------------------------

_DELIVERY_ROW = {
    "kind": "delivery", "job_id": "d1", "label": "skill:build-contract-project",
    "commit": "adf5d9d1", "chain_id": None, "address": None, "tx_hash": None,
    "ens_name": None, "cid": None, "at_ts": 1_789_000_900.0,
}


async def test_a_delivery_row_falls_back_to_its_commit():
    """No address, no ENS name, no tx hash on a ``delivery`` row -- the
    ADDRESS / SITE cell falls all the way to the commit SHA rather than
    going blank, and it carries no copy icon (a commit is neither an address
    nor a hash).
    """
    text = await _shipped(swarm_shipped_rows=[_DELIVERY_ROW])
    assert "adf5d9d1" in text
    assert COPY_GLYPH not in text


async def test_an_unknown_chain_id_renders_the_dash():
    row = dict(ROWS[0], chain_id=999999999)
    text = await _shipped(swarm_shipped_rows=[row])
    assert "—" in text
    assert "SEPOLIA" not in text and "MAINNET" not in text


async def test_a_site_row_with_no_chain_id_still_gets_the_dash_not_silence():
    """A ``site`` row's ``chain_id`` is always ``None`` -- the CHAIN column
    still prints the dash for it rather than an empty cell, because the
    column answers "which chain, if any" for every row, not only the ones
    that have one.
    """
    site_only = [row for row in ROWS if row["kind"] == "site"]
    text = await _shipped(swarm_shipped_rows=site_only)
    assert "—" in text


_HOSTILE_LABEL = "[/][red]PWNED[/] boom"


async def test_a_hostile_label_renders_with_no_literal_brackets():
    hostile = [dict(_DELIVERY_ROW, label=_HOSTILE_LABEL)]
    lines = await composite_lines(
        SurfSwarmShipped, (110, 12), swarm_shipped_rows=hostile,
        swarm_scores_as_of_hhmm="04:06", region_only=True,
    )
    region = "\n".join(lines)
    assert "[" not in region and "]" not in region
    assert "PWNED" in region


async def test_a_hostile_ens_name_renders_with_no_literal_brackets():
    hostile_site = dict(ROWS[1], ens_name="[/][red]PWNED[/]")
    lines = await composite_lines(
        SurfSwarmShipped, (110, 12), swarm_shipped_rows=[hostile_site],
        swarm_scores_as_of_hhmm="04:06", region_only=True,
    )
    region = "\n".join(lines)
    assert "[" not in region and "]" not in region
    assert "PWNED" in region


async def test_a_narrow_panel_sheds_the_when_column_and_says_widen():
    """Below :data:`FULL_WIDTH` the WHEN column is gone (never a stray
    ``??:??``) and the title's own marker agrees; CHAIN and ADDRESS / SITE,
    which are never dropped independently of each other, survive at both
    widths.

    ``at_ts=None`` makes ``_fmt.hhmm`` return the fixed sentinel ``"??:??"``
    (``ts <= 0`` short-circuits before any clock read) -- a deterministic
    **formatter output for a controlled degenerate input**, not a pinned
    threshold, so this stays a property assertion rather than depending on
    the test machine's timezone. The two widths are derived from the
    module's own constants rather than a hand-typed number, so a later
    re-sweep of either cannot make this test lie about which tier it is
    driving.
    """
    padding = SurfSwarmShipped._TITLE_PADDING_COLS
    full_width = FULL_WIDTH + padding + 5
    # One cell below the full threshold, not merely "somewhere below
    # FULL_WIDTH": at a narrower compact width a wrongly-full tier's WHEN
    # column is cut off by the panel's own edge, and a truncated ``??:`` is
    # not distinguishable in this assertion's own terms from a genuinely
    # absent column -- the same trap a container's own clipping sets for a
    # tier-selection bug. Right at the threshold there is no clipping
    # either way, so a mis-tiered column renders in full and the assertion
    # actually exercises the tier decision rather than incidental width
    # overflow.
    compact_width = FULL_WIDTH + padding - 1
    assert compact_width >= COMPACT_WIDTH + padding, (
        "the derived compact width falls below the compact tier's own floor"
    )

    row = [dict(ROWS[0], at_ts=None)]
    full_text = await _shipped((full_width, 12), swarm_shipped_rows=row)
    compact_text = await _shipped((compact_width, 12), swarm_shipped_rows=row)

    assert "SEPOLIA" in full_text
    assert "??:??" in full_text
    assert "‹" not in full_text

    assert "SEPOLIA" in compact_text
    assert "??:??" not in compact_text
    assert "‹" in compact_text
