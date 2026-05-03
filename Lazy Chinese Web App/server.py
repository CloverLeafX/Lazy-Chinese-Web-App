#!/usr/bin/env python3
"""
Lazy Chinese Web App — Flask server
"""
import base64, glob, json, os, secrets as _secrets, subprocess, sys, threading, time
from datetime import timedelta
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import requests as _req
from flask import (Blueprint, Flask, abort, jsonify, redirect,
                   render_template_string, request, send_file,
                   session as flask_session, url_for)
from flask_cors import CORS

import webauthn
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier

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
CREDS_PATH     = DATA_DIR / "webauthn_credentials.json"

MS_CLIENT_ID    = os.environ.get("MS_CLIENT_ID", "")
MS_TENANT_ID    = os.environ.get("MS_TENANT_ID", "")
MS_DRIVE_ID     = os.environ.get("MS_DRIVE_ID", "")
TOKEN_URL       = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"
GRAPH           = "https://graph.microsoft.com/v1.0"

RP_ID          = os.environ.get("RP_ID", "localhost")
RP_ORIGIN      = os.environ.get("RP_ORIGIN", f"http://localhost:{PORT}")
RP_NAME        = "Lazy Chinese"
SETUP_TOKEN    = os.environ.get("SETUP_TOKEN", "")

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

lazy_bp = Blueprint("lazy", __name__)

# ── Auth helpers ──────────────────────────────────────────────────────────────

def _load_creds() -> list:
    return json.loads(CREDS_PATH.read_text()) if CREDS_PATH.exists() else []

def _save_creds(creds: list):
    with _lock:
        CREDS_PATH.write_text(json.dumps(creds, indent=2))

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not flask_session.get("logged_in"):
            return redirect(url_for("lazy.login"))
        return f(*args, **kwargs)
    return decorated

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _from_b64url(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))

# ── Catalog ───────────────────────────────────────────────────────────────────

def _load_catalog() -> list:
    files = sorted(glob.glob(str(LAZY_CHINESE / "all_videos_*.json")), reverse=True)
    if not files:
        files = sorted(glob.glob(str(DATA_DIR / "all_videos_*.json")), reverse=True)
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

# ── Auth routes ───────────────────────────────────────────────────────────────

@lazy_bp.route("/login")
def login():
    if flask_session.get("logged_in"):
        return redirect(url_for("lazy.index"))
    has_creds = bool(_load_creds())
    return send_file(STATIC_DIR / "login.html")

@lazy_bp.route("/logout")
def logout():
    flask_session.clear()
    return redirect(url_for("lazy.login"))

@lazy_bp.route("/api/auth/begin")
def api_auth_begin():
    creds = _load_creds()
    if not creds:
        return jsonify({"error": "No passkeys registered"}), 403

    allow = [
        webauthn.helpers.structs.PublicKeyCredentialDescriptor(
            id=_from_b64url(c["id"])
        )
        for c in creds
    ]
    options = webauthn.generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    flask_session["auth_challenge"] = _b64url(options.challenge)
    return jsonify(json.loads(webauthn.options_to_json(options)))

@lazy_bp.route("/api/auth/complete", methods=["POST"])
def api_auth_complete():
    body = request.get_json(force=True) or {}
    challenge = flask_session.pop("auth_challenge", None)
    if not challenge:
        return jsonify({"error": "No challenge"}), 400

    cred_id = body.get("id", "")
    creds = _load_creds()
    stored = next((c for c in creds if c["id"] == cred_id), None)
    if not stored:
        return jsonify({"error": "Unknown credential"}), 403

    try:
        from webauthn.helpers.structs import AuthenticationCredential
        verification = webauthn.verify_authentication_response(
            credential=AuthenticationCredential.model_validate(body),
            expected_challenge=_from_b64url(challenge),
            expected_rp_id=RP_ID,
            expected_origin=RP_ORIGIN,
            credential_public_key=_from_b64url(stored["public_key"]),
            credential_current_sign_count=stored["sign_count"],
            require_user_verification=True,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 403

    stored["sign_count"] = verification.new_sign_count
    _save_creds(creds)

    flask_session.permanent = True
    flask_session["logged_in"] = True
    return jsonify({"ok": True})

@lazy_bp.route("/register")
def register_page():
    if SETUP_TOKEN and request.args.get("token") != SETUP_TOKEN:
        abort(403)
    return send_file(STATIC_DIR / "register.html")

@lazy_bp.route("/api/register/begin")
def api_register_begin():
    if SETUP_TOKEN and request.args.get("token") != SETUP_TOKEN:
        abort(403)

    options = webauthn.generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=b"kai",
        user_name="kai",
        user_display_name="Kai",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
        exclude_credentials=[
            webauthn.helpers.structs.PublicKeyCredentialDescriptor(
                id=_from_b64url(c["id"])
            )
            for c in _load_creds()
        ],
    )
    flask_session["reg_challenge"] = _b64url(options.challenge)
    return jsonify(json.loads(webauthn.options_to_json(options)))

@lazy_bp.route("/api/register/complete", methods=["POST"])
def api_register_complete():
    if SETUP_TOKEN and request.args.get("token") != SETUP_TOKEN:
        abort(403)

    body = request.get_json(force=True) or {}
    challenge = flask_session.pop("reg_challenge", None)
    if not challenge:
        return jsonify({"error": "No challenge"}), 400

    try:
        from webauthn.helpers.structs import RegistrationCredential
        verification = webauthn.verify_registration_response(
            credential=RegistrationCredential.model_validate(body),
            expected_challenge=_from_b64url(challenge),
            expected_rp_id=RP_ID,
            expected_origin=RP_ORIGIN,
            require_user_verification=True,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    creds = _load_creds()
    new_cred = {
        "id":         _b64url(verification.credential_id),
        "public_key": _b64url(verification.credential_public_key),
        "sign_count": verification.sign_count,
        "name":       body.get("name", "Device"),
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    creds.append(new_cred)
    _save_creds(creds)
    return jsonify({"ok": True, "credential_id": new_cred["id"]})

# ── App routes ────────────────────────────────────────────────────────────────

@lazy_bp.route("/")
@login_required
def index():
    return send_file(STATIC_DIR / "index.html")

@lazy_bp.route("/health")
def health():
    return jsonify({"ok": True, "catalog": len(_catalog), "index": ONEDRIVE_INDEX.exists()})

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

# ── Boot ──────────────────────────────────────────────────────────────────────

app.register_blueprint(lazy_bp)

if __name__ == "__main__":
    _ensure_catalog()
    has_index = ONEDRIVE_INDEX.exists()
    print(f"Lazy Chinese Web App  →  http://localhost:{PORT}")
    print(f"  Catalog : {len(_catalog)} videos")
    print(f"  Index   : {'✓' if has_index else '✗ run build_index.py'}")
    print(f"  Tokens  : {'✓' if TOKENS_PATH.exists() else '✗ run auth_setup.py'}")
    print(f"  Passkeys: {len(_load_creds())} registered")
    app.run(host="0.0.0.0", port=PORT, debug=False)
