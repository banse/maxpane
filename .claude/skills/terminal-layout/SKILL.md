---
name: terminal-layout
description: Read before changing anything that affects how a MaxPane dashboard is laid out or sized in the terminal - panel widths, column budgets, cell formatters, fr seams, scrollbar gutters, min-heights, `‹ widen` / `‹ taller` markers, FULL_LAYOUT_COLUMNS or any per-screen width/height pin, adding or resizing a widget or a table column, or re-sweeping a layout after a panel changed. Also read it when a width or height constant needs measuring, when a panel clips or truncates, or when deciding between raising a constant and shortening a value.
---

# Terminal layout in MaxPane

Every rule here is a bug that shipped, was found, and was fixed. The numbers
themselves are **not** here on purpose: each pin lives on its own constant, in a
30–40 line `#:` block next to the code it governs, where it cannot drift from
it. This file is the method; the constants are the record.

## The pins and who owns them

| view | pin | constant |
|---|---|---|
| app-wide | 143 | `__main__.FULL_LAYOUT_COLUMNS` |
| surf dashboard body | 143 | `screens/surf.SURF_FULL_LAYOUT_COLUMNS` |
| surf `l` launchpad | 138 cols · 31 rows | `screens/surf.SURF_LAUNCHPAD_FULL_LAYOUT_{COLUMNS,ROWS}` |
| surf `p` pool4 (key `e`, experimental, since 2026-09-15) | 99 cols · 45 rows | `screens/surf.SURF_POOL4_FULL_LAYOUT_{COLUMNS,ROWS}` |
| surf `4` pool4 market (hint `4 pool4`) | 119 cols · 35 rows | `screens/surf.SURF_POOL4_USER_FULL_LAYOUT_{COLUMNS,ROWS}` |
| surf `s` swarm (hint `s swarm`; 116 · 28 from 2026-09-16, re-swept for swarm v2 on 2026-09-21) | 141 cols · 42 rows | `screens/surf.SURF_SWARM_FULL_LAYOUT_{COLUMNS,ROWS}` |
| surf `a` agent (hint `a agent`, since 2026-09-21) | 134 cols · 40 rows | `screens/surf.SURF_AGENT_FULL_LAYOUT_{COLUMNS,ROWS}` |
| curator (all bodies) | 138 | `screens/curator.CURATOR_FULL_LAYOUT_COLUMNS` |
| coin table's own | 89 | `widgets/surf/launchpad._TABLE_FULL_WIDTH` |

**Layout is a function of terminal columns.** Widgets pick a width tier and
advertise what they dropped as `‹ widen` in their own title; a body that runs
out of rows says `‹ taller` on the screen-wide title bar. Launch forces 17 pt —
about 169 columns on a laptop — so 143 is reachable without `--font-size` /
`MAXPANE_FONT_SIZE`.

**The app-wide record, appended never rewritten: 198 → 172 → 143 → 176 → 152 →
143.** FWA set the first three and the last; surf the two in between. It tracks
*that* number only — a dashboard measuring under 143 does not append to it,
which is why nothing has been added since 2026-08-12 despite five new bodies
since. surf's `p` pool4 body holds the **row** record at 45, the largest pinned
here, and unlike the column pins it is a **worst case over payloads** rather
than a constant, so it is re-swept when a panel's line count changes, not
merely re-checked. surf's `4` market body is the newest, and **it was the
narrowest thing in the table at 105 for one day**; neither touches the
app-wide record. Its row pin
went 33 -> 35 on 2026-09-12 when every panel on it gained the repo-wide blank
row under its title (`margin: 0 0 1 0`); four panels grew a row each and the
pin moved two, because only the binding column's growth reaches it. **That
number is the price of the convention, and it is the one to quote when asked
whether a body can afford it.**

Later the same day it went **35 -> 32**, which is the same arithmetic run
backwards and is the better worked example of it. The owner asked for the
per-panel `as of` markers on that body to go; **all five panels lost a row and
the body gave back three**, because the rail lost two (two panels stack in it)
and the bottom row lost one, and only the taller of the two reaches the pin.
Five rows removed, three rows recovered — do not predict either number, sweep
for it. The one marker that was *not* redundant with the title row (a 1800 s
tier's, an hour and a half behind it) was replaced by a conditional word on a
line the panel was already painting, which is the cheap way to keep a
staleness claim when its own row has been taken away.

surf's `p` body took the same change later the same day and **its pin went
44 -> 45**, which closes F10b -- "the `p` body cannot obviously afford it" --
by measurement rather than by argument. Four of its five panels grew a row
each and the body grew one: THE SPLIT already had the blank, and POOL4 FLOW's
landed inside the floor it already sits on, so the row came out of its
`RichLog` (three log lines at the pin where there were four -- the column
heading plus two swaps rather than three) instead of out of the layout. That is the general shape of this cost and the reason to measure
it rather than multiply: **four panels x one row came to two rows on one body
and one on the other**, because only the binding column's growth reaches a
pin, and a row that lands inside an existing floor does not reach it at all.
Raising FLOW's floor to buy its fourth log row back was measured too and
costs a second row (45 -> 46); it was not spent.

On 2026-09-14 the owner removed POOL4 FLOW from the `p` body, because the `4`
body's RECENT FLOW already renders its rows. **The width pin went 106 -> 99 and
the row pin did not move.** That is the binding-column rule seen from both
axes at once, and it is the example to quote when someone expects a removed
panel to clear `‹ taller`:

* FLOW **bound** the width (a 52-need panel buying 53 with its column's
  gutter), so removing it moved that pin. It moved seven columns, not three,
  because under 1:1 the rail now has to get its 50 and an odd terminal width
  hands the rail the odd column. The binder is HATCHES now, with zero margin;
  it still marks at every width under the pin.
* FLOW sat in the column that only **tied** the height, at 34 rows each. The
  left column fell to 28 and the rail stayed at 34, so the pin stayed at 45
  and `‹ taller` is still lit at 44.

The left column kept no `1fr` child. Neither survivor scrolls inside itself,
so the freed rows are blank space at the column's foot rather than a floor on
a `Static` that could cut in silence.

Later still on the same day the owner asked for three layout changes on the
`4` body at once and **both** its pins moved: 105 -> 119 and 32 -> 35. That
entry is the worked example of three separate lessons in this file, so it is
worth reading before touching a pin:

* **A change to what a cell CONTAINS is a change to a pin.** The only code
  change behind the fourteen columns is one table column going from a
  17-cell address window to the whole 42-character address. Nothing about
  the seam, the panels or the shape was touched by that half of it.
* **"Make this panel narrower" has a floor, and it is usually not the thing
  you are looking at.** IF IMD FALLS looks half-empty because its *table* is
  27 cells. Its **caption** is 41, and below 45 columns the caption clips
  with no `‹` -- the widen tier is computed from the table. That
  disqualifies every narrower seam under the marking rule, and the gap
  between "the table is 27" and "the panel needs 45" is exactly what a sweep
  finds and arithmetic does not.
* **A `fr` is the wrong instrument for "make it smaller".** A ratio hands a
  panel a *share*, so a seam sized at the pin grows that panel straight back
  on a wide terminal -- on a 169-column screen the ladder would have come
  back at 65, wider than the 52 that prompted the request. The fix was a
  **fixed** column for the panel whose content is a constant, and `1fr` for
  the one that can use every spare column. It is the width-axis twin of the
  "put the `1fr` on the child that scrolls inside itself" rule below.

**Two of those pins WERE one column apart with the same panel binding both,
and that was the strongest argument here against deriving a pin from a
neighbour.** The example is kept because it is still the clearest one, even
though the `4` body has since moved thirteen columns past the `p` body and
handed its seam to a different panel -- which is itself the lesson, one layer
out: a relation between two independently swept pins is a coincidence with a
date on it, and nothing should be derived from it even while it holds.
`SurfPool4Flow` bound surf's `p` body and its `4` body (until 2026-09-14, when
it left `p`). In `p` it sat in a
scrolling `Vertical` that reserves its own scrollbar gutter, so that column had
to buy a column more than the panel needs; in `4` the row it sits in does not
scroll, so the seam buys the panel's need exactly and the body's single gutter
is paid once instead of twice. Same panel, same need, two different pins.
Transferring either body's number to the other would be wrong by one column, in
the direction that hides a clipped row.

**A body-level `‹ taller` does not see a table scrolling inside a panel.**
`_rail_is_cut` asks the containers a mode names for `show_vertical_scrollbar`,
so a `DataTable` or `RichLog` that overflows *within* a panel paints its own
scrollbar nub and nothing screen-wide says so. That is fine for a panel whose
content is unbounded by design — a log, a leaderboard page — and it is a silent
loss for a panel whose line count is a **constant**, where `min-height` is
meant to be floor and ceiling both. Measure a row pin against the body's
**content**, not against the height at which the marker goes out: on surf's `4`
body those two answers were one row apart, and the marker's was the optimistic
one.

**The cure is the floor, not the marker**, and it was found by accident on
2026-09-12. That one-row gap closed when `#surf-pool4-user-bottom`'s
`min-height` was raised to the ladder panel's own content height — a panel that
cannot be squeezed under its content cannot scroll *inside itself* while the
body does not, so the loss moves to the body's own scrollbar, which
`_rail_is_cut` can see. `_rail_is_cut` learned nothing, so this is a rule about
floors: **give a fixed-line-count panel a floor equal to its content and the
marker becomes honest for free; floor it lower and the gap comes straight
back.** Still measure against content — the floor is what makes the two agree,
and nothing enforces it from the marker's side.

That row's floor is now 12 rather than the ladder's 9, which is **above** its
tallest panel's content and is the one floor on that body that is not a
measurement. It was bought for the leaderboard that moved into the row later
the same day — a leaderboard in a nine-row slot prints five entries — and it
widens the safety margin above rather than narrowing it, so the rule holds in
the direction it was written. The rule's converse is the thing to watch: a
floor *above* its panel's content costs the body rows, and the skill's answer
to that is the one this file gives everywhere else — buy the margin
deliberately and write down what it cost, which
`SURF_POOL4_USER_FULL_LAYOUT_ROWS` does (32 -> 35).

## The rules

* **Measure, never derive.** Arithmetic over the column constants has been wrong
  twice — a `DataTable` buys a cell gutter per column, so a sum that looks right
  ships a clipped header with the marker dark.
* **Measure in situ**, inside the real container. A panel's widest line pays its
  own padding, its inner widget's padding *and* any reserved
  `scrollbar-gutter: stable` cell. A number from a bare harness is short. This
  has bitten twice in one branch: a panel width compared against a pure-content
  constant while the `padding: 0 1` lived on the child `Static`.
* **A sweep never starts at the pin**, or it agrees with the constant by
  construction. Re-centre the range whenever the pin moves.
* **A panel that can bind must be able to mark.** A seam whose binding panel
  clips in silence is disqualified. Some layouts therefore buy a few columns of
  margin deliberately — see the note on the seam constant before spending them.
* **Reserve the scrollbar gutter**, or a layout's *width* requirement becomes a
  function of its *height* and the pin is true at one terminal size only.
* **Measure a data-dependent width against the state the data is normally in**,
  not against whichever capture happens to be committed. A compact formatter
  makes the committed fixture the *narrow* case.
* **When a new value would widen a sized cell, shorten the value.** Raising a pin
  is reserved for when no honest short form exists. FWA's buy-gate signal was
  shortened rather than let the app-wide number grow past 143; curator caps an
  ENS name at 12 (`NAME_COLS`, exactly `surfsurf.eth`) because 15 moved its full
  layout 138 → 144. A cell earns a shorter form only once a sweep shows it is
  the one actually asking for the columns — never on a guess.
* **Give a `1fr` child a `min-height`.** A `1fr` child cannot overflow a scroll
  container — it *shrinks* — so without a floor it sheds a line per terminal row
  down to a bare title, with no scrollbar and no trace.
* **Put the column's `1fr` on the child that scrolls inside itself**, and make
  the one whose height answers to a payload `auto`. Shrinking a `RichLog` moves
  rows behind its own scrollbar; shrinking a `Vertical` holding a `Static` loses
  them. The pool4 rail is the worked example and it inverts the other bodies'
  habit deliberately: floor the variable-height hatch list and it silently cuts
  two rows off a twelve-lever payload in the narrow window where the rail does
  not yet scroll, so the fixed-height panel takes the `1fr` instead. The price is
  blank space on a tall terminal; what it buys is a panel that cannot be cut at
  any height. It does **not** buy a constant row pin, and an earlier version of
  this bullet claimed it did: that held only while one column's panels were all
  fixed-height. Once mainnet made a second panel payload-sized, no two-column
  cut kept both variable panels out of the binder and the pin became a worst
  case over payloads. Rule stands; the bonus it was credited with does not.
* **A `Vertical` defaults to `overflow: hidden`.** A column that holds a growing
  panel needs `overflow-y: auto` *and* the gutter, or it clips with no scrollbar.

## Measuring and fitting text

* **A sized cell is not a fitted one.** `len()` counts characters where the
  terminal counts cells, so CJK and emoji overflow a budget arithmetic says they
  fit. Fit on `rich.cells.cell_len`. Tickers and coin names are attacker-chosen
  (`launch(string,string)` is permissionless), so this is reachable input, not a
  theoretical edge.
* **`Text.no_wrap` and `Text.overflow` are inert** through Textual 8:
  `visualize()` funnels a Rich `Text` through `Content.from_rich_text`, which
  carries the spans and drops both attributes. Setting them reads as a promise
  and is a no-op. Clipping comes from CSS (`text-wrap: nowrap`) or from having
  already fitted every line on `cell_len`.
* **`RichLog(wrap=False)` narrows a line with no ellipsis and no marker.** A row
  built by hand must be fitted before it is written, or a number is cut in half
  and nothing says so. `widgets/surf/activity.py`'s `_budget` / `_row_cols` is
  the worked example: an absent cell takes its gap with it, and the batch shares
  one layout so columns line up down the panel.
* **`DataTable` truncates a header to its column width with no ellipsis**, so two
  labels sharing a prefix longer than their columns become the same word on
  screen. And its `default_cell_formatter` calls plain
  `rich.text.Text.from_markup`, not Textual's CSS-variable-aware renderer, so a
  `$`-prefixed theme token raises `MarkupError` in a cell where it works fine in
  a `Static`.
* **`DataTable.show_horizontal_scrollbar` is not a clipping signal** — it reads
  `True` several columns before any character is lost, so a marker keyed off it
  fires early and disagrees with the screen.
* **An address costs `widgets/address.ICON_COLS` more than its text.** Every displayed 0x address
  carries a copy icon. Where adding it would move a pin, the displayed address gives up the two
  cells instead (`short_address`, window rule 8/6 at 17 cells), and the trade is recorded in the
  pin's `#:` block together with its anti-poisoning cost.

## CSS lives in two places

Every screen rule must appear identically in `SurfScreen.DEFAULT_CSS` (or the
screen's own) **and** in the matching block of `themes/minimal.tcss`. A test
compares them property by property. A widget's own `DEFAULT_CSS` losing to a
screen rule is legal but is action at a distance — prefer changing the value
where it is declared.

## Testing a layout

* **Assert against composited output** (`_compositor.render_strips()`), never the
  content string. Join segments per **row** first, then rows by newline — joining
  every segment with a newline splits one painted row into several apparent
  lines the moment a row carries two styles.
* **Pin the derivation, not just the threshold.** The three tests that make this
  work trustworthy are of that shape: is the pin measured against the column it
  describes, is the binding panel the one this claims, does the marker agree with
  whether the header actually reaches the compositor. All three bite.
* **A width test must fail in both directions** — set the constant too low and
  too high, and confirm each reddens. A one-directional test would have missed
  the defect that shipped here.
* **Sweep the boundary, not a comfortable width.** A test that renders well
  inside the clean band cannot see a threshold move.
* **A pin is certified by its boundary set, not by an integer walk.** Since
  2026-09-19 the sweeps in `tests/screens` run at `boundary_set(pin, lo, hi,
  *thresholds)` (`tests/screens/_sweeps.py`): the band's two ends, the pin ±1,
  and every declared tier threshold or per-payload whole-from width ±1 — the
  numbers the pin's `#:` block names as measured onsets. The geometry
  invariants asserted at each size (region overflow, hidden `DataTable`
  columns, clipped lines, wrap-shed flags) are what caught `7df2e8c` and
  `f51a528`; the enumeration between thresholds never did. When a pin moves,
  the set re-centres itself through the constant; when a *new* threshold is
  measured, add it to the call — a threshold the set does not name is a
  threshold the test cannot see move.
* Prefer asserting a **property** (whenever a row would clip, the marker is lit)
  over a **literal** (the marker lights below 35). The literal goes stale
  silently; the property cannot.

## A caveat the pin does not cover

143 clears every *layout*, not every possible string: surf's announce feed still
lights `‹ widen` there whenever a post links a transaction, because the post's
own punctuation glues the URL to a 66-char hash into one unbreakable token. That
marker is correct — the next such post brings its own length — and must not be
silenced by raising the constant
(`test_a_linked_post_advertises_widen_at_the_full_layout_width`, and
`test_the_documented_width_is_not_promised_to_clear_every_post`, which pins this
paragraph).

## The 143 has no margin left on surf's title row

New on 2026-09-01, and it is a fact about the **next** change rather than this
one. `tests/screens/test_surf_screen.WORST_CASE_TITLE_COLUMNS` is a swept
measurement of the one row on the surf screen that cannot ellipsise: the board's
name, every figure, the `as of` marker, `‹ taller`, the LP warning and **every**
degraded group, which is exactly what a full outage prints. pool4 added an
eighth group (`SOURCE_POOL4`, rendered `p4`) and the row prints every member
verbatim, so it cost four columns and took the measurement 139 → **143** — level
with `SURF_FULL_LAYOUT_COLUMNS`, to the column.

The standing "shorten the value, do not raise the pin" rule does not fire here:
the row still *fits* the documented width, it merely no longer clears it. What
zero margin means is that a ninth source group, or one more word anywhere on
that line, puts the worst case past 143, where the tail is **gone** — no `…`, no
scrollbar, no trace, on the one row of that screen whose job is to say something
is down. The companion test's
`WORST_CASE_TITLE_COLUMNS <= SURF_FULL_LAYOUT_COLUMNS` assertion is what turns
that into a red suite instead of a silent loss, and it has no slack left to
absorb an edit. Shorten that row before adding to it, and re-sweep rather than
adjusting the constant to match.

## Body swaps

`c` swaps a shared slot on FWA, TTT, Talismans and curator so three panels that
cannot share a row do not have to. Surf does not: its 2026-08-10 restructure put
all six panels on screen at once, which is why its `l`, `p` (key `e` since 2026-09-15), `4` and `s`
and curator's `y`/`a` swap whole *bodies* instead. Each swapped body gets its
**own** pin, swept in situ against its own panels — surf's `p` is not derived
from and does not equal its `l`, and its sweep deliberately straddles both
neighbouring pins so agreeing with one would show up as a measurement rather
than as an assumption. The `4` body's sweep straddles all three of them for the
same reason, and it starts eighty-one columns under the number it collects --
re-centred, like every sweep here, the day the pin moved. A swapped-in body is composed once and hidden, so
the first keypress paints a complete frame rather than a blank one.
