# Sworn implementation plan

2026-10-23 · Tier 2 · approved [PRD](sworn_PRD.md).
One controller owns shared integration; one implementer owns each disjoint
package. No subagent spawns subagents. Preserve unrelated working-tree changes.

Target approximately 900 production lines by reusing lifecycle, panels, hero,
address and popup components. Tests, fixtures and docs are additional. Packages
get no separate task review while the whole production change remains below
approximately 1,000 lines; one final review covers the integrated change. If
implementation materially exceeds that estimate, the controller revises sizing
and review coverage before treating the exception as applicable.

Delivered: approximately 1,000 new production lines plus small registration
edits (about 860 nonblank/noncomment lines), retaining the final-review-only
package sizing. Live previews were shown before responsive hardening. Final
review approved with no findings; validation and terminal-visual follow-up are
recorded in `sworn_validation_2026_10_23.md` and `sworn_followups.md`.

## Dependency graph

```text
WP0 frozen contracts / verified source
             |
      +------+------+
      |      |      |
     WP1    WP2    WP3
     data   art    UI
      +------+------+
             |
       WP4 integration
             |
     live 149x45 render
             |
     hardening / review / commit
```

WP1–WP3 may run in parallel only after WP0 freezes the shared payload and art
interface. They may read each other's files but must report defects to the owner
instead of editing them. The controller integrates dependent changes in WP4.

## WP0 — freeze interfaces and source identity

**Owner:** controller. **Files:** `maxpane_dashboard/data/sworn_models.py`, and any source-provenance fixture
shared by later packages. Estimate 60 production lines, excluding ABI data.

Before dispatch:

- Read the current site manifest and Registry getters on chain 1; record the
  expected Registry, Renderer, Composer, source commit and observation block.
- Vendor only necessary read-only ABI entries from the pinned source. Check
  sequential-ID/no-burn assumptions against that implementation before paging.
- Frozen payload keys in `sworn_models.py`: `sworn_supply`, `sworn_rows`,
  `sworn_selected`, `sworn_selection`, `sworn_error`, `sworn_block`,
  `sworn_observed_at`. `SwornExplorer` accepts these keys. Selected-card fields:
  `token_id`, `claimant`, `holder`, `minted_at_block`, `metadata`, `art`, `block`,
  `observed_at`. Preserve bounded onchain metadata, including attributes, traits,
  community IDs and oracle evidence, as primitives.
- Frozen intent API: `select(value: str | None)` accepts decimal token ID or
  original claimant address; `None` selects latest. The manager supplies a
  newest-first page of at most 20 IDs around the selected token. No separate
  paging command. UI supplies intent; manager performs I/O. Latest selection wins.
- Frozen art seam: `prepare_art(svg) -> dict` returns base64 `png`, 128×128 RGB
  hex-string `pixels` and content `hash`; `SwornArt.update_art(dict | None)`
  receives it. `probe_terminal_graphics()` runs after the intro and returns
  `kitty`, `cell_width`, `cell_height`, stored as `app.sworn_graphics`.
  Controller owns dependency additions (`resvg_py==0.5.0`, Pillow >=11,<14).

**Acceptance:** WP1 and WP3 can independently build against the same contract;
no widget needs a data import and no guessed deployment value is a live metric.

## WP1 — bounded read pipeline and cache

**Owner:** data implementer. **Exclusive files:**

- `maxpane_dashboard/abis/sworn_registry.json` (read-only ABI, if needed)
- `maxpane_dashboard/data/sworn_client.py`
- `maxpane_dashboard/data/sworn_cache.py`
- `maxpane_dashboard/data/sworn_manager.py`
- `tests/data/test_sworn_client.py`, `test_sworn_cache.py`, `test_sworn_manager.py`
- `tests/fixtures/sworn/` data fixtures, except WP0's explicitly reserved fixture

Estimate 300 production lines. Depend on WP0; call WP2 only through the frozen
art-preparation interface. Reuse an existing RPC client/transport where suitable.

1. Start with failing fixture tests for authentic tokenURI decode, helper mismatch,
   claimant/holder separation, metadata community truncation and malformed data.
2. Implement cheap supply/page reads and selected-first token/fact reads. Bound
   parallel requests; never enumerate every tokenURI on each refresh. Resolve
   address searches through claimant `tokenOf`, with a real zero representing
   an unminted claimant and `None` representing a failed read.
3. Persist validated snapshots keyed by chain/Registry/token, using injected time.
   Reuse cached artwork by content hash. A changed SVG invalidates derived art.
4. Return primitive payloads; preserve source timestamps when refreshes fail.
   Prove a superseded selection cannot repaint as the active selection.

**Acceptance:** deterministic offline tests demonstrate bounded request counts,
cache reuse, bad-cache rejection, truthful missing values and selected-card
refresh. Mutate decoder/selection conditions and show named tests fail.

## WP2 — artwork preparation and display adapter

**Owner:** graphics implementer. **Exclusive files:**

- `maxpane_dashboard/data/sworn_art.py` for reader-side rasterization
- `maxpane_dashboard/terminal_graphics.py` for pre-Textual capability probing
- `maxpane_dashboard/widgets/sworn/art.py` for prepared-art display
- `tests/data/test_sworn_art.py`, `tests/widgets/test_sworn_art.py`
- `tests/fixtures/sworn_art/` authentic bounded SVG/raster fixtures

Estimate 180 production lines. Depend on WP0. Any new dependency is proposed to
the controller; only the controller edits `pyproject.toml` or startup plumbing.

1. Test decode limits, square fitting and actual SVG palette/geometry against a
   committed authentic-card fixture. Use the same raster for graphic and text
   paths; no independent artistic redraw and no synthetic card in live data.
2. Rasterize/encode on the reader side. Widget paint receives prepared data and
   does no network, SVG parsing or image encoding. Reuse rendered strips/art
   until content or viewport dimensions change.
3. Provide a reliable character fallback. Add high-fidelity terminal placement
   only through an adapter whose probing occurs before Textual starts and whose
   resources are owned and cleaned on replace, suspend and unmount. Unsupported
   graphics never prevents opening the dashboard on Python 3.11.

**Acceptance:** no import-time input probe; no UI-thread raster work; resize
preserves aspect without cropping; popup close/navigation removes owned images.
State clearly which terminal-graphics modes received actual visual verification.

## WP3 — Explorer and detail popup

**Owner:** UI implementer. **Exclusive files:**

- `maxpane_dashboard/screens/sworn_screen.py`
- `maxpane_dashboard/widgets/sworn/__init__.py`
- `maxpane_dashboard/widgets/sworn/explorer.py`
- `maxpane_dashboard/widgets/sworn/details.py`
- `tests/screens/test_sworn_screen.py`
- `tests/widgets/test_sworn_explorer.py`, `test_sworn_details.py`

Estimate 300 production lines. Depend on WP0 and frozen WP2 display interface.
Keep dashboard-specific styles in these modules; shared theme edits belong to
the controller. Read the terminal-layout skill before sizing components.

1. Test four heroes, selected-art pane and fact pane via composited strips.
   New panels use `Panel`; screen uses `DashboardScreen` and declarative PANELS.
2. Implement bounded list selection and token/claimant search, with the implicit
   page around the selection. Search
   remains editable during reads. Use existing safe table text and shared
   address links/copy icons for claimant and holder.
3. Wire row `»` and keyboard detail action to a large existing-style popup with
   dominant artwork and scrollable facts/community/evidence. Dismissal preserves
   selection and cached data. Do not implement a second data-loading loop.
4. Reuse shared status/loading footer. Ensure all empty/loading states compose
   without synthetic values, stale/unavailable banners or missing widgets.

**Acceptance:** offline pilot tests cover input during reads, selection, popup
open/close, claimant-versus-holder output and source detail. No network or real
clipboard; bounded observable-state waits instead of sleeps.

## WP4 — registration, real render and acceptance

**Owner:** controller. **Exclusive shared files:** `app.py`, `__main__.py`,
`screens/game_select.py`, `pyproject.toml` if required, shared theme/startup files
only if necessary, README, CLAUDE.md dashboard inventory, registry rules, and
shared registration tests. Estimate 60 production lines.

1. Add manager/ReaderRuntime integration and append `sworn` as game 10. Update
   app wiring, then CLI, then GAMES; preserve `surf` defaults. Grow ALL_GAMES and
   all four MANAGER_ATTRS copies so mounted tests never use the real manager.
2. Add the new screen to applicable lifecycle/dispatch registration fixtures.
   Verify reader requests stop when hidden, polls do not overlap, and cached
   return restores selection. Do not invent another reader thread or timer.
3. Render actual keyless data in main and popup at 149×45 and show the owner
   before hardening. Record measured initial/cached fetch timing and request
   counts; diagnose any read exceeding its poll period without queueing work.
4. Harden only after that render: layout sweep/pin comments if introduced,
   address checks, focused decoder/concurrency mutation proof, and real supported
   terminal cleanup/resize verification.
5. Run touched and composing files once with isolated HOME and `-n 4 --dist
   worksteal`; fast guards; docpins; mounted registration guards named in
   CLAUDE.md. Do not run the full suite. Dispatch one final whole-change reviewer
   with the verbatim reviewer contract and named risks. One fix wave and scoped
   rereview if production changes; file Minor-only findings in follow-ups.
6. Commit explicit changed paths locally. Report the start command, supported
   artwork modes, actual checks and any remaining measured limitations.

## Explicit boundaries

No gallery body, mint workflow, wallet-wide owned-inventory indexer, market data,
ENS subsystem, historical event database or collection-wide trait scan. Do not
broaden shared reader/image architecture for hypothetical future dashboards.
The high-fidelity adapter must not make Apple Terminal or Python 3.11 unusable.
If a terminal capability is unavailable, deliver and verify the same-art fallback
and describe that fidelity limit rather than claiming the pixel path was tested.
