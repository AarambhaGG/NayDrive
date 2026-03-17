#!/usr/bin/env python3
"""Debug script to diagnose USB detection issues."""

import subprocess
import json
import os

print("=== USB Detection Debug ===\n")

# Test 1: Full lsblk JSON output
print("1. Full lsblk JSON output:")
try:
    result = subprocess.run(
        ["lsblk", "-J", "-b", "-o", "NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT,RM,TYPE,TRAN"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        print(json.dumps(data, indent=2))
    else:
        print(f"Error: {result.stderr}")
except Exception as e:
    print(f"Error running lsblk: {e}")

print("\n2. Simple lsblk list (NAME, RM, TRAN, TYPE):")
try:
    result = subprocess.run(
        ["lsblk", "-n", "-o", "NAME,RM,TRAN,TYPE,SIZE"],
        capture_output=True, text=True, timeout=10,
    )
    print(result.stdout)
except Exception as e:
    print(f"Error: {e}")

print("\n3. Checking /sys/block for removable devices:")
try:
    for dev in os.listdir("/sys/block"):
        removable_path = f"/sys/block/{dev}/removable"
        if os.path.exists(removable_path):
            with open(removable_path) as f:
                removable_val = f.read().strip()
            print(f"  {dev}: removable={removable_val}")
except Exception as e:
    print(f"Error: {e}")
