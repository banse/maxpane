# WORKFLOWS guide PRD

Date: 2026-10-18. Tier 2. Design approved by the owner: **Variant 2 plus a
collapsible topic index**. The current revision restores a compact native hero
row for input capacity, documented alternatives and costs while retaining the
larger outlined diagram nodes. Lower explanations yield their space when the
diagram needs it. Revision target: under 1,000 production lines. One final
review; no package reviews.

## Purpose and approved behavior

Open WORKFLOWS from IMD BOARDROOM and understand the ten documented workflows
through a selectable diagram, explanations, limits and source examples. This
is a dated documentation atlas, separate from execution history and live WIP.
It never signs, pays, creates jobs, constructs transactions or takes credentials.

- Keep the centered boardroom title and rack geometry. Add a visible clickable
  WORKFLOWS label on the title's right and a `g` shortcut outside text inputs.
  No card is displaced and no top-level dashboard/game is registered.
- Guide header states **WORKFLOWS · DOCUMENTED 2026-10-18**. A nine-row native
  hero-card row summarizes the selected node's input capacity, documented
  roomier alternatives, integrated workflow alternatives and action cost.
  These are dated documentation facts and explicitly labeled estimates, not
  live quotes or promised output sizes. Original topic facts remain in source
  detail.
- A two-row topic strip exposes all ten topics. Below it, a full-width manually
  authored terminal diagram preserves branches, joins, retries and failures.
  Diagram nodes are prominent framed cards with a role in the top border,
  two wrapped label rows, and a bottom border. Explicit arrowheads and elbow
  connectors show direction. All 79 node IDs remain individually selectable.
- Bottom panels are **EXPLANATION**, **LIMITS**, **DOCUMENTED EXAMPLE**. Show
  all three only when the full intrinsic diagram and the panels fit the
  available height. Otherwise hide all three and retain the **SOURCE DETAILS**
  popup link below the diagram. The popup always includes the full explanation,
  limits and example, plus the capacity/alternative/cost notes. Selecting a
  node updates the cards, panels and popup snapshot immediately from local
  data. Unknown limits are dashes.
- `i` toggles the initially collapsed topic index. Its expanded list names all
  topics and keeps the selected topic visible; closing restores full diagram
  width. Topic and node selection remain unchanged by this toggle.
- Click a topic to select it; click a diagram node to select it. Left/right
  move between topics; up/down move through the selected topic's nodes in
  authored order. Enter opens selected node/source detail in a
  `RecordDetailScreen` subclass. The source detail is a cached snapshot.
- Escape from source detail closes that detail. Escape from the guide returns
  to the same boardroom. Reopening preserves topic, node and index state.
- Shared footer retains app/version/theme and centered loading only during
  the local guarded acquisition. Idle has no spinner; no extra shortcut row.
- At 149×45, dense topics such as contracts prioritize the heroes, topic strip,
  framed diagram and source link; short diagrams may also show the three lower
  panels. The nine-row hero budget and nine-row lower-panel budget are design
  constraints, not measured fit pins. Keep the source link outside the graph's
  own scroll area so it remains reachable when graph scrolling is necessary.
  The 28-column expanded index remains usable. Smaller terminals scroll with
  honest clipping/height hints. Re-evaluate the fit after topic changes,
  terminal resizing and index toggles without changing selection or shrinking
  node frames. Geometry is measured after the real-source preview.

## Frozen data handoff

Own `data/workflow_guide_models.py`; do not add keys to Surf's live contract.

| Export | Value |
| --- | --- |
| `WORKFLOW_GUIDE_KEYS` | `("workflow_guide",)` |
| `WORKFLOW_GUIDE_WIDGET_SIGNATURES` | `{"WorkflowGuideView": ("workflow_guide",)}` |

`WorkflowGuideManager.get_snapshot()` and async `fetch_and_compute()` return
`{"workflow_guide": Catalogue}`. Both use retained, packaged static Python
data. No runtime HTML parser, local absolute-path access, file write, HTTP,
RPC, clock-based freshness or persistent cache is needed. Consumers treat the
snapshot as read-only. Widgets import no `data/` module.

| Record | Required fields |
| --- | --- |
| Catalogue | `source: Source`, `topics: list[Topic]` in source order |
| Source | `title: str`, `date: str` (2026-10-18), `plane: str` (745c1db4), `worker: str` (0.1.2), `references: list[str]` |
| Topic | `id: str`, `number: int`, `title: str`, `short_title: str`, `summary: str`, `stats: list[Stat]`, `diagram: list[str]`, `nodes: list[Node]`, `source_excerpt: str` |
| Stat | `title: str`, `value: str`, `caption: str`; exactly six per topic |
| GuidanceCard | `title: str`, `heading: str`, `value: str`, `rows: list[str]`, `caption: str`, `footer: str`; exactly six cards per node |
| Node | `id: str`, `label: str`, `kind: str`, `explanation: str`, `limits: list[str]`, `example: str`, `source_excerpt: str`, `guidance: list[GuidanceCard]`, `guidance_notes: list[str]` |

Topic IDs, in order: `purchase`, `single_skill`, `shapes`, `contracts`, `site`,
`company`, `oracle`, `intake`, `schedules`, `growth`.
Node IDs are unique within a topic and match `[a-z][a-z0-9_]*`.
Kinds are `step`, `plane`, `merge`, `failure`, `state`; they describe diagram
semantics, not a current job state. Each node has a selectable rendered label.

The catalogue retains its plain ASCII `diagram` and `{node_id}` placeholders
as source-oriented content. A pure data-layer profile module supplies the new
per-node guidance records; the existing top-level handoff stays unchanged.
A presentation-only plan keyed by topic/node IDs defines framed-node placement,
explicit connector routes, branch annotations and section captions. A small
Rich Text canvas renderer consumes these plans and the literal node labels;
there is no automatic graph engine or new dependency. Existing decorative
square brackets and plane dashes may be removed from the card label only.
The full original label and explanation remain in source detail.

Unknown IDs and malformed records are rejected by content tests. Every rendered
node resolves and every defined node is reachable. Labels and explanations are
literal text, never interpreted Rich markup. All ten topics include source-derived
explanation, caps, source excerpt and example; illustrative recommendations are
distinguished from the historical event that motivated them.

The six retained catalogue stats are contextual source facts, not a forced common metric schema.
Examples: QUOTE / PERMIT / BODY / PRICE / CONFIRMATIONS / EXAMPLE TIME for x402;
STEP TEXT / RENDERED / STEPS / BODY / SHAPES / MERGE for step shapes. Units and
captions must disambiguate characters, bytes, authored steps and diagram nodes.

## Capacity, alternatives and cost cards

Reuse six native hero cards, each sized to nine terminal rows; allow the row's
existing spacing separately. `GuidanceCard` maps directly to the native hero
record: `heading` is the inner header, `value` the numeric/estimated display,
`rows` the alternative text when `value` is empty, `caption` the inner footer,
and `footer` the outer footer. The view uses `NewsHeroCard` so historical facts
do not acquire live-source timestamps or tooltips. Formatting and truthful
profile selection happen in a small pure data module, attached to each node
once when the packaged catalogue is built. Widgets do not infer capacities
from diagram roles or free-text explanations. Explicit topic/node memberships
distinguish authored work, plane-managed work, state nodes and actions with
unspecified input caps. Missing guidance on a malformed or older payload paints
dashes instead of inheriting another selection's numbers.

| Card | Visible meaning |
| --- | --- |
| STEP INPUT | Approximate input words for the selected authored step or objective, with its exact character cap and scope. A plane-managed node has no separately editable step allowance. |
| RENDERED | Approximate words for the documented combined objective-plus-step cap, or company combined request/context/draft cap. Never portray this shared cap as extra independent step space. |
| BODY | Exact whole-request byte cap, normally 16 KiB where documented; this is not prose capacity. |
| MORE ROOM | A named source-supported alternative and its capacity where known, such as a scoped single-skill objective or a fresh continuation budget. Show the important qualification in the card and full detail in the popup. |
| INTEGRATED | A source-supported way to include the work in another step/workflow, with applicability limits. No generic recommendation is invented for unrelated nodes. |
| COST | The documented charge and billing unit for the selected action context. Distinguish a free check, paid action and already included plane stage; never multiply a price by diagram nodes. |

The source is the original Swarm Workflows snapshot plus its linked companion,
**Swarm Work Options**, dated 2026-10-18 10:50 CEST. Vendor the companion HTML as
a second test fixture and cite it in source references; production still uses
packaged literals only. Its action/space tables and options list provide the
specific alternative and schedule-cost evidence.

The documented limits are **characters**, not words. Word figures are explicitly
approximate input-planning estimates at **six characters per word including
spaces**, rounded down: 3,000 characters becomes approximately 500 words and
8,000 becomes approximately 1,333 words. Keep the approximation sign or `est`
visible, and retain the exact character cap in the card or its footer. The
popup explains the assumption. These values are neither token limits nor a
guaranteed output word count. Do not convert the JSON/body byte limit to words:
UTF-8, field names and JSON overhead also consume it.

Source interpretations to preserve:

- A single-skill job documents an objective of 1–8,000 characters. An authored
  step in a multi-step job has at most 3,000 own characters; objective plus that
  step is at most 8,000. One to six authored steps are included in one action.
  Templates and plane-added tests, auditors or critics do not imply additional
  paid actions or independently editable step budgets.
- Company request allows 16,000 characters individually, but request + context
  + draft objective together must fit 8,000. Its effective combined input card
  shows 8,000, with the individual-field limit retained only as a qualified
  source fact. This is not a roomier substitute for a standalone 8,000-character
  objective.
- A scoped single-skill objective can supply more dedicated input room than a
  3,000-character authored step. This is a derived comparison of documented
  caps, not a guarantee that it reproduces deployment, hosting, inherited tree
  or other integrated semantics. Scope such suggestions to applicable work.
- The site source proposes either docs directly depending on build in a DAG,
  or README work inside the build step. These are recommendations, not a
  verified recovery. A company workflow combines contracts and site for a new
  product, refuses `parentJobId`, and does not attach to existing contracts.
  The companion explicitly offers a docs-only single-skill continuation; show
  its 8,000-character objective with the single-skill qualification. General
  multi-step continuations retain the 3,000 own / 8,000 rendered / 16 KiB body
  constraints. A fresh continuation preserves the existing project but does
  not grant every authored step an independent 8,000-character budget.
- Purchase, Intake, oracle and schedule states are not authored job steps.
  Oracle question character capacity is unspecified in this source; schedules
  inherit the underlying action's caps. Unknown applicable alternatives are
  `—` / `not documented`, rather than a claim that no alternative exists.
- The source date reports **0.5 IMD per paid action**, free checks, and no result
  guarantee. Included authored/plane nodes are not per-node charges. Recurring
  schedules buy runs up front and top up; the companion documents schedule
  creation as **0.5 IMD + runs**. Display that qualification, not just 0.5 IMD
  as a whole-schedule total. Do not invent a run-count total or assume an
  undocumented topup billing formula. No live price, gas
  estimate, converted fiat figure or total inferred from node counts is shown.

The source popup retains all six original DOCUMENTED FACTS and adds the selected
guidance and its qualifications. The documentation date stays visible even when
lower panels are collapsed.

## Framed diagram presentation

Preserve the existing authored plans: at most five columns and a 24-row canvas,
adaptive card widths from 18–25 cells, and four-row cards. Extra width enlarges
cards and spacing, not the number of parallel stages. Dense diagrams keep a
readable minimum and scroll honestly. The current composed fit is measured
again after restoring heroes; previous whole-view row pins are not assumed to
remain valid.

Frames and role labels use existing theme colors. The selected frame is the
theme accent; plane roles are muted, merge roles use success, and failure
roles remain visibly erroneous even when selected. Selection is also indicated
by weight/frame styling. Card surfaces, including their borders, carry click
metadata. Arrow routes must not pass through unrelated card labels or imply
edges between parallel siblings.

| Topic | Required layout and topology |
| --- | --- |
| purchase | Six steps in two rows of three, with an unambiguous directed turn. |
| single_skill | Four-step main path; accepted branch to delivered, failed retry to dispatch, third-failure branch to blocked. Retry condition is visible. |
| shapes | Three separately labeled bands: CHAIN, FAN OUT / JOIN, DAG. Components A/B/C all feed integration. DAG build feeds check and docs; docs feeds tests; check/tests feed critic. |
| contracts | Import/adapt lead to six parallel stages in one vertical column. Separate split/join rails connect every tests/manifest/audit card to judge. Judge leads to deploy/live or undeployed. No sequential links between parallel stages; the common rails and PARALLEL label establish simultaneity. |
| site | Build/check/docs path, with build and docs feeding critic. Blocked is observed, hosted is explicitly not reached. Proposed recovery is a separate, labeled recommendation. |
| company | Six stages in two rows of three, preserving order through deployment, frontend, publication and validation. |
| oracle | Request/admit/panel/attest/writer/registry path with stored and Missed outcome branches. |
| intake | Five main states, received to refused and admitted to failed. Keep the source discrepancy in detail. |
| schedules | Slot branches to opened, skipped or failed. Opened leads through remaining to exhausted; failed leads to paused. Topup applies to paused/exhausted as a documented action, never an automatic retry. |
| growth | Observed launch/site and proposed fix/feature/further continuations remain separate groups. Fresh job is explicitly a new project. |

Free-text source caveats and historical example sentences can move from the
canvas to the existing explanation/source areas. Labels needed to interpret
an edge or distinguish observed/proposed/not-reached paths remain on the canvas.

Detail-panel visibility is derived from the available viewport and the freshly
rendered diagram's intrinsic height, plus measured panel/source-link chrome.
Do not derive it from a previous content minimum height, which could create a
resize feedback loop. Hide/show the three panels as one group. Their absence
is intentional responsive behavior and must not itself light a clipping hint;
actual graph overflow still uses scrolling and truthful hints. Source access
and keyboard-selected boxes stay reachable at every supported size.

## Presentation and lifecycle handoff

`WorkflowGuideScreen(manager, *, view_state=None, **kwargs)` subclasses the
shared dashboard base with `POLL_DATA = False` and its own `GAME_NAME`, refresh
worker name and declarative PANELS adapter. The root-owned default
`DashboardScreen.POLL_DATA = True` preserves every existing screen's schedule;
the new guard skips only periodic data polling. Initial refresh, explicit
refresh, cancellation and common footer still use the shared lifecycle.

`WorkflowGuideView.update_data(workflow_guide=None)` consumes the catalogue.
Its package owns topic/node selection messages and the popup. A caller-owned
`view_state` dict retains `topic_id`, `node_id`, `index_open`; defaults are the
`contracts`, its first node and false. Invalid stored IDs fall back safely.
The screen is the adapter between view messages and this retained state.

The boardroom retains the guide manager and view state for repeated opens.
Opening suspends the boardroom's acquisition through existing screen lifecycle;
closing resumes only boardroom reads. UI interaction does no I/O. The static
guide has no 30-second data poll or background detail request. If a future
source becomes external, its acquisition belongs to the reader layer and is
outside this PRD.

## State and failure behavior

| Trigger / state | User-visible behavior | Recovery / side effects |
| --- | --- | --- |
| First open | Header/frame; initial cached catalogue paints through guarded refresh | No network, writes, payment or DB state |
| Select topic/node | Diagram, six guidance cards and available panels agree on selection | Local repaint only; old selection cannot overwrite new one |
| Resize / toggle index | Details appear only when graph and lower panels both fit; source link remains accessible | Stable viewport-based calculation; no acquisition or selection reset |
| Open/close detail | Full explanation, limits, example, guidance qualifications, excerpt and provenance; previous guide selection retained | Snapshot only; Space/Escape/X closes |
| Invalid retained selection | Contracts topic (or first valid topic) and first node selected | Normalize retained in-memory state |
| Empty/missing payload | Neutral dashes and no selectable phantom node | Existing good content retained where available; no retry loop |
| Long content / small terminal | Scrollable panels/diagram and honest size hints | No lost numeric fields, hidden branches or inaccessible topics |
| Rapid open/close/reopen | Current screen owns presentation; cached state returns | Shared refresh cancellation; no recurring static acquisition |
| Refresh failure in injected test | Prior content stays, loading ends; shared log records failure | Manual reopen/refresh remains possible; no timer retries |

Remote workflow failure, timeout and payment branches shown in the atlas are
historical descriptions only. The guide does not imply it observed, recovered
or executed any of those operations. Gaps in the source remain explicit in
detail; unsupported retry/timeout values are not invented.

## Acceptance

All ten topics and all declared nodes can be reached by keyboard and mouse;
index and selected state survive return; each node resolves the correct detail.
Source and diagram discrepancy notes remain available. Six native heroes show
scoped capacity/alternative/cost guidance; existing framed nodes and the shared
footer retain their appearance. Dense diagrams suppress only the three lower
panels, whose content remains in source detail. Word estimates cannot be
mistaken for exact character limits, plane nodes cannot acquire fabricated
input budgets, and paid-action prices cannot become per-node/workflow totals.
No installed runtime references `/Library`.
Evidence comprises offline data/content tests, composited screen/widget tests,
focused lifecycle and route regressions, mutation proof for relevant state/
scheduling gates, and a real bundled-source 149×45 preview before hardening.
