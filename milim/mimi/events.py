import asyncio
import discord
from milim.constants import (
    SILENT_CHANNELS, MAX_INPUT_CHARS, MAX_MEMORY_CHARS, BOT_VERSION, RELEASE_DATE,
)
from milim.permissions import is_blacklisted, get_sorted_role_names
from milim import personas
from milim.ai import call_groq, build_chat_messages, process_response
from milim.commands import admin, fun, utility, persona, image, custom, moder
from milim import shell
from milim.bot import terminal_listener

async def auto_delete_later(message, delay=10):
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception:
        pass

async def send_response(original_message, text):
    if len(text) > 100000:
        text = "Message too long."
    sent_ids = []
    msgs = []
    if len(text) <= 1990:
        reply = await original_message.reply(text)
        sent_ids.append(reply.id)
        msgs.append(reply)
    else:
        parts = []
        remaining = text
        while len(remaining) > 1990:
            sp = remaining.rfind("\n", 0, 1990)
            if sp == -1:
                sp = 1990
            parts.append(remaining[:sp])
            remaining = remaining[sp:].strip()
        parts.append(remaining)
        for i, p in enumerate(parts):
            if i == 0:
                reply = await original_message.reply(p)
                sent_ids.append(reply.id)
                msgs.append(reply)
            else:
                msg = await original_message.channel.send(p)
                sent_ids.append(msg.id)
                msgs.append(msg)
    if personas.persona_mode == "18+":
        for m in msgs:
            asyncio.create_task(auto_delete_later(m, 10))
    return sent_ids

async def apply_reactions(message, emojis):
    for emoji in emojis:
        try:
            await message.add_reaction(emoji)
        except Exception:
            pass

def register(client, state, memory, sent_replies):

    @client.event
    async def on_ready():
        print("bot is connected")
        try:
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"v{BOT_VERSION} · {RELEASE_DATE}",
            )
            await client.change_presence(
                status=discord.Status.online,
                activity=activity,
            )
        except Exception:
            pass
        asyncio.create_task(terminal_listener())

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return
        if not message.guild:
            return
        if message.channel.id in SILENT_CHANNELS:
            return

        content = message.content

        if is_blacklisted(message.author.id):
            if message.id in sent_replies:
                channel = message.channel
                for mid in sent_replies[message.id]:
                    try:
                        msg = await channel.fetch_message(mid)
                        await msg.delete()
                    except Exception:
                        pass
                del sent_replies[message.id]
            return

        if await moder.handle_nword(message):
            return
        if await moder.handle_scam_channel(message, sent_replies):
            return
        if await moder.handle_quick_mod(message, content):
            return

        if content.startswith("!onoff"):
            await admin.handle_onoff(message, content)
            return
        if content.startswith("!perm"):
            await admin.handle_perm(message, content)
            return
        if content.startswith("!blacklist") or content.startswith("!unblacklist"):
            await admin.handle_blacklist(message, content, sent_replies)
            return
        if await admin.handle_on_off_toggle(message, content, state):
            return
        if content.startswith("!pps"):
            await admin.handle_pps(message, content)
            return
        if await persona.handle_persona_cmds(message, content):
            return
        if content.startswith("!ping "):
            await admin.handle_ping(message, content)
            return
        if await admin.handle_gif_add(message, content):
            return

        if content.startswith("!") and not state["ai_enabled"]:
            cmd_check = content.strip().lower().split()[0][1:]
            if cmd_check != "on":
                await message.reply("🔒 Bot is currently disabled. Use `!on` to re-enable.")
                return

        if await custom.try_custom_command(message, content):
            return
        if await utility.handle_exec(message, content):
            return
        if await utility.handle_tr(message, content, state["ai_enabled"]):
            return
        if await utility.handle_makegif(message, content):
            return
        if await custom.handle_create(message, content):
            return
        if await custom.handle_memory(message, content):
            return
        if await fun.handle_gif_action(message, content):
            return
        if await fun.handle_fun_how(message, content, state["ai_enabled"]):
            return
        if await fun.handle_hstat(message, content, client, state["ai_enabled"]):
            return
        if await fun.handle_quote(message, content, client):
            return
        if await shell.handle_su(message, content):
            return
        if await shell.handle_solve(message, content, client):
            return
        if content.strip() == "!real":
            await message.add_reaction("❌")
            return
        if await utility.handle_working(message, content):
            return
        if await utility.handle_execs(message, content):
            return
        if await image.handle_image(message, content):
            return

        bot_mentioned = client.user in message.mentions
        is_reply_to_bot = (
            message.reference
            and message.reference.resolved
            and message.reference.resolved.author == client.user
        )
        if not (bot_mentioned or is_reply_to_bot):
            return
        if is_blacklisted(message.author.id):
            return
        if not state["ai_enabled"]:
            return

        user_content = content
        if bot_mentioned:
            user_content = user_content.replace(client.user.mention, "").strip()

        role_names = get_sorted_role_names(message.author)
        role_prefix = f"[User roles: {', '.join(role_names)}] " if role_names else ""
        context_text = ""
        if message.reference and message.reference.resolved:
            referenced = message.reference.resolved
            if referenced.author != client.user:
                context_text = f"\n[Context: {referenced.author.display_name} said: '{referenced.content[:500]}']"
        full_user_content = role_prefix + user_content + context_text
        if not full_user_content.strip():
            reply = await message.reply("Hey! What's up? 😄")
            sent_replies[message.id] = [reply.id]
            return

        executor_response = await utility.handle_executor_safety(message, user_content)
        if executor_response:
            sent_ids = await send_response(message, executor_response)
            if sent_ids:
                sent_replies[message.id] = sent_ids
            return

        if len(full_user_content) > MAX_INPUT_CHARS:
            full_user_content = full_user_content[:MAX_INPUT_CHARS] + "\n...(trimmed)"

        user_id = message.author.id
        memory[user_id].append({"role": "user", "content": full_user_content})
        msgs = build_chat_messages(user_id, full_user_content, memory)

        async with message.channel.typing():
            resp, last_error = await call_groq(msgs)
            if resp is None:
                if last_error == "rate_limit":
                    err = await message.reply("i'm being spammed rn, give me a sec and try again 😭")
                elif last_error and last_error.startswith("server_"):
                    err = await message.reply("groq's servers are having a moment, try again in a bit")
                elif last_error == "timeout":
                    err = await message.reply("took too long to respond, try again")
                else:
                    err = await message.reply("something went wrong on my end, try again")
                sent_replies[message.id] = [err.id]
                return
            try:
                resp, react_emojis = process_response(resp)
                memory[user_id].append({"role": "assistant", "content": resp})
                while sum(len(m["content"]) for m in memory[user_id]) > MAX_MEMORY_CHARS * 1.5:
                    memory[user_id].popleft()
                if react_emojis:
                    await apply_reactions(message, react_emojis)
                sent_ids = await send_response(message, resp)
                if sent_ids:
                    sent_replies[message.id] = sent_ids
            except Exception as e:
                print(f"post-processing error: {e}")
                err = await message.reply("got a response but something broke processing it, try again")
                sent_replies[message.id] = [err.id]

    @client.event
    async def on_message_edit(before, after):
        if before.author == client.user:
            return
        if not before.guild:
            return
        if is_blacklisted(before.author.id):
            reply_ids = sent_replies.pop(before.id, [])
            if reply_ids:
                channel = before.channel
                for mid in reply_ids:
                    try:
                        msg = await channel.fetch_message(mid)
                        await msg.delete()
                    except Exception:
                        pass
            return
        reply_ids = sent_replies.pop(before.id, [])
        if not reply_ids:
            return
        channel = before.channel
        for mid in reply_ids:
            try:
                msg = await channel.fetch_message(mid)
                await msg.delete()
            except Exception:
                pass

    @client.event
    async def on_message_delete(message):
        if message.author == client.user:
            return
        if not message.guild:
            return
        if is_blacklisted(message.author.id):
            reply_ids = sent_replies.pop(message.id, [])
            if reply_ids:
                channel = message.channel
                for mid in reply_ids:
                    try:
                        msg = await channel.fetch_message(mid)
                        await msg.delete()
                    except Exception:
                        pass
            return
        reply_ids = sent_replies.pop(message.id, [])
        if not reply_ids:
            return
        channel = message.channel
        for mid in reply_ids:
            try:
                msg = await channel.fetch_message(mid)
                await msg.delete()
            except Exception:
                pass
