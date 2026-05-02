#!/usr/bin/env python3
"""
Walk the OneDrive downloads folder and build data/onedrive_index.json.
Run once after auth_setup.py. Re-run after new downloads.

Usage:
    python build_index.py
"""
import json, os, time
from pathlib import Path
import requests
from dotenv import load_dotenv

HERE         = Path(__file__).parent
DATA_DIR     = HERE / "data"
LAZY_CHINESE = HERE.parent / "Lazy Chinese"

load_dotenv(HERE / ".env")

DRIVE_ID      = os.environ["MS_DRIVE_ID"]
ONEDRIVE_ROOT = os.environ.get("MS_ONEDRIVE_ROOT", "Python Apps/Canto/Lazy Chinese/downloads")
CLIENT_ID     = os.environ["MS_CLIENT_ID"]
TENANT_ID     = os.environ["MS_TENANT_ID"]
TOKEN_URL     = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
GRAPH         = "https://graph.microsoft.com/v1.0"


# ── Token management ──────────────────────────────────────────────────────────

def get_access_token() -> str:
    tokens_path = DATA_DIR / "tokens.json"
    tokens = json.loads(tokens_path.read_text())

    if time.time() < tokens["expires_at"]:
        return tokens["access_token"]

    print("  Refreshing access token...")
    r = requests.post(TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id":     CLIENT_ID,
        "scope":         "Files.Read offline_access User.Read",
    })
    r.raise_for_status()
    data = r.json()
    tokens["access_token"]  = data["access_token"]
    tokens["refresh_token"] = data.get("refresh_token", tokens["refresh_token"])
    tokens["expires_at"]    = time.time() + data.get("expires_in", 3600) - 60
    tokens_path.write_text(json.dumps(tokens, indent=2))
    return tokens["access_token"]


def graph_get(url: str, token: str) -> dict:
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        print(f"  Graph error {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    return r.json()


# ── OneDrive enumeration ──────────────────────────────────────────────────────

def enumerate_files() -> list:
    """Return all files under ONEDRIVE_ROOT using the delta endpoint (recursive)."""
    token        = get_access_token()
    encoded_root = ONEDRIVE_ROOT.replace(" ", "%20")
    url          = f"{GRAPH}/drives/{DRIVE_ID}/root:/{encoded_root}:/delta"

    files, page = [], 0
    while url:
        page += 1
        print(f"  Page {page}...", flush=True)
        data  = graph_get(url, token)
        for item in data.get("value", []):
            if "file" in item:
                files.append(item)
        url = data.get("@odata.nextLink") or data.get("@microsoft.graph.nextLink")

    print(f"  {len(files)} files found\n")
    return files


# ── Index building ────────────────────────────────────────────────────────────

def build_index(files: list) -> tuple[dict, list]:
    tracker = json.loads((LAZY_CHINESE / "download_tracker.json").read_text())

    # Build lookup: short_id → { mp4_id, srt_id, srt_tw_id }
    # Folder names on OneDrive: "{shortId}  {title}" for YouTube, "{uuid}  {title}" for Bunny.
    # Special characters in titles are replaced by OneDrive (_) so we match by short ID only.
    #
    # parentReference.path format:
    #   /drives/{id}/root:/My Documents OneDrive/.../downloads/Level/{shortId}  {title}
    path_prefix = f"/drives/{DRIVE_ID}/root:/{ONEDRIVE_ROOT}"

    # short_id (lowercase) → { "mp4": id, "srt": id, "srt_tw": id }
    folder_files: dict[str, dict] = {}

    for item in files:
        parent = item.get("parentReference", {}).get("path", "")
        name   = item["name"].lower()
        if not parent.startswith(path_prefix):
            continue
        # Folder name is last component of parent path
        folder_name = parent.split("/")[-1]   # e.g. "2rMFeanb  Are flashcards..."
        # Short ID = everything before the double-space separator (or full name if no separator)
        short_id = folder_name.split("  ")[0].lower()
        if not short_id:
            continue
        bucket = folder_files.setdefault(short_id, {})
        if name.endswith(".mp4"):
            bucket["mp4"] = item["id"]
        elif name.endswith("_tw.srt"):
            bucket["srt_tw"] = item["id"]
        elif name.endswith(".srt"):
            bucket["srt"] = item["id"]

    index:  dict = {}
    misses: list = []

    for video_id, entry in tracker.items():
        if not isinstance(entry, dict):
            continue
        folder_path = entry.get("folder_path", "")
        if not folder_path:
            continue

        # Short ID = first component of folder base name before double-space
        folder_name = Path(folder_path).name
        short_id    = folder_name.split("  ")[0].lower()
        bucket      = folder_files.get(short_id, {})

        entry_index: dict = {}
        miss_fields: list = []

        for field, key in [("mp4_id", "mp4"), ("srt_id", "srt"), ("srt_tw_id", "srt_tw")]:
            if key in bucket:
                entry_index[field] = bucket[key]
            elif entry.get({"mp4_id": "video_done", "srt_id": "srt_done", "srt_tw_id": "srt_tw_done"}[field]):
                miss_fields.append(field)

        if entry_index:
            index[video_id] = entry_index
        if miss_fields:
            misses.append({
                "video_id": video_id,
                "title":    entry.get("title", ""),
                "missing":  miss_fields,
            })

    return index, misses


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("── Build OneDrive Index ──\n")
    print(f"Drive: {DRIVE_ID[:30]}...")
    print(f"Root:  {ONEDRIVE_ROOT}\n")

    print("Enumerating files from OneDrive (this may take a minute)...")
    files = enumerate_files()

    print("Matching to download_tracker.json...")
    index, misses = build_index(files)

    index_path = DATA_DIR / "onedrive_index.json"
    index_path.write_text(json.dumps(index, indent=2))
    print(f"✓ Index written: {len(index)} videos → {index_path.name}")

    if misses:
        misses_path = DATA_DIR / "reindex_misses.json"
        misses_path.write_text(json.dumps(misses, indent=2))
        print(f"⚠  {len(misses)} videos with unmatched files → {misses_path.name}")
        for m in misses[:5]:
            print(f"   {m['video_id']}: {m['title']}")
            for f in m["missing"]:
                print(f"     {f}")
        if len(misses) > 5:
            print(f"   ...and {len(misses) - 5} more (see reindex_misses.json)")
    else:
        print("✓ All videos matched.")

    print("\nNext step: run  python server.py")


if __name__ == "__main__":
    main()
