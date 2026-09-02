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
| surf `p` pool4 | 106 cols · 44 rows | `screens/surf.SURF_POOL4_FULL_LAYOUT_{COLUMNS,ROWS}` |
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
which is why nothing has been added since 2026-08-12 despite four new bodies
since. surf's `p` pool4 body is the newest of them and the narrowest thing in
the table at 106; it does not touch the record. Its **row** requirement of 44
is the largest pinned here, which is the one number about it worth carrying in
your head — and unlike the other two it is a **worst case over payloads**
rather than a constant, so it is re-swept when a panel's line count changes,
not merely re-checked.

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
all six panels on screen at once, which is why its `l` and `p` and curator's
`y`/`f` swap whole *bodies* instead. Each swapped body gets its **own** pin,
swept in situ against its own panels — surf's `p` is not derived from and does
not equal its `l`, and its sweep deliberately straddles both neighbouring pins
so agreeing with one would show up as a measurement rather than as an
assumption. A swapped-in body is composed once and hidden, so
the first keypress paints a complete frame rather than a blank one.
