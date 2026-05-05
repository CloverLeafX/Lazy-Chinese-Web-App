#!/usr/bin/env python3
"""
Lazy Chinese Web App — Flask server
"""
import glob, json, os, re, secrets as _secrets, subprocess, sys, threading, time
from datetime import timedelta
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import requests as _req
from flask import (Blueprint, Flask, abort, jsonify, redirect,
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
ONEDRIVE_INDEX = DATA_DIR / "onedrive_index.json"
TOKENS_PATH    = DATA_DIR / "tokens.json"

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
    for _fname in ("onedrive_index.json", "watch_state.json"):
        _src, _dst = _bundled_data / _fname, DATA_DIR / _fname
        if _src.exists() and not _dst.exists():
            _shutil.copy2(_src, _dst)

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
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
        if not flask_session.get("logged_in"):
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
    files = sorted(glob.glob(str(LAZY_CHINESE / "all_videos_*.json")), reverse=True)
    if not files:
        files = sorted(glob.glob(str(DATA_DIR / "all_videos_*.json")), reverse=True)
    if not files:
        # Fallback: bundled data dir inside the app repo
        files = sorted(glob.glob(str(HERE / "data" / "all_videos_*.json")), reverse=True)
    if not files:
        return []
    videos  = json.loads(Path(files[0]).read_text())
    tracker = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {}

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
    ms_tokens_env = os.environ.get("MS_TOKENS")
    if ms_tokens_env:
        return json.loads(ms_tokens_env)
    if TOKENS_PATH.exists():
        return json.loads(TOKENS_PATH.read_text())
    raise RuntimeError("MS_TOKENS env var or data/tokens.json not found")

def _get_access_token() -> str:
    with _token_lock:
        tokens = _load_tokens()
        if time.time() < tokens.get("expires_at", 0):
            return tokens["access_token"]

        r = _req.post(TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id":     MS_CLIENT_ID,
            "scope":         "Files.Read offline_access User.Read",
        })
        r.raise_for_status()
        data = r.json()
        tokens["access_token"]  = data["access_token"]
        tokens["refresh_token"] = data.get("refresh_token", tokens["refresh_token"])
        tokens["expires_at"]    = time.time() + data.get("expires_in", 3600) - 60
        if TOKENS_PATH.exists():
            TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
        return tokens["access_token"]

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
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in translation response")
    parsed = json.loads(match.group())
    if not isinstance(parsed, list):
        raise ValueError("Translation response was not a JSON array")
    return [str(x).strip() for x in parsed]


def _translate_english_batch(lines: list[str]) -> list[str]:
    """Translate Chinese subtitle lines into concise natural English."""
    if not lines:
        return []

    prompt = (
        "You are a strict subtitle translation engine. "
        "Translate each Chinese subtitle line to natural, concise English while preserving tone and intent. "
        "Return ONLY a JSON array of strings in the same order and same length as input."
    )

    if GROQ_API_KEY:
        resp = _req.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_API_KEY}",
            },
            json={
                "model": "llama-3.3-70b-versatile",
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
            raise ValueError("Translation output length mismatch")
        return out

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
            raise ValueError("Translation output length mismatch")
        return out

    raise RuntimeError("No translation provider configured")

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

@lazy_bp.route("/api/watch-state/<video_id>", methods=["DELETE"])
@login_required
def api_watch_state_delete(video_id):
    state = _load_watch_state()
    state.pop(video_id, None)
    _save_watch_state(state)
    return jsonify({"ok": True})

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

@lazy_bp.route("/subtitle/<video_id>")
@login_required
def subtitle(video_id):
    script  = request.args.get("script", "simplified")
    tracker = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {}
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
        for i in range(0, len(missing), 40):
            chunk = missing[i:i + 40]
            if not chunk:
                continue
            translated = _translate_english_batch(chunk)
            for src, dst in zip(chunk, translated):
                _en_cache[src] = dst
    except RuntimeError:
        return jsonify({"error": "Translation provider not configured. Set GROQ_API_KEY or OPENAI_API_KEY."}), 503
    except Exception as e:
        return jsonify({"error": f"Translation failed: {e}"}), 502

    result = [_en_cache.get(line, "") if line else "" for line in cleaned]
    return jsonify({"translations": result})

@lazy_bp.route("/admin/reindex", methods=["POST"])
@login_required
def admin_reindex():
    try:
        result = subprocess.run(
            [sys.executable, str(HERE / "build_index.py")],
            capture_output=True, text=True, timeout=300
        )
        return jsonify({"ok": result.returncode == 0, "output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Stats ─────────────────────────────────────────────────────────────────────

@lazy_bp.route("/stats")
@login_required
def stats_page():
    return send_file(STATIC_DIR / "stats.html")

@lazy_bp.route("/api/stats")
@login_required
def api_stats():
    from datetime import datetime, timezone, timedelta
    from zoneinfo import ZoneInfo

    SYDNEY = ZoneInfo("Australia/Sydney")

    state   = _load_watch_state()
    _ensure_catalog()
    catalog = {v["id"]: v for v in _catalog}

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
    total_mins    = sum(e["length_mins"] for e in watched_entries)

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
            bucket[key]["count"] += 1
            bucket[key]["mins"]  += e["length_mins"]
            bucket[key]["levels"][lvl] = bucket[key]["levels"].get(lvl, 0) + 1

    # Build level breakdown
    level_counts = {}
    for e in watched_entries:
        lvl = e["level"] or "Unknown"
        level_counts[lvl] = level_counts.get(lvl, 0) + 1

    # Recent watches (last 10)
    recent = sorted(
        [e for e in watched_entries if e["watchedAt"]],
        key=lambda x: x["watchedAt"], reverse=True
    )[:10]

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
                      "watchedAt": e["watchedAt"].strftime("%Y-%m-%d %H:%M") if e["watchedAt"] else ""
                     } for e in recent],
    })

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
