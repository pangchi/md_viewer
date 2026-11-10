#!/usr/bin/env python3
"""
md_viewer.py - Two-pane Markdown -> HTML viewer.

Left pane: Markdown editor. Right pane: live HTML preview.
Requires: PySide6, markdown  (pygments optional, for code highlighting)
Missing packages are installed automatically on first run (use --no-install
to disable).
"""

import sys
import html
import subprocess
import importlib
import importlib.util
from pathlib import Path


# ---------------------------------------------------------------------------
# Auto-installer: runs before any third-party import.
# (import name, pip package, required?)
# ---------------------------------------------------------------------------
DEPENDENCIES = [
    ("PySide6", "PySide6", True),
    ("markdown", "markdown", True),
    ("pygments", "pygments", False),
]


def _missing():
    return [(mod, pkg, req) for mod, pkg, req in DEPENDENCIES
            if importlib.util.find_spec(mod) is None]


def _pip(args):
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *args]
    print("  $", " ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode == 0


def _ensure_pip():
    if importlib.util.find_spec("pip") is not None:
        return True
    print("pip not found, trying ensurepip…", flush=True)
    return subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"]).returncode == 0


def ensure_dependencies():
    missing = _missing()
    if not missing:
        return
    if "--no-install" in sys.argv:
        names = ", ".join(pkg for _, pkg, _ in missing)
        sys.exit(f"Missing packages: {names}\nInstall with: pip install {names}")

    names = [pkg for _, pkg, _ in missing]
    print(f"MD Viewer: installing missing packages: {', '.join(names)}", flush=True)

    if not _ensure_pip():
        sys.exit("pip is not available for this Python. Install pip, then re-run.")

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    attempts = [[]] if in_venv else [[], ["--user"]]
    for extra in attempts:
        if _pip([*extra, *names]):
            break
    else:
        # Fall back to installing required packages one by one, so an optional
        # package failing doesn't block the app.
        for _, pkg, req in missing:
            ok = any(_pip([*extra, pkg]) for extra in attempts)
            if not ok and req:
                sys.exit(
                    f"\nCould not install '{pkg}'.\n"
                    "If your system Python is 'externally managed', create a virtual env:\n"
                    "  python3 -m venv .venv\n"
                    "  .venv/bin/python md_viewer.py      (Windows: .venv\\Scripts\\python)\n"
                )

    # A fresh --user install dir may not have been on sys.path at startup.
    import site
    user_site = site.getusersitepackages()
    if user_site not in sys.path and Path(user_site).is_dir():
        sys.path.append(user_site)
    importlib.invalidate_caches()
    still = [pkg for _, pkg, req in _missing() if req]
    if still:
        sys.exit(f"Install finished but these still can't be imported: {', '.join(still)}. "
                 "Try restarting the program.")
    print("Dependencies installed.\n", flush=True)


ensure_dependencies()

import markdown  # noqa: E402
from PySide6.QtCore import Qt, QTimer, QUrl, QFileSystemWatcher, QEvent, QObject
from PySide6.QtGui import QAction, QKeySequence, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QPlainTextEdit, QFileDialog,
    QMessageBox, QLabel, QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAVE_WEBENGINE = True
except ImportError:  # fall back to the simpler rich-text browser
    from PySide6.QtWidgets import QTextBrowser
    HAVE_WEBENGINE = False

try:
    import pygments  # noqa: F401
    from pygments.formatters import HtmlFormatter
    HAVE_PYGMENTS = True
except ImportError:
    HAVE_PYGMENTS = False

APP_NAME = "MD Viewer"
RENDER_DELAY_MS = 250

EXTENSIONS = ["extra", "sane_lists", "toc", "nl2br"]
EXT_CONFIG = {}
if HAVE_PYGMENTS:
    EXTENSIONS.append("codehilite")
    EXT_CONFIG["codehilite"] = {"guess_lang": False, "css_class": "codehilite"}

LIGHT_CSS = """
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 16px 24px;
       color: #24292f; background: #ffffff; }
h1, h2 { border-bottom: 1px solid #d0d7de; padding-bottom: .3em; }
code { background: #f0f2f4; padding: .15em .35em; border-radius: 4px;
       font-family: Consolas, "Courier New", monospace; font-size: 90%; }
pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; }
pre code { background: none; padding: 0; }
blockquote { color: #57606a; border-left: 4px solid #d0d7de; margin: 0; padding: 0 1em; }
table { border-collapse: collapse; }
th, td { border: 1px solid #d0d7de; padding: 6px 12px; }
th { background: #f6f8fa; }
img { max-width: 100%; }
a { color: #0969da; }
hr { border: 0; border-top: 1px solid #d0d7de; }
"""

DARK_CSS = """
body { color: #e6edf3; background: #0d1117; }
h1, h2 { border-bottom-color: #30363d; }
code { background: #262c36; }
pre { background: #161b22; }
blockquote { color: #8d96a0; border-left-color: #30363d; }
th, td { border-color: #30363d; }
th { background: #161b22; }
a { color: #4493f8; }
hr { border-top-color: #30363d; }
"""


def build_page(body: str, title: str, dark: bool) -> str:
    css = LIGHT_CSS + (DARK_CSS if dark else "")
    if HAVE_PYGMENTS:
        style = "monokai" if dark else "default"
        css += HtmlFormatter(style=style).get_style_defs(".codehilite")
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{css}</style></head>"
        f"<body>\n{body}\n</body></html>"
    )


def dropped_files(mime) -> list[Path]:
    """Local, existing files in a drag's mime data (empty for text drags)."""
    if mime is None or not mime.hasUrls():
        return []
    out = []
    for u in mime.urls():
        if u.isLocalFile():
            p = Path(u.toLocalFile())
            if p.is_file():
                out.append(p)
    return out


class FileDropFilter(QObject):
    """Intercepts file drags on the panes so they open the file instead of
    being pasted as text (editor) or navigated to (web view). Plain-text
    drags pass through untouched."""

    DRAG_EVENTS = (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop)

    def __init__(self, on_files, parent):
        super().__init__(parent)
        self.on_files = on_files
        self.recursive = set()
        self.watched = []
        self.active = True
        QApplication.instance().aboutToQuit.connect(self.detach)

    def watch(self, widget, recursive=False):
        widget.setAcceptDrops(True)
        widget.installEventFilter(self)
        self.watched.append(widget)
        if recursive:
            self.recursive.add(widget)
            for child in widget.findChildren(QWidget):
                self.watch(child)

    def detach(self):
        """Remove filters so no events reach Python during shutdown."""
        if not self.active:
            return
        self.active = False
        for w in self.watched:
            try:
                w.removeEventFilter(self)
            except RuntimeError:  # widget already deleted
                pass
        self.watched.clear()
        self.recursive.clear()

    def eventFilter(self, obj, e):
        if not self.active:
            return False
        try:
            return self._filter(obj, e)
        except Exception:
            return False

    def _filter(self, obj, e):
        t = e.type()
        if t == QEvent.ChildAdded and obj in self.recursive:
            child = e.child()
            if isinstance(child, QWidget):   # e.g. WebEngine's render widget
                self.watch(child)
        elif t in self.DRAG_EVENTS:
            files = dropped_files(e.mimeData())
            if files:
                e.acceptProposedAction()
                if t == QEvent.Drop:
                    # defer so the drag finishes before any dialog appears
                    QTimer.singleShot(0, lambda: self.on_files(files))
                return True
        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.path: Path | None = None
        self.dark = False
        self.show_source = False
        self.last_html = ""
        self._reloading = False

        self.md = markdown.Markdown(extensions=EXTENSIONS, extension_configs=EXT_CONFIG)

        # --- panes ---
        self.editor = QPlainTextEdit()
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setPointSize(11)
        self.editor.setFont(mono)
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.editor.setPlaceholderText("Type Markdown here, or open / drop a .md file…")

        if HAVE_WEBENGINE:
            self.preview = QWebEngineView()
        else:
            self.preview = QTextBrowser()
            self.preview.setOpenExternalLinks(True)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(self.preview)
        self.splitter.setSizes([600, 600])
        self.setCentralWidget(self.splitter)

        self.status = QLabel()
        self.statusBar().addPermanentWidget(self.status)

        # --- debounce render ---
        self.timer = QTimer(self, singleShot=True, interval=RENDER_DELAY_MS)
        self.timer.timeout.connect(self.render)
        self.editor.textChanged.connect(self.timer.start)
        self.editor.textChanged.connect(self.update_title)
        self.editor.verticalScrollBar().valueChanged.connect(self.sync_scroll)

        # --- watch file on disk for external changes ---
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self.on_file_changed)

        # Drops land on the child widgets (editor viewport / web view), which
        # would otherwise insert the path as text or navigate away. Catch file
        # drops for the whole window at the application level instead.
        self.setAcceptDrops(True)
        self.drop_filter = FileDropFilter(self.open_files, self)
        self.drop_filter.watch(self.editor.viewport())
        self.drop_filter.watch(self.editor)
        self.drop_filter.watch(self.preview, recursive=True)
        self.build_menus()
        self.resize(1300, 820)
        self.update_title()
        self.render()

    # ---------- menus ----------
    def build_menus(self):
        def act(menu, text, slot, shortcut=None, checkable=False):
            a = QAction(text, self, checkable=checkable)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        f = self.menuBar().addMenu("&File")
        act(f, "&New", self.new_file, QKeySequence.New)
        act(f, "&Open…", self.open_dialog, QKeySequence.Open)
        act(f, "&Reload", self.reload_file, "F5")
        f.addSeparator()
        act(f, "&Save", self.save, QKeySequence.Save)
        act(f, "Save &As…", self.save_as, QKeySequence.SaveAs)
        act(f, "&Export HTML…", self.export_html, "Ctrl+E")
        f.addSeparator()
        act(f, "&Quit", self.close, QKeySequence.Quit)

        v = self.menuBar().addMenu("&View")
        act(v, "Show HTML &Source", self.toggle_source, "Ctrl+U", checkable=True)
        act(v, "&Dark Preview", self.toggle_dark, "Ctrl+D", checkable=True)
        act(v, "Toggle &Editor Pane", self.toggle_editor, "Ctrl+1")
        act(v, "Toggle &Preview Pane", self.toggle_preview, "Ctrl+2")
        v.addSeparator()
        act(v, "Zoom &In", lambda: self.zoom(1), QKeySequence.ZoomIn)
        act(v, "Zoom &Out", lambda: self.zoom(-1), QKeySequence.ZoomOut)

    # ---------- rendering ----------
    def render(self):
        self.md.reset()
        body = self.md.convert(self.editor.toPlainText())
        title = self.path.name if self.path else "Untitled"
        self.last_html = build_page(body, title, self.dark)
        base = QUrl.fromLocalFile(str(self.path.parent) + "/") if self.path else QUrl()

        if self.show_source:
            shown = f"<pre style='white-space:pre-wrap'>{html.escape(self.last_html)}</pre>"
        else:
            shown = self.last_html

        if HAVE_WEBENGINE:
            # keep the preview's scroll position across re-renders
            page = self.preview.page()
            page.runJavaScript("window.scrollY", lambda y: self._set_html(shown, base, y))
        else:
            sb = self.preview.verticalScrollBar()
            pos = sb.value()
            if self.path:
                self.preview.setSearchPaths([str(self.path.parent)])
            self.preview.setHtml(shown)
            sb.setValue(pos)

        words = len(self.editor.toPlainText().split())
        self.status.setText(f"{words} words")

    def _set_html(self, shown, base, y):
        y = y or 0
        self.preview.setHtml(shown, base)
        self.preview.loadFinished.connect(
            lambda _ok, y=y: self.preview.page().runJavaScript(f"window.scrollTo(0,{y});"),
            Qt.SingleShotConnection,
        )

    def sync_scroll(self):
        sb = self.editor.verticalScrollBar()
        ratio = sb.value() / sb.maximum() if sb.maximum() else 0.0
        if HAVE_WEBENGINE:
            self.preview.page().runJavaScript(
                "window.scrollTo(0, (document.documentElement.scrollHeight"
                f" - window.innerHeight) * {ratio});"
            )
        else:
            psb = self.preview.verticalScrollBar()
            psb.setValue(int(psb.maximum() * ratio))

    # ---------- view toggles ----------
    def toggle_source(self, checked):
        self.show_source = checked
        self.render()

    def toggle_dark(self, checked):
        self.dark = checked
        self.render()

    def toggle_editor(self):
        self.editor.setVisible(not self.editor.isVisible() or not self.preview.isVisible())

    def toggle_preview(self):
        self.preview.setVisible(not self.preview.isVisible() or not self.editor.isVisible())

    def zoom(self, step):
        if HAVE_WEBENGINE:
            self.preview.setZoomFactor(max(0.3, self.preview.zoomFactor() + 0.1 * step))
        else:
            self.preview.zoomIn(step)
        self.editor.zoomIn(step)

    # ---------- file handling ----------
    def update_title(self):
        name = str(self.path) if self.path else "Untitled"
        mod = "*" if self.editor.document().isModified() else ""
        self.setWindowTitle(f"{mod}{name} — {APP_NAME}")

    def maybe_save(self) -> bool:
        if not self.editor.document().isModified():
            return True
        r = QMessageBox.question(
            self, APP_NAME, "Save changes to the current document?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def set_path(self, path: Path | None):
        if self.watcher.files():
            self.watcher.removePaths(self.watcher.files())
        self.path = path
        if path:
            self.watcher.addPath(str(path))

    def new_file(self):
        if self.maybe_save():
            self.set_path(None)
            self.editor.setPlainText("")
            self.editor.document().setModified(False)
            self.update_title()

    def open_dialog(self):
        if not self.maybe_save():
            return
        fn, _ = QFileDialog.getOpenFileName(
            self, "Open Markdown", str(self.path.parent) if self.path else "",
            "Markdown (*.md *.markdown *.mdown *.txt);;All files (*)",
        )
        if fn:
            self.load(Path(fn))

    def load(self, path: Path):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not open {path}:\n{e}")
            return
        self.set_path(path.resolve())
        sb = self.editor.verticalScrollBar()
        pos = sb.value() if self._reloading else 0
        self.editor.setPlainText(text)
        sb.setValue(pos)
        self.editor.document().setModified(False)
        self.update_title()
        self.render()

    def reload_file(self):
        if self.path and self.maybe_save():
            self._reloading = True
            self.load(self.path)
            self._reloading = False

    def on_file_changed(self, _p):
        if not self.path:
            return
        # editors often replace the file, which drops it from the watcher
        if self.path.exists() and str(self.path) not in self.watcher.files():
            self.watcher.addPath(str(self.path))
        if not self.editor.document().isModified() and self.path.exists():
            self._reloading = True
            self.load(self.path)
            self._reloading = False
            self.statusBar().showMessage("Reloaded (changed on disk)", 3000)
        else:
            self.statusBar().showMessage("File changed on disk — F5 to reload", 5000)

    def save(self) -> bool:
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self) -> bool:
        fn, _ = QFileDialog.getSaveFileName(
            self, "Save Markdown", str(self.path) if self.path else "untitled.md",
            "Markdown (*.md);;All files (*)",
        )
        if not fn:
            return False
        return self._write(Path(fn))

    def _write(self, path: Path) -> bool:
        self.watcher.removePaths(self.watcher.files())  # don't react to our own save
        try:
            path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not save {path}:\n{e}")
            return False
        self.set_path(path.resolve())
        self.editor.document().setModified(False)
        self.update_title()
        self.render()
        self.statusBar().showMessage(f"Saved {path}", 3000)
        return True

    def export_html(self):
        default = str(self.path.with_suffix(".html")) if self.path else "untitled.html"
        fn, _ = QFileDialog.getSaveFileName(self, "Export HTML", default, "HTML (*.html *.htm)")
        if not fn:
            return
        try:
            Path(fn).write_text(self.last_html, encoding="utf-8")
            self.statusBar().showMessage(f"Exported {fn}", 3000)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not export:\n{e}")

    # ---------- drag & drop / close ----------
    # Drops on the menu/status bar reach the window itself.
    def dragEnterEvent(self, e):
        if dropped_files(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = dropped_files(e.mimeData())
        if files:
            e.acceptProposedAction()
            QTimer.singleShot(0, lambda: self.open_files(files))

    def is_blank(self) -> bool:
        return self.path is None and not self.editor.document().isModified() \
            and not self.editor.toPlainText()

    def open_files(self, paths):
        """First file opens here (or a blank window), the rest in new windows."""
        if not paths:
            return
        first, rest = paths[0], paths[1:]
        if self.is_blank() or self.maybe_save():
            self.load(first)
        else:
            rest = paths
        for p in rest:
            open_window(p)

    def closeEvent(self, e):
        if self.maybe_save():
            self.drop_filter.detach()
            if self in WINDOWS:
                WINDOWS.remove(self)
            e.accept()
        else:
            e.ignore()


WINDOWS: list[MainWindow] = []


def open_window(path: Path | None = None) -> MainWindow:
    w = MainWindow()
    WINDOWS.append(w)
    if path:
        w.load(path)
    w.show()
    return w


def main():
    files = [Path(a) for a in sys.argv[1:] if not a.startswith("--")]
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    if not files:
        open_window()
    for f in files:              # each CLI file gets its own window
        open_window(f)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
