"""
main.py — Entry point for NayDrive.
Checks for admin/root privileges and launches the GUI.
"""

import sys

from naydrive.utils import is_admin, is_windows, is_linux, request_admin_restart


def main() -> None:
    # ---- Privilege check ------------------------------------------------
    if not is_admin():
        if is_windows():
            # Attempt to re-launch with UAC elevation
            request_admin_restart()
            # If we get here, the re-launch was cancelled or failed
            print("NayDrive requires administrator privileges to format drives.")
            print("Please right-click and select 'Run as administrator'.")
            sys.exit(1)
        elif is_linux():
            print(
                "WARNING: NayDrive is not running as root.\n"
                "Formatting will fail without elevated privileges.\n"
                "Please re-run with:  sudo python -m naydrive"
            )
            # Don't exit — let the user see the UI; they'll get an error
            # when they actually try to format.

    # ---- Launch UI (import here so tkinter isn't loaded during the
    #       privilege re-launch on Windows) --------------------------------
    from naydrive.ui import NayDriveApp

    app = NayDriveApp()
    app.mainloop()


if __name__ == "__main__":
    main()
