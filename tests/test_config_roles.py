import config


def test_current_selectable_roles_are_exactly_expected():
    assert config.ROLES == [
        "Frontline",
        "Midline",
        "Prot Monk",
        "Heal Monk",
        "8 Support",
    ]


def test_role_category_sets_cover_all_selectable_roles_without_overlap():
    category_sets = [
        config.FRONTLINE_ROLES,
        config.MIDLINE_ROLES,
        config.BACKLINE_ROLES,
    ]

    combined = set().union(*category_sets)

    assert combined == set(config.ROLES)
    assert config.FRONTLINE_ROLES.isdisjoint(config.MIDLINE_ROLES)
    assert config.FRONTLINE_ROLES.isdisjoint(config.BACKLINE_ROLES)
    assert config.MIDLINE_ROLES.isdisjoint(config.BACKLINE_ROLES)


def test_flex_roles_constant_does_not_exist():
    assert not hasattr(config, "FLEX_ROLES")


def test_legacy_lyssa_role_is_not_selectable():
    assert "Lyssa/Flex Derv" not in config.ROLES


def test_legacy_lyssa_role_normalizes_to_frontline():
    assert config.normalize_roles(["Lyssa/Flex Derv"]) == ["Frontline"]


def test_legacy_profession_roles_normalize_to_midline():
    assert config.normalize_roles(
        ["Mesmer", "Elementalist", "Necromancer", "Ranger"]
    ) == ["Midline"]


def test_legacy_support_role_normalizes_to_current_support_role():
    assert config.normalize_roles(["Support/Flag (8)"]) == ["8 Support"]


def test_normalization_preserves_priority_and_removes_duplicates():
    assert config.normalize_roles(
        ["Mesmer", "Frontline", "Midline", "Prot Monk", "Mesmer"]
    ) == ["Midline", "Frontline", "Prot Monk"]


def test_normalization_accepts_comma_separated_database_text():
    assert config.normalize_roles("Frontline,Mesmer,Heal Monk") == [
        "Frontline",
        "Midline",
        "Heal Monk",
    ]
