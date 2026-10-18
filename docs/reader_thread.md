# Independent dashboard reader

## Problem and evidence

The user requests an independent UI thread and data reader thread. On 2026-10-18,
an offline 149×45 Textual probe using public captures (3,413 work rows and 8,579
oracle jobs) measured median cached projection 187 ms, dirty JSON save 141 ms,
UI deepcopy 49 ms and navigation-to-paint 598 ms (721 ms maximum). These are
diagnostic samples, not a production SLA. Most projection time repeatedly walks
seat history; SURF also updates widgets belonging to hidden bodies.

## Design

Use one persistent reader thread with its own asyncio event loop. It owns lazy
manager construction, HTTP clients, mutable caches, projections, periodic reads
and cache persistence. The Textual thread owns input, layout and widgets. A small
local snapshot store publishes isolated dictionaries atomically; UI reads only
these local references and lightweight loading/revision metadata. Copies happen
on the reader. Existing JSON caches retain their current formats and locations.

A file/SQLite queue would add serialization and I/O at every handoff without
helping this two-thread application. A separate `to_thread` call per fetch would
leave constructors, sync getters and loop-bound client/task ownership unresolved.

Keep active-view ownership: boardroom reads its card sources only; detail boards
read on entry and every 30 seconds while visible; leaving stops acquisition.
Reopening paints retained local data immediately, then refreshes. Changes to view,
seat, wallet or selection invalidate late results. Errors retain last-good data
and internal provenance; the centered animated loading footer remains the UI.

The reader publishes after reads and commands, and at a bounded cadence while
detached collectors are completing. An idle spinner tick must not re-project
large payloads. UI dispatch is limited to the visible body and changed snapshots.
Neither thread waits synchronously on the other. Shutdown drains/cancels reads,
closes constructed managers on their owner loop and joins the reader asynchronously.

## Frozen seam and ownership

`ReaderRuntime.register(key, factory, initial_metadata)` returns a `ReaderHandle`
without constructing the manager. Handles expose local snapshot getters, loading,
revision and mirrored selection metadata; setters enqueue reader commands. Async
queries return isolated results. Child handles create their real managers on the
reader and preserve shared resources. No handle exposes a manager, client or cache.

| Package | Owner | Files | Dependencies |
|---|---|---|---|
| Reader runtime and handles | Agency Software Architect | `data/reader.py`, `tests/data/test_reader.py` | Frozen seam |
| App/lifecycle and child callers | Session | `app.py`, `screens/dashboard_screen.py`, `screens/swarm_tokens.py`, `screens/surf_nft.py`, composing tests | Reader seam |
| CURATOR special callers | Agency Performance Benchmarker | `screens/curator.py`, `tests/screens/test_curator_reader.py` | Reader seam; baseline complete |
| Visible rendering and loading | Agency UX Architect | `screens/surf.py`, `screens/surfboard.py`, `widgets/status_bar.py`, focused tests | Reader passive getters |
| Responsiveness evidence | Agency Performance Benchmarker | `tests/screens/test_reader_responsiveness.py`, temporary benchmark | Reader seam |

Estimated size: 700–1,000 production lines. Packages have disjoint file ownership;
one final review covers the integrated change. Reassess review scope if the actual
implementation materially exceeds this estimate.

## Acceptance and validation

- Construction, setters, fetching, projection, persistence and close execute on
  the same reader thread, distinct from Textual.
- A deliberately blocked reader leaves keyboard navigation and animation working.
- Retained snapshots paint on reentry; old view/identity completions cannot replace
  the new scope; polling stops for inactive screens and remains single-flight.
- Every app dashboard uses a handle, including CURATOR's filter/ENS queries and
  NFT/token/portfolio children. FrenPet variants retain one shared reader cache.
- Hidden SURF widgets and unchanged timer snapshots receive no repeated updates.
- Shutdown leaves no running reader or owned tasks.
- Named tests during implementation; concurrency mutations must make tests fail.
  Once integrated, run touched/composing files and fast repository guards. No full
  suite. Show live keyless render at 149×45 and compare the diagnostic benchmark
  before final independent review; document residual findings before local commit.

## Measured outcome

The same public-capture workload at 149×45 produced these diagnostic observations:

| Metric | Before | Reader implementation |
|---|---:|---:|
| Startup to mounted | 715 ms | 315 ms |
| Navigation median | 598 ms | 97 ms |
| Navigation p95 | 721 ms | 159 ms |
| UI heartbeat lateness p95 | 520 ms | 90 ms |
| UI refresh median | 375 ms | 38 ms |

Eight navigation/refresh samples, without network. Both renders contained real
captured RECORD rows, owner/model, 688 collaborators and 3,208 oracle jobs.
Startup measures mounting, not completion of fresh reads. Before, refresh included
processing; after, it consumes a local snapshot. Reader computation and JSON
serialization are still expensive and contend for Python's GIL; this change
isolates their work and reduces repainting rather than claiming faster APIs.

Live keyless BOARDROOM and AGENT views were also rendered at 149×45 with a separate
temporary public-only cache. The UI retained its Matrix theme, populated card and
record values, and animated loading footer while sources completed independently.

Final Agency review approved both scoped corrections: pre-start query cancellation
settles the UI waiter, and idle BOARD contribution offers avoid full projection.
The post-fix affected files passed 163 tests; fast guards passed 126. Six older
composing failures reproduce on unchanged `5fe52bbf`; details and measured
follow-up work are recorded in [the loading follow-ups](surf_data_loading_followups.md).
No full suite was run.
