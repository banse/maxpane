# WORK IN PROGRESS follow-ups

The initial view deliberately covers the newest 100 jobs and 100 workflows,
plus up to 24 job details. It does not claim a complete active-work inventory.
Broader pagination is future scope and should keep explicit coverage and
bounded request costs.

No estimated completion percentage is shown; step states and timestamps are
the available evidence.

Final review: four Important findings were fixed in one wave and all four
were verified addressed. No Critical or Important findings remain. The fixes
cover conservative read-start freshness, workflow search/filter/default
selection, required detail fields, and the page-count contract. No Minor
findings were raised.

## Boardroom card replacement (2026-10-13)

The WORK IN PROGRESS card replaces PORTFOLIO and reuses the same bounded reader.
Final review approved it with no findings. A fresh keyless 149×45 render was shown;
the 144×37 rack boundary remains unchanged. Actual-app navigation preserves an
in-flight read between the two views and cancels it on leaving both.

Unrelated existing issue: `PortfolioHero.update_data()` calls a missing
`render_box` method in `widgets/portfolio/__init__.py:53`. The Portfolio screen
file has nine failing tests both before this change (HEAD d67d83cb, isolated
checkout) and after it; 15 tests pass in both runs. Track this separately from
the replacement card. The old card-opening test now opens the retained Portfolio
screen directly, preserving that screen's return-navigation coverage.
