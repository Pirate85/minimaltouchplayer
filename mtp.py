#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinimalTouchPlayer v1.2 — minimalistischer Touch-Musikspieler mit gerundeten Icon-Tasten.

Kein Albumcover. Ordner öffnen, Play/Pause, Vor/Zurück, Seek, live Lautstärke,
Shuffle & Repeat (All/One). PNG-Icons aus MTP Icons/. Globaler Zoom per Strg +/−.

GUI:      CustomTkinter (gerundete Buttons/Slider, eingebaute Skalierung)
Backend:  ffmpeg -> Python(Lautstärke/numpy) -> paplay/aplay (Taktung via Audio-Sink)
"""

import os
import re
import json
import time
import queue
import locale
import shutil
import random
import threading
import subprocess
from tkinter import filedialog
import tkinter.font as tkfont
from PIL import Image, ImageTk
import customtkinter as ctk

try:
    import numpy as np
except Exception:            # numpy optional — Fallback weiter unten
    np = None


# ----------------------------- Konstanten ---------------------------------
VERSION = "1.2"              # Anzeigeversion (unten rechts im UI)
SR   = 48000                 # interne Abtastrate (universell unterstützt)
CH   = 2                     # Stereo
AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac",
              ".wav", ".wma", ".aiff", ".ape", ".webm"}

# Farben (dunkel, ruhig, minimalistisch)
C_BG      = "#17181c"
C_PANEL   = "#202229"
C_BTN     = "#262a33"
C_BTN_HOV = "#343b48"
C_ACCENT  = "#7ee787"        # sanftes Grün (passt zum AXB35-System-Monitor)
C_TEXT    = "#d7dae0"
C_DIM     = "#8b91a0"

# ------------------- Bilinguale Strings (DE/EN per System-Locale) ---------
def _detect_lang():
    loc = (locale.getdefaultlocale() or ("C",))[0]
    return "de" if loc.lower().startswith("de") else "en"

_LANG = _detect_lang()
STRINGS = {
    "ready":       {"de": "Bereit",      "en": "Ready"},
    "pause":       {"de": "Pause",       "en": "Paused"},
    "error":       {"de": "Fehler",      "en": "Error"},
    "no_folder":   {"de": "Kein Ordner", "en": "No Folder"},
    "no_audio":    {"de": "Keine Audiodateien", "en": "No audio files"},
    "open_first":  {"de": "Erst einen Ordner öffnen!", "en": "Open a folder first!"},
    "play_hint":   {"de": "Ordner öffnen zum Starten.", "en": "Open a folder to start."},
    "choose_dir":  {"de": "Musikordner wählen", "en": "Choose music folder"},
    "tracks_in":   {"de": "{n} Titel in \"{folder}\"", "en": "{n} tracks in \"{folder}\""},
    "ok":          {"de": "OK",           "en": "OK"},
    "cancel":      {"de": "Abbrechen",   "en": "Cancel"},
}

def S(key):
    """Kurz: S('ready') -> 'Bereit' oder 'Ready' je nach System-Sprache."""
    return STRINGS[key][_LANG]

HERE          = os.path.dirname(os.path.abspath(__file__))
ICON_DIR      = os.path.join(HERE, "MTP Icons")
CONFIG_DIR    = os.path.expanduser("~/.config/mtp")
CONFIG_PATH   = os.path.join(CONFIG_DIR, "config.json")
FONT          = "DejaVu Sans"


def fmt_time(sec):
    if sec is None or sec < 0:
        return "--:--"
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def probe_duration(path):
    """Dauer einer Datei in Sekunden (via ffprobe), sonst None."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
        return float(out.stdout.strip())
    except Exception:
        return None


def natural_sort_key(s):
    """Natural Sort Key: 'Track 2' < 'Track 10', 'Album A' < 'Album B'.
    Splitzt in Text/Number-Teile, Zahlen werden als int sortiert."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


def scan_folder(root):
    """Alle Audiodateien unter `root` (rekursiv), natural-sorted nach Ordner+Name."""
    found = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if os.path.splitext(name)[1].lower() in AUDIO_EXTS:
                found.append(os.path.join(dirpath, name))
    found.sort(key=lambda p: (natural_sort_key(os.path.dirname(p)), natural_sort_key(os.path.basename(p))))
    return found


def default_music_dir():
    """Portabler Startordner für 'Ordner öffnen': XDG_MUSIC_DIR -> ~/Music/~/Musik -> Home."""
    home = os.path.expanduser("~") or "/root"
    cands = []
    env = os.environ.get("XDG_MUSIC_DIR")
    if env:
        cands.append(env)
    for name in ("Music", "Musik", "music"):
        cands.append(os.path.join(home, name))
    for c in cands:
        try:
            if c and os.path.isdir(c):
                return c
        except Exception:
            pass
    return home


# =============================== Audio-Engine =============================
class Engine:
    """ffmpeg -> Python(Lautstärke) -> aplay/paplay. Taktung direkt über Audio-Sink-Pipe."""

    def __init__(self):
        self._vol = 0.8
        self._paused = False
        self._stopped = True
        self._eof = False
        self._cond = threading.Condition()
        self.ff = None
        self.sink = None
        self.thread = None
        self.path = None
        self.duration = None
        self.events = queue.Queue()      # 'ended' | 'error'  -> GUI
        self._pumped_bytes = 0
        self._bytes_lock = threading.Lock()
        self._offset = 0.0               # Start-Offset (für Seek) in Sekunden

    def _sink_cmd(self):
        dev = os.environ.get("MUSIKPLAYER_DEVICE")     # optional: z.B. "pipewire"
        if shutil.which("paplay"):
            # --latency-msec=80 hält den Pipe-Puffer klein -> Lautstärke & Pause reagieren sofort,
            # und sink.stdin.write() übernimmt die exakte Echtzeit-Taktung der Soundkarte!
            cmd = ["paplay", "--format=s16le", f"--rate={SR}", f"--channels={CH}",
                   "--latency-msec=80"]
            if dev:
                cmd += [f"--device={dev}"]
            return cmd + ["-"]
        if shutil.which("aplay"):
            cmd = ["aplay", "-q", "-f", "S16_LE", "-r", str(SR), "-c", str(CH),
                   "--buffer-time=80000"]
            if dev:
                cmd += [f"-D{dev}"]
            return cmd + ["-"]
        raise RuntimeError("Kein Audio-Ausgabegerät gefunden (paplay/aplay fehlt).")

    def _scale(self, data, fade_start=1.0, fade_end=1.0):
        v = self._vol
        if np is not None:
            a = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            if fade_start < 1.0 or fade_end < 1.0:
                # Sample-genaue, glatte Rampe für Stereo (L/R paarweise gleich skalieren)
                frames = len(a) // CH
                ramp = np.linspace(fade_start, fade_end, frames, dtype=np.float32)
                a = (a.reshape(-1, CH) * (ramp * v)[:, None]).reshape(-1)
            else:
                a *= v
            return a.clip(-32768, 32767).astype(np.int16).tobytes()

        import array as _array                       # langsamer Fallback ohne numpy
        arr = _array.array("h"); arr.frombytes(data)
        n = len(arr)
        for i in range(n):
            f = fade_start + (fade_end - fade_start) * (i / max(1, n - 1))
            x = int(arr[i] * v * f)
            arr[i] = -32768 if x < -32768 else (32767 if x > 32767 else x)
        return arr.tobytes()

    def _pump(self, ff, sink):
        # 4096 Bytes = 1024 Stereo-Frames ≈ 21.3 ms pro Chunk bei 48 kHz
        buf = 4096
        rate = SR * CH * 2
        self._eof = False
        # Kurzes, glattes Micro-Fade-In (60 ms) gegen Knacksen beim Seek/Start
        fade_bytes = int(rate * 0.06)
        faded = 0
        try:
            while True:
                with self._cond:
                    while self._paused and not self._stopped:
                        self._cond.wait()
                    if self._stopped:
                        break

                data = ff.stdout.read(buf)
                if not data:                 # Datei-Ende erreicht (echtes EOF)
                    self._eof = True
                    break

                if self._stopped:
                    break

                if faded < fade_bytes:
                    f_start = min(1.0, faded / fade_bytes)
                    f_end = min(1.0, (faded + len(data)) / fade_bytes)
                    faded += len(data)
                else:
                    f_start = f_end = 1.0

                out = self._scale(data, f_start, f_end)
                try:
                    sink.stdin.write(out)
                    sink.stdin.flush()
                except (BrokenPipeError, OSError):
                    break                      # Sink beendet -> raus

                with self._bytes_lock:
                    self._pumped_bytes += len(data)
        finally:
            # Sicherstellen, dass sink die letzten gepufferten Millisekunden noch ausspielt
            try:
                if self._eof and not self._stopped and sink.stdin:
                    sink.stdin.close()
                    sink.wait(timeout=1.0)
            except Exception:
                pass

            if not self._stopped:              # natürlich zu Ende gelaufen -> Event senden
                rc = 0
                try:
                    if ff is not None:
                        rc = ff.wait(timeout=1) or 0
                except Exception:
                    rc = 0
                self.events.put("ended" if (self._eof and rc == 0) else "error")

    # ----------------------------- öffentliche API ------------------------
    def play(self, path, start=0.0):
        same_file = (self.path == path and self.duration is not None)
        self.stop()
        self.path = path
        if not same_file:
            self.duration = probe_duration(path)
        with self._bytes_lock:
            self._pumped_bytes = 0
        self._offset = max(0.0, float(start))

        # KEIN "-re" mehr! ffmpeg dekodiert sofort in die Pipe, Taktung erfolgt über sink.
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        if start and start > 0.05:
            cmd += ["-ss", f"{start:.3f}"]
        cmd += ["-i", path, "-vn", "-sn", "-dn",
                "-f", "s16le", "-ar", str(SR), "-ac", str(CH), "-"]

        self.ff = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.sink = subprocess.Popen(self._sink_cmd(), stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with self._cond:
            self._paused = False
            self._stopped = False
        self.thread = threading.Thread(target=self._pump, args=(self.ff, self.sink), daemon=True)
        self.thread.start()

    def pause(self):
        with self._cond:
            if not self._stopped and self.ff is not None:
                self._paused = True

    def resume(self):
        with self._cond:
            self._paused = False
            self._cond.notify_all()

    def stop(self):
        with self._cond:
            self._stopped = True
            self._paused = False
            self._cond.notify_all()

        ff, sink = self.ff, self.sink
        self.ff, self.sink = None, None

        # Zuerst Pipes schließen, damit blockierende read()/write()-Aufrufe im Thread sofort aufwachen
        for proc, stream_name in ((ff, "stdout"), (sink, "stdin")):
            try:
                if proc is not None and getattr(proc, stream_name):
                    getattr(proc, stream_name).close()
            except Exception:
                pass

        for p in (ff, sink):
            if p is not None:
                try:
                    p.terminate()
                except Exception:
                    pass

        for p in (ff, sink):
            if p is not None:
                try:
                    p.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    try:
                        p.kill()
                        p.wait(timeout=0.2)
                    except Exception:
                        pass
                except Exception:
                    pass

    def seek(self, seconds):
        if self.path:
            self.play(self.path, start=max(0.0, float(seconds)))

    def set_volume(self, v):
        self._vol = max(0.0, min(1.0, float(v)))

    def get_position(self):
        with self._bytes_lock:
            b = self._pumped_bytes
        return self._offset + b / (SR * CH * 2)

    @property
    def active(self):
        return self.ff is not None and not self._stopped

    @property
    def paused(self):
        return self.active and self._paused




# ================================== GUI ===================================
class MusicPlayer:
    WIDTH = 390
    HEIGHT = 470
    MIN_SCALE, MAX_SCALE, STEP = 0.7, 2.5, 0.1

    def __init__(self, root):
        self.root = root
        self.engine = Engine()
        self.playlist = []
        self.current_folder = None
        self.index = -1
        self.folder_name = ""
        self.dragging_seek = False

        cfg = self._load_config()
        self.volume = int(cfg.get("volume", 80))
        self.last_folder = cfg.get("last_folder") or None
        self.scale = float(cfg.get("scale", 1.0))
        # Shuffle & Repeat (v1.2)
        self.shuffle_enabled = bool(cfg.get("shuffle", False))
        self.repeat_mode = int(cfg.get("repeat", 0))   # 0=off, 1=all, 2=one
        # Resume: letzter Titel + Position (überlebt Neustart)
        self._resume_track = cfg.get("last_track") or None
        self._resume_pos = float(cfg.get("last_pos", 0))
        self._resumed = False   # Flag: wurde diese Session schon einmal resumed?

        # App-Optik + globale Skalierung (vor dem Widget-Aufbau anwenden)
        ctk.set_appearance_mode("dark")
        try:
            ctk.set_widget_scaling(self.scale)
        except Exception:
            pass
        try:
            self.engine.set_volume(self.volume / 100.0)
        except Exception:
            pass

        self._build_ui()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind_keys()

        if self.last_folder and os.path.isdir(self.last_folder):
            self.load_folder(self.last_folder, autoplay=False)

        self._poll()

    # ----------------------------- Config ---------------------------------
    def _load_config(self):
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_config(self):
        last = self.current_folder or self.last_folder
        # Resume-Daten: werden in on_close() aktualisiert (Position vor Engine-Stop),
        # ansonsten bleibt der geladene Wert erhalten (kein Überschreiben bei App-Start).
        data = {
            "volume": self.volume,
            "last_folder": last,
            "scale": round(self.scale, 3),
            "last_track": self._resume_track,
            "last_pos": self._resume_pos,
            "shuffle": self.shuffle_enabled,
            "repeat": self.repeat_mode,
        }
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    # ----------------------------- UI-Aufbau ------------------------------
    def _fnt(self, size, bold=True):
        # WICHTIG: NICHT selbst mit self.scale skalieren! CustomTkinter skaliert Schrift UND
        # Breite beide einmalig ueber set_widget_scaling -> bleiben proportional (kein Overflow).
        return (FONT, int(round(size)), "bold" if bold else "normal")

    def _load_icon(self, name, size):
        """Lädt ein Icon aus MTP Icons/ als CTkImage in gewünschter Größe."""
        path = os.path.join(ICON_DIR, f"{name}.png")
        pil_img = Image.open(path).convert("RGBA")
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)

    def _fit(self, text, size, pad=28):
        """Breite in BASIS-Pixeln: echter gerendert-Text (Font.measure) + Padding.
        Passt auf jedem Monitor/DPI, weil dieselbe Rasterung wie das Display genutzt wird."""
        f = tkfont.Font(self.root, family=FONT, size=-int(round(size)), weight="bold")
        return int(f.measure(text)) + pad

    def _zoom_hint(self):
        return f"Strg +/− : Zoom  ·  Strg 0 : Reset  ·  {int(round(self.scale * 100))}%  ·  v{VERSION}"

    def _track_wrap(self):
        """Umbruchbreite des Titel-Labels in BASIS-Pixeln (CTk skaliert intern).
        Koppelt an die Seek-Slider-Breite: WIDTH - 52 (padx=26 links+rechts) - 14 (Text-Marge)."""
        return self.WIDTH - 66

    def _apply_track_wrap(self):
        try:
            self.track.configure(wraplength=self._track_wrap())
        except Exception:
            pass

    def _build_ui(self):
        root = self.root
        root.title("MinimalTouchPlayer")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = max(0, sw - int(self.WIDTH * self.scale) - 24)   # oben rechts (Freiraum neben Monitor)
        y = 16
        root.geometry(f"{int(self.WIDTH*self.scale)}x{int(self.HEIGHT*self.scale)}+{x}+{y}")
        root.minsize(340, 370)
        root.configure(fg_color=C_BG)

        # Statuszeile (bilingual + Icon)
        self.status = ctk.CTkLabel(root, text=f"✅ {S('ready')} — {S('play_hint')}",
                                   fg_color="transparent", text_color=C_DIM, font=self._fnt(11, False))
        self.status.pack(side="top", fill="x", padx=20, pady=(14, 2), anchor="w")

        # Track-Titel (lange Namen brechen in max. ~2 Zeilen um statt ueberzulaufen)
        self.track = ctk.CTkLabel(root, text="—", fg_color="transparent",
                                  text_color=C_TEXT, font=self._fnt(15), justify="center")
        self.track.pack(pady=(6, 2))
        self._apply_track_wrap()
        # Klickbar → Track-Liste öffnen (Touch-freundlich!)
        self.track.bind("<Button-1>", lambda e: self._show_track_list())

        # Zeitangabe
        self.time = ctk.CTkLabel(root, text="--:-- / --:--", fg_color="transparent",
                                 text_color=C_DIM, font=self._fnt(12, False))
        self.time.pack()

        # Seek-Slider (streckt sich über die Breite)
        seekrow = ctk.CTkFrame(root, fg_color="transparent")
        seekrow.pack(fill="x", padx=26, pady=(8, 4))
        seekrow.grid_columnconfigure(0, weight=1)
        self.seek = ctk.CTkSlider(seekrow, from_=0, to=100, command=lambda v: None,
                                  fg_color=C_PANEL, progress_color=C_ACCENT,
                                  button_color=C_ACCENT, button_hover_color="#a7f3b4")
        self.seek.grid(row=0, column=0, sticky="ew")
        self.seek.bind("<ButtonPress-1>", lambda e: setattr(self, "dragging_seek", True))
        self.seek.bind("<ButtonRelease-1>", self.on_seek_release)

        # --- Transport-Icons (PNG aus MTP Icons/) ---
        ctrl = ctk.CTkFrame(root, fg_color="transparent")
        ctrl.pack(pady=(14, 6))
        common = dict(fg_color=C_BTN, hover_color=C_BTN_HOV,
                      corner_radius=14, height=52, border_width=0)
        # Icon-Größen: Buttons sind 64x52 bzw. 72x52 → Icons ~45x36 / ~51x42 (~50% größer)
        self.img_prev   = self._load_icon("backward", (45, 36))
        self.img_play   = self._load_icon("play",     (51, 42))
        self.img_pause  = self._load_icon("pause",    (51, 42))
        self.img_next   = self._load_icon("forward",  (45, 36))

        self.btn_prev = ctk.CTkButton(ctrl, image=self.img_prev, text="", command=self.prev, width=64, **common)
        self.btn_play = ctk.CTkButton(ctrl, image=self.img_play, text="", command=self.toggle, width=72, **common)
        self.btn_next = ctk.CTkButton(ctrl, image=self.img_next, text="", command=self.next, width=64, **common)
        self.btn_prev.grid(row=0, column=0, padx=5)
        self.btn_play.grid(row=0, column=1, padx=5)
        self.btn_next.grid(row=0, column=2, padx=5)

        # --- Lautstärke (live) ---
        volrow = ctk.CTkFrame(root, fg_color="transparent")
        volrow.pack(fill="x", padx=26, pady=(14, 4))
        volrow.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(volrow, text="🔊", fg_color="transparent",
                     text_color=C_ACCENT, font=self._fnt(16)).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.volval = ctk.CTkLabel(volrow, text=f"{self.volume}%", fg_color="transparent",
                                   text_color=C_TEXT, width=48, font=self._fnt(12, False))
        self.volval.grid(row=0, column=2, sticky="e", padx=(10, 0))
        self.vol = ctk.CTkSlider(volrow, from_=0, to=100, command=self.on_volume,
                                 fg_color=C_PANEL, progress_color=C_ACCENT,
                                 button_color=C_ACCENT, button_hover_color="#a7f3b4")
        self.vol.set(self.volume)
        self.vol.grid(row=0, column=1, sticky="ew")

        # --- Shuffle · Ordner · Repeat (neue Zeile v1.2) ---
        bottom = ctk.CTkFrame(root, fg_color="transparent")
        bottom.pack(pady=(14, 6))
        common_b = dict(fg_color=C_BTN, hover_color=C_BTN_HOV,
                        corner_radius=14, height=52, border_width=0)

        self.img_shuffle_on   = self._load_icon("shuffle_on",   (30, 24))
        self.img_shuffle_off  = self._load_icon("shuffle_off",  (30, 24))
        self.img_folder       = self._load_icon("folder",       (36, 28))
        self.img_repeat_off   = self._load_icon("repeat_off",   (30, 24))
        self.img_repeat_all   = self._load_icon("repeat_all",   (30, 24))
        self.img_repeat_one   = self._load_icon("repeat_one",   (30, 24))

        self.btn_shuffle = ctk.CTkButton(bottom, image=self.img_shuffle_off if not self.shuffle_enabled else self.img_shuffle_on,
                                         text="", command=self.toggle_shuffle, width=64, **common_b)
        self.btn_folder  = ctk.CTkButton(bottom, image=self.img_folder, text="", command=self.open_folder,
                                         width=72, fg_color=C_PANEL, hover_color=C_BTN_HOV,
                                         corner_radius=14, height=52, border_width=0)
        self.btn_repeat  = ctk.CTkButton(bottom, image=self._repeat_icon(), text="", command=self.cycle_repeat, width=64, **common_b)

        self.btn_shuffle.grid(row=0, column=0, padx=5)
        self.btn_folder.grid(row=0, column=1, padx=5)
        self.btn_repeat.grid(row=0, column=2, padx=5)

        # Zoom-Hinweis + Version (unten)
        self.zoom_label = ctk.CTkLabel(root, text=self._zoom_hint(),
                                       fg_color="transparent", text_color=C_DIM, font=self._fnt(10, False))
        self.zoom_label.pack(side="bottom", pady=(4, 12))

    # ----------------------------- Tastatur -------------------------------
    def bind_keys(self):
        r = self.root
        r.bind("<space>", lambda e: self.toggle())
        r.bind("<Left>",  lambda e: self.prev())
        r.bind("<Right>", lambda e: self.next())
        r.bind("<Up>",    lambda e: self.bump_volume(+5))
        r.bind("<Down>",  lambda e: self.bump_volume(-5))
        r.bind("o",       lambda e: self.open_folder())
        r.bind("s",       lambda e: self.toggle_shuffle())
        r.bind("r",       lambda e: self.cycle_repeat())
        # Zoom (Haupttastatur + Numpad)
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            r.bind(seq, lambda e: self.zoom_in())
        for seq in ("<Control-minus>", "<Control-underscore>", "<Control-KP_Subtract>"):
            r.bind(seq, lambda e: self.zoom_out())
        # Reset auf 100 % (Haupttastatur + Numpad)
        for seq in ("<Control-0>", "<Control-KP_Multiply>", "<Control-KP_0>"):
            r.bind(seq, lambda e: self.zoom_reset())

    # ----------------------------- Zoom -----------------------------------
    def _set_scale(self, s):
        s = max(self.MIN_SCALE, min(self.MAX_SCALE, round(s, 2)))
        if abs(s - self.scale) < 1e-6:
            return
        self.scale = s
        try:
            ctk.set_widget_scaling(s)          # skaliert alle CTk-Widgets + Schrift
        except Exception as exc:
            print("Zoom-Fehler:", exc)
        self._apply_track_wrap()               # Umbruchbreite des Titels mit dem Zoom anpassen
        self.zoom_label.configure(text=self._zoom_hint())
        self._save_config()

    def zoom_in(self):
        self._set_scale(self.scale + self.STEP)

    def zoom_out(self):
        self._set_scale(self.scale - self.STEP)

    def zoom_reset(self):
        self._set_scale(1.0)

    # ----------------------------- Aktionen -------------------------------
    def open_folder(self):
        """Eigener CTk-Ordner-Picker — skaliert automatisch mit dem Player-Zoom."""
        result = {}

        def on_select(path):
            result["path"] = path
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        # --- Toplevel (CTk → respektiert set_widget_scaling automatisch!) ---
        BASE_W, BASE_H = 800, 440
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(S("choose_dir"))
        dlg.resizable(True, True)
        dlg.minsize(550, 400)

        # Position zentriert (oder sauber im Bildschirm gehalten)
        sw = self.root.winfo_screenwidth()
        real_w = int(BASE_W * self.scale)
        dx = max(10, min(sw - real_w - 20, self.root.winfo_x() + (self.root.winfo_width() - real_w) // 2))
        dy = max(10, self.root.winfo_y() + 40)
        dlg.geometry(f"{BASE_W}x{BASE_H}+{dx}+{dy}")
        dlg.configure(fg_color=C_BG)

        # Pfad-Anzeige (oben)
        path_var = {"current": default_music_dir(), "base_w": BASE_W}
        path_label = ctk.CTkLabel(dlg, text=path_var["current"], fg_color="transparent",
                                  text_color=C_DIM, font=self._fnt(10, False), anchor="w")
        path_label.pack(fill="x", padx=14, pady=(10, 2))

        # Navigation: ↑ (Parent) + ▶ Play
        navrow = ctk.CTkFrame(dlg, fg_color="transparent")
        navrow.pack(fill="x", padx=10, pady=(2, 6))

        def go_up():
            parent = os.path.dirname(path_var["current"])
            if parent and parent != path_var["current"]:
                navigate(parent)

        ctk.CTkButton(navrow, text="↑", command=go_up, width=36, height=32,
                      fg_color=C_BTN, hover_color=C_BTN_HOV, text_color=C_ACCENT,
                      corner_radius=8, font=self._fnt(14)).pack(side="left", padx=(4, 6))
        ctk.CTkButton(navrow, text="▶ Play", command=lambda: on_select(path_var["current"]),
                      width=80, height=32, fg_color=C_ACCENT, hover_color="#a7f3b4",
                      text_color="#1a1d23", corner_radius=8, font=self._fnt(12)).pack(side="left")

        # OK / Abbrechen (unten — ERST packen damit sie IMMER sichtbar bleiben)
        btnrow = ctk.CTkFrame(dlg, fg_color="transparent")
        btnrow.pack(side="bottom", fill="x", pady=(0, 12))
        ctk.CTkButton(btnrow, text=S("cancel"), command=on_cancel, width=110, height=38,
                      fg_color=C_BTN, hover_color=C_BTN_HOV, text_color=C_TEXT,
                      corner_radius=10, font=self._fnt(12)).pack(side="right", padx=(6, 10))
        ctk.CTkButton(btnrow, text=S("ok"), command=lambda: on_select(path_var["current"]),
                      width=110, height=38, fg_color=C_ACCENT, hover_color="#a7f3b4",
                      text_color="#1a1d23", corner_radius=10, font=self._fnt(13)).pack(side="right")

        # Scrollbare Ordner-Liste (explizite Startbreite verhindert den 200px-CTk-Bug!)
        list_frame = ctk.CTkScrollableFrame(dlg, width=BASE_W - 40, fg_color=C_PANEL, corner_radius=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        def _count_tracks(folder_path, limit=500):
            """Zählt Audio-Dateien rekursiv. Stoppt bei `limit` → '500+'."""
            count = 0
            try:
                for _dp, _dn, fns in os.walk(folder_path):
                    for f in fns:
                        if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
                            count += 1
                            if count > limit:
                                return f"{limit}+"
            except (PermissionError, OSError):
                pass
            return str(count) if count > 0 else ""

        def navigate(folder):
            path_var["current"] = folder
            path_label.configure(text=folder)
            for w in list_frame.winfo_children():
                w.destroy()
            try:
                entries = sorted(
                    [e for e in os.listdir(folder)
                     if not e.startswith('.') and os.path.isdir(os.path.join(folder, e))],
                    key=natural_sort_key)
            except PermissionError:
                entries = []
            if not entries:
                ctk.CTkLabel(list_frame, text="— ∅ —", fg_color="transparent",
                             text_color=C_DIM, font=self._fnt(12)).pack(pady=20)
                return

            fnt = tkfont.Font(self.root, family=FONT, size=-int(round(12)), weight="bold")
            max_px = 0
            for name in entries:
                full = os.path.join(folder, name)
                count_str = _count_tracks(full)
                label = f"📁  {name}" + (f"   ({count_str})" if count_str else "")
                px = int(fnt.measure(label))
                if px > max_px:
                    max_px = px
                btn = ctk.CTkButton(list_frame, text=label, anchor="w",
                                    fg_color="transparent", hover_color=C_BTN_HOV,
                                    text_color=C_TEXT, font=self._fnt(12),
                                    height=34, corner_radius=6, border_width=0,
                                    command=lambda p=full: navigate(p))
                btn.pack(fill="x", padx=4, pady=1)

            try:
                list_frame._parent_canvas.yview_moveto(0)
            except Exception:
                pass

            # Dynamische Fensterbreite in BASIS-Pixeln (CTk skaliert geometry() selbst mit self.scale!)
            # 200px Puffer: 📁-Emoji(~30) + CTkButton-Pad(~60) + Scrollbar(~16) + Frame-Margins(~30) + Scale-Spielraum(~64)
            needed_base_w = min(950, max(BASE_W, int(max_px * self.scale) + 200))
            if needed_base_w != path_var["base_w"]:
                path_var["base_w"] = needed_base_w
                real_new_w = int(needed_base_w * self.scale)
                nx = max(10, min(sw - real_new_w - 20, dlg.winfo_x()))
                dlg.geometry(f"{needed_base_w}x{BASE_H}+{nx}+{dlg.winfo_y()}")

        # Initiale Ansicht
        navigate(path_var["current"])

        dlg.transient(self.root)
        dlg.grab_set()
        self.root.wait_window(dlg)

        # Ergebnis verarbeiten
        path = result.get("path")
        if not path:
            return
        self.load_folder(path, autoplay=True)

    def _show_track_list(self):
        """Klick auf Titel → breites Popup mit großer Schrift (alle Tracks im Ordner)."""
        if not self.playlist:
            self.status.configure(text=f"❌ {S('open_first')}")
            return

        dlg = ctk.CTkToplevel(self.root)
        dlg.title(f"📋  {self.folder_name} — {len(self.playlist)} Titel")
        dlg.configure(fg_color=C_BG)
        # Breite: Player-Breite (mindestens 390), Höhe: max. 70% Screenhöhe
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = max(self.WIDTH, int(sw * 0.45))
        h = min(600, int(sh * 0.7))
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + 80
        dlg.geometry(f"{w}x{h}+{max(0,x)}+{max(0,y)}")

        # Titelzeile im Popup
        ctk.CTkLabel(dlg, text=f"📁 {self.folder_name}", fg_color="transparent",
                     text_color=C_DIM, font=self._fnt(12, False), anchor="w").pack(fill="x", padx=16, pady=(10, 4))

        # Scrollbare Track-Liste (große Schrift für Touch!)
        list_frame = ctk.CTkScrollableFrame(dlg, fg_color=C_PANEL, corner_radius=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        for i, path in enumerate(self.playlist):
            base = os.path.splitext(os.path.basename(path))[0]
            is_current = (i == self.index)
            # Aktuelle Track: grün + fett; Rest: normal
            btn = ctk.CTkButton(
                list_frame, text=f"{'▶ ' if is_current else ''}{base}", anchor="w",
                fg_color=C_BTN_HOV if is_current else "transparent",
                hover_color=C_BTN_HOV,
                text_color=C_ACCENT if is_current else C_TEXT,
                font=self._fnt(14),
                height=42, corner_radius=8, border_width=0,
                command=lambda idx=i: (self.play_index(idx), dlg.destroy()))
            btn.pack(fill="x", padx=6, pady=1)

        # Schließen: Escape oder Klick außerhalb
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.transient(self.root)
        dlg.grab_set()
        # Auto-Scroll zum aktuellen Track (damit er sichtbar ist)
        try:
            list_frame.after(50, lambda: list_frame._parent_canvas.yview_moveto(
                max(0.0, self.index / max(1, len(self.playlist)))))
        except Exception:
            pass

    def load_folder(self, path, autoplay=False):
        files = scan_folder(path)
        if not files:
            self.status.configure(text=f"❌ {S('no_audio')}: {os.path.basename(path)}")
            return
        self.playlist = files
        self.current_folder = path
        self.folder_name = os.path.basename(os.path.normpath(path))
        # Resume: letzter Titel in der Playlist gefunden? → dorthin springen
        if self._resume_track and self._resume_track in files:
            self.index = files.index(self._resume_track)
        else:
            self.index = 0
        base = os.path.splitext(os.path.basename(files[self.index]))[0]
        track_info = S("tracks_in").format(n=len(files), folder=self.folder_name)
        self.track.configure(text=f"{base}  ·  {track_info}")
        self.status.configure(text=f"✅ {S('ready')}")

        self._save_config()
        if autoplay:
            self.play_index(0)

    def play_index(self, i):
        i = max(0, min(len(self.playlist) - 1, i))
        self.index = i
        path = self.playlist[i]
        base = os.path.splitext(os.path.basename(path))[0]
        # Resume: erster Play dieser Session + exakt der gemerkte Titel → Position fortsetzen
        start_pos = 0.0
        if not self._resumed and path == self._resume_track and self._resume_pos > 1.0:
            dur = probe_duration(path)
            if dur and self._resume_pos < dur * 0.9:   # >90 % → von vorn
                start_pos = self._resume_pos
        self._resumed = True   # egal ob genutzt oder nicht — nur einmal pro Session
        try:
            self.engine.play(path, start=start_pos)
        except Exception as exc:
            self.status.configure(text=f"❌ {S('error')}: {exc}")
            return
        self.track.configure(text=base)
        self.status.configure(text=f"▶ {len(self.playlist)} 🎵")
        self.sync_play_button()

    def toggle(self):
        if not self.engine.active:
            if not self.playlist:
                self.status.configure(text=f"❌ {S('open_first')}")
                return
            self.play_index(self.index if self.index >= 0 else 0)
        elif self.engine.paused:
            self.engine.resume()
            base = os.path.splitext(os.path.basename(self.playlist[self.index]))[0]
            self.track.configure(text=base)
            self.status.configure(text=f"▶ {S('ready')}")
        else:
            self.engine.pause()
            self.status.configure(text=f"⏸ {S('pause')}")
        self.sync_play_button()

    def next(self):
        if not self.playlist:
            return
        self.play_index((self.index + 1) % len(self.playlist))

    def prev(self):
        if not self.playlist:
            return
        self.play_index((self.index - 1) % len(self.playlist))

    def auto_next(self):
        """Nächster Titel — respektiert Shuffle & Repeat-Modus."""
        if not self.playlist:
            return
        # Repeat One: denselben Track von vorn
        if self.repeat_mode == 2:
            self.play_index(self.index)
            return
        # Shuffle: zufälliger Titel (nicht den aktuellen, wenn Playlist >1)
        if self.shuffle_enabled and len(self.playlist) > 1:
            new_idx = random.choice([i for i in range(len(self.playlist)) if i != self.index])
            self.play_index(new_idx)
            return
        # Normal / Repeat All: nächster in Reihenfolge (bei all → Loop)
        next_idx = (self.index + 1) % len(self.playlist)
        # Repeat Off + letzter Track erreicht → stoppen
        if self.repeat_mode == 0 and next_idx == 0 and self.index == len(self.playlist) - 1:
            try:
                self.engine.stop()
            except Exception:
                pass
            self.sync_play_button()
            return
        self.play_index(next_idx)

    # ----------------------------- Slider ---------------------------------
    def on_volume(self, value):
        self.volume = int(round(float(value)))
        try:
            self.engine.set_volume(self.volume / 100.0)
        except Exception:
            pass
        self.volval.configure(text=f"{self.volume}%")

    def bump_volume(self, delta):
        self.on_volume(max(0, min(100, self.volume + delta)))
        try:
            self.vol.set(self.volume)
        except Exception:
            pass

    # ----------------------------- Shuffle & Repeat (v1.2) -----------------
    def toggle_shuffle(self):
        self.shuffle_enabled = not self.shuffle_enabled
        img = self.img_shuffle_on if self.shuffle_enabled else self.img_shuffle_off
        try:
            self.btn_shuffle.configure(image=img)
        except Exception:
            pass
        self._save_config()

    def cycle_repeat(self):
        """Zyklus: off → all → one → off …"""
        self.repeat_mode = (self.repeat_mode + 1) % 3
        try:
            self.btn_repeat.configure(image=self._repeat_icon())
        except Exception:
            pass
        self._save_config()

    def _repeat_icon(self):
        if self.repeat_mode == 1:
            return self.img_repeat_all
        elif self.repeat_mode == 2:
            return self.img_repeat_one
        return self.img_repeat_off

    def on_seek_release(self, _event=None):
        self.dragging_seek = False
        dur = self.engine.duration or 0
        if not self.engine.active or dur <= 0:
            return
        sec = (float(self.seek.get()) / 100.0) * dur
        try:
            self.engine.seek(sec)
        except Exception as exc:
            self.status.configure(text=f"❌ {S('error')} (seek)")

    # ----------------------------- Sync & Poll ----------------------------
    def sync_play_button(self):
        if not self.engine.active or self.engine.paused:
            img = self.img_play      # bereit / pausiert -> Play anzeigen
        else:
            img = self.img_pause     # läuft -> Pause anzeigen
        try:
            self.btn_play.configure(image=img)
        except Exception:
            pass

    def _poll(self):
        # Ereignisse aus der Engine abarbeiten
        try:
            while True:
                ev = self.engine.events.get_nowait()
                if ev == "ended":
                    self.auto_next()
                elif ev == "error":
                    self.engine.stop()
                    self.status.configure(text=f"❌ {S('error')}")
        except queue.Empty:
            pass

        # Position / Dauer anzeigen
        pos = self.engine.get_position() if self.engine.active else 0.0
        dur = self.engine.duration or 0
        if not self.dragging_seek and self.engine.active:
            frac = (pos / dur * 100) if dur > 0 else 0
            try:
                self.seek.set(frac)
            except Exception:
                pass
        self.time.configure(text=f"{fmt_time(pos)} / {fmt_time(dur)}")

        # Play-Button-Label aktuell halten (z.B. nach Auto-Nächste)
        self.sync_play_button()

        self.root.after(200, self._poll)

    def on_close(self):
        # WICHTIG: Position + Track festhalten BEVOR Engine gestoppt wird!
        if self.engine.active and self.playlist and 0 <= self.index < len(self.playlist):
            self._resume_pos = round(self.engine.get_position(), 2)
            self._resume_track = self.playlist[self.index]
        try:
            self.engine.stop()
        except Exception:
            pass
        self._save_config()
        self.root.destroy()


def main():
    # className -> WM_CLASS (Name im Dock/Taskleiste). Standard waere "Tk".
    # Wichtig: einfaches Token ohne interne Grossbuchstaben!
    # "mtp" => WM_CLASS: "mtp", "Mtp"  →  .desktop: StartupWMClass=mtp ✅
    root = ctk.CTk(className="mtp")                  # => WM_CLASS: mtp / Mtp
    MusicPlayer(root)

    # GNOME (XWayland): Fenster geht ueber WM_CLASS <-> StartupWMClass in das Dock-Icon auf.

    # (Kein ctypes/_GTK_APPLICATION_ID-Hack mehr: crashte unter XWayland mit BadWindow.)

    root.mainloop()


if __name__ == "__main__":
    main()
