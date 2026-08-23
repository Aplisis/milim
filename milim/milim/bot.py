import asyncio
import sys
from collections import defaultdict, deque
import discord
from milim import config, personas
from milim.constants import BOT_VERSION, RELEASE_DATE, OWNER_ID
from milim.personas import PERSONAS, CHARACTERS

state = {
    "ai_enabled": True,
}

memory = defaultdict(lambda: deque())
sent_replies = {}

client = discord.Client()

async def terminal_listener():
    global OWNER_ID
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        cmd = line.strip()
        cmd_lower = cmd.lower()
        if cmd_lower == "off":
            state["ai_enabled"] = False
            print("AI disabled")
        elif cmd_lower == "on":
            state["ai_enabled"] = True
            print("AI enabled")
        elif cmd_lower in PERSONAS:
            personas.persona_mode = cmd_lower
            personas.character_mode = None
            print(f"Persona: {cmd_lower} (character cleared)")
        elif cmd_lower.startswith("persona "):
            name = cmd_lower.split(maxsplit=1)[1].strip()
            if name in PERSONAS:
                personas.persona_mode = name
                personas.character_mode = None
                print(f"Persona: {name}")
            else:
                print(f"Personas: {', '.join(PERSONAS.keys())}")
        elif cmd_lower == "personas":
            print(f"Personas: {', '.join(PERSONAS.keys())} | current={personas.persona_mode}")
        elif cmd_lower.startswith("character "):
            name = cmd_lower.split(maxsplit=1)[1].strip()
            if name in ("off", "clear", "none"):
                personas.character_mode = None
                print("Character off")
            elif name in CHARACTERS:
                personas.character_mode = name
                print(f"Character: {name}")
            else:
                print(f"Characters: {', '.join(CHARACTERS.keys())}")
        elif cmd_lower == "character":
            print(f"Character: {personas.character_mode or 'none'} | available: {', '.join(CHARACTERS.keys())}")
        elif cmd_lower == "dictator on":
            personas.dictator_mode = True
            print("Dictator ON")
        elif cmd_lower == "dictator off":
            personas.dictator_mode = False
            print("Dictator OFF")
        elif cmd_lower.startswith("setowner "):
            try:
                from milim import constants
                constants.OWNER_ID = int(cmd.split()[1])
                print(f"Owner {constants.OWNER_ID}")
            except (ValueError, IndexError):
                print("setowner <id>")
        else:
            print("Commands: on/off | personas | persona <n> | character <n|off> | dictator on/off | setowner <id>")

def run():
    config.load()
    token = config.token()
    if not token:
        print("No token in config.json. Run setup.py first.")
        sys.exit(1)
    from milim import events
    events.register(client, state, memory, sent_replies)
    client.run(token)
