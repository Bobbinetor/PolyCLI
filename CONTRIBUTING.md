# Contributing to PolyCLI

Thank you for your interest in contributing to PolyCLI!

## Development Setup

We use `uv` for dependency management and environment isolation.

1. Clone the repository:
   ```bash
   git clone https://github.com/bobbinetor/polycli.git
   cd polycli
   ```

2. Install dependencies:
   ```bash
   uv sync --extra dev
   ```

3. Run the CLI:
   ```bash
   uv run polycli
   ```

## Code Quality

We use `ruff` for linting and formatting, and `pytest` for testing.

1. Format your code:
   ```bash
   uv run ruff format .
   ```

2. Lint your code:
   ```bash
   uv run ruff check .
   ```

3. Run the tests:
   ```bash
   uv run pytest -v
   ```

Make sure all checks pass before opening a Pull Request.

## Architecture

PolyCLI is built with a few core principles:
- **REPL-First**: The main interface is an interactive REPL built on `prompt_toolkit` and `rich`.
- **Stateless Services**: Logic lives in stateless services (`DiscoveryService`, `RankingService`) that are injected with standard repositories.
- **SQLite Single Source of Truth**: All discovered data, rankings, and paper positions are stored in `~/.local/share/polycli/polycli.db`. We don't spam the filesystem with CSVs.

## Pull Requests

1. Fork the repo and create your branch from `main`.
2. Add tests for new features.
3. Update the documentation if needed.
4. Open a PR with a clear description of the changes.
