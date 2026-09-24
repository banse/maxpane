# Surf AGENT — RUNTIME update check (plan for Codex)

Owner, 2026-09-24: when the AGENT view loads a seat, check whether the seat's LLM runtime and its
daemon are out of date. If one is, highlight that line in the RUNTIME card. Second request, same
day: rework three AGENT hero boxes (WORK / ACCEPTED / RANK, §1b and WP5–WP6).

Branch: `feature/surf-runtime-updates` in this clone, cut from autopull main `407b8f6` (already
checked out). **Tier 2.** It adds a new keyless source, new payload keys and fixtures, and it
touches `data/surf_models.py`.

Run WP0–WP6 straight through with no pause (docs last: WP4 covers both parts). Commit per work package. Do not merge or push. Send
ONE final report: commits, tests run with counts, mutation proofs (each naming the test that
turned red), and anything you filed in the follow-ups doc.

Precedence: CLAUDE.md > this plan > your judgement. If this plan contradicts CLAUDE.md, follow
CLAUDE.md and record the conflict in the follow-ups doc. Never invent owner approval.

## 1. Owner decisions (fixed)

1. **LLM runtimes are compared with the npm registry's `latest` dist-tag.** This source is keyless.
   Probed 2026-09-24:
   - `GET https://registry.npmjs.org/@anthropic-ai/claude-code/latest` → `{"version": "2.1.281", …}`
   - `GET https://registry.npmjs.org/@openai/codex/latest` → `{"version": "0.156.1", …}`

   Runtime id → package is a hand-typed table: `claude` → `@anthropic-ai/claude-code`,
   `codex` → `@openai/codex`. Any other runtime id is **not checked** (never guessed).
2. **The daemon is compared with the fleet majority.** There is no public "latest daemon" source.
   `/health.version` is the API server's build (`0.1.0+e2af7a8e`), which no daemon runs. Live
   `/workers` on 2026-09-24 showed 242 of 298 daemons on `0.1.0+cff23c39`. The reference is the
   `daemonVersion` that the most workers in the already-read `/workers` payload report.
   - Only a **unique** top version counts; on a tie there is no reference.
   - Take no second `/workers` read. Reuse the BOARD workers slot (`SLOT_SWARM_WORKERS`). If the
     AGENT view does not currently get that slot read, make the AGENT view request
     `TIER_SWARM_BOARD` at its existing TTL rather than adding a new request.
   - The comparison is **equality only**. Build hashes have no order, so "differs from the fleet
     majority" is the whole claim.
3. **Highlight: yellow line plus a trailing `↑`**, keeping the existing text. For example:
   `claude 2.1.278 (Cl… ↑` and `daemon 0.1.0+47df9c68 ↑`, both in yellow.
   - The `↑` and its space come out of the line's own fit budget (`_fit(..., reserved=…)`), so
     the card does not widen and **no pin moves**.
   - An up-to-date line, an unchecked line and a line whose check failed render exactly as today.

## 1b. Owner decisions — AGENT hero (fixed)

The AGENT hero (`widgets/surf/swarm_agent_hero.py`) is currently SEAT · ACCEPTED · ACCEPT RATE ·
REVIEWED · RANK · STATUS. It becomes SEAT · **WORK** · **ACCEPTED** · REVIEWED · **RANK** · STATUS.
SEAT, REVIEWED and STATUS stay unchanged.

1. **Box 2, title `WORK`**, three lines:
   - Line 1: today's RANK line 2 (`3,063 turns`).
   - Line 2: today's RANK line 3 (`11.9 h`).
   - Line 3: the seat's **lifetime output tokens**, for example `1.7M tokens`. This is the owner's
     choice: output only, matching RECORD's `tok` column, and not input or cached input. The
     source is `/contributors` `outputTokens`, which `data/surf_swarm.py` already parses per
     contributor (`output_tokens`) but does not yet carry into the seat's `swarm_seat_contrib`
     fold (~line 1440). Add it there.
   - Use the existing count formatter family (`fmt_compact` style) so the line fits the box at
     every AGENT tier.
   - Missing or unparseable output tokens show `-- tokens` (dim), like turns and hours do today.
   - The box follows `contrib_body`'s availability (`not listed` / `unavailable`), because all
     three lines come from `/contributors`.
2. **Box 3, title `ACCEPTED`**, the old ACCEPTED plus ACCEPT RATE:
   - Line 1 as today: `242 of 280`, green accepted count.
   - Line 2: the accept rate, `86.4 %` in bold. Drop the `of attempts` wording; the title and
     line 1 make it clear. A zero-attempt seat keeps `no attempts` and a missing rate keeps
     `unavailable`, as `_win_rate_body` does today.
   - Line 3 stays empty. **The `as of HH:MM` line leaves the hero entirely** (owner). The seat's
     freshness marker still shows in RECORD's title. Say so in the docs, because the as-of rule
     in CLAUDE.md now rests on RECORD for the seat read.
   - Availability follows `_stat_body` (the seats state), as today.
3. **Box 5, `RANK`**:
   - Line 1 is only the rank: `#8 of 306` (or `unranked`).
   - Line 2 is the **change since the rank last moved**: `▲2` in green when the rank number fell
     (moved up), `▼1` in red when it rose. It stays until the next move. Nothing is shown until a
     first move has been observed for that seat, and nothing after a restart unless it was
     persisted.
   - Line 3 is empty.
   - Mechanism, kept cheap:
     - Persist a small per-seat slot `{token: {"rank": int, "prev": int | None}}` in the surf
       cache, next to the other swarm slots, validated per point on load.
     - Whenever a `/contributors` fold gives the selected seat a rank that differs from the stored
       `rank`, set `prev = old rank` and `rank = new`.
     - The delta is `prev - rank`.
     - A missing rank (`unranked` / `unavailable` / `not listed`) never updates the slot and shows
       no delta.
   - Add a payload key (for example `swarm_seat_rank_delta`, an `int` or `None`) to the models
     key tuple and to the hero's signature.
4. Box ids / contract keys: keep the stable ids where the meaning survives (`accepted`, `rank`).
   Give WORK its own id. Retire `win_rate`'s box, because ACCEPTED now renders the rate. Update
   `SWARM_WIDGET_SIGNATURES`, `BOX_IDS`, the stylesheet selectors and the agreement tests
   together. **No pin may move.** Check with `tests/screens/test_surf_swarm_layout.py -k "agent"`,
   and stop and report if one would.

## 2. Honesty rules (CLAUDE.md)

- A failed or absent read is `None`, never "up to date" and never "outdated". It must not
  produce a highlight.
- The card cannot print the basis, so put it in the RUNTIME box's **tooltip** (Textual `tooltip`)
  in plain text. Examples:
  - `latest claude-code 2.1.281 (npm, as of HH:MM)`
  - `fleet daemon 0.1.0+cff23c39 on 242/298 workers`
  - `update check unavailable` when the npm read failed
  - `runtime not checked` for an unknown runtime id
  - `no fleet majority` on a tie or an empty fleet

  Every third-party string reaches the tooltip as a `Text` or escaped plain text, never as markup.
- Version strings are third-party input. Parse them with a strict pure parser (§3). Anything
  unparseable compares as unknown, so no highlight.

## 3. Work packages

### WP0 — contract and pure comparison

- `analytics/surf_swarm_signals.py` (pure, no I/O, no clock) gets:
  - `runtime_semver(runtime_id, version_text) -> tuple | None`. It accepts the served shapes
    `"2.1.278 (Claude Code)"` (claude) and `"codex-cli 0.155.1"` / `"codex-cli 0.155.0-alpha.9.2"`
    (codex), and the plain npm form `"2.1.281"`. It returns `(major, minor, patch, prerelease)`,
    with prerelease ordered below the release. It returns `None` for anything else.
  - `runtime_outdated(runtime_id, seat_version, latest_version) -> bool | None`. It returns `True`
    only when both sides parse and seat < latest. A seat that is newer than or equal to latest
    returns `False`. Anything unparseable or missing returns `None`.
  - `fleet_majority(versions: list) -> tuple[str, int, int] | None`. It returns
    `(version, count, total)` for a unique plurality of valid strings, and `None` otherwise.
  - `daemon_differs(seat_daemon, majority) -> bool | None`
- `data/surf_models.py`: add the new payload keys (for example `swarm_runtime_latest`, a dict
  runtime id → version or `None`, plus its `as_of`, and `swarm_fleet_daemon`, the majority tuple
  or `None`). Add them to the key tuple and `SWARM_WIDGET_SIGNATURES` for the agent cards widget.
  Update the agreement tests that bind them (`tests/data/test_surf_swarm_models.py`,
  `tests/widgets/test_surf_widget_contract.py`).
- Tests: table-driven parser and comparator tests, including hostile strings (`None`, ints,
  `"2.1"`, `"v2.1.281"`, markup `[/x]`, huge numbers, whitespace). Mutation proof: flip the
  comparison and name the test that turns red.

### WP1 — keyless npm client

- Add a small client following `rules/data.md` (for example `data/npm_registry_client.py`, or a
  method on an existing surf client if that is cleaner — your call, and justify it in the report).
  - Mix in `rpc_common.OwnedHttpClient`. One host: `https://registry.npmjs.org`.
  - Read only `…/<package>/latest` and only the `version` field. The package names come from the
    hand-typed table in §1.1, never from payload input.
  - Keep a short timeout. No retry storm: a failure is `None` for that cycle.
- Validate the response: `version` must be a string that is at most 64 characters long and
  matches a strict semver-ish regex. Anything else is `None`.
- Tests: committed fixtures under `tests/fixtures/surf/npm/`. Capture the two live `latest`
  responses once, trimmed to the fields you read plus `name`. Also cover a 404, a 500, a
  non-JSON body and a hostile `version`. Inject a transport that raises on use. No test touches
  the network.

### WP2 — manager wiring and cache

- Add a new cache tier (for example `TIER_SWARM_RUNTIME_LATEST`) with a **1 h** TTL, persisted
  like the other swarm slots and validated per point on load (a hand-edited cache is third-party
  input). It runs only when the AGENT view is active and a seat is selected. It reads only the
  runtime ids that the selected seat actually reports, and at most 2 packages per cycle.
- When the seat changes, do not re-read npm inside the TTL. The results are per package, not per
  seat.
- The fleet majority is computed from the workers slot in the same fold that builds
  `swarm_fleet`. Do not add a network read.
- Payload: `swarm_runtime_latest` / `swarm_fleet_daemon` as frozen in WP0, with `None` for could
  not look.
- Tests (`tests/data/test_surf_manager_*.py`, pick or add one):
  - one npm read per package per TTL;
  - a failure gives `None` and no false "up to date";
  - an unknown runtime id is never requested;
  - a restart reads the persisted slot;
  - the majority tie gives `None`.

  Mutation proof: remove the TTL check and name the test that turns red.

### WP3 — RUNTIME card

- `widgets/surf/swarm_agent_cards.py` `_runtime_body`:
  - When `runtime_outdated(...) is True`, the runtime line is yellow and ends in ` ↑`. The fit
    reserves 2 cells so the `↑` is never clipped.
  - When `daemon_differs(...) is True`, the daemon line (`daemon …`) is yellow and ends in ` ↑`.
  - Every other case renders byte-identically to today. Assert this against composited output
    (`render_strips()`), not the content string.
- Tooltip on the RUNTIME box, as in §2.
- Pins: `SURF_AGENT_FULL_LAYOUT_COLUMNS` / `…_ROWS` must not move. Run the AGENT layout tests
  (`tests/screens/test_surf_swarm_layout.py -k "agent"`). If a pin would move, stop and report
  instead.
- Tests: composited colour and `↑` tests at the AGENT pin width and at the narrowest AGENT tier.
  Cover:
  - outdated claude;
  - outdated codex (prerelease seat vs release latest);
  - seat newer than latest (no highlight);
  - an unknown runtime;
  - a failed npm read;
  - a daemon equal to the majority, a daemon that differs, and a tie.

  Mutation proof: drop the reserved cells and show which test catches the clipped `↑`.

### WP5 — hero boxes WORK / ACCEPTED / RANK (§1b)

- Data: carry `output_tokens` into `swarm_seat_contrib`. Add the rank slot and the
  `swarm_seat_rank_delta` key (cache, per-point validation, manager fold).
- Tests in `tests/data/test_surf_swarm_board.py` (the contrib fold) and `tests/data/test_surf_manager_swarm.py` (the slot):
  - first observation gives no delta;
  - rank 8 → 6 gives `+2` (▲2), and 6 → 9 gives `-3` (▼3);
  - the delta stays through unchanged reads;
  - an `unranked` read leaves the slot untouched;
  - a seat change reads that seat's own slot;
  - a hand-edited slot (`"rank": "x"`, a negative, a bool) is dropped on load.

  Mutation proof: swap `prev - rank` to `rank - prev` and name the red test.

### WP6 — hero rendering

- `swarm_agent_hero.py`: titles, bodies and ids as in §1b; `rank_body` in `_swarm_seat.py`
  splits into a rank body and a work body (one definition each, no copy).
- Tests (`tests/widgets/test_surf_swarm_agent_hero.py`, composited):
  - the six titles in order;
  - WORK's three lines;
  - ACCEPTED's two lines and **no `as of`**;
  - RANK's `▲2` green and `▼3` red, and nothing without a delta;
  - `not listed` / `unavailable` / `no attempts` states;
  - a hostile or huge token count;
  - every AGENT tier's width with no clipped line.

  Update the existing assertions that expected `ACCEPT RATE`, `of attempts` and the hero
  `as of` (lines ~155, 184, 190, 212, 288, 416, 441). The owner changed them; this is not a
  weakening. Say so in the commit.
- `tests/screens/test_surf_swarm_screen.py` and the AGENT layout tests must stay green with
  unmoved pins. The owner's #420 capture is a composited case: `3,063 turns`, `11.9 h`, the
  tokens line, `242 of 280` / `86.4 %`, `#8 of 306`.

### WP4 — docs (runs last, covers both parts)

- README / rules: the hero's new boxes and lines, the output-token source, the rank-delta rule
  (since the last move, persisted per seat), and where the seat's `as of` now lives (RECORD
  title).

- README: in the AGENT/RUNTIME section, say what `↑` means, what it is compared with (npm
  `latest`; the fleet-majority daemon, equality only) and that the tooltip shows the basis.
- `.claude/rules/surf.md`: the source, the TTL, the "equality only" daemon rule and the honesty
  rules. `.claude/rules/data.md`: add `registry.npmjs.org` to the keyless source list.
- `docs/decisions.md`: dated entry with the owner decisions from §1.
- `docs/surf_runtime_updates_followups.md`: anything deferred.

## 4. Tests to run at the end (not the full suite)

```
tests/analytics/test_surf_swarm_signals.py tests/widgets/test_surf_swarm_agent_cards.py
tests/widgets/test_surf_swarm_agent_hero.py tests/data/test_surf_swarm_board.py tests/data/test_surf_manager_swarm.py tests/data/test_surf_models.py
tests/widgets/test_surf_widget_contract.py tests/data/test_surf_swarm_models.py
<the npm client test file> <the manager test file(s) you touched>
tests/screens/test_surf_swarm_screen.py
tests/screens/test_surf_swarm_layout.py -k "agent"
tests/screens/test_address_icons_everywhere.py -k surf
-m guard
```

The controller runs the full suite once, before the merge.
