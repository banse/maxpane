# Animated IMD card loading

Owner request (2026-10-23): use the IMD outline diamond instead of missing
card values while loading, including single `-`, double `--` and `—`.

Tier 2 because the card renderer is shared. The change is presentation-only:
no new reader, requests, cache state, data contract, polling or layout pin.

## Design and ownership

The session owns all implementation files. The Agency Software Architect checked
the boundaries; one final review covers the whole change (under 1,000 production
lines). No separate task reviews.

1. Add a shared loading card base/helper in `widgets/card_inner.py`. Pulse a
   single `◇` using the existing theme accent. Preserve card geometry and retained
   values, including zero. Replace only explicit missing value fields; never
   rewrite full rendered text, third-party prose, symbols or linked addresses.
2. Drive participating visible cards from `DashboardScreen`'s existing 0.2s
   local loading tick. No timer per card. Stop on idle/suspend, and avoid pulse
   redraws when a card has no missing values.
3. Connect the BOARDROOM and shared Surf hero renderers, including AGENT's custom
   STATUS and structured liquidity rows. Empty seat inputs remain unchanged.
   BOARDROOM additionally respects each card's existing loading status.
4. Add offline composited tests, show a real keyless 149×45 render, then run
   affected/composing tests and guards, obtain one review and commit locally.

The animation means the visible view is reading and the field has no value yet.
Other than BOARDROOM, individual hero fields have no pending-read contract, so
this does not claim that a specific source request is in flight. Once the view
stops reading, unresolved values return to their existing dash presentation.

## Validation

Cover placeholder spellings, multiple pulse colors without geometry changes,
cached values/zero, completion/failure, switching and suspending views, literal
prose and address actions, empty seats, and no additional network work. Verify
actual composite output, not only helper strings. Test independent theme colors.
No full test suite or data-loading changes are part of this request.

## Execution evidence

- Added the regression first: the missing-value pulse test failed before the
  implementation (no card pulse API). The implementation uses
  `set_card_loading` to avoid overriding Textual's existing `set_loading` API.
- A real keyless NFT reader cold start was rendered at 149×45, with an isolated
  `/private/tmp/maxpane-card-loading/nft-cache.json`. Its compositor text and two
  pulse frames are in `live-loading.txt`, `live-loading.svg`, and `live-pulse.svg`
  in that directory. The terminal's cell positions were also inspected visually.
- After the review fixes, 364 affected widget/lifecycle/composing tests passed
  with `NO_COLOR` unset (61.74s); 128 non-mounted guards and 12 doc-pin checks
  passed. An initial run with the environment's
  `NO_COLOR` enabled failed 31 existing color assertions; the color-enabled run
  resolves those environment failures.
- The final review identified two edge cases, both fixed in one wave: preserve
  cached literal dash-only news posts, and animate RUNTIME's standalone missing
  inner-footer value. The seven new regressions exposed both defects before the
  fixes and pass afterward. Review artifacts are in
  `/private/tmp/maxpane-card-loading/review.md` and `rereview.md`.
- Scoped re-review: Approved, both findings addressed. Reverting each fix in a
  temporary mutation failed its named regression; all source bytes were restored.
  The original disabled-loading production mutant was also killed.
- The scope remains the shared Surf/BOARDROOM rack cards and explicit missing
  value fields. Tables, free-form prose, formatted dates and existing footer
  loading indicators keep their current presentation.
