# SWARM hero mockup — proposal 2

## Approved scope and stage

The owner selected proposal 2, the balanced overview: combine fleet figures and
daily output, retain workflow and deployment summaries, and add a readable preview
of the latest workflow. Use the equipment-card design established by the dashboard
rack and the approved ONCHAIN NEWS hero.

This package is a standalone Textual mockup only. The sequence remains three ASCII
proposals → selected Textual mock-data preview → owner feedback and approval → API
integration. The ASCII selection is complete. Do not load APIs or integrate the
production SWARM screen during this stage. The owner's mock-only stage governs
preview data and overrides the general live-render-before-hardening requirement.

Treat the new composition as Tier 2, keep the implementation below 1,000 production
lines, and use one final review without individual package reviews. Superpowers
remain disabled. Prefer direct Textual composition and reuse over a new framework.

## Layout and content contract

Target **149 columns × 45 rows**. Show six equal-width rack cards in one row, each
**nine terminal rows high**, in this order. Every number, sentence and plotted point
is explicitly fictional mock data.

| Outer title | Inner title | Inner content | Inner bottom line | Outer bottom line |
| --- | --- | --- | --- | --- |
| FLEET | STATS | `online 966`, `working 8`, `enrolled 1,972` | None | `AGENTS` |
| OUTPUT | 24H | `steps 2,621`, `jobs 224`, `oracles 48` | None | `24H` and fictional sparkline |
| WORKFLOWS | STATUS | `completed 142`, `running 4`, `blocked 3` | `149 cached` | `JOBS` |
| LAUNCHES | STATUS | `live 47`, `parked 2` | `49 cached` | `DEPLOYMENTS` |
| LATEST WORKFLOW | OBJECTIVE | `Build a shared workspace for agent reviews…` | `8m ago` | `RUNNING` |
| SITES | CURRENT | Native Textual Digits displaying `63` | `named sites` | `ENS` |

Reuse `NewsHeroCard` and `HeroRecord` from `widgets/surf/news_hero.py` without changing
their production behavior. Preserve grey outer casings, dark inset backgrounds,
theme-green accents, aligned label/value lists, wrapped preview text, native digits
and the existing sparkline treatment. All outer bottoms share a baseline. At the
target size, titles, values, inset footers and outer footers must remain visible.
Long preview prose may truncate only with an explicit ellipsis.

Below the heroes, retain the native SWARM context: WORKFLOWS alongside LATEST
LAUNCHES, followed by full-width LAUNCHES and SITES. Populate the existing
`SurfSwarmWorkflows`, `SurfSwarmLatestLaunches`, `SurfSwarmLaunches` and `SurfSwarmSites`
widgets directly with fictional records. This context supports design review;
it does not authorize redesign of the production body.

Keep a visible `MOCK DATA` marker in both the interactive and exported views. Keep
hero records and body records separate from rendering/layout construction, with a
fixed mock snapshot time. Smaller terminals must expose overflow through scrolling
or an explicit size hint, without shrinking away card content or silently hiding
the last cards. This is demo behavior, not a production layout-pin change.

## Boundaries and later data meaning

Do not instantiate managers or clients, make network requests, read or write user
configuration/cache files, or change production screens, routes, registrations,
stylesheets or layout pins. The existing Python/Textual environment is sufficient.
Preview SVGs belong in a temporary directory and are not committed.

Future integration can reuse fleet and 24-hour output from the existing overview,
accepted-step history from `surfboard_hourly`, workflow records, launch summaries,
and current named-site records. The OUTPUT chart represents accepted steps only,
not combined jobs/oracles. Cached workflow/launch counts are not guaranteed lifetime
totals; current named sites do not imply website uptime. No new API or invented
history is necessary to evaluate this mockup. Live contracts and source clocks are
deferred until the visual design is approved.

## Work packages and ownership

### 1. Spec and plan — planning agent

**Owned file:** `docs/surf_swarm_hero_mockup_plan.md` only.

Record the selected contract and stage boundaries. Do not edit implementation or
other agents' work. This package has no separate task review.

### 2. Demo and verification — root session

**Owned files:** `scripts/surf_swarm_hero_demo.py` and
`tests/screens/test_surf_swarm_hero_demo.py` only.

**Dependency:** Proposal 2 selected and this plan available.

Write focused failing tests, then the smallest standalone composition using the
existing card renderer and native SWARM body widgets. Provide a local launch path
and an SVG export at 149×45. Tests must inspect composited output and actual widget
geometry: six equal nine-row cards, common baselines, no overlap, exact selected
data/footers, visible mock-data marker and the four contextual panels. Exercise a
narrow terminal to verify the overflow policy without network access.

During editing run only changed cases. Export and visually inspect the 149×45 SVG,
then show it to the owner before final review. Prove a geometry assertion detects
a deliberate reversible layout regression using the repository mutation tooling.
Once before commit, run the complete affected test file with isolated HOME and
`-n 4 --dist worksteal`, fast `guard and not mounts_app` checks and applicable
docpins. Do not run the full suite. Root records the preview and exact green results.

### 3. One final review — independent reviewer

**Ownership:** Read-only review of the plan and the two implementation files.
Root retains all fixes and commit ownership.

**Dependencies:** Working demo, inspected preview and green scoped checks.

Review the selected six-card design, renderer reuse, mock-only boundary, body
context, narrow behavior and composited test evidence. Apply the repository review
contract: one final review, one fix wave for Critical/Important findings, and one
scoped re-review only if fixes change production code. File Minor-only residuals
through the existing follow-up process rather than expanding the mockup.

## Next decision

Deliver the SWARM Textual mockup for owner feedback. After approval, connect the
existing data sources and show the live render before hardening that integration.
Complete SWARM's live-data confirmation before starting the next dashboard's
ASCII → Textual mockup → API design loop.
