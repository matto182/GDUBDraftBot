from database import load_players_into


players = {}
bot_client = None


def set_bot(client):
    global bot_client
    bot_client = client


def load_players():
    load_players_into(players)
