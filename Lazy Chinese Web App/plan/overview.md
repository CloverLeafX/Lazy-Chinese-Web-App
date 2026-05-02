# Lazy Chinese Web App — Overview

## What We're Building

A hosted web application that replaces the current standalone `browser.html` file with a proper client-server architecture. The app lets you browse, watch, and track progress through the 441-video Lazy Chinese library. Videos stream directly from OneDrive (SharePoint CDN) via the Microsoft Graph API — no video files need to be uploaded or re-hosted.

## Problems With the Current Setup

| Problem | Current state |
|---|---|
| Watch history lives in browser localStorage | Lost if you clear browser, can't share across devices |
| Videos need a manual file picker or CDN embed | Can't just click play on a downloaded MP4 |
| SRT files fall back to CDN only | Local copies exist but aren't reliably served |
| No server = no remote access | Only works as a local file on one machine |
| Static HTML can't be extended | Everything is crammed into one 1,100-line file |

## Goals

1. **Browse the library** — same filters as today (level, teacher, platform, duration, watched status, search)
2. **Play videos** — stream downloaded MP4s directly from OneDrive CDN; fall back to YouTube or Bunny embed
3. **Sync subtitles** — serve local `.srt` files (simplified + traditional); fall back to Lazy Chinese CDN
4. **Track progress** — mark Watched / Unwatch, stored server-side so it survives browser clears and works across devices
5. **Access from anywhere** — Flask server deployed to the cloud; videos served from Microsoft's CDN (the 180 GB never moves)

## Out of Scope (for now)

- Re-encoding or transcoding videos
- Multi-user support (single-user watch state is fine)
- Replacing `downloader.py` (it stays as-is)
