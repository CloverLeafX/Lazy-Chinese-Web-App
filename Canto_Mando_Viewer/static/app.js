/* ═══════════════════════════════════════════════════════════════════════════
   Canto → Mando Blueprint — Combined App
   Course Viewer + Phrase Navigator + Integrated TTS
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ── SVG Icons (Lucide 16×16) ─────────────────────────────────────────────────
const SVG = {
  speaker: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>`,
  copy:    `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
  check:   `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  play:    `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 3 19 12 5 21 5 3"/></svg>`,
  pause:   `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`,
  loader:  `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spinning"><path d="M21 12a9 9 0 1 1-9-9"/></svg>`,
  pdf:     `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
  video:   `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>`,
  chevron: `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>`,
  eyeOff:  `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`,
  eye:     `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
};

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  sidebarOpen: true,
  phrasesOpen: true,
  activeLesson: null,
  activeEl: null,

  // Phrases
  raw: [],
  rows: [],
  filtered: [],
  hidden: new Set(),
  showHidden: false,
  page: 1,
  pageSize: 20,
  studyIdx: 0,
  studyMode: false,
  chapterOptions: [],
  sectionOptions: [],

  // TTS
  ttsAudio: null,
  ttsPlaying: false,
};

const PAGE_SIZE = 20;

// ── Helpers ───────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const el = (tag, cls, inner = '') => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (inner) e.innerHTML = inner;
  return e;
};

function pretty(str) {
  return str.replace(/^\d+_/, '').replaceAll('_', ' ');
}
function sanitize(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).catch(() => {});
}
function flashCheck(btn) {
  btn.innerHTML = SVG.check;
  btn.style.color = 'var(--accent)';
  setTimeout(() => { btn.innerHTML = SVG.copy; btn.style.color = ''; }, 1200);
}

function hideKey(r) {
  return `${r.chapter}||${r.section}||${r.en}||${r.canto}`;
}

const HIDDEN_LS_KEY = 'cmb_hidden_cards';
function saveHiddenToLocal() {
  try { localStorage.setItem(HIDDEN_LS_KEY, JSON.stringify([...state.hidden])); } catch (_) {}
}
function loadHiddenFromLocal() {
  try {
    const raw = localStorage.getItem(HIDDEN_LS_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch (_) { return new Set(); }
}

// ── TTS helpers ───────────────────────────────────────────────────────────────
const VOICE_MAP = {
  'zh-HK': { female: 'zh-HK-HiuMaanNeural', male: 'zh-HK-WanLungNeural'  },
  'zh-CN': { female: 'zh-CN-XiaoxiaoNeural', male: 'zh-CN-YunyangNeural'  },
};

// Mandarin voices use OpenAI TTS; everything else uses Edge TTS
function engineFor(voice) {
  return voice.startsWith('zh-CN') ? 'openai' : 'edge';
}

function voiceFor(lang) {
  const locale = (lang === 'canto') ? 'zh-HK' : (lang === 'mando') ? 'zh-CN' : lang;
  const gender = document.querySelector('input[name="ttsGender"]:checked')?.value || 'female';
  return VOICE_MAP[locale]?.[gender] || 'zh-HK-HiuMaanNeural';
}

function currentTTSVoice() {
  const lang = document.querySelector('input[name="ttsLang"]:checked')?.value || 'zh-HK';
  return voiceFor(lang);
}

function speedFor(lang) {
  const locale = (lang === 'mando') ? 'zh-CN' : (lang === 'canto') ? 'zh-HK' : lang;
  if (locale !== 'zh-CN') return 'normal';
  // Mandarin uses OpenAI TTS; female plays better slightly slow
  const gender = document.querySelector('input[name="ttsGender"]:checked')?.value || 'female';
  return gender === 'male' ? 'normal' : 'slow';
}

function setTTSSpeed(speed) {
  const radio = document.querySelector(`input[name="ttsSpeed"][value="${speed}"]`);
  if (radio) radio.checked = true;
  const sel = $('ttsSpeed');
  if (sel && sel.tagName === 'SELECT') sel.value = speed;
}

// ── TTS Module ────────────────────────────────────────────────────────────────
const TTS = {
  async speak(text, voice, btn) {
    if (!text || text === '-') return;
    const speed     = $('ttsSpeed')?.value  || 'normal';
    const usedVoice = voice || currentTTSVoice();
    const engine    = engineFor(usedVoice);
    console.log('[TTS] speak →', { text, usedVoice, speed, engine });

    if (btn) { btn.innerHTML = SVG.loader; btn.classList.add('act-btn--loading'); }

    try {
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: usedVoice, speed, engine }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.volume = parseFloat($('ttsVolume')?.value ?? 1);
      audio.play();
    } catch (e) {
      console.warn('TTS error:', e);
    } finally {
      if (btn) { btn.innerHTML = SVG.speaker; btn.classList.remove('act-btn--loading'); }
    }
  },

};

// ── Course Module ─────────────────────────────────────────────────────────────
const Course = {
  async load() {
    try {
      const res = await fetch('/api/structure');
      const chapters = await res.json();
      this.render(chapters);
    } catch (e) {
      console.error('Failed to load course structure', e);
    }
  },

  render(chapters) {
    const list = $('sidebarList');
    list.innerHTML = '';

    // ── Cheat Sheet static entry ──
    const csIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`;
    const csItem = el('div', 'cs-sidebar-item');
    csItem.innerHTML = `<span class="cs-sidebar-icon">${csIcon}</span><span class="cs-sidebar-label">Cheat Sheet</span><span class="cs-sidebar-pill">Reference</span>`;
    csItem.title = 'Canto → Mando Cheat Sheet';
    CheatSheet._activeSidebarEl = csItem;
    csItem.addEventListener('click', () => CheatSheet.show());
    list.appendChild(csItem);

    const sep = el('div', 'sidebar-sep');
    list.appendChild(sep);

    const GROUP_MAP = [
      { key: 'cm1_Intro',        label: 'Intro' },
      { key: 'cm2_Basic',        label: 'Beginner' },
      { key: 'cm3_Intermediate', label: 'Intermediate' },
      { key: 'cm4_Advanced',     label: 'Advanced' },
    ];

    const buckets = {};
    const ungrouped = [];
    for (const ch of chapters) {
      const match = GROUP_MAP.find(g => ch.rel.includes('/' + g.key + '/'));
      if (match) {
        (buckets[match.key] = buckets[match.key] || []).push(ch);
      } else {
        ungrouped.push(ch);
      }
    }

    for (const g of GROUP_MAP) {
      if (buckets[g.key]) list.appendChild(this.groupEl(g.label, buckets[g.key]));
    }
    for (const ch of ungrouped) {
      const groupLabel = ch.name === 'Confident Cantonese Kickstarter' ? 'Confident Cantonese' : pretty(ch.name);
      list.appendChild(this.standaloneGroupEl(ch, groupLabel));
    }

    // Populate chapter filter in phrases
    Phrases.populateChapterFilter(chapters);

    // Restore last-viewed lesson
    const lastRel = localStorage.getItem('lastLesson');
    if (lastRel) {
      const item = list.querySelector(`[data-rel="${CSS.escape(lastRel)}"]`);
      if (item) {
        // Open every ancestor accordion body
        let p = item.parentElement;
        while (p && p !== list) {
          if (p.classList.contains('group-body') ||
              p.classList.contains('ch-body') ||
              p.classList.contains('sec-body')) {
            p.classList.add('open');
            const title = p.previousElementSibling;
            if (title) title.classList.add('open');
          }
          p = p.parentElement;
        }
        item.scrollIntoView({ block: 'nearest' });
        item.click();
      }
    }
  },

  groupEl(label, chapters) {
    const wrap  = el('div', 'group-item');
    const title = el('div', 'group-title');
    title.innerHTML = `<span class="group-label">${sanitize(label)}</span><span class="group-chevron">${SVG.chevron}</span>`;
    const body  = el('div', 'group-body');
    for (const ch of chapters) body.appendChild(this.chapterEl(ch));
    title.addEventListener('click', () => {
      const open = title.classList.toggle('open');
      body.classList.toggle('open', open);
    });
    wrap.appendChild(title);
    wrap.appendChild(body);
    return wrap;
  },

  // Like groupEl but expands directly into the chapter's sections (no extra chapter level)
  standaloneGroupEl(ch, label) {
    const wrap  = el('div', 'group-item');
    const title = el('div', 'group-title');
    title.innerHTML = `<span class="group-label">${sanitize(label)}</span><span class="group-chevron">${SVG.chevron}</span>`;
    const body  = el('div', 'group-body');
    if (ch.files.video || ch.files.pdfs.length) {
      body.appendChild(this.lessonItem(ch, label, label, ''));
    }
    for (const sec of ch.children) body.appendChild(this.sectionEl(sec, label));
    title.addEventListener('click', () => {
      const open = title.classList.toggle('open');
      body.classList.toggle('open', open);
    });
    wrap.appendChild(title);
    wrap.appendChild(body);
    return wrap;
  },

  chapterEl(ch) {
    // Chapter label — strip leading Chapter_XX_ pattern for badge number
    const numMatch = ch.name.match(/Chapter_(\d+)/i);
    const num = numMatch ? numMatch[1] : '';
    const label = pretty(ch.name);

    const wrap  = el('div', 'ch-item');
    const title = el('div', 'ch-title');
    title.innerHTML = `
      ${num ? `<span class="ch-num">${num}</span>` : ''}
      <span class="ch-name">${sanitize(label)}</span>
      <span class="ch-chevron">${SVG.chevron}</span>
    `;
    const body = el('div', 'ch-body');

    // Attach files at chapter level?
    const hasOwnContent = ch.files.video || ch.files.pdfs.length;
    if (hasOwnContent) {
      const item = this.lessonItem(ch, label, label, '');
      body.appendChild(item);
    }

    // Section children
    for (const sec of ch.children) {
      body.appendChild(this.sectionEl(sec, label));
    }

    title.addEventListener('click', () => {
      const open = title.classList.toggle('open');
      body.classList.toggle('open', open);
      // Always filter phrases to this chapter when clicking
      Phrases.syncToChapter(label);
    });

    wrap.appendChild(title);
    wrap.appendChild(body);
    return wrap;
  },

  sectionEl(sec, chLabel) {
    const label = pretty(sec.name);
    const wrap  = el('div', 'sec-item');
    const title = el('div', 'sec-title');
    title.innerHTML = `<span>${sanitize(label)}</span><span class="sec-chevron">${SVG.chevron}</span>`;
    const body = el('div', 'sec-body');

    // Section-level files (if any)
    if (sec.files.video || sec.files.pdfs.length) {
      body.appendChild(this.lessonItem(sec, chLabel, label, ''));
    }

    // Lesson children
    for (const lesson of sec.children) {
      body.appendChild(this.lessonItem(lesson, chLabel, label, lesson.name));
    }

    title.addEventListener('click', () => {
      const open = title.classList.toggle('open');
      body.classList.toggle('open', open);
    });

    wrap.appendChild(title);
    wrap.appendChild(body);
    return wrap;
  },

  lessonItem(node, chLabel, secLabel, lessonName) {
    const hasVideo = !!node.files.video;
    const hasPdf   = node.files.pdfs.length > 0;
    const icon     = hasVideo ? SVG.video : hasPdf ? SVG.pdf : '·';
    const label    = lessonName ? pretty(lessonName) : (secLabel || chLabel);

    const item = el('div', 'lesson-item');
    item.innerHTML = `<span class="lesson-icon">${icon}</span><span class="lesson-label">${sanitize(label)}</span>`;
    item.title = label;
    item.dataset.rel = node.rel;

    item.addEventListener('click', e => {
      e.stopPropagation();
      this.activate(item);
      this.show(node, [chLabel, secLabel, label].filter(Boolean));
      localStorage.setItem('lastLesson', node.rel);
      // Mirror to phrases filter — sync to the specific section
      Phrases.syncToSection(chLabel, secLabel);
    });

    return item;
  },

  activate(el) {
    if (state.activeEl) state.activeEl.classList.remove('active');
    el.classList.add('active');
    state.activeEl = el;
  },

  show(node, breadcrumb) {
    state.activeLesson = node;
    const content = $('courseContent');
    content.innerHTML = '';

    // -- Breadcrumb
    const bc = document.createElement('div');
    bc.className = 'breadcrumb';
    bc.innerHTML = breadcrumb.map((b, i) =>
      `<span class="breadcrumb-item">${sanitize(b)}</span>${i < breadcrumb.length - 1 ? `<span class="breadcrumb-sep">›</span>` : ''}`
    ).join('');
    content.appendChild(bc);

    // -- Video
    if (node.files.video) {
      const wrap = el('div', 'video-wrap');
      wrap.innerHTML = `<video controls playsinline src="/file/${encodeURI(node.files.video)}"></video>`;
      content.appendChild(wrap);
    }

    // -- Notes pane (always shown)
    {
      const noteWrap = el('div', 'notes-wrap');
      noteWrap.innerHTML = `
        <div class="notes-toolbar">
          <span class="notes-label">Notes</span>
        </div>
        <textarea class="notes-area" rows="5" placeholder="Type your notes here…"
          spellcheck="false" autocorrect="off" autocapitalize="off"></textarea>
      `;

      // Persist notes per lesson — use node.rel as stable key
      const noteKey = 'note:' + node.rel;
      const ta = noteWrap.querySelector('.notes-area');
      // Load from localStorage immediately, then sync from server
      ta.value = localStorage.getItem(noteKey) || '';
      fetch('/api/notes')
        .then(r => r.json())
        .then(all => {
          if (all[noteKey] !== undefined) {
            ta.value = all[noteKey];
            localStorage.setItem(noteKey, all[noteKey]);
          }
        })
        .catch(() => {});
      let _noteTimer;
      ta.addEventListener('input', () => {
        localStorage.setItem(noteKey, ta.value);
        clearTimeout(_noteTimer);
        _noteTimer = setTimeout(() => {
          fetch('/api/notes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: noteKey, text: ta.value }),
          }).catch(() => {});
        }, 600);
      });
      content.appendChild(noteWrap);
    }

    // -- Listening audio
    if (node.files.audio) {
      const audioSec = el('div', 'files-section');
      audioSec.innerHTML = `
        <p class="files-heading">Listening Audio</p>
        <audio controls style="width:100%;margin-top:6px">
          <source src="/file/${encodeURI(node.files.audio)}" type="audio/mpeg">
        </audio>`;
      content.appendChild(audioSec);
    }

    // -- PDFs
    if (node.files.pdfs.length) {
      const sec = el('div', 'files-section');
      sec.innerHTML = `<p class="files-heading">Documents</p><div class="file-links"></div>`;
      const links = sec.querySelector('.file-links');
      for (const pdf of node.files.pdfs) {
        const name = pdf.split('/').pop().replace('.pdf', '').replaceAll('_', ' ');
        const a = document.createElement('a');
        a.className = 'file-link';
        a.href = `/file/${encodeURI(pdf)}`;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.innerHTML = `${SVG.pdf} ${sanitize(name)}`;
        links.appendChild(a);
      }
      content.appendChild(sec);
    }

    // -- Readme / notes
    if (node.files.readme) {
      fetch(`/file/${encodeURI(node.files.readme)}`)
        .then(r => r.text())
        .then(md => {
          const div = el('div', 'readme-body');
          div.innerHTML = this.markdownToHtml(md);
          content.appendChild(div);
        })
        .catch(() => {});
    }

    // -- Empty fallback
    if (!node.files.video && !node.files.pdfs.length && !node.files.readme) {
      const msg = el('div', 'empty-state');
      msg.innerHTML = `<p style="margin-top:40px;color:var(--ink-3)">No media files found for this lesson.</p>`;
      content.appendChild(msg);
    }
  },

  markdownToHtml(md) {
    // Minimal markdown: headings, bold, italic, links, lists, line breaks
    return md
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/^(?!<[hul])/, '<p>')
      .replace(/$(?!<\/[hul])/, '</p>');
  },
};

// ── Phrases Module ────────────────────────────────────────────────────────────
const Phrases = {
  async load() {
    try {
      const res = await fetch('/api/curriculum');
      const data = await res.json();
      state.raw  = data;
      state.rows = this.flatten(data);

      // Load hidden list from localStorage + server, merge both
      state.hidden = loadHiddenFromLocal();
      try {
        const hRes = await fetch('/api/hidden');
        if (hRes.ok) {
          const hData = await hRes.json();
          for (const k of (hData.keys || [])) state.hidden.add(k);
        }
      } catch (_) { /* hidden API unavailable — keep localStorage set */ }
      saveHiddenToLocal();

      this.populateFilters();
      this.filter();
      this.render();
      this.updateHiddenBtn();
      // Update panel stats
      const qs = $('quickStats');
      if (qs) qs.textContent = `${state.rows.length.toLocaleString()} entries`;
    } catch (e) {
      console.error('Failed to load curriculum', e);
    }
  },

  flatten(data) {
    // JSON shape: { "Chapter_XX_...": { "NN_Lesson_...": { "NN_Section_...": { "words"|"sentences"|"vocabulary": [...] } } } }
    const rows = [];
    let id = 0;

    const addItems = (items, type, chapter, section, chNum, lessonNum, lessonLabel) => {
      for (const item of items) {
        if (!item || typeof item !== 'object') continue;
        rows.push({
          id: id++,
          type,
          chapter,
          section,
          chNum,
          lessonNum,
          lessonLabel,
          en:       item.en       || item.english   || '',
          canto:    item.canto    || item.cantonese  || '',
          mando:    item.mando    || item.mandarin   || '',
          jyutping: item.jyutping || '',
          pinyin:   item.pinyin   || '',
        });
      }
    };

    for (const [chKey, chVal] of Object.entries(data)) {
      const chapter = pretty(chKey);
      const chNum   = parseInt(chKey.match(/Chapter_(\d+)/i)?.[1] || '0', 10);
      if (!chVal || typeof chVal !== 'object') continue;

      for (const [lessonKey, lessonVal] of Object.entries(chVal)) {
        const lessonNum = parseInt(lessonKey.match(/Lesson_(\d+)/i)?.[1] || lessonKey.match(/^(\d+)/)?.[1] || '0', 10);
        const cmMatch   = lessonKey.match(/^\d+_CM_SCHOOL_(.+)$/i);
        const lessonLabel = cmMatch
          ? cmMatch[1].replace(/_/g, ' ')
          : `L${String(lessonNum).padStart(2, '0')}`;
        if (!lessonVal || typeof lessonVal !== 'object') continue;

        for (const [secKey, secVal] of Object.entries(lessonVal)) {
          const section = pretty(lessonKey) + ' › ' + pretty(secKey);
          if (!secVal || typeof secVal !== 'object') continue;

          if (Array.isArray(secVal.words))      addItems(secVal.words,      'vocabulary', chapter, section, chNum, lessonNum, lessonLabel);
          if (Array.isArray(secVal.vocabulary)) addItems(secVal.vocabulary, 'vocabulary', chapter, section, chNum, lessonNum, lessonLabel);
          if (Array.isArray(secVal.sentences))  addItems(secVal.sentences,  'sentence',   chapter, section, chNum, lessonNum, lessonLabel);
        }
      }
    }
    return rows;
  },

  populateFilters() {
    const chapters = [...new Set(state.rows.map(r => r.chapter))].sort();
    state.chapterOptions = chapters;

    const chSel = $('chapterFilter');
    chapters.forEach(c => {
      const o = document.createElement('option');
      o.value = c; o.textContent = c;
      chSel.appendChild(o);
    });

    // Section dropdown starts with just "All sections" — updated dynamically
    this.updateSectionFilter();
  },

  updateSectionFilter() {
    const chapter = $('chapterFilter').value;
    const secSel  = $('sectionFilter');
    const prev    = secSel.value;  // preserve current selection if still valid

    // Sections relevant to current chapter filter
    const rows = chapter === 'all'
      ? state.rows
      : state.rows.filter(r => r.chapter === chapter);

    // Sections in curriculum order (first-seen = course map order), not alphabetical
    const seen = new Set();
    const sections = [];
    for (const r of rows) {
      if (r.section && !seen.has(r.section)) {
        seen.add(r.section);
        sections.push(r.section);
      }
    }

    secSel.innerHTML = '<option value="all">All sections</option>';
    sections.forEach(s => {
      const o = document.createElement('option');
      o.value = s;
      o.textContent = s;
      secSel.appendChild(o);
    });

    // Restore previous selection only if it still exists
    if (prev !== 'all' && sections.includes(prev)) secSel.value = prev;
    else secSel.value = 'all';
  },

  populateChapterFilter(chapters) {
    // Called by Course.render after structure is loaded
    // Chapters from course tree might differ slightly from curriculum — skip if already populated
    if (state.chapterOptions.length) return;
    const chSel = $('chapterFilter');
    for (const ch of chapters) {
      const label = ch.label || pretty(ch.name);
      // Only add if not already present
      if (![...chSel.options].some(o => o.value === label)) {
        const o = document.createElement('option');
        o.value = label; o.textContent = label;
        chSel.appendChild(o);
      }
    }
  },

  filterToChapter(chapterLabel) {
    // Filter phrases panel to this chapter
    const chSel = $('chapterFilter');
    const match = [...chSel.options].find(o =>
      o.value.toLowerCase().includes(chapterLabel.toLowerCase().replace(/chapter_?\d+_?/i, '').trim().slice(0, 20))
      || chapterLabel.toLowerCase().includes(o.value.toLowerCase().slice(0, 20))
    );
    if (match) chSel.value = match.value;
    this.updateSectionFilter();
    this.filter();
    this.render();
  },

  syncToChapter(chapterLabel) {
    // Same as filterToChapter — always filter the phrases panel
    this.filterToChapter(chapterLabel);
  },

  syncToSection(chapterLabel, sectionPrefix) {
    // Filter to chapter first (populates section options)
    this.filterToChapter(chapterLabel);
    // Then narrow section to the first option matching the prefix
    if (sectionPrefix) {
      const secSel = $('sectionFilter');
      const prefix = sectionPrefix.toLowerCase();
      const match = [...secSel.options].find(o =>
        o.value !== 'all' && o.value.toLowerCase().startsWith(prefix)
      );
      if (match) {
        secSel.value = match.value;
        this.filter();
        this.render();
      }
    }
    // Scroll phrases result list to top
    const list = $('resultList');
    if (list) list.scrollTop = 0;
  },

  filter() {
    const q       = ($('searchInput').value || '').toLowerCase().trim();
    const type    = $('typeFilter').value;
    const chapter = $('chapterFilter').value;
    const section = $('sectionFilter').value;
    const script  = $('scriptMode').value;

    state.filtered = state.rows.filter(r => {
      const isHidden = state.hidden.has(hideKey(r));
      if (state.showHidden ? !isHidden : isHidden) return false;
      if (type !== 'all' && r.type !== type) return false;
      if (chapter !== 'all' && r.chapter !== chapter) return false;
      if (section !== 'all' && r.section !== section) return false;
      if (script === 'canto' && !r.canto) return false;
      if (script === 'mando' && !r.mando) return false;
      if (q) {
        const haystack = `${r.en} ${r.canto} ${r.mando} ${r.jyutping} ${r.pinyin}`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });

    state.page = 1;
    const label = state.showHidden ? 'hidden' : 'results';
    $('resultCount').textContent = `${state.filtered.length.toLocaleString()} ${label}`;
  },

  render() {
    const list  = $('resultList');
    const start = (state.page - 1) * PAGE_SIZE;
    const slice = state.filtered.slice(start, start + PAGE_SIZE);
    list.innerHTML = '';

    if (slice.length === 0) {
      list.innerHTML = `<p class="muted-sm" style="padding:20px 0;text-align:center">No results found. Try adjusting filters.</p>`;
    } else {
      for (const row of slice) {
        const card = row.type === 'sentence' ? this.sentenceCard(row) : this.vocabCard(row);
        if (state.showHidden) card.classList.add('is-hidden');
        list.appendChild(card);
      }
    }

    // Pager
    const total = state.filtered.length;
    const pages = Math.ceil(total / PAGE_SIZE);
    $('pageInfo').textContent = pages > 1 ? `Page ${state.page} of ${pages}` : '';
    $('prevPage').disabled = state.page <= 1;
    $('nextPage').disabled = state.page >= pages;
  },

  vocabCard(r) {
    const card = el('div', 'result-card');
    const noEn    = !r.en    || r.en    === '-';
    const noCanto = !r.canto || r.canto === '-';
    const noMando = !r.mando || r.mando === '-';

    card.innerHTML = `
      <div class="vocab-3col">
        <div class="vocab-col">
          <div class="vocab-label">English</div>
          <div class="vocab-en">${sanitize(r.en || '—')}</div>
        </div>
        <div class="vocab-col">
          <div class="vocab-label" style="color:var(--mando-clr)">Mandarin</div>
          <div class="vocab-han mando">${sanitize(r.mando || '—')}</div>
          <div class="vocab-roman">${sanitize(r.pinyin || '')}</div>
          <div class="vocab-actions">
            <button class="act-btn" data-action="speak" data-text="${sanitize(r.mando)}" data-voice="zh-CN" title="Play Mandarin" ${noMando ? 'disabled' : ''}>${SVG.speaker}</button>
            <button class="act-btn" data-action="copy" data-copy="${sanitize(r.mando)}" title="Copy" ${noMando ? 'disabled' : ''}>${SVG.copy}</button>
          </div>
        </div>
        <div class="vocab-col">
          <div class="vocab-label" style="color:var(--canto-clr)">Cantonese</div>
          <div class="vocab-han canto">${sanitize(r.canto || '—')}</div>
          <div class="vocab-roman">${sanitize(r.jyutping || '')}</div>
          <div class="vocab-actions">
            <button class="act-btn" data-action="speak" data-text="${sanitize(r.canto)}" data-voice="zh-HK" title="Play Cantonese" ${noCanto ? 'disabled' : ''}>${SVG.speaker}</button>
            <button class="act-btn" data-action="copy" data-copy="${sanitize(r.canto)}" title="Copy" ${noCanto ? 'disabled' : ''}>${SVG.copy}</button>
          </div>
        </div>
      </div>
      <div class="card-footer">
        ${r.chNum ? `<span class="card-badge">Ch${r.chNum} ${r.lessonLabel}</span>` : '<span></span>'}
        <button class="act-btn card-hide-btn" data-action="${state.showHidden ? 'unhide' : 'hide'}" data-hkey="${encodeURIComponent(hideKey(r))}" title="${state.showHidden ? 'Unhide card' : 'Hide card'}">${state.showHidden ? SVG.eye : SVG.eyeOff}</button>
      </div>
    `;
    return card;
  },

  sentenceCard(r) {
    const card = el('div', 'result-card sent-card');
    const noEn    = !r.en    || r.en    === '-';
    const noCanto = !r.canto || r.canto === '-';
    const noMando = !r.mando || r.mando === '-';

    card.innerHTML = `
      <div class="sent-en-label">English</div>
      <div class="sent-en">${sanitize(r.en || '—')}</div>
      <div class="sent-row">
        <div class="vocab-label" style="color:var(--mando-clr)">Mandarin</div>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="vocab-han mando">${sanitize(r.mando || '—')}</span>
          <div class="vocab-actions">
            <button class="act-btn" data-action="speak" data-text="${sanitize(r.mando)}" data-voice="zh-CN" title="Play" ${noMando ? 'disabled' : ''}>${SVG.speaker}</button>
            <button class="act-btn" data-action="copy" data-copy="${sanitize(r.mando)}" title="Copy" ${noMando ? 'disabled' : ''}>${SVG.copy}</button>
          </div>
        </div>
        ${r.pinyin ? `<div class="vocab-roman">${sanitize(r.pinyin)}</div>` : ''}
      </div>
      <div class="sent-row">
        <div class="vocab-label" style="color:var(--canto-clr)">Cantonese</div>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="vocab-han canto">${sanitize(r.canto || '—')}</span>
          <div class="vocab-actions">
            <button class="act-btn" data-action="speak" data-text="${sanitize(r.canto)}" data-voice="zh-HK" title="Play" ${noCanto ? 'disabled' : ''}>${SVG.speaker}</button>
            <button class="act-btn" data-action="copy" data-copy="${sanitize(r.canto)}" title="Copy" ${noCanto ? 'disabled' : ''}>${SVG.copy}</button>
          </div>
        </div>
        ${r.jyutping ? `<div class="vocab-roman">${sanitize(r.jyutping)}</div>` : ''}
      </div>
      <div class="card-footer">
        ${r.chNum ? `<span class="card-badge">Ch${r.chNum} ${r.lessonLabel}</span>` : '<span></span>'}
        <button class="act-btn card-hide-btn" data-action="${state.showHidden ? 'unhide' : 'hide'}" data-hkey="${encodeURIComponent(hideKey(r))}" title="${state.showHidden ? 'Unhide card' : 'Hide card'}">${state.showHidden ? SVG.eye : SVG.eyeOff}</button>
      </div>
    `;
    return card;
  },

  updateHiddenBtn() {
    const btn   = $('hiddenBtn');
    const count = state.hidden.size;
    if (state.showHidden) {
      btn.textContent = `← Show active`;
      btn.classList.add('active');
    } else {
      btn.textContent = count > 0 ? `Hidden (${count})` : 'Hidden';
      btn.classList.remove('active');
    }
  },

  // Study mode
  showStudy() {
    state.studyMode = true;
    state.studyIdx  = 0;
    $('studyModalOverlay').classList.add('open');
    $('studyBtn').textContent = 'Exit study';
    this.renderStudyCard();
  },

  exitStudy() {
    state.studyMode = false;
    $('studyModalOverlay').classList.remove('open');
    $('studyBtn').textContent = 'Study mode';
  },

  renderStudyCard() {
    const rows = state.filtered;
    if (!rows.length) return;
    const r = rows[state.studyIdx % rows.length];
    $('studyEnglish').textContent   = r.en || '—';
    $('studyCanto').textContent     = r.canto || '—';
    $('studyMando').textContent     = r.mando || '—';
    $('studyJyutping').textContent  = r.jyutping || '';
    $('studyPinyin').textContent    = r.pinyin || '';
    $('studyReveal').style.display  = 'none';
    $('revealBtn').style.display    = '';
    $('studyMeta').textContent      = `${state.studyIdx + 1} / ${rows.length} · ${r.chapter}`;
  },

  attachEvents() {
    // Result list: speak + copy delegation
    $('resultList').addEventListener('click', e => {
      const btn = e.target.closest('.act-btn');
      if (!btn) return;
      const action = btn.dataset.action;
      if (action === 'copy') {
        copyToClipboard(btn.dataset.copy || '');
        flashCheck(btn);
      } else if (action === 'speak') {
        setTTSSpeed(speedFor(btn.dataset.voice));
        TTS.speak(btn.dataset.text, voiceFor(btn.dataset.voice), btn);
      } else if (action === 'hide' || action === 'unhide') {
        const key    = decodeURIComponent(btn.dataset.hkey);
        const hiding = action === 'hide';
        if (hiding) state.hidden.add(key); else state.hidden.delete(key);
        saveHiddenToLocal();
        fetch('/api/hidden', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, hidden: hiding }),
        }).catch(() => {});
        this.filter();
        this.render();
        this.updateHiddenBtn();
      }
    });

    // Filters
    ['searchInput','typeFilter','scriptMode'].forEach(id => {
      $(id).addEventListener('input',  () => { this.filter(); this.render(); });
      $(id).addEventListener('change', () => { this.filter(); this.render(); });
    });
    $('chapterFilter').addEventListener('change', () => {
      this.updateSectionFilter();
      this.filter();
      this.render();
    });
    $('sectionFilter').addEventListener('change', () => { this.filter(); this.render(); });

    $('resetBtn').addEventListener('click', () => {
      $('searchInput').value = '';
      $('typeFilter').value  = 'all';
      $('chapterFilter').value = 'all';
      $('scriptMode').value  = 'both';
      state.showHidden = false;
      this.updateSectionFilter();
      this.filter();
      this.render();
      this.updateHiddenBtn();
    });

    $('studyBtn').addEventListener('click', () => {
      if (state.studyMode) this.exitStudy();
      else this.showStudy();
    });

    $('hiddenBtn').addEventListener('click', () => {
      state.showHidden = !state.showHidden;
      this.filter();
      this.render();
      this.updateHiddenBtn();
    });

    $('prevPage').addEventListener('click', () => { state.page--; this.render(); });
    $('nextPage').addEventListener('click', () => { state.page++; this.render(); });

    // Study panel
    $('revealBtn').addEventListener('click', () => {
      $('studyReveal').style.display = '';
      $('revealBtn').style.display   = 'none';
    });
    $('studyPrev').addEventListener('click', () => {
      state.studyIdx = Math.max(0, state.studyIdx - 1);
      this.renderStudyCard();
    });
    $('studyNext').addEventListener('click', () => {
      state.studyIdx = Math.min(state.filtered.length - 1, state.studyIdx + 1);
      this.renderStudyCard();
    });
    $('studyCloseBtn').addEventListener('click', () => this.exitStudy());
    $('studyModalOverlay').addEventListener('click', e => {
      if (e.target === $('studyModalOverlay')) this.exitStudy();
    });

    // Keyboard shortcuts (always active when not in input)
    document.addEventListener('keydown', e => {
      if (e.target.matches('input,textarea,select')) return;
      if (e.key === '/' ) { e.preventDefault(); $('searchInput').focus(); }
      if (e.key === 'Escape' && state.studyMode) { this.exitStudy(); return; }
      if (e.key === 'n') { state.page++; this.render(); }
      if (e.key === 'p') { if (state.page > 1) { state.page--; this.render(); } }
      if (state.studyMode) {
        if (e.key === 'j' || e.key === 'ArrowRight') {
          state.studyIdx = Math.min(state.filtered.length - 1, state.studyIdx + 1);
          this.renderStudyCard();
        }
        if (e.key === 'k' || e.key === 'ArrowLeft') {
          state.studyIdx = Math.max(0, state.studyIdx - 1);
          this.renderStudyCard();
        }
        if (e.key === ' ') {
          e.preventDefault();
          $('revealBtn').click();
        }
      }
    });
  },
};

// ── UI Module ─────────────────────────────────────────────────────────────────
const UI = {
  initTheme() {
    const saved = localStorage.getItem('cmb-theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    this.updateThemeIcon(saved);

    $('themeToggle').addEventListener('click', () => {
      const cur  = document.documentElement.getAttribute('data-theme') || 'light';
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('cmb-theme', next);
      this.updateThemeIcon(next);
    });

    $('killServerBtn').addEventListener('click', async () => {
      if (!confirm('Stop the server?')) return;
      await fetch('/api/shutdown', { method: 'POST' }).catch(() => {});
      document.body.innerHTML = '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;gap:12px"><h2>Server stopped</h2><p>You can close this tab.</p></div>';
    });
  },

  updateThemeIcon(theme) {
    $('themeIconMoon').style.display = theme === 'dark' ? 'none' : '';
    $('themeIconSun').style.display  = theme === 'dark' ? '' : 'none';
  },

  initSidebar() {
    const sidebar = $('courseSidebar');
    const toggle  = $('sidebarToggle');
    const saved   = localStorage.getItem('cmb-sidebar');
    if (saved === 'closed') { sidebar.classList.add('collapsed'); state.sidebarOpen = false; }

    toggle.addEventListener('click', () => {
      state.sidebarOpen = !state.sidebarOpen;
      sidebar.classList.toggle('collapsed', !state.sidebarOpen);
      localStorage.setItem('cmb-sidebar', state.sidebarOpen ? 'open' : 'closed');
    });
  },

  initPhrasesPanel() {
    const panel  = $('phrasesPanel');
    const toggle = $('phrasesToggle');
    const saved  = localStorage.getItem('cmb-phrases');
    if (saved === 'closed') { panel.classList.add('collapsed'); state.phrasesOpen = false; }
    toggle.classList.toggle('active', state.phrasesOpen);

    toggle.addEventListener('click', () => {
      state.phrasesOpen = !state.phrasesOpen;
      panel.classList.toggle('collapsed', !state.phrasesOpen);
      toggle.classList.toggle('active', state.phrasesOpen);
      localStorage.setItem('cmb-phrases', state.phrasesOpen ? 'open' : 'closed');
    });
  },

  initResize() {
    this._initResizeHandle($('sidebarResize'), $('courseSidebar'), 'left', '--sidebar-w', 160, 520);
    this._initResizeHandle($('phrasesResize'), $('phrasesPanel'),  'right', '--phrases-w', 280, 700);
  },

  _initResizeHandle(handle, panel, direction, cssVar, min, max) {
    let dragging = false, startX = 0, startW = 0;

    handle.addEventListener('mousedown', e => {
      dragging = true;
      startX   = e.clientX;
      startW   = panel.offsetWidth;
      handle.classList.add('dragging');
      document.body.style.cursor    = 'col-resize';
      document.body.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      const delta = direction === 'left'
        ? e.clientX - startX
        : startX - e.clientX;
      const w = Math.max(min, Math.min(max, startW + delta));
      panel.style.width    = `${w}px`;
      panel.style.minWidth = `${w}px`;
      if (cssVar) document.documentElement.style.setProperty(cssVar, `${w}px`);
    });
    document.addEventListener('mouseup', () => {
      if (dragging) {
        dragging = false;
        handle.classList.remove('dragging');
        document.body.style.cursor    = '';
        document.body.style.userSelect = '';
      }
    });
  },
};

// ── Cheat Sheet Module ────────────────────────────────────────────────────────
const CheatSheet = {
  DATA: [
    {
      num: '①', title: 'Pronouns & Plural Marker',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '哋→们',     ruleJp: 'dei6',          rulePy: 'men',          canto: '我哋去食飯。',   jp: 'ngo5 dei6 heoi3 sik6 faan6',       mando: '我们去吃饭。',   py: 'wǒmen qù chīfàn',          en: 'We are going to eat.' },
        { rule: '佢→他',     ruleJp: 'keoi5',         rulePy: 'tā',           canto: '佢係我朋友。',   jp: 'keoi5 hai6 ngo5 pang4 jau5',       mando: '他是我朋友。',   py: 'tā shì wǒ péngyǒu',        en: 'He is my friend.' },
        { rule: '佢→她',     ruleJp: 'keoi5',         rulePy: 'tā',           canto: '佢好叻㗎。',     jp: 'keoi5 hou2 lek1 gaa3',             mando: '她很厉害。',     py: 'tā hěn lìhài',             en: 'She is very capable.' },
        { rule: '佢哋→他们', ruleJp: 'keoi5 dei6',    rulePy: 'tāmen',        canto: '佢哋喺邊度？',   jp: 'keoi5 dei6 hai2 bin1 dou6',        mando: '他们在哪里？',   py: 'tāmen zài nǎlǐ',           en: 'Where are they?' },
        { rule: '你哋→你们', ruleJp: 'nei5 dei6',     rulePy: 'nǐmen',        canto: '你哋食咗未？',   jp: 'nei5 dei6 sik6 zo2 mei6',          mando: '你们吃了吗？',   py: 'nǐmen chī le ma',           en: 'Have you all eaten yet?' },
      ],
    },
    {
      num: '②', title: 'Possession 嘅→的',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '嘅→的', ruleJp: 'ge3',   rulePy: 'de',  canto: '呢係我嘅書。',   jp: 'ni1 hai6 ngo5 ge3 syu1',           mando: '这是我的书。',   py: 'zhè shì wǒ de shū',        en: 'This is my book.' },
        { rule: '嘅→的', ruleJp: 'ge3',   rulePy: 'de',  canto: '佢嘅屋企好大。', jp: 'keoi5 ge3 uk1 kei2 hou2 daai6',    mando: '他的家很大。',   py: 'tā de jiā hěn dà',         en: 'His house is very big.' },
        { rule: '哋→地', ruleJp: 'dei6',  rulePy: 'de',  canto: '佢慢慢哋行。',   jp: 'keoi5 maan6 maan6 dei6 haang4',    mando: '他慢慢地走。',   py: 'tā mànmàn de zǒu',         en: 'He walks slowly.' },
      ],
    },
    {
      num: '③', title: 'Negation',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '冇→没有', ruleJp: 'mou5',  rulePy: 'méiyǒu',  canto: '我冇錢。',   jp: 'ngo5 mou5 cin2',                   mando: '我没有钱。',     py: 'wǒ méiyǒu qián',           en: "I don't have money." },
        { rule: '唔→不',   ruleJp: 'm4',    rulePy: 'bù',      canto: '我唔知。',   jp: 'ngo5 m4 ji1',                      mando: '我不知道。',     py: 'wǒ bù zhīdào',             en: "I don't know." },
        { rule: '唔→不',   ruleJp: 'm4',    rulePy: 'bù',      canto: '佢唔去。',   jp: 'keoi5 m4 heoi3',                   mando: '他不去。',       py: 'tā bù qù',                 en: "He isn't going." },
        { rule: '未→还没', ruleJp: 'mei6',  rulePy: 'hái méi', canto: '我未食飯。', jp: 'ngo5 mei6 sik6 faan6',             mando: '我还没吃饭。',   py: 'wǒ hái méi chīfàn',        en: "I haven't eaten yet." },
      ],
    },
    {
      num: '④', title: '"What" Words 乜嘢/咩→什么',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '乜嘢→什么', ruleJp: 'mat1 je5', rulePy: 'shénme', canto: '你想食乜嘢？', jp: 'nei5 soeng2 sik6 mat1 je5',        mando: '你想吃什么？',   py: 'nǐ xiǎng chī shénme',      en: 'What do you want to eat?' },
        { rule: '乜→什么',   ruleJp: 'mat1',     rulePy: 'shénme', canto: '係乜事？',     jp: 'hai6 mat1 si6',                    mando: '是什么事？',     py: 'shì shénme shì',           en: "What's the matter?" },
        { rule: '咩→什么',   ruleJp: 'me1',      rulePy: 'shénme', canto: '你講咩？',     jp: 'nei5 gong2 me1',                   mando: '你说什么？',     py: 'nǐ shuō shénme',           en: 'What are you saying?' },
      ],
    },
    {
      num: '⑤', title: '"Thing" 嘢→东西',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '嘢→东西', ruleJp: 'je5', rulePy: 'dōngxi', canto: '呢件嘢係咩？', jp: 'ni1 gin6 je5 hai6 me1',            mando: '这个东西是什么？', py: 'zhège dōngxi shì shénme',  en: 'What is this thing?' },
        { rule: '嘢→东西', ruleJp: 'je5', rulePy: 'dōngxi', canto: '你買咗啲嘢？', jp: 'nei5 maai5 zo2 di1 je5',           mando: '你买了什么东西？', py: 'nǐ mǎi le shénme dōngxi', en: 'What things did you buy?' },
      ],
    },
    {
      num: '⑥', title: 'Indicator Words 呢/嗰/邊→这/那/哪',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '呢→这', ruleJp: 'ni1',  rulePy: 'zhè', canto: '呢個人係邊個？', jp: 'ni1 go3 jan4 hai6 bin1 go3',       mando: '这个人是谁？',   py: 'zhège rén shì shéi',       en: 'Who is this person?' },
        { rule: '嗰→那', ruleJp: 'go2',  rulePy: 'nà',  canto: '嗰間舖好正。',   jp: 'go2 gaan1 pou3 hou2 zing3',        mando: '那家店很棒。',   py: 'nà jiā diàn hěn bàng',     en: 'That shop is great.' },
        { rule: '邊→哪', ruleJp: 'bin1', rulePy: 'nǎ',  canto: '邊個係你？',     jp: 'bin1 go3 hai6 nei5',               mando: '哪个是你？',     py: 'nǎge shì nǐ',              en: 'Which one is you?' },
        { rule: '呢→这', ruleJp: 'ni1',  rulePy: 'zhè', canto: '呢件事好難。',   jp: 'ni1 gin6 si6 hou2 naan4',          mando: '这件事很难。',   py: 'zhè jiàn shì hěn nán',     en: 'This matter is hard.' },
      ],
    },
    {
      num: '⑦', title: 'Measure Words 啲→些',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '啲→些', ruleJp: 'di1',    rulePy: 'xiē',   canto: '買啲蘋果啦。', jp: 'maai5 di1 ping4 gwo2 laa1',         mando: '买些苹果吧。',   py: 'mǎi xiē píngguǒ ba',       en: 'Buy some apples.' },
        { rule: '個→个', ruleJp: 'go3',    rulePy: 'gè',    canto: '三個人。',     jp: 'saam1 go3 jan4',                    mando: '三个人。',       py: 'sān gè rén',               en: 'Three people.' },
        { rule: '張→张', ruleJp: 'zoeng1', rulePy: 'zhāng', canto: '一張紙。',     jp: 'jat1 zoeng1 zi2',                   mando: '一张纸。',       py: 'yī zhāng zhǐ',             en: 'One sheet of paper.' },
        { rule: '條→条', ruleJp: 'tiu4',   rulePy: 'tiáo',  canto: '兩條魚。',     jp: 'loeng5 tiu4 jyu2',                  mando: '两条鱼。',       py: 'liǎng tiáo yú',            en: 'Two fish.' },
        { rule: '本→本', ruleJp: 'bun2',   rulePy: 'běn',   canto: '一本書。',     jp: 'jat1 bun2 syu1',                    mando: '一本书。',       py: 'yī běn shū',               en: 'One book.' },
      ],
    },
    {
      num: '⑧', title: 'Location Words',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '喺→在',       ruleJp: 'hai2',          rulePy: 'zài',     canto: '我喺屋企。',   jp: 'ngo5 hai2 uk1 kei2',               mando: '我在家。',       py: 'wǒ zài jiā',               en: 'I am at home.' },
        { rule: '呢度→这里',   ruleJp: 'ni1 dou6',      rulePy: 'zhèlǐ',  canto: '你去呢度。',   jp: 'nei5 heoi3 ni1 dou6',              mando: '你去这里。',     py: 'nǐ qù zhèlǐ',              en: 'You go here.' },
        { rule: '嗰度→那里',   ruleJp: 'go2 dou6',      rulePy: 'nàlǐ',   canto: '佢嗰度等你。', jp: 'keoi5 go2 dou6 dang2 nei5',        mando: '他那里等你。',   py: 'tā nàlǐ děng nǐ',          en: 'He is waiting for you there.' },
        { rule: '邊度→哪里',   ruleJp: 'bin1 dou6',     rulePy: 'nǎlǐ',   canto: '洗手間邊度？', jp: 'sai2 sau2 gaan1 bin1 dou6',        mando: '洗手间哪里？',   py: 'xǐshǒujiān nǎlǐ',          en: 'Where is the bathroom?' },
        { rule: '喺…度→在…里', ruleJp: 'hai2…dou6',     rulePy: 'zài…lǐ', canto: '書喺袋度。',   jp: 'syu1 hai2 doi2 dou6',              mando: '书在袋子里。',   py: 'shū zài dàizi lǐ',         en: 'The book is in the bag.' },
        { rule: '而家→现在',   ruleJp: 'ji4 gaa1',      rulePy: 'xiànzài', canto: '而家幾多點？', jp: 'ji4 gaa1 gei2 do1 dim2',           mando: '现在几点？',     py: 'xiànzài jǐ diǎn',          en: 'What time is it now?' },
      ],
    },
    {
      num: '⑨', title: 'Time Words',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '今日→今天', ruleJp: 'gam1 jat6',  rulePy: 'jīntiān',   canto: '今日天氣好好。', jp: 'gam1 jat6 tin1 hei3 hou2 hou2',    mando: '今天天气很好。',   py: 'jīntiān tiānqì hěn hǎo',   en: 'The weather is great today.' },
        { rule: '噚日→昨天', ruleJp: 'cam4 jat6',  rulePy: 'zuótiān',   canto: '噚日落雨。',     jp: 'cam4 jat6 lok6 jyu5',              mando: '昨天下雨了。',     py: 'zuótiān xià yǔ le',        en: 'It rained yesterday.' },
        { rule: '听日→明天', ruleJp: 'ting1 jat6', rulePy: 'míngtiān',  canto: '听日見。',       jp: 'ting1 jat6 gin3',                  mando: '明天见。',         py: 'míngtiān jiàn',            en: 'See you tomorrow.' },
        { rule: '後日→后天', ruleJp: 'hau6 jat6',  rulePy: 'hòutiān',   canto: '後日先得閒。',   jp: 'hau6 jat6 sin1 dak1 haan4',        mando: '后天才有空。',     py: 'hòutiān cái yǒu kòng',     en: "I'm only free the day after tomorrow." },
        { rule: '成日→整天', ruleJp: 'seng4 jat6', rulePy: 'zhěngtiān', canto: '佢成日咁講。',   jp: 'keoi5 seng4 jat6 gam2 gong2',      mando: '他整天这样说。',   py: 'tā zhěngtiān zhèyàng shuō', en: 'He always says that.' },
      ],
    },
    {
      num: '⑩', title: 'Question Words',
      cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
      rows: [
        { rule: '邊個→谁',       ruleJp: 'bin1 go3',   rulePy: 'shéi',            canto: '呢個係邊個？', jp: 'ni1 go3 hai6 bin1 go3',             mando: '这个是谁？',       py: 'zhège shì shéi',            en: 'Who is this?' },
        { rule: '乜嘢→什么',     ruleJp: 'mat1 je5',   rulePy: 'shénme',          canto: '你做乜嘢工？', jp: 'nei5 zou6 mat1 je5 gung1',          mando: '你做什么工作？',   py: 'nǐ zuò shénme gōngzuò',    en: 'What work do you do?' },
        { rule: '邊度→哪里',     ruleJp: 'bin1 dou6',  rulePy: 'nǎlǐ',           canto: '你住邊度？',   jp: 'nei5 zyu6 bin1 dou6',               mando: '你住哪里？',       py: 'nǐ zhù nǎlǐ',              en: 'Where do you live?' },
        { rule: '幾時→什么时候', ruleJp: 'gei2 si4',   rulePy: 'shénme shíhòu',   canto: '你幾時返嚟？', jp: 'nei5 gei2 si4 faan1 lai4',          mando: '你什么时候回来？', py: 'nǐ shénme shíhòu huílái',  en: 'When will you be back?' },
        { rule: '點解→为什么',   ruleJp: 'dim2 gaai2', rulePy: 'wèishénme',       canto: '點解你唔去？', jp: 'dim2 gaai2 nei5 m4 heoi3',          mando: '为什么你不去？',   py: 'wèishénme nǐ bù qù',       en: "Why aren't you going?" },
        { rule: '點→怎么',       ruleJp: 'dim2',       rulePy: 'zěnme',           canto: '你點知？',     jp: 'nei5 dim2 ji1',                     mando: '你怎么知道？',     py: 'nǐ zěnme zhīdào',          en: 'How do you know?' },
        { rule: '幾多→多少',     ruleJp: 'gei2 do1',   rulePy: 'duōshao',         canto: '要幾多錢？',   jp: 'jiu3 gei2 do1 cin2',                mando: '要多少钱？',       py: 'yào duōshao qián',         en: 'How much does it cost?' },
        { rule: '未→了吗',       ruleJp: 'mei6',       rulePy: 'le ma',           canto: '你食飯未？',   jp: 'nei5 sik6 faan6 mei6',              mando: '你吃饭了吗？',     py: 'nǐ chīfàn le ma',          en: 'Have you eaten?' },
      ],
    },
  ],

  BONUS: [
    { canto: '佢哋去嗰度食乜嘢？', jp: 'keoi5 dei6 heoi3 go2 dou6 sik6 mat1 je5',   mando: '他们去那里吃什么？',     py: 'tāmen qù nàlǐ chī shénme',              en: 'What are they going there to eat?' },
    { canto: '我哋今日冇時間。',   jp: 'ngo5 dei6 gam1 jat6 mou5 si4 gaan3',       mando: '我们今天没有时间。',     py: 'wǒmen jīntiān méiyǒu shíjiān',          en: "We don't have time today." },
    { canto: '呢件嘢係佢嘅。',     jp: 'ni1 gin6 je5 hai6 keoi5 ge3',              mando: '这个东西是他的。',       py: 'zhège dōngxi shì tā de',                en: 'This thing is his.' },
    { canto: '你哋聽日去邊度？',   jp: 'nei5 dei6 ting1 jat6 heoi3 bin1 dou6',     mando: '你们明天去哪里？',       py: 'nǐmen míngtiān qù nǎlǐ',                en: 'Where are you all going tomorrow?' },
    { canto: '佢唔知書喺枱度。',   jp: 'keoi5 m4 ji1 syu1 hai2 toi2 dou6',         mando: '他不知道书在桌子里。',   py: 'tā bù zhīdào shū zài zhuōzi lǐ',        en: "He doesn't know the book is on the table." },
    { canto: '點解你哋噚日冇嚟？', jp: 'dim2 gaai2 nei5 dei6 cam4 jat6 mou5 lai4', mando: '为什么你们昨天没有来？', py: 'wèishénme nǐmen zuótiān méiyǒu lái',    en: "Why didn't you all come yesterday?" },
  ],

  WATCHOUT: [
    { error: '唔 negates verbs/adj, NOT nouns',       wrong: '我唔錢',     correct: '我没有钱 (use 冇/没有)' },
    { error: '喺…度 BOTH parts must convert',          wrong: '在袋度',     correct: '在袋子里 (度→里)' },
    { error: '哋 (plural) vs 哋 (adverbial 地)',        wrong: '我们慢慢们走', correct: '我们慢慢地走' },
    { error: '佢 = he/she/it (context decides char)',   wrong: 'always 他',  correct: '他/她/它 by context' },
  ],

  _activeSidebarEl: null,
  _loaded: null, // cached fetch promise

  async show() {
    if (state.activeEl) state.activeEl.classList.remove('active');
    if (this._activeSidebarEl) {
      this._activeSidebarEl.classList.add('active');
      state.activeEl = this._activeSidebarEl;
    }
    state.activeLesson = null;

    const content = $('courseContent');
    content.innerHTML = '';

    const bc = document.createElement('div');
    bc.className = 'breadcrumb';
    bc.innerHTML = `<span class="breadcrumb-item">Reference</span><span class="breadcrumb-sep">›</span><span class="breadcrumb-item">Cheat Sheet</span>`;
    content.appendChild(bc);

    // Load data from cheat.json (cached after first fetch)
    if (!this._loaded) {
      this._loaded = fetch('/api/cheat').then(r => r.json()).then(data => {
        // Normalise field names from JSON schema → internal schema used by render methods
        this.DATA = data.sections.map(sec => ({
          num: sec.num,
          title: sec.title,
          cols: ['Rule', 'Cantonese', 'Mandarin', 'English'],
          rows: sec.rows.map(r => ({
            rule: r.rule, ruleJp: r.rule_jyutping, rulePy: r.rule_pinyin,
            canto: r.canto, jp: r.jyutping,
            mando: r.mando, py: r.pinyin,
            en: r.en,
          })),
        }));
        this.BONUS    = data.bonus.map(r => ({ canto: r.canto, jp: r.jyutping, mando: r.mando, py: r.pinyin, en: r.en }));
        this.WATCHOUT = data.watchout;
      }).catch(e => { console.warn('cheat.json load failed, using built-in data', e); });
    }
    await this._loaded;

    const cs = el('div', 'cheatsheet');

    const hint = el('p', 'cs-hint');
    hint.innerHTML = `${SVG.speaker} Click any <span class="cs-demo-canto">Cantonese</span>, <span class="cs-demo-mando">Mandarin</span>, or <span class="cs-demo-rule">rule</span> to hear it spoken.`;
    cs.appendChild(hint);

    for (const section of this.DATA) cs.appendChild(this._buildSection(section));
    cs.appendChild(this._buildBonus());
    cs.appendChild(this._buildWatchOut());

    content.appendChild(cs);
    this._attachListeners(cs);
  },

  // Renders a rule like "哋→们" as two stacked clickable blocks around a → separator
  _ruleCell(rule, ruleJp, rulePy) {
    const parts = rule.split('→');
    if (parts.length !== 2) return `<span class="cs-rule-plain">${sanitize(rule)}</span>`;
    const [left, right] = parts;
    return `
      <div class="cs-rule-pair">
        <div class="cs-rule-side">
          <span class="cs-phrase cs-canto cs-rule-part" data-voice="canto" tabindex="0">${sanitize(left)}</span>
          ${ruleJp ? `<span class="cs-roman cs-roman-rule">${sanitize(ruleJp)}</span>` : ''}
        </div>
        <span class="cs-rule-arrow">→</span>
        <div class="cs-rule-side">
          <span class="cs-phrase cs-mando cs-rule-part" data-voice="mando" tabindex="0">${sanitize(right)}</span>
          ${rulePy ? `<span class="cs-roman cs-roman-rule">${sanitize(rulePy)}</span>` : ''}
        </div>
      </div>`;
  },

  _phraseCell(text, roman, voice) {
    return `<div class="cs-phrase-wrap"><span class="cs-phrase cs-${voice}" data-voice="${voice}" tabindex="0">${sanitize(text)}</span><span class="cs-roman">${sanitize(roman)}</span></div>`;
  },

  _buildSection(section) {
    const wrap = el('div', 'cs-section');
    const head = el('div', 'cs-section-head');
    head.innerHTML = `<span class="cs-badge">${section.num}</span><span class="cs-section-title">${sanitize(section.title)}</span>`;
    wrap.appendChild(head);

    const table = el('table', 'cs-table');
    table.innerHTML = `<thead><tr>${section.cols.map(c => `<th>${sanitize(c)}</th>`).join('')}</tr></thead>`;
    const tbody = el('tbody', '');
    for (const row of section.rows) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="cs-rule-tag">${this._ruleCell(row.rule, row.ruleJp, row.rulePy)}</td>
        <td class="cs-canto-cell">${this._phraseCell(row.canto, row.jp, 'canto')}</td>
        <td class="cs-mando-cell">${this._phraseCell(row.mando, row.py, 'mando')}</td>
        <td class="cs-en-cell">${sanitize(row.en)}</td>
      `;
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  },

  _buildBonus() {
    const wrap = el('div', 'cs-section cs-bonus-section');
    const head = el('div', 'cs-section-head');
    head.innerHTML = `<span class="cs-badge cs-badge--bonus">★</span><span class="cs-section-title">Bonus — Full Sentence Conversions</span>`;
    wrap.appendChild(head);

    const table = el('table', 'cs-table');
    table.innerHTML = `<thead><tr><th>Cantonese</th><th>Mandarin</th><th>English</th></tr></thead>`;
    const tbody = el('tbody', '');
    for (const row of this.BONUS) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="cs-canto-cell">${this._phraseCell(row.canto, row.jp, 'canto')}</td>
        <td class="cs-mando-cell">${this._phraseCell(row.mando, row.py, 'mando')}</td>
        <td class="cs-en-cell">${sanitize(row.en)}</td>
      `;
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  },

  _buildWatchOut() {
    const wrap = el('div', 'cs-section cs-watchout-section');
    const head = el('div', 'cs-section-head');
    head.innerHTML = `<span class="cs-badge cs-badge--warn">⚠</span><span class="cs-section-title">Watch Out — Easy Mistakes</span>`;
    wrap.appendChild(head);

    const table = el('table', 'cs-table');
    table.innerHTML = `<thead><tr><th>Common Error</th><th>Wrong ✗</th><th>Correct ✓</th></tr></thead>`;
    const tbody = el('tbody', '');
    for (const row of this.WATCHOUT) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="cs-en-cell">${sanitize(row.error)}</td>
        <td class="cs-wrong-cell">${sanitize(row.wrong)}</td>
        <td class="cs-correct-cell">${sanitize(row.correct)}</td>
      `;
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  },

  _attachListeners(container) {
    container.querySelectorAll('.cs-phrase').forEach(span => {
      const speak = () => {
        const text  = span.textContent.trim();
        const voice = voiceFor(span.dataset.voice);
        setTTSSpeed(speedFor(span.dataset.voice));
        span.classList.add('cs-phrase--speaking');
        TTS.speak(text, voice, null).finally(() => span.classList.remove('cs-phrase--speaking'));
      };
      span.addEventListener('click', speak);
      span.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); speak(); } });
    });
  },
};

// ── Boot ──────────────────────────────────────────────────────────────────────
async function init() {
  UI.initTheme();
  UI.initSidebar();
  UI.initPhrasesPanel();
  UI.initResize();
  Phrases.attachEvents();


  await Promise.all([Course.load(), Phrases.load()]);

  // Migrate any existing localStorage notes up to the server (one-time sync)
  try {
    const serverNotes = await fetch('/api/notes').then(r => r.json()).catch(() => ({}));
    const uploads = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key || !key.startsWith('note:')) continue;
      const text = localStorage.getItem(key);
      if (text && !serverNotes[key]) {
        uploads.push(fetch('/api/notes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, text }),
        }));
      }
    }
    if (uploads.length) await Promise.allSettled(uploads);
  } catch (_) {}
}

// ── One-time localStorage key migration ──────────────────────────────────────
// Old keys used the video file path as the key; new keys use node.rel (folder path).
// Maps: note:Chapter_XX_... → note:Canto_Mando_Videos/{group}/Chapter_XX.../folder
// Also handles: note:Canto_Mando_Videos/.../video.mp4 → strip the filename
(function migrateNoteKeys() {
  const MIGRATION_FLAG = '_notes_migrated_v2';
  if (localStorage.getItem(MIGRATION_FLAG)) return;

  const GROUP_MAP = [
    [/^Chapter_0[123]_/, 'cm1_Intro'],
    [/^Chapter_06\.5_/,  'cm3_Intermediate'],
    [/^Chapter_0[456]_/, 'cm2_Basic'],
    [/^Chapter_0[6789]_Bonus/, 'cm2_Basic'],
    [/^Chapter_0[789]_/, 'cm3_Intermediate'],
    [/^Chapter_1[012]_/, 'cm4_Advanced'],
  ];

  function chapterToGroup(name) {
    for (const [rx, g] of GROUP_MAP) if (rx.test(name)) return g;
    return null;
  }

  const VIDEO_EXT = /\.(mp4|mov|webm|m4v|mkv)$/i;

  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key || !key.startsWith('note:')) continue;
    const path = key.slice(5);
    let newPath = null;

    if (path.startsWith('Canto_Mando_Videos/') && VIDEO_EXT.test(path)) {
      // New-path but video filename still in key — strip filename
      newPath = path.split('/').slice(0, -1).join('/');
    } else if (!path.startsWith('Canto_Mando_Videos/')) {
      // Old-format: Chapter_XX_Name/.../video.mp4
      const parts = path.split('/');
      const group = chapterToGroup(parts[0]);
      if (group) {
        const folderParts = VIDEO_EXT.test(parts[parts.length - 1]) ? parts.slice(0, -1) : parts;
        newPath = 'Canto_Mando_Videos/' + group + '/' + folderParts.join('/');
      }
    }

    if (newPath && newPath !== path) {
      const val = localStorage.getItem(key);
      if (val !== null) {
        localStorage.setItem('note:' + newPath, val);
        localStorage.removeItem(key);
        i--; // recheck index after removal
      }
    }
  }

  localStorage.setItem(MIGRATION_FLAG, '1');
})();

document.addEventListener('DOMContentLoaded', init);
