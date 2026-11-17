"""An advisory report on the code under `src`. It has no thresholds and never fails.

The numbers point at code worth a second look; they are not scores to lower.
"""

import ast
import io
import json
import subprocess
import sys
import tempfile
import tokenize
from collections import Counter
from pathlib import Path

from layout import PACKAGE, ROOT, Source, project_imports, read_sources

TOP = 5
COHESION_MIN_LINES = 40


def code_lines(source: Source) -> int:
    return sum(1 for line in source.path.read_text(encoding="utf-8").splitlines() if line.strip())


def longest_files(sources: list[Source]) -> list[str]:
    ranked = sorted(sources, key=code_lines, reverse=True)[:TOP]
    return [f"- {s.file}: {code_lines(s)} lines" for s in ranked]


def shown(path: str) -> str:
    """A path from complexipy, relative to the repository when it lies inside it."""
    resolved = Path(path.removeprefix("//?/").removeprefix("\\\\?\\")).resolve()
    return resolved.relative_to(ROOT).as_posix() if resolved.is_relative_to(ROOT) else path


def complexity() -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "complexipy.json"
        flags = ["--isolated", "--no-ignore", "--ignore-complexity", "--quiet"]
        flags += ["--output-format", "json", "--output", str(output), "--cache-dir", tmp]
        try:
            subprocess.run(
                ["complexipy", "src", *flags], cwd=ROOT, capture_output=True, check=False
            )
            rows = json.loads(output.read_text(encoding="utf-8"))
            ranked = sorted(rows, key=lambda row: row["complexity"], reverse=True)[:TOP]
            return [
                f"- {shown(row['path'])}:{row['line_start']} "
                f"{row['function_name']}: {row['complexity']}"
                for row in ranked
            ]
        except (OSError, ValueError, KeyError, TypeError) as error:
            return [f"- unavailable: could not read complexipy's output ({error})"]


def project_names(source: Source, modules: set[str]) -> set[str]:
    """Names this module imports from the project, as written in the module."""
    names: set[str] = set()
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ImportFrom) and (
            node.level or (node.module or "").startswith(PACKAGE)
        ):
            names |= {alias.asname or alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            names |= {
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
                if alias.name.split(".")[0] == PACKAGE
            }
    return names


def module_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names |= {
                t.id for target in node.targets for t in ast.walk(target) if isinstance(t, ast.Name)
            }
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            names.add(node.name.id)
    return names


def references(node: ast.AST, project: set[str]) -> set[str]:
    """Names a definition uses; `module.Type` counts as one name when `module` is imported."""
    found: set[str] = set()
    qualified: set[int] = set()
    for child in ast.walk(node):
        match child:
            case ast.Attribute(value=ast.Name(id=base) as value, attr=attr) if base in project:
                found.add(f"{base}.{attr}")
                qualified.add(id(value))
            case ast.Name(id=name) if id(child) not in qualified:
                found.add(name)
            case _:
                pass
    return found


def groups(source: Source, modules: set[str]) -> list[list[str]]:
    """Connected groups of two or more top-level definitions."""
    members = [
        n
        for n in source.tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    names = [m.name for m in members]
    project = project_names(source, modules)
    shared = module_level_names(source.tree) | project
    refs = [references(m, project) for m in members]
    parent = list(range(len(members)))

    def root(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            linked = names[j] in refs[i] or names[i] in refs[j]
            common = {r for r in refs[i] & refs[j] if r.split(".")[0] in shared}
            if linked or common:
                parent[root(i)] = root(j)
    by_root: dict[int, list[str]] = {}
    for i, name in enumerate(names):
        by_root.setdefault(root(i), []).append(name)
    return [g for g in by_root.values() if len(g) >= 2]


def cohesion(sources: list[Source], modules: set[str]) -> list[str]:
    lines: list[str] = []
    for source in sources:
        text = source.path.read_text(encoding="utf-8")
        if source.path.name == "__init__.py" or len(text.splitlines()) < COHESION_MIN_LINES:
            continue
        found = groups(source, modules)
        if len(found) >= 2:
            lines.append(f"- {source.file}: {len(found)} unrelated groups")
            lines += [f"  - {', '.join(group)}" for group in found]
    if not lines:
        return ["- no module splits into unrelated groups"]
    hint = (
        "The groups in each module below share no names with each other, so the module may "
        "hold more than one thing. This is a hint: look, and split only if it reads better."
    )
    return [hint, "", *lines]


def fan_out(sources: list[Source], modules: set[str]) -> list[str]:
    counts = {
        s.file: len({name for _, name in project_imports(s, modules)} - {s.module}) for s in sources
    }
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:TOP]
    return [f"- {file}: {count} project modules" for file, count in ranked if count]


def comment_lines(source: Source) -> int:
    text = source.path.read_text(encoding="utf-8")
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    return len({t.start[0] for t in tokens if t.type == tokenize.COMMENT})


def comments(sources: list[Source]) -> list[str]:
    counts = Counter({s.file: comment_lines(s) for s in sources})
    top = [f"- {file}: {count}" for file, count in counts.most_common(3) if count]
    return [f"- total: {counts.total()}", *top]


def main() -> int:
    try:
        report()
    except (OSError, SyntaxError, ValueError) as error:
        print(f"health: the report stopped early ({type(error).__name__}: {error})")
    return 0


def report() -> None:
    sources = read_sources()
    modules = {s.module for s in sources}
    sections = [
        ("Longest files (non-blank lines)", longest_files(sources)),
        ("Highest cognitive complexity (complexipy)", complexity()),
        ("Cohesion (a hint, not a verdict)", cohesion(sources, modules)),
        ("Fan-out (project modules imported)", fan_out(sources, modules)),
        ("Comment lines", comments(sources)),
    ]
    print("# Health report for src (advisory; read it, don't chase the numbers)")
    for title, lines in sections:
        print(f"\n## {title}\n")
        print("\n".join(lines or ["- nothing to report"]))


if __name__ == "__main__":
    sys.exit(main())
