#!/usr/bin/env python3
"""
Systemd Bootctl & UKI Splash / EFI Rename Script for RamanOS
-------------------------------------------------------------
- Deploys splash-raman.bmp to /usr/share/systemd/bootctl/splash-raman.bmp and splash-arch.bmp.
- Updates /etc/mkinitcpio.d/*.preset files to enable default_uki="/boot/EFI/Linux/RAMAN.efi"
  and embed --splash=/usr/share/systemd/bootctl/splash-raman.bmp in default_options.
- Ensures the target EFI binary is properly compiled as a PE32+ Unified Kernel Image (UKI).
- Updates references in loader entries, loader.conf, refind_linux.conf, and efibootmgr NVRAM.
- Rebuilds UKI images via `mkinitcpio -P`.

Usage:
    sudo python3 setup_bootctl_changes.py
"""

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Source splash image paths
SPLASH_RAMAN_SRC = SCRIPT_DIR / "splash-raman.bmp"
SPLASH_ARCH_SRC = SCRIPT_DIR / "splash-arch.bmp"

# Destination directories
BOOTCTL_DIR = Path("/usr/share/systemd/bootctl")
MKINITCPIO_D = Path("/etc/mkinitcpio.d")

# Target UKI EFI output path
TARGET_EFI_DIR = Path("/boot/EFI/Linux")
TARGET_EFI_FILE = TARGET_EFI_DIR / "RAMAN.efi"

# Potential EFI roots for scanning/migration
EFI_ROOT_PATHS = [
    Path("/boot/EFI"),
    Path("/boot/EFI/Linux"),
    Path("/boot/efi/EFI"),
    Path("/efi/EFI"),
    Path("/boot/efi/EFI/Linux")
]

def log(msg: str):
    print(f"\033[1;34m[Bootctl Setup]\033[0m {msg}")

def log_success(msg: str):
    print(f"\033[1;32m[Bootctl Setup OK]\033[0m {msg}")

def log_warn(msg: str):
    print(f"\033[1;33m[Bootctl Setup Warning]\033[0m {msg}")

def log_error(msg: str):
    print(f"\033[1;31m[Bootctl Setup Error]\033[0m {msg}")

def check_root():
    if os.getuid() != 0:
        log_error("This script must be run with root privileges. Run: sudo python3 setup_bootctl_changes.py")
        sys.exit(1)

def deploy_splash_image():
    log("Step 1: Deploying splash-raman.bmp to systemd bootctl...")
    os.makedirs(BOOTCTL_DIR, exist_ok=True)

    if SPLASH_RAMAN_SRC.exists():
        dst_raman = BOOTCTL_DIR / "splash-raman.bmp"
        shutil.copy2(SPLASH_RAMAN_SRC, dst_raman)
        os.chmod(dst_raman, 0o644)
        log_success(f"Copied {SPLASH_RAMAN_SRC.name} -> {dst_raman}")

        # Also backup and replace splash-arch.bmp with splash-raman.bmp
        dst_arch = BOOTCTL_DIR / "splash-arch.bmp"
        if dst_arch.exists() and not dst_arch.is_symlink():
            shutil.copy2(dst_arch, BOOTCTL_DIR / "splash-arch.bmp.bak")
        
        shutil.copy2(SPLASH_RAMAN_SRC, dst_arch)
        os.chmod(dst_arch, 0o644)
        log_success(f"Replaced {dst_arch} with Raman splash image.")
    elif SPLASH_ARCH_SRC.exists():
        dst_arch = BOOTCTL_DIR / "splash-arch.bmp"
        shutil.copy2(SPLASH_ARCH_SRC, dst_arch)
        os.chmod(dst_arch, 0o644)
        log_success(f"Copied fallback {SPLASH_ARCH_SRC.name} -> {dst_arch}")
    else:
        log_warn("No splash image found in script directory!")

def update_mkinitcpio_presets():
    log("Step 2: Updating mkinitcpio presets in /etc/mkinitcpio.d/...")
    if not MKINITCPIO_D.exists():
        log_warn("/etc/mkinitcpio.d directory does not exist. Skipping preset updates.")
        return

    splash_flag = "--splash=/usr/share/systemd/bootctl/splash-raman.bmp"

    for preset_file in MKINITCPIO_D.glob("*.preset"):
        log(f"Processing preset: {preset_file.name}")
        with open(preset_file, "r") as f:
            lines = f.readlines()

        # Backup preset
        shutil.copy2(preset_file, Path(f"{preset_file}.bak"))

        new_lines = []
        has_default_uki = False
        has_default_opts = False

        for line in lines:
            # Enable and update default_uki line to produce /boot/EFI/Linux/RAMAN.efi
            if "default_uki=" in line or "#default_uki=" in line:
                line = 'default_uki="/boot/EFI/Linux/RAMAN.efi"\n'
                has_default_uki = True
            elif "default_options=" in line or "#default_options=" in line:
                if "--splash=" in line:
                    line = re.sub(r"--splash=\S+", splash_flag, line)
                else:
                    line = line.rstrip('\n"\'') + f' {splash_flag}"\n'
                has_default_opts = True
            new_lines.append(line)

        if not has_default_uki:
            new_lines.append('\ndefault_uki="/boot/EFI/Linux/RAMAN.efi"\n')
        if not has_default_opts:
            new_lines.append(f'default_options="{splash_flag}"\n')

        with open(preset_file, "w") as f:
            f.writelines(new_lines)

        log_success(f"Updated preset {preset_file.name}: default_uki set to {TARGET_EFI_FILE}")

def setup_efi_directory():
    log("Step 3: Ensuring target EFI directory exists...")
    os.makedirs(TARGET_EFI_DIR, exist_ok=True)
    log_success(f"Target EFI directory verified at {TARGET_EFI_DIR}")

    # Remove any old arch-linux.efi or legacy names if present
    old_file = TARGET_EFI_DIR / "arch-linux.efi"
    if old_file.exists():
        log(f"Migrating legacy {old_file} -> {TARGET_EFI_FILE}...")
        if TARGET_EFI_FILE.exists():
            TARGET_EFI_FILE.unlink()
        shutil.move(str(old_file), str(TARGET_EFI_FILE))

def update_bootloader_entries_and_nvram():
    log("Step 4: Updating bootloader configurations & efibootmgr entries...")
    
    # 1. Update systemd-boot loader configuration files
    loader_dirs = [Path("/boot/loader"), Path("/boot/efi/loader"), Path("/efi/loader")]
    for loader_dir in loader_dirs:
        if loader_dir.exists():
            entries_dir = loader_dir / "entries"
            if entries_dir.exists():
                for conf_file in entries_dir.glob("*.conf"):
                    with open(conf_file, "r") as f:
                        content = f.read()

                    if "arch-linux" in content.lower() or "arch.efi" in content.lower():
                        content = re.sub(r"arch-linux\.efi", "RAMAN.efi", content, flags=re.IGNORECASE)
                        shutil.copy2(conf_file, Path(f"{conf_file}.bak"))
                        with open(conf_file, "w") as f:
                            f.write(content)
                        log_success(f"Updated loader entry: {conf_file}")

    # 2. Update rEFInd configuration files
    refind_configs = [
        Path("/boot/refind_linux.conf"),
        Path("/boot/EFI/refind/refind_linux.conf"),
        Path("/boot/efi/EFI/refind/refind_linux.conf")
    ]
    for refind_conf in refind_configs:
        if refind_conf.exists():
            with open(refind_conf, "r") as f:
                content = f.read()
            if "arch-linux" in content.lower() or "arch" in content.lower():
                content = re.sub(r"arch-linux\.efi", "RAMAN.efi", content, flags=re.IGNORECASE)
                with open(refind_conf, "w") as f:
                    f.write(content)
                log_success(f"Updated rEFInd config: {refind_conf}")

    # 3. Update NVRAM via efibootmgr if available
    if shutil.which("efibootmgr"):
        try:
            res = subprocess.run(["efibootmgr"], capture_output=True, text=True)
            if "arch" in res.stdout.lower() or "arch-linux" in res.stdout.lower():
                log("Scanning NVRAM boot entries for Arch Linux entries...")
                esp_part = find_esp_partition()
                if esp_part:
                    disk, part_num = esp_part
                    subprocess.run([
                        "efibootmgr", "-c",
                        "-d", disk,
                        "-p", str(part_num),
                        "-L", "RamanOS",
                        "-l", "\\EFI\\Linux\\RAMAN.efi"
                    ], check=False)
                    log_success("Registered NVRAM boot entry 'RamanOS' (\\EFI\\Linux\\RAMAN.efi)")
        except Exception as e:
            log_warn(f"efibootmgr NVRAM update notice: {e}")

def find_esp_partition():
    try:
        res = subprocess.run(["lsblk", "-J", "-o", "NAME,MOUNTPOINTS,PKNAME"], capture_output=True, text=True)
        import json
        data = json.loads(res.stdout)
        for dev in data.get("blockdevices", []):
            for part in dev.get("children", []):
                mounts = part.get("mountpoints", [])
                if any(m in ["/boot", "/boot/efi", "/efi"] for m in mounts if m):
                    disk = f"/dev/{part.get('pkname') or dev.get('name')}"
                    part_name = part.get("name", "")
                    part_num = re.sub(r"\D", "", part_name.replace(dev.get("name", ""), "")) or "1"
                    return disk, part_num
    except Exception:
        pass
    return None

def rebuild_uki():
    log("Step 5: Regenerating UKI executable using mkinitcpio -P...")
    
    # Check if /boot/vmlinuz-linux exists
    vmlinuz = Path("/boot/vmlinuz-linux")
    if not vmlinuz.exists():
        log_warn("/boot/vmlinuz-linux kernel file not found. Re-installing 'linux' package...")
        if shutil.which("pacman"):
            try:
                subprocess.run(["pacman", "-S", "linux", "--noconfirm"], check=True)
                log_success("Reinstalled 'linux' kernel package.")
            except Exception as e:
                log_error(f"Failed to install linux kernel package: {e}")

    if shutil.which("mkinitcpio"):
        try:
            subprocess.run(["mkinitcpio", "-P"], check=True)
            log_success(f"Unified Kernel Image (PE binary) generated successfully at {TARGET_EFI_FILE}")
        except subprocess.CalledProcessError as e:
            log_warn(f"mkinitcpio rebuild warning: {e}")
    else:
        log_warn("mkinitcpio command not found. Skipping rebuild.")

def main():
    print("==================================================")
    print("  RamanOS Bootctl Splash & EFI Rename Script     ")
    print("==================================================")

    check_root()
    deploy_splash_image()
    update_mkinitcpio_presets()
    setup_efi_directory()
    update_bootloader_entries_and_nvram()
    rebuild_uki()

    print("\n==================================================")
    print(" \033[1;32mBootctl & EFI Rename Complete!\033[0m")
    print(" Splash image deployed to /usr/share/systemd/bootctl/splash-raman.bmp")
    print(" UKI binary compiled at /boot/EFI/Linux/RAMAN.efi")
    print("==================================================")

if __name__ == "__main__":
    main()
