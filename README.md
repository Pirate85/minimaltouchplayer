# MinimalTouchPlayer (MTP)

A minimalist, **square** desktop music player designed for small touch monitors (10", 1920×1280). Large PNG-icon buttons, dark theme, no album art — built to fit into tight desktop corners without wasting space. Zero clutter: just press play.

## Screenshots

| Main View | Folder Picker | Track Dropdown |
|-----------|---------------|----------------|
| ![Main](images/MinimalTouchPlayer_v1_2_Main.png) | ![Folder Picker](images/MinimalTouchPlayer_v1_2_Folderpicker.png) | ![Track Dropdown](images/MinimalTouchPlayer_v1_2_Track%20Topdown.png) |

> v1.2.1 ships with transparent, high-contrast PNG icons (512×400 RGBA) for effortless touch operation on any theme.

## Features

- 🎵 **Multi-format playback** — MP3, FLAC, OGG, Opus, M4A/AAC, WAV, WMA, AIFF, APE, WebM
- 📂 **Folder picker with track count** — browse and select a music folder; shows `(N)` tracks per subfolder (recursive scan, capped at 500)
- 🔊 **Live volume control** — real-time adjustment via slider or keyboard
- ⏯️ **Seamless pause/resume** — no restart, no audio gap
- 🔁 **Auto-next track** — automatically continues to the next song (respects shuffle & repeat)
- 🔀 **Shuffle mode** — toggle random playback order (key `s`), persisted across sessions
- 🔂 **Repeat modes** — Off → All → One cycle (key `r`): loop playlist or single track
- 📋 **Track dropdown** — tap the title bar to open a scrollable list of all tracks; select any song to jump directly
- 🔢 **Natural sort** — filenames with numbers sort correctly (Track 2 < Track 3 < … < Track 10)
- 💾 **Position resume** — remembers your last track and position across sessions
- 🌐 **Bilingual UI** — automatically switches between English and German based on system locale
- 🔍 **Zoom support** — `Ctrl +` / `Ctrl −` to scale, `Ctrl 0` to reset

## Installation

### System Dependencies

| Package | Debian / Ubuntu | Fedora / RHEL | Notes |
|---------|----------------|---------------|-------|
| Python 3.10+ | preinstalled | preinstalled | Runtime |
| NumPy | `sudo apt install python3-numpy` | `sudo dnf install python3-numpy` | Audio processing |
| Pillow (PIL) | `sudo apt install python3-pil` | `sudo dnf install python3-pillow` | Image handling |
| FFmpeg | `sudo apt install ffmpeg` | `sudo dnf install ffmpeg` | Audio decoding |
| ALSA / PipeWire | `sudo apt install alsa-utils` | preinstalled (PipeWire) | System audio output |

> ✅ **CustomTkinter is bundled** in both the `.deb` and `.rpm` packages — no `pip install` needed!

### From .deb package (Debian / Ubuntu)

```bash
# Prerequisites (one-time setup)
sudo apt install ffmpeg alsa-utils python3-numpy python3-pil

# Install from release asset:
sudo dpkg -i mtp_1.2.1_all.deb
# or: sudo apt install ./mtp_1.2.1_all.deb

# Or build locally:
./packaging/build-deb.sh
sudo dpkg -i packaging/mtp_1.2.1_all.deb
```

### From .rpm package (Fedora / RHEL)

```bash
# Prerequisites (one-time setup)
sudo dnf install ffmpeg python3-numpy python3-pillow

# Install from release asset:
sudo rpm -i mtp-1.2.1-1.noarch.rpm
# or: sudo dnf install ./mtp-1.2.1-1.noarch.rpm

# Or build locally (requires rpm-build):
sudo dnf install rpm-build
./packaging/build-rpm.sh
sudo rpm -i packaging/mtp-1.2.1-1.noarch.rpm
```

Both packages install the app to `/usr/share/mtp/`, a launcher at `/usr/bin/mtp`, and register it in your application menu automatically. The launcher will warn you if any system dependency is missing.

### From source (any Linux distro)

```bash
# Install all dependencies (adjust package manager for your distro)
sudo apt install python3 ffmpeg alsa-utils python3-numpy python3-pil   # Debian/Ubuntu
# sudo dnf install python3-tkinter ffmpeg python3-numpy python3-pillow  # Fedora
# sudo pacman -S python ffmpeg alsa-lib numpy python-pillow             # Arch

pip install customtkinter

# Run
./start.sh
# or directly:
python3 mtp.py
```

#### Optional: Add to your application menu (source install)

1. Copy `mtp.desktop` to `~/.local/share/applications/`
2. Replace `/PATH/TO/REPO` with your actual clone path (e.g., `~/projects/minimaltouchplayer`)
3. Run `update-desktop-database ~/.local/share/applications/`

Now "MinimalTouchPlayer" appears in your app launcher! 🎵

## Usage

| Action | Button / Key |
|--------|-------------|
| Play / Pause | Center button · **Space** |
| Previous track | Left button · **←** |
| Next track | Right button · **→** |
| Volume up / down | Slider · **↑ / ↓** |
| Seek position | Drag the seek bar |
| Open folder picker | Folder button · **o** |
| Toggle shuffle | Shuffle icon (green = on) · **s** |
| Cycle repeat mode | Repeat icon (off → all → one) · **r** |
| Select track from list | Tap the title text |
| Zoom in / out | — · **Ctrl + / Ctrl −** |
| Reset zoom | — · **Ctrl 0** |

Select a music folder and press play. Tracks are scanned recursively, played in natural sort order, and the player remembers where you left off.

## Configuration

Runtime settings (volume, last folder, zoom level, resume position, shuffle, repeat) are stored automatically in `~/.config/mtp/config.json`. The directory is created on first save. No manual configuration needed.

### Audio device override

If no sound is produced, force a specific audio backend:

```bash
MUSIKPLAYER_DEVICE=pipewire ./start.sh   # PipeWire
MUSIKPLAYER_DEVICE=alsa ./start.sh       # ALSA (aplay)
```

Or list available devices with `aplay -L`.

## Technical Details

| Component | Role |
|-----------|------|
| **CustomTkinter** | GUI framework (dark, modern widgets) |
| **ffmpeg** | Decodes any supported audio format to raw PCM (48 kHz / stereo / 16-bit), no `-re` flag — sink-paced timing |
| **NumPy** | Real-time volume scaling per 4096-byte chunk + 60 ms fade-in ramp |
| **paplay / aplay** | System audio output (PipeWire preferred, `--latency-msec=80`) |

Architecture: `ffmpeg` decodes immediately into a pipe → Python pump thread scales volume and feeds chunks to the system player. The sound card itself provides timing (back-pressure on the pipe) — no sleep loops, no drift, no jitter. Pause is implemented via a blocking condition variable — no process restart, exact position retention.

## Project Structure

```
├── mtp.py                  # Complete application v1.2.1 (GUI + audio engine)
├── MTP Icons/              # 10 PNG button icons (512×400 RGBA, transparent BG)
├── icon.png                # App icon (512×512)
├── start.sh                # Development launcher script
├── images/                 # Screenshots for this README
├── README.md               # This file
└── packaging/
    ├── build-deb.sh        # One-command .deb builder
    └── deb/                # Package source tree (DEBIAN/, usr/bin, usr/share/)
```

## Uninstalling

```bash
sudo dpkg -r mtp
# Removes: /usr/bin/mtp, /usr/share/applications/mtp.desktop,
#          /usr/share/icons/hicolor/128x128/apps/mtp.png,
#          /usr/share/mtp/

# User config (NOT removed by package uninstall):
rm -rf ~/.config/mtp/   # optional: removes saved volume, folder, resume position
```

## Changelog

### v1.2.1 (2026-11-03)
- **Transparent icons** — all PNG icons now have transparent backgrounds (no gray box), ~60 % smaller file size, cleaner on any theme
- **Simplified folder picker** — removed redundant OK button; Cancel moved next to Play in top nav row `[↑] [▶ Play] [Abbrechen]`, full height for folder list
- **Build fixes** — build script now auto-syncs DEBIAN/control version and refreshes entire app directory on every build

### v1.2.0 (2026-10-30)
- **Track dropdown** — tap the title to open a scrollable track list with large 14 pt font; select any song instantly
- **Natural sort** — numeric filenames sort correctly (Track 2 < Track 3 < … < Track 10), case-insensitive
- **Folder picker shows track count** — each subfolder displays `(N)` or `(500+)` for quick overview
- **Icons +50 % larger** — all transport & mode buttons enlarged for easier touch targeting
- **Shuffle & Repeat** — toggle shuffle (key `s`), cycle repeat off/all/one (key `r`)
- **Engine rewrite** — removed `-re`, sink-paced timing via audio pipe, 60 ms fade-in, duration cache

### v1.1.0 (2026-10-24)
- Initial public release: CustomTkinter GUI, .deb packaging, bilingual UI, position resume

## License

[MIT](LICENSE) © 2026 Pirate85

---

*Built with ❤️ for touch-friendly desktop music listening.*  
*Developed by Pirate85 & Herbert (Local AI)*
