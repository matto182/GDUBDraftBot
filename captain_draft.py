from config import normalize_roles

class CaptainDraft:
    def __init__(self, lobby, captain_a, captain_b):
        self.captain_a = captain_a
        self.captain_b = captain_b
        self.team_a = [(captain_a, "Captain")]
        self.team_b = [(captain_b, "Captain")]
        self.available = [p for p in lobby if p not in [captain_a, captain_b]]
        self.pick_index = 0
        self.pick_order = self.build_pick_order()

    def build_pick_order(self):
        order = []
        pattern = [self.captain_a, self.captain_b, self.captain_b, self.captain_a]
        while len(order) < 14:
            order.extend(pattern)
        return order[:14]

    def current_picker(self):
        if self.pick_index >= len(self.pick_order):
            return None
        return self.pick_order[self.pick_index]

    def is_complete(self):
        return len(self.team_a) == 8 and len(self.team_b) == 8

    def pick_player(self, players, picker_id, picked_id):
        if picker_id != self.current_picker():
            return False, "It is not your pick."
        if picked_id not in self.available:
            return False, "That player is not available."
        roles = normalize_roles(players[picked_id].get("roles", []))
        assigned_role = roles[0] if roles else "Unassigned"
        if picker_id == self.captain_a:
            self.team_a.append((picked_id, assigned_role))
        else:
            self.team_b.append((picked_id, assigned_role))
        self.available.remove(picked_id)
        self.pick_index += 1
        return True, "Pick accepted."
