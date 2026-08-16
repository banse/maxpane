# Live capture manifest

One row per bundle written by `scripts/capture_curator_state.py`, appended
never rewritten. Decoded from the bundle at write time; the bundle itself is
the authority. `hourTotal` and `needed` are ETH, `lastActive` is
`hour/total`.

| bundle | captured (UTC) | label | hour | hourTotal | lastActive | earlyBps | needed | timeLeft | settled | contributors | volume | logs | err |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `20260816T225006Z_grace-late.json` | 2026-08-16T22:50:06Z | grace-late | 2 | 1,708.62 | 2/1,708.62 | 18,812 | 0.0000 | 528 | false | 794 | 12,547.77 | 2077 | 0 |
