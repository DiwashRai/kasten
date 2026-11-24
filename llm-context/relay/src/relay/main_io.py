"""The `relay` command: reads arguments and the environment, runs one command, sets the exit code."""

import json
import os
import sys
from pathlib import Path

from relay.cli import Ask, Command, Post, Simple, Wait, parse
from relay.client_io import call, ensure_daemon, fetch, health, stop_daemon, url
from relay.daemon_io import DEFAULT_PORT, serve
from relay.errors import (
    EXIT_NO_ANSWER,
    EXIT_NO_DAEMON,
    EXIT_OK,
    EXIT_USAGE,
    DaemonUnreachable,
    NoAnswerYet,
    RelayError,
)
from relay.forms import Json, env_text
from relay.store_io import home
from relay.thread import describe, file_key, resolve_thread_id, thread_from_json

PAGES = "pages"


def _post(root: Path, port: int, thread_id: str, event: dict[str, Json]) -> Json:
    ensure_daemon(root, port)
    return call(root, "/event", {"thread": thread_id}, {**event, "folder": Path.cwd().name})


def _collect(
    root: Path, thread_id: str, form_id: str, timeout: float, env_file: str | None
) -> None:
    """Wait for a form's answer, hand it over, then tell the daemon to forget the values."""
    params = {"thread": thread_id, "id": form_id}
    try:
        reply = fetch(root, "/wait", {**params, "timeout": str(timeout)}, timeout=timeout + 10)
    except NoAnswerYet:
        raise NoAnswerYet(
            f"no answer to {form_id!r} yet. End the turn, ask the user to fill in the form and "
            f"say continue, then run: relay wait {form_id}"
        ) from None
    values = {str(name): str(value) for name, value in json.loads(reply).items()}
    if env_file:
        path = Path(env_file)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(env_text(existing, values), encoding="utf-8")
        print(f"wrote {', '.join(values)} to {path}")
    else:
        print(json.dumps(values))
    call(root, "/ack", params, {})


def _form(path: str) -> Json:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        return json.loads(text)
    except (OSError, ValueError) as error:
        raise RelayError(f"cannot read the form from {path}: {error}") from None


def _render(root: Path, port: int, thread_id: str) -> None:
    _post(root, port, thread_id, {"op": "render"})
    html = fetch(root, "/view", {"thread": thread_id, "inline": "1"})
    path = root / PAGES / f"{file_key(thread_id)}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(html)
    print(f"page: {path}")
    print(f"url:  {url(root, '/view', {'thread': thread_id})}")


def _status(root: Path, port: int, thread: str | None, env: dict[str, str]) -> None:
    running = health(port)
    print(f"daemon: version {running[0]} on port {port}" if running else "daemon: not running")
    try:
        thread_id = resolve_thread_id(thread, env)
    except RelayError as error:
        print(f"thread: {error}")
        return
    print(f"thread: {thread_id}")
    if running:
        state = call(root, "/state", {"thread": thread_id})
        if isinstance(state, dict):
            form = state.get("form")
            asked = f"{form.get('id')} ({form.get('state')})" if isinstance(form, dict) else "none"
            print(f"status: {state.get('status')}; form: {asked}")
        print(f"all threads: {url(root, '/', {})}")


def run(command: Command, root: Path, port: int, env: dict[str, str]) -> int:
    """Carry out one command. Raises RelayError and its subtypes; `main` maps them to exit codes."""
    match command:
        case Simple(verb="daemon"):
            return serve(root, port)
        case Simple(verb="stop"):
            print("daemon stopped" if stop_daemon(root, port) else "daemon: not running")
        case Simple(thread=thread, verb="status"):
            _status(root, port, thread, env)
        case Simple(thread=thread, verb="render"):
            _render(root, port, resolve_thread_id(thread, env))
        case Post(thread=thread, event=event):
            state = _post(root, port, resolve_thread_id(thread, env), event)
            print(describe(thread_from_json(state), event))
        case Ask(thread=thread, form_path=form_path, wait=wait, timeout=timeout, env_file=env_file):
            thread_id = resolve_thread_id(thread, env)
            form = _form(form_path)
            form_id = form.get("id") if isinstance(form, dict) else None
            _post(root, port, thread_id, {"op": "ask", "form": form})
            if wait:
                _collect(root, thread_id, str(form_id), timeout, env_file)
            else:
                print(f"form {form_id} is open; collect it with: relay wait {form_id}")
        case Wait(thread=thread, form_id=form_id, timeout=timeout, env_file=env_file):
            thread_id = resolve_thread_id(thread, env)
            ensure_daemon(root, port)
            _collect(root, thread_id, form_id, timeout, env_file)
    return EXIT_OK


def main() -> int:
    command = parse(sys.argv[1:])
    env = dict(os.environ)
    port = int(env.get("RELAY_PORT", DEFAULT_PORT))
    try:
        return run(command, home(env), port, env)
    except NoAnswerYet as error:
        print(f"relay: {error}")
        return EXIT_NO_ANSWER
    except DaemonUnreachable as error:
        if isinstance(command, (Post, Simple)):
            # A status update must never stop the agent's real work.
            print(f"relay: warning: {error}; carrying on without it", file=sys.stderr)
            return EXIT_OK
        print(f"relay: {error}. Ask in chat instead.", file=sys.stderr)
        return EXIT_NO_DAEMON
    except RelayError as error:
        print(f"relay: {error}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
