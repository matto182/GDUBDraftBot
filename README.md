# GDUB Draft Bot
.,
A Discord bot for running **Guild Wars 1 GvG drafts** and scheduled signup events.

## Add the Bot to Your Server

Use this invite link:

https://discord.com/oauth2/authorize?client_id=1500734117531226112

After adding the bot, run:

```text
/setup
```

## Initial Setup

`/setup` walks a server administrator through the required configuration.

You will choose:

1. **Draft Board Channel**  
   The text channel where the main interactive draft board will be posted.

2. **Scheduled Events Channel**  
   The text channel used for scheduled event signup boards.  
   You can use the same channel as the draft board if you want.

3. **Team A Voice Channel**  
   Used when admins move drafted Team A players into voice.

4. **Team B Voice Channel**  
   Used when admins move drafted Team B players into voice.

5. **Draft Admin Role**  
   Members with this role can manage drafts, players, timeouts, and other admin controls.

6. **Owner Role**  
   The server role used for owner-level bot access.

When setup is complete, the bot posts the draft board automatically.

## Player Setup

Before joining a draft, each player should register:

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

Players can then join with the draft board buttons or:

```text
/signup
```

## Draft Board

The draft board is the main interface for players.

Players can:

- Sign up
- Drop
- Vote for Captain or Random Draft
- Volunteer as captain
- View draft status

Admins can also start drafts and open the Admin Panel from the board.

## Lobby Size

The default lobby size is **16 players**.

Admins can change it from **2 to 16** with:

```text
/lobbysize
```

When the active lobby is full, additional players enter the waiting room.

When slots open, waiting-room players are promoted automatically in FIFO order.

## Draft Modes

### Random Draft

Random Draft automatically:

- Splits the lobby into Team A and Team B
- Uses player role preferences
- Assigns final roles
- Saves the completed draft to history

### Captain Draft

Captain Draft allows players to volunteer as captains.

Two captains are selected and alternate picks until teams are complete.

## Admin Panel

Open the Admin Panel with:

```text
/admin
```

Admins can:

- Add players
- Kick players
- Move players between lobby and waiting room
- Swap lobby and waiting-room players
- Change waiting-room order
- Timeout players
- Remove active timeouts
- Reset a draft
- Wipe the lobby
- Move completed teams to voice channels
- Refresh the draft board

## Scheduled Events

The bot also supports one-time and recurring signup events.

Main commands:

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

Scheduled events support:

- One-time events
- Weekly recurring events
- Time-zone aware scheduling
- Signup limits
- Waiting lists
- Automatic promotion when a slot opens

## Common Commands

### Players

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

## Running Locally

Install dependencies:

```bash
python -m pip install discord.py python-dotenv tzdata
```

Create a `.env` file:

```text
TOKEN=YOUR_DISCORD_BOT_TOKEN
```

Start the bot:

```bash
python bot.py
```

The SQLite database is stored in:

```text
players.db
```

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
