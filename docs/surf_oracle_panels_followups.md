# Oracle panels follow-ups

- **F-O1 — request-index growth:** the complete history cannot be age-pruned while it proves
  absence. At the captured ~125 requests/day it adds ~14 KB/day (~50 KB for 590 requests).
  Revisit storage only after measuring growth; retain complete-history semantics.
- **N2 — one request id under two jobs (Minor, re-review 2026-09-24):** if the list serves the same
  request id for two job ids, index coercion rejects the whole slot on every cycle. The row stays
  `not read` and the list is re-read each cycle. Only hostile or broken server data triggers this. The fix is to map
  the duplicate id's jobs to `None` (unavailable) instead of discarding the index.
- **5A dropped by the owner (2026-09-24, `docs/decisions.md`):** ORACLE-tile panel-agreement totals and open/closed pending
  counts are out of scope. RECORD now exposes each panel outcome without changing STATE.
- **Controller work:** one review per WP, whole-branch review and one full-suite run before merge.
  No full suite was run by the implementer.

The bool-display question is resolved: owner-approved `answer_bool` / `panel_answer_bool`
carry strict `agreement.answer`; figures never determine YES/NO. Fixtures cover both truth values.

Validation environment: use `.venv311/bin/python` and unset `NO_COLOR` for compositor
colour assertions (`env -u NO_COLOR .venv311/bin/python -m pytest ...`). The inherited
`NO_COLOR=1` renders ANSI colours as grayscale and fails existing colour assertions too.

## Native ORACLES dashboard — 2026-10-13

Live integration is complete; final scoped review approved with no findings.
The dashboard keeps the approved 66/34 split and opens with Ctrl+o. Its newest
100-request page and selected-only, 64-member details are deliberate bounds;
unknown statuses and incomplete coverage remain explicit. No pagination or global
request-total claim is included.

Live API render inspected at 149×45; measured layout is 131×42. Both directions of
both pin mutations failed as expected, as did exact-hash and selected-request
identity mutations. Data, native routing/layout, widget contracts, address actions,
registration and docpin checks passed. No full-suite run was requested or performed
for this dashboard. No new review follow-ups remain.
