# WP1 — Time-critical captures (the standalone capture rig)

**Goal:** Build a one-shot, keyless, dependency-light capture script and use it to record the
three contract states that are **irreplaceable once missed**, plus one cheap capture that
closes the sqrt-curve evidence gap. Every committed capture today is from grace hour 1; the
game's whole second half has no fixtures at all, and two of the three windows are on
**2026-08-17**.

**Dependencies:** none. This WP is deliberately decoupled from the build: it imports nothing
from `maxpane_dashboard/`, needs no frozen interface, and can be run by someone who has read
only this file. **It starts in wave 1 and its timed runs continue through every later wave.**

**Owner note.** This WP owns and creates:

- `scripts/capture_curator_state.py`
- `tests/fixtures/curator/captures/live/` (the whole directory, including its `README.md`)

It touches **nothing else**. In particular it does not touch
`tests/fixtures/curator/captures/*.json` or that directory's `README.md` (WP0's), and it does
not edit any test that consumes a capture — re-pointing tests at real payloads is WP1.7, and
it edits only the tests whose owning WP has already landed, by agreement, with the owning WP
notified. If an owning WP has not landed yet, **leave the bundle committed and record it in
the ledger**; the owning WP picks it up as it writes the test.

WP0's capture guard is written against a **named required set**, never a file count, precisely
so a bundle landing mid-build cannot turn another agent's suite red. Verify that is still true
before your first commit (`REQUIRED_CAPTURES` in `tests/data/test_curator_captures.py`); if
someone has changed it to a count, **report it, do not fix it**, and hold the commit.

### Ground rules

- **Keyless, read-only, no signing.** The script issues `eth_call`, `eth_getLogs`,
  `eth_getBalance`, `eth_blockNumber` and `eth_getBlockByNumber` and one Blockscout GET. It
  never constructs calldata for a state change and never asks for a key.
- **Set a real `User-Agent`.** publicnode returned HTTP 403 to python-urllib's default UA and
  accepted the identical batch from curl. This is the single most likely reason a capture run
  fails at 20:58 UTC, so it is the first thing the script's self-test checks.
- **The script depends only on the stdlib** (`urllib.request`, `json`, `argparse`, `time`).
  Not `httpx` — the point is that it runs from any checkout, in any venv, at short notice.
- **Never overwrite a bundle.** Filenames carry the UTC instant. A second run in the same
  second appends a counter.
- **Record what you saw, not what you expected.** If `isSettled()` is still false at 21:30,
  commit the bundle anyway and say so in the ledger. A negative observation at a named instant
  is evidence.
- Commit after each capture, `test(curator): capture <state> at <UTC instant>`.

---

### Task WP1.1: The capture script

**Files:**
- Create: `scripts/capture_curator_state.py`

**Interfaces:**
- Produces: `python3 scripts/capture_curator_state.py [--label NAME] [--logs-from BLOCK]`
  writes `tests/fixtures/curator/captures/live/<UTCSTAMP>_<label>.json` and appends one row to
  `tests/fixtures/curator/captures/live/MANIFEST.md`.
- Consumes: nothing in `maxpane_dashboard/`. It is imported by nothing (WP0.1's scan asserts
  the package never imports `scripts/`).

**Bundle shape** — one JSON object, so a single file is a complete, self-describing observation:

```json
{
  "label": "post-grace",
  "captured_at": 1787000000,
  "captured_at_utc": "2026-08-17T20:53:20Z",
  "chain_head": 25776543,
  "state": {"<selector>": {"name": "isSettled()", "result": "0x…"}, "...": "..."},
  "balance": "0x0",
  "logs": [ {"address": "...", "topics": ["..."], "data": "0x…",
             "blockNumber": "0x…", "transactionHash": "0x…", "logIndex": "0x…"} ],
  "logs_from_block": "0x189360e",
  "block_timestamps": {"0x189378e": "0x6a8215…"},
  "blockscout_page_0": { "...": "..." },
  "endpoints": {"state": "https://ethereum-rpc.publicnode.com",
                "logs": "https://gateway.tenderly.co/public/mainnet"},
  "errors": []
}
```

**Steps:**

- [ ] Write the script. Structure:
      1. Constants: contract `0xcB0b0531e86A9aC36fa865ca8e3DbcCF047fDA91`, deploy block
         `25769870`, state URL `https://ethereum-rpc.publicnode.com`, logs URL
         `https://gateway.tenderly.co/public/mainnet`, logs fallback
         `https://eth.drpc.org`, Blockscout `https://eth.blockscout.com/api/v2`.
      2. **The 21 parameterless selectors, copied verbatim out of
         `tests/fixtures/curator/captures/batch.json`** — not retyped, not recomputed. This
         script must work even if `curator_addresses.py` does not exist yet, and the captured
         batch is a known-good list. Read them out of the file at run time if it is present;
         fall back to an inlined copy if it is not.
      3. `_post(url, payload)` with `User-Agent: maxpane-capture/1.0 (+https://pypi.org/project/maxpane)`,
         `Content-Type: application/json`, a 20 s timeout, and 2 retries with 1 s/3 s backoff.
      4. One batched `eth_call` array for the 21 views → `state`.
      5. `eth_getBalance(contract, "latest")` → `balance`.
      6. `eth_blockNumber` → `chain_head`.
      7. `eth_getLogs` from `--logs-from` (default: the deploy block) to `latest`, on the logs
         URL, falling back to drpc **on a routing-message body** (classify on message text,
         not code — the whole reason the fallback exists). On a range error, halve the window;
         **never follow a provider's "suggested range"**.
      8. `eth_getBlockByNumber` for the distinct blocks of the newest 40 logs → the
         `block_timestamps` map (this is the data WP2.8 needs and no existing capture has).
      9. Blockscout `/addresses/<contract>/logs` page 0 as an independent cross-check.
      10. Every failure appended to `errors` with its URL and message; the script **never
          aborts on a partial failure** — a bundle with three of four sections is worth
          infinitely more than no bundle at 20:58 UTC.
- [ ] Add `--self-test`: performs only steps 3 and 6 (one `eth_blockNumber`) and prints
      `OK <head>` or the HTTP status. This is what you run at 20:50 to prove the UA is
      accepted before the window opens.
- [ ] Add `--dry-run`: does everything but write, printing a summary
      (`21/21 views · 377 logs · balance 0 · isSettled=false`).
- [ ] Create `tests/fixtures/curator/captures/live/README.md`: what a bundle is, what each
      label means (`grace-late`, `hour-boundary`, `post-grace`, `judged-deficit`,
      `settlement`, `curve-probe`), and the **ledger table** WP1.7 maintains.
- [ ] Verify the script is not importable by the package:
      `.venv/bin/python -m pytest tests/data/test_curator_captures.py -k scripts -v`
      (WP0.1's scan).
- [ ] Commit:
      `git add scripts/capture_curator_state.py tests/fixtures/curator/captures/live/README.md && git commit -m "feat(curator): add the one-shot keyless capture script for time-critical states"`

**Done when:** `python3 scripts/capture_curator_state.py --self-test` prints `OK <block>` from
a clean checkout with no venv.

---

### Task WP1.2: Prove the rig, and bank a "grace, late" bundle

**Files:**
- Create: one bundle under `tests/fixtures/curator/captures/live/`

**Why now:** the rig must be proven **long before** it is needed. A script that 403s at
20:58:47 UTC is a script that lost capture C forever.

**Steps:**

- [ ] `python3 scripts/capture_curator_state.py --self-test` → `OK <head>`.
- [ ] `python3 scripts/capture_curator_state.py --dry-run` → confirm 21/21 views answered and
      the log sweep returned in one call.
- [ ] Run for real with `--label grace-late`. This is a genuinely useful state on its own: it
      is the **decayed end of the early-bird ramp**, where `earlyMultiplierBps()` is far below
      the captured 19491 but still above 10000, and where the deposit history is several times
      longer than the 226 rows the research captured.
- [ ] Record in the ledger: instant, label, `currentHour`, `earlyBps`, `isSettled`,
      `contributors`, `deposits`, log count.
- [ ] Sanity-check the bundle by hand: `earlyBps` must be strictly between 10000 and the
      captured 19491, and `currentHour` strictly greater than 1. If either is not, the script
      read the wrong contract — stop and report.
- [ ] Commit: `test(curator): capture the late-grace state at <UTC instant>`

**Done when:** a real bundle is on disk and the rig is proven end to end.

---

### Task WP1.3: Capture A — the hour boundary

**The state:** `currentHourTotal() == 0` **while** `lastActiveHour()` still names the previous
hour and its total. This is the hazard the whole sparkline rule exists for (H2), and the
21:04–21:14 captures cannot show it: at 21:12 the current hour *was* the last active hour, so
the two agreed.

**What already exists — read before you start.**
`tests/fixtures/curator/captures/hour_boundary_h1_h2.json` holds 16 batch samples every ~20 s
across the hour 1 → 2 crossing (2026-08-16 21:56:15 → 22:01:21 UTC). It captures the *volume
drop* in its real form — `currentHourTotal()` 9987.26 → 51.48 ETH while `stats()` climbs — but
**not** the stale pair: a deposit landed 11 s into hour 2, so `lastActiveHour()` had already
rolled. So this task is narrower than it looks: hunt a **quiet** crossing, and diff your bundle
against that file rather than re-capturing what it already holds.

**Window:** any hour crossing, i.e. `launchTime + N*3600` = **`HH:58:47` UTC**. Cheapest of
the three and **retryable every hour until settlement** — so if you miss one, take the next.

**Steps:**

- [ ] Compute the next boundary: `1786910327 + N*3600`. In wall-clock terms the crossings are
      at **58 minutes 47 seconds past each hour, UTC**.
- [ ] From `HH:58:40`, run
      `python3 scripts/capture_curator_state.py --label hour-boundary` **repeatedly** (every
      ~10 s) through `HH:59:30`, until a bundle satisfies **all three**:
      - `currentHourTotal() == 0x0`
      - `lastActiveHour()` word 0 == `currentHour() - 1` (or lower)
      - `lastActiveHour()` word 1 != 0
      Keep only the first bundle that satisfies them plus the one immediately before it (the
      *pre*-boundary state makes the pair a before/after fixture, which is what the fold test
      actually wants).
- [ ] Note the risk honestly in the ledger: if a deposit lands in the first seconds of the new
      hour, `currentHourTotal()` is already nonzero and the boundary is invisible. During a
      busy hour this can take several attempts; during a quiet one it is trivial. **A quiet
      hour is the better hunting ground** — and after grace ends, quiet hours are exactly what
      the game is about.
- [ ] Commit both bundles: `test(curator): capture the hour-boundary zeroing at <UTC instant>`
- [ ] Update the ledger and mark the hour-boundary fixture **captured** in the index plan's
      synthetic table (WP1.7 does the doc edit; note it here).

**Done when:** a bundle exists in which `currentHourTotal()` is 0 and `lastActiveHour()` is
not — the exact pair a naive state-poll sparkline would render as a crash.

---

### Task WP1.4: Capture B — post-grace, judged hour in progress

**The state:** `earlyMultiplierBps() == 10000` exactly (flat, grace over) and
`currentHour() >= 24`, ideally with `ethNeededThisHour() > 0` (a judged hour with a live
deficit — the state that lights HOUR AT RISK).

**Window:** grace ends **2026-08-17 19:58:47 UTC**. The flat multiplier persists forever after
that, so the *multiplier* half is easy. The **deficit** half is the perishable part: an hour
with `ethNeededThisHour() > 0` and fewer than 900 seconds left is the red state, and once the
game settles no such hour can ever occur again.

**Steps:**

- [ ] At **19:58:50 UTC or later**, run
      `python3 scripts/capture_curator_state.py --label post-grace`. Confirm
      `earlyMultiplierBps()` decodes to exactly `0x2710` (10000). If it is still above,
      the clock is off or `launchTime` is not what we think — stop and report.
- [ ] Then poll for the deficit state. From **20:00 UTC**, run
      `--label judged-deficit` every ~5 minutes until a bundle has
      `ethNeededThisHour() > 0` **and** `currentHour() >= 24`. Keep the one with the smallest
      `timeLeftInHour()` you can get — under 900 seconds is the red-state fixture and is worth
      chasing; over 900 is the yellow-state fixture and is worth keeping regardless.
- [ ] If the hour fills before you catch a deficit, that is itself a capture: keep a bundle
      with `ethNeededThisHour() == 0` **and** `currentHour() >= 24`, which is the "judged and
      safe" state, and say in the ledger that the deficit was not observed in that hour.
- [ ] Also capture a `HourSaved` moment if one occurs: after any bundle where
      `ethNeededThisHour()` went from > 0 to 0, re-run with `--logs-from <recent block>` to
      pull the log window containing the `HourSaved` row. **This event may never fire** — if
      the first judged hour simply fills without ever dropping below threshold, or if the game
      dies, it does not exist. Do not block on it; record its absence.
- [ ] Commit each: `test(curator): capture the post-grace flat multiplier at <UTC instant>`,
      `test(curator): capture a judged hour with a live deficit at <UTC instant>`
- [ ] Ledger: for each bundle record `currentHour`, `earlyBps`, `ethNeededThisHour`,
      `timeLeftInHour`, `isSettled`.

**Done when:** at least one bundle has `earlyBps == 10000` and `currentHour >= 24`, and the
ledger states whether a deficit and a `HourSaved` were observed.

---

### Task WP1.5: Capture C — the settlement transition

**The state:** `isSettled() == true`. Plus, if anyone calls the permissionless `settle()`, the
`Settled(hour, timestamp, totalContributors, totalVolume)` log.

**Window:** earliest **2026-08-17 20:58:47 UTC** (the completion of hour 24, the first judged
hour). It can be any later hour boundary instead — the game dies the first time a completed
judged hour takes in less than 5 ETH. **The transition is one-shot and unrepeatable forever.**

**What makes this subtle:** settlement is *derived*, so `isSettled()` flips at the instant the
short hour completes, with **no transaction and no log**. If nobody ever calls `settle()`,
there is no `Settled` event at all and the contract is dead in silence. That is exactly the
hazard the dashboard's latch exists for (H1) — and it means the *view* observation is the
capture that matters, not the log.

**Steps:**

- [ ] From **20:57 UTC on 2026-08-17**, run
      `python3 scripts/capture_curator_state.py --label settlement` every ~60 s across the
      boundary, and keep:
      - the **last** bundle with `isSettled() == 0x0` (the alive state, one poll before death), and
      - the **first** bundle with `isSettled() == 0x1`.
      That pair is the transition, and both halves are needed: the manager's latch test needs a
      "not settled" reading followed by a "settled" reading followed by an outage.
- [ ] Keep polling every ~30 minutes for the next few hours, with the same label, so that if
      someone calls `settle()` the `Settled` log is captured too. Confirm in the bundle's
      `logs` array that a row with topic0 = the `Settled` topic0 is present, and record its
      four decoded fields in the ledger.
- [ ] If **20:58:47 passes with `isSettled()` still false**, the first judged hour survived.
      Record it in the ledger, and repeat the whole task at each subsequent
      `HH:58:47` boundary until it flips. This is not a failure mode; it is the game.
- [ ] Also record the **final** state once settled: `stats()`, `totalContributors`,
      `totalVolume`, `lastActiveHour()`, and one full-history `eth_getLogs` sweep
      (`--logs-from 25769870`). That sweep is the complete archive and never changes again —
      it is the most valuable single artefact in this WP.
- [ ] Commit: `test(curator): capture the settlement transition at <UTC instant>`
- [ ] Ledger: the alive/dead bundle pair by filename, the settled hour, whether `settle()` was
      ever called, and the final totals.

**Done when:** both halves of the transition are on disk, or the ledger records, hour by hour,
that the game is still alive.

---

### Task WP1.6: The curve probe (closes the sqrt evidence gap)

**Why:** the committed 21-call round holds only **parameterless** views, so
`previewPoints(uint256)` and `pointsOf(address)` were never captured. Without them the sqrt
curve is validated only by transcription (WP3.3) — a genuine differential, but not a witness
from the chain. This capture is cheap, needs no timing, and can be run **today**.

**Steps:**

- [ ] Add `--curve-probe` to the script: one batched `eth_call` array containing
      - `previewPoints(uint256)` for a spread of weights that exercises the floor:
        `0`, `1`, `10**9 - 1`, `10**9`, `10**18` (→ expect exactly 1000 points),
        `4 * 10**18` (→ 2000), `100 * 10**18` (→ 10000), `1000 * 10**18` (→ 31622),
        `2000 * 10**18` (the ceiling, → 44721), and three non-square values
        (`3 * 10**18`, `7 * 10**18 + 1`, `461_100_000_000_000_000_000`);
      - `pointsOf(address)` and `weightOf(address)` for the three leaderboard wallets named in
        the mechanics doc (`0x381fe486…` and the next two) plus one of the nine 60-ETH farm
        wallets.
      The selector for `previewPoints(uint256)` is
      `keccak256("previewPoints(uint256)")[:4]` — compute it in the script from the literal
      string, so the script needs no vendored table.
- [ ] Run with `--label curve-probe`. Verify by hand that `previewPoints(10**18) == 1000` and
      `previewPoints(0) == 0`; if not, the ABI encoding of the argument is wrong (left-pad the
      uint to 32 bytes, no `0x` inside the data field).
- [ ] Commit: `test(curator): capture previewPoints/pointsOf as the sqrt curve's witness`
- [ ] Notify WP3: its curve test can now assert against a real return **in addition to** the
      transcription differential. Do not delete the transcription test — it covers the whole
      input domain and the probe covers twelve points of it.

**Done when:** a bundle holds `previewPoints` returns for the twelve weights and `pointsOf`
for four real wallets.

---

### Task WP1.7: Re-point the synthetic fixtures and close the ledger

**Files:**
- Modify: `tests/fixtures/curator/captures/live/README.md` (the ledger)
- Modify: `docs/curator_implementation_plan.md` (the "synthetic until captured" table)
- Modify (**by agreement with the owning WP only**): the specific tests marked
  `# SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>`

**Steps:**

- [ ] `rg "SYNTHETIC — re-point" tests/` — that is the whole checklist.
- [ ] For each hit whose real payload has landed:
      1. Point the fixture at the live bundle.
      2. **Run the test before changing any expected value.** If it passes unchanged, the
         synthetic was faithful and you have just upgraded the evidence for free. If it fails,
         read *why* before editing the expectation — a synthetic that disagrees with chain is
         a finding, not a chore, and it goes in the ledger.
      3. Delete the `SYNTHETIC` comment and replace it with the bundle filename and its UTC
         instant.
- [ ] For each hit whose payload has **not** landed (and may never — `HourSaved`, `Rescued`,
      the >1000 ETH deposit), leave the comment in place and state in the ledger that it is
      permanent-synthetic with the reason. Do not silently delete a marker to tidy the grep.
- [ ] Update the index plan's synthetic table so its status column matches the ledger exactly.
- [ ] Run the affected suites and the full suite:
      `.venv/bin/python -m pytest -q`
- [ ] Commit: `test(curator): re-point <n> fixtures at real captures and close the ledger`

**Done when:** every `SYNTHETIC — re-point` marker is either resolved against a real bundle or
documented as permanently synthetic with a reason, and the index plan's table says the same.
