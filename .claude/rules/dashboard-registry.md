---
paths:
  - "maxpane_dashboard/app.py"
  - "maxpane_dashboard/__main__.py"
  - "maxpane_dashboard/screens/game_select.py"
  - "tests/test_app_startup.py"
  - "tests/test_cli_*.py"
  - "tests/test_*_registration.py"
  - "tests/test_game_select_quit.py"
  - "README.md"
---

# Adding, hiding or reordering a dashboard

## The ten visible dashboards

| # | `--game` | Chain | Subject |
|---|---|---|---|
| 1 | `surf` | Ethereum | surfsurf.eth Surfboard: announce channel, ten detectors, launchpad (`l`), pool4 market (`4`), experimental pool4-protocol (`e`), IMD swarm (`s`) |
| 2 | `curator` | Ethereum | THE LIST: zero-custody allowlist game, hourly doomsday clock, linked-wallet analysis (`a`), record lists (`l`), your standing (`y`) |
| 3 | `fwa` | Ethereum | Fake World Assets, inverse-weighted NFT gacha pool |
| 4 | `base` | Base | trending tokens, volume, signals |
| 5 | `frenpet` | Base | pet battles, leaderboard, activity |
| 6 | `cattown` | Base | fishing competition, KIBBLE economy |
| 7 | `ttt` | Ethereum | Ten Thousand Tokens, NFT + UniV4 burn-to-launch |
| 8 | `talismans` | Ethereum | core-conservation NFT collection |
| 9 | `surfboard` | Ethereum / IMD | SURFBOARD HUB: four-row rack, seven existing views and a read-only command terminal; shares `_surf_manager` |
| 10 | `sworn` | Ethereum | Original Sworn artwork and claimant fact explorer; menu shortcut 0 |

`surf` is position 1 and the `--game` default. The splash starts no dashboard
reads; acquisition begins when a dashboard becomes visible. Hidden from the selection pane, code and tests intact: `bakery`, `ocm`, `dota`
(backend is NXDOMAIN; 77 client tests still pass), `frenpet_full`, `frenpet_wallet`,
`frenpet_perf`. Ten themes are registered. Dashboard 9 aliases `_surf_manager` for compatibility lookup and shutdown; it adds no manager attribute. Dashboard 10 adds `_sworn_manager`; all four `MANAGER_ATTRS` lists include it. `ALL_GAMES` includes both `surfboard` and `sworn`.

**Hiding, adding or reordering a dashboard touches six surfaces and they must agree:**

1. `GAMES` in `screens/game_select.py` — keys stay contiguous 1..N (a test asserts it);
2. `_GAME_CYCLE` in `app.py`;
3. the `--game` `choices` in `__main__.py`;
4. the `--game` `default` in `__main__.py` — hiding the current default silently breaks launch;
5. `MaxPaneApp.__init__`'s `initial_game=` default in `app.py` — missed by the 2026-08-10 reorder
   when this list said "five"; pinned by
   `tests/test_app_startup.py::test_a_bare_app_prefetches_the_dashboard_the_menu_opens_on`;
6. this table and the README.

Order for an addition: `app.py` → `__main__.py` → `GAMES`; the registration tests derive their
expectations from `GAMES`, so growing that list first turns `tests/test_cli_game_choices.py` and
`tests/test_app_startup.py` red until the wiring catches up. Tests derive game ids from `GAMES`
rather than naming them.

`_GAME_CYCLE`, the `--game` `choices` and `initial_game` stay **hand-typed literals rather than
imports of `GAMES`** — deriving them would make their agreement tests compare a constant against
itself. Redundancy plus an agreement test is the pattern here; do not "simplify" any of the three.

Two worked examples: `tests/test_surf_registration.py` is the **append** (position 1, no other
key moved); `tests/test_curator_registration.py` is the **position-2 insert** (every key below
it shifted, the tables renumbered, the hardcoded lists grew: `ALL_GAMES` in
`tests/test_app_startup.py` — every `--game` choice, hidden ones included, with no agreement test
covering it — and the four `MANAGER_ATTRS` copies below). Prefer the insert's example when the
new dashboard is not going at the end.

**`MANAGER_ATTRS` exists in four files** — `tests/test_app_startup.py`,
`tests/test_surf_registration.py`, `tests/test_game_select_quit.py`,
`tests/test_curator_registration.py`. Grow every copy (`rg -n MANAGER_ATTRS tests/`): an ungrown
one leaves a **real** manager inside `run_test()`, and the `q` those tests press awaits its real
`close()`, so a headless "zero network" suite overwrites the developer's own
`~/.maxpane/<game>_cache.json` with an empty one. The copies stay hardcoded (a derived list cannot
see a manager that was never built);
`tests/test_curator_registration.py::test_every_copy_of_manager_attrs_names_every_manager_the_app_builds`
discovers the copies by walking `tests/` and finds the next missed one.

**A new body or view inside an existing dashboard is not a new dashboard**: no six-surface
renumber, `app.py` / `__main__.py` / `GAMES` untouched. A mode is a whole second body with its
own panels, never two panels sharing one slot.
