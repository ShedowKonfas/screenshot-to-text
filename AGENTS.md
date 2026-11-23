# AGENTS.md — screenshot_to_text
## Назначение
Tkinter-OCR: файл или картинка из буфера → текст в окне и в буфере, плюс перевод через Google Translate.
## Карта файлов
- `main.py` — `find_tesseract()`, `get_ocr_language()`, `ocr_worker()`, `translate_text()`, `on_ctrl_v()`, `build_gui()`.
- `requirements.txt` — Pillow, pytesseract, pyperclip; Tkinter входит в Python.
- `start.cmd` — запуск через `venv\Scripts\pythonw.exe`, иначе системный `pythonw`.
- `screenshots\`, `screenshot_to_text.lnk` — примеры и ярлык; `README.md`, `AGENTS.md` — документация.
## Запуск и тесты
```bat
python -m venv venv
venv\Scripts\pip install -r requirements.txt
start.cmd
```
Тестов нет; без запроса не добавляем. Проверка вручную: OCR скриншота и перевод.
## Соглашения
- Интерфейс и статусы — на русском.
- OCR и перевод — в daemon-потоках, результат через `queue.Queue`, GUI обновляет главный поток.
- Новые языки — в `LANGUAGES`, не в разметке UI.
## Подводные камни
- Tesseract — внешняя программа: без неё ошибка при старте; путь через `TESSERACT_CMD`.
- `get_ocr_language()` кэшируется — после доустановки языков нужен перезапуск.
- Перевод требует интернет; `Ctrl+V` работает по keycode 86 (русская раскладка).
## Запреты
- Не удалять файлы и папки без явного разрешения пользователя.
- Не трогать системные файлы, включая установленный Tesseract и PATH.
- Не выдумывать тесты и не добавлять зависимости без запроса.
- Не менять код/requirements при работе с документацией; не делать commit/push без просьбы.
