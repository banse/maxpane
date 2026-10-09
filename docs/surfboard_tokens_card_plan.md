# TOKENS hub card

Approved owner request: rename SWARM TOKENS to TOKENS; use the rack's native 3×3 digits,
LAUNCHED inset title, and `x new` inset footer. Green means the same active launch news
as the SWARM header: validated detected events aged 0 ≤ age < 3600 seconds. This is
independent of the dashboard's new/24h metric and the detector's longer FIRED TTL.

Use the retained SwarmTokensManager catalogue and its existing production-chain/live/token
identity selection. The hub offers catalogue reads only; market, price-history and trade
reads remain dashboard-owned. Cold data stays unavailable, incomplete counts carry ≥,
and retained stale counts disclose their catalogue state and successful clock in card detail.
The route, outer meter and rack geometry stay as they are.

Tier 2: shared header predicate and two views; under 150 production lines. One implementer
owns all changes, in dependency order: shared news predicate and catalogue-only summary;
manager/card projection; native digits rendering. Existing fixtures supply offline tests.
No new payload contract keys, endpoints or pins. Verify catalogue/dashboard count agreement,
news expiry/future/malformed boundaries, no market reads from hub, rendering and navigation.
Show live 149×45 render before hardening; one final review, focused mutation checks, touched
and composing tests plus fast guards; local commit only.
