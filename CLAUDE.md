# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Three Apps, Two Repos

This folder contains three distinct apps. The Viewer and Lazy Chinese share the main git root; the Yi Web App has its own git repo nested at `Yi_Web_App/`.

| App | Entry point | Port | Deployed? | Git repo |
|-----|-------------|------|-----------|----------|
| **Canto-Mando Viewer** | `Canto_Mando_Viewer/server.py` | 8800 | No — local only | this repo |
| **Lazy Chinese Web App** | `Lazy Chinese Web App/server.py` | 8802 (local) | Yes — Railway via `wsgi.py` | this repo |
| **Yi Web App (MyPhrases)** | `Yi_Web_App/server_cloud.py` | — | Yes — Railway, auto-deploy on push | `CloverLeafX/yi-web-app` |

The Viewer mounts the Lazy Chinese app as a Flask Blueprint (`lazy_bp`) at `/lazy_web_app`. In production, only the Lazy Chinese app runs (via `wsgi.py` → `Lazy Chinese Web App/server.py`).

## Running Locally

```bash
# Start the Viewer (kills any existing process on :8800, polls /health, opens browser)
cd "Canto_Mando_Viewer"
bash start.sh

# Manual start (no launcher)
"/Users/kai/Virtual Envs/Canto_Mando_App/bin/python3" Canto_Mando_Viewer/server.py

# Stop
curl -X POST http://localhost:8800/api/shutdown
# or Ctrl+C in the start.sh terminal
```

## Python Environment

Venv: `/Users/kai/Virtual Envs/Canto_Mando_App`

```bash
# Install all local deps (run after any git pull that changes requirements-local.txt)
"/Users/kai/Virtual Envs/Canto_Mando_App/bin/pip" install -r requirements-local.txt
```

- `requirements.txt` — production only (Flask, gunicorn, requests, python-dotenv, flask-cors)
- `requirements-local.txt` — extends the above with TTS engines, NLP libs, setproctitle

Missing `setproctitle` or any other local dep causes the server to crash silently on launch via the macOS app bundle.

## Environment Variables

Single `.env` at the repo root (`Canto_Mando_App/.env`), read by both servers. Required key:
- `GROQ_API_KEY` — translation via Groq (llama-3.3-70b-versatile); server fails gracefully without it
- `OPENAI_API_KEY` — optional; enables OpenAI TTS and is used for vocabulary captures

The Lazy Chinese Web App also reads `MS_CLIENT_ID`, `MS_TENANT_ID`, `MS_DRIVE_ID`, `AUTH_PASSWORD`, `SECRET_KEY` from `.env`.

## Architecture: Canto-Mando Viewer

**Folder scanning** (`Canto_Mando_Viewer/server.py` `_build_structure()`): Auto-discovers all `Chapter_*` folders under the repo root on every `/api/structure` request. Skips folders listed in `_SKIP`. Files within each lesson folder are detected by extension (`.mp4`, `.mp3`, `.pdf`, `README.md`, images).

**Translation** (`/api/translate`): Calls Groq. Pinyin in the LLM response is always discarded and regenerated from `pypinyin` due to hallucination.

**TTS** (`/api/tts`): Default engine is Edge TTS with gTTS fallback. Engine priority: `edge` → `gtts` → `openai` → `google`. Vocabulary captures auto-generate audio using OpenAI TTS (Mandarin) and Edge TTS (Cantonese).

**Dictionary** (`cedict.py`): CC-CEDICT loaded from `data/cedict_ts.u8`. Supports exact lookup (`/api/dict`) and greedy segmentation (`/api/dict/segment`).

**Gitignored data files** (machine-local, never commit): `notes.json`, `hidden.json`, `captures.json`, `watch_state.json`, `lc_watch_history.json`, `data/audio_captures/`, `data/image_cache/`.

## Architecture: Lazy Chinese Web App

Streams video from OneDrive via Microsoft Graph API. Auth is a simple shared password (`AUTH_PASSWORD`) stored in a Flask session — the `login_required` decorator is bypassed when `AUTH_PASSWORD` is unset (local dev). OneDrive tokens are refreshed using MSAL credentials. The video index is built by `build_index.py` and stored at `data/onedrive_index.json`.

On Railway, `DATA_DIR` is set to a persistent volume path; on first start it seeds the volume by copying `data/onedrive_index.json` and `data/watch_state.json` from the bundled `data/` directory.

### Xiao Gua (XG) Integration

The LC web app also serves the Xiao Gua catalog (`xiaogua/` folder, sibling to LC). Routes:
- `/api/xiaogua/catalog` — returns 250 XG videos with `video_done`, `codec`, `youtubeId`, `access`, etc.
- `/api/xiaogua/stream/<slug>` — **proxy** that streams the OneDrive mp4 through Railway. This is required because `@microsoft.graph.downloadUrl` for OneDrive for Business returns a SharePoint URL that requires browser-side SharePoint auth (silently fails as `vid.src`). The proxy forwards `Range` headers and caches the download URL for 30 minutes per slug.
- `/api/xiaogua/video-url/<slug>` — legacy direct-URL endpoint (kept for compatibility; not used by frontend).
- `/subtitle/<slug>` — falls back to local SRT files under `xiaogua/videos/{level}/{slug}/{slug}.zh-Hans.srt` (simplified, with pinyin) or `.zh.srt` (traditional).

**Codec compatibility**: `xiaogua/data/onedrive_index.json` stores a `codec` field per entry (`h264`, `av1`, `hevc`, `unknown`). ~105 of 250 XG videos are AV1-encoded, which Safari cannot play. The frontend detects Safari + AV1 and shows an unsupported message rather than spinning forever. Rebuild the index with `python xiaogua/build_onedrive_index.py` — it preserves known codecs and only detects new entries.

**XG SRT files** are committed to the repo (gitignore allows `xiaogua/videos/**/*.srt` but excludes `*.mp4`) so they ship with Railway.

## Architecture: Yi Web App (MyPhrases)

A standalone Flask app at `Yi_Web_App/` deployed separately to Railway. URL: `https://web-production-79e1c.up.railway.app`.

**Deploy**: `cd Yi_Web_App && git push origin main` — Railway auto-deploys. NEVER use `railway up`.

**MyPhrases PWA** (`Yi_Web_App/myphrases/`): served at `/phrases/`. Shows a searchable card library of saved phrases with per-character phonetic stacks (pinyin for Mandarin, jyutping for Cantonese), hover word definitions, audio playback, tagging, favourites, and inline editing.

**Captures**: stored in `Yi_Web_App/data/captures.json` on a Railway persistent volume. New captures get UTC timestamps (`datetime.now(timezone.utc)`) and are auto-tagged via Groq (`_auto_tag()` in `server_cloud.py`).

**Phonetic display**: Each Han character is wrapped in a `.char-stack` (inline-flex column): character on top, phonetic below. Segments + CEDICT lookups fetched via `POST /api/dict/segment` — both Mandarin and Cantonese pre-warmed in parallel on page load. Hover tooltip on `.word-seg` spans shows pinyin + English definitions.

**Admin secret**: stored in `Yi_Web_App/.env` as `ADMIN_SECRET`. Required for `/api/audio/upload` and `/api/captures/:id/repair`.

**Version cache-busting**: `app.js?v=YYYYMMDD{letter}` and `styles.css?v=YYYYMMDD{letter}` — bump the letter on every deploy that changes these files.

## Railway Deployment

The `Procfile` runs `wsgi.py` (Lazy Chinese Web App only — Viewer does not deploy):
```
web: gunicorn wsgi:app --bind "0.0.0.0:$PORT" --workers 1 --threads 4 --timeout 120
```

`--threads 4` is required so concurrent video range requests don't deadlock when the browser pre-buffers / seeks XG streams (proxied through `/api/xiaogua/stream/<slug>`).

`SECRET_KEY` must be set as a persistent Railway env var or sessions reset on every redeploy.

## Detailed Reference

`_MASTER_REFERENCE/` contains exhaustive documentation:
- `04_SERVER_ARCHITECTURE.md` — all API routes, TTS engines, env vars, known issues
- `01_PLATFORM_API.md` — CMB platform auth and API endpoints
- `02_EXTRACTION_WORKFLOW.md` — how to download new course videos
- `05_ADDING_CONTENT.md` — how to add new lessons or CM SCHOOL vocabulary blocks
