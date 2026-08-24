#!/usr/bin/env python3
import sys
import subprocess
import os
import json
import time

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        RED = GREEN = YELLOW = CYAN = MAGENTA = WHITE = BLUE = ""
    class Style:
        BRIGHT = RESET_ALL = ""

MIN_PY = (3, 10)
REC_PY = (3, 13)

def cprint(msg, color=Fore.WHITE):
    print(color + msg + Style.RESET_ALL)

def run(cmd, silent=False):
    if silent:
        return subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.run(cmd, shell=True)

def check_python():
    v = sys.version_info
    cprint(f"Python {v.major}.{v.minor}.{v.micro}", Fore.CYAN)
    if v.major == 3 and v.minor >= 14:
        cprint("Heads up: Python 3.14 can throw random errors with some packages.", Fore.YELLOW)
        cprint("Python 3.13 is the one we recommend. Proceed at your own risk.", Fore.YELLOW)
        time.sleep(1.5)
    elif (v.major, v.minor) < MIN_PY:
        cprint(f"Need at least Python {MIN_PY[0]}.{MIN_PY[1]}. You have {v.major}.{v.minor}.", Fore.RED)
        sys.exit(1)

def step(n, total, text):
    bar_len = 24
    filled = int(bar_len * n / total)
    bar = "█" * filled + "░" * (bar_len - filled)
    cprint(f"[{bar}] {n}/{total}  {text}", Fore.GREEN)

def install_deps():
    packages = [
        "discord.py-self",
        "aiohttp",
        "requests",
        "Pillow",
        "numpy",
        "colorama",
        "python-dotenv",
    ]
    total = len(packages) + 2

    step(1, total, "Removing discord.py if present...")
    run("pip uninstall -y discord.py discord", silent=True)
    time.sleep(0.3)

    step(2, total, "Installing discord.py-self...")
    r = run("pip install --upgrade discord.py-self")
    if r.returncode != 0:
        cprint("Failed to install discord.py-self. Check your pip / network.", Fore.RED)
        sys.exit(1)

    for i, pkg in enumerate(packages[1:], start=3):
        step(i, total, f"Installing {pkg}...")
        r = run(f"pip install --upgrade {pkg}")
        if r.returncode != 0:
            cprint(f"Could not install {pkg}. Continuing anyway...", Fore.YELLOW)

    step(total, total, "Dependencies ready.")

def ask(prompt, required=True, secret=False):
    while True:
        if secret:
            try:
                import getpass
                val = getpass.getpass(Fore.CYAN + prompt + Style.RESET_ALL)
            except Exception:
                val = input(Fore.CYAN + prompt + Style.RESET_ALL)
        else:
            val = input(Fore.CYAN + prompt + Style.RESET_ALL)
        val = val.strip()
        if val or not required:
            return val
        cprint("This one is required.", Fore.RED)

def write_config():
    cprint("\n--- Configuration ---", Fore.MAGENTA)
    cprint("You need a Discord user token and an AI API key.", Fore.WHITE)
    cprint("Provide either a Groq key OR a Gemini key (or both — Gemini takes priority).", Fore.WHITE)
    cprint("DeAPI key is optional (image generation).", Fore.WHITE)
    print()

    token = ask("Discord user token: ", required=True, secret=True)
    groq  = ask("Groq API key (leave empty to use Gemini only): ", required=False, secret=True)
    gemini = ask("Gemini API key (leave empty to use Groq only): ", required=False, secret=True)
    if not groq and not gemini:
        cprint("At least one AI key (Groq or Gemini) is required.", Fore.RED)
        sys.exit(1)
    deapi = ask("DeAPI key (leave empty to skip): ", required=False, secret=True)

    root = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(root, "config.json")
    data = {
        "TOKEN": token,
        "GROQ_API_KEY": groq or "",
        "GEMINI_API_KEY": gemini or "",
        "DEAPI_KEY": deapi or "",
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    cprint(f"\nConfig written to {cfg_path}", Fore.GREEN)
    cprint("Keep that file private. Do not commit it.", Fore.YELLOW)

def main():
    cprint("=" * 50, Fore.BLUE)
    cprint("  Milim Bot – Setup", Fore.BLUE + Style.BRIGHT)
    cprint("=" * 50, Fore.BLUE)
    print()

    check_python()
    print()
    install_deps()
    print()
    write_config()
    print()
    cprint("All set. Run the bot with:", Fore.GREEN)
    cprint("  python -m milim", Fore.WHITE + Style.BRIGHT)
    cprint("or", Fore.WHITE)
    cprint("  python milim/__main__.py", Fore.WHITE + Style.BRIGHT)
    print()

if __name__ == "__main__":
    main()
