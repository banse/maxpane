# AGENT card adjustments

Approved request: 2026-10-13. Tier 2 because the primitive AGENT hero contract
changes and rendering may need a narrowly scoped shared digit extension. The
existing twelve-card, two-row rack stays in place. Target less than 1,000 changed
production lines; one final review, no package reviews, and no full test suite.

## Required behavior

| Card | Inner content and border | Outer footer |
| --- | --- | --- |
| SEAT | Keep the selected IDMD seat digits. Replace selection wording with `online`, `working`, or `offline` from worker presence. Online/working border and border text are green; offline is red. Unknown presence remains neutral and explicit. | `AGENT #x`, using the ERC-8004 registration ID, never the IDMD seat number as a substitute. |
| ACCEPTED | Group accepted digits with a thousands separator, show `of 3,405` for attempts, and always use the neutral inset border/text. | Existing acceptance percentage followed by a track that consumes the available footer width. |
| EFFORT | Preserve hours/tokens; always use the neutral inset border/text. | Preserve the normal semantic footer. |
| REWARDS | Preserve the existing reward amount and USD calculation. Green border/text only when a confirmed payout occurred less than 24 hours ago; neutral otherwise. | Time of the latest confirmed payout, or an explicit unknown value if no timestamp is available. |
| RANK | Preserve canonical rank and population. Green on improved rank, red on worse rank, neutral on unchanged/unknown. | Existing rank-change semantics: arrow and number of places gained/lost. Do not invent a movement on the first read. |
| STATUS | Replace the working/capacity/devices list with large `0 OF 3`: active slots, static gray `OF`, capacity. Use the boardroom AGENT card's state coloring. | Reuse boardroom label and activity-meter behavior, with the track occupying available width. |

All twelve visible cards omit stale wording, including the USD stale suffix.
Keep independent source clocks and freshness states in data; removing visual
status labels must not convert old facts into successful reads or fabricate
zeros. Genuine in-flight requests show a loading indicator; failed requests
remain distinguishable from loading, and unknown/unpaired seats remain genuine
negative states. Preserve card actions and address copy/explorer behavior.

STATUS inherits the corrected boardroom activity behavior: busy is full green;
idle drains green into orange over the first 24 hours, then orange into empty
through 72 hours. Missing last-work evidence is not a full orange bar. Offline,
paused, unknown, and failed reads retain the established boardroom semantics.
A paused worker still counts as online for SEAT, with its idle activity meter
unchanged; the STATUS caption and tooltip retain the pause-until time.

## Data contract and source decisions

Contract frozen before implementation dispatch:

- `SURF_AGENT_HERO_FIELDS['seat']` adds `agent_id` only. The UI obtains presence
  from the same payload's STATUS worker presence rather than its activity history.
- `SURF_AGENT_HERO_FIELDS['rewards']` adds `last_paid_ts` and `paid_recent`.
- `SeatRewards` adds optional `last_paid_ts=None`; old cache entries remain
  readable when this field is absent.

Existing `state`, `read_ts`, USD provenance, and activity meter primitives remain
intact. Facts cross the widget boundary as primitives only; widgets never import
data modules or read clocks/network.

- Registration ID already exists in normalized selected-seat/detail data as
  `agent_id`, a string. Preserve that identifier and validate selected identity.
- Worker presence already reaches the STATUS facts. Reuse the same confirmed
  presence for SEAT; incomplete worker absence cannot establish offline.
- Rank exposes a signed `delta` with previous rank minus current rank. Positive
  means improvement. The legacy baseline retains the last nonzero movement, so
  the controller adds a hero-only per-token comparison keyed by confirmed
  records `read_ts`: cached repaints retain the displayed arrow, while the next
  successful unchanged read yields zero. Leave legacy consumers unchanged.
- Payout time must come from actual reward evidence, not reward-read time,
  accepted-job time, an observed balance change, or market-read time. Reuse the
  current rewards read, which already parses timestamps for verified Blockscout
  transfers but discards them. Retain the latest timestamp from a positive,
  verified payment and carry it through the existing reward cache and projection.
- Compute 24-hour recency using injected `now` in projection. Future, malformed,
  and missing timestamps cannot activate green. No additional endpoint, request,
  or poll fan-out is needed.
- Pending must reflect a real unfinished read, including the initial cold load;
  retained data and completed failures must not become permanently loading.

## Work packages and ownership

1. **Controller: freeze contract and source facts.** Own this plan,
   `maxpane_dashboard/data/surf_models.py`,
   `maxpane_dashboard/data/surf_manager.py`, and their manager/contract tests.
   Add the frozen model fields, hero rank comparison, reward cache propagation,
   and truthful loading metadata. Communicate the exact pending-source mapping
   to the data implementer. Dependencies: none.
2. **Data implementer: project the new facts.** Own
   `maxpane_dashboard/data/surf_client.py`,
   `maxpane_dashboard/data/surf_swarm.py`,
   `maxpane_dashboard/data/surf_agent_hero.py`, and their directly corresponding
   data tests. Retain verified payout timestamps and extend optional cache
   normalization. Add regression tests first for identity, reward boundaries,
   and real pending states. Keep canonical rank, acceptance arithmetic, and
   source isolation intact. Depends on package 1's frozen contract; root and
   implementer may work concurrently in these disjoint files.
3. **UI implementer: render all twelve cards.** Own
   `maxpane_dashboard/widgets/surf/agent_rack_hero.py` and
   `tests/widgets/test_surf_agent_rack_hero.py`. Add composited output/color tests
   first, then the smallest formatter/footer/digit changes. Reuse boardroom
   meter rendering. Request shared-file changes from the controller instead of
   editing another owner's file. Depends on package 1; may run in parallel with
   package 2 because these file sets are disjoint.
4. **Controller: integration, live render, and hardening.** Own composing
   manager/screen tests, any shared digit/formatting extension, layout pin work,
   follow-ups, and final verification. Check true cold-loading and per-seat cache
   identity. Render real keyless data at 149×45 and show it before layout sweeps,
   pin documentation, or review. Then complete scoped tests, mutation proof,
   and the single final review. Depends on packages 2 and 3.

Every implementer works in the shared tree, preserves others' changes, and
reports defects outside their owned files. No implementer spawns subagents.

## Verification and delivery

- Data regressions: ERC-8004 ID differs from seat ID; fresh idle/working/offline
  and incomplete workers; actual payout at 23:59, exactly 24h, future/missing;
  positive/negative/zero/unknown rank delta; pending versus finished failure;
  unchanged old values do not refresh source clocks.
- Composited UI checks: no visible stale label in any of the twelve cards;
  loading does not paint unavailable; default ACCEPTED/EFFORT borders; grouped
  accepted digits; reward/rank border colors; gray static `OF`; full available
  acceptance/activity tracks; boardroom STATUS state and bar parity.
- At 149×45 verify twelve equal cards, content fitting, arrows, comma glyph,
  STATUS group spacing, footer width, and existing record table/actions. Sweep
  affected native AGENT layout boundaries only after the live render; update
  pins only when measured geometry requires it.
- While editing, run only changed cases and their immediate consumer checks.
  Before commit, run touched test files and composing manager/screen files once,
  plus `pytest -m 'guard and not mounts_app' tests`, using the project venv and
  `env -u NO_COLOR`. Tests stay offline. No registration checks unless a key or
  binding actually changes.
- Use `scripts/mutate.py` for focused contract/loading/color behavior proof;
  restore mutations by inverse edit, preserving other work.
- One final reviewer receives the scoped whole change after the live render.
  At most one final fix wave and one scoped re-review when production changes.
  File Minor findings instead of expanding scope. Record evidence in the commit
  and report the completed behavior and remaining concrete limitations.

No additional user decision is required. The existing request fixes the design;
routine wording, unknown-state handling, and implementation ownership are resolved
within these constraints.

## Completion evidence

- Keyless native 149×45 Matrix render shown with seat 420: registration 50939,
  3,264 accepted of 3,405, idle 0 of 3, and the verified latest payout time.
- Native capture/capture420/stress sweeps measured width 132 (STATUS activity
  caption clips at 131); height remains 29. Narrow REWARDS footers retain the
  entire date/time by dropping only the `paid ` prefix.
- Combined touched/composing run: 1,387 passed and three stale test expectations
  failed. Corrected those expectations, including the existing WORK/ORACLES
  widget registrations; subsequent affected-file run: 178 passed.
- Sixteen implementation mutations killed across timestamp verification,
  pending/rank behavior, UI formatting, and both directions of the width pin.
  Final review approved with 21 focused tests and another pending mutation.
  Its additional STATUS check confirmed the grey separator in compact/unknown
  fallback output too. No remaining findings; no full suite was run.
- Final fast guards: 124 passed. Documentation pins: 12 passed. Diff whitespace
  checks are clean; unrelated working-tree files remain untouched.
