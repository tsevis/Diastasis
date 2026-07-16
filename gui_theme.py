"""
Theme handling for the Diastasis GUI: platform ttk theme selection and
light/dark appearance toggling. Kept separate from gui.py for cohesion.
"""
import platform
import tkinter as tk
from tkinter import ttk
from typing import Dict


def setup_theme(style: ttk.Style) -> None:
    """Pick the most native ttk theme for the current platform."""
    system = platform.system().lower()
    if system == "darwin":
        style.theme_use("aqua")
    elif system == "windows":
        try:
            style.theme_use("vista")
        except tk.TclError:
            style.theme_use("default")
    else:
        try:
            style.theme_use("clam")
        except tk.TclError:
            style.theme_use("default")


def theme_colors(mode: str) -> Dict[str, str]:
    dark = mode == "dark"
    return {
        "bg": "#1e1e1e" if dark else "#f5f5f5",
        "fg": "#f2f2f2" if dark else "#1a1a1a",
        "surface": "#2a2a2a" if dark else "#ffffff",
        "active": "#3a3a3a" if dark else "#e8e8e8",
        "canvas": "#808080" if dark else "white",
        "text_bg": "#2a2a2a" if dark else "#ffffff",
        "text_fg": "#f2f2f2" if dark else "#1a1a1a",
    }


def apply_non_macos_theme(app) -> None:
    """Restyle all widgets for the current light/dark mode (non-macOS)."""
    if platform.system() == "Darwin":
        return

    colors = theme_colors(app._theme_mode)

    app.root.configure(bg=colors["bg"])
    app.style.configure(".", background=colors["bg"], foreground=colors["fg"])
    app.style.configure("TFrame", background=colors["bg"])
    app.style.configure("TLabel", background=colors["bg"], foreground=colors["fg"])
    app.style.configure("TLabelframe", background=colors["bg"], foreground=colors["fg"])
    app.style.configure("TLabelframe.Label", background=colors["bg"], foreground=colors["fg"])
    app.style.configure("TCheckbutton", background=colors["bg"], foreground=colors["fg"])
    app.style.configure("TButton", background=colors["surface"], foreground=colors["fg"])
    app.style.map("TButton", background=[("active", colors["active"])])
    app.style.configure("TNotebook", background=colors["bg"], borderwidth=0)
    app.style.configure("TNotebook.Tab", background=colors["surface"], foreground=colors["fg"])
    app.style.map(
        "TNotebook.Tab",
        background=[("selected", colors["active"])],
        foreground=[("selected", colors["fg"])],
    )

    app.preview_canvas.configure(bg=colors["canvas"])
    app.results_text.configure(
        bg=colors["text_bg"], fg=colors["text_fg"], insertbackground=colors["text_fg"]
    )


def toggle_appearance(app) -> None:
    """Flip light/dark mode, using native macOS appearance when available."""
    if platform.system() == "Darwin":
        try:
            if app._appearance in ("auto", "aqua"):
                app.root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", ".", "darkaqua")
                app._appearance = "darkaqua"
                app._theme_mode = "dark"
            else:
                app.root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", ".", "aqua")
                app._appearance = "aqua"
                app._theme_mode = "light"
        except tk.TclError:
            app._theme_mode = "dark" if app._theme_mode == "light" else "light"
    else:
        app._theme_mode = "dark" if app._theme_mode == "light" else "light"

    app.appearance_btn.config(text="Light Mode" if app._theme_mode == "dark" else "Dark Mode")
    apply_non_macos_theme(app)
    # On macOS, ttk theme colors are mostly native-managed, so explicitly set
    # the preview canvas background to reflect dark/light mode.
    if platform.system() == "Darwin":
        app.preview_canvas.configure(bg=theme_colors(app._theme_mode)["canvas"])
