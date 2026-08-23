import os
import re
import aiohttp
import discord
from milim.permissions import has_memory_permission
from milim.commands_store import load_commands, save_commands, files_dir
from milim.memory import load_memories, save_memories
from milim.constants import MAX_MEMORY_SIZE

async def handle_create(message, content):
    if not content.startswith("!create"):
        return False
    if not has_memory_permission(message.author):
        await message.reply("❌ You don't have permission. Ask the owner to add you with `!perm add <your_id>`.")
        return True
    parts = content.split(maxsplit=2)
    if len(parts) < 2:
        await message.reply("Usage: `!create add <name> <content>` | `!create delete <name>` | `!create list`")
        return True
    action = parts[1].lower()
    commands = load_commands()
    if action == "add":
        if len(parts) < 3:
            await message.reply("❌ Usage: `!create add <name> <content>`")
            return True
        raw_name = parts[2].split(maxsplit=1)[0]
        name = raw_name.lstrip("!")
        text_content = parts[2][len(raw_name) + 1:].strip()
        if not text_content and not message.attachments:
            await message.reply("❌ Content or attachment required.")
            return True
        if name in commands:
            await message.reply(f"❌ Command `{name}` already exists. Use `!create delete {name}` first.")
            return True
        entry = {"text": text_content}
        if message.attachments:
            os.makedirs(files_dir(), exist_ok=True)
            saved_files = []
            async with aiohttp.ClientSession() as sess:
                for att in message.attachments:
                    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", att.filename)
                    filepath = os.path.join(files_dir(), f"{name}_{safe_name}")
                    async with sess.get(att.url) as r:
                        with open(filepath, "wb") as fp:
                            fp.write(await r.read())
                    saved_files.append(filepath)
            entry["files"] = saved_files
        commands[name] = entry
        save_commands(commands)
        nb_files = len(entry.get("files", []))
        await message.reply(f"✅ Command `!{name}` created.{f' ({nb_files} file(s) attached)' if nb_files else ''}")
    elif action == "delete":
        if len(parts) < 3:
            await message.reply("❌ Usage: `!create delete <name>`")
            return True
        name = parts[2].lstrip("!")
        if name not in commands:
            await message.reply(f"❌ Command `{name}` not found.")
            return True
        entry = commands[name]
        if isinstance(entry, dict):
            for fp in entry.get("files", []):
                try:
                    os.remove(fp)
                except Exception:
                    pass
        del commands[name]
        save_commands(commands)
        await message.reply(f"✅ Command `!{name}` deleted.")
    elif action == "list":
        if not commands:
            await message.reply("📭 No custom commands stored.")
            return True
        lines = ["**Custom commands:**"]
        for name, entry in commands.items():
            if isinstance(entry, str):
                lines.append(f"• `!{name}` — {len(entry)} chars")
            elif isinstance(entry, dict):
                txt = entry.get("text", "")
                nb = len(entry.get("files", []))
                desc = f"{len(txt)} chars" if txt else ""
                if nb:
                    desc += f"{', ' if desc else ''}{nb} file(s)"
                lines.append(f"• `!{name}` — {desc or 'empty'}")
        await message.reply("\n".join(lines))
    else:
        await message.reply("❌ Unknown action. Use `add`, `delete` or `list`.")
    return True

async def handle_memory(message, content):
    if not content.startswith("!memory"):
        return False
    if not has_memory_permission(message.author):
        await message.reply("❌ You don't have permission. Ask the owner to add you with `!perm add <your_id>`.")
        return True
    parts = content.split(maxsplit=2)
    if len(parts) < 2:
        await message.reply(
            "Usage: `!memory add <name> <content>` | `!memory delete <name>` | "
            "`!memory edit <name> <new_content>` | `!memory list`"
        )
        return True
    action = parts[1].lower()
    memories = load_memories()
    if action == "add":
        if len(parts) < 3:
            await message.reply("❌ Usage: `!memory add <name> <content>`")
            return True
        name = parts[2].split(maxsplit=1)[0]
        content_body = parts[2][len(name) + 1:].strip()
        if not content_body:
            await message.reply("❌ Content cannot be empty.")
            return True
        content_bytes = len(content_body.encode("utf-8"))
        if content_bytes > MAX_MEMORY_SIZE:
            await message.reply(f"❌ Too large. Max 1KB ({MAX_MEMORY_SIZE} bytes), yours {content_bytes}.")
            return True
        if name in memories:
            await message.reply(f"❌ Memory `{name}` already exists.")
            return True
        memories[name] = content_body
        save_memories(memories)
        await message.reply(f"✅ Memory `{name}` saved. Size: {content_bytes} bytes.")
    elif action == "delete":
        if len(parts) < 3:
            await message.reply("❌ Usage: `!memory delete <name>`")
            return True
        name = parts[2]
        if name not in memories:
            await message.reply(f"❌ Memory `{name}` not found.")
            return True
        del memories[name]
        save_memories(memories)
        await message.reply(f"✅ Memory `{name}` deleted.")
    elif action == "edit":
        if len(parts) < 3:
            await message.reply("❌ Usage: `!memory edit <name> <new_content>`")
            return True
        name = parts[2].split(maxsplit=1)[0]
        new_content = parts[2][len(name) + 1:].strip()
        if not new_content:
            await message.reply("❌ Content cannot be empty.")
            return True
        content_bytes = len(new_content.encode("utf-8"))
        if content_bytes > MAX_MEMORY_SIZE:
            await message.reply(f"❌ Too large. Max 1KB ({MAX_MEMORY_SIZE} bytes), yours {content_bytes}.")
            return True
        if name not in memories:
            await message.reply(f"❌ Memory `{name}` not found.")
            return True
        memories[name] = new_content
        save_memories(memories)
        await message.reply(f"✅ Memory `{name}` updated. New size: {content_bytes} bytes.")
    elif action == "list":
        if not memories:
            await message.reply("📭 No global memories stored.")
            return True
        lines = ["**Global memories:**"]
        for name, body in memories.items():
            if isinstance(body, str):
                size = len(body.encode("utf-8"))
                lines.append(f"• `{name}` ({size} bytes)")
            else:
                lines.append(f"• `{name}` ({str(body)})")
        await message.reply("\n".join(lines))
    else:
        await message.reply("❌ Unknown action. Use `add`, `delete`, `edit` or `list`.")
    return True

async def try_custom_command(message, content):
    if not content.startswith("!"):
        return False
    parts = content.split(maxsplit=1)
    cmd_name = parts[0][1:].lower()
    reserved = {
        "create", "memory", "off", "on", "tr", "exec", "blacklist", "unblacklist",
        "perm", "makegif", "onoff", "working", "execs", "persona", "character",
        "dictator", "pps", "image", "quote", "hstat", "howlist", "real", "solve",
        "su", "ping",
    }
    if cmd_name in reserved:
        return False
    custom_cmds = load_commands()
    if cmd_name not in custom_cmds:
        return False
    entry = custom_cmds[cmd_name]
    if isinstance(entry, str):
        await message.reply(entry)
    elif isinstance(entry, dict):
        text = entry.get("text", "") or None
        files = []
        for fp in entry.get("files", []):
            if os.path.exists(fp):
                files.append(discord.File(fp))
        if files:
            await message.reply(content=text, files=files)
        elif text:
            await message.reply(text)
    return True
