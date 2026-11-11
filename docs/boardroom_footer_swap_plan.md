# SWARM / SHIPPED footer swap

Owner request, 2026-11-11. Tier 2 because the rack widget is shared. One small
root-owned package, under 20 production lines; one final review, no task review.

- SWARM receives the existing 24H accepted-step sparkline from SHIPPED.
- SHIPPED receives the existing worked-duration footer from SWARM.
- Reuse `footer_data`; retain each body, source identity, tooltip provenance,
  current position and destination. Missing reloads retain observed footers.
- Fit/clipping checks follow the displayed footer. No data or polling changes.

Verify composited footers, unchanged centers, reload retention and actual zero
at owner/minimum sizes. Show a live 149x45 render before boundary checks and
documentation. Run touched/composing tests once and fast guards/doc pins;
compare residual failures with e05c9f47. One scoped review, then local commit.

## Verification

- Live public-data render shown at 149x45: SWARM's 24H sparkline and SHIPPED's
  `worked 2y 10w 4d` footer. `/tmp/boardroom-footer-live.{json,svg,png}`.
- Eleven boundary samples preserve 143x37 and existing scrollbar onsets, with
  no clipped cards. `/tmp/boardroom-footer-sweep.log`.
- Inverse footer-swap mutation caught and restored. Screen regressions cover
  independent body values, source destinations, missing refreshes and actual zero.
- One composing run: 149 passed, 40 failed. Of those, 39 existing palette and
  navigation failures reproduce on unchanged e05c9f47. The additional
  `test_completion_captions_and_digits_survive_incomplete_screen_refresh[size0]`
  hit the existing fake-manager timer path (`get_hub_snapshot` missing) under
  parallel load; it passes alone and on the baseline. No production workaround.
  Logs/XML: `/tmp/boardroom-footer-{composing,baseline,serial}.*`.
- Fast guards: 130 passed, known TOKENS/SWORN CSS-slice failure also reproduced
  on baseline. Documentation pins: 12 passed.
- Final review Approved, no findings. Four named cases passed; an independent
  mutation that ignored real zero duration failed both refresh cases and was
  restored. `/tmp/boardroom-footer-review-{tests,mutations}.log`.
