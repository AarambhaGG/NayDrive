"""
formatter.py — Drive formatting logic for NayDrive.
Handles both Windows (diskpart) and Linux (mkfs.*) formatting.
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import Callable, Optional

from naydrive.drives import DriveInfo
from naydrive.utils import is_windows, is_linux, is_admin, clamp_label


class FormatError(Exception):
    """Raised when a format operation fails."""
    pass


def format_drive(
    drive: DriveInfo,
    fs_type: str,
    label: str,
    quick: bool = True,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Format the given drive.

    Parameters
    ----------
    drive : DriveInfo
        The drive to format.
    fs_type : str
        Target filesystem: FAT32, exFAT, NTFS, or ext4.
    label : str
        Volume label (will be clamped to max allowed length).
    quick : bool
        True for a quick format, False for a full wipe.
    progress_cb : callable, optional
        A callback that receives status strings for UI updates.

    Raises
    ------
    FormatError
        If the formatting process fails.
    """
    label = clamp_label(label.strip(), fs_type)

    def _status(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    _status(f"Preparing to format {drive.path} as {fs_type}...")

    if is_windows():
        _format_windows(drive, fs_type, label, quick, _status)
    elif is_linux():
        _format_linux(drive, fs_type, label, quick, _status)
    else:
        raise FormatError(f"Unsupported platform: {os.name}")

    _status("Format complete!")


# ---------------------------------------------------------------------------
#  Windows formatting via diskpart
# ---------------------------------------------------------------------------

def _format_windows(
    drive: DriveInfo,
    fs_type: str,
    label: str,
    quick: bool,
    status: Callable[[str], None],
) -> None:
    """Format a drive on Windows using diskpart."""
    # Extract the drive letter (e.g. "E" from "E:\\")
    drive_letter = drive.mountpoint.rstrip("\\").rstrip(":")
    if len(drive_letter) != 1 or not drive_letter.isalpha():
        raise FormatError(f"Could not determine drive letter from: {drive.mountpoint}")

    # Map filesystem names to the format diskpart expects
    fs_map = {
        "FAT32": "FAT32",
        "exFAT": "EXFAT",
        "NTFS": "NTFS",
    }
    dp_fs = fs_map.get(fs_type.upper().replace("FAT32", "FAT32").replace("EXFAT", "exFAT"), None)
    dp_fs = fs_map.get(fs_type, None)
    if dp_fs is None:
        raise FormatError(f"Filesystem '{fs_type}' is not supported on Windows.")

    quick_flag = "quick" if quick else ""
    label_part = f'label="{label}"' if label else ""

    # Build diskpart script
    # First we need the disk/volume number.  We'll use a simpler approach:
    # format via the `format` command directly on the volume.
    status("Formatting drive (this may take a moment)...")

    # Using the built-in Windows `format` command is simpler and safer
    # than diskpart for single-partition removable drives.
    cmd = f'format {drive_letter}: /FS:{dp_fs} /V:"{label}" /X'
    if quick:
        cmd += " /Q"
    cmd += " /Y"  # auto-confirm

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for full format
        )
        if result.returncode != 0:
            error_detail = result.stderr.strip() or result.stdout.strip()
            raise FormatError(f"Format command failed:\n{error_detail}")
    except subprocess.TimeoutExpired:
        raise FormatError("Formatting timed out (exceeded 10 minutes).")
    except FormatError:
        raise
    except Exception as e:
        raise FormatError(f"Unexpected error during formatting:\n{e}")


# ---------------------------------------------------------------------------
#  Linux formatting via mkfs.*
# ---------------------------------------------------------------------------

def _canonical_device_path(device: str) -> str:
    """Return a canonical path for a block device when possible."""
    try:
        return str(Path(device).resolve())
    except Exception:
        return device


def _resolve_parent_device(device: str) -> str | None:
    """Resolve the immediate parent block device path for a partition/device mapper."""
    dev = _canonical_device_path(device)
    try:
        result = subprocess.run(
            ["lsblk", "-no", "PKNAME", dev],
            capture_output=True,
            text=True,
            timeout=5,
        )
        parent_name = result.stdout.strip()
        if not parent_name:
            return None
        return _canonical_device_path(f"/dev/{parent_name}")
    except Exception:
        return None


def _all_backing_devices(device: str) -> set[str]:
    """Return the given device plus all parent backing devices."""
    out: set[str] = set()
    current = _canonical_device_path(device)
    while current and current not in out:
        out.add(current)
        current = _resolve_parent_device(current)
    return out


def _get_protected_devices() -> set[str]:
    """Collect all devices that back critical mounts and swap."""
    protected: set[str] = set()
    critical_mounts = ["/", "/boot", "/boot/efi", "/home"]

    for mount in critical_mounts:
        try:
            result = subprocess.run(
                ["findmnt", "-n", "-o", "SOURCE", mount],
                capture_output=True,
                text=True,
                timeout=5,
            )
            source = result.stdout.strip()
            if source.startswith("/dev/"):
                protected.update(_all_backing_devices(source))
        except Exception:
            pass

    try:
        result = subprocess.run(
            ["swapon", "--show=NAME", "--noheadings"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            source = line.strip()
            if source.startswith("/dev/"):
                protected.update(_all_backing_devices(source))
    except Exception:
        pass

    return protected


def _format_linux(
    drive: DriveInfo,
    fs_type: str,
    label: str,
    quick: bool,
    status: Callable[[str], None],
) -> None:
    """Format a drive on Linux using the appropriate mkfs command."""
    device = drive.path  # e.g. /dev/sda
    canonical_device = _canonical_device_path(device)

    # Safety: refuse to format any device linked to critical mounts/swap.
    protected_devs = _get_protected_devices()
    target_devs = _all_backing_devices(canonical_device)
    if target_devs.intersection(protected_devs):
        raise FormatError(f"Refusing to format system device: {device}")

    # Avoid pkexec auto-escalation to prevent confusing auth behavior.
    if not is_admin():
        raise FormatError(
            "Formatting on Linux requires root privileges. "
            "Please relaunch NayDrive with: sudo python -m naydrive"
        )

    # Unmount all partitions of this device first
    status(f"Unmounting all partitions of {device}...")
    try:
        # Try to unmount all partitions (e.g., sda1, sda2, etc.)
        import glob as glob_module
        partitions = glob_module.glob(f"{device}*")
        for part in partitions:
            if part == device:  # Skip the device itself
                continue
            try:
                umount_cmd = ["umount", part]
                subprocess.run(
                    umount_cmd,
                    capture_output=True, text=True, timeout=30,
                )
            except Exception:
                pass  # May already be unmounted, that's fine
    except Exception:
        pass

    # Build the mkfs command for the raw device (will wipe all partitions)
    cmd = _build_mkfs_command(device, fs_type, label, quick)
    status(f"Formatting {device} as {fs_type}...")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            error_detail = result.stderr.strip() or result.stdout.strip()
            raise FormatError(f"mkfs failed (exit {result.returncode}):\n{error_detail}")
    except subprocess.TimeoutExpired:
        raise FormatError("Formatting timed out (exceeded 10 minutes).")
    except FormatError:
        raise
    except Exception as e:
        raise FormatError(f"Unexpected error during formatting:\n{e}")

    # Re-mount (optional — let the DE auto-mount)
    status("Format complete! You may need to re-plug the drive to see it.")


def _build_mkfs_command(
    device: str, fs_type: str, label: str, quick: bool
) -> list[str]:
    """
    Construct the correct mkfs command for the given filesystem type.

    Returns a list of arguments suitable for subprocess.run().
    """
    fs = fs_type.upper()

    if fs == "FAT32":
        cmd = ["mkfs.vfat", "-F", "32"]
        if label:
            cmd += ["-n", label]
        cmd.append(device)
        return cmd

    elif fs == "EXFAT":
        cmd = ["mkfs.exfat"]
        if label:
            cmd += ["-L", label]
        cmd.append(device)
        return cmd

    elif fs == "NTFS":
        cmd = ["mkfs.ntfs"]
        if quick:
            cmd.append("-f")  # fast / quick format
        if label:
            cmd += ["-L", label]
        cmd.append(device)
        return cmd

    elif fs == "EXT4":
        cmd = ["mkfs.ext4", "-F"]  # -F forces creation
        if label:
            cmd += ["-L", label]
        cmd.append(device)
        return cmd

    else:
        raise FormatError(f"Unsupported filesystem type: {fs_type}")
