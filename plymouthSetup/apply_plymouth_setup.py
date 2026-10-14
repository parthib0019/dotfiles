#!/usr/bin/env python3
"""
Plymouth Setup Script for RamanOS (rEFInd + mkinitcpio)
-------------------------------------------------------
- Deploys Raman_OS_Style theme to /usr/share/plymouth/themes/Raman_OS_Style
  (Fixes nested folder structure so Raman_OS_Style.plymouth is at theme root).
- Sets theme via /etc/plymouth/plymouthd.conf and default.plymouth symlink.
- Modifies /etc/mkinitcpio.conf (MODULES & HOOKS).
- Modifies rEFInd kernel parameters in refind_linux.conf.
- Updates /etc/cmdline.d/linux.conf.
- Runs `mkinitcpio -P` (GRUB is ignored as requested).

Usage:
    sudo python3 apply_plymouth_setup.py
"""

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Check for nested theme directory structure
POTENTIAL_SRC_1 = SCRIPT_DIR / "Raman_OS_Style" / "Raman_OS_Style"
POTENTIAL_SRC_2 = SCRIPT_DIR / "Raman_OS_Style"

if (POTENTIAL_SRC_1 / "Raman_OS_Style.plymouth").exists():
    THEME_SRC = POTENTIAL_SRC_1
elif (POTENTIAL_SRC_2 / "Raman_OS_Style.plymouth").exists():
    THEME_SRC = POTENTIAL_SRC_2
else:
    THEME_SRC = POTENTIAL_SRC_1

THEME_DIR = Path("/usr/share/plymouth/themes")
THEME_DST = THEME_DIR / "Raman_OS_Style"

def log(msg: str):
    print(f"\033[1;34m[Plymouth Setup]\033[0m {msg}")

def log_success(msg: str):
    print(f"\033[1;32m[Plymouth Setup OK]\033[0m {msg}")

def log_warn(msg: str):
    print(f"\033[1;33m[Plymouth Setup Warning]\033[0m {msg}")

def log_error(msg: str):
    print(f"\033[1;31m[Plymouth Setup Error]\033[0m {msg}")

def check_root():
    if os.getuid() != 0:
        log_error("This script must be run with root privileges. Run: sudo python3 apply_plymouth_setup.py")
        sys.exit(1)

def install_plymouth_theme_files():
    log("Step 1: Deploying Plymouth theme files & default symlink...")
    if not THEME_SRC.exists():
        log_error(f"Source theme directory not found at: {THEME_SRC}")
        sys.exit(1)
        
    os.makedirs(THEME_DIR, exist_ok=True)
    
    if THEME_DST.exists():
        shutil.rmtree(THEME_DST)
    
    shutil.copytree(THEME_SRC, THEME_DST)
    log_success(f"Copied theme files from {THEME_SRC} -> {THEME_DST}")

    # Set default theme via /etc/plymouth/plymouthd.conf
    plymouthd_conf = Path("/etc/plymouth/plymouthd.conf")
    os.makedirs(plymouthd_conf.parent, exist_ok=True)
    with open(plymouthd_conf, "w") as f:
        f.write("[Daemon]\nTheme=Raman_OS_Style\nShowDelay=0\nDeviceTimeout=8\n")
    log_success("Wrote theme config to /etc/plymouth/plymouthd.conf")

    # Set default symlink default.plymouth -> Raman_OS_Style.plymouth
    default_symlink = THEME_DIR / "default.plymouth"
    target_plymouth = THEME_DST / "Raman_OS_Style.plymouth"
    if target_plymouth.exists():
        if default_symlink.is_symlink() or default_symlink.exists():
            default_symlink.unlink()
        default_symlink.symlink_to(target_plymouth)
        log_success(f"Created symlink: {default_symlink} -> {target_plymouth}")
    else:
        log_warn(f"Plymouth file not found at: {target_plymouth}")

def modify_mkinitcpio_conf():
    log("Step 2: Modifying /etc/mkinitcpio.conf...")
    conf_path = Path("/etc/mkinitcpio.conf")
    if not conf_path.exists():
        log_warn("/etc/mkinitcpio.conf not found. Skipping file edit.")
        return

    with open(conf_path, "r") as f:
        content = f.read()

    # 1. Update MODULES=(...)
    gpu_modules = "i915 xe amdgpu radeon nouveau"
    if re.search(r"^MODULES=\(.*\)", content, re.MULTILINE):
        def repl_modules(match):
            existing = match.group(0)
            for mod in gpu_modules.split():
                if mod not in existing:
                    existing = existing.replace("MODULES=(", f"MODULES=({mod} ")
            return existing
        content = re.sub(r"^MODULES=\(.*\)", repl_modules, content, flags=re.MULTILINE)
    else:
        content += f"\nMODULES=({gpu_modules})\n"

    # 2. Update HOOKS=(...) to add plymouth right after base or udev
    if re.search(r"^HOOKS=\(.*\)", content, re.MULTILINE):
        def repl_hooks(match):
            line = match.group(0)
            if "plymouth" not in line:
                if "udev" in line:
                    line = line.replace("udev", "udev plymouth")
                elif "base" in line:
                    line = line.replace("base", "base plymouth")
                else:
                    line = line.replace("HOOKS=(", "HOOKS=(plymouth ")
            return line
        content = re.sub(r"^HOOKS=\(.*\)", repl_hooks, content, flags=re.MULTILINE)

    # Backup original before writing
    shutil.copy(conf_path, Path("/etc/mkinitcpio.conf.bak"))
    with open(conf_path, "w") as f:
        f.write(content)
    log_success("Updated /etc/mkinitcpio.conf (MODULES and HOOKS modified).")

def modify_refind_config():
    log("Step 3: Modifying rEFInd bootloader configuration...")
    refind_configs = [
        Path("/boot/refind_linux.conf"),
        Path("/boot/EFI/refind/refind_linux.conf"),
        Path("/boot/efi/EFI/refind/refind_linux.conf")
    ]
    
    params_to_add = "quiet splash loglevel=3 systemd.show_status=false vt.global_cursor_default=0"
    found_refind = False

    for refind_conf in refind_configs:
        if refind_conf.exists():
            found_refind = True
            log(f"Found rEFInd config at: {refind_conf}")
            with open(refind_conf, "r") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                if '"' in line:
                    parts = line.split('"')
                    if len(parts) >= 4:  # Format: "Title" "options..."
                        options = parts[3]
                        for param in params_to_add.split():
                            if param not in options:
                                options += f" {param}"
                        parts[3] = options.strip()
                        line = '"'.join(parts)
                new_lines.append(line)

            shutil.copy(refind_conf, Path(f"{refind_conf}.bak"))
            with open(refind_conf, "w") as f:
                f.writelines(new_lines)
            log_success(f"Updated rEFInd config: {refind_conf}")

    if not found_refind:
        log_warn("No rEFInd configuration file (refind_linux.conf) found. Creating default at /boot/refind_linux.conf...")
        root_uuid = get_root_uuid()
        boot_options = f"root=UUID={root_uuid} rw {params_to_add}"
        refind_linux_content = (
            f'"Boot RamanOS with standard options"  "{boot_options}"\n'
            f'"Boot RamanOS to terminal (fallback)" "{boot_options.replace("quiet splash", "")} single"\n'
        )
        os.makedirs("/boot", exist_ok=True)
        with open("/boot/refind_linux.conf", "w") as f:
            f.write(refind_linux_content)
        log_success("Created /boot/refind_linux.conf")

def get_root_uuid() -> str:
    if Path("/etc/fstab").exists():
        with open("/etc/fstab", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("UUID=") and "/" in line.split():
                    return line.split()[0].replace("UUID=", "")
    try:
        res = subprocess.run(["lsblk", "-f", "-o", "MOUNTPOINTS,UUID", "-n"], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and "/" in parts:
                return parts[-1]
    except Exception:
        pass
    return "YOUR_ROOT_UUID_HERE"

def modify_cmdline_linux_conf():
    log("Step 4: Creating/updating /etc/cmdline.d/linux.conf...")
    cmdline_dir = Path("/etc/cmdline.d")
    os.makedirs(cmdline_dir, exist_ok=True)
    cmdline_file = cmdline_dir / "linux.conf"

    root_uuid = get_root_uuid()
    cmdline_content = f"root=UUID={root_uuid} rw quiet splash loglevel=3 systemd.show_status=false vt.global_cursor_default=0\n"

    with open(cmdline_file, "w") as f:
        f.write(cmdline_content)
    log_success(f"Wrote {cmdline_file} with root UUID={root_uuid}")

def rebuild_initramfs():
    log("Step 5: Regenerating initramfs with mkinitcpio...")
    if shutil.which("mkinitcpio"):
        try:
            log("Running mkinitcpio -P...")
            subprocess.run(["mkinitcpio", "-P"], check=True)
            log_success("Initial ramdisk (mkinitcpio) rebuilt successfully.")
        except subprocess.CalledProcessError as e:
            log_warn(f"mkinitcpio warning: {e}")

def main():
    print("==================================================")
    print("   RamanOS Plymouth Setup Script (rEFInd Only)   ")
    print("==================================================")
    
    check_root()
    install_plymouth_theme_files()
    modify_mkinitcpio_conf()
    modify_refind_config()
    modify_cmdline_linux_conf()
    rebuild_initramfs()
    
    print("\n==================================================")
    print(" \033[1;32mPlymouth Setup Complete!\033[0m")
    print(" Reboot your system to see your Raman_OS_Style splash!")
    print("==================================================")

if __name__ == "__main__":
    main()
