# Spickzettel — MinimalTouchPlayer (MTP)

> Kurzes Projekt-Notizbuch. Hier steht, WIE das Ding funktioniert und was zu beachten ist.

## ⚠️ Spielregeln (Verhalten) — wichtig!
- **Erst FRAGEN / Erlaubnis holen**, bevor ich in Martins private Dateien **außerhalb** des Projektordners
  greife (z.B. `~/Programme/…`, `~/.local/share/applications/`) — auch bei „kleinen" Änderungen.
  Innerhalb des aktiven Projektordners darf ich editieren.

## Namens-Kanone & WM_CLASS (FINAL — 24.10.2026)
- **Anzeigename:** `MinimalTouchPlayer` (Fenstertitel, App-Menü, README)
- **Paket-/Binary-Name:** `mtp` (`/usr/bin/mtp`, Paket `mtp_1.2.0_all.deb`)
- **WM_CLASS-Token:** `mtp` — einfach, kurz, KEINE internen Großbuchstaben!

### ⚠️ WICHTIGE LEHRE (24.10. Bug-Fix):
**`className=` im Code muss ein einheitliches Token OHNE interne Großbuchstaben sein!**

| ❌ FALSCH | Ergebnis | Problem |
|---|---|---|
| `className="MinimalTouchPlayer"` | WM_CLASS = `"minimalTouchPlayer", "Minimaltouchplayer"` | matcht NICHT mit `StartupWMClass=minimaltouchplayer` (Case-Mismatch!) |

| ✅ RICHTIG | Ergebnis | Match |
|---|---|---|
| `className="mtp"` | WM_CLASS = `"mtp", "Mtp"` | `StartupWMClass=mtp` → **exakt** ✅ |

Regel: **Ein Wort, ein Token.** Wie vorher bei „Musicplayer" (ein Wort) hat's funktioniert.
Mehrere Wörter mit Capitals im Namen → Tk lowercased nur den ersten Buchstaben → Mismatch!

### Konfiguration (muss überall stimmen):
| Stelle | Wert |
|---|---|
| Python `className=` | `"mtp"` |
| Python `root.title()` | `"MinimalTouchPlayer"` |
| `.desktop` `Name=` | `MinimalTouchPlayer` |
| `.desktop` `StartupWMClass=` | `mtp` |
| `.desktop` `Icon=` | `mtp` (via hicolor-Theme) |
| `.desktop` `Exec=` | `/usr/bin/mtp` |
| Icon-Pfad im System | `/usr/share/icons/hicolor/128x128/apps/mtp.png` |

### ⚠️ NIE wieder:
- ctypes / `_GTK_APPLICATION_ID` Hacks → crasht unter XWayland (BadWindow)!
- `update-desktop-database` nach jeder .desktop-Änderung nicht vergessen!
- Icon-Cache Refresh: `sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/`

## Ziel
Minimalistischer, **quadratischer** Desktop-Musikplayer für **kleine Touchmonitore (10", 1920×1280)**:
große PNG-Icon-Tasten, Ordner öffnen, Lautstärke-Schieberegler, Shuffle & Repeat, **kein Albumcover**.
Soll in den freien Bereich oben rechts neben dem AXB35-System-Monitor passen.

**v1.2 Features:** PNG-Icons (MTP Icons/), Shuffle Toggle, Repeat (Off/All/One), neue Engine ohne -re, **Natural Sort**, **Track-Count im Picker**, **Klickbarer Titel → Track-Dropdown**.

## Umgebung (Martin — Ubuntu 26.10)
- Python **3.14.8** · **CustomTkinter 6.0.0** ✓ (GUI, via pip) · numpy **2.4.6** ✓ (via apt: `python3-numpy`)
- **ffmpeg**, **ffprobe**, **aplay** vorhanden · PipeWire-Audio
- **Xvfb / xvfb-run** verfügbar → GUI headless testbar (`xvfb-run -a python3 …`)
- KEIN mpv; Audio-**Backend bleibt eigen** (ffmpeg→Python→aplay/paplay) — CustomTkinter ist nur die Hülle

## Installation & Betrieb (.deb — AB SOFORT!)
Die DEV-Kopie unter `~/Programme/Musikspieler` ist **deprecated**. Ab jetzt läuft alles über das .deb-Paket!

```bash
# Installieren:
cd "/home/martin/KI Projekte/MinimalTouchPlayer 1.2.0"
sudo dpkg -i packaging/mtp_1.2.0_all.deb
# oder: sudo apt install ./packaging/mtp_1.2.0_all.deb

# Starten (aus App-Menü, Dock, oder Terminal):
mtp

# Deinstallieren:
sudo apt remove mtp   # (ruft postrm auf → Caches werden aktualisiert)

# Nach Installation: Icon-Cache ggf. manuell frischen + GNOME-Shell neu laden:
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/
update-desktop-database /usr/share/applications/
# Alt+F2 → r (X11) oder aus-/einloggen (Wayland)
```

**Wichtig:** Immer aus Martins normaler Desktop-Session starten (dort ist `XDG_RUNTIME_DIR` gesetzt).

## Architektur (1 Datei: `mtp.py`)
```
CustomTkinter-GUI  ──steuert──>  Engine  ──>  ffmpeg (Dekodierung -> rohes PCM int16/48kHz/stereo)
                                       │         KEIN -re! Dekodiert sofort in die Pipe.
                                       └─ Python skaliert Lautstärke + Fade-In (numpy)
                                              │
                                              ▼
                                       paplay/aplay  (Taktung via Audio-Sink-Pipe!)
```
- **Taktung:** Die Soundkarte selbst pumpt in Echtzeit — `sink.stdin.write()` blockiert, wenn der Puffer voll ist.
  Kein Python-sleep, kein Drift, kein Jitter! (`--latency-msec=80` hält paplay-Puffer klein.)
- **Pause** = `threading.Condition.wait()` im Pump-Thread → ffmpeg blockt am vollen Pipe-Puffer,
  Position bleibt exakt; Resume liest nahtlos weiter. (kein Neustart, keine Lücke)
- **Lautstärke live** = numpy-Skalierung pro Chunk (`Engine._scale`), Fallback rein-python
- **Seek** = `ffmpeg -ss <t>` neu starten (`Engine.seek` → `play(start=...)`) — Duration wird gecacht bei gleichem Track
- **Auto-Nächste** = Pipe leer (EOF) + ffmpeg rc==0 → Event `ended` in Queue → GUI-Poll startet nächsten Titel
  (respektiert Shuffle & Repeat-Modus!)
- **Dauer** via ffprobe; **Position** = gepumpte Bytes / (48000·2·2)
- **Fade-In:** 60ms Micro-Fade am Start/Seek (sample-genaue Rampe via numpy linspace) gegen Knacksen

## Wichtige Details
- **UI v1.2:** PNG-Icon-Buttons aus `MTP Icons/` (512×400 RGBA, transparenter BG). Layout:
  - Zeile 1: [backward] [play/pause] [forward] — Transport
  - Zeile 2: 🔊 Slider % — Lautstärke  
  - Zeile 3: [shuffle] [folder (72px)] [repeat] — v1.2 neu!
- **Shuffle:** Toggle On/Off, persistiert in Config. Bei aktiv → zufälliger Titel (nicht den aktuellen).
- **Repeat:** Zyklus Off→All→One→Off. One = gleicher Track von vorn, All = Loop, Off = Stop am Ende.
- **Resume:** `last_track` + `last_pos` in Config → nächster Start setzt Index auf gemerkten Titel, Play startet von gespeicherter Position (Guard: >90 % → von vorn). Nur 1× pro Session (`_resumed`).
- Audio-Pipeline: `SR=48000`, `CH=2` — universell, kein Sample-Rate-Mismatch
- Sink-Auswahl: `paplay` bevorzugt (`--latency-msec=80`), sonst `aplay` (`--buffer-time=80000`); Gerät per Env `MUSIKPLAYER_DEVICE`
- Config in `~/.config/mtp/config.json`: `{volume, last_folder, scale, last_track, last_pos, shuffle, repeat}`
- GUI startet bei `x = Screenbreite − WIDTH·scale − 24`, `y=16` → oben rechts; Fenster resize-fähig
- **Versionsanzeige:** `v{VERSION}` in der unteren Legendenzeile (Schema: `Strg +/− : Zoom · Strg 0 : Reset · 100% · v1.2`)

## ⚠️ Skalierung & Zoom (hier lag der Overflow-Bug — NICHT rückgängig machen!)
CustomTkinter **skaliert Schrift UND Button-Breite beide einmalig** über `set_widget_scaling(s)`
(`_apply_font_scaling` → `-abs(round(size·s))`, `_apply_widget_scaling` → `int(width·s)`).

1. **Nicht zusätzlich selbst skalieren!** Früher: `_fnt()` multiplizierte die Schriftgröße *auch* mit
   `self.scale` → Schrift wuchs mit **S²**, Breite nur mit **S** → Text lief über die Taste (Zoom > 100 %).
   Jetzt: `_fnt(size)` liefert die **Basisgröße**, CTk skaliert einmalig. → Schrift & Breite bleiben proportional.
2. **Button-Breiten sind DPI-adaptiv:** `max(Grundbreite, Font.measure(Text)+Padding)`.
3. **Zoom-Shortcuts:** `Strg +/−` (auch Numpad) rein/raus · **`Strg 0` = Reset auf 100 %** (auch Numpad).

## Tastatur
Leertaste Play/Pause · ←/→ Vor/Zurück · ↑/↓ Lautstärke · `o` Ordner öffnen · `s` Shuffle · `r` Repeat · **Strg +/− Zoom · Strg 0 Reset**

## Bekannte Grenzen / Hinweise
- Positionsanzeige führt um den paplay-Puffer leicht (wenige ms) — kosmetisches Detail
- Falls stumm: `MUSIKPLAYER_DEVICE=pipewire mtp`
- Ordner-Picker ist resizable (min 400×400), Buttons immer sichtbar via `side="bottom"`

## Dateien & Projektstruktur
### Hauptprojekt (`~/KI Projekte/MinimalTouchPlayer 1.2.0`)
| Datei / Ordner | Zweck |
|---|---|
| `mtp.py` | kompletter Player v1.2 (GUI + Engine, PNG-Icons, Shuffle/Repeat, Bilingual) |
| `MTP Icons/` | 10× PNG-Icons (512×400 RGBA): backward, forward, play, pause, folder, shuffle_on/off, repeat_all/one/off |
| `SPICKZETTEL.md` | dieses Dokument |
| `config.json` | zur Laufzeit angelegt (~/.config/mtp/) — **nicht im Projektordner** |
| `icon.png` | App-Icon (512×512 PNG, wird in .deb als `mtp.png` installiert) |
| `start.sh` | Dev-Launcher (`python3 mtp.py`) |
| `README.md` | Nutzer-Doku — **neue Screenshots in images/ von Martin bereitgestellt** |
| `images/` | Screenshot-Bilder für README (v1.2) |

### v1.1.0 bleibt unverändert!
```
~/KI Projekte/Musikspieler          ← v1.1.0 FINAL (unveränderlich)
~/GItHub Projekte/Musikspieler      ← GitHub-Repo v1.1.0 (Commit 4032207, Tag v1.1.0)
```

### v1.2 Projektstruktur:
```
├── .gitignore              ← config.json, __pycache__, *.bak, *.deb ignoriert
├── LICENSE                 ← MIT © Pirate85
├── README.md               ← Englisch (für GitHub-Upload vorbereitet)
├── mtp.py                  ← App-Code v1.2 (className="mtp", PNG-Icons, Shuffle/Repeat)
├── MTP Icons/*.png         ← 10 Button-Icons (512×400 RGBA, transparenter BG)
├── icon.png                ← 512×512 App-Icon
├── start.sh                ← Dev-Launcher
├── images/                 ← README-Screenshots
└── packaging/
    ├── build-deb.sh        ← ./build-deb.sh → mtp_1.2.0_all.deb
    └── deb/
        ├── DEBIAN/control  ← Package: mtp, Version: 1.2.0
        ├── DEBIAN/postinst ← gtk-update-icon-cache + update-desktop-database
        ├── DEBIAN/postrm   ← Caches bei Deinstallation aktualisieren
        ├── usr/bin/mtp     ← Launcher (prüft Dependencies, startet App)
        └── usr/share/
            ├── applications/mtp.desktop
            ├── icons/hicolor/128x128/apps/mtp.png
            └── mtp/
                ├── mtp.py
                └── MTP Icons/*.png   ← nur PNGs (kein Dev-Code!)
```

## .deb-Paket-Eckdaten
- **Paketname:** `mtp` · **Version:** 1.2.0 · **Architektur:** all (arch-independent)
- **Depends:** python3 (>= 3.10), python3-numpy, ffmpeg, alsa-utils | pipewire-pulseaudio
- **Nicht in apt:** `customtkinter` → wird per Launcher geprüft + klare Fehlermeldung
- **Build:** `./packaging/build-deb.sh` (braucht nur `dpkg-dev`)
- **Größe:** ~95KB

## Engine-Eckdaten (v1.2 — NEU!)
- **KEIN `-re` mehr!** ffmpeg dekodiert sofort in die Pipe → Taktung übernimmt der Audio-Sink.
  paplay: `--latency-msec=80` · aplay: `--buffer-time=80000` (kleiner Puffer = sofortige Reaktion)
- **Chunk:** 4096 Bytes (~21ms bei 48kHz/stereo/s16) — geringe Latenz für Pause/Volumen
- **Fade-In:** 60ms Micro-Fade via numpy linspace (sample-genau, L/R paarweise) gegen Knacksen
- **Stop-Logik:** Pipes ZUERST schließen → Thread wacht sofort auf → terminate → kill (kein sleep!)
- **Duration-Cache:** Gleicher Track → keine neue ffprobe-Aufrufe bei Seek (schneller)
- Erfolg/Fehler am **ffmpeg-Rückgabecode** (rc==0 → `ended`, sonst `error`) erkannt

## Optimierungen v1.2.1 (30.10.2026 20:50)
- **Thread-Safety:** `play()` ruft vor neuem Thread `old_thread.join(timeout=0.5)` auf → kein Race bei rapid Skipping
- **Gehörrichtige Lautstärke:** `_scale()` nutzt v² Kurve (`v = self._vol * self._vol`) statt linear → feinfühliger im unteren/mittleren Bereich (50% → Faktor 0.25)
- **True Shuffle (Fisher-Yates):** `_shuffle_order` Pool + `_shuffle_pos` Zähler → mischt alle Titel ohne Wiederholung, neu erst beim Durchlauf. Reset bei Playlist-Wechsel & Shuffle-On. Startposition: nach aktuellem Track.
- **Picker-Performance:** `_count_tracks()` nur noch max. 2 Ebenen tief via `os.scandir` (statt rekursivem `os.walk`) → kein GUI-Freeze bei großen Bibliotheken
- **Locale-Fix:** `locale.getdefaultlocale()` (deprecated) → `locale.getlocale()[0] or os.environ.get("LANG", "C")`

## ✅ Config-Pfad-Bug — GEFIXT (26.10.2026)
**War:** Player schrieb `config.json` ins Verzeichnis wo `mtp.py` liegt → bei .deb-Install `/usr/share/mtp/` = root-owned, keine Schreibrechte!

**Fix:** Config nach `~/.config/mtp/config.json` verlegt (XDG-konform).
- `CONFIG_DIR    = os.path.expanduser("~/.config/mtp")`
- `CONFIG_PATH   = os.path.join(CONFIG_DIR, "config.json")`
- `_save_config()`: `os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)` vor dem Write
- Gilt für BOTH: .deb-Install UND Source-Install → Config immer beim User ✅
- `.gitignore` hat `config.json` schon drin → bleibt so ✅

## Changelog
- **2026-10-30 (v1.2 FINAL — Usability + Icons + GitHub):**
  - **Klickbarer Titel → Track-Dropdown:** Tap auf den Tracktitel öffnet breites Popup mit großer Schrift (14pt), scrollbar, aktueller Track grün + ▶ hervorgehoben. Auswahl → direkt abspielen. Escape schließt.
  - **Natural Sort:** `natural_sort_key()` — Zahlen in Dateinamen werden numerisch sortiert (Track 2 < Track 3 < … < Track 10). Gilt für Playlist UND Folderpicker-Ordnerliste. Case-insensitive.
  - **Track-Anzahl im Folderpicker:** `_count_tracks(limit=500)` → zeigt `📁 Name   (42)` oder `(500+)`. Rekursiv, nur bei >0.
  - **Icons +50% größer:** backward/forward/shuffle/repeat: 45×36, play/pause/folder: 51×42 / 54×42.
  - **`current_folder` explizit gespeichert** (robuster Config-Save, kein mehr `playlist[0]`-Trick).
  - **Picker-Breite fix:** BASE_W=800, CTkScrollableFrame mit expliziter `width=`, dynamisch bis 950px. Kumpel-Tipp: `width=` auf ScrollableFrame verhindert den 200px-CTk-Bug!
  - **.deb v1.2.0 gebaut** (95KB) — enthält alle Features.
  - **GitHub Push:** master + Tag v1.2.0 → https://github.com/Pirate85/minimaltouchplayer
  - ✅ **README v1.2** aktualisiert: Features, Screenshots (Main + Folderpicker + Track Dropdown), Changelog — Commit `70c59ac`.
  - ✅ **GitHub Release v1.2.0** live mit `.deb`-Attachment → https://github.com/Pirate85/minimaltouchplayer/releases/tag/v1.2.0
- **2026-10-29 (v1.2 — Icons, Shuffle/Repeat, Engine-Update):**
  - Neues Projektordner: `~/KI Projekte/MinimalTouchPlayer 1.2.0` (eigenständig von v1.1)
  - **PNG-Icons:** Alle Unicode-Zeichen (⏮▶⏭📂) → echte PNG-Bilder aus `MTP Icons/` (512×400 RGBA, transparenter BG)
    - 10 Icons: backward, forward, play, pause, folder, shuffle_on/off, repeat_all/one/off
    - Grün (#7CE882) = aktiv/an · Grau (#242730) = inaktiv/aus
  - **Shuffle:** Toggle (Taste `s`), persistiert in Config. Zufälliger Titel bei aktiv.
  - **Repeat:** Zyklus Off→All→One (Taste `r`). One=gleicher Track, All=Loop, Off=Stop am Ende.
  - **Neue Bottom-Zeile:** [Shuffle] [Folder (72px)] [Repeat] — gleiche Breite wie Transport oben
  - **Engine komplett neu** (Tipp von Martins Kumpel):
    - `-re` entfernt → Taktung über Audio-Sink-Pipe (OS-Level, kein Python-sleep)
    - `--latency-msec=80` (paplay) / `--buffer-time=80000` (aplay) für kleinen Puffer
    - Chunk 4096 Bytes statt 8192 → weniger Latenz
    - 60ms Micro-Fade (numpy linspace) statt 250ms per-Chunk-Mittelung
    - Stop: Pipes erst schließen → Thread wacht sofort auf (kein sleep(0.15))
    - Duration-Cache bei gleichem Track (Seek ist schneller)
    - **FIX:** Sync/Skipping-Probleme komplett behoben! 🎉
  - **Ordner-Picker Verbesserungen:**
    - Breite: 400→520px Start, max 850px dynamisch
    - Resizable (min 400×400) — Buttons immer sichtbar via `side="bottom"`
    - Scroll-Reset bei jedem Ordnerwechsel (`yview_moveto(0)`)
  - **Versionsanzeige:** `v1.2` in unterer Legendenzeile (konsistentes Schema mit Zoom-Hinweis)
  - **.deb v1.2.0** gebaut (~95KB), MTP Icons/ nur als PNGs im Paket
- **2026-10-26 (Resize + Rename mtp.py):**
  - Fenstergröße: WIDTH 470→**390**, HEIGHT bleibt 470 → passt besser auf „normale" Bildschirme als Initialgröße
  - **Rename:** `musicplayer.py` → **`mtp.py`** (konsistent mit Paket-/Binary-Namen)
  - Alle Referenzen aktualisiert: start.sh, build-deb.sh, Launcher, README, packaging-Struktur
  - README Uninstall-Sektion: `~/.config/mtp/` als User-Config-Hinweis ergänzt
- **2026-10-26 (Config-Pfad-Bug fix):**
  - `config.json` von neben `musicplayer.py` → **`~/.config/mtp/config.json`** verlegt
  - `.deb`-Install: Config landet jetzt beim User statt in root-owned `/usr/share/mtp/` ✅
  - `_save_config()`: Ordner `~/.config/mtp/` wird bei Bedarf automatisch angelegt (`os.makedirs`)
  - Gilt für Source- UND .deb-Install · README + Spickzettel aktualisiert
- **2026-10-24 (GitHub-ready + Rename auf MinimalTouchPlayer/MTP):**
  - **Rename:** „Musicplayer" → **MinimalTouchPlayer** (Anzeige) / **mtp** (Paket/Binary/WM_CLASS-Token)
  - **.deb-Paket** mit postinst/postrm (Icon-Cache, Desktop-DB), saubere Dependencies
  - **WM_CLASS-Bug gefixt:** `className="MinimalTouchPlayer"` → Case-Mismatch mit StartupWMClass!
    Fix: `className="mtp"` → WM_CLASS = `"mtp","Mtp"` → matcht exakt mit `StartupWMClass=mtp` ✅
  - **Fenstertitel** auf „MinimalTouchPlayer" geändert
  - **README** komplett auf Englisch, Touch-Monitor-Kontext (10", 1920×1280) ergänzt
  - **LICENSE** MIT © Pirate85 · **.gitignore** für Repo
  - DEV-Kopie (`~/Programme/Musikspieler`) **deprecated** → .deb ist ab jetzt der offizielle Weg!
- **2026-10-21 (CTk-Ordner-Picker + Titel-Wrap-Fix):**
  - Eigener CTk-Ordner-Picker, ScrollableFrame, Parent-Navigation, Play Button
  - Titel-Wrap-Fix (S²-Bug), Fensterhöhe 560→470
- **2026-10-19 (Resume + Icons):** Position-Resume, Icon-Buttons, Bilingual DE/EN
- **2026-10-17 (CustomTkinter + Bugfixes):** GUI-Umstellung, Overflow-Fix, WM_CLASS finalisiert
