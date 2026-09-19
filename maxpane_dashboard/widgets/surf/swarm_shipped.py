"""JUST SHIPPED: recent deliveries, launch artifacts, and ENS-named sites.

A ``DataTable`` panel on ``pool4u_stakers.py``'s shape (Task 9): a title
``Static``, a ``DataTable`` filling the rest of the panel on ``1fr``, and a
footer ``Static`` that carries the panel's own degraded-state sentences --
``pool4u_stakers.no_rows_line``'s idiom, adapted to two states instead of
three, since this panel has no *sweeping* state of its own to report (its
rows ride the swarm's detached scores sweep, not a fold with its own
in-flight marker).

Row shape (``data/surf_models.SURF_ROW_KEYS["swarm_shipped_rows"]``,
frozen): ``kind`` (``"delivery"`` / ``"launch"`` / ``"site"``), ``job_id``,
``label``, ``commit``, ``chain_id``, ``address``, ``tx_hash``, ``ens_name``,
``cid``, ``at_ts``.

Five columns, one identifying cell per row
-------------------------------------------
The brief names exactly five columns -- WHAT (kind), LABEL, CHAIN,
ADDRESS / SITE, WHEN -- and no sixth for ``commit`` or ``cid`` even though
both are frozen row fields. ``cid`` never renders anywhere on this panel;
there is no column budget for it and no test asks for it.

``commit`` does render, but not in a column of its own: a ``delivery`` row
carries no address, tx hash or ENS name at all (``data/surf_swarm.
shipped_rows`` sets all three ``None`` for that kind), so ADDRESS / SITE
would be permanently blank for every delivery row unless something filled
it -- and CLAUDE.md's own "Addresses and hashes" rule calls out a commit SHA
by name as needing plain-escaped-text treatment, which only makes sense if
something renders it. So the ADDRESS / SITE column is **one cell with a
priority order**, not four independent cells picked by kind:

1. a real **address** (``launch``) -- :func:`widgets.address.address_text`,
   whole, with its copy icon;
2. else an **ENS name** (``site``) -- the same helper, *as a label* over no
   backing address, so it gets the same hostile-text hardening
   (``address_text``'s own ``_clean_label``) without a copy icon, because
   there is no address to copy;
3. else a **transaction hash** (a ``launch`` row whose address is
   ``None`` -- a malformed or in-flight artifact) -- ``widgets.address.
   short_hex``, no icon, per the brief's own instruction;
4. else a **commit SHA** (``delivery``) -- plain escaped text, fitted on
   ``cell_len``, neither an address nor a hash;
5. else :data:`_fmt.DASH`.

No row shape actually offers two of these at once except ``launch`` (address
*and* tx hash together) and ``delivery`` (no ``chain_id`` but a real
``commit``), so the order only ever resolves one real ambiguity: a
``launch`` row with a null address (case 2 above) falls through to its own
tx hash rather than going blank, which is exactly what
``test_a_transaction_hash_gets_no_icon`` drives.

Three width tiers, not two (fix round 1, 2026-09-17)
------------------------------------------------------
``full`` (all five columns) and ``compact`` (WHEN dropped) are this panel's
own, from Task 9. A third, narrower ``tight`` tier was added when this body
moved to a 2x2 grid and JUST SHIPPED was given a **fixed** width rather than
the whole row: at that fixed width the panel would otherwise be stuck
between showing WHEN (impossible, the row lacks the columns for it, ever)
and not marking widen honestly for the width it is missing. ``tight`` keeps
WHEN dropped and additionally narrows the ADDRESS / SITE column to
:data:`TIGHT_ADDR_COLS` -- the address module's own absolute legibility
floor, below which ``short_hex``/``address_text`` clamp back up to it
regardless, so nothing narrower would render any differently. See
``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s own ``#:`` block in ``screens/surf.py``
for why this panel is the one asked to shed, and why the shed is
permanent on this body rather than a response to an unusually narrow
terminal.

The chain word is per row, never in the title (ruling, 2026-09-16)
--------------------------------------------------------------------
The design doc (``docs/superpowers/specs/2026-09-16-surf-swarm-view-design.md``
§5) puts the chain word in this panel's own title. The owner overruled that
for this task: this panel's rows **mix chains** -- launches are mostly
Sepolia, an abandoned one mainnet -- so one word in the title would be
confidently wrong for some of the rows under it. Each row therefore names
its own chain, from that row's own ``chain_id``, in the CHAIN column beside
whatever carries an address or a hash; the title carries no chain word at
all, matching ``swarm_field.py``/``swarm_queue.py``/``swarm_throughput.py``
(THROUGHPUT's own per-row chain word predates this panel and set the
precedent this one follows).

:func:`_swarm_chain.chain_word` is the same helper THROUGHPUT uses, hoisted
into its own module by this same task so the two panels share one map
instead of each restating ``data/surf_swarm._NETWORKS`` -- see
``_swarm_chain.py``'s own docstring for the reasoning. A hash or address is
never shown without its chain word beside it: even a ``site`` row (whose
``chain_id`` is always ``None``) gets the em dash in the CHAIN column,
because the whole point of the column is "which chain, if any, does this
row's own identifying detail live on" and silence there would read as an
omission rather than an honest "not applicable".

Unread is not empty -- and the marker is the only signal that says so
------------------------------------------------------------------------
``data/surf_swarm.shipped_rows`` is annotated ``-> list[dict[str, Any]]``
and every one of its four input loops is ``for x in <arg> or ()``; with a
cold slot all four arguments are ``None`` and it still returns ``[]`` (the
function ends ``return rows[:limit]``, never ``return None``).
``data/surf_manager.py`` (``_swarm_scores_keys``) publishes that value
directly. **``swarm_shipped_rows`` therefore never reaches this widget as
``None`` from the real producer** -- it is ``[]`` both when the sweep has
shipped nothing and when the sweep has never run, exactly the ambiguity
``swarm_field.py``'s own module docstring names for its row list, and a
gate keyed on ``rows is None`` cannot see that ambiguity at all: it would
make the unavailable state unreachable in production, through a cold start
and through any scores-tier outage alike, which is the curator rail bug
this repo's CLAUDE.md names by name -- a dead read and a real negative
rendering identically.

The discriminator that *does* exist is ``swarm_scores_as_of_hhmm``:
``_swarm_scores_keys`` sets it to ``entry.as_of_hhmm() if entry is not None
else None`` -- ``None`` exactly while ``SLOT_SWARM_SCORES`` has never been
read, a real time string once it has, independent of what the row list
happens to contain. So :func:`_no_rows_line` gates the same way
``swarm_field.py`` does: **no real marker (or a ``rows`` sentinel that is
somehow ``None`` anyway, tolerated defensively though the producer cannot
emit it) means unavailable, full stop, whatever the rows say; a marker
present with an empty list means a genuine empty read.** ``rows is None``
is no longer the discriminator anywhere in this module -- it is checked
only as an extra defensive branch, the way ``swarm_field.py`` keeps its own
``rows_input is None`` clause "so the widget stays honest if it is ever
handed that sentinel directly."

(Fix round 1, 2026-09-16: an earlier version of this module gated on
``rows is None`` alone, because the brief's own first-draft test never set
the marker in any of its three states, which made the marker
unobservable by that test. The test itself was the thing wrong -- it
handed the widget a ``None`` the real producer cannot emit, so it proved a
branch that production never reaches, one of this repo's own "tests that
cannot fail" shapes. The coordinator corrected the test rather than
accepting the gate it justified; see ``test_an_empty_list_and_an_unread_
list_differ`` for the amended version, which drives both states through the
marker with ``swarm_shipped_rows=[]`` in both calls.)

Third-party text, and the no-bracket contract
-----------------------------------------------
``label``, ``ens_name`` and ``commit`` are every one of them a string this
widget did not choose -- an agent's own job label, an ENS name someone
picked, or (in principle) a hand-crafted delivery record. ``label`` and
``commit`` are cleaned through ``_pool4.strip_tags`` before they reach a
cell -- dropping a complete ``[...]``-shaped run outright, never merely
escaping it, for the same reason ``swarm_field.py``/``swarm_queue.py`` give:
an *escaped* ``[/x]`` still renders as the literal text ``[/x]`` once a
markup parser unescapes it for display. ``ens_name`` is stripped the same
way before it is handed to ``address_text`` as a ``label=`` -- that helper's
own ``_clean_label`` only collapses whitespace and removes a stray copy
glyph, not a bracket run, so the stripping has to happen here. Every plain
string cell (``kind``, ``label``, the chain word) is additionally passed
through ``markup_safety.safe_markup`` before ``table.add_row`` -- belt and
suspenders: stripping already leaves nothing for ``Text.from_markup`` to
misparse, and escaping costs nothing on text that is already clean. The
ADDRESS / SITE cell is never a plain string at all -- ``address_text`` /
``short_hex`` build a ``rich.text.Text`` directly (``address_text`` through
Rich's own ``Text()`` constructor, never ``Text.from_markup``), so a
chain-sourced ``[/x]`` in an ENS name never reaches a markup parser from
that column either.

Purity
------
Stdlib, ``rich``, ``textual``, and this package's own ``_fmt``/``_pool4``/
``rowfit``/``_swarm_chain`` primitives, plus ``widgets/address`` for the
copy icon and ``widgets/markup_safety`` for the plain-string cells. No
``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import (
    ICON_COLS,
    MIN_SHORT_COLS,
    address_text,
    is_address,
    short_hex,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.surf._fmt import DASH, hhmm
from maxpane_dashboard.widgets.surf._pool4 import strip_tags
from maxpane_dashboard.widgets.surf._swarm_chain import CHAIN_COLS, chain_word

__all__ = [
    "ADDR_COLS",
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "MAX_ROWS",
    "TABLE_ID",
    "TIGHT_ADDR_COLS",
    "TIGHT_WIDTH",
    "TITLE",
    "UNAVAILABLE_LINE",
    "SurfSwarmShipped",
]

TITLE = "JUST SHIPPED"

#: A real read that found nothing shipped. Tested verbatim.
EMPTY_LINE = "nothing shipped yet"

#: ``swarm_shipped_rows is None`` -- the manager's own blank-payload
#: sentinel. Tested via substring (``"unavailable" in text``).
UNAVAILABLE_LINE = "shipments unavailable"

#: The address/site column's budget for a real address, **excluding** the
#: copy icon -- ``widgets/address.address_text``'s own ``width`` contract.
#: Frozen by the brief for the ``full``/``compact`` tiers; :data:`TIGHT_ADDR_COLS`
#: is the narrower window the ``tight`` tier uses instead (fix round 1).
ADDR_COLS = 17

#: Defensive backstop past the producer's own ``limit=12``
#: (``data/surf_swarm.shipped_rows``) -- this panel never trusts a payload
#: size on its own word.
MAX_ROWS = 50

_GAP = rowfit.GAP
TABLE_ID = "surf-swarm-shipped-table"
_TITLE_ID = "surf-swarm-shipped-title"
_FOOTER_ID = "surf-swarm-shipped-footer"
_TITLE_CLASS = "surf-swarm-shipped-title"

# -- column budgets, in rendered columns --------------------------------
#
# Measured against the committed fixtures (``tests/fixtures/surf/swarm/``,
# 2026-09-16), not guessed: the widest captured job template is
# ``skill:build-contract-project`` (28 cells), the widest launch-artifact
# label is ``BazaarMarketplace`` (17), and site labels top out at 13. These
# are measurements of a producer vocabulary that is not closed
# (``label``/``commit`` are free text), so a value that outgrows its cell is
# clipped with a visible ``…`` rather than treated as a pin to widen.

#: ``kind``: fits ``delivery`` (8), the widest of the three.
_KIND_COLS = 8
#: ``label``: fits the widest captured job template,
#: ``skill:build-contract-project`` (28), with no truncation.
_LABEL_COLS = 28
#: ``_fmt.hhmm``'s own width: ``HH:MM`` or ``??:??``.
_WHEN_COLS = 5

#: What ``DataTable`` spends on each column beyond the width asked for --
#: ``pool4u_stakers._CELL_PADDING``'s own measurement, reused rather than
#: re-derived: one cell of padding either side of a column, charged whether
#: or not the column is present (a ``DataTable`` pads every column it has,
#: including the last).
_CELL_PADDING = 2

#: The address/site column's own render width: the whole address plus its
#: copy icon (:data:`ADDR_COLS` + ``ICON_COLS``). An ENS name with no
#: backing address gets this same budget in full (no icon to reserve out of
#: it); a transaction hash gets :data:`ADDR_COLS` alone, per the brief.
_ADDR_RENDER_COLS = ADDR_COLS + ICON_COLS

#: The address/site column's **tight** window (fix round 1, 2026-09-17):
#: ``widgets/address.MIN_SHORT_COLS``, the address module's own absolute
#: legibility floor -- ``_window`` clamps back up to it regardless of what
#: is asked for below it, so a window narrower than this buys nothing.
#: Spent only on this body, where JUST SHIPPED is given a fixed width rather
#: than the whole row (see ``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s own ``#:``
#: block in ``screens/surf.py``): windowing an address down to its
#: narrowest legible form under a tight pin is this repo's own established
#: anti-poisoning form (curator's ``short_addr``, surf's own 8/6-at-17
#: window one tier up), not a new one invented for this panel.
TIGHT_ADDR_COLS = MIN_SHORT_COLS
_TIGHT_ADDR_RENDER_COLS = TIGHT_ADDR_COLS + ICON_COLS

#: Full tier: all five columns. Reused as the tier-decision threshold, like
#: every sibling panel in this body -- see :func:`_render_view`.
FULL_WIDTH = sum(
    cols + _CELL_PADDING
    for cols in (_KIND_COLS, _LABEL_COLS, CHAIN_COLS, _ADDR_RENDER_COLS, _WHEN_COLS)
)                                                                    # 77
#: One tier down: WHEN is dropped, whole -- never blanked, which would light
#: the widen marker while claiming back no width. CHAIN and ADDRESS / SITE
#: are never dropped independently of each other: dropping CHAIN alone would
#: leave a hash or address on screen with no chain word beside it, which the
#: module docstring's *"A hash or address is never shown without its chain
#: word"* rule forbids, and there is no version of this panel where dropping
#: ADDRESS / SITE and keeping CHAIN says anything a reader could use.
COMPACT_WIDTH = sum(
    cols + _CELL_PADDING
    for cols in (_KIND_COLS, _LABEL_COLS, CHAIN_COLS, _ADDR_RENDER_COLS)
)                                                                    # 70
#: A second tier down (fix round 1): WHEN stays dropped, and the
#: ADDRESS / SITE column also narrows to :data:`TIGHT_ADDR_COLS`. Never the
#: reverse (WHEN kept, address narrowed) -- WHEN is the whole panel's
#: cheapest column to drop (5 cells) and buys nothing back if the address
#: is still full width, so a tier that narrows the address before dropping
#: WHEN would spend the reader's legibility for less width than dropping
#: WHEN first already buys.
TIGHT_WIDTH = sum(
    cols + _CELL_PADDING
    for cols in (_KIND_COLS, _LABEL_COLS, CHAIN_COLS, _TIGHT_ADDR_RENDER_COLS)
)                                                                    # 64


#: The ``as of`` predicate and the network-word-free title fitter, shared by
#: the four swarm panels in ``widgets/rowfit.py`` since Branch 3 (each used to
#: restate them; the reasoning is on the shared definitions), under the names
#: this module's own docstrings and tests use.
_has_marker = rowfit.has_marker
_title_with_hint = rowfit.title_with_hint


def _row_fields(row: object) -> dict | None:
    """Decompose one shipped row; ``None`` drops a malformed one.

    Every string field is cleaned through ``strip_tags`` here (once), so
    every later step works on text that already carries no bracket-shaped
    noise. Address/tx-hash validity is decided at render time
    (:func:`_addr_or_site_cell`), not here, because ``widgets.address``'s
    own helpers already validate their input and a second check here would
    only be able to disagree with them.
    """
    if not isinstance(row, dict):
        return None
    try:
        kind = strip_tags(row.get("kind")) or DASH
        label = strip_tags(row.get("label")) or DASH
        chain_id = row.get("chain_id")
        address = row.get("address")
        tx_hash = row.get("tx_hash")
        ens_name = strip_tags(row.get("ens_name")) or None
        commit = strip_tags(row.get("commit")) or None
        return {
            "kind": kind,
            "label": label,
            "chain_id": chain_id,
            "address": address if isinstance(address, str) else None,
            "tx_hash": tx_hash if isinstance(tx_hash, str) else None,
            "ens_name": ens_name,
            "commit": commit,
            "at_ts": row.get("at_ts"),
        }
    except Exception:
        # A single malformed row must never take down the panel.
        return None


def _addr_or_site_cell(fields: dict, addr_cols: int, addr_render_cols: int) -> Text:
    """The ADDRESS / SITE cell: one priority order, never a bare hash.

    See the module docstring's *"Five columns, one identifying cell per
    row"* section for the order and why each step exists. ``addr_cols``/
    ``addr_render_cols`` are the *active tier's* own window (fix round 1):
    :data:`ADDR_COLS`/:data:`_ADDR_RENDER_COLS` at ``full``/``compact``,
    :data:`TIGHT_ADDR_COLS`/:data:`_TIGHT_ADDR_RENDER_COLS` at ``tight`` --
    passed in rather than read from the module globals so this function
    cannot drift from whichever window :func:`_install_columns` actually
    built the table with.
    """
    address = fields["address"]
    if is_address(address):
        return address_text(address, width=addr_cols)
    ens_name = fields["ens_name"]
    if ens_name:
        return address_text(None, label=ens_name, width=addr_render_cols)
    tx_hash = fields["tx_hash"]
    if tx_hash:
        return Text(short_hex(tx_hash, addr_cols))
    commit = fields["commit"]
    if commit:
        return Text(rowfit.clip(commit, addr_render_cols))
    return Text(DASH)


def _no_rows_line(as_of: object, rows: object) -> tuple[str, str] | None:
    """``(text, rich style)`` for an empty/unavailable panel, or ``None``
    when there are real rows to render.

    ``swarm_field.py``'s own rule, restated: no real marker means
    unavailable, full stop, whatever ``rows`` says (the producer cannot
    actually make ``rows`` disagree with the marker, but a hand-edited cache
    file is third-party input too); a marker present with an empty list is
    a genuine empty read. See the module docstring's *"Unread is not
    empty..."* section for why the marker, not ``rows is None``, is the
    discriminator here.
    """
    if not _has_marker(as_of) or rows is None:
        return f"⚠ {UNAVAILABLE_LINE}", "yellow"
    if not rows:
        return EMPTY_LINE, "dim"
    return None


class SurfSwarmShipped(Vertical):
    """JUST SHIPPED -- deliveries, launch artifacts and published sites."""

    DEFAULT_CSS = """
    SurfSwarmShipped > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfSwarmShipped > DataTable {
        height: 1fr;
        min-height: 4;
    }
    SurfSwarmShipped > .surf-swarm-shipped-title {
        margin: 0 0 1 0;
    }
    """

    #: ``> Static``'s own ``padding: 0 1``, and -- ``pool4u_stakers``'s own
    #: precedent -- the same two columns the table's own vertical scrollbar
    #: costs once enough rows are loaded to overflow the panel's height. One
    #: constant answers for both rather than two that could drift apart.
    _TITLE_PADDING_COLS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._widen = False
        self._tier = "full"
        #: Which tier's columns are currently on the table -- tracked apart
        #: from ``_tier`` so columns are rebuilt exactly when the tier moves,
        #: never on an ordinary repaint (``pool4u_stakers``'s own reason).
        self._columns_tier: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(Text(TITLE, style="dim"), id=_TITLE_ID, classes=_TITLE_CLASS)
        yield DataTable(id=TABLE_ID)
        yield Static(Text(""), id=_FOOTER_ID)

    def on_mount(self) -> None:
        try:
            table = self.query_one(f"#{TABLE_ID}", DataTable)
        except Exception:  # pragma: no cover - not composed
            return
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._install_columns(table, self._tier)

    def _install_columns(self, table: DataTable, tier: str) -> None:
        """(Re)build the header for *tier*; a no-op when it is already there."""
        if self._columns_tier == tier:
            return
        addr_render_cols = _TIGHT_ADDR_RENDER_COLS if tier == "tight" else _ADDR_RENDER_COLS
        try:
            table.clear(columns=True)
            table.add_column("what", width=_KIND_COLS, key="kind")
            table.add_column("label", width=_LABEL_COLS, key="label")
            table.add_column("chain", width=CHAIN_COLS, key="chain")
            table.add_column("address / site", width=addr_render_cols, key="addr")
            if tier == "full":
                table.add_column("when", width=_WHEN_COLS, key="when")
        except Exception:  # pragma: no cover - defensive
            return
        self._columns_tier = tier

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        swarm_shipped_rows=None,
        swarm_scores_as_of_hhmm=None,
        swarm_network=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel from the manager's flat dict.

        Every kwarg is spelled after its full ``swarm_`` contract key
        (``data/surf_models.SWARM_KEYS``). ``swarm_network`` is accepted and
        never painted -- the chain word this panel shows is per row, off
        each row's own ``chain_id`` (see the module docstring), not off the
        live tier's single network string, which is what ``swarm_field.py``
        already does for the identical reason. ``**_kwargs`` is mandatory:
        the screen splats the whole payload.
        """
        self._payload = {
            "rows": swarm_shipped_rows,
            "as_of": swarm_scores_as_of_hhmm,
            "seen": True,
        }
        self._render_view()

    def _title_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _render_view(self) -> None:
        budget = self._title_budget()
        self._widen = bool(budget) and budget < FULL_WIDTH
        self._tier = rowfit.tier_for(
            budget, (("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH))
        )
        self._render_title()
        self._render_rows()
        self._render_footer()

    def _render_title(self) -> None:
        try:
            title = self.query_one(f"#{_TITLE_ID}", Static)
        except Exception:  # not composed yet
            return
        base = TITLE
        as_of = self._payload.get("as_of")
        if _has_marker(as_of):
            base += f" · as of {as_of}"
        title.update(Text(_title_with_hint(base, self._widen, self._title_budget()), style="dim"))

    def _render_rows(self) -> None:
        try:
            table = self.query_one(f"#{TABLE_ID}", DataTable)
        except Exception:  # not composed yet
            return
        self._install_columns(table, self._tier)

        as_of = self._payload.get("as_of")
        rows = self._payload.get("rows")
        batch: list[list] = []
        addr_cols = TIGHT_ADDR_COLS if self._tier == "tight" else ADDR_COLS
        addr_render_cols = _TIGHT_ADDR_RENDER_COLS if self._tier == "tight" else _ADDR_RENDER_COLS
        # No real marker means unavailable, full stop -- the table shows no
        # rows even if ``rows`` somehow carried content (see the module
        # docstring and ``_no_rows_line``, whose gate this mirrors so the
        # table and the footer message can never disagree about whether
        # there is anything to show).
        if _has_marker(as_of) and isinstance(rows, list):
            for row in rows[:MAX_ROWS]:
                fields = _row_fields(row)
                if fields is None:
                    continue
                values: list = [
                    safe_markup(rowfit.pad(rowfit.clip(fields["kind"], _KIND_COLS), _KIND_COLS)),
                    safe_markup(
                        rowfit.pad(rowfit.clip(fields["label"], _LABEL_COLS), _LABEL_COLS)
                    ),
                    safe_markup(rowfit.pad(chain_word(fields["chain_id"]), CHAIN_COLS)),
                    # A ``Text`` cell, never markup -- see the module
                    # docstring's *"Third-party text"* section.
                    _addr_or_site_cell(fields, addr_cols, addr_render_cols),
                ]
                if self._tier == "full":
                    values.append(
                        safe_markup(rowfit.pad(hhmm(fields["at_ts"]), _WHEN_COLS))
                    )
                batch.append(values)

        try:
            table.clear()
        except Exception:  # pragma: no cover - columns not added yet
            return
        for values in batch:
            try:
                table.add_row(*values)
            except Exception:
                continue

    def _render_footer(self) -> None:
        try:
            footer = self.query_one(f"#{_FOOTER_ID}", Static)
        except Exception:  # not composed yet
            return
        line = _no_rows_line(self._payload.get("as_of"), self._payload.get("rows"))
        if line is None:
            footer.update(Text(""))
            return
        text, style = line
        footer.update(Text(text, style=style))
