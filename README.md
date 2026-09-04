# GDUB Draft Bot

A persistent, multi-server Discord bot for organizing **Guild Wars 1 GvG drafts**.

GDUB Draft Bot handles the full draft workflow inside Discord: player registration, role preferences, lobby and waiting-room management, Random and Captain drafts, team assignment, voice-channel movement, draft history, statistics, moderation, and admin controls.

The bot is designed for communities that repeatedly run Guild Wars 1 GvG drafts and want the draft process to stay fast, organized, configurable, and persistent between bot restarts. Drafts can be configured from **1v1 through 8v8**, with **8v8 as the default**.

---

## Features

### Persistent Draft Board

The bot maintains an interactive draft board in the configured draft channel.

Players can use the board to:

- Sign up for the current draft
- Drop from the lobby or waiting room
- Vote for Captain Draft or Random Draft
- Volunteer to captain
- Start the draft when authorized
- Make Captain Draft picks when it is their turn
- Open the admin panel when authorized
- View the current draft status

The board displays:

- Current draft format
- Active lobby players
- Waiting-room players
- Current role needs
- Draft-mode votes
- Captain volunteers
- Captain Draft progress
- Completed draft teams

The board is persistent and is restored when the bot restarts.

---

## Player Registration

### In-Game Name

Players register their Guild Wars 1 name with:

```text
/name ign:<IGN>
```

A player's Discord ID is their permanent identity in the database.

Running `/name` again changes the player's current IGN without creating a new player record.

### Previous IGN / Alias Tracking

When a registered player changes their IGN with `/name`, the bot automatically preserves the old IGN as a previous name.

Example:

```text
Current IGN: Turbo Relic

Previous IGNs:
Relic
New Relic
```

The same player can still be found by an old IGN in supported player lookups.

This keeps player identity and draft history intact even when someone changes names.

---

## Role Preferences

Players choose the roles they can play with:

```text
/role
```

Up to five roles can be entered in priority order.

Current roles:

- Frontline
- Midline
- Prot Monk
- Heal Monk
- 8 Support

The first selected role is the player's primary preference, followed by secondary and lower-priority preferences.

Role preferences are used when assigning players during drafts.

---

## Lobby and Waiting Room

### Signing Up

Players can join with:

```text
/signup
```

or the **Sign Up** button on the draft board.

The active lobby capacity is based on the server's configured draft format.

| Format | Lobby Capacity |
| --- | ---: |
| 1v1 | 2 |
| 2v2 | 4 |
| 3v3 | 6 |
| 4v4 | 8 |
| 5v5 | 10 |
| 6v6 | 12 |
| 7v7 | 14 |
| 8v8 | 16 |

**8v8 is the default.**

Once the active lobby reaches the configured capacity, additional players are placed into the waiting room.

### FIFO Waiting Room

The waiting room operates as a queue.

When a lobby slot opens, the oldest eligible waiting-room player is moved into the lobby first.

This behavior is preserved across normal lobby operations and bot restarts.

### Dropping

Players can leave with:

```text
/drop
```

or the **Drop** button on the draft board.

When appropriate, the next waiting-room player is automatically promoted into the newly opened lobby slot.

### Lobby Status

```text
/lobby
/draftstatus
```

These commands show the current lobby, waiting room, votes, and Captain Draft status.

---

## Configurable Draft Formats

Each Discord server can choose its own team size from **1v1 through 8v8**.

Admins can change the format with:

```text
/draftformat
```

The format is stored per server and defaults to **8v8**.

Changing the format automatically updates:

- Active lobby capacity
- Waiting-room promotion behavior
- Start Draft requirements
- Random Draft team size
- Captain Draft team size
- Role-composition targets
- Draft Board capacity display
- Admin Panel capacity display
- Draft History format information

If the format is reduced while players are already signed up, players beyond the new lobby capacity are moved to the **front of the waiting room** while preserving their order.

If the format is increased, waiting-room players are automatically promoted into newly available lobby slots using the normal FIFO rules.

The format cannot be changed while a draft result or Captain Draft is active. Reset the current draft first.

For **1v1**, Captain Mode is disabled and the draft runs as a head-to-head Random Draft.

---

## Draft Modes

Players vote for a draft mode with:

```text
/vote
```

or the draft-board voting buttons.

The available modes are:

- Captain Mode
- Random Draft

Captain Mode is available for **2v2 through 8v8**. In **1v1**, Captain voting and captain volunteering are disabled.

When the draft starts, the current vote determines the mode. If Captain Mode does not win, the bot runs a Random Draft.

---

## Random Draft

Random Draft automatically creates two teams at the server's configured size while considering:

- Registered role preferences
- Frontline distribution
- Midline distribution
- Backline coverage
- Team composition requirements
- Role scarcity
- Off-role assignments when required to complete a valid draft

The bot adapts team-composition targets to the selected format and automatically assigns each player a role on their final team. Smaller 1v1 and 2v2 formats use flexible role assignment instead of forcing a full GvG composition.

Completed Random Drafts are saved to draft history.

---

## Captain Draft

Players volunteer to captain with:

```text
/captain
```

or the **Volunteer Captain** button.

For formats from **2v2 through 8v8**, if Captain Mode wins the vote:

1. Two volunteers are selected as captains.
2. The Captain Draft begins.
3. Captains alternate picks.
4. The current captain uses the draft board or:

```text
/pickpanel
```

5. Once all players are selected, the bot assigns team roles based on player preferences and team composition.
6. The completed draft is saved to history.

The pick sequence automatically scales to the selected team size. The draft board shows the current picker, both captains, drafted teams, and remaining available players.

---

## Starting a Draft

Admins can start a draft with:

```text
/startdraft
```

or the **Start Draft** button on the draft board.

The active lobby must contain exactly the number of players required by the configured format, from **2 players for 1v1** through **16 players for 8v8**.

Start Draft intentionally remains part of the normal draft-board workflow rather than the admin management panel.

---

## Draft History

Completed drafts are stored automatically.

Browse draft history with:

```text
/history
```

The history browser shows completed drafts newest-first and supports interactive navigation.

History includes:

- Draft ID
- Draft mode
- Draft format
- Completion time
- Team A
- Team B
- Assigned roles
- Captains for Captain Drafts

The history interface includes **Previous**, **Next**, and **View Draft** controls.

Draft history is stored per server.

---

## Player Statistics

View your own stats:

```text
/stats
```

View another registered player:

```text
/stats player:<IGN>
```

Tracked statistics include:

- Drafts played
- Times captain
- Captain rate
- Preferred-role hit rate
- Off-role rate
- Role frequency
- Role-priority usage

### Preferred-Role Hit Rate

The percentage of drafts where the player was assigned to one of their registered role preferences.

### Off-Role Rate

The percentage of drafts where the player had to be assigned outside their registered role preferences.

### Role Frequency

Shows how often the player has been assigned each role, including both the total count and percentage of their completed drafts.

---

## Draft Notifications

When teams are completed, the bot can notify drafted players by DM.

This helps players notice that the draft has finished even if they are not actively watching the draft channel.

---

## Voice Channel Movement

After teams are created, admins can move players into the configured Team A and Team B voice channels.

Voice movement is available from the admin interface and uses the server's configured team voice channels.

Players who cannot be moved are reported back to the admin.

---

# Administration

## Unified Admin Panel

Draft admins can open the main control center with:

```text
/admin
```

The legacy command:

```text
/adminboard
```

opens the same interface.

The **Admin Panel** button on the persistent draft board also opens this same panel.

The panel displays a quick overview of:

- Current draft format
- Active lobby size
- Waiting-room size
- Current draft state
- Captain and Random vote totals
- Captain volunteer count
- Active lobby timeouts

### Player Management

The admin panel includes:

- **Add Player** — manually add a registered player to the lobby or waiting room
- **Kick Player** — remove a player from the current draft
- **Move Player** — move a player between the active lobby and waiting room
- **Swap Players** — exchange one active-lobby player with one waiting-room player
- **Queue Position** — move a waiting-room player to a specific queue position

Equivalent slash commands remain available for admins who prefer commands.

### Moderation

The panel includes:

- **Timeout Player**
- **Active Timeouts**

Admins can select registered players and apply lobby timeouts without leaving the panel.

### Draft Management

The panel includes:

- **Reset Draft**
- **Wipe Lobby**
- **Move to Voice**

Destructive actions use confirmation controls where appropriate.

### System Controls

The panel includes:

- **Refresh Board**
- **Refresh Panel**

The panel does **not** replace the normal Start Draft workflow.

---

## Player Inspector

Draft admins can inspect a registered player with:

```text
/inspectplayer player:<IGN, Discord name, previous IGN, or ID>
```

The inspector includes:

- Current IGN
- Discord account information
- Previous IGNs
- Registered roles
- Backline history
- Lobby-timeout status
- Drafts played
- Captain appearances and rate
- Primary-preference assignments
- Off-role assignments
- Last draft
- Assigned-role history
- Recent draft activity

The inspector is admin-only.

### Inspector Timeout Controls

The Player Inspector also provides moderation controls.

For a player without an active timeout:

```text
Timeout Player
```

For a player with an active timeout:

```text
Change Timeout
Remove Timeout
```

Timeout controls use the same moderation system as the normal timeout commands.

---

## Lobby Timeouts

Admins can prevent a player from joining draft lobbies with:

```text
/timeout
```

Available timeout durations include temporary durations and a permanent option.

A timed-out player is removed from the active lobby or waiting room and cannot sign up again until the timeout expires or is removed.

Remove a timeout with:

```text
/untimeout
```

View active timeouts with:

```text
/timeouts
```

Expired temporary timeouts are automatically ignored and cleaned up when checked.

---

## Manual Player Management

Admins can manage signed-up players with:

```text
/addplayer
/moveplayer
/queue
/swapplayers
```

### `/addplayer`

Adds a registered player directly to either:

- Active Lobby
- Waiting Room

### `/moveplayer`

Moves a signed-up player between the lobby and waiting room.

### `/queue`

Changes a waiting-room player's queue position.

Queue positions start at `1`.

### `/swapplayers`

Swaps one active-lobby player with one waiting-room player.

This is useful when the lobby is already at the configured capacity.

---

## Additional Admin Commands

### Pull Next Waiting-Room Player

```text
/subnext
```

Moves the next waiting-room player into the active lobby when space is available.

### Reset Draft

```text
/resetdraft
```

Clears the current draft result and draft-specific state while keeping the lobby, then refills open lobby slots from the waiting room when possible.

### Wipe Lobby

```text
/wipelobby
```

Completely clears the current lobby and waiting room.

### Reset Lobby

```text
/resetlobby
```

Clears the lobby, waiting room, draft state, votes, and captain volunteers.

### Fill Test Lobby

```text
/filltest
```

Admin utility for filling the lobby with the number of test players required by the current draft format.

---

# Server Setup

## 1. Invite the Bot

Use the Discord bot invite link:

[Invite GDUB Draft Bot](https://discord.com/oauth2/authorize?client_id=1500734117531226112&permissions=2252076856109184&integration_type=0&scope=bot+applications.commands)

---

## 2. Create the Draft Channel

Create a text channel where the persistent draft board will live.

Example:

```text
#drafts
```

---

## 3. Create Team Voice Channels

Create two voice channels for drafted teams.

Example:

```text
Team A
Team B
```

---

## 4. Run Setup

Run:

```text
/setup
```

Use the setup interface to configure the server's draft channel, team voice channels, Draft Admin role, and draft format. The default format is **8v8**.

---

## 5. Post the Draft Board

Run:

```text
/draftboard
```

This posts the persistent interactive draft board in the configured environment.

---

## 6. Player Setup

Each player should register before joining a draft:

```text
/name ign:<IGN>
/role
```

After registration, they can join with `/signup` or the Sign Up button.

---

# Command Reference

## Player

```text
/name
/role
/stats
/signup
/drop
/vote
/captain
/lobby
/draftstatus
/history
```

## Draft

```text
/draftboard
/startdraft
/pickpanel
```

## Admin / Moderation

```text
/admin
/adminboard
/draftformat
/inspectplayer
/addplayer
/moveplayer
/queue
/swapplayers
/timeout
/untimeout
/timeouts
/subnext
/resetdraft
/resetlobby
/wipelobby
/filltest
```

Some controls are also available directly through the draft board or Admin Panel.

---

# Persistence

SQLite is used to persist draft data.

Persisted information includes:

- Player registrations
- Current player names
- Previous player IGNs
- Registered role preferences
- Backline-history flags
- Guild configuration and per-server draft format
- Lobby state
- Waiting-room state
- Completed draft history, including the format used for each draft
- Per-player draft assignments
- Lobby timeouts
- Draft notification cooldown data

Runtime guild state is reconstructed around the persisted data when the bot starts.

---

# Multi-Server Support

Guild-specific information is isolated by Discord server where appropriate.

Each server can maintain its own:

- Draft configuration
- Draft format
- Draft board
- Lobby
- Waiting room
- Draft state
- Draft history
- Moderation state
- Voice-channel configuration

---

# Discord Requirements

## Required Intents

Enable the intents required by your deployment in the Discord Developer Portal.

The current bot configuration uses:

- Server Members Intent
- Message Content Intent

---

## Recommended Permissions

The bot should be able to:

- View Channels
- Send Messages
- Embed Links
- Read Message History
- Use Application Commands
- Connect to voice channels
- Move Members

Additional permissions may be necessary depending on the server's channel overrides.

---

# Project Structure

The project is split into focused modules rather than a single monolithic bot file.

```text
bot.py
    Bot startup, Discord client, events, command registration

commands.py
    Top-level slash-command registration

config.py
    Current role configuration and compatibility normalization

state.py
    Per-guild runtime state

database.py
    Database compatibility facade

database_schema.py
    SQLite schema initialization and migrations

*_repository.py
    Focused persistence and database-query modules

draft_service.py
    Compatibility facade for draft services

lobby_service.py
    Signup, drop, voting, captain volunteering, resets, and lobby operations

lobby_state_service.py
    Persistent lobby loading/saving and waiting-room promotion

draft_execution_service.py
    Random Draft and Captain Draft execution

draft_format_service.py
    Per-server 1v1–8v8 format, capacity calculation, and lobby resizing

board_service.py
    Draft-board rendering and refresh behavior

voice_service.py
    Team voice-channel movement

notification_service.py
    Draft notification delivery

player_management_service.py
    Shared admin player-management operations

player_stats_service.py
    Player statistics calculations and formatting

player_alias_service.py
    Previous-IGN tracking and player-name handling

admin_panel_*.py
    Unified admin control-panel commands and views

player_inspector_*.py
    Admin player inspector data, service, and UI

draft_history_*.py
    Draft history repository, service, commands, and UI

draft_logic.py
    Draft-logic compatibility facade

role_assignment.py
random_draft.py
captain_draft.py
role_needs.py
    Focused team-generation, composition, and role-assignment logic

views.py
    Compatibility facade for Discord UI views

tests/
    Automated regression tests
```

---

# Architecture

For a detailed file-by-file map, dependency graph, and execution-flow guide, see:

```text
ARCHITECTURE.md
```

---

# Tech Stack

- Python
- discord.py
- SQLite
- python-dotenv
- pytest

---


# License

MIT License

---

# Credits

Built for the Guild Wars 1 GvG community.
