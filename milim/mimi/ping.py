import json
import os
from milim import config

PING_FILE = "ping_list.json"

def load():
    p = config.path(PING_FILE)
    try:
        with open(p, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save(lst):
    with open(config.path(PING_FILE), "w") as f:
        json.dump(lst, f)

def mentions():
    return " ".join(f"<@{uid}>" for uid in load())
