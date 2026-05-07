# External Integrations

**Analysis Date:** 2026-05-05

## APIs & External Services

**Spotify (read-only metadata):**
- Service: Spotify oEmbed API — resolves a Spotify track URL to a human-readable title
- Endpoint: `https://open.spotify.com/oembed?url={spotify_url}`
- SDK/Client: `urllib.request.urlopen` + `urllib.request.Request` (stdlib, no SDK)
- Auth: None — public unauthenticated endpoint
- Implementation: `spotify_to_search_query()` in `retune_app.py` (line 103–108)
- Limitation: Returns only the track title; used as a YouTube search query — not guaranteed to match the exact audio

**YouTube (download via yt-dlp CLI):**
- Service: YouTube — downloads audio for a given URL or search query
- SDK/Client: `yt-dlp` CLI tool invoked via `subprocess.Popen` (line 145)
- Auth: Firefox browser cookie jar (`--cookies-from-browser firefox`) — relies on user's local Firefox session; no API key
- JS runtime: Node.js (`--js-runtimes node`) — required for some yt-dlp extractors
- Remote component: `--remote-components ejs:github` — fetches EJS component from GitHub at runtime
- Search: Spotify links are converted to `ytsearch:{title} lyrics` query (line 129)
- Output format: MP3 at 192K extracted by yt-dlp's `-x --audio-format mp3` flags
- Implementation: `download_track()` in `retune_app.py` (line 116–173)

## Data Storage

**Databases:**
- None

**File Storage:**
- Local filesystem only
- Temporary files: `tempfile.TemporaryDirectory` used for intermediate WAV during ffmpeg encode (line 71)
- Raw download staging: per-track `_raw_{uuid8}` subdirectory inside output folder, deleted after retune (line 180–197)
- Final output: user-specified folder (default `~/Music/432hz`), MP3 files named `{original_title}.mp3`

**Caching:**
- None — each run re-downloads and re-processes; no result cache

## Authentication & Identity

**Auth Provider:**
- None — no user accounts or login
- YouTube access relies on Firefox browser cookies on the local machine (`--cookies-from-browser firefox`); if the user is not logged into YouTube in Firefox, age-restricted or private content will fail

## Monitoring & Observability

**Error Tracking:**
- None — errors surface in the GUI log widget and as Python exceptions caught per-future in `_run_all()` (line 329–336)

**Logs:**
- In-process only: GUI `Text` widget (`self.log_text`) receives all yt-dlp stdout lines and status messages via `on_log` callback; nothing written to disk

## CI/CD & Deployment

**Hosting:**
- Not applicable — local desktop application

**CI Pipeline:**
- None detected

## Environment Configuration

**Required env vars:**
- None — no environment variables used

**Secrets location:**
- No secrets — authentication is delegated to the local Firefox browser cookie store

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None — the only outbound HTTP is the Spotify oEmbed request (`spotify_to_search_query`, line 103–108) and yt-dlp's own network calls (managed internally by the yt-dlp subprocess)

## External Binary Dependencies

These are not Python packages but are required at runtime:

| Binary | Purpose | How Located | Notes |
|--------|---------|-------------|-------|
| `ffmpeg` | WAV → MP3 encode, ID3 tag copy | `shutil.which("ffmpeg")` (line 56) | Must be on PATH; absence raises `RuntimeError` |
| `yt-dlp` | YouTube audio download | `shutil.which("yt-dlp")` (line 117) | Must be on PATH; pip-installable |
| `node` | yt-dlp JS extractor runtime | passed as `--js-runtimes node` to yt-dlp | Must be on PATH for some extractors |

---

*Integration audit: 2026-05-05*
