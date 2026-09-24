# Surf ANSWER popup follow-ups

## F-A1 — keyboard access

Provide a keyboard path to open a cached oracle answer. RECORD currently has no cursor;
the shipped affordance is the clipped row's `»` click. Decide the selection interaction before
changing the table's cursor or Enter behavior. Keep Enter/Escape inside ANSWER as close actions.

## F-A2 — replies from other nodes

Consider popups for review/build and other non-oracle replies. Define their source, bounded cache
contract and presentation separately; their current clipping still uses the widen marker.

## Implementation notes

- F-A3 (filtered oracle reads) is implemented. Existing full detail fixtures remain unchanged;
  hit/miss/assessing filtered captures live in their own subdirectory.
- The approved 6,000-byte point budget can shorten notes, then question, then reason. The popup
  shows all retained text and preserves the normalized value; it cannot recover discarded prose.
- Resume follows the normal refresh guard. With seat/submission/oracle caches fresh, the test
  observes zero reads for those endpoints. The zero-TTL fast tier still reads nonces and chain
  state. Opening the snapshot causes no reads.
- Layout pins remain unchanged. The legacy submission-message fallback retains its measured
  widen boundary; joined answer cuts use `»` instead.
- The shared-request coverage follow-up is completed by fix F2: a filtering fake records each
  request/hash pair and verifies distinct member facts for two hashes of one job. Fix F7 covers
  the corresponding popup selection through both row buttons.
