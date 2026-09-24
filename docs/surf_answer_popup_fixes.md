# FIX WAVE — surf answer popup (after the per-WP and whole-branch reviews, 2026-09-24)

For: Codex, on `feature/surf-answer-popup` in this clone (head `a1b56e1`). This is the branch's **one** fix wave
(CLAUDE.md Tier 2). Precedence: CLAUDE.md > the plan (as amended below) > this brief.

Run straight through with no stops, except these stop conditions: a plan defect, a named test you cannot make
green, or a layout pin that would move. Use `.venv311/bin/python` with `env -u NO_COLOR`. Run named tests plus
`-m guard`, never the suite. Never push, merge, tag, bump the version or rewrite history. Nothing in the background.

## 1. Plan amendments (commit them with F1, in `docs/surf_answer_popup_plan.md`)

- **§3 "Unknown statuses" — this was a controller defect (N1).** Replace "For any non-empty status string it builds the
  point with an empty cluster" with the following. The relaxation applies **only** to a non-empty status string that is
  **not** in `_ORACLE_FINAL` and is not `assessing`/`blocked`, i.e. the documented `reproducing`, `mismatch`,
  `refused`, `failed`, or anything new. A **known final** status (`attested`, `disagreed`) with `agreement` null
  (or a non-mapping) is a failed read, as before this branch. It returns `None`: the row is `unavailable`, it is
  retried, and it is never a terminal verdict.
- **§2.2 mock (N5):** the panel line shows `agreement.figure` (the existing `panel_figure`, the same value RECORD's
  `panel <figure>` shows), not `agreement.answer`. Fix the example number to `457162630000000000` and say so.

## 2. Items

Each item gets a fix and a regression test. **Prove** means: break the code on purpose, name the test that goes red,
then restore the code by inverse edit.

| id | sev | what | where | done when |
|---|---|---|---|---|
| **F1 (N1)** | Critical | `attested`/`disagreed` with `agreement: null` builds a point with an empty cluster. It shows red `✗ no-q` / `outvoted` and is terminal, so it is never re-read | `surf_swarm.py` ~1817 | Per the amended §3. Tests: `attested` and `disagreed` with null agreement → `None` (row `unavailable`, not terminal, retried next cycle); `refused`/`failed` still keep the member's answer facts. **Prove:** go back to the relaxed rule and the new test goes red |
| **F2 (N2)** | Important | The manager test's fake `fetch_oracle_request` accepts any seat hash and returns the full detail, so passing a sibling's hash stays green | `tests/data/test_surf_manager_oracle.py:41` | The fake behaves like the real filter: it returns only the member whose hash was asked for (`members: []` otherwise), and it records the `(request_id, hash)` pairs. Assert that every row of a job with ≥ 2 seat hashes gets its **own** member's facts. **Prove:** mutate `surf_manager.py` ~5842 to pass a sibling's hash, and a test goes red |
| **F3 (N3)** | Important | The quorum fallbacks in `panel_text` are not pinned | `_oracle_answer.py:60,62` | Composited assertions of the exact cells: quorum missing → `✓ 34` / `✗ 34`. Assessing with no `panelSize` → exactly `…`, with no digit anywhere in the cell. Also `… of 200` with size, and `✓ 80/80`. **Prove** both of the reviewer's mutants (`✓ 35/—`; `… 3`) go red |
| **F4** | Important | Empty or whitespace-only `status` guard is untested | `surf_swarm.py` ~1806 | Tests `status=''` and `'  '` → `None`. **Prove:** removing the guard reddens them |
| **F5** | Important | `_oracle_answer.py:71` hardcodes `9` | — | Use `_PANEL_COLS` from one home (move it into `_oracle_answer.py` and import it in `swarm_seat_record.py`, or pass the width in). No second literal. RECORD tiers stay 102/94/53 |
| **F6** | Important | `screens/oracle_answer.py:48` re-declares the `failed · <reason>` wording | — | One helper in `_oracle_answer.py` used by both RECORD and the popup |
| **F7** | Minor | No test proves `action_open_oracle_answer` needs hash + joined beyond job_id | `surf.py` ~3752 | A pilot test with two joined rows of one job opens the right member's popup via each `»`. **Prove:** match on job_id alone and it goes red |
| **F8 (N4)** | Minor | A cap or byte trim can cut a 64-hex string at exactly 42 characters into a fake address that `address_prose` gives an icon and link | `surf_swarm.py` ~1729, `_bound_oracle_point` | After any cut, if the text ends inside a `0x` hex run, drop that whole run (and a trailing space). Test: `'x'*3957 + ' 0x' + 'ab'*32` gives no `0x` at the end and no icon; the bound point still survives coercion unchanged |
| **F9** | Minor | Size-bound test never exercises the reason-trim step | `test_maximal_member_point_fits_actual_json_byte_budget` | Add a variant where question and notes alone cannot meet 6,000 bytes, so `reason` is trimmed. Assert it was |
| **F10** | Minor | README.md:193 lists panel before model/took | README | Follow the `_SPECS` order: when, job, node, state, model, took, panel, tok, answer |
| **F11** | Minor | Unused `import asyncio` | `tests/screens/test_oracle_answer.py:2` | Remove it |

## 3. Commits, tests, report

- **Commits:**
  - `fix(surf): F1 known final status without agreement is a failed read` (with the plan amendments)
  - `test(surf): F2 F3 F4 F7 bite on hash, quorum and status`
  - `fix(surf): F5 F6 F8 one home for panel width and failed wording; no fake address after a cut`
  - `docs: F9 F10 F11`, or fold them into the nearest commit
- **Tests:**
  ```
  tests/data/test_surf_swarm_oracle.py tests/data/test_surf_manager_oracle.py tests/data/test_surf_cache_swarm.py
  tests/data/test_surf_swarm_client.py tests/data/test_surf_swarm_models.py tests/widgets/test_surf_swarm_seat_record.py
  tests/screens/test_oracle_answer.py tests/screens/test_surf_screen.py
  tests/screens/test_surf_swarm_layout.py -k "agent or record or oracle or polish"
  tests/test_address_rule.py tests/test_address_sweep_registry.py
  -m guard
  ```
- **One final report:**
  - commits (hash and subject)
  - tests and counts
  - for each proof, which test went red
  - every deviation and its reason
- After you, the controller runs one scoped re-review and the full suite once. The merge is the owner's.
