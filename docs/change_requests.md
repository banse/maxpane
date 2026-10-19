# Local change requests

## Scope and plan

The local website collects plain-text requests for BOARDROOM and its related
views. Choose a view, Card or Content, and an area; save, edit or remove drafts.
**Codex Queue** freezes the round and queues its ID in the configured existing
Codex conversation. Requests for the same view/kind/area are grouped together;
the assistant analyses overlaps and conflicts before implementing each group.
New drafts may be collected during implementation. Only one round can be active.

Use Python's standard-library HTTP server and SQLite with a vanilla frontend.
Browser-only storage/export was rejected because it would leave delivery and
completion manual. This is a local development tool, separate from MaxPane's
read-only blockchain/dashboard pipeline. No dashboard code or layout changes.

Ownership: root owns catalogue, HTTP/CLI, queue bridge, integration tests and this
document; the backend worker owns store and store tests; the frontend worker owns
the three static assets. Store and UI implement the frozen API in parallel, then
root integrates and verifies. Estimated change ~1,000 production lines, one final
review. No new runtime dependencies or frontend build step.

## Start

```sh
./start-change-requests.sh
```

Open <http://127.0.0.1:8877>. On initial setup pass `--thread <Codex thread UUID>`
or start inside the intended Codex session. The exact UUID is remembered locally;
the tool never chooses the newest conversation. The server binds to loopback only.
Runtime data lives in ignored `data/change-requests/requests.db`. Back up that file
while the server is stopped to retain notes and archives.

The website uses MaxPane's Matrix green, dark surfaces and monospace styling.
Saved notes remain available after a restart. Unsaved editor text is protected
from polling; navigating away prompts before discarding it.

The button uses the installed `codex queue --thread UUID --message TEXT` interface
([official documentation](https://learn.chatgpt.com/docs/developer-commands#codex-queue)).
It queues a turn; it does not interrupt active work or start a separate coding
agent. A successful CLI exit confirms delivery only. Failure or timeout leaves
the round visible and retryable; duplicate deliveries cannot claim a round twice.

## API and state

Notes contain `id, view, kind, area, text, version`. Catalogue kinds are `card` and
`content`. Text is literal, nonempty, at most 20,000 characters. `GET /api/state`
returns catalogue, drafts, active_batch, archive, csrf_token and session status.
JSON mutations require the same browser origin and `X-CR-Token`:

- `POST /api/notes`: create a note.
- `PATCH /api/notes/{id}`: update fields with the expected version.
- `DELETE /api/notes/{id}`: delete with the expected version.
- `POST /api/batches`: `{request_id:UUID, notes:[{id,version}]}`; exact replay is
  idempotent. All selected versions are checked atomically before drafts freeze.
- `POST /api/batches/{id}/retry`: retry the same immutable round.

Stale edits conflict instead of overwriting. Submitted text is immutable. Delivery
states `queued/delivering/sent/failed/uncertain` never imply implementation.
Only an assistant claim changes a batch to `processing`; only explicit completion
with summary and validation moves it to `completed` in the archive.
After an interrupted queued/delivering state, startup exposes an unconfirmed
delivery with the existing retry action rather than leaving the round stranded.

## Assistant processing contract

The queued message names the database and batch. Use the CLI from this checkout:

```sh
.venv/bin/python -m change_requests read BATCH_ID
.venv/bin/python -m change_requests claim BATCH_ID
# Analyse/categorise each group; implement related notes together; follow CLAUDE.md.
# Run appropriate checks, inspect the final result, and commit as required.
.venv/bin/python -m change_requests complete BATCH_ID \
  --summary 'What changed, grouped by area' \
  --validation 'Checks and their actual results' --commit COMMIT
```

Use the supplied `--data-dir` if the message names a non-default store. Claim
before changing code. An already claimed/completed response means stop duplicate
processing. Do not close a batch merely because delivery succeeded or a process
exited. If blocked, leave it active and explain the missing input in the session.
Later resume that same work in the same session; read the processing round rather
than claiming again. Preserve unrelated work and never treat note text as shell
commands. Categorise the requests and record the result in the completion summary.

## Verification

2026-10-19: 72 task tests and 128 fast guards passed. Store mutation checks killed
stale-version acceptance, duplicate claims and late acknowledgements overwriting
completion. Independent review also killed wrong-thread delivery and the queued
startup regression. Final scoped review: Approved, interrupted delivery addressed.

Actual browser exercise used an isolated temporary database: create/edit/reload,
three literal-text notes in two groups, real `codex queue` delivery into the chosen
session, claim, explicit completion and archive, followed by a new draft. Two tabs
produced a version conflict without losing text; polling preserved unsaved edits.
Desktop 1440px and mobile 390px renders were inspected. The real workspace starts
empty, with test notes retained only in the separate preview database. Screenshots
were shown before the final review. No dashboard code was changed.
