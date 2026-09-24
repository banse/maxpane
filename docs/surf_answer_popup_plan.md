# Surf AGENT: answer.json in RECORD + an ANSWER popup (spec + plan, 2026-09-24)

Tier 2: it adds keys to `data/surf_models.py` (the `swarm_seat_work_rows` row shape and
`SWARM_ORACLE_CACHE_FIELDS`) and a new screen. Owner request (2026-09-24): in RECORD's answer column,
show the seat's own answer (the value and the start of the notes) for oracle rows instead of the agent's
closing message ("Created and validated artifacts/answer.json."). When the text is cut, a small button
at the end opens a temporary popup that shows the question, the answers and the notes, with
`PRESS ENTER TO CLOSE` centred underneath. Enter closes it.

Precedence: CLAUDE.md > this spec > the WP steps > implementer report.

---

## CODEX — START HERE

1. This clone's `origin/main` is **behind**. The base is autopull's local main, which is unpushed:
   ```bash
   cd /Users/banse/codex/maxpane
   git status --short            # must show only .codex/ .venv311/, the pool4 oracle fixture and this plan
   git fetch /Library/Vibes/autopull main
   test "$(git rev-parse FETCH_HEAD)" = 4ce2e5d95bc498b035c1bed4b988aef570c529b7 || echo STOP
   git switch -c feature/surf-answer-popup FETCH_HEAD
   .venv311/bin/python -m pip install -e . -q
   ```
   If the hash differs, stop and report. Do not guess another base.
2. Read `CLAUDE.md`, `.claude/rules/surf.md`, `.claude/rules/widgets.md`, `.claude/rules/data.md` and
   `.claude/skills/terminal-layout/SKILL.md` before WP2.
3. Run WP0–WP4 **straight through**, with no stop between WPs. Stop only on a stop condition (§6). Write one final
   report at the end (§7).
4. Never push, merge, tag, bump the version or rewrite history. Commit per WP on this branch.
5. Tests: `.venv311/bin/python`, with `env -u NO_COLOR` for anything that asserts colour. Run only the named tests
   plus `-m guard`, and never the full suite (the controller runs it once).

---

## 1. The source (verified against the committed fixtures, 2026-09-24)

We already read `GET /oracle/requests/<id>` for each oracle row in RECORD's 40-row window (branch
`feature/surf-oracle-panels`, now on main). The seat's member is found by exact `submissionHash`
(`surf_swarm` ~1737: `matches`). That member entry **is the seat's answer.json**, so this feature needs
no new endpoint and no extra request.

```
detail.question                 str, 74–828 chars (median 576); may contain 0x addresses
detail.answerType               "bool" | "uint256" | "address[]" (open vocabulary)
detail.chainId                  int (seen: 1, 56, 4663)
members[i].ok                   bool (19 of 2,722 are false)
members[i].reason               str | null ("Invalid input", "expected a decimal uint256", …)
members[i].answer.answer        bool | "decimal string" (1–29 digits) | ["0x…", …]
members[i].answer.notes         str, 122–3,999 chars (median ~800); 52 % contain an 0x address
members[i].answer.{v, figure, recipe, window, chainId, requestId, answerType, definitions}   unused
```

**Live re-probe 2026-09-24 (control plane `23659b86`, checked against `aidude/docs/imd-api-changelog.md` and
the official docs at https://imd.fun/docs/):**
- The member shape is unchanged: `{ok, answer{answer, answerType, chainId, definitions, notes, recipe, requestId, v,
  window}, reason, submissionHash, wallet}`. `answer.figure` is optional (missing in the live sample) and unused.
- The detail has **28 keys**: `guards` is new. It is unused and harmless, because nothing validates the key set of
  the detail.
- **The documented statuses include ones we have never seen:** `reproducing`, `mismatch`, `refused`, `failed`.
  Live list statuses (500 items): attested 431, disagreed 63, assessing 3, blocked 3. Today the point builder
  (~1730) returns `None` when `agreement` is null and the status is not `assessing`/`blocked`, which would hide
  an answer.json that exists. WP1 changes that, see §3 "Unknown statuses".
- `?members=<submissionHash>` filters the detail to that one member and keeps `agreement.cluster`. Measured:
  **159,079 bytes in full vs 2,979 filtered** on a 112-member panel. An unknown hash gives
  `200` with `members: []`. **The owner decided on 2026-09-24 to switch to it in this branch (F-A3, §3a).** It costs
  the submitted-member count: the branch derives `panel_members` from `len(members)`, and a filtered body cannot give
  it. `panelSize` is not the same number (200 vs 112 submitted in the live sample; in the fixtures, 69 of 82 terminal
  panels have fewer members than `panelSize`). In the fixtures, attested panels typically close at
  `members == quorum == agreed` (e.g. 80/80/80, 25/25/25).

Seat 420 in the kept fixtures: 72 joined members, covering all three types (61 uint256, 10 bool,
1 address[]) and chains 1, 4663 and 56. The explorer allowlist (`widgets/explorer._CHAIN_IDS`) has 1, 8453 and
11155111, so 56 and 4663 must render **unlinked but with the copy icon**. Never add a chain to the
allowlist here.

## 2. Behaviour

### 2.1 RECORD answer cell (oracle rows with a joined member)

A row is **joined** when its oracle point has `on_panel` true and a strict boolean member `ok` was extracted.
An invalid member answer may be `None` and is shown as `—`; membership is preserved (owner-approved). Rows
that are not joined behave exactly as today: review, build and every other node, off_panel, not read,
unavailable, or a detail read that failed.

- **Joined, `ok` true:** `<value> · <notes>`, one line.
  - The value:
    - bool: `YES` / `NO`, the words the panel column already uses.
    - uint256: the raw digits. Never convert units; the unit exists only in the question text.
    - address[]: `N addresses` (`1 address`).
    - any other answer type: the flattened value, clipped to 24 cells.
  - The value takes priority; the notes use the remaining width. If the value itself does not
    fit, shorten it with `… »` and show it in full in the popup (owner-approved 2026-09-24).
    Keep the layout pins unchanged and apply the button's identity checks below.
  - Notes are flattened (newlines → spaces) and cleaned with the same `strip_tags` → `sanitize_cell`
    discipline as today.
- **Joined, `ok` false:** `failed · <reason>` in red. This is also cut to the width and gets the button when cut.
- **Addresses in the visible notes** get the copy icon and the explorer link through surf's existing fitting
  pipeline: `widgets/surf/_icons.mark_addresses` → fit → `keep_units` (an address is never cut in half:
  either it is shown whole with ` ⧉`, or the cut falls before its `0x`) → `link_prose(…, explorer)`, with
  `explorer = explorer.for_chain_id(row chain_id)`. Reuse it; do not write a second fitter.
- **The button.** When a joined row's text is cut, the cell ends `…` + ` »` (space + U+00BB, 2 cells;
  `»` is Latin-1 and one cell wide in every terminal). The `»` alone carries
  `Style(meta={"@click": "screen.open_oracle_answer('<job uuid>','<64-hex hash>')"})`. The action
  string is built only from a `fullmatch`-valid canonical job UUID and a 64-hex hash (`fullmatch`, never
  `^…$`, per rules/widgets.md). With anything else, no button is drawn.
- **Uncut:** no button. (With a median of about 800 notes characters, nearly every joined row is cut.)
- **`‹ widen`:** a joined row's cut **does not** set `_clipped`, because the button is that row's affordance.
  A non-joined row's cut lights `‹ widen` exactly as today.

### 2.2 The popup — `screens/oracle_answer.py::OracleAnswerScreen(ModalScreen[None])`

Opened by `SurfScreen.action_open_oracle_answer(job_id, submission_hash)`:
- Re-validate both arguments (`fullmatch`).
- Find the row in the `swarm_seat_work_rows` the screen **last rendered**. Never fetch; no network in a
  handler.
- Push `OracleAnswerScreen(row)`, a snapshot. If the row is gone, post the status message
  `answer no longer listed` and push nothing.

Layout: a centred box, `width: 100%` capped at 110 columns, height up to the screen minus 2. Contents, top to bottom:

```
ANSWER · 005a4ed9 · oracle · 09-23 17:36                              (title, bold)

QUESTION
What is the floor price of Moonbirds on Ethereum mainnet, in wei, as of the pinned window?

ANSWER
this seat   457162630000000000
panel       agreed 34 · quorum 35 · panel 49 · 457160520000000000    (panel_* keys; `—` for any absent part)

NOTES
Fetched https://opensea.io/collection/moonbirds with curl (User-Agent set to avoid bot
block) at a time coinciding with the pinned closing block's timestamp …   (wrapped, scrolls)

                            PRESS ENTER TO CLOSE                      (centred, dim, always visible)
```

- **Value rendering:** a bool this-seat value is `YES`/`NO`. An address[] value is one address per line
  through `address_text` (full 42 characters, ` ⧉`, linked per chain). A failed member shows
  `failed · <reason>` in red in place of the value.
- **Panel line:** reuse RECORD's panel-cell wording and only `panel_*` keys already on the row. Never
  compare figures and never parse `figure` as a float (rules/surf.md).
- **Question and notes:** they keep their paragraph breaks (newlines) and are wrapped. Every address goes
  through `address_prose(…, explorer=for_chain_id(chain_id))`. Every string arrives as a pre-built `rich.text.Text`;
  no third-party markup string ever reaches `Static.update`.
- **Scrolling:** the notes sit in a `VerticalScroll` that has focus, so arrow keys and PgUp/PgDn scroll. The
  footer line stays pinned below the scroll area.
- **Closing:** `Binding("enter", "close")` and `Binding("escape", "close")`. The footer text says only
  `PRESS ENTER TO CLOSE`, as the owner specified; escape is the silent safety net. Escape must **not** reach
  SurfScreen's `escape` → `show_dashboard`: the popup handles it itself. Test that the AGENT body is still
  showing after escape.
- **Clicks work inside the popup.** A copy icon runs `app.copy_address`, and a link runs `app.open_explorer`;
  both are app-level, so nothing is re-wired.
- **Size:** it must be usable at the smallest terminal the AGENT body is used at, and must not break
  below it. Certify it at 80×24 and at 139×33 (the AGENT pin). No horizontal scroll, the footer is visible,
  and the title fits or is clipped with `…`.
- **Styles:** keep them in the screen's `DEFAULT_CSS`. `themes/minimal.tcss` is a single-owner shared file:
  do not touch it. The screen's class name is a CSS type selector (rules/widgets.md): pick one that no
  widget or stylesheet uses.
- **Refresh:** pushing the popup suspends SurfScreen (`DashboardScreen.on_screen_suspend` stops the timer),
  and closing it resumes and refreshes. Verify that the resume refresh goes through the normal guard and
  re-reads nothing the cache holds fresh. Report what it does.

### 2.3 Rejected alternatives (do not build)

- Fetching the detail when the popup opens. It needs a worker, loading and error states, and a network
  call behind a click; the facts are already read.
- A row cursor with Enter to open. RECORD is `CURSOR_TYPE = "none"`, and a cursor changes the whole
  panel's interaction. A keyboard path is follow-up F-A1.
- A popup for review/build rows (their full reply text). That is follow-up F-A2.

## 3. Data contract (WP0 freezes it)

`data/surf_models.py`:
- Append to `SWARM_ORACLE_CACHE_FIELDS`:
  `"question", "chain_id", "member_ok", "member_reason", "seat_answer", "notes"`.
- Append to the `swarm_seat_work_rows` tuple, each with its `#` comment:
  - `oracle_question`: str | None; `detail.question`, whitespace-normalised per line, ≤ 1,000 chars.
  - `oracle_chain_id`: int | None; `detail.chainId`, strict int, not bool.
  - `oracle_member_ok`: bool | None; `members[i].ok`. None when not joined.
  - `oracle_member_reason`: str | None; ≤ 200 chars.
  - `oracle_seat_answer`: str | None; see normalisation below.
  - `oracle_notes`: str | None; ≤ 4,000 chars, newlines kept, other control characters removed.

  `panel_answer_type` (already present) says how to read `oracle_seat_answer`.

**Normalisation (data layer, `surf_swarm`), strict:**
- bool → `"true"` / `"false"`.
- uint256 → the decimal string, only if it `fullmatch`es `[0-9]{1,78}`.
- address[] → the addresses joined by one space, only if every item `fullmatch`es a 0x40-hex address, at most
  20 items.
- Any other answer type → the flattened `str` of a str or number, ≤ 200 chars.
- A value that fails its type's check → `None`, and the row shows `—` for the value, never a guess.

The answer type is the **request's** `answerType`, never the member's copy.

### 3a. F-A3: the filtered detail read (owner-approved 2026-09-24)

- **Client:** `surf_swarm_client.fetch_oracle_request(request_id, submission_hash)` sends
  `params={"members": submission_hash}`. It sends nothing when the hash does not `fullmatch` 64 lowercase hex, and
  returns `None` (unavailable) as it does for a malformed id. There is one caller (`surf_manager` ~5842): pass the row's
  hash.
- **Do not trust the filter.** The point builder keeps its exact-hash match over whatever `members` list comes back.
  If the server ignores the parameter and returns all members, the result is still correct, only bigger. A
  returned member whose hash differs is not a match. `members: []` means `on_panel` is false, exactly as a
  full list without the hash did. The duplicate-member check stays.
- **The count changes.** The cache field `members` becomes `quorum` (`detail.quorum`, a strict nonnegative int or
  `None`). The row key `panel_members` becomes `panel_quorum`. Update every reader, the agreement tests and
  `rules/surf.md` ~347–350.
- **RECORD panel cell** (`_PANEL_COLS` = 9 is unchanged; every string below fits in it):
  - agreed / outvoted: `✓ agreed/quorum` / `✗ agreed/quorum`, the same colours as today. In the fixtures this reads
    the same as today on attested panels (80/80). With the quorum missing, show only the glyph and `agreed`
    (`✓ 34`).
  - assessing: `… of <panelSize>` (e.g. `… of 200`), yellow as today. With `panelSize` missing, show `…` alone.
    The submitted count is no longer read, and the cell must not pretend it is.
  - Every other state is unchanged.
- **Popup panel line:** `agreed N · quorum Q · panel P` with the consensus value, each part `—` when absent.
- **Fixtures:** the existing full details stay; they prove that the builder is correct on an unfiltered body.
  Add a **live capture** of filtered bodies through `tests/scripts/capture_oracle_requests.py` (a new `--member`
  mode, run once by you, keyless GET): one hit for a seat-420 member, one unknown hash (`members: []`) and one
  `assessing` request if one is live. Commit them under `tests/fixtures/surf/swarm/oracle/filtered/`
  with MANIFEST entries (sha256, bytes, the capture's UTC time and control-plane commit from `/version`). The test
  transport serves them, and asserts that the request carried `members=<hash>`.
- **Proof:**
  - Drop the `params` and a client test goes red.
  - Make the builder trust the first returned member without the hash check, and a test with a filtered body
    whose member hash differs goes red.
- `rules/data.md` / `docs/imd_swarm_api.md`: record the parameter, the measured sizes (159,079 → 2,979 bytes)
  and the `members: []` behaviour.

**Unknown statuses (documented, not yet observed live):** the point builder no longer returns `None` just because
`agreement` is null and the status is outside `assessing`/`blocked`. For any non-empty status string it builds the
point with an empty cluster, so this seat's answer.json facts survive. The panel state for a status other than the
four known ones stays exactly what the row shows today when no point exists (`unavailable`), and such a
point is not terminal (`_ORACLE_FINAL` is unchanged). Test `refused` and `failed` with a found member: the popup
opens and the panel line reads `unavailable`. A non-string or empty status still returns `None`.

**Cache migration:** points persisted before this change lack the new fields, so `coerce_oracle_slot`
drops them (`set(point) != set(FIELDS)`) and they are read again: at most 40 rows at 4 details per cycle,
about 20 minutes to refill. That is accepted. Do not write a migration.

**Size bound (owner-approved correction):** keep 400 points and all character caps, plus a
6,000-byte serialized-point budget using the cache's actual JSON encoding. Shorten notes first,
then question, then member reason as needed; preserve the normalized answer. Test maximal ASCII,
Unicode and escaped text through the builder and the persisted-point validator. Reject any point
whose remaining non-prose fields alone exceed the budget. The point payloads total at most 2.4 MB,
plus job/hash keys and the cache envelope. Do not lower the 400-point cap.

`WIDGET_SIGNATURES` / the frozen row-shape test (`test_every_list_row_in_the_fixture_matches_the_frozen_row_shape`)
and `tests/screens/test_surf_screen.py::_sample_data()`'s rows gain the new keys, with realistic values: at least
one joined bool row, one uint256 row, one address[] row and one non-joined row.

## 4. Work packages

**WP0: contract.** `surf_models.py` keys and fields (§3, including the §3a rename `members` → `quorum`,
`panel_members` → `panel_quorum`). Agreement and shape tests updated. Commit
`feat(surf): freeze answer.json row and cache keys`.

**WP1: data.** The §3a client change and live capture come first. Then `surf_swarm`:
- Extract the facts in the point builder (~1737), normalise and cap them.
- `coerce_oracle_slot` validates every new field **per point** (types, caps and byte budget; all six facts must be None
  when `on_panel` is false. When true, `member_ok` is a strict bool; an invalid `seat_answer` may be None). A hostile or oversize field drops only that point.
- The fold (~1893/1917) copies the facts onto the row, with all six `None` when not joined.

Tests, all from the committed fixtures plus hand-built dicts for hostile cases:
- Seat 420's joined rows carry the values: pick one row of each type and assert the exact strings.
- A member with `ok:false` gives the reason.
- Wrong type, a 79-digit number, a non-address item, 21 addresses, 4,001-character notes, a markup string
  `[/x]` in notes, and a control character each behave as §3 says.
- Old-shape points are dropped.
- The size bound holds.
- **Prove** the per-point coercion bites: remove one new check, see the named test go red, restore by
  inverse edit. Commit `feat(surf): answer.json facts on oracle rows`.

**WP2: RECORD cell.** `swarm_seat_record.py` per §2.1. Hoist anything a second module needs (the popup
needs the bool/uint/address[] value wording, and the panel wording already in RECORD) into
`widgets/surf/_swarm_seat.py` or a new `widgets/surf/_oracle_answer.py`, never a copy.

Widget tests, composited (`render_strips()`):
- Value first and whole whenever it fits; an overlong value is cut with `… »` and remains
  available in full in the popup, without moving a layout pin.
- Notes cut with `…` + ` »`, and the `»` carries the exact action string.
- An uncut joined row has no `»`.
- A hostile job id or hash draws no button.
- A joined row does not light `‹ widen`; a non-joined cut row still does.
- An address in visible notes is whole with ` ⧉`, linked on chain 1 and unlinked on 4663/56.
- The failed row is red.

Then re-sweep RECORD in situ per the terminal-layout skill. The AGENT pin 139×33 and the RECORD width
tiers must not move. `RECORD_NEVER_CLEARS_BELOW = 167`'s `#:` block gets a line saying joined rows are
exempt (the button replaces the marker); the number moves only if the sweep says so. If a pin must move,
stop (§6). Commit `feat(surf): RECORD shows answer.json value and notes`.

**WP3: popup.**
- `screens/oracle_answer.py` per §2.2.
- `SurfScreen.action_open_oracle_answer`.
- SurfScreen's `BINDINGS` are unchanged (the popup owns enter and escape).

Pilot tests, awaiting observable state and never wall-clock:
- A click on a row's `»` (use the compositor's meta, as `tests/widgets/address_probe` does for links)
  pushes the popup.
- The question, the this-seat value, the panel line and the start of the notes are on screen.
- `PRESS ENTER TO CLOSE` is centred on the last content line.
- Enter dismisses the popup, and so does escape. After escape, the AGENT body is still showing.
- A stale job id posts `answer no longer listed`.
- The address[] row lists every address with ` ⧉`.
- At 80×24 and 139×33: no region overflow and the footer is visible.
- Copy and explorer clicks inside the popup reach the (mocked) clipboard and browser. No test touches the
  real ones (conftest already replaces them).

Address rule: `tests/test_address_rule.py` must stay green (no private formatter). The popup is not a
dashboard screen, so if `tests/screens/test_address_icons_everywhere.py` cannot render it, add a dedicated
test in the popup's test file that seeds an address in the question, the notes and an address[] value,
and asserts icon and link composited. Say in the report which one you did. Commit
`feat(surf): ANSWER popup for oracle rows`.

**WP4: docs.**
- README "Keyboard shortcuts": the popup's enter/escape, and the `»` click.
- `.claude/rules/surf.md`: the answer.json source, the join and the normalisation rules. Keep it short.
- `docs/surf_answer_popup_followups.md` with F-A1 (keyboard path to the popup) and F-A2 (popup for
  non-oracle rows), plus anything you found. F-A3 is built here, not filed.
- Run `rg -n 'CLAUDE\.md|README\.md|SKILL\.md|rules/' tests/` and every file it names.

Commit `docs(surf): answer popup`.

## 5. Tests to run (named, plus `-m guard`)

```
tests/data/test_surf_swarm_oracle.py tests/data/test_surf_manager_oracle.py tests/data/test_surf_cache_swarm.py
tests/data/test_surf_swarm_client.py
tests/data/test_surf_models*.py (whichever holds the row-shape agreement)
tests/widgets/test_surf_swarm_seat_record.py
tests/screens/test_oracle_answer.py (new)
tests/screens/test_surf_screen.py            (whole file, once, after WP3)
tests/screens/test_surf_swarm_layout.py -k "agent or record or oracle or polish"
tests/test_address_rule.py tests/screens/test_address_icons_everywhere.py -k surf
-m guard
```

## 6. Stop conditions (stop and report; everything else runs through)

- The base hash differs from `4ce2e5d`.
- A layout pin (AGENT 139×33, a RECORD tier width) would have to move.
- A spec rule here contradicts CLAUDE.md or `rules/*.md`: report it as a plan defect.
- A named test cannot be made green.
- Anything that would need a network call in a test, a key, or a new endpoint.

## 7. Final report (one, at the end)

- Commits: hash and subject.
- Tests: which ran, and counts.
- The proof: which test went red, and why.
- The sweep numbers: before and after.
- What the resume refresh does.
- Which address-rule path you took.
- Every deviation from this plan, with its reason.

Controller afterwards: one task review per WP diff, a whole-branch review on the strongest model, one fix
wave, one scoped re-review, and the full suite once. Merge only with the owner.
