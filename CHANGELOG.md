# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-14

### Added
- Interactive REPL interface powered by `prompt_toolkit` and `rich`.
- Dynamic syntax hinting and rich command documentation.
- Discovery service to fetch markets via Polymarket Gamma API.
- LLM ranking service supporting Ollama and OpenRouter.
- Paper trading broker to simulate positions.
- Live websocket streaming for order book monitoring.
- Unified SQLite storage engine for all data and snapshots.
- Scheduled watchlists for periodic market discovery.
- On-demand CSV and JSON exports via `/export`.
