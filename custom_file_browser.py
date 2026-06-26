import os
import tkinter as tk
from math import ceil
from pathlib import Path

import customtkinter as ctk


DEFAULT_THEME = {
    "panel": "#111827",
    "panel_alt": "#0f1a2b",
    "surface": "#09111d",
    "border": "#22314d",
    "text": "#e5eef6",
    "accent": "#22c55e",
    "accent_hover": "#16a34a",
    "accent_text": "#052e16",
    "disabled_bg": "#1e293b",
    "disabled_text": "#7c8aa5",
    "item_hover": "#122033",
    "secondary_button": "#243244",
    "secondary_button_hover": "#334155",
}


class CompactFileBrowserDialog:
    def __init__(
        self,
        parent,
        initial_dir=None,
        title="Выберите файл",
        icon_path=None,
        show_hidden_default=False,
        allowed_extensions=None,
        body_font=None,
        button_font=None,
        theme=None,
        folder_icon="📁",
        file_icon="📄",
    ):
        self.parent = parent
        self.result = None
        self.entries = []
        self.item_buttons = []
        self.selected_index_value = None
        self.compact_columns = 0
        self.theme = dict(DEFAULT_THEME)
        if theme:
            self.theme.update(theme)

        self.folder_icon = folder_icon
        self.file_icon = file_icon
        self.allowed_extensions = {
            suffix.lower() for suffix in (allowed_extensions or [])
        } or None

        current_dir = Path(initial_dir).expanduser() if initial_dir else Path.home()
        if current_dir.is_file():
            current_dir = current_dir.parent
        if not current_dir.is_dir():
            current_dir = Path.home()
        self.current_dir = current_dir.resolve()

        default_body_font = ctk.CTkFont(family="DejaVu Sans", size=11)
        default_button_font = ctk.CTkFont(family="DejaVu Sans", size=11, weight="bold")
        self.body_font = body_font or default_body_font
        self.button_font = button_font or default_button_font
        self.show_hidden_var = tk.BooleanVar(value=show_hidden_default)

        self.window = ctk.CTkToplevel(parent)
        self.window.title(title)
        self.window.geometry(self.calculate_geometry())
        self.window.minsize(700, 480)
        self.window.configure(fg_color=self.theme["panel"])
        self.window.transient(parent)
        self.window.grab_set()
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(0, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda _event: self.cancel())
        self.window.bind("<Return>", self.on_activate)
        self.window.bind("<Configure>", self.on_window_resize, add="+")
        self.window.lift()

        if icon_path and Path(icon_path).is_file():
            try:
                icon_image = tk.PhotoImage(file=str(icon_path))
                self.window.iconphoto(True, icon_image)
                self.window._dialog_icon_image = icon_image
            except tk.TclError:
                pass

        shell = ctk.CTkFrame(
            self.window,
            fg_color=self.theme["panel"],
            border_width=1,
            border_color=self.theme["border"],
            corner_radius=12,
        )
        shell.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        top_bar = ctk.CTkFrame(
            shell,
            fg_color=self.theme["panel_alt"],
            corner_radius=10,
        )
        top_bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        top_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            top_bar,
            text="Home",
            width=72,
            height=32,
            corner_radius=10,
            command=self.go_home,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            text_color=self.theme["accent_text"],
            font=self.button_font,
        ).grid(row=0, column=0, padx=(10, 8), pady=10)

        self.path_entry = ctk.CTkEntry(
            top_bar,
            height=32,
            corner_radius=10,
            fg_color=self.theme["surface"],
            border_color=self.theme["border"],
            text_color=self.theme["text"],
        )
        self.path_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=10)

        ctk.CTkButton(
            top_bar,
            text="Вверх",
            width=72,
            height=32,
            corner_radius=10,
            command=self.go_up,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            text_color=self.theme["accent_text"],
            font=self.button_font,
        ).grid(row=0, column=2, padx=(0, 10), pady=10)

        body = ctk.CTkFrame(shell, fg_color=self.theme["panel_alt"], corner_radius=10)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.file_grid = ctk.CTkScrollableFrame(
            body,
            fg_color=self.theme["surface"],
            corner_radius=10,
            border_width=1,
            border_color=self.theme["border"],
        )
        self.file_grid.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        bottom_bar = ctk.CTkFrame(shell, fg_color=self.theme["panel_alt"], corner_radius=10)
        bottom_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        bottom_bar.grid_columnconfigure(1, weight=1)

        hidden_toggle = ctk.CTkCheckBox(
            bottom_bar,
            text="Показывать скрытые",
            variable=self.show_hidden_var,
            command=self.refresh_entries,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            checkmark_color=self.theme["accent_text"],
            text_color=self.theme["text"],
            font=self.body_font,
        )
        hidden_toggle.grid(row=0, column=0, padx=(10, 12), pady=10, sticky="w")

        self.selection_entry = ctk.CTkEntry(
            bottom_bar,
            height=34,
            corner_radius=10,
            fg_color=self.theme["surface"],
            border_color=self.theme["border"],
            text_color=self.theme["text"],
        )
        self.selection_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=10)

        self.open_button = ctk.CTkButton(
            bottom_bar,
            text="Открыть",
            width=94,
            height=34,
            corner_radius=10,
            state="disabled",
            command=self.confirm_selection,
            fg_color=self.theme["disabled_bg"],
            hover_color=self.theme["disabled_bg"],
            text_color=self.theme["disabled_text"],
            font=self.button_font,
        )
        self.open_button.grid(row=0, column=2, padx=(0, 8), pady=10)

        ctk.CTkButton(
            bottom_bar,
            text="Отмена",
            width=94,
            height=34,
            corner_radius=10,
            command=self.cancel,
            fg_color=self.theme["secondary_button"],
            hover_color=self.theme["secondary_button_hover"],
            text_color=self.theme["text"],
            font=self.button_font,
        ).grid(row=0, column=3, padx=(0, 10), pady=10)

        self.refresh_entries()
        self.window.focus_set()

    def calculate_geometry(self):
        self.parent.update_idletasks()
        screen_width = self.parent.winfo_screenwidth()
        screen_height = self.parent.winfo_screenheight()
        width = min(820, max(700, int(screen_width * 0.5)))
        height = min(550, max(480, int(screen_height * 0.5)))

        parent_width = max(self.parent.winfo_width(), 1)
        parent_height = max(self.parent.winfo_height(), 1)
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()

        x = parent_x + (parent_width - width) // 2
        y = parent_y + (parent_height - height) // 2
        x = max(24, min(x, screen_width - width - 24))
        y = max(24, min(y, screen_height - height - 24))
        return f"{width}x{height}+{x}+{y}"

    def set_path_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete(0, "end")
        widget.insert(0, text)
        widget.configure(state="readonly")

    def calculate_compact_columns(self):
        width = max(self.window.winfo_width(), 700)
        return max(2, min(4, width // 240))

    def on_window_resize(self, _event=None):
        if not self.entries:
            return
        columns = self.calculate_compact_columns()
        if columns != self.compact_columns:
            self.render_entries()

    def clear_grid(self):
        for widget in self.file_grid.winfo_children():
            widget.destroy()
        self.item_buttons = []

    def render_entries(self):
        self.clear_grid()
        self.compact_columns = self.calculate_compact_columns()
        item_count = len(self.entries)
        row_count = max(1, ceil(item_count / self.compact_columns))

        for column in range(self.compact_columns):
            self.file_grid.grid_columnconfigure(column, weight=1, uniform="files")

        for index, (is_dir, path) in enumerate(self.entries):
            icon = self.folder_icon if is_dir else self.file_icon
            button = ctk.CTkButton(
                self.file_grid,
                text=f"{icon}  {path.name}",
                anchor="w",
                height=28,
                corner_radius=8,
                border_width=1,
                border_color=self.theme["border"],
                fg_color="transparent",
                hover_color=self.theme["item_hover"],
                text_color=self.theme["text"],
                font=self.body_font,
                command=lambda idx=index: self.select_index(idx),
            )
            row = index % row_count
            column = index // row_count
            button.grid(row=row, column=column, sticky="ew", padx=4, pady=3)
            button.bind("<Double-Button-1>", lambda _event, idx=index: self.activate_index(idx))
            self.item_buttons.append(button)

        self.update_item_styles()

    def update_item_styles(self):
        for index, button in enumerate(self.item_buttons):
            if index == self.selected_index_value:
                button.configure(
                    fg_color=self.theme["accent"],
                    hover_color=self.theme["accent_hover"],
                    text_color=self.theme["accent_text"],
                    border_color=self.theme["accent"],
                )
            else:
                button.configure(
                    fg_color="transparent",
                    hover_color=self.theme["item_hover"],
                    text_color=self.theme["text"],
                    border_color=self.theme["border"],
                )

    def extension_allowed(self, entry):
        if self.allowed_extensions is None:
            return True
        return Path(entry.name).suffix.lower() in self.allowed_extensions

    def refresh_entries(self):
        try:
            iterator = list(os.scandir(self.current_dir))
        except OSError:
            return

        self.entries = []
        self.selected_index_value = None

        directories = []
        files = []

        for entry in iterator:
            if not self.show_hidden_var.get() and entry.name.lstrip().startswith("."):
                continue
            if entry.is_dir():
                directories.append(entry)
            elif entry.is_file() and self.extension_allowed(entry):
                files.append(entry)

        directories.sort(key=lambda item: item.name.lower())
        files.sort(key=lambda item: item.name.lower())

        for entry in directories:
            self.entries.append((True, Path(entry.path)))

        for entry in files:
            self.entries.append((False, Path(entry.path)))

        self.render_entries()
        self.set_path_text(self.path_entry, str(self.current_dir))
        self.set_path_text(self.selection_entry, "")
        self.disable_open()

    def disable_open(self):
        self.open_button.configure(
            state="disabled",
            fg_color=self.theme["disabled_bg"],
            hover_color=self.theme["disabled_bg"],
            text_color=self.theme["disabled_text"],
        )

    def enable_open(self):
        self.open_button.configure(
            state="normal",
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_hover"],
            text_color=self.theme["accent_text"],
        )

    def selected_index(self):
        return self.selected_index_value

    def select_index(self, index):
        self.selected_index_value = index
        self.update_item_styles()

        is_dir, path = self.entries[index]
        self.set_path_text(self.selection_entry, path.name)
        if is_dir:
            self.disable_open()
        else:
            self.enable_open()

    def activate_index(self, index=None):
        if index is not None:
            self.selected_index_value = index
            self.update_item_styles()

        index = self.selected_index()
        if index is None:
            return

        is_dir, path = self.entries[index]
        if is_dir:
            self.current_dir = path
            self.refresh_entries()
        else:
            self.result = str(path)
            self.window.destroy()

    def on_activate(self, _event=None):
        self.activate_index()

    def confirm_selection(self):
        index = self.selected_index()
        if index is None:
            return

        is_dir, path = self.entries[index]
        if is_dir:
            self.current_dir = path
            self.refresh_entries()
            return

        self.result = str(path)
        self.window.destroy()

    def go_home(self):
        self.current_dir = Path.home()
        self.refresh_entries()

    def go_up(self):
        parent = self.current_dir.parent
        if parent != self.current_dir:
            self.current_dir = parent
            self.refresh_entries()

    def cancel(self):
        self.result = None
        self.window.destroy()

    def show(self):
        self.parent.wait_window(self.window)
        return self.result
