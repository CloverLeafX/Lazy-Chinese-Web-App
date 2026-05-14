# Lazy Chinese Web App — Decisions Log

---

## D1: Azure AD app registration ✓ RESOLVED

**Decision:** App registered as `Lazy Chinese Web App` (ID `19d8d3f3-a031-4a3b-b5a2-d66e6dd8c57f`) in the `humecorporation` tenant. Delegated permissions: `Files.Read` + `Files.Read.All` (tenant admin approved both). "Allow public client flows" enabled for device code flow.

**Note:** Device code flow requires no `client_secret` in the token polling request — only `client_id`, `device_code`, and `grant_type`. The app is a public client.

---

## D2: OneDrive path ✓ RESOLVED

**Decision:** The correct OneDrive root for the downloads folder is:
```
My Documents OneDrive/Python Apps/Canto_Mando_App/Lazy Chinese/downloads
```

The original plan had an incorrect path (`Python Apps/Canto/Lazy Chinese/downloads`). Discovered the correct path via Graph API shares endpoint and drive root enumeration.

---

## D3: Bunny videos — embed or native player

**Decision:** Keep iframe embed. Unified player UX is a Phase 5 concern only if subtitle sync on Bunny videos is needed.

---

## D4: Pinyin annotations

**Decision:** Keep MandarinSpot (third-party CDN script). It's proven and includes a popup dictionary. Revisit only if MandarinSpot goes down.

---

## D5: Port number

Yi_Web_App runs on 8801. This app runs on **8802**.

---

## D6: Refresh token storage ✓ RESOLVED

**Local dev:** Stored in `data/tokens.json`. Flask writes the updated token after each refresh. Auto-rotates.

**Railway:** Stored as `MS_TOKENS` env var (full token JSON as a string). Flask reads it at startup; token refreshes happen in-memory only (the env var is not updated). When the refresh token eventually expires, update `MS_TOKENS` via `railway variables set`. A Railway Volume was considered but skipped — the Volume adds complexity and `MS_TOKENS` is simpler for a single-user app.

---

## D7: Watch state — JSON file vs. SQLite

**Decision:** Start with `watch_state.json`. Same pattern as Yi_Web_App's `captures.json`. Switch to SQLite only if it becomes a bottleneck (unlikely for a single-user app with ~500 entries).

---

## D8: Videos not found during reindex

**Decision:** Log unmatched entries to stdout and write to `data/reindex_misses.json`. The video card shows a "not available" state rather than breaking. Re-run `POST /admin/reindex` after fixing files on OneDrive.

**Outcome:** All 441 videos matched on first run — no misses.

---

## D9: OneDrive folder name matching strategy ✓ RESOLVED

**Problem:** OneDrive sanitizes special characters (`?`, `:`, `*`, `"`) in folder names to `_`, so exact path matching fails.

**Decision:** Match on the short video ID prefix only — the first component of the folder name before the `  ` double-space separator. Example: folder `l5K9ag0O  Men that we wouldn_t date` → short ID `l5k9ag0o`. This is stable across renaming.

---

## D10: Client secret in .env

The `.env` has `MS_CLIENT_SECRET` but it is **not used** in token requests (device code flow is public client). It's kept in `.env` for potential future use (e.g. client credentials flow for background refresh). The auth flow only uses `MS_CLIENT_ID`, `MS_TENANT_ID`, and the stored refresh token.

---

## D11: Standalone deploy vs. Blueprint mount under Canto_Mando_Viewer ✓ RESOLVED

**Decision:** Deploy the Lazy Chinese Web App as a standalone Railway service, not mounted as a Blueprint under Canto_Mando_Viewer.

**Why:** Two blockers made the combined deploy impractical:
1. **Space in directory name** — `cd "Lazy Chinese Web App"` and `--chdir "Lazy Chinese Web App"` both fail in Railway's shell. Workaround (`wsgi.py` at repo root) applies cleanly to standalone but would complicate Blueprint mounting.
2. **OOM from pycantonese** — Canto_Mando_Viewer loads pycantonese corpus (~50-100MB) at startup, causing Railway to kill the process before it could serve requests. Removing it would gut the Viewer's Jyutping features.

Standalone deploy isolates the two apps cleanly. The Blueprint mount code (`lazy_bp`) remains in `server.py` in case it's needed for a local combined server in future.

---

## D12: Data files committed to git vs. Railway Volume

**Decision:** Commit `data/onedrive_index.json`, `data/watch_state.json`, and `data/all_videos_*.json` to git rather than using a Railway Volume.

**Why:** The Volume approach requires manual uploads via Railway shell after each deploy and adds a persistent-storage cost. For the initial launch, the committed files (441 videos, 18 watch entries) are a good starting snapshot. Watch history resets on redeploy — an acceptable trade-off until the watch count grows enough to matter (Phase 5 can add the Volume then). `tokens.json` is kept out of git and stored as `MS_TOKENS` env var instead.
