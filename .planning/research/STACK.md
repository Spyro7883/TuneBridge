# TuneBridge — Stack Research (v1.0 New Features)

**Date:** 2026-05-06
**Scope:** YouTube URL direct input + per-song folder selection
**Confidence:** MEDIUM-HIGH (yt-dlp Python API stable since 2021; no live doc verification)

---

## Key Findings

- **Zero new pip dependencies.** `yt-dlp` is already installed as CLI binary and Python package. `import yt_dlp` available without additional installs.
- **URL detection already implemented** in `retune_app.py` lines 121 and 291. Reuse verbatim in `YouTubeService`.
- **Info extraction without downloading** — `--dump-json --skip-download` via subprocess (consistent with existing pattern).
- **Direct URL download vs search is one-line change** — only the final argument differs; all other yt-dlp flags are identical.
- **`--no-playlist` is critical** — without it, watch URLs with `list=PLxxx` download the entire playlist.
- **YouTube metadata has no album/release-type** — `title` and `uploader`/`channel` only; `StorageService` must default to "Singles" bucket for YouTube-sourced tracks.

---

## yt-dlp URL Detection

```python
def is_youtube_url(url: str) -> bool:
    return (
        "youtube.com/watch" in url
        or "youtu.be/" in url
        or "youtube.com/shorts/" in url
        or "music.youtube.com/watch" in url
    )

def is_spotify_url(url: str) -> bool:
    return "open.spotify.com/track" in url or "spotify:" in url
```

**Reject with user message:** `youtube.com/playlist`, `youtube.com/@handle`, `youtube.com/channel/` — not single tracks.

---

## yt-dlp Info Extraction (no download)

```python
cmd = [ytdlp, "--dump-json", "--no-playlist", "--skip-download",
       "--cookies-from-browser", "firefox",
       "--js-runtimes", "node", "--remote-components", "ejs:github",
       url]
result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
info = json.loads(result.stdout)
# Fields: info["title"], info["uploader"], info["channel"], info["duration"], info["id"]
```

### Info Dict Key Fields

| Field | Type | Notes |
|-------|------|-------|
| `title` | str | Raw unsanitized title |
| `uploader` | str | Channel display name |
| `channel` | str | Same as uploader usually |
| `duration` | int or None | Seconds; None for live streams |
| `id` | str | 11-char video ID |
| `webpage_url` | str | Canonical URL |

**Guard:** `info.get("duration") or 0` — duration is `None` for live/premiere streams.

---

## Direct Download vs Search

```python
# YouTube URL: pass directly
download_target = url

# Spotify (existing): construct ytsearch prefix
download_target = f"ytsearch:{title} lyrics"
```

All other flags (`-x`, `--audio-format mp3`, `--no-playlist`, etc.) are identical. No new flags needed.

### ytsearch Info Extraction Note

`ytsearch:` info extraction returns a playlist wrapper — `info["entries"][0]` gives the first result. Direct YouTube URLs return the dict directly with no `entries` wrapper. Handle both cases in `YouTubeService.extract_info()`.

---

## Dependencies Summary

| Package | Action | Notes |
|---------|--------|-------|
| `yt-dlp` | No change — already installed | `--dump-json` flag sufficient |
| `json` | No change — stdlib | Parse `--dump-json` output |
| `subprocess` | No change — existing pattern | Keep for consistency + `_download_lock` |

**Verdict: Zero new dependencies for this milestone.**

---

## Version Notes

- yt-dlp uses date-stamped releases (not semver). Python API and `--dump-json` stable throughout.
- `--cookies-from-browser firefox` serialized by `_download_lock` — correct mitigation already in place.
- Title in info dict is raw — use yt-dlp's `-o %(title)s.%(ext)s` template for filesystem-safe filenames.
- Recommend `requirements.txt` entry: `yt-dlp>=2024.1.0` (no upper bound).

---

## Roadmap Implications

- `YouTubeService` needs two methods: `extract_info(url)` → metadata dict, `download(url, out_dir)` → Path
- `extract_info` runs before folder confirmation dialog (provides title/channel for folder proposal)
- `download` runs after user confirms folder
- Pipeline branch: `is_youtube_url()` → skip `SpotifyService` entirely, go straight to `YouTubeService.extract_info()`
- `StorageService.propose_folder()` needs a `release_type` param that defaults to `"single"` when source is YouTube

## Open Questions

- Whether `--remote-components ejs:github` is still required in current yt-dlp builds (verify when testing)
- Whether `_download_lock` should also guard `--dump-json` info extraction calls (conservative: yes, same Firefox cookie DB risk)

---

*Stack research: 2026-05-06 — focused on v1.0 new features only*
