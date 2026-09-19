# PRD — a copy icon beside every 0x address

**Status:** built; enforced by tests/test_address_rule.py, tests/screens/test_address_icons_everywhere.py and tests/test_address_sweep_registry.py.
**Applies to:** every dashboard and view in `maxpane_dashboard/`, hidden ones included, and every
dashboard written after this.

---

## 1. The rule

The owner's words: *"everywhere where a 0x wallet or contract address is displayed, a
'copy-to-clipboard' icon should be displayed next to the address, and when clicking it the address
should be copied to the users clipboard. this rule should also apply for every future dashboard
where 0x addresses are displayed."*

Scope decisions made during design, each by the owner or recorded as the default the owner accepted:

| Question | Decision |
|---|---|
| Which icon | **`⧉`** (U+29C9 TWO JOINED SQUARES), one cell wide, chosen after the owner saw it render cleanly in their terminal |
| Where its two columns come from | **Per panel:** grow where the panel has slack, otherwise shorten the displayed address. No layout pin moves for the icon (§5) |
| A name (ENS or player) shown in place of the address | **Gets the icon**, which copies the address behind the name |
| An address inside third-party prose (announce posts) | **Included**, through a prose helper (§3.3) |
| Transaction hashes | **Excluded.** The rule names wallet and contract addresses |
| Hidden dashboards (bakery, OCM, DOTA, frenpet variants) | **Included.** "All dashboards and views" |
| Future dashboards | Bound by enforcement tests, not by memory (§7) |

## 2. What was measured before designing

All of this was probed on 2026-09-14, and the design rests on it.

**One click mechanism works in every widget shape.** Textual 8.1.1. A pre-built `rich.text.Text`
carrying `Style(meta={"@click": "app.<action>(...)"})` on the icon span fires the action when that
cell is clicked. Confirmed in a `Static`, a `DataTable` cell and a `RichLog` line. That fits the
existing rule that third-party text reaches `Static` as pre-built `Text`, never as markup.

**Textual's own copy does not work in the owner's terminal.** `App.copy_to_clipboard` writes OSC 52.
The owner runs `TERM_PROGRAM=Apple_Terminal`, which ignores it, so the click would look fine and copy
nothing. `/usr/bin/pbcopy` is present, and the session was local, not SSH. A native clipboard path
is therefore required, not optional (§4).

**A click on the icon can also trigger the widget's own click behaviour:**

| Widget | Copy fires | Also fired |
|---|---|---|
| `Static` with its own `on_click` | yes | **the widget's `on_click`** |
| `DataTable` | yes | **the cursor moves to that row** (`RowHighlighted`) |
| `RichLog` | yes | nothing |

A widget's `on_click` can see `event.style.meta["@click"]`, skip its own behaviour, and let the copy
fire; a click elsewhere still runs normally (probed). Overriding `DataTable._on_click` does **not**
stop the cursor moving, so the movement comes from another handler. The conflict surface is small:
**only `widgets/surf/feed.py`** renders addresses and has its own click handler (expand/collapse),
and **the only `DataTable` selection handler in the repo is curator's header-click sort**
(`widgets/curator/lists.py:548`). No icon sits in a header, so no table can run a row action off a
copy click.

**The icon's width.** `cell_len("⧉") == 1`, and so is each other text-presentation candidate
(`⎘`, `❐`). `📋` is 2 cells and renders inconsistently in Apple Terminal. Icon plus separating space
costs **2 columns** per address.

**The current state of address rendering:**
- **48 candidate modules** match an address-formatting pattern (§9 lists them). The scan is broad,
  and a few may be false positives (for example `widgets/surf/_rowfit.py` slices strings to fit cells).
  Each work package confirms its own.
- **21 separate address formatter definitions.** Most are copies of `_short_addr`, which is the
  duplication CLAUDE.md's "Reuse before you build" warns about.
- **7 modules** show a name in place of an address, including **both templates**.
- **5 sites shorten an address before it reaches a widget**, so the full value never arrives there:
  `data/fwa_manager.py:422`, `data/curator_list_filters.py:67`, `analytics/surf_signals.py:542` and
  `:1004`, `analytics/fwa_signals.py:374/377`.
- **Test sample payloads exist for 5 dashboards** (surf, curator, FWA, frenpet, talismans) and **not**
  for base, cattown, TTT, OCM, DOTA or bakery.
- **6 of 60** text fields in the cached surf announce feed contain a full 0x address.

## 3. The helper — `maxpane_dashboard/widgets/address.py`

One module owns every address a widget renders. It is pure: no I/O, no clock, no `data/` import.
Widgets and the two templates import it; nothing copies out of it.

### 3.1 Validation, and why it comes first

```
ADDRESS_RE = ^0x[0-9a-fA-F]{40}$
```

The address is **interpolated into an action string** (`app.copy_address('0x…')`). Addresses reach
widgets from chain data and third-party payloads, so a value containing `'` or `)` could break the
action or smuggle a different one into it. **Only a value matching `ADDRESS_RE` is ever interpolated.**
Anything else renders as plain text with **no icon**, and never reaches an action string. The app
action (§4) validates again: the meta that names it is not the only way that action can be invoked.

**AMENDED 2026-09-14 — match with `fullmatch`, never `^…$`.** Python's `$` also matches *before a
trailing newline*, so `re.match(r"^0x[0-9a-fA-F]{40}$", "0x…40 hex…\n")` succeeds and a value ending
in a newline would pass validation and reach the action string, which is the injection case this
section exists to stop. The implementation compiles `0x[0-9a-fA-F]{40}` without anchors and calls
`.fullmatch()`. The spelling in the code block above is the *shape* of the rule, not its implementation.

### 3.2 Rendering one address

```python
COPY_GLYPH = "⧉"
ICON_COLS = 2                      # " " + glyph; the width cost every layout budget uses

def short_address(address: str, width: int) -> str: ...
def short_hex(value: str, width: int) -> str: ...
def address_text(address: str | None, *, label: str | None = None,
                 width: int | None = None) -> Text: ...
```

- **`short_address`** is **the one address shortener**, and it replaces the 21. It fits the address
  into `width` cells, on `rich.cells.cell_len`, with a middle ellipsis.
  **AMENDED 2026-09-14 — the window rule, and why it is this one.** With `budget = width − 3` (for
  `0x` and `…`): `tail = min(6, budget // 2)` and `head = budget − tail`, and `width` is clamped to at
  least 11. That reproduces **both** formatters it replaces, exactly:
  - at 17 cells it gives **8 head / 6 tail**, which is surf's `long_addr`. That form is an
    **anti-poisoning** window: its docstring records live spoofs of frenpet.eth's fee recipients that
    collide with the real addresses on the common first-6/last-4 form. Collapsing 21 formatters into
    one that defaulted to 6/4 would reintroduce a known attack on every dashboard at once;
  - at 11 cells it gives **4 / 4**, which is curator's `short_addr`;
  - at 40 cells, STAKERS' trade at its pin, it gives 31 / 6.
  **Case is preserved.** Curator lower-cases on purpose (its two sources spell an address two ways,
  and "this row is you" must not depend on which panel you read), so curator lower-cases its input
  *before* calling the helper and keeps that reason in its own code. A package that shortens a panel
  below its old window to protect a pin records the anti-poisoning cost beside the pin, not only the
  column cost.
- **`short_hex`** shortens any other 0x hex value, such as a transaction hash, the same way and
  **without an icon**. Transaction hashes are outside the rule, but they cannot keep their own
  slice-shaped formatters either: E1 (§7) bans those shapes everywhere, and it can only do so without
  a legitimate exception if every 0x shortening goes through this module.
- **`address_text`** returns `display + " " + ⧉`, with the click meta on **the glyph only**. Clicking
  the displayed text does nothing.
  - `label` is a name shown instead of the address. The icon still copies `address`. A label is
    fitted to `width` on `cell_len` exactly like an address, because names are attacker-chosen and
    can be wide (CJK, emoji).
  - `width` is the cell budget for the **displayed part**, excluding `ICON_COLS`. `None` means show
    the full address.
  - The display text is third-party (names are attacker-chosen), so it is appended as `Text` and never
    parsed as markup.

### 3.3 Addresses inside prose

```python
def address_prose(text: str) -> Text: ...
```

This finds each valid address in third-party prose and inserts the icon after it. The match needs
**hex boundaries on both sides**:
`(?<![0-9a-fA-F])0x[0-9a-fA-F]{40}(?![0-9a-fA-F])`. A 64-hex transaction hash starts with a
40-hex run, and without the lookahead every tx hash in a post would get an address icon copying a
truncated, meaningless value.

### 3.4 The click guard for widgets with their own click handler

```python
def is_copy_click(event) -> bool: ...    # True when the click landed on a copy icon
```

A widget with its own `on_click` returns early when `is_copy_click(event)` is true. Today that is only
`widgets/surf/feed.py`; the helper exists so the next such widget does not re-derive the meta lookup.

## 4. The copy action — `MaxPaneApp.action_copy_address(address)`

It lives on the app, so every screen shares it.

1. **Validate** against `ADDRESS_RE`. On failure, do nothing to the clipboard and post
   `copy unavailable`.
2. **Native clipboard first:** macOS `pbcopy`; Linux `wl-copy`, then `xclip -selection clipboard`,
   then `xsel --clipboard --input`; Windows `clip`.
   - Run it with `asyncio.create_subprocess_exec` (argument list, no shell, address on stdin) under
     `asyncio.wait_for`. Never use the `timeout` binary, which is absent on macOS.
   - The UI never blocks.
3. **Otherwise OSC 52** through `App.copy_to_clipboard`, when no native tool exists or it failed, as
   over SSH.
4. **Report honestly** in the status bar:

| Outcome | Message |
|---|---|
| native tool exited 0 | `copied 0xd8dA…6045` |
| only OSC 52 was possible | `sent to terminal clipboard (unconfirmed)` |
| neither | `copy unavailable` |

OSC 52 cannot confirm the terminal accepted anything, and saying `copied` on that path would be a
confident claim nobody checked.

**The message** uses `StatusBar.set_message`, curator's existing ownership pattern (CLAUDE.md,
"Long-running ENS, JSON export, and list-reload work owns the centered footer message"). It clears
itself after about 3 seconds, **and only if it is still the message on display**, so it never erases
a newer export or ENS status.

**It never reads the clipboard.** Write-only. It never logs anything but the address it copied.

**Hard constraints.** The only new capability is a local clipboard write. No network, no key, no
signing, no transaction. It sits inside constraints 1 and 2 as written.

## 5. Width: per panel, measured

The owner chose: **grow where the panel has slack, otherwise shorten the displayed address.** The icon
never raises a pin. The pins in force, read from the code on 2026-09-14:

| Constant | Value |
|---|---|
| `__main__.FULL_LAYOUT_COLUMNS` | 143 |
| `screens/surf.SURF_FULL_LAYOUT_COLUMNS` | 143 |
| `screens/surf.SURF_LAUNCHPAD_FULL_LAYOUT_{COLUMNS,ROWS}` | 138 × 31 |
| `screens/surf.SURF_POOL4_FULL_LAYOUT_{COLUMNS,ROWS}` | 99 × 45 |
| `screens/surf.SURF_POOL4_USER_FULL_LAYOUT_{COLUMNS,ROWS}` | 119 × 35 |
| `screens/curator.CURATOR_FULL_LAYOUT_COLUMNS` | 138 |
| `widgets/surf/launchpad._TABLE_FULL_WIDTH` | 89 |

- **Measure, never derive.** Each package re-sweeps the pins its panels touch, in situ, per the
  terminal-layout skill.
- **Where the icon fits in slack**, it is added and the pin holds.
- **Where it would move a pin**, the displayed address gives up `ICON_COLS` cells and the pin holds.
  Every such trade is recorded in the `#:` block of the constant it protects, so a shortened address
  is not later taken for an oversight.
- **Panels with width tiers pick the longest display that fits beside the icon.** The known case is
  surf's STAKERS: it binds `SURF_POOL4_USER_FULL_LAYOUT_COLUMNS` at 119 with whole 42-character
  addresses. At the pin it shortens by two cells; at wider terminals it shows the whole address plus
  the icon. The whole value is one click away either way.
- A panel with a cell whose honest short form cannot give up two more cells **stops and reports**. It
  must not quietly raise the pin.

## 6. Pre-shortened data

The five sites in §2 **carry the full address as its own field**, and the widget shortens it for
display through the helper:
- `data/fwa_manager.py` and `data/curator_list_filters.py` publish the address alongside, not instead
  of, their display label.
- `analytics/surf_signals.py` and `analytics/fwa_signals.py` split signal text such as
  `new contract 0xab…cd` into a label plus an `address` field. The widget joins them with
  `address_text`.

This is a payload contract change for those rows. Each owning package grows its row-shape declaration
(for example `SURF_ROW_KEYS`) and the tripwires that guard it.

## 7. Enforcement, so a future dashboard cannot forget

**E1 — no private formatters.** A source test walks `maxpane_dashboard/`. It fails when any module
other than `widgets/address.py` defines a function whose name marks it as an address formatter
(`short_addr`, `long_addr`, `full_addr`, `fmt_addr`, `truncate_addr`, with or without a leading
underscore, and their `address` spellings). It also fails when any module under `widgets/`,
`screens/`, `data/` or `analytics/` shortens with the `[:6]…[-4:]` / `[:10]…[-6:]` slice shapes.
Transaction hashes shorten through `short_hex`, so the ban has no legitimate exception. This catches
the next copy before it exists.

**E2 — every address on screen has its icon.** A composited sweep renders **every** dashboard and
view with its sample payload. The `views` tuple of each `SweepCase` in
`tests/address_sweep/builders.py` is the owner of that list (surf's and curator's swapped bodies, the
curator filter editor, the hidden screens); this paragraph does not restate it.
Each payload is seeded with known addresses in all four shapes: full, shortened, name-backed and in
prose. For each known address, the displayed form must be followed by ` ⧉`, and **that glyph's
`@click` meta must name exactly that address**. A glyph that copies the wrong address is a worse
defect than a missing one.

**E3 — every dashboard has something to sweep.** A registration test fails when any id in `GAMES`, or
any hidden registered screen, has **no sample payload builder**. Without it, E2 passes vacuously for
a dashboard nobody rendered. The six missing builders are written as part of this work.

Each dashboard is **declared** in the sweep's registry as *address-rendering* or *address-free*, as a
hand-typed literal:
- An **address-rendering** builder must seed at least one address in every shape that dashboard uses
  (full, shortened, name-backed, prose), so E2 has something to check.
- An **address-free** dashboard gets the opposite and stronger assertion: **no 0x address appears
  anywhere** in its composited output. A later panel that starts showing one then fails the suite
  instead of slipping past a sweep that expected nothing. This is also why no builder is forced to
  invent an address for a dashboard that never shows one (DOTA looks like such a case).
- An **agreement test** ties the declaration to the code: a dashboard whose widgets import
  `widgets/address.py` cannot be declared address-free. That is redundancy plus an agreement test,
  the repo's `_GAME_CYCLE` shape, so a wrong declaration fails instead of hiding a dashboard from E2.

**E4 — the validation holds.**
- An address containing `'`, `)` or a newline renders with no icon and never reaches an action string.
- A 64-hex transaction hash in prose gets no address icon.
- A malformed value in `action_copy_address` touches no clipboard.

**E5 — tests never touch the real clipboard.** The clipboard backend is injected. A test that would
spawn a real `pbcopy`, `xclip`, `wl-copy` or `clip` fails structurally, the same way a network touch
does. A headless suite that overwrote the developer's clipboard would be the `MANAGER_ATTRS`
cache-overwrite hazard in a new place.

**E6 — the message is honest and owned.** Each of the three outcomes in §4 posts its own message. The
auto-clear never removes a message it did not post.

**E7 — every rendered address is a link to its chain's explorer** (refactor programme 2026-09,
Branch 4; the helper, the action and the guards landed in WP-A on 2026-09-20, the call sites and
the sweep assertion land in WP-B). The *shown* span — the address, its window or the name standing
in for it, never the icon — carries an OSC 8 `link` (Cmd+click in the terminal) **and** an
`@click` action `app.open_explorer(name, kind, value)` naming the same page, built only by
`widgets/explorer.py` from an allowlisted explorer (`etherscan`, `basescan`, `sepolia`) and a
value validated with `fullmatch`. `ExplorerLinkMixin.action_open_explorer` re-validates all three
parts and rebuilds the URL from them; an action with anything foreign opens nothing and posts
`explorer unavailable`. An unknown chain gets no link (`for_network` returns `None`), never a
guessed one. Once WP-B lands, the E2 sweep also fails on an address without a link or with a link
on the wrong explorer. A transaction hash links through `hash_text` (`/tx/`), still without an icon.

**E8 — tests never open a browser.** `tests/conftest.py::_forbid_real_browser` replaces
`webbrowser.open` suite-wide (Textual's `Driver.open_url` reaches it even under `run_test`); a
pilot test that clicks a link mixes `tests/widgets/address_probe.LinkRecorder` into its harness,
which records `open_url` and opens nothing. E5's shape, for the browser.

Every test proves it bites: mutate, watch the named test go red, restore. `pytest ::nonexistent_test`
exits 4, so a non-zero exit is not evidence.

## 8. Templates and docs

- **`templates/activity_feed_template.py` and `templates/leaderboard_template.py`** import the helper,
  drop their `_short_addr`, and say in their docstrings that the icon is mandatory. The templates are
  how bugs propagate (CLAUDE.md, "Known hazards"), and they are equally how a convention propagates.
- **CLAUDE.md** gets a new **Conventions** entry: every displayed 0x address carries the copy icon
  through `widgets/address.py`, and the E1–E3 tests are why that is not optional.
- **`.claude/skills/terminal-layout/SKILL.md`** records `ICON_COLS` and the per-panel rule.
- **README** notes the icon under keys and interaction.

## 9. The candidate modules

From a pattern scan on 2026-09-14. Each package confirms its own list.

- **base (10):** `widgets/base/fee_claims.py`, `fee_leaderboard.py`, `graduated.py`, `launch_feed.py`,
  `overview.py`, `top_movers.py`, `trending_table.py`, `overview/_legacy_overview.py`,
  `overview/bt_leaderboard.py`, `overview/bt_overview_leaderboard.py`
- **cattown (3):** `widgets/cattown/ct_activity_feed.py`, `ct_hero_metrics.py`, `ct_leaderboard.py`
- **curator (11 shipped):** `widgets/curator/_fmt.py`, `activity.py`, `cleaned_list.py`,
  `closest_calls.py`, `leaderboard.py`, `list_filter.py`, `list_hero.py`, `lists.py`, `signals.py`,
  `wallet.py`; `screens/curator.py` (the pins the icon moved). The pre-implementation scan listed six
  and missed `cleaned_list`, `lists`, `wallet`, `list_filter` and `list_hero`.
- **frenpet (3 widgets + 3 screens):** `widgets/frenpet/overview/fp_overview_leaderboard.py`,
  `sniper_queue.py`, `top_leaderboard.py`; `screens/frenpet_full.py`, `frenpet_perf.py`,
  `frenpet_wallet.py`
- **FWA (5):** `widgets/fwa/fwa_activity_feed.py`, `fwa_chase_board.py`, `fwa_hero_metrics.py`,
  `fwa_odds_board.py`, `fwa_settlement_table.py`
- **OCM (1):** `widgets/ocm/ocm_activity_feed.py`
- **surf (8):** `widgets/surf/_fmt.py`, `_rowfit.py`, `activity.py`, `burnkeepers.py`,
  `launchpad.py`, `launchpad_activity.py`, `pool4_hatches.py`, `pool4u_stakers.py`
- **talismans (1):** `widgets/talismans/tal_leaderboard.py`
- **TTT (4):** `widgets/ttt/ttt_activity_feed.py`, `ttt_claims_table.py`, `ttt_fees_table.py`,
  `ttt_leaderboard.py`
- **shared (2):** `widgets/activity_feed.py`, `widgets/leaderboard.py`
- **templates (2):** `templates/activity_feed_template.py`, `leaderboard_template.py`
- **prose, in addition to the 48:** `widgets/surf/feed.py`, found separately rather than by the
  pattern scan, which also hosts the one conflicting `on_click`

## 10. Work packages

| Wave | Package | Owns |
|---|---|---|
| 0 | helper (§3), copy action (§4), status message, E4/E5/E6 | `widgets/address.py`, `app.py`, `widgets/status_bar.py` |
| 1 (parallel) | surf, including `feed.py` prose and the click guard | surf widgets, `analytics/surf_signals.py`, surf pins |
| 1 | curator | curator widgets, `data/curator_list_filters.py`, `CURATOR_FULL_LAYOUT_COLUMNS` |
| 1 | FWA | FWA widgets, `data/fwa_manager.py`, `analytics/fwa_signals.py`, `FULL_LAYOUT_COLUMNS` |
| 1 | base | base widgets |
| 1 | cattown + talismans | their widgets |
| 1 | TTT | TTT widgets |
| 1 | hidden (OCM, DOTA, bakery, frenpet variants) + shared feed/leaderboard + templates | those modules and screens |
| 2 | the six missing sample payloads + E1, E2, E3 | `tests/` only |
| 3 | CLAUDE.md, the skill, README, full suite | docs |

**Wave 0 lands first and alone**, because every other package builds against its signatures. Wave 2
follows wave 1, because E2 can only pass once the icons exist. Within wave 1, each dashboard's screen
and its pins have exactly one owner.

## 11. Known consequences, stated rather than discovered

- **A table's cursor moves to the row whose icon was clicked.** No table acts on selection, so nothing
  else happens. Accepted.
- **OSC 52 is unconfirmable.** The message says so rather than claiming `copied`.
- **At a pin, some addresses show two fewer characters than today** (§5). The full value is one click
  away, and every trade is recorded beside its pin.
- **DOTA only renders an unavailable state live** (its backend is NXDOMAIN). It still gets a sample
  payload so E2 covers its address sites.
- **Linux without `wl-copy`, `xclip` or `xsel`** falls back to OSC 52 and says `unconfirmed`.

## 12. What this will not do

- **No transaction-hash copying.** Out of the rule's scope, and easy to add later with the same helper.
- **No clipboard reads**, ever.
- **No network, no keys, no signing.** Constraints 1 and 2 are untouched.
- **No pin raised for the icon.**
- **No icon inside editable input fields**, such as the wallet prompt (`WalletInputScreen`). An
  address a reader is typing is input, not a displayed address.
