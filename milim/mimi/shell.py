import asyncio
from milim.permissions import is_owner
from milim.constants import SOLVE_ALLOWED
import urllib.parse
import aiohttp

su_shell = None
su_bot_msg_ids = set()

async def su_run(cmd_str):
    global su_shell
    if su_shell is None or su_shell.returncode is not None:
        su_shell = await asyncio.create_subprocess_shell(
            "bash",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    sentinel = "___SU_DONE___"
    full_cmd = f"{cmd_str}\necho {sentinel}\n"
    su_shell.stdin.write(full_cmd.encode())
    await su_shell.stdin.drain()
    output_lines = []
    try:
        while True:
            line = await asyncio.wait_for(su_shell.stdout.readline(), timeout=15)
            decoded = line.decode("utf-8", errors="replace").rstrip()
            if decoded == sentinel:
                break
            output_lines.append(decoded)
    except asyncio.TimeoutError:
        return "❌ Command timed out (15s)."
    if len(output_lines) > 6:
        output_lines = output_lines[:6] + ["...(truncated)"]
    return "\n".join(output_lines) if output_lines else "(no output)"

async def handle_su(message, content):
    global su_shell
    is_su_cmd = content.strip().startswith("!su ") and is_owner(message.author)
    is_su_reply = (
        message.reference
        and is_owner(message.author)
        and message.reference.message_id in su_bot_msg_ids
        and not content.strip().startswith("!")
    )
    if not (is_su_cmd or is_su_reply):
        return False
    if is_su_cmd:
        raw_cmd = content.strip()[4:].strip()
    else:
        raw_cmd = content.strip()
    if not raw_cmd:
        await message.reply("Usage: `!su <command>`")
        return True
    headless = raw_cmd.endswith("// headless")
    if headless:
        raw_cmd = raw_cmd[: raw_cmd.rfind("// headless")].strip()
    if raw_cmd.strip() == "exit":
        if su_shell and su_shell.returncode is None:
            su_shell.terminate()
            su_shell = None
        await message.reply("🔒 Shell closed.")
        return True
    if headless:
        await su_run(raw_cmd)
        await message.reply("✅ done")
    else:
        output = await su_run(raw_cmd)
        reply = await message.reply(f"```\n{output}\n```")
        su_bot_msg_ids.add(reply.id)
    return True

async def handle_solve(message, content, client):
    if content.strip().lower() == "!solve":
        if message.author.id not in SOLVE_ALLOWED:
            await message.reply("❌ You are not authorized to use this command.")
            return True
        await message.reply("Reply to this message with a link, REMOVE HTTPS://")
        return True
    if (
        message.reference
        and message.author.id in SOLVE_ALLOWED
        and not content.strip().startswith("!")
    ):
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg.author == client.user and ref_msg.content == "Reply to this message with a link, REMOVE HTTPS://":
                raw = content.strip()
                url = "https://" + raw
                status_msg = await message.reply("🔄 Solving...")
                try:
                    encoded = urllib.parse.quote(url, safe="")
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"http://localhost:5005/solve?url={encoded}",
                            timeout=aiohttp.ClientTimeout(total=300),
                        ) as r:
                            if r.status == 200:
                                data = await r.json()
                                key = data.get("Key", "")
                                time_taken = data.get("Time", "?")
                                if key.startswith("https://"):
                                    display_key = key[len("https://"):]
                                elif key.startswith("http://"):
                                    display_key = key[len("http://"):]
                                else:
                                    display_key = key
                                await status_msg.edit(content=f"✅ Solved in {time_taken}s\n```{display_key}```")
                            else:
                                await status_msg.edit(content="❌ Solve failed.")
                except Exception as e:
                    print(f"!solve error: {e}")
                    await status_msg.edit(content="❌ Solve failed.")
                return True
        except Exception:
            pass
    return False
