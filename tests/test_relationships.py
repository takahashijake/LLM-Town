from src.agents.relationships import RelationshipManager


def test_relationship_score_clamps_high():
    relationships = RelationshipManager()

    for _ in range(20):
        score = relationships.change_score("Maya", "Ethan", 1)

    assert score == 10


def test_relationship_score_clamps_low():
    relationships = RelationshipManager()

    for _ in range(20):
        score = relationships.change_score("Maya", "Ethan", -1)

    assert score == -10


def test_relationship_labels():
    relationships = RelationshipManager()

    assert relationships.describe_relationship("Maya", "Ethan") == "neutral"

    relationships.change_score("Maya", "Ethan", 3)
    assert relationships.describe_relationship("Maya", "Ethan") == "friendly"

    relationships.change_score("Maya", "Ethan", 4)
    assert relationships.describe_relationship("Maya", "Ethan") == "close friends"

    relationships.change_score("Maya", "Ethan", -10)
    assert relationships.describe_relationship("Maya", "Ethan") == "tense"

    relationships.change_score("Maya", "Ethan", -4)
    assert relationships.describe_relationship("Maya", "Ethan") == "enemies"