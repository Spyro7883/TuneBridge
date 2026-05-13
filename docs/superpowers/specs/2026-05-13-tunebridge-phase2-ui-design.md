# TuneBridge Phase 2 — UI Design Spec

**Date:** 2026-05-13
**Phase:** 02-input-detection
**Status:** Approved

---

## Context

Phase 2 delivers URL paste-and-classify: users paste mixed Spotify/YouTube URLs and see
type badges instantly. This spec applies the 2026 Liquid Glass + Bento Grid design language
(mockup.txt) to the PySide6 desktop app.

**Framework decision:** PySide6 + QSS. True `backdrop-filter` not available in Qt — Liquid
Glass approximated with `rgba` backgrounds and semi-transparent borders. This was chosen over
PyWebView/Flet to avoid a full rewrite and keep Phase 1 architecture intact.

---

## Layout — Bento Grid

Window is a vertical `QVBoxLayout` with four zones:

```
┌─────────────────────────────────────────┐
│  TuneBridge                (title label) │
├─────────────────────────────────────────┤
│  Paste Spotify or YouTube URLs here…    │
│                         (PasteTextEdit) │
├────────────────────┬────────────────────┤
│  2  Valide         │  1  Invalide        │
│     Spotify+YouTube│     URL-uri eronate │
│       (StatCard)   │       (StatCard)    │
├────────────────────┴────────────────────┤
│  Title            │ Type   │ Status      │
│  open.spotify.com │Spotify │ Queued      │
│  youtu.be/…       │YouTube │ Queued      │
│  bad-url.com      │Invalid │ Skipped…    │
│                (BatchTable / QTableWidget)│
├─────────────────────────────────────────┤
│  2 URL(s) added — paste more…  (QStatusBar)│
└─────────────────────────────────────────┘
```

The two `StatCard` widgets sit in a `QHBoxLayout` between the paste box and the batch table.
They update synchronously inside `_process_urls()` after every paste.

---

## New Component: StatCard

A minimal `QWidget` subclass — green-tinted for valid URLs, red-tinted for invalid.

```python
class StatCard(QWidget):
    def __init__(self, label: str, color: QColor, parent=None):
        super().__init__(parent)
        # QHBoxLayout: big number QLabel + stacked label/sublabel
        ...

    def set_count(self, n: int) -> None:
        self._count_label.setText(str(n))
```

**Valid card** (`#1DB954` tint):
- Background: `rgba(29, 185, 84, 0.06)`
- Border: `1px solid rgba(29, 185, 84, 0.18)`
- Label: "Valide" · sublabel: "Spotify + YouTube"

**Invalid card** (`#EF4444` tint):
- Background: `rgba(239, 68, 68, 0.06)`
- Border: `1px solid rgba(239, 68, 68, 0.15)`
- Label: "Invalide" · sublabel: "URL-uri eronate"

Both cards: `border-radius: 8px`, padding `14px 16px`, number font `26px bold`.

---

## Data Flow — _process_urls update

After classifying URLs, `_process_urls` calls `_update_stat_cards()`:

```python
def _process_urls(self, raw: str) -> None:
    # ... existing classify + add_row logic ...
    valid = sum(1 for u in candidates if classify_url(u) is not None)
    invalid = len(candidates) - valid
    self._card_valid.set_count(valid)
    self._card_invalid.set_count(invalid)
```

Cards reset to 0 on `table.clear()`.

---

## Liquid Glass QSS — Key Values

| Surface | bg | border |
|---------|-----|--------|
| QTableWidget | `rgba(26,26,26,220)` | `rgba(255,255,255,20)` |
| PasteTextEdit | `rgba(26,26,26,153)` | `rgba(255,255,255,25)` |
| StatCard valid | `rgba(29,185,84,15)` | `rgba(29,185,84,46)` |
| StatCard invalid | `rgba(239,68,68,15)` | `rgba(239,68,68,38)` |
| QHeaderView | `rgba(26,26,26,200)` | bottom only |

All `border-radius: 6–8px`. No `backdrop-filter` — Qt does not support it.

---

## Color Tokens (unchanged from Phase 1)

| Role | Hex |
|------|-----|
| Background | `#121212` |
| Surface | `#1A1A1A` |
| Accent / Spotify / Done | `#1DB954` |
| Destructive / YouTube / Failed | `#EF4444` |
| Warning | `#F59E0B` |
| Primary text | `#FFFFFF` |
| Dim text | `#B3B3B3` |
| Placeholder | `#555555` |

---

## Changes to GSD Plans

### 02-UI-SPEC.md
- Add `StatCard` component spec (constructor, `set_count`, QSS values)
- Add `QHBoxLayout` stat-cards zone to layout section
- Update `_process_urls` interaction contract to include card update step

### 02-01-PLAN.md (test scaffold)
- Add 2 new RED tests:
  - `test_stat_cards_after_paste` — valid/invalid counts correct after paste
  - `test_stat_cards_reset_on_clear` — both cards show 0 after `table.clear()`

### 02-02-PLAN.md (implementation)
- Add `StatCard` widget to tunebridge.py (Task 1 extension)
- Wire `_card_valid` and `_card_invalid` in `TuneBridgeApp.__init__`
- Update `_process_urls` to call `_update_stat_cards()` (Task 2 extension)

---

## Success Criteria

1. Two stat cards visible between paste box and batch table
2. After pasting 2 Spotify + 1 YouTube + 1 invalid: Valid=3, Invalid=1
3. After `table.clear()`: both cards show 0
4. Cards use correct tint colors per type
5. All 20 tests pass (18 existing + 2 new stat card tests)
