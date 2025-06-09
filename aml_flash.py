import os
import re
import tkinter as tk
from tkinter import filedialog, scrolledtext
from tkinter import ttk
import subprocess
import threading

# Определяем путь к утилите aml-burn-tool
AML_BURN_TOOL = "/home/user/aml_utils/aml-flash-tool/aml-burn-tool"  # Укажи свой путь


# Функция проверки устройства Amlogic
def check_device():
    result = subprocess.run("lsusb", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if "1b8e:" in result.stdout:  # ID устройств Amlogic начинается с 1b8e
        label_status.config(text="✅ Устройство Amlogic найдено!", fg="green")
        button_flash.config(state="normal")  # Разблокируем кнопку прошивки
    else:
        label_status.config(text="❌ Устройство НЕ найдено!", fg="red")
        button_flash.config(state="disabled")  # Блокируем кнопку прошивки


# Функция выбора файла
def select_image():
    file_path = filedialog.askopenfilename(title="Выберите прошивку",
                                           filetypes=[("Firmware files", "*.img")])
    if file_path:
        entry_path.delete(0, tk.END)
        entry_path.insert(0, file_path)


# Функция обновления логов
def update_log(message):
    log_text.insert(tk.END, message + "\n")
    log_text.see(tk.END)  # Автопрокрутка вниз


# Функция обновления прогресс-бара
def update_progress(percent):
    progress_bar["value"] = percent
    label_status_progress.config(text=f"⏳ Прошивка... {percent}%", fg="blue")
    root.update_idletasks()


# Функция обновления статуса прошивки
def update_status(message, color="black"):
    label_status_progress.config(text=message, fg=color)


# Функция извлечения процента из строки лога
def extract_progress(line):
    match = re.search(r"%(\d{1,3})\.\.", line)  # Ищем `%XX..`
    if match:
        percent = int(match.group(1))
        return percent
    return None


# Функция прошивки (выполняется в отдельном потоке)
def flash_image():
    image_path = entry_path.get()

    if not os.path.isfile(image_path):
        update_status("❌ Ошибка: Файл не найден!", "red")
        return

    update_log("🚀 Начинаем прошивку...")
    update_status("⏳ Идет прошивка...", "blue")
    progress_bar["value"] = 0  # Обнуляем прогресс

    # Запуск процесса в отдельном потоке
    def run_flash():
        #command = f"pkexec {AML_BURN_TOOL} -i {image_path}"
        command = f"pkexec {AML_BURN_TOOL} -b VIM4 -i {image_path}"
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        for line in process.stdout:
            line = line.strip()
            update_log(line)  # Выводим лог в текстовое поле

            # Проверяем, есть ли процент в строке
            progress = extract_progress(line)
            if progress is not None:
                update_progress(progress)

        process.wait()

        if process.returncode == 0:
            update_progress(100)
            update_status("✅ Прошивка завершена успешно!", "green")
        else:
            error_message = process.stderr.read()
            update_status(f"❌ Ошибка прошивки: {error_message}", "red")

    threading.Thread(target=run_flash, daemon=True).start()


# Создание GUI
root = tk.Tk()
root.title("Amlogic USB Flash Tool")
root.geometry("500x380")

# Кнопка проверки устройства
tk.Button(root, text="Проверить устройство", command=check_device).pack(pady=5)

# Статус устройства
label_status = tk.Label(root, text="🔍 Нажмите 'Проверить устройство'", fg="blue")
label_status.pack(pady=5)

# Поле ввода пути к файлу
tk.Label(root, text="Выберите файл прошивки:").pack(pady=5)
entry_path = tk.Entry(root, width=50)
entry_path.pack(pady=5)

# Кнопка выбора файла
tk.Button(root, text="Выбрать файл", command=select_image).pack(pady=5)

# Поле логов
log_text = scrolledtext.ScrolledText(root, height=3, width=60, state="normal")
log_text.pack(pady=5, padx=10)

# **Новый статус прошивки**
label_status_progress = tk.Label(root, text="⏳ Ожидание команды прошивки...", fg="black")
label_status_progress.pack(pady=5)

# Прогресс-бар
progress_bar = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
progress_bar.pack(pady=5)

# Кнопка запуска прошивки (по умолчанию отключена)
button_flash = tk.Button(root, text="Прошить устройство", command=flash_image, bg="green", fg="white", state="disabled")
button_flash.pack(pady=10)

# Запуск окна
root.mainloop()
