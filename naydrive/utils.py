"""
utils.py — Helper utilities for NayDrive.
Provides OS detection, size formatting, and privilege checks.
"""

import os
import sys
import platform


def get_os() -> str:
    """Return 'Windows' or 'Linux' (or the raw platform name)."""
    return platform.system()


def is_windows() -> bool:
    return get_os() == "Windows"


def is_linux() -> bool:
    return get_os() == "Linux"


def format_size(size_bytes: int) -> str:
    """Convert a byte count into a human-readable string (e.g. '14.9 GB')."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    size = float(size_bytes)
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.1f} {units[index]}"


def is_admin() -> bool:
    """Check whether the current process has admin/root privileges."""
    if is_windows():
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def request_admin_restart() -> None:
    """
    Attempt to re-launch the application with elevated privileges.
    On Windows: UAC prompt via ShellExecuteW.
    On Linux: prints a message (we can't auto-sudo a GUI app reliably).
    """
    if is_windows():
        try:
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            sys.exit(0)
        except Exception:
            pass  # User cancelled UAC or it failed
    # On Linux we simply inform the user via the UI


def clamp_label(label: str, fs_type: str) -> str:
    """
    Enforce max label length based on filesystem type.
    FAT32 → 11 chars, everything else → 32 chars.
    """
    max_len = 11 if fs_type.upper() == "FAT32" else 32
    return label[:max_len]


def supported_filesystems() -> list[str]:
    """Return the list of filesystem options for the current platform."""
    if is_windows():
        return ["FAT32", "exFAT", "NTFS"]
    else:
        return ["FAT32", "exFAT", "NTFS", "ext4"]
