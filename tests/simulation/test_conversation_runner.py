from src.simulation.conversation_runner import ConversationRunner


class FakeEngineWithNoPairs:
    def group_agents_by_location(self):
        return {
            "library": ["Maya"],
            "market": [],
        }


def test_conversation_runner_prints_when_no_conversations_created(capsys):
    runner = ConversationRunner()
    engine = FakeEngineWithNoPairs()

    runner.generate_conversations(
        engine=engine,
        day=1,
        hour=8,
    )

    captured = capsys.readouterr()

    assert "No conversations this tick" in captured.out
