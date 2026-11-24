"""A thread's state: stages of tasks and the form in play, with the rules that change them."""

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from typing import Literal

from relay.errors import RelayError
from relay.forms import (
    Form,
    Json,
    answer_form,
    collect_form,
    form_from_json,
    open_form,
    parse_form,
    save_draft,
    without_values,
)

SCHEMA = 1
TASK_STATUSES = ("pending", "active", "done", "failed")
THREAD_VARIABLES = ("RELAY_THREAD", "T3CODE_THREAD_ID")
KEY_LENGTH = 16

type TaskStatus = Literal["pending", "active", "done", "failed"]
type Status = Literal["needs_input", "blocked", "done", "running"]

# A task reference such as "2.3" (stage 2, task 3), or "3" when the plan has one stage.
REFERENCE = re.compile(r"(?:(\d+)\.)?(\d+)")


@dataclass(frozen=True)
class Task:
    title: str
    status: TaskStatus = "pending"
    note: str = ""


@dataclass(frozen=True)
class Stage:
    title: str
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class Thread:
    thread: str
    title: str = ""
    folder: str = ""
    stages: tuple[Stage, ...] = ()
    form: Form | None = None
    blocked: str = ""
    finished: bool = False
    updated: str = ""
    view: int = 0
    schema: int = SCHEMA


def _task(data: Json) -> Task:
    match data:
        case {
            "title": str(title),
            "status": "pending" | "active" | "done" | "failed" as status,
            "note": str(note),
        }:
            return Task(title, status, note)
        case _:
            raise RelayError("a stored task needs a title, a status and a note")


def _stage(data: Json) -> Stage:
    match data:
        case {"title": str(title), "tasks": list(tasks)}:
            return Stage(title, tuple(_task(item) for item in tasks))
        case _:
            raise RelayError("a stored stage needs a title and tasks")


def thread_from_json(data: Json) -> Thread:
    """Read a stored thread.

    Raises:
        RelayError: the data is not a thread of this schema.
    """
    match data:
        case {
            "schema": int(schema),
            "thread": str(thread),
            "title": str(title),
            "folder": str(folder),
            "stages": list(stages),
            "blocked": str(blocked),
            "finished": bool(finished),
            "updated": str(updated),
            "view": int(view),
        } if schema == SCHEMA:
            form = data.get("form")
            return Thread(
                thread=thread,
                title=title,
                folder=folder,
                stages=tuple(_stage(item) for item in stages),
                form=None if form is None else form_from_json(form),
                blocked=blocked,
                finished=finished,
                updated=updated,
                view=view,
            )
        case _:
            raise RelayError(f"not a thread of schema {SCHEMA}")


def to_json(thread: Thread) -> dict[str, Json]:
    """The thread as stored on disk, answer values included."""
    return asdict(thread)


def page_json(thread: Thread) -> dict[str, Json]:
    """The thread as a page or the CLI may see it, with the worked-out status."""
    shown = asdict(replace(thread, form=without_values(thread.form)))
    return {**shown, "status": status_of(thread), "failed": failed_count(thread)}


def parse_stage(text: str) -> Stage:
    """Read "Title|task|task" as a stage of pending tasks.

    Raises:
        RelayError: the title or every task is missing.
    """
    title, *tasks = [part.strip() for part in text.split("|")]
    if not title or not tasks or not all(tasks):
        raise RelayError(f'a stage needs a title and tasks, like "Build|compile|test": {text!r}')
    return Stage(title, tuple(Task(task) for task in tasks))


def _tasks(thread: Thread) -> list[Task]:
    return [task for stage in thread.stages for task in stage.tasks]


def status_of(thread: Thread) -> Status:
    if thread.form and thread.form.state == "open":
        return "needs_input"
    if thread.blocked:
        return "blocked"
    if thread.finished:
        return "done"
    return "running"


def failed_count(thread: Thread) -> int:
    return sum(task.status == "failed" for task in _tasks(thread))


def set_plan(thread: Thread, title: str, stages: tuple[Stage, ...], force: bool) -> Thread:
    """Replace the stages. A plan with work under way is kept unless `force` is set.

    Raises:
        RelayError: the plan is in progress and `force` is not set.
    """
    if not force and any(task.status != "pending" for task in _tasks(thread)):
        raise RelayError("a plan is in progress; pass --replace to replace it")
    if not stages:
        raise RelayError("a plan needs at least one stage")
    return replace(thread, title=title or thread.title, stages=stages, finished=False)


def _valid(thread: Thread) -> str:
    one = len(thread.stages) == 1
    spans = [
        f"1-{len(stage.tasks)}" if one else f"{number}.1-{number}.{len(stage.tasks)}"
        for number, stage in enumerate(thread.stages, start=1)
    ]
    return ", ".join(spans)


def locate(thread: Thread, ref: str) -> tuple[int, int]:
    """Find the stage and task positions (from 0) of a reference such as "2.3".

    Raises:
        RelayError: there is no plan, or the reference names no task.
    """
    if not thread.stages:
        raise RelayError('no plan yet; set one with: relay plan --stage "Title|task|task"')
    found = REFERENCE.fullmatch(ref)
    if not found or (found[1] is None and len(thread.stages) > 1):
        raise RelayError(f"bad task reference {ref!r}; valid: {_valid(thread)}")
    stage, task = int(found[1] or 1) - 1, int(found[2]) - 1
    if not (0 <= stage < len(thread.stages) and 0 <= task < len(thread.stages[stage].tasks)):
        raise RelayError(f"no task {ref}; valid: {_valid(thread)}")
    return stage, task


def _with_stage(thread: Thread, position: int, stage: Stage) -> Thread:
    stages = (*thread.stages[:position], stage, *thread.stages[position + 1 :])
    return replace(thread, stages=stages, finished=False)


def set_task(thread: Thread, ref: str, status: TaskStatus, note: str | None) -> Thread:
    """Set one task's status. The note is kept unless a new one is given.

    Raises:
        RelayError: the reference names no task.
    """
    at_stage, at_task = locate(thread, ref)
    stage = thread.stages[at_stage]
    old = stage.tasks[at_task]
    new = Task(old.title, status, old.note if note is None else note)
    tasks = (*stage.tasks[:at_task], new, *stage.tasks[at_task + 1 :])
    return _with_stage(thread, at_stage, Stage(stage.title, tasks))


def add_task(thread: Thread, title: str, stage_number: int | None) -> Thread:
    """Append a task to a stage (counted from 1), or to the last stage.

    Raises:
        RelayError: there is no plan, or no such stage.
    """
    if not thread.stages:
        raise RelayError('no plan yet; set one with: relay plan --stage "Title|task|task"')
    position = len(thread.stages) - 1 if stage_number is None else stage_number - 1
    if not 0 <= position < len(thread.stages):
        raise RelayError(f"no stage {stage_number}; the plan has {len(thread.stages)}")
    stage = thread.stages[position]
    return _with_stage(thread, position, Stage(stage.title, (*stage.tasks, Task(title))))


def _reference(thread: Thread, stage: int, task: int) -> str:
    return f"{task + 1}" if len(thread.stages) == 1 else f"{stage + 1}.{task + 1}"


def next_line(thread: Thread) -> str:
    """Name the next pending task, so the agent need not remember numbers."""
    pending = [
        (at_stage, at_task)
        for at_stage, stage in enumerate(thread.stages)
        for at_task, task in enumerate(stage.tasks)
        if task.status == "pending"
    ]
    if pending:
        at_stage, at_task = pending[0]
        title = thread.stages[at_stage].tasks[at_task].title
        return f"next {_reference(thread, at_stage, at_task)}: {title}"
    done = all(task.status == "done" for task in _tasks(thread))
    return "all tasks done" if done else "no pending tasks"


def describe(thread: Thread, event: Json) -> str:
    """The one line the CLI prints after an event: what changed and what is next."""
    match event:
        case {"op": "task", "ref": str(ref)}:
            at_stage, at_task = locate(thread, ref)
            task = thread.stages[at_stage].tasks[at_task]
            changed = f"{_reference(thread, at_stage, at_task)} {task.status}: {task.title}"
            return f"{changed} | {next_line(thread)}"
        case {"op": "plan"} | {"op": "add"}:
            count = f"{len(_tasks(thread))} tasks in {len(thread.stages)} stages"
            return f"{count} | {next_line(thread)}"
        case _:
            return status_of(thread)


def apply(thread: Thread, event: Json, now: str) -> Thread:
    """Return the thread after one event sent by the CLI.

    Raises:
        RelayError: the event is malformed or the rules refuse it.
    """
    match event:
        case {"folder": str(folder)}:
            thread = replace(thread, folder=folder)
        case _:
            pass
    match event:
        case {"op": "plan", "title": str(title), "stages": list(stages), "replace": bool(force)}:
            parsed = tuple(parse_stage(stage) for stage in stages if isinstance(stage, str))
            changed = set_plan(thread, title, parsed, force)
        case {
            "op": "task",
            "ref": str(ref),
            "status": "pending" | "active" | "done" | "failed" as status,
            "note": str() | None as note,
        }:
            changed = set_task(thread, ref, status, note)
        case {"op": "add", "title": str(title), "stage": int() | None as stage}:
            changed = add_task(thread, title, stage)
        case {"op": "block", "reason": str(reason)}:
            changed = replace(thread, blocked=reason)
        case {"op": "unblock"}:
            changed = replace(thread, blocked="")
        case {"op": "finish"}:
            changed = replace(thread, finished=True)
        case {"op": "render"}:
            changed = replace(thread, view=thread.view + 1)
        case {"op": "ask", "form": form}:
            changed = replace(thread, form=open_form(thread.form, parse_form(form)))
        case _:
            raise RelayError(f"unknown event: {event!r}")
    return replace(changed, updated=now)


def _form(thread: Thread, form_id: str) -> Form:
    if thread.form is None or thread.form.id != form_id:
        current = "none" if thread.form is None else repr(thread.form.id)
        raise RelayError(f"no form {form_id!r} on this thread; the current form is {current}")
    return thread.form


def with_draft(thread: Thread, form_id: str, values: dict[str, str]) -> Thread:
    """Keep half-typed values. Raises RelayError when the form is not the thread's."""
    return replace(thread, form=save_draft(_form(thread, form_id), values))


def with_answer(
    thread: Thread, form_id: str, values: dict[str, str], now: str, waiter: bool
) -> Thread:
    """Store a user's answer. Raises RelayError when the form or a value is refused."""
    answered = answer_form(_form(thread, form_id), values, now, waiter)
    return replace(thread, form=answered, updated=now)


def answer_of(thread: Thread, form_id: str) -> dict[str, str] | None:
    """The stored answer, or None while the form is open. Raises RelayError on a wrong id."""
    form = _form(thread, form_id)
    if form.state == "collected":
        raise RelayError(f"the answer to {form_id!r} was already collected")
    return form.values if form.state == "answered" else None


def with_collected(thread: Thread, form_id: str) -> Thread:
    """Forget an answer's values after delivery. Raises RelayError on a wrong id."""
    return replace(thread, form=collect_form(_form(thread, form_id)))


def resolve_thread_id(explicit: str | None, env: dict[str, str]) -> str:
    """Pick the thread id: the explicit one, then RELAY_THREAD, then T3CODE_THREAD_ID.

    Raises:
        RelayError: none of them is set.
    """
    found = explicit or next((env[name] for name in THREAD_VARIABLES if env.get(name)), None)
    if not found:
        raise RelayError(f"no thread id: pass --thread, or set {' or '.join(THREAD_VARIABLES)}")
    return found


def file_key(thread_id: str) -> str:
    """A short name safe for a file. A delegate's thread id holds ":" and "%"."""
    return hashlib.sha256(thread_id.encode()).hexdigest()[:KEY_LENGTH]
