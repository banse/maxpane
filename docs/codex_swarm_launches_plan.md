# Codex plan: SWARM production launches (written 2026-10-06, revision 3)

> **Do not use any superpowers skill** (brainstorming, writing-plans, executing-plans,
> subagent-driven-development, test-driven-development, requesting-code-review, or any other
> `superpowers:*` skill), even where a skill's own trigger says it must run. The superpowers plugin
> is disabled for this project (`CLAUDE.md`, "Task triage"). This plan and `CLAUDE.md` are the
> whole process.

**Tier 2, sized over ~1,000 production lines.** It widens the data contract (two persisted slots, launch facts, a
site→launch link, an eleventh signal detector), adds explorers, a chain vocabulary, a popup and a title segment,
and touches far more than 6 files. Because the plan sizes it **above** ~1,000 lines, `CLAUDE.md` requires **one task
review per WP diff** (fix rounds capped at 2), plus the final whole-branch review, all run from Claude Code.

The owner specified it on 2026-10-06 from a screenshot of the live layout-v3 SWARM body and decided the questions
marked *owner* in chat. The questions marked *controller* were decided while this brief was written; the owner may
veto them at the WP4 look. **Every line number is a starting point (autopull `fe045932`), not a fence: verify it
before editing.** Revisions 2 and 3 fold in three independent reviews: two against the code at
`fe045932`, one against the live API (2026-10-06 00:24–00:34 UTC).

Background measurements (not needed to build, but quote them when one is questioned):
- aidude `docs/superpowers/specs/2026-10-06-maxpane-launch-alerts-plan.md`, the analysis;
- aidude `docs/launch-legitimacy-check.md`, the manual checklist the verdict automates;
- aidude `docs/imd-api-changelog.md` §3 2026-10-05.

**Fixtures:** your sandbox has no network. Every live shape this brief relies on is captured in
`tests/fixtures/surf/swarm/v8/` (19 files with `MANIFEST.json`), committed with this brief before you start. Never
re-capture.

---

## Part A: Spec

### A0. Facts and words

- **Production launch** (*owner*: "mainnet" means every production chain): `chainId ∈ {1, 8453, 4663}` **and**
  `status != "abandoned"`.
  - The status rule matters: `launches_500.json` holds 10 `abandoned` chain-1 `univ4_hook` rows (#9–#29, Aug 21–27,
    0 artifacts, parked reasons such as "nothing is being deployed to mainnet" or "its repository could not be cloned"). They must never count, pin, enrich or alert.
  - Everything else is **Sepolia** (`11155111`) or unknown, and renders as today.
- **Live state at capture:** 9 production launches, #734 to #754, all chain 1 and `live`.
  - #734 is `evm_contracts`: one `other` artifact (`Counter`), no token, `requester: null`.
  - The rest are `custom_token`: roles `token`, `distributor`, `hook` in **no fixed order** (`artifacts[0]` is the
    MerkleDistributor on #737, #741 and #754).
  - Production launches arrive at about 3 an hour.
- **The API:**
  - `/launches?limit=N` clamps N at 500, takes `before=<launchNumber>` only, ignores `chainId` / `status`, and
    orders by `launchNumber` desc. `createdAt` is **not** monotonic in that order: #747 was created after #751.
  - `count` is the page size, never a total.
  - `/sites` ignores `limit` / `before` (always 100 rows, plus `total` / `live`); some rows have `label: null`.
  - A `503 busy` is "unavailable", never "empty".
- **The launch wallet and the factory** (A2.3 K2): every production deploy so far is **one tx from
  `0xcecc29b0…a551` to `0xff03410d…7120`** (custom_token selector `0xb1ac6586`, evm_contracts `0x99674075`). In
  `/launch/policies`:
  - `params.factory` exists **only on `evm_contracts` policies**: on chain 1 (v27) and Sepolia, but not on Base or
    Robinhood, which have no evm_contracts policy.
  - `params.owner` / `params.owners.*` name **contract owners, not senders**. They equal the sender on every
    production policy today, but did not on Sepolia v11, v12 and v13 (owner `0x047f…`).
- **Links (measured; the analysis doc's `imd.fun/launches/<n>/` is dead, 404):**
  - `https://explorer.imd.fun/token/<token>` → 200 for swarm launch tokens (title "IMD › Explorer › $ZTO"), and
    404 for a self-deployed token (ADAM).
  - For a tokenless launch, `https://explorer.imd.fun/jobs/<launch jobs[0].id>` (the `/published` page links
    `#deployed` on it).
  - `https://<label>.sites.imd.fun` → 200. `*.site.identitymd.eth.limo` fails TLS ("tlsv1 alert internal error";
    eth.limo's certificate covers one subdomain level). **Every site link MaxPane renders today is dead.**

### A1. Layout: swap LAUNCHES and WORKFLOWS (*owner*)

```
top:    WORKFLOWS (1fr) | THROUGHPUT (max-width 46)
mid:    LAUNCHES (full width)
bottom: SITES (full width)
```

- Swap the two `yield`s at `screens/surf.py:3468-3473`. Mirror the CSS in `SurfScreen.DEFAULT_CSS`
  (`surf.py:3173-3214`) and `themes/minimal.tcss` (`2551-2620`): WORKFLOWS goes `width: 1fr`, LAUNCHES
  `width: 100%`.
- **Measured, not predicted.** Add a production payload to `tests/screens/test_surf_swarm_layout.PAYLOADS`,
  built from `v8/launches_100.json` with a synthetic Base row and a synthetic RH row. Re-measure:
  - `LAUNCHES_NEVER_CLEARS_BELOW` / `LAUNCHES_HIDES_NO_COLUMN_FROM` (`test_surf_swarm_layout.py:124` / `:129`,
    today 162 / 125);
  - the WORKFLOWS onsets (62 / 72), which move now that it shares a row;
  - the SITES onsets;
  - the live pin block (`surf.py:~1672-1685`, `SURF_SWARM_FULL_LAYOUT_COLUMNS`); `:1587` is history.

  Feed the new values into the boundary sets `test_surf_swarm_layout._S_THRESHOLDS` (`:132`).
- **Owner's terminal size:** v3 used about 150×46; `.claude/rules/surf.md:407` records "owner-approved live at
  200×48". Ask once, then measure at both.

### A2. Data

**A2.1 · Tier and slots** (*controller*).
- **New tier `TIER_SWARM_LAUNCHES`**: TTL 60 s, failure backoff 120 s, in `surf_cache.py`'s `TIERS` /
  `TIER_TTL_SECONDS` / `TIER_FAILURE_BACKOFF_SECONDS` (`:129-161`). It runs **detached** like
  `_spawn_swarm` / `_swarm_detached` (`surf_manager.py:5464-5491`), one read in flight. Add its `_cancel_*` to
  `close()` (`:1224-1230`).
  - **Each run reads** `/launches?limit=100`. Every 300 s it also reads `/sites` (75 KB; the host is not ours), and every 1,800 s `/launch/policies`, as a
    sub-cadence inside this tier with a stored `policies_ts`, plus once before any K2 mismatch is declared (A2.3).
  - **Failures are per route:** one route's failure or `503 busy` makes that route `None` for the cycle and keeps its
    last-good copy; the other routes still store.
  - `/launches` and `/sites` **leave** the scores sweep (`surf_manager.py:6303-6307`), which keeps its other reads.
- **`SLOT_SWARM_LAUNCHES`** (last-good): the raw list rows, the site rows, the policies, and each one's read `ts`.
- **`SLOT_SWARM_LAUNCH_FACTS`** (persisted, keyed by launch `id` = uuid): per production launch, the extracted
  fields (A2.2), the K results (A2.3) and the last-seen list row (so a launch that leaves the 100-row window still
  counts and pins). Also per site id, the site-job facts (A2.4).
  - Caps: 500 launches, 500 sites.
  - **Validate every entry on load** (a hand-edited cache file is third-party input). Both slots join `SLOTS`
    (`surf_cache.py:190`) and the coercer-validated slot list (`:1216`). Each needs its coercer in
    `surf_manager.py:~1164`, or it is dropped on load.
- The new tier **names no degraded group and adds no `SOURCES` member**, like the other swarm tiers (surf.md:58-63).
  Its rows carry their own as-of: **`swarm_launches_as_of_hhmm`**, which LAUNCHES and SITES now show instead of
  `swarm_scores_as_of_hhmm` (`surf_models.py:1529-1530`). `swarm_stale` does **not** cover the new tier; its own
  as-of shows its age.

**A2.2 · Launch facts**, per production launch, from `GET /launches/<uuid>`.
- The body is about 225 KB, mostly `rewardSnapshot` and `allocations`. **Persist only these fields, never the body:**
  - `ticker` (`attestation.manifest.token.symbol`) and `token_name` (`…token.name`);
  - `pair`: map `(chainId, manifest.pool.pairedCurrency)` through a table: `(any, 0x0…0) → ETH`,
    `(1, 0xd34a99bc…) → IMD`, `(1, 0xa0df17b5…) → FWA`, `(4663, 0x5f7bb593…) → IMD`, `(8453, 0xff0c532f…) →
    FRENPET`; anything else is a short address;
  - `pool_fee` = **`manifest.pool.fee`**. The top-level `poolFee` (12500) is not the pool fee;
  - `requester` (nullable), `policy_version`, `admission` = `[(name, status)]`, `deploy_failure` = `deployFailure is not None`,
    `assurances_count`;
  - `job_ids` = `jobs[].id`;
  - `attested` = `attestation.contracts[]` as `{name, deployedCodeHash, creationCodeHash, creationCodeBytes}`.
    It lists **the project's own contracts only**; the shared MerkleDistributor / PoolInitializationGuard are not
    attested.
- **When to read:**
  - Once when the launch is first seen.
  - Again **only** when its list row's `status` or `updatedAt` changes. Never on a clock, so parked launches are
    not re-read every 60 s.
  - **Budget:** at most 3 detail reads per cycle, highest `launchNumber` first.
  - Sepolia rows and abandoned rows are never read.
- **A missing ticker** (null manifest token on a token launch) renders as `#<n>`.

**A2.3 · Verdict checks.** Run after A2.2, persist the results, and re-run only what is `unknown`.

| Check | Pass | Fail | Source |
|---|---|---|---|
| **K1** | a production list row (A2.1) | n/a | list |
| **K2** | the deploy tx (artifacts' `txHash`) has `from` ∈ the wallet set of the **launch's own** `policy_version`'s chain (every `params.owner` and `params.owners.*` value across that chain's policies up to that version), **and**, where that chain has any `params.factory`, `to` ∈ that chain's factory set. On a chain with no factory (Base, RH today), `to` is recorded but not judged. Check receipt `int(status, 16) == 1`. | `from` or a judged `to` outside the set, after re-reading `/launch/policies` once in case the launch's `policy_version` is newer than the cached copy | `eth_getTransactionByHash`, `eth_getTransactionReceipt` |
| **K3** | for each attested contract, matched to an artifact by `name`: **(a)** `keccak256(eth_getCode(address))` equals `deployedCodeHash` (lowercase hex, `0x` stripped on both sides), **or** **(b)** the attested creation code is inside the deploy tx `input`. For (b), test `keccak256(input[i:i+creationCodeBytes]) == creationCodeHash` at ABI word-boundary offsets, `(i − 4) % 32 == 0` (every real match sits right after an ABI length word). Try first the offsets whose bytes read `60 ?? 60 40 52` (the Solidity free-memory preamble; 1–2 per tx). Then, before declaring a mismatch, try every word-boundary offset: about 169 hashes (~1.7 s pure Python) for #747's 5,412-byte input. **No full byte-by-byte scan** (~53 s, and a thread does not protect the UI). (b) renders `pass (immutables)`. | neither (a) nor (b) | `eth_getCode` + the tx input; `data/keccak.py:99` |
| **K4** | every `admission` status is `passed` **and** (`deploy_failure` false **or** status `live`) | any admission check not `passed` | facts |
| **K6** *(info)* | the liquidity owner: in the receipt, the log with topic0 `ModifyLiquidity(bytes32,address,int24,int24,int256,bytes32)` (`0xf208f491…`) on **any** emitter; owner = `topics[2]`, and the emitter is recorded. n/a for `evm_contracts`. | never | receipt |
| **K7** *(info)* | `assurances_count` | never | facts |

- **K2 details:**
  - Policies without `params.chainId` (v1, v2, v4: Sepolia-era) are never in a chain's set. The zero address is
    dropped.
  - The **factory set is per chain, unbounded by version**: v26 launches are judged against v27's factory.
  - A `policy_version` still absent after the one re-read is `unknown`, never `fail`.
  - Several distinct artifact `txHash`es: every one must pass.
- **K4 details:** a failed deploy (`deploy_failure`) on a launch that is not `live` is `unknown` while it is
  `admitted`, and fails once it is `parked`.
- **Verdict precedence:** `not_deployed` (no artifacts) > `mismatch` (K2, then K3) > `failed` (K4) > `swarm` >
  `partial`.
- **Measured:**
  - #734, #737, #739, #740, #741, #745, #751 and #754 pass K3 by (a).
  - **#747 fails (a) and passes (b)** at input offset 740. Its token `IdentityToken` has constructor-time values.
- **`unknown` is never a fail:**
  - a null `eth_getTransactionByHash`, `"0x"` code, an RPC error or a missing field leaves the check `unknown`;
  - an `unknown` check is retried next cycle.
- **No copycat search** (*owner*).
- **RPC:**
  - Chain 1 goes through a **new public `SurfClient` method** that batches the three reads via `_rpc_state_batch`
    (`surf_client.py:1330`), because `_rpc_state` (`:1297`) is private to `SurfClient`.
  - Base and Robinhood each get a client that **subclasses `rpc_common.OwnedHttpClient`** (`data/rpc_common.py:146`),
    defines its own `_rpc`, and **binds an existing `rpc_classify` error-fragment table**: there are no URL tables in
    `rpc_classify`, only `ETH_ENDPOINT_LIMITATION_FRAGMENTS` (:102) and `BASE_…` (:151). Base binds the Base table;
    Robinhood binds the ETH table (no measured RH error phrasings justify a third).
  - **The URL pools are constants in each new client module,** as `cattown_client.py:85-86` does. Base:
    `https://base-rpc.publicnode.com`, `https://mainnet.base.org`. Robinhood: `https://rpc.mainnet.chain.robinhood.com`,
    `https://robinhood-rpc.publicnode.com`. All four were measured to answer the right `eth_chainId`
    (`0x2105`, `0x1237`) and to accept batches.
  - Add both clients to `tests/data/test_rpc_shared.py`'s `ALL_CLIENTS` / `RPC_CLIENTS`, and document the pools in
    `data.md`.

**A2.4 · Site → launch link** (production launches only; *controller*, from the reviews).
- **There is no structural link for single-job token launches.** The `zto` site's job is its own one-job project.
  Link a site to a production launch by the **first** method that matches, and record it in `link_method`:
  1. **`workflow`**: `site.jobId` = a workflow's `frontendJobId`, and its `contractsJobId` ∈ the launch's `job_ids`.
     Read the scores slot's persisted workflow history (`merge_workflow_history`, `data/surf_swarm.py:439`) **as a
     lookup table only**: no rows merged across the two clocks. A `workflow` link may lag up to 30 min.
  2. **`project`**: the site job's `project.versions[].jobId` ∩ the launch's `job_ids` is not empty.
  3. **`named`**: the site job's `objective` contains the launch's token address (case-insensitive, whole 40-hex
     match).
- **Methods 2 and 3 need `GET /jobs/<site jobId>`:**
  - 3.4–29 KB; one read per site, ever, at most 3 per cycle;
  - only for sites whose `createdAt` ≥ the earliest **production** launch's `createdAt`;
  - persist only `paidBy`, `project.versions[].jobId`, and the 40-hex addresses found in the objective.
- **Trust rule for `named`:** requester-written text can name any token. A `named` link **highlights only when the
  site job's `paidBy` == the launch's `requester`**; otherwise it is a plain, unhighlighted link. All three live
  `named` links agree: zto/#737, made/#741, daemon/#745.
- **Conflicts:** several sites for one launch → the newest `createdAt` is "the" site. One site matching several
  launches → no link.
- **Measured outcomes** (B3 #5):
  - zto → #737 (`named`, payer matches);
  - made → #741 and daemon → #745 (`named`);
  - **genesis and adam link to nothing**: their launches #732 / #713 are Sepolia, and Sepolia launches have no
    facts. Exercise methods 1 and 2 in unit tests of the pure matcher, against a **synthetic** production launch
    whose `job_ids` contain `71a65ccf…` / `e497ebcf…`.
  - `counter-you-know` (#734's site) matches nothing. Its objective cites #734's job URL, not a token; that is a
    known gap.

**A2.5 · Hero LAUNCHES card** (*owner*). It counts **production launches only**: line 1 is the total, line 2 the
per-status counts (largest first, whole pairs). It counts from `SLOT_SWARM_LAUNCH_FACTS`, so production launches
that left the 100-row window still count. Feed it a production-only summary; WORKFLOWS and SITES are untouched.
The edit site is the producer: `analytics/surf_swarm_signals.launch_summary` (`:100`) and its call at
`surf_manager.py:6456`. The hero (`swarm_hero.py:149`, `summary_body`) already renders a total plus whole status
pairs, largest first, so it only needs to keep doing so.

**A2.6 · Contract** (freeze first, WP1). **Every** row carries **every** new key, `None` where it does not apply,
and `SURF_ROW_KEYS` lists them exactly.
- **`swarm_launch_rows`** (`SURF_ROW_KEYS[...]`, `surf_models.py:2018`). Today `launch_rows`
  (`data/surf_swarm.py:363-387`) drops the uuid, so it gains:
  - `launch_id`, `job_id` (`jobs[0].id` from the facts, for the tokenless job link), `production` (bool), `ticker`, `token_name`, `token_address`, `pair`, `pool_fee`, `requester`,
    `policy_version`;
  - `site_label`, `site_ens_name`, `site_link_method`, `site_link_trusted`;
  - `verdict` = `{"state": "swarm"|"partial"|"mismatch"|"failed"|"not_deployed"|None, "passed": int 0-4,
    "failed": "K2"|"K3"|"K4"|None}`;
  - `checks` = `{"K1","K2","K3","K4","K6","K7": {"state": "pass"|"pass_immutables"|"fail"|"unknown"|"info"|"na",
    "evidence": {…}}}`. The evidence holds the tx hash, from/to, both hashes, the failed admission names, and the
    liquidity owner, its emitter and `owner_is_factory` (bool or None).
- **`swarm_site_rows`** (`:2023`) gains `launch_number`, `launch_ticker`, `production_link` (bool), `link_method`,
  `link_trusted`.
- **`swarm_launch_summary`** becomes production-only. Add **`swarm_launches_as_of_hhmm`**.
- **Signals** (A4): new reading keys and output keys, listed in A4.
- **The hand-typed copies that must grow** with it:
  - the `SurfSignals` map at `tests/screens/test_surf_screen.py:286`;
  - the explicit kwargs dispatch at `screens/surf.py:4182-4215`;
  - `SurfSignals.update_data`'s kwargs (`signals.py:411`);
  - `READING_KEYS` (`surf_signals.py:97`);
  - `SURF_KEYS` (`surf_models.py` around 1739);
  - `SWARM_WIDGET_SIGNATURES` (`surf_models.py:1523`).

### A3. LAUNCHES table (`widgets/surf/swarm_launches.py`)

**A3.1 · Order and pinning** (*owner* highlight, *controller* caps).
- Rows sort by **`launchNumber` desc** (the API's order), not `createdAt`.
- Production rows come first, **at most 12** (newest by number), then **at most 12 Sepolia rows**: `ROW_CAP`
  (`:203`) becomes **24 in total**. The table scrolls inside itself.

**A3.2 · Columns.** Full width now. Give each tier's specs and widths as constants, with the arithmetic in comments
as today (`:147-159`).

| key | label | width | notes |
|---|---|---|---|
| `number` | `#` | 6 | `◆` plus a space plus digits for production rows. `_NUMBER_COLS = 4` (`:82`) cannot hold `◆ 754`. |
| `ticker` | `ticker` | 11 | `$` plus up to 10, via `sanitize_cell`. `--` for Sepolia and tokenless. |
| `status` | `status` | 9 | `_STATUS_COLOURS` (`:162`) gains `admitted` (yellow). |
| `chain` | `chain` | 7 | `MAINNET` / `BASE` / `RH` / `SEPOLIA` |
| `token` | `token` | 23 (17 address + 2 icon + 4 `+n`, as `_ARTIFACTS_COLS` today) | **The token artifact first** (role `token`), as `address_text` with copy icon and explorer link. Fallback: hook, then the first artifact. Remaining artifacts are a dim `+n`. Today it is `artifacts[0]` (`:181`). |
| `site` | `site` | 16 | the linked site's label, linking to `https://<label>.sites.imd.fun` (A6); `--` when none |
| `verdict` | `verdict` | 10 | A3.3 |
| `kind` | `kind` | 13 | `_KIND_COLS = 12` (`:84`) clips `evm_contracts`, so make it 13 |
| `repo` | `repo` | 24 | for `https://github.com/identity-md-launches/` (exact prefix, like `_GITHUB`), show `launch-<n>-…`. 28 cells no longer reach the number. Fix `_TIGHT_REPO_COLS` (`:131`) with it. |
| `parked` | `parked reason` | elastic | as today |

- **Tiers, exact key sets:**
  - `full`: every key above.
  - `compact`: `full` minus `kind` and `repo`.
  - `tight`: `compact` minus `parked` and `site`, with `token` at 17 (`TIGHT_ADDR_COLS` + icon + `+n`). It **never
    sheds `ticker` or `verdict`**.

**A3.3 · Production highlight.**
- Production rows render **bold, with the `◆` mark**; Sepolia rows render dim.
- **The cue must not be colour alone:** in the `matrix` theme every cell is already green (the owner's screenshot).

**A3.4 · Verdict cell.** It always uses words. **`✓ swarm` means "the swarm launched this", never "safe"**: no other
wording, anywhere.

| `verdict.state` | Cell | Colour |
|---|---|---|
| `swarm` (K1 to K4 pass, K3 by either route) | `✓ swarm` | green |
| `partial` (no fail; `passed` < 4) | `… <passed>/4` | dim |
| `mismatch` (K2 or K3 fail) | `✗ K2` / `✗ K3` | red |
| `failed` (K4 fail) | `✗ K4` | red |
| `not_deployed` (production, no artifacts yet) | `-- pending` | dim |
| `None` (Sepolia) | `--` | dim |

- **A `mismatch` raises a SWARM title alarm**, following v3 A3's rules (SWARM mode only): `⚠ launch #<n> K3`, with
  n > 1 shown as `⚠ <n> launch checks`.

**A3.5 · Detail popup** on **Enter or a click** on a LAUNCHES row. Never `x`: `x` is bound to
`action_toggle_throughput` (`surf.py:2536` / `:3672`).
- **Hoist WORKFLOWS' row-select into `_swarm_table.SwarmTableBase`, opt-in.** This lifts v3 A4's "WORKFLOWS only"
  note, per CLAUDE.md "Reuse before you build". It covers the `Selected` message, the `_selection_rows` snapshot
  (`widgets/surf/swarm_workflows.py:232-258`), **and** the one-click select with copy/explorer-icon routing
  (`_WorkflowTable._on_click`, `:197-209`, `compose_body` `:237-239`).
  - **A class flag, `SELECTABLE = False` in the base,** set True on WORKFLOWS and LAUNCHES.
  - **Each selectable subclass declares its own `class Selected(SwarmTableBase.Selected): pass`.** Textual names a
    handler after the class that defines the message, so an inherited `Selected` dispatches to
    `on_swarm_table_base_selected`, which would break `surf.py:3678` and the new handler (measured on 8.1.1).
  - **Non-selectable subclasses neither stop nor swallow `DataTable.RowSelected`.** BOARD's seat pick
    (`SurfSwarmLeaderboard` / `_SeatTable`, `swarm_leaderboard.py:23-32`, `:58`) relies on it reaching
    `SurfScreen.on_data_table_row_selected` (`surf.py:3714`). Add a regression test that BOARD Enter still selects a
    seat.
- Add a `LaunchDetailScreen(RecordDetailScreen)` to `screens/swarm_detail.py` (pattern: `WorkflowDetailScreen`,
  `:18`), opened from a new `on_surf_swarm_launches_selected` (pattern: `surf.py:3677-3680`).
- **Contents:**
  - every artifact with copy icon and chain explorer link;
  - ticker, name, pair, pool fee, requester, policy version;
  - K1 to K4 with their evidence, and K6 / K7 as information. K6 reads `liquidity held by <address> (factory,
    unverified)` when it equals a policy factory, and **never "locked"**;
  - the site, linked;
  - the IMD token page (A6), or for a tokenless launch the job page.
- **Test the click-to-open links on Textual 8.1.1 and 8.2.8**, as v3 did.

### A4. Signals: the `SWARM LAUNCH` detector

- **Label** (*owner*): `SWARM LAUNCH`, 12 cells, the same as `BRIDGE STAGE`, which "must stay the widest"; that
  still holds.
  - Append it to `DETECTOR_LABELS` (`signals.py:192`), `_ROW_KEYS` (`:206`, `("swarm", "#surf-sig-swarm")`) and
    `_DETECTORS` (`surf_signals.py:1345`).
  - It is the **eleventh** detector.
- **A dedicated mechanism, not `BASELINE_EVENT_KEYS`** (*controller*, from the review). That machinery keeps one
  newest `(tx, ts, seq)` with hex tx hashes, so an `admitted` → `live` move or two launches in one read could
  never fire.
  - **Reading** `swarm_launch_events`: production rows `{launch_id, number, status, ticker, chain_id,
    token_address, verdict_state}`, joined from `SLOT_SWARM_LAUNCHES` (status, number, chain) and
    `SLOT_SWARM_LAUNCH_FACTS` (ticker, token, verdict), with the list's read `ts`. Absent or `None` = failed read.
  - **Baseline** `swarm_live_seen`: a persisted set of launch ids seen `live`, seeded **silently** on the first
    successful read. It is capped, and it gets a coercer (a set of uuid strings; anything else is a failed read).
  - **Fired map** `swarm_launch_fired`: `{launch_id: {ts, number, ticker, chain_id, token_address, verdict_state}}`.
    It is persisted, survives a restart, and entries expire at `FIRED_TTL_S` (24 h). The fired `ts` is when this
    app first saw the launch `live`.
  - **Persistence needs new cache code** (WP2, `data/surf_cache.py`). `_sanitise_baselines` (`:985-1024`, run on
    every `set_baselines` `:1048` and on load `:1280`) keeps a nested mapping only under `"fired"` and cuts lists at
    `BASELINE_LIST_CAP = 64` (`:396`), so as-is both structures would vanish or re-fire. Add two named branches, the
    way `BASELINE_FIRED_KEY` is handled:
    - `swarm_live_seen`: a list of canonical uuid strings with its own cap of **500** (never `BASELINE_LIST_CAP`;
      it must be at least the most production rows a reading can hold, which is ≥ 100), evicting the oldest-seen
      first;
    - `swarm_launch_fired`: validated like `_sanitise_fired` (finite `ts` not past the horizon, strings capped).
  - **`build_signals` advances both explicitly** (the `hot_leader` injection pattern), and `_advance` must not copy
    them raw.
  - **FIRED:** any id newly seen `live` → add it to both. It never re-fires, and a failed read never un-fires.
  - **WATCH:** a production row is `admitted` and its id is not in `swarm_live_seen` (`deploying $T #<n>`).
  - **OK:** `no new swarm launch`.
- **Detail** (*owner*: ticker first; the launch number follows it, because two launches already share `$IMD`,
  #739 and #751):
  - `$ZTO #737 MAINNET ✓ 0x<full token address>`, plus ` +<k>` when k more are FIRED;
  - the full address, so the widget windows it with a copy icon, as NEW DEPLOY does. A tokenless launch (#734) ends
    after the verdict word;
  - the verdict word is the A3.4 cell text (`✓ swarm` shortened to `✓`, `… n/4`, `✗ K3`, …);
  - the ticker is escaped at the widget;
  - `_cut_detail` sheds from the right: ` +<k>` goes first, then the address. The ticker and number always
    survive.
- **New output keys:**
  - `sig_swarm_chain_id`, so the panel links the address through **that chain's explorer**. Every other detector
    keeps `EXPLORER = ETHEREUM` (`_fmt.py:65`, used at `signals.py:375`).
  - `swarm_launch_fired`: the list for the title, newest first.
  - Declare both in `SURF_KEYS`. The widget and the title read these keys, never the detail string.
- **Title segment, in every body** (*owner*). This **supersedes `.claude/rules/surf.md:435-441`** ("Title alarms,
  SWARM only … Default and AGENT titles do not change"); WP5 rewrites that paragraph. The segment is a different
  kind from v3's alarms: news, rendered in the theme's accent, not the alarm colour.
  - **Text:** `▲ SWARM LAUNCH $ZTO #737` for one, and `▲ <n> SWARM LAUNCHES` for several.
  - **Lifetime** (*controller*): **60 minutes** from the fired `ts`. At about 3 launches an hour, the 24 h TTL
    would light it permanently. The signals row keeps its 24 h FIRED.
  - **Age:** `data["as_of"] − fired ts`, so tests are deterministic.
  - **Edit site:** `_title_line` (`surf.py:2385`); `_render_title` (`:3989`) only calls it. Insert the segment
    **immediately before `_fmt_degraded`**, after `as of`, the taller hint and the LP warning (`:2457-2465`), whose
    priority order stays. SWARM's compact fallback (`:2468-2477`) carries the segment ahead of its compact
    alarms.
  - **Width:** the default title has zero margin today (`test_surf_screen.py:3480-3502`, "one more word anywhere on
    this line puts the worst case past 143"). So when the segment is lit and the worst case would pass 143, the
    degraded list **collapses to `⚠ <n> src`**, the pattern of SWARM's compact fallback (`surf.py:2468-2477`); drop
    the ticker before that.
  - **AGENT** (`_agent_title_head`, which drops the degraded list at `:2465`) shows the segment the same way.
  - `WORST_CASE_TITLE_COLUMNS` (143) **must not move**. If no honest short form fits at a pin, **stop and ask**.
- **Rail height:** an eleventh row can grow the hero rail when nothing quiet-collapses. Measure the default body
  with every detector non-OK using the `test_surf_screen` sweeps; `measure_layout.py` covers only `s` / `a` / `b`.

### A5. SITES (`widgets/surf/swarm_sites.py`)

- Rows with a **trusted** production link (`production_link and link_trusted`) render **bold with `◆`** (as A3.3)
  and show the ticker after the label: `zto · $ZTO`. Clip the label first, never the ticker.
- An untrusted `named` link shows the ticker **dim, without `◆`**.
- **Pinning:** trusted production-linked sites pin above the others, at most 10 (`ROW_CAP`, `:188`), so one cannot
  fall off the panel.
- There is no popup or tooltip in SITES. The link method is visible only in the LAUNCHES popup.

### A6. Chain words, explorers and links

- **Chain words:**
  - `CHAIN_ID_WORDS` (`_swarm_chain.py:57`) and `_NETWORKS` (`data/surf_swarm.py:68`) gain `8453: "BASE"` and
    `4663: "RH"` (*owner*). Their agreement test is `tests/widgets/test_surf_swarm_chain.py:28`.
  - **`chain_word` stops delegating to `_pool4.network_word`.** That function's `NETWORK_WORDS = ("SEPOLIA",
    "MAINNET")` (`_pool4.py:148`) is pool4's closed vocabulary, bound to `surf_models.POOL4_NETWORKS` by
    `tests/widgets/test_surf_pool4_shared.py:119-120`. **Do not widen it.** `chain_word` validates against
    `CHAIN_ID_WORDS` itself, keeping the bool/int guard and the em dash; update its module docstring.
- **Explorers:**
  - Add `ROBINHOOD = Explorer("robinhood", "https://robinhoodchain.blockscout.com", ("address", "tx"))` to
    `EXPLORERS` (`explorer.py:81`), `_CHAIN_IDS` (`:96`, `4663`) and `explorer._NETWORKS` (`:86-90`, `"RH"`).
    `test_explorer.py:171-186` requires every swarm word to resolve. Update
    `test_for_chain_id_maps_the_three_ids_and_nothing_else` (`:163`).
  - **IMD token page:** give the `IMD` explorer (`explorer.imd.fun`, `:75`) a `token` kind (address value) with a
    `token_url` → `https://explorer.imd.fun/token/<address>`. Wire it through `KINDS` (`:59`), `_valid`, the
    action round-trip, `url_for` (`:217-227`, which today falls through to `job_url` for any unknown kind), and an
    `address.py` helper. Also update `test_for_network_maps_the_three_words_and_nothing_else` (`test_explorer.py:155`). For a tokenless launch, link the job with the existing `job`
    kind.
  - **No `imd.fun/launches` kind** (404), and **no chart link**.
- **Fix the site links:** `SITES = Explorer("sites", "https://site.identitymd.eth.limo", ("site",))`
  (`explorer.py:78`) becomes `https://sites.imd.fun`. `site_url` (`:206-214`) prepends the label, so the change is
  the base URL plus `site_text` (`address.py:283`), which today links only a `<label>.site.identitymd.eth` value.
  - **The `site` kind's value becomes the bare LDH label.** Change `SITE_RE` (`:56`) / `is_site`, the `_ACTION_RE`
    value, `site_url`, `site_text` and their round-trip tests together.
  - **The label is** the row's `label`, else the `ensName` minus `.site.identitymd.eth` when it ends with that suffix.
    The 9 `named` rows in `sites.json` with `label: null` but a valid `ensName` (all superseded) keep their link.
    A row with neither has none.
  - It keeps showing the ENS name as text.
  - It **never uses the API's `site.url`**, which is the dead eth.limo URL.
  - Update the docstrings at `explorer.py:16-21` and `_fmt.py:72-74`, and the docs that name eth.limo: surf.md
    396-397, `.claude/rules/widgets.md:68`, README.md:168, and the `swarm_sites.py:44-46` docstring.

### A7. Out of scope

- Copycat search.
- Self-deployed swarm code (ADAM-style tokens with no production launch row).
- Site links by job reference (`counter-you-know`).
- Chart links.
- macOS notifications: aidude's `launch-watch` covers those on the owner's Mac.
- Any "safe", "audited" or "locked" wording.

---

## Part B: Plan

### B0. Where to work

```bash
cd /Users/banse/codex/maxpane
git fetch autopull && git switch -c feature/swarm-launches autopull/main   # the commit carrying this brief + v8 fixtures
```

- **Start from `autopull/main`.** The clone was last on `feature/swarm-layout-v3`.
- **Two Textual versions:** the clone's `.venv` runs Textual 8.2.8; the owner's dev venv runs 8.1.1. Run anything
  selection- or click-shaped on both.
- **Colour tests:** the session exports `NO_COLOR=1`, so run tests as `env -u NO_COLOR …`.

### B1. Rules (CLAUDE.md, current; read it first, and `.claude/rules/surf.md`, `widgets.md`, `data.md`)

- **Tests, two steps:**
  - While editing: node ids or `-k` only.
  - Once before each commit: the touched test files and the composing screen file whole, via
    `HOME=$(mktemp -d) .venv/bin/python -m pytest -n 4 --dist worksteal <files>`.
  - Plus the guard set: `.venv/bin/python -m pytest -m "guard and not mounts_app" tests`.
  - Plus `-m mounts_app tests/test_surf_registration.py tests/test_curator_registration.py
    tests/test_fwa_guardrails.py` whenever widget registration or `BINDINGS` change.
  - Plus the doc pins: `-m docpin tests/test_surf_registration.py tests/test_curator_registration.py`.
- **No full suite.** The controller runs it only if the owner asks or before a tag.
- **No test touches the network.** Build every test from `tests/fixtures/surf/swarm/v8/`; its `MANIFEST.json`
  says what each file is and what was trimmed. Synthetic cases are built **in the test** from those files:
  - a wrong `from`;
  - a wrong code hash with no creation-code match;
  - RPC down;
  - a Base row and an RH row (chain id and addresses swapped);
  - a production launch whose `job_ids` include `71a65ccf…` / `e497ebcf…`;
  - an `admitted` row;
  - a production row past the 100-row window.
- **Mutation proof:** `scripts/mutate.py`. Report which test reddened.
- **Layout:** `scripts/measure_layout.py s <payload> WxH`, run in situ; sweeps on boundary sets.
- **CSS:** every screen rule goes into both `SurfScreen.DEFAULT_CSS` and `themes/minimal.tcss`, identically.
- **Third-party text** (ticker, token name, site label, objective-derived text) goes through `markup_safety`
  before any markup, in the table, the popup, the signals detail and the title.
- **Process:**
  - Commit per WP, with a pathspec.
  - Never merge or push.
  - Touch only your branch.
  - Leave no plan workspace or scratch files in the tree.

### B2. Work packages

Each WP ends with its diff sent for **one task review** (fix rounds ≤ 2) before the next starts.

| WP | Content | Files it may change | Stop |
|---|---|---|---|
| WP1 | Contract freeze (A2.6) · A6 chain words, ROBINHOOD, the IMD `token` kind, the site-link fix | `data/surf_models.py`, `data/surf_swarm.py` (`_NETWORKS`), `widgets/surf/_swarm_chain.py`, `widgets/explorer.py`, `widgets/address.py`, `widgets/surf/_fmt.py` (docstring); **contract-only** edits (signatures and kwargs, no behaviour) to `widgets/surf/signals.py` (`update_data`), `analytics/surf_signals.py` (`READING_KEYS`), `swarm_launches.py` / `swarm_sites.py` / `swarm_hero.py` (`update_data` parameters) and `screens/surf.py:4182-4215` (dispatch), so that `test_surf_widget_contract.py` (:339, :822), `test_surf_models.py:621` and the `test_surf_screen.py` maps (:286, :654) stay green; their tests | review |
| WP2 | Data: A2.1 tier and slots · A2.2 facts · A2.3 K checks and the per-chain RPC clients · A2.4 site link · A2.5 production summary | `data/surf_cache.py`, `data/surf_manager.py`, `data/surf_swarm.py`, `data/surf_swarm_client.py`, `data/surf_client.py`, new `data/<base/rh rpc clients>`, `analytics/surf_swarm_signals.py` (`launch_summary`), new pure modules in `analytics/` (launch checks, site match), the per-chain clients, `tests/data/test_rpc_shared.py`, their tests | review |
| WP3 | Widgets: A3 LAUNCHES (columns, pinning, highlight, verdict) · row-select hoist · A5 SITES · A4 detector (analytics plus panel row, per-row explorer) | `widgets/surf/swarm_launches.py`, `_swarm_table.py`, `swarm_workflows.py` (hoist only), `swarm_sites.py`, `swarm_hero.py`, `_swarm_summary.py`, `signals.py`, `analytics/surf_signals.py`, `data/surf_manager.py` (`_readings` `:2642`, `_signal_keys` `:6542-6576`, which today copies only `sig_{name}_state/detail/age_s`), their tests | review |
| WP4 | Screen: A1 swap and CSS · A3.5 popup (`screens/swarm_detail.py`) · A4 title segment (`_title_line`) · A3.4 mismatch alarm · the signals dispatch (`surf.py:4182-4215`) | `screens/surf.py`, `screens/swarm_detail.py`, `themes/minimal.tcss`, their tests | **STOP: the owner's live look** |
| WP5 | Hardening: pins re-swept, the B3 regressions with mutants, the address sweep, docs, follow-ups | tests; `screens/surf.py` (pin constants and `#:` blocks only); `.claude/rules/surf.md` (swarm tiers `:58`, SITES `:396`, title `:435`, layout `:445`), `widgets.md:68`, `data.md` (the RPC pools), README, the terminal-layout skill's pin table, CHANGELOG | then report for the final review |

**The WP4 STOP is hard.** The controller or the owner runs the app keyless against live data at the owner's size;
your sandbox has no network. Base and RH appear only in fixtures.

### B3. Named regressions (each must redden under its named mutant)

1. #737 and #741: the token column shows the **token**, not the MerkleDistributor. *Mutant: revert to
   `artifacts[0]`.*
2. Production rows stay pinned above 12 newer Sepolia rows, and a production row that left the 100-row window still
   counts and pins. *Mutants: drop the pin; read the count from the list.*
3. #734 (`evm_contracts`): ticker `--`, its `Counter` checked by K3 (a), K6 `na`, and verdict `✓ swarm`.
4. **#747: K3 passes by (b), `pass (immutables)`, verdict `✓ swarm`.** *Mutant: drop route (b) → `✗ K3`.*
5. A wrong `from` gives `✗ K2`. RPC down gives `… n/4`, never `✗`. A `policy_version` newer than the cached policies
   re-reads them before judging.
6. Site links: zto → #737 (`named`, trusted, highlighted). Genesis and adam: no link, not highlighted. **Pure-matcher
   tests** (adam's site predates the createdAt gate, so the app never reads its job) link genesis by `workflow` and
   adam by `project` against the synthetic production launches. A `named` link with a different payer is
   unhighlighted.
7. The hero LAUNCHES card counts production launches only: the fixture's count (9 in `launches_100.json`), never
   100. The 10 abandoned chain-1 rows in `launches_500.json` never count.
8. Base and RH rows: tokens link to basescan / `robinhoodchain.blockscout.com` in LAUNCHES, the popup and the
   signals detail. Test the signals link at a width where the detail keeps its address; at the 143 pin it is shed.
9. SWARM LAUNCH:
   - It fires once per launch, including `admitted` → `live` and two launches in one read.
   - It survives a restart as FIRED with its age, and never re-fires on a failed read.
   - Its title segment shows in a non-SWARM body for 60 minutes and then goes, while the signals row stays FIRED
     for 24 h.
   - It survives 600 seen launches: none re-fires after `swarm_live_seen` evicts (cap 500, oldest first).
12. Row-select hoist: WORKFLOWS' popup and BOARD's Enter seat pick still work, and LAUNCHES' Enter opens its popup.
    *Mutant: an inherited `Selected` with no subclass declaration.*
10. Every site link points at `<label>.sites.imd.fun` and none uses `site.url`. A `label: null` row with a valid
    `ensName` links by the derived label; a row with neither has no link.
11. A ticker containing markup (`[red]X`) renders literally in the table, the popup, the signals and the title.

### B4. After the final review

Report to the controller (Claude Code). Do not merge, push or tag. The controller verifies independently and the
owner decides.
