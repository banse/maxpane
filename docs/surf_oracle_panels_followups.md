# Oracle panels follow-ups

- **F-O1 — request-index growth:** the complete history cannot be age-pruned while it proves
  absence. At the captured ~125 requests/day it adds ~14 KB/day (~50 KB for 590 requests).
  Revisit storage only after measuring growth; retain complete-history semantics.
- **5A remains an owner decision:** ORACLE-tile panel-agreement totals and open/closed pending
  counts are out of scope. RECORD now exposes each panel outcome without changing STATE.
- **Controller work:** one review per WP, whole-branch review and one full-suite run before merge.
  No full suite was run by the implementer.

The bool-display question is resolved: owner-approved `answer_bool` / `panel_answer_bool`
carry strict `agreement.answer`; figures never determine YES/NO. Fixtures cover both truth values.

Validation environment: use `.venv311/bin/python` and unset `NO_COLOR` for compositor
colour assertions (`env -u NO_COLOR .venv311/bin/python -m pytest ...`). The inherited
`NO_COLOR=1` renders ANSI colours as grayscale and fails existing colour assertions too.
