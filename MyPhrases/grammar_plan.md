# Grammar Reference Rebuild Plan

Convert `mandarin_grammar_reference.html` into the MyPhrases suite theme with TTS, as a standalone file at `MyPhrases/grammar.html`.

---

## Goal

Recreate the full Mandarin grammar reference page so it:
- Looks visually identical to the rest of the MyPhrases suite (same CSS variables, header, fonts, dark/light toggle)
- Adds a TTS play button to every example sentence
- Remains fully self-contained (no external app.js or styles.css dependency — inline styles + inline script)
- Is not yet linked up to the nav

---

## File Output

**`MyPhrases/grammar.html`** — standalone, opens directly in a browser

---

## Structure

### 1. Head
- Same Google Fonts as MyPhrases: `Manrope`, `Noto Sans HK`, `Noto Sans SC`
- Add `Noto Serif SC` for the decorative Chinese titles (used in original)
- Inline `<style>` block: MyPhrases CSS variables + grammar-specific layout styles
- Title: `普通话 · Grammar Reference`

### 2. Header (identical to MyPhrases)
```
[ 普通话 Grammar  ]  [ ← spacer → ]  [ 🌙 theme toggle ]
```
- `.app-header` with `.brand-title` = "Grammar" + `.brand-sub` = "普通话参考"
- Icon button for theme toggle (dark/light)
- No search bar needed (page uses sidebar nav for navigation)

### 3. Sidebar Nav (retains original left sidebar)
- Fixed left sidebar, 220px wide, matching `--surface` + `--border` colours
- Logo at top using `--mando-clr` (pink) instead of the old red
- Section headers styled with `--ink-3` uppercase labels
- Nav links: Word Order coloured with `--mando-clr` tint, Grammar Patterns with `--canto-clr` (blue) tint
- Active link highlight uses `--accent` (green)

### 4. Main Content Area
- Left margin of 220px to clear sidebar
- Cover section → TOC → 10 Word Order pages → 12 Grammar Pattern pages → Reference table
- All content kept verbatim from source HTML; only CSS class names remapped

### 5. CSS Variable Remapping

| Original var | MyPhrases equivalent |
|---|---|
| `--bg` | `--bg` (same concept, new value `#0f172a`) |
| `--surface` | `--surface` |
| `--surface2` | `--surface2` |
| `--surface3` | `rgba` variant of `--surface2` |
| `--border` | `--border` |
| `--border2` | slightly lighter `--border` |
| `--red` / `--red-soft` | `--mando-clr` (`#f9a8d4`) |
| `--blue` / `--blue-soft` | `--canto-clr` (`#93c5fd`) |
| `--gold` | amber accent `#d97706` |
| `--green` / `--green-soft` | `--accent` / `--accent-hover` |
| `--text` | `--ink` |
| `--text-mid` | `--ink-2` |
| `--text-low` | `--ink-3` |
| `--font-zh` | `Noto Serif SC` (keep for decorative titles) |
| `--font-ui` | `Manrope` |
| `--font-mono` | `DM Mono` (keep, add to font import) |

### 6. Page Section Styles
- `.page.wo` (Word Order) — left-border accent using `--mando-clr`
- `.page.gp` (Grammar Pattern) — left-border accent using `--canto-clr`
- `.page-title-zh` uses appropriate colour per section type
- `.rule-box` — styled like a MyPhrases note card with `--accent-light` background
- `.example` — uses `.phrase-card` visual style (border, border-radius, subtle gradient)
- `.example.mine` — left border in `--accent` green (personal examples)
- `.pat-table` — header rows using `--mando-clr` or `--canto-clr` depending on section
- `.ref-table` — same

### 7. TTS Play Button — on every `.example`

Each example block gets a TTS trigger button in the top-right corner:

```html
<div class="example mine">
  <div class="example-header">
    <span class="example-tag">★ Your sentence</span>
    <button class="tts-btn" data-text="我通常七点起床，就算周末也一样。">
      ▶
    </button>
  </div>
  <div class="zh-line">...</div>
  <div class="example-en">...</div>
</div>
```

- `data-text` = the plain Chinese text of the sentence (stripped of ruby markup)
- Button styled as a small icon button matching `.icon-btn` from MyPhrases
- Playing state adds `.playing` class → accent background (same pattern as phrase-line)

### 8. TTS Script (inline `<script>` at bottom)

```javascript
// TTS — calls /api/tts identical to how the keyboard widget does it
const BASE = '';  // relative — works when served from same server

let activeAudio = null;

async function playTTS(text, btn) {
  if (activeAudio) { activeAudio.pause(); activeAudio = null; }
  document.querySelectorAll('.tts-btn.playing').forEach(b => b.classList.remove('playing'));

  btn.classList.add('playing');
  try {
    const res = await fetch(`${BASE}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice: 'zh-CN-XiaoxiaoMultilingualNeural', engine: 'edge', speed: 'slow' }),
    });
    if (!res.ok) throw new Error('TTS failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    activeAudio = new Audio(url);
    activeAudio.addEventListener('ended', () => {
      btn.classList.remove('playing');
      activeAudio = null;
    });
    activeAudio.play();
  } catch (e) {
    btn.classList.remove('playing');
    console.error('TTS error:', e);
  }
}

document.querySelectorAll('.tts-btn').forEach(btn => {
  btn.addEventListener('click', () => playTTS(btn.dataset.text, btn));
});
```

### 9. Theme Toggle Script

```javascript
const themeBtn = document.getElementById('themeToggle');
themeBtn.addEventListener('click', () => {
  const html = document.documentElement;
  html.dataset.theme = html.dataset.theme === 'light' ? 'dark' : 'light';
});
```

### 10. Scrollspy (retain original)
- `IntersectionObserver` highlights active nav link as user scrolls
- Unchanged from original logic

---

## Implementation Steps

1. **Copy source HTML** content (all `<section>` blocks) verbatim — no content changes
2. **Replace `<head>`** with new font imports + inline MyPhrases-themed CSS
3. **Replace `<nav>`** with sidebar using MyPhrases colour variables
4. **Add `.app-header`** above the sidebar+main layout
5. **Remap CSS class colours** — update `.page.wo` and `.page.gp` rule colours only
6. **Add `data-text` attribute** to every `.tts-btn` — extract plain text from each `zh-line`
7. **Add TTS button HTML** inside each `.example-header` wrapper
8. **Inline the JS** — TTS handler + theme toggle + scrollspy
9. **Verify** file opens correctly in browser without the server (static nav, fonts)
10. **Verify TTS** works when served via `localhost:8800/myphrases/static/grammar.html`

---

## Notes

- File is standalone — no imports from `app.js` or `styles.css`
- TTS calls `/api/tts` — only works when served via the Canto_Mando_Viewer server (not file://)
- Light mode fully supported via `[data-theme="light"]` block matching MyPhrases
- Mobile: sidebar hides at `max-width: 768px` (same as original)
- No database or API dependency beyond TTS
