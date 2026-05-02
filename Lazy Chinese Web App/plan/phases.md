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
- [x] `_get_access_token()` — auto-refresh from `data/tokens.json`
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

### Architecture decision: mount under existing server

User wants the app at `http://localhost:8800/lazy` (the Canto→Mando server), not a separate port.

**Plan (in progress — interrupted):**
- [x] `Lazy Chinese Web App/server.py` — add `lazy_bp = Blueprint("lazy", __name__)`, convert all routes to blueprint, register on standalone `app` for port 8802 use
- [ ] `Canto_Mando_Viewer/server.py` — import `lazy_bp` via importlib, mount at `url_prefix="/lazy"`, remove old `/lazy*` routes
- [ ] `static/index.html` — add `const BASE = window.location.pathname.startsWith('/lazy') ? '/lazy' : ''` and prefix all fetch calls

**Additional decision:** User wants to fully migrate off locally-hosted `.mp4` files — all video playback via OneDrive CDN only. This simplifies `setupPlayer`: no local file path needed, always use `v.video_done` → `/api/video-url/<id>` or embed.

**Done when:** `http://localhost:8800/lazy` works identically to `http://localhost:8802/`.

---

## Phase 4 — Cloud Deploy

**Goal:** App is accessible from any device via a public URL.

### Tasks

- [ ] Push project to a GitHub repo (Railway deploys from GitHub)
- [ ] Create Railway project → connect GitHub repo → Railway auto-detects Python
- [ ] Add a Railway Volume mounted at `/data`, set `DATA_DIR=/data` in Railway env vars
- [ ] Set Railway env vars: `MS_CLIENT_ID`, `MS_TENANT_ID`, `MS_DRIVE_ID`, `MS_ONEDRIVE_ROOT`, `MS_CLIENT_SECRET`, `PORT`
- [ ] Upload `data/` files (watch_state.json, onedrive_index.json, tokens.json) to the Railway volume via Railway shell
- [ ] Smoke test: open Railway URL, browse catalog, play a video, mark watched

**Note:** `Procfile` already exists: `web: python server.py`

**Done when:** Watching a video on phone and laptop both update the same watch state.

**Cost:** Railway Hobby plan ~$5/month. The app is tiny (no video proxying) so it'll use minimal resources.

---

## Phase 5 — Quality of Life

**Goal:** Improvements that make the app better than the original `browser.html`.

### Tasks

- [ ] **Resume position** — save `lastPosition` every 30s via `POST /api/watch-state/<id>`; restore on reopen
- [ ] **Unavailable badge** — if `video_done: false`, show a cloud icon on the card instead of hiding it
- [ ] **Notes panel** — if `notes_path` exists, add a Notes tab in the watch view that renders the `.md` as HTML
- [ ] **Keyboard shortcuts** — Space = play/pause, `[`/`]` = ±5s, `W` = mark watched, `T` = toggle transcript
- [ ] **Stats page** — total watch time, videos per level, % complete per level
- [ ] **Reindex on demand** — button in settings panel to trigger `POST /admin/reindex` after new downloads

---

## Milestone Summary

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Server core: catalog, watch state, subtitles | ✓ Done |
| 2 | OneDrive remapping + video streaming via Graph API | ✓ Done |
| 3 | Full browser port — everything wired to the API | ✓ Done (mount in progress) |
| 4 | Cloud deploy — accessible from any device | Pending |
| 5 | Polish | Pending |
