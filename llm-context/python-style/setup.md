# Project setup

Once per project. Gives `just check` (fails on a broken layout rule) and `just health` (a report
that never fails). Needs `uv` and `just`.

1. Copy this skill's `scripts/layout.py` and `scripts/health.py` into the project's `scripts/`.
2. Set `PACKAGE` near the top of `scripts/layout.py` to the package name under `src/`.
3. Add the configuration below, then run `uv sync` and `uv run pre-commit install`.
4. Run `just check` and `just health`; both must run before any code is written.

## `pyproject.toml`

```toml
[dependency-groups]
dev = [
    "basedpyright>=1.40.2",
    "complexipy>=9.0.0",
    "pre-commit>=4.7.0",
    "pytest>=9.2.0",
    "ruff>=0.17.5",
]

[tool.ruff]
line-length = 100
extend-exclude = [".claude"]

[tool.basedpyright]
typeCheckingMode = "standard"

[tool.pytest.ini_options]
testpaths = ["tests"]

# Every file under `src/<package>` is checked as pure unless its path, relative to the package,
# matches one of these patterns. `*` also matches across folders: "*_io.py" covers every folder,
# "server.py" only the top level, "jobs/worker.py" one file. Edit the list to suit the project.
[tool.layout]
impure = ["*_io.py"]

# Feature `a` may import feature `b` only when listed here: `a = ["b"]`. Checked by
# `scripts/layout.py`; the declared imports must not form a cycle.
[tool.layout.imports]
```

## `justfile`

```just
set windows-shell := ["pwsh", "-NoLogo", "-NoProfile", "-Command"]

# Format, lint, types and the layout rules. Edits nothing.
check:
    uv run ruff format --check
    uv run ruff check
    uv run basedpyright
    uv run python scripts/layout.py

# Advisory report on src: length, complexity, cohesion, fan-out, comments. Never fails.
health:
    uv run python scripts/health.py

# Run the tests.
test:
    uv run pytest

# Format and apply safe lint fixes.
fix:
    uv run ruff format
    uv run ruff check --fix
```

## `.pre-commit-config.yaml`

```yaml
repos:
  - repo: local
    hooks:
      - id: check
        name: just check
        entry: just check
        language: system
        pass_filenames: false
        always_run: true
```
