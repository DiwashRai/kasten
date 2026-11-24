"""What the pages show: a template filled with a snapshot, and the rows of the all-threads page."""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from relay.forms import Json
from relay.thread import Thread, failed_count, status_of

BOOT_MARK = "/*BOOT*/null"
QUIET_AFTER = timedelta(minutes=10)
HIDDEN_AFTER = timedelta(hours=24)
DELETED_AFTER = timedelta(days=7)
SHORT_ID = 12

type RowStatus = Literal["needs_input", "blocked", "running", "quiet", "done"]
ROW_ORDER: tuple[RowStatus, ...] = ("needs_input", "blocked", "running", "quiet", "done")


@dataclass(frozen=True)
class Row:
    thread: str
    title: str
    status: RowStatus
    question: str
    done: int
    total: int
    failed: int
    updated: str


def fill(template: str, boot: dict[str, Json]) -> str:
    """Put the page's starting data into a template.

    "</" is escaped so a title holding "</script>" cannot end the script block.
    """
    return template.replace(BOOT_MARK, json.dumps(boot).replace("</", "<\\/"))


def title_of(thread: Thread) -> str:
    return thread.title or thread.folder or thread.thread[:SHORT_ID]


def age(thread: Thread, now: datetime) -> timedelta:
    """Time since the thread last changed. A thread with no time yet counts as new."""
    return now - datetime.fromisoformat(thread.updated) if thread.updated else timedelta(0)


def expired(thread: Thread, now: datetime) -> bool:
    """True once the thread's file is old enough to delete."""
    return age(thread, now) > DELETED_AFTER


def _row_status(thread: Thread, now: datetime) -> RowStatus:
    status = status_of(thread)
    return "quiet" if status == "running" and age(thread, now) > QUIET_AFTER else status


def rows(threads: list[Thread], now: datetime) -> list[Row]:
    """The all-threads page: waiting threads first, newest first within a status."""
    shown = [thread for thread in threads if age(thread, now) <= HIDDEN_AFTER]
    built = [
        Row(
            thread=thread.thread,
            title=title_of(thread),
            status=_row_status(thread, now),
            question=thread.form.title if thread.form and thread.form.state == "open" else "",
            done=sum(task.status == "done" for stage in thread.stages for task in stage.tasks),
            total=sum(len(stage.tasks) for stage in thread.stages),
            failed=failed_count(thread),
            updated=thread.updated,
        )
        for thread in shown
    ]
    newest_first = sorted(built, key=lambda row: row.updated, reverse=True)
    return sorted(newest_first, key=lambda row: ROW_ORDER.index(row.status))
