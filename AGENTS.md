# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Project notes

- CrewAI-based competitor-intelligence crew. Layout, agents, and commands are in
  `README.md` (see "Project layout" and "Development"); don't duplicate them here.
- Pinned to `crewai[anthropic]==1.15.22` (see `pyproject.toml`). Uses the 1.x
  API: `crewai.LLM(model="anthropic/claude-sonnet-4-5", ...)` and the Flow API
  (`crewai.flow.flow`: `Flow`, `@start`, `@listen`, `@router`). Native providers
  need the `[anthropic]` extra; without it CrewAI raises ImportError for the
  Anthropic provider on valid Claude model ids.
- Design rule that keeps tests offline+fast: the deterministic core
  (`models`, `config`, `cache`, `scraper`, `quality`, `cost`, `report`) imports
  no `crewai`; only `crew.py`, `flow.py`, `runner.py` do. All LLM-backed agents
  are exposed as injectable callables so `runner.run(...)` / the Flow accept fakes
  in tests. HTTP is mocked via `httpx.MockTransport`; never add live-network or
  real-LLM calls to tests/CI.
- Run gate before pushing: `ruff check . && ruff format --check . && pytest -q`
  (CI runs exactly these on py3.11 + py3.12).

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
