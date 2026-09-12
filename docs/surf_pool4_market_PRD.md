# PRD — surf `4` POOL4 MARKET view

**Status:** design approved 2026-09-11, not yet planned or built.
**Sibling:** `docs/surf_pool4_PRD.md` — the `p` body, which this does **not** replace.
**Research instrument:** the `pool4hook-research` skill (`~/.claude/skills/pool4hook-research`),
a zero-dependency read-only TypeScript reader written by the protocol's own author. It is a
*research and cross-check* tool, never a runtime dependency — see §7.

---

## 1. Why this view exists

The `p` body is an **auditor's** view. THE SPLIT measures claimed-versus-actual fee shares, THE
RATCHET names an observed floor, HATCHES lists every lever an owner still holds. It answers *is
this protocol honest and who can still change it* — a question worth a whole body, and one this
view does not take away.

It does not answer the question a **reader who holds or is considering IMD** actually has.
This body does. Every panel earns its slot against one test: *does a reader do something
differently after reading it.* Anything that only describes the machine stays in `p`.

Four things are on screen here that are nowhere in MaxPane today:

1. **The backstop is a standing bid.** 24.4 ETH parked 0.84% under spot, and a ladder of what it
   pays as price falls. No dashboard in this repo has ever shown downside depth, and this is the
   one protocol where it is a real, readable number rather than a promise.
2. **Where to trade.** The hook and the hookless reference pool price IMD differently. Buying on
   the wrong side of that gap costs real money.
3. **A trailing return that is actually measured**, from realised drips — not the delivery cap the
   `p` body's vault panel correctly refuses to call APR.
4. **Whether burning is on right now.** Headroom zero means every net sell burns. It is the most
   consequential on/off state in the protocol and it is invisible today.

## 2. Scope

**IMD only.** The permissionless `CappedBurnLauncher` (`0x80587937a883743e67bB11dab356F60e4656C40d`)
has opened three markets, two of them **FWA** — our own dashboard #3, one with 316,182 FWA burned
against 7.5 ETH in position. That is a real finding and it is filed as **D6** in
`docs/surf_pool4_followups.md`, scoped as FWA dashboard work — not smuggled into surf. Surf is surfsurf.eth's tracker; IMD is its subject.

Consequences of IMD-only, all of them simplifications: fixed addresses, known decimals, a **pinned**
reference pool id. The skill warns that reference-pool *discovery* costs several hundred `eth_getLogs`
calls over public nodes; pinning avoids that entirely.

**Market-wide, not wallet-scoped.** Surf has never had a wallet concept and does not grow one here.
Every number on this screen is the same for every reader.

## 3. The frame

**Key `4`** — a reader looking at a protocol called POOL4 finds it without being told, and it does
not collide with `p`'s meaning the way `u` or `i` would. The two views read as *`p` the protocol,
`4` the market*. `escape` backs out, one-way, exactly as `l` and `p` do.

**Verified free**, not assumed: surf binds only `r`/`l`/`p`/`escape` and the app binds
`q`/`t`/`tab`/`m`. Digit keys are already bound on `curator` (filter presets) and the hidden
`frenpet_full` (sub-views), which makes a digit key an **established pattern on a screen** here
rather than a novelty — and neither is app-level, so neither collides.

**The status hint is a measured constraint, not a detail.** It currently reads
`l launchpad · p pool4` (21 columns). CLAUDE.md records that this label is the segment `StatusBar`
cuts first, that the current phrase already cost nine columns over its predecessor, and that curator
had to *delete* hint text to fit 138. `· 4 market` takes it to 32. **Measure against the left-label
budget before typing it**, and if it does not fit, the new word shortens — the existing phrase does
not, because an acceptance test greps for the contiguous string `l launchpad`.

**The hero is repurposed, and that is a deliberate break of precedent.** Every surf body swap so far
keeps the hero in place so surf's headline metrics never go dark. Here they would be the clearest
thing on screen a reader does not act on. So: a **second hero widget**, composed once at startup and
toggled with the body — the established swapped-in-body pattern ("composed once and hidden, so the
first keypress paints a complete frame"), *not* one widget with a mode branch inside it, which would
couple two subjects into one class and make their tests share a fixture.

**Three cards, not four, and the reason is a name collision.** Surf's hero already says `BURN` and
`SUPPLY`. A pool4 card called BURN shows a *different* number — hook trim burns, not launchpad burns
— and a reader tabbing between bodies would watch one word change value and reasonably read it as a
single metric moving. Burn therefore lives in the chart panel instead.

**Layout pin:** its own constants, `SURF_POOL4_USER_FULL_LAYOUT_{COLUMNS,ROWS}`, each with its own
`#:` block, **measured in situ and never derived**. A prediction recorded here so it can be proven
wrong: the bakery shape is wide-and-short where the `p` body is narrow-and-tall (106 × **44**), and
44 rows is the tallest requirement in the repo with open finding **W7** noting nobody has checked it
against a real laptop. A two-column bakery body should land nearer the launchpad's 31 rows.

## 4. Layout

Bakery's shape exactly — hero, then `#middle-row` as leaderboard beside a chart-over-signals column,
then `#bottom-row` as activity beside the EV table.

```
 IMD PRICE                DOWNSIDE BID             STAKING
 $2.845                   24.4 ETH                 4.0% trailing 7d
 cheaper on ref −1.5%     standing 0.8% under      1.36M IMD · 66 addrs

 STAKERS · 66 addresses        │  BURN & SUPPLY  ▁▂▃▅▇▅▃  3,156/day
 ─────────────────────────     │  26,289 retired · 0.12% of supply
  1  0xf53c..3364   184,200    │
  2  0xa9c5..f057   151,800    │  SIGNALS
  3  0x4c68..dd08    97,400    │   ● burning        ON · headroom 0
  …  top 3 = 32% of vault      │   ● cheaper pool   REFERENCE −1.5%
                               │   ● backstop       0.8% under spot
                               │   ● drip backlog   none
 ──────────────────────────────┴──────────────────────────────────
 RECENT FLOW                   │  IF IMD FALLS — what the hook bids now
  2m  SELL  1.2K   burned 111  │   -1%    pays 0.14 ETH     5% of band
  7m  BUY     980  burned   0  │   -10%   pays 2.33 ETH     5% of band
  14m SELL  4.5K   burned 402  │   -50%   pays 13.8 ETH    29% of band
```

**The figures in this mockup are illustrative except where §1 cites them as live.** Specifically:
the staker rows, their IMD amounts and `top 3 = 32%` are **invented to show the format** — the skill
reports largest *moves* in a window, not largest *holdings*, so real concentration is unknown until
the sweep in §7 is built and is one of the things it exists to answer. And `4.0% trailing 7d` was
measured by the skill over **72 hours**, not seven days; §8.1 specifies the 7-day window, and the two
must not be conflated when the panel is built.

## 5. The hero cards

Each keeps the template's **explicit unavailable state** (MEDI-38): a card that is skipped when its
value is missing keeps whatever it last showed, and a reader cannot tell stale from live.

### 5.1 IMD PRICE
USD per IMD, with IMD/ETH and the venue comparison beneath it. The subtitle names the **cheaper
venue**, and says nothing at all when the gap is below the two pools' fees summed (§8.3).

### 5.2 DOWNSIDE BID
ETH standing in the backstop band and its distance under spot. **Three states, not two** — a
deployed band renders its value, `none deployed` renders when no band exists, and `unavailable`
renders when the read failed. Collapsing the middle state into either of the others is the curator
rail bug verbatim: a real negative with no representable value reads confident and green through an
outage.

### 5.3 STAKING
Trailing return over 7 days, with vault TVL and depositor count beneath. Never the bare word *APR*
(§8.1).

## 6. The panels

### 6.1 STAKERS (leaderboard slot)
Rank, address, IMD, share of vault, with a footer in the form `top 3 = NN% of vault`. **The ranking is
not the point; concentration is** — whether three wallets can walk out of this vault is a risk a
reader acts on. Addresses are chain-sourced and still escaped.

**AMENDED 2026-09-12 — the three-state contract belongs here too, and this panel shipped without it.**
§5.2 gives the hero card three states and §7.4 gives the payload three; this panel was specified with
two (`rows` / `unavailable`), and reported from a live screenshot: it painted `⚠ stakers unavailable`
during an ordinary startup with nothing wrong. The sweep is **detached** (§7.2) so tick 1's payload is
always built before the first fold can land, and a transient failure backs the tier off 300 s — so the
warning stood on a healthy launch and for five minutes after any blip. `pool4_stakers`,
`pool4_staker_count`, `pool4_staker_top3_pct` and `pool4_stakers_as_of_hhmm` all come off one slot and
are `None` together, so the widget could not tell *never swept*, *sweeping now* and *failed* apart.

The fix is one payload key, **`pool4_stakers_state`**, with a frozen `POOL4_STAKERS_STATES` vocabulary
of `pending` / `sweeping` / `failed`. The split is three-way rather than two because the manager
already holds both facts — `_pool4_stakers_task` being alive is *sweeping*, and a flag set on the
failure branches themselves is *failed* — and neither is inferred from `TierCache`, which cannot tell
them apart: `_pool_pool4_stakers` calls `mark_failed` on the "no vault named yet" path too, purely to
take the short retry. The panel's rule is **`⚠` iff `failed`**; `None` and any unrecognised word fall
to the quiet pending line, because an absent state is not evidence of a fault.

### 6.2 BURN & SUPPLY (chart slot)
Daily burn sparkline, current pace, total retired, and that as a share of supply. **Imports
`widgets/sparkline_common`; never copies the helpers** — three dashboards once carried byte-identical
copies and a fix reached none of the others.

### 6.3 SIGNALS
Four rows, each a state a reader changes behaviour on, and a flat **state summary** line beneath.

| row | says | why it earns a line |
|---|---|---|
| `burning` | `ON · headroom 0` / `OFF · headroom N` | headroom zero means every net sell burns |
| `cheaper pool` | `REFERENCE −1.5%` / `HERE` / silent | where to trade; silent below combined fees |
| `backstop` | distance under spot, share used | is there a bid under me |
| `drip backlog` | `none` / `deep` | whether the trailing return *understates* |

The drip backlog is the only dripper internal that earns screen space, and only for that reason.

### 6.4 RECENT FLOW (activity slot)
**Reuse `widgets/surf/pool4_flow.py` unchanged.** It already renders age/side/size/burned/stakers with
the representable-zero contract worked out (a BUY has no burn leg, so `0.00` is a real value and
`None` is reserved for the whole-panel unavailable state). Reuse before you build: a copy means the
next fix reaches one of them.

### 6.5 IF IMD FALLS (EV table slot)
The depth ladder — price move, ETH the hook pays, share of the band consumed. Computed in
`analytics/surf_pool4_depth.py` as a **pure function** over tick, full-range liquidity and the band:
no I/O, no clock, stdlib only. Titled and labelled as a quote from the *current* position (§8.2).

**AMENDED 2026-09-11 — the three-state contract belongs here too, and this spec originally put it in
only one place.** §5.2 gives the hero card three states and §7.4 gives the payload three; the ladder
was specified with neither, so `depth_rows` folds an **unread** band and an **undeployed** one into the
same `band_used_pct` of `0.0`. Measured through the real screen: with `pool4_backstop_liquidity` set to
`0` and to `None`, the IF IMD FALLS column is byte-identical.

That is the curator rail defect exactly — CLAUDE.md records FARM rendering `-- unknown` while HOUR
SAVED and WHALE, folded from the same dead group, said `none yet`. It is worse on this panel than on
the hero, because the ladder's entire purpose is *how much is bidding under me*: `band used 0.0%`
through an outage tells a reader the backstop is not helping them, with confidence, when the truth is
that nobody looked. **The ladder must consult `pool4_backstop_state`** — the key that already carries
the distinction — and render a third, visibly different state for unread.

## 7. Data

**The skill is not a runtime dependency.** It is Node/TypeScript; MaxPane ships by `pipx` to people
who have Python and nothing else, and no test may touch the network. Its role is what the chain
probes were for the `p` body: research now, and an **independent oracle** in tests (§9).

**The existing sweep already pays for most of this view.** Of the 62 keys `TIER_POOL4` produces, the
user view re-presents roughly two-thirds with no new read at all:

| need | already keyed |
|---|---|
| price | `pool4_current_tick` |
| burning on/off | `pool4_cap_headroom` |
| depth math input | `pool4_position_liquidity`, `pool4_eth_in_pool` |
| staking TVL | `pool4_vault_assets`, `pool4_share_price` |
| drip backlog | `pool4_backlog_imd`, `pool4_backlog_days`, `pool4_can_drip` |
| burn totals | `pool4_total_burned`, `pool4_burned_supply_pct`, `pool4_total_supply` |
| RECENT FLOW | `pool4_flow` |

**Four new fast-tier reads:** the reference pool's tick (one `getSlot0` on the pinned hookless pool
id), ETH/USD, realised `Dripped` events over 7 days, and the backstop band broken out as its own keys
(lower tick, liquidity, ETH) — only the derived `pool4_backstop_centred` is exposed today.

**One new long-tier sweep:** the sIMD share token's `Transfer` fold, for the leaderboard.

### 7.1 A naming trap
`pool4_ref_tick` **already exists** and means the hook's *internal lagged tick* — its
anti-manipulation reference, nothing to do with another pool. The cross-venue comparison must not
borrow that word. New keys are `pool4_reference_pool_tick` and `pool4_venue_gap_pct`, and the
distinction gets a comment. Two things called "ref tick" in one payload is how a wrong number renders
confidently.

### 7.2 Keys and tiers
Fast additions extend `POOL4_KEYS` (same sweep, same tier). The leaderboard gets its own
`POOL4_STAKERS_KEYS` against `SLOT_POOL4_STAKERS` — the `CURATOR_ANALYSIS_KEYS` shape, where a fixed
count is itself the tripwire.

`TIER_POOL4_STAKERS` follows curator's `TIER_ANALYSIS`: long interval, shorter retry after failure,
last-good slot, **spawned and never awaited** so first paint cannot sit behind it, and its own
`as of HH:MM` that advances **only when a new fold lands** — never on a tick that found nothing,
because a fresh time beside old data is a stale number presented as live.

### 7.3 The degraded group is full
`SOURCE_POOL4` (`p4`) is the **eighth** degraded group, and CLAUDE.md records that the eighth name is
what took the worst-case title row to exactly the pinned width. **There is no room for a ninth.** The
staker sweep therefore gets no group of its own: it serves last-good behind its stale marker, and
folds into `p4` only when it has nothing at all to serve. Curator's rule for its analysis, forced
here rather than chosen.

**AMENDED 2026-09-11, and the amendment is the load-bearing half.** The clause above — "folds into
`p4` only when it has nothing at all to serve" — was implemented by WP6 and then **removed**, with the
reasoning in `_degraded`'s comment and pinned by
`test_a_sweep_with_nothing_to_serve_names_no_group_at_all`. Verified and confirmed: the sweep reads
`vault_addr` out of `SLOT_POOL4`'s own last-good, so **it cannot have nothing to serve unless the pool4
slot is already cold — which is a state `p4` already names.** The clause was therefore never reachable
in the case it was written for, and what it actually did was name `p4` when seven pool4 panels were
live and one log endpoint was refusing the share token. A *false* degradation is the same defect as a
missed one, pointing the other way, and it is the worse of the two here: it would tell a reader the
whole pool4 group is unreliable on the evidence of one panel's slow tier. The first half of 7.3 — no
ninth degraded group — is honoured absolutely and is not negotiable.

### 7.4 Degradation
- A failed read is `None`, never `0`. No sentinel ever enters the burn series.
- `burning` separates `False` (headroom > 0, genuinely off) from `None` (could not read).
- `DOWNSIDE BID` keeps its third state (§5.2).
- `top3_pct` is `None` on an incomplete fold — **never computed from a partial sweep**, the same
  guard `clean_routed_eth` uses.

### 7.5 Purity
`analytics/surf_pool4_depth.py` is stdlib-only. New widgets join the `test_surf_widget_contract.py`
allowlist, whose **recursive** import walk covers the new analytics module — a depth-1 version was
once green while an analytics module reached `data` in one more hop.

## 8. Honesty contracts

Each carries a forbidden-word test against **composited output**, the shape
`test_the_ratchet_never_promises_the_floor` already uses. A test that greps a bare word rather than
the phrase in context is a known-fake shape here and does not count.

### 8.1 Trailing return, never bare "APR"
Realised `Dripped` events over 7 days annualised against TVL, rendered `4.0% trailing 7d`. **The
window is in the label** because the number is lumpy by construction — zero in quiet periods, spiking
after a sell-off. The new key is `pool4_trailing_return_pct`; it must **not** inherit
`pool4_implied_apr_pct`, which is the *delivery cap* and is the number the vault panel already
refuses to call APR.

### 8.2 The depth ladder is a quote, not a promise
It is what the current position bids **now**; a rebalance relocates the band. Forbidden: *guaranteed*,
*protected*, *safe*, and *floor* in the protective sense.

### 8.3 The venue gap speaks only above combined fees
**This resolves a live contradiction.** The skill disagreed with itself: `state` reported the hook
+1.5% against the reference, `share` reported +0.2% twenty-eight blocks later, and `depth` put 145
ticks (~1.45%) between them. Either the reference moved hard in five minutes or the two commands
derive the gap differently — **unresolved, and recorded as unresolved.**

So: derive it **one way, from both ticks at the same block**, with the derivation written into its
`#:` block. And the `cheaper pool` signal **stays silent below the two pools' fees summed** — a gap
smaller than that is not arbitrageable, and telling a reader to switch venues over it is telling them
to lose the spread.

### 8.4 No advice
Bakery's signals template ends with a recommendation line. That is fine for a cookie game and is
something else on a financial market: this repo ships a strictly read-only tool, and a bottom-line
"buy" would be the first thing on screen that reads as advice. It is replaced by a **flat state
summary** — `burning on · cheaper on reference · bid 0.8% under`, descriptive only. The test greps for
*buy*, *sell*, *should*, *recommend*.

## 9. Testing

**No test touches the network.** Inject a transport that raises; every payload is a committed fixture.

**The independent oracle.** Capture the skill's output at a known block, commit it as a fixture, and
assert our Python reads agree. Two independent implementations of the same protocol math — one in
TypeScript by the protocol's own author — is a far stronger check than any self-consistency test, and
it is exactly how the `0x840` / `0x2840` flag error would have been caught on day one.

**The shapes that must be real**, each because its fake version already shipped somewhere here:

- The depth ladder's expectation comes from an **independent closed form**, never from the table the
  code renders from. Plus a directional check: perturb liquidity up and down, assert the ladder moves
  the right way.
- The `burning` tri-state asserts **all three** states. A checker comparing only the `None` word is a
  logged defect.
- The width pin fails in **both** directions, and the mutation harness uses a **pyc cache directory
  unique per mutation** — one shared prefix reproduces the bug where two same-size mutations in the
  same second run the first's bytecode.
- Everything asserts against `render_strips()`, never a content string.
- A **partial-sweep fixture** proves `top3_pct` goes `None` rather than ranking a subset.

## 10. Open, and recorded as open

1. **The venue-gap discrepancy** (§8.3) — unresolved until we derive it ourselves at a single block.
2. **W7** — whether this body's row requirement fits a real laptop. Only a real screen answers it, and
   this body is the repo's best chance of being comfortably under the `p` body's 44 rows.
3. **The status-hint width** (§3) — measured, not guessed, before the third hint word is typed.

## 11. What this view will not do

- **No signing, no transactions, no calldata.** Hard constraint 1. This body displays what a market
  bids; it never offers to trade with it.
- **No API keys.** Hard constraint 2. Every read is keyless.
- **No hardcoded documented values.** Hard constraint 4, which has now paid for itself twice on this
  protocol — the reward share and the reserve floor both changed between Sepolia and mainnet and
  nothing had to change, and the vault's `decimals()` of 24 would have been indistinguishable from a
  read constant had it been typed in.
- **It does not replace `p`.** HATCHES keeps carrying the `⚠ via docs` provenance disclosure, which
  is the only mitigation we have for a trust surface knowingly widened when the announce channel never
  named the mainnet hook.
- **It gives no advice** (§8.4).
- **It does not cover other launcher markets** (§2).
