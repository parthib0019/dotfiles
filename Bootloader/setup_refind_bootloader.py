#!/usr/bin/env python3
"""
RamanOS rEFInd Bootloader Setup & Environment Automation Script
---------------------------------------------------------------
Robust, cross-platform installer supporting BOTH Windows and Linux (UEFI).

Features:
  1. Safe ESP detection via standard UEFI GPT GUID (c12a7328-...) and mountvol.
  2. Cross-distro & cross-platform dependency and binary acquisition.
  3. Deploys rEFInd, RamanOS theme, and custom configuration.
  4. Deploys universal UEFI fallback loader (EFI/BOOT/bootx64.efi).
  5. Safely generates /boot/refind_linux.conf from /proc/cmdline on Linux.
  6. Registers bootloader as 'raman_os' and sets boot sequence priority.
  7. Detects firmware lockouts / Secure Boot and provides manual BIOS guidance.

Usage:
  Linux:   sudo python3 setup_refind_bootloader.py
  Windows: python setup_refind_bootloader.py (in Admin CMD/PowerShell)
"""

import os
import re
import sys
import shutil
import string
import urllib.request
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Tuple

BOOTLOADER_NAME = "raman_os"
REFIND_VERSION = "0.14.2"
REFIND_URL = (
    f"https://sourceforge.net/projects/refind/files/{REFIND_VERSION}/"
    f"refind-bin-{REFIND_VERSION}.zip/download"
)
ESP_GUID = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"

SCRIPT_DIR = Path(__file__).resolve().parent
THEME_SRC = SCRIPT_DIR / "raman-theme"
CUSTOM_REFIND_CONF = SCRIPT_DIR / "refind.conf"
LOCAL_REFIND_DIR = SCRIPT_DIR / "refind"


def log(msg: str):
    print(f"\033[1;34m[rEFInd Setup]\033[0m {msg}")


def log_success(msg: str):
    print(f"\033[1;32m[rEFInd Setup OK]\033[0m {msg}")


def log_warn(msg: str):
    print(f"\033[1;33m[rEFInd Setup Warning]\033[0m {msg}")


def log_error(msg: str):
    print(f"\033[1;31m[rEFInd Setup Error]\033[0m {msg}")


# =====================================================================
# STAGE 1: PLATFORM & PRIVILEGE VERIFICATION
# =====================================================================

def is_windows() -> bool:
    return sys.platform == "win32"


def check_privileges():
    if is_windows():
        import ctypes
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
        if not is_admin:
            log_error("Administrator privileges required on Windows.")
            log_error("Please right-click PowerShell or CMD, choose 'Run as Administrator', and run again.")
            sys.exit(1)
        log_success("Running with Administrator privileges on Windows.")
    else:
        if os.geteuid() != 0:
            log_error("This script must be run with root privileges. Run: sudo python3 setup_refind_bootloader.py")
            sys.exit(1)
        log_success("Running with root privileges on Linux.")


def verify_uefi_environment():
    log("Verifying UEFI firmware environment...")
    if not is_windows():
        if not Path("/sys/firmware/efi").exists():
            log_error("System does not appear to be booted in UEFI mode (/sys/firmware/efi missing).")
            log_error("rEFInd requires a UEFI system to function.")
            sys.exit(1)
    log_success("UEFI mode verified.")


# =====================================================================
# STAGE 2: ROBUST EFI SYSTEM PARTITION (ESP) MANAGEMENT
# =====================================================================

def get_free_windows_drive_letter() -> str:
    import ctypes
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letter in reversed(string.ascii_uppercase):
        if not (bitmask & (1 << (ord(letter) - ord("A")))):
            return letter
    return "S"


class WindowsESPManager:
    """Mounts hidden Windows ESP to a temporary drive letter and cleans up on exit."""
    def __init__(self, drive_letter: Optional[str] = None):
        self.drive_letter = drive_letter or get_free_windows_drive_letter()
        self.mount_path = Path(f"{self.drive_letter}:\\")

    def __enter__(self) -> Path:
        log(f"Mounting EFI System Partition to drive {self.drive_letter}: via mountvol...")
        cmd = ["mountvol", f"{self.drive_letter}:", "/S"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"mountvol failed to mount ESP:\n{res.stderr.strip() or res.stdout.strip()}")
        log_success(f"ESP mounted at {self.mount_path}")
        return self.mount_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        log(f"Unmounting ESP from drive {self.drive_letter}: ...")
        subprocess.run(["mountvol", f"{self.drive_letter}:", "/D"], capture_output=True)
        log_success("ESP unmounted cleanly.")


def find_linux_esp() -> Tuple[str, str, int, Optional[str]]:
    """Identifies the true ESP via the standard GPT Partition Type GUID."""
    import json
    cmd = ["lsblk", "--json", "-o", "NAME,PATH,PKNAME,PARTNUM,PARTTYPE,MOUNTPOINTS,FSTYPE"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        block_data = json.loads(res.stdout)
    except Exception as e:
        log_warn(f"lsblk JSON lookup failed ({e}). Falling back to mount scan.")
        return fallback_scan_mounts()

    def scan(devs):
        for dev in devs:
            part_type = (dev.get("parttype") or "").lower()
            fs_type = (dev.get("fstype") or "").lower()
            # Must match ESP GUID and be FAT/vfat
            if part_type == ESP_GUID or (fs_type == "vfat" and any("efi" in str(m).lower() for m in dev.get("mountpoints", []))):
                mounts = [m for m in dev.get("mountpoints", []) if m]
                return (
                    dev["path"],
                    dev.get("pkname") or dev["path"],
                    int(dev.get("partnum") or 1),
                    mounts[0] if mounts else None,
                )
            if "children" in dev:
                found = scan(dev["children"])
                if found:
                    return found
        return None

    result = scan(block_data.get("blockdevices", []))
    if result:
        return result
    return fallback_scan_mounts()


def fallback_scan_mounts() -> Tuple[str, str, int, Optional[str]]:
    mounts = Path("/proc/mounts").read_text().splitlines()
    for line in mounts:
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "vfat":
            m_point = Path(parts[1])
            # Never treat non-FAT /boot as ESP!
            if (m_point / "EFI").exists() or m_point in [Path("/boot/efi"), Path("/efi"), Path("/boot/EFI")]:
                return parts[0], parts[0], 1, str(m_point)
    raise RuntimeError("Could not locate a valid FAT32 EFI System Partition.")


class LinuxESPManager:
    """Manages ESP access on Linux, auto-mounting if unmounted. Never creates fake dirs on '/'."""
    def __init__(self):
        self.part_path, self.disk_path, self.part_num, self.existing_mount = find_linux_esp()
        self.temp_mount: Optional[str] = None

    def __enter__(self) -> Tuple[Path, str, int]:
        if self.existing_mount:
            log_success(f"Found active ESP mount at: {self.existing_mount}")
            return Path(self.existing_mount), self.disk_path, self.part_num

        self.temp_mount = tempfile.mkdtemp(prefix="esp_mount_")
        log(f"ESP is unmounted. Mounting {self.part_path} -> {self.temp_mount}...")
        subprocess.run(["mount", "-t", "vfat", self.part_path, self.temp_mount], check=True)
        return Path(self.temp_mount), self.disk_path, self.part_num

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_mount:
            log(f"Unmounting temporary ESP from {self.temp_mount}...")
            subprocess.run(["umount", self.temp_mount], check=True)
            try:
                Path(self.temp_mount).rmdir()
            except OSError:
                pass


# =====================================================================
# STAGE 3: DEPENDENCIES & PACKAGE MANAGEMENT
# =====================================================================

def verify_and_acquire_binaries(temp_workspace: Path) -> Path:
    """Acquires rEFInd binaries from local repo, package manager, or official zip."""
    # 1. Check local directory
    for candidate in [LOCAL_REFIND_DIR / "refind_x64.efi", SCRIPT_DIR / "refind_x64.efi"]:
        if candidate.exists() and candidate.parent.exists():
            log_success(f"Found local rEFInd binaries in: {candidate.parent}")
            return candidate.parent

    # 2. Try Linux package managers if on Linux
    if not is_windows():
        if shutil.which("refind-install") and Path("/usr/share/refind").exists():
            log_success("Using system-installed rEFInd package.")
            return Path("/usr/share/refind")

        log("Checking for distro package managers to install dependencies...")
        for pm, cmd in [
            ("pacman", ["pacman", "-S", "--needed", "--noconfirm", "refind", "efibootmgr"]),
            ("apt-get", ["apt-get", "update", "&&", "apt-get", "install", "-y", "refind", "efibootmgr"]),
            ("dnf", ["dnf", "install", "-y", "refind", "efibootmgr"]),
        ]:
            if shutil.which(pm):
                try:
                    log(f"Attempting dependency install via {pm}...")
                    subprocess.run(cmd if pm != "apt-get" else "apt-get install -y refind efibootmgr", shell=(pm == "apt-get"), check=True)
                    if Path("/usr/share/refind").exists():
                        return Path("/usr/share/refind")
                except Exception:
                    pass

    # 3. Fallback: Download official signed release
    zip_path = temp_workspace / "refind.zip"
    log(f"Downloading official rEFInd v{REFIND_VERSION} binary release...")
    try:
        urllib.request.urlretrieve(REFIND_URL, zip_path)
    except Exception as e:
        raise RuntimeError(f"Failed to acquire rEFInd: {e}")

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(temp_workspace)

    extracted_dir = temp_workspace / f"refind-bin-{REFIND_VERSION}" / "refind"
    if not extracted_dir.exists():
        raise RuntimeError("Unexpected rEFInd archive structure.")
    log_success("Extracted rEFInd binaries successfully.")
    return extracted_dir


# =====================================================================
# STAGE 4: INSTALLATION, THEME & KERNEL CONFIGURATION
# =====================================================================

def deploy_refind(esp_root: Path, refind_src: Path) -> Path:
    """Deploys rEFInd, RamanOS theme, and fallback loader into the ESP."""
    target_dir = esp_root / "EFI" / "refind"
    target_dir.mkdir(parents=True, exist_ok=True)
    log(f"Deploying rEFInd files to {target_dir}...")

    # Copy core binary
    efi_bin = refind_src / "refind_x64.efi"
    if not efi_bin.exists():
        # Search nested directories
        matches = list(refind_src.glob("**/refind_x64.efi"))
        if matches:
            efi_bin = matches[0]
        else:
            raise FileNotFoundError("Could not find refind_x64.efi")

    shutil.copy2(efi_bin, target_dir / "refind_x64.efi")
    log_success("Copied refind_x64.efi to EFI/refind/")

    # Deploy Universal UEFI Fallback Loader (UEFI Spec Section 3.4.1.1)
    fallback_dir = esp_root / "EFI" / "BOOT"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    fallback_bin = fallback_dir / "bootx64.efi"
    if fallback_bin.exists() and not (fallback_dir / "bootx64.efi.orig").exists():
        try:
            shutil.copy2(fallback_bin, fallback_dir / "bootx64.efi.orig")
            log_success("Backed up existing EFI/BOOT/bootx64.efi -> bootx64.efi.orig")
        except Exception:
            pass
    shutil.copy2(efi_bin, fallback_bin)
    log_success(f"Deployed fallback UEFI loader: {fallback_bin}")

    # Copy drivers and icons
    for folder in ["icons", "drivers_x64"]:
        src_folder = refind_src / folder
        if src_folder.exists():
            shutil.copytree(src_folder, target_dir / folder, dirs_exist_ok=True)
            log_success(f"Copied {folder}/")

    # Deploy RamanOS Theme
    theme_target = target_dir / "themes" / "raman-theme"
    if THEME_SRC.exists():
        log(f"Deploying RamanOS theme from {THEME_SRC}...")
        theme_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(THEME_SRC, theme_target, dirs_exist_ok=True)
        log_success("RamanOS theme files copied successfully.")

    # Deploy and configure refind.conf
    conf_target = target_dir / "refind.conf"
    if CUSTOM_REFIND_CONF.exists():
        try:
            shutil.copy2(CUSTOM_REFIND_CONF, conf_target)
            log_success("Copied custom refind.conf.")
        except Exception:
            pass

    if not conf_target.exists():
        sample_conf = refind_src / "refind.conf-sample"
        if sample_conf.exists():
            shutil.copy2(sample_conf, conf_target)
            log_success("Initialized refind.conf from sample.")

    # Ensure critical directives exist in refind.conf
    if conf_target.exists():
        try:
            content = conf_target.read_text(encoding="utf-8", errors="ignore")
            additions = []
            if "default_selection" not in content:
                additions.append(f'default_selection "{BOOTLOADER_NAME}"')
            if "timeout" not in content:
                additions.append("timeout 5")
            include_directive = "include themes/raman-theme/theme.conf"
            if THEME_SRC.exists() and include_directive not in content:
                additions.append(f"\n# RamanOS Theme\n{include_directive}")

            if additions:
                with open(conf_target, "a", encoding="utf-8") as f:
                    f.write("\n" + "\n".join(additions) + "\n")
                log_success("Configured refind.conf auto-boot and theme directives.")
        except Exception as e:
            log_warn(f"Could not update refind.conf: {e}")

    return target_dir


def configure_refind_linux_conf():
    """
    Safely configures /boot/refind_linux.conf on Linux.
    Uses /proc/cmdline from the active running system to prevent Kernel Panics.
    """
    if is_windows() or not Path("/boot").exists():
        return

    log("Configuring /boot/refind_linux.conf kernel command line...")

    # Extract working root options from running kernel cmdline
    active_cmdline = ""
    if Path("/proc/cmdline").exists():
        active_cmdline = Path("/proc/cmdline").read_text().strip()

    # Find root= specification
    root_arg = ""
    for token in active_cmdline.split():
        if token.startswith("root="):
            root_arg = token
            break

    if not root_arg:
        # Fallback to fstab check
        if Path("/etc/fstab").exists():
            for line in Path("/etc/fstab").read_text().splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] == "/":
                    root_arg = f"root={parts[0]}"
                    break

    if not root_arg:
        log_warn("Could not determine root filesystem identifier. Leaving existing refind_linux.conf untouched to avoid Kernel Panic.")
        return

    boot_options = f"{root_arg} rw quiet splash loglevel=3 systemd.show_status=false vt.global_cursor_default=0"
    content = (
        f'"Boot RamanOS with standard options"  "{boot_options}"\n'
        f'"Boot RamanOS to terminal (fallback)" "{boot_options.replace("quiet splash", "")} single"\n'
    )

    targets = [Path("/boot/refind_linux.conf"), Path("/boot/EFI/refind/refind_linux.conf")]
    for t in targets:
        if t.parent.exists():
            try:
                t.write_text(content, encoding="utf-8")
                log_success(f"Wrote validated kernel options to {t}")
            except Exception as e:
                log_warn(f"Could not write {t}: {e}")


# =====================================================================
# STAGE 5: BOOT SEQUENCE & NVRAM CONFIGURATION
# =====================================================================

def print_manual_bios_instructions(reason: str = ""):
    print("\n" + "=" * 72)
    print("        MANUAL ACTION REQUIRED: SET BOOT SEQUENCE IN BIOS/UEFI")
    print("=" * 72)
    if reason:
        print(f" Reason: {reason}\n")

    print(" Most desktop and laptop motherboards (HP, ASUS, Dell, Lenovo, Acer, MSI)")
    print(" lock their NVRAM boot priorities against software changes or reset them to Windows.")
    print(" To make 'raman_os' start automatically on every boot, follow these steps:\n")

    print(" 1. RESTART your computer.")
    print(" 2. During the manufacturer splash logo, repeatedly press your BIOS setup key:")
    print("      • ASUS:         Press F2 or DEL")
    print("      • HP:           Press F10 or ESC")
    print("      • Dell:         Press F2 or F12")
    print("      • Lenovo:       Press F2 or Fn+F2 (or Novo Button)")
    print("      • Acer:         Press F2 or DEL")
    print("      • MSI:          Press DEL")
    print("      • Gigabyte:     Press DEL or F12")
    print()
    print(" 3. Navigate to the 'Boot' or 'Boot Priority' menu:")
    print("      • Look for 'Boot Option Priorities' or 'OS Boot Manager'.")
    print(f"      • Select '{BOOTLOADER_NAME}' and move it to the very TOP (Position #1).")
    print("        (Use the '+' key, F5/F6, or arrow keys depending on your BIOS).")
    print()
    print(" 4. (CRITICAL) If Secure Boot is ON:")
    print("      • Go to the 'Security' or 'Boot' tab.")
    print("      • Set 'Secure Boot' to 'Disabled'.")
    print("      • (If Secure Boot is enabled, the motherboard will silently skip custom bootloaders).")
    print()
    print(" 5. Press F10 to 'Save and Exit'.")
    print("=" * 72 + "\n")


def configure_nvram_windows(esp_drive: str) -> bool:
    log(f"Registering '{BOOTLOADER_NAME}' in Windows BCD Firmware Boot Manager ({{fwbootmgr}})...")

    # Disable Fast Startup so cold boot order is respected
    try:
        subprocess.run(["powercfg", "/h", "off"], capture_output=True, check=False)
        log_success("Disabled Fast Startup via powercfg.")
    except Exception:
        pass

    # Check Secure Boot
    sb_enabled = False
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", "Confirm-SecureBootUEFI"], capture_output=True, text=True)
        if "true" in res.stdout.lower():
            sb_enabled = True
            log_warn("Secure Boot is ENABLED in your UEFI firmware. It must be disabled in BIOS.")
    except Exception:
        pass

    guid = None
    cmd_create = ["bcdedit", "/create", "/d", BOOTLOADER_NAME, "/application", "bootapp"]
    res_create = subprocess.run(cmd_create, capture_output=True, text=True)

    if res_create.returncode == 0:
        match = re.search(r"\{([0-9a-fA-F\-]+)\}", res_create.stdout)
        if match:
            guid = f"{{{match.group(1)}}}"
            log_success(f"Created BCD firmware entry '{BOOTLOADER_NAME}' with GUID: {guid}")
    else:
        enum_res = subprocess.run(["bcdedit", "/enum", "firmware"], capture_output=True, text=True)
        if enum_res.returncode == 0:
            for entry in enum_res.stdout.split("-------------------"):
                if BOOTLOADER_NAME in entry:
                    m = re.search(r"identifier\s+(\{[0-9a-fA-F\-]+\})", entry)
                    if m:
                        guid = m.group(1)
                        break

    sequence_ok = False
    if guid:
        subprocess.run(["bcdedit", "/set", guid, "path", r"\EFI\refind\refind_x64.efi"], check=False)
        clean_drive = esp_drive.rstrip("\\")
        subprocess.run(["bcdedit", "/set", guid, "device", f"partition={clean_drive}"], check=False)

        res_order = subprocess.run(["bcdedit", "/set", "{fwbootmgr}", "displayorder", guid, "/addfirst"], capture_output=True, text=True)
        res_def = subprocess.run(["bcdedit", "/set", "{fwbootmgr}", "default", guid], capture_output=True, text=True)
        if res_order.returncode == 0 and res_def.returncode == 0:
            log_success(f"Programmed '{BOOTLOADER_NAME}' to position 0 in firmware BootOrder.")
            sequence_ok = True

    # Fail-Safe redirection on {bootmgr}
    subprocess.run(["bcdedit", "/set", "{bootmgr}", "path", r"\EFI\refind\refind_x64.efi"], check=False)
    subprocess.run(["bcdedit", "/set", "{bootmgr}", "description", BOOTLOADER_NAME], check=False)

    return sequence_ok and not sb_enabled


def configure_nvram_linux(disk_dev: str, part_num: int) -> bool:
    if not shutil.which("efibootmgr"):
        log_warn("efibootmgr not found. Skipping NVRAM registration.")
        return False

    log(f"Registering '{BOOTLOADER_NAME}' in UEFI NVRAM (Disk: {disk_dev}, Part: {part_num})...")

    # Clean old duplicates
    try:
        out = subprocess.run(["efibootmgr"], capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            if BOOTLOADER_NAME in line and line.startswith("Boot"):
                m = re.match(r"Boot([0-9a-fA-F]{4})", line)
                if m:
                    subprocess.run(["efibootmgr", "-b", m.group(1), "-B"], capture_output=True)
    except Exception:
        pass

    cmd = [
        "efibootmgr",
        "--create",
        "--disk", disk_dev,
        "--part", str(part_num),
        "--loader", r"\EFI\refind\refind_x64.efi",
        "--label", BOOTLOADER_NAME,
        "--verbose",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        log_success(f"'{BOOTLOADER_NAME}' registered and placed at top of UEFI BootOrder.")
        return True
    return False


# =====================================================================
# MAIN ENTRYPOINT
# =====================================================================

def main():
    print("==================================================")
    print(f"    RamanOS {BOOTLOADER_NAME} Bootloader Setup Script       ")
    print("==================================================")

    check_privileges()
    verify_uefi_environment()

    sequence_ok = False

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_workspace = Path(tmpdir)
        refind_src = verify_and_acquire_binaries(temp_workspace)

        if is_windows():
            with WindowsESPManager() as esp_root:
                deploy_refind(esp_root, refind_src)
                sequence_ok = configure_nvram_windows(str(esp_root.drive))
        else:
            with LinuxESPManager() as (esp_root, disk_dev, part_num):
                deploy_refind(esp_root, refind_src)
                configure_refind_linux_conf()
                sequence_ok = configure_nvram_linux(disk_dev, part_num)

    print("\n==================================================")
    log_success("Installation and theme configuration complete!")
    print("==================================================")

    if sequence_ok:
        log_success("Bootloader sequence updated programmatically.")
        print()
        log_warn("Note: If your OEM motherboard resets NVRAM on reboot, refer to these steps:")
        print_manual_bios_instructions(reason="Preventative: In case your OEM motherboard resets NVRAM on reboot.")
    else:
        log_warn("Automatic boot sequence change could not be fully guaranteed.")
        print_manual_bios_instructions(reason="Software boot order modification failed or was blocked by Secure Boot.")


if __name__ == "__main__":
    main()
