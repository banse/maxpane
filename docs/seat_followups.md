# PEPEPANE (pepepane) — follow-ups

Residuals from the `pepepane` branch, in the sense of CLAUDE.md "Follow-ups": each is Minor unless it says otherwise —
file it, do it as Tier 0 when its file is next touched, never its own branch or dispatch. Items that belong to another
repo say so. The §16 owner decisions (all decided 2026-09-26) that leave a step on the machines, or a standing choice, are listed with their spec §16 number; the §16 #4 worker drop-in is applied from `docs/seat_install.md` step 7 at an idle gap.

## A. Withdrawn from v1 on purpose

1. **`listPriceUsdEstimate`** (spec §10, §16 #11 withdrawn). No currency anywhere in v1: no currency figure in any panel, document field or code path — `cost-state.totalCostUSD` and `imd doctor`'s list-price line are never read or shown. The value exists on one seat only (Claude Code), is a list-price estimate rather than a bill (both seats are subscriptions), and a schema field + CLI flag + redaction exception for it did not earn its slot. It is one `cost-state` read away if ever wanted; re-open only with a stated consumer.
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
12. **§16 #17** — the owner completed the VPS probe on 2026-10-02 against a8912d6 and the CONTROL drain exercise at 23:37–23:39 UTC; the live TUI slice peak was measured on 2026-10-03. `docs/seat_install_probe.md` holds sections 1–19 verbatim and section 20's audit, journal and slice evidence. Spec §18 open questions 17–20 are answered by p04 (stale cursor), p08 (compression.zstd), p12/p13 (transient commands) and p19 (sysstat HISTORY). The slice peak is 114634752 bytes of 268435456; the doctor child peak is 139M. The status child peak remains unmeasured because it emitted no accounting line, and the VPS layout sweep remains unrun (pins are certified on macOS 3.14.7 / 3.11.15, not the VPS's 3.14.4 glibc build).
13. **§16 #18** — make the Mac `imd` install root-owned/read-only in the next image (approved 2026-09-26 together with §16 #8: recreate the container with `--stop-timeout 45 --init` at the same idle gap). v1 keeps both Mac restrictions after the recreate: `LocalDockerBroker.trust()` is always `"container"`, so every Mac CLI-fed value stays `(container)`, and it refuses `--force` unconditionally (WP6). Once the recreate makes `gracefulStopPossible` read true, the CONTROL modal stops saying `force disabled (no init)` and prompts for the running node8, and the broker then refuses with "recreate … first". The follow-up that enables Mac `--force` switches the broker to the root broker's `gracefulStopPossible` check, with tests, a refusal text that no longer says "recreate first" and a matching CONTROL prompt. Dropping the `(container)` tag after §16 #18 is a separate, later change.
14. **Tracking of `docs/seat_PRD.md` and `docs/seat_implementation_plan.md`** — committed on `pepepane` with the banner (deviation recorded in `docs/decisions.md`); the owner may prefer them untracked, in which case the banner guard skips.

## D. Build, CI and hygiene

15. **`uv.lock`** for the repo (spec §15 "a `uv.lock` may be added later"; the repo has none). `deploy/vps/requirements.lock` covers the VPS closure only.
16. **CI byte-compile of `imd_dashd/` under 3.14** where available (`/opt/homebrew/bin/python3.14 -m compileall -q imd_dashd`, beside the 3.11 `.venv-pepepane` run) — the VPS interpreter is 3.14.4 and the container's is 3.11.2 (spec §5.4).
17. **Regenerate `deploy/vps/requirements.lock` and `MANIFEST.sha256` at every deployed commit** (`scripts/build_wheels.sh --out deploy/vps`): the fork wheel's hash changes with every package commit, and the guard `test_manifest_hashes_match_the_committed_files` reddens whenever a listed file changes without a `--manifest-only` re-hash. Not a bug — the price of pinning by content.
18. **Sign the MANIFEST** if the staging path is ever untrusted: `ssh-keygen -Y sign -f ~/.ssh/<key> -n file deploy/vps/MANIFEST.sha256`, verified on the host with `ssh-keygen -Y verify` (`deploy/vps/VERIFY.md`: an unsigned checksum proves transfer, not authorship — the same limit as the daemon's `SHA256SUMS`).
19. **Footprint of the lean entrypoint on Linux** — the live VPS TUI slice peak is now 114634752 bytes, measured on 2026-10-03 and recorded in `docs/seat_install_probe.md` with §16 #17. This slice measurement differs from the Mac cold physical peak of 58.8 MiB on 2026-09-27. The 160 MiB CI budget stays unchanged; investigate any excess before any separately approved budget change. The status-child peak and VPS layout certification remain open (item 12).
20. **Steady-state growth of `~/.maxpane/seat_ledger.sqlite`** and the tail state after weeks on the VPS (fill7 OPEN) — read the file sizes at the first monthly check; the ledger has no pruning by design (it is the durable copy of a log that vacuums).

## E. Build ledger handoff — 2026-09-27

21. **Owner-run captures remain pending.** WP3 Task 3.4 Step 7 (live journald cursor/window capture), WP5 Task 5.10
    Steps 3–8 (redacted live API captures), WP6 Task 6.14 Step 8 (CLI captures), every live recapture fallback were deliberately not run by Codex. The owner has since run the VPS installer and
    probe on 2026-10-02; their reviewed output is now in `docs/seat_install_probe.md`. Synthetic stand-ins remain labelled. The API capture
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
31. **Public-push hygiene, before any public push (partly completed 2026-09-28).** The two real host IPs are now replaced by documentation addresses `192.0.2.10` and `192.0.2.11` in `tests/broker/_harness.py`, `tests/broker/test_seat_child_unit.py`, `tests/fixtures/seat/cli/systemctl_cat.txt` and `tests/fixtures/seat/cli/systemctl_show_ipaddressdeny.txt`; normalized hosts retain `/32`. Both fixture hashes and the MANIFEST note are corrected. The fixture guard rejects global IPs and email addresses, including decoded journal byte arrays. The probe masks global IPs and its filled-document guard covers `docs/seat_install_probe.md`; include that document in the pre-push review. The five IP occurrences in frozen `docs/pepepane_plan.md` remain intentionally untouched until its historical-body restriction is lifted. Escape existing literal U+202E/U+202D/U+2066 in `tests/data/test_seat_log_grammar.py:168` and `:171` (U+202E) and `tests/widgets/test_seat_now_log.py:42` (U+202E, U+202D, U+2066) before public push. Optionally replace the partially synthetic `72b617d4…` and `0x887b…` values with fully synthetic identities using the `0x…c1a1` convention. Review local home-directory paths in the docs as well. This branch does not publish.

32. **Fix-round review R1–R3 independently approved (2026-09-27).** Unreadable lifecycle records now fail closed despite a cursor or neighboring valid record. A single in-flight snapshot protects accept and dispatch during write completion. Partial orphan actions retain an actual-target apply audit and verification watch on deadline or snapshot refusal, with explicit partial-action error detail. Permanent deterministic regressions cover these cases. The independent scoped reviewer marked all three ADDRESSED at `5233d4e`: 34 named checks passed, inverse mutations failed in 12/2/4 cases, and 18 checks passed after exact restoration. No Critical or Important finding remains in this scoped review.

33. **Recursive deviceKey redaction allowance (recorded residual, 2026-09-27).** The general `redact` and `redact_tree` APIs still preserve long hex values under a field named `deviceKey` at any depth. That field name alone does not prove the value is public. The seat projection separately enforces the exact root path and a whoami match; its nested-key refusal tests stay in place. A future change can restrict the general allowance to the two whoami call sites with callers and fixtures audited together. Until then, do not treat recursive redaction alone as proof that an arbitrary payload contains no private key. This round explicitly records the residual under fix brief 2 item 9 and leaves the shared API unchanged.


34. **Second-round independent review R1/R2 (2026-09-27): fixed and independently approved.** Queue-command timeout keeps the real watch until evidence or the verification deadline decides its outcome. Recovered skills changes retain restart-required state and drain-restart guidance; recovered restarts clear that note. Permanent tests use the real root broker and cover both success and failure. No live-host action was used.

Scoped re-review approved both findings after commits `cad1fbf` and `d57ec81`: all three reproductions and their pertinent permanent tests passed (26 checks). The first-orphan-timeout placeholder remains terminal failed; the uncertainty exception is restricted to real systemctl verification watches. No Critical or Important review findings remain.

35. **2026-10-03 — Lifecycle compatibility probe p05 completed.** The owner's a8912d6 probe on 2026-10-02 reports PASS for the lifecycle grep with honest split-head support, including newest match, PCRE2 and no-match behavior. The measured output is in `docs/seat_install_probe.md` p05. No further p05 re-run is pending from the fourth-round change.

36. **2026-09-28 — Forced-restart verification during prolonged teardown: closed by owner D7.** A forced watch now allows TimeoutStopUSec plus 30 seconds after shutting down, further capped to reach its verdict ten seconds before the 120-second watch purge. Both the runtimes verdict and missing-runtimes timeout use that bound. Normal restart, drain-restart and start retain 30 seconds. Synthetic root integration confirms shutdown at 20 seconds and runtimes at 95 seconds succeeds with a 90-second stop timeout, while missing or late runtimes fails before purge. Stop's separate extended deadline requires deactivating or a shutdown line. This supersedes the third-round recorded residual.

37. **2026-09-28 — Third-round independent review R3.1 resolved.** Probe MESSAGE byte arrays now pass through strict decoding before text redaction; invalid arrays are omitted with a fixed label. Independent scoped re-review marked the fix in `3b7b0a6` ADDRESSED: 13 named checks passed, three mutation cases failed, and exact inverse restoration returned all four regression cases to green. No Critical or Important review finding remains; follow-ups 35 and 36 remain as recorded.

38. **2026-09-28 — G3 honest-split limit (recorded residual).** An accepted head opens a task when the allowed-paths list or campaign harness contract is split across log records. The continuation is control-plane text and can itself be a stamped terminal line, closing that head. The same terminal forgery exists without G3. Thus the new fail-closed guarantee covers honest splits; these local logs are not authenticated task events. No protocol or control-plane redesign is included in this round. **2026-10-03 extension, Mac only:** `_docker_tail_read` in `maxpane_dashboard/data/seat_broker_client.py:469–485` drops Docker's timestamp prefix and sorts by the daemon's printed stamp. With a hostile control plane, a forged 2099 terminal continuation sorts after later real task heads and makes the local-only gate safe while a task runs. A runner fake through the actual Docker-log parser reproduced this; a quiet 200-line tail can retain it for about 100 minutes. Root orders journal records by `__REALTIME_TIMESTAMP` and does not share this ordering defect. **Owner decision needed:** consider Docker timestamps for broker gate ordering only, or clarify the spec; the Mac follower watermark explicitly remains the daemon stamp, never Docker's timestamp (spec §5.1). Add parser-path coverage; do not silently change the follower transport contract.

39. **2026-09-28 — Redactor residuals retained by owner brief 4.** The runtime redactor still permits unlabelled 32–63-character hex runs, and a Bearer value interrupted by an ESC sequence can evade its credential pattern after ESC becomes a visible glyph. G2 does not change those existing rules. The probe and its document guard apply the stricter 32-character hex policy independently; these residuals must not be read as a guarantee that arbitrary runtime text is credential-free.


## G. Final-round verified residuals — 2026-10-03 (anchored to a8912d6)

The following remain follow-ups, not fixes in this round. Synthetic local reproductions and source checks confirmed the premises; no host was contacted. Items 31 and 38 above were extended with exact code-point locations and the Mac future-stamp case. The completed install and probe are recorded in items 12, 19 and 35.

40. **IPv6 suffixes can bypass the shared probe detector.** `imd_dashd/probe_hygiene.py:11–15` greedily includes suffixes that make an otherwise global address unparseable. Both `relay 2606:4700:4700::1111: refused` and `2606:4700:4700:0:0:0:0:1111:443` survive `redact_public_ips`, `public_ip_matches` and the probe-doc guard; fixtures share that detector. A compressed address plus port such as `2606:4700:4700::1111:443` parses as another global address and is caught. Try progressively shorter candidates by dropping a trailing colon plus digits, or a bare colon, before giving up; preserve tests for complete valid compressed addresses.

41. **Lifecycle grep has an untested split-head dependency.** The behavioural G3 root cases in `tests/broker/test_seat_fix4.py` put their split heads five seconds ago, inside `JOURNAL_WINDOW_S=1800`; they do not require the head alternative in `lifecycle_journal_argv` (`imd_dashd/imd_dashd.py:430`). A local broker reproduction with a split head 40 minutes old refuses with `task running deadbeef · 40:00`; an in-memory mutation omitting only `ACCEPTED_HEAD_RE` allows the restart. The MANIFEST notices a source mutation, but is not behaviour coverage. Add a root regression older than the window, where only lifecycle grep can recover the head.

42. **Redaction is not generally idempotent and one pass can leave values clear.** `imd_dashd/redact.py:139–143` applies RULES/G2 before HEX64. A 64-character hexadecimal run immediately followed by `x-api-key: DEMO` or an npm token leaves that value clear on the first pass; a second pass masks it. A following `cookie: sid=DEMO` loses its leading c into a 65-character hex run, leaving `ookie: sid=DEMO` clear even on later passes. The earlier decisions.md idempotence claim is corrected by a dated note. HEX64-first or fixed-point iteration can repair the first two cases; the cookie case additionally needs a boundary rule that never ends a hex run inside a word. Test all three before changing the byte-identical redactors together.

43. **p04 omits journalctl's own diagnostics.** `deploy/vps/probe_seat_host.sh:200–203` merges stderr into JSON input; `journal_heads` replaces non-JSON lines with `<non-JSON line omitted>` at line 186. A synthetic `Failed to seek to cursor…` is lost, although cursor diagnostics are part of probe section 4/open question 17. Preserve scrubbed stderr and non-JSON diagnostics separately, as p05 already does. The captured p04 result remains unchanged.

44. **The probe-doc content guard has gaps beyond G2.** `_check_probe_doc` in `tests/test_seat_probe_hygiene.py:21–57` misses synthetic sk-ant-oat01 tokens, Authorization Bearer values, JWTs, email addresses and a raw U+202E. The fixture guard catches the sk-, JWT, email and raw-control/bidi cases but also misses Bearer. Reuse the fixture guard's shapes and add the RULES Bearer pattern. Exclude `PLAIN_SECRET_NAME_RE`: the probe's legitimate p11 heading/body contain “secret key name” and “secret-name regex”, so that broad name detector would reject the filled report.

45. **Spec-level redaction residuals need an owner decision before widening §13.** Step zero leaves 34 Unicode Cf code points under the local Python 3.11 Unicode 14 database: U+0600–0605, U+06DD, U+070F, U+0890–0891, U+08E2, U+110BD, U+110CD, U+13430–13438, U+1BCA0–1BCA3 and U+1D173–1D17A. Local Python 3.14 confirms 41 under Unicode 16, adding U+13439–1343F, as on the VPS interpreter. U+FE0F, U+034F, U+E0100 and Hangul fillers U+115F, U+1160, U+3164 and U+FFA0 also survive; splitting a token with one leaks it. URL userinfo can survive when it contains the SK replacement's opening bracket, a second at-sign or an underscore before the scheme. Header rules cover wire `Name: value`, but not dict/JSON renderings such as a quoted x-api-key key. Conversely, ordinary prose containing cookie: or x-api-key: is over-redacted. Agree the scope and add representative tests before changing the shared rules.

46. **Stale fork wheels accumulate across version bumps.** `deploy/vps/install.sh:187–191` copies into the installed wheels directory without pruning it; `check_fork_wheel.py:14–16` requires exactly one maxpane wheel. A future version alongside 0.9.3 leaves two candidates and fails the post-install check. Latent while the version stays 0.9.3. Remove stale maxpane wheels before copying, or point verification at the staged tree's exact wheel; cover an upgrade between two versions.

47. **Mac drain-fire exceptions can lose the drain silently.** Cross-reference decisions.md's 2026-10-02 fix6 drain-dispatch entry. `LocalDockerBroker._fire_drain` (`maxpane_dashboard/data/seat_broker_client.py:1120–1145`) has try/finally only. A synthetic gate RuntimeError during fire leaves the drain disarmed, adds no audit line, and escapes both tick and a normal non-ping call (which catches only BrokerError). Add a guarded recovery boundary before dispatch and a terminal audit after dispatch, preserving the root's no-second-restart rule.

48. **Root interpreter isolation:** `journal_heads` (`deploy/vps/probe_seat_host.sh:165–166`) runs `/usr/bin/python3 -c` without `-I`; add isolated mode and retain its explicit broker import path.
49. **UTF-8 output cuts:** p09, p12 and p13 use `head -c` (`probe_seat_host.sh:334,380,420`), which can split a character; truncate decoded text or back off to a valid byte boundary.
50. **Same-version hash drift:** the G4 guard (`scripts/build_wheels.sh:71–75`) compares name/version pins only; compare or separately approve changed hash sets if same-version hash changes must require `--upgrade`.
51. **Archive reproducibility:** `build_wheels.sh:114–116` packs the working tree with only two excludes, no `--no-mac-metadata`/`COPYFILE_DISABLE`, and unnormalised mtimes; define a reproducible staging/metadata policy before claiming byte-reproducible tarballs.
52. **Mac G3 coverage:** `tests/broker/test_seat_fix4.py::test_mac_accept_forms_block_apply` uses `_local` and its `_injected_tail`, bypassing `docker logs` parsing; add parser-path cases with Docker timestamp prefixes, including item 38.
53. **Fixture-note punctuation:** MANIFEST notes for `cli/systemctl_cat.txt` and `cli/systemctl_show_ipaddressdeny.txt` join the older explanation and “Public host IPs replaced…” without a period; separate the sentences when next editing those entries.
54. **Decision-log formatting:** decisions.md mixes dated headings, bold dated paragraphs and dated list items; choose one style for future entries, keeping historical content intact.
55. **Stop-reason wording:** a watch polled at 60 seconds with an active unit and no shutdown evidence still says “within 30 s”; this correctly names the unextended deadline, not elapsed time (`VerifyWatch.update`); consider showing both to avoid ambiguity, without changing D5–D7 timing.


## 2026-10-03 — Seat #3 extension

56. **Gate step (c) describes only the newest lifecycle task at concurrency 3.** `imd_dashd/gate.py::newest_lifecycle` returns the newest anchored lifecycle line, and `evaluate` derives its open-task reason from that single line. Seat #3 runs Claude with concurrency 3; seat #7 also had concurrency 3 before the owner's test. A terminal line for task A can hide an open task B, so the task-specific reason can be absent or name the wrong task. Non-idle heartbeats and the plane's running count still block restarts. Suggested follow-up: track open tasks by task identity across accepted and terminal records, preserving the independent heartbeat and plane gates; add overlapping-task regressions before changing the spec's step (c). No gate change in round 8.

## 2026-10-03 — Round 9 tail observation

57. **Open-ended gap after an unsuccessful cursor attach.** The synthetic `round9/empty_cursor_attach.json` fixture reproduces an empty journal cursor attach with exit code 1. `TailThread.run_once` invokes the existing cursor fallback and clears the unusable cursor; `detect_gap` has no first available timestamp and consequently records an open-ended gap. This differs from D10's successful empty read after a valid watermark, which is healthy. The fixture cannot distinguish retained-history loss from an attach failure, so round 9 preserves the gap evidence. A later diagnostic improvement should retain a scrubbed attach failure reason and distinguish these cases when the available evidence permits it, without treating every unsuccessful empty attach as ordinary idleness.


## 2026-10-04 — Round 10 redactor work retained

58. **64-hex text overmatch.** Both shared redactor copies replace every 64-hex value in prose, including a public digest inside an objective or reply. Round 9 retains this conservative behavior and never widens the document canary. Round 10 must change both copies together with regressions distinguishing public prose from credentials and preserving the status boundary.

59. **The sk- pattern matches inside ordinary words.** For example, `risk-adjusted` becomes `risk-[redacted]`. This is the same open class as item 28; round 10 owns any narrower boundary, with tests for real key forms and embedded tokens in both copies. All other unresolved items above, including concurrency item 56 and the unsuccessful cursor-attach evidence in item 57, remain open. Capacity/tier verbs, payer-chain reads and seat #3's worker-drop-in work remain outside round 9.

## 2026-10-04 — Round 9 fix deferred work

60. **Document UTF-8 byte budget and unbounded node types.** API text caps count characters, while status validation measures UTF-8 bytes and NODES retains an uncapped set of node types. Independent verification constructed an 11.7 MB hostile document: a sufficiently large ledger can exceed the 2 MiB limit and blank the dashboard until the contributing rows age out. Redesign proof 13 covers the shaper rather than the complete manager document. Round 10 should bound the complete serialized document while preserving honest all-history coverage and explicit truncation, with multibyte and many-node regressions through `document()`.

61. **Persisted effects of redactor overmatches.** Items 58 and 59 also affect the ledger's cached objective, reply and oracle text. Because round 9 sanitizes before persistence, a public 64-hex digest or an ordinary word damaged by the sk- pattern cannot be recovered from that cache merely by fixing the renderer. The later redactor correction needs an explicit cache recovery policy alongside both copies' tests. Their existing conservative behavior is unchanged in this fix round.

62. **Busy job-detail class couples oracle and other jobs.** Oracle and non-oracle jobs share the job-detail route class. A shed oracle job-detail request therefore pauses non-oracle detail reads that the verdict fallback needs. A later scheduling change should decide whether narrower pause classes are justified by actual API shedding behavior, preserving a pause floor for every trigger.

All earlier unresolved follow-ups remain open, including the concurrency gate, shared redaction, host probe and installer items. This correction changes no root-broker implementation, control verb, unit, installer, chain read or live system.
