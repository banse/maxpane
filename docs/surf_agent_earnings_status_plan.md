# AGENT earnings footer and read status

Approved user request, 2026-10-13. Bounded implementation upgraded to Tier 2
because the review found that failed reads need their own projected state.

## Behavior

- A positive selected-agent `worked_on_24h` shows `x new worked on`.
- Otherwise use `earned_24h` and show `x new`, including unknown counts as `--`.
- Compact only when required by the existing card width; retain both exact counts on hover.
- Actual reads show `◌ loading`, including refreshes with cached data.
- Only a recorded fetch failure shows red `load failed`. Unread and cancelled
  first reads remain unavailable; cancellation never creates a failure.
- Keep last-good cached values and their original timestamps for recovery.
  Hide values while pending or failed. Successful retries restore normal rendering.

## Implementation

The session owns all changes. One dependent work package, no parallel edits:
add `failed` to the existing AGENT state contract, preserve it through the pure
source/hero projection, and render it in the EARNINGS footer. No new endpoint,
cache schema, layout pin or background task.

Regression tests cover the footer branches, narrow/wide rendering, initial and
cached reads, failure, cancellation and recovery. Use injected transports and
clocks. Verify actual live data at 149×45 before final hardening. Mutation-check
the data-state and rendered-count/color boundaries, run affected/composing files
and guards/docpins, then scope re-review to the single false-failure finding.

## Evidence

Fresh public reads succeeded for seats 3 and 7. Seat 3 showed one new worked-on
token. Seat 7 showed no worked-on tokens and 46 total newly earned tokens; the
reported persistent failure could not be reproduced. These are observations,
not constants. The review identified that mapping every `unavailable` state to
`load failed` falsely labels unread/cancelled reads, which this plan corrects.
