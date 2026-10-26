# Wallet / Swarm live follow-ups

2026-10-26. Scope: direct wallet requests and explicitly attributed artifacts.

## Source limitations retained in the UI

- Latest 100 public payer requests are not complete lifetime discovery. Previously
  confirmed artifacts remain in the wallet catalogue. Contract-owned downstream
  orders are not silently attributed to their deploying EOA.
- Base and RH deployments/payments can use existing state clients; utility needs
  an individually reviewed application rule and established log capability.
  Only the Ethereum BurnTracker refresh rule is installed in this change.
- A site-to-contract link requires explicit binding evidence. Objective text and
  overlapping wallet ownership are insufficient; the current live site remains
  unlinked with unknown onchain usage.
- Refund history is not available from the paid-by payload. Paid amounts require
  receipts; refunds and net paid remain unknown. No current quote fills history.
- Schedule discovery is bounded to four pages per cycle. Larger catalogues
  remain visibly partial until later cycles resume the saved cursor and finish.

## Review record

All task findings were fixed and independently rechecked:

- UI: partial amount qualifiers survive hero rendering; unread initial data no
  longer clears the saved artifact selection.
- Data: dependent launch joins progress under the 48-read budget; oracle.group
  remains one request; nested cache values are validated; schedules resume after
  400 rows independently for each wallet.
- Evidence: malformed matching events invalidate the window; interruption rotates
  the next payment/deployment work item instead of starving later evidence.
- Integration address sweep: RECORD fits raw objective text through the shared
  address-aware fitter, preserving copy icons without inferring its chain.

## Existing repository failures reproduced on the baseline

An isolated `git archive dc94e8e9` reproduced all 13 unrelated failures observed
in the broader checks: two Boardroom tests expect Tab to reach SURF although
SWORN now follows Boardroom; nine Portfolio tests fail on the existing missing
`PortfolioHero.render_box` / coverage rendering; one SWARM TOKENS CSS agreement
test includes the subsequent SWORN stylesheet block; one SURF mount test still
expects generated outage notices that the existing display override suppresses. Evidence is retained at
`/tmp/maxpane-wallet-baseline-results.txt`. These are outside this wallet change.

Final whole-change review: Approved after its single fix wave and scoped
re-review. Duplicate cached IDs now reject the wallet. Failed usage reads retain
the prior observation only for the same confirmed runtime, with its original
source clock. Unsupported or invalidated rules clear that usage. The ONCHAIN
panel title displays its own UTC observation time. Onchain capability rows also
supply validated chain-specific payment asset/recipient targets.

The final cold live read (05:42 UTC, 31.43 seconds) confirmed the same five orders,
two artifacts and 2.5 IMD paid. The latest complete usage window was unavailable;
the cold view correctly showed NO DATA. The previously observed refresh receipt
was read separately and the production decoder still decoded kind 2 correctly.
This does not certify a complete newer window; same-wallet warm snapshots retain
the last verified window and its time. No universal utility coverage is claimed.
