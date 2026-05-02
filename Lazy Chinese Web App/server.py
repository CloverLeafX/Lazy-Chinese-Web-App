#!/usr/bin/env python3
"""
Lazy Chinese Web App — Flask server
"""
import glob, json, os, subprocess, sys, threading, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import requests as _req
from flask import Blueprint, Flask, abort, jsonify, request, send_file
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

DATA_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)

_lock       = threading.Lock()
_token_lock = threading.Lock()

lazy_bp = Blueprint("lazy", __name__)

# ── Catalog ───────────────────────────────────────────────────────────────────

def _load_catalog() -> list:
    pattern = str(LAZY_CHINESE / "all_videos_*.json")
    files   = sorted(glob.glob(pattern), reverse=True)
    if not files:
        return []
    videos  = json.loads(Path(files[0]).read_text())
    tracker = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {}

    for v in videos:
        t = tracker.get(v["id"], {})
        v["video_done"]  = t.get("video_done", False)
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

def _get_access_token() -> str:
    with _token_lock:
        if not TOKENS_PATH.exists():
            raise RuntimeError("data/tokens.json not found — run auth_setup.py first")
        tokens = json.loads(TOKENS_PATH.read_text())
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

# ── Routes ────────────────────────────────────────────────────────────────────

@lazy_bp.route("/")
def index():
    return send_file(STATIC_DIR / "index.html")

@lazy_bp.route("/health")
def health():
    return jsonify({"ok": True, "catalog": len(_catalog), "index": ONEDRIVE_INDEX.exists()})

@lazy_bp.route("/api/catalog")
def api_catalog():
    _ensure_catalog()
    return jsonify(_catalog)

@lazy_bp.route("/api/watch-state", methods=["GET"])
def api_watch_state_get():
    return jsonify(_load_watch_state())

@lazy_bp.route("/api/watch-state/<video_id>", methods=["POST"])
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
def api_watch_state_delete(video_id):
    state = _load_watch_state()
    state.pop(video_id, None)
    _save_watch_state(state)
    return jsonify({"ok": True})

@lazy_bp.route("/api/video-url/<video_id>")
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
def subtitle(video_id):
    script  = request.args.get("script", "simplified")
    tracker = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {}
    t       = tracker.get(video_id, {})

    # 1. Try local file
    rel_path = t.get("srt_tw_path") if script == "traditional" else t.get("srt_path")
    srt_text = _read_local_srt(rel_path)
    if srt_text:
        return srt_text, 200, {"Content-Type": "text/plain; charset=utf-8"}

    # 2. Try OneDrive via Graph API
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

@lazy_bp.route("/admin/reindex", methods=["POST"])
def admin_reindex():
    try:
        result = subprocess.run(
            [sys.executable, str(HERE / "build_index.py")],
            capture_output=True, text=True, timeout=300
        )
        return jsonify({"ok": result.returncode == 0, "output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Boot ──────────────────────────────────────────────────────────────────────

app.register_blueprint(lazy_bp)

if __name__ == "__main__":
    _ensure_catalog()
    has_index = ONEDRIVE_INDEX.exists()
    print(f"Lazy Chinese Web App  →  http://localhost:{PORT}")
    print(f"  Catalog : {len(_catalog)} videos")
    print(f"  Index   : {'✓' if has_index else '✗ run build_index.py'}")
    print(f"  Tokens  : {'✓' if TOKENS_PATH.exists() else '✗ run auth_setup.py'}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
