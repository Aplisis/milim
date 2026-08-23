import io
import math
import os
import time
import urllib.request
from PIL import Image, ImageDraw, ImageFont
import discord
from milim.executors import (
    fetch_executors, find_executor, build_executor_message,
    is_external_executor, get_safety_message,
)
from milim.constants import EXECUTOR_NAMES, SAFETY_KEYWORDS
import re
import aiohttp
import requests
import json
from milim import config
from milim.constants import MODEL, GROQ_API_URL
from milim.commands.fun import _ensure_fonts, FONT_REGULAR, FONT_BOLD, FONT_MONO

async def handle_exec(message, content):
    if not (content.startswith("!exec ") or content == "!exec"):
        return False
    parts = content.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("❌ Usage: `!exec <executor_name>` (e.g. `!exec madium`)")
        return True
    cmd_name = parts[1].strip().lower()
    data = await fetch_executors()
    if data:
        ex = find_executor(data, cmd_name)
        if ex:
            await message.reply(build_executor_message(ex))
            return True
    await message.reply(
        f"❌ No executor found for `{cmd_name}`. Check the name or use `!create add {cmd_name} <content>` for a custom command."
    )
    return True

async def handle_working(message, content):
    if content.strip().lower() != "!working":
        return False
    status_msg = await message.reply("⏳ Fetching working executors...")
    try:
        data = await fetch_executors()
        if not data:
            await status_msg.edit(content="❌ Could not fetch executors.")
            return True
        working = []
        for e in data:
            platform = (e.get("platform") or e.get("properties", {}).get("platform") or "").lower()
            if "windows" not in platform:
                continue
            if e.get("hidden", False) or is_external_executor(e):
                continue
            if not e.get("updateStatus", False):
                continue
            working.append(e)
        working.sort(key=lambda e: (e.get("title") or "").lower())
        if not working:
            await status_msg.edit(content="❌ No working Windows executors found right now.")
            return True
        lines = [f"**Working Windows executors** ({len(working)}):", ""]
        for e in working:
            title = e.get("title") or "Unknown"
            ver = e.get("version") or "?"
            sunc = e.get("suncPercentage")
            unc = e.get("uncPercentage")
            free = e.get("free", False)
            key = e.get("keysystem", False)
            tag = "Key" if key else ("Free" if free else "Paid")
            sunc_str = f"{sunc}%" if sunc is not None else "N/A"
            unc_str = f"{unc}%" if unc is not None else "N/A"
            lines.append(f"🟢 **{title}** · `{ver}` · {tag}\n-# sUNC: **{sunc_str}** · UNC: **{unc_str}**")
        out = "\n".join(lines)
        if len(out) > 1900:
            await status_msg.delete()
            chunk = ""
            for line in lines:
                if len(chunk) + len(line) + 1 > 1900:
                    await message.channel.send(chunk)
                    chunk = line
                else:
                    chunk = (chunk + "\n" + line) if chunk else line
            if chunk:
                await message.channel.send(chunk)
        else:
            await status_msg.edit(content=out)
    except Exception as e:
        print(f"!working error: {e}")
        await status_msg.edit(content="❌ Failed to fetch working executors.")
    return True

async def handle_execs(message, content):
    if content.strip().lower() != "!execs":
        return False
    status_msg = await message.reply("⏳ Generating executor list...")
    try:
        _ensure_fonts()
        data = await fetch_executors()
        if not data:
            await status_msg.edit(content="❌ Could not fetch executors.")
            return True
        windows = [
            e for e in data
            if "windows" in (e.get("platform") or e.get("properties", {}).get("platform") or "").lower()
            and not e.get("hidden", False)
            and not is_external_executor(e)
        ]

        def sort_key(e):
            name = (e.get("title") or "").lower()
            return (0 if e.get("updateStatus") else 1, name)

        windows.sort(key=sort_key)
        COLS = 3
        CARD_W = 360
        CARD_H = 96
        PAD = 16
        HEADER_H = 90
        FOOTER_H = 36
        ROWS = math.ceil(len(windows) / COLS) if windows else 1
        W = COLS * CARD_W + (COLS + 1) * PAD
        H = HEADER_H + ROWS * CARD_H + (ROWS + 1) * PAD + FOOTER_H
        BG = (13, 13, 20)
        SURFACE = (22, 22, 34)
        BORDER_DEF = (45, 45, 65)
        C_GREEN = (34, 211, 160)
        C_RED = (244, 63, 94)
        C_MUTED = (71, 85, 105)
        C_TEXT = (241, 245, 249)
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        f_title = ImageFont.truetype(FONT_BOLD, 36)
        f_sub = ImageFont.truetype(FONT_REGULAR, 18)
        f_name = ImageFont.truetype(FONT_BOLD, 20)
        f_tag = ImageFont.truetype(FONT_REGULAR, 14)
        f_mono = ImageFont.truetype(FONT_MONO, 13)
        f_footer = ImageFont.truetype(FONT_REGULAR, 13)
        title_txt = "Executor Status"
        draw.text((PAD, 18), title_txt, font=f_title, fill=C_TEXT)
        n_up = sum(1 for e in windows if e.get("updateStatus"))
        n_dn = sum(1 for e in windows if not e.get("updateStatus"))
        sub_txt = f"{n_up} updated · {n_dn} outdated"
        draw.text((PAD, 60), sub_txt, font=f_sub, fill=C_MUTED)
        draw.line([(0, HEADER_H - 2), (W, HEADER_H - 2)], fill=(30, 30, 50), width=1)
        for idx, ex in enumerate(windows):
            col = idx % COLS
            row = idx // COLS
            x = PAD + col * (CARD_W + PAD)
            y = HEADER_H + PAD + row * (CARD_H + PAD)
            name = ex.get("title") or "Unknown"
            updated = ex.get("updateStatus", False)
            accent_col = C_GREEN if updated else C_RED
            draw.rounded_rectangle([x, y, x + CARD_W, y + CARD_H], radius=10, fill=SURFACE, outline=BORDER_DEF, width=1)
            draw.rounded_rectangle([x, y, x + 4, y + CARD_H], radius=4, fill=accent_col)
            dot_x, dot_y = x + 18, y + CARD_H // 2
            draw.ellipse([dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5], fill=accent_col)
            name_x = x + 32
            draw.text((name_x, y + 10), name, font=f_name, fill=C_TEXT)
            ver = ex.get("version") or "?"
            draw.text((name_x, y + 36), f"v{ver}", font=f_mono, fill=C_MUTED)
            free = ex.get("free", False)
            key = ex.get("keysystem", False)
            tag = "Key" if key else ("Free" if free else "Paid")
            tag_col = (99, 102, 241) if not free else (34, 197, 94) if not key else (234, 179, 8)
            tb2 = draw.textbbox((0, 0), tag, font=f_tag)
            tw2 = tb2[2] - tb2[0] + 10
            tx = x + CARD_W - tw2 - 10
            draw.rounded_rectangle([tx, y + 10, tx + tw2, y + 30], radius=5, fill=tag_col)
            draw.text((tx + 5, y + 12), tag, font=f_tag, fill=(255, 255, 255))
            sunc = ex.get("suncPercentage")
            unc = ex.get("uncPercentage")
            if sunc is not None or unc is not None:
                unc_txt = f"sUNC {sunc}%  UNC {unc}%" if sunc is not None else f"UNC {unc}%"
                draw.text((name_x, y + 58), unc_txt, font=f_mono, fill=C_MUTED)
            st_txt = "Updated" if updated else "Outdated"
            st_col = C_GREEN if updated else C_RED
            stb = draw.textbbox((0, 0), st_txt, font=f_tag)
            stw = stb[2] - stb[0] + 10
            sx = x + CARD_W - stw - 10
            draw.rounded_rectangle([sx, y + 36, sx + stw, y + 56], radius=5, fill=(10, 40, 20) if updated else (40, 10, 20))
            draw.text((sx + 5, y + 38), st_txt, font=f_tag, fill=st_col)
        footer_y = H - FOOTER_H + 8
        ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        draw.text((PAD, footer_y), f"Generated {ts} · weao.xyz", font=f_footer, fill=C_MUTED)
        draw.line([(0, H - FOOTER_H + 2), (W, H - FOOTER_H + 2)], fill=(30, 30, 50), width=1)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        await status_msg.delete()
        await message.channel.send(file=discord.File(buf, filename="execs.png"))
    except Exception as e:
        import traceback
        print(f"!execs error: {e}\n{traceback.format_exc()}")
        await status_msg.edit(content=f"❌ Failed: {e}")
    return True

async def handle_tr(message, content, ai_enabled):
    if not content.startswith("!tr"):
        return False
    if not ai_enabled:
        await message.reply("❌ AI is currently disabled. Please enable it with `!on`.")
        return True
    args = content[4:].strip().split()
    if message.reference and message.reference.resolved and len(args) >= 2:
        referenced = message.reference.resolved
        from_lang = args[0].lower()
        to_lang = args[1].lower()
        text = referenced.content
        text = re.sub(r"<@!?\d+>", "", text).strip()
        if text:
            prompt = f"Translate this from {from_lang} to {to_lang}. Reply ONLY with the translation, no explanations: {text}"
            async with message.channel.typing():
                try:
                    msgs = [{"role": "user", "content": prompt}]
                    payload = {
                        "messages": msgs,
                        "model": MODEL,
                        "temperature": 0.3,
                        "max_tokens": 500,
                        "top_p": 0.95,
                    }
                    headers = {
                        "Authorization": f"Bearer {config.groq_key()}",
                        "Content-Type": "application/json",
                    }
                    r = requests.post(GROQ_API_URL, headers=headers, data=json.dumps(payload), timeout=45)
                    if r.status_code == 200:
                        msg_obj = r.json()["choices"][0]["message"]
                        resp = (msg_obj.get("content") or "").strip()
                        if not resp:
                            await message.reply("❌ Translation failed (empty response). Try again.")
                            return True
                        await message.reply(f"🔄 **Translation ({from_lang}→{to_lang}):**\n{resp}")
                        return True
                    await message.reply("❌ Translation failed. Try again.")
                    return True
                except Exception as e:
                    print(f"Translation error: {e}")
                    await message.reply("❌ Translation failed. Try again.")
                    return True
    if len(args) >= 3:
        from_lang = args[0].lower()
        to_lang = args[1].lower()
        text = " ".join(args[2:])
        prompt = f"Translate this from {from_lang} to {to_lang}. Reply ONLY with the translation, no explanations: {text}"
        async with message.channel.typing():
            try:
                msgs = [{"role": "user", "content": prompt}]
                payload = {
                    "messages": msgs,
                    "model": MODEL,
                    "temperature": 0.3,
                    "max_tokens": 500,
                    "top_p": 0.95,
                }
                headers = {
                    "Authorization": f"Bearer {config.groq_key()}",
                    "Content-Type": "application/json",
                }
                r = requests.post(GROQ_API_URL, headers=headers, data=json.dumps(payload), timeout=45)
                if r.status_code == 200:
                    msg_obj = r.json()["choices"][0]["message"]
                    resp = (msg_obj.get("content") or "").strip()
                    if not resp:
                        await message.reply("❌ Translation failed (empty response). Try again.")
                        return True
                    await message.reply(f"🔄 **Translation ({from_lang}→{to_lang}):**\n{resp}")
                    return True
                await message.reply("❌ Translation failed. Try again.")
                return True
            except Exception as e:
                print(f"Translation error: {e}")
                await message.reply("❌ Translation failed. Try again.")
                return True
    await message.reply("❌ Usage: `!tr <from> <to> <text>` or reply to a message with `!tr <from> <to>`")
    return True

async def handle_makegif(message, content):
    if not content.startswith("!makegif"):
        return False
    if not message.reference:
        await message.reply("❌ You must reply to an image message with `!makegif`.")
        return True
    try:
        referenced = await message.channel.fetch_message(message.reference.message_id)
    except Exception:
        await message.reply("❌ Could not fetch the referenced message.")
        return True
    image_attachment = None
    for att in referenced.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            image_attachment = att
            break
    if not image_attachment:
        await message.reply("❌ The referenced message does not contain an image.")
        return True
    async with aiohttp.ClientSession() as session:
        async with session.get(image_attachment.url) as resp:
            if resp.status != 200:
                await message.reply("❌ Failed to download the image.")
                return True
            image_data = await resp.read()
    try:
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(image_data))
        gif_buffer = io.BytesIO()
        img.save(gif_buffer, format="GIF")
        gif_buffer.seek(0)
        await message.reply(file=discord.File(gif_buffer, filename="image.gif"))
    except Exception as e:
        print(f"Error converting to GIF: {e}")
        await message.reply("❌ Failed to convert image to GIF. Ensure it's a valid image.")
    return True

async def handle_executor_safety(message, user_content):
    content_lower = user_content.lower()
    found_executor = None
    for name in EXECUTOR_NAMES:
        if name in content_lower:
            found_executor = name
            break
    if not found_executor:
        return None
    words = re.findall(r"\b\w+\b", content_lower)
    is_safety = any(kw in words for kw in SAFETY_KEYWORDS)
    if not is_safety:
        return None
    data = await fetch_executors()
    if not data:
        return "❌ Failed to fetch executor data. Please try again later."
    ex = find_executor(data, found_executor)
    return get_safety_message(found_executor, ex)
