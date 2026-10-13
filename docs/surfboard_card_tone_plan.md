# Boardroom card tones and price reads

Approved scope: restore the centered IMD BOARDROOM heading to the former muted title
color; center PROTOCOL and empty-seat outer footers; use neutral PROTOCOL inset ink;
rename ONCHAIN FEED and SWARM BUILDS; use white active feed inset ink; color POOL4's
inset green/orange/neutral for higher/lower/unchanged consecutive price reads.

Implementation (one owner, this session; under 1,000 production lines):

1. Add focused compositor regressions and manager read-sequence tests.
2. Update rack rendering and both copies of title CSS. Keep dimensions and navigation.
3. Track POOL4's previous valid USD price in SurfManager, keyed by network/pool and
   confirmed pool/market read clocks. Redraws retain direction; new equal reads clear it.
   Missing/failed/stale reads stay neutral and do not advance the comparison baseline.
   The pure card projection receives direction through an optional argument, without
   new card contract fields or persisted cache slots. Keep 24h data in card detail only.
4. Show a keyless live render at 149×45, then verify existing layout boundaries, run
   affected/composing tests and fast guards, and record mutation evidence.
5. Update the hub behavior notes and followups; obtain one final review and commit.

Risk checks: source clocks versus redraws, same-price success, missing/failing reads,
network/pool changes, and style reset when an empty seat becomes assigned.
