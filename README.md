# MD Viewer

A two-pane Markdown → HTML viewer written in Python (PySide6).
Edit Markdown on the left; the rendered HTML preview updates live on the right.

## Features

- Live preview (debounced ~250 ms) with preserved scroll position
- Editor → preview scroll sync
- Open, save, save as, and **export to standalone HTML** (CSS embedded)
- **Drag and drop** files anywhere on the window — editor, preview, or bars
- Open files from the command line, one window per file
- **Auto-installs** missing Python packages on first run
- Auto-reloads when the file changes on disk (if you have no unsaved edits)
- Relative image paths resolve against the Markdown file's folder
- GitHub-ish styling, optional dark preview
- Toggle raw HTML source view
- Code syntax highlighting when `pygments` is installed
- Markdown extensions: `extra` (tables, fenced code, footnotes, attr lists, abbreviations, definition lists), `toc`, `sane_lists`, `nl2br`
- Falls back to `QTextBrowser` if Qt WebEngine isn't available (simpler rendering)

## Install

Just run it. On first launch the script checks for `PySide6`, `markdown` and
`pygments` and installs any that are missing with the same Python that's
running it:

```bash
python md_viewer.py
```

How the auto-installer behaves:

- Inside a virtual env it runs `pip install <missing>`.
- Outside a venv it tries a normal install, then `pip install --user`.
- If pip itself is missing it tries `python -m ensurepip` first.
- `pygments` is optional: if it fails to install, the app still starts (no code highlighting).
- If your system Python is "externally managed" (Debian/Ubuntu, Homebrew) and both attempts fail, it stops and tells you to make a venv:

  ```bash
  python3 -m venv .venv
  .venv/bin/python md_viewer.py          # Windows: .venv\Scripts\python md_viewer.py
  ```

PySide6 is a large download (a few hundred MB including WebEngine), so the first run takes a while.

To skip auto-install and just report what's missing:

```bash
python md_viewer.py --no-install
```

Manual install, if you prefer:

```bash
pip install PySide6 markdown pygments
```

## Run

```bash
python md_viewer.py                   # empty editor
python md_viewer.py notes.md          # open a file
python md_viewer.py a.md b.md         # each file in its own window
```

On Windows you can also drag a `.md` file onto `md_viewer.py` in Explorer
(if `.py` files are associated with Python) — it opens just like a CLI argument.

## Drag and drop

- Drop a file onto the **editor**, the **preview**, or the menu/status bar to open it.
- Drop **several files** at once: the first opens in the current window, the rest each open in a new window.
- If the current document has unsaved changes you'll be asked to save first; if you cancel, the dropped files open in new windows instead.
- Dragging **plain text** (not a file) into the editor still inserts the text as normal.

## Shortcuts

| Action                 | Shortcut          |
|------------------------|-------------------|
| New / Open / Save      | Ctrl+N / Ctrl+O / Ctrl+S |
| Save As                | Ctrl+Shift+S      |
| Reload from disk       | F5                |
| Export HTML            | Ctrl+E            |
| Show HTML source       | Ctrl+U            |
| Dark preview           | Ctrl+D            |
| Toggle editor pane     | Ctrl+1            |
| Toggle preview pane    | Ctrl+2            |
| Zoom in / out          | Ctrl+= / Ctrl+-   |

## Notes

- Line breaks: `nl2br` is enabled, so a single newline becomes `<br>`. Remove it from `EXTENSIONS` in `md_viewer.py` for strict Markdown behaviour.
- Render delay and CSS are constants at the top of `md_viewer.py` (`RENDER_DELAY_MS`, `LIGHT_CSS`, `DARK_CSS`).
- Dependencies checked by the installer are listed in `DEPENDENCIES` near the top of `md_viewer.py`.
