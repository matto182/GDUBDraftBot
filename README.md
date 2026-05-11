# GDUB Draft Bot

A persistent multi-server Guild Wars 1 GvG draft bot for Discord.

GDUB Draft Bot supports:

* Randomized balanced drafts
* Captain drafts
* Persistent lobby state
* Waiting room queue system
* Draft statistics tracking
* Role preference weighting
* Smart team composition generation
* Voice channel team moving
* Draft-ready DM notifications
* Multi-guild support

---

# Features

## Draft Modes

### Random Draft

Automatically generates two balanced teams using:

* Backline priority logic
* Frontline balancing
* Midline distribution
* Player role preferences
* Role scarcity awareness

The draft generator prioritizes:

1. Prot / Heal / Support
2. Frontline
3. Midline
4. Flex

### Captain Draft

Players can volunteer as captains.

If Captain votes exceed Random votes:

* Two captains are selected
* Captains alternate picks
* Teams are auto-role-optimized after drafting

---

# Persistent Systems

The bot stores:

* Lobby state
* Waiting room state
* Draft history
* Player statistics
* Guild configuration

The bot survives restarts without losing state.

---

# Statistics System

Track:

* Drafts played
* Times captain
* Roles played
* Primary / secondary role usage
* Fill/off-role assignments

Commands:

```text
/stats
/stats player:Relic
```

---

# Commands

## Player Commands

### Set IGN

```text
/name
```

Sets your in-game name.

---

### Set Role Preferences

```text
/role
```

Choose your preferred roles in priority order.

---

### View Stats

```text
/stats
/stats player:<IGN>
```

View player draft statistics.

---

## Draft Commands

### Post Draft Board

```text
/draftboard
```

Posts the persistent interactive draft board.

---

### Start Draft

```text
/startdraft
```

Starts either:

* Random Draft
* Captain Draft

based on current votes.

---

### Move Teams

```text
/move
```

Moves drafted players into configured voice channels.

Players not currently in voice receive a DM notification.

---

### Pull Next Waiting Room Player

```text
/subnext
```

Moves the next waiting room player into the active lobby.

Waiting room order is preserved.

---

### Reset Lobby

```text
/resetlobby
```

Clears:

* Lobby
* Waiting room
* Draft state
* Votes
* Captains

---

## Admin Commands

### Setup

```text
/setup
```

Configure:

* Draft channel
* Team A voice channel
* Team B voice channel
* Admin role

---

# Server Setup

## 1. Invite the Bot

Open your bot invite link in a browser.
[https://discord.com/oauth2/authorize?client_id=1500734117531226112&permissions=16985216&integration_type=0&scope=bot](https://discord.com/oauth2/authorize?client_id=1500734117531226112&permissions=2252076856109184&integration_type=0&scope=bot+applications.commands)

Invite the bot to your Discord server.

---

## 2. Create Voice Channels

Create two voice channels for teams.

Example:

```text
Team A
Team B
```

---

## 3. Create a Draft Channel

Create a text channel where the draft board will live.

Example:

```text
#drafts
```

---

## 4. Run Setup Command

Run:

```text
/setup
```

Select:

* Draft channel
* Team A voice channel
* Team B voice channel
* Draft admin role

---

## 5. Post Draft Board

Run:

```text
/draftboard
```

This creates the persistent interactive draft board.

---

## 6. Player Setup

Before signing up, players should configure:

```text
/name
```

and:

```text
/role
```

---

# Commands

## Required Intents

Enable these in the Discord Developer Portal:

* Server Members Intent
* Message Content Intent
* Presence Intent

---

# Recommended Permissions

The bot should have:

* Send Messages
* Manage Messages
* Move Members
* Connect
* View Channels
* Send Messages in Threads
* Use Slash Commands
* Embed Links
* Read Message History
* Manage Channels (optional)

---

# Project Structure

```text
bot.py             -> Main bot logic and commands
views.py           -> Discord UI views/buttons/selects
draft_logic.py     -> Team generation and role balancing
database.py        -> SQLite persistence layer
state.py           -> Runtime guild state handling
config.py          -> Role configuration/constants
players.db         -> SQLite database
```

---

# Tech Stack

* Python 3.12+
* discord.py
* SQLite

---

# Roadmap

Planned features:

* Team synergy tracking
* Draft history browser
* Web dashboard
* Match result tracking
* Team chemistry analytics
* Smart substitute recommendations
* Draft quality grading

---

# License

MIT License

---

# Credits

Built for the Guild Wars 1 GvG community.

