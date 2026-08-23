# Milim

Discord selfbot with personas, executor status, image gen, custom commands and a bunch of utility tools.

**Requires a user token.** Selfbots violate Discord ToS — use at your own risk.

## Requirements

- Python **3.13** recommended (3.10+ works; 3.14 may break things)
- A [Groq](https://console.groq.com) API key
- Discord user token
- Optional: DeAPI key for `!image`

## Install

```bash
python setup.py
```

This will:

1. Uninstall `discord.py` if present
2. Install `discord.py-self` and the rest of the deps
3. Ask for your token + keys and write `config.json`

## Run

Stay in the project root (`~/milim`, the folder that has `setup.py` and `config.json`):

```bash
python run.py
```

Or:

```bash
python -m milim
```

Do **not** `cd` into the inner `milim/` folder and run files from there.

## Layout

```
milim/                  <- project root (run from here)
├── setup.py
├── run.py
├── requirements.txt
├── config.json         # created by setup (do not commit)
├── data/               # runtime json storage
└── milim/              <- python package
    ├── __main__.py
    ├── bot.py
    ├── events.py
    ├── config.py
    ├── constants.py
    ├── personas.py
    ├── memory.py
    ├── permissions.py
    ├── executors.py
    ├── ai.py
    ├── deapi.py
    ├── commands/
    │   ├── admin.py
    │   ├── custom.py
    │   ├── fun.py
    │   ├── image.py
    │   ├── moder.py
    │   ├── persona.py
    │   └── utility.py
    └── utils/
```

## Notes

- `config.json` holds secrets. Keep it out of git.
- Terminal controls while the bot is running: `on` / `off` / `persona <name>` / `character <name|off>` / `dictator on|off`
- Python 3.14 is not fully tested — stick to 3.13 if you can.

This was helped with AI

Planned updates :
Interface in Flask.
HuggingFace API support
Gemini API support
Local models support

