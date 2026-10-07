# Codex fix round 3: SWARM production launches (verification of 1d747c0, written 2026-10-06)

> **Do not use any superpowers skill.** This brief, the plan (c9352030), `fix1`, `fix2` and `CLAUDE.md` are the
> whole process.

**Branch:** `feature/swarm-launches`; continue from `1d747c0`.

**Fix round 2 is verified.** N1, N3–N8 work as briefed; 8 of your recorded mutants were re-run and killed. N2 also
works as briefed, **but the briefed rule was wrong (controller error, not yours)**. It is corrected here.

**This round:** one commit for G1–G2, one for G3–G6. Each item gets its test and its named mutant, recorded in the
commit body. **Run `tests/analytics/test_surf_signals.py` in every pre-commit test set.** Round 2's validation never
ran it, and it is red on `1d747c0`. Never merge, push or tag.

## Must fix

**G1 · Correct the K3 coverage rule (N2).**
- **Why it was wrong:** `custom_token` and `evm_project` launches use the swarm's shared `PoolInitializationGuard`
  hook, which is **never attested**. Only `univ4_hook` launches attest their own hook.
- **What that does today:** measured on all 25 live production launches, **17 of 23 deployed launches** show
  `… 3/4` (K3 `unknown`, unmatched `PoolInitializationGuard`). `test_signal_matrix[swarm-fired]` is red: the v8 #737
  event yields `… 3/4`.
- **Rule:** K3 `pass` / `pass_immutables` needs both of these:
  - at least one attested contract matched by (a) or (b);
  - every artifact whose role is in `roles` maps by name to a matched attested contract, where
    `roles = ("token", "hook") if row.get("kind") == "univ4_hook" else ("token",)`.

  Otherwise K3 is `unknown`, with `unmatched_artifacts` limited to those roles.
- **Expected live result** (verified by reimplementation): **23 deployed launches → `✓ swarm`**, and the 2 parked
  launches (#770, #787) → `✗ K4`.
- **Tests to update** (they encode the wrong rule; applying the right rule turns exactly these red):
  - `test_v8_attestation_checks[737]` and `[747]`;
  - `test_fix2_k3_needs_matched_code_and_covers_role_artifacts`: `[unattested_hook]` gets `kind="univ4_hook"`, and
    `[renamed]` expects the token only;
  - `test_per_contract_progress_survives_cache_and_rejects_invalid_states`;
  - `test_details_read_once_then_on_version_change_and_unknown_retries`;
  - `test_launch_popup_tokenless_uses_job_and_immutables_evidence`.

  `test_signal_matrix[swarm-fired]` must go green.
- **New tests:**
  - a `custom_token` with an unattested `PoolInitializationGuard` hook → `pass`;
  - a `univ4_hook` with an unattested hook → `unknown`, naming the hook.
- **Mutant:** require hooks for every kind.
- **Docs:** reword `.claude/rules/surf.md` ("every token/hook artifact") to the role rule above.

**G2 · K3 left `unknown` for coverage reasons re-reads RPC forever.**
- **Measured on the branch:** each 60 s cycle re-requested 49 tx hashes plus 17 code reads on mainnet (about 115
  publicnode calls a minute) and 4 on RH, although every other check was settled.
- **Fix:** when every per-contract state is terminal (`pass`, `pass_immutables`, `fail` or `na`) and K3 is `unknown`
  only for coverage, do not re-request its hashes or code.
  - Re-evaluate only when the facts change (status or `updatedAt` → detail re-read).
  - Otherwise use a back-off of at most one retry per 1,800 s.
- **Test:** a renamed-token launch makes RPC requests once, then none over 5 cycles.

## Should fix

**G3 · A policy without `kind` re-reads `/launch/policies` every cycle.** Measured: 6 reads in 6 cycles, against 1
normally. The trigger is the `any(not policy.get("kind"))` migration check around `surf_manager.py:5520`.
- **Fix:** run that migration once, for legacy cached entries, behind a schema marker in the slot. It must never
  react to live API content.

**G4 · A launch row without `kind` falls back to pooled factories.** #775 with `kind` removed gives a false `✗ K2`.
- **Fix:** with `kind` None, judge K2 on sender plus receipt only, and never apply other kinds' factories.
- **Test:** the #775 tx with `kind` removed → `pass`.

**G5 · Test gaps** (surviving mutants from the verification):
- **M-N1b / M-N1c:** `known` ignoring `kind`, in `policy_sets` or in the manager. Add a test that a newer
  `evm_contracts` policy version does not mark a `univ4_hook` launch's version as known, and that K6
  `owner_is_factory` uses the launch's kind.
- **M-N4c:** the memo marked fresh after the matcher raised. Add a test that after one failure and an unchanged
  input, the next cycle retries the match.

**G6 · Small robustness.**
- The WATCH row `deploying $<120 chars> #737` loses `#737` at the 143 pin, because the reserve regex requires `$` at
  the start. Build the WATCH detail from structured fields, as N7 now does for FIRED.
- A FIRED row whose chain word is `--` (unknown chain id) falls back to the generic cut and loses `#N` and the
  verdict. Treat `--` as a chain word for the reserve.
- A matcher that keeps failing logs a traceback every cycle. Log once per distinct exception type until a success
  resets it.
- The ` +k` count is shed together with the address even when it alone fits. Shed the address first, then ` +k`.

**Report:** composing-test counts with `test_surf_signals.py` and `test_surf_swarm_inflight.py` included, and the
mutant list.
