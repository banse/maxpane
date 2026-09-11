# pool4 branch — follow-ups

Findings raised by a work package in a file that package did not own. Per CLAUDE.md a package
reports and does not fix, so each one is named here with its evidence and is scheduled like any
other work. None of these is fixed on this branch.

## F1 — `widgets/markup_safety.visible_len` measures characters, not cells

**Found by:** WP2. **Severity:** repo-wide, latent. **Not fixed here, deliberately.**

`visible_len` is the repo's designated "measure a markup string the way the terminal will"
helper, and it ends in `len()`. Reproduced independently:

```
visible_len("[bold]海豚[/]")  →  2
cell_len("海豚")              →  4
```

Several existing surf width tests assert with it, which makes those assertions **character
counts wearing a column count's name** — the same defect class WP2 was created to fix, one layer
further out.

**Why it is not fixed on this branch.** `markup_safety` is imported across dashboards, and
correcting it would move width pins outside surf, on a branch that is on a deadline and whose
own layout sweep (WP8) has not run yet. Bundling a repo-wide pin movement into it would make
this branch's own width evidence unreadable. It needs its own change, its own sweep across every
affected dashboard, and its own both-directions width tests.

**When it is fixed**, the fix is not just `cell_len` — it is re-running every width sweep that
asserts through `visible_len` and re-measuring the pins those sweeps bind.

## F2 — `widgets/surf/_fmt.long_addr` measures characters, not cells

**Found by:** WP2. **Severity:** surf-local. **Not fixed here** — no work package owns `_fmt.py`.

`long_addr` guards with `if len(s) <= 17: return s`, so a 17-character CJK string passes through
as a "17-column" window and paints 34 against `ADDR_COLS = 17`. It feeds the unknown-counterparty
branch of the field `activity.py` refuses to shrink, so `_rowfit`'s new `cell_len` budgeting
sheds *other* cells around an over-wide window rather than the window being correctly sized in
the first place.

The rows are fitted now, so nothing clips — this is a correctness gap in the formatter, not a
live layout break. Schedule with F1: they are the same bug in two helpers and the fix should be
one pass with one sweep.

## F3 — three hook event topic0s remain unresolved

**Found by:** research + WP1. **Severity:** cosmetic.

Three of the hook's event signatures survived a ~45,000-candidate and then a further
143,640-candidate keccak pre-image sweep. They keep operand-shaped names in
`docs/imd_pool4_mechanics.md` and in the decoder. Nothing depends on the human-readable name —
the decoder keys off the topic0 constant — so this is a naming gap, not a functional one. It
closes for free if the hook is ever verified on Etherscan/Blockscout.

`0xbdf538ed…` (the "retired backstop" topic named in the mechanics doc) does not appear in
launch 3 at all, and no guessed 32-byte tail has been recorded for it.

## F4 — `evm_abi.decode_uint("")` returns `0`: a sentinel factory in a shared module

**Found by:** WP6. **Severity:** latent, repo-wide. **Not fixed here** — no package on this branch
owns `data/evm_abi.py`.

`decode_uint` returns `0` for an empty payload. That is precisely the shape CLAUDE.md's
failed-read rule warns about: an outage becomes a zero, the zero gets persisted, and the
corruption outlives the outage.

**It is clean today, and WP6 checked rather than assumed** — every call site in `surf_client.py`
(lines 225-230, 272-273, 354-357, 433-438, 449, 475) guards with an explicit length check first.
WP6's own client routes every decode through `P.answered` and makes `_uint_or_none` the sole door
into `decode_uint`.

Filed so that the guarding is understood as **load-bearing rather than incidental**. An unguarded
call site added later is silently wrong, and nothing in the module says so. The fix is either a
`None`-returning sibling or a raise on empty; both need a sweep of every existing call site, which
is why it is not being done mid-branch.

## F5 — `Pool4Discovery.source_tx_hash` is never populated on the adopted path

**Found by:** WP7. **Severity:** cosmetic, but it defeats a documented intent.

`Pool4Client.verify_hook` does not set `source_tx_hash`, and the manager does not pass
`discovery_verdict`'s `source_tx_by_addr`. So an adopted mainnet hook cannot cite the self-post it
came from, which is what the model's own docstring says the field is for.

No payload key is affected — `source_tx_hash` is not in `POOL4_KEYS`, so nothing on screen is
wrong today. But the field exists precisely so a reader can audit *which* announce post produced
the address the dashboard is now trusting, and on a view whose discovery gate is its security
boundary that provenance is worth having. Closing it means threading the tx hash from
`candidate_addresses` through `verify_hook` into the verdict, and then deciding whether the
HATCHES detail line shows it.

---

# Review findings (WP9 + orchestrator verification, 2026-09-01)

## W1 — `reconcile_counters` is built, tested, and never wired. CONFIRMED

**Found by:** WP9. **Verified:** `grep -rn reconcile_counters maxpane_dashboard/` returns its
definition and its `__all__` entry in `data/surf_pool4.py` and **nothing else**. Zero call sites.

The plan's §5 **R1 control (c)** names this as the day-one detection mechanism for the central
risk of this build — that the hook's interface was *recovered from bytecode selectors* and could be
wrong on mainnet. Three wei-exact reconciliations (Σ`FeeCollected` = `totalFeeToken`,
Σ`ClaimsSettled[0]` = `totalBurned`, Σ`ClaimsSettled[1]` = `totalRewarded`) were to be computed and
the *disagreement published* rather than the assumption. A9 corrected only the **fourth**, ETH
check; it never retired these three.

What exists instead: `surf_pool4.reconcile_counters` implemented correctly with its own tests, a
real committed fixture (`counter_reconciliation.json`) captured for it, and
`test_surf_pool4_client.py` reasoning about it as a downstream consumer that does not exist. And
pulling the other way, `test_surf_manager_pool4.py:1081` pins
`assert not [k for k in POOL4_KEYS if "mismatch" in k or "reconcil" in k]` — a test asserting **no**
reconciliation key exists at all.

So the plan requires the control and a test forbids its output. That contradiction is the finding.
A wrong operand order in one of the three permanently-unresolved topics, or a getter that answers
something else on mainnet, currently has **no on-screen or logged signal**.

**Two honest resolutions, and the team must pick one:** wire it into `_pool4_payload`, decide which
output becomes a `POOL4_KEYS` member and how THE SPLIT renders a disagreement — or formally retire
the control, and rewrite R1 and that test's docstring to say `pool4_split_drift_bps` supersedes it.
What must not stand is the current state, where the plan and the suite disagree in silence.

## W2 — RETRACTED. The rule IS pinned; the finding was a grep artefact

**Raised by:** orchestrator. **Refuted by:** WP9. **Verified: the test exists, runs, and passes.**

`tests/screens/test_surf_screen.py:6704 test_exactly_one_pool4_child_per_column_carries_the_fr`
asserts, per column: exactly one `1fr` child (so it catches **two** as well as **zero** —
bidirectional), that the growing child carries a `min-height`, and that the column itself has
`overflow-y: auto` and `scrollbar-gutter: stable`. That is plan §3 WP8 step 6's rule in full, for
both columns, in one test. It reads `minimal.tcss` — "the copy that actually renders" — rather than
`compose`, deliberately, because a stylesheet edit can break the rule without touching a line of
Python.

**Why I got it wrong, recorded because the method matters more than the mistake.** I concluded
absence from `grep -n pool4 <file> | grep -i "1fr\|min-height\|shrink"` returning nothing. Chained
greps keep only lines containing **both** substrings. The line naming the test carries `pool4` but
not `1fr`; the lines carrying `"1fr"` and `"min-height"` do not carry `pool4`. A well-formatted
multi-line test can never satisfy both on one physical line, so the query could only ever return
nothing — it was incapable of finding what it was asked to find.

**A grep that returns nothing is not evidence of absence until you have shown the grep can find the
thing when it is present.** That is the same defect class as this branch's tests-that-cannot-fail,
committed by the person auditing for them.

## W3 — RESOLVED by measurement. Forced on ROWS, not width. Both earlier framings were wrong

**Raised by:** orchestrator (unreported deviation). **Justification disputed by:** WP9 (circular).
**Settled by:** WP8, by rendering the PRD arrangement rather than arguing about it.

| arrangement | width pin | binder @ pin−1 | silent clip 80..105 | **height pin** | HATCHES cut unmarked |
|---|---|---|---|---|---|
| as built (HATCHES left) | 106 | `SurfPool4Flow` | none | **43** | never |
| PRD §3, HATCHES floor 21 | 106 | `SurfPool4Flow` | none | **54** | **rows 54–55** |
| PRD §3, HATCHES floor 23 | 106 | `SurfPool4Flow` | none | **56** | never |

**The width is identical in all three.** Same pin, same binder, nothing clipping unmarked anywhere.

* **My "forced on width" was wrong** — and WP9 was right that quoting HATCHES's 49 against a
  43-column rail is circular, since the rail is only 43 *because* HATCHES was moved out.
* **WP9's "margin-optimising choice" was also wrong.** The ten columns of rail margin are real but
  **moved no pin**, so they are a consequence of the swap, not a reason for it.
* **The real reason is rows.** The rail is the taller column and sets the height pin, so a
  payload-sized panel in the rail puts a payload-sized number into it. HATCHES in the rail wants
  **54** rows floored at today's lever count and **56** at the cap it may legitimately reach,
  against **43** as built. The dashboard body's marker lights at 36 and the `l` body's at 31, so 54
  would make POOL4 the one view on this screen that does not fit a terminal the other two do.
* **And the cheaper PRD variant is not honestly available:** floored at 21, HATCHES gets 21 rows
  against 23 of content at heights 54–55, with `‹ taller` **dark**, because the rail fills its
  allocation exactly and never overflows. A silent loss, in the panel whose entire subject is what
  the reader is being asked to trust.

The three contradicting comment blocks are corrected, each recording what it used to say and that
it drifted. `SURF_POOL4_FULL_LAYOUT_COLUMNS` now carries the **negative** result explicitly — that
width does not justify the swap and that the rail's 43 is circular if quoted as a reason — and the
same warning sits beside `POOL4_RAIL_NEED` in the test module, where that literal actually lives.
The PRD is annotated rather than rewritten.

**The process finding stands and is the durable lesson:** the swap was correct, and *nobody could
tell*, because the one artefact that would have settled it — a measurement of the alternative — was
never taken until it was disputed. WP8's own verdict: had it reported the swap at the time, the
width justification is the claim it would have had to withdraw.

## W5 — `analytics/surf_signals.py` says "nine detectors" in three places; there are ten

**Found by:** WP10. **Verified.** Lines 4, 18 and 584 all say "nine"; CLAUDE.md's dashboard table
says ten, and `thread` is the one the prose omits. **Pre-existing, unrelated to pool4** — the README
half was corrected by WP10 (its own file); the three code docstrings were not, correctly, since no
package on this branch owns that file.

## W6 — CLAUDE.md's test counts are stale

It states 5,630 tests. The green full-suite run on this branch was **6,550**. WP10 deliberately did
not guess a replacement number; it should be set from a verified run. `sybilkit`'s 428 is untouched
by this branch and presumably still correct.

## W7 — the 43-row requirement has never been measured against a real terminal

**Found by:** WP10, flagged rather than asserted. `SURF_POOL4_FULL_LAYOUT_ROWS = 43` is the tallest
requirement in the repo. The *columns* side of "does a laptop at the 17 pt maxpane forces on launch
actually clear this" is answered in the terminal-layout skill (~169 columns); the **rows side is
not**. If a common laptop does not clear 43, the honest sentence belongs beside the constant. This
wants a measurement, not an estimate.


## W4 — the review could not execute anything. LIMITATION, not a finding

WP9 had no shell: it could not run pytest, could not flip a constant and watch a test redden, and
**could not independently re-verify a single mutation-evidence claim**, which A21 explicitly asks a
reviewer to do after the harness-swap incident. It stated this up front rather than downgrading its
rigour silently, which is the right call.

Consequence: every "proven to bite" table on this branch remains **self-reported**. The packages'
own evidence is detailed and internally consistent, and the orchestrator independently re-ran
targeted suites and one mutation (WP0's zero-default guard, which reddened exactly the expected
test). But an independent adversarial re-run of the discovery gate's mutations has **not** happened.
That is the largest remaining unknown on this branch, and it sits precisely on its security boundary.

## S15 — the mainnet adoption has a ~64-day shelf life, and the fix is F5

**Found by:** WP7, disclosed as the stated cost of its S3 fix. **Measured by orchestrator.**

S3's fix is right: the persisted cache no longer nominates a candidate, because provenance — a
transaction signed by the announce wallet — is the only gate an attacker cannot forge, and the
cache bypassed it. But provenance now has to be re-established from the channel **on every cycle**,
and the channel window is `FEED_ITEM_LIMIT = 25`.

Measured against the real channel: 43 transactions over 107 days = **2.55 days/post**, so 25 rows
turn over in **≈64 days**. Two months after pool4 is announced, the self-post naming the hook falls
out of the window, the adoption lapses, and every panel reverts to `SEPOLIA`.

WP7 handled this honestly — it is *detected and reported* (`_pool4_lapsed_adoption`, with a detail
line naming the address and saying the view has fallen back to the vendored testnet deployment)
rather than failing silently, which is the difference between a limitation and a bug. But a view
that works for two months and then quietly stops showing mainnet is not what this was built for.

**The right fix is F5, which was filed as cosmetic and is not.** Persist the **source transaction
hash** of the self-post, and re-establish provenance by fetching *that one transaction* and checking
`from == to == announce` and that its calldata still names the address. That is:

* **unforgeable** — the chain is the authority, not the cache file, so it does not reintroduce S3;
* **cheap** — one `eth_getTransactionByHash` per cycle, against a hash the cache merely *points* at;
* **permanent** — a transaction does not age out of a window the way a feed row does.

This needs `source_tx_hash` threaded from `candidate_addresses` through `verify_hook` into the
verdict — exactly the gap F5 and WP7's D6 both describe. Deepening the channel window is the
inferior alternative: it buys time rather than closing the hole, and a bigger window is a bigger
fetch on every tick.

Until then the honest statement is: **the adoption is good for about two months per announcement,
and says so when it lapses.**

## S16 — do NOT normalise channel text before `ADDRESS_RE`. The bidi defence is positional

**Found by:** WP1, auditing its own fixture note. **Verified by orchestrator.**

`announce_adversarial_markup` was right by accident, and the accident is load-bearing. The bidi row
yields no candidate **only because U+202E sits between the `0x` and the hex**, splitting the token
so the regex cannot match it. Reproduced:

```
as committed (U+202E after 0x):      ADDRESS_RE.findall(...) -> []
if control chars are stripped first: ADDRESS_RE.findall(...) -> ['deadbeef…dead2840']
                                     flag word 0x2840,  passes the flag gate: True
```

So the protection is **positional, not semantic**. A future maintainer who adds a reasonable-looking
"sanitise the announce text before scanning it" step — strip control characters, NFKC-normalise,
collapse whitespace — silently re-arms this row: the address is extracted, masks to `0x2840`, clears
the flag gate and reaches a getter call. It would still fail `token()` today, but that is the
forgeable gate, not the boundary.

**The rule: `ADDRESS_RE` must see the raw calldata text.** Any normalisation belongs *downstream* of
candidate extraction, never upstream of it. This pairs with WP3's S11 decision (rejecting `0X`
rather than tolerating it, evidenced by a scan of the channel's complete history showing 8 `0x` and
0 `0X`) — on an attacker-writable channel, every spelling you accept is one more form that renders
differently than it parses.

WP1 has rewritten the fixture note to say this, since a note claiming the row proves something it
proves for a different reason is worse than no note.

## S17 — the counter control has a ONE-DAY working life until the sums accumulate forward

**Found and disclosed by:** WP3, while implementing W1. **Not a defect in the wiring — a limit on
what the wiring can achieve.**

W1's three identities are cumulative-counter versus sum-of-**all**-logs, but the sweep reads a
trailing `POOL4_LOG_WINDOW_BLOCKS = 7_200` (~24 h) window. So **from roughly a day after the hook is
deployed, the sums are short by everything preceding the window and the control is permanently
`window-limited`** — it detects nothing.

That is honest rather than broken: `window-limited` is a first-class state, explicitly *not* a pass,
so the panel says the control did not run instead of implying health. And the control still does
real work in the window that matters most — while the mainnet hook is young is exactly when a
decoder recovered from `PUSH4` selectors, against an unverified contract with three unresolved
event signatures, is most likely to be caught cheaply.

But a one-day detector is worth having and **not worth relying on**, and the docstring now says so.

**The fix** is to accumulate the sums forward from deployment and persist them, on the
`LaunchpadState.cursor` precedent — *a total cannot be recovered from its newest addend*. That is a
cache-shape change (a running total in `SLOT_POOL4`, seeded at the genesis block and advanced per
sweep) and it was deliberately not attempted mid-wave.

**Note the interaction with S15/F5:** both open items are now "persist one durable fact so a
cheap check keeps working past its window" — the self-post hash for provenance, the running sums
for the counters. Whoever picks one up should look at the other.

**And note what makes this checkable at all** (WP3): completeness is decided from the log set
itself, not from block arithmetic. `Ownable`'s constructor emits `OwnershipTransferred(0x0, owner)`
exactly once and no log of the contract can precede it, so `logs_reach_genesis` asks the logs rather
than trusting a window constant that goes stale when someone tunes it. Verified in the corpus:
`flow_logs_full` carries that log as the earliest of its ninety (block 11,609,650, `previousOwner`
zero); `flow_logs_mixed`'s sixty-block window carries none, and its sums are genuinely short. The
zero `previousOwner` is load-bearing — a later `transferOwnership` emits the same topic0, so testing
the topic alone would read an ownership change as a birth certificate.

## S18 — the adopted discovery detail's tx citation never reaches the screen

**Found by:** WP8, during the D8 width check. **Not a layout defect** — the pin did not move and
nothing clips unadvertised.

`pool4_hatches._discovery_markup` windows the detail to its **tier's** width — a constant 35 cells,
`FULL_WIDTH - indent` — not the panel's. Measured across terminals 106..260 the detail has exactly
**one** rendering:

```
adopted 0xa1B997A9861B2b8aC17B4c61…
```

So the `· tx 0x…` citation and the "flags, token and five getters agree" evidence **never render at
any width**. No marker is lit, and none should be — `‹ widen` promises that columns would buy
something back, and here they would not.

**Why it matters anyway.** F5 was implemented specifically so an adopted verdict could name the
transaction it rests on, because after A27 that self-post is the *only* unforgeable evidence in the
design. The hash is persisted and an auditor can reach it in the slot, so the audit trail exists —
but the reader cannot verify an adoption from the screen, which was the point of citing it.

This is a **content** question for `widgets/surf/pool4_hatches.py` (WP4) and the producer, not a
width one: either the rendered form is shortened so the citation fits (a truncated hash is still a
pointer — the first 8 characters find the transaction on any explorer), or the citation moves to a
line of its own, or the detail is composed with the tier in mind rather than truncated after the
fact.

## S19 — the counter control only ever lives on a machine that ran the dashboard daily

**Found and disclosed by:** WP7 (its D10), implementing S17. **A consequence of a deliberate trade,
not a defect.**

S17's accumulator carries the counter sums forward from the genesis block, and **continuity is
enforced by discarding**: a gap wider than the log window (`POOL4_LOG_WINDOW_BLOCKS`, ~24 h) throws
the accumulator away rather than patching it. WP3's reasoning stands — a total short by a missed
sweep is indistinguishable from one short by a decoder bug, and *losing two months of accumulation
is cheap; a total that says `reconciled` when it means `probably` is not.*

The operational consequence: **MaxPane closed for more than ~24 h discards the accumulator, and
once the hook is older than the window it can never reseed.** The control is then permanently
`window-limited` on that machine, forever. So it is live only for someone who has run the dashboard
at least daily since the hook was deployed.

That is honest — `window-limited` says the control did not run, and never claims health — but it
means the day-one detector is, in practice, a detector for people who were there on day one. Worth
a sentence in the user-facing docs rather than being discovered as a surprise.

**Two smaller notes from the same round, recorded so they are known limits rather than assumptions:**

* **D9:** `fetch_transaction` is the only pool4 client method whose *absence on a test double* is
  indistinguishable from an outage — `_guard` turns `AttributeError` into `None`, which means HOLD.
  A double missing the method silently exercises the hold path. Worth knowing when WP8 or WP11
  writes one.
* **D11:** the accumulator is cache-supplied evidence and nothing can recompute two months of sums.
  What bounds a forgery is **alignment**: a forged total is believed only while its cursor equals a
  block the forger cannot predict, so it must be rewritten in lockstep with the chain and perishes
  on its own.

## S20 — the two halves of the cap mechanism compute in two different modules

**Found and disclosed by:** WP7 (its D18), implementing `pool4_cap_headroom`.

```
floor half:   pool4_floor_distance  =  reserve − floor   ->  data/surf_pool4.py
ceiling half: pool4_cap_headroom    =  cap − reserve     ->  data/surf_manager.py
```

One mechanism, two modules, and **the operand order flips between them** so both read positive when
healthy. That flip is the sign trap WP0 caught and WP7 built three defences against — and it is
exactly the kind of thing that survives better with both halves adjacent under one docstring, where
a reader meets the warning at the same moment as the analogy that would mislead them.

WP7 implemented it where it was scoped rather than moving it unilaterally, which was right. Worth
resolving once the contract settles.

## S21 — a `**_kwargs` widget can swallow a dispatched key with every guard green

**Found by:** WP8, by rendering rather than reading. **Both instances fixed; the hole is not.**

`pool4_cap_headroom` was declared by the contract, dispatched by the screen, and **silently absorbed
by `SurfPool4Ratchet`'s `**_kwargs`** — and so was `pool4_reward_path` on `SurfPool4Hatches`. Every
existing guard stayed green: the contract sweep asserts each key has exactly one *renderer*, and
`**_kwargs` accepts everything, so it cannot distinguish **rendered** from **accepted and dropped**.

That is how a key three packages spent three rounds arguing about reached the screen as a no-op.

**The only check that can tell them apart is WP8's:** zero the key through the *real* screen and
expect a composited line to change. That is CLAUDE.md's "assert against composited output" rule,
arrived at from a new direction — it was written for markup that never reaches a pixel, and it turns
out to be the only way to catch a kwarg that never reaches a renderer.

`_KEYS_THE_WIDGET_SWALLOWS` now holds the two instances with a test that fails if a **third**
appears *or* if either is fixed. The dispatch was deliberately left in place while they were open,
because removing it would have made the widgets look correct.

**The generalisation worth acting on:** any widget taking `**_kwargs` — which is all of them, by
contract — can absorb a key forever. A render-and-diff sweep over every key, not just the two known
instances, is the durable fix.

## S22 — a both-directions width test is the single most collision-prone mutation in this repo

**Found independently by WP8 and WP4, who landed on the same conclusion from different files.**

A31 says two mutations of equal file size in the same second make the second run the first's
bytecode. The question nobody asked is *which mutations are most likely to collide*. The answer is
uncomfortable, because it is the shape this repo mandates:

> **"set the pin one too low" and "set the pin one too high" differ by a character, not a byte
> count.**

So a both-directions width or height guard — which `.claude/skills/terminal-layout/SKILL.md`
**requires** for every pin, because a one-directional test once missed a defect that shipped —
produces two mutations of *identical* size, run consecutively, well inside a second.

Measured, in two independent batteries:

* WP8: four mutations in **one** 130,183-byte group — height-low, height-high, width-low,
  width-high. All four pin guards.
* WP4: its pin-low/pin-high pair in the same 20,798-byte group.

**Under a shared bytecode cache, a both-directions pin test is testing one direction.** Both
packages' guards still bit once the cache was made per-mutation, so the conclusion held — but until
that run it held by luck.

**This is not pool4-specific.** Every dashboard in this repo has width pins, the skill requires each
to be swept in both directions, and any battery mutating those constants in place is exposed. The
durable fix is per-mutation bytecode isolation in every harness, not a note on this branch.

## S23 — the `**_kwargs` blind spot needs a repo-wide render-and-diff sweep

Recorded here as the generalisation of S21, in WP4's words: *a signature check alone would have been
the same blind spot wearing a different costume, which is worth saying because the obvious fix looks
like a signature check.*

`**_kwargs` is **mandatory on all five pool4 panels by contract** — and the same pattern is used by
widgets across this repo. So any contract key can be declared, dispatched, and silently absorbed
with every signature-shaped guard green. Two instances were found here only because someone rendered
the screen and diffed the output.

The durable fix is a render-and-diff sweep over **every** key rather than the two known instances:
zero the key through the real screen, expect a composited line to change. That is CLAUDE.md's
"assert against composited output" rule reaching a case it was not written for.

---

# Review against the official docs (pool4.imd.fun/docs, 2026-09-02)

The protocol's own documentation was read in full and compared against what this view implements
and claims. **What we derived from the chain is correct** — 85/15, the 30/40/30 subdivision giving
4.5 / 6.0 / 4.5, `capFloor` 1,000, `capDecay` 1,000/day, drip 86.4/day with 1h catch-up, 1-block
unstake hold, the 1% swap fee, and every address. The findings below are about **framing and
completeness**, and two of them put a wrong statement on screen.

## D1 — HIGH. Bonding and nodes are RESERVES, not live products, and we imply otherwise

The docs are explicit, three times over:

> "Bonding and node allocations are tracked on-chain while those programs are being built —
> **reserves, not live products**." (§05)
> "The reserve is live; **the bond market isn't**." (§07)
> "**The node program isn't live.** Its IMD is tracked on-chain as `heldNft`." (§08)

Bonding opens at **$4 per IMD**; until then nothing is sold and the reserve only grows.

What we say now is wrong in both directions. `surf_manager.py:3800` renders
`no bond contract is named by the hook` — literally true of the *hook*, but a reader after the
launch reads it as "bonding does not exist", when 6% of every retired batch is accruing to a live
reserve inside `RewardDistributor`. And the README was updated this session to say bonding is
"live at 40% of the reward share", which reads as *the bond market is open*. It is not.

The honest statement is three-part and we have all of it: the **share** is live (40% of rewards),
the **reserve** is live and readable (`heldBonding`), and the **market** is not — it opens at $4.

## D2 — HIGH. Our APR is the delivery rate, and the protocol's is the flow

`implied_apr_pct` is `drip_per_day × 365 / TVL`, and `pool4_vault.py` opens by asserting the yield
is *"rate-limited, not flow-limited"*. The docs say the opposite about which number is the yield:

> "The APR on the stake page is trailing and real: the IMD the market **set aside for stakers** over
> the last seven days … annualised against total staked. **The dripper's rate is only a cap on how
> fast that reaches the vault.**" (§06)

So the entitlement is the **flow** (4.5% of retired batches); the drip is a **delivery cap**. Ours is
neither: with a deep backlog it badly *understates* what stakers have earned (Sepolia's backlog was
a year deep), and with an empty one it *overstates*, because you cannot drip what has not arrived.

The line already says `drip rate ÷ TVL`, which is honest labelling — the defect is calling it
**APR** beside a site that publishes a differently-computed APR under the same word, and the module
docstring asserting the yield *is* rate-limited. The cheapest correct fix is to stop calling ours
APR. The better one is the trailing-flow figure the docs describe, which we have the inputs for.

## D3 — MEDIUM. `rewardShareBps` has an owner-tunable ceiling we do not surface

Parameters (§11): **"Burn / rewards 85% / 15% · rewards ≤ 30%"**. So the reward share is
owner-tunable up to **3000 bps**, double today's 1500. That is a trust surface — the burn could be
halved by policy — and HATCHES exists to show exactly this class of power. We show the *current*
value and not the bound.

## D4 — MEDIUM. Buy-wall mechanics are documented and we model only the position

We read `backstop()` and `refTick()` and render *centred / drifted*. The docs give the mechanism:
the wall's floor **drops to a new low immediately, then crawls up ~4%/day** (400 ticks) against a
**block-lagged reference** stepping 200 ticks ≈ 2%/block — deliberately, so "a one-block yank can't
drag the protocol's ETH with it". Rebalance threshold **0.1 ETH**, tip **≤ 0.002 ETH and ≤ 1%**.
Our tri-state is not wrong; it just answers less than the chain will tell us.

## D5 — LOW, but it is the headline the RATCHET panel is missing

> "**Expected annual burn is about 75% of outstanding supply**" (§06)

That is the single number that makes the ratchet legible, and it is the protocol's own estimate.

## Confirmed by the docs, worth recording as agreement

* `BurnExecutor` bridges to Base where `BaseBurnReceiver` destroys the tokens — **the burn is not on
  mainnet**, which is why WP1's finding that its balance is *queued* rather than *burned* was right,
  and why the Sepolia `balanceOf(0xdEaD)` identity does not transfer.
* The trim **removes liquidity instead of swapping**, so it does not move the price — matching what
  we decoded from the `ModifyLiquidity` calls before any of this was published.
* `closeMarket` "withdraws the entire position at any moment … holders are trusting the owner not
  to use it otherwise. The owner should be a multisig or a timelock." Our HATCHES shows the power;
  the docs supply the sentence explaining why it matters.

---

## D6 — MEDIUM, and it belongs to the **FWA** dashboard, not surf

Found 2026-09-11 while researching the `4` market view with the `pool4hook-research` skill.

The `CappedBurnHook` is **not IMD-only**. A permissionless `CappedBurnLauncher` at
`0x80587937a883743e67bB11dab356F60e4656C40d` lets anyone open a capped-burn market for any token, and
it has opened **three**, two of them for **FWA** — MaxPane's own dashboard #3:

| # | token | hook | ETH in position | burned to date |
|---|---|---|---|---|
| 0 | P4F | `0xd0ef…a840` | closed | 0 |
| 1 | FWA | `0x40f9…e840` | 0.080 ETH | 2,697.79 |
| 2 | FWA | `0x087a…a840` | 7.521 ETH ($19,586) | **316,182.22** |

Neither the FWA research (`docs/fwa_game_mechanics.md`) nor the FWA dashboard knows this exists. A
capped-burn market retiring 316k FWA against a live position is material to an FWA reader, and none
of it is on screen anywhere in this repo.

**Deliberately out of scope for the surf `4` view** (`docs/surf_pool4_market_PRD.md` §2): surf is
surfsurf.eth's tracker and IMD is its subject. Making the pool4 body market-agnostic would also buy
the reference-pool *discovery* cost the skill warns about — several hundred `eth_getLogs` calls over
public nodes unless the pool is pinned per market.

**Recommended next step:** scope it as FWA dashboard work, not surf work. Note the hook addresses
share the mined `…840` vanity tail and the same `0x2840` low-14-bit flag word, so the fingerprint and
provenance reasoning in `docs/imd_pool4_mainnet.md` transfers — including the part where the
fingerprint is *forgeable* and provenance is the only unforgeable gate.

---

## D7 — RESOLVED. The venue gap was never a tool inconsistency; it is volatile

Closes the open item at `docs/surf_pool4_market_PRD.md` §10.1 / §8.3.

The `pool4hook-research` skill appeared to contradict itself on how much dearer IMD is on the hook
pool than on the hookless reference pool: `state` said **+1.5%**, `share` said **+0.2%** twenty-eight
blocks later, and `depth` implied **~1.45%** from 145 ticks. That looked like three derivations of one
number and was filed as unresolved.

**It was not.** A third capture, at block 25955365, put the hook at tick **68181** and the reference at
**68180** — one tick apart, a gap of **−0.01%**. The reference pool had moved 161 ticks while the hook
moved 15. The gap is real, it is time-varying, and it traverses its whole observed range within an
hour:

| observation | hook tick | reference tick | gap |
|---|---|---|---|
| `state`, first capture | 68196 | 68341 | +1.46% |
| `share`, +28 blocks | — | — | +0.2% |
| block 25955365 | 68181 | 68180 | **−0.01%** |

**Two consequences, both already designed for:**

1. **Reading both ticks at the same block is not pedantry, it is the whole method.** At this volatility
   a one-block skew invents over a percent of gap from nothing. `venue_gap_pct` takes both ticks and
   the client batches both `getSlot0` calls into one round — PRD 8.3.
2. **The `cheaper pool` signal would have stayed silent at every one of these observations**, because
   both pools charge 1% and nothing observed cleared the 2% combined-fee threshold. That is the
   designed behaviour and it is now empirically supported rather than merely argued: a reader told to
   switch venues over any of these gaps would have paid more in spread than the gap was worth.

**A claim to retract.** "Buying on the hook pool costs you +1.5%" was reported as a headline user-facing
finding while scoping this view. It was never actionable — the gap sat inside the no-arbitrage band at
every measurement taken.

## D8 — The depth ladder math agrees with the independent implementation exactly

`analytics/surf_pool4_depth.py`'s constant-liquidity math, run at the oracle fixture's inputs,
reproduces the skill's entire sell-side ladder to the penny (0.28 / 1.01 / 2.24 / 4.82 / 7.57 / 13.73
ETH at −2/−5/−10/−20/−30/−50%), and `eth_between(band_liquidity, band_lower, MAX_TICK)` returns
**24.509 ETH**, matching the chain's own `backstopPrincipal()` exactly. Only −1% differs, 0.12 against
0.11 — second-decimal rounding.

Recorded because the agreement is the *evidence*, not the test: two independent implementations, one
in TypeScript by the protocol's author, arriving at the same numbers from the same chain state. This
is the check that would have caught the `0x840` / `0x2840` flag error on day one.

---

## F6 — the `4` body loses a ladder rung at 32 rows with `‹ taller` dark

**Found by:** WP10, while sweeping the market body's height. **Severity:** surf-local, one
terminal height. **Not fixed here** — the market body's CSS belongs to WP7, and a package that
fixes what it finds reviews its own work by the end of the pass.

At **32** rows — one under the measured pin `SURF_POOL4_USER_FULL_LAYOUT_ROWS = 33` — the
`IF IMD FALLS` panel paints eight of its nine lines. The line it loses is the **`-50%` rung**, the
deepest quote the panel makes, and the screen-wide `‹ taller` marker is **dark** while it happens.
Measured, not reasoned:

| rows | `SurfPool4UDepth` height | painted lines | `-50%` on screen | `‹ taller` |
|---|---|---|---|---|
| 31 | 20 | 2 (the body scrolls) | no | **lit** |
| 32 | 8 | 8 | **no** | dark |
| 33 | 9 | 9 | yes | dark |

**Why the marker cannot see it.** `SurfScreen._rail_is_cut` asks the containers named in
`_SCROLL_COLUMNS` for `show_vertical_scrollbar`, and `MODE_POOL4_USER` names
`#surf-pool4-user-body` and `#surf-pool4-user-rail`. Neither is the thing that overflowed: the
`DataTable` *inside* `SurfPool4UDepth` scrolls, painting its own two-cell nub, and a table
scrolling inside a panel is invisible to both containers. This is the 2026-08-25
missing-`_SCROLL_COLUMNS`-entry defect's cousin, arriving by a route that adding an entry cannot
close.

**Why it is not simply "the DataTable scrolls, like FLOW's RichLog does".** That allowance is
real and this panel is not in it. FLOW's log and the STAKERS leaderboard are **unbounded by
design** — a log has no last row and `pool4u_stakers.MAX_ROWS` caps a page, not a population — so
their content can never set a height pin. The ladder is **five fixed rungs** from
`analytics/surf_pool4_depth.DEPTH_MOVES`. A panel whose line count is a constant and whose floor
is under it is the "`min-height` is floor and ceiling both" case, and here the floor is two rows
short of the ceiling.

**Consequence if left.** None at the pin: the constant is measured against the body's *content*
rather than against the marker, precisely so the published number does not promise a body that
loses a row. What is left is a one-row window in which a reader sees a four-rung ladder and
nothing on screen says a rung is missing.

**The fix, when it is scheduled.** `SurfPool4UDepth`'s `min-height` is `7` against nine painted
lines, in **both** copies of the rule (`SurfScreen.DEFAULT_CSS` and `themes/minimal.tcss` — edit
both or neither). Raising it to `9` and re-sweeping is the obvious shape, and it will move
`SURF_POOL4_USER_FULL_LAYOUT_ROWS`; the standing rule says re-sweep rather than adjust the
constant to match. `tests/screens/test_surf_pool4_market_layout.py::
test_the_taller_marker_is_dark_in_the_one_row_window_below_the_pin` pins the **current**
behaviour and therefore reddens the moment this is fixed, which is deliberate: the fix has to
come with the constant's `#:` block, that module's docstring and this note updated in the same
diff.

---

## F7 — `widgets/surf/hero.py:431` hands a markup **string** to `Static.update`

**Found by:** the pool4 market wave (carry-over C6). **Severity:** surf-local, crash-class.
**Pre-existing and outside this branch's scope — deliberately not fixed here.**

```python
self.update("\n".join(lines))
```

CLAUDE.md's rule is explicit and this is the shape it forbids: *a widget that renders third-party
text through `Static` hands it a pre-built `rich.text.Text`, never a markup string.* Textual does
not parse at call time — it defers `Content.from_markup` into the message pump — so a malformed
third-party string raises **outside** the screen's `try/except` and takes the app down rather than
degrading to a skipped row. `SurfFeed._row_text` is the worked example of the correct shape:
parse it yourself, synchronously, inside your own `try`.

**Why it is not fixed on this branch.** It is pre-existing, it is in a file no package in this
wave owns, and a fix landing here would ride into the branch unreviewed — the one thing a
carry-over is not allowed to do. It needs its own change and its own test, with an attacker-shaped
string (a token symbol of `[/x]` is deployable by anyone) driven through the hero's real update
path and asserted against composited output rather than against the content string.

**Reachability, stated honestly rather than assumed.** Nobody on this wave traced every value that
reaches those `lines` to a third-party source, so this is filed as a rule violation with a known
failure mode, not as a demonstrated crash. That distinction is the work the fix has to do first:
if every value is repo-controlled today, the fix is still correct, because the next value added
there will not be.

---

## F8 — `query_one` does **not** raise on multiple matches in this Textual version

**Found by:** WP7, and recorded because it cost a debugging session rather than because it is a
defect in this repo.

`textual.dom.DOMNode.query_one(SomeWidget)` returns the **first** match. It does not raise on a
second one. Two mounted `SurfPool4Flow` instances — one in the `p` body, one in the `4` body, the
same class reused on purpose per the PRD's §6.4 — therefore reddened **nothing**, and every test
written as `screen.query_one(SurfPool4Flow)` was silently asserting about whichever instance the
DOM walked into first. In a body-swap screen that is routinely the instance that is not on screen.

**What to do instead**, and what `tests/screens/test_surf_pool4_market_layout._market_widgets`
does: resolve a panel **through its own body container** (`body.query(cls)`) and assert the match
count is one. `SurfScreen._do_refresh` is already written this way for the same reason — it
dispatches RECENT FLOW with `self.query(SurfPool4Flow)` rather than `query_one`, so one statement
feeds both instances and they cannot diverge.

This is a note, not a scheduled fix: nothing in the repo is currently wrong because of it. It is
here so the next person who reuses a widget class across two bodies does not re-learn it.

---

## WP10 mutation record — both pins, both directions, and which test bit

Not a finding. Recorded because S22 says a both-directions width test is the most
collision-prone mutation shape in this repo and A36 says "non-zero exit" is not "it bit"
(`pytest ::nonexistent_test` exits **4**). Every run below used a **unique**
`PYTHONPYCACHEPREFIX` directory, per A31 — one shared prefix reproduces the bug where two
same-size mutations in the same second run the first's bytecode — and `-p no:cacheprovider`.
Each was restored from a copy taken before the edit; nothing was `git checkout --`'d.

| mutation | exit | which tests reddened |
|---|---|---|
| `..._COLUMNS = 105` → **104** | 1 | `..._is_whole_from_its_pinned_width[capture-104]`, `[ordinary-104]`, `..._column_pin_is_the_need_it_claims_doubled`, `..._column_pin_does_not_move_with_the_payload` (9/9), `..._binding_panel_is_the_flow_log[ordinary]` — **13 failed, 42 passed** |
| `..._COLUMNS = 105` → **106** | 1 | `..._is_whole_from_its_pinned_width[capture-105]`, `[ordinary-105]`, `..._binding_panel_is_the_flow_log` (9/9), `..._column_pin_does_not_move_with_the_payload` (9/9), `..._column_pin_is_the_need_it_claims_doubled` — **21 failed, 34 passed** |
| `..._ROWS = 33` → **32** | 1 | `..._is_whole_from_its_pinned_height[capture-32]`, `[mainnet-32]`, `[widest-32]`, `..._height_pin_is_the_ladders_ninth_line`, `..._taller_marker_is_dark_in_the_one_row_window_below_the_pin` — **5 failed, 36 passed** |
| `..._ROWS = 33` → **34** | 1 | `..._is_whole_from_its_pinned_height[capture-33]`, `[mainnet-33]`, `[widest-33]`, `..._height_pin_is_the_ladders_ninth_line`, `..._taller_marker_is_dark_in_the_one_row_window_below_the_pin` — **5 failed, 36 passed** |

The first attempt at the harness exited **4** on a quoting bug (the whole `pytest` argument
string arrived as one path), which is exactly the false positive A36 describes: a harness reading
non-zero as "the test bit" would have scored it as a bite and stopped. The exit code is printed
beside every run above for that reason.

**C5's hoist was proven the same way.** Mutating the join in
`tests/widgets/surf_compositing.composite_lines` from `""` to `"|"` reddened 6 tests across the
files that now import it, and dropping the last strip reddened 2 more — the helper is live in all
five call sites rather than merely imported.
