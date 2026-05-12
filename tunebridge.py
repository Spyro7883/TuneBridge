# -*- coding: utf-8 -*-
"""TuneBridge — Phase 1: Foundation."""
from __future__ import annotations
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
import tkinter as tk
from tkinter import ttk


class SongStatus(str, Enum):
    QUEUED      = "Queued"
    FETCHING    = "Fetching metadata"
    DOWNLOADING = "Downloading"
    RETUNING    = "Retuning"
    AWAITING    = "Awaiting folder"
    SAVING      = "Saving"
    UPLOADING   = "Uploading"
    DONE        = "Done ✓"
    FAILED      = "Failed ✗"

    def __str__(self) -> str:
        return self.value


MOCK_STATUS_DELAYS = {
    SongStatus.QUEUED:      0.0,
    SongStatus.FETCHING:    0.3,
    SongStatus.DOWNLOADING: 0.8,
    SongStatus.RETUNING:    0.6,
    SongStatus.AWAITING:    0.2,
    SongStatus.SAVING:      0.2,
    SongStatus.UPLOADING:   0.4,
    SongStatus.DONE:        0.0,
}


class BatchTable(ttk.Frame):
    """Scrollable Treeview with per-row status tracking.

    Public API (Phase 2+ compatible):
        add_row(url, title, url_type) -> str   # returns iid
        update_row_status(row_id, status)       # safe from any thread via after()
        update_row_title(row_id, title)
        update_row_type(row_id, url_type)
        clear()                                 # reset table
    """

    _TAG_COLORS = {
        "queued":  {"foreground": "#B3B3B3"},
        "active":  {"foreground": "#FFFFFF"},
        "waiting": {"foreground": "#F59E0B"},
        "done":    {"foreground": "#1DB954"},
        "failed":  {"foreground": "#EF4444"},
    }

    _STATUS_TAG = {
        "Queued":            "queued",
        "Fetching metadata": "active",
        "Downloading":       "active",
        "Retuning":          "active",
        "Awaiting folder":   "waiting",
        "Saving":            "active",
        "Uploading":         "active",
        "Done ✓":       "done",
        "Failed ✗":     "failed",
    }

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._rows: dict[str, str] = {}
        self._build_tree()

    def _build_tree(self):
        vsb = ttk.Scrollbar(self, orient="vertical")
        self.tree = ttk.Treeview(
            self,
            columns=("title", "type", "status"),
            show="headings",
            yscrollcommand=vsb.set,
        )
        vsb.configure(command=self.tree.yview)

        self.tree.heading("title",  text="Title")
        self.tree.heading("type",   text="Type")
        self.tree.heading("status", text="Status")
        self.tree.column("title",  width=340, stretch=True,  anchor="w")
        self.tree.column("type",   width=90,  stretch=False, anchor="center")
        self.tree.column("status", width=180, stretch=False, anchor="w")

        for tag, opts in self._TAG_COLORS.items():
            self.tree.tag_configure(tag, **opts)

        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

    def add_row(self, url: str, title: str = "", url_type: str = "") -> str:
        """Add a row and return its iid."""
        if title:
            display_title = title
        else:
            display_title = (url[:60] + "...") if len(url) > 60 else url
        iid = self.tree.insert(
            "", "end",
            values=(display_title, url_type, "Queued"),
            tags=("queued",),
        )
        self._rows[iid] = url
        return iid

    def update_row_status(self, row_id: str, status: str) -> None:
        """Update row status. Must be called from main thread (via after())."""
        tag = self._STATUS_TAG.get(status, "active")
        self.tree.set(row_id, "status", status)
        self.tree.item(row_id, tags=(tag,))

    def update_row_title(self, row_id: str, title: str) -> None:
        """Phase 3 calls this to fill in the resolved title."""
        self.tree.set(row_id, "title", title)

    def update_row_type(self, row_id: str, url_type: str) -> None:
        """Phase 2 calls this after URL type detection."""
        self.tree.set(row_id, "type", url_type)

    def clear(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._rows.clear()


class TuneBridgeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("TuneBridge")
        self.geometry("800x540")
        self.minsize(640, 400)
        self._setup_styles()
        self._build_layout()

    def _setup_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        self.configure(bg="#121212")

        style.configure("TFrame",       background="#121212")
        style.configure("Card.TFrame",  background="#1A1A1A")
        style.configure("TLabel",       background="#121212", foreground="#FFFFFF",
                                        font=("Segoe UI", 10))
        style.configure("Dim.TLabel",   background="#121212", foreground="#B3B3B3",
                                        font=("Segoe UI", 9))
        style.configure("Title.TLabel", background="#121212", foreground="#1DB954",
                                        font=("Segoe UI", 18, "bold"))
        style.configure("TButton",      font=("Segoe UI", 10, "bold"), padding=6)
        style.configure("Accent.TButton", background="#1DB954", foreground="#000000")
        style.map("Accent.TButton", background=[("active", "#17A349")])
        style.configure("Treeview",
            background="#121212",
            foreground="#FFFFFF",
            rowheight=28,
            fieldbackground="#121212",
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure("Treeview.Heading",
            background="#1A1A1A",
            foreground="#B3B3B3",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview",
            background=[("selected", "#1DB954")],
            foreground=[("selected", "#000000")],
        )
        style.map("Treeview.Heading", background=[("active", "#222222")])
        style.configure("Vertical.TScrollbar",
            background="#2A2A2A",
            troughcolor="#121212",
            arrowcolor="#B3B3B3",
            borderwidth=0,
        )

    def _build_layout(self) -> None:
        # 1. Title header
        ttk.Label(self, text="TuneBridge", style="Title.TLabel").pack(
            anchor="w", padx=20, pady=(16, 4))

        # 2. Input placeholder frame (Phase 2 populates this)
        self.input_frame = ttk.Frame(self, height=60, style="TFrame")
        self.input_frame.pack(fill="x", padx=20, pady=(4, 8))
        self.input_frame.pack_propagate(False)

        # Start Demo button inside input_frame (Phase 1 only)
        self._demo_btn = ttk.Button(
            self.input_frame,
            text="Start Demo",
            style="Accent.TButton",
            command=self._start_demo,
        )
        self._demo_btn.pack(side="left", padx=8, pady=8)

        # 3. Batch table (dominant area)
        self.table = BatchTable(self)
        self.table.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # 4. Status bar (bottom)
        self._status_var = tk.StringVar(value="Ready — add songs to begin")
        ttk.Label(self, textvariable=self._status_var,
                  style="Dim.TLabel").pack(fill="x", padx=20, pady=(0, 10), anchor="w")

    def _start_demo(self) -> None:
        DEMO_URLS = [
            ("https://open.spotify.com/track/demo1", "Demo Song 1"),
            ("https://open.spotify.com/track/demo2", "Demo Song 2"),
            ("https://open.spotify.com/track/demo3", "Demo Song 3"),
            ("https://open.spotify.com/track/demo4", "Demo Song 4"),
            ("https://open.spotify.com/track/demo5", "Demo Song 5"),
        ]

        self.table.clear()
        iids = [
            self.table.add_row(url=url, title=title)
            for url, title in DEMO_URLS
        ]

        max_workers = min(len(iids), 4)
        self._status_var.set(f"Processing 0/{len(iids)}...")
        self._demo_btn.configure(state="disabled")

        def run():
            done_count = 0
            failed_count = 0
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(self._mock_worker, iid): iid for iid in iids}
                for future in as_completed(futures):
                    try:
                        future.result()
                        done_count += 1
                    except Exception:
                        iid = futures[future]
                        self.after(0, self.table.update_row_status, iid, str(SongStatus.FAILED))
                        failed_count += 1
            if failed_count == 0:
                self.after(0, self._status_var.set, f"Done — {done_count} tracks processed")
            else:
                self.after(0, self._status_var.set,
                           f"Done — {done_count} succeeded, {failed_count} failed")
            self.after(0, self._demo_btn.configure, {"state": "normal"})

        threading.Thread(target=run, daemon=True).start()

    def _mock_worker(self, row_id: str) -> None:
        """Cycles all 8 statuses with simulated delays. Replace in Phase 3+."""
        for status, delay in MOCK_STATUS_DELAYS.items():
            self.after(0, self.table.update_row_status, row_id, str(status))
            if delay > 0:
                time.sleep(delay)


if __name__ == "__main__":
    app = TuneBridgeApp()
    app.mainloop()
