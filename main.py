import os
import re
import shutil
import subprocess
import sys
import threading
import textwrap
import time
import tkinter as tk
from pathlib import Path

try:
    import customtkinter as ctk
except ImportError as exc:
    raise SystemExit(
        "customtkinter is required. Install dependencies with: "
        "python3 -m pip install -r requirements.txt"
    ) from exc

from app_paths import get_resource_path
from custom_file_browser import CompactFileBrowserDialog
from version import APP_NAME, APP_WM_CLASS, __version__

# Для Linux сначала ищем backend рядом с приложением/репозиторием,
# затем используем установленный в системе aml-burn-tool.
AML_BURN_TOOL = get_resource_path("aml-flash-tool", "aml-burn-tool")
AML_BURN_TOOL_FALLBACK = Path("/usr/local/bin/aml-burn-tool")
APP_ICON_PATH = get_resource_path("assets", "icons", "app-icon.png")

# Для старых S912 образов aml-flash-tool может записать system partition,
# но не завершить процесс штатно. В этом режиме после system [OK]
# и отсутствия нового вывода несколько минут показываем пользователю,
# что запись, вероятно, завершена.
LEGACY_STALL_SECONDS = 180

ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

PROFILE_AUTO = "Auto по имени файла"
PROFILE_S912 = "S912 / GXM -> VIM2 (legacy)"
PROFILE_S905W2 = "S905W2 / AP201 -> VIM4"
PROFILE_VIM1 = "VIM1"
PROFILE_VIM2 = "VIM2"
PROFILE_VIM3 = "VIM3"
PROFILE_VIM4 = "VIM4"

PROFILE_OPTIONS = [
    PROFILE_AUTO,
    PROFILE_S912,
    PROFILE_S905W2,
    PROFILE_VIM1,
    PROFILE_VIM2,
    PROFILE_VIM3,
    PROFILE_VIM4,
]

# Глобальное состояние процесса прошивки
flash_process = None
flash_lock = threading.Lock()
flash_running = False

COLOR_TEXT = "#e5eef6"
COLOR_MUTED = "#94a3b8"
COLOR_BLUE = "#60a5fa"
COLOR_GREEN = "#4ade80"
COLOR_RED = "#f87171"
COLOR_ORANGE = "#f59e0b"
COLOR_PANEL = "#111827"
COLOR_PANEL_ALT = "#0b1220"
COLOR_BORDER = "#22314d"
COLOR_ACCENT = "#22c55e"
COLOR_ACCENT_HOVER = "#16a34a"
COLOR_ACCENT_TEXT = "#052e16"
COLOR_DISABLED_BG = "#1e293b"
COLOR_DISABLED_TEXT = "#7c8aa5"

SUDO_DIALOG_WIDTH = 420
SUDO_DIALOG_HEIGHT = 220


def ui_color(color_name):
    palette = {
        "black": COLOR_TEXT,
        "blue": COLOR_BLUE,
        "green": COLOR_GREEN,
        "red": COLOR_RED,
        "orange": COLOR_ORANGE,
        "gray": COLOR_MUTED,
    }
    return palette.get(color_name, color_name)


def wrap_ui_text(text, width=40):
    return textwrap.fill(text, width=width)


def ensure_valid_cwd():
    try:
        Path.cwd()
        return
    except FileNotFoundError:
        pass

    for candidate in (Path.home(), Path(__file__).resolve().parent):
        if candidate.is_dir():
            os.chdir(candidate)
            return


def get_dialog_initial_dir():
    entry_value = entry_path.get().strip() if "entry_path" in globals() else ""
    if entry_value:
        candidate = Path(entry_value).expanduser()
        if candidate.is_file():
            candidate = candidate.parent
        if candidate.is_dir():
            return str(candidate)

    for candidate in (Path.home(), Path(__file__).resolve().parent):
        if candidate.is_dir():
            return str(candidate)

    return "/"


def apply_window_identity():
    if APP_ICON_PATH.is_file():
        try:
            icon_image = tk.PhotoImage(file=str(APP_ICON_PATH))
            root.iconphoto(True, icon_image)
            root._app_icon_image = icon_image
        except tk.TclError:
            pass


# ----------------------------- UI helpers -----------------------------

def run_on_ui(callback):
    root.after(0, callback)


def update_log(message):
    def _update():
        log_text.insert("end", message + "\n")
        log_text.see("end")

    run_on_ui(_update)


def update_progress(percent):
    percent = max(0, min(100, int(percent)))

    def _update():
        progress_bar.set(percent / 100)
        label_status_progress.configure(
            text=f"⏳ Прошивка... {percent}%",
            text_color=COLOR_BLUE,
        )

    run_on_ui(_update)


def update_status(message, color="black"):
    def _update():
        label_status_progress.configure(text=message, text_color=ui_color(color))

    run_on_ui(_update)


def set_flash_controls(is_running):
    def _update():
        widget_state = "disabled" if is_running else "normal"
        combo_state = "disabled" if is_running else "readonly"

        if is_running:
            button_flash.configure(
                state="disabled",
                fg_color=COLOR_DISABLED_BG,
                hover_color=COLOR_DISABLED_BG,
                text_color=COLOR_DISABLED_TEXT,
            )
        else:
            button_flash.configure(
                state="normal",
                fg_color=COLOR_ACCENT,
                hover_color=COLOR_ACCENT_HOVER,
                text_color=COLOR_ACCENT_TEXT,
            )
        button_select_file.configure(state=widget_state)
        combo_profile.configure(state=combo_state)
        check_skip_usb.configure(state=widget_state)
        check_legacy.configure(state=widget_state)

    run_on_ui(_update)


def ask_sudo_password():
    password_window = ctk.CTkToplevel(root)
    password_window.title("Sudo пароль")
    password_window.geometry(f"{SUDO_DIALOG_WIDTH}x{SUDO_DIALOG_HEIGHT}")
    password_window.resizable(False, False)
    password_window.transient(root)
    password_window.configure(fg_color=COLOR_PANEL)
    password_window.lift()
    password_window.attributes("-topmost", True)
    password_window.protocol("WM_DELETE_WINDOW", lambda: on_cancel())
    password_window.grid_columnconfigure((0, 1), weight=1)

    password_var = tk.StringVar()
    result = {"password": None}

    def on_ok(_event=None):
        result["password"] = password_var.get().strip()
        if password_window.winfo_exists():
            password_window.grab_release()
            password_window.destroy()

    def on_cancel(_event=None):
        if password_window.winfo_exists():
            password_window.grab_release()
            password_window.destroy()

    ctk.CTkLabel(
        password_window,
        text="Для прошивки устройства нужны права sudo.",
        font=section_title_font,
        text_color=COLOR_TEXT,
        wraplength=360,
        justify="center",
    ).grid(row=0, column=0, columnspan=2, padx=20, pady=(24, 10), sticky="ew")

    ctk.CTkLabel(
        password_window,
        text="Пароль используется только для текущего запуска aml-burn-tool.",
        font=body_font,
        text_color=COLOR_MUTED,
        wraplength=360,
        justify="center",
    ).grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 14), sticky="ew")

    password_entry = ctk.CTkEntry(
        password_window,
        textvariable=password_var,
        show="*",
        height=40,
        corner_radius=10,
        fg_color=COLOR_PANEL_ALT,
        border_color=COLOR_BORDER,
        text_color=COLOR_TEXT,
    )
    password_entry.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 18), sticky="ew")
    password_entry.bind("<Return>", on_ok)
    password_entry.bind("<KP_Enter>", on_ok)

    ctk.CTkButton(
        password_window,
        text="Отмена",
        height=38,
        corner_radius=10,
        fg_color="#243244",
        hover_color="#334155",
        text_color=COLOR_TEXT,
        command=on_cancel,
    ).grid(row=3, column=0, padx=(20, 10), pady=(0, 20), sticky="ew")

    ctk.CTkButton(
        password_window,
        text="Продолжить",
        height=38,
        corner_radius=10,
        fg_color=COLOR_ACCENT,
        hover_color=COLOR_ACCENT_HOVER,
        text_color=COLOR_ACCENT_TEXT,
        command=on_ok,
    ).grid(row=3, column=1, padx=(10, 20), pady=(0, 20), sticky="ew")

    password_window.bind("<Escape>", on_cancel)
    password_window.after(120, password_entry.focus_set)
    password_window.after(180, lambda: password_window.attributes("-topmost", False))
    password_window.grab_set()
    root.wait_window(password_window)
    return result["password"] or None


# ----------------------------- Detection -----------------------------

def clean_line(line):
    return ANSI_ESCAPE_RE.sub("", line).strip()


def resolve_aml_burn_tool():
    candidates = [AML_BURN_TOOL, AML_BURN_TOOL_FALLBACK]

    which_tool = shutil.which("aml-burn-tool")
    if which_tool:
        candidates.append(Path(which_tool))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return None


def build_flash_tool_command(aml_burn_tool, board, image_path, skip_usb_check):
    tool_command = [aml_burn_tool, "-b", board]
    if skip_usb_check:
        tool_command.append("-s")
    tool_command.extend(["-i", image_path])
    return tool_command


def detect_board_from_image(image_path):
    """
    Возвращает tuple: (board, legacy_mode, reason)
    board: VIM1/VIM2/VIM3/VIM4 или None
    legacy_mode: True для S912, где возможен завис после system [OK]
    """
    name = os.path.basename(image_path).upper()

    # Важно: SMOTRESHKA не используем как признак.
    # Это слово может быть и в S912, и в S905W2 образах.
    if "S905W2" in name or "AP201" in name:
        return "VIM4", False, "по имени файла найдено S905W2/AP201"

    if "S912" in name or "GXM" in name:
        return "VIM2", True, "по имени файла найдено S912/GXM"

    return None, False, "по имени файла профиль не определён"


def resolve_profile(image_path):
    selected_profile = profile_var.get()

    if selected_profile == PROFILE_AUTO:
        return detect_board_from_image(image_path)

    if selected_profile == PROFILE_S912:
        return "VIM2", True, "выбран профиль S912/GXM / VIM2"

    if selected_profile == PROFILE_S905W2:
        return "VIM4", False, "выбран профиль S905W2 / AP201 / VIM4"

    if selected_profile in [PROFILE_VIM1, PROFILE_VIM2, PROFILE_VIM3, PROFILE_VIM4]:
        return selected_profile, legacy_var.get(), f"выбран ручной профиль {selected_profile}"

    return None, False, "профиль не выбран"


def update_detected_profile_label():
    image_path = entry_path.get().strip()

    if not image_path:
        label_detected_profile.configure(
            text=wrap_ui_text("Профиль: файл ещё не выбран"),
            text_color=COLOR_MUTED,
        )
        return

    board, legacy_mode, reason = resolve_profile(image_path)

    if board is None:
        label_detected_profile.configure(
            text=wrap_ui_text("Профиль не определён. Выберите VIM вручную."),
            text_color=COLOR_RED,
        )
        return

    legacy_text = "legacy S912" if legacy_mode else "normal"
    label_detected_profile.configure(
        text=wrap_ui_text(
            f"Профиль: {board}, режим завершения: {legacy_text} ({reason})"
        ),
        text_color=COLOR_GREEN,
    )


def on_profile_changed(_event=None):
    update_detected_profile_label()


def check_device():
    try:
        result = subprocess.run(
            ["lsusb"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        label_status.configure(
            text="❌ Не найден lsusb. Установите пакет usbutils.",
            text_color=COLOR_RED,
        )
        button_flash.configure(state="disabled")
        return

    if "1b8e:" in result.stdout:
        label_status.configure(
            text="✅ Устройство Amlogic найдено!",
            text_color=COLOR_GREEN,
        )
        if not flash_running:
            button_flash.configure(
                state="normal",
                fg_color=COLOR_ACCENT,
                hover_color=COLOR_ACCENT_HOVER,
                text_color=COLOR_ACCENT_TEXT,
            )
    else:
        label_status.configure(
            text="❌ Устройство НЕ найдено!",
            text_color=COLOR_RED,
        )
        button_flash.configure(
            state="disabled",
            fg_color=COLOR_DISABLED_BG,
            hover_color=COLOR_DISABLED_BG,
            text_color=COLOR_DISABLED_TEXT,
        )


def select_image():
    ensure_valid_cwd()
    file_path = CompactFileBrowserDialog(
        root,
        initial_dir=get_dialog_initial_dir(),
        title="Выберите прошивку",
        icon_path=APP_ICON_PATH,
        allowed_extensions={".img"},
        body_font=body_font,
        button_font=button_font,
        theme={
            "panel": COLOR_PANEL,
            "panel_alt": "#0f1a2b",
            "surface": COLOR_PANEL_ALT,
            "border": COLOR_BORDER,
            "text": COLOR_TEXT,
            "accent": COLOR_ACCENT,
            "accent_hover": COLOR_ACCENT_HOVER,
            "accent_text": COLOR_ACCENT_TEXT,
            "disabled_bg": COLOR_DISABLED_BG,
            "disabled_text": COLOR_DISABLED_TEXT,
            "item_hover": "#122033",
            "secondary_button": "#243244",
            "secondary_button_hover": "#334155",
        },
    ).show()

    if not file_path:
        return

    entry_path.delete(0, tk.END)
    entry_path.insert(0, file_path)

    # Если выбран Auto — сразу показываем, что определилось.
    update_detected_profile_label()


# ----------------------------- Progress parsing -----------------------------

def extract_progress(line):
    match = re.search(r"%(\d{1,3})\.\.", line)
    if match:
        return int(match.group(1))

    # У aml-flash-tool часто нет процентов, поэтому ставим примерный прогресс по этапам.
    step_progress = [
        ("Burning image", 1),
        ("Rebooting the board", 5),
        ("Unpacking image", 10),
        ("Initializing ddr", 15),
        ("Running u-boot", 20),
        ("Create partitions", 30),
        ("Writing device tree", 35),
        ("Writing bootloader", 45),
        ("Wiping  data", 50),
        ("Wiping data", 50),
        ("Wiping  cache", 55),
        ("Wiping cache", 55),
        ("Writing boot partition", 65),
        ("Writing logo partition", 70),
        ("Writing recovery partition", 75),
        ("Writing system partition", 95),
    ]

    for marker, percent in step_progress:
        if marker in line:
            return percent

    return None


def is_ok_line_for_step(line, step_name):
    return step_name in line and "[OK]" in line


# ----------------------------- Flashing -----------------------------

def flash_image():
    global flash_running

    image_path = entry_path.get().strip()
    aml_burn_tool = resolve_aml_burn_tool()

    if not os.path.isfile(image_path):
        update_status("❌ Ошибка: файл прошивки не найден!", "red")
        return

    board, legacy_mode, reason = resolve_profile(image_path)

    if board is None:
        update_status("❌ Не удалось определить VIM-профиль. Выберите VIM вручную.", "red")
        return

    if aml_burn_tool is None:
        update_status(
            "❌ Не найден aml-burn-tool рядом с приложением или в /usr/local/bin.",
            "red",
        )
        return

    sudo_password = None
    needs_sudo = os.name == "posix" and os.geteuid() != 0
    if needs_sudo:
        sudo_password = ask_sudo_password()
        if not sudo_password:
            update_status("⚠️ Пароль sudo не введён. Прошивка отменена.", "orange")
            return

    with flash_lock:
        if flash_running:
            update_status("⚠️ Прошивка уже запущена.", "orange")
            return
        flash_running = True

    log_text.delete("1.0", "end")
    progress_bar.set(0)
    set_flash_controls(True)

    update_log("🚀 Начинаем прошивку...")
    update_log(f"📦 Файл: {image_path}")
    update_log(f"🔧 Профиль: {board}")
    update_log(f"ℹ️ Причина выбора: {reason}")
    update_log(f"🧩 Режим завершения: {'legacy S912' if legacy_mode else 'normal'}")

    skip_usb_check = skip_usb_check_var.get()
    tool_command = build_flash_tool_command(
        aml_burn_tool=aml_burn_tool,
        board=board,
        image_path=image_path,
        skip_usb_check=skip_usb_check,
    )
    command = tool_command
    if needs_sudo:
        command = ["sudo", "-S", "-k", "-p", "", *tool_command]
        update_log("🔐 Используется встроенная sudo-авторизация приложения.")

    if skip_usb_check:
        update_log("🔌 Используется ключ -s: предварительная USB-проверка пропущена.")

    update_log("▶️ Команда: " + " ".join(command))
    update_status("⏳ Идет прошивка...", "blue")

    def run_flash():
        global flash_process, flash_running

        system_partition_ok = False
        legacy_finish_reported = False
        was_interrupted_prompt = False
        sudo_auth_failed = False
        last_output_time = time.monotonic()

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            with flash_lock:
                flash_process = process

            if needs_sudo and process.stdin is not None:
                process.stdin.write(f"{sudo_password}\n")
                process.stdin.flush()

            def watchdog():
                nonlocal legacy_finish_reported

                while process.poll() is None:
                    time.sleep(1)

                    if not legacy_mode:
                        continue

                    if not system_partition_ok or legacy_finish_reported:
                        continue

                    idle_seconds = time.monotonic() - last_output_time

                    if idle_seconds >= LEGACY_STALL_SECONDS:
                        legacy_finish_reported = True
                        update_progress(100)
                        update_log(
                            "✅ Legacy S912: system partition уже записан, "
                            "а aml-flash-tool долго не выводит новых строк."
                        )
                        update_log(
                            "ℹ️ Для этого режима можно отключить USB, "
                            "отключить питание на 10 секунд и включить устройство."
                        )
                        update_status(
                            "✅ Запись, вероятно, завершена. Отключите USB и перезапустите питание.",
                            "green",
                        )
                        break

            threading.Thread(target=watchdog, daemon=True).start()

            for raw_line in process.stdout:
                last_output_time = time.monotonic()
                line = clean_line(raw_line)

                if not line:
                    continue

                update_log(line)

                if (
                    "Sorry, try again." in line
                    or "sudo: no password was provided" in line
                    or "incorrect password attempt" in line
                ):
                    sudo_auth_failed = True

                progress = extract_progress(line)
                if progress is not None:
                    update_progress(progress)

                if is_ok_line_for_step(line, "Writing system partition"):
                    system_partition_ok = True
                    update_status("✅ System partition записан. Ожидаем завершение tool...", "green")

                if "Do you want to reset the board" in line:
                    was_interrupted_prompt = True
                    update_log(
                        "⚠️ Tool получил прерывание и спрашивает reset. "
                        "Это не признак штатного завершения. Отвечаем: n"
                    )
                    try:
                        process.stdin.write("n\n")
                        process.stdin.flush()
                    except Exception as exc:
                        update_log(f"⚠️ Не удалось отправить ответ n: {exc}")

            process.wait()

            if process.returncode == 0:
                update_progress(100)
                update_status("✅ Прошивка завершена успешно!", "green")
            elif sudo_auth_failed:
                update_status("❌ Неверный sudo-пароль или доступ отклонён.", "red")
            elif legacy_finish_reported:
                # Для S912 это ожидаемый практический сценарий.
                update_status(
                    "✅ Legacy S912: запись завершена практически. Перезапустите питание устройства.",
                    "green",
                )
            elif was_interrupted_prompt:
                update_status(
                    "⚠️ Процесс был прерван. Проверьте загрузку устройства после перезапуска питания.",
                    "orange",
                )
            else:
                update_status(f"❌ Ошибка прошивки, код выхода: {process.returncode}", "red")

        except FileNotFoundError as exc:
            update_status(f"❌ Не удалось запустить команду: {exc}", "red")
        except Exception as exc:
            update_status(f"❌ Ошибка прошивки: {exc}", "red")
        finally:
            with flash_lock:
                flash_process = None
                flash_running = False

            set_flash_controls(False)

    threading.Thread(target=run_flash, daemon=True).start()


# ----------------------------- GUI -----------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")
ctk.set_widget_scaling(1.0)
ctk.set_window_scaling(1.0)

ensure_valid_cwd()

root = ctk.CTk(className=APP_WM_CLASS)
root.title(f"{APP_NAME} {__version__}")
root.geometry("1120x720")
root.minsize(920, 660)
root.configure(fg_color=COLOR_PANEL)
try:
    root.tk.call("tk", "scaling", 1.0)
except tk.TclError:
    pass
root.grid_columnconfigure(0, weight=1)
root.grid_rowconfigure(0, weight=1)

section_title_font = ctk.CTkFont(family="DejaVu Sans", size=14, weight="bold")
body_font = ctk.CTkFont(family="DejaVu Sans", size=11)
button_font = ctk.CTkFont(family="DejaVu Sans", size=11, weight="bold")
mono_font = ctk.CTkFont(family="DejaVu Sans Mono", size=10)

content_frame = ctk.CTkFrame(root, fg_color="transparent")
content_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
content_frame.grid_columnconfigure(0, weight=0)
content_frame.grid_columnconfigure(1, weight=1)
content_frame.grid_rowconfigure(0, weight=1)

sidebar = ctk.CTkFrame(
    content_frame,
    width=376,
    corner_radius=12,
    fg_color=COLOR_PANEL,
    border_width=1,
    border_color=COLOR_BORDER,
)
sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
sidebar.grid_columnconfigure(0, weight=1)

device_card = ctk.CTkFrame(sidebar, fg_color="#0f1a2b", corner_radius=10)
device_card.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
device_card.grid_columnconfigure(0, weight=1)

device_head = ctk.CTkFrame(device_card, fg_color="transparent")
device_head.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
device_head.grid_columnconfigure(0, weight=1)

ctk.CTkLabel(
    device_head,
    text="Статус устройства",
    font=section_title_font,
    text_color=COLOR_TEXT,
).grid(row=0, column=0, sticky="w")

button_check = ctk.CTkButton(
    device_head,
    text="Проверить",
    command=check_device,
    width=118,
    height=34,
    corner_radius=10,
    fg_color=COLOR_ACCENT,
    hover_color=COLOR_ACCENT_HOVER,
    text_color=COLOR_ACCENT_TEXT,
    font=button_font,
)
button_check.grid(row=0, column=1, sticky="e")

label_status = ctk.CTkLabel(
    device_card,
    text=wrap_ui_text("Проверьте USB-подключение.", width=38),
    font=body_font,
    text_color=COLOR_BLUE,
    justify="left",
)
label_status.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 12))

file_card = ctk.CTkFrame(sidebar, fg_color="#0f1a2b", corner_radius=10)
file_card.grid(row=1, column=0, sticky="ew", padx=12, pady=8)
file_card.grid_columnconfigure(0, weight=1)

ctk.CTkLabel(
    file_card,
    text="Файл прошивки",
    font=section_title_font,
    text_color=COLOR_TEXT,
).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))

entry_path = ctk.CTkEntry(
    file_card,
    height=38,
    corner_radius=10,
    placeholder_text="Выберите .img файл",
    fg_color="#0b1220",
    border_color=COLOR_BORDER,
    text_color=COLOR_TEXT,
)
entry_path.grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=(0, 12))

button_select_file = ctk.CTkButton(
    file_card,
    text="Обзор",
    command=select_image,
    width=96,
    height=36,
    corner_radius=10,
    fg_color=COLOR_ACCENT,
    hover_color=COLOR_ACCENT_HOVER,
    text_color=COLOR_ACCENT_TEXT,
    font=button_font,
)
button_select_file.grid(row=1, column=1, padx=(0, 12), pady=(0, 12))

profile_card = ctk.CTkFrame(sidebar, fg_color="#0f1a2b", corner_radius=10)
profile_card.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
profile_card.grid_columnconfigure(0, weight=1)

ctk.CTkLabel(
    profile_card,
    text="Профиль устройства",
    font=section_title_font,
    text_color=COLOR_TEXT,
).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

profile_var = tk.StringVar(value=PROFILE_AUTO)
combo_profile = ctk.CTkComboBox(
    profile_card,
    variable=profile_var,
    values=PROFILE_OPTIONS,
    state="readonly",
    height=38,
    corner_radius=10,
    command=on_profile_changed,
    fg_color="#0b1220",
    border_color=COLOR_BORDER,
    button_color=COLOR_ACCENT,
    button_hover_color=COLOR_ACCENT_HOVER,
    dropdown_fg_color="#0f172a",
    dropdown_hover_color="#1e293b",
    dropdown_text_color=COLOR_TEXT,
    text_color=COLOR_TEXT,
)
combo_profile.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))

legacy_row = ctk.CTkFrame(profile_card, fg_color="transparent")
legacy_row.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
legacy_row.grid_columnconfigure(1, weight=1)

legacy_var = tk.BooleanVar(value=False)
check_legacy = ctk.CTkCheckBox(
    legacy_row,
    text="",
    width=22,
    variable=legacy_var,
    command=update_detected_profile_label,
    text_color=COLOR_TEXT,
    font=body_font,
    fg_color=COLOR_ACCENT,
    hover_color=COLOR_ACCENT_HOVER,
    checkmark_color=COLOR_ACCENT_TEXT,
)
check_legacy.grid(row=0, column=0, sticky="nw", pady=(2, 0))

ctk.CTkLabel(
    legacy_row,
    text=wrap_ui_text(
        "Legacy S912: считать запись завершённой после паузы по логу"
    ),
    font=body_font,
    text_color=COLOR_TEXT,
    justify="left",
).grid(row=0, column=1, sticky="w", padx=(10, 0))

skip_row = ctk.CTkFrame(profile_card, fg_color="transparent")
skip_row.grid(row=3, column=0, sticky="ew", padx=12, pady=4)
skip_row.grid_columnconfigure(1, weight=1)

skip_usb_check_var = tk.BooleanVar(value=True)
check_skip_usb = ctk.CTkCheckBox(
    skip_row,
    text="",
    width=22,
    variable=skip_usb_check_var,
    text_color=COLOR_TEXT,
    font=body_font,
    fg_color=COLOR_ACCENT,
    hover_color=COLOR_ACCENT_HOVER,
    checkmark_color=COLOR_ACCENT_TEXT,
)
check_skip_usb.grid(row=0, column=0, sticky="nw", pady=(2, 0))

ctk.CTkLabel(
    skip_row,
    text=wrap_ui_text("Использовать -s: пропустить USB-проверку"),
    font=body_font,
    text_color=COLOR_TEXT,
    justify="left",
).grid(row=0, column=1, sticky="w", padx=(10, 0))

label_detected_profile = ctk.CTkLabel(
    profile_card,
    text=wrap_ui_text("Профиль: файл ещё не выбран", width=38),
    text_color=COLOR_MUTED,
    font=body_font,
    justify="left",
)
label_detected_profile.grid(row=4, column=0, sticky="w", padx=12, pady=(8, 12))

workspace = ctk.CTkFrame(
    content_frame,
    corner_radius=12,
    fg_color=COLOR_PANEL,
    border_width=1,
    border_color=COLOR_BORDER,
)
workspace.grid(row=0, column=1, sticky="nsew")
workspace.grid_columnconfigure(0, weight=1)
workspace.grid_rowconfigure(1, weight=1)

summary_card = ctk.CTkFrame(workspace, fg_color="#0f1a2b", corner_radius=10)
summary_card.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
summary_card.grid_columnconfigure(0, weight=1)

ctk.CTkLabel(
    summary_card,
    text="Сеанс прошивки",
    font=section_title_font,
    text_color=COLOR_TEXT,
).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 3))

label_status_progress = ctk.CTkLabel(
    summary_card,
    text="⏳ Ожидание команды прошивки...",
    font=body_font,
    text_color=COLOR_TEXT,
    justify="left",
)
label_status_progress.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))

progress_bar = ctk.CTkProgressBar(
    summary_card,
    height=10,
    corner_radius=100,
    progress_color=COLOR_ACCENT,
    fg_color="#1f2937",
)
progress_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
progress_bar.set(0)

log_card = ctk.CTkFrame(workspace, fg_color="#0f1a2b", corner_radius=10)
log_card.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
log_card.grid_columnconfigure(0, weight=1)
log_card.grid_rowconfigure(1, weight=1)

ctk.CTkLabel(
    log_card,
    text="Лог операции",
    font=section_title_font,
    text_color=COLOR_TEXT,
).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

log_text = ctk.CTkTextbox(
    log_card,
    corner_radius=10,
    fg_color="#09111d",
    border_width=1,
    border_color=COLOR_BORDER,
    text_color="#dbeafe",
    font=mono_font,
    activate_scrollbars=True,
    wrap="word",
)
log_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

action_bar = ctk.CTkFrame(workspace, fg_color="transparent")
action_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
action_bar.grid_columnconfigure(0, weight=1)

ctk.CTkLabel(
    action_bar,
    text="Используются sudo и aml-burn-tool.",
    font=body_font,
    text_color=COLOR_MUTED,
    justify="left",
).grid(row=0, column=0, sticky="w")

button_flash = ctk.CTkButton(
    action_bar,
    text="Прошить устройство",
    command=flash_image,
    state="disabled",
    width=210,
    height=40,
    corner_radius=10,
    fg_color=COLOR_DISABLED_BG,
    hover_color=COLOR_DISABLED_BG,
    text_color=COLOR_DISABLED_TEXT,
    font=button_font,
)
button_flash.grid(row=0, column=1, sticky="e")

update_detected_profile_label()
root.after(50, apply_window_identity)
root.mainloop()
