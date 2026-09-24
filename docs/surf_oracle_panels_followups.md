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
