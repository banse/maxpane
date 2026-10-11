# Surfboard offline status and detail layout specification

Date: 2026-10-11. Status: accepted user direction. Tier 2; expected change below
1,000 production lines, with one final review.

## Problem and scope

AGENT and LEADERBOARD need an explicit offline footer and matching presence colors.
The focused card's detail should be readable beneath the central terminal instead
of being clipped across the bottom of the screen. The owner also wants AGENT and
PORTFOLIO exchanged and the EARNINGS placeholder replaced by an empty BAY 10.

Preserve existing destinations, keyboard bindings, data-source scheduling, activity
history, volume history, and the recently accepted protocol/share-rate formatting.
Use the current plain card fields and existing Textual containers. No new models
keys, widget dispatch signatures, network reads, or persisted schema are needed.

## Offline evidence and card contract

`surf_swarm._seat_live_from_slot` returns `None` for unread/invalid data or a token
marked malformed. Otherwise a missing token becomes `live=False` with
`live_state='offline'`; this legacy helper alone does not establish whole-list
completeness or freshness. `surfboard_activity.project` provides that guard:

- A fresh, successful complete workers list can establish an absent token as idle.
- A failed read or an observation older than 300 seconds projects stale.
- Unknown counters, incomplete absence evidence, and unread sources remain unknown.
- Positive work on any device establishes busy even when another device is unknown.

In `data/surfboard.py::cards`, derive each card from its own identity: the selected
token and `swarm_seat_live` for AGENT, the canonical rank-one token and that row's
`live_state` for LEADERBOARD. Set the existing `meter_state` to **`offline`** only
when the activity projection is fresh `idle` and that token's live state is
`offline`. Neither legacy offline by itself nor a failed request means OFF.

Keep `surfboard_activity`'s persisted busy/idle transitions unchanged. Preserve
`remaining`, `stopped_ts`, and observation clocks; OFF is a presentation state, not
a new historical transition. Reconnecting resumes the existing observed activity
policy. Conflicting busy evidence must not be converted to OFF.

| Current evidence | Outer footer | Inset presence colors |
|---|---|---|
| Fresh busy | Orange BUSY label, full green solid bar | Working green |
| Fresh online idle | Accent-green IDLE label, existing green-to-solid-orange 24h decay | Idle grey |
| Fresh confirmed offline | Red OFF label, hollow/unfilled segment track with no solid fill | Offline red |
| Stale or unavailable | Existing explicit unknown footer; no OFF/BUSY/IDLE claim | Existing stale/unknown treatment |

The OFF track uses hollow `▱` cells and does not display retained decay as current
work. Preserve current cold-idle behavior: without an observed stop, IDLE has the
existing solid-orange track. LEADERBOARD's inset border and status-colored text
use the same worker-presence mapping as AGENT; its canonical rank, accepted-job
count, and source detail remain independent facts. Paused and unknown states retain
the existing AGENT treatment. Use source freshness for both cards so stale offline
evidence cannot imply a current red OFF state.

## Slot arrangement

Keep the six-column, four-row rack and the entire top row unchanged. Coordinates
are zero-based:

| Row | Column 0 | Columns 1–4 | Column 5 |
|---|---|---|---|
| 1 | LAUNCHPAD | Central terminal/detail container | PORTFOLIO |
| 2 | AGENT | Same spanning container | BAY 10 |
| 3 | BAY 11 | Same spanning container | BAY 12 |

BAY 10 follows BAY 11/12: `bay-10` identity, empty styling, hollow placeholder
footer, no destination, no focus, and no activation. Remove the EARNINGS card from
this rack and its obsolete projection placeholder. Arrow navigation continues to
derive from the updated slot coordinates; preserve portfolio and agent activation.
The rack still has twelve cards and exactly one terminal.

## Detail below the terminal

Use one `VerticalScroll` center container spanning the terminal's current four columns
and three rows. Its children are the existing `SurfboardTerminal`, followed
immediately by the existing `#surfboard-detail` Static. Preserve the ID so the
screen can keep updating it through descendant queries. The container and both
children share the same left and right bounds.

The terminal takes available space with a measured 12-row minimum height; the detail has
automatic height and wraps at the center column width. Display the complete
sanitized detail, including long and unbroken prose, without ellipsis or the
old `detail ‹ widen` title hint. Plain text must stay literal; preserve address
handling when applicable. Keep the existing dashboard scrollbar hints for actual
viewport overflow. Longer detail may consume more rows or require scrolling, but
must not silently clip itself, hide terminal controls, or overlap another card.

`_render_chrome` continues to update the dashboard title and focused detail, using
the center detail's actual width. Do not pre-truncate to the full screen width.
`PANELS`, refresh dispatch, input focus, command replies, and terminal state survive
the wrapper. Keep screen CSS synchronized with `themes/minimal.tcss`.

## Design alternatives

| Choice | Benefit | Cost |
|---|---|---|
| Selected: projection-only OFF plus existing activity history | Truthful fresh presence, no migration or additional source | Must combine the two existing facts consistently |
| Extend persisted activity states with offline | Single projected state source | Adds coercion/migration work without improving this display requirement |
| Selected: existing VerticalScroll around terminal/detail | One layout boundary and normal wrapping | Detail height competes with terminal space and requires measured floors |
| Separate grid detail row/custom component | Explicit row placement | More row coordination and lifecycle machinery for the same content |

## Acceptance and verification

Test fresh complete absence, incomplete absence, failed/stale reads, multi-device
work, selected/leader independence, and reconnection without history reset. Test
OFF's red label and hollow track, preserved BUSY/IDLE colors, and LEADERBOARD/AGENT
inset color parity using composited output.

At the owner's 149×45 size, verify the new positions, nonfocusable BAY 10, full
wrapped detail, equal terminal/detail bounds, and usable terminal controls. Exercise
long detail, hostile literal text, resize, refresh, focus changes, and boundary
sizes. Start from the existing 144-column/36-row pins; measure new requirements
rather than assuming either stays fixed. Show a live keyless render before pin
hardening or final review. Run focused tests while editing, touched/composing files
and fast guards once before commit, required mutation proofs, and one final review.
Use `env -u NO_COLOR` for color assertions. No full suite.
