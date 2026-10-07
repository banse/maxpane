# Codex fix round 2: SWARM production launches (verification of b206c53, written 2026-10-06)

> **Do not use any superpowers skill.** This brief, `docs/codex_swarm_launches_plan.md` (c9352030),
> `docs/codex_swarm_launches_fix1.md` and `CLAUDE.md` are the whole process.

**Branch:** `feature/swarm-launches`; continue from `b206c53`. **Fix round 1 is verified:** an independent check
confirmed all F1–F16 and gaps a–h, and 28 of 28 of its own mutants were killed. Two examples:
- F1: `match_sites` takes 1.5 ms at 500 launches × 100 sites × 1,000 workflows, against 8.7 s before.
- F2: replaying today's 23 production launches, each live one fires exactly once.

**This round:** one commit for N1–N4, one for N5–N8. Each item gets its test and its named mutant, recorded in the
commit body. Then report for verification. Never merge, push or tag.

## Must fix

**N1 · False `✗ K2` on live #775** (it was there at a5f2fe9 too).
- **The case:** #775 FREE1376 (`univ4_hook`, chain 1, policy v19). Its deploy tx
  `0x9eeabe67…1ad2` goes **from the launch wallet `0xcecc…a551` to `0x12c63b58…a96f`**, a second factory, created by
  the same dev deployer `0x047F606f…` as `0xff03…7120`.
  - In `/launch/policies`, only the `evm_contracts` policy (v27) declares a `factory`.
  - `univ4_hook` (v19), `evm_project` (v18) and `custom_token` (v17, v26) declare none.
- **Cause:** `policy_sets` pools the factories of every kind on the chain, so a hook launch is judged against the
  contracts factory.
- **Fix:**
  - The factory set for K2 is the factories declared by policies of **the launch's own `kind`** on its chain.
  - Where that kind declares none, judge K2 on **sender (wallet set) + receipt status** only, and keep `to` as
    evidence.
  - `custom_token` launches currently go to `0xff03…` and must still pass; with no custom_token factory declared,
    they pass on sender + receipt.
- **Tests:**
  - a #775-shaped launch (`univ4_hook`, foreign `to`, our sender, status `0x1`) → `pass`;
  - an `evm_contracts` launch with a foreign `to` → still `fail`.
- **Mutant:** pool factories across kinds → the #775 test reddens.

**N2 · K3 passes vacuously** (introduced by F4).
- **The case:** when every attested contract is `na`, K3 is `pass`.
  - Live #770 (parked, nothing deployed) shows `K3 · pass` in its popup.
  - #737 with its artifacts renamed reaches **`✓ swarm` with no bytecode verified**.
- **Fix:**
  - K3 is `pass` only if **at least one** attested contract is `pass` or `pass_immutables`, **and** every `token`-
    or `hook`-role artifact maps by name to a matched attested contract. That holds on all 22 live deployed
    launches.
  - All `na` → `unknown`.
  - A role artifact with no matching attested contract → `unknown`, with the evidence saying which one.
- **Tests:**
  - all-`na` → `unknown`;
  - renamed artifacts → `unknown`, not `✓`;
  - #763 (`V2TwapSwap` `na`, the others matched) still gives `✓ swarm`.
- **Mutant:** restore "no unknowns ⇒ pass".

**N3 · A long ticker still hides the verdict in the signals row** (F14 was incomplete).
- **The case:** at the 143 pin the panel is 64 cells:
  - `X`×120 renders `$XXXX… #737…`;
  - `字`×60 renders `$字字… #737…`;
  - even `Q[31mEVIL[/]R` renders `…#737 MAINNET…`.

  In all three, `✓` or `✗ K2` is gone.
- **Fix:**
  - In `_signal_detail`, reserve `#N CHAIN VERDICT` (cell-measured) first.
  - Clip the ticker into what remains, with `…`.
  - Shed only the address and ` +k`.
- **Tests:** at 143, a 120-character ticker with `✗ K2`, and `字`×60 with `✓`: `#737`, the chain word and the
  verdict all survive.
- **Mutant:** clip the ticker before reserving.

**N4 · One malformed `/workflows` row kills the launch tier** (introduced by F1).
- **The case:** the new index hashes raw `frontendJobId` / `contractsJobId`, and the scores slot is not sanitised.
  A list value raises `TypeError: unhashable type`, and then:
  - `_swarm_launch_read_ok` is False;
  - no slot is stored;
  - details are re-read every cycle;
  - SWARM LAUNCH goes DEAD.
- **Fix:**
  - Index only `str` job ids (via the existing job-id parser), and ignore other shapes.
  - Wrap the threaded match so any exception keeps the previous links and logs once.
- **Test:** a workflows list containing `{"frontendJobId": [1], "contractsJobId": {}}` → the tier stores, and the
  links are unchanged.

## Should fix / nits

**N5 · The memo recomputes every cycle.** `launches_ts` advances on every successful read, so "recompute only when
inputs change" holds only during outages. Key the memo on a content hash of its inputs: launch ids + `job_ids` +
token addresses, site ids + site-job facts, workflow `(frontend, contracts)` pairs. Or drop the claim from the commit
text and docs. It is cheap either way; the doc must be true.

**N6 · Popup wording.**
- `na` contracts print six `…: unavailable` lines, and passed contracts print `reason: unavailable`. Print only the
  fields that are present.
- An `na` contract reads `not deployed by this launch`.

**N7 · The swarm-row regex binds to the first `#digits`.** `(\$.*?) (#[0-9]+)` lets a ticker like `FOO #1` reserve
`#1` and spoof the number at narrow widths. Anchor it on the **last** `#N <CHAINWORD>`, or better, build the row
from the structured fields (`swarm_launch_fired` entry / `sig_swarm_*` keys) instead of re-parsing the detail string.
- **Test:** ticker `FOO #1` → the row shows `#737`.

**N8 · `tests/widgets/test_surf_swarm_inflight.py` fails 2 tests** (KeyError `SurfSwarmInFlight`) on both base and
branch. The cause is the parked widget's stale test from layout v3. Make it use the parked-signature export as v3 A1
prescribes (`SWARM_PARKED_WIDGET_SIGNATURES`), so the file is green. Do not unpark the widget.

**Report** the composing-test counts including `test_surf_swarm_inflight.py`.
