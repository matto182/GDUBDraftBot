# GDUB Module Consolidation

## Result

The project was reduced from 65 Python modules to 8:

- `bot.py`
- `commands.py`
- `config.py`
- `database.py`
- `draft_logic.py`
- `draft_service.py`
- `scheduled_events.py`
- `views.py`

## What moved where

- All slash-command modules -> `commands.py`
- All Discord view/modal/select modules -> `views.py`
- Runtime state and service/helper modules -> `draft_service.py`
- Schema and repository modules -> `database.py`
- Draft algorithm modules -> `draft_logic.py`
- `scheduled_events.py`, `bot.py`, and `config.py` remain separate

## Intentional behavior policy

This pass is a structural consolidation. Existing feature behavior was preserved rather than redesigned.

Legacy role strings remain only in role-normalization and database-migration compatibility code. No active `FLEX_ROLES` category was added.

## Validation performed

- `python -m py_compile *.py` passes.
- All consolidated local imports resolve to existing modules.
- Circular `draft_service` / `views` initialization was smoke-tested with a Discord API stub.
- Bot `setup_hook()` smoke test passes against a temporary database.
- Slash-command registration matches the original source: 34 direct commands plus the scheduled-event command group.
- Seeded Random Draft output matches the original source exactly.
- Database smoke tests passed for player records, historical-backline flag, aliases, guild config, board visibility, lobby persistence, hidden weights, lobby timeouts, draft stats, and draft-history retrieval.
- Repository-private SQLite connection helpers were given distinct names where consolidation would otherwise have caused one helper to overwrite another.
