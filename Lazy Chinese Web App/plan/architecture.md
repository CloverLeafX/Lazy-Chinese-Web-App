# Lazy Chinese Web App — Architecture

## Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python Flask | Same as Yi_Web_App; minimal deps; trivial to deploy |
| Frontend | Single HTML file (evolved from `browser.html`) | No build step; already proven |
| State storage | `data/watch_state.json` | Same pattern as Yi_Web_App `captures.json`; survives browser clears |
| Video streaming | Microsoft Graph API → OneDrive CDN URL | Videos already live on SharePoint; browser streams from Microsoft's CDN — Flask never touches video bytes |
| Subtitle serving | Flask proxies local `.srt` files (dev) / Graph API (cloud) | SRT files are small; fine to proxy through Flask |
| Catalog | Merged `download_tracker.json` + `all_videos_*.json` | Maintained by `downloader.py`; no new tooling needed |

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
1. OneDrive CDN     /api/video-url/<id>          ← downloaded MP4s (video_done: true)
2. YouTube embed    youtube.com/embed/<id>         ← YouTube platform videos
3. Bunny embed      iframe.mediadelivery.net        ← member Bunny videos
```

The `download_tracker.json` `video_done` flag and `platform` field determine which source to use.

---

## OneDrive Item ID Remapping

`download_tracker.json` stores local absolute paths. These are mapped to OneDrive item IDs by `build_index.py`.

**Matching strategy:** For each file enumerated from OneDrive, extract the short video ID from the folder name (first component before the `  ` double-space separator, e.g. `l5K9ag0O  Men that we wouldn't date...` → short ID `l5k9ag0o`). Match against `download_tracker.json` entries the same way. This handles OneDrive's special-character sanitization (`?`, `:`, `*` → `_`).

**OneDrive root path:**
```
My Documents OneDrive/Python Apps/Canto_Mando_App/Lazy Chinese/downloads
```

**Delta enumeration:** One paginated pass (12 pages, 1922 files). Result stored in `data/onedrive_index.json`:
```json
{
  "l5K9ag0Ouc8": {
    "mp4_id":    "01ABC…",
    "srt_id":    "01DEF…",
    "srt_tw_id": "01GHI…"
  }
}
```

All 441 tracker entries matched. Re-run via `POST /admin/reindex` after new downloads.

---

## Catalog Merge

On startup, the server:
1. Finds the most recent `all_videos_*.json` (by filename date)
2. Loads `download_tracker.json`
3. Merges by video ID — tracker fields (`video_done`, `srt_done`, `srt_tw_done`, `srt_path`, `folder_path`, `length`) are added to each video object
4. Caches in memory; `/api/catalog` returns the array

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

Writes are protected by a threading lock (same pattern as Yi_Web_App). On first frontend load: JS reads any existing localStorage watch keys, POSTs them to the API, then clears localStorage (one-time migration).

---

## Subtitle Fallback

```
1. Local disk    server reads srt_path / srt_tw_path from tracker
2. Graph API     GET /drives/{id}/items/{srt_id}/content
```

No external CDN fallback — local or Graph API only.

---

## Directory Layout

```
Lazy Chinese Web App/
├── server.py                ← Flask app
├── build_index.py           ← one-time OneDrive remapping script
├── auth_setup.py            ← one-time OAuth token acquisition
├── requirements.txt
├── Procfile                 ← web: python server.py (Railway)
├── .env                     ← credentials (not committed)
├── .gitignore
├── data/
│   ├── watch_state.json     ← persisted watch history
│   ├── onedrive_index.json  ← { video_id → { mp4_id, srt_id, srt_tw_id } }
│   └── tokens.json          ← OAuth tokens (not committed)
├── plan/                    ← these docs
└── static/
    └── index.html           ← (Phase 3) evolved browser.html
```

---

## Environment Variables

```
PORT=8802

# Microsoft Graph API
MS_CLIENT_ID=19d8d3f3-a031-4a3b-b5a2-d66e6dd8c57f
MS_TENANT_ID=143d12ca-c6fe-404f-9e82-b3713b1b18d9
MS_CLIENT_SECRET=<see .env>
MS_DRIVE_ID=b!5PKjL602aEi2J7VzQT-1hRBdWhPnIWFLmP1oSCkcUH_HRTIs11SQTpduEK7Jl4B7
MS_ONEDRIVE_ROOT=My Documents OneDrive/Python Apps/Canto_Mando_App/Lazy Chinese/downloads

DATA_DIR=./data
```

The OAuth refresh token is stored in `data/tokens.json` (on the Railway persistent volume), not in `.env`, so Flask can update it automatically after each token refresh.

---

## Deployment

Flask is lightweight (catalog + watch state + Graph API calls only — no video bytes). Deployed on Railway:

| Mode | Flask | Videos |
|---|---|---|
| Local dev | `localhost:8802` | OneDrive CDN |
| Cloud | Railway (~$5/month) | OneDrive CDN |

Railway Volume mounted at `/data`, `DATA_DIR=/data` set as env var. Holds `watch_state.json`, `onedrive_index.json`, `tokens.json`.
