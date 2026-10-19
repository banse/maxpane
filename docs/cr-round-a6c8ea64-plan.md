# CR round a6c8ea64: AGENT card order and units

Date: 2026-10-19. Batch `a6c8ea64-5517-4136-9ea2-0e1e7486932d`, read and
claimed before edits. Twelve notes, grouped below; no contradictions.

## Scope and implementation plan

Tier 2: the cohesive change affects more than six files. The Agency Software
Architect checked the scope and data semantics. Root owns one package: AGENT's
card renderer, both screen/theme CSS copies, CR catalogue and related tests.
The change is below 100 production lines, with one final independent review
and no package reviews. Existing IDs and data contracts remain stable.

Change the existing ordered tuple rather than add a separate CSS ordering system.
Retain the existing job counts rather than introduce another data reader.
Use CSS margins rather than a new title spacer widget.

## Accepted behavior

Read positions left to right, then the next row:

| Position | Stable ID | Outer title | Inner heading | Inner footer |
|---|---|---|---|---|
| 1 | seat | AGENT | SEAT | existing presence |
| 2 | status | STATUS | WORKER | existing work/action |
| 3 | accepted | JOBS | ACCEPTED | acceptance rate |
| 4 | nodes | SHIP | LAUNCHES | JOBS |
| 5 | models | RESEARCH | ORACLE | JOBS |
| 6 | effort | EFFORT | HOURS | existing tokens |
| 7 | runtime | RUNTIME | SOFTWARE | model effort |
| 8 | owner | OWNER | WALLET | pairing date |
| 9 | rank | RANK | POSITION | existing total |
| 10 | collab | COLLAB | SEATS | collaborators |
| 11 | rewards | REWARDS | IMD | existing USD |
| 12 | earnings | EARNINGS | TOKENS | new-token count |

- SHIP groups notes `d0aba11b` and `8110485e`: position four, title SHIP,
  LAUNCHES heading, JOBS inner footer, digits counting jobs with launch contributions.
- RESEARCH groups `4aa2fca4`, `671f445a`, `a9f2ee73`: position five, title RESEARCH,
  ORACLE heading and JOBS inner footer.
- `fbbac0f1`: accepted card becomes JOBS / ACCEPTED.
- Position changes: `0bf79ebe` EFFORT → 6, `b4d07128` OWNER → 8,
  `9373388c` RANK → 9, `636cc72c` COLLAB → 10, `e8df6ae5` REWARDS → 11.
- `e2463433`: move only the RECORD title line up one terminal row. Keep the table's
  y-coordinate, height and bottom unchanged. Remove the outer top margin, restore
  the title's bottom margin, and increase the panel floor by one to compensate.
  Keep the existing blank row below the table and preserve filter behavior.

The CR catalogue mirrors the new order and names without changing area IDs.
These instructions supersede the preceding round's labels/order and empty
SHIP/RESEARCH inner footers.

## Counting semantics

`surf_agent_work.summarize()` already sums production launch membership over
distinct accepted job IDs; `nodes.launches` is not a count of different launches.
Repeated accepted nodes on the same job count once. Explicit workflow-linked
frontend jobs are included. Testnets remain excluded; incomplete classification
is unknown, not a fabricated zero. No data-layer change is needed.

## Verification sequence and evidence

1. Four targeted compositor tests failed against the old order, labels and title
   coordinate, then passed after the implementation. Existing production-job
   classification and deduplication tests were also run.
2. Real public-data render shown at 149×45 before pin sweeps or this document.
   Agent #420 showed 15 launch-contribution jobs and 3,208 Oracle jobs.
   The keyless read took 32.13 seconds and used only a temporary cache copy;
   local preview: `/private/tmp/agent-cr-a6c8ea64/agent.png`.
3. The RECORD geometry regression tests both stylesheet modes at 149×45, 134×29,
   134×28 and after resize back. Title y=21, table y=23; table height remains 20
   or 4 respectively. Filter close returns to the same table rectangle.
4. Six named mutations were detected: card order, missing JOBS unit, wrong SHIP
   count, old ACCEPTED heading, lost title gap and uncompensated panel floor.
   Each file was restored byte for byte.
5. In-situ measurement: capture420 clips STATUS at 133 columns and is whole at
   134/135. Stress has the taller marker at 28 rows and is whole at 29/30.
   Existing 134×29 pins remain unchanged.
6. Complete relevant widget, composing screen, work-summary and CR files:
   770 passed (`pytest -n4 --dist worksteal`); fast guards: 128 passed;
   documentation pins: 12 passed. Runs unset `NO_COLOR`; the parallel run also
   isolates `HOME`.
7. Final independent review: Approved, no findings. The reviewer verified both
   named job-semantics tests and independently killed mutations of the JOBS unit
   and RECORD geometry, restoring files byte for byte. No fix wave was needed.
8. Commit these changes locally, reload the CR catalogue without changing the
   active session/database, then archive the round with its actual commit and
   the validation evidence above.
