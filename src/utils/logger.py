import json
from pathlib import Path
from datetime import datetime


class TownLogger:
    def __init__(self, logs_dir: str | Path = "logs"):
        self.logs_dir = Path(logs_dir)

        self.events_file = self.logs_dir / "events" / "events.jsonl"
        self.conversations_file = (
            self.logs_dir / "conversations" / "conversations.jsonl"
        )
        self.conversation_sessions_file = (
            self.logs_dir / "conversations" / "sessions.jsonl"
        )

        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        self.conversations_file.parent.mkdir(parents=True, exist_ok=True)

    def clear_logs(self):
        self.events_file.write_text("")
        self.conversations_file.write_text("")
        self.conversation_sessions_file.write_text("")

    def log_event(self, event_data: dict):
        with open(self.events_file, "a") as f:
            f.write(json.dumps(event_data) + "\n")

    def log_conversation(self, conversation_data: dict):
        with open(self.conversations_file, "a") as f:
            f.write(json.dumps(conversation_data) + "\n")

    def log_conversation_session(self, session_data: dict):
        with open(self.conversation_sessions_file, "a") as f:
            f.write(json.dumps(session_data) + "\n")

    def timestamp(self):
        return datetime.now().isoformat()
