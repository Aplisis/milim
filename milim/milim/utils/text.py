import re
from milim.constants import BANNED_WORDS

def filter_banned_words(text):
    if not text:
        return text
    pattern = r'\b(?:' + '|'.join(re.escape(w) for w in BANNED_WORDS) + r')\b'
    return re.sub(pattern, lambda m: '•' * len(m.group()), text, flags=re.IGNORECASE)

def contains_number_list(text, threshold=4):
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    if re.search(r'\b\d+(?:\s+\d+){' + str(threshold - 1) + r',}\b', re.sub(r'[,\s;]+', ' ', text)):
        return True
    count = 0
    for line in text.strip().split('\n'):
        if re.fullmatch(r'\d+', line.strip()):
            count += 1
        else:
            count = 0
        if count >= threshold:
            return True
    return False

def extract_reactions(text):
    if not text:
        return text, []
    emojis = re.findall(r'\|\|react:(.+?)\|\|', text)
    clean = re.sub(r'\s*\|\|react:.+?\|\|', '', text).strip()
    bare = re.findall(r'\|\|(\S{1,10})\|\|', clean)
    for e in bare:
        if any(ord(c) > 127 for c in e):
            emojis.append(e)
            clean = clean.replace(f'||{e}||', '').strip()
    seen = []
    for e in emojis:
        e = e.strip()
        if e and e not in seen:
            seen.append(e)
        if len(seen) >= 3:
            break
    return clean, seen
