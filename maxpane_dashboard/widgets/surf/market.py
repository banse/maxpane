"""IMD market panel: price, volume, liquidity, FP parity, the bridge spread.

Seven rows in **two columns** (title, spacer, two paired rows, a seam, and
the two-row bridge block)::

    IMD MARKET

      IMD $0.7074 · 24h ± ▲ +30.89%    price  ▁▁▂▃▄▅▆▇█
      vol 24h $244.2K · pool $548.7K   supply       ▁▁█ 2.4M

      FP  $0.7274 · parity ▼ -2.75%    IMD $0.0200 under FP, gross of fees
      IMD is FP bridged 1:1 from Base  gap narrows as IMD bridges back

The first two figure rows are deliberately the same shape -- label, figure,
``·``, labelled reading.  The price row carried a bare ``$0.7074`` until
2026-08-12 and was the only line on the whole surf screen whose number went
unnamed, directly above a row saying ``FP`` out loud.  ``24h ±`` names the
window the way ``parity`` names the comparison, and the single glyph ``±``
is worth two columns over ``+/-`` on the panel that sets this screen's
width.  The two labels are padded to a common width by :func:`_labelled`
(``FP`` is a character shorter than ``IMD``), so both figures start in one
column and re-wording either label moves both rows together.

The pairing is by subject, not by convenience: the price sparkline belongs
to the price, and the supply staircase belongs beside the IMD-token
figures.  Each left-hand field used barely 31 of the panel's ~75 rendered
columns, so the sparklines moved up out of rows of their own -- which is
what freed the two rows the bridge block now occupies.

The second column starts at :func:`_second_column`, **measured** from the
rendered width of the left-hand fields rather than pinned: the fields are
live numbers and a constant that fits ``$0.7074`` collides with
``$1,234.56``.  Only rows that actually carry a right-hand segment are
measured, so the wide unavailable line below cannot drag the sparklines
across the panel.

The bridge block
----------------

IMD is FP bridged 1:1: ``BridgedFP`` is a LayerZero OFT whose mainnet
supply exists only via ``lzReceive`` from Base, where FP is the FrenPet
game token (FP locks in the Base adapter, IMD mints here -- see
``analytics/surf_signals.parity_pct``).  One asset, two chains, which is
why a *parity* percentage is a health metric at all rather than a
comparison of two unrelated tokens.

So the block states, in this order: the per-token spread in dollars and
which side is rich, then the flow that closes it.  The flow follows the
sign, because it is the sign that decides it -- IMD rich means new supply
arriving on this side (FP bridges in) narrows the gap; IMD cheap means
supply leaving it (IMD bridges back, burning here and unlocking FP on
Base) does.  It is exactly the staircase the supply sparkline two rows up
is drawing.

Three things this block deliberately does not do:

* **It never advises a transaction.**  MaxPane is read-only by
  construction -- no signer, no calldata, nothing to advise *for*.  The
  copy describes a state and the direction that would close it, and says
  nothing about what anyone should do or earn.
* **The spread is gross and says so, in whichever form it is stated.**
  Bridge fees, mainnet and Base gas and both pools' slippage are not
  knowable keylessly, so no net figure is available at any price;
  :data:`GROSS_CAVEAT` is what stops a 2% parity being read as 2% free.
  It is **not a field of its own** and cannot be shed: it rides the dollar
  cell while that cell exists and moves onto ``parity`` when the cell sheds
  (:func:`_rows_for`).  Pairing it with the dollar figure *alone* was the
  bug -- ``parity`` never sheds, so a 100-column terminal rendered
  ``parity ▼ -2.75%`` on a bridged pair with no caveat anywhere, which is
  not an exotic width but the common one.
* **It degrades explicitly, and the whole panel shares one gate.**
  ``parity_pct`` is ``None`` whenever either price read fails, and then the
  block is :data:`SPREAD_UNAVAILABLE` -- not a blank right-hand column
  (which reads as *at parity*), not a zero, and never the last good spread
  presented as live.  The *parity cell* is gated on the same three keys in
  :func:`_parts` rather than on its own value alone: they are three
  separate payload keys, so a percentage can arrive with no prices behind
  it, and rendering it would state a spread on the same panel as the
  warning that no spread could be read.  :data:`BRIDGE_MECHANISM` survives
  that state because it is not a market read.
* **It names no direction a figure on screen does not show.**  The rich
  side and the parity glyph are decided against :data:`_GAP_EPSILON` and
  :data:`_PARITY_EPSILON`, the rounding boundaries of the two cells' own
  formatters -- ``imd - fp == 0`` exactly is a test never true of two live
  prices, and it let ``IMD $0.000000 over FP`` onto the panel beside
  ``parity ▲ +0.00%``.

``None`` anywhere renders ``--``; a missing feed is never a zero price.

The supply bar is the other half of that story: it is the burn staircase --
LP-fee burns step it down, OFT bridge-ins step it up.  Both series arrive
as ``list[[ts, value]]`` and are coerced through
``sparkline_common.coerce_points``, so a single null point degrades to a
skipped point rather than a dead panel.

Sparkline helpers are imported from ``sparkline_common`` (house rule
MEDI-36 -- import, never copy), and widths are measured with
``markup_safety.visible_len`` for the same reason.  Primitives only, and
no third-party text reaches this panel: every field here is a number this
app computed, so there is nothing for ``safe_markup`` to guard.

Width behaviour
---------------

The rows are ``Static``\\ s at ``text-wrap: nowrap; text-overflow: ellipsis``,
so an over-long row is cut with a visible ``…``.  That is half the house
contract; the other half -- a word in the *title* naming what went -- this
panel had none of until 2026-08-11, and it did not much matter while its
widest row was ~33 columns.  Pairing the sparklines with their figures and
adding the bridge block took that row to **71** rendered columns against the
captured 2.75% spread, i.e. from "fits anything" to a panel with two columns
of margin at the width the screen was then measured at.

**That margin was not there.**  The binding row's width moves with
``fmt_price``'s precision band, and it moves the *wrong way*: the band
switches to six decimals below $0.01, so a gap of $0.0071 renders
``$0.007100`` where the capture's $0.0200 renders ``$0.0200`` -- two columns
**more** for a *tighter* peg, which at $0.71 is any parity inside ±1.41% and
therefore the normal state of a 1:1 bridge.  The full tier needs **73**, not
71, and the surf screen was re-measured 142 -> **143** on 2026-08-12 for it
(``screens/surf.SURF_FULL_LAYOUT_COLUMNS``; still inside the app-wide
``__main__.FULL_LAYOUT_COLUMNS`` of 143, so no user-visible width moved).
A payload measuring this panel must therefore carry a sub-cent gap: the
capture's unusually wide spread renders the *narrow* case and clears one
column early.

**Labelling the price row cost the panel nothing**, which is not obvious and
was measured rather than assumed.  ``IMD `` and ``24h ± `` took that row's
left-hand field 24 -> 31 columns, and the panel takes 7/13 of the terminal,
so a naive estimate says the screen's requirement rises about eleven.  It
does not rise at all: the row that pins :func:`_second_column` is the
33-column mechanism sentence, 31 is still under it, and the price row's own
right-hand segment (a label and a 24-cell bar) is nowhere near the parity
row's spread cell.  The full tier is **73** against a tight peg before and
after, ``SURF_FULL_LAYOUT_COLUMNS`` stays 143 and the app-wide
``__main__.FULL_LAYOUT_COLUMNS`` stays FWA's 143.  Only the *compact* tier
moved, 68 -> 69, where the price row now outgrows the FP row it replaced as
that tier's widest left-hand field.  Re-sweep rather than estimate: the
seven columns landed on a row that was not the binding one.

So the panel now sheds **whole labelled fields** in a fixed order and the
title names them (:data:`WIDEN_HINTS`, :data:`SHORT_HINT`).

**The order is by how derivable a field is from what is left, not by
taste**, and every step in it was measured rather than assumed -- the
binding row is the *parity* row (``FP $x · parity ±y%`` beside
``IMD $d under FP, gross of fees``), so a field that is not on that row and
does not move :func:`_second_column` buys nothing at all and does not earn a
tier:

1. ``gap narrows as IMD bridges back`` -- the flow.  It restates a sign that
   is already on screen twice (the parity glyph ``▼``/``▲``, and the
   spread's own ``under``/``over``), and it is the 33-column mechanism
   sentence beside it that pins :func:`_second_column`, so dropping it moves
   every other row one column left as well: **71 -> 70**.
2. ``vol 24h`` -- the one figure here that says nothing about the spread.
   Depth (``pool``) is what decides whether a 2.75% gap is real; turnover
   does not, so ``pool`` never sheds and the volume goes first.  **70 -> 69**
   (and 71 -> 71 on its own: it pays only once the flow has gone, which is
   why the two share one tier).
3. ``FP $0.7274`` on the parity row, **with** the price sparkline.  FP's
   price is recoverable from the two figures that survive (IMD's price and
   the dollar gap beside it), and the 24h change on the price row states the
   same window the price bar draws.  They go together because the parity row
   binds: neither buys a column alone (bar alone 69 -> 69, **and FP alone
   69 -> 69**), where the pair is **69 -> 55**.

   *FP alone used to buy six columns* (68 -> 62).  It stopped on 2026-08-12,
   when labelling the price row took it 24 -> 31 columns -- level with the
   parity row -- so shedding FP now leaves the *price* row pinning
   :func:`_second_column` at the same place.  Nothing about the pairing
   changed; the measurement behind it got stronger.
4. The dollar spread ``IMD $0.0200 under FP, gross of fees``, **with** the
   supply bar -- **55 -> 33**, the biggest step on the ladder.  Note what
   does *not* go here: ``parity ▼ -2.75%`` is the spread, stated as a
   percentage, and it is 18 columns, so the panel's job survives every tier;
   what is shed is the dollar restatement.  Its *caveat* survives too, onto
   the parity cell -- and costs nothing, because the mechanism sentence is
   still the widest row at this tier.  Again measured: the supply bar alone
   is 55 -> 55 while the spread cell is present, which is why the burn
   staircase is the last graphic standing.
5. ``IMD is FP bridged 1:1 from Base`` -- the mechanism, last, because it is
   what makes "parity" mean anything.  It saves two columns in the healthy
   state (33 -> 31, the caveat now being what the parity row carries) and
   **28** in the unavailable one (56 -> 28), where it shares its row with
   ``⚠ spread unavailable``: that warning is the reason this tier exists at
   all, since a cut warning is the one thing worse than a shed one.

The tiers are picked by measuring **the very lines that are then rendered**
(:func:`_tier_for` lays each candidate out with :func:`_lay_out` and takes
``visible_len`` of the result), which is the trap ``widgets/surf/nft.py``
documents: a budget measured against a different string than the one painted
picks a tier by one width and paints another, i.e. clips with the marker
dark.  Here the measured object *is* the painted object, so the two cannot
disagree -- pinned anyway by
``test_market_tier_budget_matches_what_it_actually_renders``.

Fix round 10a (v3->v4 repoint, price-source disagreement)
-----------------------------------------------------------

The disagreement marker was re-measured against the 73-column ceiling above
rather than assumed to fit under it, and did not move it: it is two
characters on the price row, whose LEFT already sat one column under the
mechanism sentence that pins :func:`_second_column`, so the marker becomes
the new pin by one column and the panel's worst measured case is still
**73** -- the same number the module already documented for a tight peg.
``pool_liquidity_usd`` needs no gating any more: the manager now matches
the DexScreener pair by the dev's own on-chain pool id rather than by size
(fix round 10a, ``surf_client.SurfClient._pick_imd_pair``), so it is always
the live pool's own figure.

Fix round 10a also added a labelled ``legacy: v3 pool $...`` line on the
``#surf-mkt-gap`` seam, carrying the superseded v3 pool's own liquidity
apart from the live figure above. Task 2 (2026-08-23) removed it and its
whole supply chain: the v3 pool was drained on 2026-08-17 and its LP
position burned, so that number had stopped being a second opinion on the
live pool's and become a number about a pool that no longer exists. The
seam row is back to permanently blank.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import visible_len
from maxpane_dashboard.widgets.sparkline_common import (
    SPARK_WIDTH,
    build_sparkline,
    coerce_points,
)
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    fmt_compact,
    fmt_price,
)

_WAITING = "[dim]waiting for data...[/]"

#: Panel title.  Deliberately *not* imported by the tests that assert it:
#: they spell the string out, so a rename reddens them and has to be made on
#: purpose.  A test comparing this constant against itself would pass through
#: any rename at all.
PANEL_TITLE = "IMD MARKET"

#: Columns of clear space between the widest left-hand field and the second
#: column.  Two would still read as one gap on a row whose field happens to
#: end in a digit; three is the smallest that does not.
_GUTTER = 3

#: Sparkline row labels, padded to a common width so the bars themselves
#: line up as well as the labels do.
_SPARK_LABELS = ("price", "supply")
_LABEL_WIDTH = max(len(label) for label in _SPARK_LABELS)

#: The two price figures' labels: IMD's on the price row, FP's on the parity
#: row.  The price row was the only line on the surf screen whose number was
#: unnamed -- ``$0.7074  ▲ +30.89% 24h``, directly above a row saying ``FP``
#: out loud -- so it now takes that row's shape.  Read at render time through
#: :func:`_labelled` rather than baked into the f-strings, which is what lets
#: a test re-word one and watch the two columns stay together.
ROW_LABELS: dict[str, str] = {"imd": "IMD", "fp": "FP"}

#: The price row's window, mirroring ``parity`` on the row below.  The single
#: glyph ``±`` rather than ``+/-``: it reads the same and costs two columns
#: on the panel that binds the whole screen's width.
CHANGE_LABEL = "24h ±"

#: The parity row's window.  A constant rather than an f-string literal for
#: the same reason :data:`ROW_LABELS` is one: :func:`_window` pads these two
#: to a common width so the ``▲``/``▼`` glyphs start in one column, and a
#: label baked into its f-string could be re-worded without the padding
#: following it.
PARITY_LABEL = "parity"


def _window(label: str) -> str:
    """*label* padded so both windows' figures start in one column.

    ``24h ±`` is a character shorter than ``parity``, so without this the
    two rows' glyphs sat one column apart -- the same misalignment
    :func:`_labelled` fixes for the figures above them, one field to the
    right.  Derived from the two constants, never a hand-typed space.
    """
    return f"{label:<{max(len(CHANGE_LABEL), len(PARITY_LABEL))}}"


def _labelled(key: str, figure: str) -> str:
    """``IMD $0.7074`` -- *figure* behind its label, padded to one column.

    The padding is **derived from** :data:`ROW_LABELS`, never written as a
    literal space: ``FP`` is a character shorter than ``IMD`` today, and a
    hand-typed gap would keep rendering unchanged while a re-worded label
    drifted the two figures apart.
    """
    width = max(len(label) for label in ROW_LABELS.values())
    return f"[dim]{ROW_LABELS[key]:<{width}}[/] {figure}"

#: What IMD *is*, stated on the panel because the parity row above is
#: meaningless without it.  Not a market number and not a documented one: the
#: 1:1 is the OFT mint/burn invariant (an ``lzReceive`` mints exactly what was
#: sent), not a rate anyone publishes and nobody can quietly change.  Every
#: *number* in this block is read live from the payload.
BRIDGE_MECHANISM = "IMD is FP bridged 1:1 from Base"

#: The explicit unavailable state for the whole bridge block.  Rendered
#: verbatim and asserted verbatim by the widget tests.
SPREAD_UNAVAILABLE = "spread unavailable"

#: The caveat that qualifies **the spread**, in whichever form the spread is
#: currently on screen.  It rides the dollar cell while that cell exists and
#: moves onto the parity cell when it sheds -- see :func:`_rows_for`.
GROSS_CAVEAT = "gross of fees"

#: Below this the dollar gap does not survive its own formatter: ``fmt_price``
#: renders anything under it ``$0.000000``, so there is no figure on screen
#: for a named rich side to rest on.  A rounding boundary, not a taste
#: threshold -- pinned against ``fmt_price`` by
#: ``test_market_gap_epsilon_is_the_width_of_its_own_formatter``.
_GAP_EPSILON = 5e-7

#: The same rule for the percentage: below this the cell's own ``.2f`` renders
#: ``+0.00%``, and a ``▲`` beside ``+0.00%`` claims a direction the number
#: does not show.
_PARITY_EPSILON = 0.005

#: Fix round 10a wired two independent keyless price sources into the
#: payload: the on-chain ``extsload`` read (now the preferred
#: ``imd_price_usd``) and DexScreener (a cross-check now, never the number
#: of record).  Past this threshold, expressed as a percentage of the chain
#: price, the disagreement is surfaced rather than silently absorbed by
#: whichever source happened to win the preference.  Observed agreement
#: today is 0.2%; 2% is roughly a tenfold margin over that normal drift, not
#: a taste number.
_PRICE_DISAGREEMENT_PCT = 2.0

#: Appended to the price figure when the two sources disagree past
#: :data:`_PRICE_DISAGREEMENT_PCT`.  One glyph: the price row is not this
#: panel's binding row today, and a wordier marker would make it one.
_PRICE_DISAGREEMENT_MARKER = " [yellow]?[/]"

#: The width ladder: ``(tier, fields this tier gives up)``, widest first and
#: **cumulative** -- each tier has also given up everything above it.  The
#: reasoning for the order, and the measurement behind each pairing, is in
#: the module docstring; the field names are consumed only by
#: :func:`_rows_for`.
_TIER_STEPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("full", ()),
    ("compact", ("flow", "vol")),
    ("narrow", ("fp", "price_bar")),
    ("minimal", ("spread", "supply_bar")),
    ("bare", ("mechanism",)),
)


def _shed_sets() -> dict[str, frozenset[str]]:
    """Cumulative shed set per tier, built from :data:`_TIER_STEPS`.

    Written out as steps rather than as five explicit sets so a field cannot
    be dropped from one tier and silently reappear in a narrower one.
    """
    out: dict[str, frozenset[str]] = {}
    seen: set[str] = set()
    for name, fields in _TIER_STEPS:
        seen |= set(fields)
        out[name] = frozenset(seen)
    return out


#: Tier names, widest first.
TIERS: tuple[str, ...] = tuple(name for name, _fields in _TIER_STEPS)

_SHED: dict[str, frozenset[str]] = _shed_sets()

#: Marker appended to the title once a tier has shed something, naming what
#: went.  The wording gets terser as the tiers narrow for a measured reason:
#: the hint has to fit beside a 10-column title inside a panel that is *at
#: most* as wide as the tier that triggered it, which leaves 56 columns at
#: ``compact`` but only 21 at ``minimal`` and 16 at ``bare``.  A longer
#: wording down there would be unreachable in every layout this widget has --
#: a dead string, permanently replaced by :data:`SHORT_HINT` -- so the narrow
#: tiers name the field they just gave up and leave the *earlier* tiers'
#: losses to the wider titles a user passes through on the way down.
#:
#: What a tier may not do is drop two fields and name one.  ``minimal`` did:
#: it takes the dollar spread **and** the supply sparkline, and said
#: ``‹ widen: $ spread`` -- the bar went unnamed, which is the silent
#: clipping the whole ladder exists to prevent.  ``, bar`` does not fit (22
#: columns against 21, measured: it degrades the whole hint to
#: :data:`SHORT_HINT`), so the separator is ``+``.  The ``$`` is load-bearing
#: and stays: the *percentage* spread is still on screen at ``minimal``, so a
#: hint reading ``spread`` would advertise something the user is looking at.
#: Pinned by ``test_market_widen_hints_all_fit_beside_the_title_at_their_own_tier``
#: (it fits) and ``test_market_every_tier_names_every_field_it_sheds``
#: (it is complete).
WIDEN_HINTS: dict[str, str] = {
    "full": "",
    "compact": "‹ widen for 24h volume and bridge flow",
    "narrow": "‹ widen: FP price, price bar, vol, flow",
    "minimal": "‹ widen: $ spread+bar",
    "bare": "‹ widen: bridge",
}

#: Fallback marker for a panel too narrow to carry a descriptive hint beside
#: its title.  It names nothing, which is a real loss -- but "columns were
#: dropped here" is the contract, and going silent is not an option this
#: codebase allows.
SHORT_HINT = "‹ widen"

#: The pool-identity warning, and why it rides *this* panel's title.
#:
#: ``pool_id_source`` records how ``surf_client`` found the live ETH/IMD v4
#: pool: ``"hook"`` means ``LaunchpadHook.imdEthPoolId()`` answered, and
#: ``"fallback"`` means it did not and the vendored ``POOL_V4_ID_FALLBACK``
#: constant was used instead.  **38 ETH/IMD v4 pools exist on mainnet and 37
#: of them are third-party decoys**, some at fee tiers up to 98%, so
#: ``"fallback"`` is not a provenance footnote -- it is "we could not verify
#: that these numbers belong to the pool we think they do".
#:
#: It lives on the IMD MARKET title because this is the panel rendering the
#: numbers that would be wrong: ``pool_liquidity_usd`` and the on-chain leg of
#: ``imd_price_usd`` both come from the pool this flag is uncertain about.
#: The claim had no home at all between the hero's POOL box being retired
#: (2026-08-24) and this marker: DECOY POOL on the signals rail carries the
#: *count* of decoys, which is a different fact -- knowing 37 lookalikes exist
#: says nothing about whether we picked the right one out of the 38.
#:
#: ``None`` is deliberately NOT a warning.  It means the launchpad sweep has
#: not completed yet, i.e. we have not looked -- the panel's own rows already
#: render their unavailable states in that case, and warning here would
#: collapse "unverified" into "unread", which is the same two-claims-one-string
#: bug the ``burn_ready`` tri-state and the curator FARM row exist to avoid.
POOL_UNVERIFIED_HINT = "· pool id unverified"

#: The narrow-panel form.  Kept a *question*, not an abbreviation of the long
#: wording: ``· pool unver`` reads like a truncation the reader is expected to
#: complete, while ``· pool ?`` states the uncertainty in six columns.
POOL_UNVERIFIED_SHORT = "· pool ?"

#: Payload entries that belong to the panel *title* rather than to one of its
#: rows, and so must never reach :func:`_parts`. Spelled as a constant rather
#: than inlined at the call site: `_parts` is strict by design, and the next
#: title-only field added to the payload has to land here or the panel stops
#: rendering entirely -- a failure mode worth naming in one obvious place.
_TITLE_ONLY_KEYS = frozenset({"pool_id_source"})

#: The five data rows, in compose order.  ``#surf-mkt-gap`` is the blank
#: seam between the token figures and the bridge block -- fix round 10a
#: (2026-08-12) briefly wrote a dim ``legacy`` line naming the superseded
#: v3 pool's own liquidity onto it, and Task 2 (2026-08-23) removed that
#: line along with the rest of the ``legacy_pool_liquidity_usd`` chain once
#: the v3 pool itself was drained and its LP position burned, so the seam
#: is permanently blank again -- exactly what keeps
#: ``test_market_blank_row_separates_the_token_figures_from_the_bridge``
#: green.  It carries no right-hand segment, ever, so it is invisible to
#: :func:`_second_column`.
_ROW_IDS = (
    "#surf-mkt-price",
    "#surf-mkt-vol",
    "#surf-mkt-gap",
    "#surf-mkt-parity",
    "#surf-mkt-bridge",
)


def _price_marker(disagreement_pct) -> str:
    """``[yellow]?[/]`` when the two price sources disagree past the
    threshold, else ``""``.

    ``None`` -- one source missing -- is not agreement and must not render
    as agreement, but it is also not a disagreement to flag: it renders no
    marker at all, same as a value inside the threshold.  Never chooses
    between the two readings itself -- ``imd_price_usd`` is already
    whichever the manager preferred (the on-chain read when available) by
    the time it reaches :func:`_parts`; this only flags that DexScreener's
    figure disagrees with it enough to be worth a second look.
    """
    v = as_float(disagreement_pct)
    if v is None or abs(v) <= _PRICE_DISAGREEMENT_PCT:
        return ""
    return _PRICE_DISAGREEMENT_MARKER


def _fmt_change(value) -> str:
    """``24h ± ▲ +30.89%`` -- the window named, then glyph + sign in text.

    Shaped exactly like :func:`_fmt_parity` one row down, including the
    unavailable state: ``24h ± --`` still says *what* could not be read,
    where a bare label says nothing and a zero would read as "unmoved".
    """
    v = as_float(value)
    label = _window(CHANGE_LABEL)
    if v is None:
        return f"[dim]{label} {DASH}[/]"
    if v > 0:
        return f"[dim]{label}[/] [$success]▲ {v:+.2f}%[/]"
    if v < 0:
        return f"[dim]{label}[/] [$error]▼ {v:+.2f}%[/]"
    return f"[dim]{label} ● {v:+.2f}%[/]"


def _fmt_parity(value) -> str:
    """FP↔IMD parity spread; negative means IMD trades below FP.

    Availability is gated by :func:`_parts` on the same three payload keys as
    the bridge block, so this cell cannot state a spread on the same panel as
    ``⚠ spread unavailable``; ``None`` reaches here for a failed read of
    *either* price as well as of the parity itself.
    """
    v = as_float(value)
    label = _window(PARITY_LABEL)
    if v is None:
        return f"[dim]{label} {DASH}[/]"
    if v > _PARITY_EPSILON:
        return f"[dim]{label}[/] [$success]▲ {v:+.2f}%[/]"
    if v < -_PARITY_EPSILON:
        return f"[dim]{label}[/] [$error]▼ {v:+.2f}%[/]"
    return f"[dim]{label} ● {v:+.2f}%[/]"


def _spark(series) -> str:
    """A block sparkline from ``[[ts, value]]``, or the waiting message."""
    points = coerce_points(series)
    if len(points) < 2:
        return _WAITING
    values = [v for _, v in points]
    return f"[cyan]{build_sparkline(values, pad=len(values) >= SPARK_WIDTH)}[/]"


def _spark_cell(label: str, series, suffix: str = "") -> str:
    """``price  ▁▁▂▃`` -- the label padded so both bars start together."""
    return f"[dim]{label:<{_LABEL_WIDTH}}[/] {_spark(series)}{suffix}"


def _bridge_cells(imd_price_usd, fp_price_usd, parity_pct) -> tuple[str, str]:
    """``(spread, direction)`` for the bridge block, or ``("", "")``.

    Both halves are derived from the same two live prices, so they cannot
    contradict each other: ``imd - fp`` and ``(imd/fp - 1) * 100`` share a
    sign for any positive FP price, which is the only case ``parity_pct``
    returns a number for.  All three keys are the availability gate -- a
    percentage can arrive with no prices behind it -- and the empty pair is
    the caller's signal to render :data:`SPREAD_UNAVAILABLE` instead **and**
    to withhold the parity cell, which is derived from the same three reads
    (:func:`_parts`).
    """
    imd = as_float(imd_price_usd)
    fp = as_float(fp_price_usd)
    if imd is None or fp is None or as_float(parity_pct) is None:
        return "", ""

    delta = imd - fp
    if abs(delta) < _GAP_EPSILON:
        # Not ``== 0``: two live prices subtract to exactly zero almost never,
        # and a gap that renders ``$0.000000`` names a rich side no figure on
        # this panel shows.  :data:`_GAP_EPSILON` is that render boundary.
        return "[dim]IMD level with FP[/]", "[dim]no gap to close[/]"
    side = "over" if delta > 0 else "under"
    # Which flow narrows it: supply arriving on the rich side, or leaving
    # it.  Never phrased as an action for anyone to take.
    flow = "FP bridges in" if delta > 0 else "IMD bridges back"
    return (
        f"[dim]IMD[/] [bold]{fmt_price(abs(delta))}[/] "
        f"[dim]{side} FP, {GROSS_CAVEAT}[/]",
        f"[dim]gap narrows as {flow}[/]",
    )


def _second_column(rows: list[tuple[str, str]]) -> int:
    """Column the right-hand segments start at, from the rendered lefts.

    Measured over the rows that *have* a right-hand segment: a row rendering
    left-only (the unavailable bridge line, which is wider than any figure)
    must not push the sparklines across the panel to make room for nothing.
    """
    widths = [visible_len(left) for left, right in rows if right]
    return (max(widths) if widths else 0) + _GUTTER


def _lay_out(rows: list[tuple[str, str]], column: int) -> list[str]:
    """Pad each left segment so every right segment starts at ``column``."""
    return [
        left + " " * max(column - visible_len(left), 1) + right if right else left
        for left, right in rows
    ]


def _parts(
    imd_price_usd,
    imd_change_24h_pct,
    imd_vol_24h_usd,
    pool_liquidity_usd,
    fp_price_usd,
    parity_pct,
    supply_series,
    price_series,
    price_source_disagreement_pct=None,
) -> dict:
    """Every rendered fragment the tiers choose between, formatted once.

    **Deliberately has no ``**kwargs``.** ``update_data`` swallows unknown
    keywords so a stale caller cannot crash the panel; this builder is the
    layer that must NOT, because it is the only thing standing between a
    removed field and a caller still sending it. ``test_the_market_panel_no_
    longer_carries_the_superseded_v3_pool`` asserts exactly that by handing
    it ``legacy_pool_liquidity_usd`` and requiring a ``TypeError``. Anything
    the payload carries that is not a row belongs in
    :data:`_TITLE_ONLY_KEYS`, not in a ``**kwargs`` escape hatch here.

    Tier selection renders the whole panel up to five times, so the numbers
    are formatted here rather than inside :func:`_rows_for` -- and, more to
    the point, formatting them once is what guarantees the five candidates
    differ only in *which* fields they carry, never in what a field says.
    """
    price = fmt_price(imd_price_usd)
    marker = _price_marker(price_source_disagreement_pct) if price != DASH else ""
    vol = as_float(imd_vol_24h_usd)
    liq = as_float(pool_liquidity_usd)
    fp = fmt_price(fp_price_usd)
    supply_points = coerce_points(supply_series)
    spread, direction = _bridge_cells(imd_price_usd, fp_price_usd, parity_pct)
    # One gate for the whole panel.  ``_bridge_cells`` is empty exactly when
    # any of the three market keys failed to read, so deriving the parity
    # cell's availability from it is what stops ``parity ▼ -2.75%`` appearing
    # beside ``⚠ spread unavailable`` -- three keys, one answer.
    measurable = bool(spread)

    return {
        "price": _labelled(
            "imd",
            f"[bold]{price}[/]{marker}" if price != DASH else f"[dim]{DASH}[/]",
        ),
        "change": _fmt_change(imd_change_24h_pct),
        "vol": f"${fmt_compact(vol)}" if vol is not None else DASH,
        "pool": f"${fmt_compact(liq)}" if liq is not None else DASH,
        "fp": _labelled("fp", fp if fp != DASH else f"[dim]{DASH}[/]"),
        "parity": _fmt_parity(parity_pct if measurable else None),
        "price_series": price_series,
        "supply_series": supply_series,
        "supply_last": fmt_compact(supply_points[-1][1]) if supply_points else "",
        "spread": spread,
        "direction": direction,
        # ``spread`` is emptied by the tiers as well as by an outage, so the
        # bridge row needs a flag that means only "the pair could be read".
        "measurable": measurable,
        # True only while a *gap* is being stated, so the caveat follows the
        # spread onto the parity cell without appearing beside "level with FP",
        # where there is no gap to be gross about.
        "gross": GROSS_CAVEAT in spread,
    }


def _rows_for(tier: str, parts: dict) -> list[tuple[str, str]]:
    """``(left, right)`` markup for the five data rows at *tier*.

    The single source of both the measurement and the render: :func:`_tier_for`
    lays these out to decide, and :meth:`SurfMarket._render_view` lays the
    winner out to paint.  Nothing else may compose a row.
    """
    gone = _SHED[tier]

    # Joined with ``·`` and not two spaces, because this row is now the same
    # shape as the parity row below it: label, figure, join, labelled change.
    left_price = f"  {parts['price']} [dim]·[/] {parts['change']}"
    right_price = (
        "" if "price_bar" in gone else _spark_cell("price", parts["price_series"])
    )

    figures = []
    if "vol" not in gone:
        figures.append(f"[dim]vol 24h[/] {parts['vol']}")
    # ``pool`` never sheds: depth is what makes the spread above mean
    # anything, and the row it sits on is not the row that binds.
    figures.append(f"[dim]pool[/] {parts['pool']}")
    left_token = "  " + " [dim]·[/] ".join(figures)

    last = f" [dim]{parts['supply_last']}[/]" if parts["supply_last"] else ""
    if "supply_bar" not in gone:
        right_token = _spark_cell("supply", parts["supply_series"], suffix=last)
    elif parts["supply_last"]:
        # The bar is gone; the number it ended on is not.
        right_token = f"[dim]{'supply':<{_LABEL_WIDTH}}[/] {parts['supply_last']}"
    else:
        right_token = ""

    bits = []
    if "fp" not in gone:
        bits.append(parts["fp"])
    parity = parts["parity"]
    spread_shed = "spread" in gone
    if spread_shed and parts["gross"]:
        # The caveat qualifies the spread, and ``parity`` *is* the spread once
        # the dollar cell has gone -- so it follows it here rather than being
        # shed with the cell it started on.  Pairing it with the dollar figure
        # alone left the narrow tiers stating a percentage gap on a bridged
        # pair with no fee caveat anywhere, which is the reading it exists to
        # stop.  It costs nothing at ``minimal`` (the mechanism sentence is
        # still the widest row there) and three columns at ``bare``.
        parity = f"{parity} [dim]{GROSS_CAVEAT}[/]"
    bits.append(parity)
    left_parity = "  " + " [dim]·[/] ".join(bits)
    right_parity = "" if spread_shed else parts["spread"]

    if "mechanism" in gone:
        # The mechanism is a claim about what IMD *is*, so it outlives every
        # figure -- but not the explicit unavailable warning it shares a row
        # with, which is why this tier exists.
        left_bridge = (
            "" if parts["measurable"] else f"  [yellow]⚠ {SPREAD_UNAVAILABLE}[/]"
        )
    elif parts["measurable"]:
        left_bridge = f"  [dim]{BRIDGE_MECHANISM}[/]"
    else:
        left_bridge = (
            f"  [dim]{BRIDGE_MECHANISM} ·[/] [yellow]⚠ {SPREAD_UNAVAILABLE}[/]"
        )
    right_bridge = "" if "flow" in gone else parts["direction"]

    # The seam between the token figures and the bridge block.  Fix round
    # 10a briefly used it for a dim v3-pool liquidity note; Task 2
    # (2026-08-23) removed that note along with the rest of the legacy
    # chain once the v3 pool was drained and its LP position burned, so the
    # row stays blank.
    left_gap = ""

    return [
        (left_price, right_price),
        (left_token, right_token),
        (left_gap, ""),
        (left_parity, right_parity),
        (left_bridge, right_bridge),
    ]


def _lines_for(tier: str, parts: dict) -> list[str]:
    """The five rendered rows at *tier*, padded onto their common column."""
    rows = _rows_for(tier, parts)
    return _lay_out(rows, _second_column(rows))


def _tier_for(width: int, parts: dict) -> str:
    """Widest tier whose widest **rendered** row fits ``width`` columns.

    ``width <= 0`` means "not laid out yet" and optimistically picks the
    widest tier; :meth:`SurfMarket.on_resize` re-lays it out once the panel
    has a size.  Nothing narrower than the last tier exists -- a panel that
    cannot fit even that ellipsises, with :data:`WIDEN_HINTS` already lit.
    """
    if width <= 0:
        return TIERS[0]
    for tier in TIERS:
        if max(visible_len(line) for line in _lines_for(tier, parts)) <= width:
            return tier
    return TIERS[-1]


class SurfMarket(Vertical):
    """IMD market panel."""

    DEFAULT_CSS = """
    SurfMarket > .surf-market-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfMarket > .surf-market-line {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        #: The last payload, not the formatted rows, so a resize can re-lay
        #: them out at the new width.  ``None`` until the first
        #: ``update_data`` -- ``on_resize`` before that has nothing to render
        #: and must not blank the panel.
        self._payload: dict | None = None

    def compose(self) -> ComposeResult:
        yield Static(
            PANEL_TITLE, classes="surf-market-title", id="surf-mkt-title"
        )
        yield Static("", classes="surf-market-line", id="surf-mkt-spacer")
        # A second blank row, so the title sits further off its figures than
        # the figures sit off each other.  Rows are ``auto``-height, so this
        # costs one terminal row and nothing horizontal.
        yield Static("", classes="surf-market-line", id="surf-mkt-spacer-2")
        yield Static(_WAITING, classes="surf-market-line", id="surf-mkt-price")
        yield Static("", classes="surf-market-line", id="surf-mkt-vol")
        yield Static("", classes="surf-market-line", id="surf-mkt-gap")
        yield Static("", classes="surf-market-line", id="surf-mkt-parity")
        yield Static("", classes="surf-market-line", id="surf-mkt-bridge")

    def update_data(
        self,
        imd_price_usd=None,
        imd_change_24h_pct=None,
        imd_vol_24h_usd=None,
        pool_liquidity_usd=None,
        fp_price_usd=None,
        parity_pct=None,
        supply_series=None,
        price_series=None,
        price_source_disagreement_pct=None,
        pool_id_source=None,
        **_kwargs,
    ) -> None:
        """Refresh all rows.  Kwargs are the PRD §5 market keys, plus one.

        ``pool_id_source`` is the odd one out and does not render as a row:
        it is provenance for the two figures that *do* -- the pool liquidity
        and the on-chain price leg -- so it rides the panel title instead
        (:data:`POOL_UNVERIFIED_HINT`).  It arrived 2026-08-24 with the hero's
        POOL box being retired, which left the "we could not verify which pool
        this is" claim with no home anywhere on the dashboard.

        ``price_source_disagreement_pct`` never changes which price renders
        -- ``imd_price_usd`` is already whichever the manager preferred (the
        on-chain read when available) by the time it reaches this widget --
        it only marks the row when DexScreener's figure disagrees with it
        past :data:`_PRICE_DISAGREEMENT_PCT`.
        """
        self._payload = {
            "imd_price_usd": imd_price_usd,
            "imd_change_24h_pct": imd_change_24h_pct,
            "imd_vol_24h_usd": imd_vol_24h_usd,
            "pool_liquidity_usd": pool_liquidity_usd,
            "fp_price_usd": fp_price_usd,
            "parity_pct": parity_pct,
            "supply_series": supply_series,
            "price_series": price_series,
            "price_source_disagreement_pct": price_source_disagreement_pct,
            "pool_id_source": pool_id_source,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        """Re-lay the rows out: the tier depends on the width.

        The rows are formatted once per refresh against the width they were
        formatted at, and nothing else re-renders them, so without this hook
        a widened or narrowed terminal would show the previous size's tier --
        padded, or ellipsised by ``text-overflow`` with the title still
        claiming nothing was shed -- until the next 30-second poll.
        """
        if self._payload is not None:
            self._render_view()

    # -- rendering -----------------------------------------------------

    def _line_width(self) -> int:
        """Rendered columns one row of this panel can show.

        Every row (and the title) is a ``width: 100%`` ``Static`` at
        ``padding: 0 1`` inside this widget's own content box, so they all
        have the same usable width and one number answers for the lot.
        """
        return max(self.content_size.width - 2, 0)

    def _set_title(self, hint: str = "", pool_id_source=None) -> None:
        """``IMD MARKET · pool id unverified  ‹ widen: $ spread``, width permitting.

        Two markers, in priority order, both *appended*: the title itself
        never changes, so the screen tests' ``"IMD MARKET" in text`` holds at
        every width.

        **The pool warning goes first and gets first claim on the columns.**
        A shed column is a nuisance the user can fix by widening; a pool
        identity nobody verified means every figure below may belong to one
        of the 37 decoy pools, which the user cannot fix at all and cannot
        see any other way. Ordering them the other way round would let a
        narrow panel spend its last columns saying "widen me" instead of
        "these numbers may not be ours".

        Each degrades to a shorter form rather than to nothing -- silence is
        what the tiers exist to prevent -- and only a panel too narrow for
        even the short form goes unmarked, because this ``Static`` has no
        ``text-overflow`` and an over-long title wraps onto a second line,
        pushing the bridge block out of a row whose height is ``auto``. A
        wrapped warning would cost the panel a row of real data to say
        something the same panel is about to render unavailable anyway.
        """
        title = self.query_one("#surf-mkt-title", Static)
        width = self._line_width()
        text = PANEL_TITLE
        used = len(PANEL_TITLE)

        # `== "fallback"` and not a truthiness test: `None` means the sweep
        # has not run (we have not looked), which is a different claim from
        # "we looked and could not verify" and must not warn. `"hook"` is the
        # verified case and must not warn either.
        if pool_id_source == "fallback":
            for candidate in (POOL_UNVERIFIED_HINT, POOL_UNVERIFIED_SHORT):
                if not width or used + 1 + len(candidate) <= width:
                    text += f" [yellow]{candidate}[/]"
                    used += 1 + len(candidate)
                    break

        if hint:
            for candidate in (hint, SHORT_HINT):
                if not width or used + 2 + len(candidate) <= width:
                    text += f"  [yellow]{candidate}[/]"
                    used += 2 + len(candidate)
                    break
        title.update(text)

    def _render_view(self) -> None:
        payload = self._payload
        if payload is None:
            return
        # `_parts` builds ROWS and is strict about its keyword list on
        # purpose (see its docstring). `pool_id_source` rides the same
        # payload because a resize has to re-render the title from one
        # source of truth, but it is filtered out here rather than handed
        # to a builder that has no row to put it in.
        row_payload = {
            key: value
            for key, value in payload.items()
            if key not in _TITLE_ONLY_KEYS
        }
        try:
            rows = [self.query_one(row_id, Static) for row_id in _ROW_IDS]
        except Exception:  # not composed yet
            return

        parts = _parts(**row_payload)
        width = self._line_width()
        tier = _tier_for(width, parts)
        for row, line in zip(rows, _lines_for(tier, parts)):
            row.update(line)
        self._set_title(
            WIDEN_HINTS.get(tier, SHORT_HINT),
            pool_id_source=payload.get("pool_id_source"),
        )
