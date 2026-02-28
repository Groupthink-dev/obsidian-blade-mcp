# Code Quality

Three tools enforce code quality, run together via `make check`.

## mypy — Static Type Checking

```bash
make type-check
# or: uv run mypy src/obsidian_blade_mcp
```

Configuration in `pyproject.toml`:
- Strict mode: `disallow_untyped_defs`, `no_implicit_optional`
- All functions must have type annotations
- Tests excluded from strict checking

## ruff — Linting & Formatting

```bash
make lint          # Check for issues
make format        # Auto-fix formatting
make format-check  # Check without fixing
```

Configuration in `pyproject.toml`:
- Target: Python 3.12
- Line length: 120
- Rules: E, F, I (isort), N, W, UP (pyupgrade)

## pre-commit — Git Hooks

```bash
make pre-commit-install  # Set up hooks
make pre-commit-run      # Run on all files
```

Hooks:
1. **pre-commit-hooks** (v4.5.0): trailing whitespace, EOF, YAML/JSON/TOML check, large files, merge conflicts, debug statements
2. **ruff** (v0.9.0): lint with auto-fix + format
3. **mypy** (v1.14.0): type checking (excludes tests/)

## Workflow

```bash
# Before committing:
make check  # Runs lint + format-check + type-check

# Full validation:
make check && make test
```
