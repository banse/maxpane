# WORKFLOWS capacity-card revision plan

Date: 2026-10-18. Tier 2. Owner requested native heroes above the existing
framed diagrams, showing input capacity, roomier or integrated alternatives,
and costs. Hide the three lower detail panels when they do not fit alongside
the complete diagram; retain access through SOURCE DETAILS.
Contract: [PRD](workflow_guide_PRD.md).

The guide, all ten diagram plans, 79 selectable nodes, source popup, lifecycle
and boardroom route already exist. Keep their behavior and the diagram's
appearance. Expected change: fewer than 1,000 production lines. One final
review, no package reviews, no full suite.

## Work packages and ownership

All writers share the working tree with other agents and user changes. Do not
revert or edit another owner's files. No child agents. File seams define
ownership; report cross-owner defects to the controller.

| Package | Exclusive owner and files | Dependencies and result |
| --- | --- | --- |
| P0: specification | Planning architect: `docs/workflow_guide_PRD.md`, this plan | Freeze the selection guidance contract, source semantics and responsive behavior. No code or measured-pin changes. |
| P1: source-backed profiles | Data implementer: new `maxpane_dashboard/data/workflow_guide_profiles.py`, `data/workflow_guide_models.py`, `data/workflow_guide_catalog.py`, new profile tests, `tests/data/test_workflow_guide.py`, companion HTML fixture | Use original and companion sources; attach six guidance records and notes to every node. No runtime source reads, I/O, dependency or top-level manager key. Parallel with P2 after the field seam below is frozen. |
| P2: presentation | Controller: `widgets/workflow_guide.py`, `screens/workflow_guide.py`, `themes/minimal.tcss`, composing screen/layout tests | Restore six native nine-row heroes; map P1 primitives directly; keep current renderer; derive lower-panel visibility from available viewport versus intrinsic graph height; retain a source link outside the diagram scroll. |
| P3: validation and documentation | Controller: README, follow-ups, measured pin evidence and composing/registry tests as needed | After P1/P2: actual bundled-source preview, responsive measurements, scoped mutations, affected-file checks, one final review, one fix wave and local commit. |

The controller owns every shared screen/CSS seam. Diagram renderer/plans,
manager lifecycle, boardroom keys and polling do not require edits. No live
quote fetch, payment execution, generic recommendation engine or runtime HTML
parser belongs in this revision.

## Frozen profile-to-view seam

Keep `WORKFLOW_GUIDE_KEYS`, widget signatures, `Catalogue.source` and the manager
handoff unchanged. Preserve original `Topic.stats` for DOCUMENTED FACTS.
Extend each `Node` with:

```text
guidance: list[GuidanceCard]      # six cards in fixed order
guidance_notes: list[str]        # exact scope, assumptions and source caveats

GuidanceCard:
  title: str                    # outer card title
  heading: str                  # inner card header
  value: str                    # numeric/estimated display, or empty for rows
  rows: list[str]               # text alternative/capacity/cost rows
  caption: str                   # inner card footer
  footer: str                    # outer card footer
```

Card order: **STEP INPUT, RENDERED, BODY, MORE ROOM, INTEGRATED, COST**.
This is a direct mapping to the existing native hero record, avoiding view-side
parsing or inferred financial arithmetic. Reuse `NewsHeroCard` to avoid live
observation timestamps/tooltips on dated documentation. All six hero widgets
have nine rows; reserve the existing row spacing in the viewport budget.

The pure data module owns formatted display records and explicit topic/node
profile membership. A `plane`/`step`/`merge` diagram role alone does not determine
an editable input budget: for example, payment stages are not authored steps
and a design critic is plane-managed even when depicted as a merge or failure.
The catalogue attaches profiles once. Widgets import no data-layer module.
If guidance is absent, show neutral dashes; never retain a prior node's figures.

Source evidence:

- `/Library/Vibes/aidude/docs/swarm-workflows.html`, already committed as the
  original fixture: flow topology, 3,000 own / 8,000 rendered characters,
  16 KiB body, included stages, company combined limit, continuation semantics.
- Its linked `/Library/Vibes/aidude/docs/swarm-work-options.html`, dated
  2026-10-18 10:50 CEST: action/space tables, docs-only continuation, scoped
  single-skill alternatives, integration options, and 0.5 IMD + runs for a
  schedule. Commit a fixture and cite the companion; production reads neither
  local absolute path.

Word figures are estimates at six characters including spaces per word,
rounded down, always visibly approximate. Preserve exact character units.
Never convert byte capacity into a prose allowance, imply output guarantees,
inflate a company request to 16,000 usable combined characters, assign a step
budget to an uneditable plane node, or charge each diagram node separately.
An alternative includes its applicability and source caveat. It is not a
universal ranking: source-backed docs-in-build/DAG, docs-only continuation,
scoped single skill and new-product company workflow have different semantics.

## Layout decision and tradeoffs

Two feasible arrangements were considered:

1. Keep heroes, diagram and lower panels permanently in an outer scrolling page.
   This preserves simultaneous content but makes the source link and selection
   context disappear below dense graphs and recreates the owner's space issue.
2. Keep heroes and framed diagram; hide the three detail panels when the full
   graph plus those panels cannot fit. Retain the fixed source link beneath the
   graph's own scroll region. This gives the diagram priority at the cost of
   one popup action to read long explanations on dense/short views.

Choose option 2, matching the owner's request. Keep explanations inline where
there is enough height. Do not shrink or restyle the four-row diagram cards.

Use the stable viewport as the budget, subtracting hero-row spacing, topic strip
and actual screen chrome. Compare the resulting main-area height to the newly
rendered diagram's intrinsic height plus diagram/title/source chrome and the
nine-row lower-panel group. All three details show or hide together. Do not
use the previous content minimum height as the input; that can oscillate after
the details change visibility. Use an eight-row figure floor when the available
space is truly small and internal diagram scrolling for excess graph rows.

Recalculate after topic selection, resize and index toggle. Selecting a node
repaints the six cards and detail snapshot but does not unnecessarily alter the
graph plan or scroll position. Preserve the 28-column index, selected topic and
node, existing color semantics, arrow topology, click surfaces and source popup
style. Keyboard selection must reveal its framed box without moving the source
link into the graph scroll. In compact mode show SOURCE DETAILS alone in the
source row; the popup retains the full selected-node label and all details.

At 149×45 dense contracts should prioritize heroes, the full framed graph and
the source link, scrolling only if necessary. Short topics may show all three
lower panels. These are desired behaviors; fit numbers must come from the
actual-source preview and later composed measurements, not previous pins.

## Sequence and verification

1. P1 writes failing data/profile tests for exact source caps, visible word
   approximation, complete six-card coverage of all 79 nodes, explicit authored
   versus plane/action profiles, specific alternatives, and truthful cost units.
   Add source-fixture agreement for new facts. Implement only the needed pure
   records/helpers and contract fields, then pass the focused tests.
2. P2 writes failing composed tests for six native heroes, selection updates,
   dense-topic compact mode, short-topic details, resize/index transitions,
   retained source access and popup completeness. Restore native heroes and
   viewport-based layout using the frozen seam. Keep the existing renderer.
3. Mirror screen CSS into the production block. Render actual bundled sources
   at **149×45** in Matrix: contracts with authored/plane selections, a short
   topic, site docs alternatives, company caps, schedule cost, open index and
   source popup. Show the owner before writing measured pins or final evidence
   and before dispatching review. Correct visual issues in this phase.
4. Measure all ten topics with index closed/open across width and height
   boundaries. Verify that hidden details are an intentional mode, not silent
   clipping; graph overflow still has a truthful hint/scroll path. Derive any
   new view pins and their `#:` explanation from the binding rendered content.
   Leave app-wide pins unchanged unless measured evidence requires otherwise.
5. Prove focused tests bite through relevant mutations: an incorrect input/cost
   profile, always-show/always-hide details, and any changed pin in both
   directions. Restore only by inverse edit. Check composited hero values and
   source links rather than merely Rich Text contents.
6. Once before commit, run touched test files and composing screen/data files
   whole with isolated HOME and worksteal. Run `guard and not mounts_app` plus
   required docpin checks. No registration/mount run unless routes/keys changed;
   no full suite. Check malformed/empty payloads, literal strings, all 79 nodes,
   arrow-key reveal, Enter/Escape popup flow and retained state.
7. One final reviewer receives the complete revision diff and the verbatim
   repository reviewer contract. Named risks: truthful scope/word estimates,
   documented alternative applicability, per-action versus included-stage or
   schedule costs, stable responsive mode, unchanged graph semantics and
   source-link accessibility. One fix wave, scoped re-review only for production
   fixes. Record Minor residuals in follow-ups and commit authorized paths only.

## Evidence status

The existing framed renderer is unchanged. Genuine-source previews show the
restored cards and automatic detail collapse at 149×45, with expanded details
on a larger view. Composed measurements preserve all diagrams at 148×44;
the densest topic restores lower details at 53 rows. Final check results and
review evidence belong in [follow-ups](workflow_guide_followups.md). Original
and companion dates are documentation timestamps, never live prices.
