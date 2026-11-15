import ctypes
import json
import os
import queue
import shutil
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from tkinter import filedialog, messagebox, ttk

import pyperclip
import pytesseract
from PIL import Image, ImageDraw, ImageGrab, ImageTk

APP_TITLE = "OCR с файла"
TESSERACT_HINT = (
    "Tesseract не найден.\n\n"
    "Установи Tesseract-OCR или укажи путь к tesseract.exe\n"
    "в переменной окружения TESSERACT_CMD."
)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")

TRANSLATE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
LANGUAGES = {
    "Русский": "ru",
    "English": "en",
    "Українська": "uk",
    "Deutsch": "de",
}
DEFAULT_LANGUAGE = "English"

# --- палитра и шрифты ---
FONT = "Segoe UI"
BG = "#f3f4f6"
CARD = "#ffffff"
CARD_SOFT = "#fafbfc"
BORDER = "#e2e5ea"
TEXT = "#1f2937"
MUTED = "#6b7280"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
SECONDARY = "#eceef2"
SECONDARY_HOVER = "#e0e3e9"
STATUS_READY = "#6b7280"
STATUS_WORK = "#d97706"
STATUS_OK = "#16a34a"
STATUS_ERR = "#dc2626"

img_path = ""
current_image = None
busy = False
translating = False
ocr_language = None
results = queue.Queue()
translation_results = queue.Queue()

choose_button = None
recognize_button = None
translate_button = None
lang_box = None
file_label = None
text_area = None
translation_card = None
translation_title = None
translation_text = None
status_dot = None
status_label = None
count_label = None
preview_label = None
preview_photo = None
placeholder_photo = None
app_icon = None
footer = None


def enable_dpi_awareness():
    """Чёткий текст на мониторах с масштабированием Windows."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def find_tesseract():
    """Ищет tesseract.exe: переменная окружения, PATH, стандартные папки."""
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd and os.path.isfile(env_cmd):
        return env_cmd

    found = shutil.which("tesseract")
    if found:
        return found

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        r"D:\Program Files\Tesseract-OCR\tesseract.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def get_ocr_language():
    """Русский + английский, если установлены нужные языковые данные."""
    global ocr_language
    if ocr_language is not None:
        return ocr_language

    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        # tesseract ещё не настроен или недоступен — не кэшируем результат
        return "eng"

    if {"rus", "eng"} <= installed:
        ocr_language = "rus+eng"
    elif "rus" in installed:
        ocr_language = "rus"
    else:
        ocr_language = "eng"
    return ocr_language


def shorten(text, limit=62):
    if len(text) <= limit:
        return text
    keep = limit - 1
    head = keep // 2
    return text[:head] + "…" + text[-(keep - head):]


def plural_chars(count):
    mod100 = abs(count) % 100
    mod10 = mod100 % 10
    if 11 <= mod100 <= 14:
        return "символов"
    if mod10 == 1:
        return "символ"
    if 2 <= mod10 <= 4:
        return "символа"
    return "символов"


def set_status(text, color):
    status_dot.config(fg=color)
    status_label.config(text=text)


def make_icon():
    """Простенькая иконка: синий квадрат с белой буквой T."""
    size = 64
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((2, 2, size - 3, size - 3), radius=14, fill=ACCENT)
    draw.rectangle((16, 16, 48, 25), fill="white")
    draw.rectangle((28, 22, 36, 48), fill="white")
    return ImageTk.PhotoImage(icon)


def make_placeholder():
    """Заглушка вместо превью, когда картинки нет."""
    size = 88
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=14, fill=SECONDARY)
    draw.ellipse((20, 18, 34, 32), fill="#9aa2ad")
    draw.polygon(
        [(14, 68), (36, 42), (50, 56), (60, 44), (74, 68)], fill="#9aa2ad"
    )
    icon = icon.resize((44, 44), Image.LANCZOS)
    return ImageTk.PhotoImage(icon)


def update_preview(source):
    """Миниатюра выбранной картинки или заглушка."""
    global preview_photo
    preview_photo = None
    try:
        if isinstance(source, Image.Image):
            image = source.copy()
        elif source:
            with Image.open(source) as opened:
                image = opened.copy()
        else:
            raise ValueError("empty source")
        image.thumbnail((44, 44))
        preview_photo = ImageTk.PhotoImage(image)
    except Exception:
        preview_photo = placeholder_photo
    preview_label.config(image=preview_photo)


def set_source(path=None, image=None):
    """Делает картинку из буфера или файла текущим источником."""
    global img_path, current_image

    img_path = path or ""
    current_image = image

    if image is not None:
        description = f"Из буфера обмена · {image.width}×{image.height}"
    elif path:
        description = shorten(path)
    else:
        description = "Файл не выбран"

    file_label.config(text=description, fg=TEXT if (path or image is not None) else MUTED)
    update_preview(image if image is not None else path)
    text_area.delete("1.0", tk.END)
    count_label.config(text=f"0 {plural_chars(0)}")
    set_status("Готов", STATUS_READY)


def choose_file():
    path = filedialog.askopenfilename(
        title="Выберите изображение",
        filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")],
    )
    if path:
        set_source(path=path)
    else:
        set_source()


def clipboard_image():
    """Картинка из буфера обмена: PIL-изображение или путь к файлу."""
    try:
        data = ImageGrab.grabclipboard()
    except Exception:
        return None

    if isinstance(data, Image.Image):
        # ImageGrab возвращает ленивый DIB, а не обычное изображение —
        # конвертируем сразу, пока данные буфера доступны
        try:
            return data.convert("RGB")
        except Exception:
            return None

    if isinstance(data, list):
        for item in data:
            path = str(item)
            if path.lower().endswith(IMAGE_EXTENSIONS) and os.path.isfile(path):
                return path
    return None


def on_ctrl_v(event):
    """Ctrl+V по физической клавише V — работает и на русской раскладке."""
    is_v = event.keycode == 86 or str(event.keysym).lower() in ("v", "cyrillic_em")
    if not is_v:
        return None
    if busy or translating:
        return "break"

    data = clipboard_image()
    if data is not None:
        if isinstance(data, Image.Image):
            set_source(image=data)
        else:
            set_source(path=data)
        recognize()
        return "break"

    # картинки нет — вставляем текст сами, чтобы работало и с кириллицей
    widget = event.widget.winfo_toplevel().focus_get()
    if not isinstance(widget, tk.Text):
        widget = text_area
    try:
        clipboard_text = pyperclip.paste()
    except Exception:
        clipboard_text = ""

    if clipboard_text:
        if widget.tag_ranges("sel"):
            widget.delete("sel.first", "sel.last")
        widget.insert("insert", clipboard_text)
        widget.see("insert")
    return "break"


def recognize():
    if busy:
        return
    if current_image is None and not img_path:
        messagebox.showwarning("Ой", "Сначала выберите файл или вставьте картинку")
        return
    if current_image is None and not os.path.isfile(img_path):
        messagebox.showerror("Ошибка", f"Файл не найден:\n{img_path}")
        return

    set_busy(True)
    set_status("Распознаю…", STATUS_WORK)

    if current_image is not None:
        source = ("image", current_image)
    else:
        source = ("path", img_path)
    threading.Thread(target=ocr_worker, args=(source,), daemon=True).start()


def ocr_worker(source):
    kind, value = source
    try:
        if kind == "image":
            image = value
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            text = pytesseract.image_to_string(image, lang=get_ocr_language())
        else:
            with Image.open(value) as image:
                text = pytesseract.image_to_string(image, lang=get_ocr_language())
    except Exception as exc:
        results.put(("error", exc))
    else:
        results.put(("ok", text.strip()))


def split_chunks(text, limit=4000):
    """Режем текст на куски, чтобы не упираться в лимит длины запроса."""
    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks or [text]


def translate_text(text, target):
    """Перевод через публичный эндпоинт Google Translate (без ключа)."""
    parts = []
    for chunk in split_chunks(text):
        params = urllib.parse.urlencode(
            {"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": chunk}
        )
        request = urllib.request.Request(
            f"{TRANSLATE_ENDPOINT}?{params}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        parts.append(
            "".join(segment[0] for segment in payload[0] if segment and segment[0])
        )
    return "\n".join(parts)


def translate():
    global translating

    if translating or busy:
        return

    text = text_area.get("1.0", "end-1c").strip()
    if not text:
        messagebox.showwarning("Ой", "Сначала распознай текст")
        return

    language_name = lang_box.get()
    target = LANGUAGES.get(language_name, "en")

    translating = True
    translate_button.config(state=tk.DISABLED, text="Перевожу…")
    set_status(f"Перевожу на {language_name}…", STATUS_WORK)
    threading.Thread(
        target=translate_worker, args=(text, target, language_name), daemon=True
    ).start()


def translate_worker(text, target, language_name):
    try:
        translated = translate_text(text, target)
    except Exception as exc:
        translation_results.put(("error", exc))
    else:
        translation_results.put(("ok", (translated, language_name)))


def start_translation(translated, language_name):
    global translating

    translating = False
    translate_button.config(state=tk.NORMAL, text="Перевести")

    if not translated.strip():
        set_status("Перевод пустой", STATUS_WORK)
        return

    show_translation(translated, language_name)
    set_status("Перевод готов", STATUS_OK)


def show_translation(translated, language_name):
    translation_title.config(text=f"Перевод · {language_name}")
    translation_text.config(state=tk.NORMAL)
    translation_text.delete("1.0", tk.END)
    translation_text.insert(tk.END, translated)
    translation_text.config(state=tk.DISABLED)

    if not translation_card.winfo_ismapped():
        translation_card.pack(
            fill=tk.BOTH, expand=True, pady=(10, 0), before=footer
        )


def poll_results():
    try:
        kind, payload = results.get_nowait()
    except queue.Empty:
        pass
    else:
        if kind == "error":
            set_busy(False)
            set_status("Ошибка распознавания", STATUS_ERR)
            messagebox.showerror("Ошибка", str(payload))
        else:
            show_text(payload)

    try:
        kind, payload = translation_results.get_nowait()
    except queue.Empty:
        pass
    else:
        if kind == "error":
            global translating
            translating = False
            translate_button.config(state=tk.NORMAL, text="Перевести")
            set_status("Ошибка перевода", STATUS_ERR)
            messagebox.showerror(
                "Ошибка перевода",
                "Не удалось перевести текст.\n"
                "Проверь подключение к интернету.\n\n"
                f"{payload}",
            )
        else:
            start_translation(*payload)

    status_label.after(100, poll_results)


def show_text(text):
    set_busy(False)
    text_area.delete("1.0", tk.END)
    text_area.insert(tk.END, text)
    count_label.config(text=f"{len(text)} {plural_chars(len(text))}")

    if not text:
        set_status("Текст не найден", STATUS_WORK)
        return

    try:
        pyperclip.copy(text)
    except Exception:
        set_status("Текст распознан (буфер недоступен)", STATUS_WORK)
    else:
        set_status("Скопировано в буфер", STATUS_OK)


def set_busy(value):
    global busy
    busy = value
    state = tk.DISABLED if value else tk.NORMAL
    choose_button.config(state=state)
    recognize_button.config(state=state)
    translate_button.config(state=state)

    if value:
        recognize_button.config(text="Распознаю…", bg=SECONDARY, fg=MUTED)
    else:
        recognize_button.config(text="Распознать", bg=ACCENT, fg="white")
        recognize_button.configure(cursor="hand2")


def make_button(parent, text, command, kind="primary"):
    if kind == "primary":
        bg, hover, fg, active_fg = ACCENT, ACCENT_HOVER, "white", "white"
    else:
        bg, hover, fg, active_fg = SECONDARY, SECONDARY_HOVER, TEXT, TEXT

    button = tk.Button(
        parent,
        text=text,
        command=command,
        font=(FONT, 11, "bold" if kind == "primary" else "normal"),
        bg=bg,
        fg=fg,
        activebackground=hover,
        activeforeground=active_fg,
        relief="flat",
        bd=0,
        highlightthickness=0,
        cursor="hand2",
        padx=16,
        pady=9 if kind == "primary" else 7,
    )

    def on_enter(_event):
        if str(button["state"]) != tk.DISABLED:
            button.config(bg=hover)

    def on_leave(_event):
        if str(button["state"]) != tk.DISABLED:
            button.config(bg=bg)

    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)
    return button


def select_all(event):
    event.widget.tag_add("sel", "1.0", "end-1c")
    return "break"


def make_text_pane(parent, height=8, bg=CARD):
    card = tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground=BORDER)

    scrollbar = ttk.Scrollbar(card, orient=tk.VERTICAL)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=2, padx=(0, 2))

    text = tk.Text(
        card,
        wrap=tk.WORD,
        bd=0,
        highlightthickness=0,
        height=height,
        bg=bg,
        fg=TEXT,
        font=(FONT, 11),
        padx=12,
        pady=10,
        spacing1=2,
        spacing3=3,
        insertbackground=TEXT,
        selectbackground="#c7dbff",
        selectforeground=TEXT,
        yscrollcommand=scrollbar.set,
    )
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=text.yview)

    text.bind("<Control-a>", select_all)
    text.bind("<Control-A>", select_all)
    text.bind("<Control-KeyPress>", on_ctrl_v)
    return card, text


def build_gui(root):
    global choose_button, recognize_button, translate_button, lang_box, file_label
    global text_area, translation_card, translation_title, translation_text
    global status_dot, status_label, count_label, preview_label
    global placeholder_photo, app_icon, footer

    root.title(APP_TITLE)
    root.configure(bg=BG)
    root.minsize(560, 480)

    width, height = 660, 650
    x = (root.winfo_screenwidth() - width) // 2
    y = max(0, (root.winfo_screenheight() - height) // 3)
    root.geometry(f"{width}x{height}+{x}+{y}")

    app_icon = make_icon()
    root.iconphoto(True, app_icon)
    placeholder_photo = make_placeholder()

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Vertical.TScrollbar",
        background="#d5d8de",
        troughcolor=CARD,
        bordercolor=CARD,
        arrowcolor="#8b919b",
        relief="flat",
    )
    style.configure(
        "TCombobox",
        fieldbackground=CARD,
        background=CARD,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        arrowcolor=MUTED,
        padding=4,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", CARD)],
        selectbackground=[("readonly", CARD)],
        selectforeground=[("readonly", TEXT)],
    )

    container = tk.Frame(root, bg=BG)
    container.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

    # --- заголовок ---
    header = tk.Frame(container, bg=BG)
    header.pack(fill=tk.X)

    tk.Label(
        header,
        text="OCR с файла",
        bg=BG,
        fg=TEXT,
        font=(FONT, 17, "bold"),
        anchor="w",
    ).pack(fill=tk.X)

    tk.Label(
        header,
        text="Выбери картинку или вставь её через Ctrl+V — текст окажется в буфере",
        bg=BG,
        fg=MUTED,
        font=(FONT, 9),
        anchor="w",
    ).pack(fill=tk.X, pady=(2, 0))

    # --- карточка источника ---
    file_card = tk.Frame(
        container, bg=CARD, highlightthickness=1, highlightbackground=BORDER
    )
    file_card.pack(fill=tk.X, pady=(16, 10))

    preview_holder = tk.Frame(file_card, bg=CARD, width=44, height=44)
    preview_holder.pack(side=tk.LEFT, padx=(10, 0), pady=8)
    preview_holder.pack_propagate(False)

    preview_label = tk.Label(preview_holder, bg=CARD, bd=0, image=placeholder_photo)
    preview_label.pack(fill=tk.BOTH, expand=True)

    choose_button = make_button(
        file_card, "Выбрать файл", choose_file, kind="secondary"
    )
    choose_button.pack(side=tk.LEFT, padx=10, pady=8)

    file_label = tk.Label(
        file_card,
        text="Файл не выбран",
        bg=CARD,
        fg=MUTED,
        font=(FONT, 10),
        anchor="w",
    )
    file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))

    # --- кнопка распознавания ---
    recognize_button = make_button(container, "Распознать", recognize)
    recognize_button.pack(fill=tk.X, pady=(0, 12))

    # --- карточка с текстом ---
    text_card, text_area = make_text_pane(container, height=10)
    text_card.pack(fill=tk.BOTH, expand=True)

    # --- панель перевода ---
    translate_bar = tk.Frame(container, bg=BG)
    translate_bar.pack(fill=tk.X, pady=(10, 0))

    tk.Label(
        translate_bar,
        text="Перевод",
        bg=BG,
        fg=TEXT,
        font=(FONT, 10, "bold"),
    ).pack(side=tk.LEFT)

    lang_box = ttk.Combobox(
        translate_bar,
        values=list(LANGUAGES),
        state="readonly",
        font=(FONT, 10),
        width=12,
    )
    lang_box.set(DEFAULT_LANGUAGE)
    lang_box.pack(side=tk.LEFT, padx=(8, 0))

    translate_button = make_button(
        translate_bar, "Перевести", translate, kind="secondary"
    )
    translate_button.pack(side=tk.LEFT, padx=(8, 0))

    # --- карточка перевода (появляется после первого перевода) ---
    translation_card = tk.Frame(
        container, bg=CARD_SOFT, highlightthickness=1, highlightbackground=BORDER
    )

    translation_header = tk.Frame(translation_card, bg=CARD_SOFT)
    translation_header.pack(fill=tk.X, padx=12, pady=(8, 0))

    translation_title = tk.Label(
        translation_header,
        text="Перевод",
        bg=CARD_SOFT,
        fg=MUTED,
        font=(FONT, 9, "bold"),
        anchor="w",
    )
    translation_title.pack(side=tk.LEFT)

    tk.Label(
        translation_header,
        text="Google Translate",
        bg=CARD_SOFT,
        fg="#9aa2ad",
        font=(FONT, 8),
        anchor="e",
    ).pack(side=tk.RIGHT)

    translation_body, translation_text = make_text_pane(translation_card, height=6, bg=CARD_SOFT)
    translation_body.configure(highlightthickness=0)
    translation_body.pack(fill=tk.BOTH, expand=True, pady=(4, 4))
    translation_text.config(state=tk.DISABLED)

    # --- нижняя строка статуса ---
    footer = tk.Frame(container, bg=BG)
    footer.pack(fill=tk.X, pady=(10, 0))

    status_dot = tk.Label(footer, text="●", bg=BG, fg=STATUS_READY, font=(FONT, 9))
    status_dot.pack(side=tk.LEFT)

    status_label = tk.Label(
        footer, text="Готов", bg=BG, fg=MUTED, font=(FONT, 9), anchor="w"
    )
    status_label.pack(side=tk.LEFT, padx=(5, 0))

    count_label = tk.Label(
        footer, text="", bg=BG, fg=MUTED, font=(FONT, 9), anchor="e"
    )
    count_label.pack(side=tk.RIGHT)

    root.bind("<Control-KeyPress>", on_ctrl_v)
    status_label.after(100, poll_results)


def main():
    enable_dpi_awareness()

    root = tk.Tk()
    root.withdraw()

    tesseract_cmd = find_tesseract()
    if not tesseract_cmd:
        messagebox.showerror("Tesseract не найден", TESSERACT_HINT, parent=root)
        root.destroy()
        return

    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    build_gui(root)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
