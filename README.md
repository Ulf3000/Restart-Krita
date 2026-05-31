# 🔄 Krita Restart & Session Plugin

A restarting script for Krita with **Session Reload** (not the built-in one) — including new unsaved documents. Unsaved and modified documents get saved to temp files, and all open documents are reloaded after restart.

Behaviour is similar to when Clip Studio or Photoshop crash — they also reload all pictures including unsaved documents. But here you can **enforce it** whenever you need: if Krita lost pen pressure, starts lagging, you need a full PC reboot, or you just aren't a friend of sleeping PCs but still want to pick up where you left off next day after booting up. 🖊️

**Two options:**
1. 🔁 **Restart directly** — if Krita lost pen pressure or begins lagging or has another problem 
2. 💾 **Save the session and quit** — for picking up later

---

> Much thanks to **Grum999** https://github.com/grum999 for helping and showing the basics of Krita Python coding. 🙏

---

A Krita Python plugin that **autosaves your session** and lets you restart or quit cleanly — with full document restore on next launch.

---

## ✨ Features

- 💾 **Autosave** — saves all open documents to temp files every minute
- 🔁 **Save Session and Restart** — flushes all docs and relaunches Krita
- 🚪 **Save Session and Quit** — flushes all docs and exits cleanly
- 🖼️ **Restore dialog** — on next launch, shows thumbnails of all saved documents and lets you restore or discard the session
- 🟡 **Modified indicator** — documents that had unsaved changes are marked in the restore dialog

<img width="470" height="658" alt="image" src="https://github.com/user-attachments/assets/d64c7f2c-2044-4c67-922b-e86f81662056" />


---

## 📦 Installation

1. Copy `restart.py` and `restart.desktop` into your Krita pykrita folder:
   - **Windows:** `%APPDATA%\krita\pykrita\`
   - **Linux:** `~/.local/share/krita/pykrita/`
2. Restart Krita
3. Go to **Settings → Configure Krita → Python Plugin Manager** and enable **Restart**
4. Restart Krita again

---

## 🖱️ Usage

Two actions are added to the **File** menu:

| Action | What it does |
|---|---|
| **Save Session and Restart** | Saves all docs to temp files, relaunches Krita |
| **Save Session and Quit** | Saves all docs to temp files, exits Krita |

On next launch, if a saved session is found, a dialog appears:

- Click **Restore** to reopen all documents
- Click **Discard** to delete the session and start fresh

---

## ⚙️ Configuration

At the top of `restart.py`:

```python
AUTOSAVE_INTERVAL_MS = 1 * 60 * 1000  # autosave every 60 seconds
```

Adjust to taste — e.g. `2 * 60 * 1000` for every 2 minutes.

---

## 📁 Session Storage

Temp files and session data are stored in:

```
<krita resources folder>/restart_session/
```

This folder is cleaned up automatically as documents are closed or the session is discarded.

---

## ⚠️ Notes

- Temp files are saved as `.kra` via `exportImage` — original files are **not modified**
- If Krita crashes without using the menu actions, the last autosave tick (up to 1 minute ago) is restored
- Unsaved/new documents are saved to temp files and restored, but their original filename won't be set since they never had one
