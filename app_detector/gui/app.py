"""CustomTkinter GUI — a virtualized card-gallery over the scanned apps.

No sidebar: a slim top bar carries the wordmark, the Scan/Restore mode tabs and
the primary action. Below it sit a filter row (size pills · kind toggles · manual
switch · search), a live summary, and a grid of teal-accented app *cards*.

The grid (:class:`CardGrid`) is **virtualized**: it keeps a small pool of card
widgets and only ever shows the ones in view, re-pointing them at different apps
as you scroll or change filters. CustomTkinter widgets are expensive to create
(~25 ms each), so this is what keeps filtering and scrolling instant regardless
of how many thousands of packages were scanned.
"""

from __future__ import annotations

import math
import os
import threading
from tkinter import Canvas, messagebox

import customtkinter as ctk

from app_detector import config_capture, restore as restore_mod
from app_detector.filtering import apply_filter, total_size
from app_detector.manifest import Manifest
from app_detector.models import Kind, ScanFilter, SizeTier, human_size
from app_detector.platform_detect import detect_platform
from app_detector.scanners import get_installer, get_scanner

platform_info = detect_platform()
_FAM = platform_info.family

# ── Teal / emerald dark palette ──────────────────────────────────────────────
BG = "#0e1116"            # window background (near-black)
SURFACE = "#171b22"       # cards, panels
SURFACE_HI = "#1f2630"    # hover / selected surface
BORDER = "#222a35"        # idle card border
BORDER_HOVER = "#33404f"  # hovered card border
TEXT = "#e6ebf2"          # primary text
MUTED = "#8b97a8"         # secondary text (on the near-black window bg)
CARD_META = "#b9c4d4"     # secondary text on a card — brighter for readability
ACCENT = "#14b8a6"        # teal — buttons, active tab
ACCENT_HOVER = "#0d9488"  # teal pressed/hover
ACCENT_SOFT = "#2dd4bf"   # brighter teal — size, icons
ACCENT_TEXT = "#03130f"   # dark text on a teal fill

CARD_H = 110              # fixed card height (px)
CARD_MIN_W = 310          # target card width → drives column count
ICON_PX = 40              # rendered app-icon size (px)
GAP = 14                  # gap between cards
NAME_MAX = 30             # max chars before the name is ellipsised


def _trunc(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# ── App-icon loading (real .desktop icons, cached) ───────────────────────────
# Resolving + decoding an icon touches disk and is comparatively slow, so every
# result (including "no icon") is cached by name. ``None`` means fall back to the
# letter badge — e.g. SVG-only icons, missing files, or Pillow not installed.

_icon_cache: dict[str, "object | None"] = {}


def _load_icon(icon_name: str):
    """Return a ``CTkImage`` for a freedesktop icon name, or ``None``."""
    if not icon_name:
        return None
    if icon_name in _icon_cache:
        return _icon_cache[icon_name]
    result = None
    try:
        from PIL import Image
        from app_detector.util.icons import find_icon
        path = find_icon(icon_name)
        if path:
            img = Image.open(path).convert("RGBA")
            result = ctk.CTkImage(light_image=img, dark_image=img,
                                  size=(ICON_PX, ICON_PX))
    except Exception:
        result = None
    _icon_cache[icon_name] = result
    return result


# ── Native file dialogs ──────────────────────────────────────────────────────
# On Linux we shell out to ``zenity`` (a separate process) instead of opening a
# Qt dialog. A Qt dialog spins its own event loop *inside* Tk's mainloop, and two
# GUI toolkits fighting over one thread deadlocks/segfaults — that was the
# "Load Snapshot crashes" bug. A subprocess sidesteps the conflict entirely.

def _have_zenity() -> bool:
    import shutil
    return _FAM == "linux" and shutil.which("zenity") is not None


def _zenity(*args: str) -> str | None:
    """Run a zenity file dialog; return the chosen path, or ``None`` on cancel.

    Only call this when :func:`_have_zenity` is true — a ``None`` here means the
    user cancelled, *not* that zenity is missing, so callers must not fall back
    to a second dialog on ``None``.
    """
    import subprocess
    try:
        res = subprocess.run(["zenity", "--file-selection", *args],
                             capture_output=True, text=True)
    except OSError:
        return None
    path = res.stdout.strip()
    return path if res.returncode == 0 and path else None


def _native_save(title: str) -> str | None:
    if _have_zenity():
        path = _zenity("--save", "--confirm-overwrite", f"--title={title}",
                       "--filename=manifest.json",
                       "--file-filter=JSON files (*.json) | *.json")
        if path and not path.endswith(".json"):
            path += ".json"
        return path
    from tkinter.filedialog import asksaveasfilename
    return asksaveasfilename(defaultextension=".json",
                             filetypes=[("JSON", "*.json")], title=title) or None


def _native_open(title: str) -> str | None:
    if _have_zenity():
        return _zenity(f"--title={title}",
                       "--file-filter=JSON files (*.json) | *.json")
    from tkinter.filedialog import askopenfilename
    return askopenfilename(filetypes=[("JSON", "*.json")], title=title) or None


# ── A single reusable app card ───────────────────────────────────────────────

class _Card(ctk.CTkFrame):
    """A pooled card widget. ``show()`` re-points it at a different app — no new
    widgets are created, which is what makes filtering/scrolling cheap."""

    def __init__(self, master, grid: "CardGrid"):
        super().__init__(master, fg_color=SURFACE, corner_radius=14,
                         border_width=2, border_color=BORDER)
        self._grid = grid
        self.idx = -1
        self._gen = -1
        self.selectable = False
        self.selected = False
        self.grid_columnconfigure(1, weight=1)

        self.badge = ctk.CTkLabel(self, text="", width=ICON_PX + 6,
                                  height=ICON_PX + 6, corner_radius=10,
                                  fg_color=ACCENT, text_color=ACCENT_TEXT,
                                  font=ctk.CTkFont(size=16, weight="bold"))
        self.badge.grid(row=0, column=0, rowspan=3, padx=(14, 12), pady=14, sticky="n")
        self.name = ctk.CTkLabel(self, text="", anchor="w", text_color=TEXT,
                                 font=ctk.CTkFont(size=15, weight="bold"))
        self.name.grid(row=0, column=1, sticky="w", pady=(14, 0), padx=(0, 10))
        self.size = ctk.CTkLabel(self, text="", anchor="w", text_color=ACCENT_SOFT,
                                 font=ctk.CTkFont(size=17, weight="bold"))
        self.size.grid(row=1, column=1, sticky="w", padx=(0, 10))
        self.meta = ctk.CTkLabel(self, text="", anchor="w", text_color=CARD_META,
                                 font=ctk.CTkFont(size=12))
        self.meta.grid(row=2, column=1, sticky="w", pady=(0, 14), padx=(0, 10))
        self.check = ctk.CTkLabel(self, text="", width=22, text_color=ACCENT_SOFT,
                                  font=ctk.CTkFont(size=17, weight="bold"))
        self.check.grid(row=0, column=2, padx=(0, 14), pady=(14, 0), sticky="ne")

        self._bind_tree(self)

    def _bind_tree(self, widget):
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
        widget.bind("<Button-1>", self._on_click)
        self._grid._bind_wheel(widget)
        for child in widget.winfo_children():
            self._bind_tree(child)

    def show(self, app, idx, selected, selectable):
        self.idx = idx
        self.selectable = selectable
        self.selected = selected
        icon = _load_icon(app.metadata.get("icon", "")) if app.metadata else None
        if icon is not None:
            # Real icon: transparent badge, no letter — let the artwork speak.
            self.badge.configure(image=icon, text="", fg_color="transparent")
        else:
            self.badge.configure(image=None, fg_color=ACCENT,
                                 text=(app.name or "?").strip()[:1].upper() or "?")
            # CTkLabel._update_image() is a no-op when image is None, so it never
            # clears the underlying tk image. Without this, a pooled card reused
            # from an app (real icon) to a tool (no icon) keeps the stale icon.
            self.badge._label.configure(image="")
        self.name.configure(text=_trunc(app.name, NAME_MAX))
        self.size.configure(text=app.size_human)
        self.meta.configure(text=f"{app.kind.value} · {app.source}")
        self._paint()

    def _paint(self):
        if self.selectable and self.selected:
            self.configure(border_color=ACCENT, fg_color=SURFACE_HI)
            self.check.configure(text="✓")
        else:
            self.configure(border_color=BORDER, fg_color=SURFACE)
            self.check.configure(text="")

    def _on_click(self, _e):
        if not self.selectable:
            return
        self.selected = not self.selected
        self._paint()
        self._grid._toggle(self.idx, self.selected)

    def _on_enter(self, _e):
        if not (self.selectable and self.selected):
            self.configure(border_color=BORDER_HOVER, fg_color=SURFACE_HI)

    def _on_leave(self, _e):
        if not (self.selectable and self.selected):
            self.configure(border_color=BORDER, fg_color=SURFACE)


# ── Virtualized grid of cards ────────────────────────────────────────────────

class CardGrid(ctk.CTkFrame):
    def __init__(self, master, on_toggle=None):
        super().__init__(master, fg_color="transparent")
        self.on_toggle = on_toggle
        self.items: list = []
        self.state: list[bool] = []
        self.selectable = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll = ctk.CTkScrollbar(self, command=self._yview)
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scroll.set)

        self._pool: list[_Card] = []
        self._cw = 1000
        self._ch = 600
        self.cols = 4
        self._gen = 0   # bumped whenever the dataset changes; invalidates cards
        self.canvas.configure(yscrollincrement=40)
        self._msg = self.canvas.create_text(
            20, 30, anchor="nw", fill=MUTED, text="", font=("", 14),
            width=600, state="hidden")

        self.canvas.bind("<Configure>", self._on_configure)
        self._bind_wheel(self.canvas)

    # — scrolling —
    def _yview(self, *args):
        self.canvas.yview(*args)
        self._layout()

    def _bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._on_wheel)      # win/mac
        widget.bind("<Button-4>", self._on_wheel)        # linux up
        widget.bind("<Button-5>", self._on_wheel)        # linux down

    def _on_wheel(self, event):
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")
        self._layout()
        return "break"

    def _on_configure(self, event):
        self._cw, self._ch = event.width, event.height
        cols = max(1, (self._cw - GAP) // CARD_MIN_W)
        self.cols = cols
        self.canvas.itemconfigure(self._msg, width=self._cw - 40)
        self._layout()

    # — data —
    def set_items(self, items, selectable=False, state=None, message=""):
        self.items = items or []
        self.selectable = selectable
        self.state = state if state is not None else []
        self._gen += 1   # force every pooled card to repaint with new data
        self.canvas.yview_moveto(0)
        if not self.items:
            self._hide_all()
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            self.canvas.itemconfigure(self._msg, text=message, state="normal")
            return
        self.canvas.itemconfigure(self._msg, state="hidden")
        self._layout()

    def refresh(self):
        """Repaint visible cards in place (e.g. after Select All)."""
        self._gen += 1
        self._layout()

    # — pooling / layout —
    def _ensure_pool(self, k):
        while len(self._pool) < k:
            card = _Card(self.canvas, self)
            card._cid = self.canvas.create_window(0, 0, window=card, anchor="nw",
                                                  state="hidden")
            self._pool.append(card)

    def _hide_all(self):
        for card in self._pool:
            self.canvas.itemconfigure(card._cid, state="hidden")

    def _layout(self):
        n = len(self.items)
        if n == 0:
            self._hide_all()
            return
        cols = max(1, self.cols)
        rows = math.ceil(n / cols)
        row_h = CARD_H + GAP
        total_h = GAP + rows * row_h
        self.canvas.configure(scrollregion=(0, 0, self._cw, total_h))
        card_w = (self._cw - GAP * (cols + 1)) / cols

        top_y = self.canvas.canvasy(0)
        first_row = max(0, int(top_y // row_h) - 1)
        visible_rows = int(self._ch // row_h) + 2
        self._ensure_pool((visible_rows + 1) * cols)
        pool_n = len(self._pool)

        start = first_row * cols
        end = min(n, (first_row + visible_rows + 1) * cols)
        # Stable mapping: item idx → pool slot ``idx % pool_n``. A contiguous
        # window no longer than the pool keeps residues unique, so during a
        # small scroll only the rows entering view are re-shown.
        used = set()
        for idx in range(start, end):
            slot = idx % pool_n
            used.add(slot)
            card = self._pool[slot]
            col = idx % cols
            row = idx // cols
            self.canvas.coords(card._cid, GAP + col * (card_w + GAP),
                               GAP + row * row_h)
            self.canvas.itemconfigure(card._cid, width=card_w, height=CARD_H,
                                      state="normal")
            if card._gen == self._gen and card.idx == idx:
                continue   # already showing the right app — skip the work
            sel = self.state[idx] if (self.selectable and idx < len(self.state)) \
                else False
            card.show(self.items[idx], idx, sel, self.selectable)
            card._gen = self._gen
        for j in range(pool_n):
            if j not in used:
                self.canvas.itemconfigure(self._pool[j]._cid, state="hidden")

    def _toggle(self, idx, selected):
        if 0 <= idx < len(self.state):
            self.state[idx] = selected
        if self.on_toggle:
            self.on_toggle(idx, selected)


# ── Live install console (terminal-style output window) ──────────────────────

class InstallConsole(ctk.CTkToplevel):
    """A terminal-style window that streams live output while apps install.

    All ``write``/``set_status``/``finish`` calls must happen on the GUI thread;
    the install worker marshals to it via ``root.after``. Closing the window is
    blocked until the run finishes so output isn't lost mid-install.
    """

    def __init__(self, master, total: int):
        super().__init__(master)
        self.title("Installing")
        self.configure(fg_color=BG)
        self.geometry("780x540")
        self.minsize(560, 360)
        self.transient(master)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(
            self, text=f"Preparing to install {total} app(s)…", anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=TEXT)
        self.status.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))

        self.console = ctk.CTkTextbox(
            self, fg_color="#0a0d11", text_color="#cfe9e3", wrap="none",
            border_width=1, border_color=BORDER, corner_radius=10,
            font=ctk.CTkFont(family="monospace", size=12))
        self.console.grid(row=1, column=0, sticky="nsew", padx=20)
        self.console.configure(state="disabled")

        self.close_btn = ctk.CTkButton(
            self, text="Close", height=40, width=150, corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"), fg_color=ACCENT,
            hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            state="disabled", command=self.destroy)
        self.close_btn.grid(row=2, column=0, pady=16)

        self.protocol("WM_DELETE_WINDOW", lambda: None)  # locked until finish()
        self.after(200, self._grab)

    def _grab(self):
        try:
            self.grab_set()
        except Exception:
            pass

    def set_status(self, text: str):
        self.status.configure(text=text)

    def write(self, text: str):
        self.console.configure(state="normal")
        self.console.insert("end", text)
        self.console.see("end")
        self.console.configure(state="disabled")

    def finish(self, ok: int, total: int):
        self.set_status(f"Done — installed {ok} of {total} app(s).")
        self.write(f"\nFinished: {ok} of {total} succeeded.\n")
        self.close_btn.configure(state="normal")
        self.protocol("WM_DELETE_WINDOW", self.destroy)


# ── Main window ──────────────────────────────────────────────────────────────

class AppDetectorGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")  # overridden per-widget with teal
        self.configure(fg_color=BG)
        self.title("App Detector")
        self.geometry("1120x760")
        self.minsize(940, 600)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.mode = "scan"
        self.all_apps = []
        self.view = []
        self.scan_state = []          # parallel to ``view`` — saved when checked
        # Apps the user has unchecked, tracked by identity so the selection
        # survives filtering/sorting (which reshuffles ``view`` indices).
        self.deselected: set[tuple[str, str]] = set()
        self.loaded_manifest = None
        self.restore_apps = []        # full list from the loaded manifest
        self.restore_view = []        # restore_apps filtered by the kind toggles
        self.restore_state = []       # parallel to restore_view
        # Deselected apps tracked by identity so the choice survives kind filtering.
        self.restore_deselected: set[tuple[str, str]] = set()
        self._refresh_job = None

        self._build_topbar()
        self._build_controls()
        self._build_gallery()
        self._build_footer()
        self._set_mode("scan")

    # ── Top bar ──────────────────────────────────────────────────────────

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        bar.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(bar, text="◆", font=ctk.CTkFont(size=20),
                     text_color=ACCENT).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(bar, text="App Detector",
                     font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT
                     ).grid(row=0, column=1)

        tabs = ctk.CTkFrame(bar, fg_color=SURFACE, corner_radius=10)
        tabs.grid(row=0, column=2)
        self.tab_btns = {}
        for i, (key, label) in enumerate([("scan", "Scan"), ("restore", "Restore")]):
            b = ctk.CTkButton(tabs, text=label, width=110, height=36, corner_radius=8,
                              font=ctk.CTkFont(size=14, weight="bold"),
                              fg_color="transparent", text_color=MUTED,
                              hover_color=SURFACE_HI,
                              command=lambda k=key: self._set_mode(k))
            b.grid(row=0, column=i, padx=4, pady=4)
            self.tab_btns[key] = b

        self.action_btn = ctk.CTkButton(
            bar, text="⟳  Rescan", width=150, height=40, corner_radius=10,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            command=self._primary_action)
        self.action_btn.grid(row=0, column=3, padx=(16, 0))

    # ── Controls (filter row, swaps per mode) ────────────────────────────

    def _build_controls(self):
        self.controls = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14)
        self.controls.grid(row=1, column=0, sticky="ew", padx=24, pady=(4, 8))

        # — Scan controls —
        self.scan_controls = ctk.CTkFrame(self.controls, fg_color="transparent")
        self.scan_controls.grid_columnconfigure(7, weight=1)

        ctk.CTkLabel(self.scan_controls, text="Size",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED
                     ).grid(row=0, column=0, padx=(16, 6), pady=14)
        self.tier_var = ctk.StringVar(value="All")
        ctk.CTkSegmentedButton(
            self.scan_controls, values=["All", "≥100 MB", "≥1 GB"],
            variable=self.tier_var, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER, text_color=TEXT,
            command=lambda _=None: self._schedule_refresh()
        ).grid(row=0, column=1, padx=(0, 18))

        ctk.CTkLabel(self.scan_controls, text="Kind",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED
                     ).grid(row=0, column=2, padx=(0, 6))
        self.kind_vars = {
            Kind.APP: ctk.BooleanVar(value=True),
            Kind.TOOL: ctk.BooleanVar(value=True),
        }
        for i, (k, label) in enumerate(
                [(Kind.APP, "Apps"), (Kind.TOOL, "Tools")]):
            ctk.CTkCheckBox(self.scan_controls, text=label, variable=self.kind_vars[k],
                            width=20, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                            text_color=TEXT, command=self._schedule_refresh
                            ).grid(row=0, column=3 + i, padx=8)

        self.scan_sel_all = ctk.CTkButton(
            self.scan_controls, text="Select All", width=104, height=34,
            corner_radius=8, fg_color="transparent", border_width=1,
            border_color=BORDER, text_color=TEXT, hover_color=SURFACE_HI,
            command=lambda: self._set_all(True))
        self.scan_sel_all.grid(row=0, column=5, padx=(8, 8))
        self.scan_desel_all = ctk.CTkButton(
            self.scan_controls, text="Deselect All", width=104, height=34,
            corner_radius=8, fg_color="transparent", border_width=1,
            border_color=BORDER, text_color=TEXT, hover_color=SURFACE_HI,
            command=lambda: self._set_all(False))
        self.scan_desel_all.grid(row=0, column=6, padx=(0, 8))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_refresh())
        ctk.CTkEntry(self.scan_controls, placeholder_text="Search…", width=200,
                     height=34, textvariable=self.search_var,
                     fg_color=BG, border_color=BORDER, text_color=TEXT
                     ).grid(row=0, column=7, sticky="e", padx=16)

        # — Restore controls —
        self.restore_controls = ctk.CTkFrame(self.controls, fg_color="transparent")
        self.restore_controls.grid_columnconfigure(5, weight=1)

        # Same Apps / Tools categories as the scan view, so a loaded snapshot can
        # be narrowed the same way before installing.
        ctk.CTkLabel(self.restore_controls, text="Kind",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=MUTED
                     ).grid(row=0, column=0, padx=(16, 6), pady=14)
        self.restore_kind_vars = {
            Kind.APP: ctk.BooleanVar(value=True),
            Kind.TOOL: ctk.BooleanVar(value=True),
        }
        self.restore_kind_boxes = []
        for i, (k, label) in enumerate([(Kind.APP, "Apps"), (Kind.TOOL, "Tools")]):
            cb = ctk.CTkCheckBox(
                self.restore_controls, text=label, variable=self.restore_kind_vars[k],
                width=20, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                text_color=TEXT, state="disabled", command=self._refresh_restore)
            cb.grid(row=0, column=1 + i, padx=8)
            self.restore_kind_boxes.append(cb)

        self.restore_info = ctk.CTkLabel(
            self.restore_controls, text="Load a snapshot to begin.", anchor="w",
            font=ctk.CTkFont(size=13), text_color=MUTED)
        self.restore_info.grid(row=0, column=5, sticky="w", padx=16, pady=14)
        self.sel_all = ctk.CTkButton(
            self.restore_controls, text="Select All", width=104, height=34,
            corner_radius=8, fg_color="transparent", border_width=1,
            border_color=BORDER, text_color=TEXT, hover_color=SURFACE_HI,
            state="disabled", command=lambda: self._set_all(True))
        self.sel_all.grid(row=0, column=6, padx=(0, 8), pady=10)
        self.desel_all = ctk.CTkButton(
            self.restore_controls, text="Deselect All", width=104, height=34,
            corner_radius=8, fg_color="transparent", border_width=1,
            border_color=BORDER, text_color=TEXT, hover_color=SURFACE_HI,
            state="disabled", command=lambda: self._set_all(False))
        self.desel_all.grid(row=0, column=7, padx=(0, 16), pady=10)

    # ── Gallery ──────────────────────────────────────────────────────────

    def _build_gallery(self):
        self.summary = ctk.CTkLabel(self, text="", anchor="w",
                                    font=ctk.CTkFont(size=13, weight="bold"),
                                    text_color=MUTED)
        self.summary.grid(row=1, column=0, sticky="se", padx=40)

        self.grid_view = CardGrid(self, on_toggle=self._on_card_toggle)
        self.grid_view.grid(row=2, column=0, sticky="nsew", padx=20, pady=(4, 6))

    # ── Footer (primary action per mode) ─────────────────────────────────

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=24, pady=(2, 18))
        footer.grid_columnconfigure(0, weight=1)
        self.save_btn = ctk.CTkButton(
            footer, text="Save Snapshot", height=46, width=200, corner_radius=12,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            text_color_disabled=ACCENT_TEXT,  # stay black on teal while disabled
            state="disabled", command=self._save_manifest)
        self.install_btn = ctk.CTkButton(
            footer, text="Install Selected", height=46, width=200, corner_radius=12,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT,
            text_color_disabled=ACCENT_TEXT,  # stay black on teal while disabled
            state="disabled", command=self._run_restore)
        self.save_btn.grid(row=0, column=1)
        self.install_btn.grid(row=0, column=1)

    # ── Mode switching ───────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self.mode = mode
        for key, b in self.tab_btns.items():
            active = key == mode
            b.configure(fg_color=ACCENT if active else "transparent",
                        text_color=ACCENT_TEXT if active else MUTED)
        if mode == "scan":
            self.restore_controls.pack_forget()
            self.scan_controls.pack(fill="x")
            self.install_btn.grid_remove()
            self.save_btn.grid()
            self.action_btn.configure(text="⟳  Rescan")
            self._show_scan()
        else:
            self.scan_controls.pack_forget()
            self.restore_controls.pack(fill="x")
            self.save_btn.grid_remove()
            self.install_btn.grid()
            self.action_btn.configure(text="Load Snapshot…")
            self._show_restore()

    def _primary_action(self):
        if self.mode == "scan":
            self._start_scan()
        else:
            self._load_manifest()

    # ── Scan flow ────────────────────────────────────────────────────────

    def _start_scan(self):
        self.action_btn.configure(state="disabled", text="Scanning…")
        self.summary.configure(text="Scanning…")
        self.grid_view.set_items([], message="Scanning your system…")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        apps = get_scanner().scan_all()
        self.after(0, self._scan_done, apps)

    def _scan_done(self, apps):
        self.all_apps = apps
        self.action_btn.configure(state="normal", text="⟳  Rescan")
        if not apps:
            self.summary.configure(text="")
            self.grid_view.set_items([], message="No packages found or scan failed.")
            return
        self.save_btn.configure(state="normal")
        self._refresh_view()

    def _current_filter(self) -> ScanFilter:
        tier = {"All": SizeTier.ALL, "≥100 MB": SizeTier.LARGE,
                "≥1 GB": SizeTier.HUGE}[self.tier_var.get()]
        kinds = {k for k, v in self.kind_vars.items() if v.get()}
        # No kind checked → show nothing (an empty kind set matches no app).
        # Always manual_only: the app only cares about what the user installed.
        return ScanFilter(min_size_bytes=tier.value, kinds=kinds,
                          manual_only=True)

    def _schedule_refresh(self):
        if self.mode != "scan":
            return
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(120, self._refresh_view)

    def _refresh_view(self):
        self._refresh_job = None
        if not self.all_apps:
            return
        view = apply_filter(self.all_apps, self._current_filter())
        query = self.search_var.get().strip().lower()
        if query:
            view = [a for a in view
                    if query in a.name.lower() or query in a.package_id.lower()]
        self.view = sorted(view, key=lambda a: a.size_bytes, reverse=True)
        # Rebuild the checkbox state from the identity-based deselected set so
        # the user's choices persist across filtering/sorting.
        self.scan_state = [self._key(a) not in self.deselected for a in self.view]
        self.summary.configure(
            text=f"{len(self.view)} of {len(self.all_apps)} scanned  ·  "
                 f"{human_size(total_size(self.view))}")
        self._show_scan()
        self._update_scan_count()

    @staticmethod
    def _key(app) -> tuple[str, str]:
        """Stable identity for an app, independent of its position in ``view``."""
        return (app.source, app.package_id)

    def _update_scan_count(self):
        n = sum(self.scan_state)
        self.save_btn.configure(
            text=f"Save Snapshot ({n})" if n else "Save Snapshot")

    def _show_scan(self):
        if not self.all_apps:
            self.grid_view.set_items(
                [], message="Click  ⟳ Rescan  to scan your computer for "
                            "installed apps.")
        elif not self.view:
            self.grid_view.set_items([], message="No apps match the current filters.")
        else:
            self.grid_view.set_items(self.view, selectable=True,
                                     state=self.scan_state)

    # ── Restore flow ─────────────────────────────────────────────────────

    def _load_manifest(self):
        path = _native_open("Open Snapshot")
        if not path:
            return
        try:
            self.loaded_manifest = Manifest.load(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load:\n{e}")
            return
        self.restore_apps = list(self.loaded_manifest.apps)
        self.restore_deselected = set()   # fresh snapshot → everything selected
        fam = self.loaded_manifest.source_os.get("family", "unknown").capitalize()
        self.restore_info.configure(
            text=f"{os.path.basename(path)}  ·  OS: {fam}  ·  "
                 f"{len(self.restore_apps)} apps")
        for b in (self.sel_all, self.desel_all, self.install_btn,
                  *self.restore_kind_boxes):
            b.configure(state="normal")
        self._refresh_restore()

    def _refresh_restore(self):
        """Rebuild the restore view from the Apps/Tools kind toggles."""
        kinds = {k for k, v in self.restore_kind_vars.items() if v.get()}
        self.restore_view = [a for a in self.restore_apps if a.kind in kinds]
        self.restore_state = [self._key(a) not in self.restore_deselected
                              for a in self.restore_view]
        self._show_restore()
        self._update_restore_count()

    def _show_restore(self):
        if not self.restore_apps:
            self.grid_view.set_items(
                [], message="Click  Load Snapshot…  to open a saved manifest, "
                            "then click the apps you want to reinstall.")
        elif not self.restore_view:
            self.grid_view.set_items(
                [], message="No apps match the current categories.")
        else:
            self.grid_view.set_items(self.restore_view, selectable=True,
                                     state=self.restore_state)

    def _set_all(self, value: bool):
        # Act on the currently-visible view only (matches what's on screen).
        view = self.view if self.mode == "scan" else self.restore_view
        deselected = self.deselected if self.mode == "scan" else self.restore_deselected
        state = self.scan_state if self.mode == "scan" else self.restore_state
        for a in view:
            deselected.discard(self._key(a)) if value else deselected.add(self._key(a))
        state[:] = [value] * len(view)
        self.grid_view.refresh()
        self._update_scan_count() if self.mode == "scan" else self._update_restore_count()

    def _on_card_toggle(self, idx, selected):
        view = self.view if self.mode == "scan" else self.restore_view
        deselected = self.deselected if self.mode == "scan" else self.restore_deselected
        if 0 <= idx < len(view):
            key = self._key(view[idx])
            deselected.discard(key) if selected else deselected.add(key)
        self._update_scan_count() if self.mode == "scan" else self._update_restore_count()

    def _update_restore_count(self):
        n = sum(self.restore_state)
        self.install_btn.configure(
            text=f"Install Selected ({n})" if n else "Install Selected")

    # ── Save / install actions ───────────────────────────────────────────

    def _save_manifest(self):
        selected = [a for a, on in zip(self.view, self.scan_state) if on]
        if not selected:
            messagebox.showwarning("Nothing selected",
                                   "Select at least one app to save.")
            return
        path = _native_save("Save Snapshot")
        if not path:
            return
        # Capture safe, fast app config (VS Code extensions, git) so the snapshot
        # restores settings too — same data as the CLI's `scan --with-config`.
        configs = config_capture.capture_all()
        manifest = Manifest.create(selected, platform_info,
                                   self._current_filter().to_dict(), configs)
        try:
            manifest.save(path)
            messagebox.showinfo("Saved",
                                f"Snapshot ({len(selected)} apps) saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def _run_restore(self):
        selected = [a for a, on in zip(self.restore_view, self.restore_state) if on]
        if not selected:
            messagebox.showwarning("Nothing selected", "Select at least one app.")
            return
        if not messagebox.askyesno(
                "Confirm Restore",
                f"Install {len(selected)} applications?\n\n"
                "You may be prompted for your password in the terminal."):
            return
        self.install_btn.configure(state="disabled", text="Installing…")
        console = InstallConsole(self, len(selected))
        threading.Thread(target=self._restore_worker, args=(selected, console),
                         daemon=True).start()

    def _restore_worker(self, selected, console):
        installer = get_installer()
        emit = lambda text: self.after(0, console.write, text)

        # Resolve each app to a manager *this* machine has (an apt snapshot can
        # install via dnf/brew/winget); apps with no installable manager are
        # listed and skipped rather than silently failing.
        resolvable, unresolved = restore_mod.plan(selected, platform_info)
        if unresolved:
            emit(f"\n⚠ {len(unresolved)} app(s) can't be installed on this OS "
                 f"— skipped:\n")
            for a in unresolved:
                emit(f"    · {a.name} ({a.source})\n")

        total = len(resolvable)
        ok = 0
        for i, (_original, resolved, confidence) in enumerate(resolvable, 1):
            resolved.target_version = "latest"
            self.after(0, console.set_status,
                       f"Installing {i} of {total}: {resolved.name}")
            note = "" if confidence == "exact" else f"  [via {resolved.source}]"
            emit(f"\n=== [{i}/{total}] {resolved.name} "
                 f"({resolved.package_id}){note} ===\n")
            installed = installer.install_streamed(resolved, emit)
            # Trust a real presence check when the platform can do one; otherwise
            # fall back to the install command's exit code.
            verified = installer.is_installed(resolved)
            if verified if verified is not None else installed:
                ok += 1
                emit(f"✓ {resolved.name} installed"
                     + (" & verified.\n" if verified else ".\n"))
            else:
                why = ("installed but not detected afterwards" if installed
                       else "install command failed")
                emit(f"✗ {resolved.name} failed ({why}).\n")

        # Replay captured app config (extensions, git, …) once apps are present.
        configs = self.loaded_manifest.configs if self.loaded_manifest else {}
        if configs:
            emit("\n— Restoring app configuration —\n")
            config_capture.restore_all(configs, on_line=emit)

        self.after(0, self._restore_done, ok, total, console)

    def _restore_done(self, ok, total, console):
        self.install_btn.configure(state="normal", text="Install Selected")
        console.finish(ok, total)
