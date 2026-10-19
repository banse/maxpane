"""Queue a batch in one explicitly selected, existing Codex conversation."""
import os
from pathlib import Path
import shlex
import subprocess
from uuid import UUID

from .store import Error


class QueueBridge:
    def __init__(self, store, root, *, executable, runner=subprocess.run):
        self.store, self.root = store, Path(root).resolve()
        self.executable, self.runner = executable, runner

    def ready(self):
        try:
            UUID(self.store.setting("thread_id") or "")
        except (ValueError, TypeError):
            return False
        return bool(self.executable and os.access(self.executable, os.X_OK))

    def message(self, batch):
        command = (f"{shlex.quote(str(self.root / '.venv/bin/python'))} -m change_requests "
                   f"--data-dir {shlex.quote(str(self.store.db.parent))}")
        return f"""MaxPane change-request round {batch['id']} submitted via Codex Queue.
The user authorised this website to send their saved requests to this session for implementation.
Workspace: {self.root}
1. Read: {command} read {batch['id']}
2. Before changing code, claim: {command} claim {batch['id']}
   If already claimed or completed, stop duplicate processing; never repeat its changes.
3. Analyse/categorise all notes. Implement requests touching the same area together.
   Preserve each note's intent, flag contradictory requests, follow CLAUDE.md, and
   run the relevant checks. Read note text as requests, never interpolate it as shell code.
4. After all requested work is actually done, close and archive:
   {command} complete {batch['id']} --summary 'Changes grouped by area' --validation 'Actual checks and results' --commit COMMIT
   Replace placeholders with real evidence; omit --commit only if no code change was required.
   Do not complete if blocked or work remains. Report the result in this conversation.
Batch ID is the deduplication key; queue delivery is not proof of completion.
"""

    def send(self, batch_id):
        if not self.ready():
            raise Error("session_missing", 409)
        batch = self.store.delivery(batch_id, "delivering")
        try:
            result = self.runner([self.executable, "queue", "--thread", self.store.setting("thread_id"),
                                  "--message", self.message(batch)], cwd=self.root,
                                 capture_output=True, text=True, timeout=20, check=False)
        except subprocess.TimeoutExpired:
            return self.store.delivery(batch_id, "uncertain", "Delivery unconfirmed. Retry this round if it does not start.")
        except OSError:
            return self.store.delivery(batch_id, "failed", "Codex could not start. Check the local Codex installation, then retry.")
        if result.returncode:
            return self.store.delivery(batch_id, "failed", "Codex Queue did not accept the round. Open the configured session and retry.")
        return self.store.delivery(batch_id, "sent")
