# Keep card appearance stable during reads

Owner request, 2026-11-11. Tier 2, one root-owned package under 100 production
lines; one final review, no task review.

Interim reader projections can mark source data stale/loading while a refresh
is pending. Numeric presentation memory retains values, but raw status currently
recolors the frame and digits. Retain each complete displayed body/footer during
pending reads, then apply the completed projection together. Explicit loading
rows retain their last display too. Source snapshots and observation times stay
unchanged. Completed failure/idle/offline/zero states remain representable;
identity changes and empty slots clear the prior seat immediately.

Root owns SurfboardCard presentation retention and SurfboardScreen loading-state
synchronization before panel dispatch, plus event-driven composite regressions.
Reuse CardValues and existing footer/identity scopes. Do not change poll cadence,
readers, APIs or shared application scheduling. Cold cards may populate before
the first completed read where no prior display exists.

Verify text AND composited colors across pending stale/loading projections,
completion, real zero, failure and seat identity changes. Show a live refresh
before/while/after at 149x45 before final hardening. Run focused mutations and
touched/composing checks once; compare existing failures with 4e4b0dc4. Final
review, follow-ups and local commit.

## Verification

- Initial regressions failed on interim repaint and on the completion-metadata
  gap. Nine final composed cases cover both terminal sizes, raw source immutability,
  whole-card text/style retention, real zero, failure, cold load, seat reset,
  teardown and ReaderHandle completion with or without a changed revision.
- The live 149x45 refresh used public data and a gated next read. After actual
  overview TTL expiry, the raw source became stale while all twelve rendered card
  text/style signatures remained identical. Releasing the gate applied the fresh
  public snapshot. `/tmp/boardroom-refresh-{before,pending,after}.svg` and
  `/tmp/boardroom-refresh-live.log`; the pending image was shown to the owner.
- Mutations bypassing retention and suppressing metadata-only completion were
  caught and restored. The completion projection does not request another read.
- One touched/composing run: 161 passed, 39 failed. Every residual failure
  reproduces on unchanged 4e4b0dc4. Fast guards: 130 passed, the known TOKENS/SWORN
  slice failure also reproduced. Doc pins: 12 passed. Results are in
  `/tmp/boardroom-refresh-{composing,baseline,guards}.xml`.
- Final review Approved with no Critical/Important findings. Nine named cases
  passed; an independent identity-scope mutation failed its regression and was
  restored byte-for-byte. `/tmp/boardroom-refresh-review-{tests,mutations}.log`.
- Minor follow-up filed: measure latency if a slow unrelated read keeps the view
  busy before considering independent card publication. Current behavior follows
  the approved complete-presentation-until-completion policy; no starvation or
  lost-update case was observed.
