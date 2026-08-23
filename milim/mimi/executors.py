import aiohttp
from datetime import datetime, timezone
from milim.constants import RAT_LIST, DOWNLOAD_CHANNELS, CACHE_TTL

cache = {"data": None, "timestamp": None}

def utc_now():
    return datetime.now(timezone.utc)

async def fetch_executors():
    now = utc_now()
    if cache["data"] and cache["timestamp"]:
        if (now - cache["timestamp"]).total_seconds() < CACHE_TTL:
            return cache["data"]

    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.executors.online/api/executors") as resp:
            if resp.status == 200:
                data = await resp.json()
                real_executor = {
                    "_id": "real-custom",
                    "title": "Real",
                    "slug": "real",
                    "free": False,
                    "detected": False,
                    "updateStatus": False,
                    "uncStatus": False,
                    "decompiler": False,
                    "multiInject": False,
                    "platform": "Windows",
                    "extype": "wexecutor",
                    "rbxversion": "",
                    "updatedDate": "",
                    "version": "N/A",
                    "websitelink": "",
                    "discordlink": "",
                    "uncPercentage": None,
                    "suncPercentage": 100,
                    "clientmods": False,
                }
                if not any(ex.get("title") == "Real" for ex in data):
                    data.append(real_executor)
                cache["data"] = data
                cache["timestamp"] = now
                return data
    return None

def find_executor(data, name):
    name_lower = name.lower()
    for ex in data:
        title = ex.get("title", "").lower()
        slug = ex.get("slug", "")
        if isinstance(slug, dict):
            slug = slug.get("slug", "")
        else:
            slug = str(slug).lower() if slug else ""
        if title == name_lower or slug == name_lower:
            return ex
    return None

def parse_date(date_str):
    if not date_str:
        return None
    try:
        if date_str.endswith("Z"):
            date_str_iso = date_str[:-1] + "+00:00"
        else:
            date_str_iso = date_str
        return datetime.fromisoformat(date_str_iso)
    except ValueError:
        pass
    try:
        if date_str.endswith(" UTC"):
            date_str_clean = date_str[:-4]
        else:
            date_str_clean = date_str
        dt = datetime.strptime(date_str_clean, "%m/%d/%Y at %I:%M %p")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return None

def format_timestamp(date_str):
    dt = parse_date(date_str)
    if dt is None:
        return "Unknown"
    return f"<t:{int(dt.timestamp())}:R>"

def is_external_executor(executor):
    extype = (executor.get("extype") or "").lower()
    return "external" in extype

def get_download_channel(executor_name):
    return DOWNLOAD_CHANNELS.get(executor_name.lower())

def build_executor_message(executor):
    title = executor.get("title", "Unknown")
    status_emoji = "🟢" if executor.get("updateStatus", False) else "🔴"
    version = executor.get("version", "N/A")
    type_str = "Free & Paid" if title == "Real" else ("Free" if executor.get("free", False) else "Paid")
    last_update = format_timestamp(executor.get("updatedDate", ""))
    sunc = executor.get("suncPercentage")
    unc = executor.get("uncPercentage")
    sunc_str = f"{sunc}%" if sunc is not None else "N/A"
    unc_str = f"{unc}%" if unc is not None else "N/A"
    detected = executor.get("detected", False)
    decompiler = "✅" if executor.get("decompiler", False) else "❌"
    multi = "✅" if executor.get("multiInject", False) else "❌"
    keysys = " · Key System" if executor.get("keysystem", False) else ""
    msg = (
        f"{status_emoji} **{title}** · {type_str}{keysys}\n"
        f"-# Version: `{version}` · Last update: {last_update}\n"
        f"-# sUNC: **{sunc_str}** · UNC: **{unc_str}**\n"
        f"-# Decompiler: {decompiler} · Multi-inject: {multi}"
    )
    if detected:
        msg += "\n-# ⚠️ Detected by anti-cheat"
    return msg

def get_safety_message(executor_name, executor_data=None):
    name_lower = executor_name.lower()
    if name_lower in RAT_LIST:
        return f"⚠️ **{executor_name.title()}** — RAT detected. Do not use it."
    if executor_data and executor_data.get("detected", False):
        return f"⚠️ **{executor_name.title()}** may be detected by anti-cheat. Use with caution."
    return f"✅ **{executor_name.title()}** — No known RAT/malware detected."
