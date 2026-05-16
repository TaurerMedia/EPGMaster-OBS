# OBS → EPG Converter

Конвертирует плейлист OBS (VLC Video Source) в EPG JSON для сервиса StreamRussia.

## Скачать

→ **[Releases](../../releases/latest)** — готовые файлы для Windows, macOS и Linux

| Платформа | Файл |
|-----------|------|
| macOS | `OBS_EPG_Converter_macOS.dmg` |
| Windows | `OBS_EPG_Converter.exe` |
| Linux | `obs-epg-converter` |

## Как использовать

1. Запустить приложение
2. При первом запуске — согласиться скачать ffprobe (один раз, ~60-120 МБ)
3. В OBS: **Scene Collection → Export** → сохранить JSON
4. Открыть JSON в приложении
5. Выбрать сцену, указать дату/время начала EPG
6. Нажать **Генерировать EPG →**

## Формат выходного JSON

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

## Собрать самостоятельно

```bash
# macOS
chmod +x build_macos.sh && ./build_macos.sh

# Linux
chmod +x build_linux.sh && ./build_linux.sh

# Windows
build_windows.bat
```

Требуется Python 3.10+.
