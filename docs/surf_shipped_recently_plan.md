# BUILT BY SWARM: shipped recently

Approved scope, 2026-10-15: proposal 1 with a type column. Tier 2 because this
changes a widget and its dispatched row contract. Estimated total production
diff: under 1,000 lines; one final review, no package reviews.

## Result

- LAUNCHES occupies the former top-left WORKFLOWS area. Remove its parked-reason
  column. WORKFLOWS occupies the former full-width LAUNCHES row. SITES stays below.
- The top-right widget becomes SHIPPED RECENTLY: five newest shipped items, plain
  aligned lines without table headers, zebra rows or a table cursor.
- Each line reads age, name, type. Age is muted, name green, and type aligned.
  Names are token tickers, short site labels without `.sites.imd.fun`, or served
  contract names. Preserve literal third-party strings safely and fit by cells.

```text
SHIPPED RECENTLY · as of 17:18

   ~4m  $EHS                    token
   12m  weir                    site
  ~35m  PvPPad                  contract
   ~1h  $BIT                    token
    2h  hongbao                 site
```

The sample is illustrative, not captured production data. The tilde qualifies
launch times because the existing launch API supplies update/request times,
not an independently confirmed deployment timestamp.

## Frozen input contract

Keep the public `SurfSwarmLatestLaunches` class and signature constant to avoid
unnecessary registry churn. Extend its inputs to:

```python
SWARM_LATEST_LAUNCHES_SIGNATURE = (
    "swarm_launch_rows", "swarm_site_rows",
    "swarm_launches_as_of_hhmm", "as_of",
)
```

Append `named_ts: float | None` to `SURF_ROW_KEYS['swarm_site_rows']`. Preserve
raw `namedAt` through `surf_swarm._SITE_FIELDS`; `site_rows` projects it with the
existing timestamp parser. Old caches remain valid and yield `None` until the
normal site refresh. No new top-level collection, route, cache version or RPC.
Launch rows already contain production, status, kind, artifacts with names and
addresses, ticker/name, created_ts and updated_ts; no duplicate shipped_ts field.

Evidence: v9 `sites.json` contains distinct createdAt, pinnedAt and namedAt;
namedAt is publication. v9 `launches_100.json` and `launch_791.json` contain only
createdAt/updatedAt; artifact verifiedAt and job attachedAt are not deployment
timestamps. Launch ages use updated_ts, then created_ts, and visibly qualify
the approximation with `~` plus a short tooltip. Site ages use named_ts only.
Missing timestamps show `--` and sort after known timestamps. Use supplied
as_of for ages; no widget clock or network call.

## Selection and negative states

- Launch entries require production=True, status live, and actual deployed
  artifacts. Testnet, parked, admitted and abandoned launches do not appear.
- A token deployment yields one token item; do not list its distributor/hook
  as extra contract shipments. Non-token deployments use served contract
  artifact names; never invent a primary contract name from objectives.
- Sites use the existing current-site predicate plus successful publication
  status. Sites have no chain field; production_link indicates an association
  with a production launch, not the status of a standalone website. Preserve
  standalone published sites rather than filtering them out for lacking a join.
  Exclude sites with a confirmed testnet association when the available rows
  establish one; a missing production join alone does not establish testnet.
- Merge/deduplicate identities, sort newest first with deterministic ties, cap
  at five. Take independent snapshots so refresh/input mutation cannot change
  an opened detail screen.
- Preserve `x` as the latest production-launch popup shortcut independently
  of the mixed list. Launch/contract activation retains the launch detail
  message. Site names use `site_text` and the validated sites explorer route.
- No successful source is not the same as successful empty sources. Render
  explicit unavailable, empty, and partial-source states with the existing
  joint source marker; do not disguise failed reads as an empty shipment list.

## Packages and ownership

| Package | Owner | Files | Dependency |
|---|---|---|---|
| Data contract | data worker | data/surf_swarm.py, data/surf_models.py; corresponding data projection/cache/model tests | frozen contract above |
| Plain shipped list | widget worker | widgets/surf/swarm_latest.py, tests/widgets/test_surf_swarm_latest.py | frozen contract; data runtime can land independently |
| Table/layout integration | controller | widgets/surf/swarm_launches.py; screens/surf.py; themes/minimal.tcss; launch-table/composing/layout tests; layout docs/followups | widget interface preserved; integrate both workers |

Only one owner edits each shared file. Workers must preserve unrelated edits
and must not dispatch subagents. Planner owns this document only.

## Delivery and verification

1. Write focused failing tests before implementation. Data tests cover namedAt
   persistence/projection, legacy cache and exact row/signature keys. Widget
   tests cover mixed ordering/cap/dedup, production/live filtering, timestamps,
   safe names, no DataTable, column alignment, no input mutation, activation,
   and unavailable/empty/partial states. Root tests check widget regions,
   column removal and existing shortcut behavior in the compositor.
2. Once integrated, show a live keyless render at the known owner size 149×45
   before measurement/docs hardening or review. Incorporate any corrections.
3. Use `scripts/measure_layout.py` for the actual `s` body and affected boundary
   payloads. Update pin `#:` evidence and terminal-layout docs from measurement;
   do not infer pin changes from column arithmetic alone.
4. Demonstrate focused mutation proof for the changed contract/filter/layout
   behavior with `scripts/mutate.py`; restore via inverse changes. Run touched
   and composing test files whole once in isolated HOME with `-n 4 --dist
   worksteal`, plus fast guards and relevant docpins. No network in tests,
   no real clipboard, and no full suite.
5. One final whole-diff review by the controller's generic reviewer, one fix
   wave, and scoped re-review only if production code changed. File Minor-only
   findings in followups. Commit locally; no push unless requested.

All test/render commands unset NO_COLOR so palette checks see the real styles.
Keep prior shared card color/padding changes and unrelated untracked files.
