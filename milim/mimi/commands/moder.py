import re
from milim.ping import mentions as ping_mentions
from milim.constants import (
    STAFF_ROLES_FOR_N_WORD, MRBEAST_SCAM_CHANNEL,
    SCAM_FILENAMES, SAFE_DOMAINS, SAFE_EXTENSIONS,
)

async def handle_nword(message):
    nword_pattern = re.compile(r"\b(nigger)\b", re.IGNORECASE)
    if not nword_pattern.search(message.content):
        return False
    has_staff_role = any(role.id in STAFF_ROLES_FOR_N_WORD for role in message.author.roles)
    alert_msg = "N word detected🙅"
    if not has_staff_role:
        alert_msg += "\n" + ping_mentions()
    alert_msg += (
        f"\n-# user info :\n"
        f"-# user id : {message.author.id}\n"
        f"-# username : {message.author.name}\n"
        f"-# recommended action :\n"
        f"-# `?mute {message.author.id} 1w Hard R`"
    )
    await message.reply(alert_msg)
    return True

async def handle_scam_channel(message, sent_replies):
    if message.channel.id != MRBEAST_SCAM_CHANNEL:
        return False
    if message.attachments:
        images = [
            a for a in message.attachments
            if (a.content_type and a.content_type.startswith("image/"))
            or a.filename.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "gif", "webp", "bmp")
        ]
        for attachment in images:
            if attachment.filename.lower() in SCAM_FILENAMES:
                user_info = (
                    f"\n-# user-info :\n"
                    f"-# userid : {message.author.id}\n"
                    f"-# username : {message.author.name}\n"
                    f"-# recommended action :\n"
                    f"-# `?softban {message.author.id} Compromised account`"
                )
                reply_msg = await message.reply(
                    f"{ping_mentions()} Compromised account detected. "
                    f"*(this message will delete itself when the image is deleted)*{user_info}"
                )
                sent_replies[message.id] = sent_replies.get(message.id, []) + [reply_msg.id]
                return True
        if len(images) >= 4:
            user_info = (
                f"\n-# user-info :\n"
                f"-# userid : {message.author.id}\n"
                f"-# username : {message.author.name}\n"
                f"-# recommended action :\n"
                f"-# `?softban {message.author.id} Compromised account`"
            )
            await message.channel.send(f"{ping_mentions()} Compromised account detected.{user_info}")
            return True
        return False
    url_pattern = re.compile(r"https?://\S+", re.IGNORECASE)
    clean_content = re.sub(r"<#\d+>", "", message.content)
    urls = url_pattern.findall(clean_content)
    if not urls:
        return False
    for url in urls:
        if url.startswith("https://discord.com/") or url.startswith("https://discord.gg/"):
            continue
        url_lower = url.lower().split("?")[0]
        is_safe = False
        for domain in SAFE_DOMAINS:
            if domain in url_lower:
                is_safe = True
                break
        if not is_safe and ("gif" in url_lower or "gifs" in url_lower):
            is_safe = True
        if not is_safe:
            for ext in SAFE_EXTENSIONS:
                if url_lower.endswith(ext):
                    is_safe = True
                    break
        if not is_safe:
            user_info = (
                f"\n-# user-info :\n"
                f"-# userid : {message.author.id}\n"
                f"-# username : {message.author.name}\n"
                f"-# recommended action :\n"
                f"-# `?mute {message.author.id} 5h Sent a link in a public chat.`"
            )
            await message.reply(
                "⚠️ You **broke** a rule!\n"
                f"Links are **not allowed** in this channel — read rule **4** again! {ping_mentions()}\n"
                f"If you meant to share an image or gif, attach it directly instead.{user_info}"
            )
            return True
    return False

async def handle_quick_mod(message, content):
    if not (content.startswith("+") and message.reference):
        return False
    cmd = content.strip()
    try:
        ref_msg = await message.channel.fetch_message(message.reference.message_id)
        target_id = ref_msg.author.id
    except Exception:
        await message.reply("❌ Could not fetch the referenced message.")
        return True
    if cmd.lower() == "+id":
        await message.reply(f"`{target_id}`")
        return True
    if cmd.lower() == "+w":
        await message.reply(f"`?warn {target_id}`")
        return True
    if re.match(r"^\+m\d+h?dm$", cmd.lower()):
        await message.reply(f"`?mute {target_id} Leading to dms`")
        return True
    m = re.match(r"^\+m(\d+[smhdw])$", cmd.lower())
    if m:
        duration = m.group(1)
        await message.reply(f"`?mute {target_id} {duration}`")
        return True
    if cmd.lower() == "+b":
        await message.reply(f"`?ban {target_id}`")
        return True
    if cmd.lower() == "+sb":
        await message.reply(f"`?softban {target_id}`")
        return True
    return False
