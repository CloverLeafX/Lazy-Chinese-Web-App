#!/usr/bin/env python3
"""
Canto → Mando Blueprint — Combined Server
==========================================
Merges: Offline Course Viewer + Phrase Navigator + TTS

Run: python3 server.py
Then open: http://localhost:8800
"""
import asyncio, glob, hashlib, io, json, mimetypes, os, re, sys, threading
import cedict as _cedict
import setproctitle
setproctitle.setproctitle("CantoMandoServer")

from flask import Flask, jsonify, request, send_file, abort, Response
from flask_cors import CORS
import requests as _req

_HERE       = os.path.dirname(os.path.abspath(__file__))
BASE        = os.path.dirname(_HERE)                          # Canto_Mando_App root
DATA_DIR    = os.path.join(_HERE, "data")
HIDDEN_FILE = os.path.join(DATA_DIR, "hidden.json")
NOTES_FILE  = os.path.join(DATA_DIR, "notes.json")

# ── Load .env ─────────────────────────────────────────────────────────────────
def _load_env() -> dict:
    path = os.path.join(BASE, ".env")
    env = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

_ENV = _load_env()
GROQ_API_KEY    = _ENV.get("GROQ_API_KEY",    os.environ.get("GROQ_API_KEY",    ""))
OPEN_AI_API_KEY = (
    _ENV.get("OPENAI_API_KEY")
    or os.environ.get("OPENAI_API_KEY", "")
    or _ENV.get("OPEN_AI_KEY")
    or os.environ.get("OPEN_AI_KEY", "")
)
CANTO_DIR        = os.path.join(BASE, "Canto")
LAZY_CHINESE_DIR = os.path.realpath(os.path.join(BASE, "Lazy Chinese"))
VIDEOS_DIR  = os.path.join(BASE, "Canto_Mando_Videos")
STATIC_DIR  = os.path.join(_HERE, "static")
PORT        = int(os.environ.get("PORT", 8800))


app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
CORS(app)

# ── Lazy Chinese Web App (Blueprint mount) ────────────────────────────────────
try:
    import importlib.util as _ilu
    _lazy_spec = _ilu.spec_from_file_location(
        "lazy_server",
        os.path.join(BASE, "Lazy Chinese Web App", "server.py"),
    )
    _lazy_mod = _ilu.module_from_spec(_lazy_spec)
    _lazy_spec.loader.exec_module(_lazy_mod)
    app.register_blueprint(_lazy_mod.lazy_bp, url_prefix="/lazy_web_app")
    print("✅  Lazy Chinese Web App mounted at /lazy_web_app")
except Exception as _e:
    print(f"⚠️  Lazy Chinese Web App failed to mount: {_e}")

# ── Course structure helpers ──────────────────────────────────────────────────

_SKIP = {"__pycache__", "Canto_Mando_Viewer", ".venv", "Phrases", "Canto", "archive",
         ".claude", "Confident Cantonese Kickstarter", "Canto_Mando_Videos"}

def _pretty(name: str) -> str:
    return re.sub(r"^\d+_", "", name).replace("_", " ").strip()

def _chapter_label(folder: str) -> str:
    return folder.replace("_", " ").strip()

def _scan_dir(path: str, rel: str = "") -> dict:
    node = {
        "name":  os.path.basename(path),
        "label": _pretty(os.path.basename(path)),
        "rel":   rel,
        "children": [],
        "files": {"video": None, "audio": None, "pdfs": [], "image": None, "readme": None},
    }
    try:
        entries = sorted(os.listdir(path))
    except (PermissionError, FileNotFoundError):
        return node
    for e in entries:
        full = os.path.join(path, e)
        r    = os.path.join(rel, e) if rel else e
        if os.path.isdir(full):
            node["children"].append(_scan_dir(full, r))
        elif os.path.isfile(full):
            lc = e.lower()
            if lc.endswith(".mp4"):
                node["files"]["video"] = r
            elif lc.endswith((".mp3", ".mpeg")):
                node["files"]["audio"] = r
            elif lc.endswith(".pdf"):
                node["files"]["pdfs"].append(r)
            elif lc == "readme.md":
                node["files"]["readme"] = r
            elif lc.endswith((".png", ".jpg", ".jpeg")) and not node["files"]["image"]:
                node["files"]["image"] = r
    return node

def _chapter_sort_key(name: str):
    m = re.match(r'Chapter_(\d+(?:\.\d+)?)', name, re.IGNORECASE)
    return (0, float(m.group(1)), '') if m else (1, 0.0, name)

_VIDEO_GROUPS = ["cm1_Intro", "cm2_Basic", "cm3_Intermediate", "cm4_Advanced"]

def _build_structure() -> list:
    chapters = []

    # Chapters nested under group subfolders
    for group in _VIDEO_GROUPS:
        group_path = os.path.join(VIDEOS_DIR, group)
        if not os.path.isdir(group_path):
            continue
        for entry in sorted(os.listdir(group_path), key=_chapter_sort_key):
            full = os.path.join(group_path, entry)
            if not os.path.isdir(full) or entry.startswith("."):
                continue
            if not entry.startswith("Chapter"):
                continue
            rel = os.path.join("Canto_Mando_Videos", group, entry)
            node = _scan_dir(full, rel)
            node["label"] = _chapter_label(entry)
            chapters.append(node)

    # Confident Cantonese Kickstarter sits directly under Canto_Mando_Videos
    cck = "Confident Cantonese Kickstarter"
    cck_path = os.path.join(VIDEOS_DIR, cck)
    if os.path.isdir(cck_path):
        rel = os.path.join("Canto_Mando_Videos", cck)
        node = _scan_dir(cck_path, rel)
        node["label"] = cck
        chapters.append(node)

    return chapters

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file(os.path.join(STATIC_DIR, "index.html"))

@app.route("/health")
def health():
    return jsonify({"ok": True})

@app.route("/api/structure")
def api_structure():
    return jsonify(_build_structure())

@app.route("/api/curriculum")
def api_curriculum():
    path = os.path.join(DATA_DIR, "combined_curriculum.json")
    if not os.path.exists(path):
        abort(404, description="combined_curriculum.json not found")
    return send_file(path, mimetype="application/json")

@app.route("/api/cheat")
def api_cheat():
    path = os.path.join(DATA_DIR, "cheat.json")
    if not os.path.exists(path):
        abort(404, description="cheat.json not found")
    return send_file(path, mimetype="application/json")

@app.route("/advanced-progress")
def advanced_progress_page():
    return send_file(os.path.join(STATIC_DIR, "advanced-progress.html"))

@app.route("/api/advanced-progress")
def api_advanced_progress():
    ADV_BASE = os.path.join(VIDEOS_DIR, "cm4_Advanced")
    chapters = []
    for ch_folder in sorted(os.listdir(ADV_BASE)) if os.path.isdir(ADV_BASE) else []:
        if not ch_folder.startswith("Chapter_"):
            continue
        ch_path = os.path.join(ADV_BASE, ch_folder)
        sections = []
        for sec_folder in sorted(os.listdir(ch_path)):
            sec_path = os.path.join(ch_path, sec_folder)
            if not os.path.isdir(sec_path) or sec_folder == "README.md":
                continue
            posts = []
            for post_folder in sorted(os.listdir(sec_path)):
                post_path = os.path.join(sec_path, post_folder)
                if not os.path.isdir(post_path):
                    continue
                files = os.listdir(post_path)
                has_mp4   = any(f.endswith(".mp4")  for f in files)
                has_mp3   = any(f.endswith((".mp3", ".mpeg")) for f in files)
                has_pdf   = any(f.endswith(".pdf")  for f in files)
                has_readme= "README.md" in files
                readme_tbd= False
                va_url    = None
                if has_readme:
                    try:
                        with open(os.path.join(post_path, "README.md")) as rf:
                            rc = rf.read()
                        readme_tbd = "TBD" in rc
                        import re as _re
                        vm = _re.search(r'https?://www\.videoask\.com/[A-Za-z0-9_-]+', rc)
                        va_url = vm.group(0) if vm else None
                    except Exception:
                        pass
                # Determine expected type from folder name
                fn = post_folder.upper()
                if "VOCABULARY_LIST" in fn or "ROADMAP" in fn:
                    etype = "document"
                elif "INTENSIVE_LISTENING" in fn or ("LISTENING" in fn and "CM_SCHOOL" in sec_path.upper()):
                    etype = "audio"
                elif "ADVANCED_CHALLENGE" in fn or "ADVANCE_CHALLENGE" in fn:
                    etype = "challenge"
                elif "VOCAL_MESSAGING_HACK" in fn:
                    etype = "vmh"
                elif "DIARY_CHALLENGE" in fn:
                    etype = "diary"
                elif "VOCAL_HACK" in fn:
                    etype = "cm-vh"
                else:
                    etype = "video"
                # Determine status
                if etype == "video":
                    done = has_mp4
                elif etype == "audio":
                    done = has_mp3
                elif etype == "document":
                    done = has_pdf
                elif etype in ("vmh", "diary", "cm-vh"):
                    done = va_url is not None
                else:  # challenge
                    done = True  # challenges need no download
                posts.append({
                    "folder": post_folder,
                    "label": re.sub(r"^\d+_", "", post_folder).replace("_", " "),
                    "type": etype,
                    "done": done,
                    "has_mp4": has_mp4,
                    "has_mp3": has_mp3,
                    "has_pdf": has_pdf,
                    "has_readme": has_readme,
                    "readme_tbd": readme_tbd,
                    "va_url": va_url,
                })
            sections.append({
                "folder": sec_folder,
                "label": re.sub(r"^\d+_", "", sec_folder).replace("_", " "),
                "posts": posts,
            })
        chapters.append({
            "folder": ch_folder,
            "label": ch_folder.replace("_", " "),
            "sections": sections,
        })
    return jsonify({"chapters": chapters})

@app.route("/file/<path:rel>")
def serve_file(rel: str):
    full = os.path.realpath(os.path.join(BASE, rel))
    # Security: prevent path traversal
    if not full.startswith(os.path.realpath(BASE) + os.sep):
        abort(403)
    if not os.path.isfile(full):
        abort(404)

    mime, _ = mimetypes.guess_type(full)
    mime  = mime or "application/octet-stream"
    size  = os.path.getsize(full)
    range_header = request.headers.get("Range")

    if range_header and mime.startswith("video"):
        parts = range_header.strip().replace("bytes=", "").split("-")
        start = int(parts[0]) if parts[0] else 0
        # Cap each response at 2MB so Chrome buffers aggressively
        MAX_CHUNK = 2 * 1024 * 1024
        req_end = int(parts[1]) if len(parts) > 1 and parts[1] else size - 1
        end = min(req_end, start + MAX_CHUNK - 1, size - 1)
        length = end - start + 1

        def _generate():
            with open(full, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    yield chunk
                    remaining -= len(chunk)

        headers = {
            "Content-Range":  f"bytes {start}-{end}/{size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(length),
            "Content-Type":   mime,
        }
        return Response(_generate(), status=206, headers=headers)

    resp = send_file(full, mimetype=mime)
    resp.headers["Accept-Ranges"] = "bytes"
    if mime == "application/pdf":
        resp.headers["Content-Disposition"] = "inline"
    return resp


def _load_hidden() -> list:
    if not os.path.exists(HIDDEN_FILE):
        return []
    with open(HIDDEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/api/hidden", methods=["GET"])
def api_hidden_get():
    return jsonify({"keys": _load_hidden()})


@app.route("/api/hidden", methods=["POST"])
def api_hidden_post():
    data = request.get_json(force=True)
    key  = (data.get("key") or "").strip()
    hide = bool(data.get("hidden", True))
    if not key:
        return jsonify({"error": "No key"}), 400
    hidden = set(_load_hidden())
    if hide:
        hidden.add(key)
    else:
        hidden.discard(key)
    with open(HIDDEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(hidden), f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True, "count": len(hidden)})



def _load_notes() -> dict:
    if not os.path.exists(NOTES_FILE):
        return {}
    with open(NOTES_FILE, "rb") as f:
        raw = f.read()
    # Decode tolerantly (latin-1 never fails on arbitrary bytes)
    text = raw.decode("utf-8", errors="replace")
    try:
        data, _ = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        return {}
    return data


@app.route("/api/notes", methods=["GET"])
def api_notes_get():
    return jsonify(_load_notes())


@app.route("/api/notes", methods=["POST"])
def api_notes_post():
    data = request.get_json(force=True)
    key  = (data.get("key") or "").strip()
    text = data.get("text", "")
    if not key:
        return jsonify({"error": "No key"}), 400
    notes = _load_notes()
    if text:
        notes[key] = text
    else:
        notes.pop(key, None)
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    def _stop():
        import signal
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Timer(0.3, _stop).start()
    return jsonify({"ok": True})


@app.route("/api/tts", methods=["POST"])
def api_tts():
    data   = request.get_json(force=True)
    text   = (data.get("text") or "").strip()
    voice  = data.get("voice", "zh-HK-female")
    speed  = data.get("speed", "normal")
    engine = data.get("engine", "edge")   # "edge" | "gtts" | "google" | "openai"

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        if engine == "openai":
            speed_f = {"slow": 0.85, "normal": 1.0, "fast": 1.25}.get(speed, 1.0)
            audio = _tts_openai(text, speed=speed_f)
            print(f"[TTS] ✅ OpenAI TTS")
        elif engine == "google":
            try:
                audio = _tts_google_cloud(text, voice, speed)
                print(f"[TTS] ✅ Google Cloud TTS: voice={voice}")
            except Exception as gc_err:
                print(f"[TTS] ⚠️  Google Cloud failed ({gc_err}), falling back to Edge TTS")
                fallback = "zh-CN-YunjianNeural" if voice.startswith("cmn-") else "zh-HK-WanLungNeural"
                audio = _tts_edge(text, fallback, speed)
        elif engine == "gtts":
            audio = _tts_gtts(text, voice, speed)
            print(f"[TTS] ✅ gTTS: voice={voice}")
        else:
            try:
                audio = _tts_edge(text, voice, speed)
                print(f"[TTS] ✅ Edge TTS: voice={voice}")
            except Exception as edge_err:
                print(f"[TTS] ⚠️  Edge TTS failed ({edge_err}), falling back to gTTS")
                audio = _tts_gtts(text, voice, speed)
        return send_file(io.BytesIO(audio), mimetype="audio/mpeg")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _tts_edge(text: str, voice: str, speed: str) -> bytes:
    import edge_tts
    # Legacy short-form keys kept for backwards compatibility
    voice_map = {
        "zh-HK-female": "zh-HK-HiuGaaiNeural",
        "zh-HK-male":   "zh-HK-WanLungNeural",
        "zh-CN-female": "zh-CN-XiaoxiaoMultilingualNeural",
        "zh-CN-male":   "zh-CN-YunyangNeural",
        "zh-TW-female": "zh-TW-HsiaoChenNeural",
        "zh-TW-male":   "zh-TW-YunJheNeural",
    }
    rate_map = {"slow": "-25%", "normal": "+0%", "fast": "+25%"}
    # If voice is already a full Neural name, use it directly
    edge_voice = voice if "Neural" in voice else voice_map.get(voice, "zh-HK-HiuGaaiNeural")
    edge_rate  = rate_map.get(speed, "+0%")

    async def _synthesise() -> bytes:
        communicate = edge_tts.Communicate(text, edge_voice, rate=edge_rate)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        return buf.read()

    return asyncio.run(_synthesise())

_GOOGLE_CREDS_PATH = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "archive", "Canto",
        "folkloric-clock-472506-v7-9f27728139cb.json"
    ))
)

def _tts_google_cloud(text: str, voice: str, speed: str) -> bytes:
    import os as _os
    _os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _GOOGLE_CREDS_PATH
    from google.cloud import texttospeech
    client = texttospeech.TextToSpeechClient()

    # Determine language code from voice name prefix
    if voice.startswith("yue"):
        lang_code = "yue-HK"
    elif voice.startswith("cmn-TW"):
        lang_code = "cmn-TW"
    else:
        lang_code = "cmn-CN"

    rate_map = {"slow": 0.75, "normal": 1.0, "fast": 1.25}
    speaking_rate = rate_map.get(speed, 1.0)

    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice_params     = texttospeech.VoiceSelectionParams(
        language_code=lang_code, name=voice
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speaking_rate,
    )
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice_params, audio_config=audio_config
    )
    return response.audio_content

def _tts_gtts(text: str, voice: str, speed: str) -> bytes:
    from gtts import gTTS
    def _gtts_lang(v):
        if v.startswith("zh-HK") or v.startswith("yue"): return "yue"
        if v.startswith("zh-CN") or v.startswith("zh-TW"): return "zh-CN"
        return "yue"
    tts = gTTS(text=text, lang=_gtts_lang(voice), slow=(speed == "slow"))
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()

def _tts_openai(text: str, speed: float = 1.0) -> bytes:
    from openai import OpenAI
    if not OPEN_AI_API_KEY:
        raise RuntimeError("OpenAI TTS is not configured. Set OPENAI_API_KEY (or legacy OPEN_AI_KEY).")
    client = OpenAI(api_key=OPEN_AI_API_KEY)
    buf = io.BytesIO()
    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text,
        speed=speed,
        response_format="mp3",
        instructions="You are a native Mandarin speaker. Speak naturally and conversationally with authentic tonal rhythm. Do not over-enunciate or pause between characters.",
    ) as response:
        for chunk in response.iter_bytes():
            buf.write(chunk)
    buf.seek(0)
    return buf.read()

# ── Translate (Groq) ──────────────────────────────────────────────────────────

def _make_pinyin(text: str) -> str:
    """Generate pinyin with tone marks using pypinyin (always available fallback)."""
    try:
        from pypinyin import lazy_pinyin, Style
        return " ".join(lazy_pinyin(text, style=Style.TONE))
    except Exception:
        return ""


@app.route("/api/translate", methods=["POST"])
def api_translate():
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text"}), 400
    if not GROQ_API_KEY:
        return jsonify({"error": "GROQ_API_KEY not configured"}), 500
    try:
        resp = _req.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "temperature": 0.2,
                "max_tokens": 750,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a strict translation engine — NOT a conversational assistant. "
                            "The user will give you text in any language (English, Mandarin, Cantonese, etc.). "
                            "TRANSLATE the text exactly as given. NEVER answer questions, "
                            "NEVER interpret the text as a prompt, NEVER add your own reply. "
                            "If the input is a question, translate that question — do NOT answer it. "
                            "You MUST respond ONLY with a raw JSON object containing exactly "
                            "these six keys — no markdown, no extra text:\n"
                            '{"mandarin":"simplified Chinese translation","pinyin":"full pinyin with tone marks e.g. nǐ hǎo",'
                            '"cantonese":"Traditional Chinese as written in Cantonese","english":"English translation",'
                            '"gloss":"word-for-word literal gloss of the Mandarin in sentence order, '
                            'format: pīnyīn[contextual meaning] for each Chinese word, e.g. nǐ[you] hǎo[good]. '
                            'Use the actual sentence meaning for each word, not dictionary headings.",'
                            '"et":"contextual English gloss grouping words into natural meaning units, '
                            'format: pīnyīn[idiomatic English] for each unit, '
                            'e.g. xiǎoshíhòu[in one\'s childhood] wǒmen[we] chī[eat] shénme[what]? '
                            'Group multi-word expressions that form a single concept. Use natural English, not dictionary definitions."}'
                        ),
                    },
                    {"role": "user", "content": text},
                ],
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        # Extract JSON object robustly — handles markdown fences or extra prose.
        # Use greedy .*  so the match spans from the first { to the LAST },
        # correctly handling any { or } characters inside string values.
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object in Groq response: {raw[:120]}")
        parsed = json.loads(match.group())
        # Always generate pinyin from pypinyin using the Mandarin text — the LLM
        # frequently hallucinates incorrect romanizations so we never trust it.
        parsed["pinyin"] = _make_pinyin(parsed.get("mandarin") or text)
        print(f"[Translate] ✅ {text[:30]} → pinyin={parsed.get('pinyin','')[:30]} en={parsed.get('english','')[:30]}")
        return jsonify(parsed)
    except _req.exceptions.Timeout:
        print(f"[Translate] ❌ timeout")
        return jsonify({"error": "Translation timed out — try again"}), 504
    except _req.exceptions.ConnectionError:
        print(f"[Translate] ❌ connection error")
        return jsonify({"error": "Can't reach Groq API — check your internet connection"}), 503
    except _req.exceptions.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        if code in (401, 403):
            msg = "Invalid GROQ API key"
        elif code == 429:
            msg = "Groq rate limit hit — try again in a moment"
        elif code >= 500:
            msg = f"Groq server error ({code}) — try again"
        else:
            msg = f"Groq API error ({code})"
        print(f"[Translate] ❌ HTTP {code}: {exc}")
        return jsonify({"error": msg}), 502
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[Translate] ❌ parse error: {exc}")
        return jsonify({"error": "Unexpected response from AI — try again"}), 500
    except Exception as exc:
        print(f"[Translate] ❌ {exc}")
        return jsonify({"error": "Translation failed — try again"}), 500


# ── CC-CEDICT dictionary ─────────────────────────────────────────────────────

def _jyutping(word: str) -> str:
    """Convert Chinese characters to spaced Jyutping, e.g. 通常 → tung1 soeng4."""
    if not word:
        return ""
    try:
        import pycantonese as _pc
        pairs = _pc.characters_to_jyutping(word)
        parts = []
        for _, jp in pairs:
            if jp:
                parts.append(re.sub(r'([1-6])(?=[a-z])', r'\1 ', jp))
        return ' '.join(parts).strip()
    except Exception:
        return ""


@app.route("/api/dict", methods=["POST"])
def api_dict():
    """Exact lookup: {"query": "爱情"} → list of CEDICT entries + jyutping."""
    data  = request.get_json(force=True)
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "No query"}), 400
    results = _cedict.lookup(query)
    return jsonify({"query": query, "results": results, "jyutping": _jyutping(query)})


@app.route("/api/dict/segment", methods=["POST"])
def api_dict_segment():
    """Greedy segment + lookup: {"text": "我爱中文"} → per-word entries + jyutping."""
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "No text"}), 400
    words = _cedict.segment_lookup(text)
    for w in words:
        if w.get("entries"):
            w["jyutping"] = _jyutping(w["word"])
    return jsonify({"text": text, "words": words})


# ── Captures ──────────────────────────────────────────────────────────────────

CAPTURES_FILE     = os.path.join(DATA_DIR, "captures.json")
AUDIO_CAPTURES_DIR = os.path.join(DATA_DIR, "audio_captures")


def _load_captures() -> list:
    if not os.path.exists(CAPTURES_FILE):
        return []
    with open(CAPTURES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/api/captures", methods=["GET"])
def api_captures_get():
    return jsonify(_load_captures())


@app.route("/api/captures", methods=["POST"])
def api_captures_post():
    from datetime import datetime
    data      = request.get_json(force=True)
    mandarin  = (data.get("mandarin")  or "").strip()
    pinyin    = (data.get("pinyin")    or "").strip()
    cantonese = (data.get("cantonese") or "").strip()
    english   = (data.get("english")  or "").strip()
    if not mandarin:
        return jsonify({"error": "No mandarin text"}), 400

    ts  = datetime.now()
    h   = hashlib.md5(mandarin.encode()).hexdigest()[:4]
    rid = f"{ts.strftime('%Y%m%d%H%M%S')}_{h}"

    os.makedirs(AUDIO_CAPTURES_DIR, exist_ok=True)
    audio = {}

    for lang, text, voice, speed, suffix in [
        ("mandarin",  mandarin,  "zh-CN-XiaoxiaoMultilingualNeural", "slow",   "mandarin"),
        ("cantonese", cantonese, "zh-HK-HiuMaanNeural",  "normal", "cantonese"),
    ]:
        if not text:
            continue
        try:
            mp3 = _tts_openai(text, speed=1.0) if lang == "mandarin" else _tts_edge(text, voice, speed)
            fname = f"{rid}_{suffix}.mp3"
            fpath = os.path.join(AUDIO_CAPTURES_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(mp3)
            audio[lang] = f"data/audio_captures/{fname}"
            print(f"[Captures] ✅ {lang} audio → {fname}")
        except Exception as e:
            print(f"[Captures] ⚠️  {lang} TTS failed: {e}")

    record = {
        "id":        rid,
        "mandarin":  mandarin,
        "pinyin":    pinyin,
        "cantonese": cantonese,
        "english":   english,
        "timestamp": ts.isoformat(),
        "audio":     audio,
    }
    captures = _load_captures()
    captures.append(record)
    with open(CAPTURES_FILE, "w", encoding="utf-8") as f:
        json.dump(captures, f, ensure_ascii=False, indent=2)
    print(f"[Captures] ✅ saved #{len(captures)}: {mandarin[:20]}")
    return jsonify({"ok": True, "count": len(captures), "record": record})


# ── Lazy Chinese ─────────────────────────────────────────────────────────────

@app.route("/lazy")
def lazy_chinese():
    return send_file(os.path.join(STATIC_DIR, "lazy-chinese.html"))


@app.route("/api/lazy/videos")
def api_lazy_videos():
    files = sorted(glob.glob(os.path.join(LAZY_CHINESE_DIR, "all_videos_*.json")))
    if not files:
        abort(404, description="No Lazy Chinese video catalog found")
    return send_file(files[-1], mimetype="application/json")


@app.route("/api/lazy/tracker")
def api_lazy_tracker():
    path = os.path.join(LAZY_CHINESE_DIR, "download_tracker.json")
    if not os.path.exists(path):
        return jsonify({})
    return send_file(path, mimetype="application/json")


LAZY_HISTORY_FILE = os.path.join(DATA_DIR, "lc_watch_history.json")


@app.route("/api/lazy/history", methods=["GET"])
def api_lazy_history_get():
    if not os.path.exists(LAZY_HISTORY_FILE):
        return jsonify({})
    with open(LAZY_HISTORY_FILE, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/lazy/history", methods=["POST"])
def api_lazy_history_post():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected object"}), 400
    with open(LAZY_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/lazy/file")
def serve_lazy_file():
    path = request.args.get("p", "")
    if not path:
        abort(400)
    # Remap tracker paths recorded under old /Canto/Lazy Chinese/ location
    # to the current LAZY_CHINESE_DIR location
    old_lazy = os.path.realpath(os.path.join(os.path.dirname(BASE), "Canto", "Lazy Chinese"))
    if path.startswith(old_lazy):
        path = LAZY_CHINESE_DIR + path[len(old_lazy):]
    full = os.path.realpath(path)
    lazy_root = LAZY_CHINESE_DIR
    if not full.startswith(lazy_root + os.sep) and full != lazy_root:
        abort(403)
    if not os.path.isfile(full):
        abort(404)

    mime, _ = mimetypes.guess_type(full)
    mime  = mime or "application/octet-stream"
    size  = os.path.getsize(full)
    range_header = request.headers.get("Range")

    if range_header and mime.startswith(("video", "audio")):
        parts = range_header.strip().replace("bytes=", "").split("-")
        start = int(parts[0]) if parts[0] else 0
        end   = int(parts[1]) if len(parts) > 1 and parts[1] else size - 1
        end   = min(end, size - 1)
        length = end - start + 1

        def _generate():
            with open(full, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    yield chunk
                    remaining -= len(chunk)

        headers = {
            "Content-Range":  f"bytes {start}-{end}/{size}",
            "Accept-Ranges":  "bytes",
            "Content-Length": str(length),
            "Content-Type":   mime,
        }
        return Response(_generate(), status=206, headers=headers)

    resp = send_file(full, mimetype=mime)
    resp.headers["Accept-Ranges"] = "bytes"
    return resp


# ── Entry point ───────────────────────────────────────────────────────────────

def _check_deps():
    checks = [
        ("openai",                    "openai"),
        ("edge-tts",                  "edge_tts"),
        ("google-cloud-texttospeech", "google.cloud.texttospeech"),
        ("gtts",                      "gtts"),
        ("pypinyin",                  "pypinyin"),
        ("pycantonese",               "pycantonese"),
        ("setproctitle",              "setproctitle"),
    ]
    missing = []
    for pkg, imp in checks:
        try:
            __import__(imp)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[WARN] Missing packages (some features will fail): {', '.join(missing)}")
        print(f"       Fix: pip install {' '.join(missing)}")
    else:
        print("[OK] All optional dependencies present")

if __name__ == "__main__":
    _check_deps()
    # Pre-load CEDICT in a background thread so first /api/dict call is instant
    threading.Thread(target=_cedict._ensure_loaded, daemon=True).start()
    print(f"✅  Canto → Mando Blueprint  →  http://localhost:{PORT}")
    print("    Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
