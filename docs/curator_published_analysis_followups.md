# THE LIST published-analysis — open follow-ups

Branch `feature/curator-published-analysis`, merged state `905fcb3`. Twelve tasks, twelve
task reviews, nine fix rounds, one whole-branch review and one fix wave. Suite green at
**5,784 passed, 0 failed**.

Everything below was found by a review that correctly declined to fix it out of scope, or
parked by a controller ruling with its reason recorded. Nothing here blocks merge. Each
item says what it costs to leave alone, because that is the part that decides whether it
is ever worth doing.

---

## 1. A pre-existing screen flake, now diagnosed

`tests/screens/test_curator_screen.py::test_screen_adds_removes_and_deduplicates_custom_collection`
fails roughly **1 run in 12**, and it is **not this branch's** — `git log main..HEAD --
tests/screens/test_curator_screen.py` is empty, and the assertion arrived on `18dcb50` on
main.

The cause is now known rather than guessed. The assertion at `:3390` is
`assert "already available above" in _region_text(...)`, and on a failure it reads the
**previous** error strip (`NFT contract must be a 20-byte 0x address`): a single
`await pilot.pause()` after `scroll_visible` is sometimes not enough for the repaint.
It is load-sensitive, so a concurrent suite run makes it likelier.

**Fix:** a second `pause()`, or wait on the strip's content rather than on one frame.
**Cost of leaving it:** every future full-suite run has a ~8% chance of a red that means
nothing, which trains readers to discount reds.

## 2. `archive/` grows and nothing prunes it

`~/.maxpane/archive/<version-id>-<hash12>/` holds ~8 MB per archived analysis, the module
has no deletion primitive **by design** (its whole contract is "relocate, never destroy"),
and the compound key adds one directory per republish.

Judged **carry** by the final review, and it is the right call while the game stays
settled: in practice this is one directory, not a growth curve.
**Cost of leaving it:** if the publisher ever ships regularly, disk grows unbounded with
nobody owning the sweep. Revisit then, not now.

## 3. Three copies of `_valid_address`, and all three accept things that are not hex

`curator_archive.py:178`, `curator_clusters.py:344`, `curator_list_source.py:37`.

They gate on `int(value[2:], 16)`, which is far more permissive than hex. Measured:
`0x+111…1`, `0x 111…1`, `0x1_11…1` and `0x111…1\n` are all **accepted**. A trailing
newline reaches a `DataTable` cell and a written export file.

The duplication is repo-wide and predates the branch — `_opt_int` exists in five modules,
`_opt_float` in seven.

**Fix:** `re.fullmatch(r"0x[0-9a-fA-F]{40}", value)`, hoisted into one shared module.
**Cost of leaving it:** the leniency is shared by all three copies, so a fix today costs
three edits and tomorrow costs more.

## 4. The size caps are parse guards, not memory guards

`curator_published.py` reads `resp.content` — a non-streaming `client.get` — and *then*
compares its length to the cap. The PRD's wording ("size-capped before it is parsed") is
accurate; the cap simply does not protect memory.

**Fix:** check `Content-Length` first, or stream with an early abort.
**Cost of leaving it:** a hostile or compromised host can hand a TUI a multi-gigabyte body.

## 5. `_history_complete()` is a proxy, not a direct precondition

It measures the *fold* (`len(fold_rows) == len(first_deposits)`, `dropped_events == 0`)
while `build_analysis_from_published` consumes `events` and `firsts`. Conservative in the
right direction — it can only refuse — and it is the same proxy `full_list_rows` has always
used.

**Fix:** a sentence in the docstring saying so.
**Cost of leaving it:** somebody later "simplifies" it into a direct events check and
quietly removes the guard that stops a partial fold freezing the analysis forever.

## 6. The band-word *producer* is not pinned to the frozen vocabulary

Four copies of the band vocabulary are now pinned to `CURATOR_BAND_WORDS`. The producer —
`curator_clusters.bands_by_address` / `grade_of` — still writes the words from inline
literals.

Inert in practice: `conf if conf in ("high","low") else None` is closed by construction, so
it cannot emit a fifth word.
**Cost of leaving it:** it is the one site of a family this branch met four times that the
new agreements do not reach.

## 7. The archive's clean set and the slot's clean set can disagree

`_clean_rows` keeps `row["status"] == "clean"` from the payload; `clean_contributors` —
the `expected_count` the record view passes to `load_export_list` — is `clean_list()`'s
count over the **local** fold. `build_analysis_from_published` is explicitly written not to
assume those populations match.

Probed: removing one published clean wallet from the local fold gives
`slot clean_contributors = 39` against `40` rows written, and the cleaned record view falls
back to capped live rows at `complete=False`.

**Parked** because that fallback is the designed unavailable state behind a marker — not a
stale number presented as live — and item 5's fix makes the divergence require a genuine
population mismatch, which a settled game makes very unlikely.
**Cost of leaving it:** in that rare state the cleaned list degrades honestly instead of
refusing to archive.

## 8. Row 3 — one crash window leaves the cleaned list missing

If a crash lands between the archive and the writes, root can hold the correct new raw list
and no cleaned list until a **new `version_id`** arrives. Explicit degrade, no data loss.

Recorded separately because it does **not** die with the `archived_version` flag: in that
window the flag was never written, and had it been, the retry would return three empty
tuples and the cleaned list would still be missing.
**Cost of leaving it:** capped live rows behind an honest marker until the next publish.

## 9. Doc drift already re-appearing

`docs/curator_published_analysis_PRD.md:178` still writes the fetch policy as
`GET /list/export?link=all` — one parameter, where §3.3 and the code now name four.

Exactly the class of defect items 5–7 of the final fix wave closed, re-appearing within the
same document.
**Cost of leaving it:** the next reader implements from §178 and reintroduces the Critical.

## 10. Smaller, genuinely minor

- `with_optional_suffix`'s docstring says the fit is measured pre-escape; one of its three
  call sites does that and two pass already-escaped strings. Harmless — escaping only
  lengthens — but pick one convention.
- `_analysis_version` reads `published["cluster_count"]`, which `_published_block` never
  writes. Always `None`, never used. Drop the read or add the field.
- On a narrow panel the version label sheds and a bare `as of HH:MM` survives — which can
  now be weeks old, where before the branch the slot was rewritten every 30 minutes.
  Consider shedding the count instead, or abbreviating the version to its date.
- `PRD` §10's fixture table says "~400 wallets" (it is 82) and "~12 clusters" (it is 7).
  The coverage argument still holds; only the numbers are stale.
- `_finish`'s parameters are typed `Any` where the concrete types are already imported.
- `__all__` in `curator_clusters.py` was deliberately not extended with the four new public
  functions.

---

## Suggested order

**9 → 1 → 3 → 5.** Item 9 is a one-line edit that prevents the Critical being reintroduced
from the spec. Item 1 stops a meaningless red training people to ignore reds. Item 3 is the
only one with a real (if small) correctness edge, and it gets cheaper the sooner the hoist
happens. Item 5 is a sentence that protects a load-bearing guard.

Items 2, 7 and 8 are deliberately **not** on that list: each is parked with a reason, and
each would cost more than it buys today.
