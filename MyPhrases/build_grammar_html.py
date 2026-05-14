#!/usr/bin/env python3
"""
build_grammar_html.py
=====================
Build MyPhrases-themed grammar.html from mandarin_grammar_reference.html.

Usage:
    python build_grammar_html.py

Output:
    MyPhrases/grammar.html  — standalone, opens via localhost:8800/myphrases/static/grammar.html
"""

import os
import re
from pathlib import Path

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    import subprocess, sys
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'beautifulsoup4', '-q'])
    from bs4 import BeautifulSoup, NavigableString, Tag

SOURCE = Path.home() / "Downloads" / "mandarin_grammar_reference.html"
OUTPUT = Path(__file__).parent / "grammar.html"

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
/* ══ MYPHRASES CSS VARIABLES ════════════════════════════════════════════════ */
:root {
  --bg:           #0f172a;
  --surface:      #1e293b;
  --surface2:     #182233;
  --surface3:     #1c2844;
  --border:       #334155;
  --border2:      #475569;
  --ink:          #f1f5f9;
  --ink-2:        #cbd5e1;
  --ink-3:        #94a3b8;
  --accent:       #10b981;
  --accent-hover: #34d399;
  --accent-light: rgba(16,185,129,0.12);
  --canto-clr:    #93c5fd;
  --mando-clr:    #f9a8d4;
  --gold:         #d97706;
  --gold-soft:    #f59e0b;
  --header-h:     56px;
  --ff-zh:        'Noto Serif SC', 'SimSun', serif;
  --ff-ui:        'Manrope', system-ui, -apple-system, sans-serif;
  --ff-mono:      'DM Mono', monospace;
}

[data-theme="light"] {
  --bg:           #f6f7f9;
  --surface:      #ffffff;
  --surface2:     #f1f3f7;
  --surface3:     #e9ecf2;
  --border:       #e3e7ef;
  --border2:      #d1d5db;
  --ink:          #111827;
  --ink-2:        #4b5563;
  --ink-3:        #9ca3af;
  --accent:       #0c7c59;
  --accent-hover: #0a6549;
  --accent-light: rgba(12,124,89,0.10);
  --canto-clr:    #1d4ed8;
  --mando-clr:    #be185d;
  --gold:         #92400e;
  --gold-soft:    #b45309;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }

body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--ff-ui);
  font-size: 15px;
  line-height: 1.6;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

/* ── Anchor scroll offset (sticky header compensation) ── */
section[id] { scroll-margin-top: calc(var(--header-h) + 12px); }

/* ══ APP HEADER ══════════════════════════════════════════════════════════════ */
.app-header {
  position: sticky;
  top: 0;
  z-index: 200;
  height: var(--header-h);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
}
.header-left,
.header-right { display: flex; align-items: center; gap: 10px; }
.header-spacer { flex: 1; }
.header-brand  { display: flex; align-items: baseline; gap: 6px; }
.brand-title   { font-size: 16px; font-weight: 800; letter-spacing: -.3px; color: var(--accent); }
.brand-sub     { font-size: 11px; font-weight: 600; color: var(--ink-3); letter-spacing: .5px; text-transform: uppercase; }

.icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px;
  border: 1px solid var(--border); border-radius: 6px;
  background: transparent; color: var(--ink-2);
  cursor: pointer; font-size: 16px; transition: all 0.15s;
  line-height: 1;
}
.icon-btn:hover { background: var(--surface2); color: var(--ink); border-color: var(--border2); }

/* ══ SIDEBAR NAV ═════════════════════════════════════════════════════════════ */
.nav {
  position: fixed;
  left: 0; top: var(--header-h);
  width: 220px;
  height: calc(100vh - var(--header-h));
  background: var(--surface);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  z-index: 100;
  padding: 16px 0 40px;
}

.nav-logo {
  font-family: var(--ff-zh);
  font-size: 20px;
  color: var(--mando-clr);
  text-align: center;
  padding: 0 16px 14px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
  letter-spacing: 0.05em;
}

.nav-section {
  padding: 8px 16px 4px;
  font-size: 9px; font-weight: 600;
  letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--ink-3);
}

.nav a {
  display: block;
  padding: 6px 16px 6px 20px;
  font-size: 11.5px;
  color: var(--ink-2);
  text-decoration: none;
  transition: all 0.15s;
  border-left: 2px solid transparent;
  line-height: 1.4;
}
.nav a:hover                { color: var(--ink); background: var(--surface2); }
.nav a.wo:hover             { border-left-color: var(--mando-clr); color: var(--mando-clr); }
.nav a.gp:hover             { border-left-color: var(--canto-clr); color: var(--canto-clr); }
.nav a.active               { color: var(--ink); background: var(--surface2); border-left-color: var(--accent); }
.nav a.wo.active            { border-left-color: var(--mando-clr); }
.nav a.gp.active            { border-left-color: var(--canto-clr); }

.nav-zh { font-family: var(--ff-zh); font-size: 13px; margin-right: 4px; }

/* ══ MAIN CONTENT ════════════════════════════════════════════════════════════ */
.main { margin-left: 220px; padding: 0; }

/* ══ COVER ═══════════════════════════════════════════════════════════════════ */
.cover {
  min-height: 100vh;
  display: flex; flex-direction: column;
  justify-content: center; align-items: center;
  text-align: center; padding: 60px 40px;
  background:
    radial-gradient(ellipse at 30% 40%, rgba(249,168,212,0.07) 0%, transparent 60%),
    radial-gradient(ellipse at 70% 70%, rgba(147,197,253,0.05) 0%, transparent 60%),
    var(--bg);
  border-bottom: 1px solid var(--border);
}
.cover-zh   { font-family: var(--ff-zh); font-size: clamp(64px,8vw,96px); font-weight: 700; color: var(--mando-clr); line-height: 1; margin-bottom: 16px; letter-spacing: 0.1em; }
.cover-sub  { font-family: var(--ff-zh); font-size: clamp(20px,3vw,28px); color: var(--gold-soft); margin-bottom: 24px; letter-spacing: 0.08em; }
.cover-en   { font-size: 17px; color: var(--ink-2); margin-bottom: 8px; letter-spacing: 0.02em; }
.cover-meta { font-size: 13px; color: var(--ink-3); font-style: italic; margin-bottom: 48px; }
.cover-pills{ display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
.pill       { padding: 6px 16px; border: 1px solid var(--border2); border-radius: 100px; font-size: 12px; color: var(--ink-2); background: var(--surface2); }

/* ══ PAGE (WO + GP sections) ════════════════════════════════════════════════ */
.page {
  min-height: 100vh; padding: 48px 56px;
  border-bottom: 1px solid var(--border); position: relative;
}
.page::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
.page.wo::before { background: linear-gradient(90deg, var(--mando-clr), transparent); }
.page.gp::before { background: linear-gradient(90deg, var(--canto-clr), transparent); }

.page-category {
  font-size: 10px; font-weight: 600; letter-spacing: 0.2em; text-transform: uppercase;
  color: var(--ink-3); margin-bottom: 8px;
}
.page.wo .page-category { color: var(--mando-clr); }
.page.gp .page-category { color: var(--canto-clr); }

.page-title-zh {
  font-family: var(--ff-zh);
  font-size: clamp(36px,5vw,52px); font-weight: 700; line-height: 1.1; margin-bottom: 8px;
}
.page.wo .page-title-zh { color: var(--mando-clr); }
.page.gp .page-title-zh { color: var(--canto-clr); }

.page-title-en { font-size: 20px; font-weight: 600; color: var(--ink); margin-bottom: 6px; }

.page-structure {
  font-family: var(--ff-mono); font-size: 12px; color: var(--ink-3);
  margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid var(--border);
}

.rule-box {
  background: var(--surface2); border: 1px solid var(--border2);
  border-left: 3px solid var(--gold);
  padding: 12px 16px; border-radius: 0 4px 4px 0;
  font-size: 13.5px; font-weight: 500; color: var(--ink); margin-bottom: 24px; line-height: 1.5;
}

/* ══ PATTERN TABLE ═══════════════════════════════════════════════════════════ */
.pat-table { width: 100%; border-collapse: collapse; margin-bottom: 28px; table-layout: fixed; }
.pat-table th {
  background: var(--gold); color: #0f172a;
  font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
  padding: 10px 14px; text-align: center;
}
.pat-table td {
  background: var(--surface2); padding: 12px 14px;
  text-align: center; vertical-align: middle; border: 1px solid var(--border);
}
.pat-table tr:nth-child(odd) td  { background: var(--surface2); }
.pat-table tr:nth-child(even) td { background: var(--surface3); }

/* ══ RUBY TEXT ═══════════════════════════════════════════════════════════════ */
ruby {
  display: inline-flex; flex-direction: column-reverse;
  align-items: center; vertical-align: bottom;
  margin: 0 1px; line-height: 1;
}
ruby rb, ruby > span.rb {
  font-family: var(--ff-zh); font-size: 26px; font-weight: 700;
  color: var(--mando-clr); line-height: 1.1;
}
ruby rt {
  font-family: var(--ff-mono); font-size: 11px; color: var(--ink-3);
  white-space: nowrap; line-height: 1.4; display: block; text-align: center;
}

.zh-line {
  font-family: var(--ff-zh); display: flex; flex-wrap: wrap;
  align-items: flex-end; gap: 0; margin-bottom: 6px; line-height: 1.8;
}
.zh-line ruby rb, .zh-line ruby > span.rb { font-size: 22px; }
.zh-line ruby rt { font-size: 10px; }
.pat-table ruby rb, .pat-table ruby > span.rb { font-size: 24px; }
.pat-table ruby rt { font-size: 10px; }

/* ══ EXAMPLE BLOCK ═══════════════════════════════════════════════════════════ */
.examples { display: grid; gap: 16px; margin-top: 8px; }

.example {
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: 6px; padding: 16px 20px; transition: border-color 0.2s;
}
.example:hover { border-color: var(--border2); }
.example.mine  { border-left: 3px solid var(--accent-hover); }

.example-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;
}
.example-tag {
  font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--accent-hover);
}

/* TTS play button */
.tts-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; flex-shrink: 0;
  border: 1px solid var(--border); border-radius: 5px;
  background: transparent; color: var(--ink-3);
  cursor: pointer; font-size: 11px; transition: all 0.15s;
}
.tts-btn:hover   { background: var(--surface); color: var(--ink-2); border-color: var(--border2); }
.tts-btn.playing { background: var(--accent-light); color: var(--accent); border-color: var(--accent); }
.example-header .tts-btn { margin-left: auto; }

.example-en { font-size: 13px; color: var(--ink-2); margin-top: 6px; font-style: italic; }

/* ══ NOTES ═══════════════════════════════════════════════════════════════════ */
.notes { margin-top: 20px; display: grid; gap: 6px; }
.note {
  font-size: 12.5px; padding: 6px 12px; border-radius: 3px;
  color: var(--canto-clr); background: rgba(147,197,253,0.06);
  border-left: 2px solid var(--canto-clr);
}
.note.warn { color: var(--gold-soft);    background: rgba(217,119,6,0.06);    border-left-color: var(--gold); }
.note.good { color: var(--accent-hover); background: var(--accent-light);     border-left-color: var(--accent); }
.note.bad  { color: var(--mando-clr);   background: rgba(249,168,212,0.06);  border-left-color: var(--mando-clr); }

/* ══ SECTION LABEL ════════════════════════════════════════════════════════════ */
.section-label {
  font-size: 10px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--ink-3); margin: 20px 0 10px;
}

/* ══ REFERENCE TABLE ═════════════════════════════════════════════════════════ */
.ref-table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
.ref-table th {
  padding: 8px 12px; font-size: 11px; font-weight: 700;
  letter-spacing: 0.1em; text-transform: uppercase; text-align: left; color: #fff;
}
.ref-table td {
  padding: 8px 12px; font-size: 12px; border: 1px solid var(--border);
  color: var(--ink); vertical-align: middle;
}
.ref-table tr:nth-child(odd) td  { background: var(--surface2); }
.ref-table tr:nth-child(even) td { background: var(--surface3); }
.ref-zh { font-family: var(--ff-zh); font-size: 16px; color: var(--mando-clr); }

/* Ref-table section header colours */
.ref-wo-head { background: #9d174d; }
.ref-gp-head { background: #1e3a8a; }
[data-theme="light"] .ref-wo-head { background: #be185d; }
[data-theme="light"] .ref-gp-head { background: #1d4ed8; }

/* ══ TOC PAGE ════════════════════════════════════════════════════════════════ */
.toc-page { padding: 48px 56px; border-bottom: 1px solid var(--border); }
.toc-title { font-family: var(--ff-zh); font-size: 32px; color: var(--mando-clr); text-align: center; margin-bottom: 32px; }
.toc-section { margin-bottom: 24px; }
.toc-section-title {
  font-size: 10px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase;
  margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border);
}
.toc-section.wo .toc-section-title { color: var(--mando-clr); }
.toc-section.gp .toc-section-title { color: var(--canto-clr); }
.toc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 6px; }
.toc-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; background: var(--surface2);
  border: 1px solid var(--border); border-radius: 4px;
  text-decoration: none; transition: all 0.15s; color: inherit;
}
.toc-item:hover    { background: var(--surface3); border-color: var(--border2); }
.toc-item.wo:hover { border-color: var(--mando-clr); }
.toc-item.gp:hover { border-color: var(--canto-clr); }
.toc-num { font-size: 11px; font-weight: 700; color: var(--ink-3); min-width: 20px; }
.toc-item.wo .toc-num { color: var(--mando-clr); }
.toc-item.gp .toc-num { color: var(--canto-clr); }
.toc-zh { font-family: var(--ff-zh); font-size: 16px; color: var(--mando-clr); min-width: 70px; }
.toc-en { font-size: 12px; color: var(--ink-2); }

/* ══ SCROLLBAR ════════════════════════════════════════════════════════════════ */
::-webkit-scrollbar       { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }

/* ══ MOBILE ══════════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
  .nav          { display: none; }
  .main         { margin-left: 0; }
  .page         { padding: 32px 20px; }
  .toc-page     { padding: 32px 20px; }
  .cover        { padding: 40px 20px; }
}
"""

# ── JavaScript ────────────────────────────────────────────────────────────────

SCRIPT = """
// ── THEME TOGGLE ─────────────────────────────────────────────────────────────
const themeBtn = document.getElementById('themeToggle');
themeBtn.addEventListener('click', () => {
  const html = document.documentElement;
  const next = html.dataset.theme === 'light' ? 'dark' : 'light';
  html.dataset.theme = next;
  themeBtn.textContent = next === 'light' ? '🌙' : '☀️';
});

// ── TTS ───────────────────────────────────────────────────────────────────────
let activeAudio = null;

async function playTTS(text, btn) {
  if (activeAudio) { activeAudio.pause(); activeAudio = null; }
  document.querySelectorAll('.tts-btn.playing').forEach(b => b.classList.remove('playing'));
  btn.classList.add('playing');
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, engine: 'openai', speed: 'normal' }),
    });
    if (!res.ok) throw new Error('TTS failed ' + res.status);
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    activeAudio = new Audio(url);
    activeAudio.addEventListener('ended', () => { btn.classList.remove('playing'); activeAudio = null; });
    activeAudio.play();
  } catch (e) {
    btn.classList.remove('playing');
    console.error('TTS error:', e);
  }
}

document.querySelectorAll('.tts-btn').forEach(btn => {
  btn.addEventListener('click', () => playTTS(btn.dataset.text, btn));
});

// ── SCROLLSPY ─────────────────────────────────────────────────────────────────
const sections = document.querySelectorAll('section[id]');
const navLinks  = document.querySelectorAll('.nav a[href^="#"]');

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      navLinks.forEach(l => l.classList.remove('active'));
      const active = document.querySelector(`.nav a[href="#${entry.target.id}"]`);
      if (active) active.classList.add('active');
    }
  });
}, { threshold: 0.25 });

sections.forEach(s => observer.observe(s));
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

FONT_URL = (
    "https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800"
    "&family=Noto+Sans+HK:wght@400;500;700"
    "&family=Noto+Sans+SC:wght@400;500;700"
    "&family=Noto+Serif+SC:wght@300;400;600;700"
    "&family=DM+Mono:ital,wght@0,300;0,400;1,300"
    "&display=swap"
)


def extract_zh_text(zh_line) -> str:
    """Extract plain Chinese characters + punctuation from a .zh-line element."""
    text = ""
    for child in zh_line.children:
        if isinstance(child, NavigableString):
            text += str(child)
        elif isinstance(child, Tag):
            if child.name == "ruby":
                rb = child.find("rb") or child.find("span", class_="rb")
                if rb:
                    text += rb.get_text()
                else:
                    # Fallback: get all direct text (skips <rt>)
                    for c in child.children:
                        if isinstance(c, NavigableString):
                            text += str(c)
    return text.strip()


def add_tts_buttons(soup):
    """Wrap each .example's tag in .example-header and add a .tts-btn."""
    count = 0
    for example in soup.select(".example"):
        zh_line = example.find(class_="zh-line")
        if not zh_line:
            continue
        zh_text = extract_zh_text(zh_line)
        if not zh_text:
            continue

        # Build header wrapper
        header = soup.new_tag("div", attrs={"class": "example-header"})

        # Move existing .example-tag into the header (if present)
        tag_el = example.find(class_="example-tag")
        if tag_el:
            tag_el.extract()
            header.append(tag_el)

        # Build TTS button
        tts_btn = soup.new_tag(
            "button",
            attrs={
                "class": "tts-btn",
                "data-text": zh_text,
                "title": f"Play: {zh_text}",
                "type": "button",
            },
        )
        tts_btn.string = "▶"
        header.append(tts_btn)

        # Insert header at the very top of the example div
        example.insert(0, header)
        count += 1

    print(f"  Added TTS buttons to {count} examples.")


def fix_ref_table_headers(soup):
    """Replace inline var(--orange)/var(--blue) styles on ref-table <th> with CSS classes."""
    for th in soup.select(".ref-table th"):
        style = th.get("style", "")
        if not style:
            continue
        if "var(--orange" in style:
            existing = th.get("class", [])
            if isinstance(existing, str):
                existing = existing.split()
            th["class"] = existing + ["ref-wo-head"]
            new_style = re.sub(r"background\s*:[^;]+;?\s*", "", style).strip().rstrip(";")
            if new_style:
                th["style"] = new_style
            elif "style" in th.attrs:
                del th["style"]
        elif "var(--blue" in style:
            existing = th.get("class", [])
            if isinstance(existing, str):
                existing = existing.split()
            th["class"] = existing + ["ref-gp-head"]
            new_style = re.sub(r"background\s*:[^;]+;?\s*", "", style).strip().rstrip(";")
            if new_style:
                th["style"] = new_style
            elif "style" in th.attrs:
                del th["style"]


def fix_remaining_inline_styles(soup):
    """Replace old CSS variable names in any remaining inline style attributes."""
    VAR_MAP = [
        ("var(--orange-soft)", "var(--mando-clr)"),
        ("var(--orange)",      "var(--mando-clr)"),
        ("var(--blue-soft)",   "var(--canto-clr)"),
        ("var(--blue)",        "var(--canto-clr)"),
        ("var(--red-soft)",    "var(--mando-clr)"),
        ("var(--red)",         "var(--mando-clr)"),
        ("var(--green-soft)",  "var(--accent-hover)"),
        ("var(--green)",       "var(--accent)"),
        ("var(--text-low)",    "var(--ink-3)"),
        ("var(--text-mid)",    "var(--ink-2)"),
        ("var(--text)",        "var(--ink)"),
        ("var(--font-zh)",     "var(--ff-zh)"),
        ("var(--font-ui)",     "var(--ff-ui)"),
        ("var(--font-mono)",   "var(--ff-mono)"),
    ]
    for el in soup.find_all(style=True):
        style = el["style"]
        for old, new in VAR_MAP:
            style = style.replace(old, new)
        el["style"] = style


def build():
    if not SOURCE.exists():
        print(f"ERROR: Source not found: {SOURCE}")
        raise SystemExit(1)

    print(f"Reading source: {SOURCE}")
    with open(SOURCE, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # 1. Add TTS buttons
    print("Processing examples…")
    add_tts_buttons(soup)

    # 2. Fix ref-table <th> inline colours → CSS classes
    print("Fixing ref-table header styles…")
    fix_ref_table_headers(soup)

    # 3. Fix remaining inline style vars
    print("Fixing remaining inline var() references…")
    fix_remaining_inline_styles(soup)

    # 4. Extract nav and main elements
    nav  = soup.find("nav",  class_="nav")
    main = soup.find("main", class_="main")
    if not nav or not main:
        print("ERROR: Could not find <nav class='nav'> or <main class='main'> in source.")
        raise SystemExit(1)

    nav_html  = str(nav)
    main_html = str(main)

    # 5. Build complete HTML
    html_out = f"""<!DOCTYPE html>
<html lang="zh" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>普通话 · Grammar Reference</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="{FONT_URL}" rel="stylesheet">
  <style>{CSS}</style>
</head>
<body>

<header class="app-header">
  <div class="header-left">
    <div class="header-brand">
      <span class="brand-title">Grammar</span>
      <span class="brand-sub">普通话参考</span>
    </div>
  </div>
  <div class="header-spacer"></div>
  <div class="header-right">
    <a class="icon-btn" href="/myphrases" title="My Phrases" aria-label="My Phrases">
      <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><line x1="8" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="13" y2="14"/></svg>
    </a>
    <a class="icon-btn" href="/" title="Open Viewer" aria-label="Open Viewer">
      <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-6h6v6"/></svg>
    </a>
    <button id="themeToggle" class="icon-btn" title="Toggle theme" aria-label="Toggle theme">🌙</button>
  </div>
</header>

{nav_html}

{main_html}

<script>
{SCRIPT}
</script>

</body>
</html>
"""

    OUTPUT.write_text(html_out, encoding="utf-8")
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"\n✓ Written: {OUTPUT}")
    print(f"  Size: {size_kb:.1f} KB")
    print(f"\n  Open at: http://localhost:8800/myphrases/static/grammar.html")


if __name__ == "__main__":
    build()
