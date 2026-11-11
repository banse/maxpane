# Boardroom order and count scope

User request, 2026-11-11. Tier 2, one root-owned package under 100 production
lines, one final review. IMDb and terminal-layout guidance reused.

## Contract

- Restore normal outer framing for NOT ACCEPTING; outer NA remains orange and
  the refusal bar remains red. Keep the orange inner border and caption.
- Swap SWARM and SHIPPED, including physical grid positions and keyboard
  navigation. Result: ONCHAIN FEED, SWARM, WIP, RESEARCH, POOL4, SHIPPED.
- Audit working-agent scopes before changing numbers. Both WIP and SWARM use
  the full-roster distinct busy-seat total. RESEARCH matches running assignments
  to assessing requests and is a subset, not an additive population. Preserve
  these valid totals and clarify the overlap in the card tooltips.
- Do not subtract independently timed counts, introduce role partitioning,
  alter polling, change navigation destinations or rewrite source clocks.

## Work and verification

Root owns rack.py presentation/order, surfboard.py tooltip scope, their fixture
and composited regression tests, the screen pin comment and docs. The planning
agent audits count semantics read-only. TDD covers normal outer border with NA
orange, new order and arrow navigation, and total/research overlap from the
existing captured standing fixture. Show a live 149x45 render before boundary
certification and docs. Check the unchanged 143x37 pin, mutate the changed
behavior, run touched/composing files once plus guards/doc pins, compare baseline
failures with c2589c74. One final review, then commit exact paths locally.

## Evidence

- Live capture at 149x45 showed 1,053 online agents and 9 working seats in
  both WIP and SWARM; RESEARCH's one assigned seat, 1548, was among those nine.
  Before/after busy rosters agreed. All nine standing reads completed. The
  official API docs make `exclude=oracle` opt-in, and WIP does not use it.
  `health.workingNow` is a separate population and was not substituted.
- `/tmp/boardroom-order-live.png` was shown before hardening. Normal AGENT
  outer framing, orange inner NOT ACCEPTING / outer NA, red refusal bar and the
  new top-row order are visible. The unchanged 143x37 pin passed eleven boundary
  samples, including scrollbar onsets; `/tmp/boardroom-order-sweep.log`.
- Five focused checks passed. Three mutations were caught and restored:
  orange outer border, wrong SWARM position, and subtracting RESEARCH from WIP.
  Logs: `/tmp/boardroom-order-focused.log`, `/tmp/boardroom-order-mutations.log`.
- The one composing run passed 523 cases. Four old position/width expectations
  were updated and checked separately, including SHIPPED's wider last column
  at 180 columns and its complete footer at the 143-column minimum. The other
  39 failures reproduce on unchanged c2589c74. These are existing palette,
  retired card-structure and navigation harness debt; no production workaround.
- Fast guards: 130 passed, one existing TOKENS/SWORN CSS-slice failure also
  reproduced at c2589c74. Documentation pins: 12 passed. Exact composing,
  guard and baseline results: `/tmp/boardroom-order-{composing,guards,baseline}.xml`.
- Final review: Approved, no findings. Nine named cases passed independently;
  a mutation separating SHIPPED's keyboard row from its physical position was
  caught by the navigation test and restored byte-for-byte. Review logs:
  `/tmp/boardroom-order-review-{tests,mutations}.log`. No new follow-up remains.
