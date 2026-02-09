# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.4.0] - 2025-02-09

### Added
- Docker support (Dockerfile + docker-compose.yml)
- GitHub Actions CI workflow (Python 3.9, 3.11, 3.12)
- `engram serve` command (alias for `server`)
- `engram status` command (version, config paths, DB stats)
- Landing page waitlist section for hosted cloud
- CHANGELOG.md

### Changed
- Version bump to 0.4.0
- README rewritten as product-focused documentation
- CLI `--version` now pulls from `engram.__version__`
- pyproject.toml updated with Beta classifier and new keywords

## [0.3.0] - 2025-01-15

### Added
- PMK v2: staged writes with policy gateway
- Dual retrieval (semantic + episodic)
- Namespace and agent trust system
- Session tokens with capability scoping
- Sleep-cycle background maintenance
- Reference-aware decay (preserve strongly referenced memories)

## [0.2.0] - 2025-01-01

### Added
- Episodic scenes (CAST grouping with time gap and topic shift detection)
- Character profiles (extraction, self-profile, narrative generation)
- Dashboard visualizer
- Claude Code plugin (hooks, commands, skill)
- OpenClaw integration

## [0.1.0] - 2024-12-01

### Added
- FadeMem: dual-layer memory (SML/LML) with Ebbinghaus decay
- EchoMem: multi-modal encoding (keywords, paraphrases, implications, questions)
- CategoryMem: dynamic hierarchical category organization
- MCP server for Claude Code, Cursor, Codex
- REST API server
- Knowledge graph with entity extraction and linking
- Hybrid search (semantic + keyword)
- CLI with add, search, list, stats, decay, export, import commands
- Ollama support for local LLMs
