# IMD boardroom rack polish

Owner request, 2026-10-13. Keep the existing equal-width rack and full-height
terminal. Bold the low-contrast Katakana captions. Empty AGENT seats use the
placeholder `seat number` and footer `Identity.md`. TOKENS retains its top-three
last-24-hour ranking and consecutive-load price arrows, but unchanged/unknown
prices have no marker. Replace its newest-launch footer with gray `24h` and the
green USD trading-volume history across all swarm tokens, including older and
inactive launches. Keep missing buckets as gaps, never zero; coverage and source
clocks remain in the tooltip. LEADERBOARD rows have a blank before each medal,
seat numbers aligned as before, and accepted-job counts right-aligned with one
blank before the inner border. Center the green title `IMD BOARDROOM`.

Tier 2 only because integration plus tests exceeds six files; expected production
diff is below 150 lines. No new data contract, endpoint, or layout pin planned.

One coupled work package, owned by this session: add focused failing assertions;
restore existing `offer_hub_volume` polling and project its existing summary;
update rack rendering and mirrored screen CSS; run focused checks and show a
fresh keyless live render at 149×45. Then run touched/composing test files and
guards, prove changed behavior with mutations, update current documentation,
and request one final review of the complete diff. There are no independent
implementation packages or intermediate task reviews. Commit the scoped result
after the review; no full suite and no push.
