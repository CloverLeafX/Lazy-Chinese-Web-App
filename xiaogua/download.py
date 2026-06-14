#!/usr/bin/env python3
"""Download all Xiaogua Chinese YouTube videos at 720p with subtitles.

Usage:
    python3 download.py             # download everything, resume if re-run
    python3 download.py --free      # free-access videos only
    python3 download.py --retry     # re-attempt previously failed videos
    python3 download.py --limit 6   # download N videos (for testing)

Each video is saved as:
    videos/{slug}/{slug}.mp4
    videos/{slug}/{slug}.zh-Hans.srt   (if available)
    videos/{slug}/{slug}.en.srt        (if available)

Progress tracker: http://localhost:7788/progress.html
Re-running skips already-completed videos automatically.
"""
import argparse, datetime, json, os, pathlib, subprocess
import sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE          = pathlib.Path(__file__).parent
VIDEO_DIR     = HERE / "videos"
INDEX_FILE    = HERE / "data" / "video_index.json"
PROGRESS_FILE = HERE / "data" / "progress.json"
COOKIES_FILE  = HERE / "data" / "cookies.txt"

# ── Config ────────────────────────────────────────────────────────────────────
YTDLP       = "/opt/homebrew/bin/yt-dlp"
MAX_WORKERS = 4
SERVER_PORT = 7788
FORMAT      = (
    "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
    "/bestvideo[height<=720]+bestaudio"
    "/best[height<=720]"
)

_lock = threading.Lock()


# ── Cookie export ─────────────────────────────────────────────────────────────

def export_cookies() -> None:
    import time as _time
    if COOKIES_FILE.exists():
        age_days = (_time.time() - COOKIES_FILE.stat().st_mtime) / 86400
        if age_days < 7:
            print(f"Cookies file is {age_days:.1f}d old — reusing ({COOKIES_FILE.stat().st_size // 1024} KB)")
            return
    print("Exporting Edge cookies...", end=" ", flush=True)
    try:
        subprocess.run(
            [YTDLP, "--cookies-from-browser", "edge",
             "--cookies", str(COOKIES_FILE),
             "--simulate", "--quiet", "--no-warnings",
             "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("timed out", end=" ")
    if COOKIES_FILE.exists():
        print(f"ok ({COOKIES_FILE.stat().st_size // 1024} KB)")
    else:
        print("WARNING: cookies file not created — downloads may fail")


# ── Migration: flat videos → per-folder ──────────────────────────────────────

def migrate_flat_videos() -> None:
    """Move any videos/{slug}.mp4 → videos/{slug}/{slug}.mp4 (pre-level-folder legacy)."""
    moved = 0
    for f in VIDEO_DIR.glob("*.mp4"):
        slug = f.stem
        dest_dir = VIDEO_DIR / slug
        dest_dir.mkdir(exist_ok=True)
        f.rename(dest_dir / f.name)
        print(f"  migrated {f.name} → {slug}/{f.name}")
        moved += 1
    if moved:
        print(f"  {moved} file(s) migrated\n")


# ── Index ─────────────────────────────────────────────────────────────────────

def load_index() -> list:
    if not INDEX_FILE.exists():
        sys.exit(
            f"ERROR: {INDEX_FILE} not found.\n"
            "Run:  python3 fetch_index.py  first."
        )
    with open(INDEX_FILE, encoding="utf-8") as f:
        return json.load(f)


# ── Progress ──────────────────────────────────────────────────────────────────

def init_progress(videos: list, retry_failed: bool) -> list:
    existing: dict = {}
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                for v in json.load(f).get("videos", []):
                    existing[v["slug"]] = v
        except Exception:
            pass

    tracked = []
    for v in videos:
        e = existing.get(v["slug"], {})
        status = e.get("status", "pending")
        if retry_failed and status == "failed":
            status = "pending"
        # Check disk — trust file existence over stale progress status
        level      = v.get("level") or "Unknown"
        video_file = VIDEO_DIR / level / v["slug"] / f"{v['slug']}.mp4"
        if video_file.exists() and video_file.stat().st_size > 0 and status != "done":
            status = "done"
        tracked.append({
            "slug":        v["slug"],
            "title":       v["title"],
            "youtubeId":   v["youtubeId"],
            "level":       v.get("level", ""),
            "access":      v.get("access", "free"),
            "minutes":     v.get("minutes", 0),
            "status":      status,
            "filename":    e.get("filename"),
            "size_mb":     e.get("size_mb"),
            "srts":        e.get("srts", []),
            "error":       e.get("error"),
            "started_at":  e.get("started_at"),
            "finished_at": e.get("finished_at"),
        })
    return tracked


def save_progress(tracked: list) -> None:
    counts = {k: 0 for k in ("done", "downloading", "failed", "pending")}
    for v in tracked:
        s = v["status"]
        if s in counts:
            counts[s] += 1
    counts["total"] = len(tracked)

    data = {
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
        "stats":   counts,
        "videos":  tracked,
    }
    tmp = str(PROGRESS_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PROGRESS_FILE)


# ── Downloader ────────────────────────────────────────────────────────────────

def download_one(entry: dict, all_tracked: list) -> None:
    slug    = entry["slug"]
    level   = entry.get("level") or "Unknown"
    yt_id   = entry["youtubeId"]
    yt_url  = f"https://www.youtube.com/watch?v={yt_id}"
    out_dir = VIDEO_DIR / level / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out     = out_dir / f"{slug}.mp4"

    with _lock:
        entry["status"]     = "downloading"
        entry["started_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        entry["error"]      = None
        save_progress(all_tracked)

    cmd = [
        YTDLP,
        "-f", FORMAT,
        "--merge-output-format", "mp4",
        "-o", str(out),
        "--no-playlist",
        # subtitles
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", "zh-Hans,zh,en",
        "--sub-format", "srt/best",
        "--convert-subs", "srt",
        # auth
        "--cookies", str(COOKIES_FILE),
        "--quiet",
        "--no-warnings",
        yt_url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode == 0 and out.exists() and out.stat().st_size > 0:
            size_mb = round(out.stat().st_size / 1_048_576, 1)
            srts    = sorted(p.name for p in out_dir.glob(f"{slug}.*.srt"))
            with _lock:
                entry["status"]      = "done"
                entry["filename"]    = out.name
                entry["size_mb"]     = size_mb
                entry["srts"]        = srts
                entry["error"]       = None
                entry["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                save_progress(all_tracked)
            srt_note = f"  {len(srts)} srt" if srts else "  no subs"
            print(f"  ✓ {slug}  ({size_mb} MB,{srt_note})")
        else:
            err = (result.stderr or "").strip()[-300:] or f"exit {result.returncode}"
            with _lock:
                entry["status"]      = "failed"
                entry["error"]       = err
                entry["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                save_progress(all_tracked)
            print(f"  ✗ {slug}: {err[:80]}")

    except subprocess.TimeoutExpired:
        with _lock:
            entry["status"]      = "failed"
            entry["error"]       = "timeout after 15 min"
            entry["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            save_progress(all_tracked)
        print(f"  ✗ {slug}: timeout")

    except Exception as exc:
        with _lock:
            entry["status"]      = "failed"
            entry["error"]       = str(exc)[:200]
            entry["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            save_progress(all_tracked)
        print(f"  ✗ {slug}: {exc}")


# ── Progress server ───────────────────────────────────────────────────────────

def start_server() -> None:
    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(HERE), **kwargs)
        def log_message(self, *args):
            pass

    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("127.0.0.1", SERVER_PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"  Progress viewer → http://localhost:{SERVER_PORT}/progress.html\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--free",  action="store_true", help="free-access videos only")
    parser.add_argument("--retry", action="store_true", help="re-attempt failed videos")
    parser.add_argument("--limit", type=int, default=None, help="cap number of downloads (testing)")
    args = parser.parse_args()

    if not pathlib.Path(YTDLP).exists():
        sys.exit(f"ERROR: yt-dlp not found at {YTDLP}\nInstall: brew install yt-dlp")

    VIDEO_DIR.mkdir(exist_ok=True)

    # Move any flat videos/{slug}.mp4 into their own subfolder first
    migrate_flat_videos()

    export_cookies()

    print("Loading index...")
    all_videos = load_index()
    if args.free:
        all_videos = [v for v in all_videos if v.get("access") == "free"]
        print(f"  {len(all_videos)} free videos")
    else:
        print(f"  {len(all_videos)} total videos")

    print("Initialising progress...")
    tracked = init_progress(all_videos, retry_failed=args.retry)
    save_progress(tracked)

    start_server()

    to_do        = [v for v in tracked if v["status"] in ("pending", "failed")]
    already_done = sum(1 for v in tracked if v["status"] == "done")
    remaining    = len(to_do)

    if args.limit:
        to_do     = to_do[:args.limit]
        remaining = len(to_do)

    print(f"  Already done   : {already_done}")
    print(f"  This run       : {remaining}")
    print(f"  Still pending  : {len(tracked) - already_done - remaining}")
    print(f"  Concurrency    : {MAX_WORKERS} at a time")
    print()

    if not to_do:
        print("Nothing left to download.")
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
        return

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_one, v, tracked): v for v in to_do}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                print(f"  UNHANDLED: {futures[future]['slug']}: {exc}")

    done_n   = sum(1 for v in tracked if v["status"] == "done")
    failed_n = sum(1 for v in tracked if v["status"] == "failed")
    print(f"\nDone: {done_n}/{len(tracked)}  Failed: {failed_n}")
    if failed_n:
        print("Re-run with --retry to attempt failed videos again.")

    try:
        input("\nPress Enter to exit...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
