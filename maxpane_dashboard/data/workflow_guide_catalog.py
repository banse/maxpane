"""Curated Swarm Workflows document, frozen at 2026-10-18.

These are historical documentation facts, never live observations. The HTML
fixture is the agreement source; production uses only these packaged literals.
"""

from maxpane_dashboard.data.workflow_guide_models import Catalogue, Node, Stat, Topic
from maxpane_dashboard.data.workflow_guide_profiles import add_guidance

# Complete visible text of each supplied figure, including limits and captions.
_EXCERPTS = (
    (
        '01 Buying any action by x402 free check blockers, plan quote 600 s, price 402 + two signatures '
        'Permit2 · quote approval submit PAYMENT-SIGNATURE plane settles gas wallet, 3 confirmations admitted '
        'job / request id today: quote 07:48:46 → admitted 07:51:33 (2 min 47 s); the Permit2 deadline is 300 '
        's, so the payer signs within minutes; the alternative is the onchain Intake (09) bin/aid pay check → '
        'quote → pay . Nothing here is guaranteed a result: a blocked job keeps the 0.5 IMD. body ≤ 16 KiB · '
        'quote valid 600 s · Permit2 deadline 300 s · 0.5 IMD The purchase itself. The free check costs '
        'nothing and shows the plan the plane will run; after the quote the payer signs twice on the local '
        "page and the plane's gas wallet settles."
    ),
    (
        "02 A single-skill job dispatch eligible seat working the seat's model verifying checks or a reviewer "
        'accepted / failed verdict delivered bundle, report, site failed → re-dispatched, at most three '
        'attempts, then the job is blocked job.open with one skill (research-report, create-image, '
        'write-readme-and-docs…). Templates ( audit , research , fuzz …) expand into a fixed set of such '
        'nodes. objective 1–8,000 · references ≤ 8 · paths ≤ 16 · named inputs and outputs · pinned repo ≤ '
        '100/200 MB The smallest unit of work: one skill, one seat, one verdict. Good for a report, an image, '
        'docs, a scoped refinement.'
    ),
    (
        '03 The three step shapes chain fan_out_join dag build content check write docs component A component '
        'B component C integrate-project build site write docs content check tests design critic each step '
        "starts on the previous step's tree, steps 1–6, all free parallel seats, one join; interfaces must be "
        'fixed in the objective dashed: the dependency you write yourself (dependsOn) so docs start on the '
        'built site, see 05 steps[] with shape chain, fan_out_join or dag. Green outline: a node that '
        'receives several accepted bundles, where the worker merges. per rendered step ≤ 8,000 · step ≤ 3,000 '
        '· 1–6 steps · body ≤ 16 KiB, which binds from about four full steps on How several steps share one '
        'job. Chain for build → check → document, fan-out for parallel components, dag when a step needs two '
        'earlier results.'
    ),
    (
        '04 Contracts-only launch audit imported code adapt (writes) foundry tests manifest audit math audit '
        'permissions audit economics audit flow audit judge deploy: one factory tx attested bytes live + repo '
        'your 3 steps plane-added, parallel #2147: 07:48 paid → 08:26 live launch.open , kind evm_contracts : '
        '1–8 contracts, no token, all or nothing in one transaction. A blocking finding parks it undeployed. '
        "objective ≤ 8,000 · ≤ 6 steps before the audit stage · 1–8 contracts · body ≤ 16 KiB · today's body "
        "6,071 characters Deploys contracts after the plane's own audit. Our three steps carry the frozen "
        'commit and the rules; the plane adds tests, manifest, four auditors, judge and the deploy.'
    ),
    (
        '05 Site continuation, and where it broke today build-website site-content-check '
        'write-readme-and-docs design critic (plane) hosted under label tree inherited: build → check (no '
        'bundle) → docs got nothing and restarted at the base merge of build + docs bundles conflicts on '
        'README.md and DESIGN.md → clone_failed ×3 → blocked, nothing hosted accepted 10:02 · 10:04 · 10:15 '
        'CEST; blocked 10:16 · reported as Identity-md/worker#6 · remedy: a continuation Job 53f5fb2b. Rule '
        'for the next body: the docs step depends on the build directly (dag), or the build step writes the '
        'README itself. same caps as 03 · the worker also sees the delivered tree and project.md · plan B '
        'used 7,672 of 8,000 and 16,243 of 16,384 bytes A website on a launched project. The plane always '
        'adds a design critic; hosting waits for every node. The docs step must depend on the build directly.'
    ),
    (
        '06 Company workflow contracts build · tests · manifest · audits deployment rebuilt · attested · '
        'deployed frontend reads deployment.json publishing IPFS + ENS validating up to a day, then completed '
        'no pause between deployment and the site: the site goes live before your own post-deploy checks '
        'newest 100: 70 completed, 29 blocked (24 before deployment) · refuses parentJobId, so not a path for '
        "Sworn's live contracts workflow.open : a new product with contracts and a site in one order; a "
        'finished or blocked workflow takes a job.continue . request ≤ 16,000 but request + context + draft '
        'objective ≤ 8,000 · body ≤ 16 KiB · exactly one website step last, one adversarial review Contracts '
        'and site as one order for a new product. The evaluator rewrites the draft at the quote; not '
        'available on an existing project.'
    ),
    (
        '07 Oracle round trip request tx 0.5 IMD to Intake plane admits +3 confirmations panel answers 5 '
        'seats, quorum 3 computed + attested EIP-712, attester key writer → Intake onResult Registry checks '
        '2–10 stores, or Missed(reason) today: admitted +23 s · attested +72 s (ranking) / +40 s (count) · '
        'delivered +40 s · whole trip under 2 minutes reason 5 = attested below quorum (2 of 3 on the '
        'ranking, twice) · reason 8 = verified, rule false (the 701 test) · stored at the third try the '
        "Registry's panels are constants: chain evidence 5 / 3, panel evidence 11 / 7 oracle.request as the "
        "Registry buys it through the Intake; the same shape for a wallet's direct request, without the "
        "consumer step. one question · answers bool, uint256 or address[] (Sworn's Registry takes ≤ 64 "
        'addresses, 2,112 bytes) · panel and quorum set by the consumer A typed question answered by a seat '
        'panel and signed by the attester. The Registry buys these itself; a wallet can buy one directly too.'
    ),
    (
        '08 Onchain Intake states received paid admitted completing completed refused failed result at '
        '/intake-results/:id unknown_action · wrong_asset · short_payment · body_* Pay and ask in one '
        'transaction ( request on Intake v2), by a wallet or a contract; GET /intake/:chainId/:tx shows the '
        'state. No request token, no x402. the same action bodies, in calldata · price per action · 3 '
        'confirmations before admission The no-x402 path: a wallet or a contract pays and asks in one '
        'transaction; results come back to a callback.'
    ),
    (
        "09 A schedule's runs schedule.create slot (cadence) opened: spent skipped: in flight failed: nothing "
        'spent 3 in a row: paused runs remaining exhausted / topup cadence PT11M … P1D job.open or '
        'oracle.request after an outage: one late run, missedSlots counted schedule.create / schedule.topup : '
        "recurring jobs or oracle questions; slots never queue. the frozen input obeys the action's caps · "
        'cadence PT11M to P1D · runs bought up front, extended by topup Recurring jobs or oracle questions. A '
        'slot opens one run or skips; three failures pause the schedule, nothing spent.'
    ),
    (
        '10 How a project grows launch job c3792acf completed · #2147 live site job 53f5fb2b blocked · site '
        'built continuation: fix census + exact texts continuation: feature one set per job continuation: … '
        'as many as needed each arrow: parentJobId = the newest job · 0.5 IMD · payer pawai.eth · ipfs: true '
        "keeps the label sworn · start = the project's delivered tree a blocked job cannot be resumed by the "
        'payer; the next continuation is the remedy (precedent 10-16), with the open question whether its '
        'start tree merges cleanly a fresh job.open would be a new project: new label, no project.md, no '
        "chain of accepted files Sworn's chain of jobs. Features arrive as separate continuations; the site "
        'name and the project history stay. each continuation has a fresh budget · no limit on the chain · '
        'ipfs: true keeps the label Why features come as separate jobs: each is cheap, independent, and the '
        'project history and site name carry over.'
    ),
)


def _node(id: str, label: str, kind: str, explanation: str, limits: list[str],
          example: str, excerpt: str) -> Node:
    return {
        "id": id, "label": f"[- {label} -]" if kind == "plane" else f"[{label}]", "kind": kind,
        "explanation": explanation, "limits": limits,
        "example": f"Source snapshot 2026-10-18: {example}", "source_excerpt": excerpt,
    }


def _stats(*values: tuple[str, str, str]) -> list[Stat]:
    return [dict(title=title, value=value, caption=caption) for title, value, caption in values]


def _topic(id: str, number: int, title: str, short_title: str, summary: str,
           stats: list[Stat], diagram: list[str], nodes: list[Node]) -> Topic:
    add_guidance(id, nodes)
    return dict(id=id, number=number, title=title, short_title=short_title,
                summary=summary, stats=stats, diagram=diagram, nodes=nodes,
                source_excerpt=_EXCERPTS[number - 1])


CATALOG: Catalogue = {
    "source": {
        "title": "Swarm Workflows", "date": "2026-10-18", "plane": "745c1db4", "worker": "0.1.2",
        "references": [
            "aidude docs/swarm-workflows.html (supplied source snapshot)",
            "aidude docs/imd-api-changelog.md",
            "Job records 2026-10-18: c3792acf, 53f5fb2b",
            "Oracle requests: cb72b826 / 4ee4290d / 03ccc51e / fa460b4b",
            "worker 0.1.2 dist/cli.js", "Identity-md/worker#6",
            "Companion: aidude docs/swarm-work-options.html (2026-10-18 source snapshot)",
        ],
    },
    "topics": [
        _topic("purchase", 1, "Buying any action by x402", "x402 purchase",
            "A free check previews the plan; a quote precedes two local signatures and plane settlement. "
            "Payment never guarantees a result. The alternative Intake is topic 08; the source's '(09)' is a cross-reference error.",
            _stats(("QUOTE", "600", "seconds valid"), ("PERMIT", "300", "seconds deadline"),
                   ("BODY", "16 KiB", "wire limit"), ("PRICE", "0.5 IMD", "per action"),
                   ("CONFIRMATIONS", "3", "before admission"), ("EXAMPLE TIME", "2m 47s", "quote->admission")),
            ["{check} ---> {quote} ---> {signatures} ---> {submit} ---> {settle} ---> {admitted}",
             "", "Historical purchase path. Payment can end in a blocked job; the fee remains spent.",
             "Alternative: onchain Intake, topic 08 (source cross-reference corrected)."],
            [
                _node("check", "free check", "step",
                      "The free check reveals blockers and the plan the plane would run before a paid action is considered.",
                      ["Free check costs nothing.", "Whole action body is limited to 16 KiB."],
                      "The documented command sequence begins with bin/aid pay check.", "free check blockers, plan"),
                _node("quote", "quote", "step",
                      "A quote supplies the action price and a limited validity window. The later signature approves that quote.",
                      ["Quote validity: 600 seconds.", "Documented paid-action price: 0.5 IMD."],
                      "Quote at 07:48:46 preceded admission at 07:51:33.", "quote 600 s, price"),
                _node("signatures", "402 + 2 signatures", "step",
                      "The local payment page requests two signatures: Permit2 and quote approval. This atlas only describes them.",
                      ["Permit2 deadline: 300 seconds; payer signs within minutes."],
                      "The source describes Permit2 and quote approval after the 402 challenge.",
                      "402 + two signatures Permit2 · quote approval"),
                _node("submit", "submit", "step",
                      "The described external payer submits the payment proof in PAYMENT-SIGNATURE after approving the quote.",
                      ["No result guarantee accompanies submission.", "A blocked job keeps the documented 0.5 IMD."],
                      "The source names PAYMENT-SIGNATURE at submission.", "submit PAYMENT-SIGNATURE"),
                _node("settle", "plane settles", "plane",
                      "The plane's gas wallet settles the payment and waits for confirmations before admitting the action.",
                      ["Settlement admission waits for 3 confirmations."],
                      "Quote to admission took 2 minutes 47 seconds; this is an observation, not a service guarantee.",
                      "plane settles gas wallet, 3 confirmations"),
                _node("admitted", "admitted", "state",
                      "Admission returns a job or request identifier so the accepted action can be followed through its own workflow.",
                      ["Admission does not imply successful delivery.", "Intake alternative is topic 08, not source reference 09."],
                      "The documented action was admitted at 07:51:33.", "admitted job / request id"),
            ]),
        _topic("single_skill", 2, "A single-skill job", "Single skill",
            "One skill goes to one eligible seat and receives a verdict. Templates expand into a fixed set of nodes; "
            "failed work is dispatched again for at most three attempts before the job is blocked.",
            _stats(("OBJECTIVE", "8,000", "max characters"), ("REFERENCES", "8", "maximum"),
                   ("PATHS", "16", "maximum"), ("REPO", "100/200 MB", "documented caps"),
                   ("ATTEMPTS", "3", "maximum per node"), ("SKILL", "1", "authored job")),
            ["{dispatch} ---> {working} ---> {verifying} ---> {verdict}",
             "       ^                                                         |",
             "       +----------- failed: retry, at most 3 attempts ------------+",
             "                                                                 +-- accepted --> {delivered}",
             "                                                                 +-- third failure --> {blocked}"],
            [
                _node("dispatch", "dispatch", "plane",
                      "The plane assigns the one-skill node to an eligible seat. Templates such as audit, research and fuzz expand into fixed nodes.",
                      ["job.open uses one skill for this shape.", "Objective: 1–8,000 characters."],
                      "Examples listed are research-report, create-image and write-readme-and-docs.", "dispatch eligible seat"),
                _node("working", "working", "step",
                      "The eligible seat's model performs the scoped task against the supplied repository, references and named inputs or outputs.",
                      ["References <= 8; paths <= 16.", "Pinned repo <= 100/200 MB; the source does not distinguish the two caps."],
                      "A report, image, documentation or scoped refinement is a documented use case.", "working the seat's model"),
                _node("verifying", "verifying", "plane",
                      "Checks or a reviewer inspect the seat's result before a verdict decides acceptance or failure.",
                      ["The source does not promise a successful outcome or a fixed verification duration."],
                      "The source explicitly allows either checks or a reviewer.", "verifying checks or a reviewer"),
                _node("verdict", "accepted / failed", "state",
                      "An accepted verdict permits delivery. A failed verdict triggers redispatch until the attempt cap is reached.",
                      ["At most three attempts; the job is then blocked."],
                      "The documented retry arrow returns failed work to dispatch.", "accepted / failed verdict"),
                _node("delivered", "delivered", "plane",
                      "After acceptance, delivery exposes the output appropriate to the skill, such as a bundle, report or site.",
                      ["Named inputs and outputs scope the work.", "Delivery follows acceptance."],
                      "The source's delivered outputs are bundle, report and site.", "delivered bundle, report, site"),
                _node("blocked", "blocked", "failure",
                      "Repeated unsuccessful attempts stop the job instead of permitting an unbounded retry loop.",
                      ["At most three attempts.", "Paid actions have no result guarantee."],
                      "The source says the job is blocked after the retry cap.", "at most three attempts, then the job is blocked"),
            ]),
        _topic("shapes", 3, "The three step shapes", "Step shapes",
            "steps[] supports chain, fan_out_join and dag. A join receives several accepted bundles and merges them. "
            "For docs to inherit a built site, explicitly make docs depend on build. The source's dashed SVG edge "
            "points at tests despite its caption; this diagram follows the stated build-to-docs recommendation.",
            _stats(("STEP TEXT", "3,000", "own characters"), ("RENDERED", "8,000", "objective + step"),
                   ("STEPS", "1–6", "authored per job"), ("BODY", "16 KiB", "wire limit"),
                   ("SHAPES", "3", "chain/fan/dag"), ("MERGE", "join", "accepted bundles")),
            ["CHAIN: each next step receives the previous step's tree (see topic 05's missing-bundle caveat)",
             "{chain_build} ---> {chain_check} ---> {chain_docs}", "",
             "FAN_OUT_JOIN: parallel components; interfaces fixed in the objective",
             "{component_a} --+", "{component_b} --+---> {integrate}", "{component_c} --+", "",
             "DAG: explicit dependencies; recommended docs dependsOn build",
             "{dag_build} ---> {dag_check} ---------------+", "     |                                           |",
             "     +---> {dag_docs} ---> {dag_tests} ------------+---> {critic}",
             "Source caption correction: build -> docs is recommended; the drawn dashed edge targets tests."],
            [
                _node("chain_build", "build", "step",
                      "The first chain step builds on the supplied base. Later steps are intended to start from the preceding step's tree.",
                      ["1–6 authored steps; each step's own text <= 3,000 characters."],
                      "The source chain starts build -> content check -> write docs.", "chain"),
                _node("chain_check", "content check", "step",
                      "The middle chain step checks content. A check without a bundle can break the later tree handoff, as topic 05 records.",
                      ["Objective plus the rendered step <= 8,000 characters."],
                      "The site job's content check produced no bundle; do not assume transitive inheritance.", "content check"),
                _node("chain_docs", "write docs", "step",
                      "The last chain step documents its received tree. If an intermediate check emits no bundle, add a direct build dependency instead.",
                      ["Whole body <= 16 KiB; this binds from about four full steps."],
                      "The chain is an illustrated shape, not evidence that every check passes the built tree.", "write docs"),
                _node("component_a", "component A", "step",
                      "One independent component is assigned a parallel seat and returns an accepted bundle to the integration node.",
                      ["Interfaces must be fixed in the shared objective."],
                      "Component A is one of three illustrative parallel branches.", "component A"),
                _node("component_b", "component B", "step",
                      "A second parallel component works independently before its accepted result is joined with the others.",
                      ["Parallel components share the same body and rendered-step caps."],
                      "Component B is a separate seat in the source fan-out example.", "component B"),
                _node("component_c", "component C", "step",
                      "The third illustrative component supplies another result to the join; parallelism does not remove interface coordination.",
                      ["1–6 authored steps; plane-added nodes are separate."],
                      "Component C converges on integrate-project with A and B.", "component C"),
                _node("integrate", "integrate-project", "merge",
                      "The join receives the parallel accepted bundles. The worker merges those results into one integration tree.",
                      ["Interfaces must be fixed in the objective to avoid incompatible components."],
                      "The source highlights integrate-project as the fan-out merge node.", "integrate-project"),
                _node("dag_build", "build site", "step",
                      "The DAG build supplies content check and, in the recommended correction, the documentation step directly.",
                      ["Explicit dependsOn is needed; a transitive check need not forward a bundle."],
                      "Recommendation, not verified recovery: give docs its direct build dependency.", "build site"),
                _node("dag_check", "content check", "step",
                      "This branch checks the built site and supplies one prerequisite to the illustrated design critic.",
                      ["A check may not produce a bundle; use direct dependencies when a tree is required."],
                      "The source DAG draws content check as one input to design critic.", "content check"),
                _node("dag_docs", "write docs", "step",
                      "The recommended docs dependsOn build edge ensures documentation starts from the built site instead of an unrelated base.",
                      ["The source caption says build -> docs, while its dashed SVG edge targets tests."],
                      "Recommendation, not verified recovery: docs starts from build with an explicit DAG dependency.", "write docs"),
                _node("dag_tests", "tests", "step",
                      "The illustrated DAG runs tests downstream of documentation, then supplies their accepted result to the critic.",
                      ["The source's mistaken dashed edge is not treated as a docs dependency."],
                      "The source's solid dependency is write docs -> tests -> design critic.", "tests"),
                _node("critic", "design critic", "merge",
                      "The illustrated critic receives both branches. Receiving several accepted bundles is where the worker must merge trees.",
                      ["The merge can conflict; acceptance of individual branches does not guarantee integration."],
                      "Topic 05 records a critic blocked by a README.md / DESIGN.md merge conflict.", "design critic"),
            ]),
        _topic("contracts", 4, "Contracts-only launch", "Contracts launch",
            "launch.open with kind evm_contracts deploys 1–8 contracts with no token, all or nothing in one factory "
            "transaction. Authored steps carry the frozen commit and rules; the plane adds tests, manifest, four "
            "auditors, judge and deployment. A blocking finding parks the launch undeployed.",
            _stats(("CONTRACTS", "1–8", "atomic launch"), ("OBJECTIVE", "8,000", "max characters"),
                   ("STEPS", "6", "pre-audit max"), ("BODY", "16 KiB", "wire limit"),
                   ("EXAMPLE BODY", "6,071", "characters"), ("EXAMPLE", "#2147", "07:48 to 08:26")),
            ["{import_audit} ---> {adapt}",
             "                                   |  plane-added stages in parallel",
             "     +-----------------------------+",
             "     +--> {tests}-------------+",
             "     +--> {manifest}------------------+",
             "     +--> {audit_math}----------------+----> {judge} ---> {deploy}",
             "     +--> {audit_permissions}---------+             |                        |",
             "     +--> {audit_economics}-----------+             v                        v",
             "     +--> {audit_flow}----------------+        {blocked}             {live}",
             "                                                   blocking finding",
             "Documented #2147: 07:48 paid -> 08:26 live on 2026-10-18; no token launch."],
            [
                _node("import_audit", "audit imported code", "step",
                      "The authored launch begins by auditing imported code. The user's three steps carry the frozen commit and project rules.",
                      ["Objective <= 8,000 characters.", "At most 6 authored steps before the plane's audit stage."],
                      "Launch job c3792acf produced #2147; the source labels the authored work 'your 3 steps' but names only audit and adapt here.",
                      "audit imported code"),
                _node("adapt", "adapt (writes)", "step",
                      "Adaptation writes the imported code under the frozen rules before the plane's independent validation and audit stages.",
                      ["launch.open kind evm_contracts.", "Body <= 16 KiB; the observed body was 6,071 characters."],
                      "Sworn's documented launch used three authored steps; this overview does not invent the unnamed third step.",
                      "adapt (writes)"),
                _node("tests", "foundry tests", "plane",
                      "The plane adds Foundry tests alongside manifest preparation and four parallel audit perspectives after adaptation.",
                      ["Plane-added nodes are outside the authored step count."],
                      "Foundry tests form part of the documented #2147 launch pipeline.", "foundry tests"),
                _node("manifest", "manifest", "plane",
                      "The plane prepares the manifest in the same validation stage, supplying deployment information before the judge and deploy.",
                      ["The source does not specify the manifest schema; no extra fields are inferred."],
                      "The #2147 overview lists manifest beside tests and the four auditors.", "manifest"),
                _node("audit_math", "audit math", "plane",
                      "The mathematical audit is one of four independent plane-added perspectives whose findings feed the audit judge.",
                      ["A blocking finding can park the entire launch undeployed."],
                      "Math is explicitly listed among the four auditors for the documented launch.", "audit math"),
                _node("audit_permissions", "audit permissions", "plane",
                      "The permissions audit examines the access-control perspective and contributes its result to the audit judge.",
                      ["Runs in the parallel plane-added stage; acceptance does not bypass the judge."],
                      "Permissions is a separate auditor in the #2147 overview.", "audit permissions"),
                _node("audit_economics", "audit economics", "plane",
                      "The economic audit contributes a separate view of the contracts before the combined audit decision permits deployment.",
                      ["The source gives no guaranteed audit duration or successful outcome."],
                      "Economics runs alongside math, permissions and flow in the source diagram.", "audit economics"),
                _node("audit_flow", "audit flow", "plane",
                      "The flow auditor is the fourth parallel audit perspective and provides findings to the judge before deployment.",
                      ["Blocking findings park the launch undeployed."],
                      "Flow is the fourth auditor named in the #2147 launch snapshot.", "audit flow"),
                _node("judge", "audit judge", "plane",
                      "The plane's audit judge receives the validation and auditor results. A blocking finding prevents deployment of the launch.",
                      ["A blocking finding parks it undeployed; payment does not guarantee completion."],
                      "The source places the judge after tests, manifest and all four audit branches.", "audit judge"),
                _node("deploy", "deploy: 1 factory tx", "merge",
                      "The plane deploys the attested bytes for all contracts together in one factory transaction after its audit stage.",
                      ["1–8 contracts; no token.", "Deployment is all or nothing in one transaction."],
                      "#2147 went from 07:48 paid to 08:26 live; these are historical times.", "deploy: one factory tx attested bytes"),
                _node("live", "live + repo", "state",
                      "Successful deployment yields live contracts and a repository. This node describes the source's historical result, not current chain status.",
                      ["The atlas performs no deployment or chain-status acquisition."],
                      "Launch c3792acf was recorded completed with #2147 live.", "live + repo"),
                _node("blocked", "undeployed", "failure",
                      "A blocking finding stops the launch before deployment. The atomic deployment promise does not imply every launch completes.",
                      ["Paid actions are not guaranteed a result.", "No partial deployment in the described factory transaction."],
                      "This is the source's documented failure branch, not the observed outcome of #2147.",
                      "A blocking finding parks it undeployed."),
            ]),
        _topic("site", 5, "Site continuation, and where it broke today", "Site continuation",
            "Historical job 53f5fb2b built the site, but the content check emitted no bundle and docs restarted from the "
            "base tree. The plane's critic could not merge README.md and DESIGN.md: clone_failed three times, blocked, "
            "nothing hosted. A direct build-to-docs dependency is the recommended next body, not a verified recovery.",
            _stats(("RENDERED", "7,672", "of 8,000 chars"), ("BODY", "16,243", "of 16,384 bytes"),
                   ("ATTEMPTS", "3", "clone_failed"), ("ACCEPTED", "3", "authored nodes"),
                   ("BLOCKED", "10:16", "CEST observation"), ("HOSTING", "none", "observed result")),
            ["{build} ---> {check} ---> {docs}",
             "       |                                                  |", "       +--------------------------------------------------+",
             "                                                          v", "                                                   {critic} ---> {hosted}",
             "                                                          |", "                                                          v", "                                                      {blocked}",
             "", "NEXT BODY (recommendation; not verified recovery): {recovery}",
             "Direct docs dependsOn build, or write README in build. Hosting did not occur in this snapshot."],
            [
                _node("build", "build-website", "step",
                      "A website continuation starts from the delivered project tree and project.md. The build created the site and emitted its bundle.",
                      ["Same caps as topic 03: rendered step <= 8,000; own step <= 3,000; 1–6 steps; body <= 16 KiB."],
                      "Job 53f5fb2b's build was accepted at 10:02 CEST.", "build-website"),
                _node("check", "site-content-check", "step",
                      "The content check followed the build but emitted no bundle. The later docs node therefore did not receive the built tree through this step.",
                      ["An accepted check is not evidence that it forwards a tree."],
                      "The content check was accepted at 10:04 CEST with no bundle.", "check (no bundle)"),
                _node("docs", "write-readme-and-docs", "step",
                      "The docs node received no inherited bundle from its immediate check predecessor and restarted at the base tree.",
                      ["Docs must depend directly on the build when it needs the built tree."],
                      "Docs was accepted at 10:15 CEST but wrote conflicting README.md and DESIGN.md.",
                      "docs got nothing and restarted at the base"),
                _node("critic", "design critic", "failure",
                      "The plane always adds a design critic for a site. Its direct build and docs dependencies required merging both bundles, which conflicted.",
                      ["Conflict files: README.md and DESIGN.md.", "clone_failed occurred three times."],
                      "The critic failed before reviewing the site; the incident was reported as Identity-md/worker#6.",
                      "merge of build + docs bundles conflicts on README.md and DESIGN.md"),
                _node("hosted", "hosting (not reached)", "state",
                      "Hosting under the project label waits for every node to accept. Because the critic blocked, this stage was not reached.",
                      ["All nodes must accept before hosting."],
                      "The site was built, but nothing was hosted in job 53f5fb2b.", "blocked, nothing hosted"),
                _node("blocked", "blocked", "failure",
                      "After three clone failures the job stopped. Acceptance of its three authored nodes did not make the site publishable.",
                      ["Observed block: 10:16 CEST.", "Plan B used 7,672 of 8,000 characters and 16,243 of 16,384 bytes."],
                      "The source reports accepted times 10:02, 10:04, 10:15; blocked at 10:16 CEST.",
                      "accepted 10:02 · 10:04 · 10:15 CEST; blocked 10:16"),
                _node("recovery", "proposed continuation", "step",
                      "The source recommendation is a continuation whose docs step depends on build directly in a DAG, or whose build writes README itself.",
                      ["Recommendation only; successful recovery is not established.", "Whether the continuation start tree merges cleanly remains open."],
                      "Proposed next body, not verified recovery: direct docs dependsOn build, or README written by build.",
                      "the docs step depends on the build directly (dag), or the build step writes the README itself."),
            ]),
        _topic("company", 6, "Company workflow", "Company workflow",
            "workflow.open orders new contracts and a site together; its evaluator rewrites the draft at quote time. "
            "It refuses parentJobId and cannot attach to existing contracts. There is no pause for the buyer's own "
            "post-deploy checks before the site goes live. The source's newest 100 contain 70 completed and 29 blocked; one is unspecified.",
            _stats(("REQUEST", "16,000", "max characters"), ("COMBINED", "8,000", "combined inputs"),
                   ("BODY", "16 KiB", "wire limit"), ("WEBSITE", "1", "last step"),
                   ("REVIEW", "1", "adversarial"), ("VALIDATING", "1 day", "up to")),
            ["{contracts} ---> {deployment} ---> {frontend}",
             "                                              |", "        +-------------------------------------+", "        v",
             "{publishing} ---> {validating} ---> {completed}",
             "", "No pause between deployment and site publication for the buyer's post-deploy checks.",
             "Newest 100 in source: 70 completed; 29 blocked (24 before deployment); 1 unspecified."],
            [
                _node("contracts", "contracts", "step",
                      "The contracts stage combines build, tests, manifest and audits for a new product. The evaluator rewrites the draft at quote time.",
                      ["request <= 16,000 characters, but request + context + draft objective <= 8,000.",
                       "Body <= 16 KiB; exactly one website step last and one adversarial review.", "workflow.open refuses parentJobId."],
                      "Sworn's already-live contracts were not eligible for this new-product path.", "contracts build · tests · manifest · audits"),
                _node("deployment", "deployment", "plane",
                      "The plane rebuilds, attests and deploys the contracts, then proceeds directly to the frontend without an owner review pause.",
                      ["Site goes live before the buyer's own post-deploy checks."],
                      "The source sample had 29 blocked workflows, including 24 before deployment.", "deployment rebuilt · attested · deployed"),
                _node("frontend", "frontend", "step",
                      "The frontend job reads deployment.json so the new website uses the deployment output from the same order.",
                      ["Exactly one website step, placed last in the draft."],
                      "The documented frontend consumes deployment.json.", "frontend reads deployment.json"),
                _node("publishing", "publishing", "plane",
                      "The plane publishes the completed site through IPFS and ENS as part of the combined product workflow.",
                      ["The source describes no pause for independent post-deployment checks."],
                      "IPFS + ENS is the documented publishing stage.", "publishing IPFS + ENS"),
                _node("validating", "validating", "plane",
                      "After publishing, validation can continue for up to a day before the workflow reaches completed status.",
                      ["Validation takes up to a day in the documented workflow."],
                      "The figure explicitly places validation after IPFS + ENS publication.", "validating up to a day, then completed"),
                _node("completed", "completed", "state",
                      "A finished or blocked company workflow can be extended using job.continue. The source sample is a historical observation.",
                      ["Newest 100: 70 completed, 29 blocked, 24 before deployment.", "One of the 100 is unspecified; no state is inferred."],
                      "70 completed in the source sample is not a live success rate or guarantee.",
                      "a finished or blocked workflow takes a job.continue ."),
            ]),
        _topic("oracle", 7, "Oracle round trip", "Oracle round trip",
            "A typed oracle question is answered by a seat panel, computed and attested, then delivered by the writer. "
            "The Registry checks and stores or emits Missed(reason). A wallet's direct oracle.request follows the same "
            "shape without the consumer step; panel and quorum are chosen by the consumer.",
            _stats(("QUESTION", "1", "typed request"), ("CHAIN PANEL", "5 / 3", "seats / quorum"),
                   ("PANEL EVIDENCE", "11 / 7", "seats / quorum"), ("ADDRESSES", "64", "Registry maximum"),
                   ("ANSWER SIZE", "2,112", "Registry bytes"), ("EXAMPLE TRIP", "< 2 min", "observed")),
            ["{request} ---> {admit} ---> {panel}",
             "                                                   |", "            +--------------------------------------+", "            v",
             "{attest} ---> {writer} ---> {registry}",
             "                                                                      |", "                                             +------------------------+---------+",
             "                                             v                                  v",
             "                                         {stored}                       {missed}",
             "reason 5: attested below quorum (2 of 3); reason 8: verified, rule false (701 test)."],
            [
                _node("request", "request tx", "step",
                      "The Registry buys one typed oracle question through the onchain Intake. A wallet can request directly without the Registry consumer checks.",
                      ["One question; answer types bool, uint256 or address[].", "Source price: 0.5 IMD to Intake."],
                      "Recorded oracle request IDs: cb72b826, 4ee4290d, 03ccc51e and fa460b4b.", "request tx 0.5 IMD to Intake"),
                _node("admit", "plane admits", "plane",
                      "After the request transaction reaches the confirmation threshold, the plane admits the oracle question for its panel.",
                      ["3 confirmations before admission."],
                      "The source measured admission after +23 seconds; this is not a promised latency.", "plane admits +3 confirmations"),
                _node("panel", "panel answers", "plane",
                      "Eligible seats answer the question against the consumer's configured quorum. The Registry distinguishes chain and panel evidence.",
                      ["Chain evidence: 5 seats / quorum 3.", "Panel evidence: 11 / 7.", "Panel size and quorum are set by the consumer."],
                      "The ranking twice had 2 of 3 required agreeing answers, producing reason 5.", "panel answers 5 seats, quorum 3"),
                _node("attest", "computed + attested", "plane",
                      "The plane computes the result and attests it with its EIP-712 attester key. Attestation alone does not establish consumer acceptance.",
                      ["Below-quorum attestations can still be rejected by Registry checks."],
                      "The source observed +72 seconds for ranking attestation and +40 seconds for count.",
                      "computed + attested EIP-712, attester key"),
                _node("writer", "writer -> Intake", "plane",
                      "The writer delivers the attested result through Intake and onResult so the consumer can apply its checks.",
                      ["The delivered callback is not itself proof the Registry stored an accepted result."],
                      "The source lists delivered +40 seconds and whole trips under two minutes; durations are observations.",
                      "writer → Intake onResult"),
                _node("registry", "Registry checks 2-10", "merge",
                      "The Registry applies its consumer checks, then stores the result or records Missed(reason). Direct wallet requests omit this step.",
                      ["Sworn Registry takes <= 64 addresses, or 2,112 bytes.", "Panel and quorum are consumer-specific."],
                      "reason 5 means attested below quorum; reason 8 means verified but the rule is false.",
                      "Registry checks 2–10 stores, or Missed(reason)"),
                _node("stored", "stored", "state",
                      "A result is stored only when the Registry's checks accept it. The observed third-try result is historical evidence, not guaranteed recovery.",
                      ["Consumer validation is separate from successful callback delivery."],
                      "The source records stored at the third try after the ranking quorum failures.", "stored at the third try"),
                _node("missed", "Missed(reason)", "failure",
                      "Missed records why the Registry declined a delivered result: reason 5 for below quorum, reason 8 for a verified answer with a false rule.",
                      ["reason 5: 2 of 3 on the ranking, twice.", "reason 8: verified, rule false in the 701 test."],
                      "The two below-quorum ranking attempts and 701 test are distinct documented failures.",
                      "reason 5 = attested below quorum (2 of 3 on the ranking, twice) · reason 8 = verified, rule false (the 701 test)"),
            ]),
        _topic("intake", 8, "Onchain Intake states", "Intake states",
            "Intake v2 combines payment and request in one transaction from a wallet or contract, using the same action "
            "bodies in calldata. No request token and no x402 are required. The diagram follows the source SVG's "
            "received-to-refused and admitted-to-failed branches; its accessibility label describes the failure origins differently.",
            _stats(("TRANSACTION", "1", "pay + ask"), ("CONFIRMATIONS", "3", "before admission"),
                   ("PRICE", "per action", "documented"), ("REQUEST TOKEN", "none", "Intake path"),
                   ("X402", "none", "Intake path"), ("RESULT", "callback", "or result URL")),
            ["{received} ---> {paid} ---> {admitted} ---> {completing} ---> {completed}",
             "     |                           |", "     v                           v",
             " {refused}                   {failed}", "",
             "Read-only source endpoints: GET /intake/:chainId/:tx and /intake-results/:id.",
             "Source discrepancy: SVG branches from received/admitted; aria text says after received."],
            [
                _node("received", "received", "state",
                      "The Intake receives a wallet or contract's request transaction containing payment and the same action body in calldata.",
                      ["Intake v2 request combines pay and ask in one transaction.", "No request token; no x402."],
                      "The source begins received -> paid and also draws a refused branch from received.", "received"),
                _node("paid", "paid", "state",
                      "The request proceeds through its paid state on the way to plane admission after the required confirmations.",
                      ["Price is per action.", "3 confirmations before admission."],
                      "The source draws paid between received and admitted.", "paid"),
                _node("admitted", "admitted", "state",
                      "Once admitted, the request proceeds toward completing. The source SVG draws its failed branch from this state.",
                      ["The source accessibility label instead says failures branch after received; the discrepancy remains explicit."],
                      "This atlas follows the drawn admitted -> failed branch without inferring an exhaustive state machine.", "admitted"),
                _node("completing", "completing", "state",
                      "The Intake request is completing before it reaches completed and exposes its result or callback delivery.",
                      ["The source does not give a timeout for this state."],
                      "The documented successful path is admitted -> completing -> completed.", "completing"),
                _node("completed", "completed", "state",
                      "The completed state ends the illustrated happy path. Results are described at the result endpoint and through a callback.",
                      ["GET /intake/:chainId/:tx shows state.", "Result at /intake-results/:id."],
                      "These endpoint names are documentation only; the atlas does not request them.", "completed"),
                _node("refused", "refused", "failure",
                      "A refusal leaves the accepted path near receipt. The figure lists validation errors without mapping every code to a specific failure state.",
                      ["Listed reasons: unknown_action, wrong_asset, short_payment, body_*.", "No invented reason-to-state mapping."],
                      "The SVG draws received -> refused; only the source's listed reasons are retained.", "refused"),
                _node("failed", "failed", "failure",
                      "A failed state branches from admitted in the SVG. The source's accessibility description conflicts, so the diagram is not asserted as a full protocol specification.",
                      ["The supplied source does not establish every permitted transition or retry rule."],
                      "This is the drawn admitted -> failed branch, with the accessibility-text discrepancy disclosed.", "failed"),
            ]),
        _topic("schedules", 9, "A schedule's runs", "Schedule runs",
            "schedule.create buys recurring job.open or oracle.request runs in advance; schedule.topup extends them. "
            "Slots never queue: open one run, skip an in-flight predecessor, or fail without spending. Three consecutive "
            "failures pause until topup. After an outage, one late run is opened and missedSlots is counted.",
            _stats(("MIN CADENCE", "PT11M", "11 minutes"), ("MAX CADENCE", "P1D", "one day"),
                   ("PAUSE", "3", "failures in row"), ("CATCH-UP", "1", "after outage"),
                   ("QUEUED", "none", "never queue"), ("FUNDING", "up front", "topup extends")),
            ["{create} ---> {slot}",
             "                                 |",
             "                                 +---> {opened} ---> {remaining} ---> {exhausted}",
             "                                 +---> {skipped}",
             "                                 +---> {failed} ---> {paused}",
             "                                                                              |",
             "                                                                              v", "                                                                      {topup}",
             "Topup also extends exhausted schedules. After outage: one late run; missedSlots counted."],
            [
                _node("create", "schedule.create", "step",
                      "Create a recurring schedule with runs bought up front and a frozen job.open or oracle.request input.",
                      ["Frozen input obeys the chosen action's caps.", "Cadence PT11M to P1D."],
                      "The source lists only job.open and oracle.request as the recurring actions.", "schedule.create"),
                _node("slot", "slot (cadence)", "plane",
                      "Each cadence slot decides whether to open a run, skip it because a previous run is in flight, or record an opening failure.",
                      ["Slots never queue.", "After an outage: one late run, missedSlots counted."],
                      "The diagram branches each cadence slot into opened, skipped and failed.", "slot (cadence)"),
                _node("opened", "opened: spent", "state",
                      "Opening a scheduled run spends one prepaid run and reduces the remaining run count.",
                      ["Runs are bought up front and extended by topup."],
                      "The source links opened: spent to runs remaining.", "opened: spent"),
                _node("remaining", "runs remaining", "state",
                      "The remaining prepaid runs determine how many further slots can open work before exhaustion.",
                      ["The source gives no fixed maximum purchased-run count."],
                      "The source's opened branch proceeds through runs remaining toward exhaustion or topup.", "runs remaining"),
                _node("exhausted", "exhausted", "state",
                      "A schedule is exhausted when its purchased runs are used. Additional runs can be bought with schedule.topup.",
                      ["No run is opened without remaining prepaid runs in the documented lifecycle."],
                      "The source's final run-budget node is exhausted / topup.", "exhausted / topup"),
                _node("skipped", "skipped: in flight", "state",
                      "A slot is skipped while the preceding run remains in flight; the missed work does not accumulate in a queue.",
                      ["Slots never queue.", "The source does not invent catch-up work for every skipped slot."],
                      "The middle slot branch is skipped: in flight.", "skipped: in flight"),
                _node("failed", "failed: nothing spent", "failure",
                      "A failed attempt to open the scheduled run spends nothing and contributes to the consecutive-failure pause rule.",
                      ["Three consecutive failures pause the schedule.", "No spend for a failed opening."],
                      "The source's failed branch explicitly says nothing spent.", "failed: nothing spent"),
                _node("paused", "3 in a row: paused", "failure",
                      "Three consecutive failed run openings pause the schedule. The documented recovery is a topup, not an ever-growing retry queue.",
                      ["Three failures in a row trigger pause; topup is the described recovery."],
                      "This is a documented lifecycle rule, not an observed schedule incident.", "3 in a row: paused"),
                _node("topup", "schedule.topup", "step",
                      "Topup purchases additional runs to extend the schedule and is the source's described path out of a failure pause.",
                      ["The frozen action input continues to obey its original caps."],
                      "The source names schedule.create / schedule.topup for recurring jobs or questions.", "schedule.topup"),
            ]),
        _topic("growth", 10, "How a project grows", "Project growth",
            "Each continuation uses the newest job as parentJobId, a fresh budget, the same payer and the project's "
            "delivered tree. ipfs: true retains the label. A blocked job cannot be resumed by the payer. The source's "
            "fix and later features are proposed continuations; whether the next start tree merges cleanly remains an open question.",
            _stats(("PRICE", "0.5 IMD", "per continuation"), ("BUDGET", "fresh", "per continuation"),
                   ("PARENT", "newest job", "parentJobId"), ("PAYER", "same", "pawai.eth"),
                   ("SITE LABEL", "sworn", "ipfs: true"), ("CHAIN", "no limit", "documented")),
            ["OBSERVED", "{launch} ---> {site}", "",
             "PROPOSED (no verified recovery in source)",
             "{fix} ---> {feature} ---> {more}",
             "", "Each arrow: newest parentJobId; 0.5 IMD; same payer; delivered project tree.",
             "ipfs: true keeps the label. Open question: whether the next continuation tree merges cleanly.",
             "{fresh}"],
            [
                _node("launch", "launch c3792acf", "state",
                      "Sworn's recorded launch job completed and left #2147 live, creating the project history for later continuations.",
                      ["Historical outcome only; no current chain status is queried."],
                      "Launch job c3792acf was recorded completed with #2147 live.", "launch job c3792acf completed · #2147 live"),
                _node("site", "site 53f5fb2b: blocked", "failure",
                      "The next site continuation built the website but became blocked at the critic's bundle merge. The payer cannot resume the blocked job.",
                      ["A blocked job cannot be resumed by the payer.", "A new continuation is the source's remedy."],
                      "Site job 53f5fb2b remained blocked; built does not mean hosted.", "site job 53f5fb2b blocked · site built"),
                _node("fix", "proposed fix", "step",
                      "The proposed fix continuation covers census and exact texts. Its parent is the newest job, but a clean starting merge is still an open question.",
                      ["Recommendation only; not verified recovery.", "Each continuation has a fresh budget and documented 0.5 IMD price."],
                      "The source proposes census + exact texts, citing a 10-16 precedent; successful recovery is not verified.",
                      "continuation: fix census + exact texts"),
                _node("feature", "proposed feature", "step",
                      "A later feature set belongs in its own continuation so its budget and work stay scoped while preserving the project history.",
                      ["One set of features per job.", "parentJobId is the newest job; payer stays the same."],
                      "pawai.eth is the documented payer; ipfs: true retains label sworn. No feature job is shown completed.",
                      "continuation: feature one set per job"),
                _node("more", "further continuations", "plane",
                      "The project can continue through as many separate jobs as needed, each starting from its delivered tree and retaining history and site name.",
                      ["No limit on the continuation chain in the source.", "ipfs: true keeps the label."],
                      "The final source node is an open-ended continuation, not evidence any additional job ran.",
                      "continuation: … as many as needed"),
                _node("fresh", "fresh job.open = new project", "state",
                      "Starting a fresh job.open creates a different project rather than extending the existing chain of accepted files.",
                      ["New label; no inherited project.md; no chain of accepted files."],
                      "The source warns a fresh job.open would lose Sworn's project context and existing label.",
                      "a fresh job.open would be a new project: new label, no project.md, no chain of accepted files"),
            ]),
    ],
}
