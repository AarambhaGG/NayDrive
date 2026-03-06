"""
ui.py — CustomTkinter GUI for NayDrive.
Provides the full desktop interface: drive list, info panel, format options,
progress bar, and confirmation dialogs.
"""

import threading
import customtkinter as ctk
from tkinter import messagebox
from typing import Optional

from naydrive.drives import detect_drives, DriveInfo
from naydrive.formatter import format_drive, FormatError
from naydrive.utils import (
    is_admin,
    is_linux,
    is_windows,
    supported_filesystems,
    format_size,
    clamp_label,
)


class NayDriveApp(ctk.CTk):
    """Main application window."""

    WIDTH = 800
    HEIGHT = 500

    def __init__(self) -> None:
        super().__init__()

        # --- Window setup ------------------------------------------------
        self.title("NayDrive")
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(700, 420)
        self.resizable(True, True)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Try to load icon
        try:
            import os, sys
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        # --- State -------------------------------------------------------
        self.drives: list[DriveInfo] = []
        self.selected_drive: Optional[DriveInfo] = None
        self._formatting = False

        # --- Build UI ----------------------------------------------------
        self._build_layout()

        # --- Initial scan ------------------------------------------------
        self._refresh_drives()

    # =====================================================================
    #  Layout construction
    # =====================================================================

    def _build_layout(self) -> None:
        """Construct all UI widgets."""
        # Configure grid: left panel (weight 1) | right panel (weight 2)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        # ---- Header bar -------------------------------------------------
        header = ctk.CTkFrame(self, height=48, corner_radius=0)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="NayDrive",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=8, sticky="w")

        admin_text = "● Admin" if is_admin() else "● Not Admin"
        admin_color = "#2ecc71" if is_admin() else "#e74c3c"
        ctk.CTkLabel(
            header,
            text=admin_text,
            text_color=admin_color,
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=1, padx=16, pady=8, sticky="e")

        # ---- Left panel: drive list + refresh ---------------------------
        left = ctk.CTkFrame(self, corner_radius=8)
        left.grid(row=1, column=0, padx=(10, 5), pady=10, sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="USB Drives",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")

        # Scrollable frame for drive buttons
        self.drive_list_frame = ctk.CTkScrollableFrame(left, corner_radius=4)
        self.drive_list_frame.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")
        self.drive_list_frame.grid_columnconfigure(0, weight=1)

        self.refresh_btn = ctk.CTkButton(
            left, text="↻  Refresh", command=self._refresh_drives, height=32
        )
        self.refresh_btn.grid(row=2, column=0, padx=8, pady=(0, 10), sticky="ew")

        # ---- Right panel: info + options + button -----------------------
        right = ctk.CTkFrame(self, corner_radius=8)
        right.grid(row=1, column=1, padx=(5, 10), pady=10, sticky="nsew")
        right.grid_rowconfigure(3, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Drive info section
        info_frame = ctk.CTkFrame(right, corner_radius=6, fg_color="transparent")
        info_frame.grid(row=0, column=0, padx=14, pady=(14, 4), sticky="ew")
        info_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            info_frame,
            text="Drive Info",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        labels = ["Path:", "Label:", "Size:", "Filesystem:"]
        self.info_values: list[ctk.CTkLabel] = []
        for i, lbl in enumerate(labels):
            ctk.CTkLabel(info_frame, text=lbl, anchor="w", width=90).grid(
                row=i + 1, column=0, sticky="w", pady=2
            )
            val = ctk.CTkLabel(info_frame, text="—", anchor="w")
            val.grid(row=i + 1, column=1, sticky="w", padx=(6, 0), pady=2)
            self.info_values.append(val)

        # ---- Format options section -------------------------------------
        opts_frame = ctk.CTkFrame(right, corner_radius=6, fg_color="transparent")
        opts_frame.grid(row=1, column=0, padx=14, pady=(10, 4), sticky="ew")
        opts_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            opts_frame,
            text="Format Options",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        # Filesystem selector
        ctk.CTkLabel(opts_frame, text="Filesystem:", anchor="w", width=90).grid(
            row=1, column=0, sticky="w", pady=2
        )
        self.fs_var = ctk.StringVar(value=supported_filesystems()[0])
        self.fs_menu = ctk.CTkOptionMenu(
            opts_frame,
            variable=self.fs_var,
            values=supported_filesystems(),
            width=160,
            command=self._on_fs_change,
        )
        self.fs_menu.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=2)

        # Volume label
        ctk.CTkLabel(opts_frame, text="Label:", anchor="w", width=90).grid(
            row=2, column=0, sticky="w", pady=2
        )
        self.label_entry = ctk.CTkEntry(opts_frame, placeholder_text="MY_USB", width=160)
        self.label_entry.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=2)

        # Label char-limit hint
        self.label_hint = ctk.CTkLabel(
            opts_frame,
            text="Max 11 chars (FAT32)",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.label_hint.grid(row=3, column=1, sticky="w", padx=(6, 0))

        # Quick format toggle
        ctk.CTkLabel(opts_frame, text="Quick Format:", anchor="w", width=90).grid(
            row=4, column=0, sticky="w", pady=2
        )
        self.quick_var = ctk.BooleanVar(value=True)
        self.quick_switch = ctk.CTkSwitch(
            opts_frame, text="", variable=self.quick_var, onvalue=True, offvalue=False
        )
        self.quick_switch.grid(row=4, column=1, sticky="w", padx=(6, 0), pady=2)

        # ---- Format button ----------------------------------------------
        self.format_btn = ctk.CTkButton(
            right,
            text="Format Drive",
            command=self._start_format,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#e74c3c",
            hover_color="#c0392b",
            state="disabled",
        )
        self.format_btn.grid(row=2, column=0, padx=14, pady=(10, 4), sticky="ew")

        # ---- Bottom status bar ------------------------------------------
        status_frame = ctk.CTkFrame(self, height=40, corner_radius=0)
        status_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            status_frame, text="Ready", anchor="w", font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(row=0, column=0, padx=12, pady=6, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(status_frame, width=200, height=14)
        self.progress_bar.grid(row=0, column=1, padx=(0, 12), pady=6, sticky="e")
        self.progress_bar.set(0)

    # =====================================================================
    #  Drive scanning
    # =====================================================================

    def _refresh_drives(self) -> None:
        """Scan for removable drives and populate the left panel."""
        self._set_status("Detecting drives...")
        self.progress_bar.set(0)

        # Clear previous entries
        for widget in self.drive_list_frame.winfo_children():
            widget.destroy()

        self.drives = detect_drives()
        self.selected_drive = None
        self._update_info_panel(None)
        self.format_btn.configure(state="disabled")

        if not self.drives:
            ctk.CTkLabel(
                self.drive_list_frame,
                text="No USB drives detected.\nPlug in a drive and refresh.",
                text_color="gray",
                justify="center",
            ).grid(row=0, column=0, padx=10, pady=20)
            self._set_status("No drives found")
            return

        for idx, drive in enumerate(self.drives):
            btn = ctk.CTkButton(
                self.drive_list_frame,
                text=drive.display_name(),
                anchor="w",
                height=36,
                font=ctk.CTkFont(size=12),
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray75", "gray30"),
                command=lambda d=drive, i=idx: self._select_drive(d, i),
            )
            btn.grid(row=idx, column=0, padx=4, pady=2, sticky="ew")

        self._set_status(f"Found {len(self.drives)} drive(s)")

    def _select_drive(self, drive: DriveInfo, index: int) -> None:
        """Handle a drive being clicked in the left panel."""
        self.selected_drive = drive
        self._update_info_panel(drive)

        # Highlight the selected button
        for i, widget in enumerate(self.drive_list_frame.winfo_children()):
            if isinstance(widget, ctk.CTkButton):
                if i == index:
                    widget.configure(fg_color=("gray70", "gray35"))
                else:
                    widget.configure(fg_color="transparent")

        self.format_btn.configure(state="normal")
        self._set_status(f"Selected: {drive.mountpoint}")

    def _update_info_panel(self, drive: Optional[DriveInfo]) -> None:
        """Populate the drive-info labels on the right panel."""
        if drive is None:
            for val in self.info_values:
                val.configure(text="—")
            return

        self.info_values[0].configure(text=drive.path)
        self.info_values[1].configure(text=drive.label if drive.label else "(none)")
        self.info_values[2].configure(text=drive.size_pretty)
        self.info_values[3].configure(text=drive.filesystem)

    # =====================================================================
    #  Filesystem option helpers
    # =====================================================================

    def _on_fs_change(self, choice: str) -> None:
        """Update the label-length hint when the filesystem selection changes."""
        if choice.upper() == "FAT32":
            self.label_hint.configure(text="Max 11 chars (FAT32)")
        else:
            self.label_hint.configure(text="Max 32 chars")

    # =====================================================================
    #  Format workflow
    # =====================================================================

    def _start_format(self) -> None:
        """Validate inputs, show confirmation, then launch format thread."""
        if self._formatting or self.selected_drive is None:
            return

        drive = self.selected_drive
        fs_type = self.fs_var.get()
        label = self.label_entry.get().strip()
        label = clamp_label(label, fs_type)
        quick = self.quick_var.get()

        # ---- Confirmation dialog ----------------------------------------
        msg = (
            f"WARNING: All data on {drive.mountpoint} will be permanently deleted!\n\n"
            f"Drive: {drive.path}\n"
            f"Size:  {drive.size_pretty}\n"
            f"Label: {drive.label if drive.label else '(none)'}\n\n"
            f"New filesystem: {fs_type}\n"
            f"New label: {label if label else '(none)'}\n"
            f"Quick format: {'Yes' if quick else 'No (full wipe)'}\n\n"
            "Are you sure you want to continue?"
        )
        confirmed = messagebox.askyesno("Confirm Format", msg, icon="warning")
        if not confirmed:
            self._set_status("Format cancelled")
            return

        # ---- Lock UI and start ------------------------------------------
        self._set_formatting_state(True)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()

        thread = threading.Thread(
            target=self._run_format,
            args=(drive, fs_type, label, quick),
            daemon=True,
        )
        thread.start()

    def _run_format(
        self, drive: DriveInfo, fs_type: str, label: str, quick: bool
    ) -> None:
        """Execute the format in a background thread (never call from main thread)."""
        try:
            format_drive(
                drive=drive,
                fs_type=fs_type,
                label=label,
                quick=quick,
                progress_cb=lambda msg: self.after(0, self._set_status, msg),
            )
            self.after(0, self._format_success, drive, fs_type, label)
        except FormatError as e:
            self.after(0, self._format_failure, str(e))
        except Exception as e:
            self.after(0, self._format_failure, f"Unexpected error:\n{e}")

    def _format_success(
        self, drive: DriveInfo, fs_type: str, label: str
    ) -> None:
        """Called on main thread after a successful format."""
        self._set_formatting_state(False)
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(1.0)
        self._set_status("Format complete!")

        messagebox.showinfo(
            "Success",
            f"Drive {drive.mountpoint} formatted successfully!\n\n"
            f"Filesystem: {fs_type}\n"
            f"Label: {label if label else '(none)'}",
        )

        # Refresh drives to pick up new info
        self._refresh_drives()

    def _format_failure(self, error_msg: str) -> None:
        """Called on main thread after a failed format."""
        self._set_formatting_state(False)
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self._set_status("Format failed!")

        messagebox.showerror("Format Error", error_msg)

    # =====================================================================
    #  UI helpers
    # =====================================================================

    def _set_formatting_state(self, formatting: bool) -> None:
        """Enable or disable interactive widgets during formatting."""
        self._formatting = formatting
        state = "disabled" if formatting else "normal"
        self.refresh_btn.configure(state=state)
        self.format_btn.configure(state=state)
        self.fs_menu.configure(state=state)
        self.label_entry.configure(state=state)
        self.quick_switch.configure(state=state)

    def _set_status(self, text: str) -> None:
        """Update the bottom status label."""
        self.status_label.configure(text=text)
