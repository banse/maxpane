# SURF outage correction — 2026-10-23

Base: `feature/surf-rpc-budget` at `f65236ea`. Root is the only writer.
The owner handover is preserved in the first commit of this round.
**Partial acceptance: automatic mainnet recovery (point 1) remains open.**
The owner confirmed that no official alternate source is known.

## Outcomes against the handover

| Point | Result |
| --- | --- |
| 1. Mainnet through an imd.fun outage | **Not achieved.** No new authoritative adoption source established. Full fetched channel history now reaches discovery rather than the 25-row display window. Cached channel rows supply transaction locators only; actual freshly read calldata determines candidates. Cached adoption re-establishment requires current transaction proof and all current getter gates. |
| 2. Explicit fallback | Implemented for both POOL4 market and protocol title bars. Sepolia is labeled `SEPOLIA fallback`, with `mainnet hook not proven` and a bounded reason, including `docs unreachable`. Discovery retains detailed diagnostics. |
| 3. Independent chain labels | STAKERS projects its own persisted slot's network, always displays it, and chooses its explorer from it. Unknown network has no explorer link. Network-only changes invalidate row deduplication, even with identical addresses and amounts. The market hero excludes holder counts from another or unknown chain. |
| 4. Plane host pool | Verified existing SwarmClient and SurfNftClient failover. The handover misidentified `catalog.py`: it creates evidence URLs, never HTTP requests. Its display base now imports shared `SWARM_API`. Remaining `api.imd.fun` literals under the dashboard are the host pool, comments, or evidence/display URLs. |
| 5. Offline outage proof | Covered DNS failures for all imd.fun hosts, real NFT/swarm client rotation to Railway fixture responses, official-docs DNS failure with cached docs adoption refused, explicit fallback and independent chain rendering. **Successful real mainnet recovery is not proven**, because point 1 has no evidenced source. |

Additional owner request: loading cards use the plain `◇` again. The existing
theme-bounded grayscale pulse, side-text synchronization and frame timing are
unchanged. Preview cards detect transformed missing text without hardcoding a
particular glyph.

## Source investigation and trust boundary

No new source was chosen. The existing sources remain a mined Announce-wallet
self-post, then the operator-controlled `https://pool4.imd.fun/docs` page.
The latter cannot be read during the reported DNS outage. Its recorded capture
in `tests/fixtures/surf/pool4/docs_site_page.json` provides no official alternate
host. The measured API reference and local Railway `/health` captures provide
no POOL4 deployment field or protocol-document route.

A separate read-only source check returned 102 announcement transactions,
untruncated, with no flag-passing self-post hook candidate. This does not support
the handover's assumption that a hook announcement merely aged out of the
25-row display window. It was not a live dashboard render. No route or positive
recovery fixture was invented; a third-party skill naming a hook is insufficient
authority. No new service, provider or credential was added.

Current source proof checks the requested transaction identity, mined status,
Announce sender/recipient and actual calldata. The cache's text and verdict are
not credentials. Candidate transactions are read once per hash within a channel
discovery pass. Flag filtering precedes those reads. Exact hook flags, expected
token and the existing getter fingerprint still gate adoption; current signed
provenance alone cannot adopt a broken or different-token contract. Lowercase
cached locators normalize without losing their source citation. Fresh channel
adoptions retain precedence over docs and remembered deployments.

## Validation

All tests used `.venv311/bin/python`, `env -u NO_COLOR` and isolated HOME.
External traffic is replaced by committed fixtures and injected transports.

Before production edits: **659 passed, 2 failed** (61.95s). Both failures were
old launchpad hero-class expectations, reproduced serially before edits. The
broader check later exposed a third pre-existing registration expectation for
an old outage banner; it also fails in an isolated archive of base `f65236ea`.

Final affected/composing-file run: **1,135 passed** (234.44s), covering 18 files.
The three exact
baseline node IDs excluded from this final run are:

- `tests/screens/test_surf_pool4_market_screen.py::test_exactly_one_hero_shows_in_every_mode[launchpad]`
- `tests/screens/test_surf_pool4_market_screen.py::test_exactly_one_hero_survives_every_transition_between_bodies`
- `tests/test_surf_registration.py::test_a_full_outage_renders_explicit_states_not_zeros`

Fast guards: **128 passed** (17.83s). Documentation pins: **12 passed** (18.37s).
The new provenance cases first failed as intended; after implementation the
manager/outage files passed **319 checks**. The new explorer-transition test
failed before the fix and passed after it. `git diff --check` passed.

Eight mutants were run through `scripts/mutate.py --python .venv311/bin/python`.
The unmutated test selection passed first. Every mutant was **KILLED**, with
source bytes restored and no surviving mutation:

| Mutant | Named regression |
| --- | --- |
| `boxed-loading-glyph` | `test_runtime_unknown_inner_footer_pulses_with_missing_stats` |
| `cached-channel-is-proof` | `test_cached_channel_cannot_supply_current_provenance` |
| `failed-tx-holds-adoption` | `test_a_failed_fetch_cannot_reestablish_the_cached_adoption` |
| `self-post-skips-getter-verdict` | `test_reestablished_self_post_still_needs_current_getter_gates` |
| `stakers-borrow-market-network` | `test_stakers_labels_and_links_follow_its_own_network` |
| `discovery-truncated-to-display` | `test_discovery_gets_full_history_not_the_display_window` |
| `nft-skips-railway` | `test_nft_plane_reads_rotate_on_dns_failure` |
| `stakers-retain-old-explorer` | `test_staker_chain_change_rebuilds_links_without_row_changes` |

Agency final review: 53 focused checks passed; it found the explorer-link
invalidation defect and the external source gap. Scoped re-review independently
passed the transition test and marked the Critical finding addressed. Its final
verdict remains **0 Critical, 1 Important**, because acceptance point 1 is still
unfulfilled. No all-green acceptance or full-suite claim is made.

Local test logs are under `/private/tmp/maxpane-outage-*.log`; the source and
regression tests are committed. IMDB completion recorded `none`: this round
adds no new durable protocol lesson beyond the already documented provenance
and host-pool rules.

## Deviations and unresolved work

- Point 1 and its successful-outage acceptance proof remain blocked on an
  authoritative source. Both the Agency architect and final reviewer identified
  this gap; it is not a successful adoption fix.
- The existing failed-transaction `ADOPTED` hold was removed to meet the
  handover's explicit current-cycle proof rule. A provenance-read outage can
  therefore cause a clearly labeled Sepolia fallback. Historical observations
  remain cached with their own chain labels.
- The final review found the network-only explorer-link invalidation bug. One
  production fix wave adds explorer identity to the row cache key, backed by a
  failing-then-passing composited MAINNET → SEPOLIA → unknown transition test.
- No geometry/pin change, full-suite run, live dashboard render, Claude
  verification, push, merge, tag or version bump. The handover explicitly leaves
  the live render and full-suite verification outside this round.
- Unrelated untracked files were preserved and excluded from staging.
