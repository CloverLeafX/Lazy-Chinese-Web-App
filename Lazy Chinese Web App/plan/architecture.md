# Lazy Chinese Web App — Architecture

## Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python Flask | Same as Yi_Web_App; minimal deps; trivial to deploy |
| Frontend | Single HTML file (evolved from `browser.html`) | No build step; already proven |
| State storage | `data/watch_state.json` | Same pattern as Yi_Web_App `captures.json`; survives browser clears |
| Video streaming | Microsoft Graph API → OneDrive CDN URL | Videos already live on SharePoint; browser streams from Microsoft's CDN — Flask never touches video bytes |
| Subtitle serving | Flask proxies local `.srt` files (dev) / Graph API (cloud) | SRT files are small; fine to proxy through Flask |
| Catalog | Merged `onedrive_index.json` + `all_videos_*.json` (+ `download_tracker.json` if present locally) | Maintained by `downloader.py`; no new tooling needed |

---

## How OneDrive Video Streaming Works

The Microsoft Graph API exposes `@microsoft.graph.downloadUrl` on every file. This is a **pre-authenticated Azure CDN URL** that supports HTTP `Range` requests (so video seeking works natively). The browser's `<video>` element points directly at this URL — Flask never proxies video bytes.

```
Browser                Flask server          Microsoft Graph API
   │                        │                        │
   │  GET /api/video-url/   │                        │
   │  <video_id>            │                        │
   │───────────────────────>│                        │
   │                        │  GET /drives/{id}/     │
   │                        │  items/{itemId}        │
   │                        │───────────────────────>│
   │                        │  { @microsoft.graph.   │
   │                        │    downloadUrl: "…" }  │
   │                        │<───────────────────────│
   │  { url: "https://…" }  │                        │
   │<───────────────────────│                        │
   │                        │                   Microsoft CDN
   │  GET https://… (range) │                        │
   │────────────────────────────────────────────────>│
   │  video stream          │                        │
   │<────────────────────────────────────────────────│
```

URLs expire in ~1 hour. Flask fetches a fresh one each time `/api/video-url/<id>` is called.

---

## API Endpoints

```
GET    /                          → index.html
GET    /health                    → { ok: true, catalog: 441, index: true }
GET    /api/catalog               → merged video list (441 items)
GET    /api/watch-state           → { videoId: { watched, watchedAt, watchCount, lastPosition } }
POST   /api/watch-state/<id>      → upsert { watched, lastPosition }
DELETE /api/watch-state/<id>      → remove entry
GET    /api/video-url/<id>        → { url } — OneDrive CDN URL for the MP4
GET    /subtitle/<id>?script=     → SRT text (simplified or traditional)
POST   /admin/reindex             → rebuild onedrive_index.json from Graph API
```

---

## Video Source Priority

```
1. OneDrive CDN     /api/video-url/<id>          ← any video with mp4_id in onedrive_index.json
2. YouTube embed    youtube.com/embed/<id>         ← YouTube platform videos (no mp4_id)
3. Bunny embed      iframe.mediadelivery.net        ← member Bunny videos (no mp4_id)
```

`video_done` is set to `True` if `download_tracker.json` says so OR if `onedrive_index.json` has an `mp4_id` for that video. On Railway, the tracker doesn't exist so `onedrive_index.json` is the sole source — all 441 videos get `video_done=True`.

---

## Catalog Merge

On startup, the server:
1. Finds the most recent `all_videos_*.json` — first checks `Lazy Chinese/` (local dev), then `data/` (Railway)
2. Loads `download_tracker.json` if present (local dev only; absent on Railway)
3. Loads `onedrive_index.json`
4. Merges by video ID — tracker fields added if available; `video_done` falls back to `mp4_id` presence in OneDrive index
5. Caches in memory; `/api/catalog` returns the array

---

## Watch State

`data/watch_state.json`:
```json
{
  "l5K9ag0Ouc8": {
    "watched": true,
    "watchedAt": "2026-05-02T10:30:00",
    "watchCount": 2,
    "lastPosition": 342.5
  }
}
```

Writes are protected by a threading lock. On first frontend load: JS reads any existing localStorage watch keys, POSTs them to the API, then sets `lc_migrated=1` (one-time migration).

**On Railway (Phase 4):** `watch_state.json` is committed to git and loaded at deploy time. New watches within a session are written to the ephemeral filesystem — they survive the session but reset on the next deploy. A Railway Volume (Phase 5) would make them persistent.

---

## Subtitle Fallback

```
1. Local disk    server reads srt_path / srt_tw_path from download_tracker.json
2. Graph API     GET /drives/{id}/items/{srt_id}/content
```

No external CDN fallback — local or Graph API only.

---

## Directory Layout

```
Canto_Mando_App/               ← repo root
├── wsgi.py                    ← entry point (imports server.app; handles space in dir name)
├── Procfile                   ← web: gunicorn wsgi:app ...
├── requirements.txt           ← Flask, requests, python-dotenv, gunicorn, flask-cors
├── .railwayignore             ← excludes Canto_Mando_Viewer/, Canto_Mando_Videos/, etc.
└── Lazy Chinese Web App/
    ├── server.py              ← Flask app (all API endpoints)
    ├── build_index.py         ← one-time OneDrive remapping script (run locally)
    ├── auth_setup.py          ← one-time OAuth token acquisition (run locally)
    ├── .env                   ← credentials (not committed)
    ├── .gitignore
    ├── data/
    │   ├── watch_state.json       ← committed; watch history starting snapshot
    │   ├── onedrive_index.json    ← committed; { video_id → { mp4_id, srt_id, srt_tw_id } }
    │   ├── all_videos_*.json      ← committed; video catalog from downloader.py
    │   └── tokens.json            ← NOT committed; used locally only
    ├── plan/                  ← these docs
    └── static/
        └── index.html         ← single-page frontend
```

---

## Environment Variables

```
PORT=8802  (local; Railway sets this automatically)

# Microsoft Graph API
MS_CLIENT_ID=19d8d3f3-a031-4a3b-b5a2-d66e6dd8c57f
MS_TENANT_ID=143d12ca-c6fe-404f-9e82-b3713b1b18d9
MS_DRIVE_ID=b!5PKjL602aEi2J7VzQT-1hRBdWhPnIWFLmP1oSCkcUH_HRTIs11SQTpduEK7Jl4B7
MS_ONEDRIVE_ROOT=My Documents OneDrive/Python Apps/Canto_Mando_App/Lazy Chinese/downloads

# Token storage — mutually exclusive:
#   Local dev:   data/tokens.json (written by auth_setup.py; auto-refreshed by server)
#   Railway:     MS_TOKENS env var (JSON string; server reads it directly, refreshes in-memory)
MS_TOKENS=<full token JSON as string>  ← Railway only

DATA_DIR=./data  (or absolute path if set)
```

---

## Deployment

Flask is lightweight (catalog + watch state + Graph API calls only — no video bytes).

| Mode | Entry point | URL |
|---|---|---|
| Local dev | `python "Lazy Chinese Web App/server.py"` | `localhost:8802` |
| Railway | `gunicorn wsgi:app` | `lazy-chinese-web-app-production.up.railway.app` |

Videos always stream from Microsoft's OneDrive CDN regardless of environment.
