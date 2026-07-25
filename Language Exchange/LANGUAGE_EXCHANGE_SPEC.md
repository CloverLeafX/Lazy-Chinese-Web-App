# Language Exchange — Current Spec

Live at **[phrases.up.railway.app/language-exchange](https://phrases.up.railway.app/language-exchange/)**. A real-time, two-user Mandarin/Cantonese/English notebook that replaces the broken `=GOOGLETRANSLATE(...)` sheet workflow (columns: Traditional / Simplified / Pinyin / Cantonese / English / Notes).

Ships as a Flask **Blueprint** mounted at `/language-exchange` inside the existing Yi Web App (`Yi_Web_App/`); it does **not** run as a separate Railway service.

---

## 1. Design principles

1. **Deterministic first, LLM last.** Pinyin (`pypinyin`), simplified↔traditional (`opencc-python-reimplemented`), jyutping (`pycantonese`) and CEDICT lookups all run locally — zero LLM tokens spent. The Groq LLM fires only when the user clicks **Translate** in Mode 1, or when an entry is created in Mode 2.
2. **User overrides are sacred.** Any field the user edits gets `*_source = "user"` and is preserved across subsequent re-translations.
3. **On-demand audio.** TTS runs only when the user clicks ▶. First hit generates and caches the mp3 to disk; subsequent hits stream the cached file. Deletes/edits/re-translations invalidate the cache.
4. **Concurrency-safe.** SQLite in WAL mode on the Railway persistent volume; a single `threading.Lock` around writes. Live updates use SSE (Server-Sent Events).
5. **In-process integration with MyPhrases.** Save-to-MyPhrases calls `server_cloud.create_capture()` directly — no HTTP loopback — so the auto-tagging pipeline runs in the same Flask worker.
6. **No env-var leakage.** Passwords, secrets, and API keys live only in `os.environ` (Railway service vars + local `Yi_Web_App/.env`). Never hardcoded, never logged.

---

## 2. Two modes

| Mode | Trigger | LLM? | Output |
|---|---|---|---|
| **Mode 1 — Mandarin in (`mando_in`)** | User types Mandarin (traditional or simplified) | Only on **Translate** click | Simplified + Traditional + Pinyin + Jyutping deterministically; if the whole string is in CEDICT → English + Cantonese-script auto-fill via dictionary (marked 📖 dict); LLM adds sentence-aware Cantonese + English on demand |
| **Mode 2 — English in (`english_in`)** | User types English | Yes, on **Add** | Groq round-trip returns Simplified + Traditional + Pinyin. No Cantonese, no audio. |

---

## 3. Auth model

DB-backed, argon2-hashed users with an invite-only sign-up flow. **Kai is the sole bootstrapped admin;** everybody else joins via an invite link that Kai generates from the admin panel.

### 3.1 Bootstrap

On module load, `_bootstrap_users()` seeds the `users` table from two env vars — **only if a row for that username does not already exist**:

- `LE_USER_KAI_PASSWORD`   → creates `kai`   as `role='admin'`
- `LE_USER_JERRY_PASSWORD` → creates `jerry` as `role='member'`

After a successful bootstrap the DB is authoritative. The env vars can be deleted from Railway with no impact on login (they only run when the row is missing). Bootstrap is idempotent — restarting the app never overwrites an existing password.

### 3.2 Runtime behaviour

- **`users` table populated** (production) → login screen appears. `POST /api/login` verifies `{username, password}` against `password_hash` with argon2. Disabled users are rejected. Successful login stamps `last_login_at`.
- **`users` table empty** (fresh local dev) → the login screen is bypassed and `_current_user()` returns the sentinel `"local"` with implicit admin rights. As soon as the first user is bootstrapped, this fallback goes away.

Passwords are never returned to the client. `password_hash` is stripped from all admin responses via `_safe_user_dict()`.

Timing-attack defence: on a missing-username login the server still runs `_verify_password(password, _DUMMY_HASH)` so failed logins take similar CPU to successful ones.

### 3.3 Roles

| Role | Can do |
|---|---|
| `admin`  | Everything a `member` can do, plus: invite new users, promote / demote / disable / delete other users, revoke invites. |
| `member` | Create + edit + delete their own entries; change their own password. |

### 3.4 Invite flow

1. Admin opens the badge menu → **Manage users** → **Invite a new user**, picks a role (`member` / `admin`), an optional note, and TTL (1–30 days). Server generates `token = secrets.token_urlsafe(24)`, stores it in `user_invites`, and returns the URL `https://phrases.up.railway.app/language-exchange/invite/<token>`.
2. Admin copies the link and sends it out-of-band (Signal, email, whatever).
3. Invitee opens the link → SPA detects the path → calls `GET /api/invite/<token>` for a validity check → shows the sign-up form.
4. Invitee picks a username (regex `^[a-z][a-z0-9_]{2,19}$`), display name, and password (min 8 chars). `POST /api/invite/<token>` creates the user, marks the invite `used_at`, and logs the browser in.
5. If the token is used, revoked, or expired, the endpoints return 404 and the SPA shows an error.

### 3.5 Admin safeguards (how Kai stays in control)

The following operations are refused by the backend with a 400:

- Demoting yourself
- Disabling yourself
- Deleting yourself
- Demoting / disabling / deleting the **last** remaining admin (`_count_admins(exclude=username) < 1`)

This makes it structurally impossible for Kai to lock himself out through the UI. To hand off admin cleanly, Kai must first promote another user to `admin` (via an invite with `role='admin'` or by patching an existing member); only then can Kai step down.

If Kai ever *does* lose the password, recovery is straightforward: delete the row from `users` and re-set `LE_USER_KAI_PASSWORD` in Railway — the next restart re-bootstraps.

### 3.6 Sessions

`SECRET_KEY` (env var, read by `server_cloud.py`) signs the Flask session cookie. Session key is `session["le_user"] = username`. Disabled users are cleared from the session on the next request via `_current_user()`. Logging out just pops the key.

---

## 4. Routes (all under `/language-exchange/`)

| Method | Path | Purpose |
|---|---|---|
| GET  | `/` | Serves the SPA (`le_static/index.html`) |
| GET  | `/static/<path>` | SPA static assets |
| GET  | `/invite/<token>` | Serves the SPA (front-end router shows the sign-up view) |
| GET  | `/api/me` | `{user, role, display_name, login_required}` |
| POST | `/api/login` | `{username, password}` → sets `session["le_user"]`, returns `{user, role, display_name}` |
| POST | `/api/logout` | Clears session |
| POST | `/api/me/password` | Self-service password change `{old_password, new_password}` (min 8 chars) |
| GET  | `/api/admin/users` | **admin** — list all users (no `password_hash`) |
| PATCH | `/api/admin/users/<username>` | **admin** — `{role?, disabled?, display_name?}` with safeguards (see §3.5) |
| DELETE | `/api/admin/users/<username>` | **admin** — delete a user (with safeguards) |
| GET  | `/api/admin/invites` | **admin** — list pending invites |
| POST | `/api/admin/invites` | **admin** — `{role, note?, ttl_days?}` → returns `{token, url, expires_at, ...}` |
| DELETE | `/api/admin/invites/<token>` | **admin** — revoke a pending invite |
| GET  | `/api/invite/<token>` | Public — validate token, returns `{valid, role, invited_by, note, expires_at}` |
| POST | `/api/invite/<token>` | Public — accept invite `{username, password, display_name}` |
| GET  | `/api/sessions` | Lists all sessions ordered by date desc, includes `entry_count` |
| POST | `/api/sessions` | `{title, date}` — 201 with created row; SSE `session.created` |
| PATCH | `/api/sessions/<sid>` | `{title?, date?}` |
| DELETE | `/api/sessions/<sid>` | Deletes session; SQLite `ON DELETE CASCADE` wipes all entries |
| GET  | `/api/entries?session_id=&mode=&q=` | Lists entries |
| POST | `/api/entries` | `{session_id, mode, source_text}` — see §6 |
| PATCH | `/api/entries/<eid>` | Edit any field; server sets `*_source = "user"` for edited fields, updates `edited_by`/`edited_at`, invalidates audio cache |
| DELETE | `/api/entries/<eid>` | Removes entry and invalidates audio |
| POST | `/api/entries/<eid>/translate` | Fires the LLM; see §7 |
| POST | `/api/entries/<eid>/save-to-myphrases` | Push a Mode 1 entry to MyPhrases; see §10 |
| GET  | `/api/entries/<eid>/audio/<lang>` | Streams cached mp3; generates on first miss (Mode 1 only, `lang ∈ {mandarin, cantonese}`) |
| GET  | `/api/stream` | SSE endpoint; emits events listed in §9 |
| GET  | `/api/health` | `{ok, db, opencc, login_required, admin_count}` |

All JSON. Errors: `{"error": "message"}` with a 4xx/5xx status. Auth guards:

- `_require_login` — everything except `/api/me`, `/api/login`, `/api/logout`, `/api/health`, `/api/invite/*`, and the static routes.
- `_require_admin` — everything under `/api/admin/*`.

---

## 5. Data model

SQLite (WAL) at `${DATA_DIR}/language_exchange.db`. Audio cache under `${DATA_DIR}/le_audio/{entry_id}_{lang}.mp3`.

```sql
CREATE TABLE sessions (
    id           TEXT PRIMARY KEY,      -- uuid4 hex
    title        TEXT NOT NULL,
    session_date TEXT NOT NULL,         -- ISO date (YYYY-MM-DD)
    created_by   TEXT NOT NULL,         -- 'kai' | 'jerry' | 'local'
    created_at   TEXT NOT NULL          -- ISO 8601 UTC
);

CREATE TABLE entries (
    id                 TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    mode               TEXT NOT NULL CHECK(mode IN ('mando_in','english_in')),
    source_text        TEXT NOT NULL,      -- exact user input, never mutated

    -- Live/displayed values (edits land here)
    trad               TEXT,
    simp               TEXT,
    pinyin             TEXT,
    jyutping           TEXT,
    cantonese          TEXT,
    english            TEXT,

    -- Snapshots of the last LLM output (provenance; overwritten on Retranslate)
    ai_trad            TEXT,
    ai_simp            TEXT,
    ai_pinyin          TEXT,
    ai_cantonese       TEXT,
    ai_english         TEXT,

    -- Per-field provenance: 'script' | 'cedict' | 'llm' | 'user' | NULL
    trad_source        TEXT,
    simp_source        TEXT,
    pinyin_source      TEXT,
    cantonese_source   TEXT,
    english_source     TEXT,

    notes              TEXT DEFAULT '',
    created_by         TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    edited_by          TEXT,
    edited_at          TEXT,
    llm_ran_at         TEXT,
    myphrases_saved_at TEXT,
    myphrases_id       TEXT
);

CREATE INDEX idx_entries_session ON entries(session_id, created_at DESC);

CREATE TABLE users (
    username       TEXT PRIMARY KEY,        -- lowercase; regex ^[a-z][a-z0-9_]{2,19}$
    display_name   TEXT NOT NULL,           -- 1–60 chars
    password_hash  TEXT NOT NULL,           -- argon2id, argon2-cffi defaults
    role           TEXT NOT NULL CHECK(role IN ('admin','member')),
    created_at     TEXT NOT NULL,
    created_by     TEXT NOT NULL,           -- 'system' (bootstrap) or the inviting admin's username
    last_login_at  TEXT,
    disabled       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE user_invites (
    token       TEXT PRIMARY KEY,           -- secrets.token_urlsafe(24)
    role        TEXT NOT NULL CHECK(role IN ('admin','member')),
    invited_by  TEXT NOT NULL,              -- admin username
    note        TEXT DEFAULT '',            -- free-form label (e.g. invitee name)
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,              -- default now + 7 days, capped 1..30
    used_at     TEXT,                       -- set on acceptance
    used_by     TEXT                        -- accepting username
);
```

Connection settings: `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`.

---

## 6. Entry creation flow (`POST /api/entries`)

### Mode 1 — `mando_in`
Server runs, in order, all deterministic:
1. `_to_simp_trad(source_text)` → `trad`, `simp` via `OpenCC("s2t")` / `OpenCC("t2s")` (auto-detects direction).
2. `_pinyin(simp)` → `pinyin` via `pypinyin.lazy_pinyin(..., Style.TONE)`.
3. `_jyutping_of(trad)` → `jyutping` via `server_cloud._jyutping()` (pycantonese).
4. `_cedict_english(src)` (also tries `simp`, `trad`) → if a match is found, sets `english = top 3 defs joined by "; "` with `english_source = "cedict"`, and `cantonese = trad` with `cantonese_source = "script"` (whole-word canto script matches traditional).
5. Sets `trad_source = simp_source = pinyin_source = "script"`.
6. INSERTs row; broadcasts `entry.created`.

`llm_ran_at` remains `NULL`.

### Mode 2 — `english_in`
The LLM fires **synchronously** on Add:
1. `_translate_via_llm(src)` → calls `server_cloud.translate_text()` (Groq llama-3.3-70b) → returns `{mandarin, pinyin, cantonese, english}`.
2. `simp = mandarin`, `trad = OpenCC("s2t").convert(simp)`, `pinyin` from Groq (or regenerated via pypinyin if Groq's is blank).
3. `english = source_text` with `english_source = "user"` (the English is the user's original).
4. `simp_source = trad_source = pinyin_source = "llm"`.
5. Snapshots `ai_*` fields; sets `llm_ran_at = now`.
6. If the LLM call throws, the bare entry is persisted with just `english` populated so the UI can show a Retranslate button.

---

## 7. Translate flow (`POST /api/entries/<eid>/translate`) — the ONLY on-demand LLM path

Applies to both modes. Rule: **`*_source == "user"` fields are preserved verbatim; everything else is replaced with the LLM output and marked `"llm"`.**

Implementation is a `keep(field, source_field, new_val, new_source)` closure in `api_entries_translate`:
```python
def keep(field, source_field, new_val, new_source):
    if entry.get(source_field) == "user":
        return entry.get(field), entry.get(source_field)  # preserve user edit
    return new_val, new_source
```

Applied per-field for `simp`, `trad`, `pinyin`, `cantonese`, `english`. `jyutping` is regenerated from the (possibly-preserved) `trad`. `ai_*` snapshots always overwrite. `llm_ran_at = now`. Audio cache is invalidated. `entry.updated` broadcast.

For Mode 2 the LLM's English is discarded — the user's original English input is authoritative.

---

## 8. Audio (Mode 1 only)

`GET /api/entries/<eid>/audio/<lang>` where `lang ∈ {mandarin, cantonese}`:
- Cache path: `${DATA_DIR}/le_audio/{eid}_{lang}.mp3`.
- Cache miss:
  - `mandarin` → `server_cloud._tts_openai(simp or source_text, "normal")` (OpenAI `gpt-4o-mini-tts`).
  - `cantonese` → `server_cloud._tts_edge(cantonese or trad or source_text, "zh-HK-HiuMaanNeural", "normal")`.
  - Writes bytes to disk.
- Cache hit: `send_file(..., conditional=True)` streams the mp3 with range support.
- Any PATCH / DELETE / Translate on the entry calls `_invalidate_audio(eid)` which deletes both cached files.
- Attempting audio on a Mode 2 entry returns 400.

---

## 9. Live updates (SSE)

`GET /api/stream` opens an `EventSource`. Backend `_Broadcaster` holds a list of `queue.Queue` subscribers; each `publish(event, data)` writes an SSE frame to every queue.

Events emitted:
- `hello` — sent immediately on connect
- `entry.created` / `entry.updated` / `entry.deleted`
- `session.created` / `session.updated` / `session.deleted`
- `:ping` comment every 20 s to keep proxies from timing out

Frontend behavior on each event:
- Entries: patched into `state.entries` and re-rendered; a toast shows when the actor is not the current user.
- Sessions: `loadSessions()` refreshes the picker and re-selects the current session if it still exists.
- Errors: `#live-dot` gains `.offline` class; browsers auto-reconnect via native EventSource retry.

---

## 10. MyPhrases integration (Mode 1 only)

Each Mode 1 entry has a **Save to MyPhrases** button in the entry footer. `POST /api/entries/<eid>/save-to-myphrases` calls `server_cloud.create_capture(...)` directly (no HTTP loopback) with `tags=None`, so MyPhrases's `_auto_tag()` runs inside the same process.

Guards:
- 400 if `mode != "mando_in"`
- 400 if `cantonese` or `english` is empty (must run Translate or hit CEDICT first)
- 409 if `myphrases_saved_at` is already set (idempotent)

On success, sets `myphrases_saved_at` + `myphrases_id` on the LE entry (so the button re-renders as `Saved to MyPhrases` and stays disabled), broadcasts `entry.updated`.

---

## 11. Frontend (`le_static/`)

Vanilla JS SPA, no build step. Files:
- `index.html` — SPA shell (login screen, header, mode toggle, column toggles, add-entry card, results list, new-session modal)
- `styles.css` — dark theme cloned from MyPhrases; Manrope + Noto Sans HK/SC fonts
- `app.js` — full controller (~800 lines): auth, sessions, entries CRUD, inline edit, audio, translate, MyPhrases save, SSE, column-toggle persistence, CSV export

Cache-busting via `?v=YYYYMMDD{letter}` on `styles.css` and `app.js`; bump the letter on every deploy that changes these files.

### UI features

**Header**
- LIVE dot (green when SSE connected, red when disconnected)
- Session picker `<select>` (shows `YYYY-MM-DD · Title (N entries)`)
- **New** button → opens modal (title + date, defaults to today)
- **Delete session** button (trash icon) → confirms with title + entry count; on delete, auto-selects the next available session
- User badge (avatar + name); click → confirm logout (only if `login_required`)

**Mode toggle** — two segmented buttons: `Mandarin → All` and `English → Traditional`. Preference persisted in `localStorage` as `le.mode`.

**Column toggles** — per-user per-mode `localStorage` key `le.cols.{user}.{mode}`. Toggling adds/removes `.hidden-col` on field rows.
- Mode 1 defaults: **Traditional off**, Simplified/Pinyin/Notes on.
- Mode 2 defaults: **Pinyin off**, Simplified/Notes on.

**Add-entry card** — placeholder text + input font (CJK vs Latin) swap per mode; Enter submits.

**Entry cards**
- Meta row: mode tag, author (colour-coded per user), created + optional `translated at` / `edited at` timestamps.
- Field rows: label · value · actions. Click a value to inline-edit (Enter commits, Esc cancels).
- Badges: 📖 `dict` for CEDICT-filled fields, `override` for user-edited fields.
- Mode 1 only: ▶ **Mandarin** button on Simplified row, ▶ **Cantonese** button on Cantonese row (spinner while first-fetch).
- Footer: LLM status badge · Delete · (Mode 1 only) Save to MyPhrases · Translate / Retranslate.

**CSV export (Mode 2 only)** — Ghost `Export CSV` button in the results header when Mode 2 has ≥1 entry.
- Columns: `english, traditional, simplified, pinyin, notes, created_at`.
- Filename: `{session_date}_{sanitized_title}.csv` — punctuation & CJK stripped, spaces/hyphens → `_`, runs collapsed. Example: session "Travel talk!" on 2026-07-24 → `2026-07-24_Travel_talk.csv`.
- UTF-8 with BOM so Excel opens CJK correctly.

---

## 12. Files

```
Yi_Web_App/
├── language_exchange.py       # blueprint (routes, DB, SSE, helpers, LLM/TTS bridges)
├── server_cloud.py            # registers le_bp; exposes translate_text() + create_capture()
├── requirements.txt           # adds opencc-python-reimplemented>=0.1.7, argon2-cffi>=23.1.0
├── .gitignore                 # excludes data/language_exchange.db, data/le_audio/
└── le_static/
    ├── index.html
    ├── styles.css
    └── app.js
```

Runtime data (Railway persistent volume, gitignored):
```
${DATA_DIR}/
├── language_exchange.db       # SQLite WAL
├── language_exchange.db-wal
├── language_exchange.db-shm
└── le_audio/                  # {entry_id}_mandarin.mp3, {entry_id}_cantonese.mp3
```

---

## 13. Environment variables

Required on Railway service (`Yi_TTS` in the Railway UI, deploys `CloverLeafX/yi-web-app`):

| Var | Purpose |
|---|---|
| `LE_USER_KAI_PASSWORD` | **Bootstrap only.** Creates `kai` as admin on first start if the row is missing. Safe to delete after the first successful deploy. |
| `LE_USER_JERRY_PASSWORD` | **Bootstrap only.** Creates `jerry` as member on first start if the row is missing. Safe to delete after the first successful deploy. |
| `SECRET_KEY` | Flask session-cookie signing key (recommend a random 48-char string) |
| `DATA_DIR` | Railway persistent-volume path (already configured for Yi Web App) |
| `GROQ_API_KEY` | LLM translate (llama-3.3-70b-versatile) |
| `OPENAI_API_KEY` | Mandarin TTS (`gpt-4o-mini-tts`) |
| `ADMIN_SECRET` | MyPhrases admin gate (used by `/api/audio/upload`, `/api/captures/:id/repair`) |

Once at least one user row exists, the DB is authoritative — the `LE_USER_*_PASSWORD` env vars are only re-read if that row is deleted. If nobody exists in the DB **and** no `LE_USER_*_PASSWORD` env vars are set (fresh local dev only), the app auto-logs in as `"local"` with implicit admin rights and skips the login screen.

---

## 14. Deploy

Auto-deploy from GitHub (`CloverLeafX/yi-web-app`):
```bash
cd Yi_Web_App && git push origin main
```
Railway rebuilds on every push to `main`. Never use `railway up` — the CLI path is reserved for Lazy Chinese only.

The `Procfile` runs:
```
web: gunicorn wsgi:app --bind "0.0.0.0:$PORT" --workers 1 --threads 4 --timeout 120
```
`--threads 4` is required so concurrent SSE streams and audio range requests don't deadlock.

---

## 15. Local dev

```bash
# One-time install
"/Users/kai/Virtual Envs/Canto_Mando_App/bin/pip" install -r Yi_Web_App/requirements.txt

# Start (auto-logs in as "local" — no LE_USER_* vars needed)
cd Yi_Web_App
"/Users/kai/Virtual Envs/Canto_Mando_App/bin/python" server_cloud.py
# → http://localhost:8801/language-exchange/
```

`GROQ_API_KEY` and `OPENAI_API_KEY` come from `Yi_Web_App/.env`. Deleting `data/language_exchange.db*` gives you a fresh slate.

---

## 16. Not built (out of scope)

- CSV/XLSX import
- Export for Mode 1 (only Mode 2 exports currently)
- Session/entry search UI (backend supports `?q=` but no frontend)
- Public share links
- Bulk operations (multi-delete, bulk retranslate)
- Mobile-optimised layout (works but not tuned)
- Audio for Mode 2 (deliberately excluded per §2)
- Non-Google account switching / password reset UI
