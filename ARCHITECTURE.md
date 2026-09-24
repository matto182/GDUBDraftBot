# GDUB Draft Bot Architecture

The project deliberately favors **a few large, obvious files** over many tiny command/service/repository/view modules.

## Current layout

```text
bot.py
commands.py
config.py
database.py
draft_logic.py
draft_service.py
scheduled_events.py
views.py
```

## Where code lives

| If you are changing... | Open... |
| --- | --- |
| Bot startup, intents, `on_ready`, `on_message` | `bot.py` |
| Any slash command | `commands.py` |
| Any button, select, modal, setup screen, admin panel, inspector, history UI | `views.py` |
| Lobby behavior, draft board behavior, moderation, player management, notifications, trades, history helpers | `draft_service.py` |
| Random-draft balancing, role assignment, Captain Draft algorithm | `draft_logic.py` |
| Database tables, migrations, reads/writes | `database.py` |
| Scheduled event signups and timezone handling | `scheduled_events.py` |
| Token/path/role constants and legacy role normalization | `config.py` |

## Runtime flow

```text
Discord interaction
      |
      v
 commands.py / views.py
      |
      v
 draft_service.py ---------> draft_logic.py
      |                           |
      v                           |
 database.py <--------------------+

scheduled_events.py -------> draft_service.py + database.py

bot.py wires everything together.
```

## Consolidation map

The old files were folded into these larger files:

- `commands.py`: all former `*_commands.py` modules.
- `views.py`: all former `*_views.py` modules, including admin panel, player inspector, setup, captain, and history views.
- `draft_service.py`: `state.py`, runtime/lobby/board/moderation/execution/notification/voice services, player alias/stats/management/inspector services, history service, trade service, and admin player helpers.
- `database.py`: schema plus all former `*_repository.py` modules.
- `draft_logic.py`: constants, role assignment, scoring, random draft, captain draft, and role-needs modules.

`scheduled_events.py` stayed separate because it is already a substantial self-contained feature. `bot.py` and `config.py` also remain intentionally small.

## Navigation inside the large files

Each consolidated file has large semantic section dividers such as:

```python
# ========================================================================
# LOBBY ACTIONS
# ========================================================================
```

Use those headings plus normal IDE search instead of jumping across dozens of tiny modules.

## Role compatibility

The active role system is still:

- Frontline
- Midline
- Prot Monk
- Heal Monk
- 8 Support

Old strings such as `Lyssa/Flex Derv` and `Support/Flag (8)` remain only in compatibility/migration code so existing saved player data can normalize to the current role model. There is no active `FLEX_ROLES` category.
