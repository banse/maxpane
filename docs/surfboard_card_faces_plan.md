# SURFBOARD, LEADERBOARD and LAUNCHPAD faces

Owner-approved revision, Tier 2 only because the existing composing tests and
fixtures cross six files. Under 200 production lines; session owns all packages
sequentially. No new endpoints, payload fields, navigation keys or layout pins.

1. Project existing data: SURFBOARD selects the newest successful classified
   `self` announcement with readable text, never an `answer`. Count unique
   `reply` + `answer` transactions from the last 24h across the cached channel.
   Green/fresh text means that announcement is aged 0 <= age < 24h, independent
   of reply activity and signal state. Preserve source clocks in detail.
   LEADERBOARD shows rank 1 from the canonical board rows, its NFT id and exact
   accepted count. Keep the existing fleet PASS meter. LAUNCHPAD uses coin count
   and last-24h launches, green only when that count is positive.
2. Render TOP AGENT and COINS using existing native digits. Keep exact accepted
   counts in detail; remove grouping if needed, and shorten `accepted jobs` to
   `accepted` on narrow cards, with compact notation for extreme totals. Reply
   footers can drop `new` at the minimum width to retain the full count. At the owner's 149x45 size current values fit the full
   wording. SURFBOARD uses LATEST POST and three left-aligned prose lines, `...`
   on truncation. Reuse safe text/address fitting helpers; old text matches the
   empty-slot color, fresh text matches native digit color. Short posts are not
   padded with invented content.
3. Offline regressions for announcement/reply provenance, expiry, canonical rank,
   empty/unavailable counts, composited text/colors/digits, Unicode and address
   wrapping. Show real 149x45 render before boundary checks and review. Run
   touched/composing files and fast guards; one final review with mutation proof,
   scoped fixes only, local commit. Record residuals in existing followups.
