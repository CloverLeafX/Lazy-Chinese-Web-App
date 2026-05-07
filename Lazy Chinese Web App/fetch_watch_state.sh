#!/usr/bin/env bash
# Fetches watch state from Railway and saves it locally.
# Usage: ./fetch_watch_state.sh [password]
#   password defaults to AUTH_PASSWORD env var if set

set -euo pipefail

BASE_URL="https://ci-app.up.railway.app"
OUT_FILE="$(dirname "$0")/data/watch_state.json"
COOKIE_JAR="/tmp/lazy_cookies_sync.txt"
AUTH_PASSWORD="NCI3twjc449!"
PASSWORD="${1:-${AUTH_PASSWORD:-}}"

if [[ -z "$PASSWORD" ]]; then
  echo "Usage: $0 <password>  OR  set AUTH_PASSWORD in this script"
  exit 1
fi

echo "Logging in..."
curl -s -c "$COOKIE_JAR" -X POST "$BASE_URL/login" -d "password=$PASSWORD" -o /dev/null

echo "Fetching watch state..."
curl -s -b "$COOKIE_JAR" "$BASE_URL/api/watch-state" -o "$OUT_FILE"

CSV_FILE="$(dirname "$0")/data/watch_state.csv"

echo "Saved to $OUT_FILE"
SCRIPT_DIR="$(dirname "$0")"
python3 - "$OUT_FILE" "$CSV_FILE" "$SCRIPT_DIR" <<'EOF'
import json, csv, sys, glob, os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo("Australia/Sydney")

def to_sydney(dt_str):
    if not dt_str:
        return ""
    try:
        # Parse as UTC if Z suffix, else assume UTC
        dt_str_clean = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(SYDNEY).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str

data       = json.load(open(sys.argv[1]))
script_dir = sys.argv[3]

# Load catalog from most recent all_videos_*.json
catalog_files = sorted(glob.glob(os.path.join(script_dir, "data", "all_videos_*.json")), reverse=True)
catalog = {}
if catalog_files:
    for v in json.load(open(catalog_files[0])):
        catalog[v["id"]] = v

with open(sys.argv[2], "w", newline="") as f:
    w = csv.writer(f)
    def to_seconds(length_str):
        if not length_str:
            return ""
        parts = length_str.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return ""
        return ""

    w.writerow(["video_id", "title", "length", "length_seconds", "level", "teacher", "watched", "watchedAt_sydney", "watchCount", "lastPosition"])
    for vid_id, v in sorted(data.items(), key=lambda x: x[1].get("watchedAt", "")):
        meta = catalog.get(vid_id, {})
        length = meta.get("length", "")
        w.writerow([
            vid_id,
            meta.get("title", ""),
            length,
            to_seconds(length),
            meta.get("level", ""),
            meta.get("teacher", ""),
            v.get("watched", ""),
            to_sydney(v.get("watchedAt", "")),
            v.get("watchCount", ""),
            v.get("lastPosition", ""),
        ])
print(f"Saved CSV to {sys.argv[2]}")
print(f"Entries: {len(data)}")
EOF

rm -f "$COOKIE_JAR"
