---
phase: 2
slug: input-detection
status: approved
framework: PySide6
created: 2026-05-13
reviewed_at: 2026-05-13
---

# Phase 2: Input & Detection — UI Design Contract

> Visual and interaction contract for Phase 2.
> Framework: PySide6 (Qt 6.x) — Liquid Glass aesthetic via QSS.
> **Updated 2026-05-13**: Migrated from tkinter/ttk to PySide6.

---

## Design System

| Property | Value |
|----------|-------|
| Framework | PySide6 6.x |
| Styling | QSS (Qt Style Sheets) |
| Widget set | QMainWindow, QTableWidget, QTextEdit, QStatusBar |
| Icon library | none |
| Font | Segoe UI via QFont |

---

## Liquid Glass QSS Theme

Constant `TUNEBRIDGE_QSS` — applied via `self.setStyleSheet(TUNEBRIDGE_QSS)` in `TuneBridgeApp.__init__`:

```python
TUNEBRIDGE_QSS = """
QMainWindow, QWidget {
    background-color: #121212;
    color: #FFFFFF;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QLabel#title_label {
    color: #1DB954;
    font-size: 18pt;
    font-weight: bold;
    padding: 8px 0px 4px 0px;
}
QTableWidget {
    background-color: rgba(26, 26, 26, 220);
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 8px;
    gridline-color: rgba(255, 255, 255, 10);
    outline: none;
}
QTableWidget::item {
    padding: 4px 8px;
    color: #B3B3B3;
    border: none;
}
QTableWidget::item:selected {
    background-color: rgba(29, 185, 84, 51);
}
QHeaderView::section {
    background-color: rgba(26, 26, 26, 200);
    color: #B3B3B3;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 20);
    padding: 6px 8px;
    font-weight: bold;
    font-size: 9pt;
}
QTextEdit {
    background-color: rgba(26, 26, 26, 153);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: 6px;
    color: #555555;
    padding: 8px;
    selection-background-color: rgba(29, 185, 84, 76);
}
QStatusBar {
    background-color: #121212;
    color: #B3B3B3;
    font-size: 9pt;
}
QScrollBar:vertical {
    background: #1A1A1A;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #555555;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
```

---

## Color Tokens

| Role | Hex | Qt usage |
|------|-----|----------|
| Background | `#121212` | QMainWindow/QWidget bg |
| Surface | `#1A1A1A` | QTableWidget bg, QHeaderView bg |
| Accent | `#1DB954` | Spotify badge, Done status, title label, selection |
| Destructive | `#EF4444` | YouTube badge, Invalid URL badge, Failed status |
| Warning | `#F59E0B` | "Awaiting folder" status |
| Primary text | `#FFFFFF` | Active row items |
| Dim text | `#B3B3B3` | Queued row items, headings, status bar |
| Placeholder | `#555555` | QTextEdit fg when empty (via QSS) |

Colors on table cells applied via `QTableWidgetItem.setForeground(QBrush(QColor(hex)))`.

---

## Typography

| Role | QFont spec | Usage |
|------|-----------|-------|
| Title | `QFont("Segoe UI", 18, QFont.Weight.Bold)` | Title QLabel |
| Body | `QFont("Segoe UI", 10)` | Table cells, paste area |
| Column heading | `QFont("Segoe UI", 9, QFont.Weight.Bold)` | QHeaderView sections |

---

## Spacing

| Slot | Value | Usage |
|------|-------|-------|
| Window margins | 20px sides, 16px top, 8px bottom | `layout.setContentsMargins(20, 16, 20, 8)` |
| Widget spacing | 8px | `layout.setSpacing(8)` |
| Table row height | 28px | `verticalHeader().setDefaultSectionSize(28)` |
| Paste area height | 88px (~4 lines) | `setFixedHeight(88)` |

---

## Components

### 1. PasteTextEdit — `QTextEdit` subclass

Replaces the Phase 1 demo button. Single entry point for user action.

```python
class PasteTextEdit(QTextEdit):
    PLACEHOLDER = "Paste Spotify or YouTube URLs here (one per line)"
    urls_pasted = Signal(str)   # emits raw clipboard text on paste

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(self.PLACEHOLDER)
        self.setFixedHeight(88)
        self.setAcceptRichText(False)

    def insertFromMimeData(self, source: QMimeData) -> None:
        raw = source.text() if source.hasText() else ""
        if raw.strip():
            self.urls_pasted.emit(raw)
        # Do NOT call super() — suppresses default text insertion
```

**State:** widget always empty after paste (no text visible — placeholder shown by Qt).

---

### 2. BatchTable — `QWidget` wrapping `QTableWidget`

Columns (fixed order, indices 0/1/2): `["Title", "Type", "Status"]`

```python
class BatchTable(QWidget):
    COLUMNS = ["Title", "Type", "Status"]

    _STATUS_COLORS: dict[str, QColor] = {
        "Queued":            QColor("#B3B3B3"),
        "Fetching metadata": QColor("#FFFFFF"),
        "Downloading":       QColor("#FFFFFF"),
        "Retuning":          QColor("#FFFFFF"),
        "Awaiting folder":   QColor("#F59E0B"),
        "Saving":            QColor("#FFFFFF"),
        "Uploading":         QColor("#FFFFFF"),
        "Done":              QColor("#1DB954"),
        "Failed":            QColor("#EF4444"),
        "Skipped — bad URL": QColor("#EF4444"),
    }

    _TYPE_COLORS: dict[str, QColor] = {
        "Spotify":     QColor("#1DB954"),
        "YouTube":     QColor("#EF4444"),
        "Invalid URL": QColor("#EF4444"),
    }
```

`add_row(url, title, url_type) -> int` returns row index (int, not str iid).
`update_row_status(row_id: int, status: str) -> None` — must be called on main thread.
`clear() -> None`

---

### 3. Type Badge Colors

| URL type | Type column text | QColor |
|----------|-----------------|--------|
| Spotify URL | `"Spotify"` | `#1DB954` |
| YouTube URL | `"YouTube"` | `#EF4444` |
| Invalid | `"Invalid URL"` | `#EF4444` |

Applied via `type_item.setForeground(QBrush(QColor(hex)))` on column index 1.
Type color is permanent — `update_row_status()` must NOT overwrite column 1.

---

### 4. ErrorRowState

| Column | Value | Color |
|--------|-------|-------|
| Type (col 1) | `"Invalid URL"` | `#EF4444` |
| Status (col 2) | `"Skipped — bad URL"` | `#EF4444` |

Set synchronously in `add_row()` when `url_type == "Invalid URL"`.

---

### 5. StatCard — Bento Grid widget

Two cards in a `QHBoxLayout` between paste box and batch table.

```python
class StatCard(QWidget):
    def count(self) -> int: ...
    def set_count(self, n: int) -> None: ...
```

| Card | label | color_hex | sublabel |
|------|-------|-----------|---------|
| `_card_valid` | `"Valide"` | `#1DB954` | `"Spotify + YouTube"` |
| `_card_invalid` | `"Invalide"` | `#EF4444` | `"URL-uri eronate"` |

QSS per card (rgba values from `color_hex`):
- Background: `rgba(r, g, b, 15)` — subtle tint
- Border: `1px solid rgba(r, g, b, 46)`
- Border-radius: `8px`, padding `14px 16px`
- Count label: `font-size: 26pt; font-weight: bold; color: {color_hex}`

Updated by `_process_urls()` after every paste. Reset to 0 via `table._on_clear` callback.

---

### 6. _Dispatcher — thread-safe UI bridge

Replaces Phase 1 `queue.Queue` + `after()` polling pattern.

```python
class _Dispatcher(QObject):
    row_status_changed = Signal(int, str)   # row_id, new_status

    def __init__(self, table: BatchTable):
        super().__init__()
        self.row_status_changed.connect(table.update_row_status)
```

Worker threads call `dispatcher.row_status_changed.emit(row_id, status)`.
Qt signal/slot crosses thread boundary safely; `update_row_status` executes on main thread.

---

## Interaction Contracts

### Paste sequence

1. User pastes (Ctrl+V) into PasteTextEdit
2. `insertFromMimeData` fires; reads `source.text()`, emits `urls_pasted`
3. Default insertion suppressed (no `super()` call) — widget stays empty
4. `TuneBridgeApp._process_urls(raw)` handles:
   a. Split by `\n`, strip each line, skip blank lines
   b. Classify each via `classify_url()`
   c. `table.add_row()` for each URL (valid or invalid)
5. Status bar updated via `self.statusBar().showMessage(...)`

### Classification logic

```
classify_url(url: str) -> str | None
  _SPOTIFY_RE = re.compile(r'open\.spotify\.com/(track|album|playlist|artist)/')
  _YOUTUBE_RE = re.compile(r'(youtube\.com/watch\?.*v=|youtu\.be/)')
  returns "Spotify" | "YouTube" | None
```

Module-level function — importable without PySide6 fixture.

### Status bar messages

| Condition | Message |
|-----------|---------|
| Valid batch pasted | `"{N} URL(s) added — paste more or start processing"` |
| All invalid | `"No valid URLs found — check your links"` |
| Initial | `"Ready — add songs to begin"` |

---

## Copy / Strings

| Element | Exact String |
|---------|--------------|
| Placeholder text | `"Paste Spotify or YouTube URLs here (one per line)"` |
| Spotify badge | `"Spotify"` |
| YouTube badge | `"YouTube"` |
| Invalid badge | `"Invalid URL"` |
| Invalid row status | `"Skipped — bad URL"` |
| Status bar — valid batch | `"{N} URL(s) added — paste more or start processing"` |
| Status bar — all invalid | `"No valid URLs found — check your links"` |
| Status bar — initial | `"Ready — add songs to begin"` |

Note: em dash `—` (U+2014) in status strings, not double hyphen.

---

## Phase 3 Interface Contract

| Data | Location | Access method |
|------|----------|---------------|
| Row id | returned by `add_row()` | `int` row index |
| URL string | `table._rows[row_id]` | direct dict access |
| URL type | Type column (index 1) | `table._table.item(row_id, 1).text()` → `"Spotify"` / `"YouTube"` |
| Skip flag | Status column (index 2) | `"Skipped — bad URL"` rows skipped by Phase 3 |

---

## Registry Safety

| Registry | Usage | Safety Gate |
|----------|-------|-------------|
| PySide6 | Qt 6.x bindings — stdlib-equivalent | No third-party registries |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS (Liquid Glass QSS)
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS — PySide6 only

**Approval:** ✓ APPROVED — 2026-05-13 (updated for PySide6 migration)
