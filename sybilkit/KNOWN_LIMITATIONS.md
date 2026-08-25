# Known limitations — sybilkit 0.1.1

Dated 2026-08-25. These are measured defects in the released rules, published here because 0.1.1 is
installable from PyPI and its output has been used to publish verdicts about named wallets.

Full audit, evidence and reproduction: <https://github.com/banse/clustermap/tree/main/audit>

## 1. The rules link honest wallets at a high rate

On a synthetic population built to contain **no operators at all** — observed join pace, an amount
prior drawn from ENS-named wallets, the measured funder mix and gas diversity — the 0.1.1 rules flag
**45.8%** of it (mean of 5 seeds, 5,578–5,802 of 12,349). Every wallet linked there is a false positive
by construction.

The dominant causes, all measurable in `signals/`:

- round-amount windows have no width bound, so one common amount can weld a whole day of joiners into
  a single component;
- "odd amount" is anything not a multiple of 0.01 ETH, so amounts like 0.051 reach across the entire
  population;
- the protocol minimum is exempt from the amount rules but not from sequence or cadence, so a crowd
  rushing in at the minimum after an announcement is read as a farm;
- the shared-funder hub fires at two members against a hard-coded 12-address CEX list, which does not
  cover the exchange hot wallets actually present in a real population (184 exchange-scale funders were
  found in the audited one);
- the noisy-OR confidence has a floor above the documented 0.5 threshold, so the threshold never bites.

## 2. The funding family cannot find what the behavioural rules did not already propose

`signals/funding.py` folds funding evidence **onto** tier-A components: an edge is drawn only when
funder and funded already share a component. This is deliberate and well-tested — it is what stops a
family's main wallet from convicting its owner (`tests/test_signals_funding.py`).

The cost is structural. In the audited population a single operator relayed one ≈99 ETH lump serially
through 419 wallets (15.6% of all points); **81 were flagged**. Resolving the missing enrichment does
not help: with a first funder for all 19,522 contributors and a transaction fingerprint for all 28,353
deposits, the 0.1.1 output does not change by a single wallet — same 263 clusters, same 11,573 flagged,
ring still 81/419. Corroboration cannot build a component, so complete data buys nothing here.

## 3. The benchmark's precision is an artefact

`bench.py` scores the 220 labelled wallets in isolation, so a control can never be pulled into a
≥5-member component by the other 19,300 wallets. Scored inside a full population, 30 of the 60
"controls" are flagged. The controls were sampled as non-audited wallets and several are farm members,
so they are not verified-honest either. Precision 1.0 from this harness should not be read as evidence
of precision.

## What is *not* in dispute

Recall on undisputed farm waves is high and was reproduced independently: all eleven audited waves are
recovered at ≥99.4%. The library's thesis — score clusters on multiple evidence families, never convict
on one — is sound; these are implementation defects, not a refutation of the approach.

## Status

No fix is released. A prototype rule set measured against the same population improves both error
directions at once (ENS-named wallets flagged 360 → 28, ring recovered 397/419, false linking on the
null population 0.1%), but it re-implements tier A outside the library, reverses the property described
in §2, and **every one of its constants was calibrated on a single population**. It is not a release
candidate and should not be treated as one.

If you are using 0.1.1 to make decisions about real wallets, treat a cluster as a question rather than a
verdict, and read the audit's limitations section before citing any number from it.
