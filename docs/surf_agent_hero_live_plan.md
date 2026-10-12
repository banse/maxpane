# AGENT / SURFBOARD live rack integration — proposal 4

## Approved scope

Connect the owner's approved `scripts/surf_agent_hero_demo.py` layout to existing
AGENT data: two rows of six equal nine-row rack cards, with a one-row gap, at
**149 columns × 45 rows**. Row one is SEAT, ACCEPTED, EFFORT, REWARDS, RANK,
STATUS; row two is OWNER, RUNTIME, MODELS, FEEDBACK, COLLAB, NODES. Keep the
native RECORD table, filter/more controls, seat selection, saved rack seats and
per-seat caches. RECORD uses the remaining space below the cards.

This is Tier 2, targeting fewer than 1,000 production lines, with one final
review and no package reviews. Superpowers remain disabled. Use existing reads
and scheduling: no new endpoint, request fan-out, polling loop, credential or
persisted cache schema. The standalone fictional demo remains available.

## Frozen primitive contract

Root adds `surf_agent_hero` to the manager payload and freezes
`SurfSwarmAgentRackHero: ("surf_agent_hero",)` in the SWARM widget signatures.
The new widget exposes `update_data(*, surf_agent_hero=None, **kwargs)`.
The pure projection is `project(*, data, sources, now, activity=None)` in new
`data/surf_agent_hero.py`. It performs no I/O, reads no clock, and creates no
manager. Every section and field below is present on every update.

```python
SURF_AGENT_HERO_STATES = (
    "ok", "partial", "stale", "unavailable", "pending", "busy",
    "unknown_seat", "stale_unknown_seat", "empty",
)
SURF_AGENT_HERO_FIELDS = {
    "seat": ("state", "read_ts", "token_id", "selected_by", "read_error"),
    "accepted": ("state", "read_ts", "listed", "accepted", "attempts", "percent"),
    "effort": ("state", "read_ts", "listed", "hours", "output_tokens"),
    "rewards": ("state", "read_ts", "imd", "usd", "seats", "usd_state", "usd_read_ts"),
    "rank": ("state", "read_ts", "listed", "rank", "ranked_of", "delta"),
    "status": ("state", "read_ts", "live_state", "working", "capacity", "devices",
               "paused_until_ts", "failures", "last_work_ts", "last_work_kind",
               "work_state", "work_read_ts", "meter_kind", "meter_state",
               "numerator", "denominator"),
    "owner": ("state", "read_ts", "address", "name", "paired_ts"),
    "runtime": ("state", "read_ts", "runtime", "daemon", "devices", "update_state",
                "latest_version", "checked_ts", "fleet_daemon", "fleet_count",
                "fleet_total", "daemon_differs"),
    "models": ("state", "read_ts", "rows"),
    "feedback": ("state", "read_ts", "sent", "submitted", "queued"),
    "collab": ("state", "read_ts", "count", "rows"),
    "nodes": ("state", "read_ts", "rows"),
}
SURF_AGENT_HERO_ROW_FIELDS = {
    "models": ("model", "effort"),
    "collab": ("token_id", "shared_jobs"),
    "nodes": ("node_key", "accepted", "attempts"),
}
```

Rows are primitive dictionaries; `None` is unread and `[]` is a known empty
list. Numeric values are finite and appropriately nonnegative; counts exclude
booleans, seat IDs permit zero, rank begins at one, and rank delta is signed.
Percent is in [0, 100]. Timestamps are validated against injected current time.
Unknown values stay `None`, never zero. `last_work_kind` is `worked`, `accepted`,
`none_accepted` or `None`; `update_state` is `current`, `outdated`, `pending`,
`unavailable` or `not_checked`. Meter fields keep the existing rack vocabulary.

## Source capture and identity

`sources` supplies independent `seat`, `rewards`, `market`, `records`, `workers`
and `contributors` envelopes with `state` and `read_ts`. Its `runtime` mapping
is keyed by runtime ID, each with `state` and `read_ts` from the captured npm
cache. Existing `swarm_runtime_latest`, version labels and fleet facts remain
the value inputs. The market envelope describes the same IMD/USD conversion
input used for rewards; do not label a derived quote solely with a sibling
market read while ignoring its pool source.

Root captures entries, selected token, flags and their matching source metadata
together before offering detached work. Use `float(self._clock())` at capture
and projection, not an earlier cycle-start timestamp that could reject a newer
completed observation as future data. Reuse `_swarm_board_hero_sources` and
`swarm_outcomes_source`; do not introduce another workers/contributors clock.

Seat detail `read_ts` is a version clock and does not move on unchanged reads.
Root adds a bounded memory-only per-token observation, linking successful
confirmation and failure status to the exact selected point/version. Fresh
unchanged reads may confirm that version; another token's successful tier read
cannot freshen it. Restored values lacking a matching observation are
conservatively stale until confirmed. Preserve existing six-seat retention.

Root enforces selected-token and owner/pairing identity for seat and reward
inputs. Contributor/worker lookups must be computed for that same frozen token.
The projection additionally rejects a canonical outcome whose `token_id` differs
from selection. Switching seats replaces the complete card family atomically;
late completion of the previous seat cannot relabel its facts with the new ID.
The full refresh and cached/hub refresh paths must both publish the new
projection after their matching seat, board, rewards and runtime facts exist.

## Card meanings and unavailable states

- **SEAT:** keep the selected ID visible while pending, busy or unavailable.
  Preserve saved versus most-active selection. `empty` means no selected seat;
  `unknown_seat` is a successful never-paired result, distinct from failure.
  A failed/busy retry with last-good detail leaves values visibly stale and
  preserves `read_error`; without detail, say pending or busy/retrying plainly.
- **ACCEPTED and RANK:** use only canonical `swarm_seat_outcome` and its records
  source. They survive pending or failed detail independently. `listed=False`
  means no record in summary. Known 0/0 means no attempts and no percentage;
  0/N means 0%. Validate accepted <= attempts. Rank delta keeps the existing
  canonical observed-change meaning, with no invented 24-hour interval.
- **EFFORT:** `swarm_seat_contrib` supplies wall-clock seconds / 3,600 and output
  tokens. These are contributor effort, not uptime or canonical accepted-work
  totals. Keep known hours when tokens are missing; known not-listed is distinct
  from an unread/malformed selected contribution. Turns remain off this card.
- **REWARDS:** retain the existing owner receipts since pairing divided by the
  owner's current IDMD seat count. Keep the **OWNER SHARE** label and actual IMD
  amount even when USD is unknown. Refresh TTL is 600 seconds, but matching
  last-good can survive to the existing 3,600-second maximum age: failed or old
  retained values are stale, not fresh or newly pending. Owner/pairing changes
  invalidate them immediately. USD has its own source state/clock; quote failure
  must not erase known IMD or render a stale conversion as current. Tiny positive
  amounts must not round to a false zero.
- **STATUS:** workers supply current state, working slots, configured capacity,
  devices, pause-until and failures. Capacity is not a utilization denominator:
  oracle work can exceed it. Incomplete workers cannot prove an absent seat is
  offline or turn incomplete sums into zero. Preserve paused and unknown states.
  The subtitle uses seat-detail submitted/accepted timestamps with its separate
  state and clock; review queue `sentAt` is never work activity. An unavailable
  subtitle source cannot hide valid current workers.
- **OWNER:** use the existing forward-verified ENS name when available, otherwise
  the address. Preserve `address_text`, copy metadata, the package explorer and
  fitted rich spans. Pairing time belongs to this selected seat. Never turn a
  failed ENS lookup into a guessed identity or remove the address fallback.
- **RUNTIME:** retain reported runtime, daemon and devices independently of the
  optional update check. Use the existing strict SemVer helpers and captured
  per-package npm check. Show “up to date” only for a valid fresh comparison;
  absent, failed, stale, unsupported or malformed checks cannot assert current.
  An outdated runtime and a differing daemon retain their visible warning and
  exact tooltip context. Daemon comparison is equality against a fresh complete
  worker fleet reference, never version ordering; no valid reference means no
  comparison. Do not infer fleet agreement from an incomplete/stale roster.
- **MODELS:** advertised model/effort pairs, not actual submission models. Empty
  advertisement differs from unread runtimes. Show up to three rows, or two plus
  `+N more`; retain a flattened literal tooltip with all pairs and visible text
  ellipses. RECORD continues to show actual submission models independently.
- **FEEDBACK:** sent, submitted and queued are review-delivery entries, not
  accepted attempts. Keep their existing meanings, including real zeroes.
- **COLLAB:** retain collaborator count and teammates ordered by shared jobs
  descending, token ascending. The approved large count/top teammate footer
  remains; expose additional existing teammate detail in a tooltip if needed.
- **NODES:** accepted counts are seat-detail history and may differ legitimately
  from canonical records. Preserve all row facts for exact-count/attempt/rate
  tooltips. Sort by accepted, attempts, native node order and key; up to three
  rows or two plus `+N more`. Empty is no nodes yet, unread is unavailable.

A retained never-paired result uses `stale_unknown_seat`: keep its negative
result and selected ID, with a visible stale confirmation time. A fresh
confirmation returns to `unknown_seat`.

Readable stale values remain dated. A fresh source with some missing required
facts is partial; missing all usable facts is unavailable. A source failure
affects only its dependent facts. Known-empty/not-listed/no-attempt cases are
intentional real states, not missing-data alarms. Fresh installed software does
not require a successful optional update check to remain visible.

## Activity meter and rendering

Reuse existing `surfboard_activity.project` and the rack's activity conversion:
busy is fully green; over 0–24 hours after an observed stop green drains to
orange; over 24–72 hours orange drains to empty segments; offline is red OFF
with empty segments. IDLE stays grey and BUSY orange. No heartbeat or historical
submission timestamp invents an observed stop. Paused must remain visibly
paused, rather than becoming IDLE because working count is zero. Failed/stale
activity cannot paint a live bar. Reuse `meter_text` for matching render states.

Hoist the existing small conversion from `data/surfboard.py` into
`data/surfboard_activity.py` once and call it from both projections. Do not copy
the time-window arithmetic or change its current rack behavior. Keep source
activity paired with the captured worker snapshot so a later detached update
does not freshen an older STATUS card.

The widget reuses `HeroRecord` and existing rack cards with a local subclass for
the owner link, status/acceptance meters and necessary tooltips/state labels.
It imports no `data/` module. Repaint all twelve cards and clear previous rich
metadata/tooltips on each update. Respect the approved large digits, black
insets and matrix colors. Remove the old hero and seat-card row from mounted
AGENT composition while retaining their modules as parked code; keep the
RECORD panel and interactions intact. Other dashboard modes remain unchanged.

## Work packages and dependencies

1. **Planner:** only this new plan; no implementation, tests, subagents or commit.
2. **Data worker:** new `data/surf_agent_hero.py` and its focused data tests;
   the small `surfboard_activity.py` conversion hoist, `surfboard.py` call site
   and corresponding focused regression tests. No manager/model edits.
3. **Widget worker:** new `widgets/surf/swarm_agent_rack_hero.py` and its focused
   widget tests. No shared widget, screen/theme, models, manager or pin edits.
4. **Root:** models/signatures, manager observations and captured projection
   wiring, screen/theme composition, integration/contract tests, live capture,
   later layout sweeps and documentation. Root owns all shared integration files.

Data and widget packages run independently after the frozen contract. Root
integrates both, then performs preview and hardening. Preserve concurrent edits;
report cross-owner defects instead of fixing or reverting another owner's work.
The one final review covers the whole change after the live preview.

## Acceptance and verification

- TDD in each package with focused failing tests; no test network or real
  clipboard. Bind exact section/row/signature fields. Cover zero, missing,
  not-listed, empty, pending, busy, never-paired and last-good stale states.
- Exercise seat switches and out-of-order detached completion, including a
  changed owner/pairing, mismatched outcome token, missing selected contribution,
  and cached/hub reprojection. No preceding seat value or address survives.
- Prove source clocks match their captured values: unchanged confirmation,
  independent endpoint failure, restored fallback, fresh observations after cycle
  start, and reward/quote/runtime failure or expiry. Preserve independent cards.
- Cover known zero attempts, tiny rewards/hours, working above capacity,
  incomplete workers, pauses, activity 0/24/72-hour boundaries, and stale bars.
  Mutation-prove one meaningful source/identity assertion and changed geometry.
- Verify actual compositor output at 149×45 and narrow resize/recovery: all
  twelve nine-row cards, aligned columns, complete meaningful numbers and units,
  rich owner affordances, truthful runtime warnings, source states, and visible
  native RECORD. Preserve `i`, filtering, more, mode switches and saved-seat
  navigation; keep table scroll behavior and existing width-tier markers.
- Show the owner the **live production render at 149×45 before** layout sweeps,
  pin evidence blocks, hardening docs or final review. This planning document is
  the permitted precursor; temporary captures and real user data stay out of Git.
- After preview, measure AGENT through the existing `a` layout sweep at its
  actual containers. Update only evidence-backed screen/theme pins and blocks;
  do not derive the new height from the old pin. RECORD's independent full-width
  requirement need not fit the owner terminal without its normal marker.
- Root runs touched/composing files, fast guards and applicable docpins once
  near commit; no full suite without user request. One final independent review,
  one fix wave and scoped re-review only for production fixes. File Minor-only
  residuals and commit the verified result.
