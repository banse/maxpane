# WORK IN PROGRESS boardroom card

Approved 2026-10-13: replace the PORTFOLIO rack card in its existing position.
Use proposal 1 with proposal 2's outer footer. Keep the rack's existing size,
colors, black inner box and muted Japanese caption in its current gap.

- Outer title: WORK IN PROGRESS.
- Inner title: ACTIVE JOBS; existing three-row digit renderer shows executing jobs.
- Inner bottom: `1 workflow` or `N workflows` for active loaded workflows.
- Outer bottom: `5 build · 4 review`, using current working-step counts.
- Click/Enter opens the existing Work dashboard; Escape returns to boardroom.
- Reuse the same bounded WorkReader snapshot and cache. The reader is eligible
  while either boardroom or Work is visible; no duplicate collection path.
- Unknown counts use an em dash. Stale snapshots retain counts with an explicit
  `stale HH:MM` inner subtitle. Partial coverage/read time belong in card detail.
- Abbreviate footer labels only when needed to fit; never widen this card alone.

## Frozen seam

Card identity/destination `work`; `work_summary` added to SURFBOARD_CARD_FIELDS,
containing the existing jobs/workflows/seats/build/review/blocked summary.
Other cards leave that field None. Primary/secondary/status/meter_state/detail
retain their existing meanings. No new top-level payload key or widget class.

## Work packages

1. Data owner: surfboard.py, surf_manager.py and their data tests. TDD the card
   projection, shared read lifecycle, same-snapshot dispatch, and cancellation.
2. Controller: surf_models.py, rack.py, surfboard screen, UI/routing tests and
   docs. TDD digits, subtitles, neutral/active/stale states, fitted footers and
   navigation. Data and UI can proceed independently against the frozen seam.
3. Controller integration: show a fresh keyless 149×45 production render first,
   then certify existing geometry boundaries, mutation checks, touched and
   composing tests/guards. Run registration checks for changed card routing.
4. One final review (expected well under 1,000 production lines), one fix wave
   and scoped re-review if needed; record remaining findings in work followups.
   Commit only this task; no deployment or push.
