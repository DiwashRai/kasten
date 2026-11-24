"""Thread files on disk. The only code that reads and writes them."""

import json
import logging
from pathlib import Path

from relay.errors import RelayError
from relay.thread import Thread, file_key, thread_from_json, to_json

LOG = logging.getLogger("relay")
THREADS = "threads"


def home(env: dict[str, str]) -> Path:
    """Relay's folder: RELAY_HOME, else %LOCALAPPDATA%\\relay, else ~/.relay."""
    if env.get("RELAY_HOME"):
        return Path(env["RELAY_HOME"])
    local = env.get("LOCALAPPDATA")
    return Path(local) / "relay" if local else Path.home() / ".relay"


def _path(root: Path, thread_id: str) -> Path:
    return root / THREADS / f"{file_key(thread_id)}.json"


def load_threads(root: Path) -> dict[str, Thread]:
    """Read every thread file. A file that is unreadable or of another schema is skipped."""
    found: dict[str, Thread] = {}
    for path in (root / THREADS).glob("*.json"):
        try:
            thread = thread_from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, RelayError) as error:
            LOG.warning("skipped %s: %s", path.name, error)
            continue
        found[thread.thread] = thread
    return found


def save_thread(root: Path, thread: Thread) -> None:
    path = _path(root, thread.thread)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(to_json(thread), indent=2), encoding="utf-8")
    temporary.replace(path)  # a rename, so a reader never sees a half-written file


def delete_thread(root: Path, thread_id: str) -> None:
    _path(root, thread_id).unlink(missing_ok=True)
