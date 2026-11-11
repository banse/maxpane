# swarm body branch — follow-ups

Findings raised during `feature/surf-swarm-body` (docs `docs/imd_swarm_api.md`,
`docs/superpowers/specs/2026-09-16-surf-swarm-view-design.md`) and deliberately **not** fixed on
the branch, per CLAUDE.md's "report defects, do not fix them" rule and the review discipline that
a scoped re-review files what it finds outside its own target rather than repairing it. The
branch's working notes (`task-*-review.md`, `task-*-re-review*.md` under
`.superpowers/sdd/2026-09-16-surf-swarm-body/`) live in a git-ignored workspace that is deleted
when this plan finishes, so this file is the only place these survive.

## Status — all ten resolved, 2026-09-17; F13 and F14 closed by removal, 2026-09-21; F16–F25 filed 2026-09-21 (F16 AGENT closed; SWARM remains an owner decision); F20 closed, F26 closed by removal, F24 reworded and F27–F38 filed 2026-09-21 by the `/seats` programme; F16 (SWARM half), F23, F47, F51 and F54 resolved and F73–F85 filed 2026-10-04 by `feature/surf-swarm-workflows`; F86–F87 filed 2026-10-05 by the WP2 review; layout v3 closes F55/F60/F73, resolves F84 except SKILLS, and parks IN FLIGHT 2026-10-05; F88–F97 filed 2026-10-06 by the layout v3 final review (F97 corrected with I1); F98–F99 filed 2026-10-06 by the I1 scoped re-review (parked by the owner)

Swarm v2 (WP7, `docs/surf_swarm_v2_implementation_plan.md`) deleted `swarm_queue.py` and retired
`swarm_queue_depths` with the other seven v1 keys, so F13 (the `depths or None` conflation behind
QUEUE's PENDING block) and F14 (a markup-only counter name rendering as `-- 3`) have no code left
to fix: closed by removal, not by a fix. The v2 hero's QUEUE box read `swarm_queue_total` (both retired by layout v3), which was
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

### F16 — row pins exceed the owner's terminals — AGENT CLOSED; SWARM RESOLVED 2026-10-04

*2026-10-04:* **SWARM resolved, by the owner's choice of 2026-10-03:** "collapse THROUGHPUT's state and
cancel-reason blocks behind a key". `x` folds them, and SWARM opens folded (`feature/surf-swarm-workflows`, `274e14f`).
SWARM's pin went from 141×42 to **138×35**. LAUNCHES binds the width and THROUGHPUT's nine collapsed
lines set the row floor. The final review's I1 (a horizontal scrollbar in LAUNCHES at 138×35) was
fixed in `d583e73`. The owner's 119×35 terminal now has the pin's height but is 19 columns
narrower than it. The 138×31 terminal has the pin's width but is four rows short, with `‹ taller` lit. Expanded, the body clears
`‹ taller` from 55 rows (73 on F47's extra states); see F73.

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

### F23 — THROUGHPUT's state/cancel blocks are unbounded in rows — CLOSED 2026-10-04

*2026-10-04:* closed by the fold (`274e14f`). The pinned height is the collapsed one, so the fold
decides it, not the vocabulary. Expanded stays unbounded, but expanding is the reader's choice and
the top row advertises the cost with `‹ taller`.
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

## F47 — live SWARM's extra states row exceeds its fixture height — CLOSED 2026-10-04 (F23)

*2026-10-04:* the extra-states payload is now one of the four SWARM layout payloads. Collapsed, it
costs the pin nothing (whole from 35 rows). Expanded, it clears `‹ taller` from 73 rows
(`EXPANDED_THROUGHPUT_CLEARS_AT` in `tests/screens/test_surf_swarm_layout.py`).

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

## F51 — workflows have no free SWARM layout slot — RESOLVED 2026-10-04

*2026-10-04:* the owner's decision of 2026-10-03 was to hide CAPABILITY and show workflows in its
place, parking CAPABILITY for a later SKILLS board. WORKFLOWS (`widgets/surf/swarm_workflows.py`)
reads `GET /workflows?limit=12` on the swarm scores tier (`9bcd8f4`, `6d0342a`, `032e6e7`,
`274e14f`). CAPABILITY is mounted on no body. Its contract lives on in
`data/surf_models.SWARM_PARKED_WIDGET_SIGNATURES`.

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

## F54 — approved SEAT grouping requires 37 rows — RESOLVED 2026-10-04 (differently)

*2026-10-04:* the owner chose a different route on 2026-10-03: "replace the content of the SCORE
card with LLM model info". AGENT's SCORE card became **MODEL** (`ef62eb5`). It shows the seat's
advertised model and effort pairs from `/seats` `runtimes[].premiumModel` (`swarm_seat_summary`
`models`), in the same 20fr slot. The AGENT pin held at 139×25. The 37-row SEAT grouping below is
withdrawn, not built.

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

## F55 — mixed service states clip at the SWARM column pin — CLOSED BY REMOVAL 2026-10-05

Layout v3 removes SERVICES from the hero. Breaker, service and health alarms move to the title,
with compact count/labels approved by the owner; the former mixed-state card no longer exists.

*2026-10-04:* the SWARM pin this entry measures against moved from 141×42 to 138×35
(`feature/surf-swarm-workflows`). The mixed-state line was not re-measured at the new pin. The figures below are the
141×42 ones.

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
- **F60 — bidi format characters pass. CLOSED 2026-10-05 (`ea7c33f`).**
  Shared control cleaning now strips U+202A–U+202E and U+2066–U+2069, preserving ZWJ and other Cf.
  The exact-category regression kills removal of the bidi ranges. Historical finding: Only C0/C1 controls are stripped, so `x‮y` is
  accepted and `sanitize_cell` hands it to the RECORD cell unchanged (Unicode category Cf).

## F61 — F62 — AGENT card batch review Minors (2026-09-23)

- **F61 — OTHERS sums `accepted`/`onchain` leniently.** `swarm_node_cards._others_body` drops a
  row whose value is `None` from the sum, so it would be counted as 0. Today this cannot happen,
  because `seat_node_rows` starts both fields at int 0. If that ever changes, make the sum strict,
  the same way `attempts` is handled (any `None` → no total). Minor, test-rigor only.
- **F62 — a transient ENS outage is recorded as a 1 h miss.** `ens.resolve_names` cannot tell "no
  name" from "could not look", so `SurfManager._resolve_seat_owner` records both as a miss. While
  that miss is held, OWNER shows the address, never a guessed name. Minor, cosmetic.

## F63 — AGENT owner batch residual (2026-09-23)

- **F63 — CLOSED in the same change.** OTHERS sums every node key the named cards do not
  (the committed `seat_0` serves `deploy_script` and `manifest`), and a five-digit sum cut to
  `99,9…` below 145. Fixed before commit: a node card's counts step down to `fmt_compact`
  (`5.0K of 50.0K`), then whole thousands (`5K of 50K`), whenever the fuller form does not fit, and the stress payload keeps a
  five-digit OTHERS. Kept here only so the number is not reused.

## F64 — F65 — AGENT owner batch review Minors (2026-09-23)

- **F64 — CLOSED 2026-09-23 (`docs/decisions.md`).** Was: **CONTRIBUTORS floors its hours.** `swarm_fleet.py` writes `wall_clock_ms // 3,600,000`,
  so 59 minutes reads `0 h` and 5.9 h reads `5 h`. Round, or give a sub-hour form.
- **F65 — CLOSED 2026-09-23 (`docs/decisions.md`).** Was: **a failed RECORD row paints an unreadable answer red.** `swarm_seat_record.py` repaints
  the whole answer cell red on `failed`, so a yellow `unavailable` (could not read) takes the
  failed colour; the unread states could keep their own style.
- **F66 — CLOSED 2026-09-23 (`docs/decisions.md`).** Was: **whole-thousands node counts can read equal or overflow the unit.** `swarm_node_cards._whole`
  rounds 4,600 of 5,400 to `5K of 5K` (the rate line below stays true) and 999,600 to `1000K`
  rather than `1M`. Reached only below the AGENT pin (127-128 and 130 on the stress payload).

## F67 — SITES owner batch residual (2026-09-23)

- **F67 — CLOSED 2026-09-23 (`docs/decisions.md`).** Was: **SITES' label column is wider than anything it can now show.** `_LABEL_CELL_COLS` (29)
  was sized for `<label> → <label>`; superseded rows no longer show, so the widest label is the
  13-cell `site-7018907b`. Narrowing it frees 16 cells for the other columns but moves the SWARM
  body's width tiers (`_S_THRESHOLDS`), so it waits for the owner.
- **F68 — CLOSED 2026-09-23 (`docs/decisions.md`).** Was: **an all-hidden SITES list reads `No data`.** When `/sites` returns rows but every one is
  superseded or nameless, the panel cannot be told from an empty feed; "no live site" would be
  exact. Owner's call on the wording.
- **F69 — CLOSED 2026-09-23 (`docs/decisions.md`).** Was: **`swarm_site_rows` still carries `superseded_by` and `failure`.** Neither renders any more
  (only the SITES filter reads `superseded_by`); prune with the contract if it is next touched.

## F70 — follow-ups batch residual (2026-09-23)

- **F70 — the node cards' middle form is the shared `fmt_compact`, which prints `1000.0K` for
  999,960 and `500.0` for 500.** A card reaches it only when `fmt_int` does not fit, so the pair
  `500 of 50,011` can read `500.0 of 50.0K` below the AGENT pin. Fixing it touches the shared
  `widgets/sparkline_common.fmt_compact` (Tier 2) or adds a node-card-local form. Minor.
- **F71 — `_whole` carries K into M only.** `swarm_node_cards._whole(999_999_999)` reads `1000M`
  (review 2026-09-23, probed); the same class as F66 one unit up. Nothing realistic reaches it.
  Minor; do it with F70.
- **F72 — SITES' two empty words sit in different columns.** `No current site` (15 cells) no
  longer fits the 13-cell label column since F67, so `_degraded_row` lays it under `ens`, while
  `No data` stays under `label`. The documented base rule, cosmetic only. Minor.

## F73 — F85 — filed at the close of the SWARM WORKFLOWS programme (`feature/surf-swarm-workflows`, 2026-10-04)

Sources: the WP1–WP5 task reviews, the final whole-branch review (opus), the scoped re-review of
`d583e73`, and the controller's own checks. The spec is `docs/surf_swarm_workflows_spec.md`. Each
item is Minor unless it says otherwise. The Follow-ups rule applies: do it as Tier 0 when its file is
next touched, never as its own branch, except where an item is an owner decision.

- **F73 — at the 138×35 pin, `x` reveals nothing without scrolling. CLOSED 2026-10-05 (`46e8f82`).**
  `x` now opens a cached throughput popup; no inline fold remains. The owner approved the live
  200×48 layout before WP5. Historical finding: Pressing `x`
  flips the title to `x less` and lights `‹ taller`, and the top row gains a scroll nub. No states
  or cancel-reasons line becomes visible until that row is scrolled (final review M3). The spec
  allows this: expanded clears `‹ taller` from 55 rows, or 73 on F47's extra states. But on the
  owner's terminals `x` looks like it does almost nothing. Options:
  - accept it as is;
  - let the expanded top row's floor grow, at the table rows' expense;
  - show the blocks in a popup instead of inline.
- **F74 — the upgrade rule is dead code at today's start-up.** `SurfManager._upgrade_swarm_scores_slot`
  makes `TIER_SWARM_SCORES` due when the persisted sweep slot has no `"workflows"` key. Tier clocks are
  not persisted, so on a cold start the tier is due anyway (WP2 review). This is a spec-premise
  defect, recorded under the spec's §2 "Upgrade". Keep the rule, or drop it with its test.
  **CLOSED 2026-10-05** (commit: `docs(surf): clarify the deliberate scores upgrade rule`).
  Kept deliberately for future persisted tier clocks; load currently restores none,
  and no production path warms scores before the check. Existing warm-cache tests retained.
- **F75 — `_swarm_scores_keys` gates skills, launches and sites on `is not None`.** A hand-edited
  non-list for any of them publishes `[]`, a real negative, instead of `None` (pre-existing; WP2
  review). Workflows gate on `isinstance(…, list)`; do the same for the other three.
  **CLOSED 2026-10-05** (commit: `fix(surf): reject non-list persisted score routes`).
  Skills, launches and sites now require lists; persisted dictionaries publish None,
  while empty lists survive. The reverted skills gate is KILLED.
- **F76 — IN FLIGHT's prose cells give an embedded 0x address no copy icon. IMPORTANT.** This breaks
  CLAUDE.md's address convention (pre-existing; WP4 review). The E2/E7 sweep misses it only because
  no seeded IN FLIGHT objective or note carries an address. Fix: route the cells through
  `widgets/surf/_icons.py` with `explorer=None`, as WORKFLOWS' text cell does (`032e6e7`), and seed
  the sweep.
  **CLOSED 2026-10-05** (commit: `fix(surf): add copy icons to in-flight prose`).
  Shared fitted prose now keeps whole copyable, unlinked address units; live 200×48
  shown, 779 scoped tests pass and both widget/sweep tests kill the old-cell mutant.
  **IN FLIGHT parked 2026-10-05; applies when it returns.**

- **F77 — WORKFLOWS: no committed test combines a red failure with an embedded address** (WP4
  re-review). Add one case that composites the failure's colour and the icon together.
  **CLOSED 2026-10-05** (commit: `test(surf): cover red failures with embedded addresses`).
  One composited case checks red failure/address cells together with the copy icon
  and absence of an explorer link.
- **F78 — WORKFLOWS: the 20-cell text-column floor has no test.** The final review changed
  `max(TEXT_MIN_COLS, spare)` to `spare` in `swarm_workflows.py`, and
  `tests/widgets/test_surf_swarm_workflows.py` stayed green. The floor matters only under
  `TIGHT_WIDTH` (about 92 terminal columns on SWARM).
  **CLOSED 2026-10-05** (commit: `test(surf): pin the workflow text column floor`).
  Below the tight budget, the installed column stays 20 cells and its composited
  text ends in an ellipsis. Replacing the minimum with spare is KILLED.
- **F79 — WORKFLOWS: an entry with no usable field folds to an all-`None` row.** `workflow_rows` keeps
  one row per mapping, so a persisted mapping with garbage values becomes a row of `None`s. No test
  pins how WORKFLOWS paints it.
  **CLOSED 2026-10-05** (commit: `fix(surf): skip missing workflow statuses in footer counts`).
  The composited regression keeps the dash-only row and counts it in `newest N`,
  while the owner-approved footer fix skips missing statuses; restoring the dash bucket is KILLED.
- **F80 — LAUNCHES' `#` column cuts a four-digit launch number. IMPORTANT WHEN REACHABLE.** The
  worst-case payload's 1000 paints as `1,00`, cut by the `DataTable` with no ellipsis (pre-existing;
  WP5 review). That would be a wrong number on screen. It is latent: the capture's launches are
  numbered around 60. Widen the column, or switch to a compact form from 1,000, before launch
  numbers reach four digits.
  **CLOSED 2026-10-05** (commit: `fix(surf): render launch identifiers without grouping`).
  Identifiers use plain digits; overflow gets an ellipsis and widen marker.
  Live 200×48 shown; 130 scoped tests pass; restoring grouping is KILLED.
- **F81 — LAUNCHES: nothing binds the `tight` `repo` cell's fit to its 26-cell column** (re-review
  M1). Mutant G (`repo_cols = _REPO_COLS` at every tier) painted `Identity-md/launch-58-buil` at
  138×35, cut with no `…`, and every selected test stayed green. Add one widget test: at the `tight`
  tier the composited repo cell ends in `…` and is at most `_TIGHT_REPO_COLS` wide.
  **CLOSED 2026-10-05** (commit: `test(surf): cover the tight launch repository cell`).
  The composited tight-tier repo ends in an ellipsis within its 26-cell budget;
  forcing the full-tier formatter is KILLED.
- **F82 — SWARM's column sweep moved to 35 rows instead of adding 35** (re-review M2).
  `_S_COLUMN_SWEEP_HEIGHT` (35) replaced 80 for SWARM's column checks, so no test asserts the whole
  body at (138, 80) on every payload. The expanded half of the 35-row sweep never composites
  THROUGHPUT's blocks. No defect hides there today, because the 80-row detectors never saw those
  lines either. Add an 80-row pass, or record why the 35-row one suffices.
  **CLOSED 2026-10-05** (commit: `test(surf): cover swarm layouts at eighty rows`).
  All four payloads × both folds now run at the pinned width and 80 rows
  through the existing whole-body geometry checks.
- **F83 — a stale docstring in `tests/screens/test_surf_swarm_screen.py`** still names ROSTER, SEAT
  RECORD and FEEDBACK, panels SWARM no longer mounts (WP5 review).
  **CLOSED 2026-10-05** (commit: `docs(surf): describe the current agent screen composition`).
  The test module now names the agent hero, seat-card row, RECORD and its replacement filter.
- **F84 — owner decisions, resolved by layout v3 except SKILLS (2026-10-05).**
  - Pagination: done as persisted history in WORKFLOWS (`5d88ea6`), up to 1,000 rows.
    Only the newest 100 refresh each completed sweep; older changes wait for a later backfill.
  - Workflow detail popup: done (`46e8f82`), snapshot-only and scrollable.
  - Status-bar hint: `x more` replaces `l launchpad`; `l` stays bound (`46e8f82`).
  - Fold persistence: dropped by the owner; the inline fold no longer exists.
  - **SKILLS board remains OPEN.** CAPABILITY is still parked in `SWARM_PARKED_WIDGET_SIGNATURES`.
- **F85 — the sparklines outside `SparklinePanel` still draw a `None` series as an empty one.
  IMPORTANT.** These are fwa's, curator's and surf's market and pool4 sparklines. #34 fixed the
  shared base only (spec §4). Each remaining one is the same "failed read in the real negative's
  clothes" shape. Do them per dashboard, one regression case each on composited output.

  **F85 CLOSED 2026-10-05** for the prescribed FWA/curator/SURF widgets
  (`c7146ba`, `7deb9d6`, and commit `fix(surf): distinguish failed sparkline histories`).
  Missing/non-list histories now paint yellow unavailable, empty lists keep their
  existing sentences, and all five widget mutants are KILLED. Live 200×48 views shown;
  scoped runs: FWA 55, curator 668, SURF 538 passed. Upstream manager gaps and legacy
  Frenpet inventory findings are filed as handover #96–#99.

## F86 — F87 — WP2 review Minors (2026-10-05)

- **F86 — IN FLIGHT's docstring still says notes use strip-then-escape.**
  `widgets/surf/swarm_inflight.py:10` is stale: since `ad2e058`, notes go
  `strip_tags` → `fit_prose` → plain `Text`, the same literal contract as the other
  cells, and nothing is parsed as markup. **Minor, Tier 0 when the file is next touched.**
  **IN FLIGHT parked 2026-10-05; applies when it returns.**

- **F87 — IN FLIGHT marks addresses twice in its note branch.**
  `mark_addresses(clean_note)` runs inside `fit_prose` and again for `_note_clipped`.
  Both give the same result; `fit_prose` could return its cut flag. **Minor, Tier 0.**

  **IN FLIGHT parked 2026-10-05; applies when it returns.**

## F88 — F97 — SWARM layout v3 final review Minors (2026-10-06)

Final review of `feature/swarm-layout-v3` at `9c821fd`: **Needs fixes, 0 Critical / 1 Important**.
The one fix wave addresses I1 (WORKFLOWS' last-successful-read timestamp) and the explicitly
requested failure-path history cap from review Minor 4. The findings below are **Minor** and
filed without code changes; F97 records the spec correction required by I1.

- **F88 — reaching the page cap keeps backfill running.**
  `data/surf_swarm_client.py:329–355`: past 1,000 workflows, `workflows_complete` never becomes
  True, so every sweep re-reads ten pages. **Minor, open.**
- **F89 — partial history has no visible completeness warning.**
  A later-page failure stores the pages read without saying on screen that history is partial;
  the hero total can show, for example, 100. **Minor, open.**
- **F90 — unread health is reported before the first read and for a missing status key.**
  `screens/surf.py:2377`, `data/surf_swarm.py:120`: `⚠ health unavailable` appears on first paint
  before the SWARM read lands. A `/health` response without a status key makes it permanent.
  The owner approved the wording; this finding covers only cold start and the missing-key case.
  **Minor, open.**
- **F91 — compact title source counts engage earlier than necessary.**
  The compact `⚠ N src` title is chosen using the full width including alarms. Around 150–199
  columns with alarms lit, source names collapse even though they would fit. **Minor, open.**
- **F92 — summary fitting can skip a larger count in favor of a smaller one.**
  `widgets/surf/_swarm_summary.py:41–44`: `summary_body` skips a pair that does not fit but keeps
  trying later pairs. A smaller count can appear while a larger one is missing. The word
  tie-break is untested. **Minor, open.**
- **F93 — removed assertions leave coverage gaps.**
  WORKING's bold-green and dim `0 quiet` colors no longer have coverage (the mutant survived).
  MEDI-38, a malformed count showing unavailable, has no replacement. The silent-loss loop in
  `tests/screens/test_surf_swarm_layout.py` changed from `range` to `boundary_set` for AGENT too.
  **Minor, open.**
- **F94 — README still quotes the old status hint.**
  `README.md:558–559` still says `l launchpad · …`. **Minor, open.**
- **F95 — hero docstring and imports are stale.**
  `widgets/surf/swarm_hero.py:87` still names QUEUE · BREAKER · SERVICES; `flatten`,
  `sanitize_cell` and `clip` at :16/:18 are unused imports. **Minor, open.**
- **F96 — ENS width lost its agreement with the label and suffix.**
  `widgets/surf/swarm_sites.py:100` hand-types 33, formerly `_LABEL_COLS + len(_ENS_SUFFIX)`,
  with no agreement test. **Minor, open.**
- **F97 — A4's last-good sentence prescribed an insufficient shared clock.**
  `docs/codex_swarm_layout_v3_plan.md` A4 said retained workflow history uses the existing
  `as of` behavior, but the scores timestamp advances when sibling routes succeed.
  **Minor spec defect; corrected 2026-10-06 with I1.** A dated correction now requires
  WORKFLOWS' own successful-read timestamp and marker. This is part of the authorized I1 fix.

## F98 — F99 — I1 scoped re-review (2026-10-06, `090c378`; parked by the owner)

The scoped re-review verdicted I1 ADDRESSED. Its findings below are filed, not fixed, because the
branch's one fix wave was spent. The owner merged `090c378` and parked them for later.

- **F98 — the persisted `workflows_ts` is not range-checked.**
  `data/surf_manager.py:6318–6320` (carry-forward) and `:6430–6434` (publish) accept any finite
  non-bool number via `sw._optional_stamp`.
  - A hand-edited cache, or a clock step backwards, can store a future value. That publishes the
    sweep's own HH:MM over old rows (stale presented as live) and is carried forward on every
    failed sweep.
  - `0` and negatives publish invented times (`01:00`, `00:59`).
  - Precedent: `LastGood.from_dict` (`data/surf_cache.py:324–343`) refuses `ts <= 0` and
    `ts > now + CLOCK_SKEW_TOLERANCE_SECONDS`.
  - Fix (Tier 0): accept `workflows_ts` only when it is above 0 and no later than the slot
    entry's own `ts`. Add a regression case for a future, a zero and a negative stamp, and prove
    it with `scripts/mutate.py`.
  **Important, parked by the owner 2026-10-06.**
- **F99 — a slot saved before `090c378` shows its rows with no `as of`.**
  Main's and `9c821fd`'s slots carry `workflows` but no `workflows_ts`. Until a successful
  `/workflows` read sets one, WORKFLOWS lists the retained rows unmarked. That can last as long as
  the route stays dead; before layout v3 the same case showed unavailable. Self-heals on the
  first successful read. **Minor, open.**


## Production launches handoff — 2026-10-06

`feature/swarm-launches` implements `docs/codex_swarm_launches_plan.md`. The owner approved
its live 150×46 SWARM layout before WP5; 200×48 was also measured using committed v8 fixtures.
The separate launch tier warms at up to three production detail reads and three eligible site
job reads per cycle. Missing tickers and partial `… n/4` verdicts during warmup are expected;
an unavailable RPC or policy remains unknown, so repeated polling does not promise completion.
Base/RH evidence and links were tested with fixture-derived chain swaps, not live probes.

No new production defect was found during WP5's hardening. F98/F99 above remain outside this
branch's scope; the owner's earlier parked decisions are unchanged. Final whole-branch review
belongs to the Claude Code controller. Per-WP reviews were waived by the owner.

Measured SWARM pin remains 129×35: SITES/status bind width, and the nine-line throughput floor
plus two eight-line table floors bind height. LAUNCHES has no hidden columns from 77 at 35 rows
(75 on the 80-row capture without a table vertical scrollbar), compact/full at 116/157. Capture clears its marker at 157; long production
parked reasons may still mark. WORKFLOWS compact/full starts at 109/119. The broad address sweep
now seeds production MAINNET/Base/RH tokens; WORKFLOWS' unlinked failure address sets its own
seed-completeness width of 144. That width is not a layout pin. At the unchanged default
143-column width, eleven active detector rows need 43 rows; the mixed fixture needs 39.

## SURFBOARD hub handoff — 2026-10-09

`feature/surfboard-hub-9` implements dashboard 9 with the approved 149×45 four-row rack.
The seven existing SURFBOARD destinations share their original screen and manager; three
future cards and two empty bays reserve expansion space. The live native terminal accepts
read-only commands and retains its input, replies and scroll position across refreshes.
Acceptance and rank now use the same validated seat-record snapshot throughout HUB,
AGENT and BOARD. Contributor effort, presence and each meter family retain separate clocks.

The actual public-API render preceded hardening; the final live render was refreshed after
review fixes. The rack measures 140×36 with the short-window scrollbar allowance. Existing
SURF body pins and the app-wide 143-column pin are unchanged. Source failures retain dated
values or explicit unavailable states. The current POOL4 API omits return-window evidence,
so its trailing seven-day return correctly remains unavailable. IMD events are a polled
recent window rather than complete history; seat records disclose upstream caching ≤10m.

Task reviews corrected timestamp bounds, family freshness, service status, absent-record
freshness and persistent seat selection. Final review found two Important text-fit issues:
POOL4's focused source clocks and its seven-day return label. The single fix wave removed a
redundant shared clock, compacted the period label and added a focused-detail overflow hint.
The scoped re-review approved both fixes; three compositor regressions passed. No remaining
hub review findings were filed. Earlier parked findings above retain their existing scope.

Verification includes 1,534 data/widget/startup checks, the composing screen runs with their
old-source expectations migrated, 104 final-fix data/screen/layout checks, five affected
address-sweep cases, 82 registration mounts and 12 documentation pins. Decoder, cancellation,
command-generation, scroll-anchor and both-direction layout-pin mutants were killed and
restored byte for byte. All 122 project guards passed before the local commit; a full
suite is deliberately outside this branch's authorized Tier 2 verification scope.

## SURFBOARD terminal parity handoff — 2026-10-09

The hub terminal now places new live events after prior command replies, retaining its bounded
window, input draft and manual scroll anchor. Time/event/agent/state/description columns follow
the imd.fun reference. A compact prompt and footer show verified-pair IMD market cap (explicit
FDV fallback), the website's $1B display goal, total inference tokens and provider snapshot age.
Market and swarm stale states remain independent. The one-second age timer updates only the
footer and stops while the screen is suspended. Existing overview cache entries preserve useful
totals/events on upgrade; an absent new token count stays unknown.

The final 149×45 public-API capture shows two new events below a `status` reply. The rack's
140×36 pin and card palette remain unchanged. Final whole-diff review approved the extension
with no findings after 12 focused checks; no fix wave or new follow-up was needed. Verification
passed 251 UI/contract/composing tests, 317 data/composing tests after cache migration, the
earlier 587-case data run, 122 guards, 12 docpins and two address cases. Six targeted source,
ordering and timer mutants were killed and byte-restored. The full suite was not run.

## SURFBOARD event semantics and cadence — 2026-10-09

The terminal now follows the site's launch, publisher, verifier, completion, oracle and
arrival labels and descriptions. Sparse validated event metadata includes token/launch/chain,
ENS/CID, steps/failure, score counts and owner/history facts. Metadata enrichment retains
event identity and command-relative position; legacy cached events migrate without invented
detail or refreshed timestamps. Address links use only the served, allowlisted chain.

The screen and active overview use 30 seconds for refresh, eligibility and freshness; inactive
overview, other source tiers and the display-only footer timer keep their own cadences.
The live 149×45 preview showed a real PixelToken launch under deployer/deployed and a 30s poll
indicator before hardening. The highlighted input, footer and card layout remain in place.

Final review found three Important cases: blocked completions lost failure detail, cancelled
nodes lost their step, and later equal-time work could mark an earlier arrival awake. The single
fix wave addressed all three, with four focused regressions and inverse-mutation proof.
Scoped re-review: **Approved**; no remaining review findings. The initial integrated run passed
574 scoped cases, then 127 UI/composing cases after chain-link support; guards, docpins and hub
address checks passed. Nine targeted mutants were killed and restored. No full suite was run.

## LEADERBOARD hero proposal 1 mockup — 2026-10-12

The standalone `scripts/surf_leaderboard_hero_demo.py` implements the selected six-card
ranking overview with fictional data. It reuses the rack cards above the native LEADERBOARD
and FLEET panels. The 1,024 seat records reconcile to 100,000 attempts and 96,000 accepted;
worker slots and contributor receipt totals retain their independent meanings. No runtime
screen, API, configuration, cache, theme or layout pin changed in this mockup phase.

The 149×45 preview was shown at `/tmp/maxpane-leaderboard-hero-mockup.png`. Three compositor
and accounting tests passed with isolated HOME and four workers; the 100×30 scroll/resize
case recovers all six cards. A three-column layout mutant was killed by the owner-size
compositor test and restored byte for byte. All 124 fast guards passed. The next phase,
after owner feedback, is integration with the existing independent records, workers and
contributor sources.

Final review: **Approved**, no findings or fix wave. Its receipt-time unit mutant was killed
by the accounting and compositor tests. All 12 documentation pins passed; no full suite was
run. The native table's three-cell rank column still advertises `widen` for four-digit ranks;
that existing production behavior remains outside this mockup's scope.

## LEADERBOARD hero live integration — 2026-10-12

The approved six-card rack now uses the existing canonical seat records, worker
roster and contributor receipts. RECORDED shows seats as digits and attempts on
the inner bottom border. TOP SEAT remains canonical rank one through table sorting.
Known-empty records, no attempts, genuine zeros, partial observations and source
outages remain distinct. Incomplete worker coverage retains the served live count
without presenting partial slot sums as totals.

Worker and contributor confirmations have independent manager-memory clocks tied
to the captured cache entry. Successful unchanged reads confirm freshness; failed
reads retain their own last-good clock. Restored cache values remain dated until
confirmed. The existing requests, schedules and persisted formats are unchanged.

The public-API render at 149×45 was shown before layout hardening. It reported seat
527, 1,028 recorded seats and 95.7% accepted. The measured BOARD pin is 143×35;
TOP SEAT's accepted-count subtitle binds width, while the nine-row hero and native
fleet floor bind height. The native table still fits from 141 columns. The existing
four-digit rank-column `widen` indication remains outside this change's scope.

Final review found one Important timing edge: a board response arriving during
the cycle's earlier chain await was validated against cycle-start time and could
briefly appear unavailable. The single fix wave validates at the capture's current
injected clock, before detached spawning. Its regression failed before the fix;
the scoped re-review marked it ADDRESSED and killed the inverse-clock mutation.
No remaining review findings were filed.

Verification covered the projection, widget, contracts, manager and composing
screen files. The final manager run passed 192 cases; the registration file passed
83. The layout file passed 587 cases, with its sole failure an obsolete cross-body
ordering assertion from POOL4's earlier resize; removing that comparison left the
named case green. All BOARD boundaries passed, including both-direction width and
height mutation proofs. Colour-dependent screen cases passed with NO_COLOR unset.
Fast guards passed 124 cases and documentation pins passed 12. No full suite ran.

## LAUNCHPAD hero proposal 1 mockup — 2026-10-12

The standalone `scripts/surf_launchpad_hero_demo.py` implements the approved
six-card overview: COINS, CURVE FLOW, VOLUME, CREATOR FEES, BURN QUEUE and BURNED.
It reuses unchanged rack cards over the existing native launchpad panels, with
clearly fictional figures and addresses. The 2h volume uses eight completed
15-minute buckets totaling $42,600 at a mock current ETH/USD quote of 3,200.
Creator fees preserve 0.0842 ETH; event burns total 15,700 IMD, independently of
the protocol's burn accounting. Factory and swept counts are both 210; the native
coin table is a top-twenty excerpt, not the whole population.

The 149×45 mock render was shown at `/tmp/maxpane-launchpad-hero-mockup.png`.
The three compositor/accounting cases cover the exact fee digits, matching body
facts, nine-row card geometry, black/green inset and narrow scroll/resize recovery.
A three-column layout mutation was killed by the owner-size compositor case and
restored byte for byte. The standalone app performs no API, cache or configuration
access; no production screen, widget, theme, source contract or layout pin changed.
API integration is the next phase after owner approval of this mockup.

Final review: **Approved**, no findings or fix wave. Rounding the creator fee to
three decimals was killed by both the compositor and accounting tests and restored
byte for byte. The three mock tests passed with isolated HOME and four workers;
all 124 fast guards and 12 documentation pins passed. No full suite was run.

## AGENT hero proposal 4 mockup — 2026-10-12

The standalone `scripts/surf_agent_hero_demo.py` implements the selected twelve
topics in two rows of six rack cards, above the native RECORD table. It reuses
the unchanged shared card, meter and address renderers. All identities, work,
receipt totals and software/model examples are explicitly fictional. The mock
history has 1,000 attempts and 960 accepted: 500 reviews, 340 builds and 120
oracle assessments. Owner receipt share is 38.52 IMD / 3 seats = 12.84 IMD;
the fictional 9.41 USD quote gives $120.82. Effort remains a separate receipt
aggregate.

The 149×45 preview was shown at `/tmp/maxpane-agent-hero-mockup.png`. Its twelve
cards have equal nine-row heights; the native RECORD table fills the remaining
space. A 100×28 viewport scrolls to the rightmost cards and table, then recovers
at the owner size. Owner copy/explorer affordances are checked in the compositor
without touching clipboard or browser. The standalone phase performs no API,
cache or configuration access and changes no production screen, widget, theme,
source contract or layout pin. API integration follows owner mockup approval.

Final review: **Approved**, no findings or fix wave. The geometry mutant and
reviewer's owner-link and BUSY/capacity mutants were killed by the named
compositor test and restored byte for byte. All three mock tests passed with
isolated HOME and four workers; 124 fast guards and 12 documentation pins passed.
No full suite was run.

## AGENT hero proposal 4 live integration — 2026-10-13

The approved twelve-card rack now uses existing selected-seat, canonical record,
contributor, worker, reward and runtime reads. Two rows of six equal nine-line
cards sit above native RECORD, which fills the remaining space. Seat selection,
saved rack seats, per-seat caches, RECORD filtering and paging are preserved.
The old hero/seat-card widgets remain parked.

Cards retain independent source clocks. Successful unchanged detail reads confirm
only their selected seat in memory; restored or failed retained readings remain
dated. Captured detail/reward/runtime families cannot mix identities across a
detached read or seat switch. Acceptance/rank use canonical records; contributor
effort and seat-detail history keep their own meanings. Rewards retain owner and
pairing identity and an independent USD quote state. STATUS reuses the rack's
observed-stop meter, including its green/orange/empty progression and offline state.

The real API render at 149×45 showed saved seat 3, 1,288 accepted attempts,
rank 267, 12.53 IMD owner share and 264 collaborators. The live runtime banner
prompted a display-only shortening; its full string/hash remain in the tooltip,
and a differing daemon keeps its visible arrow. The captured API facts are not
committed as fixtures. No endpoint, polling cadence or persisted schema changed.
Existing npm checks are now also offered on cached AGENT activation: the former
missing offer was reproduced against HEAD before fixing its guarded call site.

In-situ measurement gives 134×29: seat420's `3,392 attempts` subtitle binds
width, while the nineteen-line hero and native RECORD floor bind height.
The live preview at 149×45 precedes these measurements. Free-form metadata may
use a visible ellipsis and full tooltip; fixed labels and numeric values must
fit. RECORD's existing answer-clearance exception remains 167 columns.

Verification: 615 data/manager/activity cases, 181 general screen/registration
cases, 187 parked-widget cases, 162 widget/contract/initial live-screen cases,
and 30 final rack/live-screen cases passed. The legacy composing screen passed
94 cases; its obsolete 25-row behavior-test viewport was raised and the remaining
case passed serially. Model agreements passed 42 cases plus one corrected parked
consumer assertion. Both address-sweep sizes passed; fast guards passed 124 and
documentation pins 12. Identity, source-confirmation, malformed-row and both
width/height directions have killed mutations. No full suite was run.


The complete layout file passed 528 cases; its one colour case passed after
unsetting NO_COLOR, verifying all 529. Width and height mutations were killed
in isolated copies at 133/135 columns and 28/30 rows. Final review identified one
Important stale-negative case: an old never-paired result lost its stale source
state. The single fix wave preserves that negative and selected ID, shows its
last confirmation time, and clears the stale label after a successful read.
Eight manager-to-compositor cases cover failed, busy, expired and restored
readings at both 134 and 149 columns. All 169 post-fix projection, manager, models,
widget and live-screen cases passed.

Scoped re-review: **Approved — ADDRESSED**. The reviewer killed the inverse
stale-negative mutation with the named manager/compositor regression and
restored the file byte for byte. No residual review findings remain.


## Rack TOKENS volume ranking — 2026-10-13

Replaced LAUNCHES with TOKENS / LAST 24h: three recent canonical deployments
ranked by selected-pool USD volume, same-market price-load arrows, and an
independent newest-launch footer. Hub offers markets without the removed hourly
chart reads. Live 149×45 preview showed SNITCH, SCOOP and PUPATE, with BITES
in the footer; indexed volume coverage was explicitly partial (18/30).
The existing 144×35 pin and equal card heights remain valid.

Verification: the affected/composing run passed 564 cases; its two obsolete
footer expectations were corrected and the complete activity file passed 20
cases under isolated-home worksteal. Guards 124, doc pins 12 and address sweeps
2 passed. Ten implementation mutations were killed. Final review: Approved,
no findings; 23 focused checks and an additional price-baseline mutation passed.
No full suite was run. No residual follow-ups.

## AGENT card state and presentation adjustments — 2026-10-13

Implemented the owner's requested captions, ERC-8004 registration ID, grouped
accepted count, full-width meters, payout time/24-hour color and consecutive-read
rank movement. STATUS uses the boardroom activity fold and a grey `0F` separator;
SEAT uses independent worker presence. Visible stale badges are removed while
internal clocks and retained-state tooltips remain intact. Loading ends for each
completed source independently, and failed/busy results stay distinguishable.

The keyless native 149×45 preview was shown before hardening. Capture and stress
sweeps measured 132×29; the STATUS activity caption binds width. Sixteen
implementation mutations were killed. The combined run passed 1,387 cases with
three outdated expectations; after correction, all 178 affected-file cases passed.
Final review approved with 21 focused tests and a further pending-state mutation;
the grey separator was also verified in compact and unknown-count output.
No residual review findings. No full suite was run.

## AGENT labels and premium model usage — 2026-10-13

SEAT now reads `Identity.md`; STATUS's static `0F` matches the outer card
background in tall and compact modes; unchanged RANK has no footer. EFFORT shows
the Astra/Opus/Fable share among known actual submission models, with premium,
known-model and total recorded attempt counts on hover. The owner explicitly
selected this subset calculation. It uses all loaded selected-seat work before
RECORD filters, adds no API reads, and remains available through contributor
outages when model evidence is valid.

The keyless native 149×45 preview showed seat 3 at 20.69% premium: 12 of 58
known-model attempts, with 1,354 recorded attempts. Native 131–133-column checks
preserved the existing 132-column boundary. The scoped composing run passed
745 cases, guards 124 and doc pins 12. Final review found one footer-priority
defect; the fix passed all 48 widget/native-integration cases. Three data
mutations and reviewer footer mutations were killed and restored byte-for-byte.
Scoped re-review: Approved. No residual findings; no full suite run.

## AGENT second-row cards — 2026-10-13

OWNER, MODELS, COLLAB and NODES use neutral frames. RUNTIME omits its widen hint,
uses orange only for a confirmed software update, hides unknown check captions,
and shows the owner-approved latest worker connection time with its independent
clock and restart distinction on hover. MODELS centers the model/effort pair on
the middle line, retaining the effort when a long model name is ellipsized.

EARNINGS replaces FEEDBACK: distinct wallet token assets, selected-seat accepted
builder assets, and explicitly claimed assets. Only a builder launch less than
24 hours old activates green. A bounded GET-only explorer decoder validates the
served owner and preserves real empty versus failed reads. NODES partitions
accepted work into oracle, confirmed live launch and other work, with coverage
and independent clocks on hover. Unread memberships do not become other work.
Two bounded persisted sources share the cancellable selected-seat read lifecycle;
their failures retain previous values and timestamps independently.

The native live 149×45 render showed seat 3 with 226 earned, five worked-on and
11 claimed assets; NODES showed 1,277 oracle, nine launch and 12 other accepted
work entries. Source dates are observations, not constants. Capture and stress
checks preserve 132×29. The first touched/composing run passed 1,234 cases;
21 failures exposed obsolete assertions and the long-model effort clipping.
After correction, all affected checks passed: 57 widget/native/cache cases,
43 stress-layout cases and ten screen cases. Guards 124 and docpins 12 passed.
Eleven implementation mutants were killed, including connection versus heartbeat
and frozen pending-owner state. No full suite was run.

Final review: Approved, no findings. Sixteen targeted checks passed; two additional
mutations killed missing wallet validation and missing selected-seat attribution.
All source bytes were restored. No residual follow-ups from this change.

## AGENT EARNINGS recent-token footer — 2026-10-13

The owner replaced the claimed footer with `x new`, plus ` (y)` only for a
positive selected-agent builder subset. Both counts use distinct chain/address
assets and the rolling 24-hour window; an old asset cannot become new through a
later duplicate row. Missing dates or work identity preserve unknowns. Raw claim
fields stay cache-compatible but no longer affect the visible summary. Existing
total figures and the green recent-builder-work rule are unchanged.

The native live 149×45 render showed seat 420 with 349 earned, 25 worked on and
`41 new (1)`. The 132-column footer check fits the largest supported count as
`4.1k new (4.1k)` and keeps exact numbers on hover; wider cards use exact counts.
No layout pin changed. Five data and two UI mutations were killed and restored.
Final verification: 579 affected tests, 124 guards and 12 doc pins passed. Review
approved with no findings; 17 targeted cases and two additional mutations verified
unknown-date handling and recent-work projection. No residual follow-ups.

## AGENT EARNINGS footer priority and read status — 2026-10-13

Recent selected-agent builder work now takes priority: `x new worked on`, otherwise
the total `x new`. Current reads show a loading indicator, including cached refreshes.
Recorded fetch failures use the distinct `failed` state and red `load failed`.
Review caught that `unavailable` also includes unread and cancelled first reads;
those remain unavailable without claiming an error. Cached values survive retries
but are hidden while pending or failed. No layout pins or fetch endpoints changed.
The single review finding is addressed by state-projection and composited regressions;
scoped re-review approved with nine focused cases and a killed regression mutation.
Final affected checks: 393 tests, 124 guards and 12 docpins passed. No residual findings.

## AGENT RECORD launch view — 2026-10-14

RECORD now offers `all` / `launches` and the exact seat/filter shortcut hint.
The filter editor adds LAUNCHES beneath WHEN. Both launch selectors use verified
live job membership, including failed or rejected attempts when their job launched.
The independent bounded membership reader covers all nonoracle attempts; accepted
NODES/EARNINGS counts retain their existing meaning. Confirmed nonlaunches leave
the window before its cap; unread and failed checks remain counted in the footer.
A failed membership refresh never presents a retained point as a fresh decision.

The live native 149×45 capture showed ten matching attempts for seat 3 alongside
nine accepted launch entries in NODES. The new selector and hint fit; the existing
editor sweep also passed at compact widths and the AGENT pin. No pin changed.
Eight implementation mutations were killed: confirmed membership versus intent,
failed cached refresh, all-attempt discovery, manager window join, filtering before
the cap, unknown retention, submission independence and unknown footer reporting.
The first affected run passed 1,095 cases and exposed two obsolete expectations;
after updating them, both affected files passed all 268 cases (1,098 distinct
cases covered across the final checks). Guards 124 and docpins 12 passed.

Final review identified one Important timing issue: membership completed after the
seat cycle began, but answer/detail windows used the older clock and discarded
those new facts as future data. All three RECORD readers now share a post-read
snapshot clock. A regression advances the injected clock during 41 membership
reads and confirms only the launched job receives answer and popup-detail reads,
for both the tab and custom filter. Reverting the clock fix kills both cases.
All four affected data files passed again (231 cases). Scoped re-review: ADDRESSED,
Approved; both permanent clock regressions and the original reproduction passed.
A further mutation proved popup-detail reads use the same clock and was restored.
No residual findings. No full suite was run.

## LEADERBOARD launch contribution tab — 2026-10-14

Added the requested second tab, ranking seats by distinct accepted non-oracle
jobs contributing to live production launches across all launch history. Testnet
and unlaunched entries are excluded before detail reads. Verified workflow links
include frontend jobs omitted by the launch's direct job list. Repeated nodes or
launch references cannot inflate a seat's job count.

The tab has jobs, launches, runtime and current-state columns, independent sorting
and cursor/scroll retention, and the existing seat-opening action. A visible-tab
background reader loads six launches at a time. First load reports progress;
refresh/failure retains the last complete ranking and its source clock. Validated
compact facts survive restart. A catalogue refresh cannot publish mid-pagination.

A genuine 149×45 Matrix-theme preview was shown. The first complete read covered
317 production launches in 391 seconds. A cached refresh picked up a new launch
in about one second: 318 launches and 727 contributing seats. BOARD remains
143×35. Narrow titles use shorter clickable labels to preserve the widen hint.

Validation: 1,026 affected tests passed; subsequent manager integration
checks passed 299 cases; reader tests passed 36; registration checks passed 85;
guards/docpins passed 127. Fourteen mutation checks were killed and restored
(six reader, six UI, two integration). No full suite was run.

Final BOARD/widget checks passed 188 cases, including the new tab at 143×35,
149×45 and 225×61 and the existing boundary sweep. Docpins passed 12 cases.
Final review: Approved, no findings. Three named integration/UI checks and a
frontend-inclusion mutation passed review verification; no residual follow-ups.

## LEADERBOARD launch contributor settings and roles — 2026-10-14

Added MODEL, EFFORT and BUILD / REVIEW to launch contribution. Model and effort
remain paired current advertised settings, joined from the existing worker cache
without per-seat requests. Multiple settings show `+N` and full pairs on hover.
Unknown settings remain distinct from a confirmed empty advertisement.

BUILD counts accepted implement, integrate, test and tests jobs; REVIEW counts
accepted review jobs. Counts deduplicate job IDs across nodes and launches. A seat
doing both roles on one job contributes to both counts but only once to its ranking.
Unknown roles preserve the ranking and leave the split unknown. Legacy cached
rankings remain visible while existing bounded reads backfill role facts.

The live 149×45 Matrix render covered all 318 production launches and 727 seats,
all with known role counts. All nine columns fit the unchanged BOARD 143×35 pin.
Compact layout remains 130 columns; the tight table clears overflow at 73 columns.
Long settings retain full hover details; large role counts preserve exact digits
through `100000/100000` at the full-layout pin. No testnet launches are included.

Validation: 326 data/model/manager tests, 230 widget/contract/composing screen
tests, 124 existing BOARD layout cases and 124 fast guards passed. Thirteen
implementation mutation checks were killed and restored. No full suite was run.

Final review found two Important issues: unavailable settings used absence wording,
and large role counts could clip. Both were fixed in one wave. Scoped re-review:
Approved; four regressions and six boundary cases passed, and both targeted mutants
were killed and restored. The initial review also killed a role-classification
mutant. No residual findings.

## BOARD cards and compact FLEET — 2026-10-15

The six neutral cards now place acceptance, online seats, launch contributors and
cumulative effort as requested. Card faces retain metric footers during stale
reads; source qualifications and independent worker clocks remain on hover.
LAUNCHES reads in either BOARD tab and counts distinct accepted non-oracle job
IDs across all live production launch history. Current claude/codex seat counts
disclose known runtime coverage, and both-runtime seats count in both categories.
EFFORT sums input/output tokens and shares the boardroom's whole-year/week/day
duration formatter. Missing sources remain unknown; retained snapshots preserve
their matching totals and timestamps.

FLEET puts its top two runtimes on one line, the top three models on separate
lines with inline omissions, and every OS/slot category in pairs. Blank rows
separate categories; RECEIPTS is bold. LEADERBOARD keeps its complete column
budget while the rail receives the spare width. The tab is named launch
contributors. The live 149×45 production preview showed 320 launches, 729 seats
and 351 distinct jobs with all table columns, metadata and receipts visible.

Measured BOARD is 142×44: recorded seats clears at 140, launch contributors at
142 (compact 129, tight 72); capture/v4 height is 42 and stress with paused detail
is 44. Five integration mutants prove visible-BOARD loading, card updates, the
width allocation and both directions of the width pin. Fourteen more mutants
cover data and the two widgets; every mutant was killed and restored.

Validation: 274 affected data tests, 532 widget/composing screen cases and 122
BOARD layout cases passed. The combined run caught the shared formatter's old
export-list expectation; after updating it, all 59 formatter tests passed.
Fast guards passed 124 cases and documentation pins passed 12. No full suite
was run. Final review: Approved, no findings. Review verified the fresh-process
boardroom import, shared duration, tab/resize column preservation and three named
tests; a distinct-canonical-seat mutant was killed and restored. No residuals.

## BOARD value emphasis and population shares — 2026-10-15

FLEET and RECEIPTS now color numeric values and omission counts with the
leaderboard foreground, preserving neutral labels, model/version text, units
and clocks. LEADERBOARD omits its widen hint at the owner's request; responsive
columns, ellipses, hover detail and clickable tabs remain.

LAUNCHES shows contributor seats divided by canonical RECORDED seats, with
the denominator's independent source state and clock on hover. WORKERS shows
the leading runtime's share of distinct online seats. Devices are deduplicated,
both-runtime seats vote once per runtime, and missing roster/runtime coverage
leaves the leader unknown. Empty and whitespace-only runtime IDs also count
as missing metadata. No new data source or polling was added.

The live production preview at 149×45 showed `68.3%` contributors and
`52.5% run codex`, with the prior launch ranking retained during its refresh.
All columns and receipt rows fit. BOARD remains 142×44; 122 layout cases passed
using actual columns/clipped fields rather than the omitted hint. Data checks
passed 239 cases; widget/composing checks covered 159 cases. Four obsolete
hint assertions were updated, then all 103 FLEET/LEADERBOARD cases passed.
Fast guards passed 124 cases and documentation pins passed 12. No full suite.

Final review found one incorrect-percentage edge involving an empty runtime
ID, fixed in one wave with five failing-then-passing regression inputs. The
initial data/UI proof killed eight mutants; the fix adds a guard-bypass proof.
Scoped re-review: Critical finding ADDRESSED; the reviewer independently killed
the guard-bypass mutant and restored exact bytes. No remaining blocking findings.

Open Minor: `_percent()` uses the existing `_face()` precision below 1%, so
`0.123456` renders `0.1235%` rather than the plan's one-decimal `0.1%`. File this
formatting refinement for the next touch of `swarm_board_hero.py`; no numerical
value is lost or rounded to zero.

## BOARD card padding and value color — 2026-10-15

LAUNCHES, WORKERS and EFFORT now keep one blank cell inside each vertical
border. Their right-hand values and the first three cards' primary digits
use the leaderboard foreground. Frames, labels, captions and outer footers
retain their existing styling. Optional shared-renderer settings default to
the previous appearance for other cards. FLEET omits heartbeat and leaves two
blank rows below paused or its detail before RECEIPTS.

The production app was rendered at 149×45 using retained live-source cache
data; the refresh failed, so this is not a fresh-data claim. Composited tests
verify padding and colors independently of the SVG export. Removing heartbeat
reduces the height pin from 44 to 43. Capture/v4 fit from 41 rows and stress
with paused detail from 43. The overall width stays 142; the padded stress
fixture now needs 141 rather than 140, while the recorded table itself still
clears at 140. The old width expectation failed serially and was corrected;
all 87 width-boundary cases then passed.

Validation covered 374 widget/composing cases and 518 layout cases, with 124
fast guards and 12 documentation pins. No full suite was run. The previously
filed boardroom FLEET hover-wording overstatement was corrected when the
behavior rules were touched; calculations and tooltips are unchanged.

Final review: Approved. Five implementation mutants and the reviewer's padding
budget mutant were killed and restored. Default-consumer colors and BOARD
refresh/resize styles passed focused review checks.

Open Minor: at 61 columns, an unknown stats value `--` clips to `…` before
`NewsHeroCard.render()` checks whether it is unknown, so the ellipsis becomes
green. Preserve the unknown flag before clipping when `news_hero.py` is next
touched. The approved owner size and full-layout pin retain neutral unknowns.

## Production launch toasts — 2026-10-15

Surf modes and the boardroom now share native ten-second launch toasts with
production filtering, silent first-session history and UUID/token alias
deduplication. Work/Oracles retain the existing launch tier while leaving
unrelated full-cycle sources paused. The new `swarm_launch_read_ts` snapshot
metadata prevents retained fired news from arming notifications before a
successful session read. No endpoint or dependency was added.

Final review found and verified one Important same-batch alias-order defect;
the fix learns known UUID aliases before selecting notifications. Scoped
re-review: ADDRESSED, no residual findings. Seven deliberate mutations were
killed and restored. The initial scoped run passed 859 cases and exposed an
older fixture missing `launch_state`; that fixture now states `not_read`.
After the fix wave, all 29 focused checks and all 96 composing-screen checks
passed. The 124 fast guards and 12 documentation pins passed; no full suite ran.
Live preview at 149×45 showed no startup notifications and rendered a
demonstration toast using an existing public production launch. No actual
new-launch event was observed during that preview.

## AGENT earnings wallet total — 2026-11-09

The EARNINGS inner footer now shows `x total` for distinct earned assets on
Ethereum, Base and Robinhood, including shared/early allocations. Testnets are
excluded. Seat-specific central digits keep their existing accepted-work scope.
The public-data render at 149×45 showed 33 centrally and `513 total` below.
Existing reads/cache are reused; source failures retain the displayed total,
while an owner change resets it. No layout pin changed.

Validation: 639 focused/composing checks passed; fast guards passed 129.
Three failures reproduced independently from an isolated archive of baseline
`a96b2c83`, and remain outside this footer change:

- `test_widget_modules_import_no_data_layer_and_no_analytics`: the existing
  `swarm_latest` import of `surf_launch_checks` is absent from the test allowlist.
- `test_board_keys_are_exact_before_finalization_and_survive_cold_start`: its
  expected keys omit the existing `swarm_launch_read_ts` signal metadata.
- `test_screen_css_agrees_with_application_stylesheet`: its SWARM TOKENS slice
  also includes the following SWORN Explorer CSS block.

All three deliberate regressions were caught: removing the production-network
filter, reverting the footer to its recent count, and removing total-caption
retention. No full suite was run. The touched composing test's old `#--` identity
placeholder assertion now follows the existing blank-placeholder convention.

Final review: Approved, no findings. The reviewer independently passed 13
focused checks and killed/restored a separate total-retention mutation.

## Boardroom active counts — 2026-11-09

SHIPPED now counts canonical production token deployments, including inactive
tokens and excluding testnets/aliases. Its inner footer shows new launches in
24 hours; the existing outer chart still represents accepted steps. WIP reports
verified working nodes or waiting jobs, with neutral styling while waiting.
RESEARCH counts a separate filtered assessing-request read. Missing current
counts stay blank/dashed locally instead of being replaced by zero or a previous
activity count. Native request history and shared card fallbacks remain unchanged.

Bounded job discovery resumes one older page per poll until verified executing
coverage matches the global total. Research request IDs seed candidates, but a
terminal candidate cannot suppress discovery. Detail failure/cancellation leaves
the history cursor unchanged so newly discovered identities are retried.

Live render at 149×45: 524 shipped tokens, 2 new, WIP 1 / 1 waiting, RESEARCH 1 /
unknown agents / 1 chain. These are dated observations, not production constants.
The independent final review raised two Important paging findings; both were
fixed in one wave and approved on scoped re-review. Three new cases failed before
the fixes and passed afterward. Five controller mutations plus the reviewer's
cancellation mutation were killed and restored byte for byte.

Validation: client 199, token catalogue 57, pure card projection 248 and composing
manager 98 checks passed. The final reader/manager run passed 129 with 17 existing
reader-harness failures. The 20 height-boundary cases passed after updating their
expected TOKENS and unknown captions. Fast guards passed 129 with one existing
CSS failure; documentation pins passed 12. No full suite ran.

Residual failures were independently reproduced on the prior implementation:
17 current-reader tests use outdated workflow/get_hub_seats harnesses; one RPC
budget test has the same missing get_hub_seats seam; 39 Boardroom widget/screen
tests have existing colour/navigation expectations. The guard failure is the
previously recorded SWARM TOKENS CSS slice that includes the SWORN block. Keep
these outside this data-correctness fix and repair when their respective files
are next maintained.

## RESEARCH assigned-agent count — 2026-11-09

The footer now counts distinct seats whose standing `running` assignments match
active research job IDs. The full `/swarm.seats` busy roster supplies coverage;
`/workers` can omit assigned seats, and `health.workingNow` is not an equivalent
roster total. A submitted job node with `live: null` can still have an assignment
in standing, so node state and submitted panel members cannot supply this count.

Standing reads resume in batches of at most 32, with four concurrent requests and
at least 60 seconds between completed attempts, including failures. Larger
rosters fill over multiple polls. Coverage must include every busy seat in the
latest roster; failed reads remain unknown. Observations expire after five minutes,
and the tooltip preserves the oldest observation time. Request identity changes
invalidate prior coverage. No layout pins or model keys changed.

Live verification at 149×45 covered 75 busy seats after three batches (141 seconds)
and rendered 1 research job / 1 assigned agent / 1 chain. The matching standing
assignment was seat 1548 for job `31a2cf4d-24f7-4fe8-8a31-f9437c520182`.
These are recorded assignments, not proof a model process is currently executing.
The RESEARCH card used public live data; other preview cards used retained cache.

Validation: 24 focused checks passed; the whole touched/composing run passed 600
with the same 17 pre-existing reader harness failures documented above. Fast
guards passed 130 with the existing SWARM TOKENS/SWORN CSS slice failure;
documentation pins passed 12. Six controller mutations were killed and restored.
The reviewer independently passed the 24 checks and killed/restored an oldest-time
mutation. Its one Important test-fixture finding was corrected by reusing the
captured standing response; no production fix or scoped re-review was needed.
No full suite ran.

Filed Minor capacity limit: at 129 stable busy seats and a 90-second batch cadence,
the five-minute expiry prevents full coverage (reviewer reproduced ten rounds,
maximum 128 covered seats). Such a roster remains unknown. Raising the rate or
age bounds would trade API limits against freshness and needs separate work;
this implementation does not promise completion for every possible roster size.

## Portfolio native filtering — 2026-11-10

Removed generated partial labels from the scan cards, tooltips and claim coverage
copy. Neutral observation times remain; source states and valuation data are
unchanged. The domain sale state displays as `limited` when no percentage exists.
The permanent select/search bar is now a compact FILTER summary. `f` opens the
existing native editor in place of the tables; Apply commits the draft, Reset
only resets the draft, and Esc cancels. `/` opens the editor at Search. Filtering
remains local, and the legacy Portfolio editor keeps its default configuration.

The public-data preview at 149×45 used the endpoint's retained 537-asset scan
(23:00 observation) and separately refreshed seats. This was not a new valuation
read. The compact summary saves two rows: the measured whole-viewport boundary
is now 147×42, with broad width 125–155 and height 30–48 probes. The native editor
uses the shared compact layout at 80×24, with keyboard access to Apply and Reset.

Validation: 59 composing checks passed. All nine failures in the legacy
`tests/screens/test_portfolio.py` reproduced in an isolated archive of unchanged
HEAD: missing PortfolioHero.render_box, obsolete held-value/coverage labels,
wallet-prompt expectations, and their height/width cases. Fast guards passed 130
with the previously recorded SWARM TOKENS/SWORN CSS-slice failure. Five deliberate
regressions were killed and restored: partial badge, cancel committing the draft,
ignored chain selection, and the height pin one row too low or high. No full
suite ran. These legacy failures remain outside this change.

Documentation pins passed 12. Final review: Approved, no findings; five focused
checks passed, including legacy filter compatibility, and a separate
reset-commits-draft mutation was killed and restored byte for byte.

## Portfolio card labels and table height — 2026-11-10

Removed the allocation line and all outer card footer text. Observation times
remain in tooltips, the screen header and source evidence. The first four inner
boxes now place their former footer above the value and USD below it. SEATS uses
the exact inner caption `Identity.md NFTs`; its inset drops side padding to keep
that caption whole at the existing minimum width. Source facts are unchanged.

The three table rows share all remaining height at 9:8:6, with their existing
minimum sizes. NFT inventory and eligibility end one blank row above the status
bar at 149×45 and 149×60. The native filter editor shares the same growing area.
The public preview showed the source's retained 537-asset scan (23:00 observation)
and independently refreshed seats. This is a display change, not a new valuation.

The measured whole-viewport boundary is 147×40 after removing the allocation
line. Broad probes covered 125–155 columns and 30–48 rows; narrow-screen scrolling
and the native filter editor remain available. Seven deliberate regressions were
killed and restored: allocation return, outer timestamps, reversed wallet labels,
old SEATS caption, fixed table height, and the height pin one row in either
direction. No full suite ran.

Validation: all 44 touched/composing checks and 12 documentation pins passed.
Fast guards passed 130 with the already recorded SWARM TOKENS/SWORN CSS-slice
failure. Review: Approved, no findings; six focused checks passed, and restoring
SEATS side padding was killed by the width-boundary test and restored byte for
byte. The full requested caption is therefore covered at the minimum width.

## Portfolio header and eligibility alignment — 2026-11-10

The SEATS caption is now `Identity.md` and its inner-box padding matches the
other cards again. Per the owner's clarified order, the filter summary follows
HOLDINGS on the same title row. Long search text ellipsizes on that single row;
the tooltip retains the complete sanitized summary. The existing filter editor
and local filtering behavior are unchanged. Eligibility content, including
wrapped lines, has the same one-character left inset as its header.

The keyless public-data render at 149×45 was shown before layout hardening. It
uses the endpoint's retained 23:00 scan and independently refreshed seats. The
removed summary row reduces the whole-viewport boundary to 147×38. Broad probes
covered 125–155 columns and 30–48 rows; tables still fill the available height
and leave one blank row before the status bar. Seven deliberate regressions were
killed and restored: old SEATS caption, unequal card padding, missing eligibility
inset, reversed header order, wrapped search, and the height pin ±1. No full suite
ran.

Validation: all 46 touched/composing checks and 12 documentation pins passed.
Fast guards passed 130 with the previously recorded SWARM TOKENS/SWORN CSS-slice
failure. Review: Approved, no findings; six focused checks passed and removal of
the full filter tooltip was killed by the long-search regression test. The
review mutation was restored byte for byte.

## Portfolio outer card captions — 2026-11-10

The first four cards move their inner-box headings to the outer card footers;
their inner headings are blank and USD remains under the digits. NFTS and SEATS
keep their existing inner labels and empty outer footers. A single blank row now
separates the card rack from the table headers or native filter editor.

The keyless public-data preview at 149×45 was shown before hardening. The first
whole viewport is now 147×39, measured across 125–155 columns and 30–48 rows.
Tables continue to grow with the terminal and leave one blank row before the
status bar. Five deliberate regressions were killed and restored: labels kept
inside, missing outer captions, missing rack gap, and the height pin ±1. Source
facts, observation timestamps and valuation arithmetic are unchanged. No full
suite ran.

Validation: 46 touched/composing checks and 12 documentation pins passed. Fast
guards passed 130 with the previously recorded SWARM TOKENS/SWORN CSS-slice
failure. Review: Approved, no findings; six focused checks passed and moving the
NFTS heading too was killed by the first-four-card test. The mutation was restored
byte for byte.

## Portfolio total in IMD — 2026-11-11

TOTAL VALUE now uses its centered outer footer for the approximate IMD equivalent
of the displayed USD total. The reference is the same scan's canonical Ethereum
IMD aggregate sale value divided by its complete wallet, stake and reward
quantity. This is a sale-quote equivalent, not a spot price or purchase quote;
the tooltip explains the method. Filters change the displayed total but retain
the unfiltered reference. A missing, ambiguous or incomplete IMD quote leaves
the footer blank. No network call or data-contract key was added.

The public-data preview at 149×45 showed `≈1.1K IMD` below the existing USD digits,
using the endpoint's retained 23:00 scan and independently refreshed seats. The
committed reference fixture retains that scan's original values and provenance.
All seven deliberate conversion, identity, missing-value and display regressions
were killed and restored byte for byte. Layout pins are unchanged.

Validation: 77 touched/composing checks and 12 documentation pins passed. Fast
guards passed 130 with the previously recorded SWARM TOKENS/SWORN CSS-slice
failure. Review: Approved, no findings; four focused checks passed and accepting
duplicate IMD references was killed by the reference-validation test. The review
mutation was restored byte for byte. No full suite ran.

## Portfolio active cards and eligibility space — 2026-11-11

TOKEN UTILITIES is hidden in the overview; its scan data and inspector support
remain available. SEATS & ELIGIBILITY spans both lower rows of the right column,
starting beside STAKES and ending beside NFT INVENTORY. It keeps its scrolling,
one-character text inset and one blank row above the status bar. The first four
cards reuse the shared active frame, caption and digit colors; NFTS and SEATS
keep their neutral colors, and all outer card captions remain centered and dim.

The public-data preview at 149×45 was shown before hardening. It used the
endpoint's retained 537-asset scan and independently refreshed seats. Eligibility
is now 19 rows tall. Broad probes across 125–155 columns and 30–48 rows confirm
the existing 147×39 viewport boundary; the visible tables keep their geometry.

Validation: 47 touched/composing checks and 12 documentation pins passed. Four
deliberate visibility, row-span and color regressions were killed and restored.
Fast guards passed 130 with the previously recorded SWARM TOKENS/SWORN CSS-slice
failure. Review: Approved, no findings; three focused checks passed, hidden
utilities stay outside the focus chain, and reverting the panel order was caught
by the layout check. The review mutation was restored byte for byte. No full
suite ran.

## Boardroom job categories — 2026-11-11

WIP now counts verified executing launch jobs (including explicit workflow stages).
RESEARCH combines goal/report/research and oracle jobs, once per job ID. Standalone
site, code and audit jobs are outside both categories. Each footer uses matching
assignments from the same complete busy-roster standing observations; SWARM keeps
all categories. A standing observation predating a new job cannot prove zero agents.

Live verification found six executing jobs: four goals, one old oracle and one
standalone site. The rendered cards showed WIP 0 and RESEARCH 5 at 149 x 45.
Current discovery and last-valid refresh presentation remain unchanged.

Validation: 430 touched/composing checks passed. Seventeen existing card-reader
harness failures (missing fake-manager methods) and the existing TOKENS/SWORN CSS
slice failure were reproduced on unchanged 0c4d5d6b. Guards otherwise passed 130;
documentation pins passed 12. Final targeted checks passed 17 after the observation
clock safeguard. Four decoder/coverage/deduplication mutations were killed. No full
suite ran. Baseline evidence: /tmp/boardroom-category-baseline.xml.

Final review found no production defect and one fixture-convention issue. The
single fix wave moved synthetic roster/standing responses into the committed
fixture; all 16 category cases passed afterward. Seven reviewer cases passed,
including refresh retention, and the observation-time mutation was killed.
No production changed in the fix wave, so no scoped re-review was required.
