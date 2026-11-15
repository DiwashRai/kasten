---
type: topic
updated: 2026-11-15
---

# Python quality gates

Implements the gates in [[quality-gates]] for Python projects using `uv`. Package names (`myapp`)
and layer names are placeholders. Change them to match the project's architecture.

| Gate                        | Tool                                              |
| --------------------------- | ------------------------------------------------- |
| Cognitive complexity ≤ 15   | complexipy                                        |
| Nesting ≤ 4, size backstops | Ruff (`PLR1702`, `PLR0913`, `PLR0915`, `PLR0911`) |
| Duplication                 | pylint `duplicate-code`                           |
| Strict typing, no `Any`     | basedpyright `recommended`                        |
| Lint rules                  | Ruff                                              |
| Dependency rules            | import-linter                                     |
| Nudges (advisory)           | vulture, scb-check                                |

## Layers

The import contracts assume four layers. Each may import only the layers below it:

- **infrastructure:** I/O, frameworks, config and entry points.
- **application:** use cases that coordinate core logic and infrastructure.
- **core:** domain rules and data. No I/O, so it can be tested directly.
- **lib:** generic helpers that any layer may use.

The split gives the checks something to enforce: dependency direction, I/O-free logic and no cycles.
The layers don't have to be folders. In a small project a layer can be a single module, or two
layers can share one module while there is nothing to separate. Import-linter contracts can name
modules as well as packages. Pick the smallest layout that still lets these checks run, and split
further as the code grows.

## `pyproject.toml`

```toml
[dependency-groups]
dev = [
  "ruff",
  "complexipy",
  "basedpyright",
  "import-linter",
  "pylint",
  "vulture",
  "pre-commit",
]

[tool.ruff.lint]
preview = true
explicit-preview-rules = true
select = [
  "F", "E", "W", "B", "SIM", "RET", "C4", "PIE", "PERF", "FURB",
  "PL", "PLR1702",
  "UP", "TRY", "BLE", "S", "PTH", "DTZ",
  "ARG", "ERA", "T20", "A", "SLF001", "TID", "I", "PT",
  "PGH004", "RUF",
]
ignore = ["E501", "TRY003"]

[tool.ruff.lint.pylint]
max-args = 7
max-statements = 60
max-returns = 8
max-nested-blocks = 4

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "parents"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "PLR2004", "SLF001"]

[tool.complexipy]
paths = ["src"]
max-complexity-allowed = 15

[tool.basedpyright]
typeCheckingMode = "recommended"
include = ["src", "tests"]
reportUnusedCallResult = "none"

[tool.importlinter]
root_package = "myapp"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Layers point inward"
type = "layers"
layers = ["myapp.infrastructure", "myapp.application", "myapp.core", "myapp.lib"]

[[tool.importlinter.contracts]]
name = "Core does no I/O"
type = "forbidden"
source_modules = ["myapp.core", "myapp.lib"]
forbidden_modules = ["sqlalchemy", "httpx", "requests"]

[[tool.importlinter.contracts]]
name = "No cycles between siblings"
type = "acyclic_siblings"
ancestors = ["myapp"]

[tool.pylint.main]
recursive = true

[tool.pylint."messages control"]
disable = ["all"]
enable = ["duplicate-code"]

[tool.pylint.similarities]
min-similarity-lines = 6

[tool.vulture]
paths = ["src"]
min_confidence = 80
```

## `.pre-commit-config.yaml`

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format
        language: system
        types: [python]
      - id: ruff
        name: ruff check
        entry: uv run ruff check --fix
        language: system
        types: [python]
      - id: complexipy
        name: cognitive complexity
        entry: uv run complexipy
        language: system
        pass_filenames: false
        types: [python]
      - id: basedpyright
        name: types
        entry: uv run basedpyright
        language: system
        pass_filenames: false
        types: [python]
      - id: import-linter
        name: import contracts
        entry: uv run lint-imports
        language: system
        pass_filenames: false
        types: [python]
      - id: duplication
        name: duplicate code
        entry: uv run pylint src
        language: system
        pass_filenames: false
        types: [python]
```

CI runs `pre-commit run --all-files`. vulture and scb-check run in CI as reports and don't fail the
build.

## Existing codebases

- Baseline complexity with `complexipy --snapshot-create`, so only new or worse functions fail.
- Write import contracts for the architecture that exists, and use `ignore_imports` for known
  violations rather than restructuring code.
- Don't fix unrelated violations as part of adoption.

## Suppressions

Every suppression names its rule: Ruff `PGH004` bans bare `noqa`, `RUF100` removes stale ones, and
basedpyright only accepts `# pyright: ignore[rule]` and reports unnecessary ones.

## Ruled out

- **NPath, maintainability index, averages:** hard to act on or easy to game.
- **Coverage percentage:** gamed by tests that run code without checking it.
