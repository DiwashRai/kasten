"""The layout rules for `src/personal_mcp`, checked with the standard library only.

- Every file is pure unless its path relative to `src/personal_mcp` matches a pattern in
  `impure` under `[tool.layout]` in `pyproject.toml` (fnmatch, so `*` also crosses folders).
  A pure file has no I/O, environment, clock or randomness, no `Any` or untyped dicts, and
  project imports only of other pure files.
- Each folder directly under `src/personal_mcp` is a feature. A feature imports another only
  when `[tool.layout.imports]` in `pyproject.toml` declares it, and the declarations are acyclic.

Each failure prints `file:line  what was found  how to fix it`. Exits 1 on any failure.
"""

import ast
import fnmatch
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "personal_mcp"
SRC = ROOT / "src" / PACKAGE
IMPURE_HINT = "if the file's job is I/O, name it to match a pattern in impure under [tool.layout]"

IO_MODULES = {
    "httpx", "requests", "aiohttp", "urllib", "urllib3", "fastmcp", "mcp", "sqlite3",
    "subprocess", "socket",
}  # fmt: skip
PURE_SUBMODULES = ("urllib.parse",)  # string handling inside an I/O package
RANDOM_MODULES = {"random", "secrets"}
IO_CALLS = {"open", "print", "input", "breakpoint"}
PATH_IO_METHODS = {
    "open", "read_text", "write_text", "read_bytes", "write_bytes", "mkdir", "unlink", "rmdir",
    "iterdir", "glob", "rglob", "touch", "exists", "is_file", "is_dir", "stat", "cwd", "home",
}  # fmt: skip
ENVIRONMENT = ("os.environ", "os.getenv", "os.putenv")
CLOCK = (
    "datetime.now", "datetime.utcnow", "datetime.today", "date.today",
    "time.time", "time.time_ns", "time.monotonic", "time.perf_counter",
)  # fmt: skip
UNTYPED_MAPPINGS = {"dict", "Dict", "Mapping", "MutableMapping"}


@dataclass(frozen=True)
class Source:
    path: Path
    module: str
    tree: ast.Module

    @property
    def file(self) -> str:
        return self.path.relative_to(ROOT).as_posix()

    def pure(self, impure: list[str]) -> bool:
        within = self.path.relative_to(SRC).as_posix()
        return not any(fnmatch.fnmatchcase(within, pattern) for pattern in impure)


def module_name(path: Path) -> str:
    parts = path.relative_to(SRC.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def read_sources() -> list[Source]:
    paths = sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)
    return [
        Source(p, module_name(p), ast.parse(p.read_text(encoding="utf-8"), str(p))) for p in paths
    ]


def feature_of(module: str) -> str | None:
    """The feature folder a module belongs to, or None for a top-level module."""
    parts = module.split(".")
    if parts[0] != PACKAGE or len(parts) == 1:
        return None
    return parts[1] if (SRC / parts[1]).is_dir() else None


def project_imports(source: Source, modules: set[str]) -> list[tuple[int, str]]:
    """Every import of a project module as (line, module), relative imports resolved."""
    package = source.module.split(".")
    if source.path.name != "__init__.py":
        package = package[:-1]
    found: list[tuple[int, str]] = []
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            up = package[: len(package) - node.level + 1] if node.level else []
            base = ".".join([*up, *(node.module.split(".") if node.module else [])])
            for alias in node.names:
                submodule = f"{base}.{alias.name}"
                found.append((node.lineno, submodule if submodule in modules else base))
    return [(line, name) for line, name in found if name.split(".")[0] == PACKAGE]


def dotted(node: ast.AST) -> str:
    match node:
        case ast.Name(id=name):
            return name
        case ast.Attribute(value=value, attr=attr):
            return f"{dotted(value)}.{attr}"
        case _:
            return ""


def ends_with(name: str, suffixes: tuple[str, ...]) -> bool:
    return any(f".{name}".endswith(f".{suffix}") for suffix in suffixes)


def impure_import(module: str, name: str | None) -> tuple[str, str] | None:
    full = f"{module}.{name}" if name else module
    top = module.split(".")[0]
    if top in IO_MODULES and not any(f"{full}.".startswith(f"{m}.") for m in PURE_SUBMODULES):
        return f"import of {full}", "do the I/O in the caller and pass the data in"
    if top in RANDOM_MODULES:
        return f"import of {full}", "draw the random value in the caller and pass it in"
    if ends_with(full, ENVIRONMENT):
        return f"import of {full}", "read the environment in the caller and pass the value in"
    if ends_with(full, CLOCK):
        return f"import of {full}", "read the clock in the caller and pass the value in"
    return None


def impurity(node: ast.AST) -> tuple[str, str] | None:
    match node:
        case ast.Import(names=aliases):
            found = [impure_import(a.name, None) for a in aliases]
            return next((f for f in found if f), None)
        case ast.ImportFrom(module=str(module), names=aliases, level=0):
            found = [impure_import(module, a.name) for a in aliases]
            return next((f for f in found if f), None)
        case ast.Call(func=ast.Name(id=name)) if name in IO_CALLS:
            return f"call to {name}()", "do the I/O in the caller and pass the data in"
        case ast.Call(func=ast.Attribute(attr=attr)) if attr in PATH_IO_METHODS:
            return f"call to .{attr}()", "do the file I/O in the caller and pass the data in"
        case ast.Attribute() if ends_with(dotted(node), ENVIRONMENT):
            what = "read the environment in the caller and pass the value in"
            return f"use of {dotted(node)}", what
        case ast.Attribute() if ends_with(dotted(node), CLOCK):
            what = "read the clock in the caller and pass the value in"
            return f"use of {dotted(node)}", what
        case _:
            return None


def last_name(node: ast.AST) -> str:
    return dotted(node).split(".")[-1]


def untyped(annotation: ast.expr | None) -> str | None:
    """Why an annotation is untyped data (`Any`, a bare dict, a dict of `object`), or None."""
    if annotation is None:
        return None
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            annotation = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return None
    nodes = list(ast.walk(annotation))
    subscripts = [n for n in nodes if isinstance(n, ast.Subscript)]
    if any(isinstance(n, (ast.Name, ast.Attribute)) and last_name(n) == "Any" for n in nodes):
        return "Any"
    for node in subscripts:
        values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        if last_name(node.value) in UNTYPED_MAPPINGS and dotted(values[-1]) == "object":
            return "a dict of object"
    subscripted = {id(n.value) for n in subscripts}
    bare = [
        n
        for n in nodes
        if isinstance(n, (ast.Name, ast.Attribute))
        and last_name(n) in UNTYPED_MAPPINGS
        and id(n) not in subscripted
    ]
    return "a bare dict" if bare else None


def annotations(tree: ast.Module) -> list[tuple[int, str, ast.expr | None]]:
    """(line, where, annotation) for signatures, class fields and type aliases."""
    found: list[tuple[int, str, ast.expr | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
            every += [a for a in (args.vararg, args.kwarg) if a]
            found += [(a.lineno, f"parameter {a.arg} of {node.name}", a.annotation) for a in every]
            found.append((node.lineno, f"return type of {node.name}", node.returns))
        elif isinstance(node, ast.ClassDef):
            found += [
                (s.lineno, f"field {dotted(s.target)} of {node.name}", s.annotation)
                for s in node.body
                if isinstance(s, ast.AnnAssign)
            ]
        elif isinstance(node, ast.TypeAlias):
            found.append((node.lineno, f"type alias {dotted(node.name)}", node.value))
    return found


def purity_failures(source: Source, pure_modules: set[str], modules: set[str]) -> list[str]:
    out: list[str] = []
    for node in ast.walk(source.tree):
        found = impurity(node)
        if found:
            what, fix = found
            line = getattr(node, "lineno", 1)
            out.append(f"{source.file}:{line}  {what}  the file is pure: {fix}; {IMPURE_HINT}")
    for line, where, annotation in annotations(source.tree):
        kind = untyped(annotation)
        if kind and annotation:
            out.append(
                f"{source.file}:{line}  {where} is {ast.unparse(annotation)} ({kind})  "
                "the file is pure and takes typed data: "
                "give the data a dataclass with named, typed fields and parse raw input into it "
                f"in the caller; {IMPURE_HINT}"
            )
    for line, imported in project_imports(source, modules):
        if imported not in pure_modules:
            out.append(
                f"{source.file}:{line}  import of impure {imported}  the file is pure and imports "
                "only pure project files: move the type or rule it needs into a pure file, or "
                f"have the caller pass the value in; {IMPURE_HINT}"
            )
    return out


def section_line(text: str, header: str) -> int:
    lines = text.splitlines()
    return next((i + 1 for i, s in enumerate(lines) if s.strip() == header), 1)


def load_impure() -> tuple[list[str], list[str]]:
    """The `impure` patterns under `[tool.layout]`, and a failure when they are malformed."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    impure = tomllib.loads(text).get("tool", {}).get("layout", {}).get("impure", [])
    if isinstance(impure, list) and all(isinstance(p, str) for p in impure):
        return impure, []
    failure = (
        f"pyproject.toml:{section_line(text, '[tool.layout]')}  impure under [tool.layout] is "
        f"{impure!r}, not a list of strings  write it as a list of glob patterns, "
        'e.g. impure = ["*_io.py", "server.py"]'
    )
    return [], [failure]


def load_declared() -> tuple[dict[str, list[str]], int]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = tomllib.loads(text).get("tool", {}).get("layout", {}).get("imports", {})
    return {k: list(v) for k, v in declared.items()}, section_line(text, "[tool.layout.imports]")


def cycle(declared: dict[str, list[str]]) -> list[str] | None:
    """One cycle among the declared feature imports, as a path that ends where it starts."""
    done: set[str] = set()

    def visit(node: str, path: list[str]) -> list[str] | None:
        if node in path:
            return [*path[path.index(node) :], node]
        if node in done:
            return None
        for target in declared.get(node, []):
            found = visit(target, [*path, node])
            if found:
                return found
        done.add(node)
        return None

    return next((c for c in (visit(n, []) for n in sorted(declared)) if c), None)


def feature_failures(sources: list[Source], modules: set[str]) -> list[str]:
    declared, section_line = load_declared()
    out: list[str] = []
    loop = cycle(declared)
    if loop:
        out.append(
            f"pyproject.toml:{section_line}  declared feature imports form a cycle "
            f"{' -> '.join(loop)}  features must depend one way: move what both sides need "
            "into the feature lower down, or into a top-level module, and drop one declaration"
        )
    for source in sources:
        own = feature_of(source.module)
        if own is None:
            continue
        for line, imported in project_imports(source, modules):
            other = feature_of(imported)
            if other is None or other == own or other in declared.get(own, []):
                continue
            out.append(
                f"{source.file}:{line}  feature {own} imports feature {other} ({imported})  "
                f"undeclared: if {own} depends on {other} by design, declare it in "
                f'pyproject.toml under [tool.layout.imports] as {own} = ["{other}"]; otherwise '
                f"move the shared code to where both can use it"
            )
    return out


def main() -> int:
    sources = read_sources()
    modules = {s.module for s in sources}
    impure, failures = load_impure()
    if not failures:
        pure = [s for s in sources if s.pure(impure)]
        pure_modules = {s.module for s in pure}
        failures += [f for s in pure for f in purity_failures(s, pure_modules, modules)]
    failures += feature_failures(sources, modules)
    for failure in failures:
        print(failure)
    print(f"layout: {len(failures)} failure(s)" if failures else "layout: ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
