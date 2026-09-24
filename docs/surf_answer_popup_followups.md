# Surf ANSWER popup follow-ups

## F-A1 — keyboard access

Provide a keyboard path to open a cached ANSWER or SUBMISSION popup. RECORD currently has no cursor;
the shipped affordance is the row's `»` click. Decide the selection interaction before
changing the table's cursor or Enter behavior. Keep Enter/Escape inside either popup as close actions.

## F-A2 — replies from other nodes — done (2026-09-24)

`docs/surf_submission_popup_plan.md` adds SUBMISSION for successfully read non-joined rows,
when cut or failed/rejected. A shared popup frame shows the bounded reply, job/node state,
usage and up to eight other seats. The approved cache persists cleaned reply text within an
8,000-byte point budget; the two-read job-detail slot retries blocked jobs. G1 also retains
bytes32[] values and displays them without address semantics.

The captured failed-build reply starts mid-line and ends mid-warning; the compile error is not
published. The popup labels that limitation. More logs cannot be recovered from this response.
No completed non-oracle job was in the live 40-row window, so the approved v4 review capture
remains the completed-job fixture. The `4c11a919…` identifier in the plan names the job;
its oracle request is `1ad552f0-7f24-4e94-9c48-d25a79a88ce9`.

## Implementation notes

- F-A3 (filtered oracle reads) is implemented. Existing full detail fixtures remain unchanged;
  hit/miss/assessing filtered captures live in their own subdirectory.
- The approved 6,000-byte point budget can shorten notes, then question, then reason. The popup
  shows all retained text and preserves the normalized value; it cannot recover discarded prose.
- Resume follows the normal refresh guard. With seat/submission/oracle caches fresh, the test
  observes zero reads for those endpoints. The zero-TTL fast tier still reads nonces and chain
  state. Opening the snapshot causes no reads.
- Layout pins remain unchanged. The legacy submission-message fallback retains its measured
  widen boundary for rows without valid popup identities; ANSWER/SUBMISSION cuts use `»` instead.
- The shared-request coverage follow-up is completed by fix F2: a filtering fake records each
  request/hash pair and verifies distinct member facts for two hashes of one job. Fix F7 covers
  the corresponding popup selection through both row buttons.
