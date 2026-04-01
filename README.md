# Ex-Alta 3 Storage Formatter

A Python script to format and partition SD cards or USB drives according to the **EX3-SE OBC ICD V0.01** partition layout specification for the Ex-Alta 3 CubeSat mission.

---

## Table of Contents

- [Overview](#overview)
- [Partition Layout](#partition-layout)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Advanced Usage](#advanced-usage)
  - [Command Line Options](#command-line-options)
- [Step-by-Step Walkthrough](#step-by-step-walkthrough)
  - [On Native Linux](#on-native-linux)
  - [On WSL (Windows Subsystem for Linux)](#on-wsl-windows-subsystem-for-linux)
- [Verifying the Result](#verifying-the-result)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Ex-Alta 3 satellite uses two 32GB SD cards for onboard data storage. Each card must be partitioned and formatted in a specific way so that the flight software (OBSW) can find and write to the correct locations.

This script automates the entire process — wiping, partitioning, and formatting — in a single command.

Filesystem labels follow the format `ex3_<storage|backup>_<icd_label>`. The Q7 system image uses these labels to auto-mount the correct partitions via `/dev/disk/by-label/`.

- **SD Card 0** → Primary storage (`ex3_storage_*`)
- **SD Card 1** → Backup storage (`ex3_backup_*`)

---

## Partition Layout

As defined in **Table 5** of the OBC ICD V0.01:

| # | Partition | ICD Label | Size | Primary FS Label | Backup FS Label |
|---|-----------|-----------|------|------------------|-----------------|
| 1 | Housekeeping | `hk` | 3 GB | `ex3_storage_hk` | `ex3_backup_hk` |
| 2 | Logs | `logs` | 3 GB | `ex3_storage_logs` | `ex3_backup_logs` |
| 3 | Software | `fsw` | 10 GB | `ex3_storage_fsw` | `ex3_backup_fsw` |
| 4 | Iris | `iris` | 10 GB | `ex3_storage_iris` | `ex3_backup_iris` |
| 5 | DFGM | `dfgm` | 6 GB | `ex3_storage_dfgm` | `ex3_backup_dfgm` |

**Total required: 32 GB. Filesystem: Ext4. Partition table: GPT.**

---

## Requirements

- **OS:** Linux only (native Ubuntu, or WSL2 on Windows)
- **Python:** Python 3.6 or higher
- **Must be run as root** (`sudo`)
- **Required system tools:**
  - `parted` — creates partitions
  - `e2fsprogs` — provides `mkfs.ext4` for formatting
  - `util-linux` — provides `lsblk` and `wipefs`

---

## Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/AlbertaSat/ex3_es_testing.git
cd ex3_es_testing
```

### Step 2 — Install required system tools

```bash
sudo apt install parted e2fsprogs util-linux python3
```

---

## Usage

### Basic Usage

Plug in your SD card or USB drive, then run:

```bash
sudo python3 tools/ex3_format_sd.py
```

The script will auto-detect your device and walk you through the rest interactively.

---

### Advanced Usage

Specify the device and role directly to skip all prompts:

```bash
# Format as primary SD card (SD Card 0)
sudo python3 tools/ex3_format_sd.py --device /dev/sdb --role primary

# Format as backup SD card (SD Card 1)
sudo python3 tools/ex3_format_sd.py --device /dev/mmcblk0 --role backup
```

---

### Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--device` | `-d` | Target block device (e.g. `/dev/sdb`). Auto-detected if omitted. |
| `--role` | `-r` | Card role: `primary` or `backup`. Prompted if omitted. |

---

## Step-by-Step Walkthrough

### On Native Linux

**1. Plug in your SD card or USB drive.**

**2. Open a terminal and confirm the device is detected:**
```bash
lsblk
```
Look for your device — it will appear as something like `/dev/sdb` or `/dev/mmcblk0`.

**3. Navigate to the repo:**
```bash
cd ~/ex3_es_testing
```

**4. Run the script:**
```bash
sudo python3 tools/ex3_format_sd.py
```

**5. Follow the prompts:**
- Select your device from the list (or confirm the auto-detected one)
- Choose `1` for primary or `2` for backup
- Type `YES` in all caps to confirm the format

**6. Wait for it to complete.** The script will print `FORMAT COMPLETE` when done.

---

### On WSL (Windows Subsystem for Linux)

WSL cannot see USB drives by default. You need to pass the USB through from Windows to Linux using `usbipd`.

**1. Install usbipd on Windows** (one time only):
```powershell
winget install --interactive --exact dorssel.usbipd-win
```
Or download the `.msi` installer from: https://github.com/dorssel/usbipd-win/releases/latest

**2. Open your Ubuntu/WSL terminal and leave it running.**

**3. Open PowerShell as Administrator, plug in your USB drive, then run:**
```powershell
usbipd list
```
Find your USB drive in the list and note its `BUSID` (e.g. `1-14`).

**4. Attach the USB to WSL:**
```powershell
usbipd bind --busid 1-14
usbipd attach --wsl --busid 1-14
```
Replace `1-14` with your actual BUSID.

**5. In your Ubuntu terminal, confirm the device is visible:**
```bash
lsblk
```
Your USB should now appear (e.g. as `/dev/sde`).

**6. Run the script:**
```bash
sudo python3 tools/ex3_format_sd.py --device /dev/sde --role primary
```

---

## Verifying the Result

After the script completes, run the following to verify the partition layout:

```bash
lsblk -o NAME,SIZE,FSTYPE,LABEL /dev/sde
```

Expected output (primary role):

```
NAME     SIZE FSTYPE LABEL
sde    114.6G
├─sde1     3G ext4   ex3_storage_hk
├─sde2     3G ext4   ex3_storage_logs
├─sde3    10G ext4   ex3_storage_fsw
├─sde4    10G ext4   ex3_storage_iris
└─sde5     6G ext4   ex3_storage_dfgm
```

All 5 partitions should be present with the correct sizes, `ext4` filesystem, and correct labels.

---

## Troubleshooting

### ERROR: Must be run as root

**Symptom:**
```
ERROR: This script must be run as root (sudo).
```
**Fix:** Always run the script with `sudo`:
```bash
sudo python3 tools/ex3_format_sd.py
```

---

### ERROR: Missing required tools

**Symptom:**
```
ERROR: Missing required tools: parted, wipefs
```
**Fix:** Install the missing tools:
```bash
sudo apt install parted e2fsprogs util-linux
```

---

### ERROR: No removable storage devices detected

**Symptom:**
```
ERROR: No removable storage devices detected.
```
**Causes and fixes:**

- **USB not plugged in** → Plug it in and try again.
- **On WSL** → You must attach the USB using `usbipd` first (see WSL walkthrough above).
- **Device not detected as removable** → Specify it manually:
  ```bash
  sudo python3 tools/ex3_format_sd.py --device /dev/sde
  ```

---

### ERROR: Device has mounted partitions

**Symptom:**
```
ERROR: Device /dev/sde has mounted partitions.
```
**Fix:** Unmount all partitions on the device first:
```bash
sudo umount /dev/sde1
sudo umount /dev/sde2
sudo umount /dev/sde3
sudo umount /dev/sde4
sudo umount /dev/sde5
```
Or unmount all at once:
```bash
sudo umount /dev/sde*
```

---

### ERROR: Device does not exist

**Symptom:**
```
ERROR: Device /dev/sdb does not exist.
```
**Fix:** Run `lsblk` to find the correct device name and use that instead:
```bash
lsblk
sudo python3 tools/ex3_format_sd.py --device /dev/sde
```

---

### WARNING: Device may be too small

**Symptom:**
```
WARNING: Device may be too small (28.8 GB < 32 GB required).
```
**Fix:** Use a storage device that is at least 32 GB. The script will still let you continue if you type `y`, but the last partition may be smaller than specified.

---

### ERROR: Partition node did not appear

**Symptom:**
```
ERROR: Partition node /dev/sde1 did not appear.
```
**Fix:** The kernel didn't re-read the partition table in time. Run:
```bash
sudo partprobe /dev/sde
```
Then run the script again.

---

### usbipd: No WSL 2 distribution running

**Symptom:**
```
usbipd: error: There is no WSL 2 distribution running
```
**Fix:** Open your Ubuntu/WSL terminal first and leave it open, then run the `usbipd attach` command in PowerShell.

---

### usbipd: command not found

**Symptom:**
```
usbipd : The term 'usbipd' is not recognized
```
**Fix:** Install usbipd on Windows:
```powershell
winget install --interactive --exact dorssel.usbipd-win
```
Then close and reopen PowerShell as Administrator.

---

### Script ran but partitions don't show labels

**Symptom:** `lsblk` shows partitions but the `LABEL` column is empty.

**Fix:** The labels are set during `mkfs.ext4`. Re-run the script — it will reformat and relabel everything correctly.
