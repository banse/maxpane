# PORTFOLIO follow-ups

The delivered phase is an offline Textual mock. Live integration is separate:

- Reuse the complete SWARM TOKENS catalogue and enrichment; read wallet token
  balances with actual token decimals and explicit discovery/read coverage.
- Resolve wallet-earned launch allocations, frozen reward leaves and onchain
  claimed/unlock state. Current online agents must not determine entitlement.
- Supply verified remaining-position USD cost basis before enabling live P/L.
  Missing cost or current valuation must remain unavailable. Decide the live
  acquisition/accounting policy before implementing it.
- Preserve shared market caching and per-wallet invalidation; retain visible
  stale/as-of and partial-coverage states when replacing the mock manager.

Verification environment: color assertions require `NO_COLOR` to be unset.
The application continues to respect the user's normal color preference.

Final scoped review: approved on 2026-10-10, no findings. The reviewer ran 47
Portfolio tests and two address checks, and killed a mutation that incorrectly
added claim value to P/L; the file was restored byte for byte.
