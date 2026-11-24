"""The CLI's side of the connection: calling the daemon, and starting it when needed."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from relay import VERSION
from relay.daemon_io import HOST, SERVER_FILE
from relay.errors import DaemonUnreachable, NoAnswerYet, RelayError
from relay.forms import Json

# No proxy: a system proxy on a work machine would otherwise receive calls meant for localhost.
OPENER = build_opener(ProxyHandler({}))
START_SECONDS = 5.0
POLL_SECONDS = 0.1
CALL_SECONDS = 10.0


def _server(root: Path) -> tuple[int, str]:
    try:
        details = json.loads((root / SERVER_FILE).read_text(encoding="utf-8"))
        return int(details["port"]), str(details["token"])
    except (OSError, ValueError, KeyError):
        raise DaemonUnreachable("the Relay daemon is not running") from None


def url(root: Path, path: str, params: dict[str, str]) -> str:
    port, token = _server(root)
    return f"http://{HOST}:{port}{path}?{urlencode({**params, 't': token})}"


def fetch(
    root: Path,
    path: str,
    params: dict[str, str],
    body: Json = None,
    timeout: float = CALL_SECONDS,
) -> bytes:
    """Call the daemon and return the reply's bytes.

    Raises:
        DaemonUnreachable: nothing answered.
        NoAnswerYet: a wait timed out.
        RelayError: the daemon refused the request; the message says why.
    """
    data = None if body is None else json.dumps(body).encode()
    try:
        with OPENER.open(Request(url(root, path, params), data=data), timeout=timeout) as reply:
            return reply.read()
    except HTTPError as error:
        message = json.loads(error.read() or b'""')
        if error.code == 408:
            raise NoAnswerYet(str(message)) from None
        raise RelayError(str(message) or f"HTTP {error.code}") from None
    except (URLError, TimeoutError, ConnectionError):
        raise DaemonUnreachable("the Relay daemon did not answer") from None


def call(root: Path, path: str, params: dict[str, str], body: Json = None) -> Json:
    """Call the daemon and parse its JSON reply. Raises as `fetch` does."""
    return json.loads(fetch(root, path, params, body))


def health(port: int) -> tuple[str, int] | None:
    """The running daemon's version and process id, or None when nothing answers."""
    try:
        with OPENER.open(f"http://{HOST}:{port}/health", timeout=1.0) as reply:
            details = json.loads(reply.read())
            return str(details["version"]), int(details["pid"])
    except (URLError, TimeoutError, ConnectionError, ValueError, KeyError):
        return None


def _until(done: bool, port: int) -> bool:
    """Wait until a daemon answers (`done` False) or stops answering (`done` True)."""
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        if (health(port) is None) == done:
            return True
        time.sleep(POLL_SECONDS)
    return False


def stop_daemon(root: Path, port: int) -> bool:
    """Stop the daemon. Returns False when none was running."""
    running = health(port)
    if running is None:
        return False
    try:
        fetch(root, "/stop", {}, body={})
    except RelayError:
        pass  # an older daemon may not know the token; the process id below still ends it
    if not _until(True, port):
        os.kill(running[1], signal.SIGTERM)
        _until(True, port)
    return True


def _spawn() -> None:
    # Detached, with no inherited pipes, so the daemon outlives the tool call that started it and
    # the tool call returns at once. The daemon writes its own log file.
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [sys.executable, "-m", "relay.main_io", "daemon"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        start_new_session=sys.platform != "win32",
        close_fds=True,
    )


def ensure_daemon(root: Path, port: int) -> None:
    """Make sure a daemon of this version is running, starting or replacing one if needed.

    Raises:
        DaemonUnreachable: the daemon did not come up.
    """
    running = health(port)
    if running and running[0] == VERSION:
        return
    if running:
        stop_daemon(root, port)
    _spawn()
    if not _until(False, port):
        raise DaemonUnreachable(
            f"the Relay daemon did not start on port {port}; see {root / 'daemon.log'}"
        )
