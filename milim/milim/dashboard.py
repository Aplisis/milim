"""
Milim Dashboard — Flask control panel
Scans for a free port in 5100-5200, starts a local web UI.
Works even if the bot token is invalid / missing.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template_string

# ── shared runtime state ──────────────────────────────────────────────────────
_bot_state   = {}
_bot_client  = None
_start_time  = None
_bot_mode    = "offline"   # "online" | "offline" | "error"
_bot_error   = ""

# ── port scanner ──────────────────────────────────────────────────────────────

def scan_free_port(start=5100, end=5200):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in {start}-{end}")

# ── config helpers ────────────────────────────────────────────────────────────

def _cfg_root() -> str:
    """
    Walk up from this file until we find the directory containing config.json.
    Works regardless of how deep dashboard.py sits in the repo.
    """
    here = os.path.abspath(__file__)
    candidate = os.path.dirname(here)
    for _ in range(6):
        if os.path.isfile(os.path.join(candidate, "config.json")):
            return candidate
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    # fallback: two levels above this file
    return os.path.dirname(os.path.dirname(here))

def _cfg_file():
    return os.path.join(_cfg_root(), "config.json")

def _read_cfg_raw():
    p = _cfg_file()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _write_cfg_raw(data):
    with open(_cfg_file(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _data_path(filename):
    d = os.path.join(_cfg_root(), "data")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, filename)

def _read_json(filename, default):
    p = _data_path(filename)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def _write_json(filename, data):
    with open(_data_path(filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# perm helpers
def _load_perm(fname):       return _read_json(fname, [])
def _save_perm(fname, data): _write_json(fname, data)

PERM_FILES = {
    "onoff":    "onoff_perms.json",
    "create":   "perms.json",
    "persona":  "pps_perms.json",
}

def get_banned_words():
    from milim.constants import BANNED_WORDS
    override = _read_json("banned_words.json", None)
    return override if override is not None else list(BANNED_WORDS)

def save_banned_words(words):
    _write_json("banned_words.json", words)

def get_uptime():
    if _start_time is None:
        return 0, "—"
    s = int((datetime.now(timezone.utc) - _start_time).total_seconds())
    d, s = divmod(s, 86400); h, s = divmod(s, 3600); m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return int((datetime.now(timezone.utc) - _start_time).total_seconds()), " ".join(parts)

# ── log ───────────────────────────────────────────────────────────────────────
_log_buffer = []
_MAX_LOG = 300

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    _log_buffer.append(entry)
    if len(_log_buffer) > _MAX_LOG:
        _log_buffer.pop(0)
    print(entry)

# ── Flask ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.urandom(24)

# ── API: status ───────────────────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    connected = _bot_client is not None and not _bot_client.is_closed()
    guilds = len(_bot_client.guilds) if connected else 0
    users  = sum(g.member_count or 0 for g in _bot_client.guilds) if connected else 0
    up_s, up_str = get_uptime()
    from milim import personas as _p
    return jsonify({
        "mode":       _bot_mode,
        "error":      _bot_error,
        "connected":  connected,
        "ai_enabled": _bot_state.get("ai_enabled", False),
        "uptime_seconds": up_s,
        "uptime_str": up_str,
        "guilds":     guilds,
        "users":      users,
        "persona":    (f"char:{_p.character_mode}" if _p.character_mode else _p.persona_mode),
        "username":   str(_bot_client.user) if connected else "—",
        "dictator":   _p.dictator_mode,
    })

# ── API: token / config ───────────────────────────────────────────────────────
@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        raw = _read_cfg_raw()
        # mask token after first 10 chars
        token = raw.get("TOKEN", "")
        masked = token[:10] + "•" * max(0, len(token) - 10) if token else ""
        return jsonify({
            "token_masked": masked,
            "groq_key_set": bool(raw.get("GROQ_API_KEY")),
            "gemini_key_set": bool(raw.get("GEMINI_API_KEY")),
            "deapi_key_set": bool(raw.get("DEAPI_KEY")),
            "active_provider": "gemini" if raw.get("GEMINI_API_KEY") else "groq",
        })
    data = request.get_json(force=True)
    raw = _read_cfg_raw()
    changed = []
    if "token" in data and data["token"].strip():
        raw["TOKEN"] = data["token"].strip()
        changed.append("TOKEN")
    if "groq_key" in data and data["groq_key"].strip():
        raw["GROQ_API_KEY"] = data["groq_key"].strip()
        changed.append("GROQ_API_KEY")
    if "gemini_key" in data and data["gemini_key"].strip():
        raw["GEMINI_API_KEY"] = data["gemini_key"].strip()
        changed.append("GEMINI_API_KEY")
    if "clear_gemini" in data and data["clear_gemini"]:
        raw["GEMINI_API_KEY"] = ""
        changed.append("GEMINI_API_KEY cleared")
    if "deapi_key" in data and data["deapi_key"].strip():
        raw["DEAPI_KEY"] = data["deapi_key"].strip()
        changed.append("DEAPI_KEY")
    _write_cfg_raw(raw)
    log(f"Config updated: {', '.join(changed)}")
    return jsonify({"ok": True, "changed": changed})

@app.route("/api/restart", methods=["POST"])
def api_restart():
    log("Restart requested via dashboard — respawning process…")
    def _do():
        time.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=_do, daemon=True).start()
    return jsonify({"ok": True})

# ── API: AI / dictator toggles ────────────────────────────────────────────────
@app.route("/api/ai", methods=["POST"])
def api_ai():
    d = request.get_json(force=True)
    _bot_state["ai_enabled"] = bool(d.get("enabled", True))
    log(f"AI {'enabled' if _bot_state['ai_enabled'] else 'disabled'} via dashboard")
    return jsonify({"ok": True, "ai_enabled": _bot_state["ai_enabled"]})

@app.route("/api/dictator", methods=["POST"])
def api_dictator():
    from milim import personas as _p
    d = request.get_json(force=True)
    _p.dictator_mode = bool(d.get("enabled", False))
    log(f"Dictator mode {'ON' if _p.dictator_mode else 'OFF'} via dashboard")
    return jsonify({"ok": True, "dictator_mode": _p.dictator_mode})

# ── API: persona ──────────────────────────────────────────────────────────────
@app.route("/api/persona", methods=["GET", "POST"])
def api_persona():
    from milim import personas as _p
    from milim.personas import PERSONAS, CHARACTERS
    if request.method == "GET":
        current = f"char:{_p.character_mode}" if _p.character_mode else _p.persona_mode
        return jsonify({"current": current, "personas": list(PERSONAS.keys()), "characters": list(CHARACTERS.keys())})
    d = request.get_json(force=True)
    name = d.get("name", "")
    if name.startswith("char:"):
        cname = name[5:]
        if cname in CHARACTERS:
            _p.character_mode = cname
            log(f"Character → {cname}")
            return jsonify({"ok": True, "current": name})
    elif name in PERSONAS:
        _p.persona_mode = name
        _p.character_mode = None
        log(f"Persona → {name}")
        return jsonify({"ok": True, "current": name})
    return jsonify({"ok": False, "error": "Unknown persona"}), 400

# ── API: banned words ─────────────────────────────────────────────────────────
@app.route("/api/banned_words", methods=["GET", "POST"])
def api_banned_words():
    if request.method == "GET":
        return jsonify({"words": get_banned_words()})
    d = request.get_json(force=True)
    words = [str(w).strip() for w in d.get("words", []) if str(w).strip()]
    save_banned_words(words)
    log(f"Banned words saved ({len(words)})")
    return jsonify({"ok": True, "words": words})

# ── API: blacklist ────────────────────────────────────────────────────────────
@app.route("/api/blacklist", methods=["GET", "POST"])
def api_blacklist():
    if request.method == "GET":
        from milim.permissions import load_blacklist
        return jsonify({"users": load_blacklist()})
    d = request.get_json(force=True)
    from milim.permissions import load_blacklist, save_blacklist
    bl = load_blacklist()
    try: uid = int(d.get("user_id", 0))
    except (ValueError, TypeError): return jsonify({"ok": False, "error": "Invalid ID"}), 400
    action = d.get("action")
    if action == "add" and uid not in bl:
        bl.append(uid); save_blacklist(bl); log(f"Blacklisted {uid}")
    elif action == "remove" and uid in bl:
        bl.remove(uid); save_blacklist(bl); log(f"Unblacklisted {uid}")
    return jsonify({"ok": True, "users": bl})

# ── API: permissions ──────────────────────────────────────────────────────────
@app.route("/api/perms/<perm_type>", methods=["GET", "POST"])
def api_perms(perm_type):
    if perm_type not in PERM_FILES:
        return jsonify({"ok": False, "error": "Unknown perm type"}), 400
    fname = PERM_FILES[perm_type]
    if request.method == "GET":
        return jsonify({"users": _load_perm(fname), "type": perm_type})
    d = request.get_json(force=True)
    try: uid = int(d.get("user_id", 0))
    except (ValueError, TypeError): return jsonify({"ok": False, "error": "Invalid ID"}), 400
    action = d.get("action")
    lst = _load_perm(fname)
    if action == "add" and uid not in lst:
        lst.append(uid); _save_perm(fname, lst); log(f"Perm '{perm_type}' granted to {uid}")
    elif action == "remove" and uid in lst:
        lst.remove(uid); _save_perm(fname, lst); log(f"Perm '{perm_type}' revoked from {uid}")
    return jsonify({"ok": True, "users": lst})

# ── API: memories ─────────────────────────────────────────────────────────────
@app.route("/api/memories", methods=["GET", "POST"])
def api_memories():
    from milim.memory import load_memories, save_memories
    if request.method == "GET":
        return jsonify({"memories": load_memories()})
    d = request.get_json(force=True)
    action = d.get("action"); key = str(d.get("key", "")).strip()
    if not key: return jsonify({"ok": False, "error": "Key required"}), 400
    mem = load_memories()
    if action == "set":
        mem[key] = str(d.get("value", "")); save_memories(mem); log(f"Memory '{key}' set")
    elif action == "delete":
        mem.pop(key, None); save_memories(mem); log(f"Memory '{key}' deleted")
    return jsonify({"ok": True, "memories": mem})

# ── API: custom commands ──────────────────────────────────────────────────────
@app.route("/api/commands")
def api_commands():
    from milim.commands_store import load_commands
    cmds = load_commands()
    return jsonify({"commands": {k: {"text": v.get("text",""), "has_files": bool(v.get("files"))} for k,v in cmds.items()}})

# ── API: logs ─────────────────────────────────────────────────────────────────
@app.route("/api/logs")
def api_logs():
    return jsonify({"logs": list(_log_buffer)})

# ── Main page ─────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Milim Control</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0D0F14; --surface:#13161E; --surface2:#1A1E2A; --border:#252A38;
  --accent:#5865F2; --accent2:#EB459E; --ok:#3BA55C; --warn:#FAA61A;
  --danger:#ED4245; --text:#E2E8F0; --muted:#6B7494;
  --mono:'JetBrains Mono',monospace; --sans:'Inter',sans-serif;
}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;min-height:100vh;display:flex;flex-direction:column}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* layout */
.shell{display:flex;min-height:100vh}
.sidebar{width:220px;flex-shrink:0;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;position:sticky;top:0;height:100vh;overflow-y:auto}
.main{flex:1;overflow:hidden;display:flex;flex-direction:column;min-width:0}

/* sidebar */
.sb-brand{padding:20px 18px 14px;border-bottom:1px solid var(--border)}
.sb-brand .logo{font-family:var(--mono);font-weight:700;font-size:18px;letter-spacing:-0.5px}
.sb-brand .logo span{color:var(--accent)}
.sb-brand .ver{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:2px}
.sb-section{padding:14px 12px 3px;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:600}
.sb-nav{list-style:none;padding:3px 8px}
.sb-nav a{display:flex;align-items:center;gap:9px;padding:8px 11px;border-radius:7px;color:var(--muted);text-decoration:none;font-size:13px;font-weight:500;transition:background .13s,color .13s;cursor:pointer}
.sb-nav a:hover{background:var(--surface2);color:var(--text)}
.sb-nav a.active{background:rgba(88,101,242,.14);color:var(--accent)}
.sb-nav a .ico{font-size:14px;width:17px;text-align:center;flex-shrink:0}
.sb-status{margin-top:auto;padding:14px;border-top:1px solid var(--border)}
.sb-status .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--muted);margin-right:6px;position:relative;vertical-align:middle}
.sb-status .dot.online{background:var(--ok)}
.sb-status .dot.online::after{content:'';position:absolute;inset:-3px;border-radius:50%;background:rgba(59,165,92,.3);animation:pulse 2s ease-in-out infinite}
.sb-status .dot.error{background:var(--danger)}
@keyframes pulse{0%,100%{transform:scale(1);opacity:.7}50%{transform:scale(1.6);opacity:0}}
.sb-status .slabel{font-size:11px;color:var(--muted)}
.sb-status .sname{font-family:var(--mono);font-size:11px;color:var(--text);margin-top:2px;word-break:break-all}

/* topbar */
.topbar{padding:14px 26px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;background:var(--surface)}
.topbar h1{font-size:15px;font-weight:600}
.uptime-badge{font-family:var(--mono);font-size:11px;color:var(--muted)}
.uptime-badge span{color:var(--accent2);font-weight:700}

/* error banner */
.err-banner{background:rgba(237,66,69,.12);border-bottom:1px solid rgba(237,66,69,.3);padding:10px 26px;font-size:13px;color:#f38a8c;display:flex;align-items:center;gap:10px}
.err-banner b{color:var(--danger)}

/* content */
.content{flex:1;overflow-y:auto;padding:24px 26px;display:flex;flex-direction:column;gap:20px}
.section{display:none}
.section.active{display:flex;flex-direction:column;gap:18px}

/* stat grid */
.stat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
.scard{background:var(--surface);border:1px solid var(--border);border-radius:11px;padding:16px 18px}
.scard .sl{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:7px}
.scard .sv{font-family:var(--mono);font-size:20px;font-weight:700}
.sv.ok{color:var(--ok)} .sv.warn{color:var(--warn)} .sv.accent{color:var(--accent)} .sv.pink{color:var(--accent2)}

/* card */
.card{background:var(--surface);border:1px solid var(--border);border-radius:11px;overflow:hidden}
.card-hd{padding:13px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:10px}
.card-hd h2{font-size:13px;font-weight:600}
.card-hd .sub{font-size:11px;color:var(--muted)}
.card-bd{padding:16px 18px}

/* toggle */
.trow{display:flex;align-items:center;gap:11px}
.toggle{position:relative;width:40px;height:22px;cursor:pointer;flex-shrink:0}
.toggle input{opacity:0;width:0;height:0}
.toggle .track{position:absolute;inset:0;background:var(--border);border-radius:11px;transition:background .18s}
.toggle input:checked+.track{background:var(--accent)}
.toggle .thumb{position:absolute;top:3px;left:3px;width:16px;height:16px;background:#fff;border-radius:50%;transition:transform .18s;pointer-events:none}
.toggle input:checked~.thumb{transform:translateX(18px)}
.tlabel{font-size:13px}

/* tags */
.tag-list{display:flex;flex-wrap:wrap;gap:7px;min-height:28px}
.tag{display:inline-flex;align-items:center;gap:5px;background:var(--surface2);border:1px solid var(--border);border-radius:6px;padding:3px 9px;font-family:var(--mono);font-size:12px}
.tag .rm{cursor:pointer;color:var(--muted);font-size:13px;border:none;background:none;padding:0;line-height:1;transition:color .13s}
.tag .rm:hover{color:var(--danger)}

/* inputs */
.row{display:flex;gap:7px;align-items:center;flex-wrap:wrap}
input[type=text],input[type=password],textarea,select{background:var(--surface2);border:1px solid var(--border);border-radius:7px;color:var(--text);font-family:var(--mono);font-size:13px;padding:7px 11px;outline:none;transition:border-color .13s}
input[type=text]:focus,input[type=password]:focus,textarea:focus,select:focus{border-color:var(--accent)}
input::placeholder,textarea::placeholder{color:var(--muted)}
textarea{resize:vertical;min-height:64px;width:100%}
select option{background:var(--surface2)}
.input-group{display:flex;gap:7px;align-items:stretch}
.input-group input{flex:1}

/* buttons */
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border-radius:7px;font-size:13px;font-weight:500;border:none;cursor:pointer;transition:opacity .13s,background .13s}
.btn:hover{opacity:.82}
.btn-primary{background:var(--accent);color:#fff}
.btn-danger{background:var(--danger);color:#fff}
.btn-ghost{background:var(--surface2);color:var(--text);border:1px solid var(--border)}
.btn-warn{background:var(--warn);color:#111}

/* perm tabs */
.perm-tabs{display:flex;gap:2px;background:var(--surface2);border-radius:8px;padding:3px;border:1px solid var(--border);width:fit-content}
.perm-tab{padding:6px 14px;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;color:var(--muted);transition:background .13s,color .13s}
.perm-tab.active{background:var(--accent);color:#fff}

/* persona grid */
.pg{display:grid;grid-template-columns:repeat(auto-fill,minmax(105px,1fr));gap:7px}
.ppill{padding:7px 10px;border-radius:7px;border:1px solid var(--border);background:var(--surface2);cursor:pointer;font-family:var(--mono);font-size:12px;color:var(--muted);text-align:center;transition:border-color .13s,color .13s,background .13s}
.ppill:hover{border-color:var(--accent);color:var(--text)}
.ppill.active{border-color:var(--accent);background:rgba(88,101,242,.14);color:var(--accent);font-weight:700}
.ppill.char{border-color:rgba(235,69,158,.4);color:var(--accent2)}
.ppill.char.active{background:rgba(235,69,158,.14);border-color:var(--accent2)}

/* table */
.tbl{width:100%;border-collapse:collapse}
.tbl th,.tbl td{padding:9px 13px;text-align:left;border-bottom:1px solid var(--border);font-size:13px}
.tbl th{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600}
.tbl tr:last-child td{border-bottom:none}
.tbl td.mono{font-family:var(--mono);color:var(--accent)}
.tbl td.mono2{font-family:var(--mono);color:var(--accent2)}

/* log */
.log-box{background:var(--bg);border:1px solid var(--border);border-radius:9px;padding:12px 14px;font-family:var(--mono);font-size:12px;overflow-y:auto;color:var(--muted)}
.log-line{line-height:1.8;white-space:pre-wrap;word-break:break-all}

/* config section */
.cfg-field{display:flex;flex-direction:column;gap:5px}
.cfg-field label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;font-weight:600}
.cfg-field input{width:100%}

/* toast */
#toast{position:fixed;bottom:22px;right:22px;z-index:999;background:var(--surface);border:1px solid var(--border);border-radius:9px;padding:11px 16px;font-size:13px;color:var(--text);transform:translateY(16px);opacity:0;transition:all .22s;pointer-events:none}
#toast.show{transform:translateY(0);opacity:1}
#toast.ok{border-color:var(--ok);color:var(--ok)}
#toast.err{border-color:var(--danger);color:var(--danger)}
#toast.warn{border-color:var(--warn);color:var(--warn)}

.empty{color:var(--muted);font-size:12px;font-family:var(--mono)}
.divider{height:1px;background:var(--border);margin:4px 0}

@media(max-width:680px){
  .sidebar{width:52px}
  .sb-brand .logo,.sb-brand .ver,.sb-section,.sb-nav a span,.sb-status .slabel,.sb-status .sname{display:none}
  .sb-nav a{justify-content:center;padding:9px}
  .content{padding:14px}
}
</style>
</head>
<body>
<div class="shell">

<aside class="sidebar">
  <div class="sb-brand">
    <div class="logo">mi<span>lim</span></div>
    <div class="ver" id="sb-ver">v—</div>
  </div>
  <div class="sb-section">Control</div>
  <ul class="sb-nav">
    <li><a class="active" data-s="overview"><span class="ico">⬡</span><span>Overview</span></a></li>
    <li><a data-s="persona"><span class="ico">◈</span><span>Persona</span></a></li>
    <li><a data-s="words"><span class="ico">⊘</span><span>Banned words</span></a></li>
    <li><a data-s="blacklist"><span class="ico">◻</span><span>Blacklist</span></a></li>
    <li><a data-s="perms"><span class="ico">🔑</span><span>Permissions</span></a></li>
    <li><a data-s="memory"><span class="ico">◫</span><span>Memory</span></a></li>
    <li><a data-s="commands"><span class="ico">⌘</span><span>Commands</span></a></li>
    <li><a data-s="logs"><span class="ico">▤</span><span>Logs</span></a></li>
    <li><a data-s="config"><span class="ico">⚙</span><span>Config</span></a></li>
  </ul>
  <div class="sb-status">
    <div><span class="dot" id="sb-dot"></span><span class="slabel">Bot status</span></div>
    <div class="sname" id="sb-name">—</div>
  </div>
</aside>

<div class="main">
  <div class="topbar">
    <h1 id="section-title">Overview</h1>
    <div class="uptime-badge">uptime <span id="uptime-val">—</span></div>
  </div>
  <div id="err-banner" class="err-banner" style="display:none">
    <b>⚠ Bot offline</b> — <span id="err-msg"></span>
    <a data-s="config" style="margin-left:8px;color:var(--accent);cursor:pointer;text-decoration:underline" onclick="switchSection('config')">Fix in Config →</a>
  </div>

  <div class="content">

    <!-- Overview -->
    <div class="section active" id="s-overview">
      <div class="stat-grid">
        <div class="scard"><div class="sl">Status</div><div class="sv" id="st-status">—</div></div>
        <div class="scard"><div class="sl">AI engine</div><div class="sv" id="st-ai">—</div></div>
        <div class="scard"><div class="sl">Servers</div><div class="sv accent" id="st-guilds">—</div></div>
        <div class="scard"><div class="sl">Members</div><div class="sv pink" id="st-users">—</div></div>
        <div class="scard"><div class="sl">Persona</div><div class="sv" style="font-size:14px" id="st-persona">—</div></div>
      </div>
      <div class="card">
        <div class="card-hd"><h2>Quick controls</h2></div>
        <div class="card-bd" style="display:flex;gap:24px;flex-wrap:wrap">
          <div class="trow">
            <label class="toggle"><input type="checkbox" id="tog-ai" onchange="toggleAI(this.checked)"><span class="track"></span><span class="thumb"></span></label>
            <span class="tlabel">AI responses</span>
          </div>
          <div class="trow">
            <label class="toggle"><input type="checkbox" id="tog-dict" onchange="toggleDict(this.checked)"><span class="track"></span><span class="thumb"></span></label>
            <span class="tlabel">Dictator mode</span>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-hd"><h2>Live log</h2><span class="sub">last 20 entries</span></div>
        <div class="card-bd"><div class="log-box" id="overview-log" style="height:220px"></div></div>
      </div>
    </div>

    <!-- Persona -->
    <div class="section" id="s-persona">
      <div class="card">
        <div class="card-hd"><h2>Personas</h2><span class="sub" id="cur-persona">current: —</span></div>
        <div class="card-bd"><div class="pg" id="pg-personas"></div></div>
      </div>
      <div class="card">
        <div class="card-hd"><h2>Characters</h2></div>
        <div class="card-bd"><div class="pg" id="pg-chars"></div></div>
      </div>
    </div>

    <!-- Banned words -->
    <div class="section" id="s-words">
      <div class="card">
        <div class="card-hd"><h2>Banned words</h2><span class="sub" id="words-cnt">0 words</span></div>
        <div class="card-bd" style="display:flex;flex-direction:column;gap:13px">
          <div class="tag-list" id="word-tags"></div>
          <div class="input-group">
            <input type="text" id="new-word" placeholder="Add a word…"/>
            <button class="btn btn-primary" onclick="addWord()">Add</button>
          </div>
          <div style="text-align:right"><button class="btn btn-primary" onclick="saveWords()">Save changes</button></div>
        </div>
      </div>
    </div>

    <!-- Blacklist -->
    <div class="section" id="s-blacklist">
      <div class="card">
        <div class="card-hd"><h2>Blacklisted users</h2><span class="sub" id="bl-cnt">0 users</span></div>
        <div class="card-bd" style="display:flex;flex-direction:column;gap:13px">
          <div class="tag-list" id="bl-tags"></div>
          <div class="input-group">
            <input type="text" id="new-bl" placeholder="Discord user ID…"/>
            <button class="btn btn-primary" onclick="addBL()">Add</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Permissions -->
    <div class="section" id="s-perms">
      <div class="card">
        <div class="card-hd">
          <h2>Permissions</h2>
          <div class="perm-tabs" id="perm-tabs">
            <div class="perm-tab active" data-perm="onoff">On/Off</div>
            <div class="perm-tab" data-perm="create">Create</div>
            <div class="perm-tab" data-perm="persona">Persona</div>
          </div>
        </div>
        <div class="card-bd" style="display:flex;flex-direction:column;gap:14px">
          <div style="font-size:12px;color:var(--muted)" id="perm-desc"></div>
          <div class="tag-list" id="perm-tags"></div>
          <div class="input-group">
            <input type="text" id="new-perm" placeholder="Discord user ID…"/>
            <button class="btn btn-primary" onclick="addPerm()">Add</button>
          </div>
          <div class="divider"></div>
          <div style="font-size:12px;color:var(--muted)">
            Users already in the list — click × to revoke.
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-hd"><h2>All permissions — overview</h2></div>
        <div class="card-bd">
          <table class="tbl" id="perm-all-table">
            <thead><tr><th>User ID</th><th>On/Off</th><th>Create</th><th>Persona</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Memory -->
    <div class="section" id="s-memory">
      <div class="card">
        <div class="card-hd"><h2>Global memories</h2></div>
        <div class="card-bd" style="display:flex;flex-direction:column;gap:14px">
          <table class="tbl" id="mem-table">
            <thead><tr><th>Key</th><th>Value</th><th></th></tr></thead>
            <tbody></tbody>
          </table>
          <div class="divider"></div>
          <div style="display:flex;flex-direction:column;gap:9px">
            <input type="text" id="mem-key" placeholder="Key…" style="width:100%"/>
            <textarea id="mem-val" placeholder="Value…"></textarea>
            <div><button class="btn btn-primary" onclick="setMemory()">Save memory</button></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Commands -->
    <div class="section" id="s-commands">
      <div class="card">
        <div class="card-hd"><h2>Custom commands</h2><span class="sub" id="cmd-cnt">0</span></div>
        <div class="card-bd">
          <table class="tbl">
            <thead><tr><th>Command</th><th>Text</th><th>Files</th></tr></thead>
            <tbody id="cmd-body"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Logs -->
    <div class="section" id="s-logs">
      <div class="card">
        <div class="card-hd"><h2>Dashboard logs</h2><button class="btn btn-ghost" onclick="logData=[];renderLogs(false)">Clear</button></div>
        <div class="card-bd"><div class="log-box" style="height:400px" id="full-log"></div></div>
      </div>
    </div>

    <!-- Config -->
    <div class="section" id="s-config">
      <div class="card">
        <div class="card-hd"><h2>Bot credentials</h2><span class="sub">config.json</span></div>
        <div class="card-bd" style="display:flex;flex-direction:column;gap:16px">
          <div class="cfg-field">
            <label>Discord user token</label>
            <input type="password" id="cfg-token" placeholder="Leave blank to keep current"/>
            <span style="font-size:11px;color:var(--muted)" id="cfg-token-hint"></span>
          </div>
          <div style="font-size:11px;padding:8px 12px;border-radius:7px;border:1px solid var(--border);background:var(--surface2);color:var(--muted)">
            Active provider: <span id="cfg-provider" style="font-family:var(--mono);font-weight:700;color:var(--accent)">—</span>
            <span style="margin-left:8px;font-size:10px">· Gemini takes priority when its key is set</span>
          </div>
          <div class="cfg-field">
            <label>Groq API key</label>
            <input type="password" id="cfg-groq" placeholder="Leave blank to keep current"/>
            <span style="font-size:11px;color:var(--muted)" id="cfg-groq-hint"></span>
          </div>
          <div class="cfg-field">
            <label>Gemini API key <span style="color:var(--accent2)">(takes priority over Groq)</span></label>
            <div style="display:flex;gap:7px">
              <input type="password" id="cfg-gemini" placeholder="Leave blank to keep current" style="flex:1"/>
              <button class="btn btn-ghost" onclick="clearGemini()" title="Remove Gemini key, fall back to Groq">✕ Clear</button>
            </div>
            <span style="font-size:11px;color:var(--muted)" id="cfg-gemini-hint"></span>
          </div>
          <div class="cfg-field">
            <label>DeAPI key <span style="color:var(--muted)">(optional — image generation)</span></label>
            <input type="password" id="cfg-deapi" placeholder="Leave blank to keep current"/>
          </div>
          <div style="display:flex;gap:9px;flex-wrap:wrap;padding-top:4px">
            <button class="btn btn-primary" onclick="saveCfg()">Save credentials</button>
            <button class="btn btn-warn" onclick="restartBot()">⟳ Save & Restart bot</button>
          </div>
          <div style="font-size:11px;color:var(--muted)">
            Restart applies new credentials. The dashboard stays alive during restart.
          </div>
        </div>
      </div>
    </div>

  </div>
</div>
</div>

<div id="toast"></div>
<script>
// ── nav ────────────────────────────────────────────────────────────────────────
let currentSection = "overview";
document.querySelectorAll(".sb-nav a[data-s]").forEach(a => {
  a.addEventListener("click", () => switchSection(a.dataset.s));
});
const TITLES = {overview:"Overview",persona:"Persona",words:"Banned words",blacklist:"Blacklist",perms:"Permissions",memory:"Memory",commands:"Commands",logs:"Logs",config:"Config"};
function switchSection(name) {
  document.querySelectorAll(".sb-nav a").forEach(a => a.classList.toggle("active", a.dataset.s === name));
  document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
  const sec = document.getElementById("s-" + name);
  if (sec) sec.classList.add("active");
  document.getElementById("section-title").textContent = TITLES[name] || name;
  currentSection = name;
  if (name === "persona")   loadPersonas();
  if (name === "words")     loadWords();
  if (name === "blacklist") loadBL();
  if (name === "perms")     { loadPermTab(); loadPermAll(); }
  if (name === "memory")    loadMemory();
  if (name === "commands")  loadCommands();
  if (name === "logs")      renderLogs(true);
  if (name === "config")    loadCfg();
}

// ── toast ──────────────────────────────────────────────────────────────────────
let _tt;
function toast(msg, type="ok") {
  const el = document.getElementById("toast");
  el.textContent = msg; el.className = "show " + type;
  clearTimeout(_tt); _tt = setTimeout(() => el.className = "", 2800);
}

// ── fetch ──────────────────────────────────────────────────────────────────────
async function api(path, opts={}) {
  const r = await fetch(path, {headers:{"Content-Type":"application/json"}, ...opts});
  return r.json();
}

// ── status poll ────────────────────────────────────────────────────────────────
let statusD = {};
async function pollStatus() {
  try {
    const d = await api("/api/status");
    statusD = d;
    // sidebar
    const dot = document.getElementById("sb-dot");
    dot.className = "dot" + (d.connected ? " online" : d.mode === "error" ? " error" : "");
    document.getElementById("sb-name").textContent = d.username;
    // topbar
    document.getElementById("uptime-val").textContent = d.uptime_str;
    // error banner
    const banner = document.getElementById("err-banner");
    if (!d.connected && d.mode !== "online") {
      banner.style.display = "flex";
      document.getElementById("err-msg").textContent = d.error || "Bot is not connected to Discord.";
    } else {
      banner.style.display = "none";
    }
    // stats
    document.getElementById("st-status").textContent = d.connected ? "Online" : "Offline";
    document.getElementById("st-status").className = "sv " + (d.connected ? "ok" : "warn");
    document.getElementById("st-ai").textContent = d.ai_enabled ? "Active" : "Paused";
    document.getElementById("st-ai").className = "sv " + (d.ai_enabled ? "ok" : "warn");
    document.getElementById("st-guilds").textContent = d.guilds;
    document.getElementById("st-users").textContent = d.users;
    document.getElementById("st-persona").textContent = d.persona;
    document.getElementById("tog-ai").checked = d.ai_enabled;
    document.getElementById("tog-dict").checked = d.dictator;
  } catch(e) {}
}

// ── toggles ────────────────────────────────────────────────────────────────────
async function toggleAI(v)   { await api("/api/ai",       {method:"POST",body:JSON.stringify({enabled:v})}); toast(v?"AI enabled":"AI paused"); }
async function toggleDict(v) { await api("/api/dictator", {method:"POST",body:JSON.stringify({enabled:v})}); toast(v?"Dictator ON":"Dictator OFF"); }

// ── persona ────────────────────────────────────────────────────────────────────
let personaD = {};
async function loadPersonas() {
  personaD = await api("/api/persona");
  document.getElementById("cur-persona").textContent = "current: " + personaD.current;
  const pg = document.getElementById("pg-personas"); pg.innerHTML = "";
  personaD.personas.forEach(p => {
    const el = document.createElement("div");
    el.className = "ppill" + (personaD.current === p ? " active" : "");
    el.textContent = p; el.onclick = () => selectPersona(p); pg.appendChild(el);
  });
  const cg = document.getElementById("pg-chars"); cg.innerHTML = "";
  personaD.characters.forEach(c => {
    const el = document.createElement("div");
    el.className = "ppill char" + (personaD.current === "char:"+c ? " active" : "");
    el.textContent = c; el.onclick = () => selectPersona("char:"+c); cg.appendChild(el);
  });
}
async function selectPersona(name) {
  const r = await api("/api/persona", {method:"POST",body:JSON.stringify({name})});
  if (r.ok) { toast("Persona → " + name); personaD.current = r.current; loadPersonas(); }
  else toast("Failed","err");
}

// ── banned words ───────────────────────────────────────────────────────────────
let wordList = [];
async function loadWords() {
  const d = await api("/api/banned_words"); wordList = d.words || []; renderWords();
}
function renderWords() {
  document.getElementById("words-cnt").textContent = wordList.length + " words";
  const c = document.getElementById("word-tags"); c.innerHTML = "";
  if (!wordList.length) { c.innerHTML = '<span class="empty">No banned words</span>'; return; }
  wordList.forEach((w,i) => {
    const t = document.createElement("span"); t.className = "tag";
    t.innerHTML = `${esc(w)}<button class="rm" onclick="removeWord(${i})">×</button>`; c.appendChild(t);
  });
}
function removeWord(i) { wordList.splice(i,1); renderWords(); }
function addWord() {
  const inp = document.getElementById("new-word"); const v = inp.value.trim();
  if (v && !wordList.includes(v)) { wordList.push(v); renderWords(); } inp.value = "";
}
async function saveWords() {
  const r = await api("/api/banned_words", {method:"POST",body:JSON.stringify({words:wordList})});
  r.ok ? toast("Banned words saved") : toast("Error","err");
}
document.getElementById("new-word").addEventListener("keydown", e => { if(e.key==="Enter") addWord(); });

// ── blacklist ──────────────────────────────────────────────────────────────────
let blList = [];
async function loadBL() {
  const d = await api("/api/blacklist"); blList = d.users || []; renderBL();
}
function renderBL() {
  document.getElementById("bl-cnt").textContent = blList.length + " users";
  const c = document.getElementById("bl-tags"); c.innerHTML = "";
  if (!blList.length) { c.innerHTML = '<span class="empty">No blacklisted users</span>'; return; }
  blList.forEach(uid => {
    const t = document.createElement("span"); t.className = "tag";
    t.innerHTML = `${uid}<button class="rm" onclick="removeBL(${uid})">×</button>`; c.appendChild(t);
  });
}
async function addBL() {
  const inp = document.getElementById("new-bl"); const uid = parseInt(inp.value.trim());
  if (!uid) { toast("Invalid ID","err"); return; }
  const r = await api("/api/blacklist", {method:"POST",body:JSON.stringify({action:"add",user_id:uid})});
  if (r.ok) { blList = r.users; renderBL(); toast("Blacklisted"); inp.value = ""; } else toast("Error","err");
}
async function removeBL(uid) {
  const r = await api("/api/blacklist", {method:"POST",body:JSON.stringify({action:"remove",user_id:uid})});
  if (r.ok) { blList = r.users; renderBL(); toast("Removed from blacklist"); }
}
document.getElementById("new-bl").addEventListener("keydown", e => { if(e.key==="Enter") addBL(); });

// ── permissions ────────────────────────────────────────────────────────────────
let currentPermType = "onoff";
let permData = {};
const PERM_DESCS = {
  onoff:   "Users who can use !on and !off to pause/resume the bot.",
  create:  "Users who can create custom commands and manage memories (!create, !memory).",
  persona: "Users who can switch persona, character and dictator mode (!persona, !character, !dictator — not 18+).",
};
document.querySelectorAll(".perm-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".perm-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    currentPermType = tab.dataset.perm;
    loadPermTab();
  });
});
async function loadPermTab() {
  const d = await api("/api/perms/" + currentPermType);
  permData[currentPermType] = d.users || [];
  document.getElementById("perm-desc").textContent = PERM_DESCS[currentPermType] || "";
  renderPermTags();
}
function renderPermTags() {
  const lst = permData[currentPermType] || [];
  const c = document.getElementById("perm-tags"); c.innerHTML = "";
  if (!lst.length) { c.innerHTML = '<span class="empty">No users</span>'; return; }
  lst.forEach(uid => {
    const t = document.createElement("span"); t.className = "tag";
    t.innerHTML = `${uid}<button class="rm" onclick="removePerm(${uid})">×</button>`; c.appendChild(t);
  });
}
async function addPerm() {
  const inp = document.getElementById("new-perm"); const uid = parseInt(inp.value.trim());
  if (!uid) { toast("Invalid ID","err"); return; }
  const r = await api("/api/perms/"+currentPermType, {method:"POST",body:JSON.stringify({action:"add",user_id:uid})});
  if (r.ok) { permData[currentPermType] = r.users; renderPermTags(); toast("Permission granted"); inp.value = ""; loadPermAll(); }
  else toast("Error","err");
}
async function removePerm(uid) {
  const r = await api("/api/perms/"+currentPermType, {method:"POST",body:JSON.stringify({action:"remove",user_id:uid})});
  if (r.ok) { permData[currentPermType] = r.users; renderPermTags(); toast("Permission revoked"); loadPermAll(); }
}
document.getElementById("new-perm").addEventListener("keydown", e => { if(e.key==="Enter") addPerm(); });

async function loadPermAll() {
  const [oo, cr, ps] = await Promise.all([
    api("/api/perms/onoff"), api("/api/perms/create"), api("/api/perms/persona")
  ]);
  const all = new Set([...(oo.users||[]), ...(cr.users||[]), ...(ps.users||[])]);
  const tbody = document.querySelector("#perm-all-table tbody"); tbody.innerHTML = "";
  if (!all.size) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty" style="padding:10px 13px">No permissions granted yet</td></tr>';
    return;
  }
  all.forEach(uid => {
    const tr = document.createElement("tr");
    const tick = v => v ? '✅' : '—';
    tr.innerHTML = `<td class="mono">${uid}</td><td>${tick((oo.users||[]).includes(uid))}</td><td>${tick((cr.users||[]).includes(uid))}</td><td>${tick((ps.users||[]).includes(uid))}</td>`;
    tbody.appendChild(tr);
  });
}

// ── memory ─────────────────────────────────────────────────────────────────────
async function loadMemory() {
  const d = await api("/api/memories"); renderMemory(d.memories || {});
}
function renderMemory(mem) {
  const tbody = document.querySelector("#mem-table tbody"); tbody.innerHTML = "";
  const entries = Object.entries(mem);
  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty" style="padding:9px 13px">No memories stored</td></tr>'; return;
  }
  entries.forEach(([k,v]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="mono" title="${esc(k)}">${esc(k)}</td><td>${esc(v)}</td><td><button class="btn btn-danger" style="padding:3px 9px;font-size:11px" onclick="deleteMemory('${esc(k)}')">Delete</button></td>`;
    tbody.appendChild(tr);
  });
}
async function setMemory() {
  const key = document.getElementById("mem-key").value.trim();
  const val = document.getElementById("mem-val").value.trim();
  if (!key) { toast("Key required","err"); return; }
  const r = await api("/api/memories", {method:"POST",body:JSON.stringify({action:"set",key,value:val})});
  if (r.ok) { renderMemory(r.memories); toast("Memory saved"); document.getElementById("mem-key").value=""; document.getElementById("mem-val").value=""; }
  else toast("Error","err");
}
async function deleteMemory(key) {
  const r = await api("/api/memories", {method:"POST",body:JSON.stringify({action:"delete",key})});
  if (r.ok) { renderMemory(r.memories); toast("Memory deleted"); }
}

// ── commands ───────────────────────────────────────────────────────────────────
async function loadCommands() {
  const d = await api("/api/commands"); const cmds = d.commands || {};
  const entries = Object.entries(cmds);
  document.getElementById("cmd-cnt").textContent = entries.length + " commands";
  const tbody = document.getElementById("cmd-body"); tbody.innerHTML = "";
  if (!entries.length) { tbody.innerHTML = '<tr><td colspan="3" class="empty" style="padding:9px 13px">No custom commands</td></tr>'; return; }
  entries.forEach(([name,data]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="mono2">!${esc(name)}</td><td>${esc(data.text||'')}</td><td>${data.has_files?'📎':'—'}</td>`;
    tbody.appendChild(tr);
  });
}

// ── logs ───────────────────────────────────────────────────────────────────────
let logData = [];
async function pollLogs() {
  try {
    const d = await api("/api/logs"); logData = d.logs || [];
    if (currentSection === "overview") renderOverviewLog();
    if (currentSection === "logs") renderLogs(false);
  } catch(e) {}
}
function renderOverviewLog() {
  const box = document.getElementById("overview-log");
  const recent = logData.slice(-20);
  box.innerHTML = recent.map(l => `<div class="log-line">${esc(l)}</div>`).join("") || '<span class="empty">No logs yet</span>';
  box.scrollTop = box.scrollHeight;
}
function renderLogs(scroll) {
  const box = document.getElementById("full-log");
  box.innerHTML = logData.map(l => `<div class="log-line">${esc(l)}</div>`).join("") || '<span class="empty">No logs yet</span>';
  if (scroll) box.scrollTop = box.scrollHeight;
}

// ── config ─────────────────────────────────────────────────────────────────────
async function loadCfg() {
  const d = await api("/api/config");
  document.getElementById("cfg-token-hint").textContent = d.token_masked ? "Current: " + d.token_masked : "No token set";
  document.getElementById("cfg-groq-hint").textContent = d.groq_key_set ? "✔ Key is set" : "No key set";
  document.getElementById("cfg-gemini-hint").textContent = d.gemini_key_set ? "✔ Key is set" : "No key set";
  const provEl = document.getElementById("cfg-provider");
  provEl.textContent = d.active_provider || "groq";
  provEl.style.color = d.active_provider === "gemini" ? "var(--accent2)" : "var(--accent)";
}
async function saveCfg() {
  const token  = document.getElementById("cfg-token").value.trim();
  const groq   = document.getElementById("cfg-groq").value.trim();
  const gemini = document.getElementById("cfg-gemini").value.trim();
  const deapi  = document.getElementById("cfg-deapi").value.trim();
  const payload = {};
  if (token)  payload.token      = token;
  if (groq)   payload.groq_key   = groq;
  if (gemini) payload.gemini_key = gemini;
  if (deapi)  payload.deapi_key  = deapi;
  if (!Object.keys(payload).length) { toast("Nothing to save","warn"); return; }
  const r = await api("/api/config", {method:"POST",body:JSON.stringify(payload)});
  if (r.ok) {
    toast("Credentials saved ✔"); loadCfg();
    document.getElementById("cfg-token").value = "";
    document.getElementById("cfg-groq").value = "";
    document.getElementById("cfg-gemini").value = "";
    document.getElementById("cfg-deapi").value = "";
  } else toast("Error saving","err");
}
async function clearGemini() {
  const r = await api("/api/config", {method:"POST",body:JSON.stringify({clear_gemini:true})});
  if (r.ok) { toast("Gemini key cleared — falling back to Groq","warn"); loadCfg(); }
  else toast("Error","err");
}
async function restartBot() {
  await saveCfg();
  toast("Restarting…","warn");
  await api("/api/restart", {method:"POST"});
  setTimeout(() => { pollStatus(); toast("Bot restarted","ok"); }, 3000);
}

// ── utils ──────────────────────────────────────────────────────────────────────
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

// ── boot ───────────────────────────────────────────────────────────────────────
pollStatus(); pollLogs();
setInterval(pollStatus, 5000);
setInterval(pollLogs,   3000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

# ── runner ─────────────────────────────────────────────────────────────────────
_dashboard_port = None

def start(bot_state: dict, bot_client, version: str = "1.18.0", mode: str = "online", error: str = ""):
    global _bot_state, _bot_client, _start_time, _dashboard_port, _bot_mode, _bot_error
    _bot_state  = bot_state
    _bot_client = bot_client
    _bot_mode   = mode
    _bot_error  = error
    if _start_time is None:
        _start_time = datetime.now(timezone.utc)
    if _dashboard_port is not None:
        return  # already running

    port = scan_free_port()
    _dashboard_port = port
    log(f"Dashboard starting on http://127.0.0.1:{port}")

    def _run():
        import logging as _l
        _l.getLogger("werkzeug").setLevel(_l.ERROR)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    threading.Thread(target=_run, daemon=True, name="milim-dashboard").start()
    print(f"\n  ╔══════════════════════════════════╗")
    print(f"  ║  Dashboard → http://127.0.0.1:{port} ║")
    print(f"  ╚══════════════════════════════════╝\n")

def start_offline(reason: str = "Token invalid or missing"):
    """Start the dashboard even when the bot failed to connect."""
    from milim.bot import state
    start(state, None, mode="error", error=reason)
