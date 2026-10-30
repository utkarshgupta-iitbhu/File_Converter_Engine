"""File Converter Engine desktop application (Python + CustomTkinter)."""
import os
import sys
import queue
import threading
import subprocess
import webbrowser
import argparse
import tempfile
import zipfile
import multiprocessing
from pathlib import Path
import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES

from core.router import FileRouter
from core.py_converters import (
    convert_image, convert_media, convert_data, convert_document,
    get_output_path, package_to_zip, unique_path,
)
from core.context_menu import add_to_registry, remove_from_registry, refresh_registry, registry_status
from core.archive_utils import extract_supported_zip
from core.headless import convert_from_explorer
from core.settings import load_settings, save_settings

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BACKGROUND = "#07152B"
SURFACE = "#102543"
PANEL = "#142D50"
BORDER = "#245184"
TEXT = "#F4F8FF"
MUTED = "#AFC2DE"
ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"
SECONDARY = "#60A5FA"


class Tk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class UniversalConverterApp(Tk):
    def __init__(self):
        super().__init__()
        self.router = FileRouter()
        self.settings = load_settings()
        self.zip_workspaces = []
        self.current_files = []
        self.file_categories = {}
        self.detected_mime = None
        self.default_out_dir = ctk.StringVar(value=self.settings.get("default_output_dir", ""))
        privacy = self.settings["privacy"]
        self.strip_exif_var = ctk.BooleanVar(value=privacy["remove_exif"])
        self.remove_location_var = ctk.BooleanVar(value=privacy["remove_location"])
        self.remove_comments_var = ctk.BooleanVar(value=privacy["remove_comments"])
        self.remove_color_profile_var = ctk.BooleanVar(value=privacy["remove_color_profile"])
        self.zip_var = ctk.BooleanVar(value=False)
        self.theme_var = ctk.BooleanVar(value=True)
        self.event_queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.hw_accel_var = ctk.BooleanVar(value=self.settings.get("hardware_acceleration", True))
        self.is_running = False
        self.last_output_files = []

        self.title("File Converter Engine")
        self.geometry("1040x820")
        self.minsize(900, 720)
        self.configure(fg_color=BACKGROUND)

        self.font_h1 = ctk.CTkFont(family="Segoe UI", size=25, weight="bold")
        self.font_h2 = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        self.font_body = ctk.CTkFont(family="Segoe UI", size=13)
        self.font_small = ctk.CTkFont(family="Segoe UI", size=11)

        self._build_ui()
        self.after(100, self._poll_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if len(sys.argv) > 1:
            paths = [p for p in sys.argv[1:] if os.path.isfile(p)]
            if paths:
                self._load_files(paths)

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=26, pady=(20, 12))
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title_frame, text="File Converter", font=self.font_h1).pack(anchor="w")
        ctk.CTkLabel(title_frame, text="A local-first workspace for converting files", text_color=MUTED, font=self.font_body).pack(anchor="w", pady=(2, 0))
        ctk.CTkSwitch(header, text="Dark mode", variable=self.theme_var, command=self.toggle_theme, font=self.font_small).pack(side="right", padx=(12, 0))

        self.tab_view = ctk.CTkTabview(self, fg_color=SURFACE, segmented_button_selected_color=ACCENT, segmented_button_selected_hover_color=ACCENT_HOVER)
        self.tab_view.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        for name in ("Convert", "Privacy", "Settings", "Activity"):
            self.tab_view.add(name)
        self._build_convert_tab()
        self._build_privacy_tab()
        self._build_settings_tab()
        self._build_activity_tab()

    def _build_convert_tab(self):
        tab = self.tab_view.tab("Convert")
        root = ctk.CTkFrame(tab, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=12, pady=8)

        ctk.CTkLabel(root, text="1. Add files", font=self.font_h2).pack(anchor="w", pady=(0, 7))
        drop = ctk.CTkFrame(root, fg_color=PANEL, border_width=1, border_color=BORDER, corner_radius=10, height=76, cursor="hand2")
        drop.pack(fill="x")
        drop.pack_propagate(False)
        drop.drop_target_register(DND_FILES)
        drop.dnd_bind("<<Drop>>", self._drop_file)
        drop.bind("<Button-1>", lambda _event: self.select_file())
        drop_label = ctk.CTkLabel(drop, text="Drop files here or click to choose", font=self.font_h2, text_color=TEXT, cursor="hand2")
        drop_label.pack(pady=(13, 2))
        drop_label.bind("<Button-1>", lambda _event: self.select_file())
        sub_label = ctk.CTkLabel(drop, text="Choose files from your computer", text_color=MUTED, font=self.font_small, cursor="hand2")
        sub_label.pack()
        sub_label.bind("<Button-1>", lambda _event: self.select_file())
        actions = ctk.CTkFrame(root, fg_color="transparent")
        actions.pack(fill="x", pady=(6, 5))
        ctk.CTkButton(actions, text="＋ Add files", command=self.select_file, width=120, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left")
        ctk.CTkButton(actions, text="Remove selected", command=self.remove_selected, width=130, fg_color=PANEL, hover_color=BORDER).pack(side="left", padx=8)
        ctk.CTkButton(actions, text="Clear queue", command=self.reset_all_data, width=105, fg_color="transparent", border_width=1, text_color=("#222", "#EEE")).pack(side="right")

        queue_head = ctk.CTkFrame(root, fg_color="transparent")
        queue_head.pack(fill="x", pady=(3, 5))
        ctk.CTkLabel(queue_head, text="2. Conversion queue", font=self.font_h2).pack(side="left")
        self.queue_summary = ctk.CTkLabel(queue_head, text="No files added", text_color=MUTED, font=self.font_small)
        self.queue_summary.pack(side="right")

        tree_frame = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=8, height=150)
        tree_frame.pack(fill="x")
        tree_frame.pack_propagate(False)
        style = ttk.Style()
        try:
            style.theme_use("clam")
            style.configure("FCE.Treeview", rowheight=28, font=("Segoe UI", 10), background=SURFACE, foreground=TEXT, fieldbackground=SURFACE, borderwidth=0)
            style.configure("FCE.Treeview.Heading", font=("Segoe UI", 10, "bold"), background=PANEL, foreground=TEXT, relief="flat")
            style.map("FCE.Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#FFFFFF")])
        except Exception:
            pass
        columns = ("file", "type", "size", "status")
        self.file_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", style="FCE.Treeview", selectmode="extended")
        for col, label in (("file", "File"), ("type", "Detected type"), ("size", "Size"), ("status", "Status")):
            self.file_tree.heading(col, text=label)
        self.file_tree.column("file", width=300, anchor="w")
        self.file_tree.column("type", width=120, anchor="w")
        self.file_tree.column("size", width=90, anchor="e")
        self.file_tree.column("status", width=140, anchor="w")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=scroll.set)
        self.file_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)

        ctk.CTkLabel(root, text="3. Output settings", font=self.font_h2).pack(anchor="w", pady=(9, 5))
        settings = ctk.CTkFrame(root, fg_color=PANEL, corner_radius=8)
        settings.pack(fill="x")
        settings.grid_columnconfigure((0, 1, 2), weight=1)
        fmt_box = ctk.CTkFrame(settings, fg_color="transparent")
        fmt_box.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        ctk.CTkLabel(fmt_box, text="Convert to", font=self.font_small, text_color=MUTED).pack(anchor="w")
        self.format_dropdown = ctk.CTkOptionMenu(fmt_box, values=["Add compatible files first"], state="disabled", command=self._on_format_change, fg_color=ACCENT, button_color=ACCENT_HOVER, button_hover_color=ACCENT_HOVER)
        self.format_dropdown.pack(fill="x", pady=(5, 0))

        self.quality_box = ctk.CTkFrame(settings, fg_color="transparent")
        self.quality_box.grid(row=0, column=1, sticky="ew", padx=12, pady=12)
        self.quality_label = ctk.CTkLabel(self.quality_box, text="Image quality: 90%", font=self.font_small, text_color=MUTED)
        self.quality_label.pack(anchor="w")
        ctk.CTkLabel(
            self.quality_box,
            text="Higher % usually means larger files and less compression.",
            font=self.font_small,
            text_color=MUTED,
        ).pack(anchor="w", pady=(3, 0))
        self.comp_slider = ctk.CTkSlider(self.quality_box, from_=10, to=100, number_of_steps=18, command=self._update_quality_label, progress_color=ACCENT, button_color=ACCENT, button_hover_color=ACCENT_HOVER)
        self.comp_slider.set(90)
        self.comp_slider.pack(fill="x", pady=(8, 0))

        extras = ctk.CTkFrame(settings, fg_color="transparent")
        extras.grid(row=0, column=2, sticky="ew", padx=12, pady=12)
        ctk.CTkCheckBox(extras, text="Package outputs as ZIP", variable=self.zip_var, font=self.font_small, fg_color=ACCENT, checkmark_color="#FFFFFF").pack(anchor="w", pady=(3, 8))
        ctk.CTkLabel(extras, text="Rename template", font=self.font_small, text_color=MUTED).pack(anchor="w")
        self.rename_template = ctk.CTkEntry(extras, placeholder_text="{name}_converted", height=30)
        self.rename_template.pack(fill="x", pady=(4, 0))

        self.action_status = ctk.CTkLabel(root, text="Ready when you are.", anchor="w", font=self.font_body)
        self.action_status.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(
            root,
            text="Output sizes are measured after conversion; a reliable pre-conversion estimate is not available for every format.",
            anchor="w",
            text_color="gray",
            font=self.font_small,
        ).pack(fill="x", pady=(0, 2))
        self.action_progress = ctk.CTkProgressBar(root, mode="determinate", progress_color=ACCENT)
        self.action_progress.set(0)
        self.action_progress.pack(fill="x", pady=(0, 7))
        buttons = ctk.CTkFrame(root, fg_color="transparent")
        buttons.pack(fill="x")
        self.convert_btn = ctk.CTkButton(buttons, text="Convert files", command=self.start_conversion, height=42, font=self.font_h2, fg_color=ACCENT, hover_color=ACCENT_HOVER, state="disabled")
        self.convert_btn.pack(side="left", fill="x", expand=True)
        self.open_output_btn = ctk.CTkButton(buttons, text="Open output folder", command=self.open_output_folder, height=42, width=155, state="disabled", fg_color=PANEL, hover_color=BORDER)
        self.open_output_btn.pack(side="left", padx=(8, 0))

        self._update_quality_visibility(False)

    def _build_privacy_tab(self):
        content = ctk.CTkScrollableFrame(self.tab_view.tab("Privacy"), fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(content, text="Privacy options", font=self.font_h2).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(content, text="These settings apply only to supported image conversions.", text_color=MUTED, font=self.font_body).pack(anchor="w", pady=(0, 16))
        self.strip_exif_switch = ctk.CTkSwitch(
            content,
            text="Remove embedded image metadata (including EXIF where supported)",
            variable=self.strip_exif_var,
            font=self.font_body,
            progress_color=ACCENT, command=self._save_preferences,
        )
        self.strip_exif_switch.pack(anchor="w", pady=4)
        self.remove_location_switch = ctk.CTkSwitch(content, text="Remove embedded location (GPS) metadata where supported", variable=self.remove_location_var, font=self.font_body, progress_color=ACCENT, command=self._save_preferences)
        self.remove_location_switch.pack(anchor="w", pady=4)
        self.remove_comments_switch = ctk.CTkSwitch(content, text="Remove comments and descriptive metadata where supported", variable=self.remove_comments_var, font=self.font_body, progress_color=ACCENT, command=self._save_preferences)
        self.remove_comments_switch.pack(anchor="w", pady=4)
        self.remove_color_profile_switch = ctk.CTkSwitch(content, text="Remove embedded colour profiles (may change colours)", variable=self.remove_color_profile_var, font=self.font_body, progress_color=ACCENT, command=self._save_preferences)
        self.remove_color_profile_switch.pack(anchor="w", pady=4)
        self.metadata_help = ctk.CTkLabel(
            content,
            text="Add image files to the queue to enable this option.",
            text_color=MUTED,
            font=self.font_small,
        )
        self.metadata_help.pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(content, text="These controls affect supported image conversions only. They cannot remove information visibly present in pixels and cannot guarantee removal of every metadata type in every format.", wraplength=760, justify="left", text_color=MUTED, font=self.font_small).pack(anchor="w", pady=(16, 0))

    def _build_settings_tab(self):
        content = ctk.CTkScrollableFrame(self.tab_view.tab("Settings"), fg_color="transparent")
        content.pack(fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(content, text="Output and integration", font=self.font_h2).pack(anchor="w", pady=(0, 12))
        ctk.CTkLabel(content, text="Default output folder", font=self.font_body).pack(anchor="w")
        row = ctk.CTkFrame(content, fg_color="transparent")
        row.pack(fill="x", pady=(5, 20))
        ctk.CTkEntry(row, textvariable=self.default_out_dir, state="readonly").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Choose folder", command=self._select_default_dir, width=120, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left", padx=(8, 0))
        ctk.CTkButton(row, text="Clear", command=lambda: self.default_out_dir.set(""), width=70, fg_color=PANEL, hover_color=BORDER).pack(side="left", padx=(8, 0))
        ctk.CTkLabel(content, text="Windows File Explorer integration", font=self.font_h2).pack(anchor="w", pady=(6, 8))
        self.context_status = ctk.CTkLabel(content, text="Checking registration...", text_color=MUTED, font=self.font_small, wraplength=760, justify="left")
        self.context_status.pack(anchor="w", pady=(0, 10))
        buttons = ctk.CTkFrame(content, fg_color="transparent")
        buttons.pack(anchor="w")
        ctk.CTkButton(buttons, text="Add to context menu", command=self._register_context_menu, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left")
        ctk.CTkButton(buttons, text="Remove context menu entry", command=self._remove_context_menu, fg_color=PANEL, hover_color=BORDER).pack(side="left", padx=8)
        ctk.CTkButton(buttons, text="Refresh / repair", command=self._refresh_context_menu, fg_color=PANEL, hover_color=BORDER).pack(side="left")
        self._refresh_context_status()
        ctk.CTkLabel(content, text="Performance and acceleration", font=self.font_h2).pack(anchor="w", pady=(16, 8))
        self.hw_accel_switch = ctk.CTkSwitch(
            content,
            text="Enable GPU Hardware Acceleration for video encoding (NVENC / QSV / AMF)",
            variable=self.hw_accel_var,
            font=self.font_body,
            progress_color=ACCENT,
            command=self._save_preferences,
        )
        self.hw_accel_switch.pack(anchor="w", pady=4)
        ctk.CTkLabel(
            content,
            text="Safe mode: If no compatible GPU is detected, the engine automatically falls back to CPU encoding.",
            text_color=MUTED,
            font=self.font_small,
        ).pack(anchor="w", pady=(0, 12))
        ctk.CTkLabel(content, text="Experimental C++ byte inversion is intentionally not part of normal file conversion. It is a reversible byte transformation, not encryption, and its output is not a standard converted file.", text_color=MUTED, wraplength=760, justify="left", font=self.font_small).pack(anchor="w", pady=(28, 0))

    def _build_activity_tab(self):
        content = ctk.CTkFrame(self.tab_view.tab("Activity"), fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=20)
        top = ctk.CTkFrame(content, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(top, text="Activity and diagnostics", font=self.font_h2).pack(side="left")
        ctk.CTkButton(top, text="Clear log", width=90, command=self.clear_logs, fg_color=PANEL, hover_color=BORDER).pack(side="right")
        self.log_box = ctk.CTkTextbox(content, font=ctk.CTkFont(family="Consolas", size=12), wrap="word")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.configure(state="disabled")
        self.log_message("Application ready. Conversions run locally using installed engines where applicable.")
    def toggle_theme(self):
        ctk.set_appearance_mode("dark" if self.theme_var.get() else "light")

    def _update_quality_label(self, value):
        q = int(float(value))
        fmt = self.format_dropdown.get().upper()
        if fmt in {"MP3", "AAC", "M4A", "OGG"}:
            kbps = int(64 + ((q - 10) / 90.0) * 256)
            self.quality_label.configure(text=f"Audio bitrate: ~{kbps} kbps ({q}%)")
        elif fmt in {"MP4", "MKV", "AVI", "MOV", "WEBM"}:
            crf = int(38 - ((q - 10) / 90.0) * 20)
            self.quality_label.configure(text=f"Video quality: {q}% (CRF {crf})")
        else:
            self.quality_label.configure(text=f"Image quality: {q}%")

    def _update_quality_visibility(self, visible):
        if visible:
            self.quality_box.grid()
        else:
            self.quality_box.grid_remove()

    def _on_format_change(self, value):
        if not self.current_files:
            self._update_quality_visibility(False)
            self._update_metadata_setting()
            return
        first_cat = self.file_categories.get(self.current_files[0])
        val_upper = value.upper()
        if first_cat == "image" and val_upper in {"JPEG", "JPG", "WEBP"}:
            self.quality_label.configure(text=f"Image quality: {int(self.comp_slider.get())}%")
            self._update_quality_visibility(True)
        elif first_cat in {"video", "audio"}:
            if val_upper in {"MP3", "AAC", "M4A", "OGG"}:
                q = int(self.comp_slider.get())
                kbps = int(64 + ((q - 10) / 90.0) * 256)
                self.quality_label.configure(text=f"Audio bitrate: ~{kbps} kbps ({q}%)")
                self._update_quality_visibility(True)
            elif val_upper in {"MP4", "MKV", "AVI", "MOV", "WEBM"}:
                q = int(self.comp_slider.get())
                crf = int(38 - ((q - 10) / 90.0) * 20)
                self.quality_label.configure(text=f"Video quality: {q}% (CRF {crf})")
                self._update_quality_visibility(True)
            else:
                self._update_quality_visibility(False)
        else:
            self._update_quality_visibility(False)
        self._update_metadata_setting()

    def _update_metadata_setting(self):
        """Only enable metadata removal when the current queue is image-only."""
        image_only = bool(self.current_files) and all(
            self.file_categories.get(path) == "image" for path in self.current_files
        )
        if hasattr(self, "strip_exif_switch"):
            state = "normal" if image_only else "disabled"
            for control in (self.strip_exif_switch, self.remove_location_switch, self.remove_comments_switch, self.remove_color_profile_switch):
                control.configure(state=state)
        if hasattr(self, "metadata_help"):
            if image_only:
                self.metadata_help.configure(text="Applies to supported image conversions only.")
            else:
                self.metadata_help.configure(text="Add image files only to enable this option.")

    def log_message(self, message):
        if not hasattr(self, "log_box"):
            return
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{__import__('datetime').datetime.now():%H:%M:%S}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _drop_file(self, event):
        self._load_files(self.tk.splitlist(event.data))

    def select_file(self):
        paths = filedialog.askopenfilenames(title="Select files to convert", filetypes=[("All files", "*.*")])
        if paths:
            self._load_files(paths)

    def _load_files(self, file_paths):
        added = 0
        errors = []
        expanded = []
        for raw in file_paths:
            p = os.path.abspath(str(raw))
            if os.path.isdir(p):
                for root_dir, _, filenames in os.walk(p):
                    for fn in sorted(filenames):
                        expanded.append(os.path.join(root_dir, fn))
            elif os.path.isfile(p):
                expanded.append(p)
            else:
                errors.append(f"Not a valid file or folder: {p}")

        for path in expanded:
            if not os.path.isfile(path):
                continue
            if Path(path).suffix.lower() == ".zip":
                try:
                    workspace, extracted, skipped = extract_supported_zip(path, self.router)
                    self.zip_workspaces.append(workspace)
                    self._load_files(extracted)
                    errors.extend(skipped)
                except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
                    errors.append(f"Could not process ZIP {os.path.basename(path)}: {exc}")
                continue
            if path in self.current_files:
                continue
            category = self.router.category_for(path)
            if category == "unsupported":
                errors.append(f"Unsupported input type: {os.path.basename(path)}")
                continue
            if self.current_files:
                existing_categories = {self.file_categories[p] for p in self.current_files}
                def _family(c):
                    return "media" if c in {"video", "audio"} else c
                existing_families = {_family(c) for c in existing_categories}
                if _family(category) not in existing_families:
                    errors.append(f"{os.path.basename(path)} was not added: this queue contains {', '.join(sorted(existing_categories))} files. Clear the queue to start a different conversion family.")
                    continue
            self.current_files.append(path)
            self.file_categories[path] = category
            mime = self.router.detect_true_format(path)
            self.detected_mime = mime
            self.file_tree.insert("", "end", iid=path, values=(os.path.basename(path), mime, self._format_size(os.path.getsize(path)), "Queued"))
            added += 1

        if self.current_files:
            common_formats = None
            for p in self.current_files:
                fmts = self.router.get_supported_conversions(self.router.detect_true_format(p), p)
                if common_formats is None:
                    common_formats = list(fmts)
                else:
                    common_formats = [f for f in common_formats if f in fmts]
            formats = common_formats or []

            if formats:
                self.format_dropdown.configure(values=formats, state="normal")
                current = self.format_dropdown.get()
                if current not in formats:
                    self.format_dropdown.set(formats[0])
                self._on_format_change(self.format_dropdown.get())
            else:
                self.format_dropdown.configure(values=["No compatible backend installed"], state="disabled")
                self.format_dropdown.set("No compatible backend installed")
                self.convert_btn.configure(state="disabled")
                errors.append("No common compatible format supports all files in the queue.")
            self._update_metadata_setting()
            if formats:
                self.convert_btn.configure(state="normal" if not self.is_running else "disabled")
        self._refresh_queue_summary()
        if added:
            self.log_message(f"Added {added} file(s) to the queue.")
            self.action_status.configure(text=f"{len(self.current_files)} file(s) queued. Review settings, then convert.")
        if errors:
            self.log_message("\n".join(errors))
            messagebox.showwarning("Some files were not added", "\n".join(errors[:8]))

    @staticmethod
    def _format_size(size):
        units = ("B", "KB", "MB", "GB", "TB")
        amount = float(size)
        for unit in units:
            if amount < 1024 or unit == units[-1]:
                return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
            amount /= 1024

    def _refresh_queue_summary(self):
        total_size = sum(os.path.getsize(p) for p in self.current_files if os.path.isfile(p))
        self.queue_summary.configure(text=f"{len(self.current_files)} file(s) · {self._format_size(total_size)}")

    def _common_queue_formats(self):
        common_formats = None
        for path in self.current_files:
            formats = self.router.get_supported_conversions(self.router.detect_true_format(path), path)
            common_formats = list(formats) if common_formats is None else [fmt for fmt in common_formats if fmt in formats]
        return common_formats or []

    def remove_selected(self):
        selected = self.file_tree.selection()
        for path in selected:
            if path in self.current_files:
                self.current_files.remove(path)
                self.file_categories.pop(path, None)
            self.file_tree.delete(path)
        if not self.current_files:
            self.format_dropdown.configure(values=["Add compatible files first"], state="disabled")
            self.format_dropdown.set("Add compatible files first")
            self.convert_btn.configure(state="disabled")
            self._update_quality_visibility(False)
        else:
            formats = self._common_queue_formats()
            if formats:
                self.format_dropdown.configure(values=formats, state="normal")
                if self.format_dropdown.get() not in formats: self.format_dropdown.set(formats[0])
                self._on_format_change(self.format_dropdown.get())
            else:
                self.format_dropdown.configure(values=["No compatible backend installed"], state="disabled")
                self.format_dropdown.set("No compatible backend installed")
                self.convert_btn.configure(state="disabled")
        self._update_metadata_setting()
        self._refresh_queue_summary()

    def reset_all_data(self):
        if self.is_running:
            messagebox.showinfo("Conversion in progress", "Wait for the current batch to finish before clearing the queue.")
            return
        self.current_files.clear()
        self.file_categories.clear()
        for item in self.file_tree.get_children(): self.file_tree.delete(item)
        self.detected_mime = None
        self.format_dropdown.configure(values=["Add compatible files first"], state="disabled")
        self.format_dropdown.set("Add compatible files first")
        self.convert_btn.configure(state="disabled")
        self.action_status.configure(text="Ready when you are.")
        self.action_progress.set(0)
        self.rename_template.delete(0, "end")
        self.zip_var.set(False)
        for workspace in self.zip_workspaces:
            workspace.cleanup()
        self.zip_workspaces.clear()
        self._update_metadata_setting()
        self._refresh_queue_summary()

    def _save_preferences(self):
        self.settings["privacy"] = {
            "remove_exif": self.strip_exif_var.get(),
            "remove_location": self.remove_location_var.get(),
            "remove_comments": self.remove_comments_var.get(),
            "remove_color_profile": self.remove_color_profile_var.get(),
        }
        self.settings["hardware_acceleration"] = self.hw_accel_var.get()
        save_settings(self.settings)

    def _select_default_dir(self):
        folder = filedialog.askdirectory(title="Select default output folder")
        if folder:
            self.default_out_dir.set(folder)
            self.settings["default_output_dir"] = folder
            save_settings(self.settings)
            self.log_message(f"Default output folder set to: {folder}")

    def _register_context_menu(self):
        success, message = add_to_registry()
        self.log_message(message)
        (messagebox.showinfo if success else messagebox.showwarning)("Context menu", message)
        self._refresh_context_status()

    def _remove_context_menu(self):
        success, message = remove_from_registry()
        self.log_message(message)
        (messagebox.showinfo if success else messagebox.showwarning)("Context menu", message)
        self._refresh_context_status()

    def _refresh_context_menu(self):
        success, message = refresh_registry()
        self.log_message(message)
        (messagebox.showinfo if success else messagebox.showwarning)("Context menu", message)
        self._refresh_context_status()

    def _refresh_context_status(self):
        status, message = registry_status()
        if hasattr(self, "context_status"):
            self.context_status.configure(text=f"Status: {status}. {message}")

    def _choose_collision_path(self, path):
        """Ask explicitly how to handle an existing output. Rename is the safe default."""
        if not os.path.exists(path):
            return ("use", path)

        dialog = ctk.CTkToplevel(self)
        dialog.title("Output already exists")
        dialog.geometry("470x245")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        result = {"action": "cancel_batch", "path": None}

        ctk.CTkLabel(
            dialog,
            text="An output file already exists",
            font=self.font_h2,
        ).pack(anchor="w", padx=22, pady=(20, 6))
        ctk.CTkLabel(
            dialog,
            text=os.path.basename(path),
            font=self.font_body,
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=22, pady=(0, 12))
        ctk.CTkLabel(
            dialog,
            text="Choose what to do. Rename is recommended to protect existing files.",
            text_color="gray",
            font=self.font_small,
            wraplength=420,
            justify="left",
        ).pack(anchor="w", padx=22, pady=(0, 14))

        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=(0, 16))

        def finish(action, chosen_path=None):
            result["action"] = action
            result["path"] = chosen_path
            dialog.destroy()

        ctk.CTkButton(
            buttons, text="Rename (recommended)", width=145,
            command=lambda: finish("use", unique_path(path)),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            buttons, text="Overwrite", width=88,
            command=lambda: finish("use", path),
            fg_color="#465365", hover_color="#596A80",
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            buttons, text="Skip file", width=75,
            command=lambda: finish("skip"),
            fg_color="#465365", hover_color="#596A80",
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            buttons, text="Cancel batch", width=90,
            command=lambda: finish("cancel_batch"),
            fg_color="#8B3A3A", hover_color="#A34848",
        ).pack(side="left", padx=4)
        dialog.bind("<Escape>", lambda _event: finish("cancel_batch"))
        dialog.wait_window()
        return result["action"], result["path"]

    def cancel_conversion(self):
        if self.is_running:
            self.cancel_event.set()
            self.action_status.configure(text="Stopping conversion…")
            self.convert_btn.configure(state="disabled")

    def start_conversion(self):
        if not self.current_files or self.is_running:
            return

        # Only process files that are not already Completed
        pending_files = []
        for path in self.current_files:
            if not self.file_tree.exists(path):
                continue
            status = self.file_tree.set(path, "status")
            if status != "Completed":
                pending_files.append(path)

        if not pending_files:
            messagebox.showinfo(
                "All files converted",
                "All files in the queue have already been converted. Add new files or clear the queue to start a new batch."
            )
            return

        target = self.format_dropdown.get()
        valid_formats = self.router.get_supported_conversions(self.router.detect_true_format(pending_files[0]), pending_files[0])
        if not valid_formats:
            messagebox.showerror("No conversion backend", "No installed backend supports this conversion.")
            return
        if target not in valid_formats:
            messagebox.showerror("Unsupported conversion", f"{target} is not a supported target for this queue.")
            return

        out_dir = self.default_out_dir.get().strip() or None
        if out_dir:
            try:
                Path(out_dir).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Output folder error", str(exc))
                return
        template = self.rename_template.get().strip() or None
        jobs = []
        reserved = set()
        batch_cancelled = False
        for path in pending_files:
            draft = get_output_path(path, target, out_dir, template=template)
            if os.path.abspath(draft) == os.path.abspath(path):
                draft = get_output_path(path, target, out_dir, suffix="_converted")
            if os.path.abspath(draft) in reserved:
                draft = unique_path(draft)
            action, chosen = self._choose_collision_path(draft)
            if action == "cancel_batch":
                batch_cancelled = True
                break
            if action == "use" and chosen:
                reserved.add(os.path.abspath(chosen))
                jobs.append((path, chosen))
                self.file_tree.set(path, "status", "Ready")
            else:
                self.file_tree.set(path, "status", "Skipped")
        if batch_cancelled:
            for path in pending_files:
                if self.file_tree.exists(path) and self.file_tree.set(path, "status") == "Ready":
                    self.file_tree.set(path, "status", "Queued")
            self.action_status.configure(text="Batch cancelled before conversion started.")
            return
        if not jobs:
            self.action_status.configure(text="No files were queued for conversion.")
            return

        self.cancel_event.clear()
        self.is_running = True
        self.convert_btn.configure(
            text="Stop conversion",
            command=self.cancel_conversion,
            fg_color="#DC2626",
            hover_color="#B91C1C",
            state="normal",
        )
        self.open_output_btn.configure(state="disabled")
        self.action_progress.set(0)
        self.action_status.configure(text=f"Converting 0 of {len(jobs)} files…")
        options = {
            "target": target,
            "quality": int(self.comp_slider.get()),
            "strip_exif": self.strip_exif_var.get(),
            "privacy": self.settings["privacy"],
            "out_dir": out_dir,
            "do_zip": self.zip_var.get(),
            "hardware_accel": self.hw_accel_var.get(),
        }
        threading.Thread(target=self._process_batch, args=(jobs, options), daemon=True).start()

    def _run_single_job(self, file_path, output_path, options):
        if self.cancel_event.is_set():
            return False, "Cancelled by user", ""
        category = self.router.category_for(file_path)
        if category == "image":
            success, result = convert_image(
                file_path, options["target"],
                strip_exif=options["strip_exif"],
                privacy=options["privacy"],
                quality=options["quality"],
                out_path=output_path,
            )
        elif category == "data":
            success, result = convert_data(file_path, options["target"], out_path=output_path)
        else:
            success, result = False, "Unsupported parallel type", ""
        size_note = ""
        if success and os.path.isfile(result) and os.path.getsize(result) > 0:
            in_sz = os.path.getsize(file_path)
            out_sz = os.path.getsize(result)
            delta = in_sz - out_sz
            if in_sz > 0:
                pct = (delta / in_sz) * 100
                if delta > 0:
                    size_note = f" · {self._format_size(delta)} smaller ({pct:.1f}% reduction)"
                elif delta < 0:
                    size_note = f" · {self._format_size(-delta)} larger ({abs(pct):.1f}% increase)"
                else:
                    size_note = " · same size"
            return True, result, f" | {self._format_size(in_sz)} → {self._format_size(out_sz)}{size_note}"
        return False, result, ""

    def _process_batch(self, jobs, options):
        outputs, errors, skipped = [], [], 0
        total = len(jobs)
        first_cat = self.router.category_for(jobs[0][0]) if jobs else None

        # Adaptive core calculation for image/data batch processing
        max_workers = max(1, min(8, (os.cpu_count() or 4) - 1)) if first_cat in {"image", "data"} else 1

        if max_workers > 1 and len(jobs) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            completed_count = 0
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(self._run_single_job, f_path, o_path, options): (f_path, o_path)
                    for f_path, o_path in jobs
                }
                for fut in as_completed(future_map):
                    f_path, o_path = future_map[fut]
                    if self.cancel_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    try:
                        success, result, size_msg = fut.result()
                        completed_count += 1
                        if success:
                            outputs.append(result)
                            self.event_queue.put(("status", f_path, "Completed", completed_count, total, os.path.basename(f_path)))
                            self.event_queue.put(("log", f"Converted: {os.path.basename(f_path)} → {os.path.basename(result)}{size_msg}"))
                        else:
                            errors.append(f"{os.path.basename(f_path)}: {result}")
                            self.event_queue.put(("status", f_path, "Failed", completed_count, total, os.path.basename(f_path)))
                    except Exception as exc:
                        completed_count += 1
                        errors.append(f"{os.path.basename(f_path)}: {exc}")
                        self.event_queue.put(("status", f_path, "Failed", completed_count, total, os.path.basename(f_path)))
        else:
            for index, (file_path, output_path) in enumerate(jobs, start=1):
                if self.cancel_event.is_set():
                    self.event_queue.put(("log", "Batch conversion stopped by user."))
                    break
                self.event_queue.put(("status", file_path, "Converting", index, total, os.path.basename(file_path)))
                try:
                    category = self.router.category_for(file_path)
                    if category == "image":
                        success, result = convert_image(
                            file_path, options["target"],
                            strip_exif=options["strip_exif"],
                            privacy=options["privacy"],
                            quality=options["quality"],
                            out_path=output_path,
                        )
                    elif category in {"video", "audio"}:
                        def _media_progress(frac, pct_str="0%", eta_str="--:--", speed_str="--"):
                            self.event_queue.put(("file_progress", file_path, frac, pct_str, eta_str, speed_str, index, total, os.path.basename(file_path)))

                        success, result = convert_media(
                            file_path, options["target"],
                            out_path=output_path,
                            quality=options.get("quality"),
                            hardware_accel=options.get("hardware_accel", False),
                            progress_callback=_media_progress,
                            cancel_event=self.cancel_event,
                        )
                    elif category == "data":
                        success, result = convert_data(file_path, options["target"], out_path=output_path)
                    elif category == "document":
                        success, result = convert_document(
                            file_path,
                            options["target"],
                            out_path=output_path,
                            notice_callback=lambda notice: self.event_queue.put(("log", notice)),
                        )
                    else:
                        success, result = False, "Unsupported file type."

                    if success and os.path.isfile(result) and os.path.getsize(result) > 0:
                        outputs.append(result)
                        input_size = os.path.getsize(file_path)
                        output_size = os.path.getsize(result)
                        delta = input_size - output_size
                        if input_size > 0:
                            change_pct = (delta / input_size) * 100
                            if delta > 0:
                                size_note = f" · {self._format_size(delta)} smaller ({change_pct:.1f}% reduction)"
                            elif delta < 0:
                                size_note = f" · {self._format_size(-delta)} larger ({abs(change_pct):.1f}% increase)"
                            else:
                                size_note = " · same size"
                        else:
                            size_note = ""
                        self.event_queue.put(("status", file_path, "Completed", index, total, os.path.basename(file_path)))
                        self.event_queue.put(("log", f"Converted: {os.path.basename(file_path)} → {os.path.basename(result)} | {self._format_size(input_size)} → {self._format_size(output_size)}{size_note}"))
                    else:
                        errors.append(f"{os.path.basename(file_path)}: {result}")
                        self.event_queue.put(("status", file_path, "Failed", index, total, os.path.basename(file_path)))
                except Exception as exc:
                    errors.append(f"{os.path.basename(file_path)}: {exc}")
                    self.event_queue.put(("status", file_path, "Failed", index, total, os.path.basename(file_path)))

        zip_result = None
        if options["do_zip"] and outputs and not self.cancel_event.is_set():
            first_dir = options["out_dir"] or str(Path(outputs[0]).parent)
            zip_path = unique_path(str(Path(first_dir) / "Batch_Output.zip"))
            zip_success, zip_message = package_to_zip(outputs, zip_path)
            if zip_success:
                zip_result = zip_message
                self.event_queue.put(("log", f"Verified ZIP created: {zip_message}"))
            else:
                errors.append(f"ZIP packaging failed: {zip_message}")
        self.event_queue.put(("complete", len(outputs), total, errors, outputs, zip_result))

    def _poll_events(self):
        try:
            while True:
                event = self.event_queue.get_nowait()
                kind = event[0]
                if kind == "log":
                    self.log_message(event[1])
                elif kind == "status":
                    _, path, status, index, total, filename = event
                    if self.file_tree.exists(path):
                        self.file_tree.set(path, "status", status)
                    self.action_status.configure(text=f"{status}: {filename} ({index} of {total})")
                    if status == "Converting":
                        self.action_progress.set((index - 1) / total if total else 0)
                    else:
                        self.action_progress.set(index / total if total else 0)
                elif kind == "file_progress":
                    _, path, fraction, pct_str, eta_str, speed_str, index, total, filename = event
                    overall = (index - 1 + fraction) / total if total else fraction
                    self.action_progress.set(overall)
                    self.action_status.configure(
                        text=f"Converting: {filename} ({pct_str}) · ETA: {eta_str} · Speed: {speed_str} · ({index} of {total})"
                    )
                    if self.file_tree.exists(path):
                        self.file_tree.set(path, "status", f"Converting ({pct_str})")
                elif kind == "complete":
                    _, success_count, total, errors, outputs, zip_result = event
                    self._conversion_complete(success_count, total, errors, outputs, zip_result)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll_events)

    def _conversion_complete(self, success_count, total, errors, outputs, zip_result):
        self.is_running = False
        self.last_output_files = outputs[:]
        self.convert_btn.configure(
            text="Convert files",
            command=self.start_conversion,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            state="normal" if self.current_files else "disabled",
        )
        self.open_output_btn.configure(state="normal" if outputs or zip_result else "disabled")
        self.action_progress.set(1 if success_count else 0)

        if self.cancel_event.is_set():
            self.action_status.configure(text=f"Conversion stopped · {success_count}/{total} files converted")
            messagebox.showinfo("Conversion stopped", f"Conversion was stopped by user.\n\nSuccessfully completed {success_count} of {total} file(s).")
        elif success_count == total and not errors:
            self.action_status.configure(text=f"Completed successfully · {success_count}/{total} files")
            zip_note = f"\n\nZIP: {zip_result}" if zip_result else ""
            messagebox.showinfo("Conversion complete", f"Successfully converted {success_count} file(s).{zip_note}")
        elif success_count:
            self.action_status.configure(text=f"Finished with some issues · {success_count}/{total} files converted")
            issues = "\n".join(errors[:8])
            messagebox.showwarning("Conversion finished", f"Converted {success_count} of {total} file(s).\n\n{issues}")
        else:
            self.action_status.configure(text="Conversion failed. See Activity for details.")
            issues = "\n".join(errors[:8])
            messagebox.showerror("Conversion failed", f"No files were converted successfully.\n\n{issues}")
        if zip_result:
            self.last_output_files.append(zip_result)
        self.log_message(f"Batch finished: {success_count}/{total} converted; {len(errors)} issue(s).")

    def open_output_folder(self):
        paths = self.last_output_files
        folder = str(Path(paths[0]).parent) if paths else (self.default_out_dir.get().strip() or "")
        if not folder or not os.path.isdir(folder):
            messagebox.showinfo("Output folder", "No output folder is available yet.")
            return
        try:
            if sys.platform == "win32": os.startfile(folder)
            elif sys.platform == "darwin": subprocess.Popen(["open", folder])
            else: subprocess.Popen(["xdg-open", folder])
        except Exception as exc:
            messagebox.showerror("Could not open folder", str(exc))

    def _on_close(self):
        if self.is_running:
            if not messagebox.askyesno("Conversion running", "A conversion is in progress. Close the app anyway? The current external conversion may be interrupted."):
                return
        self._save_preferences()
        self.settings["default_output_dir"] = self.default_out_dir.get().strip()
        save_settings(self.settings)
        for workspace in self.zip_workspaces:
            workspace.cleanup()
        self.destroy()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--convert-to")
    parser.add_argument("--same-folder", action="store_true")
    parser.add_argument("--open", action="store_true")
    known, remaining = parser.parse_known_args()
    if known.convert_to:
        raise SystemExit(convert_from_explorer(remaining, known.convert_to))
    app = UniversalConverterApp()
    app.mainloop()
