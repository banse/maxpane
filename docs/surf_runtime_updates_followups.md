# Surf runtime updates — follow-ups (2026-09-24)

- **F-RU1 — screenshot/capture mismatch (resolved by owner, 2026-09-24).** The committed v3 #420
  contributor capture has 2,189 turns, 8.1 h, 1,215,919 output tokens and rank #6 of 99;
  its paired seat capture has 190/204 accepted (93.1%). The plan's 3,063 turns, 11.9 h,
  242/280 (86.4%) and #8 of 306 are not present in the committed contributor corpus.
  The actual capture is tested with its own values; the plan examples have a separately
  named synthetic composited layout test. The owner explicitly approved keeping both the
  existing capture and the synthetic plan examples. No oracle fixtures or detail manifest
  were changed.

The live npm capture returned Claude Code 2.1.282 (one release after the plan's probe)
and Codex 0.156.1. Only name/version were retained; tests never reach the registry.

Implementation choices: a separate NpmRegistryClient keeps its one host, allowlist and
short timeout independent of SurfClient's chain/API pools. npm timestamps are per package
so switching runtimes cannot make another package appear freshly checked. Fleet totals
count workers reporting valid daemon versions; invalid/missing versions do not vote.

The docs, data, UI and whole-branch reviews were Approved with no Critical or Important
findings. The scoped fix re-review and full suite remain with the controller before merge.

- **F-RU2 — a stale persisted npm latest is compared for one cycle** (whole-branch 2). After a
  long offline gap, the stored latest version is used until the next due read. The tooltip's
  `as of HH:MM` carries no date, so a days-old check reads as today's. Low impact: the TTL is
  3,600 s and the read is due on the first cycle.
- **F-RU3 — both runtime packages are fetched** (whole-branch 4). The card compares only the
  seat's own runtime (`runtimes[0]`). The second package costs one small keyless GET per hour.
  Keep it, or fetch only the seat's runtime; decide when the file is next touched.
- **F-RU4 — `fmt_compact` renders `1000.0B tokens`** (whole-branch 5). Above 999.95 B the
  shared formatter does not carry over to a `T` suffix. This is shared-widget behaviour
  (`widgets/sparkline_common.py`), so it is out of scope here. No real seat is near it.
- **F-RU5 — `_seat_entered` calls `start_refresh` twice** (whole-branch 6). The refresh guard
  skips the second call, so there is no visible effect. Remove the second call when
  `screens/surf.py` is next touched.
