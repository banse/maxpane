# Surf card inner styling

Status: implemented across the owner-approved scope. Verification and measured
boundaries are recorded in `docs/surfboard_followups.md` and the screen pin comments.

## Approved result

Apply one inner-body color policy to every visible Surf card and boardroom card:

- A numeric readout whose final inset border is green uses the brighter ANSI green
  already used by active boardroom digits (`green`, the theme's ANSI index 2).
- Body labels and prose use that light green. Other values use the darker theme
  `foreground` green. Inactive numeric readouts use the card's normal white text
  color; orange frames retain foreground digits. Missing-value
  placeholders may retain label green; they are not measured values.
- Keep existing boldness, except where existing custom post-processing must be
  replaced to preserve the same bold value appearance.
- Text rows have one blank terminal cell between their content and each inset edge.
  This includes stats, prose previews, ordinary rows, models, owner text and compact
  numeric fallbacks. Native tall digits retain their existing centered face and
  width budget; the owner requested padding for text content.
- Inset borders, headings, subtitles and outer titles/footers retain their current
  state logic and colors. Red/orange warnings remain visible in those frames and
  footers. STATUS's deliberately muted separator remains a separator.
- Preserve values, formatting, units, safe literal text, copy/explorer affordances,
  source clocks and loading/failure semantics. Preserve card order, dimensions,
  keyboard behavior, polling, models contracts and all data calculations.

Follow-up: red inset borders require orange numeric readouts (the theme's ANSI
yellow/orange), including custom Agent STATUS and boardroom digits. The controller
implements this small shared-policy correction; test the existing composited
red-frame cases first, pass the final frame color/theme into the shared helper,
verify a live 149×45 render, then run one final review. Colors alone do not move
geometry or require new layout measurements.

Follow-up: restore inactive digits to the card's normal text color. The controller
passes that existing text color into the shared helper for neutral frames only,
updates the existing color assertions, checks the live boardroom at 149×45,
and runs the affected checks plus one review. Red-frame orange digits, active
green digits, stat values and captions retain their current colors.

The owner confirmed “Every Surf view and boardroom.” This is Tier 2 because the
renderer serves multiple bodies. Expected production change is comfortably below
1,000 lines; packages receive no separate task reviews, only one final review.

## Rendering paths

| Visible surface | Current renderer | Required treatment |
| --- | --- | --- |
| ONCHAIN NEWS | `SurfNewsHero` → `NewsHeroCard` | Shared digits, stats, previews and rows |
| LAUNCHPAD | `SurfLaunchpadHero` → `Pool4HeroCard` | Inherit shared policy; fitting hints use reduced text budget |
| POOL4 MARKET | `SurfPool4RackHero` → `Pool4HeroCard` | Same, including large/partial values |
| PROTOCOL | `SurfProtocolHero` → `ProtocolHeroCard` | Limit CHECK FAILED red override to existing frame/footer; body uses policy |
| SWARM | `SurfSwarmRackHero` → `NewsHeroCard` | Inherit shared policy |
| WORK | `SurfWorkHero` → `_WorkHeroCard` | Resolve red BLOCKED frame before selecting digit color |
| ORACLES | `SurfOraclesHero` → `_OracleCard` | Resolve orange/red/green per-state frame before selecting digit color |
| AGENT | `SurfSwarmAgentRackHero` → `AgentRackCard` | Shared rendering plus custom status/models, owner address and runtime fitting |
| LEADERBOARD | `SurfSwarmBoardHero` → `BoardHeroCard` | Replace color-rewrite pass with shared policy while retaining bold values |
| LAUNCHES/TOKENS screen | `TokensHero` → `TokensHeroCard` → `LocalSourceHeroCard` | Inherit policy; explicit value spans for liquidity amounts in free-form rows |
| BOARDROOM | `SurfboardRack` → `SurfboardCard` | Shared palette and padding helpers in independent existing renderer |

`SurfHero`, `SurfSwarmHero`, `SurfSwarmAgentHero`, `SurfSwarmSeatCards` and the
older agent hero/cards are parked; no current visible mode uses them. Do not
rewrite those renderers or unrelated tables, detail panes, terminal feeds or
toasts. Screen composition confirms all active Surf hero routes above; standalone
tokens uses its own screen and the same inherited renderer.

## Decision and small shared API

Option A duplicates palette and padding edits in each renderer. It avoids a new
module but would retain the drift this request is correcting. Option B shares two
pure body helpers while keeping each existing renderer and state decision local.
Choose B; no generalized card framework, new data layer, or hierarchy rewrite.

Shared module: `maxpane_dashboard/widgets/card_inner.py`.

```python
def inner_styles(palette, *, active=False, frame_color=None, ansi_theme=None, text_color='white'):
    # Return (label_style, value_style, digit_style).
    # All use palette['background'] and dim=False.
    # Labels: ANSI green; values: palette['foreground'];
    # Digits: red frame -> orange; active -> light green; neutral -> normal text.
    # Other colored frames retain value color.

def padded_inner_row(row: Text, inside: int, *, align='left') -> Text:
    # Copy the rich Text, fit/align to max(0, inside - 2), then add edge spaces.
    # Preserve spans, OSC8 links and click metadata; never flatten to markup.
```

These helper names/signatures are frozen for parallel implementation.
Clipping is detected against the same reduced text budget before fitting; do not
conceal dropped text. Keep the helper free of widget, data, transport and clock
imports. Use existing terminal-cell-aware Rich/rowfit utilities.

Add a small `NewsHeroCard._frame_style()` hook. `AgentRackCard` already has this
method. WORK, ORACLES and PROTOCOL should express their existing warning frame
styles through it rather than recoloring the result after body colors are chosen.
The final frame, not merely `data.accent`, decides whether a numeric readout is
active green; recognize both theme accent green and existing ANSI green frames.

Existing typed stats provide label/value boundaries. For known mixed text rows
(token liquidity, protocol drift, activity age) style explicitly at formatting or
rendering seams rather than guessing arbitrary numbers inside model names, prose
or addresses. Preserve their current textual order and units. Rich address spans
must survive any color overlay. `Pool4HeroCard` hints must use the new preview/row
budget as well as its existing stat budget.

## Work packages and ownership

All implementers work in the shared checkout and must preserve other owners'
edits. No package changes data models, clients, managers, global theme CSS or
registration. Report required edits outside ownership to the controller.

| Package / owner | Production ownership | Test ownership | Dependencies |
| --- | --- | --- | --- |
| A: shared rendering implementer | New `widgets/card_inner.py`; `widgets/surf/news_hero.py`, `pool4_hero.py`, `swarm_board_hero.py`, `protocol_hero.py`, `work.py`, `oracles.py`; `widgets/swarm_tokens/hero.py` only if mixed rows need explicit spans | `tests/widgets/test_surf_card_inner.py` (new); `test_surf_news_hero.py`, `test_surf_swarm_board_hero.py`, `test_surf_pool4_hero.py`, `test_surf_launchpad_hero.py`, `test_surf_protocol_hero.py`, `test_surf_work.py`, `test_surf_oracles.py`, `test_swarm_tokens_hero.py`, `test_surf_swarm_rack_hero.py` | Establish helper/frame API first |
| B: agent implementer | `widgets/surf/agent_rack_hero.py` | `tests/widgets/test_surf_agent_rack_hero.py` | A's helper API; final verification after A |
| C: controller / boardroom | `widgets/surfboard/rack.py` | `tests/widgets/test_surfboard_rack.py`, `test_surfboard_card_activity.py`, `test_surfboard_seats.py` | A's helper API; independent renderer edits can run alongside B |
| D: controller integration | Screen pin comments/constants only if measurements require them; scoped current followups docs and this plan | All composing/sweep tests under `tests/screens`; address sweep files; guard/docpin selection | A–C integrated, then live preview before hardening |

Paths in A/B are under `maxpane_dashboard/` unless explicitly under `tests/`.
Once the helper signatures are written, B and C may edit their disjoint files in
parallel. They must not edit A's helper or shared renderer. Do not run mutations
while another owner is writing the mutated file. One worker owns A and one owns B;
the controller implements C and D. No extra planning subagents.

## Verification and sequence

1. Begin with focused failing composited-output tests for changed policy, then the
   smallest renderer changes. During edits run named cases or narrow selections.
2. Cover final frame colors: active green, neutral/inactive, orange warning and
   red failure. Assert actual body label/value/glyph colors independently from
   frame, header, subtitle and footer colors. Assert inherited bold values remain
   bold and ordinary labels do not become bold.
3. Exercise each content branch: digits and compact fallback, stats, free-form
   rows, long/untrusted preview, owner rich address, runtime daemon/arrow, models
   with effort, STATUS tall/compact separator, boardroom fleet/protocol/tokens.
   Assert one blank cell at each edge for text; full values/units fit at owner
   size where previously available, and narrow losses carry existing hints or
   safe address windowing. Wide glyphs and literal markup must not break edges.
4. Render live keyless data at **149 × 45** after A–C work. Show boardroom and
   representative Surf views, including agent, leaderboard, warnings and tokens;
   preserve the actual live source state. This precedes pin sweeps, pin-comment
   updates, final measurement docs and review. Fixture renders are not this gate.
5. Re-sweep affected width boundaries with existing screen harnesses: owner size,
   each current pin ±1/±2, narrow fallback and wide case, including normal,
   partial/stale/unavailable and long-value fixtures. Use `scripts/measure_layout.py`
   for `s`/`a`/`b`. Keep outer card geometry fixed; measured textual clearance can
   change because padding consumes two cells. Never hide clipping by merely
   raising constants. Update only genuinely affected pin blocks after evidence.
6. Run focused mutation proof for a palette regression, padding removal and a
   false-green warning/disabled hint or broken address span. Use
   `scripts/mutate.py`, name the exact reddened node IDs, and restore inverse edits.
7. Once stable, run touched widget files and their composing screen files whole,
   in one isolated-HOME `env -u NO_COLOR ... pytest -n 4 --dist worksteal` command.
   Compose paths: default Surf, launchpad, POOL4 protocol/market, swarm/agent/board,
   work, oracles, standalone tokens, and boardroom. Include their relevant layout
   files once. Do not run the full repository suite or registration-mount checks
   when no keys/registration surfaces changed. A parallel-only failure gets its
   file rerun serially and documented.
8. Run fast `guard and not mounts_app` and relevant docpins. Run the targeted
   address affordance sweep because padding may change owner/news/token address
   windowing. Tests remain offline and clipboard-disabled.
9. One final review receives the combined diff, explicit rendering risks and
   named test/mutation evidence. Apply at most one fix wave; scoped re-review only
   if it changes production code. File Minor-only findings. Update relevant
   followups, remove temporary plan workspaces, and commit locally.

Do not claim revised pins, live data correctness or passing checks in this plan;
the controller records measured evidence after implementation.
