from draft_constants import COMPOSITION_QUALITY_WEIGHT, EXTREME_WEIGHT_THRESHOLD

def team_weight(team_result, player_weights):
    return sum(
        player_weights.get(user_id, 0)
        for user_id, _role in team_result["team"]
    )

def effective_team_strength(team_result, player_weights):
    # Debug-only summary. Team selection itself uses explicit weight difference
    # plus composition quality in score_match below.
    return team_weight(team_result, player_weights) - team_result["score"]

def _extreme_rule_is_feasible(lobby, player_weights):
    strong = sum(
        1 for user_id in lobby
        if player_weights.get(user_id, 0) >= EXTREME_WEIGHT_THRESHOLD
    )
    weak = sum(
        1 for user_id in lobby
        if player_weights.get(user_id, 0) <= -EXTREME_WEIGHT_THRESHOLD
    )
    return strong <= 2 and weak <= 2

def _violates_extreme_stack(team_ids, player_weights):
    strong = sum(
        1 for user_id in team_ids
        if player_weights.get(user_id, 0) >= EXTREME_WEIGHT_THRESHOLD
    )
    weak = sum(
        1 for user_id in team_ids
        if player_weights.get(user_id, 0) <= -EXTREME_WEIGHT_THRESHOLD
    )
    return strong > 1 or weak > 1

def score_match(team_a_result, team_b_result, player_weights):
    weight_a = team_weight(team_a_result, player_weights)
    weight_b = team_weight(team_b_result, player_weights)
    weight_difference = abs(weight_a - weight_b)

    composition_total = team_a_result["score"] + team_b_result["score"]
    composition_difference = abs(team_a_result["score"] - team_b_result["score"])

    return (
        weight_difference
        + (composition_total * COMPOSITION_QUALITY_WEIGHT)
        + (composition_difference * 0.05)
    )
