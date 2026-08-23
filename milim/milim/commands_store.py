import json
import os
from milim import config

COMMANDS_FILE = "custom_commands.json"
COMMANDS_FILES_DIR = "custom_commands_files"

def load_commands():
    p = config.path(COMMANDS_FILE)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}

def save_commands(commands):
    with open(config.path(COMMANDS_FILE), "w", encoding="utf-8") as f:
        json.dump(commands, f, indent=2, ensure_ascii=False)

def files_dir():
    d = config.path(COMMANDS_FILES_DIR)
    os.makedirs(d, exist_ok=True)
    return d
