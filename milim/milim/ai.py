import asyncio
import aiohttp
from milim import config
from milim.constants import MODEL as _DEFAULT_MODEL, GROQ_API_URL, GEMINI_API_URL
from milim.personas import get_system_prompt
from milim.memory import get_memory_injection
from milim.utils.text import filter_banned_words, contains_number_list, extract_reactions

groq_semaphore = asyncio.Semaphore(1)

# ── provider selection ────────────────────────────────────────────────────────

def get_provider() -> str:
    """Return 'gemini' if a Gemini key is set, otherwise 'groq'."""
    return "gemini" if config.gemini_key() else "groq"

# ── Groq ───────────────────────────────────────────────────────────────────────

async def call_groq(messages, temperature=0.9, max_tokens=400):
    payload = {
        "messages": messages,
        "model": config.model(_DEFAULT_MODEL) or _DEFAULT_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 0.95,
    }
    headers = {
        "Authorization": f"Bearer {config.groq_key()}",
        "Content-Type": "application/json",
    }
    last_error = None
    async with groq_semaphore:
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        GROQ_API_URL,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=45),
                    ) as r:
                        if r.status == 200:
                            data = await r.json()
                            msg_obj = data["choices"][0]["message"]
                            resp = (msg_obj.get("content") or "").strip()
                            if not resp:
                                if attempt < 2:
                                    payload["max_tokens"] = 600
                                    last_error = "empty_content"
                                    await asyncio.sleep(1)
                                    continue
                                return "hmm", None
                            return resp, None
                        elif r.status == 429:
                            wait = 5 * (attempt + 1)
                            last_error = "rate_limit"
                            await asyncio.sleep(wait)
                        elif r.status in (500, 502, 503, 504):
                            wait = 3 * (attempt + 1)
                            last_error = f"server_{r.status}"
                            await asyncio.sleep(wait)
                        else:
                            body = await r.text()
                            print(f"Groq API error {r.status}: {body[:300]}")
                            last_error = f"http_{r.status}"
                            break
            except asyncio.TimeoutError:
                last_error = "timeout"
                await asyncio.sleep(3)
            except Exception as e:
                print(f"Groq request exception: {e}")
                last_error = "exception"
                break
    return None, last_error

# ── Gemini ─────────────────────────────────────────────────────────────────────

async def call_gemini(messages, temperature=0.9, max_tokens=400):
    """
    Call Google Gemini via the REST API (gemini-2.0-flash by default).
    messages follows the OpenAI format; we convert to Gemini's format here.
    """
    key = config.gemini_key()
    if not key:
        return None, "no_gemini_key"

    # Extract system prompt and convert history
    system_text = ""
    gemini_contents = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if role == "system":
            system_text = content
        elif role == "user":
            gemini_contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            gemini_contents.append({"role": "model", "parts": [{"text": content}]})

    payload = {
        "contents": gemini_contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.95,
        },
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}

    _gem_model = config.model("gemini-2.0-flash")
    _gem_url = f"https://generativelanguage.googleapis.com/v1beta/models/{_gem_model}:generateContent"
    url = f"{_gem_url}?key={key}"
    last_error = None

    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=45),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        try:
                            resp = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        except (KeyError, IndexError):
                            resp = ""
                        if not resp:
                            last_error = "empty_content"
                            await asyncio.sleep(1)
                            continue
                        return resp, None
                    elif r.status == 429:
                        last_error = "rate_limit"
                        await asyncio.sleep(5 * (attempt + 1))
                    elif r.status in (500, 502, 503, 504):
                        last_error = f"server_{r.status}"
                        await asyncio.sleep(3 * (attempt + 1))
                    else:
                        body = await r.text()
                        print(f"Gemini API error {r.status}: {body[:300]}")
                        last_error = f"http_{r.status}"
                        break
        except asyncio.TimeoutError:
            last_error = "timeout"
            await asyncio.sleep(3)
        except Exception as e:
            print(f"Gemini request exception: {e}")
            last_error = "exception"
            break
    return None, last_error

# ── unified call ───────────────────────────────────────────────────────────────

async def call_ai(messages, temperature=0.9, max_tokens=400):
    """Call whichever provider is configured (Gemini if key set, else Groq)."""
    if get_provider() == "gemini":
        return await call_gemini(messages, temperature, max_tokens)
    return await call_groq(messages, temperature, max_tokens)

# ── helpers ────────────────────────────────────────────────────────────────────

def build_chat_messages(user_id, full_user_content, memory_dict):
    system_prompt = {
        "role": "system",
        "content": get_system_prompt(get_memory_injection()),
    }
    msgs = [system_prompt]
    chars = 0
    hist = []
    from milim.constants import MAX_MEMORY_CHARS
    for p in reversed(memory_dict[user_id]):
        c = len(p["content"]) + 50
        if chars + c > MAX_MEMORY_CHARS:
            break
        hist.insert(0, p)
        chars += c
    msgs.extend(hist)
    msgs.append({"role": "user", "content": full_user_content})
    return msgs

def process_response(resp):
    resp, react_emojis = extract_reactions(resp)
    resp = filter_banned_words(resp)
    if contains_number_list(resp):
        resp = "Sorry, I can't display a list of numbers!"
    if not resp.strip():
        resp = "hmm"
    return resp, react_emojis
