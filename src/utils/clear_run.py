from pathlib import Path 

def clear_run() -> None: 
    files_to_clear = [
        Path("logs/conversations/conversations.jsonl"),
        Path("logs/events/events.jsonl"),
        Path("logs/town_arc_changes.jsonl"),
        Path("data/save_state.json"),
    ]
    for file_path in files_to_clear: 
        path = Path(file_path) 

        if path.exists():
            path.write_text("")

    print("Previous run data cleared.")

        