# Surf and boardroom loading presentation

Approved owner request, 2026-10-16: remove stale and unavailable source notices
from every Surf/boardroom view; show loading while an opened or reopened view
still has reads in flight. This changes presentation, not the source truth.

## Scope and behavior

- Apply to the boardroom, every native Surf body, the tokens overview and the
  selected-token dashboard, including cards, panel headings, footers and tooltips.
- Remove explicit stale, unavailable and load-failed source notices and degraded
  source badges. Keep neutral read/as-of times where useful.
- Retain cached values, real zeroes, partial coverage qualifiers and operational
  states such as blocked jobs, offline seats and failed workflows. Missing values
  remain `—`/`--`; a source-only warning footer becomes blank. Never manufacture
  an empty result or success state to hide an error.
- Show one restrained screen-level loading indicator while its guarded refresh
  or relevant manager tasks are actually running. Existing data remains visible.
  Opening, reopening and mode switches participate. Completed, failed, cancelled
  and cancelling tasks do not keep the indicator running.
- Repaint completed background work promptly through a passive cache projection.
  The indicator must not launch requests, bypass backoff or create retry loops.
- Do not remove words from third-party content using a generic text replacement.
  Target source-status presentation at its explicit rendering branches.

This owner-directed display policy overrides earlier project instructions to
print stale/unavailable warnings on these views. Internal source states, clocks,
failure bookkeeping, cache semantics and keyless read-only behavior remain.

## Frozen manager interface

No snapshot key lists or widget update signatures change.

`SurfManager.is_loading(view: str | None = None) -> bool` reports running tasks
relevant to the named native mode (`dashboard`, `launchpad`, `pool4`,
`pool4_user`, `swarm`, `work`, `oracles`, `agent`, `board`) or the `surfboard`
boardroom. `None` includes its owned work. A task is running only when it exists,
is not done and is not cancelling. This method is synchronous and read-only.

`SwarmTokensManager.is_loading(view: str | None = None, *, token_id: str | None = None)
-> bool` uses the same task rule. The optional token identity limits enrichment
batches to that token; catalogue reads still apply. Batch identity is recorded
when a task is accepted, without modifying network scheduling.

`SwarmTokenDetailManager.is_loading(view: str | None = None) -> bool` combines
its own launch-detail task with token-scoped work in its borrowed overview.

All three managers expose `get_snapshot() -> dict`: a synchronous passive
projection of completed cache data, with no task creation, network I/O or offers.
Surf delegates its existing `get_hub_snapshot()`. The tokens manager additionally
exposes `get_selected_token(token_id, *, launch_uuid=None) -> dict | None` to
refresh the detail screen's exact token identity from completed borrowed reads.

## Acceptance

1. Source warning words/badges are absent from rendered views and tooltips.
2. Source states and missing/zero/partial distinctions survive unchanged.
3. A held fetch or detached task shows loading with and without cached data.
4. Completion, failure and cancellation stop loading; reopening starts it again
   only when real reads are pending. A different token's task does not hold the
   selected-token indicator open.
5. Passive completion repaint updates values without offering another read.
6. Operational statuses, safe markup, links/copy actions and layouts survive.

## Design choice

Per-widget loading envelopes would require new keys across many independent
sources and duplicate lifecycle logic. A screen-level indicator driven by real
tasks covers both initial reads and cached reopen refreshes with a smaller
contract. Neutral timestamps retain the source age without warning text.
