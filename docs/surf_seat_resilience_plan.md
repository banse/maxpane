# Surf AGENT — seat resilience plan (per-seat last-good, busy state, loading words)

Tier 2. Owner request, 2026-09-26. Branch `feature/surf-seat-resilience`, created from autopull
`main` at `b7cb92a` (v0.9.3):

```
git fetch /Library/Vibes/autopull main
git switch -c feature/surf-seat-resilience FETCH_HEAD
```

Run WP0–WP4 straight through, with no pause. Commit once per WP. Do not merge, push or tag. At
the end, send one report: the commits, the tests per WP with their counts, and a mutation proof
for every item marked **(M)** that names the test that turned red. The controller runs the full
suite; you do not.

Rules: CLAUDE.md conventions (a failed read is `None`; a dead source degrades to an explicit
state behind `as of`; never a false degradation; no network in tests — every payload is a
committed fixture; inject the clock). No pin may move. If one would, stop and report.

## 0. What happened (evidence, 2026-09-26 21:57)

- `GET /seats/420` returned **503** on both `SWARM_API_HOSTS` (one deployment), with this body:
  `{"error":"busy","detail":"the plane is answering as many record reads as it can; try again in
  a moment"}`
  Large records (#420, #1545) got the 503; `/seats/1` returned 200. A few minutes later #420
  returned 200 in 0.5 s. This is transient load shedding by the host.
- `SLOT_SWARM_SEAT` holds **one** token. It held seat 7 (the owner had looked at it), so #420 had
  no last-good. The single-token guard (seat A's numbers never under B's name) is correct, and it
  left every seats-backed card and RECORD reading `unavailable`.
- WORK, RANK and STATUS read `/contributors` and `/workers`, so they stayed live.
- Separately, RECORD writes `not read` for answers and panels the seat tier has not read *yet*.
  The owner wants the user to see that these are still loading.

## 1. Owner decisions

1. **Per-seat last-good.** Switching back to a seat whose read now fails shows that seat's last
   good record behind its own `as of HH:MM`. It never shows another seat's record.
2. **Busy state.** A host that says it is busy is a distinct, explicit state, not `unavailable`:
   the host is up and asking us to wait.
3. **Loading words.** Everything RECORD is still going to load reads as loading, not `not read`.

Controller choices, fixed here:

- Busy wording: `busy · retrying` (yellow). With a last-good record, the record stays on screen
  and RECORD's title reads `… · as of HH:MM · busy` (the `busy` word is yellow; the title's other
  words are unchanged).
- Loading wording: `loading…` (dim), with the single-character ellipsis `…`.
- Per-seat cap: 6 seats, most recently read first, then by token.

## 2. Design

### 2.1 Client — recognise "busy" (`data/surf_swarm_client.py`)

- A response is **busy** when all of these hold:
  - the status is 503;
  - the body is a JSON object;
  - `error == "busy"` (exact string).
  Anything else keeps its current handling.
- `_get` keeps rotating on a busy host exactly as on any other non-200. The pool is never shrunk
  (CLAUDE.md: a provider's error is evidence only about the request it read; classify on the
  message text, not on the code alone). That is why the check requires `error == "busy"`, not just
  503.
- `fetch_seat` distinguishes three outcomes:
  - a seat or `UNKNOWN_SEAT`, as now;
  - a new sentinel `SEAT_BUSY` (a frozen, exported constant like `UNKNOWN_SEAT`), returned when
    **every** host answered busy;
  - `None` for any other failure, including a mix of busy and other failures.
- Only `/seats` needs this. The other swarm routes keep their current handling.
- Commit a fixture: `tests/fixtures/surf/swarm/seats_503_busy.json`, with the body above.

### 2.2 Cache — per-seat slot (`data/surf_cache.py`, `data/surf_swarm.py`, `data/surf_manager.py`)

- `SLOT_SWARM_SEAT` payload becomes
  `{"seats": {"<token>": {"state": "ok"|"unknown_seat", "seat": dict|None, "read_ts": float}}}`.
  Keep at most `SEAT_SLOT_CAP = 6` entries: most recent `read_ts` first, ties broken by token
  ascending. Give the constant a `#:` comment that names the ~90 KB size of a large seat.
- A new pure `coerce_seat_slot(payload, *, now)` in `surf_swarm.py` validates **each** entry
  independently:
  - the token is a canonical decimal string;
  - `state` is in `("ok", "unknown_seat")`;
  - `ok` requires `seat_state(seat, token) == "ok"`;
  - `unknown_seat` requires `seat is None`;
  - `read_ts` is a finite, non-negative float that is not in the future relative to `now` (with
    the same tolerance that the other slots use).
  A bad entry is dropped and its valid siblings are kept.
- **Old shape:** a v0.9.3 payload `{token, state, seat}` is migrated on load into a one-entry map
  when it validates, using the entry's stored `ts` as `read_ts`. Otherwise it is dropped. Do not
  bump the cache file version for this.
- Register the coercer wherever the other slot coercers are registered (the `SLOT_SWARM_SEAT_RANK:
  sw.coerce_rank_slot` table).

### 2.3 Manager (`data/surf_manager.py`)

- `_pool_swarm_seat` handles each outcome:
  - **A finished read** (`ok` or `unknown_seat`): update only that token's entry, trim to the cap,
    and store the slot only when it changed, as now.
  - **`SEAT_BUSY`**: mark the tier failed with the normal backoff, and remember the busy outcome
    for that token (`self._seat_busy_token = token`). A later finished read of that token clears
    it.
  - **Any other failure**: as now (`_seat_failed_token`).
- **Served keys:** `swarm_seat_summary`, `swarm_seat_state`, `swarm_seat_work_rows` and
  `swarm_seat_as_of_hhmm` come from **the selected token's entry**, with `as of` taken from that
  entry's `read_ts`. Three cases:
  - **The entry exists:** its state and record are served, and `as of` is its own `read_ts`,
    even while its current read is busy or failing.
  - **No entry, and the last read was busy:** `swarm_seat_state = "busy"`.
  - **No entry, and the last read failed** (not busy): `None`, exactly as now.
  - **No entry, and nothing has finished yet:** `"pending"`, as now.
- A new contract key, `swarm_seat_read`, of type `str | None`:
  - `"busy"` when the selected token's latest read was busy;
  - `"failed"` when it failed for another reason;
  - `None` when the latest read finished, or no read has completed yet.
  It lets RECORD's title say `busy` behind a last-good record. Add it to `SWARM_KEYS`, and to
  `SWARM_WIDGET_SIGNATURES["SurfSwarmSeatRecord"]` only. The agreement tests must pass.
- Add `"busy"` to `SWARM_SEAT_STATES`.
- `set_seat` and the seat-change reset keep their current behaviour. The single-token guard is now
  structural: a key is read only from the selected token's own entry. Every place that read
  `slot["token"]` must read the map instead. Find them all: `grep -n "SLOT_SWARM_SEAT"
  maxpane_dashboard/data/surf_manager.py` currently shows lines 176, 5858 and 6472.

### 2.4 Widgets

- `_swarm_seat.seat_state_line` gains `"busy"`: yellow `busy · retrying`. It must fit every box at
  the AGENT pin; the layout test proves this. Pending, unknown_seat and None are unchanged.
- The hero boxes (ACCEPTED and REVIEWED) and every seats-backed card go through
  `seat_state_line`, so they pick this up with no change of their own. Verify this; do not assume
  it.
- RECORD (`swarm_seat_record.py`):
  - With `state == "busy"` and no rows, the footer and body read `busy · retrying` where they read
    `unavailable` today.
  - With a record on screen and `swarm_seat_read == "busy"`, the title appends ` · busy` (yellow)
    after `as of HH:MM`. It must not push `SEAT_HINT` off: where it does not fit, the seat hint is
    shed first, as it already is at narrow tiers.
  - `swarm_seat_read == "failed"` adds nothing. The aging `as of` already says it.
- The RUNTIME tooltip: a busy seat is a gated state, so the tooltip is `None`, as for pending.

### 2.5 Loading words (RECORD, popups)

Replace `not read` with `loading…` **only where the manager will read it**. Verify each path in
the manager before changing its word:

| site | today | becomes | condition |
|---|---|---|---|
| `swarm_seat_record.py:324` answer cell, `answer_state == "not_read"` | `not read` | `loading…` | the row is inside `record_window` (it always is, because RECORD shows only that window) and the submission read will reach it: 4 per cycle, due rows first |
| `_oracle_answer.py:103` panel, `panel_state == "not_read"` | `not read` | `loading…` | the row is eligible for the oracle read (oracle node inside the window) |
| `screens/submission_detail.py:41` job line, `job_read == "not_read"` | `not read yet` | `loading…` | the row is eligible for the job-detail read (§ "SLOT_SWARM_JOB_DETAIL" in rules/surf.md) |

If a `not_read` path exists that the manager will **never** read (the row is ineligible), it must
**not** say `loading…`, because that would promise a read that never comes. Give it a distinct,
honest word instead, such as `not read` kept for that case only, and list it in the report. Add a
test that pins each ineligible case to its word.

## 3. Work packages

**WP0 — contract.** Add `SEAT_BUSY`, `"busy"` in `SWARM_SEAT_STATES`, the `swarm_seat_read` key
and signature entry, `SEAT_SLOT_CAP`, and the fixture. Agreement tests updated.
Tests: `tests/data/test_surf_swarm_models.py`, `tests/widgets/test_surf_widget_contract.py`,
`-m guard`.

**WP1 — client.** Busy classification and the `fetch_seat` outcome.
- Tests with an injected transport:
  - both hosts busy gives `SEAT_BUSY`;
  - one busy and one 500 gives `None`;
  - a 503 with a different `error` gives `None`;
  - a 503 whose body is not JSON gives `None`;
  - one busy host then a 200 gives the seat.
- **(M)** Remove the `error == "busy"` check and name the test that turns red.

**WP2 — slot and manager.** `coerce_seat_slot`, the migration, the per-token entries, the cap,
the served keys and `swarm_seat_read`. Tests:
- **(M)** Seat A read, then seat B read, then seat A busy: A's record and A's `as of` are
  served, `swarm_seat_state == "ok"` and `swarm_seat_read == "busy"`. B's numbers never appear
  under A.
- **(M)** A never-read seat that is busy gives `swarm_seat_state == "busy"`. One that failed for
  another reason gives `None`.
- The cap: reading 7 seats keeps 6, and the oldest is dropped.
- Load: the old single-token shape is migrated. A malformed entry is dropped and its siblings
  survive. A future `read_ts` is dropped.
- The slot is not re-stored when nothing changed.

**WP3 — widgets.** The busy state line, RECORD's title and footer, the gated RUNTIME tooltip, and
the loading words from §2.5. Composited assertions (`render_strips()`), including the colours.
Tests:
- **(M)** RECORD title `as of HH:MM · busy`, with the busy word yellow.
- **(M)** A pending answer and panel read `loading…`, never `not read`.
- The ineligible cases keep their honest word.

Run `tests/screens/test_surf_swarm_layout.py -k "agent or record"`: no pin moves, and the busy line
fits every AGENT box.

**WP4 — docs.**
- `.claude/rules/surf.md`: the per-seat slot, busy and the loading words. Replace the
  "single-token slot" sentence.
- `CHANGELOG.md` `## Unreleased`.
- `docs/surf_seat_resilience_followups.md` for anything you defer.

Run the doc-pinning tests (`rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/`) and
`-m guard`.

## 4. Tests to run per WP

For each WP: the touched modules' test files, plus `tests/screens/test_surf_swarm_screen.py`,
plus `-m guard`. After WP3, also the layout set named there. Never the full suite.
