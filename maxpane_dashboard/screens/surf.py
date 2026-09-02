"""SurfScreen -- the surfsurf.eth Surfboard as a Textual Screen.

Layout: three content rows, every widget on screen at once::

    #title-bar         SURFBOARD · IMD $x.xx · parity ±x.x% · as of HH:MM
    #hero-row          SurfHero (full width, four boxes)
    #middle-row        SurfFeed (7fr)   | #surf-right-rail (6fr)
                                        |   SurfSignals     (auto, +1 margin)
                                        |   SurfDevActivity (1fr)
    #separator
    #bottom-row        SurfMarket (7fr) | SurfNft (6fr)
    StatusBar

``l`` swaps ``#middle-row``/``#separator``/``#bottom-row`` for a fourth body
holding the v4 launchpad's own panels -- five of them since 2026-08-25 --
laid out on ``#middle-row``'s own shape::

    #surf-launchpad-body   #surf-launchpad-left (2fr)       | #surf-launchpad-rail (1fr)
                             SurfLaunchpadCoins    (auto)   |   SurfCurveFlow      (auto, +1 margin)
                             SurfLaunchpadActivity (1fr)    |   SurfBurnPipeline   (auto, +1 margin)
                                                            |   SurfBurnkeepers    (1fr)

``p`` swaps the same three rows for a **third** body, the POOL4 view
(2026-09-01), on the identical shape::

    #surf-pool4-body   #surf-pool4-left (1fr)          | #surf-pool4-rail (1fr)
                         SurfPool4Split   (auto, +1 m) |   SurfPool4Hatches (auto, +1 margin)
                         SurfPool4Ratchet (auto, +1 m) |   SurfPool4Vault   (1fr)
                         SurfPool4Flow    (1fr)        |

The columns are cut to **balance their heights** -- 33 rows each at the
worst payload -- which is what ``SURF_POOL4_FULL_LAYOUT_ROWS`` is measured
from. It is the reverse of what this paragraph said before mainnet landed:
the rail no longer holds only constant-height panels, because THE SPLIT
became payload-sized too and no two-column cut of these five can keep both
variable panels out of the binder. The rail's ``1fr`` is still on the
*fixed* panel (sIMD VAULT), which is the reverse of the other two bodies'
rule -- see that constant for why.

``#hero-row`` is never touched by either swap and stays on screen in all
three modes. See "The 2026-08-23 ``l`` view" below.

The rail arrived 2026-08-24. The two summary panels were stacked *under*
the coin table until then, which spent eleven of the body's rows on ten
lines of label/value text that never grow, while the one panel here with
a variable row count -- the table, whose rows are the launchpad's own
population -- absorbed the loss. Beside the table they cost columns
instead. That trade is only worth making because rows are the scarce
currency in this body and columns are not: the coin table's
``DataTable`` has nine fixed columns, so what it needs horizontally is a
constant, and what it can *show* vertically is not.

**That constant is also why this body's seam is not the other two rows'.**
``2fr:1fr``, re-swept 2026-08-25 for the five-panel body -- the left column
needs 92 columns and cannot give one back, the rail needs 40 against the
committed capture and 43 against an ordinary one. The seam is deliberately
*not* the cheapest: ``23:10`` collects the arithmetic floor at 132 and is
disqualified, because at every width in between the panel that binds is
``SurfBurnPipeline``, a plain ``Static`` that ellipsises in silence. 2:1
hands the rail 46 columns at the pin -- more than the 43 its widest possible
line can ever need -- so the binder is always the coin table, which marks,
and the pin is 138 against every payload rather than moving with the data
the way the old ``12fr:5fr`` number did.
``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`` carries the full per-seam table.

The two rows below the hero *in dashboard mode* are both split 7:6 on the
same seam, so they read as one grid rather than two unrelated bands. The
launchpad body is a third row that replaces both, never a row beside them,
so its own seam is free to answer to its own two panels -- and has to.

**The seam is a measurement, and both panels it balances have since got
narrower.** It was 3:2 until 2026-08-10. The left column's binding panel is
``SurfFeed``, the right column's is ``SurfDevActivity``, and what each needs
is what the seam has to serve.

*When 7:6 was chosen*, those needs were 81 and 71 columns, so the narrowest
terminal serving both was 81 + 71 = 152 and only a seam near 81:71 collected
it: 3:2 handed the feed 0.60 W against the 0.538 it needed, so the rail
reached 71 only at 176 -- 24 columns of waste, and past the ~169 a laptop
gets at the 17 pt ``__main__`` forces on launch, i.e. the full layout was
unreachable at the app's own font size. Swept over the real screen, 152 was
the floor and four seams reached it; 7:6 was the simplest.

*Both needs then fell.* ``feed.FULL_TEXT_WIDTH`` came down 76 -> 71 (the feed
now wraps in **76** columns of its own) and the activity row's cells were
sized to the vocabularies their producer really emits (the rail now sheds a
field below **63**). 76 + 63 = 139 is the floor today, collected by a seam
near 76:63 -- re-swept over the real screen, table in
``tests/screens/test_surf_screen.py``. **7:6 collects it at 142**, three
columns above that floor and one *below* FWA's 143, which is what
``__main__.FULL_LAYOUT_COLUMNS`` documents for the app as a whole. Those
three columns are therefore not worth a re-seam today: spending them would
not move a single number a user sees. The seam stays 7:6, on record, with
the arithmetic that would justify moving it written down for whenever the
feed's or the rail's need next changes.

**Nothing is hidden.** Until 2026-08-10 the announce feed and the
dev-activity panel shared the middle-left slot and ``c`` swapped them, which
meant half the dashboard's content was off screen at any moment and the
status bar had to carry a ``view:`` word to say which half. The activity
panel moved into the rail under the signals, the market moved down beside
the NFT panel, and the key, its action, the status-bar indicator and their
tests went with the slot they served. The market did not cost the bottom
row a single row on the way: ``SurfNft`` is the taller of the two (its
last-sales block runs to four lines), so an ``auto`` row sized to the NFT
panel already had room for the market's seven.

**The 2026-08-23 ``l`` view is a different shape of "hidden," not a return
of this one.** It does not put two panels back in one slot the way ``c``
did; it swaps the *whole* three-row dashboard body for the v4 launchpad's
own panels (``SurfLaunchpadCoins``, ``SurfLaunchpadActivity``,
``SurfCurveFlow``, ``SurfBurnPipeline``, ``SurfBurnkeepers``), on curator's
``y``/``f`` precedent, and ``escape`` backs out one-way. The hero row is untouched by the swap and stays mounted
and visible in both modes, so nothing it tracks (LAUNCHPAD/FLOW/BURN/SUPPLY
since the 2026-08-24 rebuild) ever goes dark. The five dashboard-body panels above still never share a slot
with each other -- only the *body as a whole* now has a second view.

``SurfSignals`` is ``auto`` (a title, a spacer and six detector rows) with a
one-row bottom margin, and ``SurfDevActivity`` takes the rest of the rail at
``1fr``, floored by ``ACTIVITY_MIN_HEIGHT``. That margin is the blank line
between the two rail panels: they sat flush and read as one block. A margin
rather than a spacer widget -- nothing to compose, nothing to query, and it
collapses into the rail's scroll extent like any other row, so ``TALLER_HINT``
keeps accounting for it. It costs the rail exactly one row: the marker now
lights at 36 rows instead of 35, and the first genuinely-lost activity row
moved 33 -> 34 with it, so the marker still leads the loss by two. That floor is what keeps the rail's
``overflow-y: auto`` honest: a ``1fr`` child cannot overflow its scroll
container -- it shrinks -- so without a floor the activity panel would shed
one row per terminal row down to a bare title with no scrollbar, no marker
and no other trace anywhere on screen. That is exactly what ``SurfMarket``
did from this same rail until 2026-08-09, and it is the reason the floor is
declared rather than left to Textual.

The hero was half a row wide until 2026-08-09 and shared it with the
signals panel. Two things were wrong with that. Its four boxes had to
share a ``3fr`` half, which left each of them 13 content columns on a
139-column terminal -- narrow enough that the box copy had to shed whole
fields to fit (see ``widgets/surf/hero.py``), and the ``full`` tier was
unreachable below ~220 columns, i.e. on no terminal anybody owns. And the
row was pinned at ``height: 10`` for a ``height: 7`` widget, so three rows
under the boxes were reserved and blank on every launch. Full width buys
each box ~26 columns at the same 139, which reaches the ``full`` tier, and
the row now sizes to its content.

**Every row but the middle one sizes to its content**, and the middle row
alone carries ``1fr``. That is what makes a tall terminal grow the feed
instead of stranding whitespace: previously ``#bottom-row`` also carried
``1fr`` and took half the slack for a panel with eight lines in it, which
left roughly a fifth of the screen empty above the status bar.

Deliberate choices, in the FWA screen's terms (see screens/fwa.py, whose
docstring carries the full rationale):

1. **Every widget update is individually guarded** -- one widget raising must
   never cost the other five their refresh. A *manager* failure touches only
   the StatusBar and leaves the previous frame standing.
2. **Degradation reaches the title bar** (``· ⚠ logs, market``), because the
   shared StatusBar API has no ``set_degraded()``.

The screen is clock-free: every time-derived string (``feed_last_post_age_s``,
per-signal ages) arrives pre-computed in the payload. Nothing here consults
the wall clock, so any captured instant replays forever in tests.

Written against the frozen ``SURF_KEYS`` contract, not against
``SurfManager``'s internals -- any object with an awaitable
``fetch_and_compute()`` returning that dict drives it.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static

from maxpane_dashboard.screens.refresh_guard import RefreshGuard
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf import (
    SurfBurnkeepers,
    SurfBurnPipeline,
    SurfCurveFlow,
    SurfDevActivity,
    SurfFeed,
    SurfHero,
    SurfLaunchpadActivity,
    SurfLaunchpadCoins,
    SurfMarket,
    SurfNft,
    SurfPool4Flow,
    SurfPool4Hatches,
    SurfPool4Ratchet,
    SurfPool4Split,
    SurfPool4Vault,
    SurfSignals,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from maxpane_dashboard.data.surf_manager import SurfManager

logger = logging.getLogger(__name__)

_EMDASH = "—"

#: Shown until the first payload lands -- and, on the degraded path where the
#: manager raises, for good: ``_title_line`` is what replaces it and that code
#: is never reached. The name here must therefore be the name the game-select
#: menu uses (``screens/game_select.GAMES``), which is asserted by
#: ``test_the_initial_title_names_the_dashboard_the_menu_names``. It was not:
#: the rename to "Surfboard" reached the menu, the README and CLAUDE.md and
#: stopped here, so the one surface a user reads *inside* the dashboard kept
#: the old name.
#:
#: **Two segments since 2026-08-12, not three.** ``SURF · Surfboard ·
#: Ethereum Mainnet`` said the name twice -- the abbreviation and then the
#: word -- so the live title's ``SURF`` became ``SURFBOARD`` and this line
#: dropped the middle segment to match. The menu's ``Surfboard`` is still the
#: name being asserted against; only its case differs, this row being the
#: shouted one.
INITIAL_TITLE = "SURFBOARD · Ethereum Mainnet"

#: The row-wise counterpart of the widgets' ``‹ widen``: the right rail holds
#: more than this terminal's height can show, so some of SIGNALS / DEV
#: ACTIVITY is scrolled off. It rides the **title bar** rather than a panel
#: title because a panel title is itself the first thing a short rail loses --
#: when the market was still in this rail, 143x31 composited the ``IMD
#: MARKET`` heading alone and 143x30 not even that. Row 0 cannot be pushed off
#: by anything.
#:
#: It lights at or below **36** rows and is dark from 37 up. It was 35/36
#: until 2026-08-10, when the one-row margin under ``SurfSignals`` -- the
#: blank line separating the rail's two panels -- made the rail's content one
#: row taller. Nothing else about the threshold moved: the first genuinely
#: lost activity row went 33 -> 34 in the same step, so the marker still leads
#: the first real loss by two rows, which is the property that matters.
#: Below 20 rows the bottom row goes off the end of a screen that has itself
#: started scrolling; the marker is already lit long before that, so nothing
#: is ever lost in silence.
#:
#: Riding row 0 is necessary but not sufficient: that row is one line of a
#: *wrapping* ``Static``, so its own tail is silently dropped rather than
#: ellipsised. ``_title_line`` therefore puts this marker ahead of both
#: warnings -- see its docstring for why it, of the three, is the one that
#: has to survive.
#:
#: **It serves both bodies since 2026-08-25, and served only one before
#: that.** The ``l`` LAUNCHPAD body has its own, higher threshold --
#: :data:`SURF_LAUNCHPAD_FULL_LAYOUT_ROWS`, 31 rows against this body's 36
#: -- and until that date the marker was dark on the whole of the ``l``
#: view at every height, because ``_rail_is_cut`` read ``#surf-right-rail``
#: unconditionally and that container is inside a hidden ``#middle-row``
#: while the launchpad is showing. See ``SurfScreen._rail_is_cut``.
TALLER_HINT = "‹ taller"

#: Sentinel staleness pushed to the StatusBar when the manager itself failed.
MANAGER_FAILURE_SECONDS = 999

#: The rail's floor for ``SurfDevActivity``: a title, a spacer and five rows
#: -- the same seven rows ``SurfMarket`` occupied here until it moved to the
#: bottom row, which is why the height at which ``TALLER_HINT`` lights did not
#: move then. (It moved one row later, when the signals panel gained its
#: separating margin: 35 -> 36. This floor is unchanged.)
#: A ``1fr`` child shrinks instead of overflowing its scroll
#: container, so this floor is the only thing that turns "the rail is too
#: short" into an overflow the screen can see and advertise; without it the
#: panel silently thins to its title. **Restated as ``min-height`` in both
#: stylesheets** -- CSS cannot read a Python constant, so
#: ``test_the_activity_floor_is_the_same_number_in_both_stylesheets`` pins the
#: three copies together.
ACTIVITY_MIN_HEIGHT = 7

#: Measured against composited output, not estimated -- see tests.
#:
#: Reconciled to the measured **142** on 2026-08-10, re-swept column by column
#: before the constant moved: 141 lights exactly one marker, 142 lights none,
#: and every width from 142 to 200 lights none either.
#:
#: **142 -> 143 on 2026-08-12**, and the sweep that said 142 was measuring the
#: wrong state of ``SurfMarket``. That panel's binding row carries the IMD/FP
#: dollar gap, and ``_fmt.fmt_price`` switches to six decimals below $0.01:
#: the captured 2.75% spread renders ``$0.0200`` and the row needs 71 columns,
#: while any *tighter* peg renders ``$0.007100`` and needs **73**. At IMD's
#: $0.7074 that is every parity inside ±1.41% -- the ordinary state of a 1:1
#: bridge -- so the friendlier number was the one measured and the margin it
#: implied never existed. Re-swept against a tight peg, the whole-screen
#: marker count reads: 130-134 three (feed, market, activity), 135-141 two
#: (feed, market), 142 one (market alone), 143-200 none.
#:
#: **The market is the panel that sets this number now**, one column above the
#: announce feed. It is not worth re-seaming for: the bottom row's 7:6 split
#: is settled and ``__main__.FULL_LAYOUT_COLUMNS`` is FWA's 143 either way, so
#: surf clearing at 143 rather than 142 is a width nobody can see the loss of.
#:
#: **Re-swept 2026-08-24 after the feed was rewritten, and it did not move.**
#: ``SurfFeed`` stopped being a ``RichLog`` and became per-row widgets with a
#: reply thread behind a toggle, which indents a nested row one column per
#: depth -- the obvious suspicion being that an open thread costs the screen
#: up to two columns. It costs **none**, and the sweep says so in both
#: states: 128..152, threads collapsed and then expanded, reproduces the
#: 2026-08-12 table exactly (three markers 128-134, two 135-141, one at 142,
#: none from 143). The reason is in ``feed._item_lines``: ``depth`` is
#: subtracted from the row's own *text budget* and never added to the line,
#: so a nested row is one column narrower than its parent rather than one
#: column wider than the panel. Threading is paid in rows, and this is the
#: panel the layout hands its spare rows to.
#:
#: That sweep needs a fixture the committed capture cannot supply: its one
#: ``reply`` is *older* than the post it follows, so ``build_threads`` makes
#: it a root of its own and nothing is ever indented. It was re-staged with
#: the same two real messages and the reply's ``ts`` moved after the post's,
#: which is what a reply normally is -- see
#: ``test_an_open_thread_costs_the_screen_no_columns``.
#:
#: **The binding panel has changed hands twice.** Through the 176 and 152 eras
#: the last marker standing was ``SurfDevActivity``'s and the feed was clean
#: well below it; sizing the activity row's cells to the vocabularies their
#: producer emits took that panel's full row layout 66 -> 58, so it clears
#: from a **135**-column terminal and 142 was the **announce feed's** edge.
#: At 143 it is ``SurfMarket``'s. Any statement of the form "the activity
#: panel is the one still asking for width" is from the first regime and is
#: false; "the feed is" belongs to the second.
#: The number is quoted by ``__main__.FULL_LAYOUT_COLUMNS``, the ``--font-size``
#: help text, the README width table and CLAUDE.md, and all five now agree.
#: ``tests/screens/test_surf_screen.MEASURED_FULL_LAYOUT_COLUMNS`` holds the
#: same number as an **independent literal** and pins it to the real screen in
#: both directions; keep it a separate literal, because a test that aliased it
#: to this constant would compare a number against itself and pin nothing.
#: A documented width *above* the measured one is merely generous -- one
#: *below* it would clip, which is what
#: ``test_the_documented_width_still_covers_the_measured_one`` forbids.
#:
#: The history, because the number has moved five times in four days:
#: **135 -> 176 -> 152 -> 142 -> 143**.
#:
#: It was 135 while ``SurfDevActivity`` had a ``3fr`` slot of its own (shared
#: with the feed, behind a ``c`` swap that no longer exists). The three-row
#: restructure traded that slot for a share of the right rail and the number
#: went to 176 -- not because the panel needs 176 columns, but because a
#: **3:2** seam gives the rail only ``0.4 * W`` and the rail then needed 71.
#: Re-seaming to **7:6** handed the feed the 0.538 it needed and the rail the
#: rest, and 81 + 71 = 152 fell out -- the number came back **down**, 176 ->
#: 152, without hiding anything.
#:
#: 142 is the same kind of move made on the other side of the seam: the panels
#: got narrower rather than the split moving. ``feed.FULL_TEXT_WIDTH`` 76 -> 71
#: took the feed's own need 81 -> 76, and the activity row's wallet and kind
#: cells sized to ``{"dev", "ops"}`` and ``DEV_TX_KINDS`` took the rail's 71 ->
#: 63. 76 + 63 = 139 is the floor a seam near 76:63 would collect; the settled
#: **7:6** collects 142, three columns above it. Not worth re-seaming for:
#: FWA's 143 is what the app documents, so those three columns buy nothing a
#: user could see. The whole seam sweep is in the screen docstring and, with
#: the losing candidates, in the test module. **That seam is no longer what
#: binds** -- 143 comes from the *bottom* row, where the market takes 7/13.
#:
#: 143 is inside the ~169 columns a laptop gets at the forced 17 pt, as 152
#: was; that headroom was the point of re-seaming, because at 176 the full
#: layout was unreachable at the font size the app itself picks and
#: ``--font-size 12`` was the only way in.
#:
#: The measured number deliberately EXCLUDES posts carrying an inherently
#: unbreakable token (a URL glued to a raw tx hash, e.g. by a trailing
#: period with no space -- the real nonce-13 capture's link is 91 columns).
#: SurfFeed correctly truncates such a token and lights its own ``‹ widen``;
#: *this particular capture* clears at 216 (194 before the re-seam, the feed
#: being narrower now -- unchanged by the 152 -> 142 move, which took nothing
#: from the feed's column), and the next real post linking a transaction
#: reproduces the shape at whatever width its own token needs. A fixture
#: containing one therefore cannot be what "full layout" is measured against
#: -- see ``test_a_linked_post_advertises_widen_at_the_full_layout_width``.
#: Do not raise this toward 216 to silence a linked post's marker: that
#: marker is correct, and 216 is a "full layout" nobody could reach.
SURF_FULL_LAYOUT_COLUMNS = 143

#: The ``l`` LAUNCHPAD body's own measured width (Task 13, re-swept
#: 2026-08-25 for the five-panel body) -- a **separate, independently-named**
#: constant, never a rewrite of :data:`SURF_FULL_LAYOUT_COLUMNS` above or
#: ``__main__.FULL_LAYOUT_COLUMNS``. Swept column by column over the real
#: screen (``tests/screens/test_surf_screen.py``'s
#: ``test_the_launchpad_body_is_whole_from_its_pinned_width``, which runs
#: 128..150 -- comfortably below and above this number and never starting at
#: it, so the sweep cannot agree with the pin by construction).
#:
#: **The binding panel is ``SurfLaunchpadCoins``**, pinned by
#: ``test_the_launchpad_binding_panel_is_the_coins_table`` rather than by
#: this sentence (curator's own
#: ``test_the_analysis_binding_panel_is_the_operators_table`` precedent).
#: Its ``DataTable`` has nine fixed columns (``launchpad._TABLE_FULL_WIDTH``,
#: 89 since MCAP replaced PRICE) that do not shrink with the terminal, and it
#: advertises the loss on its own title -- the same idiom ``SurfMarket`` and
#: curator's ``CuratorOperators`` use, one tier rather than a ladder, because
#: a fixed-column ``DataTable`` has nothing shorter to fall back to.
#:
#: **93 -> 135 -> 138, and each number described a body the next one no
#: longer is.** 93 was three full-width panels stacked; 135 was the
#: 2026-08-24 rail on a ``12fr:5fr`` seam. This is the five-panel body:
#: LAUNCHPAD COINS over LAUNCHPAD ACTIVITY in a left *column*, CURVE FLOW /
#: BURN PIPELINE / BURNKEEPERS in the rail. Both halves were re-measured
#: *in situ*, each inside its own real container:
#:
#:   * the **left column needs 92** screen columns -- 89 content, plus
#:     ``SurfLaunchpadCoins``' ``padding: 0 1``, plus the column's own
#:     reserved ``scrollbar-gutter: stable`` cell. ``SurfLaunchpadActivity``
#:     never competes: its ``FULL_WIDTH`` is 45, so it clears at 48.
#:   * the **rail needs 40** against the committed capture and **43**
#:     against any ordinary one, measured inside ``#surf-launchpad-rail``
#:     and not in a bare harness -- its widest line pays the panel's
#:     ``padding: 0 1``, the inner ``Static``'s own, and the reserved gutter
#:     cell on top. ``SurfBurnkeepers`` clears at **37** in situ -- measured,
#:     not derived from its ``FULL_WIDTH`` of 32, which is a pure-content
#:     constant while the panel's ``padding: 0 1`` sits on its child. 37 is
#:     comfortably under 40 either way, so the rail's own binder is
#:     ``SurfBurnPipeline``'s ``accrued … IMD · staged … IMD`` line.
#:
#:     **Re-measured 2026-08-26 against the fixed widget, and 37 held.**
#:     It was reached twice by different routes: before ``9284305`` the
#:     panel clipped from 36 down while its own ``‹ widen`` went dark at
#:     35, so 37 was where the rows stopped clipping and 35 was where the
#:     marker stopped speaking -- a two-column window inside the panel.
#:     The marker now goes dark at 37 as well, so the two agree. The number
#:     recorded here never depended on the marker (it is the width at which
#:     the *rows* clear), which is why this half of the measurement did not
#:     move; what moved is the ``3:1`` row of the table below, whose window
#:     was bounded by that marker.
#:
#: **That last fact is what chose the seam, and it is not the arithmetic.**
#: The rail's *binding* panel is one of ``SurfCurveFlow`` /
#: ``SurfBurnPipeline``, and those two are plain label/value ``Static``s:
#: they ellipsise and go quiet. (The other two rail-adjacent panels do have
#: markers -- ``SurfBurnkeepers`` clears at 37, ``SurfLaunchpadActivity`` at
#: 48 -- but neither is ever the one asking for the rail's columns, so
#: neither can advertise the loss that matters here.) So a seam whose *rail* is the
#: binder renders a clipped line with no ``‹ widen`` anywhere on screen, and
#: this repo disqualifies that (the same test that rejected ``5:2`` in the
#: 2026-08-24 sweep). The window 129..132 as this body shipped -- 131..132
#: once the left column reserved its own scrollbar gutter -- where the old
#: ``12fr:5fr`` seam clipped ``accrued 1.2K IMD · staged 45.00 I…`` in
#: silence, is exactly that failure, and it is why the pin could not simply
#: be re-typed: **no value of this constant cleared the sweep on the old
#: seam.** Below 129 the coin table was clipped too and marked, so the pin
#: could not be dropped under the window either.
#:
#: **And the rail's need is data-dependent while the table's is not.**
#: ``fmt_imd`` renders 100.00..999.99 at six columns and compacts above
#: 1000, so the accrued/staged line is 35 cells against the committed
#: capture's ``1.2K``/``45.00`` and 38 -- its widest possible form -- against
#: the ``620.00``/``500.00`` an ordinary launchpad prints: 40 and 43 screen
#: columns. A seam pinned to the small case can therefore *stop qualifying*
#: the moment the data is ordinary.
#:
#: **That six-column ceiling bounds the accrued/staged line, not the rail.**
#: The ``burned … IMD (all-time)`` line beneath it goes through
#: ``_fmt_total`` -- exact and comma-grouped, deliberately *not* compacted,
#: because it is the headline cumulative figure. It is 28 cells at the
#: capture's 3,299 IMD and 35 at a billion, so it stays under the
#: accrued/staged line's 38 across every magnitude this pipeline can reach
#: and the rail's 43 survives. It is the line to re-measure if that
#: formatter ever changes; the ceiling argument below is about the widest
#: line, whichever line that is, and today it is the accrued/staged one.
#:
#: Swept over the real screen at both magnitudes: the first width at which
#: both halves are clean, and the widths below it at which something clips
#: with nothing on screen saying so.
#:
#: ==========  ========  ===========  ========  ===========
#: seam        capture   silent       ordinary  silent
#: ==========  ========  ===========  ========  ===========
#: ``23:10``   132       --           139       132..138
#: ``7:3``     132       --           141       132..140
#: ``16:7``    133       --           139       133..138
#: ``9:4``     133       --           137       133..136
#: ``12:5``    133       131..132     143       131..142
#: ``11:5``    134       --           135       134
#: ``17:7``    134       130..133     145       130..144
#: ``13:6``    135       --           135       --
#: ``15:7``    135       --           135       --
#: ``22:9``    135       130..134     145       130..144
#: ``19:9``    136       --           136       --
#: ``21:10``   136       --           136       --
#: ``5:2``     137       129..136     148       129..147
#: ``2:1``     **138**   --           **138**   --
#: ``3:2``     154       --           154       --
#: ``3:1``     157       145..156     169       145..168
#: ``9:7``     164       --           164       --
#: ``11:9``    168       --           168       --
#: ``7:6``     171       --           171       --
#: ==========  ========  ===========  ========  ===========
#:
#: ``3:1``'s window is the one row worth reading twice, because two
#: different numbers are both true of it. The **coin table** is clean from
#: **123** -- that is where the left column reaches 92 -- but 123..144 is
#: not silent: ``SurfBurnkeepers``' own marker is lit there, the rail being
#: 31..36. The window opens at **145**, which is exactly where that marker
#: goes dark (rail 37) while ``SurfBurnPipeline`` is still clipping. So the
#: genuinely unadvertised stretch is 145..156. Quote 123 for "where the
#: table stops asking" and 145 for "where the screen stops saying
#: anything".
#:
#: **This row is the whole table's canary, and it has already fired once.**
#: It was 137..156 until 2026-08-26, and it moved without any seam, panel
#: width or pin changing: ``9284305`` fixed ``SurfBurnkeepers`` to compare
#: its ``‹ widen`` against the real text budget instead of the raw panel
#: width, which took the marker's own threshold 35 -> 37 and handed this
#: window back its first eight columns. Re-swept, all nineteen seams and
#: both payloads: **this is the only row that moved, and no pin did.**
#: That is the shape to expect -- a marker fix can only ever shrink a
#: silent window, never a pin, because a pin is where the *pixels* stop
#: being lost and a marker is only who says so. It is also why the row is
#: worth keeping in a table of rejected seams: it is the one entry whose
#: number is a fact about a *marker* rather than about a width, so it is the
#: one that goes stale when a sibling widget is repaired.
#:
#: ``23:10`` and ``7:3`` collect the arithmetic floor (92 + 40 = 132)
#: against the committed capture and are the cheapest seams there -- and
#: both are **disqualified** the moment the burn line is an ordinary length,
#: because the rail then binds and its binding panel cannot mark. ``16:7``, ``9:4``
#: and ``11:5`` fail the same way, one column at a time. The old ``12:5``
#: fails it under *both* payloads, which is why this pin could not simply be
#: re-typed: **no value of this constant cleared the sweep on the old
#: seam**, and every seam above it in the ordinary column fails worse.
#:
#: **The qualifying set is the seams at or below about 2.16:1**, and the
#: reason is arithmetic rather than luck: the left column binds at every
#: width iff its share reaches 92 no earlier than the rail's reaches 43.
#: ``13:6`` and ``15:7`` are the cheapest of them at 135, ``19:9`` and
#: ``21:10`` next at 136, and ``2fr:1fr`` is the simplest at 138. Everything
#: gentler than 2:1 qualifies too and costs more, monotonically: ``3:2`` 154,
#: ``9:7`` 164, ``11:9`` 168, ``7:6`` 171. The last of those is what this
#: body was provisionally built with.
#:
#: **2:1 is pinned, and the three columns are bought deliberately.** What
#: separates it from ``13:6`` is not the pin but the *margin*: at 135 the
#: rail gets exactly the 43 it needs and the left exactly its 92, so both
#: halves sit on the edge, while 2:1 hands the rail **46**. Zero margin on
#: the left column is harmless -- it is the binder, it marks, and a change
#: there simply moves the pin and lights ``‹ widen`` on the way. Zero margin
#: on the *rail* is not, because **the panel that sets the rail's width
#: cannot mark**: the next format change that costs a rail line one cell
#: reopens a silent-clip window, and this is not hypothetical -- the rail's
#: own need moved 39 -> 40 during this very task series, when ``staged``
#: gained a decimal place in a sibling widget. 43 is the ceiling
#: ``fmt_imd`` imposes on that line today; 46 is what survives the next
#: such edit without a re-sweep nobody will run.
#:
#: **Say that precisely, because the loose form invites a wrong "fix".**
#: It is not that the rail has no markers -- ``SurfBurnkeepers`` exports a
#: ``WIDEN_HINT`` and ``SurfLaunchpadActivity`` a whole ``WIDEN_HINTS``
#: ladder. It is that neither of those is ever the panel *asking for
#: columns*: BURNKEEPERS clears at 37 and ACTIVITY at 48, both under the
#: rail's own 40..43, so the width the rail needs is always
#: ``SurfBurnPipeline``'s (or ``SurfCurveFlow``'s), and those two are the
#: plain label/value ``Static``s with no marker at all. A reader who
#: notices BURNKEEPERS has a marker and concludes the seam argument is
#: wrong has checked the wrong panel; the argument is about the binder,
#: not about the population.
#: 135, 136 and 138 are all below FWA's 143 and far below the ~169 columns a
#: laptop gets at the forced 17 pt, so the three columns cost a user
#: nothing. Take them back if the rail ever grows a marker of its own.
#:
#: The tie-break within the qualifying set is the one that chose ``7:6`` for
#: ``#middle-row`` and ``12:5`` for this body before it: prefer the seam a
#: reader can hold in their head. 2:1 is the simplest seam in the family and
#: also the one with the margin, so here the two criteria agree.
#:
#: **138, five columns under FWA's 143** -- so this task moves neither
#: :data:`SURF_FULL_LAYOUT_COLUMNS` nor ``__main__.FULL_LAYOUT_COLUMNS``,
#: and the ``198 -> 172 -> 143 -> 176 -> 152 -> 143`` record in CLAUDE.md is
#: correctly **not** appended to: that record tracks changes to the
#: app-wide number only (CLAUDE.md says so twice already, about curator's
#: own screen pin and its ``f`` view). The hero row, which stays mounted in
#: both modes, clears on its own at **87** and never competes for the binder
#: role.
SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS = 138

#: The ``l`` LAUNCHPAD body's own measured **height** (2026-08-25) -- new
#: with the five-panel body, which is the first version of this view that
#: could run out of rows. Curator's ``f``/``y`` precedent: the body is whole
#: from this many terminal rows, and below it the body scrolls and the title
#: bar says :data:`TALLER_HINT`.
#:
#: The binder is the **rail**, at 20 rows of content:
#:
#:   ``SurfCurveFlow`` 6 (title, blank, two flow lines, owed, ``as of``)
#:   + its 1-row bottom margin
#:   + ``SurfBurnPipeline`` 7 (title, blank, status, accrued/staged, min
#:   bridge, burned, ``as of``) + its 1-row bottom margin
#:   + ``SurfBurnkeepers`` 5 (``min-height``: title, blank, three rows)
#:   = **20**.
#:
#: The left column asks for less: ``SurfLaunchpadCoins`` is 13 rows with a
#: full ten-coin table (title, blank, header, ten rows) and
#: ``SurfLaunchpadActivity``'s floor is 6, so 19. The body itself is the
#: screen minus the title bar (1), the hero row and its top margin (8), this
#: body's own top margin (1) and the StatusBar (1) -- eleven rows -- so a
#: 20-row body wants a **31**-row terminal, and the 19-row column would have
#: wanted 30. One row of margin, and it is the rail's.
#:
#: **That derivation is measured, and the committed capture cannot measure
#: it.** ``_sample_data``'s ``launchpad_coins`` has two rows, so in the
#: fixture the table is 5 rows tall and the left column 11 -- eight rows
#: short of the 19 this paragraph is about, and never scrolling at any
#: height the sweep visits. The numbers above are pinned against a ten-coin
#: payload by ``test_the_height_pin_is_measured_against_the_column_it_
#: describes``, and the sweep itself runs at both magnitudes, for the same
#: reason :data:`SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` is swept at two burn
#: magnitudes: the committed capture is the small case on both axes. The
#: derivation has to be read below the pin, too -- both ``1fr`` children
#: grow on a roomy terminal, so at 31 rows each column reports 20 and the 19
#: is invisible; at 28 they sit on their floors and it is not.
#:
#: **Both columns scroll, and both had to.** ``#surf-launchpad-rail`` has
#: carried ``overflow-y: auto`` since it was born; ``#surf-launchpad-left``
#: did not, and a ``Vertical`` defaults to ``overflow: hidden hidden``, so
#: below 22 rows the activity feed was clipped out of the column with no
#: scrollbar and nothing on screen to say so. Both carry
#: ``scrollbar-gutter: stable`` with it, for ``#curator-right-rail``'s own
#: reason: without the gutter the scrollbar takes its column out of the
#: panel beside it only on terminals short enough to overflow, so this
#: layout's WIDTH pin would become a function of its HEIGHT.
#: :data:`SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` above is measured with that
#: gutter reserved, which is the 92nd of its 92 columns.
SURF_LAUNCHPAD_FULL_LAYOUT_ROWS = 31

#: The ``p`` POOL4 body's own measured width (2026-09-01) -- a **separate,
#: independently-named** constant, never a rewrite of
#: :data:`SURF_FULL_LAYOUT_COLUMNS`, of
#: :data:`SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` above, or of
#: ``__main__.FULL_LAYOUT_COLUMNS``. It is **not derived from the launchpad's
#: 138 and is not equal to it**: a third body measured against a different set
#: of panels has no reason to land on a neighbour's number, and one that did
#: would be a coincidence worth distrusting.
#:
#: Swept column by column over the real screen by
#: ``tests/screens/test_surf_screen.py``'s
#: ``test_the_pool4_body_is_whole_from_its_pinned_width``, which runs
#: **96..152** -- ten columns below this pin and forty-six above it, never
#: starting at it, and deliberately straddling **both** neighbouring pins (the
#: launchpad's 138 and the app-wide 143) so agreeing with either would show up
#: as a sweep result rather than as an assumption. The brief for this task
#: asked for 118..152; that range is a subset of this one and every width in
#: it is above the pin, so on its own it would have executed the
#: below-the-pin branch zero times and pinned nothing from underneath. The
#: range was extended downward rather than the pin pushed up to meet it.
#:
#: **The binding panel is ``SurfPool4Flow``**, pinned by
#: ``test_the_pool4_binding_panel_is_the_flow_log`` rather than by this
#: sentence (``test_the_launchpad_binding_panel_is_the_coins_table``'s and
#: curator's ``test_the_analysis_binding_panel_is_the_operators_table``
#: precedent). At 105 -- one column under the pin -- it is the only one of the
#: five panels with a marker lit.
#:
#: **That was chosen, not observed.** Measured *in situ*, each panel inside
#: its own real container and swept across all three payload magnitudes (the
#: committed capture, the ordinary-magnitude flow, and mainnet), this body's
#: five needs are the **widest column the panel ever asks for**:
#:
#: ==================  ====  ==========  =============================================
#: panel               col   needs       what it does when it does not get it
#: ==================  ====  ==========  =============================================
#: ``POOL4 FLOW``      left  53          drops the inference column, then size,
#:                                       naming each on its own title
#: ``HATCHES``         rail  50          drops the per-row address column, marked
#: ``THE RATCHET``     left  45          drops to its compact tier, marked
#: ``sIMD VAULT``      rail  44          drops to its compact tier, marked
#: ``THE SPLIT``       left  36          reflows its paired lines onto one line
#:                                       each -- **loses nothing**, so it never
#:                                       marks and never sets a requirement
#: ==================  ====  ==========  =============================================
#:
#: So the **left column needs 53** (FLOW's; RATCHET rides along at 45 and
#: SPLIT at 36) and the **rail needs 50** (HATCHES'; VAULT rides along at
#: 44). Those are screen columns including the reserved
#: ``scrollbar-gutter: stable`` cell each column pays, measured against
#: composited output inside ``#surf-pool4-left`` / ``#surf-pool4-rail`` and
#: not in a bare harness -- FLOW's widest line pays the panel's
#: ``padding: 0 1``, the inner ``RichLog``'s own, that log's always-on
#: scrollbar column, and the column's reserved gutter on top, which is four
#: columns a pure-content constant like its ``FULL_WIDTH`` cannot see.
#:
#: **The ``col`` column is the part that changed on 2026-09-02** and the
#: reason every number below it was re-measured rather than carried over.
#: The mainnet rebalance moved THE SPLIT and THE RATCHET to the left column
#: and HATCHES to the rail (argued in
#: :data:`SURF_POOL4_FULL_LAYOUT_ROWS`), so the rail's need went from
#: VAULT's 43 to HATCHES' 50 and the left's stayed FLOW's 53. Everything in
#: this block that is stated as a measurement was re-run against the layout
#: this file now builds; nothing is inherited from the pre-swap sweep.
#:
#: **Nothing in this body clips in silence at any width, and no seam in the
#: table below is disqualified for going quiet.** That is the one way this
#: body is easier than the ``l`` one, and it needs saying precisely, because
#: the loose form of it invites the wrong conclusion. Every panel here either
#: re-tiers with a marker (FLOW, HATCHES, VAULT, RATCHET) or reflows
#: losslessly (SPLIT), so the sweep never had to reject a candidate the way
#: ``23:10`` and ``12:5`` were rejected next door -- and a rail-bound seam
#: here really would still advertise its loss.
#:
#: What the seam decides instead is **which** panel does the asking, and that
#: is still worth deciding. FLOW writes its marker into its own log body,
#: where every other panel here -- the rail's two included -- *appends* its
#: own to a title and drops it again once
#: the title plus its network word no longer fits (``_pool4.title_text``
#: places ``‹ widen``, then a bare ``‹``, then nothing). So the rail's
#: markers go quiet under enough pressure and FLOW's does not, and a marker
#: that survives one more column is the one to put in front of the reader.
#:
#: The arithmetic floor is therefore 53 + 50 = **103**, and -- unlike the
#: pre-swap 96, which ``5:4`` collected exactly -- **no integer seam collects
#: it**: the two needs are close enough that the nearest seams to 1:1 waste a
#: column to integer flooring. The condition for the left column to bind is
#: ``53/a >= 50/b``, i.e. any seam at or gentler than about **1.06:1**, which
#: is a much narrower window than the pre-swap 1.23:1 and is why the table
#: below has so many more rail-bound rows than its predecessor. The ratio is
#: a guide to where to look; the table is what was actually rendered. Swept
#: over the real screen, column by column, on the arrangement this file
#: currently builds:
#:
#: ==========  =======  ====================  ======  =====  =====
#: seam        pin      marked at pin-1       binder  L@pin  R@pin
#: ==========  =======  ====================  ======  =====  =====
#: ``20:19``   104      ``SurfPool4Flow``     left    53     51
#: ``21:20``   104      ``SurfPool4Flow``     left    53     51
#: ``9:8``     105      ``SurfPool4Hatches``  rail    55     50
#: ``1:1``     **106**  ``SurfPool4Flow``     left    53     53
#: ``8:7``     106      ``SurfPool4Hatches``  rail    56     50
#: ``6:5``     108      ``SurfPool4Hatches``  rail    58     50
#: ``15:16``   110      ``SurfPool4Flow``     left    53     57
#: ``5:4``     111      ``SurfPool4Hatches``  rail    61     50
#: ``9:7``     113      ``SurfPool4Hatches``  rail    63     50
#: ``7:8``     114      ``SurfPool4Flow``     left    53     61
#: ``4:3``     115      ``SurfPool4Hatches``  rail    65     50
#: ``6:7``     115      ``SurfPool4Flow``     left    53     62
#: ``3:2``     123      ``SurfPool4Hatches``  rail    73     50
#: ``2:1``     148      ``SurfPool4Hatches``  rail    98     50
#: ==========  =======  ====================  ======  =====  =====
#:
#: **``8:7`` is the row worth reading twice.** It collects **the same 106**
#: this constant is pinned at and is a different layout entirely: the rail
#: binds there, so the panel a reader watches for the loss is ``HATCHES``
#: rather than the flow log. Two seams with one pin, told apart only by which
#: panel asks for the columns -- which is the whole reason the binder is
#: pinned by a test and not by this paragraph. Before the swap that role was
#: played by ``3:2``, which now collects 123.
#:
#: **``2:1`` is the row that shows how far the swap moved this table.** It
#: was 127 with VAULT binding the rail; with HATCHES in there it is 148 --
#: five columns past ``__main__.FULL_LAYOUT_COLUMNS``. A seam chosen on the
#: old measurement and never re-run would have taken this body out of the
#: app-wide width without anything saying so.
#:
#: **The same table under all THREE payload magnitudes, and that is a
#: measurement rather than a coincidence.** Re-run against the committed
#: capture, against a flow whose every fitted cell is at the widest form its
#: formatter can produce (``fmt_imd``'s 100.00..999.99 six-column band on
#: size, burn and stakers, a four-decimal ETH fee), and against the adopted
#: mainnet payload with its three-way split and five addresses: every pin
#: and every binder in all fourteen rows is identical, with no exceptions.
#: The mainnet column is the one added on 2026-09-02, and it is the one that
#: mattered -- the pre-swap version of this table had been swept on two
#: Sepolia-shaped payloads only.
#: The reason is structural and worth writing down: ``pool4_flow``'s columns
#: are floored at their own **header labels** (``STAKERS`` is seven columns,
#: ``INFERENCE`` nine), and those floors already exceed what the widest data
#: cell needs. This panel is the opposite of the ``l`` body's burn line,
#: whose width moves with its payload and forced that seam's whole argument.
#:
#: **1:1 is pinned, and the three columns above the cheapest seam are bought
#: deliberately** -- the same trade ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS``
#: makes for its own three, and after the swap it is the same size of trade
#: rather than the ten columns this paragraph used to claim. What separates
#: 1:1 (106) from ``20:19``/``21:20`` (104) is not the pin but the
#: **margin**: at 104 the rail gets 51 against the 50 it needs, one column
#: from the edge, while 1:1 hands it **53**. Zero margin on the left column
#: is harmless -- it is the binder, it marks, and a change there moves the
#: pin and lights ``‹ widen`` on the way. Thin margin on the rail is the
#: expensive kind, because the rail's binder is ``HATCHES``, whose marker is
#: **appended to a title** and is therefore the first thing a narrow panel
#: gives up (``_pool4.title_text`` places ``‹ widen``, then a bare ``‹``,
#: then nothing). Three columns is what survives the next format change
#: without a re-sweep nobody will run -- and this is not hypothetical for
#: this body: HATCHES' need is 50 because its widest lever row carries an
#: address window, and ``fmt_imd`` renders 100.00..999.99 at six columns
#: rather than compacting, so one number crossing that boundary is worth two
#: of them.
#:
#: **Two columns is what the margin costs, and it is worth naming as a
#: cost.** 104 is genuinely available and was declined, not overlooked. The
#: reason is the one above plus the tie-break below, and a future reader who
#: disagrees has the table to argue from rather than a sentence.
#:
#: The tie-break inside the qualifying set is the one that chose ``7:6`` for
#: ``#middle-row`` and ``2:1`` for the ``l`` body: prefer the seam a reader can
#: hold in their head. 1:1 is the simplest seam there is and is also the one
#: with the margin, so here the two criteria agree rather than compete.
#:
#: **106, thirty-seven columns under FWA's 143** -- so this task moves neither
#: :data:`SURF_FULL_LAYOUT_COLUMNS` nor ``__main__.FULL_LAYOUT_COLUMNS``, and
#: the ``198 -> 172 -> 143 -> 176 -> 152 -> 143`` record in CLAUDE.md is
#: correctly **not** appended to: that record tracks the app-wide number only.
#: The hero row, mounted in all three modes, clears on its own at **87** and
#: never competes for the binder role here either.
#:
#: **One panel deliberately does not reach its widest tier at this pin.**
#: ``THE SPLIT`` pairs its counters onto shared lines (``burned … · rewarded
#: …``) from **59** panel columns up, and the **left column** -- where the
#: mainnet rebalance put it -- gives it 52 at the pin (53 less the panel's own
#: padding). That is not a loss and must not be treated as one: the narrow
#: layout carries every value, one per line, which is why that panel has no
#: ``‹ widen`` for it to advertise (``widgets/surf/pool4_split.py``'s own
#: docstring), and it is why its measured need is 36 rather than 59. Raising
#: this pin to reach the paired layout would buy a reader nothing but a
#: shorter panel, and would put the body's requirement above the ``l`` body's
#: for a cosmetic reason.
#:
#: **Neither column need may be quoted as a reason for the arrangement, and
#: that warning survived the swap by changing sides.** It used to read "the
#: rail needs 43 *because* HATCHES is not in it, so quoting 43 as the reason
#: HATCHES had to move is circular" -- the W3 follow-up caught exactly that
#: reasoning being reconstructed after the fact. HATCHES is now in the rail
#: and the same trap points the other way: the rail needs 50 *because*
#: HATCHES is in it, and quoting 50 as evidence the swap was right is the
#: identical circle mirrored. The honest comparison is a rendered one and it
#: was run in both directions: **this pin does not move.** 106 with HATCHES
#: in the rail, 106 with it on the left, ``SurfPool4Flow`` binds at 105 under
#: the pinned seam either way, and no width in 80..105 clips without a marker
#: in either. **Width did not choose this arrangement; rows did**, and that
#: measurement lives in :data:`SURF_POOL4_FULL_LAYOUT_ROWS`. See
#: ``POOL4_RAIL_NEED`` in the test module, which carries the same warning
#: beside the literal.
#:
#: **The ADOPTED discovery detail does not move this pin either (D8,
#: 2026-09-02).** Once a mainnet hook is adopted, ``pool4_discovery_detail``
#: becomes WP3's sentence plus ``· tx`` plus a 66-character hash -- ~159
#: characters, on HATCHES -- the panel that binds the **rail**, and that
#: under four of the fourteen seams measured above binds the whole body.
#: Swept 96..152 against an adopted payload: **pin 106, unchanged**, and no
#: unadvertised clip at any width. (This paragraph said HATCHES was "in the
#: binding column" until 2026-09-02. Under the pinned 1:1 seam the binder is
#: ``SurfPool4Flow`` on the left, which is what
#: ``test_the_pool4_binding_panel_is_the_flow_log`` asserts -- the sentence
#: was reasoning from the swap rather than from the sweep.)
#:
#: It cannot move the pin, and the reason is structural rather than lucky:
#: ``pool4_hatches._discovery_markup`` windows the detail to its **tier's**
#: own width (``FULL_WIDTH - indent``, a constant 35 cells) rather than to
#: the panel's, so the line is 47 screen columns at a 99-column panel and at
#: a 260-column one alike. Measured across 106..260 the detail has exactly
#: **one** rendering.
#:
#: That last fact is why no marker is lit for it and why none should be:
#: ``‹ widen`` promises that columns would buy the reader something back, and
#: here they would not. The truncation is visible in the line's own ``…``,
#: and the untruncated value stays in the slot for an auditor. **A content
#: consequence worth knowing about, and not this file's to fix:** what
#: reaches the screen is ``adopted 0xa1B997A9861B2b8aC17B4c61…`` -- the tx
#: citation and the "flags, token and five getters agree" evidence never
#: render at any width. Filed against ``widgets/surf/pool4_hatches.py`` and
#: the producer, not worked around here.
#:
#: So **nothing about the width chose the arrangement.** What it did change is
#: the rail's margin -- ten spare columns instead of three -- and that is a
#: consequence worth having but was not the reason; the reason is rows, and it
#: is argued in :data:`SURF_POOL4_FULL_LAYOUT_ROWS`.
SURF_POOL4_FULL_LAYOUT_COLUMNS = 106

#: The ``p`` POOL4 body's own measured **height**, re-swept 2026-09-02 for
#: the mainnet deployment and then again after the panels were shortened.
#: **43 -> 44 -> 46 -> 44.**
#:
#: **What mainnet did to this body.** The reward split became three-way
#: inside a Distributor, so ``SurfPool4Split`` went 12 rows -> 15; the
#: inventory ceiling arrived, so ``SurfPool4Ratchet`` gained a line; and
#: ``SurfPool4Hatches`` gained the topology and provenance lines. That is
#: what took the pin to 46.
#:
#: **What brought it back to 44** was not this file: WP4 took four rows of
#: whitespace out of ``widgets/surf/pool4_hatches.py`` and merged one more,
#: which is the standing "shorten the value, do not raise the pin" rule
#: applied where the rows actually are. It is worth recording what that
#: package **refused** to do, because the cheap version of the same saving
#: was available and would have been a silent loss: a ``MAX_ROWS`` of ten
#: reaches 44 too, and it does it by cutting the hook's burn-sink row --
#: whose destination changed on mainnet from ``0x…dEaD`` to a BurnExecutor,
#: which is exactly the lever a reader opens this panel to check -- and
#: bonding's deployed row, live since the Distributor landed and carrying
#: 40% of the reward share. Two rows of blank space and two rows of evidence
#: cost the same number of rows and are not the same thing.
#:
#: Measured through the real app, every payload the widgets can render
#: crossed with every network shape, at 150 columns and 34 rows (where both
#: columns sit on their floors, so each column's ``virtual_size`` is its
#: real content rather than the terminal's height):
#:
#: ===========================  =====  =======  ====  =====  =====  ====  ====  ====
#: payload                      SPLIT  RATCHET  FLOW  HATCH  VAULT  left  rail  need
#: ===========================  =====  =======  ====  =====  =====  ====  ====  ====
#: sepolia, 0 levers            12     10       6     10     12     30    23    41
#: sepolia, 8 levers            12     10       6     17     10     30    28    41
#: sepolia, 10 levers           12     10       6     19     10     30    30    41
#: sepolia, 12 levers           12     10       6     21     10     30    32    43
#: mainnet, 0 levers            15     10       6     11     11     33    23    **44**
#: mainnet, 8 levers            15     10       6     18     10     33    29    **44**
#: mainnet, 10 levers           15     10       6     20     10     33    31    **44**
#: mainnet, 12 levers           15     10       6     22     10     33    33    **44**
#: mainnet, 12 levers, long     15     10       6     22     10     33    33    **44**
#: flow log
#: ===========================  =====  =======  ====  =====  =====  ====  ====  ====
#:
#: ``need`` is ``max(left, rail) + 11``, and the **11 is chrome measured
#: rather than assumed** -- the hero, the title bar, the status bar and this
#: body's own top margin. It is identical on all nine rows, which is what
#: makes the column figures comparable at all.
#:
#: **The two ``23``s in the rail column are ceilings, not content**, and the
#: distinction matters more than the number. The harness hands each column
#: 34 − 11 = 23 rows; a column holding less than that reports 23 anyway,
#: because its ``1fr`` child grows to fill the slack. Both rows where it
#: happens are rows where the rail is nowhere near binding, so no ``need``
#: in the table rests on one -- but a reader taking 23 as "the no-lever
#: rail's content" would be reading the harness rather than the layout. Every
#: other figure is a genuine ``virtual_size`` overflowing its column.
#:
#: **The worst case is 33 rows of content and it is reached by BOTH columns**
#: at the twelve-lever mainnet payload -- left 33 (SPLIT 15 + RATCHET 10 +
#: FLOW's ``min-height`` 6 + two inter-panel margins), rail 33 (HATCHES 22 +
#: VAULT's floor 10 + one margin). That balance is the whole reason the
#: columns were rebalanced when mainnet landed: on the pre-swap arrangement
#: (HATCHES over FLOW on the left, SPLIT/RATCHET/VAULT in the rail) the rail
#: carried 38 rows on mainnet against the left's 20 and the body needed 49.
#: Moving THE SPLIT and THE RATCHET across and HATCHES back bought three rows
#: for a change of ``compose`` order alone -- every panel kept its role
#: (``auto`` with a margin, or the column's ``1fr`` with its floor) and not
#: one CSS rule moved.
#:
#: **The width was re-measured, not assumed, after that swap**, and it did
#: not move: the left column still needs FLOW's 53 and the rail now needs
#: HATCHES' 50 (it needed VAULT's 43 before the swap), so the arithmetic
#: floor went 96 -> 103 while :data:`SURF_POOL4_FULL_LAYOUT_COLUMNS` stayed
#: **106** and ``SurfPool4Flow`` is still the binder at 105. That constant
#: carries the re-run per-seam table.
#:
#: **The property this constant used to claim is gone, and saying so is the
#: point.** It read "the pin is a constant under every payload, because every
#: panel whose line count answers to the data is kept out of the binding
#: column". That was true and it is no longer achievable: HATCHES (10..22
#: rows) and THE SPLIT (12 on Sepolia, 15 on mainnet) are now *both*
#: payload-sized, and any two-column arrangement of these five puts one of
#: them in the binder -- the table above shows the taller column switching
#: from the left to the rail as the lever list grows (on Sepolia it crosses
#: at twelve levers; on mainnet the two tie at 33). What replaced the old
#: property is weaker and honest: the pin is the **worst case over every
#: payload the widgets can render**, which is the twelve-lever list at
#: ``pool4_hatches.MAX_ROWS``.
#:
#: Pinning against ``MAX_ROWS`` rather than the ten levers the producer emits
#: today is deliberate and follows ``SURF_LAUNCHPAD_FULL_LAYOUT_ROWS``, which
#: pins against the coin table's ten-row cap rather than the two-row fixture.
#: Here it happens to cost nothing -- mainnet needs 44 at every lever count
#: from zero to the cap, because the left column binds until the rail catches
#: it -- but that is a fact about today's line counts, not a reason to stop
#: measuring the cap.
#:
#: **THIS PIN ASSUMES sIMD VAULT'S CONTENT NEVER EXCEEDS ITS FLOOR, and that
#: is a coupling rather than a detail.** VAULT carries the rail's ``1fr``
#: *because* its line count is fixed and small, so ``min-height: 10`` is
#: effectively its ceiling too and the panel is never cut. A ``1fr`` child
#: cannot overflow -- it shrinks -- so a VAULT that grows past ten lines
#: does not push the column taller and does not raise this pin: it **loses
#: the line**, with no scrollbar and no marker, while the rail's
#: ``virtual_size`` goes on reporting the floored ten. The pin would still
#: measure 44 while the body silently dropped a row.
#:
#: **That is not hypothetical -- it happened on 2026-09-02.** A rewording of
#: the delivery row took VAULT to eleven lines, and the pin went on
#: measuring 44 with the eleventh row being cut. Measured at the time:
#: **an eleven-line VAULT needs a pin of 45.** It was fixed at source
#: instead, by dropping the panel's post-title blank, which is the standing
#: rule working -- shorten the value, do not raise the pin. VAULT now sits
#: under its floor with a row of slack, so the next line added there fails a
#: test rather than vanishing.
#:
#: The guard is not this constant, it is
#: ``test_the_pool4_floors_never_thin_a_panel_below_its_content``, which
#: compares VAULT's laid-out height against its own content. Keep it: the
#: pin cannot detect this failure, because the failure is precisely a body
#: that stops asking for the rows it needs.
#:
#: **44 is the tallest pinned requirement in this repo and nobody has
#: measured whether a common laptop clears it.** The *columns* side of that
#: question is answered in the terminal-layout skill (launch forces 17 pt,
#: about 169 columns); the rows side is open, and it is filed as W7 rather
#: than estimated here. What can be said is the consequence rather than the
#: threshold: the ``l`` body is pinned at
#: :data:`SURF_LAUNCHPAD_FULL_LAYOUT_ROWS` (31), so a terminal that clears
#: that one and not this one loses ``p`` alone, with ``‹ taller`` lit and
#: both columns scrolling -- degraded, never silent, and never a row cut
#: without a marker. That is what makes W7 a question worth answering
#: calmly rather than a defect.
#:
#: **The row marker itself was stale until the 2026-09-02 sweep**, which is
#: why the numbers before it were a row optimistic: see ``_render_title``,
#: where a one-row overflow settled a layout pass after the callback that
#: composed the title, leaving ``‹ taller`` dark on a body that was
#: scrolling.
SURF_POOL4_FULL_LAYOUT_ROWS = 44

#: The **three** bodies ``l``/``p``/``escape`` swap between, named on
#: curator's MODE_DASHBOARD/MODE_ANALYSIS precedent.
#:
#: This comment said "the two bodies ... this screen only ever needs two, so
#: there is no MODE_WALLET/MODE_LIST sibling to grow into" until 2026-09-01,
#: and the sentence was wrong the way a prediction is wrong rather than the
#: way a fact is: curator grew from two modes to four and so has this screen.
#: What the sentence was really protecting is worth keeping, so it is restated
#: as a rule instead of as a count: **a mode is a whole second body with its
#: own panels, never two panels sharing one slot** -- that was ``c``, and ``c``
#: is gone. :data:`MODE_POOL4` is a third body on that rule, not a fourth key
#: hiding half the screen.
MODE_DASHBOARD = "dashboard"
MODE_LAUNCHPAD = "launchpad"
MODE_POOL4 = "pool4"

#: The launchpad body's container id -- exported so the test module and any
#: future consumer can query it without retyping the literal.
LAUNCHPAD_BODY_ID = "surf-launchpad-body"

#: The launchpad body's LEFT column (2026-08-25), holding LAUNCHPAD COINS
#: over LAUNCHPAD ACTIVITY. It became a column when the coin table was capped
#: at ten rows: a capped table has no use for the body's spare rows, and a
#: feed does -- so the rows the table can no longer spend go to the panel
#: whose content is unbounded, which is the same "rows are the scarce
#: currency in this body" trade the 2026-08-24 rail made in the other
#: direction. Exported for the same reason as :data:`LAUNCHPAD_BODY_ID`.
LAUNCHPAD_LEFT_ID = "surf-launchpad-left"

#: The launchpad body's right rail (2026-08-24), holding CURVE FLOW over BURN
#: PIPELINE (and BURNKEEPERS since 2026-08-25) beside the coin table --
#: ``#surf-right-rail``'s opposite number in the other body, and named for
#: it. Exported for the same reason as :data:`LAUNCHPAD_BODY_ID`: the id is
#: queried from the test module and retyping a literal in two files is how
#: one of them goes stale.
LAUNCHPAD_RAIL_ID = "surf-launchpad-rail"

#: The ``p`` POOL4 body's container id (2026-09-01) -- the third body, on
#: :data:`LAUNCHPAD_BODY_ID`'s own contract: composed once, hidden by
#: ``display``, swapped in by ``_show_mode``. Exported for that constant's
#: reason -- the id is queried from the test module, and retyping a literal in
#: two files is how one of them goes stale.
POOL4_BODY_ID = "surf-pool4-body"

#: The POOL4 body's LEFT column: **THE SPLIT over THE RATCHET over POOL4
#: FLOW**.
#:
#: The columns are split by **how tall each panel is**, and after the mainnet
#: rebalance the split is a balance rather than a segregation: this column
#: carries 33 rows at the worst payload and the rail carries 33 too, which is
#: what took :data:`SURF_POOL4_FULL_LAYOUT_ROWS` from 49 to 44 without one
#: CSS rule moving. THE SPLIT is itself payload-sized now (12 rows on
#: Sepolia, 15 on mainnet's three-way Distributor split), so the older
#: arrangement's promise -- keep every payload-sized panel out of the binding
#: column -- is no longer available to any two-column cut of these five
#: panels. See that constant for the measurement and the alternative.
#:
#: Exactly one child per column carries ``1fr``, and here it is POOL4 FLOW:
#: it is a ``RichLog``, so shrinking it moves rows behind its own scrollbar
#: rather than off the layout. THE SPLIT and THE RATCHET are ``height: auto``
#: beside it precisely because they are *not* safe to shrink -- a plain
#: ``Vertical`` holding a ``Static`` loses clipped rows with no scrollbar and
#: no trace.
#:
#: **This block has now been wrong twice and both are recorded rather than
#: quietly overwritten**, because a ``#:`` block is the authority here *only*
#: because it sits beside the code, and one that drifts is worse than none.
#: It read "THE SPLIT over POOL4 FLOW" until the W3 follow-up, which was the
#: pre-swap arrangement; it was then corrected to "HATCHES over POOL4 FLOW",
#: which the mainnet rebalance invalidated the same day
#: :data:`SURF_POOL4_FULL_LAYOUT_ROWS` recorded that rebalance three hundred
#: lines above.
#:
#: **Twice is a pattern, not an accident, and it is now a test rather than a
#: habit.** This pair goes stale every time the body is recut, and each of
#: those was a human noticing months later -- plus a third round trip spent
#: refuting a false alarm raised against a pre-edit copy. So the opening
#: bold sentence above is parsed and compared against what ``compose``
#: actually builds by
#: ``tests/screens/test_surf_screen.py``'s
#: ``test_the_pool4_column_blocks_name_the_panels_compose_builds``. **The
#: convention that test pins: this block leads with a bold run naming its
#: panels top to bottom, joined by "over".** Keep that shape, and a future
#: rebalance that moves a panel without moving the sentence fails on its own
#: commit instead of being rediscovered. What the test does not cover is the
#: ``1fr`` claim below, which is guarded against ``minimal.tcss`` by
#: ``test_exactly_one_pool4_child_per_column_carries_the_fr``.
POOL4_LEFT_ID = "surf-pool4-left"

#: The POOL4 body's right rail: **HATCHES over sIMD VAULT**.
#: ``#surf-launchpad-rail``'s opposite number in the third body, and named
#: for it.
#:
#: HATCHES is the panel whose line count moves furthest with the data -- ten
#: rows with no levers, twenty-two at ``pool4_hatches.MAX_ROWS`` -- and sIMD
#: VAULT's ten are a constant. Their sum is what makes this column 33 rows at
#: the worst payload, level with the left column's 33; see
#: :data:`SURF_POOL4_FULL_LAYOUT_ROWS` for why balancing the two was worth
#: three rows of pin.
#:
#: **``sIMD VAULT`` carries the rail's ``1fr``, and it is the panel with the
#: fixed line count on purpose** -- the opposite of the rule the left column
#: and both other bodies follow. A ``1fr`` child shrunk below its content
#: loses those rows silently unless it scrolls inside itself, and of this
#: body's five panels only POOL4 FLOW does. VAULT's nine lines and blank are
#: a constant, so ``min-height: 10`` is both its floor and its ceiling and it
#: cannot be cut at any height. HATCHES is ``auto`` above it for the same
#: reason inverted: it is the panel that would actually be cut, and a cut
#: HATCHES row is a lever the reader was asked to trust and never saw. The
#: price is that the rail's spare rows land in VAULT as blank space on a tall
#: terminal.
#:
#: **HATCHES is also the panel this column binds on**, at 50 columns -- and
#: its ``‹ widen`` is *appended to a title*, so it is the first marker a
#: narrow panel gives up. That is why the pinned seam buys this column three
#: columns of margin rather than taking the two-column-cheaper seam;
#: :data:`SURF_POOL4_FULL_LAYOUT_COLUMNS` carries the table.
#:
#: **This block has been wrong twice too.** It read "THE RATCHET over sIMD
#: VAULT over HATCHES ... HATCHES carries the rail's 1fr" until the W3
#: follow-up, then "THE SPLIT over THE RATCHET over sIMD VAULT" until the
#: mainnet rebalance moved those two to the left column. Both times the
#: authority was ``compose``, and both times a reader had two ``#:`` blocks
#: in one file disagreeing about which panel carries a ``1fr`` with no way to
#: tell which half to believe.
#:
#: **Its opening bold sentence is checked against ``compose`` by the same
#: test that checks :data:`POOL4_LEFT_ID`'s** --
#: ``test_the_pool4_column_blocks_name_the_panels_compose_builds``, which
#: runs once per column. See that constant for the convention and for why a
#: recurring documentation defect was worth a test rather than a third
#: correction.
POOL4_RAIL_ID = "surf-pool4-rail"


# -- format helpers ----------------------------------------------------


def _num(value, default: float = 0.0) -> float:
    """Coerce to ``float``, falling back to ``default`` — never raise."""
    if value is None or isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return out


def _fmt_int(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _EMDASH


def _fmt_usd(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"${out:,.2f}"


def _fmt_signed_pct(value) -> str:
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        out = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if out != out:
        return _EMDASH
    return f"{out:+.1f}%"


def _fmt_age(value) -> str:
    """``42s`` / ``17m`` / ``23h`` / ``3d`` — or an em-dash for ``None``.

    90 is the seconds/minutes boundary and 90 min the minutes/hours boundary
    (``5400.0`` renders ``90m``); 36 h is the hours/days boundary — the same
    tiers the sparkline axis uses.
    """
    if value is None or isinstance(value, bool):
        return _EMDASH
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return _EMDASH
    if seconds != seconds or seconds < 0:
        return _EMDASH
    if seconds < 90:
        return f"{int(seconds)}s"
    if seconds <= 90 * 60:
        return f"{int(seconds // 60)}m"
    if seconds < 36 * 3600:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _fmt_hhmm(ts) -> str:
    """An epoch stamp as local ``HH:MM``, or the em-dash when there is none.

    Deliberately **not** a clock read: the value is handed in, so this stays
    as deterministic as every other formatter on this row (CLAUDE.md's
    "inject the clock" -- the rule is about *reading* the time, and nothing
    here does).  ``None`` is the honest state on a cold cache, and it renders
    ``as of —`` rather than disappearing: a freshness marker that vanishes
    when there is nothing to be fresh about is the FARM/HOUR SAVED bug.
    """
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return _EMDASH
    try:
        return time.strftime("%H:%M", time.localtime(float(ts)))
    except (ValueError, OSError, OverflowError):
        return _EMDASH


def _fmt_degraded(sources) -> str:
    """``· ⚠ logs, market`` — or an empty string when all is well.

    Only ``None``/``[]`` (or anything else falsy) genuinely mean "nothing is
    degraded" and may render empty. Every other input must render
    *something* visibly wrong, even if it is a shape the manager should
    never actually produce: a bare ``except: return ""`` here would let a
    malformed ``degraded`` value collapse the title bar to the healthy line
    on the single most prominent row of the screen, which is the exact
    failure this whole project exists to prevent.

    The prefix was the word ``degraded: `` until 2026-08-12. ``⚠`` is this
    codebase's warning idiom already (``⚠ feed unavailable``, ``⚠ sales
    unavailable``, ``⚠ LP owner changed`` on this very row), so it needs no
    new vocabulary and buys eight columns back on a row whose overflow is
    *silent*. The **names** are untouched: they are the manager's own
    ``SOURCES`` members and nothing here abbreviates or re-words them.
    """
    if not sources:
        return ""

    # A bare string is one group name, not a sequence of one-letter groups
    # (``"logs"`` iterates to ``"l", "o", "g", "s"`` otherwise).
    if isinstance(sources, (str, bytes)):
        sources = [sources]

    try:
        names = [str(s).strip() for s in sources if str(s).strip()]
    except TypeError:
        # Truthy but not iterable (an int, a float, ...) -- an unexpected
        # shape the manager never emits today, but "unreachable today" is
        # not a reason to fail toward looking healthy.
        return " · ⚠ ?"

    if not names:
        return " · ⚠ ?"
    return " · ⚠ " + ", ".join(names)


def _title_line(data: dict, row_hint: bool = False) -> str:
    """Compose the meta row (PRD §4).

    Ordered by what must survive a narrow terminal, because ``#title-bar`` is
    ``height: 1`` around a wrapping ``Static``: everything past the first
    line reaches no pixel at all -- no ``…``, no scrollbar, no trace. The tail
    of this string is not "clipped", it is *gone*, so the order here is the
    only priority mechanism the row has. Parity renders with the em-dash
    fallback rather than a zero: a dead market source must never read as
    perfect parity.

    ``row_hint`` -- the height counterpart of a widget's ``‹ widen`` -- comes
    **first**, ahead of both warnings. It used to sit after the degraded list,
    which meant the one advertisement on this screen with no second home was
    lost exactly when a source was also down: the outermost guard emits
    ``list(SOURCES)``, so a failed cycle plus the LP warning runs this line to
    133 columns, and at 100 the wrap falls inside the list. It took only
    three groups to reach past a 100-column terminal, and a full outage --
    when the row is read most -- lights all six. The warnings are each
    mirrored inside a panel (the LP flag is
    the hero's ``OWNER CHANGED`` box; a degraded group is that panel's own
    unavailable state), and nothing anywhere else says a row went off the
    bottom of the rail -- so if exactly one of the three has to survive a
    narrow terminal, it is this one.

    **There is no version tail any more** (2026-08-12). It used to end
    ``· v0.6.0``, which the StatusBar three rows down already renders -- nine
    columns of the one row on this screen that cannot ellipsise, spent saying
    something twice. Dropping it, and shortening ``degraded: `` to ``⚠ ``,
    took the worst-case line 145 -> 133 columns even after ``SURF`` grew into
    ``SURFBOARD``; see
    ``tests/screens/test_surf_screen.WORST_CASE_TITLE_COLUMNS``, and
    ``test_the_status_bar_still_carries_the_version_to_a_pixel`` for the
    other half of that argument -- the StatusBar has to actually render it.

    **``as of HH:MM`` arrived, and ``feed #N (age)`` paid for it** (final fix
    wave, I4 -- the same argument as the version tail, one segment further
    on). This screen had *no* freshness signal anywhere: opting into the
    StatusBar's ``KEY_HINTS`` costs both ``tab switch`` and ``updated Ns
    ago`` (``StatusBar._ordinary_status``), and unlike curator -- which makes
    exactly that trade -- surf had no title-bar marker to fall back on. That
    was survivable while every tier moved on the poll loop; it stopped being
    survivable when the launchpad arrived as a **detached** sweep whose only
    ``as of`` marker lives inside the hidden ``l`` body. A wedged refresh
    worker now shows a stalling clock instead of confident numbers.

    ``feed #N (age)`` is what it cost, and the announce panel's own title
    already renders both halves of it verbatim (``ANNOUNCE · #14 · last 23h
    ago``, ``widgets/surf/feed.py``) -- seventeen columns of the one row that
    cannot ellipsise, spent saying something twice. The row is measured, not
    counted: adding the marker without paying for it took the worst case past
    ``SURF_FULL_LAYOUT_COLUMNS``, where the tail is *gone* rather than
    clipped, and this repo's standing rule is to shorten the copy rather than
    widen the layout. The marker is not optional and rides ahead of both
    warnings and the row hint, matching curator's order.
    """
    line = (
        f"SURFBOARD · IMD {_fmt_usd(data.get('imd_price_usd'))} · "
        f"parity {_fmt_signed_pct(data.get('parity_pct'))} · "
        f"as of {_fmt_hhmm(data.get('as_of'))}"
    )

    if row_hint:
        line += f" · [yellow]{TALLER_HINT}[/]"

    if data.get("lp_owner_ok") is False:
        line += " · [yellow]⚠ LP owner changed[/]"

    line += _fmt_degraded(data.get("degraded"))
    return line


class SurfScreen(RefreshGuard, Screen):
    """surfsurf.eth Surfboard dashboard."""

    #: Still no ``c``: the swap it drove died with the shared slot (see the
    #: module docstring), and nothing here has grown a second shared slot for
    #: it to revive.
    #:
    #: ``l``/``escape`` (2026-08-23) are a different shape of key, not a
    #: return of ``c``. This comment used to say a key that hides half the
    #: screen has nothing to offer this layout -- that was true of ``c``,
    #: which swapped two panels that were both worth seeing inside one slot,
    #: but ``l`` swaps the whole dashboard body for an unrelated second view
    #: (curator's ``y``/``f`` precedent), and the hero row it leaves mounted
    #: is the reason that is safe: nothing the hero tracks ever goes dark.
    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("l", "toggle_launchpad", "Launchpad", show=False),
        Binding("p", "toggle_pool4", "Pool4", show=False),
        Binding("escape", "show_dashboard", show=False),
    ]

    #: Named in the status bar's left label (``StatusBar.set_key_hints``),
    #: curator's own vocabulary (``"c panels · y you · f linked · l lists"``)
    #: -- this screen's sole entry. Opting in trades the bar's ``updated Ns
    #: ago`` freshness segment for this hint (``StatusBar._ordinary_status``).
    #:
    #: That trade used to be made on the argument that the title bar's own
    #: ``feed #N (age)`` "gestures at" freshness. It does not: that is the age
    #: of the last announce POST, not of the data, and it sits still for weeks
    #: at a time while the dashboard keeps polling. So the hint was bought
    #: with the screen's only freshness signal and nothing replaced it -- a
    #: wedged refresh worker showed confident numbers with no staleness marker
    #: anywhere, on the one dashboard that had just gained a **detached**
    #: sweep. The trade is fine; the missing half was. ``_title_line`` now
    #: carries curator's own ``as of HH:MM`` fallback, which is what made
    #: opting in defensible there in the first place.
    #:
    #: One markup run, not curator's "``[dim]l[/]`` letter, plain word" split:
    #: Rich/Textual compositing keeps adjacent differently-styled runs as
    #: separate ``Segment``s, so a letter-only ``[dim]`` tag would put ``l``
    #: and `` launchpad`` in two segments that never sit on the same
    #: composited line together -- and the app-level acceptance test greps
    #: for the whole phrase ``l launchpad`` as one contiguous string.
    #:
    #: **``· p pool4`` joined it on 2026-09-01, inside the same single run**,
    #: for that same reason and one more: the two halves are now separated by
    #: a `` · `` that a per-half tag would strand in a third segment of its
    #: own. Curator's ``"c panels · y you · f linked · l lists"`` is the
    #: shape, and the separator is its `` · `` verbatim.
    #:
    #: **Measured against ``StatusBar``'s own left-label budget at the full
    #: layout width, not assumed to fit.** This hint is nine columns longer
    #: than what shipped, and the bar's left label is the segment that gets
    #: cut when it runs out -- see
    #: ``test_the_pool4_key_hint_fits_the_status_bar_at_the_full_layout``,
    #: which reads the phrase back off composited output at
    #: :data:`SURF_FULL_LAYOUT_COLUMNS` rather than counting characters.
    KEY_HINTS = "[dim]l launchpad · p pool4[/]"

    #: Worker name for the guarded refresh (see RefreshGuard).
    REFRESH_WORKER_NAME = "surf-refresh"

    # Structural fallback only. WP6 restates these in themes/minimal.tcss
    # (one owner) the way the FWA block does, app-stylesheet rules then beat
    # DEFAULT_CSS. They live here so the screen is reviewable and correctly
    # proportioned on its own, under any theme that has no surf block. The
    # two copies must stay in agreement -- edit both or neither.
    #
    # `#hero-row` is `height: auto` and carries NO vertical padding. SurfHero
    # is a height-7 widget whose boxes hold five content lines inside a
    # height-7 frame; one row of vertical padding here clips the bottom
    # border off the screen, which is the FWA hero-clipping bug. `auto` also
    # replaces the old `height: 10`, whose three spare rows were the dead
    # space above the feed.
    #
    # `#middle-row` is the ONLY `1fr` row on the screen, so every row a
    # taller terminal adds lands in the feed and the activity panel.
    # `#bottom-row` is `auto`: the market's seven rows and the NFT panel's
    # eight are content, not slack, and a `1fr` here used to hand them half
    # the screen's spare rows.
    #
    # Inside the rail SurfSignals is `auto` -- a title, a spacer and six
    # detector rows, exactly 8 -- plus a one-row bottom margin, the blank line
    # that stops the two rail panels reading as one block. A margin, not a
    # spacer widget: nothing to compose or query, and it collapses into the
    # rail's scroll extent like any other row, so `TALLER_HINT` still accounts
    # for it (that marker moved 35 -> 36 rows, and the first real loss 33 ->
    # 34, so it still leads the loss by two).
    # SurfDevActivity takes the remainder at
    # `1fr` with a `min-height` floor. The floor is the load-bearing part: a
    # `1fr` child cannot overflow its scroll container, it shrinks, so
    # without one the activity panel would shed a row per terminal row down
    # to a bare title with no scrollbar, no marker and no trace on screen.
    # SurfMarket did precisely that from this rail until 2026-08-09.
    # With the floor the rail's content height is a constant
    # 8 + ACTIVITY_MIN_HEIGHT, which is what makes the overflow, the
    # scrollbar and the title bar's `‹ taller` fire on the same terminal row.
    #
    # Vertical padding on SurfSignals costs the sixth detector row -- BURN --
    # while the panel still looks complete. tests/test_surf_registration.py
    # asserts all six reach the compositor.
    #
    # The rail scrolls (`overflow-y: auto`, at the stylesheet-wide
    # `scrollbar-size: 1 1`) as the short-terminal guard. Scrolling is the
    # *affordance* -- nothing is dropped, it is all still reachable. The
    # *advertisement* is `TALLER_HINT` on the title bar, because a one-cell
    # scrollbar in a gutter names nothing, and at very short heights Textual
    # paints it outside the rail's own rectangle.
    #
    # Both rows below the hero split 7:6 on the same seam: SurfFeed/SurfMarket
    # take `7fr`, the rail/SurfNft `6fr`. Measured, not chosen -- the seam has
    # to serve the feed's need for an unbroken post and the rail's before the
    # activity panel sheds a field, and their sum is the floor. Those needs
    # were 81 and 71 when 7:6 was picked (floor 152); they are 76 and 63 now
    # (floor 139, collected at 142 by this seam). This was 3:2 until
    # 2026-08-10, which over-fed the left column and pushed the full layout to
    # 176 -- and still costs 156 today. Equal shares are wrong in the other
    # direction: 1:1 starves the feed and costs 152. The dated sweep and the
    # reason those last three columns stay unspent are in the module docstring.
    DEFAULT_CSS = """
    SurfScreen #title-bar {
        width: 100%;
        height: 1;
        text-align: center;
        content-align: center middle;
    }
    SurfScreen #hero-row {
        height: auto;
        margin: 1 0 0 0;
    }
    SurfScreen SurfHero {
        width: 1fr;
        padding: 0 1;
    }
    SurfScreen #middle-row {
        height: 1fr;
        margin: 1 0 0 0;
    }
    SurfScreen SurfFeed {
        width: 7fr;
        padding: 0 1;
    }
    SurfScreen #surf-right-rail {
        width: 6fr;
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }
    SurfScreen SurfSignals {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SurfScreen SurfDevActivity {
        width: 1fr;
        height: 1fr;
        min-height: 7;
        padding: 0 1;
    }
    SurfScreen #separator {
        width: 100%;
        height: 1;
        padding: 0 2;
    }
    SurfScreen #bottom-row {
        height: auto;
        margin: 0 0 1 0;
    }
    SurfScreen SurfMarket {
        width: 7fr;
        height: auto;
        padding: 0 1;
    }
    SurfScreen SurfNft {
        width: 6fr;
        height: auto;
        padding: 0 1;
    }

    /* The ``l`` LAUNCHPAD body (2026-08-23): composed hidden, shown in place
     * of #middle-row/#separator/#bottom-row by `_show_mode`. `1fr` so the
     * coin table -- the one panel here with real content to scroll -- gets
     * the screen's spare rows the same way #middle-row does in dashboard
     * mode. `margin: 1 0 0 0` matches #middle-row's own top margin, so
     * swapping bodies does not also move the hero's breathing room.
     *
     * A ROW since 2026-08-24, on #middle-row's own shape: the coin table
     * left, a rail of CURVE FLOW over BURN PIPELINE right. Stacked, the two
     * summary panels took eleven rows off the one panel here that has rows
     * to lose -- their ten lines are label/value text that never grows,
     * while the table's row count is the launchpad's own population.
     *
     * The seam is `2fr:1fr`, RE-SWEPT for the five-panel body (2026-08-25)
     * and deliberately NOT the `12fr:5fr` it replaces, the `7fr:6fr` this
     * body was built with, or the 7:6 the other two rows use. Do not "tidy"
     * it into agreement with them: this body balances a fixed-width
     * `DataTable` (92 screen columns, immovable) against a rail of short
     * label/value lines (40 against the committed capture, 43 against an
     * ordinary one), where #middle-row balances a wrapping feed against a
     * rail that both give ground.
     *
     * IT IS NOT THE CHEAPEST SEAM, ON PURPOSE. `23:10` and `7:3` collect
     * the arithmetic floor at 132; both are DISQUALIFIED, because between
     * the floor and the width the rail actually needs the binding panel is
     * `SurfBurnPipeline` -- a plain label/value `Static` with no `< widen`
     * of its own, so it clips in silence. That is the same test that
     * rejected `5:2` in the 2026-08-24 sweep, and the old `12fr:5fr` seam
     * fails it too: 131..132 clipped the accrued/staged line with nothing
     * on screen saying so. `13:6` and `15:7` survive it at 135, and are
     * still not this seam: they hand the rail exactly the 43 it needs,
     * where 2:1 hands it 46. Zero margin is safe only where the binder can
     * mark, and the rail's binder cannot: BURNKEEPERS and LAUNCHPAD
     * ACTIVITY do carry markers but clear at 37 and 48, well under the
     * rail's 40..43, so what asks for the columns is always
     * `SurfBurnPipeline` or `SurfCurveFlow` -- the two plain `Static`s.
     * One format change reopens the window; that need moved 39 -> 40 in
     * this same task series. 2:1 keeps the marked coin table the
     * binder under every payload and pins at 138. The full per-seam table,
     * both payload magnitudes, is in
     * `SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`'s own docstring.
     *
     * BOTH columns scroll and BOTH carry `scrollbar-gutter: stable`, for
     * curator's reason (`#curator-right-rail`): without the gutter the
     * scrollbar takes its column out of the panel beside it only on
     * terminals short enough to overflow, so the layout's WIDTH requirement
     * would move with its HEIGHT and a width pin measured at 48 rows would
     * be one column short at 40. `#surf-launchpad-left` had neither until
     * 2026-08-25 -- a `Vertical` defaults to `overflow: hidden hidden`, so
     * below 22 rows the activity feed was clipped out of the column with no
     * scrollbar, no marker and no other trace. `SURF_LAUNCHPAD_FULL_LAYOUT_
     * ROWS` is the height at which neither column needs to scroll.
     *
     * FIVE PANELS IN TWO COLUMNS since 2026-08-25. The left half is a
     * `#surf-launchpad-left` column rather than the bare table it was,
     * because the coin table is now capped at ten rows: a capped table has
     * no use for the body's spare rows, so LAUNCHPAD ACTIVITY -- a feed,
     * whose content is unbounded -- takes them instead. That is why
     * `SurfLaunchpadCoins` is `auto` here and its own `DataTable` is
     * overridden to `auto` one rule down: leaving the table at the `1fr`
     * its widget DEFAULT_CSS declares would have it claim the column's
     * spare rows from inside an auto-sized parent, which is the whole of
     * what this change is undoing. (The override lives here rather than in
     * `widgets/surf/launchpad.py` only because that module belongs to
     * another work package this wave; it should move inward.)
     *
     * WHICH PANEL IN EACH COLUMN CARRIES THE `1fr`, AND ITS FLOOR, IS THE
     * LOAD-BEARING PART. Exactly one child per column may be `1fr`, and it
     * must be the one with content to spend rows on: LAUNCHPAD ACTIVITY on
     * the left, BURNKEEPERS in the rail. Every other panel is `auto` --
     * SurfCurveFlow (five lines) and SurfBurnPipeline (six) never grow, and
     * both carry the one-row bottom margin `SurfSignals` uses in the other
     * rail, since flush they read as one block. Each `1fr` child is floored
     * (`min-height`), and that floor is not decoration: a `1fr` child cannot
     * overflow a scroll container -- it SHRINKS -- so without one it sheds a
     * line per terminal row down to a bare title with no scrollbar and no
     * trace, exactly what `min-height` under `SurfDevActivity` exists to
     * stop. 6 is LAUNCHPAD ACTIVITY's title + blank + four rows; 5 is
     * BURNKEEPERS' title + blank + the three burnkeeper rows the sweep has
     * ever returned.
     */
    SurfScreen #surf-launchpad-body {
        height: 1fr;
        width: 100%;
        margin: 1 0 0 0;
    }
    SurfScreen #surf-launchpad-left {
        width: 2fr;
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen SurfLaunchpadCoins {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    SurfScreen SurfLaunchpadCoins > DataTable {
        height: auto;
    }
    SurfScreen SurfLaunchpadActivity {
        width: 1fr;
        height: 1fr;
        min-height: 6;
        padding: 0 1;
    }
    SurfScreen #surf-launchpad-rail {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen SurfCurveFlow {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SurfScreen SurfBurnPipeline {
        width: 1fr;
        height: auto;
        min-height: 6;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SurfScreen SurfBurnkeepers {
        width: 1fr;
        height: 1fr;
        min-height: 5;
        padding: 0 1;
    }

    /* The ``p`` POOL4 body (2026-09-01): the THIRD body on this screen, and
     * a copy of the `l` body's structure rather than a new idea -- composed
     * once and hidden by `display`, swapped in by `_show_mode`, hero left
     * mounted above it. `margin: 1 0 0 0` matches `#middle-row`'s and
     * `#surf-launchpad-body`'s, so swapping between any two of the three
     * bodies never moves the hero's breathing room.
     *
     * THE SEAM IS `1fr:1fr`, MEASURED FOR THIS BODY AND NOT INHERITED. It is
     * deliberately not the `l` body's 2:1 and not the other two rows' 7:6.
     * This body balances a fitted `RichLog` (POOL4 FLOW, needing 53 screen
     * columns) on the left against a rail whose widest need is HATCHES' 50
     * -- and 1:1 hands the rail 53, three columns of margin on a panel whose
     * `‹ widen` is appended to a title and is therefore the first marker a
     * narrow panel gives up. The left column has to be the binder, because
     * POOL4 FLOW writes `‹ widen` into its own log body and never goes
     * quiet. `SURF_POOL4_FULL_LAYOUT_COLUMNS` carries the full per-seam
     * table, re-run after the mainnet rebalance moved every panel.
     *
     * BOTH columns scroll and BOTH carry `scrollbar-gutter: stable`, for
     * `#surf-launchpad-left`/`#curator-right-rail`'s reason: a `Vertical`
     * defaults to `overflow: hidden hidden`, and without the reserved gutter
     * this layout's WIDTH requirement would become a function of its HEIGHT.
     *
     * EXACTLY ONE `1fr` CHILD PER COLUMN, EACH FLOORED -- AND THE TWO COLUMNS
     * PICK THEIRS BY DIFFERENT RULES ON PURPOSE. A `1fr` child cannot
     * overflow a scroll container, it SHRINKS, so one given fewer rows than
     * its content loses them with no scrollbar and no trace UNLESS it scrolls
     * inside itself. Only POOL4 FLOW does (it is a `RichLog`), so it takes
     * the left column's `1fr` at a floor of 6 -- title, legend note, four
     * rows -- exactly like LAUNCHPAD ACTIVITY next door. The rail's `1fr`
     * goes to sIMD VAULT instead, which is the panel there with a FIXED line
     * count: `min-height: 10` is both its floor and its ceiling, so it can
     * never be cut. HATCHES is `auto` beside it, because its height answers
     * to the producer (ten rows with no levers, twenty at the ten emitted
     * today, twenty-two at the widget's own cap) and a floored `1fr` version
     * of it would silently cut rows in the narrow window where the column
     * does not yet scroll. THE SPLIT and THE RATCHET are `auto` on the left
     * for the same reason. See `SURF_POOL4_FULL_LAYOUT_ROWS`.
     */
    SurfScreen #surf-pool4-body {
        height: 1fr;
        width: 100%;
        margin: 1 0 0 0;
    }
    SurfScreen #surf-pool4-left {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen SurfPool4Hatches {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SurfScreen SurfPool4Flow {
        width: 1fr;
        height: 1fr;
        min-height: 6;
        padding: 0 1;
    }
    SurfScreen #surf-pool4-rail {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen SurfPool4Split {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SurfScreen SurfPool4Ratchet {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SurfScreen SurfPool4Vault {
        width: 1fr;
        height: 1fr;
        min-height: 10;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        data_manager: "SurfManager",
        poll_interval: int = 30,
        name: str = "surf",
        **kwargs,
    ):
        super().__init__(name=name, **kwargs)
        self._data_manager = data_manager
        self._poll_interval = poll_interval
        self._refresh_timer = None
        #: Last payload the title bar was built from, kept so a resize can
        #: rebuild the line with (or without) the row marker at no cost and
        #: without a refetch. ``None`` until the first payload lands, which
        #: is also the degraded-manager state -- see ``_render_title``.
        self._title_data: dict | None = None
        #: Which body is showing: MODE_DASHBOARD (the three rows below the
        #: hero) or MODE_LAUNCHPAD (the ``l`` view). The hero row is not
        #: part of either -- it stays mounted and visible regardless.
        self._mode: str = MODE_DASHBOARD

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static(INITIAL_TITLE, id="title-bar")

        with Horizontal(id="hero-row"):
            yield SurfHero()

        with Horizontal(id="middle-row"):
            yield SurfFeed()
            # The right rail: the six detectors on top, the dev wallets'
            # transactions underneath. Both are permanently visible -- the
            # activity panel used to live in the feed's slot behind a ``c``
            # swap and was composed hidden.
            with Vertical(id="surf-right-rail"):
                yield SurfSignals()
                yield SurfDevActivity()

        yield Static("─" * 300, id="separator")

        with Horizontal(id="bottom-row"):
            yield SurfMarket()
            yield SurfNft()

        # The `l` LAUNCHPAD view (2026-08-23): the v4 launchpad's own three
        # panels, composed once and hidden until `l` shows them -- the same
        # composed-once-shown-by-display contract curator's `f`/`l` bodies
        # use, so the first keypress paints a complete frame instead of a
        # blank one. The hero above is outside this container and is never
        # touched by the swap.
        #
        # A `Horizontal` since 2026-08-24, mirroring `#middle-row`: the coin
        # table is the only panel here with rows to scroll, and stacking the
        # two summary panels *under* it spent eleven of the body's rows on
        # ten lines of label/value text that never grow. Beside it they cost
        # the table columns instead, which is the cheaper currency for a
        # panel whose height is its content and whose width is fixed.
        with Horizontal(id=LAUNCHPAD_BODY_ID):
            # A COLUMN since 2026-08-25, not the bare table it was: the coin
            # table is capped at ten rows, so it no longer has spare rows to
            # hold -- LAUNCHPAD ACTIVITY takes them, which is the currency a
            # feed actually spends. Same trade as the rail's, made the other
            # way round.
            with Vertical(id=LAUNCHPAD_LEFT_ID):
                yield SurfLaunchpadCoins()
                yield SurfLaunchpadActivity()
            with Vertical(id=LAUNCHPAD_RAIL_ID):
                yield SurfCurveFlow()
                yield SurfBurnPipeline()
                yield SurfBurnkeepers()

        # The `p` POOL4 view (2026-09-01): the third body, composed once and
        # hidden by `display` exactly like the `l` body above it, so the first
        # `p` paints a complete frame rather than a blank one that fills in a
        # beat later. The hero is outside this container too and survives both
        # swaps.
        #
        # THE COLUMNS ARE SPLIT TO BALANCE THEIR HEIGHTS, NOT BY WHAT THE
        # PANELS ARE ABOUT. At the worst payload each column carries 33 rows
        # -- left: SPLIT 15 + RATCHET 10 + FLOW's floor 6 + two margins;
        # rail: HATCHES 22 + VAULT's floor 10 + one margin -- and that
        # balance IS the height pin. The pre-mainnet arrangement (HATCHES
        # here, SPLIT/RATCHET/VAULT in the rail) put 38 rows in the rail
        # against 20 here and needed 49.
        #
        # Each column's `1fr` goes to the child it is safe to shrink, and the
        # two columns reach opposite answers. Left: FLOW, because a `RichLog`
        # scrolls inside itself, so rows go behind its own scrollbar rather
        # than off the layout. Rail: VAULT, whose ten lines are a constant so
        # `min-height: 10` is floor and ceiling both -- the one thing that
        # must NOT take it is HATCHES, the panel whose height answers to the
        # lever list, because a shrunken `Static` loses rows with no
        # scrollbar and no trace.
        #
        # Measured against the alternative rather than asserted: see
        # `SURF_POOL4_FULL_LAYOUT_ROWS`, which records the arrangement this
        # replaced and what it cost.
        #
        # This comment described the pre-swap arrangement until the W3
        # follow-up and the pre-mainnet one until the rebalance; the three
        # lines directly beneath it are the authority.
        with Horizontal(id=POOL4_BODY_ID):
            with Vertical(id=POOL4_LEFT_ID):
                yield SurfPool4Split()
                yield SurfPool4Ratchet()
                yield SurfPool4Flow()
            with Vertical(id=POOL4_RAIL_ID):
                yield SurfPool4Hatches()
                yield SurfPool4Vault()

        yield StatusBar()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._show_mode()

    def on_screen_resume(self) -> None:
        self._do_initial_refresh()
        self._refresh_timer = self.set_interval(
            self._poll_interval, self._schedule_refresh
        )
        try:
            self.query_one(StatusBar).set_theme_name(self.app.theme)
            self.query_one(StatusBar).set_game_name("surf")
            self.query_one(StatusBar).set_key_hints(self.KEY_HINTS)
            # No set_active_view: no slot on this screen has two views, so a
            # `view:` word on the shared bar would name something that does
            # not exist.
        except Exception:
            pass

    def on_screen_suspend(self) -> None:
        if self._refresh_timer:
            self._refresh_timer.stop()
            self._refresh_timer = None

    def on_resize(self, _event=None) -> None:
        """Keep the row marker honest when the terminal changes height.

        Deferred to after the next refresh: the ``Resize`` message arrives
        before the rail has been re-laid-out, so reading its scroll state
        here would answer for the *previous* height and the marker would
        lag one resize behind -- lit on a terminal that now fits, dark on
        one that no longer does. Both are worse than no marker.
        """
        self.call_after_refresh(self._render_title)

    # ------------------------------------------------------------------
    # Mode toggle -- ``l`` LAUNCHPAD / ``escape`` back to the dashboard
    # ------------------------------------------------------------------

    def _show_mode(self) -> None:
        """Apply ``self._mode`` to the three bodies' visibility.

        Curator's ``y``/``f`` shape, minus the hero swap: curator mounts a
        second hero per mode and toggles which one shows, but this screen
        has exactly one hero and it is not part of any body -- it is
        outside ``#surf-launchpad-body`` and ``#surf-pool4-body`` entirely
        (see ``compose``) and this method never touches its ``display``, so
        it is on in every mode.

        **A three-way since 2026-09-01, and written as one so it cannot
        become a two-way plus an exception.** The obvious edit when the third
        body arrived was to keep ``launchpad = self._mode == MODE_LAUNCHPAD``
        and add a second boolean beside it; the dashboard rows would then
        have read ``not launchpad``, which is *true* in MODE_POOL4, and the
        pool4 body would have painted on top of a dashboard body that was
        still showing. Deriving all four visibilities from one comparison
        against ``self._mode`` makes the modes exclusive by construction.
        """
        try:
            self.query_one("#middle-row").display = self._mode == MODE_DASHBOARD
            self.query_one("#separator").display = self._mode == MODE_DASHBOARD
            self.query_one("#bottom-row").display = self._mode == MODE_DASHBOARD
            self.query_one(f"#{LAUNCHPAD_BODY_ID}").display = (
                self._mode == MODE_LAUNCHPAD
            )
            self.query_one(f"#{POOL4_BODY_ID}").display = self._mode == MODE_POOL4
        except Exception as exc:  # noqa: BLE001 -- a toggle must never crash
            logger.debug("surf mode toggle failed: %s", exc)
        # The row marker is about whichever body is now showing (only the
        # dashboard body's right rail can scroll), so it has to be re-read --
        # deferred, exactly like ``on_resize``, because the newly-shown body
        # has not been laid out when this method returns.
        self.call_after_refresh(self._render_title)

    def action_toggle_launchpad(self) -> None:
        """``l`` -- swap the dashboard body for the v4 launchpad panels.

        Idempotent: pressing ``l`` again from MODE_LAUNCHPAD returns to the
        dashboard rather than doing nothing, so the key is also its own way
        back (curator's ``action_toggle_analysis`` does the same for ``f``).
        """
        if self._mode == MODE_LAUNCHPAD:
            self.action_show_dashboard()
            return
        self._mode = MODE_LAUNCHPAD
        self._show_mode()

    def action_toggle_pool4(self) -> None:
        """``p`` -- swap the dashboard body for the POOL4 panels.

        Idempotent on ``action_toggle_launchpad``'s contract: a second ``p``
        returns to the dashboard rather than doing nothing, so the key is
        also its own way back. Pressing ``p`` from MODE_LAUNCHPAD switches
        bodies directly -- there is no need to ``escape`` out of one view
        before entering the other, and requiring it would be the only place
        on this screen where a view key did nothing.
        """
        if self._mode == MODE_POOL4:
            self.action_show_dashboard()
            return
        self._mode = MODE_POOL4
        self._show_mode()

    def action_show_dashboard(self) -> None:
        """``escape`` -- one-way back out of **either** alternate body."""
        self._mode = MODE_DASHBOARD
        self._show_mode()

    #: The scrolling columns of each body, in the order they are asked.
    #: ``show_vertical_scrollbar`` is each column's own answer to "do I hold
    #: more than this height can show", and is what the layout already turns
    #: the loss into; asking it rather than re-deriving the arithmetic keeps
    #: the marker and the scrollbars from ever disagreeing.
    #:
    #: **A body added here without its entry is the 2026-08-25 defect
    #: repeated.** ``_rail_is_cut`` falls back to ``()`` for an unlisted mode,
    #: so the whole new body would report "nothing is cut" at every terminal
    #: height while its columns visibly scrolled -- which is exactly what
    #: ``MODE_LAUNCHPAD`` did before it was listed, for the length of that
    #: view's existence. ``test_the_taller_marker_lights_on_the_pool4_body``
    #: and ``test_every_mode_names_its_scrolling_columns`` are the two halves
    #: of the guard: one proves the marker really lights, the other proves no
    #: future mode can be added without an entry.
    _SCROLL_COLUMNS = {
        MODE_DASHBOARD: ("#surf-right-rail",),
        MODE_LAUNCHPAD: (f"#{LAUNCHPAD_LEFT_ID}", f"#{LAUNCHPAD_RAIL_ID}"),
        MODE_POOL4: (f"#{POOL4_LEFT_ID}", f"#{POOL4_RAIL_ID}"),
    }

    def _rail_is_cut(self) -> bool:
        """Does the body now showing hold more than this height can show?

        **Asked of the body that is showing, not of one fixed id.** This read
        ``#surf-right-rail`` unconditionally until 2026-08-25, which is the
        dashboard body's rail: in ``MODE_LAUNCHPAD`` that container is inside
        a ``display: none`` ``#middle-row``, is never laid out, and answers
        ``False`` at every terminal height -- so the one advertisement this
        screen has for a lost row was dark on the whole of the ``l`` view
        while the launchpad rail was visibly scrolling. Both of the launchpad
        body's columns scroll and either can be the one that overflows, so
        both are asked.
        """
        for selector in self._SCROLL_COLUMNS.get(self._mode, ()):
            try:
                if self.query_one(selector).show_vertical_scrollbar:
                    return True
            except Exception:  # noqa: BLE001 -- not composed yet, or torn down
                continue
        return False

    def _render_title(self, _recheck: bool = True) -> None:
        """(Re)compose the title bar from the last payload plus the marker.

        **One deferred pass is not enough at the boundary** (2026-09-02).
        ``_show_mode`` and ``on_resize`` both schedule this through
        ``call_after_refresh``, on the reasoning that the newly-shown body
        has not been laid out when they return. That is true and necessary
        -- and at the *one-row* boundary it is still one pass short: a
        column whose content exceeds its height by exactly one row acquires
        its scrollbar on a later pass than the one this callback runs in, so
        the line is composed while ``_rail_is_cut()`` is still ``False`` and
        nothing ever recomposes it.

        The result was ``‹ taller`` **dark on a body that was scrolling**, at
        exactly the height where a reader most needs it -- one row from
        fitting. Measured, deterministic, and not a race: at 150x45 on the
        Sepolia payload ``_rail_is_cut()`` returned ``True`` while the marker
        was absent, and calling this method a second time lit it. WP5 saw
        this shape and reported it honestly as unverified because it could
        not separate it from its own dispatch injection; it is real, and it
        is subtler than the 2026-08-25 missing-``_SCROLL_COLUMNS``-entry
        defect it resembles -- that mapping is present and correct, and
        ``_rail_is_cut`` answers correctly. Only the title was stale.

        So the render **re-checks itself once**. ``_recheck`` is the
        termination guard: the deferred pass compares a freshly-read
        ``_rail_is_cut()`` against what was actually rendered and recomposes
        only if it has changed, with ``_recheck=False`` so it cannot schedule
        another. At most one extra pass, and only when the answer moved.
        """
        cut = self._rail_is_cut()
        if self._title_data is None:
            # No payload yet -- or the manager raised and there never will
            # be one. The marker simply goes on the end here, and *neither*
            # line carries a version tail since 2026-08-12, so this branch
            # and ``_title_line`` no longer differ in that respect at all --
            # what still differs is that ``_title_line`` puts the marker
            # ahead of two warnings this branch has no payload to produce.
            line = INITIAL_TITLE + (f" · [yellow]{TALLER_HINT}[/]" if cut else "")
        else:
            line = _title_line(self._title_data, row_hint=cut)
        try:
            self.query_one("#title-bar", Static).update(line)
        except Exception as exc:  # noqa: BLE001 -- a title must never crash
            logger.debug("Failed to update title bar: %s", exc)

        if _recheck:
            self.call_after_refresh(self._recheck_row_marker, cut)

    def _recheck_row_marker(self, rendered: bool) -> None:
        """Recompose once if the row marker's answer moved after the render.

        See :meth:`_render_title`. This exists because a one-row overflow
        settles a layout pass later than the callback that composed the
        line, and it is deliberately not a loop: it recomposes with
        ``_recheck=False``, so the correction can happen at most once per
        render and a layout that keeps changing cannot spin the title.
        """
        try:
            if self._rail_is_cut() != rendered:
                self._render_title(_recheck=False)
        except Exception as exc:  # noqa: BLE001 -- never crash on a marker
            logger.debug("row marker re-check failed: %s", exc)

    # ------------------------------------------------------------------
    # Refresh flow
    # ------------------------------------------------------------------

    async def _do_refresh(self) -> None:
        try:
            data = await self._data_manager.fetch_and_compute()
        except Exception as exc:
            # Belt and braces: WP4's SurfManager.fetch_and_compute() never
            # raises -- it guarantees the full SURF_KEYS dict with None
            # values under every failure combination. This branch covers a
            # mis-wired manager or a future manager edit that breaks that
            # guarantee, not the specified outage path (see
            # test_screen_survives_all_none_payload for the real one).
            logger.debug("surf refresh failed: %s", exc)
            try:
                self.query_one(StatusBar).update_data(
                    last_updated_seconds_ago=MANAGER_FAILURE_SECONDS,
                    error_count=getattr(self._data_manager, "_error_count", 0),
                    poll_interval=self._poll_interval,
                )
            except Exception:
                pass
            return

        if not isinstance(data, dict):  # defensive: a broken manager contract
            logger.debug("surf refresh returned %r, not a dict", type(data))
            return

        # Title bar. The payload is kept so a later resize can re-compose
        # this same line with or without the row marker, without refetching.
        self._title_data = data
        self._render_title()

        # Hero (the full-width top row): LAUNCHPAD / FLOW / BURN / SUPPLY,
        # rebuilt 2026-08-24 (widgets/surf/hero.py). The v3->v4 migration had
        # already replaced the HOOK/GATE boxes with POOL/LP; this wave retires
        # those two in turn, so the pool and LP keys are no longer dispatched
        # here either. Both boxes read the launchpad sweep that already runs
        # for the ``l`` view -- no new request -- and both carry that tier's
        # own ``launchpad_as_of_hhmm`` clock rather than the title bar's
        # faster one, because these numbers can be ten minutes older than it.
        #
        # Where the retired boxes' keys went, because getting this wrong is
        # what produced the C2 defect (a detector left pointed at a burned
        # position because a comment said the wiring was already there):
        #
        # * ``decoy_pool_count`` still reaches the screen -- through the DECOY
        #   POOL detector, which ``surf_manager._readings`` builds off this
        #   same flat key, so it is dispatched as ``sig_decoy_*`` below.
        # * ``pool_liquidity_usd`` still reaches SurfMarket (``pool $548.7K``),
        #   which is where POOL's headline figure was already duplicated.
        # * ``lp_owner_ok`` still reaches ``_title_line`` as the ``⚠ LP owner
        #   changed`` warning, which is the whole of what the LP box's
        #   ``owner ✓`` was saying.
        # * ``pool_venue``, ``pool_fee_bps``, ``pool_id_source``, ``lp_state``,
        #   ``lp_imd`` and ``lp_weth`` now reach NOTHING. They are published by
        #   the manager and rendered nowhere; they belong in the same cleanup
        #   that removed ``hook_status``/``pool_liquidity_raw`` from
        #   ``SURF_KEYS``, which this task does not own
        #   (``data/surf_models.py``) -- see task-12-report.md. Deliberately
        #   listed rather than quietly dropped: an unconsumed contract key
        #   that nobody has written down reads, to the next person, as a
        #   dispatch somebody forgot.
        #
        # The older accounting below still holds for the HOOK/GATE-era keys:
        #
        # Where each of them actually goes now, because getting this wrong is
        # what produced the C2 defect (a detector left pointed at a burned
        # position because a comment said the wiring was already there):
        #
        # * ``gate_open`` DOES still feed a detector -- ``_detect_gate``, via
        #   ``surf_manager._readings`` -- so its information reaches the
        #   screen through ``sig_gate_*`` below, dispatched to SurfSignals as
        #   it always was.
        # * ``identities_written`` does NOT. The manager feeds the GATE
        #   detector the *log-window* write count off ``SLOT_LOGS``, which is
        #   a different number (``_readings`` says so at the assignment); this
        #   flat key is the lifetime count off ``NftStats.written`` and no
        #   widget reads it. IDENTITY.MD's ``N/2000 written`` cell renders
        #   ``nft_written``, which is the same value under its own name.
        # * ``lp_liquidity`` does NOT any more either (final fix wave, C2).
        #   ``_detect_lp`` was repointed at ``lp_position_count`` -- the v4
        #   position count -- precisely because this key reads
        #   ``NFPM.positions()`` on the v3 position the ops wallet burned on
        #   2026-08-17, so it reverts and the value is ``None`` forever.
        # * ``hook_status`` measures a v4 hook launch the dev has publicly
        #   retracted and reaches no widget at all any more.
        #
        # See ``META_KEYS`` in the test module for the fuller accounting.
        try:
            self.query_one(SurfHero).update_data(
                launchpad_coin_count=data.get("launchpad_coin_count"),
                launchpad_new_24h=data.get("launchpad_new_24h"),
                launchpad_creator_count=data.get("launchpad_creator_count"),
                launchpad_swap_count=data.get("launchpad_swap_count"),
                launchpad_trader_count=data.get("launchpad_trader_count"),
                launchpad_creator_eth_owed=data.get("launchpad_creator_eth_owed"),
                launchpad_as_of_hhmm=data.get("launchpad_as_of_hhmm"),
                burn_accrued=data.get("burn_accrued"),
                burn_staged=data.get("burn_staged"),
                burn_ready=data.get("burn_ready"),
                imd_supply=data.get("imd_supply"),
                imd_burned_cum=data.get("imd_burned_cum"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfHero: %s", exc)

        # Signals (right rail, top) -- the nine detectors (Task 9 grew this
        # from six: DECOY POOL, BURN READY, HOT COIN are the v4-launchpad
        # additions, quiet-collapsed like every other ``ok`` row).
        try:
            self.query_one(SurfSignals).update_data(
                sig_post_state=data.get("sig_post_state"),
                sig_post_detail=data.get("sig_post_detail"),
                sig_post_age_s=data.get("sig_post_age_s"),
                sig_thread_state=data.get("sig_thread_state"),
                sig_thread_detail=data.get("sig_thread_detail"),
                sig_thread_age_s=data.get("sig_thread_age_s"),
                sig_lp_state=data.get("sig_lp_state"),
                sig_lp_detail=data.get("sig_lp_detail"),
                sig_lp_age_s=data.get("sig_lp_age_s"),
                sig_gate_state=data.get("sig_gate_state"),
                sig_gate_detail=data.get("sig_gate_detail"),
                sig_gate_age_s=data.get("sig_gate_age_s"),
                sig_deploy_state=data.get("sig_deploy_state"),
                sig_deploy_detail=data.get("sig_deploy_detail"),
                sig_deploy_age_s=data.get("sig_deploy_age_s"),
                sig_bridge_state=data.get("sig_bridge_state"),
                sig_bridge_detail=data.get("sig_bridge_detail"),
                sig_bridge_age_s=data.get("sig_bridge_age_s"),
                sig_burn_state=data.get("sig_burn_state"),
                sig_burn_detail=data.get("sig_burn_detail"),
                sig_burn_age_s=data.get("sig_burn_age_s"),
                sig_decoy_state=data.get("sig_decoy_state"),
                sig_decoy_detail=data.get("sig_decoy_detail"),
                sig_decoy_age_s=data.get("sig_decoy_age_s"),
                sig_burnready_state=data.get("sig_burnready_state"),
                sig_burnready_detail=data.get("sig_burnready_detail"),
                sig_burnready_age_s=data.get("sig_burnready_age_s"),
                sig_hot_state=data.get("sig_hot_state"),
                sig_hot_detail=data.get("sig_hot_detail"),
                sig_hot_age_s=data.get("sig_hot_age_s"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfSignals: %s", exc)

        # Announce feed (middle row, left)
        try:
            self.query_one(SurfFeed).update_data(
                feed_items=data.get("feed_items"),
                feed_nonce=data.get("feed_nonce"),
                feed_last_post_age_s=data.get("feed_last_post_age_s"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfFeed: %s", exc)

        # Dev activity (middle row, right rail, under the signals)
        try:
            self.query_one(SurfDevActivity).update_data(
                dev_activity=data.get("dev_activity"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfDevActivity: %s", exc)

        # Market (bottom row, left)
        try:
            self.query_one(SurfMarket).update_data(
                imd_price_usd=data.get("imd_price_usd"),
                imd_change_24h_pct=data.get("imd_change_24h_pct"),
                imd_vol_24h_usd=data.get("imd_vol_24h_usd"),
                pool_liquidity_usd=data.get("pool_liquidity_usd"),
                fp_price_usd=data.get("fp_price_usd"),
                parity_pct=data.get("parity_pct"),
                supply_series=data.get("supply_series"),
                price_series=data.get("price_series"),
                price_source_disagreement_pct=data.get(
                    "price_source_disagreement_pct"
                ),
                # Not a row: provenance for the two figures above it that
                # come out of the v4 pool (`pool_liquidity_usd`, and the
                # on-chain leg of `imd_price_usd`). `"fallback"` means
                # `LaunchpadHook.imdEthPoolId()` did not answer and a
                # vendored constant was used, i.e. we cannot be sure this is
                # the real pool rather than one of the 37 decoys -- the panel
                # says so on its own title. Restored 2026-08-24 (fix round 1):
                # retiring the hero's POOL box left that claim with no home,
                # and DECOY POOL on the signals rail carries the decoy *count*,
                # which is a different fact.
                pool_id_source=data.get("pool_id_source"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfMarket: %s", exc)

        # NFT (bottom row, right)
        try:
            self.query_one(SurfNft).update_data(
                nft_holders=data.get("nft_holders"),
                nft_transfers_24h=data.get("nft_transfers_24h"),
                nft_dev_holdings=data.get("nft_dev_holdings"),
                nft_written=data.get("nft_written"),
                nft_last_sales=data.get("nft_last_sales"),
                nft_floor=data.get("nft_floor"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfNft: %s", exc)

        # Launchpad body (`l` view) -- dispatched every refresh whether or
        # not `l` is showing it, exactly like curator's `f`/`l` bodies: a
        # body that starts rendering only when it becomes visible is blank
        # for a beat after the keypress. ``launchpad_as_of_hhmm`` is the
        # detached launchpad tier's own slower clock (surf_manager.py's
        # ``_launchpad_payload``), shared by all three panels below.
        try:
            self.query_one(SurfLaunchpadCoins).update_data(
                coins=data.get("launchpad_coins"),
                coin_count=data.get("launchpad_coin_count"),
                launch_count=data.get("launchpad_launch_count"),
                # The sweep's OWN population count, beside the factory's
                # ``coinCount()`` claim. Without it ``_set_note`` has nothing
                # to compare and stays silent about a disagreement -- which is
                # how a truncating sweep returned 2 of 146 launches looking
                # perfectly healthy (Task 6's review finding). The widget has
                # accepted this kwarg since Task 11; the screen simply never
                # passed it, so the detector could not fire in the running app.
                as_of_hhmm=data.get("launchpad_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfLaunchpadCoins: %s", exc)

        try:
            self.query_one(SurfCurveFlow).update_data(
                swap_count=data.get("launchpad_swap_count"),
                trader_count=data.get("launchpad_trader_count"),
                creator_eth_owed=data.get("launchpad_creator_eth_owed"),
                as_of_hhmm=data.get("launchpad_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfCurveFlow: %s", exc)

        try:
            self.query_one(SurfBurnPipeline).update_data(
                burn_accrued=data.get("burn_accrued"),
                burn_staged=data.get("burn_staged"),
                burn_ready=data.get("burn_ready"),
                burn_min_bridge=data.get("burn_min_bridge"),
                burn_bridgeable=data.get("burn_bridgeable"),
                burned_total=data.get("launchpad_burned_total"),
                as_of_hhmm=data.get("launchpad_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfBurnPipeline: %s", exc)

        # The two panels the `l` body grew on 2026-08-25. Same contract as
        # the three above and for the same reason -- dispatched on EVERY
        # refresh, whether or not `l` is showing them, so the first keypress
        # paints a complete frame rather than a blank one. Each in its own
        # `try` so one bad panel cannot blank the others.
        #
        # Both take their PRD §5 key under its own name (`launchpad_activity`,
        # `launchpad_burnkeepers`) rather than the short names the first three
        # panels use, so both land in
        # `tests/widgets/test_surf_widget_contract.py`'s strict kwarg check by
        # default instead of in its `_SHORT_KWARG_WIDGETS` escape list. The
        # one elision they keep is `as_of_hhmm`, which every launchpad panel
        # spells short.
        try:
            self.query_one(SurfLaunchpadActivity).update_data(
                launchpad_activity=data.get("launchpad_activity"),
                as_of_hhmm=data.get("launchpad_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfLaunchpadActivity: %s", exc)

        try:
            self.query_one(SurfBurnkeepers).update_data(
                launchpad_burnkeepers=data.get("launchpad_burnkeepers"),
                as_of_hhmm=data.get("launchpad_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfBurnkeepers: %s", exc)

        # POOL4 body (`p` view, 2026-09-01) -- the same contract as the five
        # launchpad panels above and for the same reason: dispatched on EVERY
        # refresh, whether or not `p` is showing them, so the first keypress
        # paints a complete frame rather than a blank one. Each in its own
        # `try` so one bad panel cannot blank the other four.
        #
        # Every kwarg is spelled with its full `pool4_` prefix, including
        # `pool4_as_of_hhmm`. That is a deliberate departure from the
        # launchpad panels, which spell that one key `as_of_hhmm` and rely on
        # `tests/widgets/test_surf_widget_contract._PREFIXED_KWARG_ALIASES`:
        # that alias maps ONE kwarg name onto ONE contract key, and a second
        # body whose panels also took `as_of_hhmm` would make one kwarg name
        # stand for two different keys, at which point the alias stops
        # proving anything. No new alias, and no pool4 widget on
        # `_SHORT_KWARG_WIDGETS` -- pinned by
        # `test_no_pool4_widget_needs_a_kwarg_alias`.
        #
        # `pool4_as_of_hhmm` is the POOL4 tier's own slower clock
        # (`surf_manager._pool4_payload`), shared by all five panels and
        # deliberately not the title bar's faster one: these numbers can be
        # half an hour older than it.
        try:
            self.query_one(SurfPool4Split).update_data(
                pool4_network=data.get("pool4_network"),
                pool4_measured_inference_pct=data.get(
                    "pool4_measured_inference_pct"
                ),
                pool4_measured_burn_pct=data.get("pool4_measured_burn_pct"),
                pool4_measured_stakers_pct=data.get("pool4_measured_stakers_pct"),
                pool4_reward_share_bps=data.get("pool4_reward_share_bps"),
                pool4_bps_denominator=data.get("pool4_bps_denominator"),
                pool4_split_drift_bps=data.get("pool4_split_drift_bps"),
                pool4_total_burned=data.get("pool4_total_burned"),
                pool4_total_rewarded=data.get("pool4_total_rewarded"),
                pool4_total_fee_token=data.get("pool4_total_fee_token"),
                pool4_retained_eth=data.get("pool4_retained_eth"),
                pool4_last_claim_block=data.get("pool4_last_claim_block"),
                pool4_unsettled_burn=data.get("pool4_unsettled_burn"),
                pool4_unsettled_stakers=data.get("pool4_unsettled_stakers"),
                # The counter reconciliation (W1). THE SPLIT is where it
                # belongs because it is the panel whose numbers the check is
                # about: the sums of `FeeCollected` and `ClaimsSettled` must
                # equal `totalFeeToken()` / `totalBurned()` / `totalRewarded()`
                # to the wei, and a disagreement means the RECOVERED interface
                # is wrong on this deployment rather than that a read failed.
                #
                # `pool4_counter_state is None` means the check has NEVER RUN
                # -- it is not a pass. That distinction is the whole point of
                # the key existing (`"unchecked"` is a state the producer can
                # assert; `None` is the absence of any assertion), and it is
                # why this is dispatched rather than defaulted anywhere on the
                # way: `data.get` hands the widget the `None` verbatim.
                pool4_counter_state=data.get("pool4_counter_state"),
                pool4_counter_detail=data.get("pool4_counter_detail"),
                # The mainnet three-way reward split (2026-09-02). Sepolia
                # retires a fee two ways; mainnet inserts a Distributor and
                # splits the staker leg again -- 85 burn / 4.5 stakers / 6.0
                # bonding / 4.5 nodes per 100 IMD retired. `pool4_reward_path`
                # is the topology word, and it is dispatched to THE SPLIT and
                # to HATCHES and to nothing else: WP0 pins that exactly two
                # panels carry it, so a third acquiring it is visible rather
                # than quiet.
                #
                # `bonding_bps` is the REMAINDER (10000 - staking - nodes),
                # not its own getter. The producer derives it and says so; a
                # panel or a fixture that hardcodes 4000 is asserting a
                # number the chain never returned.
                pool4_reward_path=data.get("pool4_reward_path"),
                pool4_distributor_addr=data.get("pool4_distributor_addr"),
                pool4_distributor_staking_bps=data.get(
                    "pool4_distributor_staking_bps"
                ),
                pool4_distributor_nodes_bps=data.get(
                    "pool4_distributor_nodes_bps"
                ),
                pool4_distributor_bonding_bps=data.get(
                    "pool4_distributor_bonding_bps"
                ),
                pool4_distributor_staking_earned=data.get(
                    "pool4_distributor_staking_earned"
                ),
                pool4_distributor_nodes_earned=data.get(
                    "pool4_distributor_nodes_earned"
                ),
                pool4_distributor_bonding_earned=data.get(
                    "pool4_distributor_bonding_earned"
                ),
                pool4_distributor_held_nodes=data.get(
                    "pool4_distributor_held_nodes"
                ),
                pool4_distributor_held_bonding=data.get(
                    "pool4_distributor_held_bonding"
                ),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4Split: %s", exc)

        try:
            self.query_one(SurfPool4Flow).update_data(
                pool4_flow=data.get("pool4_flow"),
                pool4_network=data.get("pool4_network"),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4Flow: %s", exc)

        try:
            self.query_one(SurfPool4Ratchet).update_data(
                pool4_network=data.get("pool4_network"),
                pool4_tokens_in_pool=data.get("pool4_tokens_in_pool"),
                pool4_cap_floor=data.get("pool4_cap_floor"),
                # The inventory CEILING (2026-09-02), the floor's mirror.
                #
                # ⚠ THE OPERAND ORDER FLIPS BETWEEN THE TWO AND THAT IS THE
                # WHOLE POINT. `pool4_floor_distance` is reserve − floor;
                # `pool4_cap_headroom` is cap − reserve. Both read positive
                # when healthy, which is what makes them readable side by
                # side -- and it is why writing the ceiling half "by analogy"
                # with its sibling gives reserve − cap and renders a binding
                # cap (94.68 IMD of headroom on mainnet) as −94.68 of slack,
                # the exact misreading the key exists to prevent. The screen
                # only passes these through, but a fixture written here
                # reverses them just as easily: see
                # `test_the_cap_headroom_keeps_its_operand_order`.
                pool4_inventory_cap=data.get("pool4_inventory_cap"),
                pool4_cap_headroom=data.get("pool4_cap_headroom"),
                pool4_cap_decay_per_day=data.get("pool4_cap_decay_per_day"),
                pool4_floor_distance=data.get("pool4_floor_distance"),
                pool4_floor_distance_pct=data.get("pool4_floor_distance_pct"),
                pool4_burned_supply_pct=data.get("pool4_burned_supply_pct"),
                pool4_total_supply=data.get("pool4_total_supply"),
                pool4_reserve_series=data.get("pool4_reserve_series"),
                pool4_eth_in_pool=data.get("pool4_eth_in_pool"),
                pool4_position_liquidity=data.get("pool4_position_liquidity"),
                pool4_current_tick=data.get("pool4_current_tick"),
                pool4_ref_tick=data.get("pool4_ref_tick"),
                pool4_backstop_centred=data.get("pool4_backstop_centred"),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4Ratchet: %s", exc)

        try:
            self.query_one(SurfPool4Vault).update_data(
                pool4_network=data.get("pool4_network"),
                pool4_share_price=data.get("pool4_share_price"),
                pool4_share_price_delta_pct=data.get(
                    "pool4_share_price_delta_pct"
                ),
                pool4_vault_assets=data.get("pool4_vault_assets"),
                pool4_vault_shares=data.get("pool4_vault_shares"),
                pool4_drip_per_day=data.get("pool4_drip_per_day"),
                pool4_drippable=data.get("pool4_drippable"),
                pool4_can_drip=data.get("pool4_can_drip"),
                pool4_backlog_imd=data.get("pool4_backlog_imd"),
                pool4_backlog_days=data.get("pool4_backlog_days"),
                pool4_implied_apr_pct=data.get("pool4_implied_apr_pct"),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4Vault: %s", exc)

        try:
            self.query_one(SurfPool4Hatches).update_data(
                pool4_hatches=data.get("pool4_hatches"),
                pool4_network=data.get("pool4_network"),
                pool4_discovery_state=data.get("pool4_discovery_state"),
                pool4_discovery_detail=data.get("pool4_discovery_detail"),
                # The citation, as its OWN key rather than merged into the
                # detail above it (S18). `SLOT_POOL4`'s comment always said
                # the two were never to be merged -- "a later reader must be
                # able to tell them apart" -- and the payload was violating
                # that three lines away, because `_pool4_cited_detail` glued
                # `· tx <hash>` onto WP3's sentence before it left the
                # manager. That function is gone; the detail is WP3's
                # sentence verbatim and this is the transaction it came from.
                #
                # Dispatched separately for the reason the split exists: a
                # consumer that wants the provenance can have it without
                # string-parsing a sentence, and one that wants the sentence
                # is not handed a 66-character hash it has to strip.
                pool4_discovery_source_tx=data.get("pool4_discovery_source_tx"),
                # WHICH source an adoption came from (2026-09-02), and this
                # is a disclosure key rather than a descriptive one. The
                # announce channel requires a dev-signed self-post; the docs
                # site does not, and the operator has accepted it as a
                # *candidate* source. Anyone who can edit that page can name
                # a hook, and the chain fingerprint alone will not stop them
                # -- a `0x2840` tail mines in ~20,000 tries. So the panel
                # names the source, and weaker provenance identifies itself
                # instead of hiding behind the same word as a signed post.
                pool4_discovery_source=data.get("pool4_discovery_source"),
                # The topology, the second of exactly two panels to get it.
                pool4_reward_path=data.get("pool4_reward_path"),
                pool4_distributor_addr=data.get("pool4_distributor_addr"),
                pool4_hook_addr=data.get("pool4_hook_addr"),
                pool4_token_addr=data.get("pool4_token_addr"),
                pool4_vault_addr=data.get("pool4_vault_addr"),
                pool4_dripper_addr=data.get("pool4_dripper_addr"),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4Hatches: %s", exc)

        # Status bar. A refresh that reaches this line just fetched, so the
        # staleness is honestly 0 without consulting any clock; ``as_of`` is
        # the *payload's* fetch instant and stays inside the widgets' strings.
        try:
            self.query_one(StatusBar).update_data(
                last_updated_seconds_ago=0.0,
                error_count=int(_num(getattr(self._data_manager, "_error_count", 0))),
                poll_interval=self._poll_interval,
            )
        except Exception as exc:
            logger.debug("Failed to update StatusBar: %s", exc)
