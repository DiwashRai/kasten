"""The command line: arguments turned into one typed command per verb."""

import argparse
from dataclasses import dataclass
from typing import Literal

from relay.forms import Json
from relay.thread import TASK_STATUSES

DEFAULT_TIMEOUT = 100.0  # seconds; below the two-minute default limit of a T3 Code tool call

EPILOG = """\
examples:
  relay plan --title "Search PoC" --stage "Ingest|fetch issues|drop PRs" --stage "Index|embed"
  relay task 1.1 active
  relay task 1.1 done --note "2,104 issues"
  relay task add "write meta table" --stage 2
  relay ask form.json --env-file .env
  relay wait service-env --env-file .env
  relay render          then pass the printed path to html_render
The thread is --thread, else RELAY_THREAD, else T3CODE_THREAD_ID."""


@dataclass(frozen=True)
class Post:
    """A status verb: one event for the daemon. Never fails the agent's work."""

    thread: str | None
    event: dict[str, Json]


@dataclass(frozen=True)
class Ask:
    thread: str | None
    form_path: str
    wait: bool
    timeout: float
    env_file: str | None


@dataclass(frozen=True)
class Wait:
    thread: str | None
    form_id: str
    timeout: float
    env_file: str | None


@dataclass(frozen=True)
class Simple:
    thread: str | None
    verb: Literal["render", "status", "stop", "daemon"]


type Command = Post | Ask | Wait | Simple


def _parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--thread", default=argparse.SUPPRESS, help="thread id to act on")
    waiting = argparse.ArgumentParser(add_help=False)
    waiting.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds to wait")
    waiting.add_argument("--env-file", help="write the answer to this KEY=value file")

    parser = argparse.ArgumentParser(
        prog="relay",
        description="Live status pages and input forms for agent threads.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--thread", default=None, help="thread id to act on")
    verbs = parser.add_subparsers(dest="verb", required=True)

    plan = verbs.add_parser("plan", parents=[shared], help="set the stages and their tasks")
    plan.add_argument("--title", default="", help="a name for the thread")
    plan.add_argument("--stage", action="append", required=True, help='"Title|task|task"')
    plan.add_argument("--replace", action="store_true", help="replace a plan in progress")

    task = verbs.add_parser("task", parents=[shared], help="set a task's status, or add a task")
    task.add_argument("ref", help='a task such as 2.1, or the word "add"')
    task.add_argument("value", help=f"one of {', '.join(TASK_STATUSES)}; or the new task's title")
    task.add_argument("--note", default=None, help="a short note shown under the task")
    task.add_argument("--stage", type=int, default=None, help="stage to add to (default: last)")

    block = verbs.add_parser("block", parents=[shared], help="mark the thread blocked")
    block.add_argument("reason")
    verbs.add_parser("unblock", parents=[shared], help="clear the blocked mark")
    verbs.add_parser("finish", parents=[shared], help="mark the thread's work as over")

    ask = verbs.add_parser("ask", parents=[shared, waiting], help="open a form and wait")
    ask.add_argument("form", help="path to the form's JSON, or - for standard input")
    ask.add_argument("--no-wait", action="store_true", help="open the form and return at once")
    wait = verbs.add_parser("wait", parents=[shared, waiting], help="collect a form's answer")
    wait.add_argument("id", help="the form's id")

    verbs.add_parser("render", parents=[shared], help="write the page; prints its path and URL")
    verbs.add_parser("status", parents=[shared], help="show the daemon and this thread")
    verbs.add_parser("stop", help="stop the daemon")
    verbs.add_parser("daemon", help="run the daemon in this process")
    return parser


def _task(
    parser: argparse.ArgumentParser, ref: str, value: str, note: str | None
) -> dict[str, Json]:
    if value not in TASK_STATUSES:
        parser.error(f"status must be one of {', '.join(TASK_STATUSES)}, not {value!r}")
    return {"op": "task", "ref": ref, "status": value, "note": note}


def parse(argv: list[str]) -> Command:
    """Turn arguments into a command. Wrong arguments print usage and exit with code 2."""
    parser = _parser()
    args = parser.parse_args(argv)
    thread: str | None = args.thread
    match args.verb:
        case "plan":
            stages: list[Json] = list(args.stage)
            event: dict[str, Json] = {
                "title": args.title,
                "stages": stages,
                "replace": args.replace,
            }
            return Post(thread, {"op": "plan", **event})
        case "task" if args.ref == "add":
            return Post(thread, {"op": "add", "title": args.value, "stage": args.stage})
        case "task":
            return Post(thread, _task(parser, args.ref, args.value, args.note))
        case "block":
            return Post(thread, {"op": "block", "reason": args.reason})
        case "unblock" | "finish" as verb:
            return Post(thread, {"op": verb})
        case "ask":
            return Ask(thread, args.form, not args.no_wait, args.timeout, args.env_file)
        case "wait":
            return Wait(thread, args.id, args.timeout, args.env_file)
        case "render" | "status" | "stop" | "daemon" as verb:
            return Simple(thread, verb)
        case other:
            parser.error(f"unknown verb {other!r}")
