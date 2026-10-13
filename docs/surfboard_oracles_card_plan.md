# Boardroom ORACLES card: approved specification and implementation plan

Date: 2026-10-13. Tier 2; expected change below 1,000 production lines. One final
review after the live render, with no package reviews. Use existing Python,
Textual and Rich architecture. This connects the approved option-1 mockup.

## Approved behavior

The owner requested an oracle card that “should replace the LAUNCHPAD card,”
selected option “1,” then approved the rendered mockup: “looks good continue.”

- Replace only the boardroom LAUNCHPAD slot (row 1, column 0) with **ORACLES**.
  Preserve standard card geometry, black inset and neighboring captions/cards.
- Inner title **ASSESSING**, large digit for loaded requests whose state is
  `assessing`, inner footer **<n> loaded**, outer footer **<n> attested**.
  Mock values 7 / 100 / 86 are examples, never production defaults.
- Paint the inner frame and title orange for a fresh positive assessing count,
  including a partial page; default grey at zero, stale or unavailable.
- Click or Enter opens the existing ORACLES dashboard through `MODE_ORACLES`;
  returning retains the boardroom. Keep native LAUNCHPAD navigation intact.
- Counts describe the newest loaded request page, currently capped at
  `surf_oracles.PAGE_LIMIT == 100`, never an asserted global total. A successfully
  empty list means real zero counts. No usable list means unknown, never zero.
- Keep **<n> loaded** for fresh complete and partial pages: “loaded” explicitly
  scopes the counts. The decoder marks coverage partial at the page cap; retain
  that metadata and disclose the cap or excluded rows in the tooltip. Replace the
  inner footer with compact `stale HH:MM` or `unavailable` when appropriate.
  Tooltip text includes assessing, loaded and attested counts, page scope, source
  state and successful read time; retained stale evidence is never presented live.

## Frozen representation and read lifecycle

Reuse the current card fields; add no model keys or endpoint/cache layer.

| Existing field | ORACLES value |
| --- | --- |
| `key`, `destination` | `oracles` |
| `title` | `ORACLES` |
| `primary` | Assessing count as digits, or `—` without usable evidence |
| `secondary` | Loaded count for `ok`/`partial`, otherwise the explicit degraded footer above |
| `numerator`, `denominator` | Attested and loaded counts; preserve real `0 / 0` |
| `meter_kind` | `oracles` |
| `meter_state` | `ok`, `partial`, `stale` or `unavailable` |
| `status` | `assessing` for positive counts in `ok`/`partial`, `idle` for zero in `ok`/`partial`; otherwise source state |
| `detail` | Literal tooltip containing all three counts, scope and read clock |

The outer footer reads the attested numerator (`— attested` when unavailable),
without a progress bar. The existing pure card projection consumes
`surf_oracles` from the manager's shared reader snapshot.

Boardroom visibility offers only the existing oracle request-list read. Selected
request details are eligible only while the native ORACLES mode is active. Mode
transitions must not cancel a list still needed by either visible consumer, allow
detail reads to continue after native mode closes, or launch duplicate reader
tasks. Preserve selection, per-request detail identity, existing cache TTL/backoff,
retained last-good evidence and shutdown cancellation. Projection remains pure;
the manager owns read scheduling. Keep legacy launchpad helpers needed elsewhere.

## Exclusive work packages

Owners preserve concurrent work and report defects outside their owned files.
The planner owns this document only. No child agents or separate package reviews.

| Package | Owner and files | Dependencies / acceptance |
| --- | --- | --- |
| Data and lifecycle | Data implementer: `maxpane_dashboard/data/surf_oracles_reader.py`, `surf_manager.py`, `surfboard.py`; focused `tests/data/test_surf_oracles_reader.py`, `test_surf_manager_surfboard.py`, `test_surfboard.py` and a dedicated data test if needed | Frozen representation above. Shared list data supplies all three correct counts; inactive native mode performs no detail I/O; consumers share one reader. |
| Card, navigation and integration | Controller: `maxpane_dashboard/widgets/surfboard/rack.py`; `scripts/surfboard_oracle_card_demo.py`; `tests/surfboard_fixtures.py`; affected widget/screen/preview tests; integration documentation | Can start against the frozen fields in parallel. Correct labels, colors, counts and destination appear in the existing slot; captions and all card heights/widths remain correct. |

### Data acceptance and focused tests

Write failing offline tests first. Cover fresh positive/zero, empty/unavailable,
mixed states, page-cap partial, retained stale after failure, successful read
clocks, and the three-count relationship. Prove boardroom offers list-only work,
native mode adds selected detail, concurrent offers deduplicate, both mode orders
preserve required work, leaving native mode blocks further detail requests, and
shutdown cancels owned work. Reuse injected clients/clocks and existing fixtures.

### Card and integration acceptance

Assert composited output and style for active, zero, partial, stale and unavailable
states. Verify the outer footer, tooltip scope/clocks, ordinary digit geometry,
ORACLES slot/caption positions, and Click/Enter navigation with boardroom return.
Update the approved offline preview adapter without adding live reads to tests.
Existing native oracle selection and answers remain functional.

## Completion sequence

1. Integrate both disjoint packages and pass focused tests while editing.
2. Show a real keyless boardroom render at **149×45**, before layout/doc hardening
   or final review. Check the live count source and native navigation; incorporate
   any owner corrections before continuing.
3. Follow the terminal-layout skill for existing boundary/resize checks. Change no
   pin or its evidence block unless measured geometry requires it. Prove changed
   scheduling/cancellation gates with focused mutation checks.
4. Run touched files and composing screen/manager tests once with isolated test
   home and worksteal, then `guard and not mounts_app` checks and relevant doc pins.
   Tests remain offline and avoid the real clipboard. No full suite.
5. Dispatch one final review with the repository reviewer contract. Allow one fix
   wave and a scoped re-review only for production fixes; file Minor residuals,
   update follow-ups and commit the scoped change. No production secrets or keys.


## Completion evidence

Implemented 2026-10-13. The live 149×45 render showed 0 assessing / 100 loaded /
70 attested before layout hardening and review. Existing 144×37 geometry remains
unchanged. Validation: 482 affected tests, 124 guards and 12 docpins passed; three
implementation concurrency mutations were rejected. Final review approved with
no findings, 12 focused checks and one additional rejected cancellation mutant.
No outstanding follow-ups.
