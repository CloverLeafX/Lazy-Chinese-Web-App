# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Two Apps, One Repo

This repo has two distinct Flask apps sharing a git root:

| App | Entry point | Port | Deployed? |
|-----|-------------|------|-----------|
| **Canto-Mando Viewer** | `Canto_Mando_Viewer/server.py` | 8800 | No — local only |
| **Lazy Chinese Web App** | `Lazy Chinese Web App/server.py` | 8802 (local) | Yes — Railway via `wsgi.py` |

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

Streams video from OneDrive via Microsoft Graph API. Auth is a simple shared password (`AUTH_PASSWORD`) stored in a Flask session. OneDrive tokens are refreshed using MSAL credentials. The video index is built by `build_index.py` and stored at `data/onedrive_index.json`.

On Railway, `DATA_DIR` is set to a persistent volume path; on first start it seeds the volume by copying `data/onedrive_index.json` and `data/watch_state.json` from the bundled `data/` directory.

## Railway Deployment

The `Procfile` runs `wsgi.py` (Lazy Chinese Web App only — Viewer does not deploy):
```
web: gunicorn wsgi:app --bind "0.0.0.0:$PORT" --workers 1 --timeout 120
```

`SECRET_KEY` must be set as a persistent Railway env var or sessions reset on every redeploy.

## Detailed Reference

`_MASTER_REFERENCE/` contains exhaustive documentation:
- `04_SERVER_ARCHITECTURE.md` — all API routes, TTS engines, env vars, known issues
- `01_PLATFORM_API.md` — CMB platform auth and API endpoints
- `02_EXTRACTION_WORKFLOW.md` — how to download new course videos
- `05_ADDING_CONTENT.md` — how to add new lessons or CM SCHOOL vocabulary blocks
