# surf `p` POOL4 — the frozen data contract

**This is the WP0 hand-off.** It is §0 of `docs/surf_pool4_implementation_plan.md`
reproduced **verbatim except where a later amendment supersedes it** — those
corrections are made inline, in bold, and each names the amendment that owns it —
followed by the points WP0 had to resolve to land it as code. Five work packages
build against this document and against nothing else.

**Superseding amendments already folded in:** **A14** (the vault's `decimals()` is
24, so §0.2's two `1e18` share formulas were wrong by 10⁶), **A15** (`backstop()`
returns three words, not four) and **A27** (the persisted-adoption defence is
retired — nothing is ever adopted from storage). Finding **W1** added
`pool4_counter_state` / `pool4_counter_detail`, and the citation finding added
`pool4_discovery_source_tx` — taking `POOL4_KEYS` from 45 to **48** and
`SURF_KEYS` from 127 to **130**. **Mainnet went live 2026-09-02** and brought
twelve more — the Reward Distributor's three-way split (nine), the ratchet's
ceiling half (two) and `pool4_discovery_source` (one) — taking `POOL4_KEYS` to
**60** and `SURF_KEYS` to **142**; `pool4_reward_path` then took them to
**61** and **143**, and `pool4_cap_headroom` to **62** and **144**. `docs/imd_pool4_mainnet.md` is the record of
that deployment; every number in it is a live read. The plan's amendment log is
the authority for the rest.

The code that implements it is `maxpane_dashboard/data/surf_models.py`
(`POOL4_KEYS`, `SURF_ROW_KEYS["pool4_flow"]`, `SURF_ROW_KEYS["pool4_hatches"]`,
`POOL4_FLOW_LIMIT`, the six closed vocabularies and the five wire-level
dataclasses). It is pinned by `tests/data/test_surf_pool4_models.py`.

**Where this document and the code disagree, the code is right and this document
is a bug** — the tests run, prose does not. Every resolution below is there
because the plan's §0 was ambiguous or self-contradicting at that point, and each
names what was frozen and why.

**The house rules that govern every key here**, restated once so no package has to
go looking:

- **A failed read is `None`, never `0`.** Each table below says what `None` means
  for that key specifically. A client that turns an outage into `0` makes the
  manager unable to tell "RPC down" from "the value is zero", and the zero then
  gets *persisted* and outlives the outage.
- **A representable zero is `0`, never `None`.** `pool4_split_drift_bps = 0.0` is
  the healthy answer and renders as a number. `burned_imd = 0.0` on a buy is a
  fact about the mechanism, not a missing read.
- **Models are wei-native; the flat dict is the presentation boundary.** The
  manager divides exactly once. No `_wei` key exists in the payload and no
  whole-unit field exists on a model.
- **Widgets receive only `str` / `int` / `float` / `bool` / `dict` / `list[dict]`**
  (plus the nested `list[list[float]]` series, on the existing `supply_series` /
  `price_series` precedent).
- **The clock is injected.** Nothing on the pool4 path calls `time.time()`
  internally; every age reaching a widget is precomputed by the manager, which is
  the only reason a committed capture replays forever.

---

## 0. FROZEN DATA CONTRACT

**This section is the interface.** WP0 lands it as code; every other package builds against it
and against nothing else. Widgets receive only `str` / `int` / `float` / `bool` / `dict` /
`list[dict]`. A failed read is `None`, never `0`. A representable zero is `0`, never `None`.

### 0.1 Where the keys live

`POOL4_KEYS` is a tuple in `data/surf_models.py`, spliced into `SURF_KEYS` as one contiguous
block after the launchpad block. `SurfManager.fetch_and_compute()` returns **exactly**
`SURF_KEYS` under every failure combination, as it does today. Two new row shapes join
`SURF_ROW_KEYS`.

**Every key is spelled with its full `pool4_` prefix in the widget kwargs too.** This is a
deliberate departure from the launchpad panels, which take `as_of_hhmm` short and rely on
`tests/widgets/test_surf_widget_contract._PREFIXED_KWARG_ALIASES`. That alias maps one kwarg
name onto one contract key; a second body whose panels also took `as_of_hhmm` would make one
kwarg name stand for two different keys and the alias would silently stop proving anything.
**No new alias is added, and no pool4 widget goes on `_SHORT_KWARG_WIDGETS`.** WP8 pins that
decision with a test.

### 0.2 Scalar keys (60 — 43 at the freeze; W1 two, the citation one, mainnet twelve, the reward path one, the headroom one)

#### Network, discovery and addresses — rendered by `SurfPool4Hatches` (+ titles everywhere)

| key | type | `None` means |
|---|---|---|
| `pool4_network` | `str \| None` | closed vocabulary `"SEPOLIA"` / `"MAINNET"`. `None` = no sweep has ever completed. Every panel title renders `· <word>`, and `· —` on `None` — a panel title never goes networkless |
| `pool4_as_of_hhmm` | `str \| None` | the POOL4 tier's own slower clock. `None` = nothing has ever landed. **Advances only when new data actually lands**, never on a tick that found nothing new |
| `pool4_discovery_state` | `str \| None` | closed vocabulary `"not-discovered"` / `"adopted"` / `"rejected"`. `None` = discovery has not run |
| `pool4_discovery_detail` | `str \| None` | one line of pattern language: which gate a candidate failed, or what was adopted and when. Third-party-derived → escaped at render. **The citation is never appended to it** — see below |
| `pool4_discovery_source_tx` | `str \| None` | the self-post an adoption rests on. A **pointer, not a credential**. `None` = no citation available; read it against `pool4_discovery_state`. Escaped at render like any chain-sourced string |
| `pool4_hook_addr` | `str \| None` | the adopted (mainnet) or vendored (Sepolia) hook. `None` = undiscovered |
| `pool4_token_addr` | `str \| None` | IMD on the active network |
| `pool4_vault_addr` | `str \| None` | read **off the hook**, never scraped. `None` = hook did not name one |
| `pool4_distributor_addr` | `str \| None` | the Reward Distributor's address when one was read. **`None` is ambiguous on purpose** — no Distributor, *or* `rewardsRecipient()` unread — so it must never be read as topology. Use `pool4_reward_path` |
| `pool4_reward_path` | `str \| None` | what `rewardsRecipient()` points at: `"direct"` (the Dripper — the reward share **is** the staker share) or `"via-distributor"` (a Distributor subdivides it). `None` = unknown; annotate nothing rather than guess a leg |
| `pool4_dripper_addr` | `str \| None` | `distributor.dripper()` on mainnet, `rewardsRecipient()` on Sepolia. `None` = unread |
| `pool4_discovery_source` | `str \| None` | which source nominated the adopted address: `"self-post"` / `"docs"` / `"unattributed"`, **ordered strongest first**. `None` = no adoption to attribute. **Never renders as `self-post`** — see the block below |

> ### ⚠ Discovery: provenance is the only unforgeable gate (amendment A27)
>
> `pool4_discovery_state` reaching `"adopted"` is a claim about an
> **attacker-writable** channel. Exactly one thing makes it safe: the candidate
> came from a transaction **signed by the announce wallet's key**. Forging that
> costs the key. Forging everything else costs about a second of CPU.
>
> **The fingerprint narrows the field; it does not make a candidate trustworthy.**
> An address with the right permission bits was mined in ~16,000 tries by the
> security pass and in **20,141 tries, in under a second**, by WP3. Four of the
> five getters it checks are pure liveness — any contract that answers passes them
> — and `token()` is a value the candidate's own contract chooses.
>
> **Nothing is ever adopted from storage.** A persisted address is not in the
> candidate set: not tried first, not tried last, not re-verified. Discovery
> re-runs from the channel every time, and a state read back from disk is a label
> on the last run, never a nomination for the next one. An earlier design
> re-verified the stored address and this contract promised it; the promise held
> only against the committed fixture, whose flag word is all zeros. WP7 removed the
> persisted address from the candidate set and WP3 deleted `reverify_persisted`.
>
> **The citation gets its own key, and that is a correctness fix, not tidiness.**
> `pool4_discovery_source_tx` is published *beside* `pool4_discovery_detail` and
> never merged into it. `surf_manager`'s slot writer already stated the principle
> — *"never merged into it: the detail is WP3's sentence, this is a pointer to a
> credential, and a later reader must be able to tell them apart"* — and the slot
> honoured it while the payload appended a 66-character hash to a ~94-character
> sentence.
>
> The merge is what **guaranteed** the citation would be lost. After A27 the tail
> is the load-bearing half, so any tail-truncation deletes the only unforgeable
> evidence in the design and keeps the hook address — which the reader could
> already see four lines below. Two keys let HATCHES give the citation its own
> line, in full, at a width it controls.
>
> **`None` is read against the verdict**, which is why no second key is needed:
>
> | `pool4_discovery_state` | `pool4_discovery_source_tx` | meaning |
> |---|---|---|
> | `"not-discovered"` | `None` | nothing to cite yet — expected |
> | `"rejected"` | a hash | the rejection cites the post it judged |
> | `"adopted"` | a hash | the audit trail exists — the healthy case |
> | `"adopted"` | `None` | **an adoption nothing can audit** — the one combination worth surfacing |
>
> So the panel that renders the citation must also receive the state, or it
> cannot tell an expected absence from an unauditable adoption. A test pins that.
>
> **The known pressure, named so it can be refused on its merits:** the self-post
> can age out of the channel window (~64 days measured), and discovery then loses a
> genuinely adopted hook. The fix is to read more channel history, or to
> re-establish provenance from the chain via the self-post's transaction hash —
> **never to re-nominate from storage**, which trades a paging bug for the
> provenance bypass A27 closed.

#### `THE SPLIT` — rendered by `SurfPool4Split`

| key | type | `None` means |
|---|---|---|
| `pool4_measured_inference_pct` | `float \| None` | computed from the live counters, never quoted |
| `pool4_measured_burn_pct` | `float \| None` | ditto |
| `pool4_measured_stakers_pct` | `float \| None` | ditto |
| `pool4_reward_share_bps` | `int \| None` | `rewardShareBps()` — the *claimed* share |
| `pool4_bps_denominator` | `int \| None` | `BPS_DENOMINATOR()` |
| `pool4_split_drift_bps` | `float \| None` | measured stakers share minus claimed, in bps. `None` when either side is unread. **`0.0` is the healthy value and must render as such, not as a dash** |
| `pool4_total_burned` | `float \| None` | whole IMD |
| `pool4_total_rewarded` | `float \| None` | whole IMD |
| `pool4_total_fee_token` | `float \| None` | whole IMD |
| `pool4_retained_eth` | `float \| None` | whole ETH |
| `pool4_last_claim_block` | `int \| None` | |
| `pool4_unsettled_burn` | `float \| None` | accrued-but-unsettled burn leg. `0.0` = settled up to date |
| `pool4_unsettled_stakers` | `float \| None` | ditto, staker leg |
| `pool4_counter_state` | `str \| None` | **W1.** Closed vocabulary `"reconciled"` / `"mismatch"` / `"window-limited"` / `"unchecked"`. `None` = the check has never run — it **never** means the counters agree. See the block below |
| `pool4_counter_detail` | `str \| None` | which counter disagrees and by how much. `None` when there is nothing to say |
| `pool4_distributor_staking_bps` | `int \| None` | `stakingBps()` |
| `pool4_distributor_nodes_bps` | `int \| None` | `nftBps()` — **`nodes` in the payload, `nft` on the chain** |
| `pool4_distributor_bonding_bps` | `int \| None` | **DERIVED**: `bps_denominator − staking − nodes`. No getter exists. `None` whenever *either* input is unread. Labelled derived on screen |
| `pool4_distributor_staking_earned` | `float \| None` | whole IMD, cumulative |
| `pool4_distributor_nodes_earned` | `float \| None` | whole IMD, cumulative |
| `pool4_distributor_bonding_earned` | `float \| None` | whole IMD, cumulative |
| `pool4_distributor_held_nodes` | `float \| None` | awaiting `distribute()`. `0.0` = distributed up to date |
| `pool4_distributor_held_bonding` | `float \| None` | ditto. **There is no held-staking leg** — that leg is forwarded, not held |

> ### ⚠ R1 control (c): the counter reconciliation, and why it is **two** keys
>
> This is the day-one detection mechanism for this build's central risk. The hook
> interface was **recovered from bytecode selectors**, the contract is unverified
> on mainnet too, and three event signatures remain unresolved — so a wrong
> operand order in a decoder surfaces as a *confident wrong number* with no signal
> anywhere. `surf_pool4.reconcile_counters` computes it; these two keys are how it
> reaches the screen.
>
> **The three wei-exact IMD identities:**
> ```
> Σ FeeCollected[imd]    == totalFeeToken()
> Σ ClaimsSettled[0]     == totalBurned()      == balanceOf(0x…dEaD)
> Σ ClaimsSettled[1]     == totalRewarded()
> ```
>
> **There is no symmetric ETH check, and there must not be** (amendment A9).
> `totalFeeToken()` is cumulative; `retainedEth()` is a *current balance*. So
> `Σ FeeCollected[eth] == retainedEth()` reads non-zero against zero on a
> perfectly healthy hook and would fire on **every owner withdrawal**. The ETH
> identity that holds is `Σ FeeCollected[eth] == Σ FeesWithdrawn[eth] + retainedEth()`
> and it needs `FeesWithdrawn` logs; without them the ETH leg is simply not checked.
>
> **`None` never means the counters agree.** The healthy answer is the *word*
> `"reconciled"`. This is the one decision in W1 worth defending: if the manager
> fails to compute the check, `_finalise` fills the key with `None`, and under a
> "None means agree" reading that failure would render as a **clean bill of
> health**. A control that reports all-clear when it did not run is not a control.
> `None` therefore keeps the house meaning it has on all 46 other keys — the check
> has never run — and every outcome of actually looking is a word.
>
> | state | meaning |
> |---|---|
> | `None` | the check has never run |
> | `"reconciled"` | every applicable identity holds **to the wei**, over complete history |
> | `"mismatch"` | at least one does not — `pool4_counter_detail` names which and by how much |
> | `"window-limited"` | the log sums cover a **trailing window**, not full history, so the cumulative identities cannot hold by construction. Not an error, and **not a pass** |
> | `"unchecked"` | the sweep failed or the counters are unread — we could not compute it |
>
> **`window-limited` is not a formality.** `POOL4_LOG_WINDOW_BLOCKS = 7_200` is a
> *trailing* window (~24 h). Every identity above is cumulative-counter versus
> sum-of-**all**-logs, so once the hook is older than the window the sum is short
> by everything preceding it and all three "disagree" by construction. The control
> is meaningful **only when the sweep reaches the hook's deployment block**, and
> the producer must say `window-limited` rather than `mismatch` whenever it does
> not. This is the same trap WP7 already solved for the negative unsettled legs by
> publishing `None` rather than a negative.
>
> **To make the control actually fire in steady state**, the sums have to be
> accumulated forward from deployment rather than recomputed over a window — the
> `LaunchpadState.cursor` precedent, which carries `burned_total_wei` and
> `traders` forward for exactly this reason ("a total cannot be recovered from its
> newest addend"). Until that exists, `window-limited` is the honest answer and
> the control is dormant, which is a known state rather than a silent one.
>
> **Word choice:** `"reconciled"`/`"mismatch"`, not `"agree"`/`"disagree"` —
> `agree` is a substring of `disagree`, so a widget testing `"agree" in state`
> would render a mismatch as healthy. No member is a substring of another.

> ### ⚠ Provenance now has two sources, and the weaker one must say so
>
> The announce channel has **not** named the mainnet hook, so automatic discovery
> correctly refuses under A27. Rather than show SEPOLIA while mainnet is live, the
> operator accepted the project's documentation page as a **candidate** source.
> The full chain fingerprint still applies, and the announce channel remains the
> stronger path and overrides it whenever a self-post lands.
>
> **The cost, stated once:** the docs site is now a trusted input. Anyone who can
> change that page can name a hook, and the fingerprint alone will not stop them —
> a correctly-shaped address mines in ~20,000 tries, four of the five getters are
> pure liveness checks, and `token()` is the candidate's own choice.
>
> **The mitigation is disclosure, not prevention**, which is why the source is a
> contract-level closed vocabulary and not a string each panel invents:
>
> | state | source | meaning |
> |---|---|---|
> | not `"adopted"` | `None` | nothing to attribute — expected |
> | `"adopted"` | `"self-post"` | a transaction signed by the announce wallet. **Unforgeable** |
> | `"adopted"` | `"docs"` | the documentation page. Trusted, **not signed** |
> | `"adopted"` | `"unattributed"` | adopted with no source recorded — show it **at least as weakly as `docs`** |
>
> `"unattributed"` exists for the `pool4_counter_state` reason: if the producer
> forgets to set the source, `_finalise` fills the key with `None`, and a renderer
> treating `None` as "nothing to say" would draw a docs-sourced adoption
> identically to a dev-signed one — undoing, by omission, the disclosure the
> operator's decision was conditioned on. **`None` must never render as
> `self-post`.** Absence is not provenance.
>
> Accepting the page as a *candidate source* is not the same as scraping values
> from it: a candidate is an address the chain fingerprint then interrogates. Every
> number on this view is still read from the chain.

> ### ⚠ The cap headroom: refused twice, admitted on evidence
>
> `pool4_cap_headroom` is **`inventoryCap − tokensInPool`**. Measured live:
>
> ```
> MAINNET  inventoryCap 5,331.227804  tokensInPool 5,236.544041  headroom 94.683763
> SEPOLIA  inventoryCap 472,569,750.774434  tokensInPool 472,569,750.774434  headroom 0
> ```
>
> **Why it is a quantity, not a word.** 94.68 IMD against a 1,000 IMD/day decay
> is **the cap binding in ~2.3 hours**. The magnitude relative to the decay rate
> is the entire meaning, and a three-state word discards it. THE RATCHET is the
> panel about the ceiling coming down; this is how far it has left to come. Two
> pools both rendering `5.5K` through a compact formatter — one with a day of
> slack, one about to clamp — are different decisions.
>
> **⚠ The sign is the trap.** `pool4_floor_distance` is `reserve − floor`; this
> is `cap − reserve`. The operand order **flips** so that both read positive when
> healthy. Writing the ceiling half as `reserve − cap` by analogy with its
> sibling inverts the sign and renders a binding cap as slack.
>
> **The two earlier refusals are superseded, not wrong**, recorded so this is not
> reopened a third time on the same grounds:
>
> | ground | status |
> |---|---|
> | the difference is unrepresentable in `float` | **expired** — built on a 12-wei sample taken minutes after an event and mistaken for a property. 94.68 IMD is ~1.0e14 ulps; the 12-wei case was 1.3e-5 ulps |
> | the divergent state has never been observed | **expired, and self-sealing** — the only deployment that could show it is Sepolia, whose cap cannot move *because* its decay is the no-decay sentinel |
> | both operands are already published | **proves too much** — `pool4_floor_distance` has exactly that shape and nobody argues it is wrong |
>
> What survives is weaker than it looked: the absolute form has no division
> hazard (no `_pct` sibling, and none is asked for) and the comparison stays
> derivable downstream. Those were reasons it was *cheap* to omit, never reasons
> it was wrong to publish.
>
> **Pre-identified follow-up, named so nobody re-derives it.** "Binds in days" is
> `headroom ÷ decay` and is the more actionable form. It is **not** a key: no
> panel has asked for one. Its hazard is worse than `backlog_days`' zero
> denominator — on the no-decay sentinel, `94.68 / 3.4e20` is ~2.8e-19 days,
> which reads as **"binds now"** when the truth is **"never binds"**. That is a
> sign-of-meaning inversion, not a missing value, so whoever builds it must
> resolve the sentinel *before* dividing rather than guard against zero.

> ### ⚠ The reward path is a **word**, not an address
>
> `SurfPool4Split` annotates the measured stakers percentage with which leg it
> is — `4.50% (staking leg)` on mainnet, `9.89% (reward leg)` on Sepolia. Those
> two annotations are **three times apart** and are the bug WP3 caught.
>
> `pool4_distributor_addr` cannot decide it. That key is `None` in two different
> worlds — there is no Distributor, and `rewardsRecipient()` was not read — and
> the hook's getters are batched with `allowFailure=True`, so **one reverted
> sub-call degrades one field rather than the round**. "The counters answered,
> `rewardsRecipient()` did not" is a routine payload, and in it a panel reading
> absence-of-address as absence-of-Distributor labels mainnet's 15% as the
> staker share — the 3× bug, arriving through the door opened to prevent it.
>
> | `pool4_reward_path` | meaning |
> |---|---|
> | `None` | the path is unknown. **Annotate nothing** |
> | `"direct"` | `rewardsRecipient()` is the Dripper; `totalRewarded()` all reaches stakers |
> | `"via-distributor"` | a Distributor subdivides it; the staker share is a *fraction* |
>
> Same reasoning as `POOL4_COUNTER_STATES`: the healthy reading has to be a word
> a producer must *say*, because `None` is what an omission produces.
>
> **Both keys go to both panels** — SPLIT to annotate, HATCHES for custody. The
> shared key *is* the agreement (one dispatch, one value, no second source to
> drift from), so there is no cross-panel equality test to write; what is pinned
> instead is that any panel rendering a leg-dependent number receives the fact
> that decides the leg. A topology fact split across two panels is how the next
> version of this bug gets in.

> ### ⚠ The vault is three hops away on mainnet — the one change that is not self-adapting
>
> ```
> Sepolia:  hook.rewardsRecipient() → Dripper → dripper.vault()
> Mainnet:  hook.rewardsRecipient() → Distributor → distributor.dripper() → Dripper → dripper.vault()
> ```
>
> A two-hop reader calls `vault()` on the **Distributor**, which has no such
> method, and the vault and dripper reads fail outright. The hop count must be
> discovered from what each address answers, never assumed from the Sepolia shape.
> `pool4_distributor_addr` is what makes it visible; its `None` means "no
> distributor in this path", not "unread".
>
> **D13 — both chains answer both new hook getters.** An earlier brief said
> `inventoryCap()` / `capDecayTokensPerDay()` were mainnet-only and Sepolia had
> neither. That was assumed, never measured, and it is wrong; only the *values*
> differ:
>
> ```
>                          Sepolia                Mainnet
> capDecayTokensPerDay()   2**128-1 (no decay)    1,000 IMD/day
> inventoryCap()           472,569,750.77 IMD     5,413.26 IMD
> tokensInPool()           472,569,750.77 IMD     5,413.26 IMD   ← cap == inventory on BOTH
> ```
>
> Two things follow. **The absence case cannot be driven by pointing at
> Sepolia** — a test written as "aim it at Sepolia and watch the fields go
> `None`" passes for the wrong reason; absence must come from a getter made to
> revert, which is what a differently-built future hook looks like. And
> **`2**128-1` is a sentinel meaning *no decay*, not a rate**: the producer
> resolves it to that word, because ~3.4e20 IMD/day is not a number any panel
> should print, and `None` stays the ordinary failed read.
>
> **What self-adapts, because it is read live and not hardcoded:**
> `rewardShareBps` 1000 → **1500**, `capFloor` 250,000,000 → **1,000 IMD**,
> vault `decimals()` 24. That is the house rule paying for itself.

#### `THE RATCHET` — rendered by `SurfPool4Ratchet`

| key | type | `None` means |
|---|---|---|
| `pool4_tokens_in_pool` | `float \| None` | the reserve, whole IMD |
| `pool4_cap_floor` | `float \| None` | **the observed floor, labelled as inferred** (see §5) |
| `pool4_inventory_cap` | `float \| None` | `inventoryCap()`, the ceiling half of the ratchet. Answered on **both** chains (D13) |
| `pool4_cap_headroom` | `float \| None` | **`cap − reserve`** — note the operand order flips vs `floor_distance`, so both are positive when healthy. Whole IMD. `None` when either operand is unread. A negative is real (inventory above the cap) and renders rather than clamping |
| `pool4_cap_decay_per_day` | `float \| None` | `capDecayTokensPerDay()`, whole IMD/day. Answered on **both** chains. **`2**128-1` is a "no decay" sentinel, not a rate** — ~3.4e20 whole IMD/day — and the producer resolves it to a word; a panel must never print it |
| `pool4_floor_distance` | `float \| None` | reserve − floor, whole IMD. May be negative; a negative is real and renders |
| `pool4_floor_distance_pct` | `float \| None` | distance as % of the floor. `None` when the floor is 0 or unread — never an infinity |
| `pool4_burned_supply_pct` | `float \| None` | `total_burned / total_supply * 100` |
| `pool4_total_supply` | `float \| None` | whole IMD |
| `pool4_reserve_series` | `list[list[float]] \| None` | `[[ts, imd], …]`, oldest first. `[]` = swept and empty. **No sentinel is ever appended**; see §5 for the network-splice hazard |
| `pool4_eth_in_pool` | `float \| None` | whole ETH |
| `pool4_position_liquidity` | `float \| None` | raw uint128 L |
| `pool4_current_tick` | `int \| None` | |
| `pool4_ref_tick` | `int \| None` | |
| `pool4_backstop_centred` | `bool \| None` | tri-state. `None` must never render as "centred" nor as a confident "not centred" |

#### `sIMD VAULT` — rendered by `SurfPool4Vault`

| key | type | `None` means |
|---|---|---|
| `pool4_share_price` | `float \| None` | **`convertToAssets(10 ** decimals) / 1e18`**, whole IMD per share. `decimals` is read off the vault (24 today), *not* assumed to be 18 — see **A14** and the warning below the table |
| `pool4_share_price_delta_pct` | `float \| None` | change since the session baseline. `None` until a second reading exists — never `0.0` as a stand-in |
| `pool4_vault_assets` | `float \| None` | TVL, whole IMD |
| `pool4_vault_shares` | `float \| None` | whole sIMD = **`total_shares_raw / 10 ** decimals`**, *not* `/ 1e18` — see **A14** and the warning below the table |
| `pool4_drip_per_day` | `float \| None` | `dripRatePerSecond() * 86400`, whole IMD |
| `pool4_drippable` | `float \| None` | whole IMD |
| `pool4_can_drip` | `bool \| None` | tri-state |
| `pool4_backlog_imd` | `float \| None` | the dripper's own IMD balance |
| `pool4_backlog_days` | `float \| None` | `backlog / drip_per_day`. **`None` when the rate is 0 or unread — never an infinity** |
| `pool4_implied_apr_pct` | `float \| None` | derived from `drip_per_day` and TVL only, **never from fee flow**. `None` when TVL is 0 or unread — never an infinity |

> ### ⚠ The sIMD vault is **not** an 18-decimal token (amendment A14, verified live)
>
> Solady's `ERC4626` reports `asset decimals + _decimalsOffset()`, and
> `StakedIMD._decimalsOffset()` is **6**, so `decimals()` returns **24**. One whole
> `sIMD` is `1e24` units. The two rows above originally divided by `1e18` and were
> wrong by a factor of a million in both directions:
>
> ```
> convertToAssets(1e18) / 1e18 = 0.000001302985528554   ✗ renders as a dead vault
> convertToAssets(1e24) / 1e18 = 1.302985528554         ✓ pool4_share_price
> total_shares / 1e18 = 21,010,977,789.12 sIMD          ✗ renders as an emissions farm
> total_shares / 1e24 =         21,010.98 sIMD          ✓ pool4_vault_shares
> cross-check: totalAssets 27,377.00 / 21,010.98 = 1.302986 ✓
> ```
>
> **Both wrong forms render as entirely plausible numbers.** Neither looks like an
> error on screen, so no downstream test, review or eyeball would catch it — which
> is what makes this the most dangerous single line in the contract.
>
> **Read `decimals()`; never hardcode 24.** The mainnet vault does not exist yet and
> nothing binds its offset to Sepolia's, so a constant would reproduce this defect at
> the switchover, silently. `Pool4VaultState.decimals` carries the live read, and the
> share count is named **`total_shares_raw`, not `total_shares_wei`** — everything
> suffixed `_wei` in this repo divides by `1e18` and shares do not, so the asymmetry is
> deliberate and there is no symmetry to lean on. `share_price_wei` keeps its suffix
> correctly: its *result* is an 18-decimal IMD amount.
>
> `pool4_share_price_delta_pct` is scale-invariant and is unaffected.

### 0.3 Row keys (2)

`SURF_ROW_KEYS["pool4_flow"]` — `pool4_flow` is `list[dict] | None`; **`None` = the read
failed, `[]` = swept and genuinely quiet.** Newest first, capped at `POOL4_FLOW_LIMIT = 25` by
the manager.

| field | type | note |
|---|---|---|
| `ts` | `float \| None` | epoch |
| `age_s` | `float \| None` | precomputed by the manager — **the screen and the widget are clock-free** |
| `side` | `str` | closed, producer-owned: `"buy"` / `"sell"` |
| `size_imd` | `float \| None` | IMD in on a sell, IMD out on a buy |
| `burned_imd` | `float` | `ClaimsSettled[0]`. **`0.0` on a buy — a representable zero, never `None`** |
| `stakers_imd` | `float` | `ClaimsSettled[1]`. Same rule |
| `fee_imd` | `float \| None` | `FeeCollected` IMD leg; `None` when the fee was taken in ETH |
| `fee_eth` | `float \| None` | `FeeCollected` ETH leg; `None` when the fee was taken in IMD |
| `settled` | `bool` | `False` = accrued, `ClaimsSettled` has not paid it yet |
| `tx_hash` | `str \| None` | |

`SURF_ROW_KEYS["pool4_hatches"]` — `pool4_hatches` is `list[dict] | None`; `None` = unread,
`[]` is never emitted (the BOND row always exists).

| field | type | note |
|---|---|---|
| `scope` | `str` | closed: `"vault"` / `"dripper"` / `"hook"` / `"bond"` |
| `label` | `str` | closed, producer-owned: `"owner"` / `"paused"` / `"rescue"` / `"market"` / `"rebalance"` / `"burn sink"` / `"rewards"` / `"deployed"` |
| `state` | `str` | closed: `"live"` / `"renounced"` / `"paused"` / `"open"` / `"closed"` / `"absent"` / `"unknown"` |
| `detail` | `str \| None` | free text, third-party-derived → escaped at render |
| `addr` | `str \| None` | rendered through `_fmt.long_addr` |
| `addr_known` | `bool` | `KNOWN_LABELS` allowlist only — never a fallback, never a prefix match |

### 0.4 Widget constructor and update signatures

All five are `textual.containers.Vertical` subclasses with `__init__(self, *args, **kwargs)` —
**no required constructor argument**, so the screen composes them bare and the contract sweep
can instantiate every one of them with no args. Each exposes exactly one public method:

```
SurfPool4Flow.update_data(
    pool4_flow=None, pool4_network=None, pool4_as_of_hhmm=None, **_kwargs) -> None

SurfPool4Split.update_data(
    pool4_network=None,
    pool4_measured_inference_pct=None, pool4_measured_burn_pct=None,
    pool4_measured_stakers_pct=None, pool4_reward_share_bps=None,
    pool4_bps_denominator=None, pool4_split_drift_bps=None,
    pool4_total_burned=None, pool4_total_rewarded=None,
    pool4_total_fee_token=None, pool4_retained_eth=None,
    pool4_last_claim_block=None, pool4_unsettled_burn=None,
    pool4_unsettled_stakers=None,
    pool4_counter_state=None, pool4_counter_detail=None,
    pool4_as_of_hhmm=None, **_kwargs) -> None

SurfPool4Ratchet.update_data(
    pool4_network=None, pool4_tokens_in_pool=None, pool4_cap_floor=None,
    pool4_floor_distance=None, pool4_floor_distance_pct=None,
    pool4_burned_supply_pct=None, pool4_total_supply=None,
    pool4_reserve_series=None, pool4_eth_in_pool=None,
    pool4_position_liquidity=None, pool4_current_tick=None,
    pool4_ref_tick=None, pool4_backstop_centred=None,
    pool4_as_of_hhmm=None, **_kwargs) -> None

SurfPool4Vault.update_data(
    pool4_network=None, pool4_share_price=None,
    pool4_share_price_delta_pct=None, pool4_vault_assets=None,
    pool4_vault_shares=None, pool4_drip_per_day=None, pool4_drippable=None,
    pool4_can_drip=None, pool4_backlog_imd=None, pool4_backlog_days=None,
    pool4_implied_apr_pct=None, pool4_as_of_hhmm=None, **_kwargs) -> None

SurfPool4Hatches.update_data(
    pool4_hatches=None, pool4_network=None, pool4_discovery_state=None,
    pool4_discovery_detail=None, pool4_discovery_source_tx=None,
    pool4_hook_addr=None, pool4_token_addr=None,
    pool4_vault_addr=None, pool4_dripper_addr=None,
    pool4_as_of_hhmm=None, **_kwargs) -> None
```

**Every one of the 45 scalar keys and both row keys has exactly one renderer above.** Nothing
joins `_KEYS_WITHOUT_A_RENDERER`. `**_kwargs` is mandatory on all five: the screen splats and a
future key must not raise.

### 0.5 Module boundaries frozen with the keys

| module | may import | may **not** import |
|---|---|---|
| `data/surf_pool4.py` | stdlib, `data/keccak.py`, `data/surf_v4.py` | `httpx`, `textual`, anything that reads a clock, `data/surf_client.py` |
| `data/surf_pool4_client.py` | `httpx` (lazily, via `OwnedHttpClient`), `data/surf_pool4.py`, `data/surf_addresses.py` | `textual`, `widgets/` |
| `widgets/surf/pool4_*.py` | `widgets/surf/_fmt.py`, `widgets/surf/_rowfit.py`, `widgets/markup_safety.py`, `widgets/sparkline_common.py` | `data/`, `analytics/` (no pool4 widget needs an analytics module; the allowlist stays at `analytics.surf_feed`) |

---

## WP0 resolutions — where §0 above was ambiguous, and what was frozen

§0 is reproduced verbatim above, defects included. These four points could not be
transcribed as written; each was resolved in the direction the rest of the plan
already agreed with, and each is pinned by a named test.

### R-A. "Scalar keys (45)" tabulates 43. `POOL4_KEYS` is 45 = 43 scalars + 2 rows.

The §0.2 heading says 45; its four tables list 8 + 13 + 12 + 10 = **43**. The five
`update_data` signatures in §0.4 union to those same 43 and no more, so the
signatures and the tables agree with each other and only the heading is out.
§0.4's own sentence ("every one of the 45 scalar keys **and** both row keys") would
make 47, which nothing supports.

**Frozen:** `POOL4_KEYS` has **45 members — 43 scalars plus `pool4_flow` and
`pool4_hatches`.** The two row keys are members of the payload tuple for exactly
the reason `feed_items` and `launchpad_coins` are members of `SURF_KEYS`:
`SURF_ROW_KEYS` describes the *shape of a row*, it does not excuse the key from
the payload contract, and `test_row_key_sets_match_the_prd` already asserts
`set(SURF_ROW_KEYS) <= set(SURF_KEYS)` repo-wide. Under this reading the "45" in
the §0.2 heading, in WP0 and in WP8 step 4 is the same number throughout.

Pinned by `test_pool4_keys_is_forty_five_of_which_forty_three_are_scalar`, which
asserts **both** numbers rather than the total alone — so a later edit cannot
satisfy 45 by adding a scalar and dropping a row.

### R-B. `pool4_vault_addr` is read off the **dripper**, not off the hook.

§0.2 says the vault address is "read **off the hook**, never scraped. `None` = hook
did not name one". The hook's recovered interface (mechanics doc, *Recovered
interface*) names `token() poolManager() poolId() poolKey() owner() burnSink()
rewardsRecipient() backstop() marketOpen() rebalanceEnabled()` — **there is no
vault getter on the hook.** The path is one hop longer:
`hook.rewardsRecipient()` → the RewardDripper → `dripper.vault()` → StakedIMD.
(`RewardDripper.renounceOwnership()` is blocked when `vault == 0`, which is where
the getter is evidenced.)

**Frozen:** `Pool4DripperState.vault` carries it; `Pool4HookState` has **no**
`vault` field, deliberately — a field with no getter behind it is an invitation to
fill it by scraping, and scraping is the one way this address must never be
obtained. `pool4_dripper_addr` is `rewardsRecipient()` off the hook, exactly as
§0.2 says.

**The intent of §0.2's clause is unchanged and binding: read from chain, never from
a page, never hardcoded for mainnet.** Only the number of hops was wrong.

Pinned by `test_the_hook_state_does_not_name_a_vault`.

### R-C. `POOL4_FLOW_LIMIT` lives in `surf_models.py`, not beside `FEED_ITEM_LIMIT`.

WP0 is told to add `POOL4_FLOW_LIMIT = 25` "beside the existing `FEED_ITEM_LIMIT`
family" and, in the same package, told it owns only `surf_models.py` and must not
touch `surf_manager.py`. `FEED_ITEM_LIMIT` / `DEV_ACTIVITY_LIMIT` /
`NFT_SALES_LIMIT` are all in `surf_manager.py` (owned by WP7), so the two
instructions cannot both be honoured.

**Frozen:** `POOL4_FLOW_LIMIT = 25` is in `surf_models.py`. Ownership won, and the
cap belongs to the contract anyway — `SurfPool4Flow` codes against it and
`surf_models` is the module every surf package may import. WP7 imports it rather
than redeclaring it.

### R-D. The splice reddens four existing test files. This is by design, not a defect.

WP0's acceptance says "the existing full suite is unaffected (this package only
adds names)". That reasoning covers the *manager* — `_finalise` only logs keys
outside `SURF_KEYS`, so an unproduced key is inert — but **not** the tests that
derive their expectations from `SURF_KEYS` itself. Growing the contract before its
producers exist necessarily reddens them:

| test | why | owner |
|---|---|---|
| `tests/data/test_surf_models.py::test_surf_keys_is_exactly_the_prd_contract` | `set(SURF_KEYS) == EXPECTED_KEYS` and `len(SURF_KEYS) == 82`, now 127 | **nobody** — see below |
| `tests/data/test_surf_manager.py` (`set(data) == set(SURF_KEYS)`, 4 sites) | the manager does not produce pool4 keys until WP7 | WP7 |
| `tests/screens/test_surf_screen.py` (dispatch coverage; `set(SURF_ROW_KEYS) <=` fixture list keys) | no widget receives a pool4 key until WP8 | WP8 |
| `tests/test_surf_registration.py` (the `SURF_KEYS` triage sweep) | 45 keys are untriaged until WP8 buckets them | WP8 |

Three of the four are owned files whose owners fix them as part of their own work.
**`tests/data/test_surf_models.py` is owned by no work package in this plan and
must be assigned**, or the wave-0 gate cannot be met. The fix is mechanical: add
the pool4 block to `EXPECTED_KEYS` (or, better, `EXPECTED_KEYS |= set(POOL4_KEYS)`,
matching the splice) and move the count from 82 to 127.

`tests/widgets/test_surf_widget_contract.py` is **not** affected: its check runs
kwargs ⊆ `SURF_KEYS`, so growing the contract is safe in that direction.

The alternative — declare `POOL4_KEYS` but let WP7 splice it — was rejected: it
would mean WP0 is not the contract freeze, and four packages would code against a
tuple that is not yet part of the payload the manager promises to return.

### R-E. `Pool4HookState.backstop` is **three `int | None` fields**, not a string (A15).

`backstop()` returns 96 bytes — `(int24 lower, int24 upper, uint128 liquidity)`.
**There is no ETH word**; the fourth operand in the mechanics doc's earlier draft
came from the *event* `0xe3966151…`, and a decoder expecting four reads past the
answer. A15 left the typing to WP0.

**Frozen:** `backstop_tick_lower`, `backstop_tick_upper`, `backstop_liquidity`, all
`int | None`. Not a delimited `"lower,upper,liquidity"` string and not a
`tuple[int, int, int]`, for three reasons:

1. It is this module's **existing shape for a multi-word getter** — `positions()` is
   already flattened into `ChainState.lp_liquidity` / `lp_token0` / `lp_token1` /
   `lp_fee` / `lp_tokens_owed0_wei` / `lp_tokens_owed1_wei`. A second convention for
   the same job is how a reader learns to check which one applies.
2. **Outage discipline is per field.** A tuple or a string is all-or-nothing; "we read
   the bounds but not the liquidity" has nowhere to live in either. Three `| None`
   fields degrade independently, which is the granularity the rest of the module
   promises.
3. **A delimited string makes every consumer a parser** — of a value that comes off an
   *unverified* contract, so malformed is a real case. `pool4_backstop_centred` is
   derived from the bounds against `current_tick`; from a string that is a `split(",")`
   and an `int()` per consumer, each with its own behaviour on a bad value.

`backstop_liquidity` is **not** `_wei`-suffixed, for `position_liquidity`'s reason: raw
`uint128` `L` is not an amount of any token.

**This changed the dataclass shape** — see the propagation note in the WP0 report.
No payload key changed: `POOL4_KEYS` is still 45, and the three fields feed the
derived `pool4_backstop_centred` rather than reaching the screen themselves.

### R-F. `Pool4VaultState` reads `decimals()`; the share count is `total_shares_raw` (A14).

Two field changes, both forced by A14 and both about making the wrong divisor
*unwritable* rather than merely documented:

- **`decimals: int | None` added.** The divisor for shares is `10 ** decimals`, and
  A14's 24 is a Sepolia measurement. The mainnet vault does not exist and nothing binds
  its `_decimalsOffset()` to Sepolia's, so a hardcoded 24 — or a module constant, which
  is the hardcode wearing a name — would reproduce the defect at the switchover,
  silently and plausibly. This is CLAUDE.md's "read values live, never hardcode a
  documented one" in its most literal form. A test refuses a
  `POOL4_VAULT_DECIMALS`-style constant.
- **`total_shares_wei` → `total_shares_raw`.** Everything suffixed `_wei` in this repo
  divides by `1e18`; shares divide by `1e24`. Two *adjacent* `_wei` fields with two
  different divisors is the habit-trap that produced A14, so the share count is spelled
  differently on purpose. `total_assets_wei` and `share_price_wei` keep their suffixes,
  correctly — both are 18-decimal IMD amounts.

**Both changed the dataclass shape** — see the propagation note in the WP0 report.

---

## What WP0 added beyond the literal task list, and why

§0 calls six vocabularies "closed" and names their members in prose
(`POOL4_NETWORKS`, `POOL4_DISCOVERY_STATES`, `POOL4_FLOW_SIDES`,
`POOL4_HATCH_SCOPES`, `POOL4_HATCH_LABELS`, `POOL4_HATCH_STATES`). They are
exported as tuples on `CHANNEL_KINDS` / `SIGNAL_STATES`'s existing precedent in the
same module, so five packages share one spelling of `"not-discovered"` instead of
hand-typing it five times. Nothing else was added.

`tests/data/test_surf_pool4_models.py` also carries `POOL4_WIDGET_SIGNATURES` — §0.4
transcribed — and asserts its union is exactly `POOL4_KEYS`, with no orphan key and
no unbacked kwarg, and that only `pool4_network` and `pool4_as_of_hhmm` are rendered
by more than one panel. This is the **contract-side** copy; WP8 owns the screen-side
`SURF_WIDGET_SIGNATURES` and the two are meant to stay redundant. Deriving either
from the other would make the agreement test compare a constant against itself.
