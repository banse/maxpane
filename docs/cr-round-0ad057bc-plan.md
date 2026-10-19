# CR round 0ad057bc: AGENT cards and RECORD spacing

Date: 2026-10-19. Batch `0ad057bc-b47f-402d-a098-04a19b91297a`, claimed before edits.
The five submitted requests authorize this implementation. No contradictory notes.

## Scope and decisions

Tier 2 because the cohesive change crosses more than six files. The Agency Software
Architect reviewed the scope and plan. Root owns the renderer, both CSS copies,
catalogue labels and tests together; these depend on the same card mapping. Fewer
than 200 production lines are expected, so there is one final independent review
and no package reviews. KISS: compose existing observations in the AGENT renderer
instead of adding data-contract keys, endpoints or a second model projection.

The terminal-layout and imdb skills apply. This request supersedes the older
MODELS presentation, SEAT captions, SHIPPED Oracle footer and blank row above
RECORD described in previous card specifications. Other cards retain their layout.

## Accepted behavior

- `2f058329-727a-4786-a1c6-ef334de2e211`: internal card key `models` remains stable;
  outer title RESEARCHED, inner header ORACLE, tall digits from `nodes.oracle`.
  State, clock and source tooltip also come from `nodes`. These are distinct
  accepted production Oracle jobs, excluding testnets, as already projected.
  Unknown stays `--`; observed zero stays zero.
- `d919051a-87ce-4405-b8df-853ae9a24505`: SHIPPED retains its launch-job digits
  and LAUNCHES header; its inner footer is empty, including unavailable states.
- `10ebf5eb-eed0-4b33-b9ed-a387a53e24a1`: RUNTIME's third row becomes `model` /
  first advertised model, with its effort in the inner footer. With several models,
  keep a visible `+N` suffix and all model/effort pairs in the tooltip. Models use
  their own availability and timestamp even when the runtime check is unavailable.
  Empty advertisements say `none`; unread values say `--`. Runtime's outer footer
  is always blank. Keep version/update color and connection details in the tooltip.
- `95993050-dcd6-44db-b89c-a2fb905ade62`: outer AGENT, inner SEAT. Working workers
  say OPERATING; idle/paused say ON; offline says OFFLINE. Unknown presence stays
  unknown. Retain ERC-8004 identity, existing colors, and API pairing state on hover.
- `88689570-a656-4477-99dd-aabfd346ed4e`: keep the RECORD title and panel fixed,
  move the table up exactly one terminal row, and put the released blank row below
  it. Preserve table height, scroll/filter behavior and both stylesheet variants.

The CR catalogue keeps stable area IDs but shows the new AGENT and RESEARCHED labels.

## Work and verification order

1. Write compositor regressions, observe the old rendering fail, implement the
   smallest card/CSS changes. Remove the retired custom model renderer.
2. Show a real keyless render at 149×45 before layout measurements or this document.
3. Measure with `scripts/measure_layout.py`; verify width/height boundaries and
   source failures. Run named mutations, touched/composing files and fast guards.
4. One independent final review, bounded fix wave if necessary, then local commit.
5. Close/archive this batch only with the actual commit and validation evidence.

## Evidence collected

- New card regressions: 26 failures before implementation, then 26 passes.
- RECORD integration failed at table y=24 versus title bottom=23, then passed after
  moving the margin; the title remains at y=22 and table height stays unchanged.
- The composing test already expected obsolete premium/worked-on/since labels at
  baseline `bee470c2`; updated those assertions to the previously approved display.
- Live keyless AGENT read completed in 18.83 seconds using a temporary cache copy.
  Agent #420: Oracle 3,208, launches 15, model fable 5.1, effort high, idle/ON.
  Render shown at 149×45; local evidence `/private/tmp/agent-cr-0ad057bc/agent.png`.
- In-situ `capture420` width measurement: 133 clipped STATUS's accepted-time caption;
  134 and 135 whole. Existing 134-column / 29-row pins remain unchanged.
- AGENT boundary cases: 158 passed. Touched/composing files, production-job
  classification and CR service checks: 767 passed. Fast guards: 128 passed;
  documentation pins: 12 passed. Seven deliberate source/count/caption/spacing
  mutations were detected by their named compositor tests.
- Final review identified one source-independence defect: `unknown_seat` and
  `stale_unknown_seat` could overwrite an observed Runtime effort with `never paired`.
  Both regressions were red before the one-line fix; Runtime now preserves the
  independently observed effort in these states too.
- After the fix: both affected widget/integration files passed all 106 cases.
  Scoped re-review: Approved; reverting the fix makes both unknown-seat regressions
  fail. No open findings remain for this round. The full suite was not requested;
  only the relevant files and required guards were run.
