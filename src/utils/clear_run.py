from pathlib import Path 

def clear_run() -> None: 
    files_to_clear = [
        "logs/conversations/conversations.jsonl",
        "data/save_state.json",
    ]

    for file_path in files_to_clear: 
        path = Path(file_path) 

        if path.exists():
            path.write_text("")

    print("Previous run data cleared.")

        