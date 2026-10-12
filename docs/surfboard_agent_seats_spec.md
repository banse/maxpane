# Four saved Surfboard agent seats

Date: 2026-10-12. Tier 2: card contract, configuration, data projection, routing,
and widget changes. Target below 1,000 production lines; one final review only.

## Behavior

The four lower perimeter cards, currently AGENT and BAY 10/11/12, become four
independently assigned agent cards. All four outer titles are exactly `AGENT`.
Keep their existing positions and the rest of the rack layout.

The first assignment uses the existing saved IDMD seat number from the AGENT
dashboard. This is a public NFT token number, not a wallet address. If none is
saved, its card is empty; never select the most-active roster entry as a fallback.
The other three assignments are saved independently and survive restart. The
same token may be assigned to more than one card; changing one assignment does
not change another.

An empty card has a black background across the card, inset, and input. Its
inset title is `EMPTY SEAT`, its number input sits inside the inset, its inset
footer is `type in seat no`, and its outer meter label is `EMPTY` with an unfilled
track. All four cards remain focusable. Entering a valid seat number saves and
populates that card without opening the dashboard. Clicking/activating a filled
card opens the AGENT dashboard for that card's token. An empty card focuses its
input and does not navigate.

Use the existing seat parser: at most ten ASCII digits with an optional leading
`#`, token zero allowed. Valid tokens are integers from 0 to 9,999,999,999,
excluding booleans. Invalid input does not write configuration or change a card; show
an inline error without growing the inset. Preserve an unfinished input draft
through background refreshes. Polling or focus must never submit the input.

An assigned card uses the current AGENT face, live slots, status colors, and
activity meter. An unavailable/offline assigned token stays assigned; source
failure does not turn it into `EMPTY SEAT`. Preserve grey `IDLE`, orange `BUSY`
with full green bar, red `OFF` with hollow track, the 0–24h green-to-orange decay,
and the existing 24–72h orange-to-empty cooldown. Keep right-aligned launch
verification marks and all other recent visual changes.

## Saved assignments and active dashboard selection

Use zero-based `seat_slot` values 0 through 3 in code; the first visible card is
slot 0. Slot 0 aliases the existing `[seat].token_id`. Store slots 1–3 as scalar
`seat_2`, `seat_3`, and `seat_4` keys under `[surfboard]`, compatible with the existing simple TOML writer.
Preserve unrelated configuration and validate hand-edited values independently.

Keep the four saved assignments separate from the currently opened token.
`SurfManager._seat_saved` currently controls the active AGENT projection and is
changed by `set_seat`; opening a secondary card may change that active token,
but must not rewrite slot 0 or any persisted assignment.

During a visit opened from an assigned rack card, the native AGENT `i` prompt
and any leaderboard seat selection update that originating assignment. Opening
the dashboard alone is read-only. Native/menu entry resets the origin to slot 0
and restores the saved primary selection. Leaving a rack visit clears its
origin so a later native selection cannot overwrite a forgotten secondary slot.
Unscoped existing seat commands continue to use the primary context.

The prompt currently persists slot 0 inside `SeatInputScreen` before its callback.
Give it an optional current value and save callback, preserving its native
defaults, so a secondary-origin prompt cannot perform that wrong write first.
Route all successful selection paths through the same origin-aware behavior.

Configuration stays outside the data layer. `__main__` loads the tuple and
injects it through the optional `surfboard_seats` app/manager argument. A bare app/manager remains independent
of the developer's config file, as the existing startup tests require.

## Plain-data contract

Keep `SURF_KEYS` and rack widget signatures unchanged. Extend
`SURFBOARD_CARD_FIELDS` only with `seat_slot` and `token_id`; both are `None` on
non-agent cards. Use stable keys `agent`, `agent-2`, `agent-3`, and `agent-4`.
The title is presentation, never routing identity.

| Card state | token_id | status / meter_state | destination |
|---|---|---|---|
| Empty assignment | None | empty / empty | None |
| Assigned | Valid token | Existing AGENT states | agent |

The frozen configuration seams are `get_surfboard_seats()` returning exactly
four tokens/None and `save_surfboard_seat(slot, token)` writing just one slot.
The manager seams are `get_hub_seats()` and `set_hub_seats(tokens)`;
the setter validates and replaces assignments without configuration I/O or an
await. Reads/in-memory tuples allow None for empty slots; saving requires a valid
integer. The existing `set_seat` remains the active dashboard selection seam.

`cards(..., agent_seats=...)` receives four plain per-slot projections containing
`token_id`, `live`, and `outcome`. The manager builds them from the saved tuple
and the shared worker/record snapshot. Existing activity data supplies each
token's history. The manager always supplies the explicit tuple; active selection
or a roster fallback must never fill an unassigned card.

Extend the card activation message with optional `seat_slot` and `token_id`,
leaving non-agent routing unchanged. An empty input emits a separate
`SeatSubmitted(seat_slot, value)` message with slot and raw text. The screen validates,
saves that assignment, updates the manager tuple, and refreshes. It does not
await network I/O in a message handler. App routing carries the originating slot
to the native screen and selects the token without a configuration write.

## Cache and network decision

Reuse one SurfManager. `SLOT_SWARM_SEAT` already stores independent token-keyed
finished reads, and `coerce_seat_slot` validates each token's record and clocks.
Its existing bounded cache keeps six recent seats, enough for four assignments;
ordinary eviction remains possible after browsing other seats. Worker presence,
canonical record outcomes, rank/rewards, and persisted activity also key their
results by token. Reassigning a card must not relabel another token's cached data
or transfer its stop timestamp.

Refresh all four cards from the existing shared workers/records/activity reads.
Only an opened AGENT needs the full `/seats/{token}` read and its detail
hydration. Keep the current single-active-seat task and cancellation semantics:
calling that scheduler once per card would cancel the other reads repeatedly.
Its singleton failure/busy markers apply only to the active detail view, never
to the other three cards. Duplicate assignments reuse the same token's data.

Four independent managers would multiply network reads and risk whole-cache
file overwrites. Four full detail tasks would require per-token task/backoff
state without improving these card faces. Shared reads plus token-keyed
projections satisfy the request with less state and preserve current caching.

## Acceptance and layout

Test persisted assignments and startup injection, no-primary fallback, independent
status/history across four tokens, duplicate tokens, and source failures. Test
all empty/filled combinations needed to expose routing and style dependencies,
especially all-filled news rendering: it currently looks up an `.empty` bay for
its muted color, and that dependency must be removed.

Use the existing five-line inset for the input. Show a live keyless 149×45 render
before hardening dimensions. The current 144×35 pin is the target, subject to
actual compositor checks; preserve readable input/footer and truthful scrolling.
Run focused tests while editing, then touched/composing files, required guards
and docpins, and one final review. No extra approval step or full-suite run.
