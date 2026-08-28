# FWA NETWORK — Implementation Plan

**Branch:** `feature/fwa-ecosystem-dashboard`<br>
**Input:** [`fwa_ecosystem_PRD.md`](fwa_ecosystem_PRD.md)<br>
**Decision:** approved on 2026-08-28<br>
**Scope:** one additional `NETWORK` body inside the existing FWA screen<br>
**Non-negotiable:** PULLS stays the default, keeps its existing payload contract, and
must not wait for NETWORK work on first paint.

## 1. Outcome

The shipped FWA screen has two already-composed bodies:

```text
PULLS     existing seven-widget gacha dashboard, unchanged default
NETWORK   platform + $FWA flow + FWAIR drops + verified integrations
```

`e` switches between the bodies without fetching. `escape` returns to PULLS. `c`
continues to switch Odds/Activity in PULLS and is a true no-op in NETWORK. MAXPANE
remains read-only, keyless, and usable when every NETWORK source is unavailable.

The implementation adds no signer, transaction encoder, wallet prompt, keyed endpoint,
runtime ABI download, backend, or new third-party Python dependency.

## 2. Architectural boundary

```text
existing FWAManager ───────────────────────────────┐
                                                   ├─ FWACompositeManager
FWA ecosystem clients/adapters → cache → manager ─┘       │
                                                           ▼
                                              one exact flat umbrella dict
                                                           │
                                                           ▼
                                                FWAScreen dispatch only
```

- `FWAManager.fetch_and_compute()` continues to return **exactly**
  `FWA_DATA_KEYS`. Its public constructor, lifecycle, and seven widget contracts do not
  change.
- `FWAEcosystemManager.fetch_and_compute()` returns exactly
  `FWA_NETWORK_DATA_KEYS`.
- `FWACompositeManager.fetch_and_compute()` returns exactly
  `FWA_UMBRELLA_DATA_KEYS = FWA_DATA_KEYS + FWA_NETWORK_DATA_KEYS`.
- The composite manager owns both children, concurrency, background task cleanup, and
  close-once semantics. The screen still makes one manager call per refresh.
- Widgets receive primitives and row dictionaries only. They import no `data`, ABI,
  RPC, HTTP, filesystem, or clock module.

## 3. Frozen umbrella presentation contract

The contract is defined in `maxpane_dashboard/data/fwa_ecosystem_models.py`. The order
below is normative and mechanically tested.

```python
FWA_NETWORK_DATA_KEYS: tuple[str, ...] = (
    # NETWORK snapshot/title/hero
    "network_ready",
    "network_state_block",
    "network_chain_head",
    "network_state_stale",
    "network_active_listings",
    "network_pull_quote_eth",
    "network_pending_count",
    "network_unsettled_count",
    "network_crown_pot_eth",
    "network_token_supply_fwa",
    "network_burned_since_genesis_fwa",
    "network_burned_since_genesis_pct",
    "network_last_buyback_age_s",
    "network_drop_count",
    "network_project_family_count",
    "network_project_healthy_count",
    "network_project_degraded_count",
    "network_project_unverified_count",

    # value-flow rail
    "network_flow_rows",
    "network_flow_available",
    "network_flow_history_complete",
    "network_flow_as_of_block",
    "network_flow_as_of_ts",
    "network_flow_stale",

    # FWAIR launches
    "network_drop_rows",
    "network_drops_available",
    "network_drops_as_of_block",
    "network_drops_stale",

    # project surfaces and visible legacy liabilities
    "network_project_rows",
    "network_projects_available",
    "network_projects_as_of_block",
    "network_projects_stale",

    # normalized log activity
    "network_events",
    "network_feed_available",
    "network_feed_unavailable_reason",
    "network_feed_as_of_ts",

    # NETWORK-only source health
    "network_degraded_sources",
    "network_integrity_warning_count",
    "network_last_updated_seconds_ago",
    "network_error_count",
)

FWA_UMBRELLA_DATA_KEYS: tuple[str, ...] = FWA_DATA_KEYS + FWA_NETWORK_DATA_KEYS
```

There are no duplicate names between the tuples. Every failure path returns every key.
Unavailable numeric values are `None`; measured zero remains `0`. ETH and FWA values in
this presentation dict are whole-token `float` values. All data models and decoders keep
wei as strict `int` until this one boundary.

### 3.1 Scalar meaning

| Key | Type | Meaning |
|---|---|---|
| `network_ready` | `bool` | At least one complete NETWORK snapshot has been committed to cache. |
| `network_state_block` | `int | None` | One block passed to every direct NETWORK state read in that snapshot. |
| `network_chain_head` | `int | None` | Head observed when that snapshot started; never presented as the state block. |
| `network_state_stale` | `bool` | Direct state is last-good or older than its fast-tier TTL. |
| `network_active_listings` | `int | None` | FWA core active listing count at `network_state_block`. |
| `network_pull_quote_eth` | `float | None` | Returned total quote with transaction context; never reconstructed. |
| `network_pending_count` / `network_unsettled_count` | `int | None` | Independent FWA queue stages. |
| `network_crown_pot_eth` | `float | None` | Current crown liability/pot. |
| `network_token_supply_fwa` | `float | None` | Live ERC-20 total supply. |
| `network_burned_since_genesis_fwa` | `float | None` | `1_000_000_000 FWA - totalSupply`; unavailable if the invariant fails. |
| `network_burned_since_genesis_pct` | `float | None` | Previous value divided by genesis supply, times 100. |
| `network_last_buyback_age_s` | `float | None` | Age computed upstream from an injected clock and latest decoded event timestamp. |
| `network_drop_count` | `int | None` | Successfully decoded launches in `1 .. nextLaunchId - 1`; holes do not stop enumeration. |
| `network_project_family_count` | `int | None` | Distinct current `family` values, not legacy rows. |
| health counters | `int | None` | Current project rows only; `healthy`, `degraded`, and source-unverified are separate. |
| `*_available` | `bool` | Source group answered or a labelled last-good snapshot is renderable. |
| `*_stale` | `bool` | Visible values are last-good or incomplete; never inferred from an empty list. |
| `*_as_of_block` | `int | None` | Highest common confirmed block for that group, not an umbrella block. |
| `*_as_of_ts` | `float | None` | Original observation time of the visible last-good payload. |
| `network_degraded_sources` | `list[str]` | Stable source ids, sorted: `core`, `flow_logs`, `drops`, `pullpool`, `megarip`, `fwap`, `project_logs`, `integrity`, `market`. |

`network_last_updated_seconds_ago` and `network_error_count` describe NETWORK only. The
existing StatusBar continues to use the existing PULLS `last_updated_seconds_ago`,
`error_count`, and `poll_interval`, so an optional adapter cannot make a healthy PULLS
footer red.

## 4. Frozen row contracts

These tuples are exported as `FWA_NETWORK_ROW_KEYS`. A row must have exactly its declared
keys; no widget guesses aliases or reads adapter-specific raw payloads.

```python
ROW_META_KEYS = (
    "source_kind",      # chain_state | chain_log | project_api | market_api
    "measurement",      # measured | derived | estimated
    "block_number",     # int | None
    "observed_at",      # float | None, injected-clock timestamp
    "stale",            # bool
    "verified_source",  # bool | None
    "integrity",        # ok | warning | mismatch | unknown
)

FLOW_ROW_KEYS = (
    "key",              # member of FLOW_KEYS below
    "label",            # constant presentation label
    "value",            # int | float | None
    "unit",             # eth | fwa | bps | seconds | blocks | count | none
    "configured_bps",   # int | None; route branch config beside an observed amount
    "state",            # str | None; e.g. ended, live, unavailable
    "direction",        # in | out | branch | state
    "detail",           # constant/derived prose; never required to recover the value
    "tx_hash",          # str | None
) + ROW_META_KEYS

DROP_ROW_KEYS = (
    "launch_id", "launch_address", "collection_address", "collection_name",
    "phase", "support_open", "token_count", "supported_count",
    "supporter_count", "launched_count", "terminal_count", "backing_eth",
    "total_backing_eth", "artist_credit_eth", "supporter_principal_eth",
    "supporter_reserve_fwa",
) + ROW_META_KEYS

PROJECT_ROW_KEYS = (
    "family", "surface", "version", "address", "is_current",
    "is_legacy_liability", "lifecycle", "primary_label", "primary_value",
    "primary_unit", "eth_label", "eth_value", "fwa_label", "fwa_value",
    "detail", "source_badge",
) + ROW_META_KEYS

NETWORK_EVENT_ROW_KEYS = (
    "event_id", "ts", "tx_hash", "log_index", "origin", "family",
    "version", "event_key", "event_label", "eth_amount", "fwa_amount",
    "detail",
) + ROW_META_KEYS
```

Closed vocabularies:

```python
FLOW_KEYS = (
    "protocol_escrow_eth", "refund_credits_eth", "settlement_payout",
    "crown_share", "buyback_gross_eth", "buyback_swap_eth",
    "caller_reward_eth", "fwa_bought", "purchaser_route",
    "depositor_route", "burn_route", "burned_since_genesis",
    "burn_24h", "burn_7d", "emissions", "rewards_balance",
    "claim_balance", "token_buy_allowance_eth", "official_integrity",
)

DROP_PHASES = (
    "uninitialized", "escrowing", "supporting", "launching",
    "complete", "failed", "unwinding", "unknown",
)

PROJECT_FAMILIES = (
    "pullpool", "group_pull", "standing_orders", "megarip", "fwap",
)

SOURCE_BADGES = (
    "VERIFIED", "CHAIN-READ", "API STALE", "INTEGRITY", "DEGRADED",
)
```

Project `primary_unit` is one of `rounds`, `packs`, `orders`, `recovery_pct`, or
`nav_eth`; it is always rendered beside `primary_label`. `eth_label` and `fwa_label`
prevent a liability, accounted balance, final pot, and NAV from being presented as the
same concept.

A legacy `PROJECT_ROW_KEYS` row is included only when `eth_value > 0`, `fwa_value > 0`,
or `integrity != "ok"`. A finalized old version with zero outstanding state is omitted.

`event_id` is exactly `"1:{address_lower}:{tx_hash_lower}:{log_index}"`. Normalization
deduplicates on this id, never on display text or timestamp. Newest `(block_number,
log_index)` sorts first.

## 5. Frozen widget signatures

`FWA_NETWORK_WIDGET_SIGNATURES` is asserted against keyword-only `update_data()`
parameters. Every parameter has a `None`, `False`, or empty-list default.

```python
FWA_NETWORK_WIDGET_SIGNATURES = {
    "FWANetworkHero": (
        "network_ready", "network_state_block", "network_state_stale",
        "network_active_listings", "network_pull_quote_eth",
        "network_pending_count", "network_unsettled_count",
        "network_crown_pot_eth", "network_token_supply_fwa",
        "network_burned_since_genesis_fwa",
        "network_burned_since_genesis_pct", "network_last_buyback_age_s",
        "network_drop_count", "network_project_family_count",
        "network_project_healthy_count", "network_project_degraded_count",
        "network_project_unverified_count",
    ),
    "FWAFlowRail": (
        "network_flow_rows", "network_flow_available",
        "network_flow_history_complete", "network_flow_as_of_block",
        "network_flow_as_of_ts", "network_flow_stale",
    ),
    "FWAIRDropBoard": (
        "network_drop_rows", "network_drops_available",
        "network_drops_as_of_block", "network_drops_stale",
    ),
    "FWAEcosystemRegistry": (
        "network_project_rows", "network_projects_available",
        "network_projects_as_of_block", "network_projects_stale",
    ),
    "FWANetworkActivity": (
        "network_events", "network_feed_available",
        "network_feed_unavailable_reason", "network_feed_as_of_ts",
    ),
}
```

The existing `FWA_WIDGET_SIGNATURES`, `FWA_ROW_KEYS`, and `FWA_DATA_KEYS` are not edited.

## 6. Frozen manifests

### 6.1 Manifest shape

`ProjectManifest` is a frozen, extra-forbidden boundary model:

```text
family, surface, version, role, address, deployment_block, abi_resource,
runtime_codehash, source_status, is_current, dependencies
```

- Addresses are stored lowercase and checksummed only for display.
- `source_status` is `verified` or `unverified`.
- `dependencies` is a tuple of `(getter, expected_address_lower)` pairs.
- A runtime hash or dependency mismatch changes semantic values for that manifest to
  unavailable. Only explicitly dated last-good rows may remain with `INTEGRITY`.
- `CHAIN-READ` requires bytecode, the vendored ABI/topics, every declared dependency,
  and at least one lifecycle/accounting invariant. It never derives from frontend copy.

### 6.2 Project adapter manifest

The following values were checked against Ethereum and are the V1 registry. Runtime
hashes are the keccak256 of deployed runtime bytecode observed during the approved
research/plan pass.

| Family / surface | Version / role | Address | Deploy block | ABI | Source | Runtime codehash |
|---|---|---|---:|---|---|---|
| PullPool | v1 / pool | `0xb2d80254af189854bf90d2c338d87236d67d2bf3` | 25,625,281 | `abis/fwa/pullpool_v1.json` | verified | `0x86d7b83bf3ea73cadd39330b4eb58ca5ca3b8a25459430843db0d1b4ac78f40a` |
| PullPool | v2 / pool | `0x03c45c9c594b19ca5fde54f38c7e6b6a5f2329d7` | 25,639,384 | `abis/fwa/pullpool_v2.json` | verified | `0x9086cc5f10b8b8ee1a775ae683f0770d151665a56e7b5f9632cc2253ec68a792` |
| Standing orders | v1 / factory | `0xe60a9341c3c73636b911e609defaf05b09edeb9c` | 25,631,178 | `abis/fwa/standing_orders_v1.json` | verified | `0x1f5161fb6b898fa6e5f2634022678109704011172c7b364bc8b53b9d56562073` |
| Standing orders | v2 / factory | `0xfba041453dabbfe8b34409cf88417913cc483d1e` | 25,643,539 | `abis/fwa/standing_orders_v2.json` | verified | `0x52b7619ed66be42d34b84d32d4dafd9ead511fe74b024706de2ebf1c61280735` |
| GroupPull | v1 / pool | `0xd23dcbfd47e849dac946689e264aad3c6bbd4187` | 25,671,215 | `abis/fwa/group_pull.json` | verified | `0x3c53349d2d4b4c59cab54e3844c17ad6dc4c1967c0329801076923fb0e1957a7` |
| Group orders | v1 / factory | `0x2315f319c0e47afa26c6167e0e3a4dc46585f605` | 25,683,290 | `abis/fwa/group_orders.json` | verified | `0xb2f3058bb25e51e28915a6f0fff1dbbb9adf637a8175bc371d1e220e915b4ba8` |
| MegaRip | v1 / campaign | `0x68f8e0bd62ed310f692ae0d01f7e568948818d25` | 25,721,560 | `abis/fwa/megarip_v1.json` | verified | `0x7cd2bfa992850e1fb61393852e38f7c48b0e4fc01031ad820f3e3fd95d55ad8b` |
| MegaRip | v2 / campaign | `0x6769944589f5cc96d5f900f06539681db84ac5c6` | 25,771,992 | `abis/fwa/megarip_v2.json` | verified | `0x56b1436bab9f9a603fb91de8fea2d10abbb3adfb2d280e3ac71386b2d5e60661` |
| MegaRip | v3 / campaign | `0x58a1d8daf6d68eec8b350684e8fecc4379d13d7d` | 25,827,317 | `abis/fwa/megarip_v3.json` | unverified | `0xca1db5711ba143cedd26c4e785e6f5f5c5698503105b373c7b060377d7077541` |
| FWAP | v1 / house | `0x00000000000e56073987eaf8694fe54fca2f53de` | 25,715,581 | `abis/fwa/fwap_house_v1.json` | verified | `0x82100575483b234c314eb63993560f7f4c5df57ab61eff7b463c7056dd72b43f` |
| FWAP | v1 / share | `0x00000000007209d66e4128f17e82348d9348ac50` | 25,715,580 | `abis/fwa/fwap_share_v1.json` | verified | `0x87422373388712bace9b4fdeb9b1864e9f366eb306044f6184262d84ae6519e2` |
| FWAP | v1 / receipt | `0x00000000003031738a7cf786baadd372f4c45cbb` | 25,715,579 | `abis/fwa/fwap_receipt_v1.json` | verified | `0x0d6f24608304078fff0b229657ac4f68fbbb01cb91eaddfb48211456df66f744` |
| FWAP | v2 / house | `0x000000000095f80f42f09c4515d3ff841e65a541` | 25,791,179 | `abis/fwa/fwap_house_v2.json` | verified | `0x9994b7a30e8a3cb6600f44e921781cc83cd92ae25d3648bb7eadc3127047a071` |
| FWAP | v2 / share | `0x0000000000f7795f0e6f5c7faf837bfb8b512c8a` | 25,791,179 | `abis/fwa/fwap_share_v2.json` | verified | `0xd76dd5ad3f9c316c112c72bf05fd9d159a23f98d9fdbbc8d7c3a73ca93565c7a` |
| FWAP | v2 / receipt | `0x000000000026185bdcb69f4a2631ffc4483f8635` | 25,791,179 | `abis/fwa/fwap_receipt_v2.json` | verified | `0xcd9ed8aaac19ed7e7bf5869fa35d08b66a903ea9da3c1798efa65e49613863e9` |

Exact dependency maps:

```text
pullpool v1/v2:
  FWA -> core; FWA_REWARDS -> rewards; FWA_TOKEN -> token
standing v1:
  POOL -> pullpool v1
standing v2:
  pool -> pullpool v2; LEGACY -> pullpool v1; SUCCESSOR -> pullpool v2
group_pull v1:
  pool -> pullpool v2; FWA_TOKEN -> token
group_orders v1:
  GROUP -> group_pull v1
megarip v1/v2/v3:
  FWA -> core; FWA_REWARDS -> rewards; FWA_TOKEN -> token
fwap house v1/v2:
  FWA -> core; FWA_REWARDS -> rewards; REWARD_TOKEN -> token;
  SHARE_TOKEN -> matching share; RECEIPT_TOKEN -> matching receipt
fwap share v1/v2:
  house -> matching house; REWARD_TOKEN -> token
fwap receipt v1:
  recycler -> house v1
fwap receipt v2:
  house -> house v2; recycler -> house v2
```

MegaRip v3's ABI is the smallest chain-confirmed read/event surface required by its row
and activity events. Because source is unverified, it stays `CHAIN-READ` even when its
runtime hash and dependencies match.

### 6.3 Official integrity manifest

`fwa_ecosystem_addresses.py` also freezes the official deployment graph below. Existing
ABI resources are reused. Code-only components use `abi_resource=None` and are checked
only for non-empty code plus runtime hash.

| Role | Address | Deploy block | Runtime codehash |
|---|---|---:|---|
| core | `0xb276f62db0ce8ca2ca5bc522695be604521eac1c` | 25,546,793 | `0xa53298a411a9ce5b5d352c45e3aaa90fac78632d21e7b928425cf6eb11ab8cc4` |
| rewards | `0x6a1a1c0cfb3d3c538e13d36d608a5bcaa992fc78` | 25,546,795 | `0xf638c9e341efecf99bd093cff9b780bb3f7bf03bbd814b80c092d7e3361b4555` |
| vrf | `0xa084c33fb7a467307452898b8d58165ebd2e5d9f` | 25,546,791 | `0x8ab6e6d4ca28ade13f80314ccd54b3a648734ee88a5bcd807711fe5ae037f4a4` |
| token | `0xa0df17b5ac76ababa36e1450e2cbcd18a620c845` | 25,546,793 | `0xd07b0280e4e25689956cff42290d843739714308e6fbe693017cede05c2c52fd` |
| transfer escrow | `0xce6d5b618e034f87c7a8b6dca65fb8669b8c301b` | 25,805,935 | `0xfa15fdd90dc7d1fca0896bb6800d6ae75718369e621fe65a2c652cb812ac9f60` |
| ERC-20 wrapper | `0x727c739f07a89f11e883fe0f34937c55e4c3d74a` | 25,626,109 | `0x7290b8383665145791a739a5d8fd5c938fd70788571ad1d7999a7c7e87836c8b` |
| renderer | `0x69cc9c633867eee71b17142bbbc2c6aaf14c61a4` | 25,626,109 | `0x931f7f1b18e2b417c6d5bcdf80de1412f0b4b79551e30ddefd83586b16c2ce25` |
| token wrapper | `0x470879abd61fdca91436fe27ed87db2c8650f3e7` | 25,635,307 | `0xe501d470b0c1cf04ac52b7021b40780d33642c74461304b32cdaff3f2cb3982e` |
| hook | `0x2c67eba8a50af0db5fba55f725247a75cbda6444` | 25,546,793 | `0x5eeafce23c30462750069d6313286eca9587da8ecffdff880288d31b75d41df0` |
| owner splitter | `0x7400824eec17f86cc74385862810710f9c46ec04` | 25,747,691 | `0x4806749cbc67c6cbc0a19960a776ec43597058b92dfb05b09c526e1aa0d02438` |
| v1 claim | `0xd4085d38855f17edf0b1ccbfad7b3846fb305655` | 25,546,798 | `0x2bcc7652822828e6672fe46b9f2330ea71bad315f2df8e740605e0e0fff89f0d` |
| whitelist authority | `0x54b641ac97a9e9375665934b8e7a7d0b2c0e898b` | 25,818,569 | `0x9599c4753ca705e17cb169d7c192298b45b55f0b98ba5c4d627d522d893c4a2e` |
| FWAIR manager | `0xfbc8b4ac9b827bde0fe8b2d6aa52043704d38628` | 25,818,681 | `0x5844dd2b805ef433be410fcb954157e1f42cbfb070c20522fdf7dfd6bde566cf` |

FWAIR children are discovered dynamically. Each child's runtime hash must equal the
manager's live `launchRuntimeCodeHash()`; no child address or row count is hardcoded.

## 7. Refresh and first-paint algorithm

The composite algorithm is exact:

```python
network_task = start_or_reuse_background_network_refresh()
pulls_payload = await pulls_manager.fetch_and_compute()
if network_task.done():
    commit_its_result_without_raising()
return exact_union(pulls_payload, latest_complete_network_or_blank())
```

It **never awaits an unfinished NETWORK task after PULLS completes**. Therefore a hung
adapter, empty history, API timeout, or slow integrity check cannot extend PULLS first
paint. The task is reused rather than queued. Completion atomically replaces the complete
NETWORK cache snapshot; partial group dictionaries never leak into the umbrella payload.

The ecosystem manager obtains one state block, then passes that explicit block tag to
core/token/rewards, drops, and every project state adapter. Logs end at that block. The
PULLS payload keeps its own existing block provenance; the UI never claims the two bodies
share a block.

Refresh tiers and hard work limits:

| Tier | TTL | Failure backoff | Limit per cycle |
|---|---:|---:|---|
| fast state | 30 s | 15 s | one pinned batch per client; 8 s request timeout |
| medium state/recent logs | 60 s | 30 s | two log pages per adapter, at most 5,000 blocks/page |
| project API enrichment | 120 s | 60 s | one keyless request, 6 s timeout |
| integrity | 600 s | 120 s | one code/dependency batch, no archive reads |
| historical | watermark-driven | 60 s | two pages per adapter; detached and never first-paint blocking |

State uses the existing keyless state pool. Logs use the separate log pool. Watermarks
are `(adapter, version, topic_group)` scoped, re-read an overlap, store the last block
hash, and advance only after a complete page. Event dedupe uses `event_id`.

FWAP API enrichment is accepted only with its source block/time. `stale: true`, an older
source block, or unanchored data can annotate a chain row but cannot overwrite it.

## 8. Screen and terminal contract

The existing PULLS widgets remain direct children in their current order; they are not
wrapped in a new container. NETWORK is composed once as one initially hidden sibling body.
The mode switch hides/shows the four existing PULLS layout sections and the NETWORK body,
which avoids changing the existing PULLS sizing context.

State is separate:

```text
_mode:       pulls | network
_pulls_view: odds | activity
```

StatusBar is not expanded. It keeps its ordinary freshness segment. Its existing active
view surface receives `pulls/odds · e network`, `pulls/activity · e network`, or
`network · e pulls`. `set_key_hints()` is not used.

NETWORK layout (the body is one already-composed `Horizontal`):

```text
FWANetworkHero
Horizontal #fwa-network-body
├─ Vertical #fwa-network-main (3fr, scroll)
│  ├─ FWAFlowRail
│  └─ FWAEcosystemRegistry
└─ Vertical #fwa-network-rail (2fr, scroll)
   ├─ FWAIRDropBoard
   └─ FWANetworkActivity
StatusBar (shared)
```

- The app-wide pin stays `FULL_LAYOUT_COLUMNS = 143`.
- Implementers measure the new layout in situ across 120..150 columns and define the
  smallest honest NETWORK width constant at or below 143. The test must redden if that
  constant is moved one column in either direction.
- Measure the minimum full-content row count across 24..48 rows and define
  `FWA_NETWORK_FULL_LAYOUT_ROWS` to the first clean row. Below it, the screen title owns
  `‹ taller`.
- Both vertical columns have measured `min-height`, `overflow-y: auto`, and a stable
  scrollbar gutter. Their 3fr/2fr seam is measured in the real screen; each child also
  has a floor so a short terminal scrolls the column instead of shrinking a panel to its
  title.
- `DataTable` column tiers use measured gutter-inclusive costs and unique headers.
  `RichLog(wrap=False)` rows are fitted before write.
- Third-party names and details are fitted with `rich.cells.cell_len`, escaped, and
  passed as prebuilt `Text` where `Static` would otherwise defer markup parsing.
- Every `FWAScreen.DEFAULT_CSS` NETWORK rule is mirrored property-for-property in
  `themes/minimal.tcss`.

## 9. Error and integrity rules

- A failed read is `None`, never zero/false/empty-state prose.
- Each group owns last-good data and its original block/time. One failed adapter does not
  mark core, drops, or another project stale.
- A codehash/dependency mismatch makes current semantic metrics unavailable. A dated
  last-good row may remain with `INTEGRITY`; a badge does not bless newly decoded values.
- Buyback route bps must sum to 10,000; gross ETH must equal swap ETH plus caller reward;
  event route amounts must agree within integer rounding.
- `settlementDiscountBps` is rendered as payout bps. Fixture mutations such as 8,750 and
  crown share 75 must flow through without production constants.
- Ended emissions are determined from live start+duration and the injected clock, not
  from nonzero legacy rate getters.
- No metric calls `weightedBackingTotal` TVL. Escrow/refunds/outstanding credits remain
  liabilities; MegaRip gross recovery is not investment return.

## 10. Verification gates

All client and adapter tests inject a transport. The default test transport raises on any
unexpected network use. All time-sensitive tests inject a fixed clock.

Required gates:

1. Contract tests prove exact top-level/row tuples and widget signatures.
2. Decoder tests prove selector/topic fixtures, strict wei integers, `None` propagation,
   dependency and codehash mismatch behaviour.
3. Adapter tests cover current/legacy liabilities, FWAIR holes, API precedence, overlap,
   watermark resume, reorg replacement, and cross-adapter event dedupe.
4. Composite timing tests use a never-finishing NETWORK future and prove the returned
   PULLS payload is not behind it; shutdown cancels it and closes each child once.
5. Screen tests prove PULLS default, `e`/`escape`/`c` state, zero fetches on switches,
   independent guarded dispatch, and StatusBar freshness retention.
6. Layout tests assert composited output, two-direction boundary failure, resize
   re-tiering, gutters, `‹ widen`, `‹ taller`, hostile markup, CJK, and emoji.
7. AST import tests recursively prove NETWORK widgets cannot reach `data`, Textual-side
   I/O, `httpx`, `aiohttp`, filesystem, or clocks.

Baseline recorded before implementation in a fresh venv (Python 3.13 / Textual 8.2.8):
688 FWA tests pass; 12 known pixel/colour failures already exist in
`tests/widgets/test_fwa_accessibility.py`. Every work package must add zero failures
outside that file. Final comparison must show the same 12 node ids, not merely the same
count, plus all new tests green. The full suite is required once after integration, not
from parallel work packages.

## 11. Rollout order

1. Freeze contracts, manifests, ABIs, and offline test helpers.
2. Build core/tokenomics, drops, project adapters, cache, and shared fitting primitives in
   parallel.
3. Build the ecosystem manager and five widgets against the frozen boundary.
4. Add the non-blocking composite manager.
5. Integrate screen, theme, and app wiring in one shared-file package.
6. Run focused regression, terminal sweeps, independent review, then the full suite.

No partially wired NETWORK mode lands: production registration happens only after the
composite contract, widgets, and integration tests are green.

## 12. Definition of done

- Launching `maxpane --game fwa` still paints PULLS first with its existing seven panels.
- PULLS payload keys and widget signatures are byte-for-byte unchanged.
- A permanently hung NETWORK child cannot delay PULLS or app shutdown.
- `e` immediately reveals an already-composed NETWORK frame; no fetch occurs on switch.
- Platform, flow, manager-enumerated drops, and the five initial project families render
  from chain-backed values with independent freshness/integrity.
- No key, credential, signer, state-changing calldata path, or live-network test exists.
- The 143-column app pin does not increase; every omitted column/row is advertised.
- Targeted tests add zero regressions relative to the recorded baseline, new tests pass,
  and the final full-suite result is reviewed before merge.
