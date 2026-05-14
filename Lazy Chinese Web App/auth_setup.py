#!/usr/bin/env python3
"""
One-time setup: authenticate with Microsoft Graph API using device code flow.
Writes data/tokens.json and updates .env with MS_DRIVE_ID.

Usage:
    python auth_setup.py
"""
import json, os, re, sys, time, traceback
from pathlib import Path
import requests
from dotenv import load_dotenv

HERE     = Path(__file__).parent
ENV_PATH = HERE / ".env"
DATA_DIR = HERE / "data"
LOG_PATH = HERE / "data" / "auth_log.txt"

DATA_DIR.mkdir(exist_ok=True)
load_dotenv(ENV_PATH)

log_file = open(LOG_PATH, "w", buffering=1)

def log(msg=""):
    print(msg, flush=True)
    log_file.write(msg + "\n")
    log_file.flush()

CLIENT_ID     = os.environ.get("MS_CLIENT_ID", "")
TENANT_ID     = os.environ.get("MS_TENANT_ID", "")
CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")
SCOPES        = "Files.Read offline_access User.Read"
TOKEN_URL     = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"


def request_device_code():
    log("Requesting device code...")
    r = requests.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/devicecode",
        data={"client_id": CLIENT_ID, "scope": SCOPES},
    )
    log(f"  Status: {r.status_code}")
    data = r.json()
    if r.status_code != 200:
        log(f"  Error: {data}")
        r.raise_for_status()
    return data


def poll_for_token(device_code, interval):
    log("Polling for token (waiting for sign-in)...")
    payload = {
        "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
        "client_id":   CLIENT_ID,
    }

    while True:
        time.sleep(interval)
        r = requests.post(TOKEN_URL, data=payload)
        data = r.json()
        err  = data.get("error", "")
        if "access_token" in data:
            log("  Token received.")
            log(f"  Has refresh_token: {'refresh_token' in data}")
            log(f"  Scopes granted: {data.get('scope', 'unknown')}")
            return data
        if err == "authorization_pending":
            log("  Still waiting...", )
            continue
        if err == "slow_down":
            interval += 5
            continue
        log(f"  Auth failed: {data}")
        raise RuntimeError(f"Auth failed: {data}")


def get_drive_id(access_token):
    log("Getting OneDrive drive ID...")
    r = requests.get(
        "https://graph.microsoft.com/v1.0/me/drive",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    log(f"  Status: {r.status_code}")
    if r.status_code != 200:
        log(f"  Error: {r.text}")
        r.raise_for_status()
    drive_id = r.json()["id"]
    log(f"  Drive ID: {drive_id}")
    return drive_id


def save_tokens(tokens):
    path = DATA_DIR / "tokens.json"
    payload = {
        "access_token":  tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at":    time.time() + tokens.get("expires_in", 3600) - 60,
    }
    path.write_text(json.dumps(payload, indent=2))
    log(f"  Tokens saved → {path}")


def write_drive_id_to_env(drive_id):
    text = ENV_PATH.read_text()
    if "MS_DRIVE_ID=" in text:
        text = re.sub(r"^#?\s*MS_DRIVE_ID=.*$", f"MS_DRIVE_ID={drive_id}", text, flags=re.MULTILINE)
    else:
        text += f"\nMS_DRIVE_ID={drive_id}\n"
    ENV_PATH.write_text(text)
    log(f"  .env updated → MS_DRIVE_ID={drive_id}")


def main():
    log("── Lazy Chinese Web App — Auth Setup ──\n")
    log(f"CLIENT_ID: {CLIENT_ID[:8]}..." if CLIENT_ID else "CLIENT_ID: MISSING")
    log(f"TENANT_ID: {TENANT_ID[:8]}..." if TENANT_ID else "TENANT_ID: MISSING")
    log(f"SECRET:    {'set' if CLIENT_SECRET else 'NOT SET'}\n")

    dc = request_device_code()
    log(f"\n1. Open:  {dc['verification_uri']}")
    log(f"2. Enter: {dc['user_code']}\n")
    log("Waiting for sign-in...\n")

    tokens   = poll_for_token(dc["device_code"], dc.get("interval", 5))
    drive_id = get_drive_id(tokens["access_token"])

    log("\nSaving tokens...")
    save_tokens(tokens)
    write_drive_id_to_env(drive_id)

    log("\n✓ Done. Next step: run  python build_index.py")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("\n--- ERROR ---")
        log(traceback.format_exc())
        sys.exit(1)
    finally:
        log_file.close()
