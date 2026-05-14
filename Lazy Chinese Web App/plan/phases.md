# Lazy Chinese Web App — Implementation Phases

## Phase 1 — Flask Server Core ✓ COMPLETE

**Goal:** Server runs locally. Catalog loads. Watch state persists. Subtitles serve from disk.

### Tasks

- [x] Create `server.py` (based on Yi_Web_App structure)
- [x] `GET /api/catalog` — find most recent `all_videos_*.json`, merge with `download_tracker.json`, return array (441 videos)
- [x] `GET /api/watch-state` — return `data/watch_state.json`
- [x] `POST /api/watch-state/<id>` — upsert `{ watched, lastPosition }` with threading lock
- [x] `DELETE /api/watch-state/<id>` — remove entry
- [x] `GET /subtitle/<id>?script=simplified|traditional` — read `.srt` from tracker path; fallback to Graph API
- [x] `GET /health`
- [x] `requirements.txt`, `.env`

---

## Phase 2 — OneDrive Remapping + Video Streaming ✓ COMPLETE

**Goal:** Every downloaded video has a OneDrive item ID. Videos stream from OneDrive CDN.

### Tasks

**Auth setup (complete):**
- [x] Register Azure AD app in `humecorporation` tenant
  - App ID: `19d8d3f3-a031-4a3b-b5a2-d66e6dd8c57f`
  - Enabled "Allow public client flows" for device code flow (no client_secret in token request)
  - Delegated permissions: `Files.Read`, `Files.Read.All` (tenant admin approved)
- [x] Write `auth_setup.py` — OAuth2 device code flow
  - Discovered Drive ID: `b!5PKjL602aEi2J7VzQT-1hRBdWhPnIWFLmP1oSCkcUH_HRTIs11SQTpduEK7Jl4B7`
  - Writes `data/tokens.json`, updates `.env` with `MS_DRIVE_ID`

**Index build (complete):**
- [x] Write `build_index.py`
  - OneDrive root path: `My Documents OneDrive/Python Apps/Canto_Mando_App/Lazy Chinese/downloads`
  - Delta enumeration: 12 pages, 1922 files found
  - Matching strategy: short video ID prefix (first component before `  ` double-space in folder name)
  - Result: **441/441 videos matched**, `data/onedrive_index.json` written

**Server additions (complete):**
- [x] `_get_access_token()` — auto-refresh from `data/tokens.json` or `MS_TOKENS` env var
- [x] `GET /api/video-url/<id>` — returns `@microsoft.graph.downloadUrl` (Azure CDN, supports Range requests)
- [x] Updated `GET /subtitle/<id>` — local path → Graph API `/content` fallback
- [x] `POST /admin/reindex` — subprocess call to `build_index.py`

**Verified:** `GET /api/video-url/l5K9ag0Ouc8` returns an Azure CDN URL. HEAD request confirms `content-type: video/mp4`, `accept-ranges: bytes`, `content-length: 926631187`.

---

## Phase 3 — Frontend Port ✓ COMPLETE

**Goal:** `browser.html` becomes `static/index.html`, fully backed by the server API.

### Tasks

- [x] Write `static/index.html` — all CSS/HTML identical to `browser.html`, script section fully rewritten
- [x] Replace inline JSON load with `fetch('/api/catalog')` — server returns merged catalog+tracker
- [x] Replace localStorage watch history with `GET/POST/DELETE /api/watch-state/<id>`
- [x] Replace SRT fetch with `fetch('/subtitle/<id>?script=...')` — server handles local+Graph fallback
- [x] Video source logic: `v.video_done` → fetch `/api/video-url/<id>`, YouTube embed, Bunny embed
- [x] One-time localStorage migration: reads `lc_watch_history`, POSTs each watch event to server, sets `lc_migrated=1`
- [x] `GET /` serves `static/index.html`
- [x] Layout fix: transcript panel is side-by-side (right column), not below video
- [x] Captions bar overlaid on video (position absolute, gradient), not a block below it
- [x] `const BASE` detects `/lazy_web_app` prefix for Blueprint mode, falls back to `''` for standalone

**Blueprint mount: abandoned** — chose standalone deploy instead (see D11 in decisions.md).

---

## Phase 4 — Cloud Deploy ✓ COMPLETE

**Goal:** App is accessible from any device via a public URL.

**URL:** `https://lazy-chinese-web-app-production.up.railway.app`

### What was done

- [x] Repo pushed to GitHub (`CloverLeafX/Lazy-Chinese-Web-App`)
- [x] `wsgi.py` at repo root imports `server.app` (avoids shell quoting issues with spaces in dir name)
- [x] `Procfile` at repo root: `web: gunicorn wsgi:app --bind "0.0.0.0:$PORT" --workers 1 --timeout 120`
- [x] `requirements.txt` stripped to Lazy Chinese Web App deps only (no pycantonese, cedict)
- [x] `.railwayignore` excludes `Canto_Mando_Viewer/` (heavy, not needed)
- [x] Data files committed to git: `data/all_videos_2026-04-29.json`, `data/onedrive_index.json`, `data/watch_state.json`
- [x] Railway env vars set: `MS_CLIENT_ID`, `MS_TENANT_ID`, `MS_DRIVE_ID`, `MS_TOKENS` (full token JSON as string)
- [x] `_load_catalog()` updated to fall back to `DATA_DIR` if `Lazy Chinese/` dir absent
- [x] `video_done` now set to `True` for any video with `mp4_id` in `onedrive_index.json` (tracker absent on Railway)
- [x] Smoke tested: catalog loads (441 videos), videos play, subtitles load and sync, watch state reads

**Deviation from original plan:** No Railway Volume. `data/watch_state.json` is committed to git and starts from that snapshot. New watches during a session are written to the ephemeral filesystem and reset on redeploy. See Phase 5 for persistent watch state.

---

## Phase 5 — Quality of Life

**Goal:** Improvements that make the app better than the original `browser.html`.

### Tasks

- [ ] **Persistent watch state** — add Railway Volume at `/data`, set `DATA_DIR=/data`; upload current `watch_state.json` to volume via Railway shell. Until then, watch history resets on each deploy.
- [ ] **Resume position** — save `lastPosition` every 30s via `POST /api/watch-state/<id>`; restore on reopen
- [ ] **Keyboard shortcuts** — Space = play/pause, `[`/`]` = ±5s, `W` = mark watched, `T` = toggle transcript
- [ ] **Stats page** — total watch time, videos per level, % complete per level
- [ ] **Reindex on demand** — button in settings panel to trigger `POST /admin/reindex` after new downloads

---

## Milestone Summary

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Server core: catalog, watch state, subtitles | ✓ Done |
| 2 | OneDrive remapping + video streaming via Graph API | ✓ Done |
| 3 | Full browser port — everything wired to the API | ✓ Done |
| 4 | Cloud deploy — accessible from any device | ✓ Done |
| 5 | Polish + persistent watch state | Pending |
