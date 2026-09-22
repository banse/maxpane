# swarm body branch — follow-ups

Findings raised during `feature/surf-swarm-body` (docs `docs/imd_swarm_api.md`,
`docs/superpowers/specs/2026-09-16-surf-swarm-view-design.md`) and deliberately **not** fixed on
the branch, per CLAUDE.md's "report defects, do not fix them" rule and the review discipline that
a scoped re-review files what it finds outside its own target rather than repairing it. The
branch's working notes (`task-*-review.md`, `task-*-re-review*.md` under
`.superpowers/sdd/2026-09-16-surf-swarm-body/`) live in a git-ignored workspace that is deleted
when this plan finishes, so this file is the only place these survive.

## Status — all ten resolved, 2026-09-17; F13 and F14 closed by removal, 2026-09-21; F16–F25 filed 2026-09-21 (F16 AGENT closed; SWARM remains an owner decision); F20 closed, F26 closed by removal, F24 reworded and F27–F38 filed 2026-09-21 by the `/seats` programme

Swarm v2 (WP7, `docs/surf_swarm_v2_implementation_plan.md`) deleted `swarm_queue.py` and retired
`swarm_queue_depths` with the other seven v1 keys, so F13 (the `depths or None` conflation behind
QUEUE's PENDING block) and F14 (a markup-only counter name rendering as `-- 3`) have no code left
to fix: closed by removal, not by a fix. The hero's QUEUE box now reads `swarm_queue_total`, which is
`None` only when nothing could be summed and `0` for a real zero (`sw.queue_total`). F11, F12 and F15
remain open.

Seat-details update (2026-09-22): F27 is resolved by separate feedback-status rows; F29 is closed
by removal. F30's SEAT case is resolved, its FEEDBACK case removed, and the tokenless RECORD /
BY NODE residual is F39. F28 remains open because the single-token cache is unchanged. F40
records handover defects; F41 records the existing missing-`work` conflation. The older status
heading and original observations below describe their respective programmes.

Worked on branch `feature/swarm-followups`. Each entry's original reasoning is kept below, unedited,
so the argument that produced it survives alongside what actually happened.

| | resolution | commit |
|---|---|---|
| F1 | **fixed** — derived thresholds replaced by a real sweep (15–89); boundary found empirically at 43 | `a82748b` |
| F2 | **fixed** — a second, independently-shaped adversarial payload added; both now swept | `a89ed97` |
| F3 | **fixed** — the shortened-window branch now requires a hash-only *painter*, not just a value match | `6f4c358` |
| F4 | **nothing to do** — see the correction under that entry | — |
| F5 | **fixed** — both curator waits are event-driven or honestly bounded | `67f0e52` |
| F6 | **fixed** — QUEUE gained a `PENDING` block; row pin 26 → 28, binding container body → `SWARM_TOP_ID` | `6d3d5a1` |
| F7 | **fixed, with its benefit corrected** — see the correction under that entry | `3603279` |
| F8 | **evidence refuted** — see the correction under that entry | `0503651` |
| F9 | **fixed** — and it was real: a live request to `pool4.imd.fun/docs` appeared under mutation | `698fdc5` |
| F10 | **fixed** — `jobs is None` split from `jobs == []`, per field | `f06a8f3` |

Two entries below state things that later measurement contradicted, and one asked for work that
turned out not to exist. They are corrected in place rather than deleted, because the reasoning that
led to each is worth more than a tidy file:

- **F4 needed no fix at all.** Its own text already says so ("There is nothing to fix"), and that
  held up: the package-root rule is correct for every case in the repo, and walking into every
  `__init__.py` body is a more invasive check neither incident called for. It stays filed as a
  *named dormant blind spot* for whoever first puts real logic in a package root.
- **F7's benefit was overstated when the fix was chosen.** The dirty-flag skip is correct and proven,
  but `SLOT_CHAIN` stores an advancing `block` on virtually every cycle and `set_baselines` is
  unconditional, so with one JSON document and one flag *any* changing field still forces the whole
  write. The savings are structural — idle periods, degraded periods, shutdown — **not** a reduction
  of the steady-state 30 s rewrite while online. The owner was told this and chose to keep it as
  landed rather than trim the scores slot or split the cache per slot.
- **F8's central claim did not reproduce** — see the correction under that entry.

## F1 — the throughput width test re-derives the widget's own arithmetic instead of sweeping

`tests/widgets/test_surf_swarm_rail.py::test_throughput_sheds_the_hash_and_its_chain_word_together`
computes its narrow/wide widths from `swarm_throughput.py`'s own private constants
(`_AGENT_COLS`/`_SCORE_COLS`/`_JOBS_COLS`/`_MIN_TX_COLS`/`_CHAIN_COLS`/`_GAP`) rather than sweeping
a range of widths and asking whether the marker and the rendered pair agree at the boundary the way
the terminal-layout skill's own "sweep the boundary, not a comfortable width" rule asks for. It
does bite today: mutating the formula's *behaviour* (for example, dropping the hash without the
chain word, or the reverse) reddens it, because the test asserts what actually renders at its two
computed widths, not merely that the formula returns some number. What it cannot catch is a
refactor that changes the formula's **shape** — a different reservation order, an added term — in a
way that moves both the test's derived thresholds and the widget's real behaviour together, in
lockstep, while breaking their agreement with the *true* crossover a sweep would find. A
values-agree-with-themselves test cannot see that class of drift.

**Why it is not fixed here.** It was filed once by the implementer's own review pass
(`task-8-re-review.md`) and re-disclosed, correctly left untouched, by the Task 12/13 layout review
(`task-13-review.md`, "Filed observations"). Two independent passes looked at it and concluded the
same thing: turning it into a real width sweep is a bigger change than either review's own scope
(fixing what was asked, not what was merely noticed), and the test is not wrong for today's code —
it is a known-narrower guarantee than the skill asks for, not a defect in what it currently checks.

## F2 — the `SWARM_BODY_ID` false-positive check has one adversarial payload, not a family

`tests/screens/test_surf_swarm_layout.py::test_the_registration_does_not_light_the_marker_when_nothing_is_cut`
is the other half of the fix that registered `#surf-swarm-body` in
`_SCROLL_COLUMNS[MODE_SWARM]` (closing the gap where the body could scroll and cut JUST SHIPPED's
table with `‹ taller` dark) — it exists to prove the registration does not *cry wolf*, the
`DataTable.show_horizontal_scrollbar`-shaped risk applied to a vertical scrollbar instead. It sweeps
only `_shipped_heavy_light_rail_payload(30)`, the one payload shape built to stress
`#surf-swarm-body` in the first place (light rail content, thirty JUST SHIPPED rows), over heights
from the row pin upward.

That payload is the right one for proving *this* fix does not fire spuriously, and it does: the
review that added the false-positive check confirmed no independent adversarial shape was
constructed to hunt for a different way the body's own scrollbar could appear for a cost-free
reason (`task-12-review.md`, "Filed observations": *"is not independently ruled out by this file"*).
A future payload shape — a different content mix that grows the body's own scrollbar without
costing a row of any panel's content — is not swept here and could in principle find a false
positive this file's one payload cannot.

**Why it is not fixed here.** Building a second adversarial payload and re-sweeping against it is
new test-authoring work, not a repair of what shipped; the existing check is correct for the shape
it tests. Filed as a note for whoever next adds a payload shape to
`tests/screens/test_surf_swarm_layout.py`.

## F3 — the main sweep loop's shortened-window hash exclusion is still value-only (pre-existing, not introduced by this branch)

`tests/screens/test_address_icons_everywhere.py::test_every_rendered_address_carries_an_icon_that_copies_it_and_a_link_that_opens_it`'s
own sweep loop excuses a shortened address window with no icon in two different places, and only
one of them was tightened on this branch:

- the **whole-address** branch (line 757) checks `_hash_only_module(painter) and
  _continues_as_hash_window(...)` — provenance *and* value, fixed on this branch
  (`1c279ea`, "narrow the hash-window excuse to provenance, not value");
- the **shortened-window** branch (line 772) still reads
  `if not copied and any(_window_matches(head, tail, h) for h in hashes): continue` — value only,
  with no `_hash_only_module` check on which widget painted the token at all.

This is the identical defect class the region scanner (`_address_tokens_in_region`) and the
whole-address branch both had before this branch's fix: a real, un-iconized address whose digits
happen to match some hash's own head/tail window anywhere in the *entire served payload* — not
necessarily the same widget, not necessarily related — is silently excused as "a hash's own
window," which would hide a genuine missing-icon defect on a shortened address rather than fail the
sweep.

**Evidence it is pre-existing and known, not new.** `task-13-review.md`'s Finding 1 (High) — the
review that found and drove the whole-address/region-scanner fix — names this exact line by its own
pre-fix number (`tests/screens/test_address_icons_everywhere.py:495-496`) as *"an existing,
unmodified exclusion already in place for the shortened-window scan, present before this diff, not
touched by it — so the risk model was already accepted by this repo for that one path."* The
follow-on scoped re-review (`task-13-re-review.md`) independently re-confirmed the same failure
**class** — excusing by classification or value rather than by proven provenance — is still live in
a sibling mechanism (`_hash_only_module`'s direct-import-only check misclassifying `feed.py`/
`signals.py`, itself since closed by `cc4a8a3`), reinforcing that this is a recognised, accepted-risk
shape rather than an oversight. Both reviews treated it as out of their own scope: the first because
fixing it was not what it was asked to verify, the second because its brief was scoped to the
provenance fix alone.

**How the region-scanner version was fixed, for whoever picks this up.** `_hash_only_module`
(`tests/screens/test_address_icons_everywhere.py:460`) decides whether a widget can *ever* construct
a real, icon-bearing address, by walking that widget's own module's imports to a fixed point
(`_reaches_icon_machinery`, a `queue`/`seen` BFS over `module_imports`, following only
`maxpane_dashboard.*` names) until it either reaches `address_text`/`address_prose` or exhausts the
graph. Two things made that walk correct rather than merely plausible:

1. **It went to a fixed point, not depth 1.** A depth-1 version (checking only the widget's own
   direct imports) was green while `widgets/surf/feed.py`/`widgets/surf/signals.py` reached the icon
   machinery one hop further out, through `widgets/surf/_icons.py`. This branch's own final commit
   (`cc4a8a3`, "resolve the icon-machinery indirection transitively, to a fixed point") closed that
   exact gap by walking the import graph to a fixed point instead of one layer.
2. **Package roots are excluded from the walk.** `from maxpane_dashboard.widgets.surf import
   _rowfit` resolves to *two* names in the AST — the real edge (`...surf._rowfit`) and the bare
   package (`...surf`) as an artifact of the import shape, not a real one. Following the package
   root made every surf widget that imports any sibling this common way reach every icon-producing
   widget in the package, which is a **different** bug (a package-root false positive, itself found
   and fixed the same way this file already fixed a false-negative). The walk resolves each
   candidate through `_is_module` and skips a name whose `importlib.util.find_spec(...)
   .submodule_search_locations` is not `None` — i.e. a package, not a plain module — before
   following it.

The fix for F3, when it is scheduled, is the same shape: give the shortened-window branch the
`hash_only=_hash_only_module(type(widget).__module__)`-equivalent check the whole-address branch
and the region scanner already have, resolving the *painting* widget the same way
`_widget_module_at` does for the whole-address case, rather than exempting on value alone.

## F4 — `_hash_only_module`'s package-root exclusion is correct today and has a named dormant blind spot

> **Resolved 2026-09-17: nothing to do, and no commit.** This entry asked for no repair and, on
> re-examination, still asks for none. Re-confirmed against the current tree: no `__init__.py` under
> `maxpane_dashboard/` defines an icon-building helper or calls one, so every package root the walk
> skips is a pure re-export surface and the exclusion is correct for every case that exists. It stays
> filed as a **named dormant blind spot** — the value here is the warning, not a change. The next
> person to put real logic in a package root, rather than only re-exports, needs to know this walk
> will not see it.

`_reaches_icon_machinery`'s walk (`tests/screens/test_address_icons_everywhere.py:391`) never
follows a package root (`__init__.py`) as an import edge, which is the right general rule — see F3
above for why following one produced a false positive during this branch's own fix. The blind spot
that rule leaves open, named rather than hidden: **a package `__init__.py` that ever *defines*
icon-related logic directly**, rather than only re-exporting names from its own submodules, would be
invisible to the walk, because the walk treats every package root as a non-edge unconditionally —
it never inspects what the `__init__.py` itself contains, only whether the name it resolves to is a
package.

Checked across the whole repo as of this branch's head: no `__init__.py` under `maxpane_dashboard/`
defines `address_text`, `address_prose`, or any function that calls either — every package root
that is a plausible import target for a surf (or any dashboard's) widget is a pure re-export
surface, exactly `widgets/surf/__init__.py`'s own stated contract ("the package root is the import
surface the screen and its tests use"). So this is a dormant risk, not a live one: nothing in the
repo exercises it today.

**Why it is not fixed here.** There is nothing to fix — the rule is correct for every case that
exists, and pre-emptively walking into every package root's own body to check for a defined
function (rather than an import) is a different, more invasive check that the two false-positive/
false-negative incidents this branch actually hit did not call for. Filed so the next person adding
a package `__init__.py` with real logic in it — rather than only re-exports — knows this walk will
not see it, and knows to either keep the convention (re-exports only) or extend the walk.

## F5 — a curator test flaked during this branch's suite run, found here but not caused by this branch

`tests/screens/test_curator_screen.py::test_screen_adds_removes_and_deduplicates_custom_collection`
failed once, during Task 14's full-suite run, inside a directory-level chunked run of
`tests/screens/` — nothing on this branch touches curator code, and the failure is **load-dependent**,
not deterministic and not caused by anything here.

**The four measurements, quoted rather than re-run:**

- The failing test **alone**: 1 passed in 2.64s.
- The **whole file** (`tests/screens/test_curator_screen.py`) alone: **219 passed in 263.27s**,
  exit 0 — so it is not intra-file ordering pollution either; every other test in the file, run
  together with this one, passes.
- It failed only inside a chunked, directory-level run alongside other test files under load.
- `git diff --name-only main...HEAD | grep -i curator` returns **nothing**: this branch touched no
  curator code, test, or fixture at all.

**The error shape:**

```
AssertionError: assert 'already available above' in 'NFT contract must be a 20-byte 0x address ...'
tests/screens/test_curator_screen.py:3505: AssertionError
```

Expecting `"already available above"` (the duplicate-collection message) and getting `"NFT contract
must be a 20-byte 0x address"` (the malformed-input message) is a debounce/timing race in the
custom-collection filter's input handling — the assertion lands before or between two `Input.value`
writes and their debounced validation settling, so it reads a transient invalid-input state instead
of the final one, only when the process is under the extra scheduling pressure a concurrent
directory-level pytest run adds.

**A sibling flake in the same feature area is already documented.**
`docs/address_copy_followups.md`'s "Flaky test (pre-existing, load-sensitive)" section already
names `test_delayed_custom_name_does_not_block_reset_or_clear_new_input` — the same curator
custom-collection filter editor, the same shape (a wall-clock wait, `asyncio.wait_for(...,
timeout=0.25)`, that has failed under full-suite load and passed alone 3/3), with the same fix idea
already on record: replace the wall-clock waits with event-driven awaits or generous timeouts. This
is a second instance of that same class in the same area, not a new class of defect.

**Conclusion.** The fix belongs to a curator-scoped pass that makes the custom-collection filter's
timing deterministic — event-driven awaits in the test, or a debounce the widget itself exposes to
wait on — rather than load-sensitive wall-clock/scheduling assumptions. Not fixed here: no curator
code, test, or fixture was touched by this branch, and this finding is filed exactly where it was
found rather than repaired, per the same "report, do not fix" rule every other item in this file
follows.

## F6 — `swarm_queue_depths` is published and consumed by nothing

It is in the frozen contract (`data/surf_models.py:1457`), folded by the manager's `_swarm_keys`
(`data/surf_manager.py`, `"swarm_queue_depths": facts["queue_depths"]`), and read by no widget
anywhere: `rg swarm_queue_depths maxpane_dashboard/widgets/` finds only `swarm_hero.py`'s own
docstring, which names it as a key that hero card explicitly does *not* need (a worked example of
what it deliberately omits, not a consumer). Design §4 lists it as a payload key, and the gap is
already documented twice over rather than hidden: `tests/screens/test_surf_screen.py:759` and
`tests/test_surf_registration.py:1388` both carry a comment recording that this key reaches no
widget, alongside the fixed set every other `swarm_*` key belongs to.

**Why it is not fixed here.** The 2026-09-17 fix wave (`final-review.md`'s six named findings,
F-A through F-F in that report's own lettering -- distinct from this file's F-numbering) was
scoped to those six; deciding whether to build a consumer for this key or drop it from the
contract is a product call (does a fifth panel, or a cell inside one of the existing four, want
`pending*` counters by name?), not a defect with one obvious repair. Filed so whoever next touches
the swarm body's contract makes that call deliberately rather than leaving a payload key nothing
reads.

## F7 — cache write amplification, roughly 2×, every poll

> **Fixed 2026-09-17 (`3603279`) — and the benefit below was overstated when the fix was chosen.**
> The mechanism is a comprehensive **dirty flag**, set at the exact point of every mutation and
> cleared only on a successful write. Two cheaper mechanisms were measured and rejected: *identity
> checks* cannot work because the `series` deques are mutated **in place** (`append`,
> `deq[-1] = ...`) and `_pool4_accumulators` via `__setitem__` on the same outer dict — the container
> object never changes, only its contents; and *per-slot content diffing* buys nothing, because
> `SLOT_CHAIN` stores an advancing `block` on virtually every cycle and `set_baselines` runs
> unconditionally.
>
> **The correction:** with one JSON document and one flag — the shape this entry asks for — *any*
> single changing field still forces the whole file to be written. So the saving is **structural**
> (idle periods, degraded periods, shutdown), **not** a reduction of the steady-state 30 s rewrite
> while the dashboard is online and the chain is advancing. That is inherent to a whole-file design,
> not a flaw in the implementation. The owner was told this explicitly and chose to keep it as
> landed rather than trim the scores slot or split the cache per slot.
>
> The fix also caught a **pre-existing** test that this very change would have turned green for the
> wrong reason: `test_save_creates_its_directory_is_atomic_and_never_raises` called `save()` on a
> never-mutated cache pointed at an unwritable path to prove "never raises" — under the fix a clean
> cache skips before it ever reaches that path. It now dirties the cache first, restoring genuine
> coverage of the failure it names.

`save_cache()` runs at the end of every `_cycle` and `SurfCache.save` serialises every last-good
slot whole, with no per-slot size cap. Measured against the committed capture during the final
review (2026-09-17):

| | bytes |
|---|---|
| `SLOT_SWARM` payload | 52,814 |
| `SLOT_SWARM_SCORES` payload | 223,122 |
| combined new | 275,936 |
| existing `~/.maxpane/surf_cache.json` | 250,713 |

So the two swarm slots roughly double the surf cache file, and the whole file is rewritten every
poll (30 s default) even when neither swarm tier changed anything that cycle. The scores slot in
particular stores all 62 captured jobs' own details, which feed only two panels (JUST SHIPPED and
THROUGHPUT's score rows).

**Why it is not fixed here.** Not a correctness defect — nothing here is wrong, stale, or dishonest
— and not a rule this repo has written down anywhere: no existing convention caps a slot's
persisted size or exempts an unchanged slot from a poll's write. Costing and deciding whether it
is worth a fix (a per-slot size cap, a dirty-slot skip on save, trimming the scores slot's stored
detail) is a separate, deliberate piece of work, and nobody had costed it before this review found
it. Filed rather than repaired, per the same rule as every other entry in this file.

## F8 — a pre-existing network-dependent test in `test_surf_cache.py` (pre-existing, not caused by this branch)

> **Correction, 2026-09-17 (`0503651`): the central claim below did not reproduce.** Before fixing
> anything, the evidence was re-measured with interception at four layers —
> `httpx.AsyncHTTPTransport.handle_async_request`, `httpx.HTTPTransport.handle_request`,
> `socket.socket.connect` and `socket.getaddrinfo` — and the recorder was **validated first against a
> deliberate real call** to confirm it catches what it claims to. Result: **0 outbound requests**, for
> the named test alone, for the whole file, and for the exact two-file combination this entry names
> (101 passed, where this entry claims 100 passed / 1 failed). `git diff` from the branch's fork point
> shows no functional change to either file, so nothing explains the discrepancy: the test was
> **already structurally network-dead**, building every client on injected `httpx.MockTransport`
> doubles whose handlers assert on unexpected calls.
>
> **What was genuinely missing** was narrower, and is what got fixed: nothing proved those mocks were
> ever *exercised*, only that they were *present* — a test that silently stopped issuing requests
> would still have passed. Two `assert transport.requests`-shaped assertions now close that, on
> `test_curator_published.py::test_every_request_goes_through_the_injected_transport`'s precedent,
> each proven to bite by clearing the recorded requests immediately before it.
>
> The original claim was filed in good faith but never re-derived against the shipped tree. Left
> standing below, uncorrected in its own words, because a wrong measurement that was caught is worth
> keeping visible — the failure mode it illustrates (trusting a filed number instead of re-measuring)
> is the same one this branch hit twice more, in F7's benefit and in a "retired" layout exception
> that turned out to be an artifact of a defect.

`tests/data/test_surf_cache.py::test_the_launchpad_cursors_real_shape_round_trips_through_the_cache_file`
genuinely depends on the network: blocking outbound `httpx` makes it **fail**, with 10 real requests
recorded against `gateway.tenderly.co`, `rpc.mevblocker.io` and `ethereum-rpc.publicnode.com`. It
passes today only because the machine running it is online.

**Evidence it is pre-existing and not this branch's doing.** `git show 9606626:tests/data/test_surf_cache.py`
(the branch's fork point) already contains this test, unchanged in shape; this branch's only
change to the file is the `TIERS`/`SLOTS` count growing to account for the two new swarm tiers. The
same construction the final review used to catch F-D (an outbound-request-recording pytest plugin)
was run against `tests/data/test_surf_manager_pool4_market.py` + `test_surf_cache.py` together:
100 passed, 1 failed — this test, and only this one.

**Why it is not fixed here.** Exactly F5's shape, labelled the same way: no code, test, or fixture
this branch touched is the cause, `git diff` against the fork point shows no functional change to
this file, and the fix (giving this test the same structurally-network-dead double every other
manager/cache test file in this package already uses) belongs to a `surf_cache`-scoped pass, not to
the swarm body fix wave. Filed exactly where it was found, per the same "report, do not fix" rule
every other item in this file follows.

## F9 — a second test that can reach the network (pre-existing, not introduced by this branch)

`tests/data/test_surf_manager.py:4083` builds its `m2` manager by hand — the same construction F-D
already touched on this branch — and passes `swarm_client=DeadSwarmClient()` but no `pool4_client=`.
`SurfManager.__init__` (`data/surf_manager.py:872`) falls back to a real `Pool4Client()` whenever
`pool4_client` is `None`, so this call site is, structurally, exactly the shape the swarm-client
fix (commit `a965b01`, "inject the swarm client structurally in the sibling manager test helpers")
closed for three sibling call sites: the suite is kept off the network by circumstance — nobody has
exercised the pool4 path from this particular manager instance — rather than by structure, which is
the repo's own hard constraint ("No test may touch the network. Assert it structurally — inject a
transport that raises on use.").

**Why it is not fixed here.** The whole-branch review that produced `a965b01` named this exact
call site for the swarm client and left the pool4 client's identical gap alone: the branch's single
fix wave was already spent on the swarm-client instances it was scoped to, and repairing a second,
adjacent gap at that point would have shipped a fix with no review behind it — the same "a fix that
looks trivial still skips review" reasoning every other deferred item in this file rests on. Filed
here rather than patched.

**What a fix would involve.** The same shape as `a965b01`: pass a structurally clientless
`pool4_client=` double (raises on any use, the way `DeadSwarmClient` does for the swarm side) into
this `SurfManager(...)` construction at `tests/data/test_surf_manager.py:4083`, and add the same
`assert not hasattr(m2.pool4_client, "_client")`-shaped assertion the swarm-client fix added, so a
future regression fails loudly instead of passing by accident of network availability.

## F10 — the read-but-empty versus never-read conflation survives in one more place

The final review's finding F-C was that a *successful* read of an idle swarm published `None`
instead of `0`, so a real zero rendered as `unavailable`. The fix (commit `1ccc8f3`) corrected the
hero's `swarm_jobs_in_flight` and `swarm_jobs_blocked`, which now distinguish `jobs=[]` (a read that
found nothing → `0`) from `jobs=None` (no read → `--`), with tests
(`widgets/surf/swarm_hero.py:332`).

The scoped re-review found the same conflation still present in `data/surf_swarm.throughput`
(`maxpane_dashboard/data/surf_swarm.py:259`), unfixed and untested:

```python
if not jobs:
    return {"accepted_per_day": None, "median_delivery_s": None,
            "revision_rate": None, "window_days": window_days}
```

`not jobs` is true for both `jobs=None` (the swarm tier was never read) and `jobs=[]` (a genuine
read that found no jobs), so both collapse to the identical all-`None` dict. `THROUGHPUT`'s rate
rows — `accepted_per_day`, `median_delivery_s`, `revision_rate` — therefore render a dead read and a
real "the swarm has shipped nothing in the window" identically. `SurfManager._swarm_score_keys`
(`data/surf_manager.py:5476-5488`) passes `jobs`/`details` straight through from the slot with no
flattening idiom in between (`jobs = slot.get("jobs") if slot else None`, then directly into
`sw.throughput(jobs, details, now=now)`), so the two cases are still distinguishable at the point
they reach the function — the conflation is inside `throughput` itself, on the `not jobs` line, not
upstream of it.

**Why it is not fixed here.** Exactly F6/F7/F8's reasoning: the branch's one fix wave (which closed
F-C for the hero) and the one scoped re-review that followed it are both complete, and this repo's
process adjudicates residuals by filing them rather than by opening a second round on a pass that
already finished. This is a residual of a finding already fixed once, not a new defect class.

**The rule it violates, in the repo's own words.** "A failed read is `None`, never `0`" — and the
converse the hero fix established: an unread value renders `--` and a real zero renders `0`. "A row
whose real negative has no representable value ... renders `None` identically for 'we looked and
there was nothing' and 'we could not look', so it reads confident and green through an outage."
`throughput`'s three fields are exactly that row today.

**What a fix would involve.** Branch on `jobs is None` before the `not jobs` check (or replace it
with an explicit `if jobs is None: return {...}` for the never-read case and a separate `if not
jobs: return {...accepted_per_day: 0.0...}`-shaped branch for the read-but-empty case), the same
split the hero fix made for `swarm_jobs_in_flight`/`swarm_jobs_blocked`. The distinction has to be
made **before** any `for x in <arg> or ()` idiom flattens `None` and `[]` together — that idiom is
exactly where the original F-C defect hid, and `throughput`'s own `details` parameter already goes
through one at line 276 (`for job in details or ()`), which is a second place the same flattening
could reappear if the fix is copied there carelessly rather than reasoned through. Both states —
never-read and read-but-empty — need their own covering test, on the model of the hero's tests for
the same split.

## F11 — F15 — filed by a whole-branch review of the `feature/swarm-followups` fix round (2026-09-17)

Five more observations, from the review that also produced the fix round covering F5's status-table
entry and the `SurfCache.load()`/`store_last_good` work elsewhere in this branch. Filed exactly
where found, per this file's own rule: none of these is repaired here.

### F11 — `save(path=…)` clears `_dirty` for a file that is not `self.path`

`SurfCache.save()` (`maxpane_dashboard/data/surf_cache.py`) checks `_dirty` once, up front, before
it even computes `target = str(path or self.path)`. On a successful write it clears the flag
unconditionally (`self._dirty = False`), regardless of which `target` the write actually went to.
So `save("/some/other/file.json")` followed immediately by a bare `save()` leaves the *real* cache
file — `self.path` — never written: the first call satisfies `_dirty` and writes only the alternate
path, and the second call finds the flag already clear and skips.

The method's own docstring already documents the mechanism accurately — "`_dirty` tracks whether
*this cache's in-memory state* has moved since it was last committed anywhere, not the freshness of
one particular file on disk" — but "committed anywhere" is the part that hides the consequence: it
reads as reassurance (the state was persisted *somewhere*, so the flag's job is done) without
naming that "anywhere" can be a path nobody will ever read back from.

**Production-unreachable today.** The one production call site,
`SurfManager.save_cache` (`maxpane_dashboard/data/surf_manager.py:949`), always calls
`self.cache.save()` with no `path` argument, so `target` is always `self.path` there and this gap
never opens. `path=` exists for callers such as an export or an archive write that legitimately
want a *different* file without disturbing the live one — and any future caller doing that, then
also calling the ordinary `save()` in the same cycle, would hit this silently.

### F12 — F3's protection has no dashboard behind it

F3 above (`6f4c358`) closed the shortened-window hash-exclusion's provenance gap in
`tests/screens/test_address_icons_everywhere.py`. Its own commit message says plainly: "Mutating
the real call site alone (dropping the provenance check, with the fixed predicate left otherwise
intact) does not redden the existing parametrized sweep across any current dashboard — no live
widget today exercises this path." Reconfirmed here: the dashboard-wide parametrized sweep
(`test_every_rendered_address_carries_an_icon_that_copies_it_and_a_link_that_opens_it`, 29 cases over the current `CASES`
registry) stays green with `_shortened_window_hash_excuse`'s provenance check reverted to its
pre-fix, value-only body — because no seeded fixture in any current `CASES` entry manufactures the
specific collision the fix guards against (a real, un-iconized address whose shortened window
shares digits with an unrelated hash elsewhere in the same payload, painted by a widget capable of
building a real address).

The fix is real and covered — just not by the big sweep. Two *dedicated* tests carry the entire
weight: `test_the_shortened_window_hash_excuse_requires_a_hash_only_painter` (the width-swept unit
test on the extracted predicate) and
`test_the_main_sweep_catches_a_shortened_address_the_old_value_only_excuse_missed` (the end-to-end
reproduction against a real running app). If either is weakened or deleted, the branch silently
reverts to value-only excusal with nothing else in the suite able to notice — the 29-case sweep
would keep passing throughout. Worth a comment on `_shortened_window_hash_excuse` (or on the two
tests themselves) pinning them to each other, so a future editor sees why the big sweep's silence
here is expected and not evidence the predicate is unreachable.

### F13 — `swarm_queue_depths`'s upstream conflation is unchanged — CLOSED BY REMOVAL 2026-09-21 (WP7)

F6 (`6d3d5a1`) gave `swarm_queue_depths` a consumer (QUEUE's PENDING block,
`maxpane_dashboard/widgets/surf/swarm_queue.py`), but the upstream shape it consumes is unchanged:
`data/surf_swarm.health_facts` folds every `pending*` key off the live `/health` read into
`depths or None` (`maxpane_dashboard/data/surf_swarm.py:82`) — so `swarm_queue_depths is None` means
*either* "health was never read" *or* "the payload had no `pending*` key at all". `swarm_queue.py`
gates the whole PENDING block on `_has_marker(as_of) and isinstance(queue_depths, dict)`
(`swarm_queue.py:357`): when `queue_depths` is `None`, the block — the blank separator line and the
`PENDING …` line both — is simply never appended, with no message in its place. A genuine
`/health` read that happens to carry no `pending*` key at all therefore renders identically to a
panel whose swarm tier was never read: the PENDING block is *silently absent* either way, exactly
the "real negative with no representable value" shape CLAUDE.md's convention section names.

This predates this branch — `health_facts`' `depths or None` line is untouched by F6 — and F6 only
made it *visible*: before F6 nothing rendered `swarm_queue_depths` at all, so the conflation had no
panel to show through. Filed rather than fixed, on this file's own "report, do not fix" rule.

### F14 — a counter whose entire name is markup renders as `-- 3` — CLOSED BY REMOVAL 2026-09-21 (WP7)

`swarm_queue.py`'s `_pending_line` (`swarm_queue.py:295`) builds each nonzero counter's label as
`f"{strip_tags(name) or DASH} {count}"`, where `name` is one of the open-vocabulary `pending*` keys
the swarm API may add beyond `_DEPTH_ORDER`'s own seven, and `DASH` (`_fmt.DASH = "--"`) is this
package's own glyph for "unavailable" everywhere else it appears. `strip_tags` removes bracketed
markup from a host-controlled string, on the same defensiveness `queue_rows`' `state` column and
`blocked_rows`' `reason` column already apply to their own open vocabularies. If a counter's *name*
is composed entirely of markup — `"[bold]"`, say — `strip_tags` empties it, and `"" or DASH`
substitutes the unavailable glyph in a spot that is not reporting unavailability at all: a real,
positive count next to a name the code could not print. The line would read `"-- 3"`, indistinguishable
from how this same package renders a genuinely dead reading. A degenerate name is host data, not
attacker-modeled specifically for this — but the fallback reuses a glyph whose entire meaning
elsewhere in this repo is "we could not read this," which is the wrong thing to reach for here.

### F15 — `_settle`/`_settle_layout` return silently on exhaustion rather than failing

Both helpers landed by F5 (`67f0e52`, `tests/screens/test_curator_screen.py:574` and `:595`) loop a
bounded number of `attempts`, polling an observable (a widget's `region`, or a caller-supplied
`condition`) and returning as soon as it stabilizes or holds. Neither raises, logs, or otherwise
signals when the loop instead runs out of attempts without ever seeing the condition hold — they
just fall through and return normally, relying entirely on whatever assertion the caller writes
next to notice the wait never actually succeeded.

This is correct at every call site that exists today: each one is followed by an assertion on the
same state `_settle`/`_settle_layout` was waiting for, so a timeout that found nothing still turns
the test red, just via that assertion rather than the helper itself. But nothing in either helper's
signature or contract requires a caller to do this — a future call site that polls for a side effect
and then moves on without asserting the outcome (a cleanup step, a "make sure it's had a chance to
settle" call before some other action) would wait the full `attempts` budget and then silently
proceed as if it had succeeded, exactly when the underlying condition never became true. Worth
either an assertion inside the helpers themselves (trading the current "the caller's own check is
the failure signal" design for a `TimeoutError` with a good message) or a comment on each making the
"every call site must assert next" requirement explicit rather than implicit.

## F16 — F25 — filed at the close of the swarm v2 programme (`feature/surf-swarm-v2`, 2026-09-21)

Sources: the WP2–WP8 reviews and the controller's own checks, all recorded in
`docs/surf_swarm_v2_implementation_plan.md`'s "landed/implemented" blocks. Each is Minor unless it says otherwise;
the Follow-ups rule applies (Tier 0 when its file is next touched, never its own branch) except where an item is an
owner decision.

### F16 — row pins exceed the owner's terminals — AGENT CLOSED; SWARM OWNER DECISION

*2026-09-22:* **AGENT closed: owner accepted 32 rows, 2026-09-22.** The historical
40-row layout below was replaced by the measured 32-row seat-details layout. SWARM `s` at
42 rows remains open as an owner decision. BOARD WP5 subsequently adds four source-separated
rows: its new 36-row requirement is filed separately as **F46**, without extending the owner's earlier acceptance. Current geometry is in
`screens/surf.py`'s pin blocks.

`SURF_SWARM_FULL_LAYOUT_ROWS` is 42 and `SURF_AGENT_FULL_LAYOUT_ROWS` 40; the owner's terminals are 119×35 and 138×31.
Both bodies scroll there with `‹ taller` lit — degraded honestly, but degraded. THROUGHPUT's 16 fixed lines set the
`s` pin (a `#surf-swarm-top { min-height: 16 }` floor was needed); VERDICTS' 13 set the `a` pin. Options: accept;
collapse THROUGHPUT's state/cancel blocks behind a key; drop the separators; make the hero one line shorter.

### F17 — LAUNCHES `parked reason` is clipped, not wrapped (decision recorded, revisit on demand)
A `DataTable` row is height 1; a 197-char corpus reason in its column would be ~15 lines. The column is elastic above
13 cells and a clipped reason lights `‹ widen` at the full threshold on the corpus payload. `decisions.md` records the
clip. A detail view (enter on a row) would show the whole reason if the owner wants it.

### F18 — the status bar is never whole under 131 columns; the `4` body's pin is 119 (pre-existing)

*Amended fix wave, 2026-09-22:* the exact shortened hint measures a whole bar from **134**.
LAUNCHPAD/AGENT body widths are 138 and SWARM/BOARD 141. Pool4's 99/119 body-only guarantees
remain below the status edge; the narrow-status finding remains open. Earlier measurements:

*BOARD update, 2026-09-22:* the added `b board` hint makes the current whole-bar threshold
**142 columns**, verified against the complete composited right label. The `4` body's 119-column
body pin still does not promise a whole status bar; this finding remains open. Original observation:

The hint `l launchpad · 4 pool4 · s swarm · a agent` is whole from 131 (`STATUS_BAR_WHOLE_FROM`); the v1 phrase was
whole from 121; the `4` body's 119 was whole under neither. No surf pin lies in [121, 131) so WP7 regressed nothing,
but the `#status-left` `width: auto` crops the bar at the terminal edge rather than the phrase. A shorter hint at
narrow widths, or a right-label that yields first, would close it.

### F19 — `network_of("1")` coerces a numeric string to MAINNET
`int()` inside the allowlist accepts `"1"`. The API sends ints; the test asserts a non-numeric string is refused.
Tighten to `isinstance(value, int)` when the file is next touched.

### F20 — `_NON_NUMERIC_KEYS`'s comment still names `swarm_queue_depths` — CLOSED 2026-09-21 (`/seats` WP0, `8a71457`)
`tests/test_surf_registration.py:1393`: historical prose about a retired key in a live triage comment; one line.

### F21 — `MAXPANE_IMD_SEAT` is missing from CLAUDE.md's env-var list (owner-owned file) — CLOSED 2026-09-21
Closed by removal, not by listing: the owner retired the variable for a seat prompt that saves to
`~/.maxpane/config.toml`. The seat reaches `SurfManager` only as `seat=`; nothing is left to list.

### F22 — `data/surf_swarm.__all__` re-exports `seen_since_ts`, defined in `analytics/surf_swarm_signals`
The fold tests bind the re-export (`fold.seen_since_ts`). Either import it in the tests from analytics and drop the
re-export, or say in the `__all__` comment why the fold's public surface carries an analytics helper.

### F23 — THROUGHPUT's state/cancel blocks are unbounded in rows
The panel height is pinned against the corpus vocabulary (six states, a handful of cancel reasons); a new state adds
a line. Cap the blocks (top-N + `… n more`) or bind the pin to a vocabulary test.

### F24 — seat selection takes effect on the next slow-tier cycle — REWORDED 2026-09-21 (`/seats` WP2)

*2026-09-22:* the cursor path and `select_seat` are removed; the saved-seat `set_seat` path still
marks the seat tier due. The remaining timing and single-token-cache observation below applies.

`select_seat(token)` is an attribute write; the AGENT body refolds when the slow tier next runs (up to its interval).
The status bar's marker says so, but an operator expects the pick to land at once. A cheap fix: refold
`_swarm_seat_keys` from the cached sweep on selection, no network.

*Since `/seats` (WP2, `5649247`):* the seat is its own tier (`TIER_SWARM_SEAT`, 120 s). `select_seat` / `set_seat`
stay attribute writes and `mark_due` the seat tier, so the pick lands one detached `/seats` read after the next poll,
not a whole slow-tier interval. The switch shows `Loading…` (never the previous seat's numbers) until then. Still
not instant; a per-token last-good map (F28) would make a switch *back* instant.

### F25 — the hero SERVICES box's worst case (33 cells) versus its share of the pin
`verifier ● publisher ● deployer ?` is 33 cells; at 141 columns six boxes leave ~19 content cells each. Verify how the
worst case composites at the pin (clipped with `…` is acceptable; a silent overflow is not) and pin it with a test.

### F26 — `swarm_seat_selected`'s key-list comment does not name the optional `unseen_token` — CLOSED BY REMOVAL 2026-09-21 (`/seats` WP5, `57f429e`: `unseen_token` retired, decision D1)
`data/surf_models.py`: the comment says `{token_id, agent_id, selected_by}`; since 4e4bc30 the `most_active` fallback
also carries `unseen_token` when a saved seat is off the roster. Comment-only, but the file is a Tier 2 trigger — fold
it into the next change that owns `surf_models.py`.

## F27 — F38 — filed at the close of the `/seats` programme (2026-09-21)

Sources: the task reviews of WP0–WP6, the final whole-branch review and the controller's checks; spec
`docs/surf_agent_seats_spec.md`, plan `docs/surf_agent_seats_plan.md`. Minor unless stated; the Follow-ups rule
applies (Tier 0 when its file is next touched).

### F27 — SEAT RECORD's pending row clips silently at a four-digit `submitted` — RESOLVED 2026-09-22

SEAT's rewrite gives feedback statuses separate rows, so submitted and queued no longer compete
for the same fixed-width line. The original combined-line failure is retained below for context.

`widgets/surf/swarm_seat_verdicts.py`: `N submitted · M queued` is one line under `max-width: 46`; at
`9,000 submitted · 999 queued` it is CSS-clipped (`… que…`) at every width, and SEAT RECORD has no widen marker.
Pending is a draining backlog (largest seen: 13 on #0), so not reachable today. Fix as REVIEWED was (WP6 fix round):
bound the width by design, e.g. one status per line or a compact count.

### F28 — one seat slot: switching back after a failed read shows `unavailable` — OPEN

*2026-09-22:* the seat-details rewrite leaves `SLOT_SWARM_SEAT` and its TTL unchanged; no
per-token history is added, so this observation remains open.

`SLOT_SWARM_SEAT` holds one token's read. A → B → (B fails) → A shows `unavailable`/`Loading…` for A, not A's older
numbers. Correct (never another seat's numbers) but lossy. A bounded per-token map is the fix if the owner wants it
(plan §9 B).

### F29 — the ROSTER title's "last 100 jobs" may understate — CLOSED BY REMOVAL 2026-09-22

ROSTER and `swarm_roster_window` are retired. The internal roster fold still selects the most
active default seat, but emits no table or misleading window title. Original observation:

The roster also folds the 48 h jobs-seen map (`SLOT_SWARM_JOBS_SEEN`), so its rows can cover more than the `/jobs`
window the title names. Owner call: fold the roster from the window only, or title it `jobs seen since HH:MM`
(plan §9 E). Related capture note: `jobs_window_100.json` spans 02:26–05:44 UTC but was read at ~12:46 UTC, identical
to a read 6 minutes earlier — either no jobs for ~7 h or the route lags.

### F30 — "never paired" without `#N` in SEAT RECORD, RECORD and FEEDBACK — SEAT RESOLVED; RESIDUAL F39

*2026-09-22:* SEAT receives `swarm_seat_selected` and names `#N never paired`. FEEDBACK is removed.
RECORD remains tokenless, as does the replacement BY NODE; that open contract gap is F39.
Original observation:

Their signatures carry no `swarm_seat_selected`, so they render the bare words; the hero names the seat
(`IDMD #N` / `never paired` — the one-line `#N never paired` is 19 cells and the box holds ~16). Adding the token means a
signature change in `surf_models.py` (Tier 2 trigger).

### F31 — the owner cell links by the package `EXPLORER`, `rules/surf.md` says per-row `chain_id`
Owner decision Q-C (2026-09-21): follow the spec (`EXPLORER` = Ethereum; `chainId` is 1 on every captured seat). If a
seat ever carries another `chainId`, link by it and add `chain_id` to the summary.

### F32 — the A1 2×2 agent-grid argument is stale — SUPERSEDED 2026-09-22

The seat-details layout replaces that grid with SEAT beside BY NODE over RECORD; current rules
no longer claim the old A1 arithmetic as its justification. Original historical observation:

`docs/decisions.md` (2026-09-21) rejected A1 on 59 + 92 tight cells; RECORD's tight tier is now 52 (+4 = 56), so the
sum is 115 and the arithmetic no longer rules A1 out. Not re-measured; the `#:` block and `minimal.tcss` comment say so.

### F33 — test gaps (test-rigor only)

*2026-09-22:* the ROSTER `TITLE` item is closed by removal of the widget. The original list is
retained; it does not imply the other gaps have been verified or resolved in this programme.

- a single role wider than `VALUE_COLS` renders only `+1 more` (no role word); untested (`swarm_seat_verdicts._fit_roles`);
- `_runtime`'s partial case (only `id` or only `version`) is untested (`data/surf_swarm.py`);
- no test proves repeated `update_data` does not compound ROSTER's instance `TITLE` (code is correct:
  `type(self).TITLE`);
- no single test names "non-`unknown_seat` 404 on host 1, then a transport error on host 2" (verified by script);
- `_VERDICT_FIELDS` in `tests/data/test_surf_swarm_fixtures.py` still pins verdict sub-fields (`failedChecks`,
  `verifierVersion`) that no fold reads since WP5 — over-pins the corpus shape;
- the never-paired screen composite matches `never paired` as a substring.

### F34 — "no seat selected" does not say why

*2026-09-22:* still open. ROSTER is removed, so its former explanation is no longer displayed;
the default selection still depends on the internal job-data fold. Original observation:

With no roster and no saved seat the hero shows `no seat selected` whether the roster is empty or the sweep failed;
ROSTER says which. Spec §4 does not define the case (state `None`).

### F35 — the seat slot adds ~95 KB to `surf_cache.json`
Measured on #0: 354 B → 95,735 B, written only when the payload changed (below `SLOT_SWARM_SCORES`' 188 KB). Joins F7
if the write cost is ever measured as a problem.

### F36 — `data/surf_swarm.py` imports `surf_swarm_client` for `UNKNOWN_SEAT`
The pure fold now pulls `httpx` in transitively. Allowed (`data/` may import `httpx`; docstring corrected in WP5), but
moving `UNKNOWN_SEAT` into `surf_models.py` would keep the fold client-free — relevant to the data-layer-as-a-library
plan.

### F37 — plan defects recorded for the record
Plan §1.1 said `runtime` is `None` for an empty list (a false degradation; fixed in WP5 to `""` → `none`);
`/seats` serves `tokenId`/`agentId` as decimal strings (spec/plan were silent; `parse_seat_token` is strict ASCII);
`test_dashboard_screen.py -k surf` selects nothing; §3's `block_number` and `_NEXT` gates cannot reach 0 as written
(launch/site rows, curator's `SEL_REQUIRED_NEXT`); WP0's named set omitted the manager test it turned red until WP2.

### F38 — runtime wording is the source's raw text

*2026-09-22:* the panel is now titled SEAT; runtime wording remains the source's raw text.

SEAT RECORD shows `claude 2.1.278 (Claude Code)` / `codex codex-cli 0.149.0` — `"<id> <version>"` as served, clipped.
Prettifying is an owner call, not a parser of vendor strings (plan §9 D).


## F39 — F45 — seat-details programme (2026-09-22)

### F39 — RECORD and BY NODE cannot name the never-paired token — OPEN

The approved `SurfSwarmSeatRecord` and `SurfSwarmSeatNodes` signatures do not include
`swarm_seat_selected`. They render `never paired` without `#N`, while SEAT and the hero identify
the token. This is F30's remaining RECORD case plus the replacement panel's same limitation.
Adding the selected-seat value to both signatures is a contract change (Tier 2), not a display-only
fix. The handover's request to close all of F30 overstates what its specified signatures permit.

### F40 — seat-details handover defects and resolved process deviations

`docs/surf_agent_seat_details_handover.md` is the approved target, but these details required
explicit corrections under its CLAUDE.md precedence rule:

- Its per-package green requirement conflicts with its staged removal of contract keys and
  widgets: WP1–WP3 leave consumers awaiting later work. Transitional failures are recorded in
  the package commits rather than represented as passing checks. WP1 temporarily retained
  `SWARM_ROSTER_WINDOW_FIELDS` so the old fold could import; WP2 removed the constant together
  with its last import and consumer.
- WP4 asks a markup-bearing node key to render literally, while the established shared
  `sanitize_cell` path flattens, strips bracket-tag runs, clips, then escapes. The implementation
  follows that shared sanitisation contract; escaped residual brackets cannot become markup.
- §5 says all three AGENT layout constants already live in `screens/surf.py`, but
  `RECORD_NEVER_CLEARS_BELOW` actually lived in the layout test. It is moved to the screen with
  its measurement block so the test imports the same named production pin.
- WP5's blanket F30 closure is only supported for SEAT. The remaining contract gap is F39.

### F41 — missing `work` list still displays a real-empty RECORD — OPEN

When a valid seat payload lacks a `work` list, the existing manager path still publishes
`swarm_seat_work_rows == []`, because `seat_work_rows` folds absent and empty input alike.
RECORD can therefore show its real-empty message for data that was not supplied. This predates
seat-details. New node rows preserve `None` when either the reviews or work list is unavailable;
the analogous RECORD fix remains separate. The manager should preserve a missing/invalid list
as `None` and reserve `[]` for a successfully supplied empty list, with a regression test for both.

### F42 — RECORD preserves source order when acceptance times are out of sequence — OPEN

An actual CLI capture for seat #420 on **2026-09-22 at approximately 00:31 Europe/Berlin**
showed RECORD's first timestamps as `09-21 23:35`, `09-21 23:29`, `09-21 23:26`, then
`09-21 23:32`. Evidence: `/tmp/surf-seat-details-live/seat-420-134x32.png`. This came from the
running application's live read, not a test or a new committed fixture. It demonstrates that
`work[]` source order is not reliably descending by `acceptedAt`; earlier capture descriptions
remain observations of their stated dates.

The existing `seat_work_rows` fold preserves source order. The seat-details specification extends
the row fields but does not explicitly require a sorting change. If the owner wants canonical
chronology, sort by parsed `accepted_ts` newest first, placing unknown timestamps last, and add a
regression test with out-of-order and missing timestamps.


### F43 — AGENT's status-bar width depends on the version and theme label — OPEN

*Amended fix wave, 2026-09-22:* the shortened hint moves the status edge to **134**. Complete
composited-label assertions remain; the four larger bodies are now bound by their own content.
The version/theme dependency and pool4 narrow-status limitation remain open. F46 is closed by
the measured 32-row AGENT layout. Earlier measurements:

*BOARD update, 2026-09-22:* current whole-bar width is **142** after adding `b board`. WP4
strengthened the test to compare the complete expected right-label text with composited output:
region bounds alone missed the final `f` of `surf` clipped at 141. That test gap is fixed; the
version/theme label dependency remains open. AGENT's new body height is tracked by F46.

Before the §9 fix wave, the AGENT full-layout column pin was **131**, bound by
`STATUS_BAR_WHOLE_FROM`; the body itself cleared at **117/118**. The status bar includes
version and theme labels, so a version bump or theme rename can move that threshold without
changing any panel. These are the earlier measurements; the fix wave's rendered-width changes
required a fresh final measurement. The completed sweep (handover §10, `999317f`) keeps
the pin at **131 × 32**, with the body now whole from **130**; the label dependency remains.

Retain the composited status-bar coverage when updating those labels and re-measure the affected
pin. A layout guarantee tied to label length remains a follow-up; this fix wave does not redesign
the status bar.

### F44 — the 64-hex `submissionHash` check is written twice — CLOSED 2026-09-22 (BOARD WP2)

Closed by `47d2247`: one `_hex64` helper validates both consumers. Regression:
`tests/data/test_surf_swarm_seats.py::test_work_and_review_dedup_share_one_hex64_validator`.
Original finding:

`data/surf_swarm.py` `_distinct_reviews` (~l.762) re-states the 64-hex validation that
`seat_work_rows` (~l.842) already applies. Hoist one `_hex64` helper in the same module and use it
in both; Tier 0 the next time the file is touched.

### F45 — the duplicated-review capture has no permanent layout case — CLOSED 2026-09-22 (BOARD WP0)

The AGENT `#:` blocks say `seat_420_duplicated_reviews` was swept, but `PAYLOADS` in
`tests/screens/test_surf_swarm_layout.py` (~l.352) lists only capture, capture420 and the two worst
payloads. The worst-a payload covers the `entries served` line, so this is test rigor only: add the
capture to `PAYLOADS` when the layout test is next touched.

Closed: `duplicates420` now participates in permanent width/height boundaries and pin assertions.

## F46 — AGENT's new source groups require more than the accepted 32 rows — CLOSED 2026-09-22 (§11)

Closed by the amended fix wave: AGENT measures **138 × 32** on ordinary v3 and five-digit
stress. Removing the two worker metadata rows, merging paired time into identity, and merging
queued feedback into the feedback line leaves eleven detail lines plus title/blank: a 13-row
SEAT top floor. Contributor facts retain two lines at the pin and collapse only when they fit.
The original §9 trial stopped correctly at 33; §11 authorized the additional fact-preserving
merges. The owner's 138×31 terminal still needs scrolling, within the accepted 32-row choice.
Canonical measurements and boundary tests live beside the screen pins. Original finding:

BOARD's WP5 adds four fixed SEAT rows: two source-labelled contributor lines, worker metadata,
and its source clock. The measured AGENT minimum is now **36 rows**; at 35 the body still scrolls
and `‹ taller` remains visible. The owner's 119×35 and 138×31 terminals therefore need vertical
scrolling. Current canonical measurements remain beside `SURF_AGENT_FULL_LAYOUT_ROWS` in
`screens/surf.py`.

F16's AGENT closure records the owner's acceptance of the previous **32-row** seat-details
layout on 2026-09-22. It does not imply acceptance of the new 36-row requirement. The new facts
and their source separation were requested; no field was silently removed to preserve the old
height. The owner can accept this height or request a separate layout change to recover rows.
SWARM's existing 42-row height remains F16's open half.

## F47 — live SWARM's extra states row exceeds its fixture height — OPEN (F23)

The required real CLI render on **2026-09-22 around 06:35 Europe/Berlin**, with a fresh isolated
HOME at **142×42**, showed `‹ taller` and a THROUGHPUT scrollbar; bottom `cancel reasons`
content was not fully visible. Evidence: `/tmp/board-final-live/s-420-142x42.svg` and `.png`.
The scoped review identified the extra **`states` row** as the cause: this is F23's
content-dependent THROUGHPUT height. The visible accumulation message was not the cause of the
overflow. BOARD at 142×23 and AGENT at 142×36 fit their body heights during that historical check.

The fixture sweeps do not establish the same height guarantee for the extra-states-row payload.
THROUGHPUT production code remains unchanged by BOARD and this fix wave. Follow up under
[F23](#f23--throughputs-statecancel-blocks-are-unbounded-in-rows): add the extra-states-row canned regression
and measure its height before choosing a remedy. No new pin is inferred from the screenshot.
M6 in the amended wave corrects this attribution only; F47/F23 remain open.

## F48 — AGENT STATUS cannot tell unknown pause state from known not-paused — CLOSED 2026-09-22 (polish WP5)

Resolved through the public `swarm_seat_live.live_state` contract, populated by the shared
worker-state fold and consumed by AGENT STATUS. Missing pause evidence stays unavailable;
a known idle worker remains distinct. `d77b7d4` records the actual fold-to-widget test
`test_polish_unknown_pause_fold_reaches_unavailable_not_idle` and a killed/restored mutation
that falsely falls back to idle. The original finding follows for history.

Filed by the BOARD fix-wave re-review, 2026-09-22. `widgets/surf/swarm_agent_hero.py:197-203` reads
`swarm_seat_live` through `SWARM_SEAT_LIVE_FIELDS`, which does not carry `pause_known`. #420 with
`paused` popped renders `working 0 of 1` like a seat known not to be paused, while BOARD's
LEADERBOARD shows `unavailable` for the same seat. Fix needs a contract key (Tier 2).

## F49 — a malformed-but-tokened contributor seat is counted in SEATS but has no LEADERBOARD row — OPEN (Minor)

Filed by the BOARD fix-wave re-review, 2026-09-22. `data/surf_swarm.py:1238-1239` leaves such a seat
out of `swarm_board_rows` (99 seats vs 98 rows) with no row saying it is unavailable. The README
discloses "every fully parsed contributor seat"; an explicit unavailable row would be more honest.

## F50 — AGENT/SWARM below-pin layout branch is vacuous under 134 columns — CLOSED 2026-09-22 (polish WP3)

Resolved in `54e7ffa`: below-pin tests require degradation of the body independently of the
status bar, and exclude the named content exceptions' hidden columns from that evidence.
Deliberately injected false whole-body results with a cropped status fail for both AGENT and
SWARM; exact inverse restoration and the named tests pass. Original finding follows.

Filed by the BOARD fix-wave re-review, 2026-09-22. `tests/screens/test_surf_swarm_layout.py:528`
`assert not r["status_whole"] or …` is always true where the status bar is cropped (< 134) — the
M2 shape. `test_the_column_pin_is_not_loose` still covers pin−1. Do as Tier 0 when the file is next touched.

## F51 — workflows have no free SWARM layout slot — OPEN (owner design decision)

Polish handover §1.3 explicitly defers `/workflows`. The read-only shared reference
`/Library/Vibes/aidude/docs/imd-api-changelog.md` (2026-09-22) describes contractsJobId and
frontendJobId joining two-stage launches, with status and failure. SWARM already exceeds the
owner's heights (F16); decide placement before adding another panel. No workflow fetch is added
in this branch.

## F52 — per-job submissions expose co-working candidates — OPEN (future TEAMMATES data)

Polish WP0 captures `/jobs/{id}/submissions`, which lists every attempting seat for a known job.
This supersedes the older inference that panel membership is unavailable because `nodes[]`
contains only one seat. A future TEAMMATES change can use the submission identities, with explicit
scope for known jobs and attempted versus accepted work. This branch extracts only the selected
seat's exact submission hash; it adds no co-working aggregate.

## F53 — a seat's rejected attempts lack complete job discovery — OPEN (source coverage)

The captured submissions contain oracle outcomes, including rejected attempts, but the seat's
work list supplies accepted jobs. Rejected attempts inside jobs not otherwise known cannot be
found from this path. A full per-seat rejected-attempt record therefore needs a discovery source;
never claim the currently known jobs are the seat's complete rejected history. Deferred by polish
handover §1.3.

## F54 — approved SEAT grouping requires 37 rows — OPEN (polish budget skip)

The exact polish §2.3 grouping was rendered at 138 columns with its separate pairing/model
rows, two group gaps and CONTRIBUTORS header plus two fact rows. The measured SEAT panel is
18 rows; RECORD needs eight and surrounding chrome eleven, so the minimum is **138×37**.
At 34 and 36 rows the body scrolls and RECORD is not wholly visible. The WP0 v4 seat #420/workers
with independent contributor data, and five-digit counters, were whole at 37. This exceeds the owner's accepted ≈34 rows.

Per polish §4, the SEAT restructure was skipped, including its advertised-model row and
retirement of the responsive contributor join. Existing SEAT content/layout remains; its
AGENT body pin is unchanged at 138×32. FLEET's advertised model mix and the new data fields
proceed independently. No facts or approved group gaps were silently removed to lower the pin.
Owner decision in polish §7: SEAT stays as it is; F54 remains open. The produced
`swarm_seat_live.advertised_model` and `advertised_effort` fields are intentionally unrendered
until this grouping is reconsidered (M5). FLEET's advertised model mix is rendered separately.

Measurement harness: `/tmp/test_polish_seat_budget.py`; SVGs and region/scroll JSON in
`/tmp/polish-wp3-seat-budget-v4/`. These are local review artifacts, not shipped runtime files.

## F55 — mixed service states clip at the SWARM column pin — OPEN (pre-existing layout)

WP5 measured the existing SERVICES box at 141×42: 23 outer columns and 19 content cells.
The mixed-state line (`verifier` down, `publisher` up, `deployer` unknown) already rendered
as `verifier ● publish…` before the polish changes. The all-up summary fits.

Polish adds explicit up/down/unreported words so state does not depend on colour, and places
`/health.status` on the available second body line. The example grows from 33 to 46 cells; the
container width and height remain unchanged. It does not redesign the clipped mixed-state
layout or raise SWARM's 141×42 pin. A later service layout change must preserve all service
names/states and health status within the budget, with an actual at-pin mixed-state composite.
At 141×42 the corrected mixed line renders `verifier down publ…`, while `health unavailable`
is whole. Baseline evidence: `/tmp/polish-wp5-services-baseline.log`; corrected measurement:
`/tmp/polish-wp5-services-words-measure.log`.

F55 adjacent measurements: the 46-cell mixed line clips at 301 terminal columns (45 content
cells) and is whole at 302 (46). The 60-cell all-unreported line clips at 385 and is whole at 386.
These are content onsets, not adopted layout pins. Evidence:
`/tmp/polish-wp5-services-width-boundary.log`.

## F56 — answer cleaning cosmetically changes markup-like text — OPEN (Minor)

Polish §7 M6 files cosmetic transformations such as `[/x]` → `[x]`. Safety cleaning and
widget sanitization protect rendering, but the intermediate text can differ cosmetically
from the supplied summary. Defer this cosmetic work until the function is next touched;
it is outside the one fix wave. Preserve path/link privacy, idempotence and bounded work
when addressing it, and distinguish literal text from actual Markdown syntax.

## F57 — F60 — polish fix-wave scoped re-review Minors (2026-09-22, Approved)

The scoped re-review of `5d1b1ed..503297b` verdicted I1–I4 and M1–M3 ADDRESSED. It filed these
four Minors in `answer_sentence` / `_safe_stored_answer` (`maxpane_dashboard/data/surf_swarm.py`). Do them
as Tier 0 when the function is next touched, together with F56. Keep idempotence, bounded linear
work and the stored-safety predicate in step with the cleaner.

- **F57 — a bare home directory swallows the prose after it.** The user-name pattern takes the
  words that follow the path and stops only at and/or/but/then. `Wrote /home/bob; done` →
  `Wrote ~`, `cd /Users/jane && ls` → `cd ~`, `Saved to /home/bob as requested.` → `Saved to ~.`
  Text is lost but nothing leaks.
- **F58 — UNC paths are not detected.** `\\server\Users\bob\a.json` passes through unchanged and
  exposes `bob`, and the stored-safety predicate accepts it. Privacy gap.
- **F59 — a non-breaking space or tab inside a user name leaks the surname.** `_HOME_USER`
  allows only `[ ]+`, so `/Users/Jane Doe/work/a.json` → `~ Doe/work/a.json`. Privacy gap.
- **F60 — bidi format characters pass.** Only C0/C1 controls are stripped, so `x‮y` is
  accepted and `sanitize_cell` hands it to the RECORD cell unchanged (Unicode category Cf).
