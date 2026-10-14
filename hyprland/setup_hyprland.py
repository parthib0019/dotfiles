#!/usr/bin/env python3
"""
Hyprland & Waybar Setup Script for RamanOS
-------------------------------------------
- Checks if Hyprland and its ecosystem tools (Waybar, Hyprpaper, Hyprlock, Hyprpolkitagent, Wofi, Kitty, Dolphin, Portals) are installed.
- Installs any missing packages automatically via pacman.
- Deploys Hyprland configuration files from `at_the_folder_hypr` to `~/.config/hypr/`.
- Deploys Waybar configuration files from `at_the_folder_waybar` to `~/.config/waybar/`.
- Ensures proper permissions and user ownership.

Usage:
    python3 setup_hyprland.py
    # or with root/sudo:
    sudo python3 setup_hyprland.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Source dotfiles directories
HYPR_SRC = SCRIPT_DIR / "at_the_folder_hypr"
WAYBAR_SRC = SCRIPT_DIR / "at_the_folder_waybar"

# Hyprland ecosystem required packages
REQUIRED_PACKAGES = [
    "hyprland",
    "waybar",
    "hyprpaper",
    "hyprlock",
    "hyprpolkitagent",
    "xdg-desktop-portal-hyprland",
    "xdg-desktop-portal-gtk",
    "wofi",
    "kitty",
    "dolphin",
    "qt6-wayland",
    "qt5-wayland",
    "dunst",
    "grim",
    "slurp",
    "wl-clipboard",
    "brightnessctl",
    "pamixer",
    "ttf-jetbrains-mono-nerd",
    "ttf-font-awesome"
]

def log(msg: str):
    print(f"\033[1;34m[Hyprland Setup]\033[0m {msg}")

def log_success(msg: str):
    print(f"\033[1;32m[Hyprland Setup OK]\033[0m {msg}")

def log_warn(msg: str):
    print(f"\033[1;33m[Hyprland Setup Warning]\033[0m {msg}")

def log_error(msg: str):
    print(f"\033[1;31m[Hyprland Setup Error]\033[0m {msg}")

def get_target_user_and_home():
    """Determine the non-root target username and home directory."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        user_name = sudo_user
        user_home = Path(f"/home/{user_name}")
    else:
        user_name = os.environ.get("USER", "root")
        user_home = Path(os.environ.get("HOME", "/root"))

    return user_name, user_home

def verify_and_install_packages():
    log("Step 1: Checking Hyprland & ecosystem packages...")
    if not shutil.which("pacman"):
        log_warn("pacman package manager not found. Skipping package installation.")
        return

    missing_pkgs = []
    for pkg in REQUIRED_PACKAGES:
        res = subprocess.run(["pacman", "-Qq", pkg], capture_output=True, text=True)
        if res.returncode != 0:
            # Fallback check for alternative names if polkit agent varies
            if pkg == "hyprpolkitagent":
                alt_check = subprocess.run(["pacman", "-Qq", "polkit-kde-agent"], capture_output=True, text=True)
                if alt_check.returncode == 0:
                    continue
            missing_pkgs.append(pkg)

    if missing_pkgs:
        log(f"Missing packages detected: {', '.join(missing_pkgs)}")
        log("Installing missing packages via pacman...")
        cmd = ["pacman", "-S", "--needed", "--noconfirm"] + missing_pkgs
        if os.getuid() != 0:
            cmd = ["sudo"] + cmd
        
        try:
            subprocess.run(cmd, check=True)
            log_success("All Hyprland ecosystem packages installed successfully.")
        except subprocess.CalledProcessError as e:
            log_warn(f"Failed to install some packages: {e}")
    else:
        log_success("All required Hyprland packages are already installed.")

def deploy_config(src_dir: Path, dst_dir: Path, target_user: str):
    log(f"Deploying config from {src_dir.name} -> {dst_dir}...")
    if not src_dir.exists():
        log_error(f"Source configuration directory not found: {src_dir}")
        return

    os.makedirs(dst_dir, exist_ok=True)

    for item in src_dir.iterdir():
        dst_item = dst_dir / item.name
        if dst_item.exists():
            log(f"Backing up existing config: {dst_item} -> {dst_item}.bak")
            if dst_item.is_dir():
                if Path(f"{dst_item}.bak").exists():
                    shutil.rmtree(Path(f"{dst_item}.bak"))
                shutil.move(str(dst_item), str(Path(f"{dst_item}.bak")))
            else:
                shutil.copy2(dst_item, Path(f"{dst_item}.bak"))

        if item.is_dir():
            shutil.copytree(item, dst_item, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst_item)
        log_success(f"Deployed: {item.name} -> {dst_item}")

    # Set ownership if run via sudo
    if os.getuid() == 0 and target_user != "root":
        try:
            subprocess.run(["chown", "-R", f"{target_user}:{target_user}", str(dst_dir)], check=False)
            log_success(f"Set file ownership to {target_user} for {dst_dir}")
        except Exception as e:
            log_warn(f"Could not change file ownership: {e}")

def main():
    print("==================================================")
    print("      RamanOS Hyprland & Waybar Setup Script     ")
    print("==================================================")

    target_user, target_home = get_target_user_and_home()
    log(f"Configuring Hyprland environment for user: '{target_user}' ({target_home})")

    verify_and_install_packages()

    # Target config directories
    hypr_dst = target_home / ".config" / "hypr"
    waybar_dst = target_home / ".config" / "waybar"

    deploy_config(HYPR_SRC, hypr_dst, target_user)
    deploy_config(WAYBAR_SRC, waybar_dst, target_user)

    print("\n==================================================")
    print(" \033[1;32mHyprland & Waybar Setup Complete!\033[0m")
    print(f" Hyprland Config: {hypr_dst}")
    print(f" Waybar Config:   {waybar_dst}")
    print(" You can start Hyprland from TTY by running: Hyprland")
    print("==================================================")

if __name__ == "__main__":
    main()
