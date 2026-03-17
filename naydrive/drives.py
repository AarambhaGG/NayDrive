"""
drives.py — USB drive detection for NayDrive.
Uses psutil to enumerate partitions and filters for removable drives only.
On Linux, also uses lsblk to detect unmounted removable drives.
"""

import json
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
    """Detect removable drives on Windows using psutil + win32.

    Groups partitions by physical device and shows only one entry per device.
    """
    drives: list[DriveInfo] = []
    seen_devices: dict[str, DriveInfo] = {}  # Map device_id -> DriveInfo

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

            # Get a unique identifier for this physical device (serial number)
            device_id = _get_device_id_windows(part.mountpoint)

            # If we've already seen this physical device, update total size
            if device_id in seen_devices:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    seen_devices[device_id].total_size += usage.total
                    seen_devices[device_id].size_pretty = format_size(seen_devices[device_id].total_size)
                except Exception:
                    pass
                continue

            total_size = 0
            try:
                usage = psutil.disk_usage(part.mountpoint)
                total_size = usage.total
            except Exception:
                pass

            label = _get_volume_label_windows(part.mountpoint)
            filesystem = part.fstype if part.fstype else "Unknown"

            drive_info = DriveInfo(
                path=part.device,
                mountpoint=part.mountpoint,
                label=label,
                filesystem=filesystem,
                total_size=total_size,
                size_pretty=format_size(total_size),
            )
            seen_devices[device_id] = drive_info

    except Exception:
        pass

    return list(seen_devices.values())


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


def _get_device_id_windows(mountpoint: str) -> str:
    """Get a unique ID for the physical device (using volume serial number)."""
    try:
        import ctypes
        serial_buf = ctypes.c_ulong()
        ctypes.windll.kernel32.GetVolumeInformationW(
            mountpoint,
            None, 0,
            ctypes.byref(serial_buf),
            None, None, None, 0,
        )
        return f"serial_{serial_buf.value}"
    except Exception:
        # Fallback: use the mountpoint (less reliable but better than nothing)
        return mountpoint


# ---------------------------------------------------------------------------
#  Linux drive detection
# ---------------------------------------------------------------------------

def _detect_linux() -> list[DriveInfo]:
    """Detect removable drives on Linux using lsblk (catches mounted AND unmounted).

    Falls back to the psutil-based approach if lsblk is unavailable.
    """
    drives = _detect_linux_lsblk()
    if drives is not None:
        return drives
    return _detect_linux_psutil()


def _detect_linux_lsblk() -> list[DriveInfo] | None:
    """Use ``lsblk -J`` to find all removable USB devices (not partitions).

    Returns *None* if lsblk is not available so the caller can fall back.
    """
    try:
        result = subprocess.run(
            ["lsblk", "-J", "-b", "-o",
             "NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT,RM,TYPE,TRAN"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
    except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return None

    drives: list[DriveInfo] = []
    seen_devices: set[str] = set()

    for dev in data.get("blockdevices", []):
        # Top-level device: check if it is removable or connected via usb
        removable = dev.get("rm") in (True, "1", 1)
        transport = (dev.get("tran") or "").lower()
        is_usb = removable or transport == "usb"
        if not is_usb:
            continue

        # Only show the parent device, not individual partitions
        if dev.get("type") != "disk":
            continue

        name = dev.get("name", "")
        device_path = f"/dev/{name}"
        if device_path in seen_devices:
            continue
        seen_devices.add(device_path)

        # Use the first child partition's mountpoint if available (or any mounted partition)
        mountpoint = ""
        label = ""
        filesystem = "Unknown"
        children = dev.get("children", [])
        for child in children:
            if child.get("type") == "part":
                child_mount = child.get("mountpoint") or ""
                # Only use safe mount points
                if child_mount and child_mount not in ("/", "/boot", "/boot/efi", "/home", "/var", "/tmp") and not child_mount.startswith("/snap"):
                    mountpoint = child_mount
                    break
                # If this is the first partition, try to use its info
                if not label and not mountpoint:
                    label = child.get("label") or ""
                    filesystem = child.get("fstype") or "Unknown"

        # If no mounted partition found, use first partition's info
        if not label and not mountpoint and children:
            for child in children:
                if child.get("type") == "part":
                    label = child.get("label") or ""
                    filesystem = child.get("fstype") or "Unknown"
                    break

        raw_size = dev.get("size")
        total_size = int(raw_size) if raw_size else 0

        # If any partition is mounted, get accurate size from psutil
        if mountpoint:
            try:
                usage = psutil.disk_usage(mountpoint)
                total_size = usage.total
            except Exception:
                pass

        drives.append(DriveInfo(
            path=device_path,
            mountpoint=mountpoint if mountpoint else "(not mounted)",
            label=label,
            filesystem=filesystem,
            total_size=total_size,
            size_pretty=format_size(total_size),
        ))

    return drives


def _detect_linux_psutil() -> list[DriveInfo]:
    """Fallback: detect removable drives on Linux using psutil + sysfs."""
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
