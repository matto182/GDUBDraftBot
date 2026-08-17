import discord
from discord import app_commands

from config import TOKEN
from database import init_db
from views import DraftBoardView

import draft_service as svc
from commands import register_commands


class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        init_db()
        svc.load_players()
        svc.set_bot(self)
        register_commands(self)

        await self.tree.sync()
        self.add_view(DraftBoardView(svc.get_view_context))
        # self.loop.create_task(self.inactivity_check_loop())
        # This makes the lobby reset automatically if no one signs up for 2 hours.


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
            except Exception as e:
                print(f"Failed to sync commands to {guild.name}: {e}")

    if getattr(bot, "already_posted_board", False):
        return

    bot.already_posted_board = True

    for guild in bot.guilds:
        await svc.post_new_draft_board(guild.id)


bot.run(TOKEN)
