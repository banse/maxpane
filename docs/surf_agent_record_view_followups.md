# Surf AGENT record view follow-ups — 2026-09-24

The review fix wave resolves X1–X7; F-R1 below remains filed, not changed.

The owner approved testing the committed submissions #420 capture (232 collaborators,
#1626 ×158, #1731 ×150, ORACLE 219/256) instead of the newer screenshot numbers.
The screenshot values remain covered separately by a synthetic composited case.
No fixture or oracle detail manifest was changed.

The 400-row limit is intentional: at that limit the remaining older count stays,
and `more` is no longer offered. Larger histories require a separate product decision.

Controller scoped re-review and the full suite remain before the owner's merge decision.

- **F-R1 — stale non-terminal points after grow → shrink → grow** (whole-branch 5). Rows 41–400
  that were read earlier keep their cached point, and it is not re-read while the row is
  outside the window. After the window grows again, those rows show the old value until the
  due read reaches them (4 per cycle), behind the seat's `as of` only. The impact is low
  because old rows are almost always terminal. The same thing already happens inside the
  40-row window after a restart.
