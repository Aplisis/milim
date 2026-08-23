import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG_PATH = os.path.join(_ROOT, "config.json")

_data = {}

def load():
    global _data
    if not os.path.exists(_CFG_PATH):
        raise FileNotFoundError(
            "config.json missing. Run setup.py first."
        )
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        _data = json.load(f)
    return _data

def get(key, default=""):
    if not _data:
        load()
    return _data.get(key, default)

def token():
    return get("TOKEN")

def groq_key():
    return get("GROQ_API_KEY")

def deapi_key():
    return get("DEAPI_KEY")

def data_dir():
    d = os.path.join(_ROOT, "data")
    os.makedirs(d, exist_ok=True)
    return d

def path(*parts):
    return os.path.join(data_dir(), *parts)
