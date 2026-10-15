# Surf loading implementation plan

Tier 2: cross-dashboard presentation and manager lifecycle observation.
Estimated production change: 500–900 lines, below 1,000; no package reviews,
one final whole-diff review after integration. No full repository suite.

## Work packages and ownership

1. **Manager seams — planning/manager implementer.** Own
   `data/surf_manager.py`, `data/swarm_tokens_manager.py`,
   `data/swarm_token_detail.py`, and dedicated
   `tests/data/test_surf_loading.py`. Implement the frozen interfaces in the PRD;
   preserve scheduling, cache and source-state behavior. Own this plan and PRD.
2. **News/launchpad/POOL4 presentation — widget implementer A.** Own those
   dashboard-specific modules under `widgets/surf/` and their targeted widget
   tests. Remove explicit source warnings, preserving clocks/values/coverage and
   layout. Shared `news_hero.py` ownership is assigned by the controller before
   editing so its common card renderer has exactly one writer.
3. **Swarm/work/oracles/boardroom presentation — widget implementer B.** Own
   the `widgets/surf/swarm*`, `agent*`, `work.py`, `oracles.py`, relevant `_swarm*`
   helpers and `widgets/surfboard/`, plus matching targeted widget tests. Do not
   edit manager, screen or A-owned common hero files.
4. **Screen integration/token presentation — controller.** Own screen lifecycle
   adapter, `screens/surf.py`, `surfboard.py`, `swarm_tokens.py`,
   `swarm_token_detail.py`, token widget packages, shared presentation helpers,
   compositing/lifecycle tests and final documentation/followups. Use
   `_refresh_in_flight or manager.is_loading(view)`; a short UI-only timer
   updates the indicator and requests a passive repaint on completion. Stop the
   timer on suspend/unmount. Keep RefreshGuard as the request owner.

Packages 1–3 can run concurrently after this interface freeze. Package 4 can
prepare tests and presentation independently, then integrate the manager seams.
The controller assigns any shared helper to one writer. Agents do not overwrite
other owners' changes and do not dispatch reviewers or further agents.

## Existing seams and risks

- `RefreshGuard.start_refresh()` raises `_refresh_in_flight` before scheduling;
  `_guarded_refresh()` clears it in `finally`. It alone cannot represent manager
  detached tasks after a cached snapshot returns.
- `SurfManager._hub_loading_state()` only marks missing boardroom cards; cached
  reopen reads require the new task observer. Task references already live on
  the manager and its work/oracle/contribution readers.
- `get_hub_snapshot()` is already a passive Surf projection. Tokens `_snapshot`
  currently schedules work; separate its offer phase with an explicit flag.
  Detail must refresh borrowed cached token fields without calling its async
  fetch seam, or market completion would retain the old token until normal poll.
- A cancelled reader can remain not-done briefly: check `cancelling()` as well as
  `done()`. Closing a detail adapter does not close borrowed overview tasks.
- Do not infer pending from missing data or stale/pending source labels: retry
  backoff and unsupported sources have no request to display as loading.
- `is_loading` maps view-specific tasks so a long staker sweep does not keep an
  unrelated agent or work view loading. Boardroom includes its visible families.
- Missing values must not become known-empty rows. Coverage `partial`/`≥`
  remains meaningful even when a source warning disappears.

## Implementation and verification sequence

1. Write failing task-observer and passive-projection tests with held
   `asyncio.Event` operations, then implement the smallest manager changes.
2. Write composited widget expectations before removing each warning branch;
   preserve meaningful operational warnings and third-party text.
3. Integrate loading on open/reopen/mode change and passive completion repaint.
   Assert no overlapping refresh, no retry loop and no stuck indicator after
   success, failure, cancellation or suspend. Use observable events, not sleeps.
4. Show real keyless renders at the owner's 149×45 size before hardening,
   docs records or final review. Prefer representative Surf, boardroom and token
   views covering cached/fresh/pending states. No pin changes are intended.
5. Mutation-proof task scoping, cancelling-task handling and passive no-offer
   behavior. Run targeted cases while editing; once before commit run touched
   and composing files, fast non-mount guards and docpins. Use isolated HOME for
   parallel pytest and unset NO_COLOR for render checks. Re-sweep only pins whose
   geometry changed; address sweeps if address cells changed.
6. One final generic whole-diff review under the CLAUDE reviewer contract; one
   fix wave and scoped re-review only for production fixes. File Minor-only
   findings. Record any reproducible preexisting failures explicitly.
7. Controller updates followups/rules with the owner display override and commits
   the completed, verified change. Leave unrelated untracked files untouched.
