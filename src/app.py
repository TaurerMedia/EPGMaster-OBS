"""
EPGMaster — OBS EPG Converter
https://epgmaster.io

Reads OBS scene collection JSON, extracts VLC/Media playlists,
measures durations via ffprobe, exports EPG JSON for EPGMaster.
"""

import json
import os
import platform
import shutil
import ssl
import stat
import subprocess
import sys
import tarfile
import threading
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ─────────────────────────────────────────────────────────────────────────────
#  SSL fix — macOS Python не имеет системных сертификатов
# ─────────────────────────────────────────────────────────────────────────────

def _make_ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

_SSL = _make_ssl_context()

def _urlretrieve(url: str, dest: Path, progress=None):
    """SSL-safe download with progress callback(done_bytes, total_bytes)."""
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_SSL))
    with opener.open(url) as r:
        total = int(r.headers.get("Content-Length", 0))
        done  = 0
        with open(dest, "wb") as f:
            while chunk := r.read(65536):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)

# ─────────────────────────────────────────────────────────────────────────────
#  Design System — EPGMaster
# ─────────────────────────────────────────────────────────────────────────────

DS = {
    "bg":          "#FFFFFF",
    "fg":          "#1F1F2E",
    "primary":     "#0040FF",
    "primary_hov": "#0033CC",
    "primary_lt":  "#EEF0FF",
    "secondary":   "#F5F6F8",
    "muted_fg":    "#73778C",
    "border":      "#E5E7EB",
    "card":        "#FFFFFF",
    "success":     "#22C55E",
    "error":       "#DC2626",
    "warning":     "#F59E0B",
}

SYS = platform.system()

# Montserrat недоступен в tkinter напрямую — используем ближайший системный
# (tkinter грузит только установленные шрифты, Montserrat нужно ставить отдельно)
_FONT = "Montserrat" if SYS == "Darwin" else ("Segoe UI" if SYS == "Windows" else "DejaVu Sans")

def font(size=11, weight="normal"):
    return (_FONT, size, weight)

# ─────────────────────────────────────────────────────────────────────────────
#  ffprobe — поиск и авто-загрузка
# ─────────────────────────────────────────────────────────────────────────────

APP_DIR     = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent.parent
FFPROBE_DIR = APP_DIR / ".ffprobe"

_FFPROBE_BUILDS = {
    ("Windows", "x86_64"): {
        "url":  "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "name": "ffprobe.exe",
        "type": "zip",
    },
    ("Darwin", "x86_64"): {
        "url":  "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
        "name": "ffprobe",
        "type": "zip",
    },
    ("Darwin", "arm64"): {
        "url":  "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
        "name": "ffprobe",
        "type": "zip",
    },
    ("Linux", "x86_64"): {
        "url":  "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
        "name": "ffprobe",
        "type": "tar",
    },
}

def _platform_key():
    system  = platform.system()
    machine = platform.machine().lower()
    machine = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    return system, machine

def find_ffprobe() -> Path | None:
    system, _ = _platform_key()
    local = FFPROBE_DIR / ("ffprobe.exe" if system == "Windows" else "ffprobe")
    if local.exists():
        return local
    found = shutil.which("ffprobe")
    return Path(found) if found else None

def download_ffprobe(progress=None) -> Path:
    key  = _platform_key()
    info = _FFPROBE_BUILDS.get(key)
    if not info:
        raise RuntimeError(f"Нет сборки ffprobe для {key[0]} {key[1]}")

    FFPROBE_DIR.mkdir(parents=True, exist_ok=True)
    ext     = ".zip" if info["type"] == "zip" else ".tar.xz"
    archive = FFPROBE_DIR / f"_download{ext}"
    dest    = FFPROBE_DIR / info["name"]

    _urlretrieve(info["url"], archive, progress)

    if info["type"] == "zip":
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            match = next((n for n in names if n.endswith("/" + info["name"]) or n == info["name"]), None)
            if not match:
                raise RuntimeError(f"ffprobe не найден в архиве.\nФайлы: {names[:6]}")
            with zf.open(match) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    else:
        with tarfile.open(archive) as tf:
            members = tf.getmembers()
            match   = next((m for m in members if m.name.endswith("/" + info["name"])), None)
            if not match:
                raise RuntimeError("ffprobe не найден в tar-архиве.")
            with tf.extractfile(match) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)

    archive.unlink(missing_ok=True)

    if key[0] != "Windows":
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return dest

# ─────────────────────────────────────────────────────────────────────────────
#  EPG — логика
# ─────────────────────────────────────────────────────────────────────────────

def get_duration(ffprobe: Path, filepath: str) -> float | None:
    try:
        raw = subprocess.check_output(
            [str(ffprobe), "-v", "quiet", "-show_format", "-print_format", "json", filepath],
            stderr=subprocess.DEVNULL, timeout=30,
        )
        return float(json.loads(raw)["format"]["duration"])
    except Exception:
        return None

def clean_title(path: str) -> str:
    name = Path(path).stem
    for ch in ("_", "-", "."):
        name = name.replace(ch, " ")
    return " ".join(name.split())

def parse_obs_json(path: str) -> dict[str, list[str]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    sources: dict[str, list[str]] = {}
    for src in data.get("sources", []):
        sid, cfg = src.get("id", ""), src.get("settings", {})
        files: list[str] = []
        if sid == "vlc_source":
            files = [i["value"] for i in cfg.get("playlist", []) if i.get("value")]
        elif sid == "ffmpeg_source":
            if v := cfg.get("local_file", ""):
                files = [v]
        if files:
            sources[src.get("name", "Unnamed")] = files

    scenes: dict[str, list[str]] = {}
    for src in data.get("sources", []):
        if src.get("id") not in ("scene", "group"):
            continue
        collected = []
        for item in src.get("settings", {}).get("items", []):
            if item.get("name") in sources:
                collected.extend(sources[item["name"]])
        if collected:
            scenes[src.get("name", "Scene")] = collected

    return scenes if scenes else sources

def build_epg(files: list, start: datetime, ffprobe: Path, on_progress=None) -> list:
    result, t = [], start
    for i, path in enumerate(files):
        if on_progress:
            on_progress(i + 1, len(files), path)
        dur = get_duration(ffprobe, path)
        if dur is None:
            continue
        end = t + timedelta(seconds=dur)
        result.append({
            "title":    clean_title(path),
            "start":    t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end":      end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration": max(1, round(dur / 60)),
        })
        t = end
    return result

# ─────────────────────────────────────────────────────────────────────────────
#  Widgets — переиспользуемые компоненты
# ─────────────────────────────────────────────────────────────────────────────

class PrimaryButton(tk.Button):
    def __init__(self, parent, text, command, **kw):
        super().__init__(parent, text=text, command=command,
            bg=DS["primary"], fg="#FFFFFF",
            activebackground=DS["primary_hov"], activeforeground="#FFFFFF",
            relief="flat", bd=0, cursor="hand2",
            font=font(11, "bold"), padx=20, pady=10, **kw)
        self.bind("<Enter>", lambda _: self.config(bg=DS["primary_hov"]))
        self.bind("<Leave>", lambda _: self.config(bg=DS["primary"]))

class OutlineButton(tk.Button):
    def __init__(self, parent, text, command, **kw):
        super().__init__(parent, text=text, command=command,
            bg=DS["bg"], fg=DS["primary"],
            activebackground=DS["primary_lt"], activeforeground=DS["primary"],
            relief="flat", bd=0, cursor="hand2",
            highlightthickness=1, highlightbackground=DS["border"],
            font=font(10), padx=12, pady=7, **kw)

class Card(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent,
            bg=DS["card"],
            highlightthickness=1,
            highlightbackground=DS["border"],
            **kw)

class SectionLabel(tk.Label):
    def __init__(self, parent, text, **kw):
        super().__init__(parent, text=text,
            bg=DS["card"], fg=DS["primary"],
            font=font(12, "bold"), **kw)

class HintLabel(tk.Label):
    def __init__(self, parent, text, **kw):
        super().__init__(parent, text=text,
            bg=DS["card"], fg=DS["muted_fg"],
            font=font(9), **kw)

class InputField(tk.Frame):
    """Entry с бордером в стиле EPGMaster."""
    def __init__(self, parent, textvariable, width=34, **kw):
        super().__init__(parent,
            bg=DS["border"], padx=1, pady=1)
        inner = tk.Frame(self, bg=DS["secondary"])
        inner.pack(fill="both")
        self.entry = tk.Entry(inner,
            textvariable=textvariable,
            bg=DS["secondary"], fg=DS["fg"],
            insertbackground=DS["primary"],
            relief="flat", bd=0,
            font=font(11), width=width)
        self.entry.pack(padx=10, pady=8)

# ─────────────────────────────────────────────────────────────────────────────
#  Download Dialog
# ─────────────────────────────────────────────────────────────────────────────

class DownloadDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Загрузка ffprobe")
        self.configure(bg=DS["bg"])
        self.resizable(False, False)
        self.grab_set()

        # header stripe
        tk.Frame(self, bg=DS["primary"], height=4).pack(fill="x")

        body = tk.Frame(self, bg=DS["bg"], padx=36, pady=28)
        body.pack()

        tk.Label(body, text="Скачиваю ffprobe…",
                 bg=DS["bg"], fg=DS["fg"],
                 font=font(15, "bold")).pack(anchor="w")

        tk.Label(body, text="Потребуется только один раз",
                 bg=DS["bg"], fg=DS["muted_fg"],
                 font=font(10)).pack(anchor="w", pady=(2, 16))

        self.sub = tk.Label(body, text="Подключаюсь…",
                            bg=DS["bg"], fg=DS["muted_fg"], font=font(10))
        self.sub.pack(anchor="w")

        s = ttk.Style()
        s.configure("DL.Horizontal.TProgressbar",
                    troughcolor=DS["secondary"],
                    background=DS["primary"],
                    bordercolor=DS["border"],
                    thickness=8)

        self.bar = tk.DoubleVar()
        ttk.Progressbar(body, variable=self.bar, maximum=100,
                        length=380, style="DL.Horizontal.TProgressbar"
                        ).pack(pady=(8, 6))

        self.pct_lbl = tk.Label(body, text="0%",
                                bg=DS["bg"], fg=DS["primary"],
                                font=font(11, "bold"))
        self.pct_lbl.pack(anchor="e")

        self.result: Path | None = None
        self.error:  str  | None = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        def cb(done, total):
            if total > 0:
                pct = min(done / total * 100, 100)
                self.bar.set(pct)
                self.sub.config(text=f"{done/1_048_576:.1f} МБ из {total/1_048_576:.1f} МБ")
                self.pct_lbl.config(text=f"{pct:.0f}%")
                self.update_idletasks()
        try:
            self.result = download_ffprobe(progress=cb)
        except Exception as e:
            self.error = str(e)
        finally:
            self.grab_release()
            self.destroy()

# ─────────────────────────────────────────────────────────────────────────────
#  Main Application Window
# ─────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OBS EPG Converter — EPGMaster")
        self.configure(bg=DS["bg"])
        self.resizable(False, False)

        self.obs_path  = tk.StringVar()
        self.scene_var = tk.StringVar()
        self.date_var  = tk.StringVar(value=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        self.time_var  = tk.StringVar(value="07:00")
        self.scenes:   dict[str, list[str]] = {}
        self.ffprobe:  Path | None = find_ffprobe()

        self._setup_style()
        self._build_header()
        self._build_body()
        self._build_footer()

        if not self.ffprobe:
            self.after(300, self._offer_download)
        else:
            self._set_ffprobe_status(ok=True)

    # ── Style ─────────────────────────────────────────────────────────────────

    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TCombobox",
            fieldbackground=DS["secondary"], background=DS["secondary"],
            foreground=DS["fg"], bordercolor=DS["border"],
            arrowcolor=DS["primary"], selectbackground=DS["secondary"],
            selectforeground=DS["fg"], padding=(10, 8),
        )
        s.map("TCombobox",
            fieldbackground=[("readonly", DS["secondary"])],
            selectbackground=[("readonly", DS["secondary"])],
            selectforeground=[("readonly", DS["fg"])],
        )
        s.configure("EPG.Horizontal.TProgressbar",
            troughcolor=DS["secondary"], background=DS["primary"],
            bordercolor=DS["border"], thickness=6,
        )

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self, bg=DS["primary"])
        hdr.pack(fill="x")

        inner = tk.Frame(hdr, bg=DS["primary"])
        inner.pack(fill="x", padx=28, pady=18)

        tk.Label(inner, text="EPGMaster",
                 bg=DS["primary"], fg="#FFFFFF",
                 font=font(20, "bold")).pack(side="left")

        tk.Label(inner, text=" · OBS EPG Converter",
                 bg=DS["primary"], fg="#FFFFFFAA",
                 font=font(12)).pack(side="left", pady=(5, 0))

        # thin bottom accent
        tk.Frame(self, bg=DS["border"], height=1).pack(fill="x")

    # ── Body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        self.body = tk.Frame(self, bg=DS["bg"], padx=28, pady=24)
        self.body.pack(fill="both")

        # ── Card 1: OBS file ──
        c1 = self._card(self.body)
        SectionLabel(c1, text="1  Файл OBS Scene Collection").pack(anchor="w", pady=(0, 10))

        row1 = tk.Frame(c1, bg=DS["card"])
        row1.pack(fill="x")
        self.obs_field = InputField(row1, self.obs_path, width=34)
        self.obs_field.pack(side="left")
        OutlineButton(row1, "Выбрать…", self._browse_obs).pack(side="left", padx=(10, 0))

        HintLabel(c1, text="OBS → Scene Collection → Export  •  или ~/Library/…/obs-studio/basic/scenes/").pack(anchor="w", pady=(8, 0))

        # ── Card 2: Scene ──
        c2 = self._card(self.body)
        SectionLabel(c2, text="2  Сцена / источник").pack(anchor="w", pady=(0, 10))

        self.scene_combo = ttk.Combobox(c2, textvariable=self.scene_var,
                                        state="readonly", font=font(11), width=50)
        self.scene_combo.pack(anchor="w")
        self.scene_combo.bind("<<ComboboxSelected>>", self._on_scene)

        self.files_lbl = HintLabel(c2, text="— загрузите JSON чтобы увидеть сцены —")
        self.files_lbl.pack(anchor="w", pady=(6, 0))

        # ── Card 3: Time ──
        c3 = self._card(self.body)
        SectionLabel(c3, text="3  Дата и время начала EPG (UTC)").pack(anchor="w", pady=(0, 10))

        row3 = tk.Frame(c3, bg=DS["card"])
        row3.pack(fill="x")

        tk.Label(row3, text="Дата", bg=DS["card"], fg=DS["fg"], font=font(11)).pack(side="left")
        InputField(row3, self.date_var, width=12).pack(side="left", padx=(8, 20))
        tk.Label(row3, text="Время (ЧЧ:ММ)", bg=DS["card"], fg=DS["fg"], font=font(11)).pack(side="left")
        InputField(row3, self.time_var, width=8).pack(side="left", padx=(8, 0))

        HintLabel(c3, text="Пример: 2026-05-15  07:00  →  EPG начнётся в 07:00 UTC").pack(anchor="w", pady=(8, 0))

        # ── ffprobe status ──
        self.ffprobe_lbl = tk.Label(self.body, text="",
                                    bg=DS["bg"], fg=DS["muted_fg"], font=font(10))
        self.ffprobe_lbl.pack(anchor="w", pady=(4, 0))

        # ── Progress ──
        self.prog_var = tk.DoubleVar()
        self.prog_bar = ttk.Progressbar(self.body, variable=self.prog_var,
                                        maximum=100, length=540,
                                        style="EPG.Horizontal.TProgressbar")
        self.prog_bar.pack(fill="x", pady=(16, 0))

        self.prog_lbl = tk.Label(self.body, text="",
                                 bg=DS["bg"], fg=DS["muted_fg"], font=font(10))
        self.prog_lbl.pack(anchor="w", pady=(4, 0))

        # ── Action ──
        btn_row = tk.Frame(self.body, bg=DS["bg"])
        btn_row.pack(fill="x", pady=(20, 4))

        self.gen_btn = PrimaryButton(btn_row, "Генерировать EPG →", self._start_generate)
        self.gen_btn.pack(side="right")

        self.status_lbl = tk.Label(self.body, text="",
                                   bg=DS["bg"], fg=DS["muted_fg"], font=font(10))
        self.status_lbl.pack(anchor="w", pady=(6, 0))

    def _card(self, parent) -> tk.Frame:
        card = Card(parent, padx=20, pady=18)
        card.pack(fill="x", pady=(0, 14))
        return card

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        tk.Frame(self, bg=DS["border"], height=1).pack(fill="x")
        footer = tk.Frame(self, bg=DS["secondary"], padx=28, pady=10)
        footer.pack(fill="x")
        tk.Label(footer, text="EPGMaster · epgmaster.io",
                 bg=DS["secondary"], fg=DS["muted_fg"], font=font(9)).pack(side="left")
        tk.Label(footer, text="v1.0",
                 bg=DS["secondary"], fg=DS["muted_fg"], font=font(9)).pack(side="right")

    # ── ffprobe ───────────────────────────────────────────────────────────────

    def _set_ffprobe_status(self, ok: bool, msg: str = ""):
        if ok:
            self.ffprobe_lbl.config(
                text=f"✓  ffprobe готов: {self.ffprobe}",
                fg=DS["success"])
        else:
            self.ffprobe_lbl.config(
                text=msg or "✗  ffprobe не найден",
                fg=DS["error"])

    def _offer_download(self):
        if messagebox.askyesno(
            "ffprobe не найден",
            "ffprobe не установлен.\n\n"
            "Скачать автоматически? (~60–120 МБ)\n"
            "Потребуется только один раз.",
        ):
            dlg = DownloadDialog(self)
            self.wait_window(dlg)
            if dlg.error:
                messagebox.showerror("Ошибка загрузки", dlg.error)
                self._set_ffprobe_status(False, f"✗  Не удалось скачать: {dlg.error}")
            else:
                self.ffprobe = dlg.result
                self._set_ffprobe_status(True)
        else:
            self._set_ffprobe_status(False, "✗  ffprobe не найден — генерация EPG недоступна")

    # ── OBS JSON ──────────────────────────────────────────────────────────────

    def _browse_obs(self):
        defaults = {
            "Darwin":  "~/Library/Application Support/obs-studio/basic/scenes",
            "Windows": "%APPDATA%\\obs-studio\\basic\\scenes",
            "Linux":   "~/.config/obs-studio/basic/scenes",
        }
        default = os.path.expandvars(os.path.expanduser(defaults.get(SYS, "~")))

        path = filedialog.askopenfilename(
            title="Выберите OBS Scene Collection JSON",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
            initialdir=default if os.path.isdir(default) else os.path.expanduser("~"),
        )
        if not path:
            return

        self.obs_path.set(path)
        try:
            self.scenes = parse_obs_json(path)
        except Exception as e:
            messagebox.showerror("Ошибка парсинга", str(e))
            return

        if not self.scenes:
            self.files_lbl.config(text="Плейлистов VLC/Media не найдено.", fg=DS["error"])
            self.scene_combo["values"] = []
            return

        names = list(self.scenes.keys())
        self.scene_combo["values"] = names
        self.scene_combo.current(0)
        self._on_scene()

    def _on_scene(self, *_):
        files = self.scenes.get(self.scene_var.get(), [])
        self.files_lbl.config(
            text=f"{len(files)} файлов в плейлисте",
            fg=DS["success"] if files else DS["error"],
        )

    # ── Generate ──────────────────────────────────────────────────────────────

    def _parse_start(self) -> datetime | None:
        try:
            return datetime.fromisoformat(f"{self.date_var.get()}T{self.time_var.get()}:00+00:00")
        except ValueError:
            messagebox.showerror("Ошибка даты", "Формат: YYYY-MM-DD и HH:MM")
            return None

    def _start_generate(self):
        if not self.ffprobe:
            self._offer_download()
            return

        files    = self.scenes.get(self.scene_var.get(), [])
        start_dt = self._parse_start()

        if not files:
            messagebox.showerror("Ошибка", "Нет файлов в выбранной сцене.")
            return
        if not start_dt:
            return

        out = filedialog.asksaveasfilename(
            title="Сохранить EPG JSON",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"epg_{self.scene_var.get().replace(' ', '_')}.json",
        )
        if not out:
            return

        self.gen_btn.config(state="disabled", bg=DS["muted_fg"])
        self.prog_var.set(0)
        self.status_lbl.config(text="Обрабатываю файлы…", fg=DS["muted_fg"])

        def worker():
            def cb(cur, total, path):
                self.prog_var.set(cur / total * 100)
                self.prog_lbl.config(text=f"[{cur}/{total}]  {Path(path).name}")
                self.update_idletasks()

            epg = build_epg(files, start_dt, self.ffprobe, on_progress=cb)

            with open(out, "w", encoding="utf-8") as f:
                json.dump(epg, f, ensure_ascii=False, indent=2)

            h, m = divmod(sum(e["duration"] for e in epg), 60)
            self.prog_var.set(100)
            self.prog_lbl.config(text="Готово!")
            self.status_lbl.config(
                text=f"✓  {len(epg)} программ, {h}ч {m}мин → {Path(out).name}",
                fg=DS["success"],
            )
            self.gen_btn.config(state="normal", bg=DS["primary"])
            messagebox.showinfo("EPG готов",
                f"✓ {len(epg)} программ\nДлительность: {h}ч {m}мин\n\nСохранено:\n{out}")

        threading.Thread(target=worker, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    App().mainloop()
