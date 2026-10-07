# Codex fix round 4: SWARM production launches (verification of 3356389, written 2026-10-06)

> **Do not use any superpowers skill.** This brief, the plan (c9352030), `fix1`–`fix3` and `CLAUDE.md` are the
> whole process.

**Branch:** `feature/swarm-launches`; continue from `3356389`. **Fix round 3 is verified; nothing blocking.** Live,
26 production launches give 24 `✓ swarm` and 2 parked `✗ K4`. G2 makes 0 RPC calls in settled cycles. Every live
launch fires exactly once. Your 18 mutants were re-run and all killed.

**This round:** one commit. Each item gets its test and its named mutant, in the commit body. Keep
`tests/analytics/test_surf_signals.py` and `tests/widgets/test_surf_swarm_inflight.py` in the pre-commit set. Never
merge, push or tag.

**H1 · A parked launch's K4 freezes on an early, empty detail** (should-fix; predates round 3).
- **Evidence:** the owner's real cache holds #787 with `admission: []` at
  `detail_version ['parked','2026-10-06T09:18:03.751Z']`. The API now returns 7 admission checks (`findings` and
  `protected_invariants` failed) under the **same** `updatedAt`, so the API filled `admissionChecks` without bumping
  `updatedAt`. `admission == []` gives K4 `pass` → `-- parked` forever. A cold start gives the correct `✗ K4`.
- **Fix:**
  - `check_launch` treats `admission == []` as K4 `unknown`, never `pass`.
  - The manager re-reads the detail **even when the version is unchanged** while K4 is `unknown` for a `parked` or
    `admitted` production launch, on a back-off of at most once per 1,800 s. The read counts against the
    3-per-cycle budget.
- **Tests:**
  - empty admission → K4 `unknown`;
  - #787-shaped: a cached empty admission at the same version, then 1,801 s later a detail with failed checks →
    `✗ K4`;
  - no re-read within 1,800 s.
- **Mutant:** empty admission → `pass`.

**H2 · Test gap (N5):** a detector case with two or more active FIRED launches, asserting
`extra_count == len(active) - 1` and that `+k` shows in the mounted row at a width that keeps it.
- **Mutant:** FIRED `extra_count` = 0. It survives today.

**H3 · Nits** (fix if small; otherwise leave them with the follow-ups):
- **K6 / K2 unknown re-reads txs every cycle** (hypothetical today):
  - with complete receipts but no `ModifyLiquidity` log, K6 is `na`;
  - with K2 unknown only because the policy version is unknown, wait for the next policy refresh rather than
    re-reading txs.
- **Migration marker order:** set `policies_schema = 1` only after a **successful** policies read when legacy
  policies are present.
- **K6 `owner_is_factory`:** return `None`, not `False`, when the kind is absent or declares no factory, and update
  the one test that pins `False`.

**Report:** test counts (the two required files included) and the mutant list.
