# AGENT SHIPPED card

The former NODES card becomes SHIPPED, with LAUNCHES over a tall digit and
`oracle x` inside the bottom border. Its grid position, neutral frame, and empty
outer footer stay intact. Each figure counts distinct jobs with accepted work
by the selected seat. Multiple accepted nodes on the same job count once.
Oracle jobs take precedence when an inconsistent job has both node kinds.

Launch jobs must belong to a live production launch, including frontend jobs
linked through a workflow. Production uses the existing explicit chain policy
(Ethereum, Base, RH); testnets are excluded. Oracle jobs require structured chain
evidence from the public oracle request catalogue and include BNB Chain and
Arbitrum One as well. Known testnets are excluded; unclassified networks remain
unknown rather than being silently omitted. Missing evidence remains an
unknown value, never zero or a chain guessed from the objective or seat identity.

## Implementation plan

Tier 2, estimated below 1,000 production lines; one final review, no package
reviews. The Software Architect recommended the selected-seat data path instead
of loading BOARD's entire contribution graph.

1. Data worker owns `surf_agent_work.py`, `surf_agent_card_sources.py`, their
   tests and small fixtures. Preserve RECORD's launch-membership semantics,
   enrich cached facts with chain evidence, deduplicate SHIPPED by job, and
   resolve selected workflow links. Legacy live membership needs enrichment.
2. UI worker owns `agent_rack_hero.py` and affected widget/screen tests. Retain
   the `nodes` ID and existing projected fields; render launches and oracle as
   the new digit/footer. This package runs alongside the data package.
3. Controller owns `surf_swarm.py`, `surf_manager.py`, oracle tests and this
   document. Extend the existing bulk oracle index with validated chain facts;
   continue bounded paging for accepted oracle jobs beyond RECORD's window.
   No per-oracle-job detail fanout. The selected-agent initial chain backfill has
   a 20-page budget; the existing RECORD budget stays at four pages. A live
   measurement read all 8,579 entries in 18 pages in 6.77 seconds. Accepted jobs
   also take priority within the existing 64-job / four-worker membership budget.
   Legacy index entries retain request identity;
   chain backfill must not fabricate history coverage or zero counts.
4. Integrate, show a real public-data render at 149×45, run focused compositor
   and data checks plus the affected layout boundary sweep. Demonstrate decoder
   mutation failures, then request one final independent review. Run touched and
   composing test files once plus fast guards before the local commit.

The existing widget contract remains `nodes.launches`, `nodes.oracle`,
`nodes.known_jobs`, `nodes.total_jobs`; the latter pair describes launch evidence.
The bulk index gains optional `chains` (job ID → positive integer or unknown).
Persisted legacy index shapes remain readable. Source states stay internal;
the shared loading indicator and unknown-value dashes remain the display policy.

Selected-job cache facts add `chain_id` and `shipped`; RECORD continues to use
the direct `launched` flag. Both legacy true and false points are enriched since
the old false flag cannot rule out a frontend contribution through a workflow.

Network references verified 2026-10-18:
[BNB Chain mainnet 56 / testnet 97](https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/),
[Arbitrum One 42161 / Sepolia 421614](https://docs.arbitrum.io/chain-info),
[Robinhood mainnet 4663](https://robinhood.com/us/en/support/articles/robinhood-chain-testnet/).

## Verification

- Public-data render at 149×45: seat 420 shows 14 launch jobs and `oracle 3,208`.
  The initial empty-cache read and reopening from that temporary public-only
  cache were both exercised. No personal cache was copied or modified.
- Layout measurement: 133×29 remains marked/cut; 134×29 and 135×29 are whole.
  Existing pins remain unchanged; the complete composing layout file passed.
- Affected and composing files: 1,191 passed, two failures in 433.08 seconds.
  Both failures reproduce unchanged in a separate archive of baseline commit
  `7f3afefb`; neither is introduced by SHIPPED. Fast guards: 126 passed.
- Six named mutants killed: production-launch filtering, exact workflow launch
  association, BSC oracle inclusion, oracle-chain retention, inactive-agent
  network eligibility, and preservation of RECORD's direct membership flag.
- Independent final review: Approved, no findings; 26 focused checks passed.

## Follow-ups

Baseline failures confirmed against `7f3afefb`, left outside this card change:

- `tests/data/test_surf_agent_hero_manager.py::test_finished_failure_does_not_keep_loading_while_sibling_read_waits`:
  the existing board-source gather retains `pending` until its sibling completes,
  while the test expects the finished failure to be `unavailable` independently.
- `tests/data/test_surf_cache_swarm.py::test_the_jobs_seen_slot_is_registered_so_it_restores`:
  the assertion still expects 34 cache slots; the baseline already has 35.
