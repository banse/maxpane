# Wave-5 brief — what WP7 needs to register THE LIST

Written by the waves 3–4 gate after WP5 and WP6 landed and the full suite went green
(4241 passed, 0 failed). The curator screen's own full layout **measures 138 columns**,
independently re-swept by the gate rather than read off the constant; `FULL_LAYOUT_COLUMNS`
stays 143 (FWA still binds, curator is 5 columns under). Where this file and an older
document disagree, this file wins, and the source wins over this file.

---

Full text: /Library/Vibes/autopull/docs/curator_work_packages/wave5_brief.md (committed as 3f531f2).

MANAGER — maxpane_dashboard/data/curator_manager.py
  class CuratorManager:
      def __init__(self, poll_interval: int = 30, *, client=None, cache=None,
                   wallet: str | None = None, clock=time.time,
                   cache_path: str = DEFAULT_CACHE_PATH) -> None
      async def fetch_and_compute(self) -> dict   # exactly CURATOR_KEYS, never raises
      async def close(self) -> None               # closes client, then persists cache
      def save_cache(self) -> None
  SOURCES = ("state","logs","wallet") is exported here — import it, do not type the strings.
  DEFAULT_CACHE_PATH = ~/.maxpane/curator_cache.json (add to CLAUDE.md's caches sentence).
  `wallet` is normalised with `wallet or None`, so the empty string get_wallet() returns is safe.
  CORRECTION to wp7.md: MaxPaneApp.__init__'s parameter is `wallet_address`, not `wallet`, and it
  is NOT stored on self. Construction line: CuratorManager(poll_interval=poll_interval,
  wallet=wallet_address). The screen is built later in _launch_game where that local is out of
  scope — read it back as self._curator_manager.wallet rather than storing a second copy.

SCREEN — maxpane_dashboard/screens/curator.py
  class CuratorScreen(RefreshGuard, Screen)
      __init__(self, data_manager, poll_interval: int = 30, name: str = "curator",
               wallet: str | None = None, **kwargs)
      REFRESH_WORKER_NAME = "curator-refresh"; BINDINGS = [r, c]
  Module names: CURATOR_FULL_LAYOUT_COLUMNS=138, INITIAL_TITLE, TALLER_HINT="‹ taller",
  RAIL_FULL_HEIGHT, MANAGER_FAILURE_SECONDS=999, VIEW_CLUSTERS/VIEW_CLOSEST,
  CLOSEST_ID="curator-closest-calls", CLUSTERS_ID="curator-clusters".
  Install branch: CuratorScreen(self._curator_manager, self.poll_interval, name="curator",
  wallet=self._curator_manager.wallet) behind `if not self.is_screen_installed("curator")`.

WIDGET / CONTAINER IDS
  Containers: #title-bar #hero-row #middle-row #curator-right-rail #separator #bottom-row.
  The only two widget ids the screen sets are #curator-closest-calls and #curator-clusters (the
  `c` pair, both mounted, one hidden). Everything else is placed by type: CuratorHero,
  CuratorLeaderboard, CuratorSparklines, CuratorSignals, CuratorActivity, CuratorClosestCalls,
  CuratorClusters.

themes/minimal.tcss — DO NOT COPY DEFAULT_CSS VERBATIM
  The screen's tests run under _ThemedHarness, which already loads the real minimal.tcss, so
  everything WP6 measured was measured with the shared unscoped rules BEATING DEFAULT_CSS (an app
  stylesheet always outranks DEFAULT_CSS in Textual). Two shared rules win today: #bottom-row
  (line 126) height:1fr vs DEFAULT_CSS's auto, and #title-bar (line 12) padding:0 2 vs none.
  Measured now at 138x48: bottom-row 17 rows, title-bar 134 columns.
  Copying verbatim scopes `CuratorScreen #bottom-row { height: auto }`, which then wins, and
  CuratorActivity's own height:auto takes the screen: middle-row 17→1, bottom-row 17→47, SIGNALS
  and YOU stop reaching the compositor, a screen scrollbar eats two columns (138→136), and the
  `‹ widen` count goes to 0 at 137 as well — the width test passes with the rail gone.
  FIX (verified against a scratch copy: 12 markers at 136, 12 at 137, 0 at 138, bottom-row back
  to 17 rows): restate CuratorScreen #bottom-row { height: 1fr; margin: 0 0 1 0; }. Then either
  report the DEFAULT_CSS/block disagreement to WP6 (screens/curator.py is their file) or make
  `height` on #bottom-row an explicit commented exception in WP7.6's two-copies-agree test.
  Selectors the block needs (screen geometry only, ids scoped to CuratorScreen, Curator* types
  unscoped): #hero-row height:auto margin:1 0 0 0 (NO vertical padding); CuratorHero width:1fr
  padding:0 1; #middle-row height:1fr margin:1 0 0 0; CuratorLeaderboard width:3fr padding:0 1;
  #curator-right-rail width:5fr height:1fr overflow-y:auto scrollbar-gutter:stable
  scrollbar-size:1 1 (NO vertical padding); CuratorSparklines width:1fr height:auto padding:0 1
  margin:0 0 1 0; CuratorSignals width:1fr height:auto padding:0 1; #bottom-row height:1fr
  margin:0 0 1 0; CuratorActivity width:5fr height:auto padding:0 1; CuratorClosestCalls
  width:3fr height:auto padding:0 1; CuratorClusters width:3fr height:auto padding:0 1.
  scrollbar-gutter:stable is load-bearing (commit 98b8ae6) — without it the pinned width is true
  at 48 rows and false at 40. The 3:5 and 5:3 seams are measurements, re-swept with the gutter
  (10:17/7:12/13:22/17:29 reach 137, 3:5 and 4:7 reach 138, 5:8 140, 1:2 150, 1:1 173).
  #title-bar and #separator stay OUT of the block — the shared rules already style them and
  WORST_CASE_TITLE_COLUMNS=90 was swept with padding:0 2 in force (90 <= 134).
  No widget-internal class belongs in the block (.curator-lb-*, .curator-signals-*,
  .curator-spark-*, .curator-activity-title, .curator-cc-*, .curator-cl-*, #curator-hero-boxes,
  CuratorHeroBox, #curator-hero-note): all owned by the seven widget modules, none collides with
  a shared selector. Restating one gives a rule two owners — the surf block's documented rule.

THE SIX SURFACES, IN ORDER: app.py → __main__.py → GAMES
  app.py — SEVEN edits, not eight. wp7.md's step 5 ("elif self._initial_game == 'curator'") names
  a chain that does not exist; the prefetch is the _prefetch_manager dict alone.
    1 from ...data.curator_manager import CuratorManager      (~line 18)
    2 from ...screens.curator import CuratorScreen            (~line 35)
    3 self._curator_manager = CuratorManager(poll_interval=poll_interval,
        wallet=wallet_address)                                (~line 104, beside _surf_manager)
    4 "curator": self._curator_manager,                       (_prefetch_manager dict, ~line 164)
    5 elif game_id == "curator": install branch               (_launch_game, after surf, ~line 297)
    6 _GAME_CYCLE = ["surf","curator","fwa","base","frenpet","cattown","ttt","talismans"]
      (~line 200, HAND-TYPED literal — never derived from GAMES)
    7 await self._curator_manager.close() in its own try/except (shutdown chain, ~line 459)
  Sixth SURFACE: initial_game: str = "surf" (line 72) is VERIFIED AND NOT EDITED — curator goes in
  at position 2, surf stays position 1. Record that in the commit body.
  __main__.py — insert "curator" at index 1 of --game choices (line 256). Leave default="surf"
  (255), the help text, --theme choices (242) and FULL_LAYOUT_COLUMNS=143 (59) alone.
  game_select.py GAMES — insert at key "2", renumber 3..8, leave every commented hidden row and
  its restore comment untouched. Measured: the proposed row `[2] THE LIST — Zero-custody
  allowlist game w/ an hourly doomsday clock on Ethereum` is 82 columns against a current longest
  of 80 (Fake World Assets) and a median of 58; +2 is inside "a few", dropping "Zero-custody "
  gives 69.
  CLAUDE.md — "## The eight visible dashboards", table row 2, every "seven" in the prose, curator
  added as the second worked example in the registration paragraph (noting it was a position-2
  INSERT, a different shape from surf's append), the width sentence per WP7.7, and
  ~/.maxpane/curator_cache.json in the caches sentence.
  README.md — table row 2, `maxpane --game curator` in the usage block, display name THE LIST,
  and read _readme_width_bands()'s regex in test_surf_registration.py before touching the width
  table. Do not touch the surf caveats.

WHAT CHECKS EACH SURFACE
  contiguous 1..N keys: tests/test_fwa_theme.py:490, inside test_game_cli_choice_includes_fwa
    (line 462) — its name gives no hint it guards this. Do not duplicate; reference in a comment.
  GAMES↔_GAME_CYCLE: test_surf_registration.py::test_the_menu_and_the_tab_cycle_offer_the_same_
    games_in_the_same_order
  GAMES↔--game choices: test_surf_registration.py::test_the_cli_choices_are_exactly_the_menu,
    test_cli_game_choices.py::test_every_game_choice_is_offered_by_the_menu, ::test_reachable_
    games_still_work
  prefetch entry: test_app_startup.py::test_every_game_choice_has_a_prefetch_manager
  bare-app default: test_app_startup.py::test_a_bare_app_prefetches_the_dashboard_the_menu_opens_on
  --game default: test_surf_registration.py::test_the_default_game_is_the_first_menu_entry
  surf stays entry one: test_surf_registration.py::test_surf_is_menu_entry_one (SURF_ROW verbatim)
  prefetch failure survivable: test_app_startup.py::test_failing_prefetch_does_not_kill_app
  docs: test_surf_registration.py::test_every_visible_dashboard_is_documented (needs the literal
    `--game curator` AND `THE LIST` in README, and `curator` in backticks in CLAUDE.md) and
    ::test_claude_md_counts_the_visible_dashboards (derives "eight" from len(GAMES))
  width tripwire: tests/screens/test_curator_screen.py::test_curator_fits_inside_the_documented_
    app_width (138 <= 143)

WIDTH DECISION: WP7.7 case one. 138 <= 143, nothing moves. Do not append to CLAUDE.md's record
  198 → 172 → 143 → 176 → 152 → 143; add one sentence saying curator measures 138, five columns
  under FWA's 143, binding panel CuratorSignals, height-independent because the rail reserves its
  scrollbar gutter.
