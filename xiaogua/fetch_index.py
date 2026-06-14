#!/usr/bin/env python3
"""Fetch all video metadata from xiaoguachinese.com and save to video_index.json.

The site's own JS fetches /transcripts?format=json-pretty on every page load to
build window.videosCache — this script replicates that exact request chain.

Run: python3 fetch_index.py
Output: video_index.json (245 videos with slug, title, youtubeId, level, access, etc.)
"""
import json, time, random, urllib.request, pathlib, sys

BASE_URL = "https://www.xiaoguachinese.com"
TRANSCRIPTS_PATH = "/transcripts"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "data" / "video_index.json"


def _get(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json, text/html;q=0.9"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _tag(tags: list, prefix: str) -> str:
    for t in tags:
        if isinstance(t, str) and t.startswith(prefix):
            return t[len(prefix):]
    return ""


def _tags(tags: list, prefix: str) -> list:
    return [t[len(prefix):] for t in tags if isinstance(t, str) and t.startswith(prefix)]


def fetch_all_items() -> list:
    items = []
    url = f"{BASE_URL}{TRANSCRIPTS_PATH}?format=json-pretty"
    page = 1
    seen = set()
    while url and url not in seen:
        seen.add(url)
        print(f"  page {page}: fetching...", end=" ", flush=True)
        try:
            data = _get(url)
        except Exception as e:
            print(f"ERROR: {e}")
            break
        batch = data.get("items", [])
        items.extend(batch)
        print(f"{len(batch)} items (running total: {len(items)})")
        nxt = data.get("pagination", {}).get("nextPageUrl")
        if nxt:
            # ensure format param is present
            if "format=" not in nxt:
                sep = "&" if "?" in nxt else "?"
                nxt = nxt + sep + "format=json-pretty"
            url = BASE_URL + nxt if nxt.startswith("/") else nxt
        else:
            url = None
        page += 1
        if url:
            time.sleep(random.uniform(2.0, 4.0))
    return items


def parse_videos(items: list) -> list:
    videos = []
    for item in items:
        tags = item.get("tags") or []
        yt_id = _tag(tags, "youtube:")
        if not yt_id:
            continue  # not a video entry
        url_id = item.get("urlId") or item.get("slug") or ""
        minutes_raw = _tag(tags, "minutes:")
        part_raw = _tag(tags, "part:")
        videos.append({
            "id":       item.get("id", ""),
            "slug":     url_id.strip().lower(),
            "title":    (item.get("title") or "").strip(),
            "youtubeId": yt_id,
            "level":    _tag(tags, "level:"),
            "access":   _tag(tags, "access:") or "free",
            "teachers": _tags(tags, "teacher:"),
            "topics":   _tags(tags, "topic:"),
            "minutes":  int(minutes_raw) if minutes_raw.isdigit() else 0,
            "date":     _tag(tags, "date:"),
            "series":   _tag(tags, "series:"),
            "part":     int(part_raw) if part_raw.isdigit() else 0,
        })
    return videos


def main():
    print(f"Fetching video index from {BASE_URL}{TRANSCRIPTS_PATH} ...")
    items = fetch_all_items()
    print(f"\nParsing {len(items)} raw items...")
    videos = parse_videos(items)
    print(f"  {len(videos)} videos with YouTube IDs")

    free    = sum(1 for v in videos if v["access"] == "free")
    member  = sum(1 for v in videos if v["access"] == "member")
    print(f"  {free} free, {member} member")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    print(f"\nSaved → {OUT}")


if __name__ == "__main__":
    main()
