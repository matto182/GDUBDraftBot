class GuildState:
    def __init__(self):
        self.lobby = []
        self.waiting_room = []
        self.votes = {}
        self.captain_volunteers = []
        self.draft_result = None
        self.captain_draft = None
        self.final_team_a = []
        self.final_team_b = []
        self.last_signup_time = None


guild_states = {}


def get_state(guild_id):
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildState()

    return guild_states[guild_id]