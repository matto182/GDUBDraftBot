import discord
from discord import app_commands

from commands import register_commands
from config import TOKEN
from database import init_db
import draft_service as svc
from views import DraftBoardView
from scheduled_events import init_events, event_loop, EventBoard, db


class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        init_db()
        init_events()
        svc.set_bot(self)
        svc.load_players()
        register_commands(self)

        await self.tree.sync()

        self.add_view(DraftBoardView(svc.get_view_context))
        with db() as conn:
            event_ids = [row[0] for row in conn.execute(
                "SELECT id FROM event_occurrences WHERE message_id IS NOT NULL AND starts_at > strftime('%s','now')-86400")]
        for event_id in event_ids:
            self.add_view(EventBoard(event_id))
        self.event_task = self.loop.create_task(event_loop(self))


bot = MyBot()


@bot.event
async def on_message(message: discord.Message):
    await svc.handle_owner_prefix_message(message)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    if not getattr(bot, "already_synced_commands", False):
        bot.already_synced_commands = True

        for guild in bot.guilds:
            try:
                guild_obj = discord.Object(id=guild.id)

                bot.tree.copy_global_to(guild=guild_obj)
                synced = await bot.tree.sync(guild=guild_obj)

                print(f"Synced {len(synced)} commands to {guild.name}")
            except Exception as error:
                print(f"Failed to sync commands to {guild.name}: {error}")

    if getattr(bot, "already_posted_board", False):
        return

    bot.already_posted_board = True

    for guild in bot.guilds:
        await svc.post_new_draft_board(guild.id)


bot.run(TOKEN)
