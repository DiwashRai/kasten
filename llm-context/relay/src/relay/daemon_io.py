"""The daemon: one HTTP server on 127.0.0.1 that owns thread state and serves the pages."""

import json
import logging
import os
import secrets
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from relay import VERSION
from relay.errors import RelayError
from relay.forms import Json
from relay.pages import expired, fill, rows
from relay.store_io import delete_thread, load_threads, save_thread
from relay.thread import (
    SCHEMA,
    Thread,
    answer_of,
    apply,
    page_json,
    with_answer,
    with_collected,
    with_draft,
)

LOG = logging.getLogger("relay")
HOST = "127.0.0.1"
DEFAULT_PORT = 47615
SERVER_FILE = "server.json"
TEMPLATES = Path(__file__).parent / "templates"
KEEP_ALIVE_SECONDS = 15
MAX_WAIT_SECONDS = 3600.0
LOG_BYTES = 1_000_000
LOG_FILES = 3


def now() -> datetime:
    return datetime.now(UTC)


class Hub:
    """Every thread's state, one lock, and the count of agents waiting on each form."""

    def __init__(self, root: Path, token: str, port: int) -> None:
        self.root = root
        self.token = token
        self.base = f"http://{HOST}:{port}"
        self.changed = threading.Condition()
        self.version = 0
        self.waiters: Counter[tuple[str, str]] = Counter()
        self.threads = load_threads(root)
        self.sweep()

    def get(self, thread_id: str) -> Thread:
        return self.threads.get(thread_id) or Thread(thread_id)

    def change(self, thread_id: str, update: Callable[[Thread], Thread]) -> Thread:
        """Apply a change, write the thread's file and wake every listener."""
        with self.changed:
            thread = update(self.get(thread_id))
            save_thread(self.root, thread)
            self.threads[thread_id] = thread
            self.version += 1
            self.changed.notify_all()
            return thread

    def sweep(self) -> None:
        """Delete the files of threads that have not changed for a week."""
        with self.changed:
            for thread in [t for t in self.threads.values() if expired(t, now())]:
                delete_thread(self.root, thread.thread)
                del self.threads[thread.thread]


class Server(ThreadingHTTPServer):
    # On Windows the default lets a second daemon bind the same port. Off, the bind is the lock.
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, port: int, hub: Hub) -> None:
        super().__init__((HOST, port), Handler)
        self.hub = hub


def _values(body: Json) -> tuple[str, dict[str, str]]:
    match body:
        case {"id": str(form_id), "values": dict(values)}:
            return form_id, {name: str(value) for name, value in values.items()}
        case _:
            raise RelayError("expected an object with id and values")


class Handler(BaseHTTPRequestHandler):
    server: Server  # pyright: ignore[reportIncompatibleVariableOverride]

    def log_message(self, format: str, *args: object) -> None:
        # The path only: the query string holds the token.
        LOG.info("%s %s %s", self.command, urlparse(self.path).path, args[1] if args[1:] else "")

    def reply(self, code: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        # An inline frame has no origin, so the token is the gate, not the origin.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def reply_json(self, code: int, data: Json) -> None:
        self.reply(code, json.dumps(data).encode())

    def reply_page(self, template: str, boot: dict[str, Json]) -> None:
        html = fill((TEMPLATES / template).read_text(encoding="utf-8"), boot)
        self.reply(200, html.encode(), "text/html; charset=utf-8")

    def query(self) -> dict[str, str]:
        """The query string, after the token check. Raises RelayError on a bad token."""
        query = {name: values[0] for name, values in parse_qs(urlparse(self.path).query).items()}
        if not secrets.compare_digest(query.get("t", ""), self.server.hub.token):
            raise RelayError("bad token")
        return query

    def thread_id(self, query: dict[str, str]) -> str:
        if not query.get("thread"):
            raise RelayError("no thread given")
        return query["thread"]

    def body(self) -> Json:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self) -> None:
        hub = self.server.hub
        try:
            path = urlparse(self.path).path
            if path == "/health":
                self.reply_json(200, {"version": VERSION, "pid": os.getpid()})
                return
            query = self.query()
            boot: dict[str, Json] = {"base": hub.base, "token": hub.token, "schema": SCHEMA}
            match path:
                case "/events":
                    self.events(self.thread_id(query))
                case "/wait":
                    self.wait(self.thread_id(query), query["id"], float(query["timeout"]))
                case "/state":
                    self.reply_json(200, page_json(hub.get(self.thread_id(query))))
                case "/view":
                    state = page_json(hub.get(self.thread_id(query)))
                    pinned = query.get("inline") != "1"
                    self.reply_page("thread.html", {**boot, "state": state, "pinned": pinned})
                case "/":
                    self.reply_page("threads.html", boot)
                case "/threads":
                    hub.sweep()
                    listed = rows(list(hub.threads.values()), now())
                    self.reply_json(200, [asdict(row) for row in listed])
                case _:
                    self.reply_json(404, "not found")
        except (RelayError, KeyError, ValueError) as error:
            self.reply_json(400, str(error))

    def do_POST(self) -> None:
        hub = self.server.hub
        try:
            query = self.query()
            path = urlparse(self.path).path
            if path == "/stop":
                self.reply_json(200, "stopping")
                threading.Thread(target=self.server.shutdown).start()
                return
            thread_id, body, stamp = self.thread_id(query), self.body(), now().isoformat()
            match path:
                case "/event":
                    changed = hub.change(thread_id, lambda t: apply(t, body, stamp))
                case "/draft":
                    form_id, values = _values(body)
                    changed = hub.change(thread_id, lambda t: with_draft(t, form_id, values))
                case "/answer":
                    form_id, values = _values(body)
                    with hub.changed:
                        waiter = hub.waiters[(thread_id, form_id)] > 0
                        changed = hub.change(
                            thread_id, lambda t: with_answer(t, form_id, values, stamp, waiter)
                        )
                case "/ack":
                    changed = hub.change(thread_id, lambda t: with_collected(t, query["id"]))
                case _:
                    self.reply_json(404, "not found")
                    return
            self.reply_json(200, page_json(changed))
        except (RelayError, KeyError, ValueError) as error:
            self.reply_json(400, str(error))

    def wait(self, thread_id: str, form_id: str, timeout: float) -> None:
        """Hold the call until the form is answered or the time runs out."""
        hub, key = self.server.hub, (thread_id, form_id)
        with hub.changed:
            answer_of(hub.get(thread_id), form_id)  # refuses a wrong id before any waiting
            hub.waiters[key] += 1
            try:
                hub.changed.wait_for(
                    lambda: answer_of(hub.get(thread_id), form_id) is not None,
                    timeout=min(timeout, MAX_WAIT_SECONDS),
                )
                values = answer_of(hub.get(thread_id), form_id)
            finally:
                hub.waiters[key] -= 1
        if values is None:
            self.reply_json(408, "no answer yet")
        else:
            self.reply_json(200, dict(values))

    def events(self, thread_id: str) -> None:
        """Server-sent events: the thread's state on connect and after every change."""
        hub = self.server.hub
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        seen = -1
        try:
            while True:
                with hub.changed:
                    hub.changed.wait_for(
                        lambda seen=seen: hub.version != seen, timeout=KEEP_ALIVE_SECONDS
                    )
                    changed, seen = hub.version != seen, hub.version
                    state = page_json(hub.get(thread_id))
                message = f"data: {json.dumps(state)}\n\n" if changed else ": keep-alive\n\n"
                self.wfile.write(message.encode())
                self.wfile.flush()
        except OSError:
            return  # the page went away


def _token(root: Path) -> str:
    """Reuse the stored token so pages rendered before a restart keep working."""
    try:
        return json.loads((root / SERVER_FILE).read_text(encoding="utf-8"))["token"]
    except (OSError, ValueError, KeyError):
        return secrets.token_urlsafe(16)


def serve(root: Path, port: int) -> int:
    """Run the daemon until it is told to stop. Returns 1 when the port is taken."""
    root.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(root / "daemon.log", maxBytes=LOG_BYTES, backupCount=LOG_FILES)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    token = _token(root)
    try:
        server = Server(port, Hub(root, token, port))
    except OSError as error:
        LOG.error("cannot listen on port %s: %s", port, error)
        return 1
    # Written only after the bind, so the file always describes the daemon that holds the port.
    details = {"port": port, "token": token, "pid": os.getpid(), "version": VERSION}
    (root / SERVER_FILE).write_text(json.dumps(details), encoding="utf-8")
    LOG.info("relay %s listening on %s:%s", VERSION, HOST, port)
    server.serve_forever()
    LOG.info("stopped")
    return 0
