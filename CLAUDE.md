# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Avatar-Bots is a Discord bot ecosystem for "Avatar: Peace in Ba Sing Se", a turn-based strategy wargame. It consists of two bots:

- **Iroh** - Wargame bot: Manages factions, territories, units, resources, and turn-based order resolution
- **Hawky** - Task/communication bot: Handles character letters, scheduled tasks, and responses

## Commands

### Running Tests (Iroh only)
```bash
make test                              # Run all iroh tests in Docker
make test-verbose                      # Run with verbose output
make test-file FILE=tests/test_order_handlers.py  # Run specific test file
```

Tests run inside the iroh-api container via `docker compose exec`.

### Docker Development
```bash
docker compose -f docker-compose-development.yaml up -d  # Start local environment
# PostgreSQL runs on port 5432 (user=AVATAR, password=password, db=AVATAR)
# Iroh API: port 5001, Hawky API: port 4242
```

## Architecture

### Layered Design
```
Discord Commands (iroh.py, hawky.py)
    ↓
Handler Functions (handlers/*.py)  ← Pure logic, no Discord imports
    ↓
Database Models (db/*.py)
    ↓
PostgreSQL
```

### Key Directories

- `db/` - Shared database models using asyncpg with dataclass-based entities. All tables include `guild_id` for multi-server isolation.
- `iroh/handlers/` - Business logic layer. Each handler module focuses on a domain (orders, factions, territories, units, etc.). Returns `(success: bool, message: str)` tuples.
- `iroh/orders/` - Order execution during turn resolution. Each order type has a handler returning `TurnLog` entries.
- `iroh/event_logging/` - Turn report generation with character-view and GM-view formatters.
- `iroh/tests/` - pytest with asyncio. Fixtures in `conftest.py` provide `db_conn`, `test_server`, `test_server_multi_guild`.

### Turn Resolution System

The wargame uses a 9-phase turn resolution engine (`turn_handlers.resolve_turn()`):
1. BEGINNING - Faction join/leave/kick orders
2. MOVEMENT - Transit orders
3. COMBAT - (placeholder)
4. RESOURCE_COLLECTION - Auto-generate resources from territories
5. RESOURCE_TRANSFER - Process resource trades
6. ENCIRCLEMENT - (placeholder)
7. UPKEEP - Consume resources for unit maintenance
8. ORGANIZATION - (placeholder)
9. CONSTRUCTION - (placeholder)

Orders have types (`OrderType` enum), statuses (`PENDING`, `ONGOING`, `SUCCESS`, `FAILED`, `CANCELLED`), and are processed by phase with priority ordering.

### Database Pattern

Models in `db/` follow this pattern:
- Dataclass with async `upsert()` and `fetch_by_*()` class methods
- All operations require `asyncpg.Connection` as first parameter
- Multi-guild support via `guild_id` on all tables

### Handler Pattern

Handlers in `iroh/handlers/` follow this pattern:
- Async functions taking `(conn: asyncpg.Connection, guild_id: int, ...)`
- Return `(success: bool, message: str)` or `List[TurnLog]`
- No Discord imports - pure business logic

## Configuration

- YAML-based game state import/export via `ConfigManager` class
- Environment variables in `.env` files (iroh/, hawky/)
- Database connection: `postgresql://AVATAR:password@db:5432/AVATAR`
