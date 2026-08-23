import json
import os
import aiohttp
from datetime import datetime, timezone
from milim import config
from milim.constants import DEAPI_GEN_URL, DEAPI_JOB_URL, DEAPI_BAL_URL

user_last_image = {}
user_gen_times = {}

def _headers():
    return {
        "Authorization": f"Bearer {config.deapi_key()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def _balance_path():
    return config.path("deapi_balance.json")

async def get_balance():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                DEAPI_BAL_URL,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    balance = float((data.get("data") or {}).get("balance", 0))
                    with open(_balance_path(), "w") as f:
                        json.dump({"balance": balance}, f)
                    return balance
    except Exception:
        pass
    try:
        with open(_balance_path(), "r") as f:
            return float(json.load(f).get("balance", 0))
    except Exception:
        return 0.0

def cached_balance():
    try:
        with open(_balance_path(), "r") as f:
            return float(json.load(f).get("balance", 0))
    except Exception:
        return 5.0

def dynamic_cooldown(user_id):
    now = datetime.now(timezone.utc)
    times = user_gen_times.get(user_id, [])
    times = [t for t in times if (now - t).total_seconds() < 600]
    user_gen_times[user_id] = times
    base = 1
    spam_penalty = max(0, len(times) - 2) * 120
    balance = cached_balance()
    low_balance_mult = 2.0 if balance < 1.0 else 1.0
    return int((base + spam_penalty) * low_balance_mult)
