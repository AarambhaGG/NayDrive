"""
drives.py — USB drive detection for NayDrive.
Uses psutil to enumerate partitions and filters for removable drives only.
"""

import os
import subprocess
from dataclasses import dataclass

import psutil

from naydrive.utils import is_windows, is_linux, format_size


@dataclass
class DriveInfo:
    """Represents a single removable USB drive."""
    path: str           # E.g. "E:\\" on Windows, "/dev/sdb1" on Linux
    mountpoint: str     # Where the drive is mounted (e.g. "E:\\" or "/media/user/USB")
    label: str          # Volume label
    filesystem: str     # Current filesystem (FAT32, NTFS, ext4, …)
    total_size: int     # Size in bytes
    size_pretty: str    # Human-readable size string

    def display_name(self) -> str:
        """Friendly string for showing in the drive list."""
        label_part = self.label if self.label else "No Label"
        return f"{self.mountpoint}  [{label_part}]  {self.size_pretty}  ({self.filesystem})"


# ---------------------------------------------------------------------------
#  Windows drive detection
# ---------------------------------------------------------------------------

def _detect_windows() -> list[DriveInfo]:
    """Detect removable drives on Windows using psutil + win32."""
    drives: list[DriveInfo] = []
    try:
        import ctypes
        # Drive types: 2 = REMOVABLE
        DRIVE_REMOVABLE = 2

        for part in psutil.disk_partitions(all=False):
            # Check if Windows considers this drive removable
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(part.mountpoint)
            if drive_type != DRIVE_REMOVABLE:
                continue

            # Never show C:\ or the system drive
            if part.mountpoint.upper().startswith("C:"):
                continue

            total_size = 0
            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_size = usage.total
            except Exception:
                pass

            label = _get_volume_label_windows(part.mountpoint)
            filesystem = part.fstype if part.fstype else "Unknown"

            drives.append(DriveInfo(
                path=part.device,
                mountpoint=part.mountpoint,
                label=label,
                filesystem=filesystem,
                total_size=total_size,
                size_pretty=format_size(total_size),
            ))
    except Exception:
        pass

    return drives


def _get_volume_label_windows(mountpoint: str) -> str:
    """Retrieve the volume label on Windows via kernel32."""
    try:
        import ctypes
        volume_name_buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.kernel32.GetVolumeInformationW(
            mountpoint,
            volume_name_buf, 256,
            None, None, None, None, 0,
        )
        return volume_name_buf.value or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
#  Linux drive detection
# ---------------------------------------------------------------------------

def _detect_linux() -> list[DriveInfo]:
    """Detect removable drives on Linux by inspecting /sys/block."""
    drives: list[DriveInfo] = []

    for part in psutil.disk_partitions(all=True):
        mountpoint = part.mountpoint

        # Safety: skip critical system mounts
        if mountpoint in ("/", "/boot", "/boot/efi", "/home", "/var", "/tmp"):
            continue
        if mountpoint.startswith("/snap"):
            continue

        # Determine the base block device (e.g. sdb from /dev/sdb1)
        device = part.device  # e.g. /dev/sdb1
        base_dev = os.path.basename(device).rstrip("0123456789")  # sdb

        # Check if the device is removable via sysfs
        removable_path = f"/sys/block/{base_dev}/removable"
        if not os.path.exists(removable_path):
            continue
        try:
            with open(removable_path) as f:
                if f.read().strip() != "1":
                    continue
        except Exception:
            continue

        total_size = 0
        try:
            usage = psutil.disk_usage(mountpoint)
            total_size = usage.total
        except Exception:
            pass

        label = _get_volume_label_linux(device)
        filesystem = part.fstype if part.fstype else "Unknown"

        drives.append(DriveInfo(
            path=device,
            mountpoint=mountpoint,
            label=label,
            filesystem=filesystem,
            total_size=total_size,
            size_pretty=format_size(total_size),
        ))

    return drives


def _get_volume_label_linux(device: str) -> str:
    """Retrieve the volume label on Linux using lsblk."""
    try:
        result = subprocess.run(
            ["lsblk", "-n", "-o", "LABEL", device],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def detect_drives() -> list[DriveInfo]:
    """
    Detect all removable USB drives on the current platform.
    Returns a list of DriveInfo objects.
    """
    if is_windows():
        return _detect_windows()
    elif is_linux():
        return _detect_linux()
    return []
