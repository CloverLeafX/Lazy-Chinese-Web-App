#!/usr/bin/env python3
"""
Step 1: Download missing SRTs for all existing videos (--skip-download, no re-fetch of video)
Step 2: Move videos/{slug}/ → videos/{level}/{slug}/

Run: python3 backfill_and_reorganize.py
"""
import json, pathlib, subprocess, sys

HERE         = pathlib.Path(__file__).parent
VIDEO_DIR    = HERE / "videos"
INDEX_FILE   = HERE / "data" / "video_index.json"
COOKIES_FILE = HERE / "data" / "cookies.txt"
YTDLP        = "/opt/homebrew/bin/yt-dlp"


def load_index() -> dict:
    if not INDEX_FILE.exists():
        sys.exit(f"ERROR: {INDEX_FILE} not found. Run fetch_index.py first.")
    with open(INDEX_FILE, encoding="utf-8") as f:
        return {v["slug"]: v for v in json.load(f)}


def slug_folders() -> list:
    """Top-level folders that contain at least one .mp4 (i.e. are slug dirs, not level dirs)."""
    return sorted(d for d in VIDEO_DIR.iterdir() if d.is_dir() and any(d.glob("*.mp4")))


# ── Step 1 — Backfill SRTs ────────────────────────────────────────────────────

def backfill_srts(by_slug: dict) -> None:
    print("=== Step 1: Backfill SRTs ===")
    folders = slug_folders()
    missing = [f for f in folders if not any(f.glob("*.srt"))]
    has_srt = len(folders) - len(missing)
    print(f"  {len(folders)} video folders  |  {has_srt} already have SRTs  |  {len(missing)} need backfill\n")

    if not missing:
        print("  Nothing to backfill.\n")
        return

    for folder in missing:
        slug = folder.name
        info = by_slug.get(slug)
        if not info:
            print(f"  ⚠  {slug}: not in index — skipping")
            continue

        yt_url = f"https://www.youtube.com/watch?v={info['youtubeId']}"
        out    = str(folder / f"{slug}.%(ext)s")

        print(f"  → {slug} ... ", end="", flush=True)
        result = subprocess.run(
            [
                YTDLP,
                "--write-subs", "--write-auto-subs",
                "--sub-langs", "zh-Hans,zh,en",
                "--sub-format", "srt/best",
                "--convert-subs", "srt",
                "--skip-download",
                "--cookies", str(COOKIES_FILE),
                "-o", out,
                "--quiet", "--no-warnings",
                yt_url,
            ],
            capture_output=True, text=True, timeout=60,
        )
        srts = sorted(s.name for s in folder.glob("*.srt"))
        if srts:
            print(f"✓  {srts}")
        else:
            err = result.stderr.strip()[:80] if result.stderr else "no subs available"
            print(f"✗  {err}")

    print()


# ── Step 2 — Reorganize into level folders ────────────────────────────────────

def reorganize(by_slug: dict) -> None:
    print("=== Step 2: Reorganize into level folders ===")
    folders = slug_folders()
    moved = skipped = unknown = 0

    for folder in folders:
        slug  = folder.name
        info  = by_slug.get(slug)
        level = (info.get("level") or "Unknown") if info else "Unknown"
        if not level:
            level = "Unknown"

        level_dir = VIDEO_DIR / level
        level_dir.mkdir(exist_ok=True)
        dest = level_dir / slug

        if dest.exists():
            skipped += 1
            continue

        folder.rename(dest)
        print(f"  {level:25s}  ←  {slug}")
        moved += 1
        if level == "Unknown":
            unknown += 1

    print(f"\n  Moved: {moved}  |  Already in place: {skipped}  |  Unknown level: {unknown}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    by_slug = load_index()
    backfill_srts(by_slug)
    reorganize(by_slug)
    print("Done.")


if __name__ == "__main__":
    main()
