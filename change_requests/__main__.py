"""Local server and assistant acknowledgement CLI."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
from uuid import UUID

from .bridge import QueueBridge
from .catalogue import CATALOGUE
from .server import Application, serve
from .store import Error, Store

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data/change-requests"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("serve", "read", "claim", "complete"):
        sub = subs.add_parser(command)
        sub.add_argument("--data-dir", type=Path, default=argparse.SUPPRESS)
        if command == "serve":
            sub.add_argument("--port", type=int, default=8877)
            sub.add_argument("--thread")
        else:
            sub.add_argument("batch")
        if command == "complete":
            sub.add_argument("--summary", required=True)
            sub.add_argument("--validation", required=True)
            sub.add_argument("--commit", default="")
    args = parser.parse_args()
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    store = Store(data / "requests.db", CATALOGUE)
    try:
        if args.command == "serve":
            # A single server per database; assistant CLI connections remain independent.
            with (data / "server.lock").open("w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    parser.error("A change-request server is already using this data directory.")
                thread = args.thread or store.setting("thread_id") or os.environ.get("CODEX_THREAD_ID")
                if thread:
                    try:
                        thread = str(UUID(thread))
                    except ValueError:
                        parser.error("--thread must be an existing Codex thread UUID.")
                    active = store.state()["active_batch"]
                    if active and store.setting("thread_id") != thread:
                        parser.error("Finish the active round before changing its destination session.")
                    store.setting("thread_id", thread)
                if not 1024 <= args.port <= 65535:
                    parser.error("Use a port between 1024 and 65535.")
                active = store.state()["active_batch"]
                if active and active["status"] in ("queued", "delivering"):
                    store.delivery(active["id"], "uncertain", "Server restarted during delivery. Check this session before retrying.")
                bridge = QueueBridge(store, ROOT, executable=shutil.which("codex"))
                serve(Application(store, bridge, port=args.port))
                return
        if args.command == "read":
            result = store.get_batch(args.batch)
        elif args.command == "claim":
            result = store.claim(args.batch)
        else:
            result = store.complete(args.batch, args.summary, args.validation, args.commit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Error as error:
        print(json.dumps({"error": error.code, "message": str(error)}))
        raise SystemExit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
