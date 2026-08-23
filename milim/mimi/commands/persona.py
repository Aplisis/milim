from milim.permissions import can_use_persona, can_use_18plus
from milim import personas
from milim.personas import PERSONAS, CHARACTERS

async def handle_persona_cmds(message, content):
    low = content.strip().lower()
    if not (low.startswith("!persona") or low.startswith("!character") or low.startswith("!dictator")):
        return False
    if not can_use_persona(message.author.id):
        await message.reply("❌ You don't have permission.")
        return True

    if low.startswith("!dictator"):
        parts = low.split()
        if len(parts) == 1 or parts[1] not in ("on", "off"):
            await message.reply(
                f"**Dictator mode:** `{'ON' if personas.dictator_mode else 'OFF'}`\n"
                f"Usage: `!dictator on` | `!dictator off`"
            )
            return True
        personas.dictator_mode = parts[1] == "on"
        await message.reply(f"✅ Dictator mode **{'ON' if personas.dictator_mode else 'OFF'}**.")
        return True

    if low.startswith("!persona"):
        parts = content.split()
        if len(parts) == 1 or (len(parts) == 2 and parts[1].lower() in ("list", "help")):
            lines = [
                f"**Persona:** `{personas.persona_mode}`",
                f"**Character:** `{personas.character_mode or 'none'}`",
                f"**Dictator:** `{'ON' if personas.dictator_mode else 'OFF'}`",
                "",
                "**Personas:** " + ", ".join(f"`{p}`" for p in PERSONAS),
                "**Characters:** " + ", ".join(f"`{c}`" for c in CHARACTERS),
                "",
                "`!persona <name>` · `!character <name|off>` · `!dictator on/off`",
            ]
            await message.reply("\n".join(lines))
            return True
        name = parts[1].lower()
        if name not in PERSONAS:
            await message.reply(f"❌ Unknown persona. Available: {', '.join(f'`{p}`' for p in PERSONAS)}")
            return True
        if name == "18+" and not can_use_18plus(message.author.id):
            await message.reply("❌ 18+ mode is restricted. You don't have permission.")
            return True
        personas.persona_mode = name
        personas.character_mode = None
        extra = " · bot replies auto-delete after 10s" if name == "18+" else ""
        await message.reply(f"✅ Persona **{name}** (character cleared).{extra}")
        return True

    if low.startswith("!character"):
        parts = content.split(maxsplit=1)
        if len(parts) == 1:
            await message.reply(
                f"**Character:** `{personas.character_mode or 'none'}`\n"
                f"Available: {', '.join(f'`{c}`' for c in CHARACTERS)}\n"
                f"`!character <name>` · `!character off`"
            )
            return True
        name = parts[1].strip().lower()
        if name in ("off", "clear", "none", "reset", "stop"):
            personas.character_mode = None
            await message.reply("✅ Character **off**. Back to persona.")
            return True
        aliases = {
            "benjamin netanyahu": "netanyahu",
            "nethanyu": "netanyahu",
            "nethanyahu": "netanyahu",
            "donald trump": "trump",
            "volodymyr zelensky": "zelensky",
            "zelenskyy": "zelensky",
            "adolf hitler": "hitler",
            "african living in nigeria": "nigerian",
            "nigeria": "nigerian",
            "elon musk": "elon",
            "kim jong un": "kim",
            "kim jong-un": "kim",
        }
        name = aliases.get(name, name)
        if name not in CHARACTERS:
            await message.reply(f"❌ Unknown character. Available: {', '.join(f'`{c}`' for c in CHARACTERS)}")
            return True
        personas.character_mode = name
        await message.reply(f"✅ Now embodying **{name}**. `!character off` to stop.")
        return True
    return False
