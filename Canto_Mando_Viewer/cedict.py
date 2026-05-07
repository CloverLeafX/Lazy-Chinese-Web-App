"""
CC-CEDICT loader — fast in-memory lookup and greedy sentence segmentation.

Dictionary file: data/cedict_ts.u8  (CC-CEDICT, UTF-8, updated monthly)
Format per line: Traditional Simplified [pin1 yin1] /def1/def2/…/

Public API
----------
lookup(query)          → list of entry dicts  (exact match, simp or trad)
segment_lookup(text)   → list of {word, entries} dicts  (greedy max-length)
is_loaded()            → bool
"""

import os
import re

_DICT_PATH = os.path.join(os.path.dirname(__file__), "data", "cedict_ts.u8")
_ENTRY_RE  = re.compile(r'^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.+)/$')

# Vowel → tone-mark string  (index 0=tone1 … 3=tone4, 4=neutral / no mark)
_TONES = {
    'a': 'āáǎàa',
    'e': 'ēéěèe',
    'i': 'īíǐìi',
    'o': 'ōóǒòo',
    'u': 'ūúǔùu',
    'v': 'ǖǘǚǜü',   # CC-CEDICT uses 'v' for ü / lü
}
_VOWELS = set('aeiouv')

# ── Pinyin conversion ─────────────────────────────────────────────────────────

def _syllable_to_marks(syllable: str) -> str:
    """Convert one numeric-tone syllable, e.g. 'qing2' → 'qíng', 'lv4' → 'lǜ'."""
    if not syllable:
        return syllable

    if syllable[-1].isdigit():
        tone_idx = int(syllable[-1]) - 1   # 0-based; '5' neutral → 4
        tone_idx = max(0, min(tone_idx, 4))
        syl = syllable[:-1]
    else:
        tone_idx = 4
        syl = syllable

    syl = syl.replace('u:', 'v')       # CEDICT sometimes writes u: for ü
    lower = syl.lower()

    # Determine which vowel gets the mark (standard Mandarin rule)
    mark_pos = -1
    if 'a' in lower:
        mark_pos = lower.index('a')
    elif 'e' in lower:
        mark_pos = lower.index('e')
    elif 'ou' in lower:
        mark_pos = lower.index('ou')
    else:
        for k in range(len(lower) - 1, -1, -1):
            if lower[k] in _VOWELS:
                mark_pos = k
                break

    if mark_pos == -1 or tone_idx == 4:
        return syl.replace('v', 'ü')

    vowel  = lower[mark_pos]
    marked = _TONES.get(vowel, 'aaaaa')[tone_idx] if vowel in _TONES else syl[mark_pos]
    return syl[:mark_pos] + marked + syl[mark_pos + 1:]


def _numeric_to_marks(pinyin_raw: str) -> str:
    """Convert full pinyin string, e.g. 'ai4 qing2' → 'ài qíng'."""
    return ' '.join(_syllable_to_marks(s) for s in pinyin_raw.split())


# ── In-memory indexes ─────────────────────────────────────────────────────────

_by_simplified:  dict | None = None
_by_traditional: dict | None = None


def _ensure_loaded() -> None:
    global _by_simplified, _by_traditional
    if _by_simplified is not None:
        return

    _by_simplified  = {}
    _by_traditional = {}

    if not os.path.exists(_DICT_PATH):
        print("[CEDICT] ⚠️  cedict_ts.u8 not found — "
              "download from https://www.mdbg.net/chinese/dictionary?page=cedict")
        return

    count = 0
    with open(_DICT_PATH, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = _ENTRY_RE.match(line)
            if not m:
                continue

            trad, simp, pinyin_raw, defs_raw = m.groups()
            raw_defs = [d.strip() for d in defs_raw.split('/') if d.strip()]

            measure_words, clean_defs = [], []
            for d in raw_defs:
                if d.startswith('CL:'):
                    measure_words.extend(d[3:].split(','))
                else:
                    clean_defs.append(d)

            entry = {
                'traditional':   trad,
                'simplified':    simp,
                'pinyin':        _numeric_to_marks(pinyin_raw),
                'pinyin_raw':    pinyin_raw,
                'definitions':   clean_defs,
                'measure_words': measure_words,
            }

            _by_simplified.setdefault(simp, []).append(entry)
            if trad != simp:
                _by_traditional.setdefault(trad, []).append(entry)
            count += 1

    print(f"[CEDICT] ✅ Loaded {count:,} entries")


# ── Public API ────────────────────────────────────────────────────────────────

def is_loaded() -> bool:
    return _by_simplified is not None


def lookup(query: str) -> list:
    """
    Exact lookup by simplified or traditional Chinese.
    Returns a deduplicated list of entry dicts.
    Each entry: {traditional, simplified, pinyin, pinyin_raw, definitions, measure_words}
    """
    _ensure_loaded()
    query = query.strip()
    seen, results = set(), []
    for entry in (_by_simplified.get(query) or []) + (_by_traditional.get(query) or []):
        key = (entry['traditional'], entry['pinyin_raw'])
        if key not in seen:
            seen.add(key)
            results.append(entry)
    return results


def segment_lookup(text: str, max_word_len: int = 6) -> list:
    """
    Greedy maximum-length left-to-right segmentation of a Chinese string.
    Returns list of {'word': str, 'entries': list} dicts.
    Unknown characters are returned with empty entries.
    """
    _ensure_loaded()
    results = []
    i = 0
    while i < len(text):
        matched = False
        for length in range(min(max_word_len, len(text) - i), 0, -1):
            word    = text[i:i + length]
            entries = (_by_simplified.get(word) or []) + \
                      ([e for e in (_by_traditional.get(word) or [])
                        if (e['traditional'], e['pinyin_raw']) not in
                           {(x['traditional'], x['pinyin_raw']) for x in (_by_simplified.get(word) or [])}])
            if entries:
                results.append({'word': word, 'entries': entries})
                i += length
                matched = True
                break
        if not matched:
            results.append({'word': text[i], 'entries': []})
            i += 1
    return results
