# AGENT EARNINGS footer — approved specification and work packages

## Approved scope

Replace the EARNINGS outer footer `x CLAIMED` with `x new`, where `x` is the
number of distinct tokens earned in the rolling last 24 hours. Append ` (y)`
only when a known positive `y` of those tokens were worked on by the selected
agent. Omit the suffix for zero; unknown selected work must not invent a count.
Keep the existing total earned/worked-on figures and green recent-work behavior.

Tier 2: the visible hero contract changes. The entire change is expected to be
under 1,000 production lines: no package reviews, one final whole-diff review.
Follow `CLAUDE.md`; Superpowers are disabled by the project. Use KISS and the
existing Python/Textual data-to-widget flow. No dependency, endpoint, polling,
network call, signer, key or layout-pin change is required.

## Frozen data contract and semantics

- Replace `claimed` in `SURF_AGENT_HERO_FIELDS["earnings"]` with `earned_24h`
  and `worked_on_24h`, both nonnegative integer counts or `None` when unknown.
  Preserve `state`, `read_ts`, `earned`, `worked_on`, `worked_recent`, `owner`.
- Use the existing public explorer EarnedTable records: `chain_id`,
  `token_address`, `job_id`, `launched_ts`, `builder`, `claimed`.
- Deduplicate tokens by chain and normalized token address, never by row,
  reward quantity or job alone. The same address on another chain is distinct.
- Use an asset's earliest known launch/earned timestamp: a later duplicate
  must not make an old token new.
- A token was worked on only with both a builder record and that record's job
  in the selected seat's accepted job IDs. An owner-level reward alone cannot
  establish selected-agent work. The `worked_on_24h` cohort is a subset of the
  distinct recently earned tokens.
- Use the launch/earned timestamp and the injected clock: `0 <= age < 86400`.
  Include age zero, exclude exactly 24 hours and future timestamps. Read time
  and claim time cannot substitute for earned time.
- Missing dates leave recent counts unknown unless a known old timestamp
  already excludes the asset from the window. The selected-agent builder
  subset can remain known independently. Do not publish false zero.
- Retain the raw `claimed` cache field for compatibility; it has no influence
  on the visible summary. Preserve current stale, pending and unavailable
  handling; known empty input produces real zero recent counts.

## Work packages and ownership

1. **Planner — this file only (complete on handoff).** Record approved scope,
   contract, ownership, dependency order and acceptance gates; no code changes.
2. **Root — data contract and projection.** Own
   `maxpane_dashboard/data/surf_models.py`, `surf_agent_earnings.py`,
   `surf_agent_card_sources.py`, `surf_agent_hero.py` and their data tests under
   `tests/data/`. Freeze the fields above first. Add failing focused tests,
   minimally implement the distinct recent counts and propagate them through
   source capture and projection. Retain cache compatibility and current totals.
3. **UI worker — footer rendering.** Own only
   `maxpane_dashboard/widgets/surf/agent_rack_hero.py`,
   `tests/widgets/test_surf_agent_rack_hero.py` and
   `tests/screens/test_surf_agent_hero_live.py`. Against the frozen contract,
   add failing compositor assertions and render `x new` / `x new (y)` with
   existing styles and truthful unknown states. Use exact counts normally;
   compact large counts only when text such as `4,096 new (4,096)` would not
   fit, and retain full numbers on hover. Preserve other card content.
4. **Root — integration and evidence.** Own documentation,
   rules, followups and integration outside the worker's files. Run focused
   verification, show the live render, update affected documentation, then
   commission the final review and commit the verified change.

Packages 2 and 3 may run in parallel after contract freeze; package 4 depends
on both. One owner per file; report cross-owner defects without reverting or
editing another owner's changes. No new planning workspace is needed.

## Acceptance and verification

- Data tests cover earliest dates across duplicates, mixed chain identity, builder plus accepted
  job matching, selected-seat switches, zero/recent/old/future timestamps,
  the exact 24-hour boundary, missing dates and genuinely empty input.
- Exercise unknown accepted-job data without fabricated `(y)`, retained raw
  claim cache values, and claim-state changes that cannot affect visible counts.
- Projection and compositor tests bind the new fields and show `0 new`,
  `x new`, `x new (y)` plus unknown/stale states; old total and green behavior
  remain covered. Tests use injected clocks/fixtures and never the network.
- Show a keyless live production render at **149×45** before hardening docs
  or review. Verify the new footer fits the existing **132-column** pin; do
  not move a pin to accommodate this copy change.
- Root runs touched/composing test files, fast guards and applicable docpins
  once before commit; mutation-proof changed decoding where required. No full
  suite. One final whole-diff review, one fix wave and scoped re-review only
  if production fixes land; file Minor-only findings in the followups document.
