#!/usr/bin/env python3
"""
Ex-Alta 3 Storage Device Formatter
------------------------------------
Formats and partitions SD cards or USB drives according to the
EX3-SE OBC ICD V0.01 partition layout specification.

Partition layout (applied to both SD Card 0 and SD Card 1):
  1. Housekeeping  ->  3 GB
  2. Logs          ->  3 GB
  3. Software      ->  10 GB
  4. Iris          ->  10 GB
  5. DFGM          ->  6 GB

Filesystem labels follow the format: ex3_<storage|backup>_<icd_label>
The Q7 system image uses these labels to auto-mount partitions via
/dev/disk/by-label/LABEL.

Usage:
  sudo python3 ex3_format_sd.py [--device /dev/sdX] [--role primary|backup]

Requirements:
  - Linux only
  - Must be run as root (sudo)
  - parted, mkfs.ext4 must be installed
"""

import argparse
import json
import os
import subprocess
import sys
import time

# Partition specification from ICD Table 5

PARTITIONS = [
    {"name": "Housekeeping", "label": "hk",   "size_gb": 3},
    {"name": "Logs",         "label": "logs",  "size_gb": 3},
    {"name": "Software",     "label": "fsw",   "size_gb": 10},
    {"name": "Iris",         "label": "iris",  "size_gb": 10},
    {"name": "DFGM",         "label": "dfgm",  "size_gb": 6},
]

TOTAL_REQUIRED_GB = sum(p["size_gb"] for p in PARTITIONS)  # 32 GB

ROLE_LABEL_PREFIX = {
    "primary": "storage",
    "backup":  "backup",
}


def fs_label(role, icd_label):
    """Return the full filesystem label for a partition, e.g. ex3_storage_hk."""
    return f"ex3_{ROLE_LABEL_PREFIX[role]}_{icd_label}"


# Helpers

def run(cmd, check=True, capture=False):
    """Run a shell command, optionally capturing output."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )
    return result


def require_root():
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root (sudo).")
        sys.exit(1)


def require_tools():
    missing = []
    for tool in ["parted", "mkfs.ext4", "lsblk", "wipefs"]:
        result = subprocess.run(["which", tool], capture_output=True)
        if result.returncode != 0:
            missing.append(tool)
    if missing:
        print(f"ERROR: Missing required tools: {', '.join(missing)}")
        print("Install with: sudo apt install parted e2fsprogs util-linux")
        sys.exit(1)


# Device Detection

def list_block_devices():
    """Return a list of removable block devices (SD cards and USB drives)."""
    result = subprocess.run(
        ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,TRAN,HOTPLUG,RM,MOUNTPOINT,VENDOR,MODEL"],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    devices = []

    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        is_removable = dev.get("rm") == "1" or dev.get("hotplug") == "1"
        tran = dev.get("tran", "")
        is_sd_or_usb = tran in ("usb", "sd", "mmc", "") or is_removable

        if is_sd_or_usb and is_removable:
            devices.append({
                "path":   f"/dev/{dev['name']}",
                "name":   dev.get("name"),
                "size":   dev.get("size"),
                "tran":   tran if tran else "unknown",
                "vendor": (dev.get("vendor") or "").strip(),
                "model":  (dev.get("model") or "").strip(),
            })

    return devices


def select_device_interactive(devices):
    """Prompt the user to pick a device from a list."""
    print("\nDetected removable storage devices:")
    print(f"  {'#':<4} {'Device':<16} {'Size':<10} {'Transport':<10} {'Vendor/Model'}")
    print("  " + "-" * 60)
    for i, d in enumerate(devices):
        label = f"{d['vendor']} {d['model']}".strip() or "—"
        print(f"  {i:<4} {d['path']:<16} {d['size']:<10} {d['tran']:<10} {label}")

    print()
    while True:
        choice = input("Enter device number to use, or type a path manually (e.g. /dev/sdb): ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(devices):
                return devices[idx]["path"]
            else:
                print(f"  Invalid number. Enter 0–{len(devices)-1}.")
        elif choice.startswith("/dev/"):
            return choice
        else:
            print("  Please enter a valid number or /dev/... path.")


def resolve_device(args_device):
    """
    Determine the target device. If --device was passed, use it.
    Otherwise auto-detect and present a menu.
    """
    if args_device:
        if not os.path.exists(args_device):
            print(f"ERROR: Device {args_device} does not exist.")
            sys.exit(1)
        return args_device

    devices = list_block_devices()
    if not devices:
        print("ERROR: No removable storage devices detected.")
        print("  Plug in your SD card or USB drive and try again.")
        print("  Or specify a device manually with --device /dev/sdX")
        sys.exit(1)

    if len(devices) == 1:
        print(f"\nAuto-detected one removable device: {devices[0]['path']} ({devices[0]['size']})")
        confirm = input("Use this device? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            sys.exit(0)
        return devices[0]["path"]

    return select_device_interactive(devices)


# Partition node naming

def partition_node(device, number):
    """
    Return the partition device node for a given disk and partition number.
    e.g. /dev/sda -> /dev/sda1, /dev/mmcblk0 -> /dev/mmcblk0p1
    """
    base = os.path.basename(device)
    if base.startswith("mmcblk") or base.startswith("nvme") or base[-1].isdigit():
        return f"{device}p{number}"
    return f"{device}{number}"


# Validation

def validate_device_size(device):
    """Warn if the device is smaller than the required partition total."""
    result = subprocess.run(
        ["lsblk", "-b", "-d", "-o", "SIZE", "--noheadings", device],
        capture_output=True, text=True, check=True
    )
    size_bytes = int(result.stdout.strip())
    size_gb = size_bytes / (1024 ** 3)

    print(f"\n  Device size: {size_gb:.1f} GB")
    print(f"  Required:    {TOTAL_REQUIRED_GB} GB")

    if size_gb < TOTAL_REQUIRED_GB * 0.95:
        print(f"\nWARNING: Device may be too small ({size_gb:.1f} GB < {TOTAL_REQUIRED_GB} GB required).")
        confirm = input("Continue anyway? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            sys.exit(0)


def check_mounted_partitions(device):
    """Abort if any partitions on the device are currently mounted."""
    result = subprocess.run(
        ["lsblk", "-o", "MOUNTPOINT", "--noheadings", device],
        capture_output=True, text=True, check=False
    )
    mounts = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if mounts:
        print(f"\nERROR: Device {device} has mounted partitions: {mounts}")
        print("Unmount them first with: sudo umount /dev/...")
        sys.exit(1)


# Role selection

def select_role(args_role):
    if args_role in ROLE_LABEL_PREFIX:
        return args_role
    print("\nSelect the role for this SD card/drive:")
    print("  [1] Primary storage  (SD Card 0)")
    print("  [2] Backup storage   (SD Card 1)")
    while True:
        choice = input("Enter 1 or 2: ").strip()
        if choice == "1":
            return "primary"
        elif choice == "2":
            return "backup"
        else:
            print("  Please enter 1 or 2.")


# Formatting

def confirm_destructive(device, role):
    print("\n" + "=" * 60)
    print("  ARE YOU SURE?? – ALL DATA WILL BE ERASED !!")
    print("=" * 60)
    print(f"  Device : {device}")
    print(f"  Role   : {role}")
    print(f"  Layout : {len(PARTITIONS)} partitions, Ext4, GPT")
    print()
    confirm = input("Type YES (all caps) to continue: ").strip()
    if confirm != "YES":
        print("Aborted.")
        sys.exit(0)


def wipe_device(device):
    print("\n[1/3] Wiping existing signatures and partition table...")
    run(["wipefs", "--all", "--force", device])
    run(["parted", "-s", device, "mklabel", "gpt"])
    time.sleep(1)  # let the kernel settle


def create_partitions(device, role):
    print("\n[2/3] Creating partitions...")
    start_mb = 1  # 1 MB alignment offset

    for i, part in enumerate(PARTITIONS, start=1):
        size_mb = part["size_gb"] * 1024
        end_mb = start_mb + size_mb
        label = fs_label(role, part["label"])

        print(f"\n  Partition {i}: {label}  ({part['size_gb']} GB)")
        run([
            "parted", "-s", device, "mkpart",
            label,
            "ext4",
            f"{start_mb}MiB",
            f"{end_mb}MiB",
        ])
        start_mb = end_mb

    time.sleep(2)
    run(["partprobe", device], check=False)
    time.sleep(1)


def format_partitions(device, role):
    print("\n[3/3] Formatting partitions as Ext4...")

    for i, part in enumerate(PARTITIONS, start=1):
        node = partition_node(device, i)
        label = fs_label(role, part["label"])

        # Wait for the node to appear
        for _ in range(20):
            if os.path.exists(node):
                break
            time.sleep(0.5)
        else:
            print(f"ERROR: Partition node {node} did not appear. Try running partprobe manually.")
            sys.exit(1)

        print(f"\n  Formatting {node} as ext4 (label: {label})...")
        run([
            "mkfs.ext4",
            "-L", label,
            "-F",
            node,
        ])


# Summary

def print_summary(device, role):
    print("\n" + "-" * 60)
    print("  FORMAT COMPLETE")
    print("-" * 60)
    print(f"  Device : {device}")
    print(f"  Role   : {role}")
    print()
    print(f"  {'#':<4} {'Partition':<16} {'FS Label':<28} {'Size':>6}")
    print("  " + "-" * 58)
    for i, part in enumerate(PARTITIONS, start=1):
        label = fs_label(role, part["label"])
        print(f"  {i:<4} {part['name']:<16} {label:<28} {part['size_gb']:>4} GB")
    print()

    print("  lsblk output:")
    run(["lsblk", "-o", "NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT", device])


# Entry point

def parse_args():
    parser = argparse.ArgumentParser(
        description="Format and partition a storage device for Ex-Alta 3 (OBC ICD V0.01).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 ex3_format_sd.py
      Auto-detect device and prompt for role.

  sudo python3 ex3_format_sd.py --device /dev/sdb --role primary
      Format /dev/sdb as the primary SD card (non-interactive).

  sudo python3 ex3_format_sd.py --device /dev/mmcblk0 --role backup
      Format an SD card reader device as the backup card.
        """,
    )
    parser.add_argument(
        "--device", "-d",
        help="Target block device (e.g. /dev/sdb, /dev/mmcblk0). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--role", "-r",
        choices=["primary", "backup"],
        help="Card role: 'primary' (SD Card 0) or 'backup' (SD Card 1).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("  Ex-Alta 3 Storage Formatter  |  OBC ICD V0.01")
    print("=" * 60)

    require_root()
    require_tools()

    # 1. Resolve device
    device = resolve_device(args.device)
    print(f"\nTarget device: {device}")

    # 2. Safety checks
    validate_device_size(device)
    check_mounted_partitions(device)

    # 3. Select role
    role = select_role(args.role)

    # 4. Final confirmation
    confirm_destructive(device, role)

    # 5. Partition and format
    wipe_device(device)
    create_partitions(device, role)
    format_partitions(device, role)

    # 6. Done
    print_summary(device, role)


if __name__ == "__main__":
    main()
