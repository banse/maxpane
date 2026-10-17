# NFT details popup and repository summary

Status: implementation authorized by the owner, 2026-10-17. Tier 2: one new
panel/modal and one flat payload key. Expected production change: under 1,000 lines.

## User-visible result

The NFT Explorer keeps its heroes, filters, catalogue and selected identity.
The right column contains two panels:

1. **COLLECTION DETAIL**: name, chain/standard, contract or project, supply and
   observed holder/custody figures. These are the existing facts above MINT ROUTES.
2. **SUMMARY (github README.md)**: a short, deterministic excerpt from the selected
   collection/project's linked GitHub repository, with its source link. It scrolls
   independently when necessary and is clearly repository prose, not verified mint
   conditions or wallet eligibility.

Every real catalogue row, including IN THE MAKING, ends with the same `»` affordance
as AGENT RECORD. Clicking it or pressing Enter opens that row's snapshot popup.
Highlighting a row selects its basics and README without opening the popup. Address
and copy clicks keep their existing actions and must not also open the popup.
An empty-result placeholder has no popup action.

The popup reuses `RecordDetailScreen`: centered accent frame, title and top-right
close control, focused scrolling content, pinned Space/Esc close hint. It contains
all existing detail content from **MINT ROUTES** onward: mint/IDMD conditions,
reported terms, utility, related tokens, Swarm sources, chain/review sources,
observations and coverage. No existing evidence is dropped. The popup is a deep
copied snapshot and performs no reads itself. On close, table selection/focus is
restored. Existing address explorer/copy behavior remains available inside it.

## Decision and alternatives

Use the existing popup base and split the current detail renderer into basic and
extended sections. A second bespoke modal would duplicate focus, closing and style
behavior; retaining a huge detail pane would not meet the requested layout.

Keep README data in a small selected-repository cache owned by the NFT manager.
This avoids catalogue-wide fetches and persistent evidence-schema changes; the
trade-off is that restarting MaxPane re-reads the README. Persisting README on every
row would survive restarts but couples untrusted repository prose to chain evidence
and duplicates content across collections from the same repository.

## Frozen payload and ownership boundary

Add `nft_readme` to `NFT_KEYS`, and this widget signature:

```python
'NftSummary': ('nft_readme',)
```

`nft_readme` is `None` when nothing is selected, otherwise a primitive dictionary:

```python
{
    'identity': str,             # selected collection/project ID
    'repository_url': str | None,
    'readme_url': str | None,    # validated source document link
    'revision': str | None,      # requested pinned commit; None = default branch
    'text': str | None,          # deterministic source excerpt, never generated claims
    'observed_at': float | None, # successful observation, never a projection clock
    'state': str,               # pending / ok / missing / unavailable
}
```

`project_snapshot` passes this dictionary only when its identity matches the actual
projected selection, including filter fallback. It never attaches another row's
summary. README fields do not enter `NFT_ROW_FIELDS`. Retained successful text
stays visible during retries; unavailable/pending source words are not painted.
Missing source content uses a neutral dash; no linked repository may be stated
explicitly. Domain and third-party prose are not filtered for status words.

Manager `select(identity)` remains synchronous. Selection can offer a separate
owned README task only in active view `NFT EXPLORER`. `get_readme()` returns the
selected cached payload without I/O or catalogue projection. `get_snapshot()`
includes the same payload. The shared loading footer includes active README work.

## Source and lifecycle constraints

- Choose one valid linked GitHub repository deterministically in source order.
  Use its explicit commit when valid; reject malformed supplied revisions. When
  no revision is supplied, read root `README.md` from GitHub's default branch;
  never guess `main`/`master`. Public GitHub Contents README reads need
  no authentication. A blob SHA is not a commit SHA and must not be labelled one.
  Source: [GitHub repository contents API](https://docs.github.com/en/rest/repos/contents#get-repository-content).
- Normalize and allowlist GitHub repository identities before constructing URLs.
  Never fetch arbitrary repository URLs, README links, images or embedded assets.
  Keep existing response/deadline limits and add a small bounded excerpt/cache.
  Retain source attribution and original successful observation time.
- Summary extraction is local and deterministic: retain useful introductory prose,
  omit badges/image-only lines, code fences and navigation noise; flatten Markdown
  decoration, preserve meaning, and bound the excerpt. No LLM or paid service.
- Cache by repository plus requested revision, with bounded entries and retry/TTL
  policy. Selecting another NFT from the same repo reuses its excerpt while binding
  the payload to the newly selected identity.
- Start the selected README promptly; never wait for the existing chain cycle or
  the next 30-second poll. Selection changes cancel and drain the previous owned
  task before replacement. Late A completions cannot paint B. Suspend/leave and
  close cancel and drain README work just as other NFT reads do.
- BOARDROOM proof-only cycles and passive snapshots never start README reads.
  No catalogue fanout. Reopening NFT displays cached data immediately; only its
  visible refresh lifecycle can revalidate due content.
- A fast README completion must repaint while a slower chain cycle remains active.
  The screen may compare `get_readme()` in its existing loading tick and update only
  the summary panel; no additional timer or full catalogue projection is needed.
- Third-party text uses the existing sanitization and address-prose helpers.
  Evidence addresses retain known chain links and independent copy icons; README
  prose can discuss multiple chains, so its addresses remain copyable without a
  guessed explorer link.

## Acceptance evidence

Verify popup contents and all open/close paths, selected-summary identity after
filtering, prompt independent completion, cached revisit, hidden-view cancellation,
no BOARDROOM reads and safe source decoding using offline fixtures. Inspect the
actual compositor, including trailing icons, address clicks, table geometry and
independent scroll regions. Show a fresh keyless live render at 149×45 before final
layout hardening/review; measure changed table/layout boundaries rather than
assuming the previous 146×33 pin still applies.
