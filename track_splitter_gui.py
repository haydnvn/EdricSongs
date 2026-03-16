#!/usr/bin/env python3
"""
Track Splitter GUI
Select your MP3, album cover, paste timestamps, hit go.
Requires ffmpeg to be installed and on PATH.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import re
import subprocess
import sys
import os
import zipfile
import threading
from pathlib import Path

# Suppress CMD window popups on Windows for every ffmpeg call
_NO_WINDOW = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def resource_path(filename):
    """Resolve a bundled resource path — works both as a script and PyInstaller onefile exe."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).parent / filename

# ---------------------------------------------------------------------------
# Dark theme palette
# ---------------------------------------------------------------------------

BG       = "#1e1e1e"   # window / frame background
SURFACE  = "#252526"   # raised surfaces (labelframes)
INPUT_BG = "#2d2d2d"   # text inputs / listbox
FG       = "#d4d4d4"   # primary text
FG_MUTED = "#6e6e6e"   # hints, labels, borders
ACCENT   = "#4dabf7"   # blue accent (progress, selection, go button)
SUCCESS  = "#51cf66"   # track count success green
ERROR    = "#ff6b6b"   # error red
BORDER   = "#3a3a3a"   # widget borders
BTN_BG   = "#2f2f2f"   # regular button bg
BTN_HOV  = "#3e3e3e"   # regular button hover

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def parse_timestamp(ts_str):
    ts_str = ts_str.strip()
    parts = ts_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return None


def secs_to_str(secs):
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


_TS = r"\d{1,2}:\d{2}(?::\d{2})?"


def parse_timestamps_text(text):
    tracks = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^\d{1,3}[.)]\s*", "", line)

        # Format A: "Name  start - end"
        m = re.match(rf"^(.+?)\s+({_TS})\s*[-–]\s*{_TS}\s*$", line)
        if m:
            secs = parse_timestamp(m.group(2))
            name = m.group(1).strip()
            if secs is not None and name:
                tracks.append((secs, name))
                continue

        # Format B: "Name  start"  (single timestamp at end)
        m = re.match(rf"^(.+?)\s+({_TS})\s*$", line)
        if m:
            candidate = m.group(1).strip()
            if not re.fullmatch(_TS, candidate):
                secs = parse_timestamp(m.group(2))
                if secs is not None and candidate:
                    tracks.append((secs, candidate))
                    continue

        # Format C: timestamp at start "[0:00]", "(0:00)", or bare "0:00"
        m = re.match(rf"^[\[(]?({_TS})[\])]?\s*[-–]?\s*(.+)$", line)
        if m:
            secs = parse_timestamp(m.group(1))
            name = re.sub(rf"\s*[-–]\s*{_TS}\s*$", "", m.group(2)).strip()
            if secs is not None and name:
                tracks.append((secs, name))
                continue

    seen, unique = set(), []
    for secs, name in sorted(tracks, key=lambda x: x[0]):
        if secs not in seen:
            seen.add(secs)
            unique.append((secs, name))
    return unique


def sanitize_filename(name):
    for ch in r'<>:"/\|?*':
        name = name.replace(ch, "_")
    return name.strip(" .")[:200]


def get_audio_duration(filepath):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", filepath]
    result = subprocess.run(cmd, capture_output=True, text=True, **_NO_WINDOW)
    return float(result.stdout.strip())


def ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, **_NO_WINDOW)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def extract_track(mp3, cover, output_path, start, duration, title, track_num, album, artist):
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", mp3]
    if cover and os.path.exists(cover):
        cmd += ["-i", cover, "-map", "0:a", "-map", "1:v",
                "-c:v", "png", "-disposition:v", "attached_pic",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)"]
    else:
        cmd += ["-map", "0:a"]
    cmd += ["-c:a", "libmp3lame", "-q:a", "0", "-id3v2_version", "3",
            "-metadata", f"title={title}", "-metadata", f"track={track_num}"]
    if album:
        cmd += ["-metadata", f"album={album}"]
    if artist:
        cmd += ["-metadata", f"artist={artist}"]
    cmd.append(output_path)
    return subprocess.run(cmd, capture_output=True, **_NO_WINDOW)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        # Crisp rendering on high-DPI screens
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.title("Track Splitter")
        self.geometry("800x960")
        self.minsize(660, 800)
        self.configure(bg=BG)

        self._apply_theme()
        self._build()

        # Window icon — resource_path works both as script and PyInstaller onefile exe
        try:
            icon_path = resource_path("icon.png")
            if icon_path.exists():
                self._icon_img = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(False, self._icon_img)
        except Exception:
            pass

        if not ffmpeg_available():
            self.after(400, self._ffmpeg_warning)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure(".",
            background=BG, foreground=FG,
            font=("Segoe UI", 10),
            bordercolor=BORDER,
            focuscolor=ACCENT,
            troughcolor=INPUT_BG,
            selectbackground=ACCENT,
            selectforeground="#000000",
        )

        s.configure("TFrame", background=BG)

        s.configure("TLabel", background=BG, foreground=FG, padding=0)

        s.configure("Muted.TLabel", background=BG, foreground=FG_MUTED,
                    font=("Segoe UI", 9))

        s.configure("TLabelframe",
            background=SURFACE,
            bordercolor=BORDER,
            relief="flat",
            padding=(10, 8),
        )
        s.configure("TLabelframe.Label",
            background=SURFACE,
            foreground=FG_MUTED,
            font=("Segoe UI", 9),
        )

        s.configure("TEntry",
            fieldbackground=INPUT_BG,
            foreground=FG,
            insertcolor=FG,
            bordercolor=BORDER,
            relief="flat",
            padding=4,
        )
        s.map("TEntry",
            fieldbackground=[("readonly", SURFACE)],
            bordercolor=[("focus", ACCENT)],
        )

        s.configure("TButton",
            background=BTN_BG,
            foreground=FG,
            bordercolor=BORDER,
            relief="flat",
            padding=(8, 4),
        )
        s.map("TButton",
            background=[("active", BTN_HOV), ("pressed", "#4a4a4a")],
            foreground=[("disabled", FG_MUTED)],
        )

        s.configure("Go.TButton",
            background=ACCENT,
            foreground="#0a0a0a",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            padding=(12, 6),
        )
        s.map("Go.TButton",
            background=[("active", "#74c0fc"), ("pressed", "#339af0"),
                        ("disabled", BTN_BG)],
            foreground=[("disabled", FG_MUTED)],
        )

        s.configure("Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor=INPUT_BG,
            bordercolor=BG,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=6,
        )

        s.configure("TScrollbar",
            background=BORDER,
            troughcolor=SURFACE,
            bordercolor=SURFACE,
            arrowcolor=FG_MUTED,
            relief="flat",
        )
        s.map("TScrollbar",
            background=[("active", FG_MUTED)],
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build(self):
        main = ttk.Frame(self, padding=(16, 12))
        main.pack(fill=tk.BOTH, expand=True)

        # Title row
        row = ttk.Frame(main)
        row.pack(fill=tk.X, pady=(0, 14))
        tk.Label(row, text="Track Splitter",
                 font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=FG).pack(side=tk.LEFT)
        tk.Label(row, text="Made by Hxydn",
                 bg=BG, fg=FG_MUTED, font=("Segoe UI", 9)).pack(side=tk.RIGHT, padx=(4, 0))
        self._ffmpeg_lbl = tk.Label(row, text="", font=("Segoe UI", 9),
                                    bg=BG, fg=ERROR)
        self._ffmpeg_lbl.pack(side=tk.RIGHT, padx=4)

        # Files
        ff = ttk.LabelFrame(main, text="  Files")
        ff.pack(fill=tk.X, pady=(0, 10))
        ff.columnconfigure(1, weight=1)
        self.mp3_var   = tk.StringVar()
        self.cover_var = tk.StringVar()
        self.out_var   = tk.StringVar()
        self._file_row(ff, 0, "MP3 File:",      self.mp3_var,   self._browse_mp3)
        self._file_row(ff, 1, "Album Cover:",   self.cover_var, self._browse_cover, tip="optional")
        self._file_row(ff, 2, "Output Folder:", self.out_var,   self._browse_out, folder=True)

        # Album info
        mf = ttk.LabelFrame(main, text="  Album Info")
        mf.pack(fill=tk.X, pady=(0, 10))
        mf.columnconfigure(1, weight=1)
        mf.columnconfigure(3, weight=1)
        tk.Label(mf, text="Album Name:", bg=SURFACE, fg=FG,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.album_var = tk.StringVar()
        ttk.Entry(mf, textvariable=self.album_var).grid(
            row=0, column=1, sticky="ew", padx=(0, 16))
        tk.Label(mf, text="Artist:", bg=SURFACE, fg=FG,
                 font=("Segoe UI", 10)).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.artist_var = tk.StringVar()
        ttk.Entry(mf, textvariable=self.artist_var).grid(row=0, column=3, sticky="ew")

        # Timestamps
        tf = ttk.LabelFrame(main, text="  Timestamps")
        tf.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        tf.rowconfigure(1, weight=1)
        tf.columnconfigure(0, weight=1)

        hint = ("Paste tracklist — all common formats work:\n"
                "  Artist - Title  0:00 - 2:55     |     0:00  Artist - Title\n"
                "  [0:00] Track Name                |     1. 0:00 Track Name")
        tk.Label(tf, text=hint, bg=SURFACE, fg=FG_MUTED,
                 font=("Segoe UI", 9), justify=tk.LEFT).grid(
            row=0, column=0, sticky="w", pady=(0, 6))

        self.ts_box = tk.Text(
            tf, height=9, font=("Consolas", 10), undo=True,
            bg=INPUT_BG, fg=FG, insertbackground=FG,
            selectbackground=ACCENT, selectforeground="#000",
            relief=tk.FLAT, borderwidth=0, padx=6, pady=4)
        ts_scroll = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.ts_box.yview)
        self.ts_box.configure(yscrollcommand=ts_scroll.set)
        self.ts_box.grid(row=1, column=0, sticky="nsew")
        ts_scroll.grid(row=1, column=1, sticky="ns")

        ttk.Button(tf, text="Parse & Preview  ▶",
                   command=self._parse_preview).grid(
            row=2, column=0, sticky="w", pady=(10, 2))

        # Preview list
        pf = ttk.LabelFrame(main, text="  Parsed Tracks")
        pf.pack(fill=tk.X, pady=(0, 10))
        pf.columnconfigure(0, weight=1)

        self.track_count_lbl = tk.Label(
            pf, text="No tracks parsed yet.",
            bg=SURFACE, fg=FG_MUTED, font=("Segoe UI", 9))
        self.track_count_lbl.grid(row=0, column=0, sticky="w", pady=(0, 6))

        lf2 = tk.Frame(pf, bg=SURFACE)
        lf2.grid(row=1, column=0, sticky="ew")
        lf2.columnconfigure(0, weight=1)
        self.preview_lb = tk.Listbox(
            lf2, height=6, font=("Consolas", 9),
            bg=INPUT_BG, fg=FG, activestyle="none",
            selectbackground=ACCENT, selectforeground="#000",
            relief=tk.FLAT, borderwidth=0, highlightthickness=0)
        lb_scroll = ttk.Scrollbar(lf2, orient=tk.VERTICAL, command=self.preview_lb.yview)
        self.preview_lb.configure(yscrollcommand=lb_scroll.set)
        self.preview_lb.grid(row=0, column=0, sticky="ew")
        lb_scroll.grid(row=0, column=1, sticky="ns")

        # Progress
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            main, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 3))

        # Status
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(main, textvariable=self.status_var,
                 bg=BG, fg=FG_MUTED, font=("Segoe UI", 9)).pack(anchor="w")

        # Log
        log_frame = ttk.LabelFrame(main, text="  Log")
        log_frame.pack(fill=tk.X, pady=(6, 8))
        self.log_box = tk.Text(
            log_frame, height=4, font=("Consolas", 9), state="disabled",
            bg=INPUT_BG, fg=FG, insertbackground=FG,
            relief=tk.FLAT, borderwidth=0, padx=6, pady=4)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=log_scroll.set)
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Go button
        self.go_btn = ttk.Button(
            main, text="Split Tracks & Create ZIP",
            style="Go.TButton", command=self._run)
        self.go_btn.pack(fill=tk.X, ipady=8)

    def _file_row(self, parent, row, label, var, cmd, tip="", folder=False):
        tk.Label(parent, text=label, bg=SURFACE, fg=FG,
                 font=("Segoe UI", 10)).grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        inner = tk.Frame(parent, bg=SURFACE)
        inner.grid(row=row, column=1, sticky="ew", padx=(0, 8))
        inner.columnconfigure(0, weight=1)
        ttk.Entry(inner, textvariable=var).grid(row=0, column=0, sticky="ew")
        if tip:
            tk.Label(inner, text=f"({tip})", bg=SURFACE, fg=FG_MUTED,
                     font=("Segoe UI", 8)).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(parent, text="Browse…", command=cmd).grid(row=row, column=2)

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------

    def _browse_mp3(self):
        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[("Audio files", "*.mp3 *.m4a *.wav *.flac *.aac"),
                       ("All files", "*.*")])
        if not path:
            return
        self.mp3_var.set(path)
        if not self.album_var.get():
            self.album_var.set(Path(path).stem)
        if not self.out_var.get():
            self.out_var.set(str(Path(path).parent / "tracks"))

    def _browse_cover(self):
        path = filedialog.askopenfilename(
            title="Select album cover",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                       ("All files", "*.*")])
        if path:
            self.cover_var.set(path)

    def _browse_out(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.out_var.set(path)

    # ------------------------------------------------------------------
    # Parse & preview
    # ------------------------------------------------------------------

    def _parse_preview(self):
        tracks = parse_timestamps_text(self.ts_box.get("1.0", tk.END))
        self.preview_lb.delete(0, tk.END)
        if not tracks:
            self.preview_lb.insert(tk.END,
                "  No tracks found — check your timestamp format above.")
            self.track_count_lbl.config(text="0 tracks found.", fg=ERROR)
            return
        for i, (secs, name) in enumerate(tracks):
            self.preview_lb.insert(
                tk.END, f"  {i+1:02d}.  [{secs_to_str(secs):>8}]  {name}")
        self.track_count_lbl.config(
            text=f"{len(tracks)} tracks found.", fg=SUCCESS)
        self._log(f"Parsed {len(tracks)} tracks.")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _run(self):
        mp3    = self.mp3_var.get().strip()
        cover  = self.cover_var.get().strip()
        out    = self.out_var.get().strip()
        album  = self.album_var.get().strip()
        artist = self.artist_var.get().strip()

        if not mp3 or not os.path.isfile(mp3):
            messagebox.showerror("Missing file", "Please select a valid audio file.")
            return
        if not out:
            messagebox.showerror("Missing folder", "Please select an output folder.")
            return
        if cover and not os.path.isfile(cover):
            messagebox.showerror("Missing file",
                "Album cover path is set but the file was not found.")
            return

        tracks = parse_timestamps_text(self.ts_box.get("1.0", tk.END))
        if not tracks:
            messagebox.showerror("No tracks",
                "No timestamps found.\nPaste your tracklist and click Parse & Preview first.")
            return
        if not ffmpeg_available():
            self._ffmpeg_warning()
            return

        self.go_btn.config(state="disabled")
        self.progress_var.set(0)
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")

        threading.Thread(
            target=self._process,
            args=(mp3, cover, out, album, artist, tracks),
            daemon=True,
        ).start()

    def _process(self, mp3, cover, out, album, artist, tracks):
        try:
            os.makedirs(out, exist_ok=True)
            self._log(f"Input : {Path(mp3).name}")
            self._log(f"Cover : {Path(cover).name if cover else '(none)'}")
            self._log(f"Output: {out}")
            self._log(f"Tracks: {len(tracks)}")
            self._log("─" * 48)

            self._status("Getting audio duration…")
            total = get_audio_duration(mp3)
            self._log(f"Duration: {secs_to_str(total)}")

            errors = []
            for i, (start, name) in enumerate(tracks):
                dur = (tracks[i+1][0] - start) if i < len(tracks)-1 else (total - start)
                safe = sanitize_filename(name)
                out_path = os.path.join(out, f"{i+1:02d} - {safe}.mp3")
                short = name[:55] if len(name) <= 55 else name[:52] + "…"

                self._log(f"  [{i+1:02d}/{len(tracks)}] {short}")
                self._status(f"Extracting {i+1}/{len(tracks)}: {short}")
                self._progress((i / len(tracks)) * 88)

                res = extract_track(mp3, cover, out_path, start, dur,
                                    name, i+1, album, artist)
                if res.returncode != 0:
                    errors.append(name)
                    self._log("         ⚠ ffmpeg error on this track")

            self._status("Creating ZIP…")
            self._log("─" * 48)
            self._log("Zipping…")
            self._progress(93)

            zip_name = sanitize_filename(album or Path(mp3).stem) + ".zip"
            zip_path = os.path.join(str(Path(out).parent), zip_name)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in sorted(f for f in os.listdir(out) if f.lower().endswith(".mp3")):
                    zf.write(os.path.join(out, fname), fname)

            self._progress(100)
            self._status(f"Done!  →  {zip_path}")
            self._log(f"ZIP: {zip_path}")
            if errors:
                self._log(f"⚠ {len(errors)} track(s) had errors.")

            msg = f"Done! {len(tracks)} tracks extracted.\n\nZIP:\n{zip_path}"
            if errors:
                msg += f"\n\n⚠ {len(errors)} track(s) had ffmpeg errors."
            self.after(0, lambda: messagebox.showinfo("Done!", msg))
            self.after(0, lambda: self._prompt_open(out))

        except Exception as exc:
            self._log(f"\nERROR: {exc}")
            self.after(0, lambda: messagebox.showerror("Error", str(exc)))
            self._status("Error — see log.")
        finally:
            self.after(0, lambda: self.go_btn.config(state="normal"))

    def _prompt_open(self, folder):
        if messagebox.askyesno("Open folder?", "Open the output folder?"):
            os.startfile(folder)

    # ------------------------------------------------------------------
    # Thread-safe helpers
    # ------------------------------------------------------------------

    def _log(self, msg):
        def _do():
            self.log_box.config(state="normal")
            self.log_box.insert(tk.END, msg + "\n")
            self.log_box.see(tk.END)
            self.log_box.config(state="disabled")
        self.after(0, _do)

    def _status(self, msg):
        self.after(0, lambda: self.status_var.set(msg))

    def _progress(self, pct):
        self.after(0, lambda: self.progress_var.set(pct))

    # ------------------------------------------------------------------
    # FFmpeg warning
    # ------------------------------------------------------------------

    def _ffmpeg_warning(self):
        self._ffmpeg_lbl.config(text="⚠  ffmpeg not found")
        messagebox.showerror(
            "FFmpeg Not Found",
            "FFmpeg was not found on this computer.\n\n"
            "Track Splitter needs FFmpeg to work.\n\n"
            "How to install:\n"
            "  1. Go to  https://ffmpeg.org/download.html\n"
            "  2. Download a Windows build (e.g. from gyan.dev)\n"
            "  3. Extract it and add the bin\\ folder to your PATH\n\n"
            "Restart Track Splitter after installing.",
        )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
