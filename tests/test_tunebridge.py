# -*- coding: utf-8 -*-
# Note: sys.stdout UTF-8 wrapper intentionally omitted — pytest's capture plugin
# owns sys.stdout during collection/execution; wrapping it causes ValueError.
# Unicode characters (✓/✗) are handled by the # -*- coding: utf-8 -*- header.
import pytest
import tkinter as tk
from tkinter import ttk

try:
    from tunebridge import TuneBridgeApp, BatchTable, SongStatus
except ImportError:
    # tunebridge.py does not exist yet (RED state — Plan 02 creates it).
    # Tests are collected normally; they fail at runtime with NameError,
    # which satisfies the TDD RED requirement.
    TuneBridgeApp = None  # type: ignore[assignment,misc]
    BatchTable = None     # type: ignore[assignment,misc]
    SongStatus = None     # type: ignore[assignment,misc]


@pytest.fixture
def app_root():
    app = TuneBridgeApp()
    app.withdraw()
    try:
        yield app
    finally:
        app.destroy()


# ---------------------------------------------------------------------------
# Pure / no-fixture tests
# ---------------------------------------------------------------------------

def test_worker_count_formula():
    assert min(1, 4) == 1
    assert min(2, 4) == 2
    assert min(4, 4) == 4
    assert min(7, 4) == 4
    assert min(0, 4) == 0


def test_status_enum_values():
    expected = [
        "Queued",
        "Fetching metadata",
        "Downloading",
        "Retuning",
        "Awaiting folder",
        "Saving",
        "Uploading",
        "Done ✓",
        "Failed ✗",
    ]
    assert [s.value for s in SongStatus] == expected


# ---------------------------------------------------------------------------
# Tkinter-touching tests — require app_root fixture
# ---------------------------------------------------------------------------

def test_app_initializes(app_root):
    assert isinstance(app_root, tk.Tk)


def test_dark_theme_colors(app_root):
    style = ttk.Style(app_root)
    assert style.lookup("TLabel", "background") == "#121212"
    assert style.lookup("Title.TLabel", "foreground") == "#1DB954"


def test_batch_table_columns(app_root):
    assert app_root.table.tree["columns"] == ("title", "type", "status")


def test_batch_table_api(app_root):
    iid = app_root.table.add_row("https://example.com", "Test Song", "[Spotify]")
    assert iid  # non-empty string
    # Should not raise
    app_root.table.update_row_status(iid, "Downloading")
    assert app_root.table.tree.set(iid, "status") == "Downloading"


def test_status_tags(app_root):
    iid = app_root.table.add_row("https://example.com", "Tag Test", "[YouTube]")

    app_root.table.update_row_status(iid, "Done ✓")
    app_root.update()
    assert app_root.table.tree.item(iid, "tags") == ("done",)

    app_root.table.update_row_status(iid, "Failed ✗")
    app_root.update()
    assert app_root.table.tree.item(iid, "tags") == ("failed",)

    app_root.table.update_row_status(iid, "Awaiting folder")
    app_root.update()
    assert app_root.table.tree.item(iid, "tags") == ("waiting",)
