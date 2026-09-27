# PEPEPANE (pepepane) — follow-ups

Residuals from the `pepepane` branch, in the sense of CLAUDE.md "Follow-ups": each is Minor unless it says otherwise —
file it, do it as Tier 0 when its file is next touched, never its own branch or dispatch. Items that belong to another
repo say so. The §16 owner decisions (all decided 2026-09-26) that leave a step on the machines, or a standing choice, are listed with their spec §16 number; the §16 #4 worker drop-in is applied from `docs/seat_install.md` step 7 at an idle gap.

## A. Withdrawn from v1 on purpose

1. **`listPriceUsdEstimate`** (spec §10, §16 #11 withdrawn). No currency anywhere in v1: no `$` figure in any panel, document field or code path — `cost-state.totalCostUSD` and `imd doctor`'s list-price line are never read or shown. The value exists on one seat only (Claude Code), is a list-price estimate rather than a bill (both seats are subscriptions), and a schema field + CLI flag + redaction exception for it did not earn its slot. It is one `cost-state` read away if ever wanted; re-open only with a stated consumer.
2. **`tier set`, `capacity set`, `update` as verbs** (spec §11 "Not verbs in v1", §16 #3). The CONTROL modal prints one static line per procedure pointing at the aidude runbook (§2.1 update, §4c capacity). The promotion rule (spec §16 #3): each becomes a real apply verb — with its own plan, preconditions, rollback and fixtures — the moment the owner has exercised the procedure by hand once at idle. The Mac `update` procedure (`docker exec imd-worker imd update && docker restart -t 30 imd-worker`) is already measured and may be promoted first. Facts the future verbs must carry are in spec §11 (zod-invalid config → seat offline; premium model/effort table; OOM at capacity 3 reads as rejected work; never `--auto-update`).
3. **Six-surface registration** (`maxpane` menu key 9; spec §16 #10, decided no on 2026-09-26). The lean `pepepane` entrypoint is the product on both hosts. If ever wanted, it is the six-surface WP6 of the old plan (`docs/seat_implementation_plan.md`, now banner-overridden), done as its own Tier 2 change — and it re-imports the eager-manager footprint (142 vs 371 MiB, fill7 §4).
4. **Codex sqlite as a cost source** (`~/.codex/thread_history_1.sqlite` `thread_turns`; contradictions #11 unresolved: "near-empty" vs 317 turn rows). A `?mode=ro` row inspection decides whether it is a re-derivation fallback if rollout compression ever breaks the reader.

## B. Other repo: aidude

5. **`docs/imd-api-changelog.md` §3 entry** (spec §6 rule 6 — a follow-up, not a fork dependency). The 2026-09-26 entry there already records the measured standing semantics, the `/health` fields and the `/jobs/<id>/submissions` reason fields. Add, dated, the *consumer* facts PEPEPANE relies on so that The Lineup and MaxPane do not rediscover them:

   ~~~markdown
   ### 2026-09-26 (later) — how the PEPEPANE dashboard (maxpane pepepane) consumes these routes
   - Verdict-reason source order: `GET /seats/<id>/standing` (the seats form, which omits `recentFailures[].summary`) for
     the last 24 h; `GET /jobs/<jobId>/submissions` for any older failed attempt, at most 2 jobs per 300 s cycle, `summary`
     dropped before parsing completes and never persisted; reasons rendered as the enum word only.
   - `GET /seats/<id>?work=60&reviews=0` is about 78 KB raw by extrapolation (21.7 KB + 0.94 KB/row); the gzip size of this
     form is unmeasured (the full 341 KB route compressed to 59.6 KB). `work=1000&reviews=0` for the one-time backfill is
     about 271 KB raw by extrapolation from the measured `reviews=1000` form (345,685 B); measured once at install.
   - `standing.running[0].since` leads the daemon's `accepted` line by 1–4 s and `working` drops to 0 within 2 s of
     `submitted`; a restart gate that trusts a cached standing read has a ~30 s blind window at exactly the cadence tasks
     arrive (heartbeat 30 s, oracle tasks 22–40 s) — PEPEPANE re-reads standing at apply time.
   - `presenceWindowMs: 60000` in the standing `server` block is the plane's own staleness reference.
   - Bodies of `/jobs/<id>` and `/jobs/<id>/submissions` can carry raw control characters inside JSON strings: parse with
     `json.loads(strict=False)` and strip C0/C1/bidi controls before rendering.
   ~~~

6. **Mode-B writer fixes** (`tools/surf/_worker_page.py`; spec §17; §16 #12, decided 2026-09-26: keep the writer for the HTML page, stop treating `worker-status.json` as a contract). The fixes for the kept page: dedup Claude usage by `message.id` (the per-line sum is 1.5–1.9× over); Codex turns = `AgentMessage` items, not `token_usage_record`; exclude doctor/probe sessions by cwd/slug; cap or drop `reputation.rows` (uncapped, ~296 B/row); per-field `sources` with `asOfUtc`; a `completedAtUtc`; a local systemd mode and a seat-7 timer; stop `--quiet` swallowing durations; adopt `schemaVersion: 2` per `docs/seat_status_schema_v2.md`. `pepepane --once` on a timer can replace the JSON half when The Lineup wants v2.
7. **Parked dev asks** (spec §17; append to the aidude runbook §8 message; **do not send unprompted**, owner rule): `imd pause` / SIGUSR1 → `setAcceptingWork(false)`; SIGHUP config reload; `imd config get|set` so settings leave the key file; the tier in the `running <rt> on <model>` progress line or a `.imd/task.json`; `imd status --json`; signed releases (`SHA256SUMS` is unsigned); workspace retention; `ProtectProc=invisible` in the manual's unit; a per-attempt failure-reason line locally; control-character sanitisation of `working:` lines at the daemon.
8. **A nightly count-only grep** over transcripts and workspaces for `devicePrivateKey` (0/0 today, safety §1) stays an aidude ops task, not a fork feature (spec §13).

## C. Owner decisions (spec §16, all decided 2026-09-26)

9. **§16 #7** — enable `imd-worker.service` at boot. Decided yes on 2026-09-26: `systemctl enable imd-worker.service` as root (no restart), or the `enable-boot` verb. The owner completed this on 2026-09-26 (`UnitFileState=enabled`); the hero still reports future disabled states.
10. **§16 #9** — restart systemd-journald (or reboot) so `SystemMaxUse` re-resolves from about 347 MiB to 4 GiB. Decided 2026-09-26: at the next planned reboot; pepepane only surfaces the cap on MACHINE.
11. **§16 #12** — the aidude 5-minute mode-B writer stays for the HTML page (decided 2026-09-26; see item 6).
12. **§16 #17** — one measurement run on the VPS (approved 2026-09-26): `deploy/vps/probe_seat_host.sh` (→ `docs/seat_install_probe.md`, a placeholder until then), the layout sweep inside the VPS venv (fill7 OPEN: pins certified on macOS 3.14.7 / 3.11.15, not on the VPS's 3.14.4 glibc build), the slice `memory.peak`, the transient children's `memory.peak`. The unit, slice and child posture are provisional until it has run. Spec §18 open questions 17–20 close with it (stale-cursor behaviour on systemd 259; `compression.zstd` on 3.14.4; `imd status`/`doctor` under the transient posture; sysstat `HISTORY`).
13. **§16 #18** — make the Mac `imd` install root-owned/read-only in the next image (approved 2026-09-26 together with §16 #8: recreate the container with `--stop-timeout 45 --init` at the same idle gap). v1 keeps both Mac restrictions after the recreate: `LocalDockerBroker.trust()` is always `"container"`, so every Mac CLI-fed value stays `(container)`, and it refuses `--force` unconditionally (WP6). Once the recreate makes `gracefulStopPossible` read true, the CONTROL modal stops saying `force disabled (no init)` and prompts for the running node8, and the broker then refuses with "recreate … first". The follow-up that enables Mac `--force` switches the broker to the root broker's `gracefulStopPossible` check, with tests, a refusal text that no longer says "recreate first" and a matching CONTROL prompt. Dropping the `(container)` tag after §16 #18 is a separate, later change.
14. **Tracking of `docs/seat_PRD.md` and `docs/seat_implementation_plan.md`** — committed on `pepepane` with the banner (deviation recorded in `docs/decisions.md`); the owner may prefer them untracked, in which case the banner guard skips.

## D. Build, CI and hygiene

15. **`uv.lock`** for the repo (spec §15 "a `uv.lock` may be added later"; the repo has none). `deploy/vps/requirements.lock` covers the VPS closure only.
16. **CI byte-compile of `imd_dashd/` under 3.14** where available (`/opt/homebrew/bin/python3.14 -m compileall -q imd_dashd`, beside the 3.11 `.venv-pepepane` run) — the VPS interpreter is 3.14.4 and the container's is 3.11.2 (spec §5.4).
17. **Regenerate `deploy/vps/requirements.lock` and `MANIFEST.sha256` at every deployed commit** (`scripts/build_wheels.sh --out deploy/vps`): the fork wheel's hash changes with every package commit, and the guard `test_manifest_hashes_match_the_committed_files` reddens whenever a listed file changes without a `--manifest-only` re-hash. Not a bug — the price of pinning by content.
18. **Sign the MANIFEST** if the staging path is ever untrusted: `ssh-keygen -Y sign -f ~/.ssh/<key> -n file deploy/vps/MANIFEST.sha256`, verified on the host with `ssh-keygen -Y verify` (`deploy/vps/VERIFY.md`: an unsigned checksum proves transfer, not authorship — the same limit as the daemon's `SHA256SUMS`).
19. **Footprint of the lean entrypoint on Linux** — measured on macOS only (fill7 §4); the VPS `memory.peak` lands in `docs/seat_install_probe.md` with §16 #17. The Mac lean build measured 58.8 MiB on 2026-09-27. The 160 MiB CI budget stays unchanged; investigate any excess before any separately approved budget change.
20. **Steady-state growth of `~/.maxpane/seat_ledger.sqlite`** and the tail state after weeks on the VPS (fill7 OPEN) — read the file sizes at the first monthly check; the ledger has no pruning by design (it is the durable copy of a log that vacuums).

## E. Build ledger handoff — 2026-09-27

21. **Owner-run captures remain pending.** WP3 Task 3.4 Step 7 (live journald cursor/window capture), WP5 Task 5.10
    Steps 3–8 (redacted live API captures), WP6 Task 6.14 Step 8 (CLI captures), every live recapture fallback, the actual
    VPS installer and actual probe were deliberately not run. Synthetic stand-ins remain labelled. The API capture
    shape test skips until captures exist; the opt-in host test is excluded. Python 3.11 lacks `compression.zstd`, so
    its real-zstd case skips there; missing-module degradation passes and a separate existing Python 3.14 check passed.
22. **Corpus steps completed.** The locally captured windows and seven-day logs replaced the designated stand-ins;
    source hashes were checked immediately before use, fixtures were redacted and their own hashes recorded.
    `rollout_401.jsonl` is byte-identical to the authorized metadata capture. Its captured time is 19:32:59Z, correcting
    the reference plan's 19:31 value. No aidude files were edited.
23. **BASE drag-copy failures resolved by owner D2 (2026-09-27).** The two `tests/test_select_to_copy.py` cases
    `test_releasing_a_drag_copies_the_selection` and `test_ctrl_c_after_a_drag_copies_the_same_way` reflected Textual's
    change from 8.1.1 to 8.2.8, rather than a BASE code defect: the end cell is now included. Their expectations use
    the installed Textual version, preserving the earlier exclusive end below 8.2.8. Versions 8.1.2–8.2.7 were not
    bisected. This is the owner's explicit exception to leaving BASE failures alone. Historical BASE: 11261 passed,
    2 failed, 1 xfailed; neighbourhood 697 and Surf 545 (the plan's earlier measurements were 672 and 544).
24. **Final-review findings resolved and independently approved (2026-09-27).** The critical review reproduced transient
    thread-start lock leaks and queued socket applies (R1/R2). Both brokers now clean up failed startup and complete
    the watch; root admits bounded concurrent requests and refuses writes received during an active write. Review also
    found raw session metadata crossing socket/SQLite boundaries (R3) and absent lifecycle history treated as terminal
    (R4). Deep redaction now covers both brokers and direct session persistence; normal restart/stop/drain requires
    a terminal latest lifecycle line or a successful empty history read (owner D1, 2026-09-27); failed reads remain unknown, with bounded older-history retrieval and stale-segment refusal on Mac.
    Named regressions and deliberate inverse-restored mutations pass. The original reviewer marked R1–R4 ADDRESSED
    at commit 314e316, independently checking 21 distinct cases, the delayed-decode busy snapshot mutation, all 21
    MANIFEST/archive entries, every wheel hash and packaged source bytes. No Critical or Important finding remains
    in the scoped re-review. This approval is separate from the final full-suite result.
25. **Resolved spec/plan defects.** Owner-confirmed specific-first redactor order and plain yellow pending are in
    the PRD header. Bounded synchronous once backfill, centralized screen CSS, complete orphan identity/group checks,
    apply-time doctor cooldown, completed transient failure reporting, audit redaction, nonblocking CONTROL workers,
    independent force/local-only acknowledgements, positive footprint fallback and probe redaction/timeout corrections
    are implemented and tested; dated technical details are in `docs/decisions.md`.
26. **Execution and test repairs are recorded.** WP4's inverse-mutation helper briefly changed a docstring and a
    failing intermediate verification was committed; the immediate repair preceded dependent work and the mutation
    was repeated successfully. Reference API request recording, first-batch LOG assertions, modal observable waits,
    CSS-selector/AST guards and installer executable-command guards were corrected without weakened assertions.
    WP9's empty-string inverse helper refused restoration; the exact original line was restored and byte-checked
    before any commit. These are closed execution defects, not remaining product work.
27. **Whitespace inherited by the hoist.** The original seat-word EOF blank and retained Surf formatter separator
    remain as required by the verbatim-hoist instruction; they do not change behavior. Do not use a global whitespace
    cleanup to rewrite the protected Surf files.


## F. Independent-verification follow-ups — 2026-09-27

28. **Over-redaction of ordinary words.** The specific-first rule preserves secret placeholders, but the broad `sk-`
    pattern still turns `task-runner` into `task-[redacted]` (owner note 8). Keep the conservative redaction until a
    narrower rule has tests for real key forms and embedded tokens; do not weaken the secret boundary to prettify a log.
29. **Pending reason suffixes.** Restore `pending (disagreed)` and `pending (awaiting)` only when an authoritative
    field carries that distinction. Until then the plain yellow `pending` remains owner-approved (D3), with no inferred
    disagreement or awaiting status.
30. **Root broker security review.** The root-run code is about 2,500 lines against the spec's approximate 700-line
    estimate. The owner should review that larger privileged surface before deployment; the estimate is not a tested
    size limit, and no automatic source reduction is proposed.
31. **Public-push hygiene, before any public push.** This round records the work; it does not publish or make these
    fixture/lineage changes. Replace real host IPs `82.165.187.96` and `89.167.27.194` with documentation addresses
    in `192.0.2.x` in `tests/broker/_harness.py`, `tests/broker/test_seat_child_unit.py`,
    `tests/fixtures/seat/cli/systemctl_cat.txt` and `tests/fixtures/seat/cli/systemctl_show_ipaddressdeny.txt`.
    Rehash both captures in `tests/fixtures/seat/MANIFEST.json`, correct its note naming the addresses, and replace
    the five places in `docs/pepepane_plan.md`. Escape literal U+202E/U+202D/U+2066 in
    `tests/data/test_seat_log_grammar.py` (the original lines 168/171) and `tests/widgets/test_seat_now_log.py`
    (original line 42). Optionally replace the partially synthetic `72b617d4…` and `0x887b…` values with fully
    synthetic identities using the `0x…c1a1` convention. Review local `/Users/banse/...` paths in the docs as well.
