# GDUB Draft Bot Architecture

This document describes the current high-level structure of the GDUB Draft Bot.

The project intentionally uses a **small number of larger modules** instead of splitting each feature into separate service, repository, command, and view files.

## Project Layout

```text
bot.py
commands.py
config.py
database.py
draft_logic.py
draft_service.py
scheduled_events.py
views.py
players.db
```

## Module Responsibilities

### `bot.py`

Application entry point.

Responsible for:

- Creating the Discord client
- Initializing the database
- Initializing scheduled events
- Registering slash commands
- Registering persistent Discord views
- Starting background event processing
- Handling startup and ready events

`bot.py` should stay small and should not contain feature logic.

---

### `commands.py`

Contains slash-command registration and command handlers.

Commands should:

1. Validate Discord-facing input
2. Call the appropriate service function
3. Return the result to Discord

Business logic should stay in `draft_service.py`, `draft_logic.py`, or `scheduled_events.py`.

---

### `views.py`

Contains Discord UI components:

- Buttons
- Select menus
- Modals
- Admin panels
- Setup wizard
- Captain Draft UI
- Draft history UI
- Player inspector UI

Views should primarily handle interaction flow and delegate state changes to service functions.

---

### `draft_service.py`

Main runtime and business-logic module for the draft system.

Responsible for:

- Per-guild runtime state
- Lobby and waiting-room behavior
- Draft board rendering
- Player signup and drop behavior
- Voting and captain volunteering
- Admin player management
- Timeouts and moderation
- Player inspection
- Draft history helpers
- Team trades and substitutions
- Voice-channel movement
- Draft execution
- Completed-draft notifications

This is the main place to look when changing how the draft system behaves.

---

### `draft_logic.py`

Contains draft-generation algorithms.

Responsible for:

- Random team generation
- Role assignment
- Team composition rules
- Captain Draft state and pick order
- Team balancing calculations

This module should remain mostly independent of Discord UI code.

---

### `database.py`

Owns SQLite persistence.

Responsible for:

- Database initialization and migrations
- Player registration
- Player aliases
- Guild configuration
- Lobby persistence
- Draft history
- Player statistics
- Moderation state
- Scheduled-event persistence used by shared systems

Other modules should use the database functions instead of writing SQL directly.

---

### `scheduled_events.py`

Contains the scheduled signup-event system.

Responsible for:

- Event creation and editing
- Weekly recurrence
- Time-zone handling
- Signup and waitlist management
- Event boards
- Event commands
- Event background processing

Scheduled events are intentionally kept separate from the draft runtime because they are a distinct feature.

---

### `config.py`

Contains shared configuration and role definitions.

Responsible for:

- Environment configuration
- Discord token loading
- Current role names
- Role normalization
- Compatibility mappings for older stored data

---

## Runtime State

Each Discord server has its own `GuildState`.

Typical runtime data includes:

```text
lobby
waiting_room
votes
captain_volunteers
draft_result
captain_draft
final_team_a
final_team_b
lobby_size
```

The default lobby size is 16 and can be changed at runtime from 2–16 players.

Runtime state is kept in memory while important persistent data is stored in SQLite.

## Draft Flow

Typical draft flow:

```text
Player registers
      ↓
Player signs up
      ↓
Lobby fills
      ↓
Players vote
      ↓
Admin starts draft
      ↓
Random Draft or Captain Draft
      ↓
Teams and roles are finalized
      ↓
Draft is saved to history
      ↓
Board updates / players notified
```

### Random Draft

```text
draft_service.py
      ↓
draft_logic.py
      ↓
Generated Team A / Team B
      ↓
database.py saves completed draft
```

### Captain Draft

```text
Players volunteer
      ↓
Two captains selected
      ↓
CaptainDraft manages alternating picks
      ↓
Teams finalized
      ↓
database.py saves completed draft
```

## Lobby and Waiting Room

The active lobby uses the server's current `lobby_size`.

When the lobby is full:

```text
New signup
    ↓
Waiting room
```

When a slot becomes available:

```text
Oldest eligible waiting player
    ↓
Promoted into lobby
```

The waiting room is FIFO unless an admin explicitly changes queue order.

## Discord UI Flow

Discord buttons and modals live in `views.py`.

A typical interaction looks like:

```text
Discord button
      ↓
views.py
      ↓
draft_service.py
      ↓
database.py / draft_logic.py
      ↓
views.py or draft board refresh
```

This keeps UI code separate from state-changing logic.

## Scheduled Event Flow

```text
/event command
      ↓
scheduled_events.py
      ↓
Event saved
      ↓
Event board posted
      ↓
Players sign up
      ↓
Signup / waitlist updated
      ↓
Background event loop handles future occurrences
```

Scheduled-event time zones use IANA regional zones where possible so daylight-saving changes are handled correctly.

## Persistence

The bot uses:

```text
players.db
```

SQLite is used for data that must survive restarts.

Examples include:

- Players
- Guild configuration
- Lobby state
- Completed drafts
- Draft stats
- Player aliases
- Timeouts
- Scheduled events

Temporary interaction state stays in memory.

## Startup Flow

```text
bot.py
  ↓
init_db()
  ↓
init_events()
  ↓
load players
  ↓
register commands
  ↓
register persistent views
  ↓
sync Discord commands
  ↓
start scheduled-event loop
  ↓
post/restore draft boards
```

## Testing

Tests live under:

```text
tests/
```

Run the regression suite with:

```bash
python -m pytest -q
```

The suite covers:

- Database behavior
- Draft generation
- Role assignment
- Lobby sizes
- Waiting-room behavior
- Captain Drafts
- Admin operations
- Moderation
- Scheduled events
- Project imports and wiring

## Architecture Rules

Keep the project simple.

### Prefer

- One module per major domain
- Clear section headers inside larger files
- Business logic outside Discord callbacks
- Shared database functions
- Automated regression tests before deployment

### Avoid

- One-file-per-function architecture
- Thin wrapper modules
- Separate service/repository/view files for tiny features
- Duplicate implementations
- Direct SQL outside `database.py`
- Feature logic inside `bot.py`

The goal is to make it obvious where to look:

```text
Discord startup?       bot.py
Slash command?         commands.py
Button/modal/UI?       views.py
Draft behavior?        draft_service.py
Draft algorithm?       draft_logic.py
Database/data?         database.py
Scheduled events?      scheduled_events.py
Roles/configuration?   config.py
```
