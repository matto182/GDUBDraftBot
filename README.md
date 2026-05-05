# GDUBDraftBot
Discord Draft Bot for Guild Wars 1 GVG


SETUP

GW1 GvG Draft Bot — Full Setup Guide

This guide walks you through everything needed to get the bot working in your Discord server.

1. Add the Bot to Your Server

Open your bot invite link in a browser.
https://discord.com/oauth2/authorize?client_id=1500734117531226112&permissions=16985216&integration_type=0&scope=bot

Select the server you want to add the bot to
Click Authorize

You must have Administrator or Manage Server permissions to do this.

2. Run the Setup Command

In your Discord server, type:

/setup

This will start the setup process.

The bot will ask you to select a few things. Each one is explained below.

Select Draft Board Channel (text channel)

This is the text channel where the draft system will live.

The bot will post the draft board here
Players will click buttons in this channel to join, vote, and draft
This must be a text channel, not a voice channel

What to pick:

A channel like #gvg-draft, #drafts, or similar

What happens after:

The bot will continuously update one message in this channel
That message is the main draft interface
Select Team A Voice Channel

This is the voice channel where Team A players will be moved after the draft.

This must be a voice channel
The bot will move players here automatically when you use “Move Teams”
Players must already be connected to voice for this to work

What to pick:

A voice channel named something like Team A, Blue Team, or similar
Select Team B Voice Channel

This is the voice channel where Team B players will be moved after the draft.

Same rules as Team A voice channel
Must be a different voice channel

What to pick:

A voice channel named something like Team B, Red Team, etc.
Select Draft Admin Role

This is the role that is allowed to control the draft system.

People with this role can:

Reset the draft
Kick players
Move teams to voice channels

What to pick:

A trusted role like Officer, Leader, or Admin

Important:

Server Administrators can always use admin controls even without this role
After Setup

Once all selections are made:

The bot saves your settings
The draft board will be posted automatically in the channel you selected

At this point, the system is ready to use.

3. Player Setup (Required for Each Player)

Before joining a draft, each player must register.

Step 1 — Set your in-game name
/name YourCharacterName

Example:

/name Smelly Monk
Step 2 — Set your roles
/role

You will choose up to 5 roles.

Order matters.

The first role you select is your main role
The second is your backup
The third is your fallback, and so on

Example:

1. Prot Monk
2. Heal Monk
3. Support/Flag

The bot will try to assign you to your first role whenever possible.

4. Joining a Draft

Go to the draft board channel.

Use the buttons on the draft board:

Sign Up → join the draft
Drop → leave the draft
Vote Captain → vote for captain mode
Vote Random → vote for random draft
Volunteer Captain → mark yourself as a captain
Lobby Behavior
The first 16 players go into the active lobby
Any additional players go into the waiting room
If someone leaves, the next player in the waiting room is automatically moved into the lobby
5. Starting the Draft

When there are 16 players:

/startdraft
Draft Modes
Random Draft
The bot automatically builds two teams
It uses player role priorities to decide placements
It tries to create a balanced team composition
Captain Draft

Requirements:

At least 2 players must click “Volunteer Captain”
Captain mode must win the vote

How it works:

Two captains are selected randomly from volunteers
They take turns picking players
The pick order follows a snake pattern:
Captain A picks 1
Captain B picks 2
Captain A picks 2
Captain B picks 2

Captains pick players by clicking:

Pick Player

Only the current captain is allowed to pick.

6. During the Draft

While a draft is active:

Players cannot sign up
Players cannot vote
Players cannot volunteer as captain
Players can still drop if needed

The draft board will show:

Current teams
Available players
Whose turn it is to pick
7. Moving Teams to Voice Channels

After teams are created:

Click:

Admin Panel → Move Teams

What happens:

Team A players are moved to the Team A voice channel
Team B players are moved to the Team B voice channel

Requirements:

Players must already be in a voice channel
The bot must have permission to move members
8. Admin Controls

Click the Admin Panel button on the draft board.

Available actions:

Reset Draft
Clears current teams
Keeps players in the lobby
Refills empty spots from waiting room
Kick Player
Removes a player from the lobby or waiting room
Useful if someone leaves Discord without clicking Drop
Move Teams
Moves players into their assigned voice channels
9. Full Reset

If you want to completely restart everything:

/resetlobby

This clears:

Lobby
Waiting room
Votes
Draft state
10. Common Issues
Bot does not post draft board

Run:

/setup

again

Bot cannot move players

Check:

Bot has “Move Members” permission
Players are already in a voice channel
Commands do not appear
Wait 30–60 seconds
Or remove and re-invite the bot
That’s it

Once setup is complete, everything runs from the draft board. Players only need to:

register once
click buttons to participate

Admins only need the Admin Panel for control.
