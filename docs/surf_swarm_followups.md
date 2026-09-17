# swarm body branch — follow-ups

Findings raised during `feature/surf-swarm-body` (docs `docs/surf_swarm_api.md`,
`docs/superpowers/specs/2026-09-16-surf-swarm-view-design.md`) and deliberately **not** fixed on
the branch, per CLAUDE.md's "report defects, do not fix them" rule and the review discipline that
a scoped re-review files what it finds outside its own target rather than repairing it. The
branch's working notes (`task-*-review.md`, `task-*-re-review*.md` under
`.superpowers/sdd/2026-09-16-surf-swarm-body/`) live in a git-ignored workspace that is deleted
when this plan finishes, so this file is the only place these survive.

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

`tests/screens/test_address_icons_everywhere.py::test_every_rendered_address_carries_an_icon_that_copies_it`'s
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
