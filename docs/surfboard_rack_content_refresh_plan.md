# Surfboard rack content refresh specification and plan

Date: 2026-10-13. Tier 2: the plain card contract gains a field and several rack
components change. Expected scope is below 1,000 production lines: no package
reviews, one final review. The owner's screenshots and latest instructions are
the specification; this is the existing Python/Textual/Rich application. There is
no `ai/memory-bank/site-setup.md` in this repository. No new API source is needed.

## Approved behavior

1. **TOKENS:** replace up/down triangles with green `↑` and red `↓`. The owner
   explicitly chose **“Consecutive loads (keep current rule)”**; first, equal,
   missing, or incomparable prices remain neutral. Preserve the existing stable
   volume ranking and pool-aware price comparisons. The outer footer becomes
   `NEWEST BITES 3h`, in the order `NEWEST {symbol} {age}`, with exactly one
   separator space. The inner footer shows the positive last-24-hour launch
   population as `x new`; preserve the standing rule that zero shows no text.
   Remove partial/stale/source-time text from this inner footer. Unknown counts
   remain explicitly unavailable, never a fabricated zero. Keep source evidence
   in the literal tooltip.
2. **Central terminal:** remove automatic stale labels wherever the terminal
   paints them, including header/footer, compact variants, and generated status/seat command summaries. Remove `V* P* D*`
   service flags at every width. Preserve the metrics, event log, command input,
   update age, and underlying source metadata. This explicit owner instruction
   changes the visible stale-label policy for this terminal; do not remove
   unavailable states or rewrite third-party event text containing these words.
3. **LEADERBOARD:** inner title `TOP AGENTS`; three aligned rows containing a
   leading Unicode `★`, seat number, and accepted-job count. Color the stars
   gold, silver, and bronze in rank order. Use canonical leaderboard ranking,
   independent of live worker order. Preserve the outer activity footer for the
   first-ranked agent. Known empty and unavailable sources stay distinguishable.
4. **PROTOCOL:** replace the outer `BURN` label and segmented meter with
   `x% of supply burned`, using the existing computed supply percentage. Keep
   its precision and source qualification; unknown supply remains unavailable.
5. **Empty AGENT seats:** restore neither a green input border nor extra boxes.
   Keep the current inset and borderless input. Put a centered `↑` on the line
   below the input, change the inset bottom prompt to `type in`, and replace the
   outer `EMPTY` plus meter with `Identity.md NFT`. Assigned seats retain their
   existing behavior, styling, navigation, and independent caches.
6. **Below the side cards:** show `キープ` on the left and `ビルディング` on the
   right. Focused discovery found the start screen's tagline uses phonetic
   Katakana, centered in `$text-muted`, without a translation animation. Use
   those same static presentation conventions in the available side space,
   without shrinking the central terminal or making card heights unequal.

## Frozen plain-data contract

Root adds `top_agents` to `SURFBOARD_CARD_FIELDS` and its literal agreement test
before independent renderer implementation. Every card has this field; it is
`None` outside the leaderboard. For the leaderboard:

```text
top_agents: None | [] | up to three {rank, token_id, accepted}
rank: canonical integer rank 1..3, in ascending order
token_id: validated canonical agent seat number
accepted: known nonnegative accepted-job count, or None when unknown
```

`None` means unavailable; `[]` means known empty. Do not rank by currently active
workers or promote a lower rank because an activity read is missing. Missing
accepted counts render as unknown, not zero. Existing activity fields continue
to describe rank one. No widget imports `data/`.

No other new card field is required: TOKENS uses `token_ranking.total` for its
last-24-hour count, and PROTOCOL reuses its existing `secondary` supply text.
Underlying ranking state/read timestamps and price baselines remain unchanged.

## Work packages and exclusive ownership

All owners preserve other work and report defects in another owner's files.
The planner owns only this document. Production paths below are relative to
`maxpane_dashboard/`; test paths are repo-relative.

| Package | Owner and files | Dependencies and acceptance |
|---|---|---|
| WP0: projection and contract | Root: `data/surf_models.py`, `data/surfboard.py`, `data/surf_manager.py`, related data/contract tests | Freeze the field first; project canonical top three and the last-24-hour token count without changing ranking or network behavior. |
| WP1: rack card rendering | Rack worker: `widgets/surfboard/rack.py`, related rack/activity/seat widget tests, `tests/surfboard_fixtures.py` | Starts after WP0 contract freeze; implements all five card changes with aligned literal-safe text and compositor assertions. |
| WP2: terminal labels | Terminal worker: `widgets/surfboard/terminal.py`, `tests/widgets/test_surfboard_terminal.py` | Independent of WP0/WP1; suppress automatic stale labels and service flags at all widths while preserving metrics and controls. |
| WP3: translated side text and integration | Rack worker: caption placement in `rack.py`; root: `screens/surfboard.py` and screen tests | Add static centered muted Katakana labels using the start-screen conventions. Rack ownership returns to root after WP1 for measured column sizing. Integrate after WP1/WP2. |
| WP4: evidence and completion | Root: measured layout records and required documentation/follow-ups | All packages integrated, then live preview before layout hardening and the single final review. |

WP1 and WP2 may run in parallel once the contract is communicated. WP3 needs no
new shared component or start-screen modification. If the rack needs placement
hooks, its worker adds them or explicitly hands the whole file back to root.
Reserve side-column space only if needed; the terminal keeps its full height.

## Verification and completion

- Write failing focused tests before changing each behavior. Test canonical top
  three order and accepted counts, unknown/empty data, count provenance, unchanged
  consecutive-load semantics, and the card contract agreement.
- Assert composited strips for arrow characters/colors, exact footer separators,
  absent status/service labels at compact and wide sizes, ranked star colors and
  column alignment, protocol footer, and empty-seat input/arrow/prompt placement.
  Include literal markup, wide tickers, and address copy/explorer behavior in the
  changed newest footer. Preserve meaningful clipping markers.
- Check the side words match the start screen's static Katakana presentation,
  remain under their respective columns, and do not change card equality or the
  terminal's remaining-height allocation.
- Once the integrated UI works, show the owner a **real keyless live render at
  149×45**. Do this before re-sweeping pins, editing `#:` blocks, hardening layout
  docs, or dispatching review. Incorporate any correction in the same work.
- Then verify minimum/adjacent dimensions in situ with normal, long, empty, and
  unavailable payloads. Measure rather than guess any changed pin; update its
  boundary tests and `#:` derivation only when required. Use `scripts/mutate.py`
  for changed decoder or pin gates, including both pin directions if one moves.
- Before commit, run touched test files and their composing manager/screen files
  once with isolated test home and `-n 4 --dist worksteal`; unset `NO_COLOR` for
  color/render checks. Run `guard and not mounts_app` and the required doc-pin
  checks. All tests stay offline and never touch the real clipboard. No full
  suite or registration mount set unless the project rules require it.
- Dispatch one final review with the repository's verbatim reviewer contract.
  Allow one fix wave and a scoped re-review only for production fixes. File
  Minor-only residuals, record relevant verification in the scoped commit, and
  leave unrelated files untouched.

## Measured integration

The live keyless render was shown at 149×45 before hardening. Public reads gave
30 eligible launches, volume leaders SNITCH/SCOOP/PUPATE, and accepted-job leaders
527 (4,184), 1207 (4,156), 355 (4,142). These are capture observations, not constants.
PROTOCOL reserves 29 columns for the full stress footer; POOL4 reserves 23 and
the other columns share the remaining width. Cards retain equal heights and the
terminal retains its full center height. The measured rack pin is 148×35; the
app-wide pin stays unchanged. Captions use existing spare rows and hide when
none remain. Source metadata stays intact while requested visible qualifiers
are removed. Consecutive identical prices retain the neutral dash.
