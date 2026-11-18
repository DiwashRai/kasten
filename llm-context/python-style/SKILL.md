---
name: python-style
description:
  "Use when writing, editing, or reviewing Python code. Python written as a statically-typed
  language: full type hints, dataclasses, enums and literal types, `match`, one error type per way
  of handling. Covers the workflow, the project layout and the style guidelines. Useful for building
  services, tools, MCP servers."
---

# python

Write Python as a statically-typed language: type hints on everything, dataclasses for data, enums
and `Literal` for fixed sets, `X | None`, generics.

Target the Python version the project declares (`requires-python`); in a new project with a free
choice, use 3.12 or later. The examples use 3.12 syntax. On an older version every guideline still
applies, written with that version's equivalent:

- **Below 3.12:** `type Job = A | B` becomes `Job: TypeAlias = A | B`, and `def latest[T](...)`
  becomes a `TypeVar`.
- **Below 3.11:** `assert_never`, `Self` and `StrEnum` come from `typing_extensions`, or
  `class Colour(str, Enum)` replaces `StrEnum`.
- **Below 3.10:** `match` becomes an `if`/`elif` chain on the type that ends in a raise, so a new
  variant still fails loudly. `X | None` in annotations needs `from __future__ import annotations`.

Write it in a functional style: comprehensions instead of loops that mutate an accumulator, and
`match` instead of `if` chains. Errors are raised as exceptions; don't return sentinel values or
error fields.

**ALWAYS follow the [Style guidelines](#style-guidelines)**, in new code and in edits.

## Layout

**ALWAYS read [layout.md](layout.md) before creating, moving or splitting a file.** It says where
code goes and what each file may do. In short: every file is pure (no I/O, environment, clock or
randomness) unless `pyproject.toml` lists it as impure, and impure files stay thin.

## Workflow

```bash
uv run pytest                    # run every test
uv run ruff format               # canonicalize the project's formatting
uv run complexipy src            # complexity per function
uv run just check                # format, lint, types and the layout rules
uv run just health               # length, complexity, cohesion, fan-out and comments
```

`just check` and `just health` exist once the project is set up as [setup.md](setup.md) describes.
In a new project, do that setup first. Never loosen the checks or suppress one with a comment.

**Workflow: sketch → `uv run pytest` constantly → `uv run complexipy src` → `uv run ruff format`
when a feature is done. `just check` must pass before every commit.**

**Check code quality as you go, not just at the end.** Run `uv run complexipy src` each time you
finish a function or a piece of a feature, and look for anything that stands out: a function far
more complex, more nested, or longer than the rest. Run `uv run just health` when a feature is done
and look the same way at long files, modules whose functions fall into unrelated groups, modules
that import many others, and heavy commenting. Simplify those while the code is fresh, keeping the
tests passing. Don't hill-climb the numbers: the metric points at code worth a second look, and it
isn't a score to lower. Splitting a function or moving logic around just to shrink a metric makes
the code worse. `uv run complexipy --help` lists the options.

## Style guidelines

ALWAYS follow these guidelines. Each entry shows a bad form and a good form.

Entries 14, 18, and 22 add structure. Apply them where the structure removes duplication or encodes
an invariant the program relies on, not to one-off code.

### 1. Name repeated values

Repeated literals drift apart, and readers can't tell which ones are the same.

Bad:

```python
def page(xs: list[str]) -> list[str]:
    return xs[:25]


def is_full(xs: list[str]) -> bool:
    return len(xs) >= 25
```

Good:

```python
PAGE_SIZE = 25


def page(xs: list[str]) -> list[str]:
    return xs[:PAGE_SIZE]


def is_full(xs: list[str]) -> bool:
    return len(xs) >= PAGE_SIZE
```

### 2. Raise instead of returning error fields

Callers can ignore an `error` field. They can't ignore an exception.

Bad:

```python
from dataclasses import dataclass


@dataclass
class Result:
    value: str | None
    error: str | None


def lookup(domain: str) -> Result:
    if "." not in domain:
        return Result(value=None, error="bad domain")
    return Result(value=domain, error=None)
```

Good:

```python
def lookup(domain: str) -> str:
    if "." not in domain:
        raise ValueError("bad domain")
    return domain
```

### 3. Prefer a functional style, especially on containers

Transform lists with comprehensions and generator expressions instead of looping and mutating an
accumulator. Each step says what it does, and there's no state to track.

Bad:

```python
from dataclasses import dataclass


@dataclass
class User:
    name: str
    active: bool


def active_names(users: list[User]) -> list[str]:
    out: list[str] = []
    for u in users:
        if u.active:
            out.append(u.name)
    return out
```

Good:

```python
from dataclasses import dataclass


@dataclass
class User:
    name: str
    active: bool


def active_names(users: list[User]) -> list[str]:
    return [u.name for u in users if u.active]
```

### 4. Use `match` instead of `if` chains

With `assert_never` in the default arm, `match` is exhaustive, so a new variant is a type-checker
error instead of a silent fallthrough.

Bad:

```python
from enum import Enum, auto


class Color(Enum):
    RED = auto()
    GREEN = auto()


def hex_code(c: Color) -> str:
    if c == Color.RED:
        return "#f00"
    else:
        return "#0f0"
```

Good:

```python
from enum import Enum, auto
from typing import assert_never


class Color(Enum):
    RED = auto()
    GREEN = auto()


def hex_code(c: Color) -> str:
    match c:
        case Color.RED:
            return "#f00"
        case Color.GREEN:
            return "#0f0"
        case _:
            assert_never(c)
```

### 5. Use truthiness

`None`, `False`, `0`, and empty strings and collections are falsy.

Bad:

```python
def greet(name: str | None) -> str:
    if name is not None and len(name) > 0:
        return f"hi {name}"
    return "hi"
```

Good:

```python
def greet(name: str | None) -> str:
    if name:
        return f"hi {name}"
    return "hi"
```

### 6. Use f-strings instead of `+`

Bad:

```python
def greet(name: str) -> str:
    return "hi " + name + "!"
```

Good:

```python
def greet(name: str) -> str:
    return f"hi {name}!"
```

### 7. Prefer the standard library to handwritten code

The stdlib is tested, and readers already know what it does. A local helper has to be read to be
trusted.

Bad:

```python
def has_prefix(s: str, prefix: str) -> bool:
    return len(s) >= len(prefix) and s[: len(prefix)] == prefix


def is_secure(url: str) -> bool:
    return has_prefix(url, "https://")
```

Good:

```python
def is_secure(url: str) -> bool:
    return url.startswith("https://")
```

### 8. Say what a regex matches

At minimum, a comment with what it matches and an example. For long regexes, verbose mode
(`re.VERBOSE`) lets you split it up and comment each part.

Bad:

```python
import re


def is_ticket_id(text: str) -> bool:
    return re.fullmatch(r"[A-Z]{2,5}-\d+", text) is not None
```

Good:

```python
import re


def is_ticket_id(text: str) -> bool:
    # A ticket ID like "PROJ-1024": 2 to 5 capital letters, a dash, then digits.
    return re.fullmatch(r"[A-Z]{2,5}-\d+", text) is not None
```

### 9. Use a class instead of a joined string

Bad:

```python
def contact_key(name: str, email: str) -> str:
    return f"{name}|{email}"
```

Good:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ContactKey:
    name: str
    email: str
```

### 10. Use a closed type for fixed sets of values

`str` accepts typos. Use an `Enum` or a `Literal`.

Bad:

```python
from dataclasses import dataclass


@dataclass
class Ticket:
    status: str


def is_open(t: Ticket) -> bool:
    return t.status == "open"
```

Good:

```python
from dataclasses import dataclass
from enum import Enum, auto


class Status(Enum):
    OPEN = auto()
    CLOSED = auto()


@dataclass
class Ticket:
    status: Status


def is_open(t: Ticket) -> bool:
    return t.status == Status.OPEN
```

### 11. Use `Literal` for raw values, enums for concepts

Use a `Literal` when the strings themselves are the data: wire formats, protocol values, or a small
option on one function. Use an `Enum` (or `StrEnum`) for a concept that shows up across the
codebase, or that needs methods. Both work with `match`.

Bad:

```python
from enum import Enum, auto
from typing import assert_never


class Method(Enum):
    GET = auto()
    POST = auto()


def request_line(method: Method, path: str) -> str:
    match method:
        case Method.GET:
            verb = "GET"
        case Method.POST:
            verb = "POST"
        case _:
            assert_never(method)
    return f"{verb} {path}"
```

Good:

```python
from typing import Literal


def request_line(method: Literal["GET", "POST"], path: str) -> str:
    return f"{method} {path}"
```

### 12. One error type per way of handling

An exception class is for the code that catches it; the message is for the person who reads it.
Raise one error type with a message, and add a subclass only where some caller catches it and does
something different.

Bad:

```python
class UserNotFound(Exception):
    def __init__(self, user_id: str) -> None:
        super().__init__(user_id)
        self.user_id = user_id

    def __str__(self) -> str:
        return f"no user with id {self.user_id}"


class MissingAt(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(email)
        self.email = email

    def __str__(self) -> str:
        return f"no @ in {self.email!r}"


class EmptyDomain(Exception):
    def __init__(self, email: str) -> None:
        super().__init__(email)
        self.email = email

    def __str__(self) -> str:
        return f"no domain in {self.email!r}"


def email_domain(emails: dict[str, str], user_id: str) -> str:
    email = emails.get(user_id)
    if not email:
        raise UserNotFound(user_id)
    if "@" not in email:
        raise MissingAt(email)
    domain = email.partition("@")[2]
    if not domain:
        raise EmptyDomain(email)
    return domain
```

Good:

```python
class Failure(Exception):
    """Something went wrong; the message says what."""


class NotFound(Failure):
    """The thing asked for doesn't exist. Callers may fall back."""


def email_domain(emails: dict[str, str], user_id: str) -> str:
    email = emails.get(user_id)
    if not email:
        raise NotFound(f"no user with id {user_id}")
    if "@" not in email:
        raise Failure(f"no @ in {email!r}")
    domain = email.partition("@")[2]
    if not domain:
        raise Failure(f"no domain in {email!r}")
    return domain


def domain_label(emails: dict[str, str], user_id: str) -> str:
    try:
        return email_domain(emails, user_id)
    except NotFound:
        return "unknown"
```

### 13. Use `timedelta` instead of unit arithmetic

Bad:

```python
from datetime import UTC, datetime


def elapsed_ms(start: datetime) -> int:
    return int((datetime.now(UTC).timestamp() - start.timestamp()) * 1000)
```

Good:

```python
from datetime import UTC, datetime, timedelta


def elapsed_ms(start: datetime) -> int:
    return (datetime.now(UTC) - start) // timedelta(milliseconds=1)
```

### 14. Validate in a constructor

Check once, then pass the validated type around.

Bad:

```python
def record(score: float) -> str:
    if score < 0.0 or score > 1.0:
        return "invalid"
    return f"recorded {score}"
```

Good:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    value: float

    def __post_init__(self) -> None:
        if self.value < 0.0 or self.value > 1.0:
            raise ValueError("score out of range")


def record(score: Score) -> str:
    return f"recorded {score.value}"
```

### 15. Raise instead of returning sentinel values

`-1`, `""`, and `None` meaning "failed" look like real values, so callers forget to check.

Bad:

```python
def parse_port(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return -1
```

Good:

```python
def parse_port(text: str) -> int:
    return int(text)
```

### 16. Catch where you can recover

Don't let one bad item fail the whole batch.

Bad:

```python
class NotFound(Exception):
    pass


def lookup(item_id: str) -> str:
    if not item_id:
        raise NotFound(f"no item with id {item_id!r}")
    return item_id


def lookup_all(ids: list[str]) -> list[str]:
    return [lookup(item_id) for item_id in ids]
```

Good:

```python
class NotFound(Exception):
    pass


def lookup(item_id: str) -> str:
    if not item_id:
        raise NotFound(f"no item with id {item_id!r}")
    return item_id


def lookup_all(ids: list[str]) -> list[str]:
    found: list[str] = []
    for item_id in ids:
        try:
            found.append(lookup(item_id))
        except NotFound:
            continue
    return found
```

### 17. Put a function on a class only when it uses that class's data and nothing else

A method that also reads the environment, the clock or the network ties the data to that I/O: the
value can't be built, compared or tested without it. Keep the data class plain, and write the work
as a module-level function that takes the value and what it talks to as arguments.

Bad:

```python
import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class TaskQuery:
    project: str
    limit: int

    def run(self) -> list[str]:
        token = os.environ["TASKS_TOKEN"]
        response = httpx.get(
            "https://tasks.example.com/api/tasks",
            params={"project": self.project, "limit": self.limit},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return [task["title"] for task in response.json()]
```

Good:

```python
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class TaskQuery:
    project: str
    limit: int


def fetch_tasks(query: TaskQuery, client: httpx.Client) -> list[str]:
    params = {"project": query.project, "limit": query.limit}
    response = client.get("/tasks", params=params)
    response.raise_for_status()
    return [task["title"] for task in response.json()]
```

### 18. Implement special methods instead of ad-hoc methods

Implement `__str__`, `__eq__`, `__lt__`, `__hash__`, and the others (or let `@dataclass` generate
them) instead of inventing method names. Then `<`, f-string interpolation, and `sorted` work on your
type like they do on builtins.

Bad:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Version:
    major: int
    minor: int

    def label(self) -> str:
        return f"{self.major}.{self.minor}"

    def older_than(self, other: "Version") -> bool:
        return self.major < other.major or (
            self.major == other.major and self.minor < other.minor
        )
```

Good:

```python
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"
```

### 19. Declare types and raised exceptions on your public API

The exceptions a function raises are part of its contract, like its return type. Python can't check
them, so a change deep in the call tree can add a new exception that reaches your users with no
change to the signature. On functions other modules call, write full type hints and a `Raises:` line
in the docstring. Leave the `Raises:` line off internal helpers.

Bad:

```python
def parse_age(text):
    return int(text)
```

Good:

```python
def parse_age(text: str) -> int:
    """Parse an age in years.

    Raises:
        ValueError: text is not an integer.
    """
    return int(text)
```

### 20. Model states as a union, not optional fields

Optional fields that are "only set when..." allow combinations that make no sense, like a job with
both a result and an error. One class per state makes them unrepresentable.

Bad:

```python
from dataclasses import dataclass


@dataclass
class Job:
    result: str | None = None
    error: str | None = None


def describe(job: Job) -> str:
    if job.error:
        return f"failed: {job.error}"
    elif job.result:
        return f"done: {job.result}"
    else:
        return "running"
```

Good:

```python
from dataclasses import dataclass
from typing import assert_never


@dataclass(frozen=True)
class Running:
    pass


@dataclass(frozen=True)
class Done:
    result: str


@dataclass(frozen=True)
class Failed:
    error: str


type Job = Running | Done | Failed


def describe(job: Job) -> str:
    match job:
        case Running():
            return "running"
        case Done(result):
            return f"done: {result}"
        case Failed(error):
            return f"failed: {error}"
        case _:
            assert_never(job)
```

### 21. Use one generic function instead of copies that differ by output type

Bad:

```python
from dataclasses import dataclass


@dataclass
class Summary:
    text: str


@dataclass
class Outline:
    points: list[str]


def latest_summary(history: list[Summary]) -> Summary:
    if not history:
        raise LookupError("history is empty")
    return history[-1]


def latest_outline(history: list[Outline]) -> Outline:
    if not history:
        raise LookupError("history is empty")
    return history[-1]
```

Good:

```python
def latest[Output](history: list[Output]) -> Output:
    if not history:
        raise LookupError("history is empty")
    return history[-1]
```

### 22. Put per-type behavior in a `Protocol`, not a `match`

When several classes each compute something their own way, give each class a method through a shared
`Protocol`. Each class's logic stays with the class, and a new class is one new implementation
instead of a new arm in every `match`.

Bad:

```python
from dataclasses import dataclass
from typing import assert_never


@dataclass(frozen=True)
class Square:
    side: float


@dataclass(frozen=True)
class Rect:
    width: float
    height: float


def area(shape: Square | Rect) -> float:
    match shape:
        case Square(side):
            return side * side
        case Rect(width, height):
            return width * height
        case _:
            assert_never(shape)
```

Good:

```python
from dataclasses import dataclass
from typing import Protocol


class Shape(Protocol):
    def area(self) -> float: ...


@dataclass(frozen=True)
class Square:
    side: float

    def area(self) -> float:
        return self.side * self.side


@dataclass(frozen=True)
class Rect:
    width: float
    height: float

    def area(self) -> float:
        return self.width * self.height
```

### 23. Exit early instead of nesting

A guard clause that raises or returns handles the missing case up front, and the rest of the
function stays flat.

Bad:

```python
def email_domain(emails: dict[str, str], user_id: str) -> str:
    email = emails.get(user_id)
    if email:
        domain = email.partition("@")[2]
        if domain:
            return domain
        else:
            raise ValueError(f"no domain in {email!r}")
    else:
        raise LookupError(f"no user with id {user_id}")
```

Good:

```python
def email_domain(emails: dict[str, str], user_id: str) -> str:
    email = emails.get(user_id)
    if not email:
        raise LookupError(f"no user with id {user_id}")
    domain = email.partition("@")[2]
    if not domain:
        raise ValueError(f"no domain in {email!r}")
    return domain
```

### 24. Catch the errors you can handle, not everything

`except Exception` also catches failures you didn't plan for. Name the exceptions you can recover
from and let the rest propagate.

Bad:

```python
from pathlib import Path

DEFAULT_SETTINGS = "{}"


def load_settings(path: Path) -> str:
    try:
        return path.read_text()
    except Exception:
        return DEFAULT_SETTINGS
```

Good:

```python
from pathlib import Path

DEFAULT_SETTINGS = "{}"


def load_settings(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return DEFAULT_SETTINGS
```

### 25. Write multi-line strings as indented triple-quoted literals

`textwrap.dedent` strips the common indentation, so the string reads the way it prints.

Bad:

```python
def usage() -> str:
    return "usage: tool [options]\n  -h  show help\n  -v  verbose"
```

Good:

```python
from textwrap import dedent


def usage() -> str:
    return dedent("""\
        usage: tool [options]
          -h  show help
          -v  verbose""")
```

### 26. Raise on invalid input instead of substituting a default

A placeholder like `"untitled"` hides the bug and spreads bad data.

Bad:

```python
from dataclasses import dataclass


@dataclass
class Tag:
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            self.name = "untitled"
```

Good:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Tag:
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("tag name is empty")
```
