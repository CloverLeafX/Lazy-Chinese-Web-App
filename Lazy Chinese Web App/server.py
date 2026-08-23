#!/usr/bin/env python3
"""
Lazy Chinese Web App — Flask server
"""
import glob, html as _html, json, os, re, secrets as _secrets, subprocess, sys, threading, time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")   # root — shared keys
try:
    load_dotenv(Path(__file__).parent / ".env")       # local — app-specific overrides (may be cloud-only on OneDrive)
except Exception:
    pass

import requests as _req
from flask import (Blueprint, Flask, Response, abort, jsonify, redirect,
                   request, send_file, session as flask_session, url_for)
from flask_cors import CORS

# ── Config ────────────────────────────────────────────────────────────────────

HERE           = Path(__file__).parent
LAZY_CHINESE   = HERE.parent / "Lazy Chinese"
STATIC_DIR     = HERE / "static"
_dd = os.environ.get("DATA_DIR", "")
DATA_DIR       = (Path(_dd) if Path(_dd).is_absolute() else HERE / "data") if _dd else HERE / "data"
PORT           = int(os.environ.get("PORT", 8802))

TRACKER_PATH   = LAZY_CHINESE / "download_tracker.json"
WATCH_STATE    = DATA_DIR / "watch_state.json"
ONEDRIVE_INDEX   = DATA_DIR / "onedrive_index.json"
TOKENS_PATH      = DATA_DIR / "tokens.json"
XIAOGUA_DIR      = HERE.parent / "xiaogua"
XIAOGUA_INDEX    = XIAOGUA_DIR / "data" / "video_index.json"
XIAOGUA_OD_INDEX = XIAOGUA_DIR / "data" / "onedrive_index.json"

MS_CLIENT_ID    = os.environ.get("MS_CLIENT_ID", "")
MS_TENANT_ID    = os.environ.get("MS_TENANT_ID", "")
MS_DRIVE_ID     = os.environ.get("MS_DRIVE_ID", "")
TOKEN_URL       = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"
GRAPH           = "https://graph.microsoft.com/v1.0"

AUTH_PASSWORD  = os.environ.get("AUTH_PASSWORD", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

DATA_DIR.mkdir(exist_ok=True)

# Seed volume from bundled data on first start (only when DATA_DIR differs from repo data/)
_bundled_data = HERE / "data"
if DATA_DIR != _bundled_data:
    import shutil as _shutil
    # onedrive_index.json: always overwrite so new deploys pick up fresh index
    for _fname in ("onedrive_index.json",):
        _src, _dst = _bundled_data / _fname, DATA_DIR / _fname
        if _src.exists():
            _shutil.copy2(_src, _dst)
    # watch_state.json: seed only on first start (preserves user watch history)
    for _fname in ("watch_state.json",):
        _src, _dst = _bundled_data / _fname, DATA_DIR / _fname
        if _src.exists() and not _dst.exists():
            _shutil.copy2(_src, _dst)

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
# Restrict CORS to the Railway deployment origin in production; allow all locally.
_railway_origin = os.environ.get("RAILWAY_STATIC_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
if _railway_origin and not _railway_origin.startswith("http"):
    _railway_origin = f"https://{_railway_origin}"
if _railway_origin:
    CORS(app, origins=[_railway_origin])
else:
    CORS(app)
app.secret_key = os.environ.get("SECRET_KEY", _secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RAILWAY_ENVIRONMENT")),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

_lock       = threading.Lock()
_token_lock = threading.Lock()
_en_cache   = {}

lazy_bp = Blueprint("lazy", __name__)

# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if AUTH_PASSWORD and not flask_session.get("logged_in"):
            return redirect(url_for("lazy.login"))
        return f(*args, **kwargs)
    return decorated

@lazy_bp.route("/login", methods=["GET", "POST"])
def login():
    if flask_session.get("logged_in"):
        return redirect(url_for("lazy.index"))
    error = ""
    if request.method == "POST":
        if AUTH_PASSWORD and request.form.get("password") == AUTH_PASSWORD:
            flask_session.permanent = True
            flask_session["logged_in"] = True
            return redirect(url_for("lazy.index"))
        error = "Incorrect password."
    html = (STATIC_DIR / "login.html").read_text()
    html = html.replace("<!--ERROR-->", f'<p class="error">{error}</p>' if error else "")
    return html, (401 if error else 200)

@lazy_bp.route("/logout")
def logout():
    flask_session.clear()
    return redirect(url_for("lazy.login"))

# ── Catalog ───────────────────────────────────────────────────────────────────

def _load_catalog() -> list:
    candidates = []
    for search_dir in (LAZY_CHINESE, DATA_DIR, HERE / "data"):
        candidates += sorted(glob.glob(str(search_dir / "all_videos_*.json")), reverse=True)
    videos_text = None
    for path in candidates:
        try:
            videos_text = Path(path).read_text()
            break
        except OSError:
            continue  # cloud-only OneDrive placeholder or other read error — try next
    if not videos_text:
        return []
    videos  = json.loads(videos_text)
    try:
        tracker = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {}
    except OSError:
        tracker = {}

    od_idx = _load_onedrive_index()

    for v in videos:
        t = tracker.get(v["id"], {})
        v["video_done"]  = t.get("video_done", False) or bool(od_idx.get(v["id"], {}).get("mp4_id"))
        v["srt_done"]    = t.get("srt_done", False)
        v["srt_tw_done"] = t.get("srt_tw_done", False)
        v["srt_path"]    = t.get("srt_path")
        v["srt_tw_path"] = t.get("srt_tw_path")
        v["folder_path"] = t.get("folder_path")
        v["length"]      = v.get("length") or t.get("length", "")
    return videos

_catalog: list = []

def _ensure_catalog():
    global _catalog
    if not _catalog:
        _catalog = _load_catalog()

# ── Watch state ───────────────────────────────────────────────────────────────

def _load_watch_state() -> dict:
    return json.loads(WATCH_STATE.read_text()) if WATCH_STATE.exists() else {}

def _save_watch_state(state: dict):
    with _lock:
        WATCH_STATE.write_text(json.dumps(state, indent=2))

# ── Graph API / OneDrive ──────────────────────────────────────────────────────

def _load_tokens() -> dict:
    # Prefer the persisted file: refresh tokens rotate on every use, and the
    # file reflects the latest rotation while MS_TOKENS is a static snapshot
    # that goes stale (and gets rejected by Microsoft) after a restart.
    if TOKENS_PATH.exists():
        return json.loads(TOKENS_PATH.read_text())
    ms_tokens_env = os.environ.get("MS_TOKENS")
    if ms_tokens_env:
        return json.loads(ms_tokens_env)
    raise RuntimeError("MS_TOKENS env var or data/tokens.json not found")

# In-memory token cache so Railway (no persistent TOKENS_PATH) tracks expiry
# across requests within the same worker process.
_cached_tokens: dict | None = None

def _get_access_token() -> str:
    global _cached_tokens
    with _token_lock:
        if _cached_tokens is None:
            _cached_tokens = _load_tokens()
        if time.time() < _cached_tokens.get("expires_at", 0):
            return _cached_tokens["access_token"]

        r = _req.post(TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "refresh_token": _cached_tokens["refresh_token"],
            "client_id":     MS_CLIENT_ID,
            "scope":         "Files.Read offline_access User.Read",
        })
        r.raise_for_status()
        data = r.json()
        _cached_tokens["access_token"]  = data["access_token"]
        _cached_tokens["refresh_token"] = data.get("refresh_token", _cached_tokens["refresh_token"])
        _cached_tokens["expires_at"]    = time.time() + data.get("expires_in", 3600) - 60
        # Always persist the rotated refresh_token to disk (creating the file
        # if needed) so the next restart picks up the latest rotation instead
        # of falling back to a stale MS_TOKENS env var.
        TOKENS_PATH.write_text(json.dumps(_cached_tokens, indent=2))
        return _cached_tokens["access_token"]

def _graph_download_url(item_id: str) -> str:
    token = _get_access_token()
    r = _req.get(
        f"{GRAPH}/drives/{MS_DRIVE_ID}/items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    url = r.json().get("@microsoft.graph.downloadUrl")
    if not url:
        raise RuntimeError(f"No downloadUrl for item {item_id}")
    return url

def _graph_file_text(item_id: str) -> str:
    token = _get_access_token()
    r = _req.get(
        f"{GRAPH}/drives/{MS_DRIVE_ID}/items/{item_id}/content",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.text

def _load_onedrive_index() -> dict:
    return json.loads(ONEDRIVE_INDEX.read_text()) if ONEDRIVE_INDEX.exists() else {}

# ── Subtitle helpers ──────────────────────────────────────────────────────────

def _read_local_srt(rel_path) -> str | None:
    if not rel_path:
        return None
    full = LAZY_CHINESE / rel_path
    return full.read_text(encoding="utf-8") if full.exists() else None


def _extract_json_array(raw: str) -> list[str]:
    """Extract a JSON array from model output, tolerating extra wrapper text."""
    # Try parsing the whole response first
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed]
        # If it's a dict with a "translations" or "lines" key, use that
        if isinstance(parsed, dict):
            for key in ("translations", "lines", "results"):
                if key in parsed and isinstance(parsed[key], list):
                    return [str(x).strip() for x in parsed[key]]
    except json.JSONDecodeError:
        pass
    
    # Fall back to finding JSON array with regex
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in translation response")
    
    try:
        parsed = json.loads(match.group())
        if not isinstance(parsed, list):
            raise ValueError("Translation response was not a JSON array")
        return [str(x).strip() for x in parsed]
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON array: {e}")


def _translate_english_batch(lines: list[str]) -> list[str]:
    """Translate Chinese subtitle lines into concise natural English."""
    if not lines:
        return []

    prompt = (
        "You are a strict subtitle translation engine. "
        "Translate each Chinese subtitle line to natural, concise English while preserving tone and intent. "
        "Return ONLY a JSON array of strings in the same order and same length as input."
    )

    if OPENAI_API_KEY:
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            json={
                "model": "gpt-4o-mini",
                "temperature": 0.1,
                "max_tokens": 1600,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps(lines, ensure_ascii=False)},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        out = _extract_json_array(raw)
        if len(out) != len(lines):
            # If API returns fewer items, pad with empty strings instead of failing
            if len(out) < len(lines):
                print(f"WARNING: API returned {len(out)} translations for {len(lines)} lines, padding", file=sys.stderr)
                out = out + [""] * (len(lines) - len(out))
            else:
                out = out[:len(lines)]
        return out

    raise RuntimeError("No translation provider configured (set OPENAI_API_KEY)")

# ── Routes ────────────────────────────────────────────────────────────────────

@lazy_bp.route("/")
@login_required
def index():
    return send_file(STATIC_DIR / "index.html")

@lazy_bp.route("/health")
def health():
    return jsonify({"ok": True, "catalog": len(_catalog), "index": ONEDRIVE_INDEX.exists(), "data_dir": str(DATA_DIR)})

@lazy_bp.route("/api/catalog")
@login_required
def api_catalog():
    _ensure_catalog()
    return jsonify(_catalog)

@lazy_bp.route("/api/watch-state", methods=["GET"])
@login_required
def api_watch_state_get():
    return jsonify(_load_watch_state())

@lazy_bp.route("/api/watch-state/<video_id>", methods=["POST"])
@login_required
def api_watch_state_post(video_id):
    body  = request.get_json(force=True) or {}
    state = _load_watch_state()
    entry = state.get(video_id, {})
    if "watched" in body:
        entry["watched"]    = bool(body["watched"])
        entry["watchedAt"]  = body.get("watchedAt") or time.strftime("%Y-%m-%dT%H:%M:%S")
        entry["watchCount"] = entry.get("watchCount", 0) + (1 if body["watched"] else 0)
    if "lastPosition" in body:
        entry["lastPosition"] = float(body["lastPosition"])
    state[video_id] = entry
    _save_watch_state(state)
    return jsonify({"ok": True})

@lazy_bp.route("/api/watch-state/<video_id>", methods=["PATCH"])
@login_required
def api_watch_state_patch(video_id):
    """Directly set fields on a watch-state entry without side-effects (e.g. no watchCount increment)."""
    body  = request.get_json(force=True) or {}
    state = _load_watch_state()
    entry = state.get(video_id, {}) if video_id in state else {}
    for field in ("watched", "watchedAt", "watchCount", "lastPosition"):
        if field in body:
            entry[field] = body[field]
    # Allow patching _yt sub-fields (title, level, length)
    if "_yt" in body and isinstance(body.get("_yt"), dict):
        yt = entry.get("_yt", {})
        for k in ("title", "level", "length", "youtubeId"):
            if k in body["_yt"]:
                yt[k] = body["_yt"][k]
        entry["_yt"] = yt
    state[video_id] = entry
    _save_watch_state(state)
    return jsonify({"ok": True})

@lazy_bp.route("/api/watch-state/<video_id>", methods=["DELETE"])
@login_required
def api_watch_state_delete(video_id):
    state = _load_watch_state()
    state.pop(video_id, None)
    _save_watch_state(state)
    return jsonify({"ok": True})

# ── YouTube manual entries ────────────────────────────────────────────────────

_YT_LEVELS = [
    "Complete Beginner", "Beginner", "Low Intermediate",
    "Intermediate", "High Intermediate", "Advanced",
]

def _fetch_yt_meta(video_id: str) -> dict:
    """Fetch title and duration via yt-dlp (falls back to oEmbed for title)."""
    title  = ""
    length = ""
    # Try yt-dlp first — most reliable
    try:
        import yt_dlp
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                    "youtube_include_dash_manifest": False, "extract_flat": False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        title = info.get("title", "")
        secs  = int(info.get("duration") or 0)
        if secs:
            length = f"{secs // 60}:{secs % 60:02d}"
        return {"title": title, "length": length}
    except Exception:
        pass
    # Fallback: oEmbed for title, page scrape for duration
    try:
        r = _req.get(
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
            timeout=10,
        )
        if r.ok:
            title = r.json().get("title", "")
    except Exception:
        pass
    try:
        r = _req.get(
            f"https://www.youtube.com/watch?v={video_id}",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        )
        if r.ok:
            pg = r.text
            if not title:
                m = re.search(r'<meta property="og:title" content="([^"]*)"', pg)
                if m:
                    title = _html.unescape(m.group(1))
            for pat in (r'"lengthSeconds":"(\d+)"', r'"length_seconds":"(\d+)"'):
                dur_m = re.search(pat, pg)
                if dur_m:
                    secs   = int(dur_m.group(1))
                    length = f"{secs // 60}:{secs % 60:02d}"
                    break
    except Exception:
        pass
    return {"title": title, "length": length}

@lazy_bp.route("/api/yt-entry", methods=["POST"])
@login_required
def api_yt_entry():
    body  = request.get_json(force=True) or {}
    url   = body.get("url", "").strip()
    level = body.get("level", "").strip()
    if level not in _YT_LEVELS:
        return jsonify({"error": "Invalid level"}), 400
    m = re.search(r'(?:v=|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})', url)
    if not m:
        return jsonify({"error": "Invalid YouTube URL — could not extract video ID"}), 400
    video_id = m.group(1)
    meta  = _fetch_yt_meta(video_id)
    state = _load_watch_state()
    key   = f"yt_{video_id}"
    existing = state.get(key, {})
    state[key] = {
        "watched":    True,
        "watchedAt":  datetime.now(timezone.utc).isoformat(),
        "watchCount": existing.get("watchCount", 0) + 1,
        "_yt": {
            "title":     meta.get("title", ""),
            "level":     level,
            "length":    meta.get("length", ""),
            "youtubeId": video_id,
        },
    }
    _save_watch_state(state)
    return jsonify({
        "ok":       True,
        "title":    meta.get("title", ""),
        "length":   meta.get("length", ""),
        "youtubeId": video_id,
        "error":    meta.get("error", ""),
    })

@lazy_bp.route("/api/video-url/<video_id>")
@login_required
def api_video_url(video_id):
    idx = _load_onedrive_index()
    entry = idx.get(video_id)
    if not entry or not entry.get("mp4_id"):
        abort(404)
    try:
        url = _graph_download_url(entry["mp4_id"])
        return jsonify({"url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@lazy_bp.route("/api/xiaogua/catalog")
@login_required
def api_xiaogua_catalog():
    if not XIAOGUA_INDEX.exists():
        return jsonify([])
    videos = json.loads(XIAOGUA_INDEX.read_text())
    od_idx = json.loads(XIAOGUA_OD_INDEX.read_text()) if XIAOGUA_OD_INDEX.exists() else {}
    result = []
    for v in videos:
        slug = v.get("slug", "")
        mins = v.get("minutes") or 0
        od_entry = od_idx.get(slug, {})
        result.append({
            "id":         slug,
            "title":      v.get("title", ""),
            "level":      v.get("level", ""),
            "teacher":    ", ".join(v.get("teachers", [])),
            "platform":   "",
            "length":     f"{mins}:00",
            "uploadDate": v.get("date", ""),
            "video_done": bool(od_entry.get("mp4_id")),
            "codec":      od_entry.get("codec", ""),
            "source":     "xiaogua",
            "youtubeId":  v.get("youtubeId", ""),
            "access":     v.get("access", ""),
        })
    return jsonify(result)

@lazy_bp.route("/api/xiaogua/video-url/<slug>")
@login_required
def api_xiaogua_video_url(slug):
    od_idx = json.loads(XIAOGUA_OD_INDEX.read_text()) if XIAOGUA_OD_INDEX.exists() else {}
    entry  = od_idx.get(slug)
    if not entry or not entry.get("mp4_id"):
        abort(404)
    try:
        url = _graph_download_url(entry["mp4_id"])
        return jsonify({"url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 502

# Cache XG download URLs to avoid repeated Graph API calls on every range request
_xg_url_cache: dict = {}  # slug -> (url, expires_at)

@lazy_bp.route("/api/xiaogua/stream/<slug>")
@login_required
def api_xiaogua_stream(slug):
    """Proxy XG video through Railway to avoid SharePoint browser-auth issues."""
    od_idx = json.loads(XIAOGUA_OD_INDEX.read_text()) if XIAOGUA_OD_INDEX.exists() else {}
    entry  = od_idx.get(slug)
    if not entry or not entry.get("mp4_id"):
        abort(404)
    try:
        now = time.time()
        cached = _xg_url_cache.get(slug)
        if cached and cached[1] > now:
            download_url = cached[0]
        else:
            download_url = _graph_download_url(entry["mp4_id"])
            _xg_url_cache[slug] = (download_url, now + 1800)  # 30-min cache
        range_hdr = request.headers.get("Range")
        req_hdrs  = {"Range": range_hdr} if range_hdr else {}
        r = _req.get(download_url, headers=req_hdrs, stream=True, timeout=60)
        resp_hdrs = {}
        for h in ("Content-Type", "Content-Length", "Content-Range",
                  "Accept-Ranges", "ETag", "Last-Modified"):
            if h in r.headers:
                resp_hdrs[h] = r.headers[h]
        resp_hdrs.setdefault("Accept-Ranges", "bytes")
        return Response(r.iter_content(chunk_size=65536),
                        status=r.status_code, headers=resp_hdrs)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@lazy_bp.route("/api/karaoke/cues/<video_id>")
@login_required
def api_karaoke_cues(video_id):
    """Return pre-generated word-level karaoke JSON stored alongside the source files."""
    try:
        tracker = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {}
    except OSError:
        tracker = {}
    entry = tracker.get(video_id, {})
    folder = entry.get("folder_path", "")
    title  = entry.get("title", "")
    if folder and title:
        path = Path(folder) / f"{title}_karaoke.json"
        if path.exists():
            return path.read_text(encoding="utf-8"), 200, {"Content-Type": "application/json"}
    # Fallback: bundled karaoke files committed to the repo under data/karaoke/
    bundled = HERE / "data" / "karaoke" / f"{video_id}.json"
    if bundled.exists():
        return bundled.read_text(encoding="utf-8"), 200, {"Content-Type": "application/json"}
    abort(404)


@lazy_bp.route("/subtitle/<video_id>")
@login_required
def subtitle(video_id):
    script  = request.args.get("script", "simplified")
    try:
        tracker = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {}
    except OSError:
        tracker = {}
    t       = tracker.get(video_id, {})

    rel_path = t.get("srt_tw_path") if script == "traditional" else t.get("srt_path")
    srt_text = _read_local_srt(rel_path)
    if srt_text:
        return srt_text, 200, {"Content-Type": "text/plain; charset=utf-8"}

    idx   = _load_onedrive_index()
    entry = idx.get(video_id, {})
    key   = "srt_tw_id" if script == "traditional" else "srt_id"
    if entry.get(key):
        try:
            srt_text = _graph_file_text(entry[key])
            return srt_text, 200, {"Content-Type": "text/plain; charset=utf-8"}
        except Exception:
            pass

    # ── Xiaogua: look for local SRT in xiaogua/videos/{level}/{slug}/
    if XIAOGUA_INDEX.exists():
        xg_videos = json.loads(XIAOGUA_INDEX.read_text())
        xg_entry  = next((v for v in xg_videos if v.get("slug") == video_id), None)
        if xg_entry:
            level    = xg_entry.get("level", "")
            slug     = video_id
            base_dir = XIAOGUA_DIR / "videos" / level / slug
            # simplified: prefer zh-Hans, fall back to zh
            # traditional: prefer zh, fall back to zh-Hans
            if script == "traditional":
                candidates = [f"{slug}.zh.srt", f"{slug}.zh-Hans.srt"]
            else:
                candidates = [f"{slug}.zh-Hans.srt", f"{slug}.zh.srt"]
            for fname in candidates:
                path = base_dir / fname
                if path.exists():
                    return path.read_text(encoding="utf-8"), 200, {"Content-Type": "text/plain; charset=utf-8"}

    abort(404)


@lazy_bp.route("/api/translate-lines", methods=["POST"])
@login_required
def api_translate_lines():
    body = request.get_json(force=True) or {}
    lines = body.get("lines") or []
    if not isinstance(lines, list):
        return jsonify({"error": "lines must be an array"}), 400

    cleaned = [str(x).strip() for x in lines]
    if not cleaned:
        return jsonify({"translations": []})

    if len(cleaned) > 500:
        return jsonify({"error": "Too many lines in one request (max 500)"}), 400

    # Reuse cached results for repeated subtitle lines across videos.
    missing = [line for line in cleaned if line and line not in _en_cache]
    try:
        for i in range(0, len(missing), 30):  # Batch in groups of 30
            chunk = missing[i:i + 30]
            if not chunk:
                continue
            translated = _translate_english_batch(chunk)
            # Pad or truncate to match chunk size if API returns wrong count
            if len(translated) != len(chunk):
                print(f"WARNING: Translation returned {len(translated)} for {len(chunk)}, adjusting", file=sys.stderr)
            for src, dst in zip(chunk, translated):
                _en_cache[src] = dst
    except RuntimeError as e:
        return jsonify({"error": "Translation provider not configured. Set OPENAI_API_KEY."}), 503
    except Exception as e:
        print(f"Translation error: {e}", file=sys.stderr)
        return jsonify({"error": f"Translation failed: {str(e)[:100]}"}), 502

    result = [_en_cache.get(line, "") if line else "" for line in cleaned]
    return jsonify({"translations": result})

@lazy_bp.route("/admin/reindex", methods=["POST"])
@login_required
def admin_reindex():
    """Run the indexer in a background thread and return immediately.
    Prevents the single gunicorn worker from blocking on a 5-minute subprocess.
    After a successful run the in-memory catalog is refreshed.
    """
    def _run():
        try:
            r = subprocess.run(
                [sys.executable, str(HERE / "build_index.py")],
                capture_output=True, text=True, timeout=300
            )
            ok = r.returncode == 0
            print(f"[reindex] {'OK' if ok else 'FAILED'}\n{r.stdout}{r.stderr}", flush=True)
            if ok:
                # Refresh the in-memory catalog so subsequent requests see new data
                global _catalog
                _catalog = _load_catalog()
                print(f"[reindex] catalog refreshed — {len(_catalog)} videos", flush=True)
        except Exception as e:
            print(f"[reindex] exception: {e}", flush=True)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "Reindex started in background. Check server logs for result."})

# ── Stats ─────────────────────────────────────────────────────────────────────

@lazy_bp.route("/stats")
@login_required
def stats_page():
    return send_file(STATIC_DIR / "stats.html")

@lazy_bp.route("/api/stats")
@login_required
def api_stats():
    SYDNEY = ZoneInfo("Australia/Sydney")

    state   = _load_watch_state()
    _ensure_catalog()
    catalog = {v["id"]: v for v in _catalog}
    if XIAOGUA_INDEX.exists():
        _XG_LEVEL = {
            "Super Beginner":    "Complete Beginner",
            "Advanced Beginner": "Beginner",
            "Lower Intermediate": "Low Intermediate",
            "Upper Intermediate": "High Intermediate",
        }
        for v in json.loads(XIAOGUA_INDEX.read_text()):
            slug = v.get("slug", "")
            if slug and slug not in catalog:
                catalog[slug] = {
                    "id":    slug,
                    "title": v.get("title", ""),
                    "level": _XG_LEVEL.get(v.get("level", ""), v.get("level", "")),
                    "length": f"{v.get('minutes') or 0}:00",
                }

    def to_sydney(dt_str):
        if not dt_str:
            return None
        try:
            dt_str_clean = dt_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(dt_str_clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(SYDNEY)
        except Exception:
            return None

    def parse_mins(length_str):
        if not length_str:
            return 0
        parts = length_str.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) + int(parts[1]) / 60
            if len(parts) == 3:
                return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60
        except (ValueError, IndexError):
            pass
        return 0

    watched_entries = []
    for vid_id, v in state.items():
        if not v.get("watched"):
            continue
        dt = to_sydney(v.get("watchedAt", ""))
        yt_meta = v.get("_yt", {})
        if yt_meta:
            meta = {
                "title":  yt_meta.get("title", ""),
                "level":  yt_meta.get("level", ""),
                "length": yt_meta.get("length", ""),
            }
        else:
            meta = catalog.get(vid_id, {})
        mins = parse_mins(meta.get("length", ""))
        watched_entries.append({
            "id": vid_id,
            "title": meta.get("title", ""),
            "level": meta.get("level", ""),
            "teacher": meta.get("teacher", ""),
            "length_mins": mins,
            "watchedAt": dt,
            "watchCount": v.get("watchCount", 1),
        })

    total_watched = len(watched_entries)
    total_mins    = sum(e["length_mins"] * e["watchCount"] for e in watched_entries)

    # Group by day / week / month (with per-level counts)
    by_day   = {}
    by_week  = {}
    by_month = {}

    for e in watched_entries:
        dt = e["watchedAt"]
        if not dt:
            continue
        lvl       = e["level"] or "Unknown"
        day_key   = dt.strftime("%Y-%m-%d")
        week_key  = dt.strftime("%G-W%V")
        month_key = dt.strftime("%Y-%m")

        for key, bucket in [(day_key, by_day), (week_key, by_week), (month_key, by_month)]:
            if key not in bucket:
                bucket[key] = {"count": 0, "mins": 0.0, "levels": {}}
            bucket[key]["count"] += e["watchCount"]
            bucket[key]["mins"]  += e["length_mins"] * e["watchCount"]
            bucket[key]["levels"][lvl] = bucket[key]["levels"].get(lvl, 0) + e["watchCount"]

    # Build level breakdown
    level_counts = {}
    for e in watched_entries:
        lvl = e["level"] or "Unknown"
        level_counts[lvl] = level_counts.get(lvl, 0) + e["watchCount"]

    # All watches sorted newest-first
    recent = sorted(
        [e for e in watched_entries if e["watchedAt"]],
        key=lambda x: x["watchedAt"], reverse=True
    )

    def fmt_bucket(d):
        return {k: {"count": v["count"], "mins": round(v["mins"], 1), "levels": v["levels"]}
                for k, v in sorted(d.items())}

    return jsonify({
        "total_watched":  total_watched,
        "total_mins":     round(total_mins, 1),
        "total_hours":    round(total_mins / 60, 2),
        "by_day":   fmt_bucket(by_day),
        "by_week":  fmt_bucket(by_week),
        "by_month": fmt_bucket(by_month),
        "by_level": level_counts,
        "recent":   [{"id": e["id"], "title": e["title"], "level": e["level"],
                      "length_mins": round(e["length_mins"], 1),
                      "watchCount": e["watchCount"],
                      "is_yt": e["id"].startswith("yt_"),
                      "watchedAt": e["watchedAt"].strftime("%Y-%m-%d %H:%M") if e["watchedAt"] else ""
                     } for e in recent],
    })

# ── Subtitle Prototype ────────────────────────────────────────────────────────

def _srt_ms(ts: str) -> int:
    ts = ts.replace(',', '.')
    h, m, s = ts.split(':')
    return int((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


def _parse_en_srt(text: str) -> list:
    """Parse XG .en.srt blocks (index/timing/zh/pinyin/english) into cue dicts."""
    cues = []
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = [l.rstrip() for l in block.strip().splitlines()]
        if len(lines) < 3:
            continue
        m = re.match(r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)',
                     lines[1] if len(lines) > 1 else '')
        if not m:
            continue
        start  = _srt_ms(m.group(1))
        end    = _srt_ms(m.group(2))
        zh     = lines[2] if len(lines) > 2 else ''
        third  = lines[3] if len(lines) > 3 else ''
        fourth = lines[4] if len(lines) > 4 else ''
        if third and re.search(r'[a-zA-Zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]', third):
            py_line, english = third, fourth
        else:
            py_line, english = '', third
        chars     = list(zh.strip())
        syllables = py_line.split() if py_line else []
        if syllables and len(syllables) == len(chars):
            char_data = [{'c': c, 'p': p} for c, p in zip(chars, syllables)]
        else:
            char_data = [{'c': c, 'p': ''} for c in chars]
        if char_data:
            cues.append({'s': start, 'e': end, 'chars': char_data, 'en': english.strip()})
    return cues


@lazy_bp.route('/api/subtitle-proto/index')
@login_required
def api_subtitle_proto_index():
    """Slugs that have .en.srt subtitle files (used by prototype picker)."""
    vids_dir = XIAOGUA_DIR / 'videos'
    slugs = sorted(p.parent.name for p in vids_dir.glob('*/*/*.en.srt')) if vids_dir.exists() else []
    return jsonify(slugs)


@lazy_bp.route('/api/subtitle-proto/cues/<slug>')
@login_required
def api_subtitle_proto_cues(slug):
    if not XIAOGUA_INDEX.exists():
        abort(404)
    xg_videos = json.loads(XIAOGUA_INDEX.read_text())
    entry = next((v for v in xg_videos if v.get('slug') == slug), None)
    if not entry:
        abort(404)
    en_path = XIAOGUA_DIR / 'videos' / entry.get('level', '') / slug / f'{slug}.en.srt'
    if not en_path.exists():
        return jsonify([])
    return jsonify(_parse_en_srt(en_path.read_text(encoding='utf-8')))


# ── Boot ──────────────────────────────────────────────────────────────────────

app.register_blueprint(lazy_bp)

if __name__ == "__main__":
    _ensure_catalog()
    has_index = ONEDRIVE_INDEX.exists()
    print(f"Lazy Chinese Web App  →  http://localhost:{PORT}")
    print(f"  Catalog : {len(_catalog)} videos")
    print(f"  Index   : {'✓' if has_index else '✗ run build_index.py'}")
    print(f"  Tokens  : {'✓' if TOKENS_PATH.exists() else '✗ run auth_setup.py'}")
    print(f"  Auth    : {'✓ password set' if AUTH_PASSWORD else '✗ set AUTH_PASSWORD'}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
