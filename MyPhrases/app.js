'use strict';

const state = {
  rows: [],
  filtered: [],
  sortBy: 'newest',
  activeTag: 'all',
  activeType: 'all',
  activeAudio: null,
  activeButton: null,
  repairingMissing: false,
};

const $ = id => document.getElementById(id);
const segCache = new Map();

function initTheme() {
  document.documentElement.setAttribute('data-theme', 'dark');
}

function sanitize(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

function rowTimestamp(row) {
  const ts = Date.parse(row.timestamp || '');
  return Number.isFinite(ts) ? ts : 0;
}

function rowEnglish(row) {
  return (row.english || '').trim().toLowerCase();
}

function parseCategories(row) {
  // Prefer the canonical `tags` array field
  if (Array.isArray(row.tags) && row.tags.length) {
    return row.tags.map(v => String(v || '').trim()).filter(Boolean);
  }

  if (Array.isArray(row.categories)) {
    const tags = row.categories
      .map(v => String(v || '').trim())
      .filter(Boolean);
    return tags.length ? tags : ['Uncategorized'];
  }

  if (typeof row.category === 'string') {
    const tags = row.category
      .split(',')
      .map(v => v.trim())
      .filter(Boolean);
    return tags.length ? tags : ['Uncategorized'];
  }

  return ['Uncategorized'];
}

function populateTagPills(rows) {
  const container = $('tagPills');
  const all = new Set();
  for (const row of rows) {
    for (const tag of row._categories || []) all.add(tag);
  }

  const tags = [...all].sort((a, b) => {
    if (a === 'untagged') return 1;
    if (b === 'untagged') return -1;
    return a.localeCompare(b);
  });

  const favCount = rows.filter(r => r.favourite).length;

  container.innerHTML = '';

  const makePill = (value, label) => {
    const pill = document.createElement('button');
    pill.className = 'tag-pill' + (value === state.activeTag ? ' active' : '');
    pill.dataset.tag = value;
    pill.textContent = label;
    container.appendChild(pill);
  };

  makePill('all', `All (${rows.length})`);
  if (favCount > 0) makePill('favourites', `♥ Favourites (${favCount})`);
  for (const tag of tags) {
    const count = rows.filter(r => (r._categories || []).includes(tag)).length;
    const label = tag === 'untagged' ? `untagged (${count})` : `${tag} (${count})`;
    makePill(tag, label);
  }
}

function applySort(rows, mode) {
  const out = [...rows];
  if (mode === 'oldest') {
    out.sort((a, b) => rowTimestamp(a) - rowTimestamp(b));
  } else if (mode === 'english_az') {
    out.sort((a, b) => rowEnglish(a).localeCompare(rowEnglish(b)) || (rowTimestamp(b) - rowTimestamp(a)));
  } else if (mode === 'english_za') {
    out.sort((a, b) => rowEnglish(b).localeCompare(rowEnglish(a)) || (rowTimestamp(b) - rowTimestamp(a)));
  } else {
    out.sort((a, b) => rowTimestamp(b) - rowTimestamp(a));
  }
  return out;
}

function isHanChar(ch) {
  return /\p{Script=Han}/u.test(ch);
}

// Convert numbered pinyin syllable to tone-mark form e.g. "ni3" → "nǐ"
function numberToToneMark(syll) {
  const tones = {
    a: ['ā','á','ǎ','à','a'], e: ['ē','é','ě','è','e'],
    i: ['ī','í','ǐ','ì','i'], o: ['ō','ó','ǒ','ò','o'],
    u: ['ū','ú','ǔ','ù','u'], ü: ['ǖ','ǘ','ǚ','ǜ','ü'],
    v: ['ǖ','ǘ','ǚ','ǜ','ü'],
  };
  const m = syll.match(/^([a-züv:]+)([1-5])$/i);
  if (!m) return syll;
  const text = m[1].toLowerCase();
  const ti = parseInt(m[2]) - 1;
  if (text.includes('a')) return text.replace('a', tones.a[ti]);
  if (text.includes('e')) return text.replace('e', tones.e[ti]);
  if (text.includes('ou')) return text.replace('o', tones.o[ti]);
  for (let i = text.length - 1; i >= 0; i--) {
    const c = text[i];
    if (tones[c]) return text.slice(0, i) + tones[c][ti] + text.slice(i + 1);
  }
  return syll;
}

// Convert jyutping number to superscript e.g. "nei5" → "nei⁵"
function jyutpingToneSuper(syll) {
  return syll.replace(/([1-6])$/, m => '¹²³⁴⁵⁶'[parseInt(m) - 1] ?? m);
}

function buildMandarinRubyHtml(text, pinyin) {
  const base = text || '-';
  const safeFallback = sanitize(base);
  const syllables = (pinyin || '').trim().split(/\s+/).filter(Boolean);
  if (!syllables.length || !text) return safeFallback;

  const chars = Array.from(text);
  let pyIdx = 0;
  let usedRuby = false;
  let out = '';

  for (const ch of chars) {
    const safeCh = sanitize(ch);
    if (isHanChar(ch) && pyIdx < syllables.length) {
      usedRuby = true;
      out += `<ruby>${safeCh}<rt>${sanitize(numberToToneMark(syllables[pyIdx]))}</rt></ruby>`;
      pyIdx += 1;
    } else {
      out += safeCh;
    }
  }

  return usedRuby ? out : safeFallback;
}

// ── Segment-based ruby & hover definitions ───────────────────────────────────

async function fetchSegments(text) {
  if (!text || !text.trim()) return [];
  const key = text.trim();
  if (segCache.has(key)) return segCache.get(key);
  try {
    const res = await fetch('/api/dict/segment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: key }),
    });
    if (!res.ok) return [];
    const data = await res.json();
    const words = data.words || [];
    segCache.set(key, words);
    return words;
  } catch { return []; }
}

// Build ruby HTML from segment words. rubySource: 'pinyin' | 'jyutping'
function buildSegRuby(words, rubySource) {
  if (!words.length) return '';
  let out = '';
  for (const w of words) {
    const chars = Array.from(w.word);
    const hasEntries = w.entries && w.entries.length > 0;

    // Pick ruby syllables with proper tone representation
    let rtSylls = [];
    if (rubySource === 'jyutping') {
      rtSylls = (w.jyutping || '').trim().split(/\s+/).filter(Boolean)
        .map(jyutpingToneSuper);
    } else {
      // Prefer pinyin with diacritics (API already provides it); fall back to converting raw
      const py = w.entries?.[0]?.pinyin || w.entries?.[0]?.pinyin_raw || '';
      rtSylls = py.trim().split(/\s+/).filter(Boolean).map(s =>
        /[1-5]/.test(s) ? numberToToneMark(s) : s
      );
    }

    let innerHtml = '';
    let rtIdx = 0;
    for (const ch of chars) {
      const safeCh = sanitize(ch);
      if (isHanChar(ch) && rtIdx < rtSylls.length) {
        innerHtml += `<ruby>${safeCh}<rt>${sanitize(rtSylls[rtIdx++])}</rt></ruby>`;
      } else {
        innerHtml += safeCh;
      }
    }

    if (hasEntries) {
      // Store pinyin with diacritics in tooltip data
      const defs = w.entries.slice(0, 3).map(e => ({
        pinyin: e.pinyin || e.pinyin_raw || '',
        defs: (e.definitions || []).slice(0, 3).join('; '),
      }));
      out += `<span class="word-seg" data-word="${sanitize(w.word)}" data-defs='${JSON.stringify(defs).replace(/'/g, '&#39;')}'>${innerHtml}</span>`;
    } else {
      out += innerHtml;
    }
  }
  return out;
}

function getOrCreateTooltip() {
  let tip = document.getElementById('wordTooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'wordTooltip';
    tip.className = 'word-tooltip';
    document.body.appendChild(tip);
  }
  return tip;
}

function showWordTooltip(seg) {
  let defs;
  try { defs = JSON.parse(seg.dataset.defs || '[]'); } catch { return; }
  if (!defs.length) return;
  const word = seg.dataset.word || '';
  const tip = getOrCreateTooltip();
  const lines = defs.map(d => {
    const py = d.pinyin ? `<span class="wt-pinyin">${sanitize(d.pinyin)}</span> ` : '';
    return `<div class="wt-def">${py}${sanitize(d.defs)}</div>`;
  }).join('');
  tip.innerHTML = `<div class="wt-word">${sanitize(word)}</div>${lines}`;
  // Show first so offsetHeight is available
  tip.style.display = 'block';
  // Position using viewport coords (tip is position:fixed)
  const rect = seg.getBoundingClientRect();
  const tipW = 240;
  let left = rect.left;
  let top = rect.top - tip.offsetHeight - 8;
  if (left + tipW > window.innerWidth - 8) left = Math.max(4, window.innerWidth - tipW - 8);
  if (top < 4) top = rect.bottom + 6;
  tip.style.left = left + 'px';
  tip.style.top = top + 'px';
}

function hideWordTooltip() {
  const tip = document.getElementById('wordTooltip');
  if (tip) tip.style.display = 'none';
}

function lineHtml(kind, text, lang, audioRel, rowId, textHtml) {
  const safeText = textHtml || sanitize(text || '-');
  const safeLang = sanitize(lang);
  const safeAudio = sanitize(audioRel || '');
  const safeId = sanitize(rowId || '');
  return `
    <button class="phrase-line line-${kind}" data-row-id="${safeId}" data-audio="${safeAudio}" data-lang="${safeLang}">
      <span class="line-text">${safeText}</span>
      <span class="line-tag">${safeLang}</span>
    </button>
  `;
}

function hasMandarinAudio(row) {
  return Boolean((row.audio?.mandarin || '').trim());
}

function getMissingMandarinRows() {
  return state.rows.filter(row => !hasMandarinAudio(row) && (row.mandarin || '').trim());
}

function syncRow(updatedRow) {
  if (!updatedRow?.id) return;
  const nextRows = state.rows.map(row => row.id === updatedRow.id
    ? { ...updatedRow, _categories: parseCategories(updatedRow) }
    : row);
  state.rows = nextRows;
  // Also update filtered so re-render reflects changes immediately
  state.filtered = state.filtered.map(row => row.id === updatedRow.id
    ? nextRows.find(r => r.id === updatedRow.id)
    : row);
}

// ── Tag editor ──────────────────────────────────────────────────────────────

function getKnownTags() {
  const all = new Set();
  for (const row of state.rows) {
    for (const t of row._categories || []) all.add(t);
  }
  return [...all].sort((a, b) => {
    if (a === 'untagged') return 1;
    if (b === 'untagged') return -1;
    return a.localeCompare(b);
  });
}

function buildTagFooter(row) {
  const tags = row._categories || [];
  const safeId = sanitize(row.id || '');
  const isFav = Boolean(row.favourite);
  const pillsHtml = tags.map(t =>
    `<span class="card-tag-pill">${sanitize(t)}</span>`
  ).join('');
  const favCls = isFav ? 'card-fav-btn active' : 'card-fav-btn';
  const heartFill = isFav ? 'currentColor' : 'none';
  return `<div class="card-tag-row" data-row-id="${safeId}">
    <div class="card-tag-pills">${pillsHtml}</div>
    <button class="${favCls}" data-row-id="${safeId}" title="${isFav ? 'Remove from favourites' : 'Add to favourites'}" aria-label="Toggle favourite">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="${heartFill}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>
    </button>
    <button class="card-tag-edit-btn" data-row-id="${safeId}" title="Edit tags" aria-label="Edit tags">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>
    </button>
    <button class="card-edit-btn" data-row-id="${safeId}" title="Edit content" aria-label="Edit content">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6M9 12h6M9 15h4"/></svg>
    </button>
    <button class="card-del-btn" data-row-id="${safeId}" title="Delete" aria-label="Delete">
      <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
    </button>
  </div>`;
}

async function toggleFavourite(rowId) {
  const row = state.rows.find(r => r.id === rowId);
  if (!row) return;
  const newVal = !row.favourite;
  try {
    const res = await fetch(`/api/captures/${encodeURIComponent(rowId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ favourite: newVal }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    syncRow(data.record);
    // Re-render just this card's footer
    const cardTagRow = document.querySelector(`.card-tag-row[data-row-id="${CSS.escape(rowId)}"]`);
    if (cardTagRow) {
      const updatedRow = state.rows.find(r => r.id === rowId);
      if (updatedRow) {
        const newFooter = document.createElement('div');
        newFooter.innerHTML = buildTagFooter(updatedRow);
        const newEl = newFooter.firstElementChild;
        cardTagRow.replaceWith(newEl);
        newEl.querySelector('.card-fav-btn')?.addEventListener('click', e => { e.stopPropagation(); toggleFavourite(rowId); });
        newEl.querySelector('.card-tag-edit-btn')?.addEventListener('click', e => { e.stopPropagation(); openTagEditor(rowId); });
      }
    }
    populateTagPills(state.rows);
  } catch (err) {
    console.error('Favourite toggle failed', err);
  }
}

async function deleteCapture(rowId) {
  const row = state.rows.find(r => r.id === rowId);
  if (!row) return;

  // Inline confirm inside the card
  const cardTagRow = document.querySelector(`.card-tag-row[data-row-id="${CSS.escape(rowId)}"]`);
  if (!cardTagRow) return;

  const confirmBar = document.createElement('div');
  confirmBar.className = 'card-delete-confirm';
  confirmBar.innerHTML = `<span>Delete "${sanitize((row.english || row.mandarin).slice(0, 40))}"?</span>
    <button class="card-del-yes">Delete</button>
    <button class="card-del-no">Cancel</button>`;
  cardTagRow.replaceWith(confirmBar);

  confirmBar.querySelector('.card-del-no').addEventListener('click', () => {
    confirmBar.replaceWith(cardTagRow);
  });

  confirmBar.querySelector('.card-del-yes').addEventListener('click', async () => {
    try {
      const res = await fetch(`/api/captures/${encodeURIComponent(rowId)}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // Remove from state and DOM
      state.rows = state.rows.filter(r => r.id !== rowId);
      const article = confirmBar.closest('article');
      if (article) {
        article.style.transition = 'opacity 0.2s';
        article.style.opacity = '0';
        setTimeout(() => article.remove(), 200);
      }
      state.filtered = state.filtered.filter(r => r.id !== rowId);
      $('status').textContent = `${state.filtered.length.toLocaleString()} shown`;
      populateTagPills(state.rows);
    } catch (err) {
      console.error('Delete failed', err);
      confirmBar.replaceWith(cardTagRow);
    }
  });
}

function openEditContent(rowId) {
  const row = state.rows.find(r => r.id === rowId);
  if (!row) return;

  const existing = document.querySelector('.content-editor-popup');
  if (existing) existing.remove();

  const popup = document.createElement('div');
  popup.className = 'content-editor-popup';
  popup.innerHTML = `
    <div class="content-editor-inner">
      <h3 class="content-editor-title">Edit</h3>
      <label>English<input class="content-editor-input" name="english" value="${sanitize(row.english || '')}" /></label>
      <label>Mandarin<input class="content-editor-input" name="mandarin" value="${sanitize(row.mandarin || '')}" /></label>
      <label>Pinyin<input class="content-editor-input" name="pinyin" value="${sanitize(row.pinyin || '')}" /></label>
      <label>Cantonese<input class="content-editor-input" name="cantonese" value="${sanitize(row.cantonese || '')}" /></label>
      <div class="content-editor-actions">
        <button class="content-editor-save">Save</button>
        <button class="content-editor-cancel">Cancel</button>
      </div>
    </div>`;

  document.body.appendChild(popup);

  popup.querySelector('.content-editor-cancel').addEventListener('click', () => popup.remove());
  popup.addEventListener('click', e => { if (e.target === popup) popup.remove(); });
  popup.querySelector('.content-editor-save').addEventListener('click', () => saveEditContent(rowId, popup));
}

async function saveEditContent(rowId, popup) {
  const inputs = {};
  for (const inp of popup.querySelectorAll('.content-editor-input')) {
    inputs[inp.name] = inp.value.trim();
  }
  try {
    const res = await fetch(`/api/captures/${encodeURIComponent(rowId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(inputs),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    syncRow(data.record);
    popup.remove();
    filterRows();
  } catch (err) {
    console.error('Edit save failed', err);
  }
}

function openTagEditor(rowId) {
  // Close any open editor first
  document.querySelectorAll('.tag-editor-popup').forEach(el => el.remove());

  const row = state.rows.find(r => r.id === rowId);
  if (!row) return;

  const currentTags = new Set(row._categories || []);
  const cardTagRow = document.querySelector(`.card-tag-row[data-row-id="${CSS.escape(rowId)}"]`);
  if (!cardTagRow) return;

  const knownTags = getKnownTags();

  const checkboxesHtml = knownTags.map(tag => {
    const checked = currentTags.has(tag) ? 'checked' : '';
    const safeTag = sanitize(tag);
    return `<label class="tag-editor-option">
      <input type="checkbox" value="${safeTag}" ${checked}>
      <span>${safeTag}</span>
    </label>`;
  }).join('');

  const popup = document.createElement('div');
  popup.className = 'tag-editor-popup';
  popup.innerHTML = `
    <div class="tag-editor-grid">${checkboxesHtml}</div>
    <div class="tag-editor-new">
      <input type="text" class="tag-editor-new-input" placeholder="New tag…" autocomplete="off" />
      <button class="tag-editor-new-add" type="button">Add</button>
    </div>
    <div class="tag-editor-actions">
      <button class="tag-editor-save" data-row-id="${sanitize(rowId)}">Save</button>
      <button class="tag-editor-cancel">Cancel</button>
    </div>
  `;

  cardTagRow.appendChild(popup);

  // Add new tag to the grid
  popup.querySelector('.tag-editor-new-add').addEventListener('click', () => {
    const input = popup.querySelector('.tag-editor-new-input');
    const val = input.value.trim();
    if (!val) return;
    // Check not already in grid
    const existing = [...popup.querySelectorAll('input[type=checkbox]')].map(el => el.value);
    if (!existing.includes(val)) {
      const label = document.createElement('label');
      label.className = 'tag-editor-option';
      label.innerHTML = `<input type="checkbox" value="${sanitize(val)}" checked><span>${sanitize(val)}</span>`;
      popup.querySelector('.tag-editor-grid').appendChild(label);
    } else {
      // Just check the existing one
      const cb = popup.querySelector(`input[value="${CSS.escape(val)}"]`);
      if (cb) cb.checked = true;
    }
    input.value = '';
  });

  // Allow Enter key in the new-tag input
  popup.querySelector('.tag-editor-new-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); popup.querySelector('.tag-editor-new-add').click(); }
  });

  popup.querySelector('.tag-editor-cancel').addEventListener('click', () => popup.remove());
  popup.querySelector('.tag-editor-save').addEventListener('click', () => saveTagEdit(rowId, popup));
}

async function saveTagEdit(rowId, popup) {
  const checked = [...popup.querySelectorAll('input[type=checkbox]:checked')].map(el => el.value);
  if (!checked.length) { alert('Select at least one tag.'); return; }

  const saveBtn = popup.querySelector('.tag-editor-save');
  saveBtn.disabled = true;
  saveBtn.textContent = 'Saving…';

  try {
    const res = await fetch(`/api/captures/${encodeURIComponent(rowId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: checked }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    syncRow(data.record);
    popup.remove();
    // Re-render just this card's tag footer
    const cardTagRow = document.querySelector(`.card-tag-row[data-row-id="${CSS.escape(rowId)}"]`);
    if (cardTagRow) {
      const updatedRow = state.rows.find(r => r.id === rowId);
      if (updatedRow) {
        cardTagRow.outerHTML = buildTagFooter(updatedRow);
        // Re-attach editor listener on the new element
        document.querySelector(`.card-tag-edit-btn[data-row-id="${CSS.escape(rowId)}"]`)
          ?.addEventListener('click', () => openTagEditor(rowId));
      }
    }
    // Refresh tag pill counts
    populateTagPills(state.rows);
  } catch (err) {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save';
    console.error('Tag save failed', err);
    alert(`Save failed: ${err.message}`);
  }
}

function updateRepairButton() {
  const btn = $('repairMissingBtn');
  const missingCount = getMissingMandarinRows().length;
  btn.hidden = missingCount === 0;
  btn.disabled = state.repairingMissing;
  btn.textContent = state.repairingMissing
    ? `Repairing ${missingCount}...`
    : `Repair Missing Mandarin (${missingCount})`;
}

function render() {
  const list = $('list');
  const status = $('status');

  list.innerHTML = '';
  status.textContent = `${state.filtered.length.toLocaleString()} shown`;

  if (!state.filtered.length) {
    list.innerHTML = '<div class="empty">No phrases match your search.</div>';
    return;
  }

  for (const row of state.filtered) {
    const card = document.createElement('article');
    card.className = 'phrase-card';

    const mandoAudio = row.audio?.mandarin || '';
    const cantoAudio = row.audio?.cantonese || '';
    const defaultAudio = mandoAudio || cantoAudio;

    // Use cached segments for ruby + hover defs; stored pinyin always wins for Mandarin display
    const manWords = segCache.get((row.mandarin || '').trim()) || [];
    const canWords = segCache.get((row.cantonese || '').trim()) || [];
    const manHtml = row.pinyin
      ? buildMandarinRubyHtml(row.mandarin, row.pinyin)
      : manWords.length ? buildSegRuby(manWords, 'pinyin') : sanitize(row.mandarin || '-');
    const canHtml = canWords.length ? buildSegRuby(canWords, 'jyutping') : sanitize(row.cantonese || '-');

    card.innerHTML = [
      lineHtml('en', row.english || '-', 'English', defaultAudio, row.id),
      lineHtml('mando', row.mandarin || '-', 'Mandarin', mandoAudio || defaultAudio, row.id, manHtml),
      lineHtml('canto', row.cantonese || '-', 'Cantonese', cantoAudio || defaultAudio, row.id, canHtml),
      buildTagFooter(row),
    ].join('');

    // Attach tag edit button listener
    card.querySelector('.card-fav-btn')?.addEventListener('click', e => {
      e.stopPropagation();
      toggleFavourite(row.id);
    });
    card.querySelector('.card-tag-edit-btn')?.addEventListener('click', e => {
      e.stopPropagation();
      openTagEditor(row.id);
    });
    card.querySelector('.card-edit-btn')?.addEventListener('click', e => {
      e.stopPropagation();
      openEditContent(row.id);
    });
    card.querySelector('.card-del-btn')?.addEventListener('click', e => {
      e.stopPropagation();
      deleteCapture(row.id);
    });

    // Attach word tooltip via direct mouseenter/leave — avoids button event issues
    card.querySelectorAll('.word-seg').forEach(seg => {
      seg.addEventListener('mouseenter', () => showWordTooltip(seg));
      seg.addEventListener('mouseleave', hideWordTooltip);
    });

    list.appendChild(card);
  }
}

function filterRows() {
  const q = ($('searchInput').value || '').trim().toLowerCase();
  const tag = state.activeTag;
  const type = state.activeType;

  let filtered = state.rows.filter(row => {
    if (tag === 'favourites' && !row.favourite) return false;
    if (tag !== 'all' && tag !== 'favourites' && !(row._categories || []).includes(tag)) return false;
    if (type !== 'all' && (row.type || 'word') !== type) return false;
    if (!q) return true;
    const haystack = `${row.english || ''} ${row.mandarin || ''} ${row.cantonese || ''} ${row.pinyin || ''}`.toLowerCase();
    return haystack.includes(q);
  });

  filtered = applySort(filtered, state.sortBy);
  state.filtered = filtered;

  updateRepairButton();
  render();
}

function stopActive() {
  if (state.activeAudio) {
    state.activeAudio.pause();
    state.activeAudio.currentTime = 0;
    state.activeAudio = null;
  }
  if (state.activeButton) {
    state.activeButton.classList.remove('playing');
    state.activeButton = null;
  }
}

function playAudio(btn) {
  const rel = btn.dataset.audio;
  if (!rel) return;

  const src = `/file/${encodeURI(rel)}`;
  stopActive();

  const audio = new Audio(src);
  state.activeAudio = audio;
  state.activeButton = btn;
  btn.classList.add('playing');

  audio.addEventListener('ended', () => {
    if (state.activeButton === btn) {
      btn.classList.remove('playing');
      state.activeButton = null;
      state.activeAudio = null;
    }
  });

  audio.addEventListener('error', () => {
    btn.classList.remove('playing');
    state.activeButton = null;
    state.activeAudio = null;
  });

  audio.play().catch(() => {
    btn.classList.remove('playing');
    state.activeButton = null;
    state.activeAudio = null;
  });
}

async function loadCaptures() {
  const status = $('status');
  status.textContent = 'Loading...';

  try {
    const res = await fetch('/api/captures');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = await res.json();
    state.rows = Array.isArray(rows)
      ? rows.map(r => ({ ...r, _categories: parseCategories(r) }))
      : [];
    populateTagPills(state.rows);
    // Pre-warm segment cache for all unique texts before first render
    const uniqueTexts = new Set();
    for (const r of state.rows) {
      if (r.mandarin) uniqueTexts.add(r.mandarin.trim());
      if (r.cantonese) uniqueTexts.add(r.cantonese.trim());
    }
    status.textContent = 'Loading dictionary…';
    await Promise.all([...uniqueTexts].map(t => fetchSegments(t)));
    filterRows();
    status.textContent = `${state.rows.length.toLocaleString()} total`;
  } catch (err) {
    state.rows = [];
    state.filtered = [];
    render();
    status.textContent = 'Failed to load captures';
    console.error('Failed to load captures', err);
  }
}

async function repairMissingMandarin() {
  const status = $('status');
  const targets = getMissingMandarinRows();
  if (!targets.length || state.repairingMissing) return;

  state.repairingMissing = true;
  updateRepairButton();

  let repaired = 0;
  try {
    for (const row of targets) {
      status.textContent = `Repairing Mandarin audio ${repaired + 1}/${targets.length}...`;
      const res = await fetch(`/api/captures/${encodeURIComponent(row.id)}/repair`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lang: 'mandarin' }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      syncRow(data.record);
      repaired += 1;
    }
    filterRows();
    status.textContent = repaired === 1 ? 'Repaired 1 Mandarin audio file' : `Repaired ${repaired} Mandarin audio files`;
  } catch (err) {
    filterRows();
    status.textContent = repaired > 0
      ? `Repaired ${repaired}, then stopped: ${err.message}`
      : `Repair failed: ${err.message}`;
    console.error('Failed to repair missing Mandarin audio', err);
  } finally {
    state.repairingMissing = false;
    updateRepairButton();
  }
}

function attachEvents() {
  $('searchInput').addEventListener('input', filterRows);

  $('tagPills').addEventListener('click', e => {
    const pill = e.target.closest('.tag-pill');
    if (!pill) return;
    state.activeTag = pill.dataset.tag;
    document.querySelectorAll('.tag-pill').forEach(p =>
      p.classList.toggle('active', p.dataset.tag === state.activeTag)
    );
    filterRows();
  });

  $('typeToggle').addEventListener('click', e => {
    const btn = e.target.closest('.type-btn');
    if (!btn) return;
    state.activeType = btn.dataset.type;
    document.querySelectorAll('.type-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.type === state.activeType)
    );
    filterRows();
  });

  $('sortSelect').addEventListener('change', e => {
    state.sortBy = e.target.value;
    filterRows();
  });
  $('repairMissingBtn').addEventListener('click', repairMissingMandarin);
  $('list').addEventListener('click', e => {
    const btn = e.target.closest('.phrase-line');
    if (!btn) return;
    playAudio(btn);
  });
  window.addEventListener('beforeunload', stopActive);

}

initTheme();
attachEvents();
loadCaptures();
