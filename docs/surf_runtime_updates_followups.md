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

Controller reviews and the full suite remain before the owner's merge decision.
