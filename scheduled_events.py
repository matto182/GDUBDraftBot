"""Scheduled signups, kept independent of the live 16-player draft lobby."""
import asyncio
import calendar
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands

from config import DB_FILE
from database import get_guild_config
from moderation_service import is_draft_admin
from service_runtime import load_players, players

UTC = timezone.utc
WEEKDAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}
POST_LOCK = asyncio.Lock()


def configured_event_channel_id(config):
    return config.get('event_channel_id') or config.get('draft_channel_id')


def posted_channel_id(event, config):
    return event['channel_id'] or config.get('draft_channel_id')
REGIONAL_ZONES = {
    'ET': 'America/New_York', 'EASTERN': 'America/New_York',
    'CT': 'America/Chicago', 'CENTRAL': 'America/Chicago',
    'MT': 'America/Denver', 'MOUNTAIN': 'America/Denver',
    'PT': 'America/Los_Angeles', 'PACIFIC': 'America/Los_Angeles',
    'LONDON': 'Europe/London', 'DUBLIN': 'Europe/Dublin',
    'LISBON': 'Europe/Lisbon', 'PARIS': 'Europe/Paris',
    'BERLIN': 'Europe/Berlin', 'ROME': 'Europe/Rome',
    'MADRID': 'Europe/Madrid', 'WARSAW': 'Europe/Warsaw',
    'ATHENS': 'Europe/Athens', 'HELSINKI': 'Europe/Helsinki',
    'BUCHAREST': 'Europe/Bucharest',
    'SYDNEY': 'Australia/Sydney', 'MELBOURNE': 'Australia/Melbourne',
    'BRISBANE': 'Australia/Brisbane', 'ADELAIDE': 'Australia/Adelaide',
    'PERTH': 'Australia/Perth',
    'AUCKLAND': 'Pacific/Auckland', 'WELLINGTON': 'Pacific/Auckland',
}
FIXED_ABBREVIATIONS = {
    'EST': -5, 'EDT': -4, 'CST': -6, 'CDT': -5,
    'MST': -7, 'MDT': -6, 'PST': -8, 'PDT': -7,
}
ZONE_LABELS = {
    'America/New_York': 'Eastern (EST/EDT)',
    'America/Chicago': 'Central (CST/CDT)',
    'America/Denver': 'Mountain (MST/MDT)',
    'America/Los_Angeles': 'Pacific (PST/PDT)',
    'Europe/London': 'London (GMT/BST)',
    'Europe/Dublin': 'Dublin (GMT/IST)',
    'Europe/Lisbon': 'Lisbon (WET/WEST)',
    'Europe/Paris': 'Paris (CET/CEST)',
    'Europe/Berlin': 'Berlin (CET/CEST)',
    'Europe/Rome': 'Rome (CET/CEST)',
    'Europe/Madrid': 'Madrid (CET/CEST)',
    'Europe/Warsaw': 'Warsaw (CET/CEST)',
    'Europe/Athens': 'Athens (EET/EEST)',
    'Europe/Helsinki': 'Helsinki (EET/EEST)',
    'Europe/Bucharest': 'Bucharest (EET/EEST)',
    'Australia/Sydney': 'Sydney (AEST/AEDT)',
    'Australia/Melbourne': 'Melbourne (AEST/AEDT)',
    'Australia/Brisbane': 'Brisbane (AEST)',
    'Australia/Adelaide': 'Adelaide (ACST/ACDT)',
    'Australia/Perth': 'Perth (AWST)',
    'Pacific/Auckland': 'New Zealand (NZST/NZDT)',
}

TIME_ZONE_CHOICES = [
    ('Eastern (EST/EDT)', 'Eastern'), ('Central (CST/CDT)', 'Central'),
    ('Mountain (MST/MDT)', 'Mountain'), ('Pacific (PST/PDT)', 'Pacific'),
    ('UTC / GMT', 'UTC'),
    ('London (GMT/BST)', 'London'), ('Dublin (GMT/IST)', 'Dublin'),
    ('Lisbon (WET/WEST)', 'Lisbon'), ('Paris (CET/CEST)', 'Paris'),
    ('Berlin (CET/CEST)', 'Berlin'), ('Rome (CET/CEST)', 'Rome'),
    ('Madrid (CET/CEST)', 'Madrid'), ('Warsaw (CET/CEST)', 'Warsaw'),
    ('Athens (EET/EEST)', 'Athens'), ('Helsinki (EET/EEST)', 'Helsinki'),
    ('Bucharest (EET/EEST)', 'Bucharest'),
    ('Sydney (AEST/AEDT)', 'Sydney'), ('Melbourne (AEST/AEDT)', 'Melbourne'),
    ('Brisbane (AEST)', 'Brisbane'), ('Adelaide (ACST/ACDT)', 'Adelaide'),
    ('Perth (AWST)', 'Perth'),
    ('Auckland (NZST/NZDT)', 'Auckland'), ('Wellington (NZST/NZDT)', 'Wellington'),
]


def normalize_time(value):
    """Accept 8 PM, 8:30 PM, or 20:30; store the same HH:MM form."""
    value = value.strip().upper().replace('.', '')
    twelve = re.fullmatch(r'(\d{1,2})(?::(\d{1,2}))?\s*(AM|PM)', value)
    if twelve:
        hour, minute, period = twelve.groups()
        hour, minute = int(hour), int(minute or 0)
        if 1 <= hour <= 12 and 0 <= minute <= 59:
            return f'{hour % 12 + (12 if period == "PM" else 0):02d}:{minute:02d}'
    twenty_four = re.fullmatch(r'(\d{1,2}):(\d{2})', value)
    if twenty_four:
        hour, minute = map(int, twenty_four.groups())
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f'{hour:02d}:{minute:02d}'
    raise ValueError('Enter a time like 8 PM, 8:30 PM, or 20:30.')


def normalize_zone(value):
    """Keep regional zones DST-aware; represent GMT offsets as fixed UTC offsets."""
    value = value.strip()
    upper = value.upper()
    if upper in REGIONAL_ZONES:
        return REGIONAL_ZONES[upper]
    if upper in ('UTC', 'GMT'):
        return 'UTC'
    if upper in FIXED_ABBREVIATIONS:
        hours = FIXED_ABBREVIATIONS[upper]
        return f'UTC{hours:+03d}:00'
    match = re.fullmatch(r'(?:GMT|UTC)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?', upper)
    if match:
        sign, hours, minutes = match.groups()
        hours, minutes = int(hours), int(minutes or 0)
        if hours <= 14 and minutes < 60 and (hours < 14 or minutes == 0):
            return f'UTC{sign}{hours:02d}:{minutes:02d}'
    if value.startswith('UTC') or value.startswith('GMT'):
        raise ValueError('Use a GMT offset like GMT-5 or GMT+05:30 (up to 14 hours).')
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError('Choose a region from the menu, UTC, or a GMT offset such as GMT+2.') from exc
    return value


def zone_info(value):
    zone = normalize_zone(value)
    if zone == 'UTC':
        return UTC
    match = re.fullmatch(r'UTC([+-])(\d{2}):(\d{2})', zone)
    if match:
        sign, hours, minutes = match.groups()
        delta = timedelta(hours=int(hours), minutes=int(minutes))
        return timezone(delta if sign == '+' else -delta)
    return ZoneInfo(zone)


def zone_label(value):
    zone = normalize_zone(value)
    return ZONE_LABELS.get(zone, zone.replace('UTC', 'GMT', 1))


async def timezone_autocomplete(interaction: discord.Interaction, current: str):
    options = TIME_ZONE_CHOICES.copy()
    options.extend((f'GMT{hours:+d} — fixed offset', f'GMT{hours:+d}')
                   for hours in range(-12, 15))
    search = current.casefold().strip()
    # Show common regions first. When searching, accept labels and values.
    matches = [(label, value) for label, value in options
               if not search or search in label.casefold() or search in value.casefold()]
    return [app_commands.Choice(name=label, value=value) for label, value in matches[:25]]


def db():
    connection = sqlite3.connect(DB_FILE, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA busy_timeout=20000')
    return connection


def init_events():
    with db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS event_series (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL,
                local_time TEXT NOT NULL, time_zone TEXT NOT NULL,
                first_date TEXT NOT NULL, weekdays TEXT NOT NULL DEFAULT '',
                capacity INTEGER NOT NULL, reminder_minutes INTEGER NOT NULL DEFAULT 60,
                paused INTEGER NOT NULL DEFAULT 0, cancelled INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS event_occurrences (
                id INTEGER PRIMARY KEY, series_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,
                name TEXT NOT NULL, starts_at INTEGER NOT NULL, capacity INTEGER NOT NULL,
                reminder_minutes INTEGER NOT NULL, message_id INTEGER,
                channel_id INTEGER,
                cancelled INTEGER NOT NULL DEFAULT 0, pause_cancelled INTEGER NOT NULL DEFAULT 0,
                reopened INTEGER NOT NULL DEFAULT 0,
                reminder_sent INTEGER NOT NULL DEFAULT 0, start_sent INTEGER NOT NULL DEFAULT 0,
                UNIQUE(series_id, starts_at)
            );
            CREATE TABLE IF NOT EXISTS event_signups (
                occurrence_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                position INTEGER NOT NULL, area TEXT NOT NULL,
                ign TEXT NOT NULL, roles TEXT NOT NULL,
                discord_name TEXT NOT NULL, server_name TEXT NOT NULL,
                joined_at INTEGER NOT NULL,
                PRIMARY KEY (occurrence_id, user_id)
            );
            CREATE INDEX IF NOT EXISTS event_signups_order
                ON event_signups(occurrence_id, area, position);
        ''')
        try:
            conn.execute('ALTER TABLE event_occurrences ADD COLUMN channel_id INTEGER')
        except sqlite3.OperationalError:
            pass
        # Boards posted before channel selection are still in the draft channel.
        conn.execute('''UPDATE event_occurrences SET channel_id=(
            SELECT draft_channel_id FROM guild_config WHERE guild_id=event_occurrences.guild_id
        ) WHERE channel_id IS NULL AND message_id IS NOT NULL''')


def get_event(event_id, guild_id=None):
    with db() as conn:
        row = conn.execute('SELECT * FROM event_occurrences WHERE id=?' +
                           (' AND guild_id=?' if guild_id is not None else ''),
                           (event_id,) if guild_id is None else (event_id, guild_id)).fetchone()
        return dict(row) if row else None


def get_series(series_id, guild_id):
    with db() as conn:
        row = conn.execute('SELECT * FROM event_series WHERE id=? AND guild_id=?', (series_id, guild_id)).fetchone()
        return dict(row) if row else None


def signups(event_id):
    with db() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM event_signups WHERE occurrence_id=? ORDER BY position", (event_id,))]


def parse_weekdays(value):
    if not value.strip():
        return ''
    days = []
    for token in value.split(','):
        token = token.strip().lower()
        matches = [i for name, i in WEEKDAYS.items() if name.startswith(token) and len(token) >= 3]
        if len(matches) != 1:
            raise ValueError('Use weekday names separated by commas, such as Tuesday, Friday, Saturday.')
        days.append(matches[0])
    return ','.join(str(day) for day in sorted(set(days)))


def local_start(day, clock, zone):
    naive = datetime.fromisoformat(f'{day}T{normalize_time(clock)}')
    local_zone = zone_info(zone)
    aware = naive.replace(tzinfo=local_zone)
    # Reject DST gaps; ambiguous fall-back times use the first occurrence.
    if aware.astimezone(UTC).astimezone(local_zone).replace(tzinfo=None) != naive:
        raise ValueError(f'{day} {clock} does not exist in {zone_label(zone)} because of a clock change.')
    return int(aware.timestamp())


def validate(name, date, clock, zone, capacity, weekdays, reminder):
    if not name.strip() or len(name) > 100 or '@' in name:
        raise ValueError('Name must be 1–100 characters without @mentions.')
    if not 1 <= capacity <= 100:
        raise ValueError('Player limit must be between 1 and 100.')
    if not 1 <= reminder <= 1440:
        raise ValueError('Reminder must be 1–1440 minutes before start.')
    normalize_zone(zone)
    normalize_time(clock)
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError as exc:
        raise ValueError('Enter the date as YYYY-MM-DD.') from exc
    local_start(date, clock, zone)


def materialize(series_id, horizon_days=14):
    with db() as conn:
        row = conn.execute('SELECT * FROM event_series WHERE id=?', (series_id,)).fetchone()
        if not row or row['cancelled'] or row['paused']:
            return
        zone = zone_info(row['time_zone'])
        today = datetime.now(zone).date()
        first = datetime.strptime(row['first_date'], '%Y-%m-%d').date()
        days = {int(x) for x in row['weekdays'].split(',') if x}
        dates = [today + timedelta(days=offset) for offset in range(horizon_days + 1)]
        if first > dates[-1]:
            dates.extend(first + timedelta(days=offset) for offset in range(7))
        for day in dates:
            if day < first or (days and day.weekday() not in days) or (not days and day != first):
                continue
            try:
                stamp = local_start(day.isoformat(), row['local_time'], row['time_zone'])
            except ValueError:
                continue
            if stamp <= int(datetime.now(UTC).timestamp()):
                continue
            conn.execute('''INSERT OR IGNORE INTO event_occurrences
                (series_id,guild_id,name,starts_at,capacity,reminder_minutes)
                VALUES (?,?,?,?,?,?)''', (series_id,row['guild_id'],row['name'],stamp,row['capacity'],row['reminder_minutes']))


def fmt_event(event):
    return f"#{event['id']} **{discord.utils.escape_markdown(event['name'])}** — <t:{event['starts_at']}:F> (<t:{event['starts_at']}:R>)"


def board_embed(event):
    with db() as conn:
        series = conn.execute('SELECT * FROM event_series WHERE id=?', (event['series_id'],)).fetchone()
    signup_rows = signups(event['id'])
    seated = [r for r in signup_rows if r['area'] == 'seat']
    waiting = [r for r in signup_rows if r['area'] == 'wait']
    status = 'Cancelled' if event['cancelled'] else 'Open' if event['starts_at'] > int(datetime.now(UTC).timestamp()) or event['reopened'] else 'Closed'
    def line(row, index):
        fields = [row['ign'], row['roles'], row['discord_name'], row['server_name']]
        safe = [discord.utils.escape_markdown(discord.utils.escape_mentions(str(x)))[:55] for x in fields]
        return f"{index}. **{safe[0]}** · {safe[1]} · {safe[2]} · {safe[3]}"
    embed = discord.Embed(title=event['name'], color=discord.Color.blue(),
        description=f"<t:{event['starts_at']}:F> (<t:{event['starts_at']}:R>)\n"
                    f"Time zone: {zone_label(series['time_zone'])} · Status: {status}\n"
                    f"Players: **{len(seated)}/{event['capacity']}** · Waiting: {len(waiting)}\n"
                    f"Reminder: {event['reminder_minutes']} minutes before start")
    for label, rows in [('Signed up', seated), ('Waiting list', waiting)]:
        lines = [line(row, index) for index, row in enumerate(rows[:20], 1)] or ['Nobody yet.']
        if len(rows) > 20:
            lines.append(f'…and {len(rows)-20} more. Ask an admin for the complete list.')
        chunk = ''
        for entry in lines:
            if len(chunk) + len(entry) + 1 > 1000:
                embed.add_field(name=label, value=chunk, inline=False)
                chunk, label = '', label + ' (continued)'
            chunk += entry + '\n'
        if len(embed.fields) < 24:
            embed.add_field(name=label, value=chunk, inline=False)
    embed.set_footer(text=f"Event #{event['id']} · Schedule #{event['series_id']}")
    return embed


class EventBoard(discord.ui.View):
    def __init__(self, event_id):
        super().__init__(timeout=None)
        self.event_id = event_id
        for label, action, style in [('Sign Up','join',discord.ButtonStyle.success),
                                     ('Drop Out','drop',discord.ButtonStyle.secondary)]:
            button = discord.ui.Button(label=label, style=style, custom_id=f'event:{action}:{event_id}')
            button.callback = self.on_join if action == 'join' else self.on_drop
            self.add_item(button)
        admin = discord.ui.Button(label='Admin', style=discord.ButtonStyle.secondary,
                                  custom_id=f'event:admin:{event_id}')
        admin.callback = self.on_admin
        self.add_item(admin)

    async def on_join(self, interaction):
        await change_signup(interaction, self.event_id, True)

    async def on_drop(self, interaction):
        await change_signup(interaction, self.event_id, False)

    async def on_admin(self, interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        await interaction.response.send_message('Manage this event:', view=EventAdminView(self.event_id), ephemeral=True)


class EventAdminView(discord.ui.View):
    def __init__(self, event_id):
        super().__init__(timeout=300)
        self.event_id = event_id

    async def interaction_check(self, interaction):
        if is_draft_admin(interaction):
            return True
        await interaction.response.send_message('Draft admins only.', ephemeral=True)
        return False

    @discord.ui.button(label='Edit', style=discord.ButtonStyle.primary)
    async def edit_button(self, interaction, button):
        event = get_event(self.event_id, interaction.guild.id)
        if not event or event['cancelled']:
            await interaction.response.send_message('Event not found.', ephemeral=True)
            return
        await interaction.response.send_modal(EditEventModal(event))

    @discord.ui.button(label='Add player', style=discord.ButtonStyle.secondary)
    async def add_button(self, interaction, button):
        await interaction.response.send_message('Select a registered player:',
            view=EventPlayerPicker(self.event_id, True), ephemeral=True)

    @discord.ui.button(label='Remove player', style=discord.ButtonStyle.secondary)
    async def remove_button(self, interaction, button):
        await interaction.response.send_message('Select a player:',
            view=EventPlayerPicker(self.event_id, False), ephemeral=True)

    @discord.ui.button(label='Reopen', style=discord.ButtonStyle.secondary)
    async def reopen_button(self, interaction, button):
        event = get_event(self.event_id, interaction.guild.id)
        if not event or event['cancelled']:
            await interaction.response.send_message('Event not found.', ephemeral=True)
            return
        with db() as conn:
            conn.execute('UPDATE event_occurrences SET reopened=1 WHERE id=?', (self.event_id,))
        await interaction.response.send_message('Signups reopened.', ephemeral=True)
        await refresh_event(interaction.client, self.event_id)

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction, button):
        await interaction.response.send_message('Confirm cancellation:',
            view=CancelEventView(self.event_id), ephemeral=True)


class EventPlayerPicker(discord.ui.View):
    def __init__(self, event_id, joining):
        super().__init__(timeout=300)
        self.event_id, self.joining = event_id, joining
        self.player_select = discord.ui.UserSelect(placeholder='Choose a player')
        self.player_select.callback = self.selected
        self.add_item(self.player_select)

    async def selected(self, interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        await change_signup(interaction, self.event_id, self.joining, self.player_select.values[0])


class CancelEventView(discord.ui.View):
    def __init__(self, event_id):
        super().__init__(timeout=120)
        self.event_id = event_id

    async def cancel(self, interaction, entire):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        event = get_event(self.event_id, interaction.guild.id)
        if not event:
            await interaction.response.send_message('Event not found.', ephemeral=True)
            return
        await cancel_events(interaction.client, interaction.guild.id,
                            event['series_id'] if entire else self.event_id, entire)
        await interaction.response.send_message('Cancelled.', ephemeral=True)
        self.stop()

    @discord.ui.button(label='This date', style=discord.ButtonStyle.danger)
    async def date_button(self, interaction, button):
        await self.cancel(interaction, False)

    @discord.ui.button(label='Entire schedule', style=discord.ButtonStyle.danger)
    async def series_button(self, interaction, button):
        await self.cancel(interaction, True)


async def dm(bot, user_id, message):
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await user.send(message)
    except (discord.HTTPException, discord.Forbidden):
        pass


async def update_occurrence(bot, event, name, date, clock, capacity, reminder):
    series = get_series(event['series_id'], event['guild_id'])
    clock = normalize_time(clock)
    validate(name, date, clock, series['time_zone'], capacity, '', reminder)
    stamp = local_start(date, clock, series['time_zone'])
    if stamp <= int(datetime.now(UTC).timestamp()):
        raise ValueError('New start must be in the future.')
    enrolled = signups(event['id'])
    seated = sum(row['area'] == 'seat' for row in enrolled)
    if capacity < seated:
        raise ValueError(f'Limit cannot be below {seated} signed up players.')
    with db() as conn:
        conn.execute('''UPDATE event_occurrences SET name=?,starts_at=?,capacity=?,reminder_minutes=?,
            reminder_sent=0,start_sent=0 WHERE id=?''', (name.strip(), stamp, capacity, reminder, event['id']))
        promoted = []
        for _ in range(capacity - seated):
            next_row = conn.execute("SELECT user_id FROM event_signups WHERE occurrence_id=? AND area='wait' ORDER BY position LIMIT 1", (event['id'],)).fetchone()
            if not next_row:
                break
            promoted.append(next_row['user_id'])
            conn.execute("UPDATE event_signups SET area='seat',position=(SELECT COALESCE(MAX(position),0)+1 FROM event_signups WHERE occurrence_id=? AND area='seat') WHERE occurrence_id=? AND user_id=?", (event['id'], event['id'], next_row['user_id']))
    changed = name.strip() != event['name'] or stamp != event['starts_at']
    if changed:
        for row in enrolled:
            await dm(bot, row['user_id'], f"Event updated: {discord.utils.escape_mentions(name.strip())} — <t:{stamp}:F> (previously {discord.utils.escape_mentions(event['name'])} — <t:{event['starts_at']}:F>)." )
    for user_id in promoted:
        await dm(bot, user_id, f'A spot opened in {name}! You are now signed up for <t:{stamp}:F>.')
    await refresh_event(bot, event['id'])


async def cancel_events(bot, guild_id, identifier, entire):
    now = int(datetime.now(UTC).timestamp())
    with db() as conn:
        if entire:
            conn.execute('UPDATE event_series SET cancelled=1 WHERE id=? AND guild_id=?', (identifier, guild_id))
            affected = [row[0] for row in conn.execute('SELECT id FROM event_occurrences WHERE series_id=? AND guild_id=? AND cancelled=0 AND starts_at>?', (identifier, guild_id, now))]
            conn.execute('UPDATE event_occurrences SET cancelled=1 WHERE series_id=? AND guild_id=? AND starts_at>?', (identifier, guild_id, now))
        else:
            affected = [identifier] if conn.execute('SELECT 1 FROM event_occurrences WHERE id=? AND guild_id=? AND cancelled=0', (identifier, guild_id)).fetchone() else []
            conn.execute('UPDATE event_occurrences SET cancelled=1 WHERE id=? AND guild_id=?', (identifier, guild_id))
    for event_id in affected:
        event = get_event(event_id)
        for row in signups(event_id):
            await dm(bot, row['user_id'], f"Cancelled: {discord.utils.escape_mentions(event['name'])} — <t:{event['starts_at']}:F>.")
        await refresh_event(bot, event_id)


class EditEventModal(discord.ui.Modal, title='Edit event date'):
    name = discord.ui.TextInput(label='Event name', max_length=100)
    date = discord.ui.TextInput(label='Date (YYYY-MM-DD)')
    clock = discord.ui.TextInput(label='Time (8 PM or 20:00)')
    capacity = discord.ui.TextInput(label='Player limit')
    reminder = discord.ui.TextInput(label='Reminder minutes')

    def __init__(self, event):
        super().__init__()
        self.event_id = event['id']
        series = get_series(event['series_id'], event['guild_id'])
        local = datetime.fromtimestamp(event['starts_at'], zone_info(series['time_zone']))
        for field, value in ((self.name, event['name']), (self.date, local.strftime('%Y-%m-%d')),
                             (self.clock, local.strftime('%I:%M %p')), (self.capacity, str(event['capacity'])),
                             (self.reminder, str(event['reminder_minutes']))):
            field.default = value

    async def on_submit(self, interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        event = get_event(self.event_id, interaction.guild.id)
        if not event or event['cancelled']:
            await interaction.response.send_message('Event not found.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await update_occurrence(interaction.client, event, self.name.value, self.date.value,
                                    self.clock.value, int(self.capacity.value), int(self.reminder.value))
        except (ValueError, sqlite3.IntegrityError) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        await interaction.followup.send('Occurrence updated.', ephemeral=True)


async def create_schedule(interaction, data, zone, weekdays):
    try:
        name, date, clock, capacity, reminder = data
        capacity, reminder = int(capacity), int(reminder)
        clock, zone = normalize_time(clock), normalize_zone(zone)
        validate(name, date, clock, zone, capacity, weekdays, reminder)
        if not weekdays and local_start(date, clock, zone) <= int(datetime.now(UTC).timestamp()):
            raise ValueError('The event must start in the future.')
        with db() as conn:
            cur = conn.execute('''INSERT INTO event_series
                (guild_id,name,local_time,time_zone,first_date,weekdays,capacity,reminder_minutes)
                VALUES (?,?,?,?,?,?,?,?)''', (interaction.guild.id, name.strip(), clock, zone, date, weekdays, capacity, reminder))
            series_id = cur.lastrowid
        materialize(series_id)
        await interaction.response.send_message(f'Created schedule #{series_id}. The next event board will appear in the events channel; later dates are available through /events.', ephemeral=True)
        await process_events(interaction.client)
    except (ValueError, sqlite3.IntegrityError) as exc:
        await interaction.response.send_message(str(exc), ephemeral=True)


class CreateEventModal(discord.ui.Modal, title='Create an event'):
    name = discord.ui.TextInput(label='Event name', max_length=100)
    date = discord.ui.TextInput(label='First date (YYYY-MM-DD)', placeholder='2026-10-06')
    clock = discord.ui.TextInput(label='Time (8 PM or 20:00)', placeholder='8 PM')
    capacity = discord.ui.TextInput(label='Player limit', placeholder='8')
    reminder = discord.ui.TextInput(label='Reminder minutes', default='60')

    async def on_submit(self, interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        data = tuple(field.value for field in (self.name, self.date, self.clock, self.capacity, self.reminder))
        try:
            int(data[3]); int(data[4]); normalize_time(data[2]); datetime.strptime(data[1], '%Y-%m-%d')
        except ValueError:
            await interaction.response.send_message('Check the date, time, player limit, and reminder minutes.', ephemeral=True)
            return
        await interaction.response.send_message('Choose a time zone:', view=CreateZoneView(data), ephemeral=True)


class CustomZoneModal(discord.ui.Modal, title='Custom time zone'):
    zone = discord.ui.TextInput(label='GMT offset or region', placeholder='GMT+2 or Europe/London')

    def __init__(self, data):
        super().__init__()
        self.data = data

    async def on_submit(self, interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        try:
            zone = normalize_zone(self.zone.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message('Repeat weekly? Select every day you want, or choose One-time.', view=CreateRepeatView(self.data, zone), ephemeral=True)


class CreateZoneView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=300)
        self.data = data
        self.zone_select = discord.ui.Select(placeholder='Choose a time zone', options=[
            discord.SelectOption(label=label, value=value) for label, value in TIME_ZONE_CHOICES])
        self.zone_select.callback = self.selected
        self.add_item(self.zone_select)

    async def selected(self, interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        await interaction.response.send_message('Repeat weekly? Select every day you want, or choose One-time.',
            view=CreateRepeatView(self.data, self.zone_select.values[0]), ephemeral=True)

    @discord.ui.button(label='Custom GMT offset', style=discord.ButtonStyle.secondary)
    async def custom(self, interaction, button):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        await interaction.response.send_modal(CustomZoneModal(self.data))


class CreateRepeatView(discord.ui.View):
    def __init__(self, data, zone):
        super().__init__(timeout=300)
        self.data, self.zone = data, zone
        self.weekday_select = discord.ui.Select(placeholder='Weekly days (choose one or more)', min_values=1, max_values=7,
            options=[discord.SelectOption(label=day, value=str(index)) for index, day in enumerate(calendar.day_name)])
        self.weekday_select.callback = self.weekly
        self.add_item(self.weekday_select)

    async def weekly(self, interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        weekdays = ','.join(sorted(self.weekday_select.values, key=int))
        await create_schedule(interaction, self.data, self.zone, weekdays)
        self.stop()

    @discord.ui.button(label='One-time', style=discord.ButtonStyle.primary)
    async def once(self, interaction, button):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.', ephemeral=True)
            return
        await create_schedule(interaction, self.data, self.zone, '')
        self.stop()


class EventListView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=900)
        self.events = {str(event['id']): event['id'] for event in rows}
        self.event_select = discord.ui.Select(placeholder='Choose a date to sign up or drop out', options=[
            discord.SelectOption(label=f"{event['name'][:45]} · {datetime.fromtimestamp(event['starts_at'], UTC):%b %d %H:%M} UTC",
                                 value=str(event['id'])) for event in rows])
        self.event_select.callback = self.selected
        self.add_item(self.event_select)

    async def selected(self, interaction):
        event_id = self.events.get(self.event_select.values[0])
        event = get_event(event_id, interaction.guild.id) if event_id else None
        if not event or event['cancelled']:
            await interaction.response.send_message('This date is no longer available. Run /events again.', ephemeral=True)
            return
        await interaction.response.send_message(embed=board_embed(event), view=EventBoard(event_id), ephemeral=True)

async def change_signup(interaction, event_id, joining, admin_user=None):
    event = get_event(event_id, interaction.guild.id)
    if not event:
        await interaction.response.send_message('Event not found in this server.', ephemeral=True)
        return
    user = admin_user or interaction.user
    if joining and (event['cancelled'] or (event['starts_at'] <= int(datetime.now(UTC).timestamp()) and not event['reopened'])):
        await interaction.response.send_message('Signups are closed.', ephemeral=True)
        return
    load_players()
    player = players.get(user.id)
    if joining and (not player or not player.get('ign') or not player.get('roles')):
        await interaction.response.send_message('Player must register an IGN and role preferences first.', ephemeral=True)
        return
    promoted = None
    try:
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute('SELECT area FROM event_signups WHERE occurrence_id=? AND user_id=?', (event_id,user.id)).fetchone()
            if joining:
                if existing:
                    result = 'Already signed up.'
                else:
                    count = conn.execute("SELECT COUNT(*) FROM event_signups WHERE occurrence_id=? AND area='seat'", (event_id,)).fetchone()[0]
                    area = 'seat' if count < event['capacity'] else 'wait'
                    pos = conn.execute('SELECT COALESCE(MAX(position),0)+1 FROM event_signups WHERE occurrence_id=? AND area=?', (event_id,area)).fetchone()[0]
                    conn.execute('''INSERT INTO event_signups
                        (occurrence_id,user_id,position,area,ign,roles,discord_name,server_name,joined_at)
                        VALUES (?,?,?,?,?,?,?,?,?)''', (event_id,user.id,pos,area,player['ign'],
                        ', '.join(player['roles']),str(user),user.display_name,int(datetime.now(UTC).timestamp())))
                    result = 'Signed up.' if area == 'seat' else 'Added to the waiting list.'
            elif not existing:
                result = 'Not signed up for this event.'
            else:
                conn.execute('DELETE FROM event_signups WHERE occurrence_id=? AND user_id=?', (event_id,user.id))
                result = 'Removed from this event.'
                if existing['area'] == 'seat' and (event['starts_at'] > int(datetime.now(UTC).timestamp()) or event['reopened']):
                    next_row = conn.execute("SELECT user_id FROM event_signups WHERE occurrence_id=? AND area='wait' ORDER BY position LIMIT 1", (event_id,)).fetchone()
                    if next_row:
                        promoted = next_row['user_id']
                        conn.execute("UPDATE event_signups SET area='seat', position=(SELECT COALESCE(MAX(position),0)+1 FROM event_signups WHERE occurrence_id=? AND area='seat') WHERE occurrence_id=? AND user_id=?", (event_id,event_id,promoted))
    except sqlite3.Error:
        await interaction.response.send_message('Could not save the signup. Please try again.', ephemeral=True)
        return
    await interaction.response.send_message(result, ephemeral=True)
    if result in ('Signed up.','Added to the waiting list.'):
        await dm(interaction.client,user.id,f"{result} {event['name']} — <t:{event['starts_at']}:F>.")
    if promoted:
        await dm(interaction.client,promoted,f"A spot opened in {event['name']}! You are now signed up for <t:{event['starts_at']}:F>.")
    await refresh_event(interaction.client,event_id)


async def refresh_event(bot, event_id):
    event = get_event(event_id)
    if not event or not event['message_id']:
        return
    config = get_guild_config(event['guild_id']) or {}
    channel = bot.get_channel(posted_channel_id(event, config))
    if not channel:
        return
    try:
        message = await channel.fetch_message(event['message_id'])
        await message.edit(embed=board_embed(event),view=EventBoard(event_id))
    except discord.HTTPException:
        pass


async def post_event(bot, event):
    async with POST_LOCK:
        await _post_event_locked(bot, event)


async def _post_event_locked(bot, event):
    event = get_event(event['id'])
    config = get_guild_config(event['guild_id']) or {}
    channel_id = configured_event_channel_id(config)
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    if event['message_id']:
        if posted_channel_id(event, config) == channel_id:
            return
        old_channel = bot.get_channel(posted_channel_id(event, config))
        if not old_channel:
            print(f"Cannot move event {event['id']}: old channel unavailable.")
            return
        try:
            await (await old_channel.fetch_message(event['message_id'])).delete()
        except discord.NotFound:
            pass
        except discord.HTTPException as exc:
            print(f"Cannot move event {event['id']}: {exc}")
            return
        with db() as conn:
            conn.execute('UPDATE event_occurrences SET message_id=NULL, channel_id=NULL WHERE id=?', (event['id'],))
    message = await channel.send(embed=board_embed(event),view=EventBoard(event['id']))
    with db() as conn:
        conn.execute('UPDATE event_occurrences SET message_id=?, channel_id=? WHERE id=? AND message_id IS NULL', (message.id,channel_id,event['id']))


async def remove_event_board(bot, event):
    config = get_guild_config(event['guild_id']) or {}
    channel = bot.get_channel(posted_channel_id(event, config))
    if not channel:
        return
    try:
        await (await channel.fetch_message(event['message_id'])).delete()
    except discord.NotFound:
        pass
    except discord.HTTPException as exc:
        print(f"Cannot remove event board {event['id']}: {exc}")
        return
    with db() as conn:
        conn.execute('UPDATE event_occurrences SET message_id=NULL,channel_id=NULL WHERE id=? AND message_id=?', (event['id'], event['message_id']))


async def process_events(bot):
    now = int(datetime.now(UTC).timestamp())
    with db() as conn:
        series_ids = [row[0] for row in conn.execute('SELECT id FROM event_series WHERE cancelled=0 AND paused=0')]
    for series_id in series_ids:
        materialize(series_id)
    with db() as conn:
        previous = [dict(row) for row in conn.execute('''SELECT * FROM event_occurrences
            WHERE starts_at<=? AND message_id IS NOT NULL AND series_id IN
            (SELECT id FROM event_series WHERE weekdays!='')''', (now,))]
        upcoming = [dict(row) for row in conn.execute('SELECT * FROM event_occurrences WHERE cancelled=0 AND starts_at>? ORDER BY starts_at,id', (now,))]
    first_by_series = {}
    for event in upcoming:
        first_by_series.setdefault(event['series_id'], event['id'])
    for event in previous:
        if event['series_id'] in first_by_series:
            await remove_event_board(bot, event)
    for event in upcoming:
        if event['id'] != first_by_series[event['series_id']]:
            if event['message_id']:
                await remove_event_board(bot, event)
            continue
        try:
            await post_event(bot,event)
        except discord.HTTPException as exc:
            print(f"Could not post event {event['id']}: {exc}")
    with db() as conn:
        due = [dict(row) for row in conn.execute('''SELECT * FROM event_occurrences WHERE cancelled=0 AND starts_at>? AND starts_at<?
            AND ((reminder_sent=0 AND starts_at-reminder_minutes*60<=?) OR (start_sent=0 AND starts_at<=?))''', (now-86400,now+86400,now,now))]
    for event in due:
        for column, deadline in [('reminder_sent',event['starts_at']-event['reminder_minutes']*60),('start_sent',event['starts_at'])]:
            if event[column] or now < deadline:
                continue
            with db() as conn:
                claim = conn.execute(f'UPDATE event_occurrences SET {column}=1 WHERE id=? AND {column}=0 AND cancelled=0', (event['id'],))
                if not claim.rowcount:
                    continue
            if column == 'reminder_sent' and now >= event['starts_at']:
                continue
            seated = [r for r in signups(event['id']) if r['area']=='seat']
            prefix = 'Starting soon' if column=='reminder_sent' else 'Starting now'
            message = f"**{prefix}:** {discord.utils.escape_mentions(event['name'])} — <t:{event['starts_at']}:F>"
            config = get_guild_config(event['guild_id']) or {}
            channel = bot.get_channel(configured_event_channel_id(config))
            if channel:
                for start in range(0,len(seated),20):
                    mentions = ' '.join(f"<@{row['user_id']}>" for row in seated[start:start+20])
                    try:
                        await channel.send(message+'\n'+mentions,allowed_mentions=discord.AllowedMentions(users=True,roles=False,everyone=False))
                    except discord.HTTPException as exc:
                        print(f"Event {event['id']} channel reminder failed: {exc}")
                if not seated:
                    await channel.send(message,allowed_mentions=discord.AllowedMentions.none())
            for row in seated:
                await dm(bot,row['user_id'],message)
            await refresh_event(bot,event['id'])


async def event_loop(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await process_events(bot)
        except Exception as exc:
            print(f'Event processing failed: {exc!r}')
        await asyncio.sleep(5)


def register_event_commands(bot):
    group = app_commands.Group(name='event', description='Manage scheduled event signups')

    @group.command(name='create',description='Create a one-time or weekly scheduled event')
    async def create(interaction:discord.Interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        if not configured_event_channel_id(get_guild_config(interaction.guild.id) or {}):
            await interaction.response.send_message('Run /setup to configure an events channel first.',ephemeral=True);return
        await interaction.response.send_modal(CreateEventModal())

    @group.command(name='edit',description='Edit a single occurrence (future dates stay unchanged)')
    @app_commands.describe(time='8 PM, 8:30 PM, or 20:30')
    async def edit(interaction:discord.Interaction,event_id:int,name:str=None,date:str=None,time:str=None,players_needed:int=None,reminder_minutes:int=None):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        event=get_event(event_id,interaction.guild.id)
        if not event or event['cancelled']:
            await interaction.response.send_message('Event not found.',ephemeral=True);return
        series=get_series(event['series_id'],interaction.guild.id)
        current=datetime.fromtimestamp(event['starts_at'],zone_info(series['time_zone']))
        name=name if name is not None else event['name']
        date=date or current.strftime('%Y-%m-%d')
        time=time or current.strftime('%H:%M')
        players_needed=players_needed if players_needed is not None else event['capacity']
        reminder_minutes=reminder_minutes if reminder_minutes is not None else event['reminder_minutes']
        await interaction.response.defer(ephemeral=True)
        try:
            await update_occurrence(bot,event,name,date,time,players_needed,reminder_minutes)
        except (ValueError,sqlite3.IntegrityError) as exc:
            await interaction.followup.send(str(exc),ephemeral=True)
            return
        await interaction.followup.send('Occurrence updated.',ephemeral=True)

    @group.command(name='editseries',description='Change the weekly pattern and settings for future dates')
    @app_commands.describe(time='8 PM, 8:30 PM, or 20:30',time_zone='Select Eastern, Central, etc., or enter GMT+2')
    @app_commands.autocomplete(time_zone=timezone_autocomplete)
    async def editseries(interaction:discord.Interaction,series_id:int,name:str=None,time:str=None,time_zone:str=None,players_needed:int=None,weekdays:str=None,reminder_minutes:int=None):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        row=get_series(series_id,interaction.guild.id)
        if not row or row['cancelled']:
            await interaction.response.send_message('Schedule not found.',ephemeral=True);return
        try:
            vals=(name if name is not None else row['name'],normalize_time(time) if time is not None else row['local_time'],normalize_zone(time_zone) if time_zone is not None else row['time_zone'],players_needed if players_needed is not None else row['capacity'],parse_weekdays(weekdays) if weekdays is not None else row['weekdays'],reminder_minutes if reminder_minutes is not None else row['reminder_minutes'])
            validate(vals[0],row['first_date'],vals[1],vals[2],vals[3],vals[4],vals[5])
        except ValueError as exc:
            await interaction.response.send_message(str(exc),ephemeral=True);return
        # Preserve booked dates and their players; replace empty future boards.
        with db() as conn:
            obsolete=[dict(r) for r in conn.execute('''SELECT * FROM event_occurrences WHERE series_id=? AND starts_at>? AND NOT EXISTS
                (SELECT 1 FROM event_signups WHERE occurrence_id=event_occurrences.id)''',(series_id,int(datetime.now(UTC).timestamp())))]
        config=get_guild_config(interaction.guild.id) or {}
        for old in obsolete:
            channel=bot.get_channel(posted_channel_id(old, config))
            if old['message_id'] and not channel:
                await interaction.response.send_message('Could not find an old event board channel. Check channel permissions and retry.',ephemeral=True)
                return
            if channel and old['message_id']:
                try:await (await channel.fetch_message(old['message_id'])).delete()
                except discord.NotFound:pass
                except discord.HTTPException:
                    await interaction.response.send_message('Could not remove an old board. Check channel permissions and retry.',ephemeral=True)
                    return
        with db() as conn:
            for old in obsolete:
                conn.execute('DELETE FROM event_occurrences WHERE id=?',(old['id'],))
            conn.execute('''UPDATE event_series SET name=?,local_time=?,time_zone=?,capacity=?,weekdays=?,reminder_minutes=? WHERE id=?''',(*vals,series_id))
        materialize(series_id)
        await interaction.response.send_message('Updated future schedule. Existing dates with signups were kept.',ephemeral=True)
        await process_events(bot)

    @group.command(name='cancel',description='Cancel one event date or an entire schedule')
    async def cancel(interaction:discord.Interaction,id:int,entire_schedule:bool=False):
        if not is_draft_admin(interaction):
            await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        if entire_schedule:
            if not get_series(id,interaction.guild.id):
                await interaction.response.send_message('Schedule not found.',ephemeral=True);return
        elif not get_event(id,interaction.guild.id):
            await interaction.response.send_message('Event not found.',ephemeral=True);return
        await interaction.response.defer(ephemeral=True)
        await cancel_events(bot,interaction.guild.id,id,entire_schedule)
        await interaction.followup.send('Cancelled.',ephemeral=True)

    @group.command(name='pause',description='Pause generating future dates for a weekly schedule')
    async def pause(interaction:discord.Interaction,series_id:int):
        await set_pause(interaction,series_id,True)

    @group.command(name='resume',description='Resume generating dates for a weekly schedule')
    async def resume(interaction:discord.Interaction,series_id:int):
        await set_pause(interaction,series_id,False)

    async def set_pause(interaction,series_id,paused):
        if not is_draft_admin(interaction):await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        row=get_series(series_id,interaction.guild.id)
        if not row or row['cancelled'] or not row['weekdays']:
            await interaction.response.send_message('Active weekly schedule not found.',ephemeral=True);return
        with db() as conn:
            conn.execute('UPDATE event_series SET paused=? WHERE id=?',(int(paused),series_id))
            if paused:
                affected=[r[0] for r in conn.execute('SELECT id FROM event_occurrences WHERE series_id=? AND cancelled=0 AND starts_at>?',(series_id,int(datetime.now(UTC).timestamp())))]
                conn.execute('UPDATE event_occurrences SET cancelled=1,pause_cancelled=1 WHERE series_id=? AND cancelled=0 AND starts_at>?',(series_id,int(datetime.now(UTC).timestamp())))
            else:
                affected=[r[0] for r in conn.execute('SELECT id FROM event_occurrences WHERE series_id=? AND pause_cancelled=1 AND starts_at>?',(series_id,int(datetime.now(UTC).timestamp())))]
                conn.execute('UPDATE event_occurrences SET cancelled=0,pause_cancelled=0 WHERE series_id=? AND pause_cancelled=1 AND starts_at>?',(series_id,int(datetime.now(UTC).timestamp())))
        if not paused:materialize(series_id)
        await interaction.response.send_message('Schedule paused.' if paused else 'Schedule resumed.',ephemeral=True)
        for event_id in affected:await refresh_event(bot,event_id)
        if not paused:await process_events(bot)

    @group.command(name='reopen',description='Reopen a date for late signups')
    async def reopen(interaction:discord.Interaction,event_id:int):
        if not is_draft_admin(interaction):await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        event=get_event(event_id,interaction.guild.id)
        if not event or event['cancelled']:await interaction.response.send_message('Event not found.',ephemeral=True);return
        with db() as conn:conn.execute('UPDATE event_occurrences SET reopened=1 WHERE id=?',(event_id,))
        await interaction.response.send_message('Signups reopened.',ephemeral=True)
        await refresh_event(bot,event_id)

    @group.command(name='add',description='Add a registered player to an event')
    async def add(interaction:discord.Interaction,event_id:int,player:discord.Member):
        if not is_draft_admin(interaction):await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        await change_signup(interaction,event_id,True,player)

    @group.command(name='remove',description='Remove a player and promote the waiting list')
    async def remove(interaction:discord.Interaction,event_id:int,player:discord.Member):
        if not is_draft_admin(interaction):await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        await change_signup(interaction,event_id,False,player)

    @group.command(name='copy',description='Copy an event setup to a new date')
    @app_commands.describe(time='Optional new time: 8 PM, 8:30 PM, or 20:30')
    async def copy(interaction:discord.Interaction,event_id:int,date:str,time:str=None):
        if not is_draft_admin(interaction):await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        event=get_event(event_id,interaction.guild.id)
        if not event:await interaction.response.send_message('Event not found.',ephemeral=True);return
        series=get_series(event['series_id'],interaction.guild.id)
        clock=time or datetime.fromtimestamp(event['starts_at'],zone_info(series['time_zone'])).strftime('%H:%M')
        try:
            clock=normalize_time(clock)
            validate(event['name'],date,clock,series['time_zone'],event['capacity'],'',event['reminder_minutes'])
            if local_start(date,clock,series['time_zone'])<=int(datetime.now(UTC).timestamp()):raise ValueError('Use a future date.')
        except ValueError as exc:await interaction.response.send_message(str(exc),ephemeral=True);return
        with db() as conn:
            cur=conn.execute('''INSERT INTO event_series (guild_id,name,local_time,time_zone,first_date,weekdays,capacity,reminder_minutes)
                VALUES (?,?,?,?,?,'',?,?)''',(interaction.guild.id,event['name'],clock,series['time_zone'],date,event['capacity'],event['reminder_minutes']))
            new_id=cur.lastrowid
        materialize(new_id)
        await interaction.response.send_message(f'Copied to schedule #{new_id}.',ephemeral=True)
        await process_events(bot)

    @group.command(name='history',description='Show past event signups (admin only)')
    async def history(interaction:discord.Interaction,event_id:int=None):
        if not is_draft_admin(interaction):await interaction.response.send_message('Draft admins only.',ephemeral=True);return
        if event_id is None:
            with db() as conn:
                past=[dict(r) for r in conn.execute('SELECT * FROM event_occurrences WHERE guild_id=? AND starts_at<? ORDER BY starts_at DESC LIMIT 15',(interaction.guild.id,int(datetime.now(UTC).timestamp())))]
            await interaction.response.send_message('\n'.join(fmt_event(row) for row in past)[:1900] if past else 'No past events.',ephemeral=True)
            return
        event=get_event(event_id,interaction.guild.id)
        if not event:await interaction.response.send_message('Event not found.',ephemeral=True);return
        lines=[f"{r['area']}: {r['ign']} ({r['discord_name']})" for r in signups(event_id)]
        await interaction.response.send_message(fmt_event(event)+'\n'+'\n'.join(lines or ['No signups.'])[:1700],ephemeral=True)

    bot.tree.add_command(group)

    @bot.tree.command(name='events',description='List upcoming scheduled event signup boards')
    async def events(interaction:discord.Interaction):
        now=int(datetime.now(UTC).timestamp())
        with db() as conn:
            rows=[dict(r) for r in conn.execute('''SELECT * FROM event_occurrences WHERE guild_id=? AND cancelled=0 AND starts_at>=? ORDER BY starts_at LIMIT 25''',(interaction.guild.id,now))]
        config=get_guild_config(interaction.guild.id) or {}
        lines=[]
        for event in rows:
            seats=sum(r['area']=='seat' for r in signups(event['id']))
            channel_id=posted_channel_id(event, config)
            link=f"[Board](https://discord.com/channels/{interaction.guild.id}/{channel_id}/{event['message_id']})" if event['message_id'] and channel_id else 'Select below to sign up'
            lines.append(f"{fmt_event(event)} · {seats}/{event['capacity']} · {link}")
        await interaction.response.send_message('\n'.join(lines)[:1900] if lines else 'No upcoming events.',
            view=EventListView(rows) if rows else None,ephemeral=True)
