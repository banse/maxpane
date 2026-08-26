# Surf launchpad — open follow-ups

Everything here was found during the 2026-08-25/26 five-panel `l` view build and
**deliberately not fixed then**, either because it was out of the owning agent's
scope or because it was correctly deferred. Nothing here blocks: the branch is
merged and pushed at `0059e4c`, suite 5630 green (plus one pre-existing curator
flake, item 10).

Each item carries its evidence so the next session does not re-derive it.
Ordered by what I would do first.

---

## 1. `surf_client` should give `coins` its own failure shape

**Where:** `data/surf_client.py::fetch_launchpad`, `data/surf_models.LaunchpadState.coins`

`coins` is the only log-derived launchpad field with no failure shape. `activity`
and `burnkeepers` arrive as `None` when the sweep failed; `coins` cannot, because
`fetch_launchpad` **derives** it by running `rank_coins` over the sweep's launch
list, and a failed sweep returns `launches=[]` — so an outage arrives as `()`.

`SurfManager._coins_if_swept` currently infers the failure from `launch_count is
None` and is correct, but it sits one layer downstream of where the information
is born. Fix properly: return `coins=None` from `fetch_launchpad` when
`_launchpad_logs` failed, declare `LaunchpadState.coins` optional, then simplify
the manager back to the plain `if coins is None` guard its two siblings use.

Do this one first — it is the root of the Critical the final review found, and
the manager-side inference is the workaround.

## 2. `fetch_burn_fees` wedges permanently at roughly 25 lifetime burns

**Where:** `data/surf_client.py::fetch_burn_fees` (~:2581), `_MAX_BURN_FEE_PAGES = 4` (~:179)

The reader walks `/addresses/{BURN_EXECUTOR_V2}/internal-transactions`
newest-first. Measured on the committed fixture: **39 entries for 5 burns**, ~7.8
legs each. At a 50-row page that is ~25 burns to fill four pages. Past that the
oldest burns can never be priced, `unpriced` never empties, and **every 600 s
sweep re-fetches four pages to learn nothing**. `bridgeToBaseBurnReceiver()` is
permissionless and this panel exists to encourage repeat callers, so 25 is not a
distant number.

Fix: read per-transaction (`/transactions/{hash}/internal-transactions`), bounded
by the rows that actually need a fee, instead of paging the whole address.

## 3. Unattributed burns are indistinguishable from "nobody has burned"

**Where:** `data/surf_client.py::_rank_burnkeepers` (~:646, ~:675), widget `widgets/surf/burnkeepers.py`

`_rank_burnkeepers` skips every row whose `sender is None`, so a cold sweep during
a state-pool outage yields `()` → payload `[]` → the panel renders `no burns yet`.
That is CLAUDE.md's named defect verbatim ("a row whose real negative has no
representable value renders `None` identically for 'we looked and there was
nothing' and 'we could not look'"), and curator's rail shipped exactly it once.

`tests/data/test_surf_client.py:5510` currently asserts the collapsed state as
correct — that test changes with the fix.

The input already exists: the cursor holds the count of rows with `sender is
None`. Crosses client → models → manager → widget, so it is a small task rather
than a patch.

## 4. Hand-edited cursor can wedge the launchpad tier permanently

**Where:** `data/surf_client.py::_coerce_launchpad_resume` (~:934-947)

`burns[*].amount_wei` is bounded for type and sign but not **magnitude**.
Verified: a row with `amount_wei = 10**400` survives coercion, then
`_rank_burnkeepers`' `acc["imd_wei"] / 1e18` raises `OverflowError: int too large
to convert to float`, which propagates out of `fetch_launchpad`, is swallowed by
`_guard`, marks the tier failed — and the poisoned cursor stays in last-good, so
it recurs every sweep until `~/.maxpane/surf_cache.json` is deleted by hand.

The spec promised "a hand-edited cache file with a malformed `burns` entry
degrades rather than crashing"; no test covers a magnitude. The pre-existing
accumulators share the missing bound — this is a new instance of an old class, so
fix the class.

## 5. Hoist the duplicated sanitiser (narrowed)

**Where:** `widgets/surf/{launchpad,launchpad_activity,burnkeepers}.py`

`_TAG_LIKE` + the flatten/strip/clip/escape pipeline exists in three modules,
copied rather than imported because the source file was owned by a concurrent
agent at the time.

**The final review narrowed this correctly:** the shared `len()`-vs-`cell_len()`
bug is *not* equally live in all three. `launchpad.py`'s copy is harmless — its
cells go into a `DataTable` with fixed column widths, which fits CJK correctly.
The copy that bit was `launchpad_activity.py`, and **that one is already fixed**.
What remains is a refactor: hoist into `widgets/surf/_fmt.py`, delete the copies.

Fold in while there: `SurfBurnkeepers.DEFAULT_CSS` declares `height: auto` while
both screen stylesheets override it to `1fr`, and the `DataTable { height: auto }`
override sits in the screen stylesheets rather than in `launchpad.py`'s own
`DEFAULT_CSS` where the `1fr` it overrides lives.

## 6. Markers for `SurfCurveFlow` / `SurfBurnPipeline` — deferred on purpose

They ellipsise in silence, and that muteness is the **only** reason the `l` view's
seam buys three columns of rail margin. Giving the rail's binding panel a
`‹ widen` would let the seam drop to `13:6` and the pin to 135.

**Correctly deferred, and it should stay that way** unless something else forces a
re-sweep: changing it invalidates the premise the 19-seam sweep was run under, so
it costs the whole sweep to save three columns nobody can see (surf's *dashboard*
body needs 143, so no terminal that renders this app whole ever sits at 135–137).
`SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS`' docstring already says "take the columns
back if the rail grows a marker".

## 7. Small correctness items

- **`SurfBurnkeepers._title_text`** appends `‹ widen` without checking it fits, so
  below a rail budget of 20 the title is `BURNKEEPE…` with no marker. It adopted
  `SurfLaunchpadCoins`' padding fix but not the other half of that lesson (the
  ellipsis ate the marker it was warning with). Not reachable at the pinned seam.
- **`_BURNS_COLS = 2`** (`burnkeepers.py:92`) overflows at 100 burns from one
  wallet — plausible for a permissionless call this panel tracks.
- **`COINS_EMPTY = "no coins launched yet"`** renders as `no coins` in the
  8-column TICKER cell, so it reads as a coin named "no coins", not a message.
- **`_launchpad_feed_from_logs`' `now_ts` parameter is dead** (`surf_client.py`
  ~:578) — never referenced; age comes from `head`. Every call site passes it.
- **`price_eth` is in `SURF_ROW_KEYS["launchpad_coins"]` with no renderer** —
  `mcap_eth` is computed from it in the client, so the row copy is carried and
  cached for nobody.

## 8. Tests that need attention

- **`test_the_eth_column_shows_the_fee_not_the_value_sent`**
  (`tests/widgets/test_surf_burnkeepers.py:74`) asserts `"0.001" not in text` at
  the *widget* layer, where the transaction's value is not in the row shape at
  all. It cannot fail for the reason it names. The real claim lives in
  `test_every_real_burn_prices_below_the_value_its_caller_sent`
  (`test_surf_client.py:5108`) and is fine there.
- **Two tests keep the buggy per-segment composited join** —
  `test_burn_pipeline_shows_ready_only_when_ready` and
  `test_burn_pipeline_unknown_is_not_ready`. Harmless today (whole-blob substring
  assertions), but the correct per-strip form now sits in the same file, so fix
  them before someone copies the wrong one.
- **`launchpad_activity._MAX_ROWS = 40` mirrors `surf_client._MAX_ACTIVITY_ROWS`**
  with nothing enforcing the mirror, while the sibling pair has
  `assert LAUNCHPAD_RENDER_LIMIT == MAX_COIN_ROWS == 10`. Same idea, one of two
  instances guarded.
- **`_region_text` raises `IndexError`** (`tests/screens/test_surf_screen.py`
  ~:4153, `strips[y]` unguarded) when a widget's region runs past the composited
  strips — screens under ~20 rows. Not hit by any current sweep; any future
  short-terminal sweep trips it.

## 9. Stale docstrings

- `widgets/surf/launchpad.py:222` says `SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS` "has
  not been re-swept against this change" — it was, in `601ece8`/`433a538`.
- `widgets/surf/launchpad.py:196` contradicts itself about the scrollbar flag
  clearing at 92 vs 93 (inherited from the 95/93 era).
- `tests/data/test_surf_manager.py:3692` still quotes `LAUNCHPAD_RENDER_LIMIT` as
  "(20)"; it is 10.

Both `launchpad.py` ones are affirmatively wrong, not merely stale — one tells a
future reader a re-sweep is still owed. Fold into the next touch of that file.

## 10. Pre-existing curator flake — not this branch's

`tests/screens/test_curator_screen.py::test_screen_adds_removes_and_deduplicates_custom_collection`
fails **4 times in 12 isolated runs** on identical code. It asserts the
duplicate-collection error `already available above` but intermittently gets
`NFT contract must be a 20-byte 0x address` — the typed `Input` has not been
delivered through Textual's message pump before the submit is asserted. A missing
pause/await, not a logic bug.

Verified this branch touched no curator file (`git log --name-only` over the range
is empty), so it predates the work. Worth fixing regardless: a suite with a 1-in-3
flake is a suite people learn to re-run instead of believe.

---

## Suggested order

1 → 3 → 2 (correctness in the data layer, root first), then 4, then the cheap
sweep of 7 / 8 / 9 in one pass over the files they touch, then 5. Leave 6 unless
something else forces a re-sweep. 10 is independent and can go any time.
