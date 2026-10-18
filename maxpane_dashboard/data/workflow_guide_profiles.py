"""Pure guidance curated from the two supplied 2026-10-18 documents.

These are dated documentation facts, not current protocol limits or live quotes.
Membership is authored explicitly: a diagram's visual role is not an input schema.
"""

from maxpane_dashboard.data.workflow_guide_models import GuidanceCard, Node

_PROFILES = {
    "purchase": {"action": "check quote signatures submit settle admitted"},
    "single_skill": {"single": "working", "managed": "dispatch verifying verdict delivered blocked"},
    "shapes": {
        "authored": "chain_build chain_check chain_docs component_a component_b component_c integrate dag_build dag_check dag_docs dag_tests",
        "managed": "critic",
    },
    "contracts": {
        "authored": "import_audit adapt",
        "managed": "tests manifest audit_math audit_permissions audit_economics audit_flow judge deploy live blocked",
    },
    "site": {"authored": "build check docs recovery", "managed": "critic hosted blocked"},
    "company": {"company": "contracts deployment frontend publishing validating completed"},
    "oracle": {"question": "request", "managed": "admit panel attest writer registry stored missed"},
    "intake": {"action": "received paid admitted completing completed refused failed"},
    "schedules": {"action": "create slot opened remaining exhausted skipped failed paused topup"},
    "growth": {"authored": "fix feature", "managed": "launch site more fresh"},
}
_DOCS = {("site", "docs"), ("shapes", "chain_docs"), ("shapes", "dag_docs")}
_SCOPE = {
    "purchase": "paid action", "single_skill": "job", "shapes": "job",
    "contracts": "launch", "site": "continuation", "company": "workflow",
    "oracle": "request", "intake": "paid action", "growth": "continuation",
}
_SOURCE = (
    "Source snapshot 2026-10-18: aidude docs/swarm-workflows.html and "
    "docs/swarm-work-options.html (#space, #shapes and #sworn). Dated guidance, not a live quote."
)
_ESTIMATE = (
    "Word counts are an estimate at 6 characters per word including spaces, "
    "not a word quota or output limit; language and formatting change the estimate. "
    "The character limits remain authoritative for this source snapshot."
)


def _card(title: str, heading: str, value: str = "", *, rows: tuple[str, ...] = (),
          caption: str = "", footer: str = "DOC 2026-10-18") -> GuidanceCard:
    return dict(title=title, heading=heading, value=value, rows=list(rows), caption=caption, footer=footer)


def _capacity(profile: str) -> tuple[list[GuidanceCard], list[str]]:
    if profile == "authored":
        cards = [_card("STEP INPUT", "EST. WORDS", "≈500", caption="3,000 chars"),
                 _card("RENDERED", "EST. WORDS", "≈1,333", caption="8,000 chars")]
        notes = ["Authored step text: ≤3,000 characters (≈500 words). The rendered objective + this step "
                 "must fit ≤8,000 characters (≈1,333 words combined), not 8,000 extra per step. "
                 "All authored steps share the same objective; 1–6 steps do not increase a step's limit.", _ESTIMATE]
    elif profile == "single":
        cards = [_card("STEP INPUT", "OBJECTIVE WORDS", "≈1,333", caption="8,000 chars"),
                 _card("RENDERED", "EST. WORDS", "≈1,333", caption="objective only")]
        notes = ["Single-skill objective: 1–8,000 characters (≈1,333 words), with no separate authored-step text. "
                 "The 3,000-character steps[] field limit does not cap this objective.", _ESTIMATE]
    elif profile == "company":
        cards = [_card("STEP INPUT", "WORKFLOW STAGE", "N/A", caption="plane managed"),
                 _card("RENDERED", "SHARED WORDS", "≈1,333", caption="8,000 total")]
        notes = ["This stage has no editable instruction budget of its own. The company envelope shares "
                 "≤8,000 characters across request + context + draft objective: not 16,000 usable characters, "
                 "despite the request field's individual cap. Explicit draft-step text is ≤3,000 characters; "
                 "the evaluator rewrites the draft at quote time.", _ESTIMATE]
    elif profile in {"action", "question"}:
        cards = [_card("STEP INPUT", "ACTION INPUT", "—", caption="chosen action"),
                 _card("RENDERED", "WORD LIMIT", "—", caption="not documented")]
        notes = ["This is an action or lifecycle stage, not an authored steps[] instruction. "
                 "Its text budget depends on the selected action; no universal word budget is documented."]
        if profile == "question":
            cards[0] = _card("STEP INPUT", "ORACLE", rows=("typed question",), caption="no word quota")
            notes.append("oracle.request carries one typed question. The source specifies answer types and "
                         "consumer quorum, but no numeric question-text limit; no 8,000-character limit is inferred.")
    else:
        cards = [_card("STEP INPUT", "SELECTED NODE", "N/A", caption="not an input"),
                 _card("RENDERED", "SELECTED NODE", "N/A", caption="not an input")]
        notes = ["This plane-managed node, result or failure state has no editable instruction budget. "
                 "Its containing action can have input limits, but those are not a separate allowance for this node."]
    cards.append(_card("BODY", "KiB / REQUEST", "16", caption="16,384 bytes"))
    notes.append("The whole containing request body is ≤16 KiB (16,384 bytes) on the wire, including JSON "
                 "and every field. Bytes are not converted to words; Unicode and serialization affect size.")
    return cards, notes


def _alternatives(topic: str, node: str, profile: str) -> tuple[list[GuidanceCard], list[str]]:
    more = _card("MORE ROOM", "ALTERNATIVE", "—", caption="none documented")
    integrated = _card("INTEGRATED", "ALTERNATIVE", "—", caption="none documented")
    notes = []
    if profile == "authored":
        more = _card("MORE ROOM", "SINGLE SKILL", rows=("≈1,333 words", "8,000 chars"),
                     caption="objective", footer="0.5 IMD / job")
        notes.append("More room for a scoped skill: use a single-skill job.open or job.continue so its "
                     "objective has the full 8,000-character envelope, rather than a 3,000-character step field. "
                     "This is not extra text capacity beyond the 8,000 rendered limit. Each new continuation "
                     "has a fresh budget and costs 0.5 IMD; use the same payer and newest parentJobId. "
                     "A fresh job.open creates a separate project and loses the inherited project tree.")
    elif profile == "single":
        more = _card("MORE ROOM", "FRESH BUDGET", rows=("new follow-up", "≈1,333 words"),
                     caption="8,000 chars", footer="0.5 IMD / job")
        notes.append("The single-skill objective already has the full 8,000-character budget. A new single-skill "
                     "job.continue buys a fresh 8,000-character objective for the next scoped task, "
                     "not a larger per-job allowance. Each continuation costs another 0.5 IMD; "
                     "use the same payer and newest parentJobId to retain the project tree.")
    if (topic, node) in _DOCS:
        more["heading"] = "DOCS-ONLY JOB"
        integrated = _card("INTEGRATED", "DOCS + BUILD", rows=("README in build", "or DAG → build"),
                           caption="same job budget", footer="0.5 IMD / job")
        notes.append("Docs-only alternative: a single-skill job.continue with write-readme-and-docs after "
                     "the final site uses one objective up to 8,000 characters for 0.5 IMD. Integrated option: "
                     "put README work into the build objective, or keep a docs step with explicit dependsOn build "
                     "in a DAG. Neither adds a separate step fee. A review-only dependency does not pass the built tree.")
    elif topic == "contracts":
        integrated = _card("INTEGRATED", "LAUNCH PIPELINE", rows=("tests, manifest", "audits + deploy"),
                           caption="plane included", footer="0.5 IMD / launch")
        notes.append("launch.open integrates tests, manifest, four auditors, judge and deployment; "
                     "plane-added nodes are not separately charged. A scoped single-skill audit/adaptation "
                     "job is not equivalent to a launch: it does not deploy or provide the launch audit pipeline.")
    elif topic in {"site", "company"}:
        integrated = _card("INTEGRATED", "WORKFLOW.OPEN", rows=("contract + site", "new project"),
                           caption="one order", footer="0.5 IMD / order")
        notes.append("Integrated alternative: workflow.open combines contracts, deployment, frontend and "
                     "publishing for a new product, not an existing project. It refuses parentJobId, so it "
                     "cannot extend the existing launched contracts; use job.continue for that. "
                     "The source price is 0.5 IMD for the order, not per stage.")
    elif topic == "shapes":
        integrated = _card("INTEGRATED", "DAG", rows=("dependsOn", "pass build tree"),
                           caption="same job budget", footer="0.5 IMD / job")
        notes.append("A DAG can integrate the selected skill with explicit dependencies in the same job. "
                     "Implement/docs work depends directly on the preceding implementation; reviews pass no bundle. "
                     "Merging multiple bundles can still conflict; 1–6 steps share the 16 KiB request cap.")
    elif topic in {"growth", "single_skill"}:
        integrated = _card("INTEGRATED", "CONTINUATION", rows=("one feature set", "1–6 steps"),
                           caption="same project", footer="0.5 IMD / job")
        notes.append("Integrate a coherent feature set into one job.continue, up to six authored steps. "
                     "Steps are not separately priced; smaller separate continuations provide fresh budgets "
                     "but cost 0.5 IMD each. A blocked job cannot be resumed, and recovery is not guaranteed.")
    if not notes:
        notes.append("No larger-text or integrated-workflow alternative is documented for this selected state/action; "
                     "the cards deliberately show no numeric allowance or equivalent replacement.")
    return [more, integrated], notes


def _cost(topic: str, node: str) -> tuple[GuidanceCard, str]:
    note = "Documented 2026-10-18 price is per paid action, not per node; result not guaranteed and a blocked job keeps its fee."
    if topic == "purchase" and node == "check":
        return _card("COST", "IMD / CHECK", "0", caption="free preview"), note + " Only the free check costs zero; a later paid action costs 0.5 IMD."
    if topic == "schedules":
        if node == "create":
            return _card("COST", "IMD / CREATE", rows=("0.5 IMD", "+ prepaid runs"), caption="total unknown"), note + " schedule.create is 0.5 IMD plus runs bought up front; run count is unspecified, so total unknown."
        if node in {"failed", "skipped"}:
            return _card("COST", "IMD / SLOT", "0", caption="nothing spent"), note + " A failed opening or an in-flight skipped slot spends no run; creation and prior runs are not refunded."
        return _card("COST", "PREPAID RUNS", "—", caption="total unknown"), note + " Runs are prepaid; topup buys more runs. No total or topup fee is inferred without a run count and quote. The frozen input retains the chosen action's caps."
    scope = "launch" if topic == "growth" and node == "launch" else _SCOPE[topic]
    if topic == "growth" and node == "fresh":
        scope = "job"
    return _card("COST", "IMD", "0.5", caption="per follow-up" if scope == "continuation" else f"per {scope}"), note


def add_guidance(topic: str, nodes: list[Node]) -> None:
    """Attach only serializable, independently allocated cards at catalogue construction."""
    profiles = {node: profile for profile, ids in _PROFILES[topic].items() for node in ids.split()}
    if set(profiles) != {node["id"] for node in nodes}:
        raise ValueError(f"Workflow guidance membership differs for {topic}")
    for node in nodes:
        cards, notes = _capacity(profiles[node["id"]])
        alternatives, alternative_notes = _alternatives(topic, node["id"], profiles[node["id"]])
        cost, cost_note = _cost(topic, node["id"])
        node["guidance"] = cards + alternatives + [cost]
        node["guidance_notes"] = [_SOURCE] + notes + alternative_notes + [cost_note]
