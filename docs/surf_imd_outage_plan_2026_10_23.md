# SURF outage correction plan

Tier 2; owner handover is `surf_imd_outage_handover_2026_10_23.md`.
One writer: root. Agency architect consulted read-only; one final scoped review.
No push, tag, version change, or full suite. Use `.venv311` and isolated test HOME.

## Findings and limits

- The handover's mainnet source is not yet established. Existing captures name
  only the official docs page. The complete current public announcement history
  returned 102 transactions, untruncated, with no flag-passing self-post hook.
  This was a read-only source check, not the excluded live dashboard render.
- No measured Railway route in the local API captures names the hook. Do not
  invent a route/fixture, trust a cached address, or accept fingerprint alone.
  The owner has been asked for an official alternate source or signed post.
  Owner response: no alternate source is known. Point 1 remains explicitly open.
- `catalog.py` makes evidence links, not HTTP requests. NFT reads already use
  `SWARM_API_HOSTS`; consolidate the display base and prove DNS failover offline.
- STAKERS loses its own slot's network during projection and is labeled from
  the market slot. It must keep its own network, including explorer links.
- A failed cached self-post re-read currently returns ADOPTED. Remove that
  behavior and rerun the full existing candidate gates after successful proof.

## Ordered work (all root-owned)

1. Restore the plain diamond in `widgets/card_inner.py`; keep color/timing.
   Update existing composited marker tests; preserve all unrelated files.
2. Freeze `pool4_stakers_network` in `data/surf_models.py`; project it from the
   staker slot, dispatch it in `screens/surf.py`, and render it explicitly in
   `widgets/surf/pool4u_stakers.py`. Keep unknown networks unknown. Prevent the
   market hero merging holder counts from a different chain into vault data.
3. In `data/surf_manager.py`, reprove cached transaction locators and rerun
   fingerprint gates. Cached channel rows also require a fresh transaction;
   only its actual calldata enters candidate discovery. Discovery must use the full fetched channel history,
   not the 25-row presentation window. Failed adoption receives a bounded,
   explicit reason in the existing discovery detail; the title names testnet
   fallback and why mainnet could not be proven. No layout/geometry changes.
4. Consolidate catalog display URLs and add a fixture transport that makes all
   `imd.fun` hosts fail DNS while existing Railway endpoints return fixtures.
5. Implement a new mainnet source only if authoritative evidence is obtained.
   Existing self-post and docs gates, stronger-source precedence and per-cycle
   proof remain mandatory. Otherwise report acceptance point 1 as unresolved.

## Verification

Baseline: 659 passed, two existing launchpad-hero screen assertions failed;
both failures reproduced serially before production edits. New targeted tests
must fail before implementation. Run touched/composing files, guards and doc
pins, plus named mutations for plain glyph, independent network, failed proof
and DNS failover. Final report states all results and any unmet requirement.
The handover excludes the live dashboard/Claude verification run and full suite.
