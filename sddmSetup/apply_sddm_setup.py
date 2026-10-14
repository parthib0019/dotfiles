#!/usr/bin/env python3
"""
SDDM Setup Script for RamanOS
-----------------------------
- Verifies system environment & installs required dependencies (SDDM, Qt6 modules, QtMultimedia).
- Copies the Raman_OS SDDM theme to /usr/share/sddm/themes/Raman_OS.
- Installs the theme's custom font (zhcn.ttf) to /usr/share/fonts/TTF/ and updates font cache.
- Configures /etc/sddm.conf.d/theme.conf (and /etc/sddm.conf) to set Current=Raman_OS.
- Enables the sddm.service.
- Provides test options to preview the greeter.

Usage:
    sudo python3 apply_sddm_setup.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Source theme path
THEME_SRC = SCRIPT_DIR / "Raman_OS"

# System destination paths
SDDM_THEME_DIR = Path("/usr/share/sddm/themes")
THEME_DST = SDDM_THEME_DIR / "Raman_OS"
SYSTEM_FONT_DIR = Path("/usr/share/fonts/TTF")
SDDM_CONF_DIR = Path("/etc/sddm.conf.d")
SDDM_CONF_FILE = SDDM_CONF_DIR / "theme.conf"

REQUIRED_PACKAGES = [
    "sddm",
    "qt6-declarative",
    "qt6-5compat",
    "qt6-multimedia",
    "qt6-svg",
    "ffmpeg"
]

def log(msg: str):
    print(f"\033[1;34m[SDDM Setup]\033[0m {msg}")

def log_success(msg: str):
    print(f"\033[1;32m[SDDM Setup OK]\033[0m {msg}")

def log_warn(msg: str):
    print(f"\033[1;33m[SDDM Setup Warning]\033[0m {msg}")

def log_error(msg: str):
    print(f"\033[1;31m[SDDM Setup Error]\033[0m {msg}")

def check_root():
    if os.getuid() != 0:
        log_error("This script must be run with root privileges. Run: sudo python3 apply_sddm_setup.py")
        sys.exit(1)

def verify_and_install_dependencies():
    log("Step 1: Checking system environment & dependencies...")
    if not shutil.which("pacman"):
        log_warn("pacman not found. Skipping dependency installation step.")
        return

    missing_pkgs = []
    for pkg in REQUIRED_PACKAGES:
        res = subprocess.run(["pacman", "-Qq", pkg], capture_output=True, text=True)
        if res.returncode != 0:
            missing_pkgs.append(pkg)

    if missing_pkgs:
        log(f"Installing missing dependencies via pacman: {', '.join(missing_pkgs)}...")
        try:
            subprocess.run(["pacman", "-S", "--needed", "--noconfirm"] + missing_pkgs, check=True)
            log_success("All required dependencies installed.")
        except subprocess.CalledProcessError as e:
            log_warn(f"Failed to install some dependencies: {e}")
    else:
        log_success("All required dependencies are already installed.")

def install_fonts():
    log("Step 2: Installing Raman_OS theme custom fonts...")
    font_src = THEME_SRC / "font" / "zhcn.ttf"
    if font_src.exists():
        os.makedirs(SYSTEM_FONT_DIR, exist_ok=True)
        font_dst = SYSTEM_FONT_DIR / "zhcn.ttf"
        shutil.copy2(font_src, font_dst)
        os.chmod(font_dst, 0o644)
        log_success(f"Copied {font_src.name} -> {font_dst}")

        if shutil.which("fc-cache"):
            try:
                subprocess.run(["fc-cache", "-f", str(SYSTEM_FONT_DIR)], check=True)
                log_success("Font cache updated successfully.")
            except Exception as e:
                log_warn(f"Failed to update font cache: {e}")
    else:
        log_warn(f"Font file not found at {font_src}")

def deploy_sddm_theme():
    log("Step 3: Deploying Raman_OS SDDM theme...")
    if not THEME_SRC.exists():
        log_error(f"Source SDDM theme directory not found at: {THEME_SRC}")
        sys.exit(1)

    os.makedirs(SDDM_THEME_DIR, exist_ok=True)

    if THEME_DST.exists():
        log(f"Removing existing destination theme at {THEME_DST}...")
        shutil.rmtree(THEME_DST)

    shutil.copytree(THEME_SRC, THEME_DST)

    # Set correct permissions (755 for dirs, 644 for files)
    for root, dirs, files in os.walk(THEME_DST):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for f in files:
            os.chmod(os.path.join(root, f), 0o644)

    log_success(f"Copied theme files from {THEME_SRC} -> {THEME_DST}")

def configure_sddm():
    log("Step 4: Configuring SDDM theme setting...")
    os.makedirs(SDDM_CONF_DIR, exist_ok=True)

    sddm_config_content = (
        "[Theme]\n"
        "Current=Raman_OS\n"
        "CursorTheme=Breeze_Snow\n\n"
        "[General]\n"
        "Numlock=on\n"
        "InputMethod=\n"
    )

    if SDDM_CONF_FILE.exists():
        shutil.copy2(SDDM_CONF_FILE, Path(f"{SDDM_CONF_FILE}.bak"))

    with open(SDDM_CONF_FILE, "w") as f:
        f.write(sddm_config_content)

    log_success(f"Updated SDDM config at {SDDM_CONF_FILE}")

    # Also update main /etc/sddm.conf if it exists
    main_conf = Path("/etc/sddm.conf")
    if main_conf.exists():
        try:
            with open(main_conf, "r") as f:
                content = f.read()

            if "[Theme]" in content:
                if "Current=" in content:
                    import re
                    content = re.sub(r"^Current=.*$", "Current=Raman_OS", content, flags=re.MULTILINE)
                else:
                    content = content.replace("[Theme]", "[Theme]\nCurrent=Raman_OS")
            else:
                content += "\n[Theme]\nCurrent=Raman_OS\n"

            shutil.copy2(main_conf, Path("/etc/sddm.conf.bak"))
            with open(main_conf, "w") as f:
                f.write(content)
            log_success("Updated theme entry in /etc/sddm.conf")
        except Exception as e:
            log_warn(f"Could not update /etc/sddm.conf: {e}")

def enable_sddm_service():
    log("Step 5: Enabling sddm.service...")
    if shutil.which("systemctl"):
        try:
            subprocess.run(["systemctl", "enable", "sddm.service"], check=True)
            log_success("sddm.service enabled successfully.")
        except subprocess.CalledProcessError as e:
            log_warn(f"Could not enable sddm.service: {e}")
    else:
        log_warn("systemctl command not found. Skipping service enablement.")

def main():
    print("==================================================")
    print("      RamanOS SDDM Theme Setup Script            ")
    print("==================================================")

    check_root()
    verify_and_install_dependencies()
    install_fonts()
    deploy_sddm_theme()
    configure_sddm()
    enable_sddm_service()

    print("\n==================================================")
    print(" \033[1;32mSDDM Theme Setup Complete!\033[0m")
    print(" Theme installed at: /usr/share/sddm/themes/Raman_OS")
    print(" You can test the theme using:")
    print("   sddm-greeter-qt6 --test-mode --theme /usr/share/sddm/themes/Raman_OS")
    print("==================================================")

if __name__ == "__main__":
    main()
