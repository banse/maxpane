---
paths:
  - "maxpane_dashboard/widgets/**/*"
  - "maxpane_dashboard/templates/**/*"
  - "maxpane_dashboard/themes/**/*"
  - "maxpane_dashboard/screens/**/*"
  - "tests/widgets/**/*"
  - "tests/screens/**/*"
  - "tests/address_sweep/**/*"
  - "maxpane_dashboard/clipboard.py"
  - "tests/test_address_rule.py"
  - "tests/test_address_sweep_registry.py"
  - "tests/conftest.py"
---

# Widgets, screens and templates — the full rules

Every rule here is a bug that shipped, was found, and was fixed repo-wide. The headlines are in
`CLAUDE.md` "Conventions"; this file carries the reasoning and the tests that enforce them.
Layout and sizing rules live in `.claude/skills/terminal-layout/SKILL.md`, not here.

## Escape every third-party string before it reaches markup or a `DataTable`

Use `widgets/markup_safety.safe_markup`. Textual defers `Text.from_markup` into the message
pump, so a malformed name raises *outside* the screen's `try/except` and kills the app. Token
symbols are attacker-controlled: anyone can deploy an ERC-20 named `[/x]`. Analytics never
sanitises; escaping (or a `Text` with markup disabled) happens at the widget boundary, and a
brief's test that cannot pass under escaping is a brief defect.

## A widget that renders third-party text through `Static` hands it a pre-built `rich.text.Text`

Never a markup string. `Static.update("…[/x]…")` does not parse at call time — Textual defers
`Content.from_markup` into the message pump — so the parse failure raises outside the screen's
`try/except`. Parse it yourself, synchronously, inside your own `try` (`Text.from_markup(...)`)
and a malformed row degrades to a skipped row. `SurfFeed._row_text` is the worked example.
`Text.no_wrap` and `Text.overflow` are inert through Textual 8, and a *sized* cell is not a
*fitted* one (terminal-layout skill).

## Every displayed 0x address carries a copy icon, and so does every name that stands in for one

Render addresses only through `widgets/address.py`: `address_text` for an address or a name
backed by one, `address_prose` for third-party text that may contain addresses, `short_hex` for
any other hex such as a transaction hash (no icon). The icon is `⧉` with a Textual `@click`
action on the glyph only, calling `app.copy_address`, which `copy_action.CopyAddressMixin` runs
through `maxpane_dashboard/clipboard.py`: native tool first (`pbcopy`; Apple Terminal ignores the
OSC 52 that `App.copy_to_clipboard` writes), OSC 52 second, and the status bar says `copied`,
`unconfirmed` or `unavailable`. Validation is `fullmatch`, never `^…$` (`$` accepts a trailing
newline and the address is interpolated into an action string). The icon costs `ICON_COLS = 2`;
a panel grows where it has slack and shortens its displayed address where a pin would move; the
window rule (8/6 at 17 cells) is surf's anti-poisoning form.

**None of this is optional:** `tests/test_address_rule.py` fails on a private address formatter;
`tests/screens/test_address_icons_everywhere.py` fails on an address that reaches the screen
without its icon — rendering every case at 170 columns and again at each view's own layout pin
(plus any `extra_sizes` the case names, such as FWA's 120), because a defect that lives where a
panel is tight is invisible at 170; `tests/test_address_sweep_registry.py` fails on a dashboard
the sweep does not render. A new dashboard joins the sweep: add a `SweepCase` to `CASES` in
`tests/address_sweep/builders.py` — its screen class, a harness `build`, a `payload`, the `views`
that reach every body, and a hand-listed `seeded` tuple carrying at least one address in every
shape it renders. `address_free=True` is only for a dashboard that renders none, and the
agreement test refuses it the moment the dashboard's widgets import the helper.
`docs/address_copy_PRD.md` §7 spells out E1–E6. No test may reach the real clipboard:
`tests/conftest.py` replaces the runner suite-wide.

## Sparklines import `widgets/sparkline_common`

Do not copy the helpers. Its docstring lists the older copies not yet on the module.

## Screens inherit `screens/refresh_guard.RefreshGuard`

It gives skip-not-queue refresh and joins the startup prefetch. Do not hand-roll
`run_worker(..., exclusive=True)`. Workers are cancelled or invalidated on leave; no network
await inside a message handler.

## Reuse before you build

Almost nothing here is the first of its kind. Check, in this order:

1. **the genuinely shared modules** — `widgets/fmt.py` (the unknown markers, `as_float`,
   `fmt_eth`, ages, countdowns, points, percentages, `hhmm`/`mmdd`), `widgets/sparkline_common.py`,
   `widgets/markup_safety.py`, `widgets/address.py`, `widgets/status_bar.py`. Import them; never copy
   out of them.
   (`widgets/hero_metrics.py`, `leaderboard.py`, `activity_feed.py`, `signals_panel.py` are
   Bakery-only despite living at the top level — two import `data.models`, two are shaped for
   Bakery's payload, and all four are imported by `screens/bakery.py` only. Do not treat them as
   shared.)
2. **the dashboard's own `_fmt.py`** (`widgets/surf/`, `widgets/curator/` — each re-exports
   `widgets/fmt.py` and holds only its dashboard-specific formatters on top of it, such as
   `fmt_imd` or `fmt_eth_compact`; row fitting, the widen hints and the width-tier `Ladder` are
   shared in `widgets/rowfit.py`) and the
   sibling panel that already does the same *shape* of job. `widgets/surf/launchpad_activity.py`
   was built on `widgets/surf/activity.py` and inherited its width-tier ladder and its "the panel
   names the columns it shed" contract for free.
3. **`templates/`** — copy-sources for when there is no sibling to follow. A template can only
   be behind or ahead of the widgets copied from it; it never propagates. When you fix a widget,
   check its template, and check whether the template drifted *ahead* of the widget (the MEDI-38
   unavailable state in `hero_metrics_template.py` never reached the ocm/cattown/dota heroes).

The failure this prevents is **divergence**: three copies of one helper means a fix reaches one of
them. A private helper needed by two modules is hoisted to the package's shared module in the
same change — never re-declared. Ownership seams are for files, not functions. **Mandated
redundancy is the narrow exception:** a hand-typed copy that an agreement test binds
(`_GAME_CYCLE`, `--game` choices, `initial_game`, `MANAGER_ATTRS`, a widget restating a `data/`
tuple such as `POOL4_NETWORKS` / `POOL4_DISCOVERY_SOURCES`) is correct and must not be
"simplified" into a derivation, because the test would then compare a constant against itself.

The strip-then-escape sanitiser is `markup_safety.sanitize_cell` (flatten → `strip_tags` →
`rowfit.clip` on cells → `safe_markup`, in that order) since HANDOVER §3.2 was closed on 2026-09-19;
`strip_tags` alone is for a value that is never clipped. Do not re-declare either.

## Blank row under a title

The title margin rule lives in `themes/minimal.tcss` (`margin: 0 0 1 0`) and in widget
`DEFAULT_CSS`; do not add `Static("")` spacers for it.

## Testing widgets and screens

- **Assert against composited output** (`_compositor.render_strips()`), not the content string.
  A string that never reaches a pixel passes a naive test while being invisible to the user.
- **Prove a test bites** where the change is decoder- or concurrency-shaped, or moves a pin:
  mutate the code, watch the named test go red, restore by inverse edit.
- Screens are the expensive tier (0.3–1.3 s per composited case). Put content assertions in the
  widget's own test file; keep only composition and geometry in the screen file.
- No wall-clock waits in pilot tests: await an observable state (`_settle` helpers in
  `tests/screens/test_curator_screen.py`), bounded so a real regression still fails.
- A layout pin is certified by an in-situ sweep with the geometry invariants (region overflow,
  hidden `DataTable` columns, clipped lines, wrap-shed flags), never by a guess; a change to a
  cell's contents is a change to a pin — re-sweep (terminal-layout skill).
