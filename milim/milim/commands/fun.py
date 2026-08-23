import io
import math
import os
import random
import re
import urllib.request
from PIL import Image, ImageDraw, ImageFont
import discord
from milim.constants import FUN_COMMANDS
import milim.gifs as gifs

_FONT_DIR = os.path.expanduser("~/.cache/quote_fonts")
FONT_REGULAR = os.path.join(_FONT_DIR, "NotoSans-Regular.ttf")
FONT_BOLD = os.path.join(_FONT_DIR, "NotoSans-Bold.ttf")
FONT_ITALIC = os.path.join(_FONT_DIR, "NotoSans-Italic.ttf")
FONT_MONO = os.path.join(_FONT_DIR, "NotoSansMono-Regular.ttf")

def _ensure_fonts():
    os.makedirs(_FONT_DIR, exist_ok=True)
    urls = {
        FONT_REGULAR: "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
        FONT_BOLD: "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
        FONT_ITALIC: "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Italic.ttf",
        FONT_MONO: "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansMono/NotoSansMono-Regular.ttf",
    }
    for fp, url in urls.items():
        if not os.path.exists(fp):
            try:
                urllib.request.urlretrieve(url, fp)
            except Exception:
                pass

async def handle_fun_how(message, content, ai_enabled):
    if not ai_enabled:
        return False
    fun_cmd = content.strip().split()[0].lower() if content.strip() else ""
    if content.strip() == "!howlist":
        lines = "\n".join(f"{emoji} `{cmd}`" for cmd, (emoji, _) in FUN_COMMANDS.items())
        await message.reply(f"**Available !how commands:**\n{lines}")
        return True
    if fun_cmd not in FUN_COMMANDS:
        return False
    parts = content.strip().split()
    if len(parts) < 2 or not parts[1].startswith("<@"):
        await message.reply(f"Usage: `{fun_cmd} <@user>`")
        return True
    raw = parts[1]
    user_id = raw.strip("<@!>")
    if not user_id.isdigit():
        await message.reply("❌ Invalid user mention.")
        return True
    emoji, label = FUN_COMMANDS[fun_cmd]
    seed = int(user_id) ^ hash(label)
    rng = random.Random(seed)
    percent = rng.randint(0, 100)
    bar_filled = round(percent / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    await message.reply(f"{emoji} <@{user_id}> is **{percent}%** {label}\n`[{bar}]` {percent}%")
    return True

async def handle_gif_action(message, content):
    cmd_parts = content.strip().split()
    action_cmd = cmd_parts[0].lower() if cmd_parts else ""
    if not re.match(r"^![a-zA-Z]+$", action_cmd) or len(cmd_parts) < 2 or not cmd_parts[1].startswith("<@"):
        return False
    db = gifs.load_gif_db()
    action_key = action_cmd[1:]
    if action_key not in db or not db[action_key]:
        return False
    target_raw = cmd_parts[1].strip("<@!>")
    if not target_raw.isdigit():
        return False
    target_id = int(target_raw)
    gif_url = random.choice(db[action_key])
    key = (target_id, action_key)
    gifs.action_counts[key] = gifs.action_counts.get(key, 0) + 1
    count = gifs.action_counts[key]
    ordinal = f"{count}{'st' if count == 1 else 'nd' if count == 2 else 'rd' if count == 3 else 'th'}"
    await message.channel.send(
        f"<@{message.author.id}> **{action_key}ed** <@{target_id}> for the **{ordinal}** time! [.​]({gif_url})"
    )
    return True

async def handle_hstat(message, content, client, ai_enabled):
    if not content.strip().lower().startswith("!hstat"):
        return False
    if not ai_enabled:
        return True
    parts = content.strip().split()
    if len(parts) < 3 or parts[1].lower() not in ("irl", "game") or not parts[2].startswith("<@"):
        await message.reply("Usage: `!hstat irl <@user>` or `!hstat game <@user>`")
        return True
    mode = parts[1].lower()
    user_id = parts[2].strip("<@!>")
    if not user_id.isdigit():
        await message.reply("❌ Invalid user mention.")
        return True
    if mode == "irl":
        stat_labels = ["Strength", "Intelligence", "Cardio", "Charisma", "Discipline", "Luck"]
        title = "IRL Stats"
    else:
        stat_labels = ["Roblox", "CS:GO", "Valorant", "Call of Duty", "Fortnite", "Minecraft"]
        title = "Gaming Stats"
    values = []
    for stat in stat_labels:
        seed = int(user_id) ^ hash(f"hstat:{mode}:{stat}")
        rng = random.Random(seed)
        values.append(rng.randint(10, 99))
    status_msg = await message.reply("🔄 Generating stats...")
    try:
        try:
            target_user = await client.fetch_user(int(user_id))
            subtitle = f"@{target_user.name}"
        except Exception:
            subtitle = f"user {user_id}"
        _ensure_fonts()
        CANVAS = 900
        CX, CY = CANVAS // 2, CANVAS // 2 + 30
        MAX_R = 240
        N = len(stat_labels)
        img = Image.new("RGB", (CANVAS, CANVAS), (17, 17, 22))
        draw = ImageDraw.Draw(img)

        def point_at(index, radius_frac):
            angle = math.radians(-90 + index * (360 / N))
            x = CX + radius_frac * MAX_R * math.cos(angle)
            y = CY + radius_frac * MAX_R * math.sin(angle)
            return (x, y)

        for frac in [0.2, 0.4, 0.6, 0.8, 1.0]:
            ring_points = [point_at(i, frac) for i in range(N)]
            draw.polygon(ring_points, outline=(55, 55, 68))
        for i in range(N):
            edge = point_at(i, 1.0)
            draw.line([(CX, CY), edge], fill=(55, 55, 68), width=1)
        data_points = [point_at(i, values[i] / 100) for i in range(N)]
        overlay = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.polygon(data_points, fill=(130, 90, 255, 100), outline=(180, 140, 255, 255))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        for p in data_points:
            draw.ellipse([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5], fill=(210, 180, 255))
        font_label = ImageFont.truetype(FONT_REGULAR, 27)
        font_value = ImageFont.truetype(FONT_BOLD, 21)
        for i in range(N):
            lx, ly = point_at(i, 1.30)
            text = stat_labels[i]
            bbox = draw.textbbox((0, 0), text, font=font_label)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((lx - tw / 2, ly - th / 2 - 12), text, font=font_label, fill=(230, 230, 235))
            val_text = f"{values[i]}%"
            bbox2 = draw.textbbox((0, 0), val_text, font=font_value)
            tw2, th2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
            draw.text((lx - tw2 / 2, ly - th2 / 2 + 16), val_text, font=font_value, fill=(170, 140, 220))
        font_title = ImageFont.truetype(FONT_BOLD, 40)
        tb = draw.textbbox((0, 0), title, font=font_title)
        tw3 = tb[2] - tb[0]
        draw.text(((CANVAS - tw3) / 2, 30), title, font=font_title, fill=(240, 240, 245))
        font_sub = ImageFont.truetype(FONT_REGULAR, 22)
        sb = draw.textbbox((0, 0), subtitle, font=font_sub)
        sw = sb[2] - sb[0]
        draw.text(((CANVAS - sw) / 2, 78), subtitle, font=font_sub, fill=(140, 140, 155))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await status_msg.delete()
        await message.channel.send(
            content=f"📊 <@{user_id}>'s **{title}**",
            file=discord.File(buf, filename="hstat.png"),
        )
    except Exception as e:
        print(f"!hstat error: {e}")
        await status_msg.edit(content="❌ Failed to generate stats.")
    return True

async def handle_quote(message, content, client):
    if content.strip().lower() != "!quote":
        return False
    if not message.reference:
        await message.reply("❌ Reply to a message to quote it.")
        return True
    try:
        ref_msg = await message.channel.fetch_message(message.reference.message_id)
    except Exception:
        await message.reply("❌ Could not fetch the referenced message.")
        return True
    quote_text = ref_msg.content or "[no text]"
    author = ref_msg.author
    display_name = author.display_name
    avatar_url = author.display_avatar.replace(size=256, format="png").url
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(avatar_url) as r:
            avatar_bytes = await r.read()
    _ensure_fonts()
    CANVAS_W = 1100
    CANVAS_H = 400
    AV_W = 380
    FADE_W = 160
    TEXT_X = AV_W + 40
    TEXT_MAX_W = CANVAS_W - TEXT_X - 40
    try:
        font_msg = ImageFont.truetype(FONT_REGULAR, 38)
        font_name = ImageFont.truetype(FONT_ITALIC, 28)
    except OSError:
        font_msg = ImageFont.load_default()
        font_name = ImageFont.load_default()

    def wrap_text(text, font, max_width):
        dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        words = text.split()
        lines, current = [], ""
        for word in words:
            test = (current + " " + word).strip()
            if dummy.textlength(test, font=font) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    lines = wrap_text(quote_text, font_msg, TEXT_MAX_W)
    LINE_H = 52
    NAME_H = 42
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), (15, 15, 15))
    av_raw = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
    scale = CANVAS_H / av_raw.height
    av_w2 = int(av_raw.width * scale)
    av_resized = av_raw.resize((av_w2, CANVAS_H), Image.LANCZOS)
    cx = av_w2 // 2
    left = max(0, cx - AV_W // 2)
    av_crop = av_resized.crop((left, 0, left + AV_W, CANVAS_H))
    img.paste(av_crop, (0, 0))
    fade_start = AV_W - FADE_W
    av_fade_zone = av_crop.crop((fade_start, 0, AV_W, CANVAS_H))
    black_zone = Image.new("RGB", (FADE_W, CANVAS_H), (15, 15, 15))
    mask = Image.new("L", (FADE_W, CANVAS_H))
    mask_draw = ImageDraw.Draw(mask)
    for x in range(FADE_W):
        val = int(255 * (1 - x / (FADE_W - 1)))
        mask_draw.line([(x, 0), (x, CANVAS_H)], fill=val)
    blended = Image.composite(av_fade_zone, black_zone, mask)
    img.paste(blended, (fade_start, 0))
    draw = ImageDraw.Draw(img)
    total_h = len(lines) * LINE_H + NAME_H + 16
    text_y = (CANVAS_H - total_h) // 2
    for line in lines:
        draw.text((TEXT_X, text_y), line, font=font_msg, fill=(235, 235, 235))
        text_y += LINE_H
    text_y += 16
    draw.text((TEXT_X, text_y), f"— {display_name}", font=font_name, fill=(170, 160, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    await message.channel.send(file=discord.File(buf, filename="quote.png"))
    await message.delete()
    return True
