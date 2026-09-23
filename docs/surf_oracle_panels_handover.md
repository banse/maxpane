# CODEX — START HERE (added 2026-09-23 for the implementation run)

Implement `docs/surf_oracle_panels_plan.md` (the plan). The rest of this file below the line is the
owner-approved spec it cites (§3, §5B, §6). Before any code:

1. **Fetch the latest release.** This clone is on `feature/surf-swarm-polish` @ `9305a3e`, which is
   older than v0.9.1. The plan's file and line references are against `main` @ `71289c9` (tag `v0.9.1`).
   ```bash
   git fetch origin --tags
   git rev-parse origin/main        # must print 71289c9f9b022b31d9e41455a2091f0158d73792
   ```
   If it prints anything else, stop and report. Do not rebase or merge the polish branch into it.
2. **Keep the two docs.** They are untracked (`docs/surf_oracle_panels_plan.md` and this file), so they
   survive the checkout. Leave `.codex/`, `.venv311/` and `tests/fixtures/surf/pool4/oracle_25955365.json`
   alone. They are not part of this work.
3. **Start a dedicated branch from that commit.**
   ```bash
   git switch -c feature/surf-oracle-panels origin/main
   git log --oneline -1             # 71289c9 release: v0.9.1
   ```
4. **Re-install and check the version.** The editable install writes the version once.
   ```bash
   .venv311/bin/pip install -e .
   .venv311/bin/python -m maxpane_dashboard --version   # 0.9.1
   ```
   Use this interpreter for every test run (`.venv311/bin/python -m pytest …`), because the system `python3`
   skips tests that need `httpx` and reports green. CLAUDE.md names `.venv`; here it is `.venv311`.
5. **Commit the two docs as the branch's first commit** (`docs(surf): oracle panels handover + plan`,
   pathspec only: `git commit -- docs/surf_oracle_panels_plan.md docs/surf_oracle_panels_handover.md`).
6. **Run WP0 → WP5 straight through without pausing between packages.** Make one commit per WP and run each WP's
   named tests plus `-m guard` before its commit. The owner reviews the branch commit by commit afterwards. The owner has
   already decided D1–D4 (§0.1 of the plan), so do not re-ask.
   Stop early **only** for one of the plan's own stop conditions: `origin/main` is not `71289c9`, a plan defect
   (see the plan header's **Precedence** line), BOARD's layout test going red in WP4, or a named test you cannot make green.
   Report and wait in those cases. Do not work around them.
7. **One report at the end** (or at an early stop): the commits (hash + subject), the tests run for each WP and their
   results, which test reddened for each mutation proof, and every deviation from the plan with its reason.
   Never push, merge, tag or bump the version. The full suite is the controller's job, not yours.

---

# HANDOVER — surf AGENT: oracle panel outcomes from `/oracle/requests`

**Status:** 5B chosen by the owner 2026-09-23 (column spec in §5B); 5A still open. Written by Claude (aidude session) on 2026-09-23
~20:30 UTC from a live read of `api.imd.fun`, after the owner's screenshot of maxpane v0.9.1 SURFBOARD
· AGENT #420. Short on purpose: facts, the join, two candidate displays, and the traps. Spec and plan
are for whoever picks it up, following this repo's `CLAUDE.md` tiers.
**Shared record:** `/Library/Vibes/aidude/docs/imd-api-changelog.md` §3, entry "2026-09-23 (evening)".

---

## 1. Why

The AGENT body answers "was my work accepted?" (`/seats/<id>`) but not two questions the owner is now
asking:

1. **Did the seat agree with the panel, and what did the panel say when it didn't?** An oracle answer
   is judged against the quorum of every seat that answered it. `/seats` gives only a status.
2. **Is "pending" waiting, or closed?** It is mostly closed. `/seats` keeps a submission `pending` for
   good when its panel ends `disagreed` (no quorum). Measured for #420 at 20:25 UTC: **26 pending =
   17 on `disagreed` panels (final) + 3 on `assessing` panels (live) + 6 not found on any panel.**
   The REVIEWED tile's "69 pending" and BOARD's "36 pending" both read as a backlog that mostly is not one.

## 2. The route (new 2026-09-23, keyless, no CORS, like every route)

`GET /oracle/requests` → `{attester, count, requests[]}`, newest first.
- Item: `id status question chainId window{fromBlock,toBlock,toBlockHash} answerType jobId signer
  attestedAt createdAt updatedAt`.
- `status` seen: `attested` · `disagreed` · `assessing` · `blocked`.
- **Paging works here (unlike `/jobs`)**: default 100, `?limit=` up to **500** (larger is capped),
  `?before=<ISO createdAt>` is the cursor. `?offset` `?page` `?status` are ignored.
- Whole history at 20:25 UTC: **590 requests**, oldest 2026-09-19 03:18 UTC, in two pages
  (`limit=500`, then `before=<oldest of page 1>`).

`GET /oracle/requests/<uuid>` → 27 keys. Malformed id → `400 {"error":"invalid_id"}`. The fields
that matter here:
- `status`, `panelSize`, `quorum`, `toleranceBps` (0 discrete, 1000 = ±10 % on prices)
- `agreement{agreed, answer, figure, quorum, recipe{kind,source}, cluster[], sources[], definitions}`,
  where `cluster` is **the submission hashes that agreed**.
- `members[]{ok, answer{answer, figure, notes, recipe, definitions, window, …}, reason, wallet,
  submissionHash}`. This is **every panel member's full answer and notes**. Panels run from 0 to 112
  members.
- `attestation{…}` + `signature` + `signer` (one attester key, `0x5598aa91…2982`).

## 3. The join

```
/seats/<token>.work[].submissionHash  ==  /oracle/requests/<id>.members[].submissionHash
in cluster  <=>  submissionHash ∈ agreement.cluster
```

Match on the submission hash, never on `wallet` (a holder can run several seats) and never on
`jobId` alone (the panel job is shared by every member).

## 4. What it shows for #420 (full history, 2026-09-23 20:25 UTC)

| | count |
|---|---|
| oracle work on `/seats/420` | 243 |
| matched to a panel | 219 |
| in the agreeing cluster | **205** (196 attested + 9 on disagreed panels) |
| outside the cluster | **11** (3 attested, 8 disagreed) |
| panel still `assessing` | 3 |
| not on any panel | 24 (12 accepted, 6 pending, 6 failed; failed runs never reach a panel) |

The misses are the useful part. The latest three were NFT floors where #420 answered `0` with a note
saying it could not read OpenSea (401, no key) while 32–34 other seats found the floor, e.g.
Moonbirds: seat `0`, panel `457162630000000000`. The RECORD's "I could not find the Creepz floor
price" rows are exactly these.

## 5. Two candidate displays (the owner picks)

- **A. One ORACLE-tile line.** Add `panel 205 of 216 agreed`, and split pending into
  `open 3 · closed 17`. This is the smallest change.
- **B. A PANEL column in RECORD.** Oracle rows get `✓ agreed`, `✗ panel <figure>`, `… assessing` or
  `– no quorum`. It is the one place where "why was this not accepted" becomes visible per row.

These are not exclusive. A is a tier-1 change here; B touches the RECORD contract.

### 5B in detail — owner's choices, 2026-09-23

The owner chose B with these rules: **drop `role`, keep `took`, add `panel` and `tok`, and shorten
model names.** RECORD is `widgets/surf/swarm_seat_record.py` (`_SPECS`, `build_cells`,
`_usage_cell`).

**New column order:** `when · job · node · state · model · took · panel · tok · answer`.
- `role` is dropped entirely, not just from the tiers. It is `implement` on 217 of #420's 218 rows.
- The widths roughly balance: `role` 9 + model 15→9 frees 15 cells; `panel` 8 + `tok` 6 take 14,
  plus one more column of padding.
- Re-measure `FULL_WIDTH`, `COMPACT_WIDTH` and `TIGHT_WIDTH` with `table_cols`, as the screen sweep does.
- Tiers: `tight` keeps `panel` and drops `tok`, together with `answer`, `model` and `took`.

**`panel` (8 cells):** one state per oracle row, from the §3 join.

| cell | when | style |
|---|---|---|
| `✓ 35/36` | the seat's hash ∈ `agreement.cluster` and `status == attested`; shows `agreed/len(members)` | green |
| `✗ 35/36` | not in the cluster and `attested`. **This is the miss that counts** | red |
| `✓ no-q` | in `cluster` and `status == disagreed` (the larger group, but no quorum) | dim green |
| `✗ no-q` | not in the cluster and `disagreed` | dim red |
| `… 3/112` | `status == assessing`; shows `len(members)/panelSize` if present, else `len(members)` | yellow |
| `blocked` | `status == blocked` | dim |
| `–` | not an oracle row, or the seat's hash is on no panel. Failed runs never reach one | dim |

Any row showing `no-q` is **closed**, whatever `/seats` `status` says. That is the per-row answer
to "is pending waiting?".

**Answer cell on red rows:** prefix it with the panel's figure, e.g. `panel 457162630000000000 ·
I could not get the Moonbirds floor…`. Show it raw. `answerType: uint256` carries no unit: floors are
wei, `2` meant VOID, and `50` was a post count. For `bool`, show `panel YES` / `panel NO`.

**`tok` (6 cells):** `usage.outputTokens`, compact (`1.5k`, `22k`). Nothing new to fetch, because
`usage` is already on the submission RECORD reads for `model`.
- Output tokens, because they vary with the task. `cachedInputTokens` is about 170–200k on every
  oracle run (prompt and skills re-read), so it would look the same on every row.
- `–` when `usage` is null.
- Sample, 6 of #420's latest: 5–6 turns, 1.5–1.9k out, 170–200k cached, 20–27 s.

**Model short names.** No mapping exists anywhere: MaxPane, aidude and The Lineup all print the raw
id, which is why `model` needs 15 cells. Use **a rule, not a lookup table**, so a new model shortens
without a code change:

```
claude-<family>-<major>[-<minor>]   ->  <family> <major>[.<minor>]     claude-opus-5-5  -> opus 5.5
gpt-<version>-<name>                ->  <name> <version>               gpt-5.6-luna     -> luna 5.6
anything else                       ->  the raw id, clipped with …     gpt-5.5          -> gpt-5.5
```

Ids observed on 2026-09-23 (`/workers` `premiumModel`, submission `usage.model`, the Codex model list),
with the result:

| raw | short | | raw | short |
|---|---|---|---|---|
| `claude-sonnet-5` | `sonnet 5` | | `gpt-6-astra` | `astra 6` |
| `claude-opus-5` | `opus 5` | | `gpt-6-sol` | `sol 6` |
| `claude-opus-5-5` | `opus 5.5` | | `gpt-6-luna` | `luna 6` |
| `claude-fable-5-1` | `fable 5.1` | | `gpt-5.6-luna` / `-terra` / `-sol` | `luna 5.6` / `terra 5.6` / `sol 5.6` |

- The longest result is 9 cells (`fable 5.1`, `terra 5.6`), so `model` goes from 15 to 9.
- The raw id is still third-party text. Run it through `flatten` / `strip_tags` before matching, and
  only shorten ids that match the patterns exactly.
- The same function fits `swarm_fleet._model_lines`. There, the effort stays appended:
  `astra 6 xhigh`.

## 6. Traps

- **Cost.** Detail is roughly 50 KB per request (the full history is 29 MB, and 590 fetches take about 20 s
  at 8 in parallel). Fetch the list every poll, but fetch a detail only for requests that contain one of
  the seat's hashes. Cache `attested`, `disagreed` and `blocked` details for good, since they are final,
  and refetch only `assessing` ones.
- **But the list does not name members.** You cannot tell from the list which requests the seat is on.
  Walk from the seat instead: `/seats` `work[].jobId` equals the request's `jobId` (verified 219 of 219 for
  #420), so map `jobId → request id` from the list, fetch only the seat's requests, and confirm on
  `submissionHash`.
- **`members[].answer.notes` and `question` are third-party text.** Escape them, as for every other
  string from this API.
- **`figure` is a decimal string, and wei values exceed 2^53.** Do not parse it as a float. Display
  the string, or format it with integer arithmetic.
- **`toleranceBps` decides agreement on prices.** A seat can differ from `agreement.figure` and still
  be in the cluster (Pudgy Penguins: 3497353… vs 3665300… at 1000 bps). Show "in cluster", not "equal".
- **The route is one day old.** Degrade to UNAVAILABLE, never to zero, if it 404s.
