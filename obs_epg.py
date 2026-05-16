"""
OBS → EPG Converter
• Автоматически скачивает ffprobe при первом запуске
• Читает OBS scene collection JSON
• Строит EPG JSON совместимый со StreamRussia
"""

import json
import os
import platform
import shutil
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

# ── константы ─────────────────────────────────────────────────────────────────

APP_NAME = "OBS EPG Converter"
APP_DIR  = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
FFPROBE_DIR = APP_DIR / "ffprobe_bin"

# Ссылки на статичные сборки ffprobe (только сам ffprobe, без ffmpeg)
FFPROBE_URLS = {
    ("Windows", "x86_64"): {
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "exe": "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe",
        "type": "zip",
    },
    ("Darwin", "x86_64"): {
        "url": "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
        "exe": "ffprobe",
        "type": "zip",
    },
    ("Darwin", "arm64"): {
        "url": "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
        "exe": "ffprobe",
        "type": "zip",
    },
    ("Linux", "x86_64"): {
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
        "exe": "ffmpeg-master-latest-linux64-gpl/bin/ffprobe",
        "type": "tar",
    },
}

# ── ffprobe: поиск и авто-установка ──────────────────────────────────────────

def get_platform_key():
    system = platform.system()   # Windows / Darwin / Linux
    machine = platform.machine() # x86_64 / arm64 / AMD64
    if machine.lower() in ("amd64", "x86_64"):
        machine = "x86_64"
    elif machine.lower() in ("arm64", "aarch64"):
        machine = "arm64"
    return system, machine


def find_ffprobe() -> Path | None:
    """Сначала ищем в нашей папке, потом в PATH."""
    system, _ = get_platform_key()
    local_name = "ffprobe.exe" if system == "Windows" else "ffprobe"
    local = FFPROBE_DIR / local_name
    if local.exists():
        return local

    # Поиск в PATH
    found = shutil.which("ffprobe")
    if found:
        return Path(found)
    return None


def download_ffprobe(progress_cb=None) -> Path:
    """
    Скачивает ffprobe для текущей платформы.
    progress_cb(downloaded_bytes, total_bytes)
    Возвращает путь к исполняемому файлу.
    """
    key = get_platform_key()
    info = FFPROBE_URLS.get(key)
    if not info:
        raise RuntimeError(f"Нет сборки ffprobe для {key[0]} {key[1]}")

    FFPROBE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = FFPROBE_DIR / ("ffprobe_dl.zip" if info["type"] == "zip" else "ffprobe_dl.tar.xz")

    # Скачиваем
    def reporthook(count, block_size, total_size):
        if progress_cb and total_size > 0:
            progress_cb(count * block_size, total_size)

    urllib.request.urlretrieve(info["url"], archive_path, reporthook)

    # Распаковываем нужный файл
    system, _ = key
    dest_name = "ffprobe.exe" if system == "Windows" else "ffprobe"
    dest = FFPROBE_DIR / dest_name

    if info["type"] == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            # Находим нужный файл внутри архива
            target_inner = info["exe"]
            # Пробуем точное совпадение, потом по имени файла
            members = zf.namelist()
            match = next(
                (m for m in members if m == target_inner or m.endswith("/" + dest_name) or m == dest_name),
                None,
            )
            if not match:
                raise RuntimeError(f"ffprobe не найден в архиве. Файлы: {members[:10]}")
            with zf.open(match) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)

    elif info["type"] == "tar":
        with tarfile.open(archive_path) as tf:
            target_inner = info["exe"]
            members = tf.getmembers()
            match = next(
                (m for m in members if m.name == target_inner or m.name.endswith("/" + dest_name)),
                None,
            )
            if not match:
                raise RuntimeError(f"ffprobe не найден в архиве.")
            src = tf.extractfile(match)
            with open(dest, "wb") as out:
                shutil.copyfileobj(src, out)

    archive_path.unlink(missing_ok=True)

    # chmod +x на Unix
    if system != "Windows":
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return dest


# ── EPG логика ────────────────────────────────────────────────────────────────

def get_duration(ffprobe_path: Path, filepath: str) -> float | None:
    try:
        out = subprocess.check_output(
            [str(ffprobe_path), "-v", "quiet", "-show_format", "-print_format", "json", filepath],
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return None


def clean_title(filepath: str) -> str:
    name = Path(filepath).stem
    for ch in ["_", "-", "."]:
        name = name.replace(ch, " ")
    return " ".join(name.split()).strip()


def parse_obs_json(path: str) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Собираем все источники с файлами
    source_files: dict[str, list[str]] = {}
    for src in data.get("sources", []):
        sid = src.get("id", "")
        settings = src.get("settings", {})
        files: list[str] = []

        if sid == "vlc_source":
            for item in settings.get("playlist", []):
                v = item.get("value", "")
                if v:
                    files.append(v)
        elif sid == "ffmpeg_source":
            v = settings.get("local_file", "")
            if v:
                files.append(v)

        if files:
            source_files[src.get("name", "Unnamed")] = files

    # Группируем по сценам
    scene_map: dict[str, list[str]] = {}
    for src in data.get("sources", []):
        if src.get("id") not in ("scene", "group"):
            continue
        scene_name = src.get("name", "Scene")
        collected: list[str] = []
        for item in src.get("settings", {}).get("items", []):
            item_name = item.get("name", "")
            if item_name in source_files:
                collected.extend(source_files[item_name])
        if collected:
            scene_map[scene_name] = collected

    # Если сцен нет — отдаём источники напрямую
    if not scene_map and source_files:
        scene_map = source_files

    return scene_map


def build_epg(files: list[str], start_dt: datetime, ffprobe: Path, progress_cb=None) -> list[dict]:
    epg = []
    t = start_dt
    total = len(files)
    for i, filepath in enumerate(files):
        if progress_cb:
            progress_cb(i + 1, total, filepath)
        dur_sec = get_duration(ffprobe, filepath)
        if dur_sec is None:
            continue
        dur_min = max(1, round(dur_sec / 60))
        end_dt = t + timedelta(seconds=dur_sec)
        epg.append({
            "title": clean_title(filepath),
            "start": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end":   end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration": dur_min,
        })
        t = end_dt
    return epg


# ── GUI ───────────────────────────────────────────────────────────────────────

BG      = "#1a1a2e"
CARD    = "#16213e"
ACCENT  = "#7c3aed"
ACCENT2 = "#a855f7"
FG      = "#e2e8f0"
FG2     = "#94a3b8"
ENTRY   = "#0f3460"
GREEN   = "#10b981"
RED     = "#ef4444"
FONT    = "SF Pro Display" if platform.system() == "Darwin" else ("Segoe UI" if platform.system() == "Windows" else "DejaVu Sans")


class DownloadDialog(tk.Toplevel):
    """Модальное окно загрузки ffprobe."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Загрузка ffprobe…")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()

        tk.Label(self, text="⬇  Скачиваю ffprobe…", bg=BG, fg=FG,
                 font=(FONT, 13, "bold")).pack(padx=30, pady=(20, 8))

        self.sub = tk.Label(self, text="Подключаюсь…", bg=BG, fg=FG2, font=(FONT, 10))
        self.sub.pack()

        self.bar_var = tk.DoubleVar()
        ttk.Progressbar(self, variable=self.bar_var, maximum=100, length=340).pack(padx=30, pady=12)

        self.pct_lbl = tk.Label(self, text="0%", bg=BG, fg=FG2, font=(FONT, 10))
        self.pct_lbl.pack(pady=(0, 20))

        self.result: Path | None = None
        self.error: str | None = None

        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        def cb(done, total):
            pct = min(done / total * 100, 100)
            mb_done = done / 1_048_576
            mb_total = total / 1_048_576
            self.bar_var.set(pct)
            self.sub.config(text=f"{mb_done:.1f} МБ / {mb_total:.1f} МБ")
            self.pct_lbl.config(text=f"{pct:.0f}%")
            self.update_idletasks()

        try:
            self.result = download_ffprobe(progress_cb=cb)
        except Exception as e:
            self.error = str(e)
        finally:
            self.grab_release()
            self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.resizable(False, False)
        self.configure(bg=BG)

        self.obs_path  = tk.StringVar()
        self.scene_var = tk.StringVar()
        self.date_var  = tk.StringVar(value=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        self.time_var  = tk.StringVar(value="07:00")

        self.scenes: dict[str, list[str]] = {}
        self.ffprobe: Path | None = find_ffprobe()

        self._build_ui()

        # Если ffprobe нет — предлагаем скачать сразу
        if not self.ffprobe:
            self.after(300, self._offer_download)
        else:
            self._set_ffprobe_ok()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=ACCENT, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  {APP_NAME}", bg=ACCENT, fg="#fff",
                 font=(FONT, 16, "bold")).pack(side="left")

        body = tk.Frame(self, bg=BG, padx=28, pady=18)
        body.pack(fill="both")

        # Step 1
        self._section(body, "1  OBS Scene Collection JSON")
        row1 = tk.Frame(body, bg=BG)
        row1.pack(fill="x", pady=(0, 2))
        tk.Entry(row1, textvariable=self.obs_path, bg=ENTRY, fg=FG,
                 insertbackground=FG, relief="flat", font=(FONT, 11), width=38
                 ).pack(side="left")
        self._btn(row1, "Browse…", self._browse_obs).pack(side="left", padx=(8, 0))
        self._small(body, "OBS → Scene Collection → Export  (или ~/Library/…/obs-studio/basic/scenes/)")

        # Step 2
        self._section(body, "2  Выберите сцену")
        self.scene_combo = ttk.Combobox(body, textvariable=self.scene_var,
                                        state="readonly", font=(FONT, 11), width=46)
        self.scene_combo.pack(anchor="w", pady=(0, 2))
        self.files_lbl = self._small(body, "— загрузите JSON чтобы увидеть сцены —")
        self.scene_combo.bind("<<ComboboxSelected>>", self._on_scene)

        # Step 3
        self._section(body, "3  Дата и время начала EPG (UTC)")
        row3 = tk.Frame(body, bg=BG)
        row3.pack(fill="x", pady=(0, 2))
        self._label(row3, "Дата").pack(side="left")
        tk.Entry(row3, textvariable=self.date_var, bg=ENTRY, fg=FG,
                 insertbackground=FG, relief="flat", font=(FONT, 11), width=13
                 ).pack(side="left", padx=(6, 16))
        self._label(row3, "Время HH:MM").pack(side="left")
        tk.Entry(row3, textvariable=self.time_var, bg=ENTRY, fg=FG,
                 insertbackground=FG, relief="flat", font=(FONT, 11), width=8
                 ).pack(side="left", padx=(6, 0))
        self._small(body, "Пример: 2026-05-15  07:00  → EPG начнётся в 07:00 UTC")

        # ffprobe status
        self.ffprobe_lbl = tk.Label(body, text="", bg=BG, fg=FG2, font=(FONT, 10))
        self.ffprobe_lbl.pack(anchor="w", pady=(10, 0))

        # Progress
        self.prog_var = tk.DoubleVar()
        self.prog_bar = ttk.Progressbar(body, variable=self.prog_var, maximum=100, length=480)
        self.prog_bar.pack(fill="x", pady=(10, 0))
        self.prog_lbl = self._small(body, "")

        # Buttons
        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x", pady=(16, 4))
        self._btn(btn_row, "Генерировать EPG →", self._start_generate, accent=True).pack(side="right")

        self.status_lbl = self._small(body, "")

    def _section(self, p, t):
        tk.Label(p, text=t, bg=BG, fg=ACCENT2, font=(FONT, 12, "bold")).pack(anchor="w", pady=(14, 2))

    def _label(self, p, t):
        return tk.Label(p, text=t, bg=BG, fg=FG, font=(FONT, 11))

    def _small(self, p, t):
        l = tk.Label(p, text=t, bg=BG, fg=FG2, font=(FONT, 10))
        l.pack(anchor="w")
        return l

    def _btn(self, p, t, cmd, accent=False):
        return tk.Button(p, text=t, command=cmd,
                         bg=ACCENT if accent else CARD,
                         fg="#fff" if accent else FG2,
                         activebackground=ACCENT2, activeforeground="#fff",
                         relief="flat", bd=0, cursor="hand2",
                         font=(FONT, 11, "bold" if accent else "normal"),
                         padx=14, pady=7)

    # ── ffprobe helpers ───────────────────────────────────────────────────────

    def _set_ffprobe_ok(self):
        self.ffprobe_lbl.config(text=f"✓ ffprobe готов: {self.ffprobe}", fg=GREEN)

    def _offer_download(self):
        ans = messagebox.askyesno(
            "ffprobe не найден",
            "ffprobe не установлен на вашем компьютере.\n\n"
            "Скачать автоматически? (~60–120 МБ)\n"
            "(потребуется только один раз)",
        )
        if ans:
            self._do_download()
        else:
            self.ffprobe_lbl.config(text="✗ ffprobe не найден — EPG генерировать нельзя", fg=RED)

    def _do_download(self):
        dlg = DownloadDialog(self)
        self.wait_window(dlg)
        if dlg.error:
            messagebox.showerror("Ошибка загрузки", dlg.error)
            self.ffprobe_lbl.config(text="✗ Не удалось скачать ffprobe", fg=RED)
        else:
            self.ffprobe = dlg.result
            self._set_ffprobe_ok()

    # ── OBS JSON ──────────────────────────────────────────────────────────────

    def _browse_obs(self):
        default = ""
        if platform.system() == "Darwin":
            default = os.path.expanduser("~/Library/Application Support/obs-studio/basic/scenes")
        elif platform.system() == "Windows":
            default = os.path.expandvars(r"%APPDATA%\obs-studio\basic\scenes")

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
            self.files_lbl.config(text="Плейлистов VLC/Media не найдено в этом файле.", fg=RED)
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
            fg=GREEN if files else RED,
        )

    # ── Generate ──────────────────────────────────────────────────────────────

    def _parse_dt(self) -> datetime | None:
        try:
            s = f"{self.date_var.get()}T{self.time_var.get()}:00+00:00"
            return datetime.fromisoformat(s)
        except ValueError:
            messagebox.showerror("Ошибка", "Формат даты: YYYY-MM-DD, время: HH:MM")
            return None

    def _start_generate(self):
        if not self.ffprobe:
            self._offer_download()
            return
        files = self.scenes.get(self.scene_var.get(), [])
        if not files:
            messagebox.showerror("Ошибка", "Нет файлов в выбранной сцене.")
            return
        start_dt = self._parse_dt()
        if not start_dt:
            return

        scene_name = self.scene_var.get()
        out_path = filedialog.asksaveasfilename(
            title="Сохранить EPG JSON как…",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"epg_{scene_name.replace(' ', '_')}.json",
        )
        if not out_path:
            return

        self.prog_var.set(0)
        self.status_lbl.config(text="Обрабатываю файлы…", fg=FG2)

        def worker():
            def cb(cur, total, path):
                self.prog_var.set(cur / total * 100)
                self.prog_lbl.config(text=f"[{cur}/{total}]  {Path(path).name}")
                self.update_idletasks()

            epg = build_epg(files, start_dt, self.ffprobe, progress_cb=cb)

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(epg, f, ensure_ascii=False, indent=2)

            self.prog_var.set(100)
            h, m = divmod(sum(e["duration"] for e in epg), 60)
            self.status_lbl.config(
                text=f"✓ {len(epg)} программ, {h}ч {m}мин → {Path(out_path).name}",
                fg=GREEN,
            )
            self.prog_lbl.config(text="Готово!")
            messagebox.showinfo(
                "EPG готов",
                f"✓ {len(epg)} программ\n"
                f"Суммарная длительность: {h}ч {m}мин\n\n"
                f"Сохранено:\n{out_path}",
            )

        threading.Thread(target=worker, daemon=True).start()


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
