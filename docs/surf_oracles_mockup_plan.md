# ORACLES / SURFBOARD mockup

## Approved design and current stage

The owner selected proposal 1, with proposal 2's expandable answer tree inside the
selected-request detail. This package implements only a standalone Textual preview
with explicitly fictional data. The sequence is ASCII selection → Textual mock-data
preview → owner feedback and approval → live API preview. The ASCII selection is
complete; API loading and production integration follow mock-preview approval.

Treat the new demo composition as Tier 2. Keep the change below 1,000 production
lines, with one final review and no individual package reviews. Superpowers remain
disabled by the project instructions. Apply KISS: local records, ordinary Textual
widgets and existing rendering helpers; no additional application framework.

## Visual and interaction contract

The target terminal is **149 columns × 45 rows**. Place six equal-width rack cards
in one row, each **nine terminal rows high**, using the existing `NewsHeroCard` and
`HeroRecord` from `maxpane_dashboard/widgets/surf/news_hero.py`.

| Outer title | Inner title | Mock value | Meaning |
| --- | --- | --- | --- |
| REQUESTS | LOADED | 100 | Requests present in this preview's loaded fixture |
| ASSESSING | OPEN | 7 | Loaded requests still being assessed |
| ATTESTED | CLOSED | 86 | Loaded requests with an attested outcome |
| NO QUORUM | CLOSED | 5 | Loaded requests closed without quorum |
| BLOCKED | ATTENTION | 2 | Loaded requests requiring attention |
| NETWORKS | CHAINS | 3 | Distinct networks represented by loaded requests |

These are **loaded-request counts**, never all-time protocol totals. The fixture
contains exactly 100 requests: 7 + 86 + 5 + 2 mutually exclusive states across three
networks. Derive the cards from those records so the table and rack stay coherent.

Use the existing rack's grey casing, dark inner readout, green accents and neutral
secondary text. Preserve meaningful state distinctions; a blocked request must not
look successful. All six cards share their top and bottom baselines. At the target
size, titles, numbers and footers remain visible without overlap or silent clipping.
Keep an explicit `MOCK DATA` marker visible in the exported frame.

Below the rack, the request table takes approximately half the width on the left.
It provides readable request identity, state and question context, with internal
scrolling for the 100 loaded rows. The right side shows the selected request's
question, result, agreement, quorum and panel target, then its expandable answer
tree. Keep these summary fields distinct: agreement is not the quorum, and the
quorum is not the panel target. Long questions may wrap; deliberate truncation must
be visible. The tree scrolls independently when expanded beyond its available rows.

Required interactions:

- Clicking a request row or pressing Enter on it selects that request and updates
  its summary and tree together.
- Nested answer branches expand and collapse with mouse and keyboard. Selection
  must preserve the distinction between opening a branch and opening an answer.
- Answer leaves identify their mock seat, including the established seat examples
  527, 1207 and 355, and expose the associated answer detail. Values remain mock
  data; these identities do not make the displayed outcomes live observations.
- Opening an answer leaf/detail uses the existing `OracleAnswerScreen`, populated
  from that leaf's exact mock record. Closing it returns to the preview.

Reuse `maxpane_dashboard/widgets/surf/_oracle_answer.py` for existing answer,
consensus and panel wording, and `maxpane_dashboard/screens/oracle_answer.py` for
the modal. Preserve its record identity (`job_id`, `submission_hash`), answer type,
question and notes rather than introducing a second answer formatter. Include
representative open, attested, no-quorum and blocked request details; each selection
must remain internally consistent. Separate mock records from UI construction so
later live-data mapping does not require a layout rewrite.

## Boundary and later data mapping

The demo must not instantiate a manager or client, fetch any URL, access a live API,
write user configuration or change production screens, shared widgets, routes,
bindings, registrations, layout pins or theme files. Reusing existing classes and
pure helpers is allowed. Use the existing Python/Textual environment; export preview
artifacts to a temporary directory and do not commit them.

The live-data stage must preserve these distinctions when its contract is designed:

- A loaded request page describes that page's coverage, not protocol-wide totals.
- Members filtered to known seats are not the whole oracle panel. Obtain agreement,
  quorum and panel target from their authoritative request data; never substitute
  the number of displayed leaves for panel size.
- A seat answer belongs to an exact submission identity. Do not join on seat or job
  alone when a submission hash distinguishes attempts.
- Unknown, unread and unavailable values remain distinct from zero, false, an empty
  answer or a negative outcome. Preserve existing answer-type interpretation and
  source freshness rather than inventing a value.

No live-data mapping, endpoint research or other dashboard redesign belongs to this
package. A keyless live render is a subsequent stage, after mock-preview approval.

## Work packages, owners and dependencies

### 1. Spec and plan — planning agent

**Owned file:** `docs/surf_oracles_mockup_plan.md` only.

Record the selected composition, loaded-count semantics, interaction requirements
and stage boundary. This package and implementation have disjoint file ownership;
the approved contract is the implementation dependency. No separate task review.

### 2. Standalone demo and tests — root session

**Owned files:** `scripts/surf_oracles_demo.py` and
`tests/screens/test_surf_oracles_demo.py` only.

**Dependencies:** Owner's selected proposal and this specification.

Write focused failing tests, then implement the smallest matching composition.
Support interactive local execution and an SVG export at 149×45. Verify the actual
composited frame and widget geometry: six equal nine-row cards, shared baselines,
visible metrics, left/right body arrangement and the mock-data marker. Assert the
fixture's 100 rows, four state totals and three networks rather than testing only
hardcoded hero strings.

Exercise request selection by mouse and Enter, nested branch expansion/collapse by
mouse and keyboard, and answer opening/closing with the exact selected record in
`OracleAnswerScreen`. Assert that changing the request replaces both summary and
tree, and that unknown values are not rendered as known zero or false. Keep tests
network-free and avoid real clipboard access and wall-clock waits.

During editing, run only the cases that exercise the changed behavior. Export,
visually inspect and show the mock preview to the owner before final review. Prove
a geometry assertion detects a deliberate regression with `scripts/mutate.py`,
restoring the source afterward. Before delivery, run the complete affected test
file with isolated HOME and `-n 4 --dist worksteal`, the fast
`guard and not mounts_app` set and the applicable docpin tests. Do not run the full
suite or change production pins for a standalone mock. Record the exact results
and preview location in the delivery message.

### 3. One final review — independent reviewer

**Ownership:** Read-only review of this specification and the two implementation
files; root retains fix ownership.

**Dependencies:** Working demo, inspected/exported preview and green scoped checks.

Review the six-card contract, fixture/count agreement, selection/tree/modal
interactions, record identity, mock-only boundary and composited test evidence.
Follow the repository reviewer contract: one final review, one fix wave for
Critical/Important findings and one scoped re-review only when that wave changes
production code. File Minor-only residuals through the existing follow-up process.

## Next decision

Deliver the Textual mock preview for owner feedback. After its approval, plan the
keyless live-data stage, show the real render before hardening and continue the
same ASCII → mock → live workflow only for the next approved dashboard.
