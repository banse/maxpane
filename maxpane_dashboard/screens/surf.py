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
                             SurfLaunchpadCoins    (2fr, 13..23, +1 margin) |   SurfCurveFlow      (auto, +1 margin)
                             SurfLaunchpadActivity (1fr)    |   SurfBurnPipeline   (auto, +1 margin)
                                                            |   SurfBurnkeepers    (1fr)

``e`` swaps the same three rows for a **third** body, the POOL4 view
(2026-09-01), on the identical shape. The key was ``p`` until 2026-09-15,
when the owner took it off the status hint and moved it to ``e`` for
experimental; "the ``p`` body" below and throughout this module names this
body, whichever key opens it::

    #surf-pool4-body   #surf-pool4-left (1fr)          | #surf-pool4-rail (1fr)
                         SurfPool4Split   (auto, +1 m) |   SurfPool4Hatches (auto, +1 margin)
                         SurfPool4Ratchet (auto, +1 m) |   SurfPool4Vault   (1fr)

**POOL4 FLOW left this body on 2026-09-14.** The owner asked for it off a
live screenshot: the ``4`` market body's RECENT FLOW already renders the
same rows, so ``p`` printed them twice. The left column is now two ``auto``
panels and **no** ``1fr`` child -- :data:`POOL4_LEFT_ID` argues why its
spare rows stay blank space at the column's foot instead of going to a
panel.

The columns were cut to **balance their heights** when mainnet landed -- 34
rows each at the worst payload -- and that balance ended with FLOW: the left
column carries 28 and the rail 34, so the rail alone sets
``SURF_POOL4_FULL_LAYOUT_ROWS`` now, which is why that pin did not move
while ``SURF_POOL4_FULL_LAYOUT_COLUMNS`` did (106 -> 99, HATCHES binding).
The rail's ``1fr`` is still on the *fixed* panel (sIMD VAULT), which is the
reverse of the other two bodies' rule -- see that constant for why.

``4`` swaps the same three rows for a **fourth** body, the POOL4 MARKET
view (2026-09-11), on bakery's shape rather than on the other two bodies'::

    #surf-pool4-user-body  (a column of two rows)
      #surf-pool4-user-middle  SurfPool4Flow     (1fr) | #surf-pool4-user-rail (1fr)
                                                       |   SurfPool4UBurn    (auto, +1 m)
                                                       |   SurfPool4USignals (1fr)
      #surf-pool4-user-bottom  SurfPool4UStakers (1fr) | SurfPool4UDepth      (45 cols)

**The two left-hand panels traded rows on 2026-09-12, and the bottom row's
seam stopped being a ratio.** The owner read the live screen and asked for
three things at once: STAKERS below RECENT FLOW, STAKERS wide enough to print
a **whole** 42-character address, and IF IMD FALLS narrower, "as half of its
space is empty". The first is the swap above. The second and third are one
change: the ladder's width is now the **constant** its content actually is
(``SurfPool4UDepth`` is 45 columns, which is ``pool4u_depth.CAPTION`` plus
its padding and nothing else) and STAKERS takes every remaining column as
``1fr``. A ``fr`` seam would have handed the ladder a *share* of the terminal
and grown it back past its old 52 on any wide screen, which is the opposite of
what was asked; a fixed column gives the extra to the leaderboard at every
width. See :data:`SURF_POOL4_USER_FULL_LAYOUT_COLUMNS` for what the whole
address cost and what the ladder gave back.

``SurfPool4Flow`` is **mounted here and nowhere else since 2026-09-14.** From
2026-09-11 it was the ``p`` body's panel mounted a second time rather than
copied (PRD §6.4), and the screen dispatched to every instance in one
statement so the two could never be handed different rows. The owner then
removed the ``p`` body's copy because it duplicated this one. The module is
still reused unchanged, the dispatch still loops ``self.query`` (so a future
second mount would be fed without an edit), and the per-instance keywords the
mount passes are now vestigial -- filed as F15 in
``docs/surf_pool4_followups.md``.

**``#hero-row`` is NOT untouched any more, and this is the sentence that had
to change.** It read "``#hero-row`` is never touched by either swap and stays
on screen in all three modes" until 2026-09-11, and the ``4`` body is exactly
the case that makes it false: the row now holds **two** heroes, ``SurfHero``
and ``SurfPool4UserHero``, and ``_show_mode`` toggles which one shows. The row
itself still never hides -- a hero is on screen in every mode, as it always
was -- but *which* hero is a function of ``self._mode``, on curator's
per-mode hero pattern. PRD §3 argues the break: surf's own headline metrics
are the clearest thing on this body a reader does not act on. See "The
2026-08-23 ``l`` view" below.

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
from textual.widgets import DataTable, Static

from maxpane_dashboard import config
from maxpane_dashboard.screens.seat_input import parse_seat
from maxpane_dashboard.widgets.surf import SurfSwarmBoardHero, SurfSwarmLeaderboard, SurfSwarmFleet
from copy import deepcopy
from maxpane_dashboard.screens.oracle_answer import OracleAnswerScreen
from maxpane_dashboard.widgets.surf._oracle_answer import valid_identity, joined
from maxpane_dashboard.status_message import post_status_message
from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.screens.dashboard_screen import DashboardScreen
from maxpane_dashboard.screens.seat_input import SeatInputScreen
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token
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
    SurfPool4UBurn,
    SurfPool4UDepth,
    SurfPool4USignals,
    SurfPool4UStakers,
    SurfPool4UserHero,
    SurfPool4Vault,
    SurfSignals,
    SurfSwarmAgentHero,
    SurfSwarmCapability,
    SurfSwarmHero,
    SurfSwarmInFlight,
    SurfSwarmLaunches,
    SurfSwarmNodeCards,
    SurfSwarmSeatCards,
    SurfSwarmSeatRecord,
    SurfSwarmSites,
    SurfSwarmThroughput,
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
#:
#: **2026-09-15: re-swept for the twenty-coin table, and 138 held.** The coin
#: panel became the left column's ``2fr`` share. The first cut of that change
#: handed the table all twenty coins at every height. At 31 rows the table
#: then scrolled inside itself, and its scrollbar cut the ``BURNED`` header at
#: 138-140 while this panel's ``‹ widen`` was dark: the width need had become
#: a function of the height. The shipped version draws only the coins its
#: laid-out height holds (``SurfLaunchpadCoins._rows_that_fit``), so the table
#: never scrolls. Re-swept in situ over 128-146 at 31, 36 and 60 rows (10, 13
#: and 20 coins drawn), with a twenty-coin payload under both the capture's
#: burn line and the ordinary one: ``‹ widen`` lit through 137, ``BURNED``
#: whole and nothing clipped from 138, no table scrollbar at any width.
#: BOARD WP4 (2026-09-22): adding b board moves the whole status bar's
#: onset to 142. §11 shortens the hint and restores the 138 body pin; its
#: COINS table marks below that. The 128–145 capture/ordinary-burn sweep
#: confirms 138, while complete status text clears from 134 (133 still crops).
#: Row boundaries 30/31 were checked again at 138 with capture and 20 coins.
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
#:
#: **2026-09-15: COINS took ACTIVITY's rows, and 31 held with the margin
#: spent.** The owner's screenshot showed ten coins over a mostly empty
#: ACTIVITY feed, and the coin table running straight into the ACTIVITY
#: title. Three changes answer it:
#:
#: * ``SurfLaunchpadCoins`` gained ``margin: 0 0 1 0``, the blank row above
#:   ACTIVITY's title.
#: * COINS is now ``2fr`` against ACTIVITY's ``1fr``, floored at 13 (the ten
#:   rows it had) and capped at 23 (title, blank, header and the twenty
#:   coins ``LAUNCHPAD_RENDER_LIMIT`` now fetches).
#: * The table draws only the coins its height holds, so it never scrolls
#:   inside itself.
#:
#: **The left column is now 20 at its floors (13 + 1 + 6), level with the
#: rail's 20.** The paragraph above says it was 19; the gap row spent that one
#: row of margin, so both columns bind at once. Re-swept in situ, starting
#: below the pin, over rows 24-46 plus 50, 55 and 60 at 150 columns, with the
#: capture and a twenty-coin payload. ``‹ taller`` is lit through 30 and dark
#: from 31 in both. Coins drawn by height: 10 at 31, 15 at 40, 19 at 45, 20
#: from 50. ACTIVITY is 6 rows at 31, 10 at 40, 15 at 50, then 25 at 60, as
#: every row past COINS' 23-row ceiling goes to the feed. The blank row sits
#: above ACTIVITY's title at every height from 31. **Below the pin the
#: column's ``fr`` children inflate while it scrolls** (COINS reads its
#: 23-row ceiling at 30 rows). That is why the derivation is now asserted at
#: the pin rather than at 28 rows, where it used to be read off the floors.
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
#: **RE-SWEPT 2026-09-14, WHEN POOL4 FLOW LEFT THIS BODY: 106 -> 99.** The
#: owner asked for the flow log gone from ``p`` because the ``4`` market
#: body's RECENT FLOW already renders the same rows. FLOW was this pin's
#: binder (a 52-need panel buying 53 with its column's gutter), so removing it
#: had to lower the pin. It fell seven columns, not the three a "53 -> 50"
#: guess predicts: 1:1 now has to hand the *rail* its 50, and at an odd width
#: the rail takes the odd column.
#:
#: Swept column by column over the real screen at 50 rows, **86..125**, on the
#: committed capture, the ordinary-magnitude payload and the twelve-lever
#: mainnet payload. The range starts thirteen under the number it collected
#: and never on the old pin or the new one. All three agree to the column:
#:
#: * **whole from 99** -- no ``‹`` on any panel and no CSS-clipped line;
#: * at **98** exactly one panel is marked, ``SurfPool4Hatches``, in the rail
#:   (left 49 | rail 49). **The binder is HATCHES now**, pinned by
#:   ``test_the_pool4_binding_panel_is_hatches`` on the precedent of
#:   ``test_the_launchpad_binding_panel_is_the_coins_table`` and curator's
#:   ``test_the_analysis_binding_panel_is_the_operators_table``;
#: * THE RATCHET marks from 89 down, and its **45** is now the left column's
#:   widest need (SPLIT rides along at 36). Every CSS-clipped line in 86..91
#:   has HATCHES' marker lit beside it, and
#:   ``test_nothing_below_the_pool4_pin_clips_without_saying_so`` covers
#:   80..98.
#:
#: So **left needs 45 and the rail 50**, the arithmetic floor is 95, and 1:1
#: does not collect it. At 99 it gives the left column 49 (four spare) and the
#: rail exactly 50.
#:
#: **The seam was not re-chosen, and the argument that chose it is now
#: inverted rather than retired.** 1:1 was picked so the LEFT column bound,
#: because FLOW wrote its marker into its own log and never went quiet. HATCHES
#: appends its marker to a title and gives it up first under pressure, so the
#: rail was bought three columns of margin. With FLOW gone, the rail binds with
#: **zero** margin, which is exactly the arrangement the paragraphs below
#: declined. It is acceptable here because it was measured, not argued:
#: HATCHES carries a ``‹`` at every width in the 86..98 sweep on all three
#: payloads, and the full ``‹ widen`` at 80..85 and at 98 on the capture (its
#: panel is 39..48 columns across that range). A seam favouring the rail might
#: buy that margin back, but it was **not** swept: re-cutting the seam is a
#: layout decision this removal did not ask for.
#:
#: **EVERYTHING BELOW THIS POINT IS THE PRE-2026-09-14 RECORD** of the
#: five-panel body. It is kept because it is what the seam was chosen on.
#: Where it says FLOW binds, the left column needs 53, the rail has three
#: columns of margin or the pin is 106, read it as history. The bullets above
#: are the live measurement.
#:
#: **The binding panel WAS ``SurfPool4Flow``**, pinned until 2026-09-14 by
#: ``test_the_pool4_binding_panel_is_the_flow_log``. At 105 -- one column
#: under the old pin -- it was the only one of the five panels with a marker
#: lit.
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
#:
#: **2026-09-14 -- the copy icon, paid for inside HATCHES' own cell.** Every
#: displayed address gained a ``⧉`` that copies it (``docs/address_copy_PRD.md``
#: §5), and no pin may move for it. HATCHES binds this pin with zero margin,
#: so its lever grid's last cell could not grow: it stays 17 cells and the
#: address inside it went **17 -> 15**, with the icon in the two cells freed.
#: The anti-poisoning window there is **8 hex / 6 hex -> 6 / 6**
#: (``widgets/address.short_address``); both halves still differ on the live
#: spoof pair the 8/6 form was chosen for, and the whole address is one click
#: away. The address block above the grid kept the full 17-cell 8/6 window
#: beside its icon: its widest line (the distributor row) is 41 cells, under
#: the grid's 45. Re-swept in situ over 94-102 with the mainnet payload:
#: HATCHES is unmarked from 99 and marked at 98, as before.
SURF_POOL4_FULL_LAYOUT_COLUMNS = 99

#: The ``p`` POOL4 body's own measured **height**, re-swept 2026-09-02 for
#: the mainnet deployment, again after the panels were shortened, and again
#: on **2026-09-12** when this body took the repo-wide blank row under every
#: panel title. **43 -> 44 -> 46 -> 44 -> 45 -> 45.**
#:
#: **RE-SWEPT 2026-09-14, WHEN POOL4 FLOW LEFT THIS BODY: 45, UNMOVED.** The
#: owner removed the flow log from ``p`` off a live screenshot showing
#: ``‹ taller`` lit, and removing a panel reads as though it should clear
#: that. It does not, for the reason this block has argued since mainnet: only
#: the binding column reaches a pin, and FLOW sat in the column that *tied*
#: rather than the one that binds alone. Measured on ``mainnet-capped`` at 150
#: columns, every height from 36 to 50:
#:
#: * left column content **34 -> 28** (SPLIT 15 + margin + RATCHET 11 +
#:   margin, with FLOW's 6-row floor gone), whole from 39 rows;
#: * rail content **34, unchanged** (HATCHES 23 + margin + VAULT 10), whole
#:   from 45 -- so ``‹ taller`` is still lit at 44, and what it reports is the
#:   rail's last row (sIMD VAULT's ``as of`` line) behind the rail's own
#:   scrollbar;
#: * no panel shorter than its own ``virtual_size`` at any height, in either
#:   column.
#:
#: **What the owner sees at 44 rows, before and after, rendered rather than
#: inferred:** ``‹ taller`` lit both times. THE SPLIT's title is on screen
#: both times (``scroll_y`` 0 on a fresh render; the scrolled-away title in
#: the screenshot is not reproduced by this harness). The one visible change
#: is that the left column stops scrolling: THE SPLIT and THE RATCHET are both
#: whole, with blank rows beneath them where FLOW was. Clearing the marker at
#: 44 needs a row out of the RAIL, and that was not this change's to spend.
#:
#: The committed capture still goes whole at 42, because the rail binds it
#: too. **Every row the left column set or tied now needs less, and only the
#: twelve-lever mainnet rows keep 45.** That is not a guess:
#: ``test_the_pool4_height_pin_is_measured_against_the_column_it_describes``
#: measured its two older payloads at **33** rows of worst-case content after
#: the removal (Sepolia twelve levers 33, mainnet ten levers 32), where it had
#: read 34 through mainnet's left column. That test now measures
#: ``mainnet-capped`` directly. The other lighter rows were not re-swept
#: individually, because a payload that needs less than the pin never lowers
#: it. **The table and the "33 rows ... reached by BOTH columns" paragraph
#: below are the pre-removal record**: their ``FLOW``, ``left`` and ``need``
#: columns are history everywhere except the two twelve-lever mainnet rows.
#:
#: **THE 2026-09-12 RE-SWEEP, AND THE 2026-09-02 NOTE IT REVERSES.** Until
#: today this block recorded that ``sIMD VAULT``'s post-title blank row was
#: **deleted** to hold the pin at 44, and cited that deletion as the standing
#: "shorten the value, do not raise the pin" rule working. That row is back,
#: and so are three more: the owner's convention is that **every** widget
#: title on every dashboard is followed by one blank row, and a body that
#: opts out because it is the tallest one is how a convention stops being a
#: convention. ``SurfPool4Ratchet``, ``SurfPool4Hatches`` and
#: ``SurfPool4Vault`` each grew a rendered blank line, and ``SurfPool4Flow``
#: lost the ``.market`` scope on the ``margin: 0 0 1 0`` it had been painting
#: in the ``4`` body alone. (``SurfPool4Split`` already had the row -- its
#: ``_body_lines`` has always opened with one -- so the survey's count of
#: four panels on this body was one high; see the report.)
#:
#: **THE PIN MOVED 44 -> 45 AND THAT IS THE WHOLE PRICE OF THE CONVENTION
#: HERE.** Four panels each grew a row and the body grew one, because only
#: the binding column's growth reaches the pin and the two columns grew one
#: row each rather than two: on the binding mainnet payload the left column
#: took RATCHET's row (SPLIT and FLOW are unchanged -- SPLIT already had its
#: blank, and FLOW's lands inside a panel whose height is the column's
#: ``1fr`` floor) and the rail took HATCHES' (VAULT's landed inside its own
#: ``min-height: 10``, which it now fills exactly). The ``4`` market body
#: paid two rows for the same change on 2026-09-12; this one pays one.
#:
#: SWEPT **36..55**, nine rows below the number it collected and ten above,
#: never starting at either the old pin or the new one -- so agreeing with 44
#: would have had to show up as a measurement rather than as an assumption.
#: Five payloads at each height (no levers, ten, the widget's twelve-row cap,
#: mainnet, and mainnet at the cap), reading the screen-wide ``‹ taller``
#: marker off composited output **and** comparing every panel's laid-out
#: height against its own ``virtual_size``, because the marker alone cannot
#: see a panel cut inside a column that is not itself scrolling. No height in
#: the sweep produced a cut panel with the marker dark. The three lighter
#: payloads go whole earlier -- 42, 42 and 44 -- which is why the pin is a
#: worst case over payloads and is collected from ``mainnet-capped``.
#:
#: **WHAT THE ROW COSTS A READER, named rather than buried.** Two things,
#: and neither is free:
#:
#: * a terminal one row short of 45 that cleared 44 now loses this body --
#:   ``‹ taller`` lit, both columns scrolling, degraded and never silent.
#:   W7 (below) is still open, so nobody can say how many real laptops that
#:   is; making the tallest pin in the repo taller is a real cost to a real
#:   user and it is recorded here rather than estimated away.
#: * at the pin itself ``SurfPool4Flow``'s log shows **three** lines where it
#:   showed four -- its column heading plus **two** swaps instead of three.
#:   Its floor stayed at 6 (raising it to 7 would have taken the pin to 46 --
#:   measured, not guessed), so the header block's new blank row comes out of
#:   the log. That is a row moved behind the ``RichLog``'s own scrollbar,
#:   which is somewhere the reader can still reach, not a row lost -- the
#:   distinction the ``1fr`` rules on this body turn on.
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
#: real content rather than the terminal's height). **Re-measured whole on
#: 2026-09-12**, not adjusted by one:
#:
#: ===========================  =====  =======  ====  =====  =====  ====  ====  ====
#: payload                      SPLIT  RATCHET  FLOW  HATCH  VAULT  left  rail  need
#: ===========================  =====  =======  ====  =====  =====  ====  ====  ====
#: sepolia, 0 levers            12     11       6     11     11     31    23    42
#: sepolia, 8 levers            12     11       6     18     10     31    29    42
#: sepolia, 10 levers           12     11       6     20     10     31    31    42
#: sepolia, 12 levers           12     11       6     22     10     31    33    44
#: mainnet, 0 levers            15     11       6     12     10     34    23    **45**
#: mainnet, 8 levers            15     11       6     19     10     34    30    **45**
#: mainnet, 10 levers           15     11       6     21     10     34    32    **45**
#: mainnet, 12 levers           15     11       6     23     10     34    34    **45**
#: mainnet, 12 levers, long     15     11       6     23     10     34    34    **45**
#: flow log
#: ===========================  =====  =======  ====  =====  =====  ====  ====  ====
#:
#: SPLIT and FLOW are the two columns that did **not** move on 2026-09-12,
#: for two different reasons, and both are worth knowing: SPLIT already
#: painted the blank row, and FLOW's new one is absorbed by the floor it sits
#: on (its log gives the row up instead). RATCHET and HATCHES each grew one,
#: and that is the whole of the +1 in every ``need`` above.
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
#: rail's content" would be reading the harness rather than the layout.
#:
#: **The lone ``11`` in the VAULT column is the same artifact one level
#: down**, and it moved when the blank rows landed (it used to sit on the
#: mainnet no-lever row and now sits on the Sepolia one), which is the
#: clearest possible demonstration that it is slack rather than content.
#: VAULT carries the rail's ``1fr``, so on a row where the rail is not
#: binding it absorbs whatever HATCHES did not take. Its **content** is ten
#: lines on every payload -- title, blank, seven rows and the ``as of``
#: marker -- and that is the figure ``min-height: 10`` is set against. Every
#: other figure in the table is a genuine ``virtual_size`` overflowing its
#: column.
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
#: **an eleven-line VAULT needs a pin of 45.** It was fixed at source then,
#: by dropping the panel's post-title blank.
#:
#: **That blank came back on 2026-09-12 and the slack it bought is gone.**
#: VAULT is ten lines again, which is exactly ``min-height: 10`` -- floor and
#: ceiling both, with nothing spare. The eleventh line added to this panel
#: will be cut, and the guard against that is still
#: ``test_the_pool4_floors_never_thin_a_panel_below_its_content``, which
#: compares the laid-out height against the panel's own content and does not
#: need slack to bite. What the slack used to buy was a *warning shot*, and
#: there is no longer one: raise the floor with the line, in this file and in
#: ``themes/minimal.tcss``, and re-sweep. The 2026-09-02 measurement above
#: says what that costs -- an eleven-line VAULT takes this pin to 46.
#:
#: The guard is not this constant, it is
#: ``test_the_pool4_floors_never_thin_a_panel_below_its_content``, which
#: compares VAULT's laid-out height against its own content. Keep it: the
#: pin cannot detect this failure, because the failure is precisely a body
#: that stops asking for the rows it needs.
#:
#: **45 is the tallest pinned requirement in this repo and nobody has
#: measured whether a common laptop clears it -- and on 2026-09-12 it got
#: one row taller.** That is the part of W7 that changed today: the question
#: was open at 44 and it is open at 45, but the answer can only have got
#: worse, and the row was spent knowingly on a convention rather than on a
#: number. The *columns* side of that
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
SURF_POOL4_FULL_LAYOUT_ROWS = 45

#: The ``4`` POOL4 MARKET body's own full-layout width, swept in situ on
#: 2026-09-11 and **re-swept on 2026-09-12 after the body was restructured**.
#: **Neither a restatement nor a derivation of
#: :data:`SURF_FULL_LAYOUT_COLUMNS` (143), of
#: :data:`SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` (138), of
#: :data:`SURF_POOL4_FULL_LAYOUT_COLUMNS` (99; 106 until 2026-09-14) or of
#: ``__main__.FULL_LAYOUT_COLUMNS``** -- a fourth body gets a fourth
#: measurement, on the rule in the terminal-layout skill.
#:
#: **105 -> 119, and the whole of the move is one column of one table.** The
#: owner asked for STAKERS' addresses in full -- all 42 characters, no window
#: -- off the live screen. ``pool4u_stakers._ADDR_COLS`` went 17 -> 42, that
#: panel's ``FULL_WIDTH`` went 44 -> 69 and what it needs on screen went
#: **48 -> 73**. IF IMD FALLS gave **seven** of those columns back (52 -> 45,
#: below), so the body paid the remaining fourteen. That is the honest
#: accounting and it is stated here rather than absorbed: nothing else on this
#: body was shortened to hold 105, and the alternative that would have held it
#: is recorded at the bottom of this block.
#:
#: HOW IT WAS MEASURED. The composed body was rendered through ``run_test``
#: at **every width from 38 to 156** -- eighty-one columns below the number it
#: collected and thirty-seven above, never starting at it, and crossing every
#: other pin on this screen (106 at the time, 138, 143) so agreeing with any of them would
#: have had to show up as a sweep result rather than as an assumption. At each
#: width the five panels were read off composited output for a ``‹`` marker
#: and for a CSS-truncated line. Arithmetic over the column constants was not
#: used and must not be: a ``DataTable`` buys a cell gutter per column, two of
#: these five panels are tables, and a panel's own ``size.width`` is already
#: its **content** width, so a sum built from the outer widths is two columns
#: out per panel before the gutters are counted.
#:
#: WHICH PANEL BINDS: ``SurfPool4UStakers`` -- it was ``SurfPool4Flow`` until
#: the restructure -- and it is the **sole** marked panel at 118 under every
#: payload swept. That satisfies the standing rule that a panel which can bind
#: must be able to *mark*: STAKERS drops its ``share`` column and lights ``‹``
#: in its own title the moment it is short, so the seam is not carried by a
#: panel that would lose a column in silence.
#:
#: WHAT THE NUMBER IS MADE OF, measured panel by panel at the width where each
#: one's own marker goes dark rather than added up from their ``FULL_WIDTH``
#: constants:
#:
#: ===================== ====== ==============================================
#: panel                  needs  in which column
#: ===================== ====== ==============================================
#: ``SurfPool4UStakers``     73  bottom row, left (was 48 at a 17-cell address)
#: ``SurfPool4UDepth``       45  bottom row, right -- FIXED, see below
#: ``SurfPool4Flow``         52  top row, left
#: ``SurfPool4USignals``     50  top row, rail (51 with the rail's gutter)
#: ``SurfPool4UBurn``        36  top row, rail
#: ===================== ====== ==============================================
#:
#: The **top** row is ``1fr:1fr``, so it asks for 1 + 2 x 52 = 105 and no
#: longer binds anything. The **bottom** row is a fixed column beside a
#: ``1fr``: 73 + 45 = 118, plus the one column ``#surf-pool4-user-body``
#: reserves for its own ``scrollbar-gutter: stable``, is 119.
#:
#: **WHY THE LADDER IS A FIXED 45 AND NOT A ``fr``, and it is two reasons.**
#: The first is the request: a ``fr`` gives IF IMD FALLS a *share* of the
#: terminal, so on the owner's own 169-column screen a ``73:45``-shaped ratio
#: would have handed it 65 columns -- wider than the 52 they asked to shrink.
#: A fixed column gives every extra column to the leaderboard instead, at
#: every width, which is what "give the freed columns to STAKERS" actually
#: means. The second is that 45 is not a taste: it is
#: ``widgets/surf/pool4u_depth.CAPTION`` (41 cells) plus the two columns of
#: panel padding and the two the caption's own ``Static`` takes, measured in
#: situ and pinned by
#: ``test_the_ladder_column_is_exactly_the_width_of_its_own_caption``.
#:
#: **AND THE CAPTION IS WHY IT COULD NOT GO NARROWER, WHICH IS THE ANSWER TO
#: "half of its space is empty".** The ladder *table* was 27 cells wide -- the
#: request's own estimate of 26 was one out -- and is 29 since ``not reached``
#: widened ``band used`` on 2026-09-14; but the sentence under it,
#: ``quoted from the position as it stands now``, is 41, and below 45 columns
#: that sentence is cut by CSS with an ellipsis and **no ``‹`` marker**: this
#: panel's widen tier is decided by its table, so between 33 and 44 columns it
#: clips in silence (31 and 44 before that change; both swept). That disqualifies every seam narrower than 45 under the
#: standing rule, and it is the reason the freed columns stop at seven rather
#: than the twenty-five the table alone would allow. Shortening the caption to
#: 29 cells or fewer was measured as the alternative -- it would hold this pin
#: at 105 and take the ladder to 33 -- and was **not** spent: that sentence is
#: PRD §8.2's honesty contract, and rewriting it to protect a constant is the
#: trade this repo makes in the other direction.
#:
#: **The pin does not move with the data**, and that was measured rather than
#: hoped: the sweep ran over the same payload states the row pin uses (ten
#: since 2026-09-14, when a live-shaped band-not-reached state joined them) --
#: the committed capture, ``_ordinary_pool4_payload``'s widest flow formats,
#: the mainnet capture, a twenty-row staker list (the renderer's cap until
#: 2026-09-15, when it became every staker) with ``999.9B``-magnitude holdings, both at
#: once, an unread staker list, an empty one, and a deployed/absent/unread
#: band -- and collected 119 for every one of them. Every column on both
#: tables is floored at its own header label, and an address is 42 characters
#: whatever the wallet, so the widest value a cell can hold never exceeds the
#: budget the header already bought.
#:
#: **IT IS NO LONGER THE NARROWEST PINNED BODY IN THE REPO.** It was, at 105,
#: one column under the ``p`` body's 106 with the same panel binding both. It
#: is now thirteen columns *over* it and the binder is a different panel, so
#: the two numbers no longer have anything to say about each other. 119 is
#: still comfortably inside ``__main__.FULL_LAYOUT_COLUMNS`` (143), which is
#: the number that decides whether a reader can actually open this body, so it
#: does not append to the app-wide width record the terminal-layout skill
#: keeps.
#:
#: **2026-09-14 -- the copy icon, and STAKERS gave it two cells at the pin.**
#: Every displayed address gained a ``⧉`` that copies it
#: (``docs/address_copy_PRD.md`` §5), and no pin may move for it. STAKERS
#: binds this pin, so the whole address plus icon (44 cells) would have moved
#: it. The panel now picks the longest form that fits beside the icon: at a
#: text budget of 71 or more (terminal 121+ on this body) the **whole
#: 42-character address**; below that, the address windowed to **40** --
#: ``0x`` + 31 hex + ``…`` + 6 hex (``widgets/address.short_address``), which
#: still carries every character an address-poisoning spoof would have to
#: match on either end and more -- so ``pool4u_stakers.FULL_WIDTH`` stays 69
#: and the icon costs the body nothing. The whole value is one click away at
#: every width. No marker announces the 40: it is a short form, not a shed
#: column. Re-swept in situ over 114-122 with the mainnet payload: compact
#: and marked at 118, windowed and unmarked at 119-120, whole from 121.
SURF_POOL4_USER_FULL_LAYOUT_COLUMNS = 119

#: The ``4`` POOL4 MARKET body's own full-layout height, swept in situ on
#: 2026-09-11, re-swept twice on 2026-09-12 for the ``as of`` removal and a
#: **third** time the same day for the STAKERS/FLOW row swap, at 150 columns
#: -- comfortably past the width pin above, so nothing here is measuring a
#: width.
#:
#: HOW IT WAS MEASURED. Rows **24 to 46**, never starting at the pin and
#: re-centred each time it moved, over ten payload states (the committed
#: capture; the mainnet capture; the widest flow formats; a twenty-row staker
#: list; both at once; an unread staker list; an empty one; a deployed band,
#: an absent band and an unread band). At each height the screen-wide
#: ``‹ taller`` marker was read off the title row **and** every fixed-height
#: panel's painted line count was compared against the same panel's count on
#: a 60-row terminal, because the marker alone could not always see the loss
#: this body had (below).
#:
#: **33 -> 35 -> 32 -> 35, and the last move is a choice rather than a
#: measurement of content.** The first two are recorded below. The third came
#: with the row swap: STAKERS moved out of ``#surf-pool4-user-middle`` (floor
#: 12, the rail's own content) into ``#surf-pool4-user-bottom`` (floor 9, the
#: ladder's own content), and a leaderboard in a nine-row slot prints
#: **five** entries. It printed nine before the swap. So the bottom row's
#: floor was raised 9 -> 12 to match the top row's, and with it
#: ``SurfPool4UStakers``'s own 11 -> 12.
#:
#: **That is the deliberate margin the terminal-layout skill asks to be
#: declared rather than hidden.** Every other floor on this body is a panel's
#: own content height; this one is three rows above IF IMD FALLS's. What it
#: buys is measured and exact: swept against the baseline at every height from
#: 35 to 46, STAKERS now prints **the same number of rows or more** than it
#: did before the swap -- 9 at the pin, 12 at 40 rows, 15 at 46 -- so the
#: owner's leaderboard lost nothing at any height they can reach. What it
#: costs is the three rows: at 12/9 floors this pin would still read 32, and
#: STAKERS would print 5, 6 and 7 rows at 32, 33 and 34 against the 9 it
#: printed there before. Above 35 the two rows are ``1fr`` siblings and share
#: every extra row equally, so the floors are the *only* place this choice is
#: visible at all.
#:
#: THE RECORD, FOR THE TWO EARLIER MOVES. 33 -> 35 paid for the repo-wide blank
#: row under every panel title (``_pool4.TITLE_CLASS``, ``margin: 0 0 1 0``):
#: four panels grew a row and the pin moved two, because only the binding
#: column's growth reaches it. 35 -> 32 gave three rows back when the owner
#: asked for the per-panel ``as of`` markers on this body to go and **all five
#: panels lost a row** -- three rows back for five removed, because the rail
#: lost two (BURN and SIGNALS stack in it) and the bottom row lost one, and
#: only the *taller* of the two rows reaches the pin. Neither number is
#: recoverable by arithmetic, which is the point of sweeping for both.
#:
#: WHICH PANEL BINDS: **neither row's content, and that is new.** It was
#: ``SurfPool4UDepth``, whose eight painted lines over nine rows were exactly
#: ``#surf-pool4-user-bottom``'s floor. The ladder still paints those eight
#: lines and its own ``min-height`` is still the nine they sit in, but the row
#: around it is now floored at 12 for the leaderboard beside it, so what binds
#: is the pair of floors: 12 + 12 + the bottom row's one-row margin is 25, and
#: the ten rows of chrome above and below the body (title, blank, hero, status
#: bar) make 35. **35 is tight in the same way 32 was**: at 34 the body
#: scrolls, and what goes off the bottom first is the ladder's caption and
#: STAKERS' concentration footer -- the two lines on this body that say what
#: the numbers above them mean.
#:
#: **THE ONE-ROW MARKER-DARK WINDOW IS STILL GONE, AND STILL NOT BECAUSE
#: ANYONE FIXED THE MARKER.** ``_rail_is_cut`` asks
#: ``#surf-pool4-user-body`` and ``#surf-pool4-user-rail`` for
#: ``show_vertical_scrollbar`` and neither container can see a table
#: scrolling inside a panel (F6). What closes the window is the **floor**:
#: a panel floored at its own content cannot be squeezed into a height where
#: its table scrolls internally while the body does not, so the loss moves to
#: the body's own scrollbar, which the marker can see. Raising the bottom
#: row's floor above its tallest panel's content only widens that safety
#: margin. Swept over 24..46 and all ten payloads, the two answers agree
#: exactly: content whole from 35, marker dark from 35.
#: **``_rail_is_cut``'s blindness itself is unchanged** and will bite the
#: next panel floored below its own content.
#:
#: WHICH PANELS ARE ALLOWED TO SCROLL INSIDE THEMSELVES, and therefore do
#: **not** set this number: ``SurfPool4UStakers`` (its table caps at
#: ``MAX_ROWS`` -- 20 until 2026-09-15, every staker up to 999 since, with
#: the panel's height unchanged -- against a floor of 12 -- a leaderboard is unbounded by
#: design, the way FLOW's ``RichLog`` is) and ``SurfPool4Flow`` itself. The
#: pin covers the panels whose line count is a **constant**: the hero (6
#: lines), BURN & SUPPLY (4 lines over 5 rows), SIGNALS (5 over 6) and the
#: ladder (8 over 9). That is the same allowance
#: :data:`SURF_POOL4_FULL_LAYOUT_ROWS` gave FLOW one body over, until FLOW
#: left the ``p`` body on 2026-09-14, applied to the two panels here that
#: have it.
#:
#: **The pin does not move with the payload.** All ten states collect 35.
#: Only a fully-unreadable ladder fits in less, and it fits because it has
#: collapsed to a single unavailable line -- a payload that needs *less* than
#: the pin never lowers it.
#:
#: **2026-09-15: RECENT FLOW gave a row to a blank line, and 35 held.** The
#: owner's screenshot showed FLOW's full 25-row log running straight into the
#: ``STAKERS`` title below it. ``SurfPool4Flow`` gained ``margin: 0 0 1 0``,
#: which takes the blank row out of the panel's own ``1fr`` height (its
#: ``RichLog`` scrolls inside itself) rather than adding a row to the body.
#: The top row's floor of 12 is unchanged, and FLOW's floor of 6 plus the
#: margin is 7, still under it. Re-swept in situ, starting below the pin,
#: rows 24-46 at 150 columns over the capture, the mainnet capture and the
#: widest payload. The taller/whole result is identical to the pre-change
#: sweep at every height: whole from 35, ``‹ taller`` lit at 34. FLOW is 11
#: rows at the pin (12 before) and STAKERS still paints nine addresses there.
#: The column pin was re-swept too (110-127, same three payloads): marked at
#: 118, clean from 119. Neither pin moved.
#: ``test_a_blank_row_separates_recent_flow_from_the_stakers_title`` pins the
#: gap against a full log. The committed capture's short log leaves the
#: bottom of the panel blank with or without the margin.
#:
#: **W7, ANSWERED FOR THIS BODY.** Open finding W7 asks whether a real laptop
#: clears the ``p`` body's 45 rows, the tallest requirement in the repo. This
#: body needs **35**: ten rows under ``p`` and four over
#: :data:`SURF_LAUNCHPAD_FULL_LAYOUT_ROWS` (31). It is no longer the smaller
#: of the two in *both* dimensions -- at 119 x 35 it is twenty columns wider
#: than ``p``'s 99 x 45 (106 x 45 until POOL4 FLOW left ``p`` on 2026-09-14)
#: and ten rows shorter -- so the two bodies now ask for
#: different terminals rather than one asking for a subset of the other. In
#: every case the shortfall is announced by ``‹ taller`` rather than taken
#: silently.
SURF_POOL4_USER_FULL_LAYOUT_ROWS = 35

#: The ``s`` SWARM body's own width. Set at 93 on 2026-09-16 when the body
#: was first wired; 128, 115, 95 and 116 across the 2026-09-17 review rounds
#: of the v1 grid (THE FIELD beside QUEUE over JUST SHIPPED beside
#: THROUGHPUT; ``docs/decisions.md`` keeps that history). **Re-swept to 141
#: on 2026-09-21 for swarm v2 (WP7).** Every v1 panel is gone and the grid
#: is new -- CAPABILITY beside THROUGHPUT, IN FLIGHT beside LAUNCHES, SITES
#: full-width beneath -- so nothing about 116 could be carried over; a new
#: body gets a new measurement (terminal-layout skill). **Neither a
#: restatement nor a derivation of :data:`SURF_FULL_LAYOUT_COLUMNS` (143),
#: :data:`SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` (138),
#: :data:`SURF_POOL4_USER_FULL_LAYOUT_COLUMNS` (119) or
#: ``__main__.FULL_LAYOUT_COLUMNS`` (143)**; it is the widest of surf's
#: bodies now, and it stays under the app-wide pin.
#:
#: HOW IT WAS MEASURED. The composed body was rendered through ``run_test``
#: and ``Pilot.resize_terminal`` at **every width from 60 to 225** at height
#: 80, on the committed v2 capture (100 jobs, 30 skills, 30 launches, 6
#: sites; ``tests/fixtures/surf/swarm_v2/``) and on the plan's worst case
#: (30 launches carrying 55 artifacts, 30 skills, 10 sites, 25 in-flight
#: rows with 200-character objectives); the two payloads agreed at every
#: width. At each width every panel's tier word, its ``‹`` marker, its
#: ``DataTable``'s hidden columns (``max_scroll_x``), its CSS-clipped lines
#: and its region against its row container's were read off composited
#: output. No arithmetic over the exported tier widths was used and none
#: may be: a ``DataTable`` buys a cell gutter per column and an ``fr`` share
#: rounds, so a sum is two to five cells out (below).
#:
#: WHICH PANEL BINDS: ``SurfSwarmCapability``. Its ceiling is
#: ``max-width: 93`` (``swarm_capability.FULL_WIDTH`` 89 + the table's
#: gutter 2 + padding 2) and it reaches ``full`` at content width 91 -- the
#: cell the ``fr`` share hands it at outer 141: ``tight`` through 131,
#: ``compact`` 132-140 with ``‹`` lit, ``full`` and dark from 141. At 140 it
#: is the **sole** marked panel besides the two named exceptions, so the pin
#: is not loose (``tests/screens/test_surf_swarm_layout.py``). It marks when
#: short (it sheds columns and lights its own title), so the seam is not
#: carried by a panel that would lose a column in silence. Shortening a
#: value was not an alternative: the columns CAPABILITY sheds below ``full``
#: are its tier ladder already, and 141 is what ``full`` costs.
#:
#: WHAT IS ON THE ROW, measured at 141: the screen is 141 wide, the body's
#: ``scrollbar-gutter: stable`` leaves each row 140, CAPABILITY takes 91 and
#: THROUGHPUT 44 under its ``max-width: 46`` (fr rounding) -- 135 of 140,
#: the rest is rounding, not slack to spend. THROUGHPUT paints its widest
#: fixed line whole from 93 outer columns and never marks or clips above it.
#: SITES is ``full`` from 100, ``compact`` 92-99, ``tight`` at or under
#: 91 with hidden columns under 72 (re-swept 2026-09-23 for F67, the label
#: column 29 -> 13; every width 60-159 on capture and worst case, which
#: agreed; the body pin did not move -- CAPABILITY binds it, SITES never did).
#:
#: THE TWO NAMED EXCEPTIONS, on THE FIELD's own precedent (its ``‹`` cleared
#: at 170 while the pin stood at 116): IN FLIGHT (``4fr``) is ``tight``
#: through 176, ``compact`` 177-221 and reaches ``full`` at **222**
#: (``INFLIGHT_NEVER_CLEARS_BELOW``, the no-note lower bound); LAUNCHES (``5fr``) hides columns
#: through 137 and none from 138, stays ``tight`` through 179, ``compact``
#: 180-204 and clears at **205** (``LAUNCHES_NEVER_CLEARS_BELOW``). Both
#: markers track a real loss and clear at a reachable width -- neither is a
#: permanently lit marker. The ``4fr : 5fr`` seam is what keeps LAUNCHES
#: hiding no column at 143 while IN FLIGHT keeps its log legible; both are
#: bounded by ratio and not by ``min-width`` because a bounded ``1fr`` child
#: whose ``min-width`` exceeds its share snaps to its ``max-width`` and
#: overflows the row in silence (measured 2026-09-17, ``minimal.tcss``).
#: Region overflow was zero at every width swept.
#:
#: THE OWNER'S TWO TERMINALS sit under the pin and degrade honestly: at 119
#: CAPABILITY is ``tight`` with ``‹`` lit and LAUNCHES hides eleven columns
#: behind its own horizontal scrollbar; at 138 CAPABILITY is ``compact``
#: with ``‹`` lit, LAUNCHES is ``tight`` with ``‹`` lit and hides none.
#: BOARD WP4 made complete status text bind at 142. The §11 hint re-sweep
#: restores the 141 body pin: CAPABILITY binds, while status clears at 134.
#: Height 20–61 at the new column pin confirms the same 42-row onset.
#: BOARD WP5 re-swept every width 60–225 at 80 rows on capture, v3 executing
#: note and stress. §11 repeated the 140/141 body boundary after the hint
#: change. IN FLIGHT's new last note
#: column keeps an explicit widen marker while clipped, even in full tier.
#: Named content exception: the served 81-character note clears at 532 and
#: the synthetic 309-character note at 1558, measured in situ beyond 225
#: with both adjacent widths and the complete composited note checked.
#: Those payload-dependent widths do not raise the body's pin. A fitting
#: literal ellipsis does not light widen. Unchanged template/objective cells
#: retain their existing literal-text ellipsis behavior.
#: WP6 amendment: CAPABILITY full now includes two optional columns. Its
#: baseline tier retains all seven original columns at141; only optional
#: inf/acc-att are shed through165 and advertised by widen. Full clears166.
#: The cap grows93 to118; at141 the original91-cell allocation is unchanged.
SURF_SWARM_FULL_LAYOUT_COLUMNS = 141

#: The ``s`` SWARM body's own height. 42 on 2026-09-16, 26 the same day for
#: the 2x2 grid, 28 on 2026-09-17 (F6, QUEUE's counter block). **Re-swept to
#: 42 on 2026-09-21 for swarm v2 (WP7)** -- the launch-day number again by
#: coincidence, measured on a body that shares no panel with that one.
#:
#: HOW IT WAS MEASURED. Every height from 20 to 61 at width 150 (past the
#: column pin, so nothing here is a width) and again at the column pin
#: itself, on the v2 capture and the worst case above; ``‹ taller`` lit
#: through 41 and dark from 42 on both. **The binder is
#: :data:`SWARM_BODY_ID`**, the ``Vertical`` of the three rows, and it is
#: the only container that ever scrolls on this body: the top row is
#: floored at THROUGHPUT's own sixteen fixed lines (``minimal.tcss``
#: ``#surf-swarm-top { min-height: 16 }`` -- a floor equal to content, so
#: the row never scrolls inside itself; the layout test binds the floor to
#: THROUGHPUT's composited height), IN FLIGHT | LAUNCHES and SITES are
#: ``1fr`` floored at eight lines each (title, blank, header, five rows),
#: and the body clears when the screen's chrome -- title row, blank,
#: six-line hero, the body's top margin, status bar -- leaves those 32 lines.
#:
#: WHY THE FLOOR. Without it the top row was a ``1fr`` share of the body
#: split three ways and reached THROUGHPUT's sixteen lines only at **58**
#: terminal rows (measured before the floor was added, same sweep), with
#: the row scrolling inside itself from 34 to 57 -- a ``‹ taller`` lit on
#: every terminal the owner has and cleared only by one nobody uses. The
#: floor gives THROUGHPUT its lines first and lets the two table rows take
#: the rest; AGENT's top floor now carries SEAT's thirteen the same way.
#: (§11 reduced it from WP5's seventeen.) At the owner's 35 and 31 rows the body scrolls and the marker says
#: so; no row of any panel is lost in silence
#: (``test_no_height_loses_a_row_of_either_body_in_silence``).
#: BOARD WP5 confirmed this onset again at every height 20–61, at 150 and
#: 142 columns, on capture, v3 executing notes and stress.
SURF_SWARM_FULL_LAYOUT_ROWS = 42

#: AGENT full-layout width, re-verified 2026-09-23 with oracle RECORD: 139
#: (135 for the first card rows, 138 before them, bound by BY NODE).
#: The owner asked for the three card rows to share one column grid and for
#: the wide cards to stack under STATUS (RANK in the hero since
#: 2026-09-22; row 2 ends COLLAB · TEAMMATES, row 3 OTHERS · BOARD). Column i has the same ``fr``
#: weight in every row (23 23 20 19 18 28): each weight is the column's
#: widest card, measured one card at a time in situ on the payloads below.
#: Measured in situ at every integer 125–160 at 80 rows on capture, #420,
#: duplicated reviews, the five-digit stress payload, the committed v4
#: RECORD and all seven v3 source states (pending, seats/workers/
#: contributors unread, never paired, no seat).
#:
#: **Binder: row 2, ``SurfSwarmSeatCards``.** OWNER's 17-cell address
#: window plus its copy icon is whole from 139 and ellipsises at 138 -- a
#: visible cut, which the sweep counts as a clipped line. Measured onsets
#: under it: the node row is whole from 116 (the stress payload's
#: ``55,555 acc of 99,999`` BOARD). OTHERS sums every node key the named
#: cards do not since 2026-09-22 (seat_0 serves deploy_script/manifest), so
#: a node card's counts shorten instead of cutting: full ``5,011 of 50,011``
#: at 142-143 and 145+, ``5.0K of 50.0K`` at 144, 129 and 131-141, whole
#: ``5K of 50K`` at 127-128 and 130 (fr rounding interleaves them). The status bar from 134, the row-1 hero from 129 (the stress
#: payload's ``19,998 pending``). On the capture the node row is whole from
#: 108 and the hero from 116; the pending payload's RANK (hero column 5)
#: from 117. STATUS writes ``⚙`` for
#: "working" (owner), so ``paused · ⚙ 0 of 99,999`` fits its 28 weight; the
#: word cost 32. The never-paired, pending and unread payloads are whole
#: from 134. Also swept: idle/paused/working/unknown worker states on the
#: stress payload (sixteen payloads in all, every one whole from 139). Free text
#: (runtime, daemon, node keys, role names) is fitted with a visible ``…``.
#: Row 1 gives up one right-hand column (``padding: 0 1 0 0``) so its
#: right edge lines up with the card rows inside the body's scrollbar gutter.
#:
#: RECORD is this body's one named exception: at 139 its full tier keeps
#: when/job/node/state/model/took/panel/tok/answer without horizontal clipping.
#: Re-swept 2026-09-23: full from 107, compact 99-106 (drops tok), tight
#: below 99 (also drops answer/model/took, keeps panel). table_cols needs
#: 102/94/53 cells; the screen contributes five cells of gutters/padding.
#: Full order and content-clearance onset are at
#: RECORD_NEVER_CLEARS_BELOW below.
SURF_AGENT_FULL_LAYOUT_COLUMNS = 139

#: AGENT height, re-verified 2026-09-23 with oracle RECORD: 33 (unchanged).
#: The owner asked for a blank row above each card row, matching the
#: two-cell gap between cards (+2), and allowed RECORD to shrink to pay
#: for it: RECORD's floor went 8 -> 6 (-2). Measured at 139 columns through
#: heights 26–45 on the twelve payloads named above: ``‹ taller`` lit
#: through 32, dark from 33 on every one. Re-swept 2026-09-22 when RECORD
#: lost the blank row under its title (the owner's exception for this body
#: only): still 33 on all twelve -- the freed row lands inside RECORD's
#: 6-row floor and so never reaches the pin. The card rows are fixed-height,
#: so the body is the only container that scrolls. The owner's 35 rows
#: fit; 31 shows ``‹ taller``.
SURF_AGENT_FULL_LAYOUT_ROWS = 33

#: RECORD answer-clearance onset, re-swept 2026-09-23 in the real AGENT body.
#: The committed v4 seat420 first40 rows are enriched with exact submission
#: captures and the new raw oracle corpus: 37 agreed, three off-panel.
#: Jobs76296dcd and73d7dcd7 have 27/80-cell replies; job33016bad at index125
#: remains outside the cap. table_cols reports full102/compact94/tight53;
#: in situ compact begins99 and full107 (98/106 still shed a tier).
#: Probed80-220 then both sides of every measured edge: no hidden selected
#: column or region overflow. At166 the 80-cell answer clips;167 and168
#: are whole. Five-hundred-character stress replies still mark at167.
#: This is a content exception, not the 139x33 body pin. Prefixes can make
#: other payloads wider; the latest oracle seat capture is checked separately.
#: Earlier clearances:204 ->165 when launch/sub left (2026-09-22), then
#: 165 ->167 for panel/tok and short models (2026-09-23).
#: 167 remains the submission-message fallback clearance for this v4 window.
#: Joined answer.json rows use their popup button instead of the widen marker.
RECORD_NEVER_CLEARS_BELOW = 167

#: CAPABILITY optional inf/acc-att columns: baseline keeps every original
#: column from141. At165 its115-cell panel sheds only these two extras;
#: at166 panel116/budget114 shows all nine columns without horizontal scroll.
#: Measured in situ on committed v4 skills at42 rows; SWARM remains141x42.
CAPABILITY_OPTIONAL_FULL_COLUMNS = 166


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

#: The ``4`` POOL4 MARKET body (2026-09-11) -- the **fourth** mode, and the
#: first one that also swaps the hero.
#:
#: It is a mode on the rule stated three paragraphs up rather than on the
#: count: a whole second body with its own five panels, not two panels
#: sharing a slot. ``p`` is the protocol and ``4`` is the market -- the two
#: read off the same ``TIER_POOL4`` sweep and answer different questions,
#: which is why the split is two bodies and not one crowded one.
MODE_POOL4_USER = "pool4_user"

#: The ``s`` SWARM body (2026-09-16) -- the **fifth** mode, and the second
#: (after :data:`MODE_POOL4_USER`) to swap the hero rather than leave
#: :class:`SurfHero` mounted. A whole second body with its own five panels
#: since swarm v2 (WP7, 2026-09-21: CAPABILITY, THROUGHPUT, IN FLIGHT,
#: LAUNCHES, SITES), on the same rule the docstring above states rather
#: than on a count.
MODE_SWARM = "swarm"

#: The ``a`` AGENT body shows the saved seat (``i``), or the most active
#: seat in the job window. Two card rows (seat details, work by node) sit
#: above a full-width RECORD. Seats, contributors and workers keep independent groups.
MODE_AGENT = "agent"
MODE_BOARD = "board"
BOARD_BODY_ID = "surf-board-body"

#: BOARD width, measured 2026-09-22: every integer 60–225 at 80 rows, with
#: v3 capture, 999-seat stress, workers-unread, contributors-unread and both
#: unread. Stress carries five-digit counters, 64-character runtime/daemon
#: names, 99 paused seats and 20 daemon versions. All twelve LEADERBOARD
#: columns are installed from 141; §11 complete status text clears from 134.
#: Compact begins 121; selected tight columns stop clipping at 94 with rows
#: and 92 without rows. Independent source-clock footer clears 86 on capture,
#: 92 with one unread source and 98 with both unread. Hero clears 97 on capture,
#: 126 on stress, 132 with workers unread and 133 with contributors/both unread.
#: The earlier region-only status check falsely passed 141 while surf lost
#: its final f. The gate now compares expected and composited right text.
#: No horizontal region overflow was observed. FLEET is 37 outer cells,
#: 35 panel cells and 33 content cells; it preserves whole metadata values
#: and accounts for every omitted entry with +N.
#:
#: Named content exception: stress runtime names exceed their eleven-cell
#: column and retain visible ellipsis plus widen even at the full-tier pin.
#: Only runtime may clip in that stress case; capture and source-failure
#: labels, all fixed counters, clocks and all twelve columns fit whole.
#: Owner 119 x 35 fits vertically (138 x 31 did until the 33-row pin, below); LEADERBOARD is tight at
#: 119 and compact at 138. Both mark widen; status is cropped only at 119. App-wide
#: 143 is unchanged.
SURF_BOARD_FULL_LAYOUT_COLUMNS = 141

#: BOARD height, 27 -> 33 on 2026-09-22 (owner: a blank row under
#: CONTRIBUTORS and "more data about the contributors" -- five lines:
#: devices · seats, accepted of attempts, rejected · pending, turns · hours,
#: tokens in · out). FLEET went 16 -> 22 rows with pauses (21 without), and
#: the body followed it one for one. Re-measured at 141 columns through
#: heights 45 down to 21 on capture, v4, stress and all three source-failure
#: states: ``‹ taller`` lit through 32 and dark from 33 on capture, stress and
#: contributors-unread; v4, workers-unread and both-unread are whole from 32.
#: The width did not move (every payload marks first at 140; stress's named
#: runtime exception marks at 141 as before). The owner's 35 rows fit; 31
#: now shows ``‹ taller`` -- the price of the five lines, not a margin.
#:
#: Before that, remeasured 2026-09-22 for polish WP3: every row 23–32 at
#: 141 columns, with v3 capture, v4 workers, 999-seat/five-digit stress and
#: all three source-failure states. FLEET now has aligned labels, the model
#: mix plus its advertised/omitted-count continuation, separate paused count
#: and detail, two group spacers and the independent contributor sub-header.
#: With pauses, fourteen body lines plus title and mandatory blank make 16;
#: seven hero rows and four chrome rows make the measured worst-case 27.
#: Without pauses (v4 capture) or without workers the detail is hidden: 15
#: panel rows, whole from 26. Contributors-unread retains the 27-row bound.
#: At 26 the v3/stress body scrolls and says taller; at 27 it does neither.
#: LEADERBOARD retains all 999 stress seats and scrolls internally. The width
#: was re-swept 60–225 on v4/stress and at source-state boundaries: all twelve
#: columns still begin at 141; 140 sheds three. FLEET remains 37 outer cells,
#: 35 panel cells and 33 content cells, with no silent clipping at the pin.
#: Both owner heights (31 and 35) fitted then. AGENT remained 138×32: its exact
#: approved polish grouping measured 37 rows and was skipped under the owner budget.
SURF_BOARD_FULL_LAYOUT_ROWS = 33

#: The modes whose hero is :class:`SurfHero` -- **enumerated, not negated**.
#:
#: ``_show_mode`` could write ``SurfHero.display = self._mode !=
#: MODE_POOL4_USER`` and it would be correct today. It is the ``not
#: launchpad`` shape that docstring warns about, one layer out: the fifth
#: body to arrive with a hero of its own would inherit ``True`` here and
#: paint two heroes into one row. Enumerating instead makes that case render
#: **no** hero, which is loud on screen and red in
#: ``test_exactly_one_hero_shows_in_every_mode`` either way -- but only one of
#: the two failures is visible to a reader who is not running the tests.
#:
#: **MODE_SWARM, MODE_AGENT and MODE_BOARD are deliberately absent.**
#: Each is a body with a hero of its own (:class:`SurfSwarmHero`,
#: :class:`SurfSwarmAgentHero`, toggled in ``_show_mode`` the same way as
#: :class:`SurfPool4UserHero`), and adding either here would paint two heroes
#: into one row -- the exact defect enumerating instead of negating exists to
#: make loud rather than silent.
_SURF_HERO_MODES = (MODE_DASHBOARD, MODE_LAUNCHPAD, MODE_POOL4)

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

#: The POOL4 body's LEFT column: **THE SPLIT over THE RATCHET**.
#:
#: **It held POOL4 FLOW beneath those two until 2026-09-14**, when the owner
#: asked for the flow log gone from ``p`` because the ``4`` market body's
#: RECENT FLOW already renders the same rows. The column is now two
#: ``height: auto`` panels and **no ``1fr`` child at all**. That is a
#: decision, not an omission:
#:
#: * FLOW carried this column's ``1fr`` because it was the one panel here that
#:   scrolls inside itself -- a ``RichLog``, so shrinking it moved rows behind
#:   its own scrollbar rather than off the layout. Neither survivor can do
#:   that. A ``1fr`` on THE SPLIT or THE RATCHET would be a ``Static`` that
#:   loses rows with no scrollbar and no trace once the column is squeezed,
#:   which is the failure the ``1fr`` rules on this screen exist to prevent. A
#:   floor equal to today's content would hold today and silently cut the
#:   first line either panel grows -- and THE SPLIT is payload-sized (12 rows
#:   on Sepolia, 15 on mainnet).
#: * With both ``auto``, the column's spare rows are blank space at its foot:
#:   six at the 45-row pin on the worst payload, more on a taller terminal. A
#:   column shorter than its content scrolls instead, which ``_rail_is_cut``
#:   sees and ``‹ taller`` reports. Nothing here can be cut in silence at any
#:   height.
#: * Measured, not assumed: 36..50 rows on the worst payload, left content
#:   28, whole from 39, and no panel ever shorter than its own
#:   ``virtual_size``. ``test_the_pool4_floors_never_thin_a_panel_below_its_content``
#:   pins both panels at exactly their content.
#:
#: The column keeps ``overflow-y: auto`` and ``scrollbar-gutter: stable``:
#: THE SPLIT still grows with the payload, and without the gutter this body's
#: width pin would become a function of its height.
#:
#: The columns were split by **how tall each panel is** when mainnet landed,
#: and that balance -- 34 rows a side at the worst payload -- ended with FLOW.
#: This column now carries 28 against the rail's 34, so the rail alone sets
#: :data:`SURF_POOL4_FULL_LAYOUT_ROWS`, which is why that pin held at 45 while
#: :data:`SURF_POOL4_FULL_LAYOUT_COLUMNS` fell to 99. Moving a rail panel
#: across to spend the six spare rows was not attempted: rebalancing the body
#: is a layout decision this removal did not ask for.
#:
#: **This block has now been wrong twice and been rewritten a third time, and
#: all three are recorded rather than quietly overwritten**, because a ``#:``
#: block is the authority here *only* because it sits beside the code, and one
#: that drifts is worse than none. It read "THE SPLIT over POOL4 FLOW" until
#: the W3 follow-up, which was the pre-swap arrangement. It was then corrected
#: to "HATCHES over POOL4 FLOW", which the mainnet rebalance invalidated the
#: same day :data:`SURF_POOL4_FULL_LAYOUT_ROWS` recorded that rebalance three
#: hundred lines above. It read "THE SPLIT over THE RATCHET over POOL4 FLOW"
#: until the removal above -- the one change of the three made on purpose.
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
#: ``1fr`` claim above, which is guarded against ``minimal.tcss`` by
#: ``test_the_pool4_rail_has_one_floored_fr_and_the_left_column_none``
#: (``test_exactly_one_pool4_child_per_column_carries_the_fr`` until
#: 2026-09-14).
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
#: body's four panels none does (POOL4 FLOW did, until it left the body on
#: 2026-09-14 -- which is why the left column now has no ``1fr`` at all, see
#: :data:`POOL4_LEFT_ID`). VAULT's nine lines and blank are
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

#: The ``4`` POOL4 MARKET body's container id (2026-09-11) -- the fourth body,
#: on :data:`LAUNCHPAD_BODY_ID`'s contract: composed once, hidden by
#: ``display``, swapped in by ``_show_mode``. Exported for that constant's
#: reason: the id is queried from the test module, and retyping a literal in
#: two files is how one of them goes stale.
#:
#: **A ``Vertical`` of two rows, where the other two alternate bodies are a
#: single ``Horizontal``.** This body follows the *bakery* template (PRD §4) --
#: a leaderboard beside a chart-over-signals column, then an activity log
#: beside the EV table -- which is two rows, so the container that ``display``
#: toggles has to be their common parent rather than either row.
POOL4_USER_BODY_ID = "surf-pool4-user-body"

#: The market body's TOP row: **RECENT FLOW beside the rail**.
#:
#: ``#middle-row``'s opposite number in the fourth body, and named for it. It
#: carries a ``min-height`` for the reason every ``1fr`` here does: a ``1fr``
#: child cannot overflow a scroll container, it *shrinks*, so a row without a
#: floor sheds a line per terminal row until it is a pair of bare titles --
#: no scrollbar, no marker, no trace.
#:
#: **It held STAKERS until 2026-09-12.** The owner asked for the leaderboard
#: below the log rather than above it, and the two left-hand panels traded
#: rows; the rail did not move, which is why ``_SCROLL_COLUMNS`` still names
#: this row's rail and needs no edit for the swap. This row is also the one
#: place ``SurfPool4Flow``'s three per-instance keywords live now
#: (``quiet_mainnet``, ``quiet_as_of``, ``classes="market"``) -- they are set
#: on the instance, so they travelled with it and a move that dropped one
#: would have put MAINNET and a second clock back on this body in silence.
POOL4_USER_MIDDLE_ID = "surf-pool4-user-middle"

#: The market body's right rail: **BURN & SUPPLY over SIGNALS**.
#:
#: ``#surf-right-rail``'s opposite number in the fourth body. **SIGNALS
#: carries the rail's ``1fr`` and it is the panel with the fixed line count
#: on purpose** -- the same inversion ``sIMD VAULT`` makes in the ``p``
#: body's rail, and for the same reason: of these two panels neither scrolls
#: inside itself, so whichever takes the ``1fr`` must be one that can never
#: actually be cut. SIGNALS renders a title, four state rows and one summary
#: line and never more, so its ``min-height`` is both its floor and its
#: ceiling. BURN & SUPPLY is ``auto`` above it with the one-row bottom margin
#: ``SurfSignals`` and ``SurfCurveFlow`` carry in the other two rails, since
#: flush the two read as one block.
POOL4_USER_RAIL_ID = "surf-pool4-user-rail"

#: The market body's BOTTOM row: **STAKERS beside IF IMD FALLS**.
#:
#: ``#bottom-row``'s opposite number, and since 2026-09-12 the one row on this
#: screen whose seam is **not** a ratio. IF IMD FALLS is a fixed 45 columns --
#: its own caption's width and nothing more -- and STAKERS takes every
#: remaining column as ``1fr``. See
#: :data:`SURF_POOL4_USER_FULL_LAYOUT_COLUMNS` for why a ``fr`` was the wrong
#: instrument here (it would grow the ladder back past its old width on a wide
#: terminal, which is the opposite of what was asked) and for what the ladder
#: can and cannot give back.
#:
#: Its floor is the **only** one on this body that is not its tallest panel's
#: own content: 12 rather than the ladder's 9, bought deliberately so the
#: leaderboard that moved in here prints as many rows as it did in the top
#: row. :data:`SURF_POOL4_USER_FULL_LAYOUT_ROWS` records what that cost.
#:
#: ``SurfPool4Flow``, which this row used to hold, renders in the row above
#: and nowhere else. It was the one widget class mounted twice on this screen
#: -- here and in the ``p`` body, reused rather than copied (PRD §6.4) --
#: until 2026-09-14, when the owner removed the ``p`` body's copy as a
#: duplicate. The top row's seam is ``1fr:1fr``, so that panel still needs no
#: scoped width override: the one unscoped rule in both CSS copies is the
#: rule it wants there.
POOL4_USER_BOTTOM_ID = "surf-pool4-user-bottom"

#: The ``s`` SWARM body's container id (2026-09-16) -- the fifth body, on
#: :data:`LAUNCHPAD_BODY_ID`'s contract: composed once, hidden by ``display``,
#: swapped in by ``_show_mode``. Exported for that constant's reason: the id
#: is queried from the test module, and retyping a literal in two files is
#: how one of them goes stale.
#:
#: A ``Vertical`` of two ``Horizontal`` rows and one full-width panel since
#: swarm v2 (WP7, 2026-09-21): CAPABILITY beside THROUGHPUT on top, IN FLIGHT
#: beside LAUNCHES beneath, SITES alone across the bottom. The plan's §2 grid
#: (IN FLIGHT beside THROUGHPUT, CAPABILITY beside LAUNCHES) was measured and
#: does not fit under ``__main__.FULL_LAYOUT_COLUMNS``: CAPABILITY's and
#: LAUNCHES' *tight* tiers alone need 68 + 79 = 147 cells of one row, more
#: than a 143-column terminal has, so that pairing would hide table columns
#: at every admissible width. Pairing each table with the panel that plateaus
#: (THROUGHPUT at 46) or shrinks honestly (IN FLIGHT's objective column) is
#: what lets CAPABILITY reach ``full`` at the pin -- see
#: :data:`SURF_SWARM_FULL_LAYOUT_COLUMNS`. The 2026-09-16 2x2 grid (THE FIELD
#: beside QUEUE, JUST SHIPPED beside THROUGHPUT) went with those panels.
SWARM_BODY_ID = "surf-swarm-body"

#: The swarm body's top row: **CAPABILITY beside THROUGHPUT** (WP7). The row
#: scrolls (THROUGHPUT is ``height: auto`` with two open-ended blocks) and is
#: named in ``_SCROLL_COLUMNS[MODE_SWARM]``. Held THE FIELD beside QUEUE from
#: 2026-09-16 to WP7.
SWARM_TOP_ID = "surf-swarm-top"

#: The swarm body's bottom row: **IN FLIGHT beside LAUNCHES** (WP7). Both
#: children are ``1fr`` in height and floored at the row's own floor, so the
#: row itself cannot overflow and carries no scrollbar; SITES follows it in
#: the body directly, with no row container of its own. Held JUST SHIPPED
#: beside THROUGHPUT from 2026-09-16 to WP7.
SWARM_BOTTOM_ID = "surf-swarm-bottom"

#: The AGENT container: the seat-card and node-card rows (fixed height,
#: 2026-09-22, replacing SEAT | BY NODE) above a full-width RECORD, which
#: keeps its answer column visible at the body pin. The body alone scrolls.
AGENT_BODY_ID = "surf-agent-body"

#: The three swarm bodies' thirteen widgets, in ``SWARM_WIDGET_SIGNATURES``'s own
#: order. ``_do_refresh`` dispatches each one's contract keys by class name
#: off this tuple, so a widget the export names and this tuple does not
#: would never be painted -- ``tests/screens/test_surf_screen.py`` binds the
#: two by identity of their name sets (the one legitimate hand-typed copy:
#: the export cannot name classes without importing widgets into ``data/``).
_SWARM_PANELS = (
    SurfSwarmBoardHero,
    SurfSwarmLeaderboard,
    SurfSwarmFleet,
    SurfSwarmHero,
    SurfSwarmInFlight,
    SurfSwarmThroughput,
    SurfSwarmCapability,
    SurfSwarmLaunches,
    SurfSwarmSites,
    SurfSwarmAgentHero,
    SurfSwarmSeatCards,
    SurfSwarmNodeCards,
    SurfSwarmSeatRecord,
)


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


def _agent_title_head(data: dict) -> str:
    """``Identity.md AGENT #420``: the AGENT body's name for its selected seat.

    The owner asked for it on 2026-09-22 in place of the IMD price and parity,
    which the AGENT body does not show. The number is the IDMD token id of
    ``swarm_seat_selected``, validated as the hero's SEAT box validates it;
    anything else renders the em dash, never a guessed seat.
    """
    selected = data.get("swarm_seat_selected")
    token = seat_token(selected.get("token_id")) if isinstance(selected, dict) else None
    return f"Identity.md AGENT #{'—' if token is None else token}"


def _title_line(data: dict, row_hint: bool = False, agent: bool = False) -> str:
    """Compose the meta row (PRD §4).

    ``agent`` -- the AGENT body is showing -- swaps the IMD price and parity
    for :func:`_agent_title_head`, in green, and drops the degraded list
    (owner, 2026-09-22): its groups name the dashboard's other sources, and
    every AGENT panel shows its own unavailable state. The row hint and the
    LP warning are unchanged.

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
    if agent:
        # Built from an int token or the em dash only: nothing to escape.
        # ``ansi_green`` is the terminal's green, as RECORD's Rich ``green``
        # cells paint; Textual markup's bare ``green`` is CSS #008000.
        head = f"[ansi_green]{_agent_title_head(data)}[/]"
    else:
        head = (f"IMD {_fmt_usd(data.get('imd_price_usd'))} · "
                f"parity {_fmt_signed_pct(data.get('parity_pct'))}")
    line = f"SURFBOARD · {head} · as of {_fmt_hhmm(data.get('as_of'))}"

    if row_hint:
        line += f" · [yellow]{TALLER_HINT}[/]"

    if data.get("lp_owner_ok") is False:
        line += " · [yellow]⚠ LP owner changed[/]"

    if not agent:
        line += _fmt_degraded(data.get("degraded"))
    return line


class SurfScreen(DashboardScreen):
    """surfsurf.eth Surfboard dashboard.

    Lifecycle (constructor, resume, suspend) comes from
    :class:`~maxpane_dashboard.screens.dashboard_screen.DashboardScreen`; the
    five bodies mean the dispatch genuinely differs per view, so this screen
    keeps its own ``_do_refresh`` and declares no ``PANELS``.
    """

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
        # `e` for EXPERIMENTAL (2026-09-15): the owner took the POOL4 protocol
        # body out of the status hint and asked to keep it reachable under
        # `e`. It was `p` from 2026-09-01; `p` is unbound now. Comments across
        # this module still say "the `p` body" -- that is MODE_POOL4, the body
        # this key opens, and the internal names did not change with the key.
        Binding("e", "toggle_pool4", "Pool4 (experimental)", show=False),
        Binding("4", "toggle_pool4_user", "Pool4", show=False),
        # `s` for SWARM (2026-09-16): free on this screen and in the app,
        # verified rather than assumed -- see `action_toggle_swarm`.
        Binding("s", "toggle_swarm", "Swarm", show=False),
        # `a` for AGENT (swarm v2 plan A1, WP7): free on this screen and in
        # the app, verified rather than assumed -- see `action_toggle_agent`.
        Binding("a", "toggle_agent", "Agent", show=False),
        # `i` for IDENTITY (2026-09-21): the seat prompt -- THE LIST's `w`
        # shape, asking for an Identity.md NFT id instead of a wallet. Free
        # on this screen, in the app and in `DataTable`'s own bindings.
        Binding("i", "set_seat", "Seat", show=False),
        Binding("b", "toggle_board", "Board", show=False),
        Binding("o", "cycle_board_sort", "Sort column", show=False),
        Binding("O", "reverse_board_sort", "Reverse sort", show=False),
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
    #: **``· 4 market`` joined it on 2026-09-11**, inside that same single
    #: run and for both of those reasons again. It is the third and last
    #: segment this label can afford: measured off composited output at
    #: :data:`SURF_FULL_LAYOUT_COLUMNS` rather than counted, the whole phrase
    #: still reaches a pixel, and ``4 market`` is the half that shortens if a
    #: fourth ever has to fit -- ``l launchpad`` does not, because the
    #: app-level acceptance test greps for that contiguous string.
    #:
    #: **2026-09-15: two segments again, ``l launchpad · 4 pool4``.** The
    #: owner asked for ``p pool4`` gone from the bottom line and for ``4
    #: market`` to read ``4 pool4``. The protocol body is still reachable, under
    #: ``e`` for experimental, and is deliberately not advertised here. The
    #: ``4`` body keeps its internal names (``MODE_POOL4_USER``,
    #: ``SurfPool4UserHero``) and its docs name, POOL4 MARKET. The hint names
    #: the key, and ``pool4`` is what that key now opens on the bar. The run is
    #: still one markup run and still read back off composited output. It is
    #: eleven columns shorter than the three-part hint, so it fits wherever
    #: that one did.
    #:
    #: **``· s swarm`` joined it on 2026-09-16**, inside the same single run
    #: and for both of those reasons again -- curator's ``"c panels · y you ·
    #: f linked · l lists"`` shape, one more segment. ``s swarm`` is the half
    #: that shortens if a fourth ever has to fit, for ``4 market``'s own
    #: reason: ``l launchpad`` is the one the app-level acceptance test greps
    #: for as a contiguous string.
    #: §11: shortened by owner to keep the body as width binder; whole bar from 134.
    KEY_HINTS = "[dim]l launchpad · 4 pl4 · s swm · a agt · b brd[/]"

    #: The words the status bar shows for this dashboard.
    GAME_NAME = "surf"

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
     *
     * 2026-09-15: THE LEFT COLUMN HAS TWO GROWING CHILDREN NOW, AND THE ROWS
     * MOVED TO THE COINS. The owner asked for LAUNCHPAD COINS taller and
     * LAUNCHPAD ACTIVITY shorter, with a blank row between them. COINS is
     * `2fr` against ACTIVITY's `1fr`. COINS is floored at 13 (the ten rows it
     * always had at the pin) and capped at 23 (twenty coins plus title,
     * blank and header), so past that ceiling every row goes to ACTIVITY.
     * Its `margin: 0 0 1 0` is the blank row. The table stays `auto` and
     * `SurfLaunchpadCoins` draws only the coins that fit its laid-out height,
     * because a table that scrolls inside itself paints a scrollbar that
     * takes columns, and that was measured cutting the header at the width
     * pin. Both pins held; `SURF_LAUNCHPAD_FULL_LAYOUT_ROWS` has the sweep.
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
        height: 2fr;
        min-height: 13;
        max-height: 23;
        padding: 0 1;
        margin: 0 0 1 0;
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
     * It was chosen when a fitted `RichLog` (POOL4 FLOW, 53 screen columns)
     * bound the left column, which bought the rail three columns of margin
     * on a panel whose `‹ widen` is appended to a title. POOL4 FLOW left
     * this body on 2026-09-14 (the `4` body's RECENT FLOW shows the same
     * rows). The left column now needs THE RATCHET's 45 and the rail binds
     * at HATCHES' 50 with zero margin: 99 columns, re-swept, with HATCHES
     * still marking at every width below. The seam was not re-cut.
     * `SURF_POOL4_FULL_LAYOUT_COLUMNS` carries the re-sweep and the old
     * per-seam table.
     *
     * The `SurfPool4Flow` rule below gained `margin: 0 0 1 0` on 2026-09-15:
     * the blank row between RECENT FLOW's log and the STAKERS title in the
     * `4` body, taken out of the panel's own `1fr` height. Both of that
     * body's pins held (`SURF_POOL4_USER_FULL_LAYOUT_ROWS`).
     *
     * BOTH columns scroll and BOTH carry `scrollbar-gutter: stable`, for
     * `#surf-launchpad-left`/`#curator-right-rail`'s reason: a `Vertical`
     * defaults to `overflow: hidden hidden`, and without the reserved gutter
     * this layout's WIDTH requirement would become a function of its HEIGHT.
     *
     * ONE FLOORED `1fr` CHILD IN THE RAIL AND NONE ON THE LEFT, SINCE
     * 2026-09-14. A `1fr` child cannot overflow a scroll container, it
     * SHRINKS, so one given fewer rows than its content loses them with no
     * scrollbar and no trace UNLESS it scrolls inside itself. POOL4 FLOW did
     * (it is a `RichLog`), and it carried the left column's `1fr` at a floor
     * of 6 until the owner removed it from this body as a duplicate of the
     * `4` body's RECENT FLOW. Neither panel left in that column scrolls
     * inside itself, so THE SPLIT and THE RATCHET are both `auto` and the
     * column takes no `1fr` at all: its spare rows are blank at its foot,
     * and too few rows make the column scroll, which `‹ taller` reports.
     * The rail's `1fr` goes to sIMD VAULT, the panel there with a FIXED line
     * count: `min-height: 10` is both its floor and its ceiling, so it can
     * never be cut -- and since it took the repo-wide blank row under its
     * title it fills those ten EXACTLY, with nothing spare. HATCHES is `auto`
     * beside it, because its height answers to the producer (ten rows with no
     * levers, twenty at the ten emitted today, twenty-two at the widget's own
     * cap) and a floored `1fr` version of it would silently cut rows in the
     * narrow window where the column does not yet scroll. The `SurfPool4Flow`
     * rule below now styles only the `4` body's instance and its values did
     * not move. See `POOL4_LEFT_ID` and `SURF_POOL4_FULL_LAYOUT_ROWS`.
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
        margin: 0 0 1 0;
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

    /* The ``4`` POOL4 MARKET body (2026-09-11): the FOURTH body, and the
     * first one on the BAKERY template rather than on the `l` body's
     * structure -- a leaderboard beside a chart-over-signals column, then an
     * activity log beside the EV table (PRD section 4). That is two rows, so
     * the container `_show_mode` toggles is a `Vertical` holding both of
     * them rather than a single `Horizontal`. `margin: 1 0 0 0` matches
     * `#middle-row`'s, `#surf-launchpad-body`'s and `#surf-pool4-body`'s, so
     * moving between any two of the four bodies never also moves the hero's
     * breathing room.
     *
     * THE TOP ROW'S SEAM IS `1fr:1fr` AND THE REUSED PANEL IS THE REASON.
     * `SurfPool4Flow` is mounted in it a SECOND time (PRD section 6.4: reuse
     * the module, do not copy it), and the rule it already carries --
     * `width: 1fr; height: 1fr; min-height: 6` -- is exactly the rule it
     * wants there. A 7:6 seam would have needed a scoped width override, i.e.
     * a second place where that panel's geometry is stated, which is the
     * divergence reuse exists to avoid.
     *
     * THE BOTTOM ROW'S SEAM IS NOT A RATIO AT ALL, SINCE 2026-09-12. Both
     * rows were `1fr:1fr` and read as one grid until the owner asked, off the
     * live screen, for STAKERS below RECENT FLOW, for its addresses whole,
     * and for IF IMD FALLS narrower. The ladder is now a FIXED 45 columns --
     * `pool4u_depth.CAPTION` plus its padding, measured, not chosen -- and
     * STAKERS takes the rest as `1fr`. A ratio was measured and rejected: it
     * hands the ladder a SHARE of the terminal, so on a 169-column screen a
     * 73:45-shaped seam grows it to 65, wider than the 52 that prompted the
     * request. A fixed column gives every extra column to the leaderboard at
     * every width. The price is that the two rows' seams no longer line up --
     * 59 in the top row against 73 in the bottom at the pin -- which is the
     * visible consequence of asking for two differently-sized left panels and
     * is recorded here rather than smoothed over.
     *
     * EVERY `1fr` CHILD IS FLOORED AND EVERY SCROLLING `Vertical` RESERVES
     * ITS GUTTER. A `1fr` child cannot overflow a scroll container, it
     * SHRINKS -- so without `min-height` each of these sheds a line per
     * terminal row down to a bare title with no scrollbar and no trace,
     * which is what the floor under `SurfDevActivity` exists to stop next
     * door. And without `scrollbar-gutter: stable` the scrollbar takes its
     * column out of the panel beside it only on terminals short enough to
     * overflow, so the layout's WIDTH requirement would move with its
     * HEIGHT (`#curator-right-rail`'s reason, inherited through
     * `#surf-launchpad-left`).
     *
     * WHICH PANEL CARRIES THE RAIL'S `1fr` IS THE INVERTED CASE AGAIN.
     * Neither BURN & SUPPLY nor SIGNALS scrolls inside itself, so the `1fr`
     * goes to the one that can never be cut: SIGNALS renders a title, the
     * blank row under it and four state rows and never more, so
     * `min-height: 6` is both its floor and its ceiling. BURN & SUPPLY is
     * `auto` above it -- its sparkline row and its two text lines are
     * content, not slack -- with the one-row bottom margin `SurfSignals` and
     * `SurfCurveFlow` carry in the other two rails. Same answer, same
     * reasoning, as `SurfPool4Vault` one rule up.
     *
     * EVERY FLOOR IN THIS BLOCK CAME DOWN ONE ROW ON 2026-09-12 when the
     * five panels lost their per-panel `as of` markers (`_pool4`'s *One
     * clock on the `4` body*). SIGNALS 7 -> 6 and BURN 6 -> 5 took the rail
     * 14 -> 12 and the middle row with it; the ladder's 10 -> 9 took
     * `#surf-pool4-user-bottom` down the same amount.
     *
     * ...AND `#surf-pool4-user-bottom` WENT BACK UP, 9 -> 12, LATER THE SAME
     * DAY, WHICH IS THE ONE FLOOR HERE THAT IS NOT A PANEL'S OWN CONTENT.
     * STAKERS moved into that row and a leaderboard in a nine-row slot prints
     * FIVE entries where it printed nine upstairs. 12 is the top row's floor,
     * so the two `1fr` rows now have the same floor as well as the same
     * growth, and the leaderboard prints as many rows as it ever did at every
     * height. `SurfPool4UStakers`'s own floor went 11 -> 12 with it, because a
     * child floored ABOVE its row is a child the row cannot hold. What the
     * three rows cost is in `SURF_POOL4_USER_FULL_LAYOUT_ROWS`, declared
     * rather than absorbed. Every other floor is still each panel's own
     * content height, which is what makes the screen-wide `‹ taller` honest
     * for free -- see that constant for why the property, and not the marker,
     * is what the pin is swept against.
     */
    SurfScreen #surf-pool4-user-body {
        height: 1fr;
        width: 100%;
        margin: 1 0 0 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen #surf-pool4-user-middle {
        height: 1fr;
        min-height: 12;
    }
    SurfScreen SurfPool4UStakers {
        width: 1fr;
        height: 1fr;
        min-height: 12;
        padding: 0 1;
    }
    SurfScreen #surf-pool4-user-rail {
        width: 1fr;
        height: 1fr;
        min-height: 12;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen SurfPool4UBurn {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    SurfScreen SurfPool4USignals {
        width: 1fr;
        height: 1fr;
        min-height: 6;
        padding: 0 1;
    }
    SurfScreen #surf-pool4-user-bottom {
        height: 1fr;
        min-height: 12;
        margin: 0 0 1 0;
    }
    SurfScreen SurfPool4UDepth {
        width: 45;
        height: 1fr;
        min-height: 9;
        padding: 0 1;
    }

    /* The ``s`` SWARM body and the ``a`` AGENT body (swarm v2, WP7,
     * 2026-09-21). This copy is the fallback; ``themes/minimal.tcss``
     * carries the copy that actually renders (an app stylesheet outranks a
     * screen's ``DEFAULT_CSS``) **and the reasoning** -- the grid, why it is
     * not the plan's §2 pairing, why no ``1fr`` child carries a
     * ``min-width``, the ``4fr : 5fr`` seam, and which container scrolls.
     * ``tests/screens/test_surf_screen.py`` pins the two copies together
     * property by property. Edit both or neither. */
    SurfScreen SurfSwarmHero {
        height: 6;
    }
    SurfScreen SurfSwarmHero > SurfSwarmHeroBox {
        width: 1fr;
        height: 6;
        padding: 0 1;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfScreen SurfSwarmAgentHero {
        height: 7;
        padding: 0 1 0 0;
    }
    SurfScreen SurfSwarmAgentHero > SurfSwarmAgentHeroBox {
        width: 1fr;
        height: 7;
        padding: 0 1;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center top;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    /* One column grid for the three AGENT card rows (owner, 2026-09-22):
     * column i has the same weight in every row, so the rows' borders line up
     * at any width. Each weight is that column's widest measured card
     * (border and padding included) on the AGENT sweep payloads; with
     * weight = need, every card is whole once the row has their sum. */
    SurfScreen #surf-swarm-agent-seat { width: 23fr; }
    SurfScreen #surf-swarm-card-owner { width: 23fr; }
    SurfScreen #surf-swarm-card-roles { width: 23fr; }
    SurfScreen #surf-swarm-agent-accepted { width: 23fr; }
    SurfScreen #surf-swarm-card-runtime { width: 23fr; }
    SurfScreen #surf-swarm-card-node0 { width: 23fr; }
    SurfScreen #surf-swarm-agent-win-rate { width: 20fr; }
    SurfScreen #surf-swarm-card-score { width: 20fr; }
    SurfScreen #surf-swarm-card-node1 { width: 20fr; }
    SurfScreen #surf-swarm-agent-reviewed { width: 19fr; }
    SurfScreen #surf-swarm-card-feedback { width: 19fr; }
    SurfScreen #surf-swarm-card-node2 { width: 19fr; }
    SurfScreen #surf-swarm-agent-rank { width: 18fr; }
    SurfScreen #surf-swarm-card-collab { width: 18fr; }
    SurfScreen #surf-swarm-card-others { width: 18fr; }
    SurfScreen #surf-swarm-agent-status { width: 28fr; }
    SurfScreen #surf-swarm-card-board { width: 28fr; }
    SurfScreen #surf-swarm-card-teammates { width: 28fr; }

    SurfScreen #surf-swarm-body {
        height: 1fr;
        width: 100%;
        padding: 0 0;
        margin: 1 0 0 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen #surf-swarm-top {
        height: 1fr;
        min-height: 16;
        padding: 0 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen SurfSwarmCapability {
        width: 1fr;
        max-width: 118;
        height: 1fr;
        min-height: 8;
        padding: 0 1;
    }
    SurfScreen SurfSwarmThroughput {
        width: 1fr;
        max-width: 46;
        height: auto;
        padding: 0 1;
    }
    SurfScreen #surf-swarm-bottom {
        height: 1fr;
        min-height: 8;
        padding: 0 0;
    }
    SurfScreen SurfSwarmInFlight {
        width: 4fr;
        height: 1fr;
        min-height: 8;
        padding: 0 1;
    }
    SurfScreen SurfSwarmLaunches {
        width: 5fr;
        height: 1fr;
        min-height: 8;
        padding: 0 1;
    }
    SurfScreen SurfSwarmSites {
        width: 100%;
        height: 1fr;
        min-height: 8;
        padding: 0 1;
    }
    SurfScreen #surf-agent-body {
        height: 1fr;
        width: 100%;
        padding: 0 0;
        margin: 0 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfScreen SurfSwarmAgentCards {
        height: 7;
        margin: 1 0 0 0;
    }
    SurfScreen SurfSwarmAgentCards > SurfSwarmAgentCard {
        width: 1fr;
        height: 7;
        padding: 0 1;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center top;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfScreen SurfSwarmSeatRecord {
        width: 100%;
        height: 1fr;
        min-height: 6;
        padding: 0 1;
        margin: 1 0 0 0;
    }

    SurfSwarmBoardHero {
        height: 7;
    }
    SurfSwarmBoardHero > SurfSwarmBoardHeroBox {
        width: 1fr;
        height: 7;
        padding: 0 1;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center top;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfScreen #surf-board-body {
        height: 1fr;
        margin: 1 0 0 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-gutter: stable;
    }
    SurfSwarmLeaderboard {
        width: 1fr;
        height: 1fr;
        min-height: 8;
    }
    SurfSwarmFleet {
        width: 37;
        max-width: 37;
        height: auto;
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
        super().__init__(data_manager, poll_interval, name=name, **kwargs)
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

        # Shared hero row, exactly one hero showing (curator's
        # per-mode hero pattern). `#hero-row` itself is never hidden -- a
        # hero is on screen in every mode, as it always was -- but which one
        # is a function of `self._mode`, and `_show_mode` derives both
        # visibilities from the same comparison every other body does.
        #
        # The `surf-hero` class is what makes "exactly one hero shows" an
        # assertion a test can write without naming either class, so a fifth
        # body's hero is covered on the day it is composed rather than on the
        # day somebody remembers to add it to a list.
        with Horizontal(id="hero-row"):
            yield SurfHero(classes="surf-hero")
            yield SurfPool4UserHero(classes="surf-hero")
            yield SurfSwarmHero(classes="surf-hero")
            yield SurfSwarmAgentHero(classes="surf-hero")
            yield SurfSwarmBoardHero(classes="surf-hero")

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
            # way round. (Reversed in part on 2026-09-15: COINS is the `2fr`
            # share up to twenty coins and ACTIVITY the `1fr`, at the owner's
            # request -- see `SURF_LAUNCHPAD_FULL_LAYOUT_ROWS`.)
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
        # THE COLUMNS WERE SPLIT TO BALANCE THEIR HEIGHTS, NOT BY WHAT THE
        # PANELS ARE ABOUT, and since 2026-09-14 they no longer balance. At
        # the worst payload the rail carries 34 rows (HATCHES 23 + VAULT's
        # floor 10 + one margin) and IS the height pin. The left column
        # carried 34 too until POOL4 FLOW left this body (the owner: the `4`
        # body's RECENT FLOW already shows the same rows). It now carries 28,
        # SPLIT 15 + RATCHET 11 + two margins, so the pin held at 45. The
        # pre-mainnet arrangement (HATCHES here, SPLIT/RATCHET/VAULT in the
        # rail) put 38 rows in the rail against 20 here and needed 49.
        #
        # The rail's `1fr` goes to VAULT, whose ten lines are a constant, so
        # `min-height: 10` is floor and ceiling both; the one thing that must
        # NOT take it is HATCHES, whose height answers to the lever list,
        # because a shrunken `Static` loses rows with no scrollbar and no
        # trace. The left column has NO `1fr` now: FLOW carried it because a
        # `RichLog` scrolls inside itself, and neither panel left here does.
        # Its spare rows are blank at the column's foot -- see
        # `POOL4_LEFT_ID`.
        #
        # Measured against the alternative rather than asserted: see
        # `SURF_POOL4_FULL_LAYOUT_ROWS`, which records the arrangement this
        # replaced and what it cost.
        #
        # This comment described the pre-swap arrangement until the W3
        # follow-up, the pre-mainnet one until the rebalance, and a three-panel
        # left column until 2026-09-14; the lines directly beneath it are the
        # authority.
        with Horizontal(id=POOL4_BODY_ID):
            with Vertical(id=POOL4_LEFT_ID):
                yield SurfPool4Split()
                yield SurfPool4Ratchet()
            with Vertical(id=POOL4_RAIL_ID):
                yield SurfPool4Hatches()
                yield SurfPool4Vault()

        # The `4` POOL4 MARKET view (2026-09-11): the fourth body, composed
        # once and hidden by `display` exactly like the two above it, so the
        # first `4` paints a complete frame rather than a blank one. Unlike
        # them it is a `Vertical` of two rows, because it follows the BAKERY
        # template (PRD section 4) rather than the `l` body's shape.
        #
        # `SurfPool4Flow` below is this screen's ONLY instance of the class
        # since 2026-09-14. It was the `p` body's panel mounted a second time
        # (PRD section 6.4: a second instance, never a second module) until
        # the owner removed the `p` body's copy as a duplicate of this one.
        # `_do_refresh` still dispatches it with `self.query(SurfPool4Flow)`,
        # so a second mount would be handed the same rows without an edit.
        with Vertical(id=POOL4_USER_BODY_ID):
            with Horizontal(id=POOL4_USER_MIDDLE_ID):
                # The `p` body mounts this same class untouched, two blocks
                # up. Only this instance leaves MAINNET unsaid and only this
                # one drops the `as of` note -- see the widget's __init__ for
                # why each opt-in is its own per-instance keyword and set
                # here rather than module-wide. The three keywords travelled
                # with the panel when it moved rows on 2026-09-12: they are
                # per-INSTANCE, so a move that dropped one would have put
                # MAINNET and a second clock back on this body silently.
                yield SurfPool4Flow(
                    quiet_mainnet=True, quiet_as_of=True, classes="market"
                )
                with Vertical(id=POOL4_USER_RAIL_ID):
                    yield SurfPool4UBurn()
                    yield SurfPool4USignals()
            with Horizontal(id=POOL4_USER_BOTTOM_ID):
                yield SurfPool4UStakers()
                yield SurfPool4UDepth()

        # The `s` SWARM body (swarm v2, WP7): a `Vertical` of two `Horizontal`
        # rows and one full-width table -- see `SWARM_BODY_ID` for why this is
        # not the plan's §2 pairing. Composed once and hidden, like every
        # other alternate body.
        with Vertical(id=SWARM_BODY_ID):
            with Horizontal(id=SWARM_TOP_ID):
                yield SurfSwarmCapability()
                yield SurfSwarmThroughput()
            with Horizontal(id=SWARM_BOTTOM_ID):
                yield SurfSwarmInFlight()
                yield SurfSwarmLaunches()
            yield SurfSwarmSites()

        # The `a` AGENT body: two card rows above a full-width RECORD -- see
        # `AGENT_BODY_ID`.
        with Vertical(id=AGENT_BODY_ID):
            yield SurfSwarmSeatCards()
            yield SurfSwarmNodeCards()
            yield SurfSwarmSeatRecord()

        with Horizontal(id=BOARD_BODY_ID):
            yield SurfSwarmLeaderboard()
            yield SurfSwarmFleet()

        yield StatusBar()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._show_mode()

    def _prime_status_bar(self, bar: StatusBar) -> None:
        """The one extra line this screen primes: the body keys.

        No ``set_active_view``: no slot on this screen has two views, so a
        ``view:`` word on the shared bar would name something that does not
        exist.
        """
        bar.set_key_hints(self.KEY_HINTS)

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
        """Apply ``self._mode`` to every body and hero's visibility.

        **Curator's ``y``/``f`` shape, hero swap included since 2026-09-11.**
        This docstring said the opposite until then: *"curator mounts a second
        hero per mode and toggles which one shows, but this screen has exactly
        one hero and it is not part of any body ... this method never touches
        its ``display``, so it is on in every mode."* Every clause of that was
        true when it was written and the ``4`` body made all of it false in one
        commit -- ``#hero-row`` now holds ``SurfHero`` **and**
        ``SurfPool4UserHero``, and the line below toggles both. The sentence is
        replaced rather than annotated because a docstring asserting the
        opposite of its own method is what the next reader trusts instead of
        reading the code.

        What is *still* true, and is the invariant worth stating: ``#hero-row``
        itself is never hidden, so a hero is on screen in every mode. Only
        *which* hero moved. PRD §3 argues the break -- on the market body
        surf's LAUNCHPAD/FLOW/BURN/SUPPLY figures would be the clearest thing
        on screen that a reader does not act on.

        **A five-way now, and still written as ONE derivation so it cannot
        become a four-way plus an exception.** The obvious edit when the third
        body arrived was to keep ``launchpad = self._mode == MODE_LAUNCHPAD``
        and add a second boolean beside it; the dashboard rows would then
        have read ``not launchpad``, which is *true* in MODE_POOL4, and the
        pool4 body would have painted on top of a dashboard body that was
        still showing. The fourth and fifth bodies offer the same edit one
        size larger each time, and the heroes offer a new one: a
        ``self._pool4_user_hero_shown`` flag, or a ``hero.display = not
        body.display``, would each be a second source of truth for the same
        fact. Every visibility here -- ten of them now (seven bodies plus
        three heroes), ``SurfSwarmHero`` joining ``SurfPool4UserHero`` as the
        second hero swapped with its own body -- is ``self._mode == <one mode
        word>`` and nothing else, which makes the modes exclusive by
        construction rather than by care.
        """
        try:
            self.query_one("#middle-row").display = self._mode == MODE_DASHBOARD
            self.query_one("#separator").display = self._mode == MODE_DASHBOARD
            self.query_one("#bottom-row").display = self._mode == MODE_DASHBOARD
            self.query_one(f"#{LAUNCHPAD_BODY_ID}").display = (
                self._mode == MODE_LAUNCHPAD
            )
            self.query_one(f"#{POOL4_BODY_ID}").display = self._mode == MODE_POOL4
            self.query_one(f"#{POOL4_USER_BODY_ID}").display = (
                self._mode == MODE_POOL4_USER
            )
            self.query_one(f"#{SWARM_BODY_ID}").display = self._mode == MODE_SWARM
            self.query_one(f"#{AGENT_BODY_ID}").display = self._mode == MODE_AGENT
            self.query_one(f"#{BOARD_BODY_ID}").display = self._mode == MODE_BOARD
            # The heroes, each answering to ``self._mode`` and never to the
            # other. ``SurfHero.display = not market_hero`` is available and
            # is the ``not launchpad`` defect one layer out: it would show
            # the wrong hero on a new body rather than no hero, and a wrong
            # hero is the one of those two a reader cannot see is wrong.
            self.query_one(SurfPool4UserHero).display = (
                self._mode == MODE_POOL4_USER
            )
            self.query_one(SurfSwarmHero).display = self._mode == MODE_SWARM
            self.query_one(SurfSwarmAgentHero).display = self._mode == MODE_AGENT
            self.query_one(SurfSwarmBoardHero).display = self._mode == MODE_BOARD
            self.query_one(SurfHero).display = self._mode in _SURF_HERO_MODES
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
        """``e`` -- swap the dashboard body for the POOL4 panels (experimental).

        Bound to ``p`` from 2026-09-01 until 2026-09-15, when the owner took
        it off the status hint and moved it to ``e``. It is not advertised on
        the bar.

        Idempotent on ``action_toggle_launchpad``'s contract: a second ``e``
        returns to the dashboard rather than doing nothing, so the key is
        also its own way back. Pressing ``e`` from MODE_LAUNCHPAD switches
        bodies directly -- there is no need to ``escape`` out of one view
        before entering the other, and requiring it would be the only place
        on this screen where a view key did nothing.
        """
        if self._mode == MODE_POOL4:
            self.action_show_dashboard()
            return
        self._mode = MODE_POOL4
        self._show_mode()

    def action_toggle_pool4_user(self) -> None:
        """``4`` -- swap the dashboard body for the POOL4 MARKET panels.

        Idempotent on ``action_toggle_launchpad``'s contract: a second ``4``
        returns to the dashboard rather than doing nothing, so the key is
        also its own way back. Pressing ``4`` from any other body switches
        directly, for ``action_toggle_pool4``'s reason -- requiring an
        ``escape`` first would be the only place on this screen where a view
        key did nothing.

        A digit key, and verified free rather than assumed: this screen binds
        ``r``/``l``/``e``/``escape`` (``p`` until 2026-09-15) and the app binds
        ``q``/``t``/``tab``/``m``.
        Digits are an established per-screen pattern here (curator's filter
        presets, ``frenpet_full``'s sub-views) and neither of those is
        app-level, so neither collides. ``4`` reads off the protocol's own
        name where ``u`` or ``i`` would have read as the protocol body's key
        (``p`` when this was written, ``e`` since 2026-09-15).
        """
        if self._mode == MODE_POOL4_USER:
            self.action_show_dashboard()
            return
        self._mode = MODE_POOL4_USER
        self._show_mode()

    def action_toggle_swarm(self) -> None:
        """``s`` -- swap the dashboard body for the swarm panels.

        Idempotent like ``4``: a second ``s`` returns to the dashboard.  ``s``
        was free on this screen (``r``/``l``/``e``/``4``/``escape``) and in the
        app (``q``/``t``/``tab``/``m``) -- verified, not assumed.
        """
        if self._mode == MODE_SWARM:
            self.action_show_dashboard()
            return
        self._mode = MODE_SWARM
        self._show_mode()

    def action_toggle_agent(self) -> None:
        """``a`` -- swap the dashboard body for one seat's AGENT panels.

        Idempotent like ``s``: a second ``a`` returns to the dashboard. ``a``
        was free on this screen (``r``/``l``/``e``/``4``/``s``/``escape``)
        and in the app (``q``/``t``/``tab``/``m``) -- verified, not assumed;
        ``DataTable``'s own bindings (arrows, page keys, ``enter``) do not
        include it either.
        """
        if self._mode == MODE_AGENT:
            self.action_show_dashboard()
            return
        self._mode = MODE_AGENT
        self._show_mode()

    def action_toggle_board(self) -> None:
        if self._mode == MODE_BOARD:
            self.action_show_dashboard()
            return
        self._mode = MODE_BOARD
        self._show_mode()
        self.query_one(SurfSwarmLeaderboard).query_one(DataTable).focus()

    def action_cycle_board_sort(self) -> None:
        if self._mode == MODE_BOARD:
            self.query_one(SurfSwarmLeaderboard).cycle_sort()

    def action_reverse_board_sort(self) -> None:
        if self._mode == MODE_BOARD:
            self.query_one(SurfSwarmLeaderboard).reverse_sort()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._mode != MODE_BOARD or event.data_table.id != SurfSwarmLeaderboard.TABLE_ID:
            return
        value = self.query_one(SurfSwarmLeaderboard).token_for_row(event.row_key)
        token = parse_seat(str(value)) if value is not None else None
        if token is None:
            return
        event.stop()
        config.save_seat(token)
        self._seat_entered(token)

    def action_set_seat(self) -> None:
        """``i`` -- prompt for the seat the AGENT body is about.

        ``SeatInputScreen`` validates the number and persists it to
        ``~/.maxpane/config.toml``, so the next launch opens on it too
        (``__main__`` reads it into ``SurfManager(seat=)``).
        """
        self.app.push_screen(SeatInputScreen(), callback=self._seat_entered)

    def _seat_entered(self, token: int | None) -> None:
        """Callback from ``SeatInputScreen``: ``None`` means escape.

        The manager's ``set_seat`` is an attribute write -- the rule for a
        message handler -- and the refresh after it refolds the seat keys off
        the cached sweep. The reader asked about a seat, so they land on the
        body that is about one. No seam (a test double) still lands there.
        """
        if token is None:
            return
        set_seat = getattr(self._data_manager, "set_seat", None)
        if set_seat is not None:
            set_seat(token)
        self._mode = MODE_AGENT
        self._show_mode()
        self.start_refresh()

    def action_show_dashboard(self) -> None:
        """``escape`` -- one-way back out of **any** alternate body."""
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
        # The market body scrolls at TWO levels and both are asked: the body
        # itself is the `Vertical` holding its two rows (the row that goes
        # off the bottom is a whole row, not a panel), and the rail scrolls
        # inside the top row. Naming only the rail would light the marker for
        # a cut SIGNALS panel and leave it dark for a cut bottom row, which
        # is the larger loss of the two.
        #
        # **Unchanged by the 2026-09-12 row swap, and that was checked rather
        # than assumed.** STAKERS and RECENT FLOW traded rows; the rail did
        # not move and neither did the body, so both selectors still name the
        # containers that actually scroll. The panels that swapped are the two
        # on this body that scroll INSIDE themselves, which no entry here has
        # ever been able to see -- see `SURF_POOL4_USER_FULL_LAYOUT_ROWS` on
        # why the cure for that is a floor and not a selector.
        MODE_POOL4_USER: (
            f"#{POOL4_USER_BODY_ID}", f"#{POOL4_USER_RAIL_ID}",
        ),
        # The swarm body, on `MODE_POOL4_USER`'s own shape: all THREE of
        # `#surf-swarm-body`, `#surf-swarm-top` and `#surf-swarm-bottom` are
        # asked, the same way `MODE_POOL4_USER` asks its own body id
        # alongside its rail.
        #
        # **`#surf-swarm-body` was missing here through Task 12's first
        # pass, and that was a real gap, not a style choice** (fix round 1).
        # `#surf-swarm-body` is a `Vertical` of two rows, and JUST SHIPPED's
        # own `DataTable` can be squeezed by the body's own flex allocation
        # without either row container ever needing to scroll: a light top
        # row (little FIELD/QUEUE content) and a large JUST SHIPPED table
        # reproduced a genuine one-row-wide window at height 25 --
        # `#surf-swarm-body.show_vertical_scrollbar` true, rows actually
        # lost off JUST SHIPPED's table, `‹ taller` dark -- with 24 and 26
        # either side both correctly lighting it. That is the `p` body's own
        # F6 shape (a table scrolling where no named container sees it), one
        # container over, and it is closed the way `MODE_POOL4_USER` already
        # was built to close it: by asking the body itself, not by raising a
        # floor. A floor would only have moved the window to a different
        # content mix; asking the body makes the marker aware of every mix.
        # `test_the_body_only_scrollbar_case_now_lights_the_marker` and
        # `test_no_height_loses_a_row_of_this_body_in_silence`
        # (`tests/screens/test_surf_swarm_layout.py`) are the reproduction
        # and the property, both red before this line and green after.
        #
        # `#surf-swarm-top` and `#surf-swarm-bottom` replace the launch-day
        # `#surf-swarm-left`/`#surf-swarm-rail` pair on the 2026-09-16 layout
        # change to a 2x2 grid: QUEUE and THROUGHPUT no longer share a
        # column, so there is no separately-scrolling rail nested a level
        # deeper any more -- each row is now the only container besides the
        # body itself that can overflow, so each row is asked directly.
        #
        # **Swarm v2 (WP7):** the body and its top row. The bottom row holds
        # two ``1fr`` panels floored at the row's own floor, so it cannot
        # overflow and shows no scrollbar (its region is compared against
        # its children's in the layout test instead); SITES sits in the body
        # directly. Asking a container that cannot scroll is harmless, but
        # naming only the ones that can is what keeps this map a statement.
        MODE_SWARM: (f"#{SWARM_BODY_ID}", f"#{SWARM_TOP_ID}"),
        # The AGENT body: its card rows are fixed-height, so the body is the
        # only container on it that can scroll.
        MODE_AGENT: (f"#{AGENT_BODY_ID}",),
        MODE_BOARD: (f"#{BOARD_BODY_ID}",),
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
            line = _title_line(self._title_data, row_hint=cut, agent=self._mode == MODE_AGENT)
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

    async def action_open_oracle_answer(self, job_id: str, submission_hash: str) -> None:
        if not valid_identity(job_id, submission_hash):
            return
        row = next((row for row in getattr(self, '_oracle_answer_rows', ())
                    if row.get('job_id') == job_id and row.get('submission_hash') == submission_hash
                    and joined(row)), None)
        if row is None:
            post_status_message(self.app, 'answer no longer listed')
            return
        await self.app.push_screen(OracleAnswerScreen(row))

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
                feed_signal_tx_hashes=data.get("feed_signal_tx_hashes"),
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
        # (`surf_manager._pool4_payload`), shared by every pool4 panel and
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

        # RECENT FLOW is mounted ONCE, in the `4` body's top row. It was
        # mounted twice (PRD section 6.4: reuse the module, never copy it)
        # until 2026-09-14, when the owner removed the `p` body's copy as a
        # duplicate of this one. The loop stays `query`, not `query_one`:
        # with one instance it costs nothing, and a second mount tomorrow is
        # fed the same rows without this block being touched. (This comment
        # used to say `query_one` would raise `TooManyMatches` -- it does
        # not in this Textual version, it returns the first match silently;
        # see CLAUDE.md and followups F8.)
        try:
            for _flow in self.query(SurfPool4Flow):
                _flow.update_data(
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

        # POOL4 MARKET body (`4` view, 2026-09-11) -- the same contract as
        # the two bodies above and for the same reason: dispatched on EVERY
        # refresh, whether or not `4` is showing it, so the first keypress
        # paints a complete frame. Each panel in its own `try` so one bad
        # panel cannot blank the others. RECENT FLOW is not here -- it is
        # dispatched with the `p` body's copy, in one statement, above.
        #
        # Every kwarg is the contract key verbatim, `pool4_as_of_hhmm` and
        # `pool4_stakers_as_of_hhmm` included, on the `p` body's decision and
        # for its reason: `_PREFIXED_KWARG_ALIASES` maps ONE kwarg name onto
        # ONE contract key, and a body eliding either clock to `as_of_hhmm`
        # would make one name stand for three different keys.
        #
        # TWO clocks reach this body and they are not interchangeable.
        # `pool4_as_of_hhmm` is the 600 s pool4 sweep's; STAKERS carries
        # `pool4_stakers_as_of_hhmm`, the long `Transfer`-fold tier's own and
        # much slower one, which advances only when a new fold lands. The
        # hero takes NEITHER (contract C4): a hero has no room for a clock
        # and the title bar carries the fast tier's.
        try:
            self.query_one(SurfPool4UserHero).update_data(
                pool4_price_usd=data.get("pool4_price_usd"),
                pool4_venue_gap_pct=data.get("pool4_venue_gap_pct"),
                pool4_cheaper_venue=data.get("pool4_cheaper_venue"),
                pool4_backstop_state=data.get("pool4_backstop_state"),
                pool4_backstop_eth=data.get("pool4_backstop_eth"),
                pool4_backstop_lower_tick=data.get("pool4_backstop_lower_tick"),
                pool4_current_tick=data.get("pool4_current_tick"),
                pool4_trailing_return_pct=data.get("pool4_trailing_return_pct"),
                pool4_vault_assets=data.get("pool4_vault_assets"),
                pool4_staker_count=data.get("pool4_staker_count"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4UserHero: %s", exc)

        try:
            self.query_one(SurfPool4UStakers).update_data(
                pool4_stakers=data.get("pool4_stakers"),
                pool4_staker_count=data.get("pool4_staker_count"),
                pool4_staker_top3_pct=data.get("pool4_staker_top3_pct"),
                # The long tier's own marker, NOT `pool4_as_of_hhmm`: this
                # panel's rows can be half a day older than the five beside
                # it, and a fast clock over slow data is a stale number
                # presented as live.
                pool4_stakers_as_of_hhmm=data.get("pool4_stakers_as_of_hhmm"),
                # Why the panel has no rows, when it has none. All four keys
                # above come from one slot and are `None` together, so this
                # is the only thing that separates "the fold has not landed
                # yet" -- the ordinary state of tick 1, because the sweep is
                # detached -- from "the sweep failed". Only the second may
                # render a warning.
                pool4_stakers_state=data.get("pool4_stakers_state"),
                pool4_network=data.get("pool4_network"),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4UStakers: %s", exc)

        try:
            self.query_one(SurfPool4UBurn).update_data(
                # Shared with RECENT FLOW, which renders the same rows as a
                # log. Reuse of a KEY, not of a widget: two questions off one
                # read, where folding a second copy into the payload would
                # cost a sweep and buy nothing.
                pool4_flow=data.get("pool4_flow"),
                pool4_total_burned=data.get("pool4_total_burned"),
                pool4_burned_supply_pct=data.get("pool4_burned_supply_pct"),
                pool4_total_supply=data.get("pool4_total_supply"),
                pool4_network=data.get("pool4_network"),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4UBurn: %s", exc)

        try:
            self.query_one(SurfPool4USignals).update_data(
                pool4_cap_headroom=data.get("pool4_cap_headroom"),
                pool4_cheaper_venue=data.get("pool4_cheaper_venue"),
                pool4_venue_gap_pct=data.get("pool4_venue_gap_pct"),
                # ⚠ `pool4_reference_pool_tick`, NOT `pool4_ref_tick`. The
                # second one is THE RATCHET's: the hook's own block-lagged
                # anti-manipulation tick, a different number for a different
                # job. `data.get` would hand either one over without a word.
                pool4_reference_pool_tick=data.get("pool4_reference_pool_tick"),
                pool4_current_tick=data.get("pool4_current_tick"),
                pool4_backstop_state=data.get("pool4_backstop_state"),
                pool4_backstop_lower_tick=data.get("pool4_backstop_lower_tick"),
                pool4_backstop_eth=data.get("pool4_backstop_eth"),
                pool4_backlog_days=data.get("pool4_backlog_days"),
                pool4_network=data.get("pool4_network"),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4USignals: %s", exc)

        try:
            self.query_one(SurfPool4UDepth).update_data(
                pool4_current_tick=data.get("pool4_current_tick"),
                pool4_position_liquidity=data.get("pool4_position_liquidity"),
                pool4_backstop_lower_tick=data.get("pool4_backstop_lower_tick"),
                pool4_backstop_liquidity=data.get("pool4_backstop_liquidity"),
                # WP11, 2026-09-11. The ladder's fifth input, and the only one
                # that is not a number: `analytics/surf_pool4_depth.depth_rows`
                # used to derive the band's existence from its own numbers, so
                # an UNREAD band and an UNDEPLOYED one both painted
                # `band used 0.0%`. `pool4_backstop_state` is the key that
                # carries the distinction and it has to be dispatched for the
                # panel to be able to make it. It already reaches
                # `SurfPool4USignals` and `SurfPool4UserHero`; this is the
                # third and last panel on this body that branches on it.
                pool4_backstop_state=data.get("pool4_backstop_state"),
                pool4_network=data.get("pool4_network"),
                pool4_as_of_hhmm=data.get("pool4_as_of_hhmm"),
            )
        except Exception as exc:
            logger.debug("Failed to update SurfPool4UDepth: %s", exc)

        # The `s` SWARM body's six widgets and the `a` AGENT body's five
        # (swarm v2, WP7): dispatched every refresh, whether or not either
        # body is showing, so the first keypress paints a complete frame.
        # One loop over the frozen contract -- every kwarg is a key
        # `SWARM_WIDGET_SIGNATURES` names for that class, verbatim -- and
        # each panel in its own `try`, so one bad panel cannot blank the
        # others. The per-panel marker choices (`swarm_as_of_hhmm` for the
        # live tier's panels, `swarm_scores_as_of_hhmm` for the sweep's,
        # `swarm_seat_as_of_hhmm` for the seat's) are the export's, made once
        # in `data/surf_models.py` rather than re-argued here.
        for cls in _SWARM_PANELS:
            try:
                keys = SWARM_WIDGET_SIGNATURES[cls.__name__]
                self.query_one(cls).update_data(**{k: data.get(k) for k in keys})
                if cls is SurfSwarmSeatRecord:
                    rows = data.get('swarm_seat_work_rows')
                    self._oracle_answer_rows = deepcopy(rows) if isinstance(rows, list) and data.get('swarm_seat_state') == 'ok' else []
            except Exception as exc:
                logger.debug("Failed to update %s: %s", cls.__name__, exc)

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
