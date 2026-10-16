# Surf loading baseline — 17.10.2026

P0 of `docs/surf_data_loading_plan.md`. Measurement only; no application edits,
provider additions, signing, paid jobs or real-user cache writes. All pytest
commands used a temporary `HOME`; the live script used a temporary Surf cache.

## Gate decision

Correctness, finite freshness and detail deduplication may proceed. **Optional
P6 scheduler detachment and P7 seat-stage reordering are deferred:** the real
app path was exercised, but neither live run completed before 80 **observed**
attempts. Review
subsequently found incomplete coverage of late-owned clients; total attempts
are unknown and compliance with the requested total cap is not established.
A real terminal paint was **not measured**. There is no accepted visible
speedup, completed navigation latency, or performance SLA claim.

## Original application: controlled event observations

The tests call the actual `SwarmClient.fetch_job`,
`SurfManager.fetch_and_compute` / `_cycle`, `_pool_swarm_seat` and
`AgentCardSources.read` methods. Existing committed fixtures provide payloads;
`asyncio.Event` holds individual reads. The membership scenario expands a
captured seat into 64 distinct build-job rows; it is a controlled upper-bound
case, not a claim that every live seat requires 64 requests.

| Scenario | Observed before implementation |
|---|---|
| Five concurrent readers, one job ID | 5 logical reads, 5 HTTP transport attempts; all receive complete fixture detail |
| First membership group held | 4 membership reads started; seat slot already published; 0 submission reads |
| All 64 membership reads completed, earnings held | 0 submission reads; seat collection still pending |
| Earnings released | Exactly 4 submission jobs read, existing cap preserved |
| Chain held in the actual full cycle | Market fetch not started; selected-seat read not offered |
| A → B → A | Requests 420, 421, 420; first two seat tasks cancelled; final seat 420 and exact original submission hash |
| Warm popup and local WORK selection | 0 network attempts; existing popup snapshot and WORK selection methods exercised |

These are request counts and event ordering, not wall-clock latency samples.
The observed blocking paths establish causality in controlled fixtures; the
plan additionally requires a complete live baseline for optional performance
changes. Original counts are retained in
[surf_data_loading_offline_baseline.json](surf_data_loading_offline_baseline.json).
The shared-detail harness test permits 1–5 actual attempts after implementation,
so it does not require the application to retain the original duplication.
The memo package owns the stricter one-flight regression contract.

## Public read-only probe — incomplete transport coverage

```sh
SURF_PROBE_HOME=$(mktemp -d /tmp/maxpane-surf-probe.XXXXXX)
env HOME="$SURF_PROBE_HOME" .venv/bin/python scripts/measure_surf_loading.py \
  --size 149x45 --max-requests 80 --deadline 90 \
  --output /tmp/maxpane-surf-loading-live.json
```

A cold manager and a newly constructed warm manager shared one isolated,
persisted cache. The script runs the existing full collection, awaits its BOARD
collection, selects an actual BOARD row with submitted outcomes, and attempts
the selected seat/RECORD path. No synthetic seat or extra provider was used.
The original per-instance instrumentation covered clients present at setup,
but missed clients created later by retained factories. Consequently **80 is
only the observed count; total attempts are unknown**. The historical capture
cannot certify the requested total 80-attempt cap or absence of HTTP 429 on
unobserved clients. Its recorded responses contain no 429. No global production
instrumentation was installed. The corrected harness now instruments all three
retained factories before the caller can send, and fixture tests verify budget
and 429 stopping. That correction does not repair the old live capture.

| Run | Observed attempts; total unknown | Abort elapsed incl. cleanup | First useful manager snapshot | Selected seat | Outcome |
|---|---:|---:|---:|---:|---|
| Cold | 80 | 6,423.049 ms | 3,952.317 ms | 527 | Censored: observed-attempt budget |
| Warm | 80 | 5,092.934 ms | 3,997.204 ms | 527 | Censored: observed-attempt budget |

Responses included HTTP 200 and 503. The recorded snapshot event means a
projection contained actual useful overview/market/record data; it does not
mean the selected RECORD finished. The elapsed values describe aborts and
must not be compared as successful cold/warm latency. Sample size: 2 attempts,
0 complete, 2 censored; complete-sample median/range are `null`. No p95, p99,
confidence interval or speedup is inferred. The earlier 33 endpoint probes are
not part of this baseline. A preceding sandbox-only attempt could not resolve
public hosts and was excluded from live timings.

Recorded events, status codes, response byte counts, slot publications and
projection timestamps are in
[surf_data_loading_live_baseline.json](surf_data_loading_live_baseline.json)
(about 66 KiB, no response bodies). Its amended validity fields explicitly mark
transport coverage incomplete, observed attempts 80, and total attempts `null`.
Logical method events are separate from
physical transport attempts. The current harness additionally links physical
attempt ordinals to instrumented logical calls; an ordinal is not automatically
a retry (market calls contain parallel endpoint branches).

The `--size` value records the intended terminal size. This manager-only probe
does not mount a screen and leaves `first_paint_ms: null`; it cannot satisfy P8's
real live-render gate. Fixture WORK compositing validates local selection only.

## Verification and limitations

Initial harness RED: six behavioral cases failed with the deliberate
`NotImplementedError` measurement stub. Initial GREEN: **6 passed in 0.30 s**.
Actual-manager baseline then recorded **8 passed in 0.46 s**, before additive
model metadata seeding was released. Final scoped command:

```sh
SURF_TEST_HOME=$(mktemp -d /tmp/maxpane-surf-baseline.XXXXXX)
env HOME="$SURF_TEST_HOME" .venv/bin/python -m pytest tests/test_measure_surf_loading.py -q
```

**16 passed in 0.93 s after review fix round 1.** Budget and deadline tests
cancel and await all owned
operation/child tasks, and the HTTP-429 test proves no second host attempt.
All HTTP test responses use MockTransport and committed detail fixtures or
synthetic error responses; manager tests
use the established network-dead client doubles. No full suite was run.

Review fix round 1 added six actual-factory regressions before changing the
harness. Base and Robinhood launch clients reproduced **4 actual HTTP attempts,
0 measured** with a requested cap of one, for both 503 rotation and 429.
The token/portfolio adapter factories similarly reproduced **2 actual, 0
measured**. All six were RED. The minimal correction wraps
`_launch_rpc_client`, `swarm_tokens_manager`, and `portfolio_manager` on the
measured manager instance and traverses each returned owner before its first
read; existing seen-object tracking prevents duplicate instrumentation. All six
are now GREEN with exactly one actual/measured attempt and the correct stop
reason. The concurrent five-reader test also compares the instrumented count
directly with the independent MockTransport counter.

No live probe was repeated after discovery or correction of the coverage bug.
A complete, correctly instrumented live baseline plus real paint remains
required before accepting optional scheduling changes. The historical total
request budget is unverified; it was not deliberately increased.
