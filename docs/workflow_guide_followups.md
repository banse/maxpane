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
- Measured guide layout: 148×43, both CSS paths, index open/closed, all topics.
  Width 147 scrolls one column; STEP SHAPES at height 42 scrolls one row.
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

Final verification: 195 scoped tests passed under worksteal; 128 fast guards
passed. The independent final review approved with no findings. Its additional
title-click routing mutation was caught by the integration test and restored.
No full suite was run.
