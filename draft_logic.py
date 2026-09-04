"""Compatibility facade for draft balancing and captain-draft logic.

The implementation is split into focused modules, while this module preserves
the original import surface used by the rest of the bot and the regression
suite.
"""

import random
from functools import lru_cache

from config import BACKLINE_ROLES, normalize_roles
from draft_constants import (
    TEAM_FORMATIONS,
    ROLE_ORDER,
    PREFERENCE_COST,
    HISTORICAL_BACKLINE_COST,
    OFF_ROLE_COST,
    COMPOSITION_QUALITY_WEIGHT,
    EXTREME_WEIGHT_THRESHOLD,
)
from role_assignment import (
    role_sort_key,
    _normalized_roles_for_player,
    role_priority_index,
    assignment_cost,
    _build_role_cache,
    _priority_from_roles,
    _cost_from_roles,
    _solve_formation,
    assign_best_team_roles,
    optimize_team_roles,
)
from balance_scoring import (
    team_weight,
    effective_team_strength,
    _extreme_rule_is_feasible,
    _violates_extreme_stack,
    score_match,
)
from random_draft import (
    _quick_team_penalty,
    generate_random_teams,
)
from captain_draft import CaptainDraft
from role_needs import analyze_role_needs


__all__ = [
    "TEAM_FORMATIONS",
    "ROLE_ORDER",
    "PREFERENCE_COST",
    "HISTORICAL_BACKLINE_COST",
    "OFF_ROLE_COST",
    "COMPOSITION_QUALITY_WEIGHT",
    "EXTREME_WEIGHT_THRESHOLD",
    "role_sort_key",
    "_normalized_roles_for_player",
    "role_priority_index",
    "assignment_cost",
    "_build_role_cache",
    "_priority_from_roles",
    "_cost_from_roles",
    "_solve_formation",
    "assign_best_team_roles",
    "optimize_team_roles",
    "team_weight",
    "effective_team_strength",
    "_extreme_rule_is_feasible",
    "_violates_extreme_stack",
    "score_match",
    "_quick_team_penalty",
    "generate_random_teams",
    "CaptainDraft",
    "analyze_role_needs",
]
