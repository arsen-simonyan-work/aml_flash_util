import os
import re
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext
from tkinter import ttk

# Путь к утилите aml-burn-tool
AML_BURN_TOOL = "/home/user/aml_flash_util/aml-flash-tool/aml-burn-tool"

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


# ----------------------------- UI helpers -----------------------------

def run_on_ui(callback):
    root.after(0, callback)


def update_log(message):
    def _update():
        log_text.insert(tk.END, message + "\n")
        log_text.see(tk.END)

    run_on_ui(_update)


def update_progress(percent):
    percent = max(0, min(100, int(percent)))

    def _update():
        progress_bar["value"] = percent
        label_status_progress.config(text=f"⏳ Прошивка... {percent}%", fg="blue")

    run_on_ui(_update)


def update_status(message, color="black"):
    def _update():
        label_status_progress.config(text=message, fg=color)

    run_on_ui(_update)


def set_flash_controls(is_running):
    def _update():
        button_flash.config(state="disabled" if is_running else "normal")
        button_select_file.config(state="disabled" if is_running else "normal")
        combo_profile.config(state="disabled" if is_running else "readonly")
        check_skip_usb.config(state="disabled" if is_running else "normal")
        check_legacy.config(state="disabled" if is_running else "normal")

    run_on_ui(_update)


# ----------------------------- Detection -----------------------------

def clean_line(line):
    return ANSI_ESCAPE_RE.sub("", line).strip()


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
        label_detected_profile.config(text="Профиль: файл ещё не выбран", fg="gray")
        return

    board, legacy_mode, reason = resolve_profile(image_path)

    if board is None:
        label_detected_profile.config(
            text="Профиль не определён. Выберите VIM вручную.",
            fg="red",
        )
        return

    legacy_text = "legacy S912" if legacy_mode else "normal"
    label_detected_profile.config(
        text=f"Профиль: {board}, режим завершения: {legacy_text} ({reason})",
        fg="green",
    )


def on_profile_changed(_event=None):
    update_detected_profile_label()


# ----------------------------- Device / file -----------------------------

def check_device():
    result = subprocess.run(
        ["lsusb"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if "1b8e:" in result.stdout:
        label_status.config(text="✅ Устройство Amlogic найдено!", fg="green")
        button_flash.config(state="normal")
    else:
        label_status.config(text="❌ Устройство НЕ найдено!", fg="red")
        button_flash.config(state="disabled")


def select_image():
    file_path = filedialog.askopenfilename(
        title="Выберите прошивку",
        filetypes=[("Firmware files", "*.img"), ("All files", "*")],
    )

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

    if not os.path.isfile(image_path):
        update_status("❌ Ошибка: файл прошивки не найден!", "red")
        return

    board, legacy_mode, reason = resolve_profile(image_path)

    if board is None:
        update_status("❌ Не удалось определить VIM-профиль. Выберите VIM вручную.", "red")
        return

    if not os.path.isfile(AML_BURN_TOOL):
        update_status(f"❌ Не найден aml-burn-tool: {AML_BURN_TOOL}", "red")
        return

    with flash_lock:
        if flash_running:
            update_status("⚠️ Прошивка уже запущена.", "orange")
            return
        flash_running = True

    log_text.delete("1.0", tk.END)
    progress_bar["value"] = 0
    set_flash_controls(True)

    update_log("🚀 Начинаем прошивку...")
    update_log(f"📦 Файл: {image_path}")
    update_log(f"🔧 Профиль: {board}")
    update_log(f"ℹ️ Причина выбора: {reason}")
    update_log(f"🧩 Режим завершения: {'legacy S912' if legacy_mode else 'normal'}")

    command = ["pkexec", AML_BURN_TOOL, "-b", board]

    if skip_usb_check_var.get():
        command.append("-s")
        update_log("🔌 Используется ключ -s: предварительная USB-проверка пропущена.")

    command.extend(["-i", image_path])
    update_log("▶️ Команда: " + " ".join(command))
    update_status("⏳ Идет прошивка...", "blue")

    def run_flash():
        global flash_process, flash_running

        system_partition_ok = False
        legacy_finish_reported = False
        was_interrupted_prompt = False
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

root = tk.Tk()
root.title("Amlogic USB Flash Tool")
root.geometry("760x680")

main_frame = tk.Frame(root)
main_frame.pack(fill="both", expand=True, padx=12, pady=10)

# Проверка устройства
button_check = tk.Button(main_frame, text="Проверить устройство", command=check_device)
button_check.pack(pady=5)

label_status = tk.Label(main_frame, text="🔍 Нажмите 'Проверить устройство'", fg="blue")
label_status.pack(pady=5)

# Файл прошивки
file_frame = tk.Frame(main_frame)
file_frame.pack(fill="x", pady=5)

tk.Label(file_frame, text="Файл прошивки:").pack(anchor="w")

path_frame = tk.Frame(file_frame)
path_frame.pack(fill="x")

entry_path = tk.Entry(path_frame)
entry_path.pack(side="left", fill="x", expand=True, padx=(0, 6))

button_select_file = tk.Button(path_frame, text="Выбрать файл", command=select_image)
button_select_file.pack(side="right")

# Профиль устройства
profile_frame = tk.LabelFrame(main_frame, text="Профиль устройства")
profile_frame.pack(fill="x", pady=8)

profile_var = tk.StringVar(value=PROFILE_AUTO)
combo_profile = ttk.Combobox(
    profile_frame,
    textvariable=profile_var,
    values=PROFILE_OPTIONS,
    state="readonly",
    width=42,
)
combo_profile.pack(anchor="w", padx=8, pady=5)
combo_profile.bind("<<ComboboxSelected>>", on_profile_changed)

legacy_var = tk.BooleanVar(value=False)
check_legacy = tk.Checkbutton(
    profile_frame,
    text="Legacy завершение: после system [OK] считать S912 запись завершённой при долгом молчании",
    variable=legacy_var,
    command=update_detected_profile_label,
)
check_legacy.pack(anchor="w", padx=8, pady=2)

skip_usb_check_var = tk.BooleanVar(value=True)
check_skip_usb = tk.Checkbutton(
    profile_frame,
    text="Использовать -s: пропустить предварительную USB-проверку",
    variable=skip_usb_check_var,
)
check_skip_usb.pack(anchor="w", padx=8, pady=2)

label_detected_profile = tk.Label(profile_frame, text="Профиль: файл ещё не выбран", fg="gray")
label_detected_profile.pack(anchor="w", padx=8, pady=5)

# Логи
log_text = scrolledtext.ScrolledText(main_frame, height=11, width=90, state="normal")
log_text.pack(fill="both", expand=True, pady=8)

# Статус и прогресс
label_status_progress = tk.Label(main_frame, text="⏳ Ожидание команды прошивки...", fg="black")
label_status_progress.pack(pady=5)

progress_bar = ttk.Progressbar(main_frame, orient="horizontal", length=600, mode="determinate")
progress_bar.pack(fill="x", pady=5)

button_flash = tk.Button(
    main_frame,
    text="Прошить устройство",
    command=flash_image,
    bg="green",
    fg="white",
    state="disabled",
    height=2,
)
button_flash.pack(pady=10)

root.mainloop()
