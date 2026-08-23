import json
import os
from milim import config

GIF_DB_FILE = "reaction_gifs.json"
add_gif_mode = None
action_counts = {}

def load_gif_db():
    p = config.path(GIF_DB_FILE)
    if os.path.exists(p):
        with open(p, "r") as f:
            return json.load(f)
    return {}

def save_gif_db(db):
    with open(config.path(GIF_DB_FILE), "w") as f:
        json.dump(db, f, indent=2)
