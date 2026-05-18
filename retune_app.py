#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
432Hz Retune App – Desktop UI
Paste YouTube or Spotify links → download via yt-dlp → retune 440→432Hz.

YouTube links: downloads exactly that video (recommended!)
Spotify links: searches YouTube for best match (may not be exact)

Dependencies:
  pip install yt-dlp librosa soundfile numpy

Also requires ffmpeg installed and in PATH.
"""

import base64
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from urllib.request import urlopen, Request

import numpy as np
import librosa
import soundfile as sf

# ── Retune ────────────────────────────────────────────────────────────────────

SRC_A4 = 440.0
DST_A4 = 432.0
RATIO = DST_A4 / SRC_A4


def semitones_for_ratio(ratio: float) -> float:
    return 12.0 * math.log(ratio, 2)


def retune_file(in_path: Path, out_path: Path) -> None:
    y, sr = librosa.load(str(in_path), sr=None, mono=False)
    if y.ndim == 1:
        y = y[np.newaxis, :]

    n_steps = semitones_for_ratio(RATIO)
    channels = []
    for ch in y:
        channels.append(librosa.effects.pitch_shift(ch, sr=sr, n_steps=n_steps))

    y_out = np.clip(np.stack(channels, axis=0), -1.0, 1.0).T
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH.")

    # Read metadata from original file before encoding
    original_tags = {}
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3
        orig_id3 = ID3(str(in_path))
        for key in orig_id3:
            original_tags[key] = orig_id3[key]
    except Exception:
        pass

    with tempfile.TemporaryDirectory() as td:
        tmp_wav = Path(td) / (out_path.stem + ".wav")
        sf.write(str(tmp_wav), y_out, sr)
        cmd = [
            ffmpeg, "-y", "-i", str(tmp_wav),
            "-vn", "-codec:a", "libmp3lame", "-b:a", "192k",
            str(out_path),
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {p.stderr[:300]}")

    # Re-apply original tags with forced UTF-8 encoding via mutagen
    if original_tags:
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3
            audio = MP3(str(out_path))
            if audio.tags is None:
                audio.add_tags()
            for key, value in original_tags.items():
                # Force UTF-8 encoding (3) on all text frames
                if hasattr(value, 'encoding'):
                    value.encoding = 3  # 3 = UTF-8
                audio.tags.add(value)
            audio.save(v2_version=3)
        except Exception:
            pass


# ── Download ──────────────────────────────────────────────────────────────────

# Optional Spotify API credentials — enables ISRC + duration matching.
# Set via environment: SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET
_SP_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
_SP_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")


def _spotify_bearer_token() -> str:
    creds = base64.b64encode(f"{_SP_CLIENT_ID}:{_SP_CLIENT_SECRET}".encode()).decode()
    req = Request(
        "https://accounts.spotify.com/api/token",
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {creds}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]


def spotify_get_metadata(url: str) -> dict:
    """Returns {title, artist, duration_ms, isrc}.

    Uses Spotify Web API (client_credentials) when credentials are set,
    otherwise falls back to the public oembed endpoint.
    """
    if _SP_CLIENT_ID and _SP_CLIENT_SECRET:
        try:
            track_id = url.split("/track/")[-1].split("?")[0].split("/")[0]
            token = _spotify_bearer_token()
            req = Request(
                f"https://api.spotify.com/v1/tracks/{track_id}",
                headers={"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"},
            )
            with urlopen(req, timeout=15) as r:
                d = json.loads(r.read())
            return {
                "title": d["name"],
                "artist": ", ".join(a["name"] for a in d["artists"]),
                "duration_ms": d.get("duration_ms", 0),
                "isrc": d.get("external_ids", {}).get("isrc", ""),
            }
        except Exception:
            pass  # fall through to oembed

    # oembed: free, no credentials — returns title + author_name (artist)
    req = Request(
        f"https://open.spotify.com/oembed?url={url}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urlopen(req, timeout=15) as r:
        d = json.loads(r.read())
    return {
        "title": d.get("title", ""),
        "artist": d.get("author_name", ""),
        "duration_ms": 0,
        "isrc": "",
    }


def find_yt_music_match(meta: dict, on_log=None) -> str | None:
    """Search YouTube Music for the best audio match.

    Scores candidates by duration proximity (±2 s) and title/artist presence.
    Returns a direct YouTube Music URL or None if nothing matched.
    """
    ytdlp = shutil.which("yt-dlp")
    title = meta["title"]
    artist = meta["artist"]
    duration_ms = meta["duration_ms"]

    query = f"{artist} {title}" if artist else title
    if on_log:
        on_log(f"Searching YouTube Music: {query}")

    from urllib.parse import quote_plus
    encoded = quote_plus(query)
    cmd = [
        ytdlp, "--playlist-end", "5", "--no-check-certificate", "--no-warnings",
        "--print", "%(id)s|||%(title)s|||%(duration)s",
        f"https://music.youtube.com/search?q={encoded}",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )

    candidates = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|||")
        if len(parts) >= 3:
            vid_id = parts[0].strip()
            vid_title = parts[1].strip()
            dur_str = parts[2].strip()
            if not vid_id:
                continue
            try:
                candidates.append({
                    "id": vid_id,
                    "title": vid_title,
                    "duration_s": float(dur_str),
                })
            except ValueError:
                continue

    if not candidates:
        return None

    target_s = duration_ms / 1000.0 if duration_ms else None
    title_l = title.lower()
    artist_l = artist.lower()

    scored = []
    for c in candidates:
        score = 0.0
        vid_l = c["title"].lower()

        if target_s is not None:
            diff = abs(c["duration_s"] - target_s)
            if diff <= 2:
                score += 10.0 - diff * 2
            elif diff <= 5:
                score += 2.0

        if title_l in vid_l:
            score += 5.0
        if artist_l and artist_l in vid_l:
            score += 3.0

        scored.append((score, c))

    scored.sort(key=lambda x: -x[0])
    best_score, best = scored[0]

    if on_log:
        on_log(f"Best match: {best['title']} ({best['duration_s']:.0f}s, score={best_score:.1f})")

    # Reject if we had duration info but nothing came close
    if target_s is not None and best_score <= 0:
        return None

    return f"https://music.youtube.com/watch?v={best['id']}"


# Global lock: serialize yt-dlp calls to avoid Firefox cookie DB conflicts.
# Retune still runs in parallel (that's the slow part anyway).
_download_lock = threading.Lock()


def download_track(url: str, out_dir: Path, on_log=None) -> Path | None:
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp not found. Install: pip install yt-dlp")

    if "spotify.com" in url or "spotify:" in url:
        if on_log:
            on_log("Resolving Spotify track…")
        meta = spotify_get_metadata(url)
        if not meta["title"]:
            raise RuntimeError("Could not resolve Spotify track name.")

        search_url = find_yt_music_match(meta, on_log=on_log)
        if search_url is None:
            raise RuntimeError(
                "Not found on YouTube Music — paste a direct YouTube URL instead."
            )
    else:
        search_url = url

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        ytdlp, "--no-playlist",
        "--no-check-certificate",
        "--cookies-from-browser", "firefox",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-x", "--audio-format", "mp3", "--audio-quality", "192K",
        "-o", str(out_dir / "%(title)s.%(ext)s"),
        search_url,
    ]

    with _download_lock:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")

        # Safety timeout: kill process after 10 minutes so a stuck yt-dlp doesn't hang the pool
        def kill_if_stuck():
            try:
                if process.poll() is None:
                    process.kill()
                    if on_log:
                        on_log("⏱  Timeout — killing yt-dlp")
            except Exception:
                pass

        timer = threading.Timer(600, kill_if_stuck)
        timer.start()
        try:
            for line in process.stdout:
                line = line.strip()
                if line and on_log:
                    on_log(line)
            process.wait()
        finally:
            timer.cancel()

        if process.returncode != 0:
            raise RuntimeError("yt-dlp download failed or timed out.")

    mp3s = sorted(out_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mp3s[0] if mp3s else None


# ── Full pipeline ─────────────────────────────────────────────────────────────

def process_one(url: str, out_dir: Path, on_log=None) -> str:
    import uuid
    raw_dir = out_dir / f"_raw_{uuid.uuid4().hex[:8]}"
    downloaded = download_track(url, raw_dir, on_log=on_log)
    if not downloaded:
        raise RuntimeError("No audio file found after download.")

    if on_log:
        on_log(f"🎵 Retuning: {downloaded.name}")

    final_name = downloaded.stem + ".mp3"
    final_path = out_dir / final_name
    retune_file(downloaded, final_path)

    downloaded.unlink(missing_ok=True)
    try:
        raw_dir.rmdir()
    except OSError:
        pass

    return final_path.name


# ── GUI ───────────────────────────────────────────────────────────────────────

class RetuneApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("432 Hz Retune")
        self.geometry("620x560")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground="#b4befe")
        style.configure("Sub.TLabel", font=("Segoe UI", 8), foreground="#6c7086", background="#1e1e2e")
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6)
        style.configure("Accent.TButton", background="#b4befe", foreground="#1e1e2e")
        style.map("Accent.TButton", background=[("active", "#89b4fa")])

        pad = {"padx": 20, "pady": (6, 2)}

        ttk.Label(self, text="♫  432 Hz Retune", style="Title.TLabel").pack(pady=(18, 6))

        # Links
        ttk.Label(self, text="YouTube / Spotify Links  (one per line):").pack(anchor="w", **pad)
        self.links_text = tk.Text(self, height=6, bg="#313244", fg="#cdd6f4",
                                   font=("Consolas", 10), relief="flat", wrap="word",
                                   insertbackground="#cdd6f4")
        self.links_text.pack(padx=20, pady=(0, 6), fill="x")
        ttk.Label(self, text="💡  YouTube links = audio exact  ·  Spotify links = best match pe YouTube Music",
                  style="Sub.TLabel").pack(padx=24, anchor="w")

        # Output folder
        ttk.Label(self, text="Output Folder:").pack(anchor="w", **pad)
        folder_frame = ttk.Frame(self)
        folder_frame.configure(style="TLabel")
        folder_frame.pack(padx=20, fill="x", pady=(0, 6))
        self.folder_var = tk.StringVar(value=str(Path.home() / "Music" / "432hz"))
        ttk.Entry(folder_frame, textvariable=self.folder_var, width=52).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_frame, text="Browse…", command=self._browse).pack(side="right", padx=(6, 0))

        # Workers
        opt_frame = ttk.Frame(self)
        opt_frame.configure(style="TLabel")
        opt_frame.pack(padx=20, fill="x", pady=(4, 2))
        ttk.Label(opt_frame, text="Parallel tracks:").pack(side="left")
        self.workers_var = tk.IntVar(value=2)
        ttk.Spinbox(opt_frame, from_=1, to=6, textvariable=self.workers_var, width=4).pack(side="left", padx=(6, 0))

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.configure(style="TLabel")
        btn_frame.pack(pady=12)
        self.go_btn = ttk.Button(btn_frame, text="Download & Retune ▶", style="Accent.TButton", command=self._start)
        self.go_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(btn_frame, text="Stop ■", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)

        # Progress
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var).pack(padx=20, anchor="w")
        self.progress = ttk.Progressbar(self, mode="determinate", length=580)
        self.progress.pack(padx=20, pady=(4, 0))

        # Log
        self.log_text = tk.Text(self, height=7, bg="#313244", fg="#a6adc8",
                                font=("Consolas", 9), relief="flat", wrap="word",
                                insertbackground="#a6adc8")
        self.log_text.pack(padx=20, pady=(10, 18), fill="both", expand=True)

        self._cancel = False

    def _browse(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.folder_var.set(d)

    def _log(self, msg: str):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _stop(self):
        self._cancel = True
        self.after(0, self._log, "⏹  Stopping after current tracks…")

    def _parse_links(self) -> list[str]:
        raw = self.links_text.get("1.0", "end").strip()
        links = []
        for line in raw.splitlines():
            line = line.strip()
            if line and ("spotify.com" in line or "spotify:" in line
                         or "youtube.com" in line or "youtu.be" in line):
                links.append(line)
        return links

    def _start(self):
        links = self._parse_links()
        if not links:
            messagebox.showwarning("Input needed", "Paste at least one link.")
            return

        self._cancel = False
        self.go_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress["value"] = 0
        self.progress["maximum"] = len(links)
        self.log_text.delete("1.0", "end")
        self.status_var.set(f"0 / {len(links)} tracks")

        threading.Thread(
            target=self._run_all,
            args=(links, Path(self.folder_var.get().strip()), self.workers_var.get()),
            daemon=True,
        ).start()

    def _run_all(self, links, out_dir, workers):
        done, failed, total = 0, 0, len(links)
        lock = threading.Lock()

        def on_log(msg):
            self.after(0, self._log, f"   {msg}")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(process_one, url, out_dir, on_log): url for url in links if not self._cancel}

            for future in as_completed(futures):
                url = futures[future]
                with lock:
                    try:
                        name = future.result()
                        done += 1
                        self.after(0, self._log, f"✓  [{done + failed}/{total}] {name}")
                    except Exception as e:
                        failed += 1
                        short = url[:60] + "…" if len(url) > 60 else url
                        self.after(0, self._log, f"✗  [{done + failed}/{total}] {short}: {e}")
                    d, f = done, failed
                self.after(0, lambda d=d, f=f: (
                    self.progress.configure(value=d + f),
                    self.status_var.set(f"{d + f} / {total}  (✓ {d}  ✗ {f})"),
                ))

        self.after(0, self.status_var.set, f"Done! ✓ {done}  ✗ {failed}")
        self.after(0, lambda: self.go_btn.configure(state="normal"))
        self.after(0, lambda: self.stop_btn.configure(state="disabled"))
        if done:
            self.after(0, lambda: messagebox.showinfo(
                "Done!", f"✓ {done} tracks saved to:\n{out_dir}" + (f"\n✗ {failed} failed" if failed else "")
            ))


if __name__ == "__main__":
    RetuneApp().mainloop()