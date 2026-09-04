import player_alias_repository as repository


def record_name_change(user_id, previous_ign, new_ign, db_file=None):
    previous_ign = str(previous_ign or "").strip()
    new_ign = str(new_ign or "").strip()

    if not previous_ign or not new_ign:
        return False

    if previous_ign.casefold() == new_ign.casefold():
        return False

    saved = repository.save_player_alias(
        user_id,
        previous_ign,
        db_file=db_file,
    )

    # If the player returns to an older IGN, it is current again rather than previous.
    repository.remove_player_alias(user_id, new_ign, db_file=db_file)
    return saved


def get_player_aliases(user_id, db_file=None):
    return repository.get_player_aliases(user_id, db_file=db_file)


def resolve_alias_user_id(identifier, db_file=None):
    return repository.resolve_alias_user_id(identifier, db_file=db_file)
