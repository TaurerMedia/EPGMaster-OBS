# OBS EPG Converter — EPGMaster

Desktop-приложение для пользователей [EPGMaster](https://epgmaster.io).  
Читает плейлист OBS (VLC Video Source), измеряет длительности файлов и экспортирует EPG JSON для загрузки в сервис.

---

## Скачать

→ **[Releases](../../releases/latest)**

| Платформа | Файл |
|-----------|------|
| macOS | `OBS_EPG_Converter_macOS.dmg` |
| Windows | `OBS_EPG_Converter.exe` |
| Linux | `obs-epg-converter` |

---

## Использование

1. Запустить приложение
2. При первом запуске — согласиться скачать ffprobe (один раз)
3. В OBS: **Scene Collection → Export** → сохранить JSON
4. Открыть JSON в приложении, выбрать сцену
5. Указать дату и время начала эфира (UTC)
6. Нажать **Генерировать EPG →**
7. Загрузить результат на EPGMaster

## Формат JSON

```json
[
  {
    "title": "Morning Show",
    "start": "2026-05-15T07:00:00Z",
    "end":   "2026-05-15T08:00:00Z",
    "duration": 60
  }
]
```

---

## Структура репозитория

```
epgmaster-obs/
├── src/
│   └── app.py               ← исходный код приложения
├── build/
│   ├── macos.spec           ← PyInstaller конфиг macOS
│   ├── windows.spec         ← PyInstaller конфиг Windows
│   └── linux.spec           ← PyInstaller конфиг Linux
├── scripts/
│   ├── build_macos.sh       ← сборка macOS вручную
│   ├── build_windows.bat    ← сборка Windows вручную
│   └── build_linux.sh       ← сборка Linux вручную
├── assets/                  ← иконки (генерируются при сборке)
└── .github/workflows/
    └── build.yml            ← автосборка при git tag v*
```

---

## Сборка вручную

```bash
# macOS
chmod +x scripts/build_macos.sh && ./scripts/build_macos.sh

# Linux
chmod +x scripts/build_linux.sh && ./scripts/build_linux.sh

# Windows
scripts\build_windows.bat
```

Требуется Python 3.10+.

---

© EPGMaster / VXDGROUP. См. LICENSE.
