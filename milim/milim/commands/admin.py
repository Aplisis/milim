import discord
from milim.permissions import (
    is_owner, load_onoff_perms, save_onoff_perms,
    load_perms, save_perms, load_blacklist, save_blacklist,
    load_pps_perms, save_pps_perms, is_overseer, is_onoff_permitted,
)
from milim.constants import PERSONA_ALLOWED_ID, OWNER_ID
from milim import personas
import milim.gifs as gifs
from milim.ping import load as ping_load, save as ping_save
from milim.constants import PING_OWNER, GIF_ADD_CHANNEL
import re

async def handle_onoff(message, content):
    if not is_owner(message.author):
        await message.reply("❌ You don't have permission to use this command.")
        return True
    parts = content.split()
    if len(parts) < 2:
        await message.reply("Usage: `!onoff perm add <user_id>` | `!onoff perm remove <user_id>` | `!onoff perm list`")
        return True
    action = parts[1].lower()
    perms = load_onoff_perms()
    if action != "perm":
        await message.reply(f"❌ Unknown action `{action}`. Use `perm`.")
        return True
    if len(parts) < 3:
        await message.reply("❌ Usage: `!onoff perm add <user_id>` | `!onoff perm remove <user_id>` | `!onoff perm list`")
        return True
    sub = parts[2].lower()
    if sub == "add":
        if len(parts) != 4:
            await message.reply("❌ Usage: `!onoff perm add <user_id>`")
            return True
        try:
            target_id = int(parts[3])
        except ValueError:
            await message.reply("❌ Invalid user ID.")
            return True
        if target_id in perms:
            await message.reply(f"❌ User `{target_id}` is already allowed to use !on/!off.")
            return True
        perms.append(target_id)
        save_onoff_perms(perms)
        await message.reply(f"✅ User `{target_id}` can now use !on/!off.")
    elif sub == "remove":
        if len(parts) != 4:
            await message.reply("❌ Usage: `!onoff perm remove <user_id>`")
            return True
        try:
            target_id = int(parts[3])
        except ValueError:
            await message.reply("❌ Invalid user ID.")
            return True
        if target_id not in perms:
            await message.reply(f"❌ User `{target_id}` is not in the permission list.")
            return True
        perms.remove(target_id)
        save_onoff_perms(perms)
        await message.reply(f"✅ User `{target_id}` removed from !on/!off permission list.")
    elif sub == "list":
        if not perms:
            await message.reply("📭 No users have permission to use !on/!off beyond overseers and owner.")
            return True
        lines = ["**Users with !on/!off permission:**"]
        for uid in perms:
            lines.append(f"• <@{uid}> (`{uid}`)")
        await message.reply("\n".join(lines))
    else:
        await message.reply(f"❌ Unknown subaction `{sub}`. Use `add`, `remove` or `list`.")
    return True

async def handle_perm(message, content):
    if not is_owner(message.author):
        await message.reply("❌ You don't have permission to use this command.")
        return True
    parts = content.split()
    if len(parts) < 2:
        await message.reply("Usage: `!perm add <user_id>` | `!perm remove <user_id>` | `!perm list`")
        return True
    action = parts[1].lower()
    perms = load_perms()
    if action == "add":
        if len(parts) != 3:
            await message.reply("❌ Usage: `!perm add <user_id>`")
            return True
        try:
            target_id = int(parts[2])
        except ValueError:
            await message.reply("❌ Invalid user ID.")
            return True
        if target_id in perms:
            await message.reply(f"❌ User `{target_id}` is already in the permission list.")
            return True
        perms.append(target_id)
        save_perms(perms)
        await message.reply(f"✅ User `{target_id}` added to !create permission list.")
    elif action == "remove":
        if len(parts) != 3:
            await message.reply("❌ Usage: `!perm remove <user_id>`")
            return True
        try:
            target_id = int(parts[2])
        except ValueError:
            await message.reply("❌ Invalid user ID.")
            return True
        if target_id not in perms:
            await message.reply(f"❌ User `{target_id}` is not in the permission list.")
            return True
        perms.remove(target_id)
        save_perms(perms)
        await message.reply(f"✅ User `{target_id}` removed from !create permission list.")
    elif action == "list":
        if not perms:
            await message.reply("📭 No users have been added to the permission list.")
            return True
        lines = ["**Users with !create permission:**"]
        for uid in perms:
            lines.append(f"• <@{uid}> (`{uid}`)")
        await message.reply("\n".join(lines))
    else:
        await message.reply(f"❌ Unknown action `{action}`. Use `add`, `remove` or `list`.")
    return True

async def handle_blacklist(message, content, sent_replies):
    if not is_owner(message.author):
        await message.reply("❌ You don't have permission to use this command.")
        return True
    parts = content.split()
    if len(parts) != 2:
        await message.reply("❌ Usage: `!blacklist <user_id>` or `!unblacklist <user_id>`")
        return True
    action = parts[0][1:].lower()
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.reply("❌ Invalid user ID. Must be a number.")
        return True
    blacklist = load_blacklist()
    if action == "blacklist":
        if target_id in blacklist:
            await message.reply(f"❌ User `{target_id}` is already blacklisted.")
            return True
        deleted_count = 0
        for msg_id, reply_ids in list(sent_replies.items()):
            try:
                msg = await message.channel.fetch_message(msg_id)
                if msg.author.id == target_id:
                    for rid in reply_ids:
                        try:
                            rm = await message.channel.fetch_message(rid)
                            await rm.delete()
                            deleted_count += 1
                        except Exception:
                            pass
                    del sent_replies[msg_id]
            except Exception:
                pass
        blacklist.append(target_id)
        save_blacklist(blacklist)
        await message.reply(f"✅ User `{target_id}` blacklisted. Deleted {deleted_count} bot replies to them.")
    elif action == "unblacklist":
        if target_id not in blacklist:
            await message.reply(f"❌ User `{target_id}` is not blacklisted.")
            return True
        blacklist.remove(target_id)
        save_blacklist(blacklist)
        await message.reply(f"✅ User `{target_id}` removed from blacklist.")
    return True

async def handle_pps(message, content):
    if message.author.id != PERSONA_ALLOWED_ID and not is_owner(message.author):
        await message.reply("❌ You don't have permission to use this command.")
        return True
    parts = content.split()
    if len(parts) < 2:
        await message.reply("Usage: `!pps add <user_id>` | `!pps remove <user_id>` | `!pps list`")
        return True
    action = parts[1].lower()
    perms = load_pps_perms()
    if action == "add":
        if len(parts) != 3:
            await message.reply("❌ Usage: `!pps add <user_id>`")
            return True
        try:
            target_id = int(parts[2])
        except ValueError:
            await message.reply("❌ Invalid user ID.")
            return True
        if target_id in perms:
            await message.reply(f"❌ User `{target_id}` already has persona permissions.")
            return True
        perms.append(target_id)
        save_pps_perms(perms)
        await message.reply(f"✅ User `{target_id}` can now use `!persona` / `!character` / `!dictator` (not 18+).")
    elif action == "remove":
        if len(parts) != 3:
            await message.reply("❌ Usage: `!pps remove <user_id>`")
            return True
        try:
            target_id = int(parts[2])
        except ValueError:
            await message.reply("❌ Invalid user ID.")
            return True
        if target_id not in perms:
            await message.reply(f"❌ User `{target_id}` is not in the list.")
            return True
        perms.remove(target_id)
        save_pps_perms(perms)
        await message.reply(f"✅ User `{target_id}` removed from persona permissions.")
    elif action == "list":
        if not perms:
            await message.reply("📭 No users have extra persona permissions.")
            return True
        lines = ["**Users with !persona / !character / !dictator permission:**"]
        for uid in perms:
            lines.append(f"• <@{uid}> (`{uid}`)")
        await message.reply("\n".join(lines))
    else:
        await message.reply("❌ Unknown action. Use `add`, `remove` or `list`.")
    return True

async def handle_on_off_toggle(message, content, state):
    low = content.strip().lower()
    if low == "!off":
        if is_overseer(message.author) or is_onoff_permitted(message.author.id) or is_owner(message.author):
            state["ai_enabled"] = False
            await message.reply("🔒 AI replies disabled. Auto‑correction remains active.")
        else:
            await message.reply("❌ sorry, ur not a vampire 👀")
        return True
    if low == "!on":
        if is_overseer(message.author) or is_onoff_permitted(message.author.id) or is_owner(message.author):
            state["ai_enabled"] = True
            await message.reply("🔓 AI replies re-enabled.")
        else:
            await message.reply("sorry, ur not a vampire 👀")
        return True
    return False

async def handle_ping(message, content):
    if message.author.id != PING_OWNER:
        await message.reply("You don't have permission to use this command.")
        return True
    parts = content.strip().split()
    if len(parts) != 3 or parts[1] not in ("add", "remove"):
        await message.reply("Usage: `!ping add <user_id>` | `!ping remove <user_id>`")
        return True
    try:
        target_id = int(parts[2])
    except ValueError:
        await message.reply("Invalid user ID.")
        return True
    lst = ping_load()
    if parts[1] == "add":
        if target_id in lst:
            await message.reply(f"<@{target_id}> is already in the ping list.")
        else:
            lst.append(target_id)
            ping_save(lst)
            await message.reply(f"<@{target_id}> added to ping list. ({len(lst)} total)")
    else:
        if target_id not in lst:
            await message.reply(f"<@{target_id}> is not in the ping list.")
        else:
            lst.remove(target_id)
            ping_save(lst)
            await message.reply(f"<@{target_id}> removed from ping list. ({len(lst)} remaining)")
    return True

async def handle_gif_add(message, content):
    if message.channel.id != GIF_ADD_CHANNEL or not is_owner(message.author):
        return False
    add_match = re.match(r"^!add([a-zA-Z]+)$", content.strip(), re.IGNORECASE)
    if add_match:
        action_name = add_match.group(1).lower()
        gifs.add_gif_mode = action_name
        await message.reply(f"✅ Mode **add {action_name}** activé — envoie tes GIFs, tape `!adddone` quand t'as fini.")
        return True
    if content.strip().lower() == "!adddone":
        gifs.add_gif_mode = None
        await message.reply("✅ Ajout terminé.")
        return True
    if gifs.add_gif_mode:
        gif_urls = []
        for att in message.attachments:
            if att.url and (att.content_type or "").startswith("image/") or att.filename.lower().endswith((".gif", ".png", ".jpg", ".webp")):
                gif_urls.append(att.url)
        urls_in_msg = re.findall(r"https?://\S+", content)
        for u in urls_in_msg:
            if any(ext in u for ext in [".gif", ".png", ".jpg", ".webp", "tenor.com", "giphy.com"]):
                gif_urls.append(u)
        if gif_urls:
            db = gifs.load_gif_db()
            db.setdefault(gifs.add_gif_mode, [])
            db[gifs.add_gif_mode].extend(gif_urls)
            gifs.save_gif_db(db)
            await message.add_reaction("✅")
        return True
    return False
