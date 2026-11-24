"""Forms: the description an agent sends, the answer a user gives, and the environment file."""

import re
from dataclasses import dataclass, field, replace
from typing import Literal

from relay.errors import RelayError

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
type FieldType = Literal["text", "number", "choice", "password"]
type FormState = Literal["open", "answered", "collected"]

# A field or form name such as "PORT" or "db_url": a letter or underscore, then letters, digits
# and underscores. It becomes a key in an environment file.
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# A form id such as "service-env": letters, digits, dashes and underscores.
FORM_ID = re.compile(r"[A-Za-z0-9_-]+")
# An integer or a decimal such as "8080" or "-0.5".
NUMBER = re.compile(r"-?\d+(\.\d+)?")
# A character that forces quotes in an environment file: white space, "#", "=", or a quote.
NEEDS_QUOTES = re.compile(r"""[\s#="']""")


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    type: FieldType
    default: str
    required: bool
    options: tuple[str, ...]
    help: str


@dataclass(frozen=True)
class Form:
    id: str
    title: str
    fields: tuple[Field, ...]
    state: FormState = "open"
    draft: dict[str, str] = field(default_factory=dict)
    values: dict[str, str] = field(default_factory=dict)
    answered_at: str = ""
    delivered: bool = False


def _text(data: dict[str, Json], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise RelayError(f"{key} must be text")
    return value


def _texts(data: dict[str, Json], key: str) -> dict[str, str]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise RelayError(f"{key} must be an object of text values")
    return {name: str(item) for name, item in value.items() if item is not None}


def _field_type(kind: str, name: str) -> FieldType:
    match kind:
        case "text" | "number" | "choice" | "password":
            return kind
        case _:
            raise RelayError(f"field {name}: type must be text, number, choice or password")


def _field(data: Json) -> Field:
    if not isinstance(data, dict):
        raise RelayError("each field must be an object with a name")
    name = _text(data, "name", "")
    if not NAME.fullmatch(name):
        raise RelayError(f"field name {name!r} must look like PORT or db_url")
    kind = _field_type(_text(data, "type", "text"), name)
    options = data.get("options", [])
    if not isinstance(options, list) or (kind == "choice") != bool(options):
        raise RelayError(f"field {name}: a choice needs options, and only a choice has them")
    choices = tuple(str(option) for option in options)
    default = _text(data, "default", choices[0] if choices else "")
    if choices and default not in choices:
        raise RelayError(f"field {name}: default must be one of {', '.join(choices)}")
    required = data.get("required", True)
    if not isinstance(required, bool):
        raise RelayError(f"field {name}: required must be true or false")
    label = _text(data, "label", name)
    return Field(name, label, kind, default, required, choices, _text(data, "help", ""))


def _state(value: Json) -> FormState:
    match value:
        case "open" | "answered" | "collected":
            return value
        case _:
            raise RelayError("form state must be open, answered or collected")


def form_from_json(data: Json) -> Form:
    """Read a stored form, with its state and answer.

    Raises:
        RelayError: the data is not a valid form.
    """
    if not isinstance(data, dict):
        raise RelayError("a form must be an object with id, title and fields")
    form_id = _text(data, "id", "")
    if not FORM_ID.fullmatch(form_id):
        raise RelayError(f"form id {form_id!r} must use letters, digits, dashes and underscores")
    fields = data.get("fields")
    if not isinstance(fields, list) or not fields:
        raise RelayError("a form needs at least one field")
    parsed = tuple(_field(item) for item in fields)
    names = [item.name for item in parsed]
    if len(set(names)) != len(names):
        raise RelayError("field names must be different from each other")
    return Form(
        id=form_id,
        title=_text(data, "title", form_id),
        fields=parsed,
        state=_state(data.get("state", "open")),
        draft=_texts(data, "draft"),
        values=_texts(data, "values"),
        answered_at=_text(data, "answered_at", ""),
        delivered=data.get("delivered") is True,
    )


def parse_form(data: Json) -> Form:
    """Read a form description sent by an agent. The result is always open and empty.

    Raises:
        RelayError: the description is not a valid form.
    """
    described = form_from_json(data)
    return Form(described.id, described.title, described.fields)


def open_form(current: Form | None, new: Form) -> Form:
    """Return the form a thread holds after an agent asks.

    Asking the same question again changes nothing, so a retry cannot erase an answer.

    Raises:
        RelayError: a different form is still open or its answer is not collected.
    """
    if current is None or current.state == "collected":
        return new
    if (current.id, current.title, current.fields) == (new.id, new.title, new.fields):
        return current
    raise RelayError(
        f"form {current.id!r} is still {current.state}; collect it first with: "
        f"relay wait {current.id}"
    )


def save_draft(form: Form, values: dict[str, str]) -> Form:
    """Keep half-typed values for an open form. Unknown names are dropped."""
    if form.state != "open":
        return form
    names = {item.name for item in form.fields}
    return replace(form, draft={name: value for name, value in values.items() if name in names})


def _problem(item: Field, value: str) -> str | None:
    if not value:
        return f"{item.label} is required" if item.required else None
    if "\n" in value or "\r" in value:
        return f"{item.label} must be a single line"
    if item.type == "number" and not NUMBER.fullmatch(value):
        return f"{item.label} must be a number"
    if item.type == "choice" and value not in item.options:
        return f"{item.label} must be one of {', '.join(item.options)}"
    return None


def answer_form(form: Form, values: dict[str, str], now: str, waiter: bool) -> Form:
    """Store a user's answer. `waiter` says whether an agent was waiting when it arrived.

    Raises:
        RelayError: the form is not open, or a value is unknown, missing or of the wrong kind.
    """
    if form.state != "open":
        raise RelayError(f"form {form.id!r} was already answered")
    unknown = sorted(set(values) - {item.name for item in form.fields})
    if unknown:
        raise RelayError(f"unknown field: {', '.join(unknown)}")
    cleaned = {item.name: values.get(item.name, "").strip() for item in form.fields}
    problems = [found for item in form.fields if (found := _problem(item, cleaned[item.name]))]
    if problems:
        raise RelayError("; ".join(problems))
    return replace(
        form, state="answered", values=cleaned, draft={}, answered_at=now, delivered=waiter
    )


def collect_form(form: Form) -> Form:
    """Forget the values once the agent has confirmed it received them."""
    return replace(form, state="collected", values={}) if form.state == "answered" else form


def without_values(form: Form | None) -> Form | None:
    """The form as a page may see it: an answer's values are never sent to a page."""
    return None if form is None else replace(form, values={})


def quote(value: str) -> str:
    """Write a value by dotenv rules: quoted when empty or when it holds a special character."""
    if value and not NEEDS_QUOTES.search(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _key(line: str) -> str | None:
    if line.lstrip().startswith("#") or "=" not in line:
        return None
    return line.split("=", 1)[0].strip()


def env_text(existing: str, values: dict[str, str]) -> str:
    """Merge an answer into an environment file's text.

    Lines already there are kept. A key already present is replaced in place; new keys are added
    at the end.
    """
    lines = existing.splitlines()
    present = {key for line in lines if (key := _key(line))}
    kept = [
        f"{key}={quote(values[key])}" if (key := _key(line)) in values and key else line
        for line in lines
    ]
    added = [f"{key}={quote(value)}" for key, value in values.items() if key not in present]
    return "\n".join([*kept, *added]) + "\n"
