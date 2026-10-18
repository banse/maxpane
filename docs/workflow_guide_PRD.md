# WORKFLOWS guide PRD

Date: 2026-10-18. Tier 2. Design approved by the owner: **Variant 2 plus a
collapsible topic index**. Implementation target: under 1,000 production lines,
excluding curated documentation content. One final review; no package reviews.

## Purpose and approved behavior

Open WORKFLOWS from IMD BOARDROOM and understand the ten documented workflows
through a selectable diagram, explanations, limits and source examples. This
is a dated documentation atlas, separate from execution history and live WIP.
It never signs, pays, creates jobs, constructs transactions or takes credentials.

- Keep the centered boardroom title and rack geometry. Add a visible clickable
  WORKFLOWS label on the title's right and a `g` shortcut outside text inputs.
  No card is displaced and no top-level dashboard/game is registered.
- Guide header states **WORKFLOWS · DOCUMENTED 2026-10-18**. Six equal nine-row
  rack cards carry selected-topic statistics with explicit units/context.
  Values describe that document, never a fresh observation.
- A two-row topic strip exposes all ten topics. Below it, a full-width manually
  authored terminal diagram preserves branches, joins, retries and failures.
- Bottom panels are **EXPLANATION**, **LIMITS**, **EXAMPLE**. Selecting a node
  updates those panels immediately from local data. Topic-level summary is the
  fallback where no node is selected. Unknown limits are dashes.
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
- At 149×45 the normal collapsed layout shows six hero cards, both topic rows,
  the complete selected diagram and all three lower panels. Expanded index
  remains usable. Smaller terminals scroll with honest clipping/height hints.
  Geometry is measured after the real-source preview, never inferred as a pin.

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
| Node | `id: str`, `label: str`, `kind: str`, `explanation: str`, `limits: list[str]`, `example: str`, `source_excerpt: str` |

Topic IDs, in order: `purchase`, `single_skill`, `shapes`, `contracts`, `site`,
`company`, `oracle`, `intake`, `schedules`, `growth`.
Node IDs are unique within a topic and match `[a-z][a-z0-9_]*`.
Kinds are `step`, `plane`, `merge`, `failure`, `state`; they describe diagram
semantics, not a current job state. Each node has a selectable rendered label.

Diagram lines contain plain ASCII connectors and `{node_id}` placeholders.
Each placeholder renders the corresponding complete `label`, with selection
and click metadata. Spaces/newlines preserve the authored layout; no automatic
graph engine. Unknown IDs and malformed records are rejected by content tests.
Every rendered node resolves and every defined node is reachable. Labels and
explanations are literal text, never interpreted Rich markup. All ten topics
include source-derived explanation, caps, source excerpt and example; illustrative
recommendations are distinguished from the historical event that motivated them.

The six stats are contextual source facts, not a forced common metric schema.
Examples: QUOTE / PERMIT / BODY / PRICE / CONFIRMATIONS / EXAMPLE TIME for x402;
STEP TEXT / RENDERED / STEPS / BODY / SHAPES / MERGE for step shapes. Units and
captions must disambiguate characters, bytes, authored steps and diagram nodes.

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
| Select topic/node | Diagram and three panels agree on selection | Local repaint only; old selection cannot overwrite new one |
| Open/close detail | Full literal excerpt and provenance; previous guide selection retained | Snapshot only; Space/Escape/X closes |
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
Source and diagram discrepancy notes remain available. Six cards and the shared
footer match existing rendering. No installed runtime references `/Library`.
Evidence comprises offline data/content tests, composited screen/widget tests,
focused lifecycle and route regressions, mutation proof for relevant state/
scheduling gates, and a real bundled-source 149×45 preview before hardening.
