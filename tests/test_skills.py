from app.core.optimizer import choose_skills


def test_skill_choice_picks_exact_amount_and_prefers_role_synergy():
    proficiency_choices = [
        {
            "choose": 2,
            "from": [
                {
                    "index": "skill-athletics",
                    "name": "Skill: Athletics",
                    "url": "/api/proficiencies/",
                },
                {"index": "skill-stealth", "name": "Skill: Stealth", "url": "/api/proficiencies/"},
                {
                    "index": "skill-perception",
                    "name": "Skill: Perception",
                    "url": "/api/proficiencies/",
                },
                {"index": "skill-arcana", "name": "Skill: Arcana", "url": "/api/proficiencies/"},
            ],
        }
    ]
    mods = {"STR": 1, "DEX": 3, "CON": 2, "INT": 0, "WIS": 1, "CHA": 0}

    picked, _ = choose_skills(proficiency_choices, ability_mods=mods, role="skills", seed=7)

    assert len(picked) == 2
    assert "Stealth" in picked


def test_skill_choice_respects_desired_skills_when_allowed():
    proficiency_choices = [
        {
            "choose": 2,
            "from": [
                {
                    "index": "skill-athletics",
                    "name": "Skill: Athletics",
                    "url": "/api/proficiencies/",
                },
                {"index": "skill-stealth", "name": "Skill: Stealth", "url": "/api/proficiencies/"},
                {
                    "index": "skill-perception",
                    "name": "Skill: Perception",
                    "url": "/api/proficiencies/",
                },
                {"index": "skill-arcana", "name": "Skill: Arcana", "url": "/api/proficiencies/"},
            ],
        }
    ]
    mods = {"STR": 1, "DEX": 3, "CON": 2, "INT": 0, "WIS": 1, "CHA": 0}

    picked, _ = choose_skills(
        proficiency_choices,
        ability_mods=mods,
        role="skills",
        seed=7,
        desired_skills=["Arcana"],
    )

    assert len(picked) == 2
    assert "Arcana" in picked
