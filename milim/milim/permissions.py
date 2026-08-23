import json
import os
from milim import config
from milim.constants import OWNER_ID, PERSONA_ALLOWED_ID, ROLE_HIERARCHY

def _load_list(filename):
    p = config.path(filename)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def _save_list(filename, data):
    with open(config.path(filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_onoff_perms():
    return _load_list("onoff_perms.json")

def save_onoff_perms(perms):
    _save_list("onoff_perms.json", perms)

def is_onoff_permitted(user_id):
    return user_id in load_onoff_perms()

def load_pps_perms():
    return _load_list("pps_perms.json")

def save_pps_perms(perms):
    _save_list("pps_perms.json", perms)

def is_pps_permitted(user_id):
    return user_id in load_pps_perms()

def can_use_persona(user_id):
    return user_id == PERSONA_ALLOWED_ID or user_id == OWNER_ID or is_pps_permitted(user_id)

def can_use_18plus(user_id):
    return user_id == PERSONA_ALLOWED_ID or user_id == OWNER_ID

def load_blacklist():
    return _load_list("blacklist.json")

def save_blacklist(blacklist):
    _save_list("blacklist.json", blacklist)

def is_blacklisted(user_id):
    return user_id in load_blacklist()

def load_perms():
    return _load_list("perms.json")

def save_perms(perms):
    _save_list("perms.json", perms)

def is_perm_user(user_id):
    return user_id in load_perms()

def get_highest_role(member):
    highest = -1
    for role in member.roles:
        if role.id in ROLE_HIERARCHY:
            if ROLE_HIERARCHY[role.id] > highest:
                highest = ROLE_HIERARCHY[role.id]
    return highest

def is_overseer(member):
    return get_highest_role(member) >= 7

def get_sorted_role_names(member):
    roles = []
    for role in member.roles:
        if role.id in ROLE_HIERARCHY:
            roles.append((role.name, ROLE_HIERARCHY[role.id]))
    roles.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in roles]

def is_owner(member):
    return member.id == OWNER_ID

def has_memory_permission(member):
    if member.id == 1531175662415773749:
        return True
    if is_perm_user(member.id):
        return True
    return get_highest_role(member) >= 1
