#!/usr/bin/env python3
"""
Walk the xiaogua/videos folder on OneDrive and build data/onedrive_index.json.
Run once after downloading videos to OneDrive. Re-run after new downloads.

Uses the same credentials / tokens as the Lazy Chinese Web App.

Usage:
    python xiaogua/build_onedrive_index.py
"""
import json, os, time
from pathlib import Path
import requests
from dotenv import load_dotenv

HERE       = Path(__file__).parent
LAZY_APP   = HERE.parent / "Lazy Chinese Web App"
DATA_DIR   = HERE / "data"

load_dotenv(HERE.parent / ".env")
load_dotenv(LAZY_APP / ".env")

DRIVE_ID          = os.environ["MS_DRIVE_ID"]
ONEDRIVE_ROOT     = os.environ.get("MS_ONEDRIVE_XIAOGUA_ROOT",
                      "My Documents OneDrive/Python Apps/Canto_Mando_App/xiaogua/videos")
CLIENT_ID         = os.environ["MS_CLIENT_ID"]
TENANT_ID         = os.environ["MS_TENANT_ID"]
TOKEN_URL         = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
GRAPH             = "https://graph.microsoft.com/v1.0"
TOKENS_PATH       = LAZY_APP / "data" / "tokens.json"


# ── Token management ──────────────────────────────────────────────────────────

def get_access_token() -> str:
    tokens = json.loads(TOKENS_PATH.read_text())

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
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
    return tokens["access_token"]


def graph_get(url: str, token: str) -> dict:
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        print(f"  Graph error {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    return r.json()


# ── OneDrive enumeration ──────────────────────────────────────────────────────

def enumerate_files() -> list:
    """Return all files under ONEDRIVE_ROOT using the delta endpoint."""
    token        = get_access_token()
    encoded_root = ONEDRIVE_ROOT.replace(" ", "%20")
    url          = f"{GRAPH}/drives/{DRIVE_ID}/root:/{encoded_root}:/delta"

    files, page = [], 0
    while url:
        page += 1
        print(f"  Page {page}...", flush=True)
        data = graph_get(url, token)
        for item in data.get("value", []):
            if "file" in item:
                files.append(item)
        url = data.get("@odata.nextLink") or data.get("@microsoft.graph.nextLink")

    print(f"  {len(files)} files found\n")
    return files


# ── Index building ────────────────────────────────────────────────────────────

def build_index(files: list, existing: dict | None = None) -> dict:
    """
    Folder layout on OneDrive:  videos/{Level}/{slug}/{slug}.mp4
    We extract the slug from the parent folder's last path component.
    Preserves the `codec` field from an existing index if the mp4_id is unchanged.
    """
    existing = existing or {}
    path_prefix = f"/drives/{DRIVE_ID}/root:/{ONEDRIVE_ROOT}"

    index: dict = {}
    for item in files:
        name   = item["name"].lower()
        parent = item.get("parentReference", {}).get("path", "")
        if not parent.startswith(path_prefix):
            continue
        if not name.endswith(".mp4"):
            continue

        # Parent path: .../videos/Level/slug
        slug = parent.split("/")[-1]
        if not slug:
            continue

        entry = {"mp4_id": item["id"]}
        prev  = existing.get(slug, {})
        if prev.get("mp4_id") == item["id"] and prev.get("codec"):
            entry["codec"] = prev["codec"]
        index[slug] = entry

    return index


# ── Codec detection ───────────────────────────────────────────────────────────

def detect_codec(mp4_id: str, token: str) -> str:
    """Identify video codec by reading the ftyp + moov atom prefix.
    Returns 'av1', 'h264', 'hevc', or 'unknown'. Browser support:
      h264 — universal
      hevc — Safari only
      av1  — Chrome/Edge/Firefox only (NOT Safari)
    """
    try:
        meta = graph_get(f"{GRAPH}/drives/{DRIVE_ID}/items/{mp4_id}", token)
        url  = meta.get("@microsoft.graph.downloadUrl", "")
        if not url:
            return "unknown"
        r = requests.get(url, headers={"Range": "bytes=0-65535"}, timeout=15)
        d = r.content
        brands = d[8:32]
        if b"av01" in brands:
            return "av1"
        if b"hvc1" in d or b"hev1" in d:
            return "hevc"
        if b"avc1" in d or b"avc3" in d:
            return "h264"
        return "unknown"
    except Exception:
        return "unknown"


def fill_missing_codecs(index: dict) -> None:
    """Detect codec for any entries that don't already have one."""
    token = get_access_token()
    missing = [(s, e) for s, e in index.items() if not e.get("codec")]
    if not missing:
        return
    print(f"Detecting codec for {len(missing)} new/changed videos...")
    for slug, entry in missing:
        entry["codec"] = detect_codec(entry["mp4_id"], token)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("── Build Xiao Gua OneDrive Index ──\n")
    print(f"Drive: {DRIVE_ID[:30]}...")
    print(f"Root:  {ONEDRIVE_ROOT}\n")

    print("Enumerating files from OneDrive (this may take a minute)...")
    files = enumerate_files()

    out_path = DATA_DIR / "onedrive_index.json"
    existing = json.loads(out_path.read_text()) if out_path.exists() else {}

    print("Building slug → mp4_id index...")
    index = build_index(files, existing)

    fill_missing_codecs(index)

    out_path.write_text(json.dumps(index, indent=2))
    print(f"✓ Index written: {len(index)} videos → {out_path}")

    # Cross-check against video_index.json
    video_index_path = DATA_DIR / "video_index.json"
    if video_index_path.exists():
        videos = json.loads(video_index_path.read_text())
        slugs_in_index = {v["slug"] for v in videos}
        matched = sum(1 for s in index if s in slugs_in_index)
        missing = [v["slug"] for v in videos if v["slug"] not in index]
        print(f"✓ {matched}/{len(videos)} videos matched to OneDrive files")
        if missing:
            print(f"⚠  {len(missing)} videos not found on OneDrive:")
            for s in missing[:10]:
                print(f"   {s}")
            if len(missing) > 10:
                print(f"   ...and {len(missing) - 10} more")


if __name__ == "__main__":
    main()
