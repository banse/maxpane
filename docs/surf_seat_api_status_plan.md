# Offline seat status labels

Approved user request, 2026-10-14. Tier 2 because the change extends the
shared seat-summary contract and affects both the boardroom and AGENT board.
The production change is expected to be far below 1,000 lines: one session
implements it, with no package reviews and one final review.

## Required behavior

- When existing worker-presence logic identifies a seat as offline, the
  boardroom AGENT inner-box subtitle and AGENT board SEAT subtitle display
  that seat's `/seats/{id}.status`, for example `revoked`.
- Missing, blank, or non-string API status falls back to `offline`.
- Preserve current online/working labels, slot counts, unknown/loading
  behavior, and offline red borders and border text. The boardroom outer
  `OFF` label and activity meter remain unchanged.
- A status label is descriptive metadata, never evidence of worker presence.
  Incomplete or unread worker data must not become a confirmed offline seat.
- Read only existing seat-detail caches. Do not add endpoints, background
  readers, polling, or eager fetches for boardroom seats.

## Contract and source ownership

Append `api_status: str | None` to `SWARM_SEAT_SUMMARY_FIELDS` and to
`SURF_AGENT_HERO_FIELDS['seat']`. Normalize the source `status` with the existing
seat string-cleaning convention; retain a nonblank display string, otherwise
`None`. Keep the API status separate from read state and worker live state.

`seat_summary_from_seat()` is the decoding boundary. The AGENT hero projects
the selected summary's status only while that selected detail is available,
including permitted last-good data. Pending, missing, and mismatched detail
must not borrow another seat's label.

For the boardroom, the manager looks up the assigned token's existing
`SLOT_SWARM_SEAT` cache entry and passes its status with that seat's facts.
The card projection places the status in the existing `secondary` field only
when the established live state is offline; otherwise it retains slot text.
No top-level dashboard key or boardroom-card contract field is needed.

Widgets display this value as safe plain text through their existing text
and clipping helpers. Offline coloring must use actual presence state, not
comparison with the literal subtitle `offline`, so `revoked` remains red.

## Dependency order and ownership

1. **Planner:** owns this document only; no code, tests, or agents.
2. **Session implementer:** owns the contract, decoder, manager handoff, pure
   projections, both widgets, and their focused tests. Freeze the fields
   above, add failing tests, then carry the status through the existing
   caches and rendering paths. These changes are sequential because each
   stage consumes the preceding contract; no parallel edit package is useful.
3. **Session implementer:** show both real, keyless renders at 149×45 before
   layout/document hardening or review. Preserve layout pins unless actual
   render evidence requires a change. Run the affected/composing test files,
   guards and doc pins, and mutation checks; update relevant followups.
4. **Final reviewer:** reviews the whole task once. The session handles one
   fix wave and requests a scoped re-review only if production code changes.
   Preserve unrelated work and commit locally; no push is requested.

## Verification and risks

- Decoder and contract tests: `revoked`, another valid status, missing/null,
  blank and malformed input; no input mutation or hardcoded seat/status.
- Projection/manager tests: exact cache-to-token matching for multiple seats;
  no detail and mismatched detail; existing cache recovery; unchanged fetch
  calls; worker presence remains authoritative despite API metadata.
- Composited widget tests: both offline cards show `revoked` in red; absent
  status shows red `offline`; online/working labels and colors remain;
  boardroom footer remains `OFF`; unknown presence does not imply offline.
- Check a long or markup-shaped source value through existing clipping/plain
  text rendering. A status may need clipping at narrow widths, but must not
  expand the inset or inject styling.
- Mutation proof must kill dropping status during decoding/forwarding,
  forcing the generic offline subtitle, and tying red styling to that text.
  Use inverse restoration; never revert another contributor's work.
- Tests stay offline with fixture/injected data. Live verification is a
  separate public read. Run only affected/composing files and fast guards,
  not the full repository suite. Record actual results in the commit.

## Followups

Cached status is intentionally shown only after that seat's detail has been read;
unknown metadata retains `offline`.

- Existing `test_loading_repaints_completed_cache_without_offering_more_reads`
  raced its automatic age timer under four-worker worksteal: the loader had already
  been replaced before the assertion. Its isolated serial rerun passed. Make timer
  setup deterministic when that test is next changed; no production change is needed.
