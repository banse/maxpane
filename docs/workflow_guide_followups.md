# Workflow guide verification and follow-ups

Implemented 2026-10-18 from the approved diagram-first design with a collapsible
topic index. Entry is the boardroom's WORKFLOWS title link or `g`; default is
Contracts-only launch. Ten topics and 79 selectable nodes use the supplied
2026-10-18 document. Numeric examples and limits are dated documentation.

## Verified behavior

- Local catalogue loads through the common guarded lifecycle. Static screens
  opt out of periodic polling; existing dashboards retain the default timer.
- Boardroom acquisition suspends while the guide is open. Escape restores the
  same boardroom; reopening retains topic, node and index state.
- All 79 real nodes are mouse reachable. Keyboard selection, source popup,
  literal prose, scrolling, missing payload and invalid saved state are tested.
- Genuine-source previews inspected in Matrix at 149×45: contracts, site,
  expanded index and source popup. Exported SVG needs `xml:space="preserve"`
  when rasterized by librsvg; otherwise leading spaces are lost in the image.
- Each node has a native inset frame, semantic role header and full-card click
  target; all six original dated facts remain in the source popup. Explicit routing preserves parallel stages,
  retries, joins and failure branches. Keyboard selection reveals offscreen nodes.
- Capacity-card revision: six native heroes show selected-node input capacity,
  rendered envelope, body size, larger/integrated alternatives and cost. Word
  counts are estimates at six characters per word, with authoritative exact
  character caps. Companion source fixture and explicit profiles cover all nodes.
- Measured guide layout: 148×44, both CSS paths, index open/closed, all topics.
  Width 147 scrolls one column; CONTRACTS at height 43 scrolls one diagram row.
  Its details hide at 52 rows and return at 53. On short views, the graph
  scrolls internally while SOURCE DETAILS stays above it; details remain in the popup.
  Narrow/short terminals retain scroll access. The app-wide pin is unchanged.
- Mutations caught loss of snapshot isolation, retained selection, correct
  source-node routing and the no-poll gate. Width and height pin mutations
  failed on both sides, then were restored byte-for-byte.

## Known limits and existing failures

- The catalogue is a packaged historical snapshot. Updating the source requires
  updating its curated text and fixture; there is no live document sync.
- References in the source are attribution, not independently verified data.
  The source's contradictions and proposed recovery are explicitly retained.
- The existing registration test
  `tests/test_surf_registration.py::test_a_full_outage_renders_explicit_states_not_zeros`
  still expects the removed outage banner. The owner previously requested its
  removal. Registration run: 79 passed, this one pre-existing failure; the
  banner was not restored. Update that old assertion when its area is touched.

Initial guide verification: 195 scoped tests passed under worksteal; 128 fast guards
passed. The independent final review approved with no findings. Its additional
title-click routing mutation was caught by the integration test and restored.
No full suite was run.

Framed-diagram revision: 147 scoped tests passed under isolated HOME/worksteal;
128 fast guards passed. All ten diagrams fit with the index open and closed,
and all 79 source labels are checked in composed output. Both directions of
each layout pin, loss of selected-card scrolling and removal of one parallel
audit inlet were mutation-tested: all six mutants were caught and restored.
The final review found one reversed schedule edge. The fix makes exhausted and
paused states lead to the topup action; 87 touched/composing tests passed after
the change. The scoped re-review approved, with a mutation proving the new
composited assertion rejects the old direction. No residual findings remain.
No full suite was run for this revision.

Reading-order revision: source row and optional text panels now precede the
diagram; the topic strip follows it. Actual-source purchase and contracts
previews were shown at 149×45 before hardening. All layout thresholds remain
unchanged. 132 touched/composing tests, 128 fast guards and 12 documentation
checks passed. Independent final review approved without findings; moving
the topic strip back above the diagram failed the new composed-order test,
and the mutation was restored byte-for-byte. No full suite was run.

Capacity-card revision: 174 scoped tests passed under isolated HOME/worksteal;
128 fast guards passed. All 79 nodes' card labels, rows, captions, footers and
approximate values are checked in composited output. Nine mutations were
caught and restored: incorrect step/company capacities, a plane node exposed
as editable, both directions of the graph/detail height boundaries, and
always-show/always-hide lower panels. Independent final review approved with
no findings. Its additional popup-sanitization mutation was caught and restored.
No full suite was run for this revision.
