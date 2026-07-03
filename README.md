# Discord Auto-Compress

**Paste any video, image or audio into Discord — it is automatically shrunk under the upload limit before it sends.** No manual re-encoding, no "file too large" errors.

The app lives quietly in the system tray. When you press **Ctrl+V** in Discord and the clipboard file is over the limit, it pops a small overlay, compresses the file with a two-pass x264 encode, and pastes the smaller version back for you.

![python](https://img.shields.io/badge/python-3.8%2B-blue)
![platform](https://img.shields.io/badge/platform-Windows-0a84ff)
![license](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Auto-compress on paste** — catches Ctrl+V in Discord, compresses, re-pastes. Guaranteed to fit the limit.
- **Video, images and audio** — x264 for video, WebP for images, MP3 for audio.
- **Split long videos** into parts that each fit the limit, or "compress & split" for fewer files.
- **Built-in editor** — trim, cut, reorder and remove clips on a CapCut-style timeline with a live **audio waveform that follows your zoom, cuts and moves**. Preview with sound; export to MP4 or GIF.
- **Shrink-more** offer for videos that already fit but could be smaller.
- **Themes & languages** — Discord / DokiDoki / Aero themes, UK / RU / EN.
- **Auto-updates** — pulls the latest code from GitHub on every launch.

## Install (no Python needed)

1. Download the release `DiscordAutoCompress.exe` and run it — a **graphical installer** opens.
2. Pick a folder (all program files are installed there, fully visible — no hidden stuff), choose desktop shortcut / autostart, click **Install**.
3. Uninstall anytime from **Windows Settings → Apps** ("Discord Auto-Compress"), the Start-menu **Uninstall** shortcut, or `DiscordAutoCompress.exe --uninstall`.
4. Update anytime with the **Check for updates** button in Settings (code auto-syncs from GitHub on every launch).

> Alternative for Python users: `setup.zip` + `scripts/Install.bat` (installs Python + ffmpeg via winget).

## Build it yourself

Requires Python 3 and ffmpeg (`winget install Gyan.FFmpeg`). Run the app directly with `python discord_overlay.py`, or build a single-file executable with PyInstaller: `pyinstaller --onefile --noconsole launcher.py`.

---

## Support this project ❤

Discord Auto-Compress is **free and open-source (MIT)** and always will be. If it saves you time, a small tip helps keep it going:

- ❤ **Donate** — use the **Sponsor** button at the top of this repo, the button below, or the **Support** button inside the app (Settings → About). It's a free, no-strings donation — nothing is locked behind it.

<!-- DONATE:START -->
[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/latratrol)
<!-- DONATE:END -->

Every bit of support is genuinely appreciated and goes straight into new features.

## License

[MIT](LICENSE) — free to use, modify and share.

---

*This repo also bundles a separate webhook tool (`discord_toolbox.py`) — see its header for usage.*
