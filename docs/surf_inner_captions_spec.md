# Surf WORK and ORACLES inner captions

Status: implemented and approved; live verification and scoped checks passed.

## Approved result

In the native WORK / WIP (`w`) and ORACLES (`Ctrl+o`) views, move every hero
card's existing descriptive outer-bottom caption into the bottom line of its
inner box. Preserve the exact words and render each caption with the same
resolved style as the entire inner frame, including its neutral, green, yellow
or red state. Six captions move in each view:

| WORK card | Exact caption | ORACLES card | Exact caption |
| --- | --- | --- | --- |
| JOBS | `executing` | REQUESTS | `request history` |
| WORKFLOWS | `in progress` | ASSESSING | `in progress` |
| SEATS | `assigned seats` | ATTESTED | `with agreement` |
| BUILD | `building` | NO QUORUM | `without quorum` |
| REVIEW | `reviewing` | BLOCKED | `needs attention` |
| BLOCKED | `needs attention` | NETWORKS | `loaded requests` |

Each caption appears once, on the inner bottom border, and no outer footer is
painted. This holds on initial unread composition and after fresh, known-zero,
stale, unavailable and partial updates. ORACLES partial coverage remains in the
tooltip, including its existing read clock; it must not replace the caption or
reintroduce a `partial` outer footer.

Keep all digits, count calculations, activity decisions and existing frame-color
overrides. Keep six equal cards, nine-row hero height, card order, gutters and
body geometry, including WORK's balanced panes and ORACLES' 66/34 split. Existing
body content, controls, source lifecycle and data contracts stay unchanged.

## Implementation boundary

Use the existing `HeroRecord.subtitle` and `NewsHeroCard` inner-bottom renderer:
set `footer=""` and `subtitle=caption` in both initial and updated records.
Reuse `Pool4HeroCard`'s existing clipping detector for both native card classes,
preserving their frame-style overrides. Suppress the inherited partial source
footer locally where needed while retaining source information in tooltips.
No shared renderer change, new abstraction, API, schema or dependency is needed.

Full captions have priority over the previous width pins. At narrower sizes,
clipping must be advertised by the existing widen hint. Do not shorten captions
to preserve an obsolete pin.

## Acceptance and measurement

- Composited tests prove all twelve literal captions occupy the inner bottom
  border, have the complete frame style, and are absent from the outer footer.
- State tests retain the existing values and activity colors across fresh,
  zero, unread/unavailable, stale and partial inputs.
- Show fresh keyless live renders of both native views at the owner's 149×45
  terminal size before hardening any pin or dispatching review.
- After that live check, measure both bodies in situ using
  `scripts/measure_layout.py` modes `w` and `o`; certify each measured width at
  its boundary and at the owner size. The existing baseline pins are WORK
  126×30 and ORACLES 131×42; these are not measurements of this change.
- Retain row pins 30 and 42 unless measurement demonstrates a change. Record
  any new width only beside its existing constant and in the corresponding
  terminal-layout skill table row. This spec makes no new threshold claim.

This is Tier 2 under `CLAUDE.md`: two native views, two width pins and more than
six affected files. Expected production changes are below 1,000 lines. One
session implementer owns one work package; one final reviewer examines the
complete diff. The owner has already authorized the work.
