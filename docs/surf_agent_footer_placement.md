# AGENT card footer placement

Date: 2026-10-19. Tier 2 because the change touches a shared widget. Approved
scope: the AGENT dashboard's ten cards other than SEAT and STATUS. Expected
production change is under 100 lines and removes obsolete rendering branches.
One final review on the most capable available model; no package reviews.

## Specification

For each affected card, remove its former outer footer, move the current inner
footer text to the outer card footer, and clear the inner footer. Render the
moved text using the native muted, regular-weight footer style. The inner
bottom border becomes continuous; card heights, positions, digits, content,
header and frame styling remain unchanged.

| Card | Text moved to the outer footer |
| --- | --- |
| ACCEPTED | Acceptance percentage |
| EFFORT | Output-token count |
| RANK | `of` ranked-seat count |
| REWARDS | Existing USD equivalent |
| RUNTIME | Existing runtime/daemon update status |
| MODELS | Advertised model count |
| OWNER | Existing paired date |
| SHIPPED | `oracle` job count |
| COLLAB | `collaborators` |
| EARNINGS | Tokens newly earned in the last 24 hours, `x new` |

SEAT and STATUS retain both existing footer locations and behavior. STATUS
retains its activity meter. Existing unknown/empty-state captions and missing
values keep their meanings; an absent inner caption produces a blank outer
footer. No former paid/since/rank-delta footer is substituted back in.

Retain the source tooltip facts, including payment/connection times, exact
counts and runtime detail. Preserve OWNER's explorer/copy affordances and
runtime/rank frame accents. Only the moved outer caption becomes uniformly
muted and regular. Strings remain literal and sanitized. Keep the full caption
in the border subtitle so the inherited width check can signal clipping;
especially do not silently shorten a long runtime caption.

No data model, manager, acquisition, endpoint, polling, key or dashboard-route
change is required. Geometry pins are not changed unless composed measurement
demonstrates that their existing claim is no longer true.

## Implementation plan and ownership

The controller owns the single implementation package:

- `maxpane_dashboard/widgets/surf/agent_rack_hero.py`
- `tests/widgets/test_surf_agent_rack_hero.py`
- `tests/screens/test_surf_agent_hero_live.py`

The planning architect owns this document until handoff. All agents share the
working tree; do not revert another contributor's changes. No child agents.

1. Add focused failing composed assertions for the ten moved captions, empty
   inner-border labels, muted regular styling and preserved SEAT/STATUS behavior.
2. At the end of each `agent_records` entry, after state-specific caption
   handling, move `subtitle` to `footer` and clear `subtitle` unless the key is
   `seat` or `status`. Remove obsolete outer-footer calculations. Render the ten
   moved captions directly as dim literal Text; leave the two exceptions intact.
3. Verify update/resize behavior, unknown/empty states, narrow runtime clipping
   hints, OWNER actions, unchanged dimensions and existing source tooltips.
   Update obsolete caption expectations in touched tests while retaining the
   associated behavior coverage.
4. Show the actual-source render before measured pin evidence or review. Then
   run affected widget and composing screen files, relevant layout checks and
   repository-required fast guards. No full suite. Prove changed assertions
   through a focused mutation where required by repository rules.
5. One final reviewer receives the full diff and the repository reviewer
   contract. One fix wave; scoped re-review only if production fixes are needed.
   Record Minor residuals here, then commit only the authorized change.

## Evidence and follow-ups

The controller showed an actual keyless SurfManager render for seat 420 at
149×45: `/tmp/agent-footer-preview/live.png`.

Before production edits, the composing test already failed on its obsolete
expectation for `75% premium`. Updating that expectation is part of replacing
outdated caption assertions, not evidence of a regression introduced here.

The composed measurements retain the existing 134-column / 29-row boundary.
`scripts/measure_layout.py` checked worst-a at widths 132–149 and capture at
133–135 columns; narrow STATUS still binds. Longer runtime captions retain
their full text and advertise clipping below their required width.

Verification: 138 touched/widget/composing tests, 164 AGENT layout cases and
128 fast guards passed. The final review approved without findings. Disabling
caption promotion failed both new composed tests (132 and 149 columns); the
mutation was restored byte-for-byte. No full suite was run and no follow-ups
remain from this change. IMDB recorded `none`: no new protocol knowledge.
