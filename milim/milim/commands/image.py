import io
import os
import asyncio
import aiohttp
import discord
from datetime import datetime, timezone
from milim import deapi
from milim import config
from milim.constants import DEAPI_GEN_URL, DEAPI_JOB_URL

async def handle_image(message, content):
    if not content.startswith("!image "):
        return False
    prompt = content[7:].strip()
    if not prompt:
        await message.reply("Usage: `!image <prompt>`")
        return True
    if not config.deapi_key():
        await message.reply("Image generation is not configured (no DeAPI key).")
        return True
    now_utc = datetime.now(timezone.utc)
    cooldown = deapi.dynamic_cooldown(message.author.id)
    last = deapi.user_last_image.get(message.author.id)
    if last is not None:
        elapsed = (now_utc - last).total_seconds()
        if elapsed < cooldown:
            wait = int(cooldown - elapsed)
            await message.reply(f"Slow down! Wait **{wait}s** before generating another image.")
            return True
    balance = deapi.cached_balance()
    if balance < 0.01:
        await message.reply("Image generation is temporarily disabled (no credits left).")
        return True
    status_msg = await message.reply("Creating image...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DEAPI_GEN_URL,
                headers=deapi._headers(),
                json={
                    "prompt": prompt,
                    "model": "Flux1schnell",
                    "width": 512,
                    "height": 512,
                    "guidance": 7.5,
                    "steps": 4,
                    "seed": 0,
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status == 400:
                    body = await r.json()
                    msg = str(body)
                    if "NSFW" in msg or "nsfw" in msg:
                        await status_msg.edit(content="Sorry but this is against the rules.")
                    else:
                        await status_msg.edit(content="Image generation failed. Try again.")
                    return True
                if r.status != 200:
                    await status_msg.edit(content="Image generation failed. Try again.")
                    return True
                data = await r.json()
        request_id = data["data"]["request_id"]
        img_url = None
        for _ in range(30):
            await asyncio.sleep(3)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    DEAPI_JOB_URL.format(request_id),
                    headers=deapi._headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    job = await r.json()
            status = job["data"]["status"]
            if status == "done":
                img_url = job["data"].get("results_alt_formats", {}).get("jpg") or job["data"].get("result_url")
                break
            elif status == "failed":
                await status_msg.edit(content="Image generation failed.")
                return True
        if not img_url:
            await status_msg.edit(content="Timeout generating image. Try again.")
            return True
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url) as r:
                img_bytes = await r.read()
        save_dir = "/sdcard/download/IMG"
        try:
            os.makedirs(save_dir, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(save_dir, f"{ts}_{message.author.id}.jpg")
            with open(save_path, "wb") as f:
                f.write(img_bytes)
        except Exception:
            pass
        deapi.user_last_image[message.author.id] = now_utc
        times = deapi.user_gen_times.get(message.author.id, [])
        times.append(now_utc)
        deapi.user_gen_times[message.author.id] = times
        new_balance = await deapi.get_balance()
        img_file = discord.File(io.BytesIO(img_bytes), filename="image.jpg")
        await status_msg.edit(content=f"-# ${new_balance:.4f} remaining", attachments=[img_file])
    except Exception as e:
        print(f"!image error: {e}")
        await status_msg.edit(content="Something went wrong generating the image.")
    return True
