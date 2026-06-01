import json
from pathlib import Path
from datetime import datetime


class TownLogger:
    def __init__(self):
        self.logs_dir = Path("logs")

        self.events_file = self.logs_dir / "events" / "events.jsonl"
        self.conversations_file = (
            self.logs_dir / "conversations" / "conversations.jsonl"
        )

        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        self.conversations_file.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_data: dict):
        with open(self.events_file, "a") as f:
            f.write(json.dumps(event_data) + "\n")

    def log_conversation(self, conversation_data: dict):
        with open(self.conversations_file, "a") as f:
            f.write(json.dumps(conversation_data) + "\n")

    def timestamp(self):
        return datetime.now().isoformat()