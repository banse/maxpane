# Sworn implementation evidence

Approved layout: proposal 1 as main Explorer; proposal 3 in the existing-style
detail popup. Implementation uses the shared dashboard lifecycle and reader,
four native hero cards, a bounded card page, selected artwork and claimant facts.

## Live observation

The public site's `imd-deployment.json` names Ethereum chain 1, source commit
`c4ff3238390fc51962fb67e86affc20cf418126e`, and these bindings:

- Registry: `0x0da2679000ea5380d1361cc3cca7d4e8c881f766`
- Renderer: `0x3039eaf3b979759c77a2a3fc62850f9534162c3b`
- Composer: `0xf564dd76bd081554170c5e0b78144abfb39f7061`

The client verifies chain and helper getters before reading selected data at
the same block. It does not use older addresses from DEPLOYMENTS.md or a local
sworn-site checkout. All calls are public reads; no wallet signing exists.

At block **26,256,950**, supply was **10**, selected token **10**, mint block
**26,256,592**. The token's accepted trait/community lists were empty. Its dark
unfilled SVG is therefore the observed artwork, not a failed loading fallback.

The live reader-to-UI run at **149×45** took **0.619 seconds**, using **three
HTTP batches**. Recorded thread IDs differed: UI `8454758784`, reader
`6173241344`. An independent manager-only cold read took 0.684 seconds.
These are individual observations, not a latency guarantee. The manager has a
24-second refresh deadline; the shared reader coalesces overlap and skips elapsed
poll deadlines. Only the selected tokenURI is read, not the whole collection.

Main/popup live SVG exports and evidence were generated under
`/private/tmp/maxpane-sworn-preview/`. Headless Playwright screenshots preserve
the exported terminal's whitespace and typography. They were shown before the
layout hardening pass. Native terminal pixels are not claimed as visually tested.

## Verification

- Data: 28 offline tests; deployment, malformed metadata/cache, claimant vs
  holder, cancellation, retained observation time, same-art reuse and overlap.
- Artwork: 17 tests on Python 3.11 and 3.13; actual token SVG, explicitly labeled
  official full-house illustration, fallback color/geometry, TGP chunking,
  replacement, stable placement and owned-image deletion.
- UI: 20 composited/pilot tests; main and popup, clicks, lookup, old-response
  rejection, checksummed address normalization, responsive boundaries, short
  viewport scrolling, evidence and metadata detail.
- Integrated touched/composing run: 308 passed initially; three test/registration
  issues corrected and their checks passed. One existing SURF banner assertion
  reproduced at the unchanged baseline; see the follow-ups file.
- Guard checks: 127 passed initially; two new-registration assumptions corrected
  and both named checks passed. Address sweep: two Sworn cases passed. Dashboard
  PANELS agreement passed. Additional FWA mounted guards: two passed.
- Decoder/identity and graphics mutations were killed and restored; no full
  repository suite was run. `uv build --wheel` produced
  `maxpane-0.9.3-py3-none-any.whl`.

Final independent review: **Approved, no findings**. The reviewer independently
killed the selection-generation mutation and restored it byte-for-byte. No
review fix wave was required. Native terminal visual verification remains the
explicit follow-up above.
