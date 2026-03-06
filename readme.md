# NayDrive

A simple, modern USB formatting tool for **Windows** and **Linux**, built with Python and CustomTkinter.

![Dark theme](https://img.shields.io/badge/theme-dark-1a1a2e)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

## Quick Start - For Everyone

Download the latest release: [NayDrive Releases](https://github.com/yourusername/NayDrive/releases)

Simply download `NayDrive.exe` and run it. No installation required.

---

## Features

- **Auto-detect** all connected removable USB drives
- **Format** to FAT32, exFAT, NTFS, or ext4 (Linux)
- **Quick Format** or full wipe toggle
- **Custom volume label** with per-filesystem character limits
- **Safety first** — system drives are never shown; confirmation dialog before formatting
- **Cross-platform** — works on Windows (diskpart / format) and Linux (mkfs.\*)
- **Dark-themed** modern UI powered by CustomTkinter

---

## Screenshot

![NayDrive Screenshot](naydrive/assets/screenshot.png)

---

## Development

### Project Structure

```
naydrive/
├── __init__.py      # Package marker
├── __main__.py      # python -m naydrive entry
├── main.py          # Privilege check & app launch
├── ui.py            # CustomTkinter GUI
├── drives.py        # USB drive detection (psutil + sysfs / kernel32)
├── formatter.py     # Format commands (diskpart / mkfs)
├── utils.py         # Helpers (OS detection, size formatting, etc.)
└── assets/
    └── icon.ico     # App icon (optional)
```

---

### Requirements

- Python 3.10 or newer
- `customtkinter >= 5.2.0`
- `psutil >= 5.9.0`

### Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

### Running from Source

```bash
# Linux (needs root for formatting)
sudo python -m naydrive

# Windows (will auto-request admin/UAC)
python -m naydrive
```

### Building the Executable

```bash
python -m PyInstaller NayDrive.spec
```

The built executable will be in `dist/NayDrive.exe`.

---

## Packaging with PyInstaller

For custom builds:

```bash
# Windows
pyinstaller --onefile --windowed --icon=naydrive/assets/icon.ico naydrive/main.py --name NayDrive

# Linux
pyinstaller --onefile --windowed naydrive/main.py --name NayDrive
```

The binary will be in `dist/`.

---

## License

MIT
