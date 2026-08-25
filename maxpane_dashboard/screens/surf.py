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

    #surf-launchpad-body   #surf-launchpad-left (12fr)      | #surf-launchpad-rail (5fr)
                             SurfLaunchpadCoins    (auto)   |   SurfCurveFlow      (auto, +1 margin)
                             SurfLaunchpadActivity (1fr)    |   SurfBurnPipeline   (auto, +1 margin)
                                                            |   SurfBurnkeepers    (1fr)

``#hero-row`` is never touched by that swap and stays on screen in both
modes. See "The 2026-08-23 ``l`` view" below.

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
``12fr:5fr``, swept (Task 13) -- the table needs 95 columns and cannot give
one back, the rail needs 39, and 95:39 is a 71/29 split. The provisional
``7fr:6fr`` it was built with handed the table 95 only on a 177-column
terminal, so the ``l`` view lit ``‹ widen`` on every terminal anybody owns;
12:5 collects it at 135. ``SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`` carries the
per-seam costs.

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

#: The ``l`` LAUNCHPAD body's own measured width (Task 13, re-measured
#: 2026-08-24) -- a **separate, independently-named** constant, never a
#: rewrite of :data:`SURF_FULL_LAYOUT_COLUMNS` above or
#: ``__main__.FULL_LAYOUT_COLUMNS``. Swept column by column over the real
#: screen (``tests/screens/test_surf_screen.py``'s
#: ``test_the_launchpad_body_is_whole_from_its_pinned_width``, which runs
#: 120..145 -- comfortably below and above this number and never starting at
#: it, so the sweep cannot agree with the pin by construction).
#:
#: **The binding panel is ``SurfLaunchpadCoins``**, pinned by
#: ``test_the_launchpad_binding_panel_is_the_coins_table`` rather than by
#: this sentence (curator's own
#: ``test_the_analysis_binding_panel_is_the_operators_table`` precedent).
#: Its ``DataTable`` has nine fixed columns (``_TICKER_COLS`` ..
#: ``_BURNED_COLS``, 79 content columns plus the table's own cell gutters =
#: ``launchpad._TABLE_FULL_WIDTH``, 93) that do not shrink with the terminal
#: -- unlike every other surf widget, this panel had **no width tiering at
#: all** before this task series (Task 11's own finding): below its
#: structural width a column was clipped with no on-screen trace, which is
#: exactly the silent clipping CLAUDE.md forbids.  ``DataTable``'s own
#: ``show_horizontal_scrollbar`` cannot be read as that signal either -- it
#: is already ``True`` several columns before anything is actually lost, so
#: a marker keyed off it would fire early and disagree with the compositor.
#: ``SurfLaunchpadCoins`` (``widgets/surf/launchpad.py``) advertises the
#: loss on its own title, the same idiom ``SurfMarket``/curator's
#: ``CuratorOperators`` already use for their own column tiers -- one tier
#: here, not a ladder, because a fixed-column ``DataTable`` has nothing
#: shorter to fall back to.
#:
#: **93 -> 135, and the old number described a body that no longer exists.**
#: 93 was measured with all three launchpad panels full width and stacked.
#: The 2026-08-24 rail put the table on a share of a two-column body, so
#: this number is now a function of the seam, and the seam had never been
#: swept. Both halves were therefore re-measured first, each *in situ*:
#:
#:   * the table needs **95** screen columns (93 content +
#:     ``padding: 0 1``); at 94 the compositor eats ``BURNED``'s D.
#:   * the rail needs **39**, measured inside ``#surf-launchpad-rail``
#:     rather than in a bare harness -- its widest line
#:     (``accrued 1.2K IMD · staged 45.0 IMD``, 34 cells) pays the panel's
#:     ``padding: 0 1``, the inner ``Static``'s own ``padding: 0 1``, and
#:     the reserved ``scrollbar-gutter: stable`` column on top. Measured
#:     without the gutter the answer is 38, and a body pinned to that is
#:     one column short on the real screen.
#:
#: So 95 + 39 = **134** is the arithmetic floor, and the sweep is what each
#: candidate seam actually collects it at (real screen, whole ``l`` body):
#:
#:   ``3:2`` 159 · ``7:6`` **177** · ``9:7`` 169 · ``11:9`` 173 · ``2:1``
#:   143 · ``12:5`` **135** · ``3:1`` 153
#:
#: 7:6 -- what this body was built with -- is the *worst* of the seven: it
#: hands a 71/29 split 54/46, so the table reached 95 only at 177, which is
#: 34 past FWA's 143 and past the ~169 columns a laptop gets at the 17 pt
#: ``__main__`` forces on launch. The ``l`` view would have advertised
#: ``‹ widen`` on every terminal anybody owns.
#:
#: **12:5 is pinned, and it is not quite the cheapest.** Three seams sit at
#: or below it -- ``5:2`` and ``22:9`` both collect 134, the floor itself --
#: and both are **disqualified for the same structural reason**, which is
#: worth more than the column: below the pin the only panel that *marks* has
#: to be the one that binds. At 5:2 the table is clean from 133 while the
#: rail still needs 134, so at exactly 133 the body clips a rail line with
#: no ``‹ widen`` anywhere on screen -- the rail panels are plain
#: label/value ``Static``s and have no marker of their own. ``3:1`` fails
#: the same test far more loudly (table clean from 127, rail not until 153).
#: 22:9 survives it but is a seam nobody can read for one column that no
#: user can see, both numbers being eight or nine under the 143 the app
#: documents. Of the seams that keep the marked panel the binder, ``12:5``
#: and ``17:7`` both collect 135 and 12:5 is the simpler -- the same
#: tie-break that chose 7:6 for ``#middle-row`` out of four seams that all
#: reached 152.
#:
#: The rail's 39 is **data-dependent and the fixture is the small case**.
#: ``accrued``/``staged`` render through ``fmt_compact``, so a launchpad
#: that has run a while prints ``accrued 12.3K IMD · staged 500.0 IMD`` --
#: 36 cells, +2, taking the rail to 41. Re-swept against that payload 12:5
#: collects 137 (still under 143); 5:2 would have needed 141. That headroom
#: is a second reason the marginally-cheaper seam was not worth taking, and
#: it is the standing CLAUDE.md rule about measuring a data-dependent width
#: against the state the data is normally in, applied to a rail instead of
#: to ``SurfMarket``'s dollar gap.
#:
#: **135, eight columns under FWA's 143** -- so this task moves neither
#: :data:`SURF_FULL_LAYOUT_COLUMNS` nor ``__main__.FULL_LAYOUT_COLUMNS``,
#: and the ``198 -> 172 -> 143 -> 176 -> 152 -> 143`` record in CLAUDE.md is
#: correctly **not** appended to: that record tracks changes to the
#: app-wide number only (CLAUDE.md says so twice already, about curator's
#: own screen pin and its ``f`` view). The hero row, which stays mounted in
#: both modes, clears on its own at **87** -- re-measured here, not
#: inherited: the long-quoted "by 80" was true when ``hero.MINIMAL_WIDTH``
#: was 13 and this branch re-derived it to 15. 87 is still 48 columns below
#: this pin, so the conclusion the old number was quoted for still holds and
#: the hero never competes for the binder role.
SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS = 135

#: The two bodies ``l``/``escape`` swap between. Named on curator's
#: MODE_DASHBOARD/MODE_ANALYSIS precedent -- this screen only ever needs two,
#: so there is no MODE_WALLET/MODE_LIST sibling to grow into.
MODE_DASHBOARD = "dashboard"
MODE_LAUNCHPAD = "launchpad"

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
    KEY_HINTS = "[dim]l launchpad[/]"

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
     * The seam is `12fr:5fr`, SWEPT (Task 13, 2026-08-24) and deliberately
     * NOT the `7fr:6fr` this body was built with or the 7:6 the other two
     * rows use. Do not "tidy" it into agreement with them: this body
     * balances a fixed-width `DataTable` (95 columns, immovable) against a
     * rail of short label/value lines (39) -- a 71/29 split -- where
     * #middle-row balances a wrapping feed against a rail that both give
     * ground. At 7:6 the table reaches its 95 columns only on a 177-column
     * terminal, 34 past FWA's 143 and past the ~169 a laptop gets at the
     * 17 pt `__main__` forces on launch, so the `l` view would have lit
     * `< widen` on every terminal anybody owns. 12:5 collects it at 135.
     * The losing candidates and what each costs are recorded in
     * `SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`'s own docstring.
     *
     * The rail carries `scrollbar-gutter: stable` for curator's own reason
     * (`#curator-right-rail`): without it the scrollbar takes its column
     * out of the panel beside it only on terminals short enough to overflow,
     * so the layout's WIDTH requirement would move with its HEIGHT and a
     * width pin measured at 48 rows would be one column short at 40.
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
        width: 12fr;
        height: 1fr;
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
        width: 5fr;
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
        """Apply ``self._mode`` to the launchpad body's visibility.

        Curator's ``y``/``f`` shape, minus the hero swap: curator mounts a
        second hero per mode and toggles which one shows, but this screen
        has exactly one hero and it is not part of either body -- it is
        outside ``#surf-launchpad-body`` entirely (see ``compose``) and this
        method never touches its ``display``, so it is on in both modes.
        """
        launchpad = self._mode == MODE_LAUNCHPAD
        try:
            self.query_one("#middle-row").display = not launchpad
            self.query_one("#separator").display = not launchpad
            self.query_one("#bottom-row").display = not launchpad
            self.query_one(f"#{LAUNCHPAD_BODY_ID}").display = launchpad
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

    def action_show_dashboard(self) -> None:
        """``escape`` -- one-way back out of the launchpad view."""
        self._mode = MODE_DASHBOARD
        self._show_mode()

    def _rail_is_cut(self) -> bool:
        """Does the right rail hold more than this height can show?

        ``show_vertical_scrollbar`` is the rail's own answer to that question
        and is what the layout already turns the loss into; asking it rather
        than re-deriving the arithmetic keeps the marker and the scrollbar
        from ever disagreeing.
        """
        try:
            return bool(self.query_one("#surf-right-rail").show_vertical_scrollbar)
        except Exception:  # noqa: BLE001 -- not composed yet, or torn down
            return False

    def _render_title(self) -> None:
        """(Re)compose the title bar from the last payload plus the marker."""
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
