#!/usr/bin/env python3
"""
import_reference_html.py
========================
Bulk-import vocab + sentences from the two Mandarin reference HTML files into
the captures store, generating Mandarin (OpenAI) + Cantonese (Edge) TTS audio
for every entry via the local Flask server.

Usage:
    python import_reference_html.py

Requirements:
    pip install beautifulsoup4 requests
    Flask server must be running on localhost:8800
"""

import json
import os
import sys
import time

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing beautifulsoup4…")
    os.system(f"{sys.executable} -m pip install beautifulsoup4 -q")
    from bs4 import BeautifulSoup

import requests

BASE_URL   = "http://localhost:8800"
HTML_FILES = [
    os.path.expanduser("~/Downloads/mandarin_full_reference.html"),
    os.path.expanduser("~/Downloads/mandarin_vocab_reference.html"),
]
# Pause between API calls to avoid hammering TTS/translate services
TRANSLATE_DELAY = 1.2   # seconds between translate calls
CAPTURE_DELAY   = 0.5   # seconds between capture saves


# ── Parsing ──────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def parse_html_entries(path: str) -> list[dict]:
    """Return list of {mandarin, pinyin, english} dicts from vocab + sentence cards."""
    entries = []
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # ── Vocab cards (.vocab-card) ──────────────────────────────────────────
    for card in soup.select(".vocab-card"):
        # Extract plain-text mandarin (may be in <span class="mandarin"> or <ruby>)
        mandarin_el = card.select_one(".mandarin")
        if mandarin_el:
            mandarin = _clean(mandarin_el.get_text())
        else:
            # ruby-entry format
            ruby_el = card.select_one(".ruby-entry")
            if ruby_el:
                # Strip <rt> tags (romanisation), keep only base characters
                for rt in ruby_el.find_all("rt"):
                    rt.decompose()
                mandarin = _clean(ruby_el.get_text())
            else:
                continue

        pinyin_el  = card.select_one(".pinyin")
        english_el = card.select_one(".english")
        pinyin  = _clean(pinyin_el.get_text())  if pinyin_el  else ""
        english = _clean(english_el.get_text()) if english_el else ""

        if mandarin and not mandarin.startswith("…"):
            entries.append({"mandarin": mandarin, "pinyin": pinyin, "english": english})

    # ── Sentence cards (.sentence-card) ───────────────────────────────────
    for card in soup.select(".sentence-card"):
        m_el = card.select_one(".s-mandarin")
        p_el = card.select_one(".s-pinyin")
        e_el = card.select_one(".s-english")
        if not m_el:
            continue
        mandarin = _clean(m_el.get_text())
        pinyin   = _clean(p_el.get_text()) if p_el else ""
        english  = _clean(e_el.get_text()) if e_el else ""
        if mandarin:
            entries.append({"mandarin": mandarin, "pinyin": pinyin, "english": english})

    return entries


def collect_all_entries() -> list[dict]:
    all_entries: dict[str, dict] = {}  # deduplicate by mandarin text
    for path in HTML_FILES:
        if not os.path.exists(path):
            print(f"⚠  File not found, skipping: {path}")
            continue
        parsed = parse_html_entries(path)
        print(f"   {os.path.basename(path)}: {len(parsed)} entries")
        for e in parsed:
            key = e["mandarin"]
            if key not in all_entries:
                all_entries[key] = e
    return list(all_entries.values())


# ── API helpers ───────────────────────────────────────────────────────────────

def get_existing_captures() -> set[str]:
    """Return set of mandarin texts already in captures.json."""
    try:
        r = requests.get(f"{BASE_URL}/api/captures", timeout=10)
        r.raise_for_status()
        return {c.get("mandarin", "").strip() for c in r.json()}
    except Exception as e:
        print(f"⚠  Could not fetch existing captures: {e}")
        return set()


def translate(mandarin: str) -> dict | None:
    """Call /api/translate and return the JSON result."""
    try:
        r = requests.post(
            f"{BASE_URL}/api/translate",
            json={"text": mandarin},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            print(f"   ⚠  translate error: {data['error']}")
            return None
        return data
    except Exception as e:
        print(f"   ⚠  translate failed: {e}")
        return None


def save_capture(mandarin: str, pinyin: str, cantonese: str, english: str) -> bool:
    """POST to /api/captures (server generates audio)."""
    try:
        r = requests.post(
            f"{BASE_URL}/api/captures",
            json={
                "mandarin":  mandarin,
                "pinyin":    pinyin,
                "cantonese": cantonese,
                "english":   english,
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            audio = data.get("record", {}).get("audio", {})
            has_m = "✓" if audio.get("mandarin") else "✗"
            has_c = "✓" if audio.get("cantonese") else "✗"
            print(f"   ✅ saved  [mando audio:{has_m}  canto audio:{has_c}]  (total: {data.get('count')})")
            return True
        else:
            print(f"   ⚠  save response: {data}")
            return False
    except Exception as e:
        print(f"   ⚠  save failed: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n── Mandarin Reference HTML → Captures Import ─────────────────────")

    # Collect entries
    print("\n📂 Parsing HTML files…")
    entries = collect_all_entries()
    print(f"   Total unique entries: {len(entries)}")

    # Load existing captures to skip duplicates
    print("\n📋 Checking existing captures…")
    existing = get_existing_captures()
    print(f"   Already saved: {len(existing)}")

    to_import = [e for e in entries if e["mandarin"] not in existing]
    print(f"   To import:     {len(to_import)}")

    if not to_import:
        print("\n✅ Nothing to import — all entries already in captures.")
        return

    print(f"\n🚀 Importing {len(to_import)} entries (translate + TTS per entry)…\n")

    ok = 0
    fail = 0
    for i, entry in enumerate(to_import, 1):
        mandarin = entry["mandarin"]
        pinyin   = entry["pinyin"]
        english  = entry["english"]

        print(f"[{i:>3}/{len(to_import)}] {mandarin[:40]}")

        # Get Cantonese translation
        time.sleep(TRANSLATE_DELAY)
        trans = translate(mandarin)
        if trans is None:
            # Fall back: save without cantonese (audio will still generate for mandarin)
            cantonese = ""
        else:
            cantonese = trans.get("cantonese", "").strip()
            # Use server-generated pinyin if we didn't have one
            if not pinyin:
                pinyin = trans.get("pinyin", "").strip()
            if not english:
                english = trans.get("english", "").strip()

        print(f"         canto: {cantonese[:40] if cantonese else '(none)'}")

        # Save to captures (server generates audio)
        time.sleep(CAPTURE_DELAY)
        if save_capture(mandarin, pinyin, cantonese, english):
            ok += 1
        else:
            fail += 1

    print(f"\n── Done ────────────────────────────────────────────────────────────")
    print(f"   Saved:  {ok}")
    print(f"   Failed: {fail}")
    print(f"   Total:  {ok + fail}\n")


if __name__ == "__main__":
    main()
