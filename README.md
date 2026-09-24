# GDUB Draft Bot

A Discord bot for running **Guild Wars 1 GvG drafts** and scheduled signup events.

GDUB handles player registration, role preferences, configurable lobbies, waiting rooms, Random and Captain drafts, admin controls, draft history, moderation, voice movement, and recurring event signups.

## Features

### Drafts

Players register with:

```text
/name
/role
```

Current roles:

- Frontline
- Midline
- Prot Monk
- Heal Monk
- 8 Support

Players can then join from the persistent draft board or with:

```text
/signup
/drop
```

Lobby size is configurable from **2–16 players** with `/lobbysize`. The default is **16**. Once full, additional players enter a FIFO waiting room and are promoted when slots open.

Supported draft modes:

- **Random Draft** — automatically builds two teams and assigns roles.
- **Captain Draft** — two volunteers become captains and alternate picks.

Completed drafts are saved automatically.

### Admin Panel

Open with:

```text
/admin
```

Admins can:

- Add, kick, move, and swap players
- Change waiting-room order
- Timeout players
- Reset drafts or wipe the lobby
- Move completed teams to voice channels
- Refresh the draft board

### History and Stats

```text
/history
/stats
/inspectplayer
```

The bot stores completed drafts, team assignments, player aliases, captain appearances, role assignments, and moderation state.

### Scheduled Events

The bot also supports one-time and recurring signup events with their own Discord boards.

```text
/event create
/event edit
/event editseries
/event cancel
/event pause
/event resume
/event reopen
/event add
/event remove
/event copy
/event history
/events
```

Events support weekly recurrence, time zones, signup limits, waiting lists, and automatic promotion when a slot opens.

## Commands

### Player

```text
/name
/role
/signup
/drop
/vote
/captain
/lobby
/draftstatus
/stats
/history
/events
```

### Draft

```text
/draftboard
/startdraft
/pickpanel
/lobbysize
```

### Admin

```text
/admin
/inspectplayer
/addplayer
/moveplayer
/queue
/swapplayers
/trade
/timeout
/untimeout
/timeouts
/resetdraft
/resetlobby
/wipelobby
/subnext
/hidelobby
/showlobby
/setup
```

## Setup

Run:

```text
/setup
```

The setup wizard configures:

- Draft board channel
- Scheduled events channel
- Team A and Team B voice channels
- Draft Admin role
- Owner role

Players then register with `/name` and `/role`.

## Running Locally

Install dependencies:

```bash
python -m pip install discord.py python-dotenv tzdata
```

Create `.env`:

```text
TOKEN=YOUR_DISCORD_BOT_TOKEN
```

Start the bot:

```bash
python bot.py
```

SQLite data is stored in `players.db`.

## Tests

Install test dependencies:

```bash
python -m pip install pytest pytest-cov pytest-asyncio
```

Run:

```bash
python -m pytest -q
```

## Project Structure

```text
bot.py               Discord startup
commands.py          Slash commands
views.py             Discord UI
draft_service.py     Draft/admin business logic and runtime state
draft_logic.py       Team building and role assignment
database.py          SQLite persistence
scheduled_events.py  Scheduled event system
config.py            Configuration and roles
```

## Tech Stack

Python • discord.py • SQLite • pytest

## License

MIT
