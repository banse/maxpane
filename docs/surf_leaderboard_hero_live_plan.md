# LEADERBOARD / SURFBOARD live hero integration — proposal 1

## Approved scope

The owner accepted proposal 1 and the revised RECORDED card: large seat-count
digits with attempts below. Connect that approved layout to the existing BOARD
sources. Keep six equal nine-row cards at **149 columns × 45 rows**, in order:
TOP SEAT, RECORDED, ACCEPT RATE, OUTCOMES, WORKERS and EFFORT. Preserve the native
leaderboard and fleet body, table interactions, other dashboard modes and the
standalone fictional mockup.

This is Tier 2, below 1,000 production lines, with one final review and no package
reviews. Reuse existing records, worker and contributor requests and scheduling.
No new API, endpoint, credentials or persisted cache format is needed. Superpowers
remain disabled. Root owns the data contract and integration seams.

## Frozen primitive contract

Add `surf_leaderboard_hero` to `SURF_KEYS` beside the other hero projections.
The existing contiguous `SWARM_KEYS` block remains unchanged.
Keep class `SurfSwarmBoardHero` and its existing mode/dispatch ownership; change
its signature in `SWARM_WIDGET_SIGNATURES` to `("surf_leaderboard_hero",)`.
Its method is `update_data(*, surf_leaderboard_hero=None, **kwargs)`.

The pure projection is `project(*, data, sources, now)` in new
`data/surf_leaderboard_hero.py`. `data` contains the existing canonical
`swarm_board_rows` and `swarm_board_summary`. `sources` contains independent
`records`, `workers` and `contributors` envelopes with `state` and `read_ts`.
The workers envelope additionally carries boolean `partial` for incomplete
roster coverage, including when the source is stale.

```python
SURF_LEADERBOARD_HERO_STATES = ("ok", "partial", "stale", "unavailable")
SURF_LEADERBOARD_HERO_FIELDS = {
    "top": ("state", "read_ts", "token_id", "accepted", "rank", "empty"),
    "recorded": ("state", "read_ts", "seats", "attempts"),
    "rate": ("state", "read_ts", "accepted", "attempts", "percent"),
    "outcomes": ("state", "read_ts", "rejected", "failed", "pending"),
    "workers": ("state", "read_ts", "live", "working", "capacity"),
    "effort": ("state", "read_ts", "receipts", "turns", "hours"),
}
```

Every section and field is present on every update. All values are primitives.
Counters and seat IDs are nonnegative integers, excluding booleans. Percent and
hours are finite nonnegative numbers. Timestamps are finite positive observation
epochs no later than injected `now`. Unknown values remain `None`; zero is a
valid reading. Pure helpers perform no I/O or clock reads.

## Source meanings and projection

- TOP SEAT uses the canonical row whose `rank == 1`, not the selected seat,
  current table sort or `/contributors` ranking. `empty=False` accompanies a
  valid top row. A proven empty canonical set uses `empty=True`, no seat/rank/
  accepted values, and a healthy source state; render `no recorded seats`.
  Unread records use `empty=None`, never an inferred empty board.
- RECORDED uses summary `seats` and `attempts`. These are distinct recorded seat
  IDs and cumulative recorded attempts, not wallets, all enrolled agents, jobs
  completed or a 24-hour count.
- ACCEPT RATE uses canonical summary `accepted / attempts * 100`. Known
  `accepted=attempts=0` yields `percent=None` and `no attempts`, a valid state
  rather than partial or 0%. Zero accepted with positive attempts is genuinely
  0%. Invalid relationships cannot produce a healthy percentage.
- OUTCOMES uses summary `rejected`, `failed` and `pending`. Do not merge failed
  and rejected or substitute contributor receipt counters.
- WORKERS uses summary `live`, `working` and `capacity`. Live is the served
  worker count, not a row count; working/capacity are concurrent slot sums, not
  distinct agent counts. If the roster's served count differs from normalized
  row count or it contains malformed tokens, keep a known served live value but
  leave incomplete working/capacity totals unknown. The source coverage flag
  must survive stale state. A complete empty roster can truthfully show zeros.
- EFFORT uses contributor summary `receipts`, `turns` and
  `wall_clock_ms / 3_600_000`. These are independent contribution metrics, not
  canonical outcomes or elapsed runtime of a single worker. Malformed contributor
  accounting already leaves aggregate effort unknown while served receipts may
  remain readable; preserve that partial information.

The first four cards depend only on records, WORKERS only on workers, and EFFORT
only on contributors. A failed source cannot erase or stale another source's
cards. Readable stale values remain explicitly dated. A fresh source with some
missing required facts is partial; no usable facts is unavailable. Staleness
takes precedence over missing-field partial state when values survive. The
known-empty top and zero-attempt rate cases are deliberate exceptions to counting
nullable fields as missing.

## Capture and freshness integration

Root adds the projection to `_swarm_board_keys`, so both `_project_hub` and the
full cycle publish it with the same canonical summary/rows. Capture each source
envelope beside the exact entry used for those values, before detached work is
offered. Do not capture entries and later re-read newer metadata to date them.

Records already supplies a complete independent `swarm_outcomes_source` envelope;
preserve its success/failure and source age. Contributor and worker version clocks
currently advance only when payload changes, while `TIER_SWARM_BOARD` records
joint success/failure. That shared tier cannot identify which endpoint failed.

Root chooses a uniform **two-entry manager-memory observation map** for workers
and contributors. Update it at each existing normalized read, retaining the
successful read time, latest attempt result and linkage to the matching
entry/version. Do not normalize the same result again. Failed reads retain the
last-good clock; unchanged successful reads may advance confirmation time. Capture
these observations beside the entries before `_spawn_swarm_board`.

On restored caches without a matching runtime observation, retain values with
their version timestamp conservatively as stale until an existing request
confirms them. This avoids a persisted schema change and keeps both sources on
the same simple path. `SLOT_SURFBOARD_ACTIVITY` already has worker attempt clocks,
but its extra historical semantics need not enter this hero's observation map.
In particular, do not use its `complete` flag for current roster coverage: bounded
historical retention can make it false independently of the current worker list.

Never use global refresh time, a sibling endpoint's success, table interaction or
a failed attempt to freshen a card. Keep existing board scheduling untouched.

## Rendering and ownership

Use the existing `HeroRecord` and `Pool4HeroCard`/`LocalSourceHeroCard` support for
partial and stale local-clock footers. Keep the approved titles, inner labels,
numeric/list content and footers. RECORDED remains large digits with attempts
below. Known values stay visible beside unknown neighbors, and every update
paints all six cards. Distinguish no seats, no attempts, zero, partial and outage.
Use compact formatting without turning nonzero percentages/hours into false zero.
No widget imports from `data/`.

1. **Planning agent:** only this new plan; no implementation or subagents.
2. **Data worker:** new `data/surf_leaderboard_hero.py` and new
   `tests/data/test_surf_leaderboard_hero.py`, implementing the frozen pure seam.
3. **Widget worker:** existing `widgets/surf/swarm_board_hero.py` and its focused
   widget test file assigned by root. Convert its old six-box `HeroRow` to the
   approved rack grid without changing native table/fleet behavior.
4. **Root:** `data/surf_models.py`, manager capture/projection, manager/contract
   tests, screen and theme CSS, composing/layout tests, live capture, layout
   measurements and follow-up docs. Root freezes the signature before parallel
   workers proceed and is the sole owner of shared files.

Data and widget work are independent after contract freeze; integration depends
on both. Preserve concurrent work and report cross-owner issues. Layout tests
remain root-owned and are hardened only after the live preview.

## Verification and delivery

- Begin with focused failing tests and use no test network or real clipboard.
  Cover the frozen field/signature agreement, known zeros/empty board, 0/0 versus
  0/N rate, invalid counters/clocks, partial source fields, retained stale values,
  canonical top selection, incomplete workers and independent contributor effort.
- Prove successful unchanged reads, per-endpoint failures/recovery, restored
  fallback and detached completion cannot misdate or cross-degrade another
  source. Use one targeted reversible source-clock mutation where appropriate.
- Verify actual compositor output at 149×45: six nine-row cards, approved content,
  units, source states/clocks, common baseline and readable native body. Exercise
  table sorting, mode switching, narrow scrolling/resizing and recovery.
- Show the owner the **live production render at 149×45 before** re-sweeping pins,
  writing layout evidence blocks/hardening docs, or dispatching the final review.
  This planning document precedes the gate. Temporary capture files stay out of Git.
- Then measure the actual BOARD boundary through the existing `b` layout sweep
  (current pin 141×33 is a starting point, not a promised result), update only
  evidence-backed pins/`#:` blocks, and mutation-prove changed geometry assertions.
- Before commit, run touched/composing files once with isolated HOME and
  `-n 4 --dist worksteal`, fast `guard and not mounts_app` checks and applicable
  docpins. No full suite without an owner request.
- One final independent review, one fix wave and one scoped re-review only for
  production fixes. File Minor-only residuals; root commits the verified result
  before progressing to the next dashboard's proposals.
