import json
import os
from milim import config
from milim.constants import MAX_MEMORY_SIZE

MEMORY_FILE = "global_memories.json"

def _path():
    return config.path(MEMORY_FILE)

def load_memories():
    p = _path()
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def save_memories(memories):
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(memories, f, indent=2)

def get_memory_injection():
    memories = load_memories()
    if not memories:
        return ""
    lines = ["\n=== GLOBAL MEMORIES ==="]
    for name, content in memories.items():
        lines.append(f"[{name}]: {content}")
    return "\n".join(lines)
