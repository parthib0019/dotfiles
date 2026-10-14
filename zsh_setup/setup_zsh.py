#!/usr/bin/env python3
"""
Zsh, Powerlevel10k & Plugins Setup Script for RamanOS
------------------------------------------------------
- Checks and installs Zsh, Git, and Zoxide if missing.
- Installs Oh My Zsh framework (~/.oh-my-zsh).
- Installs Powerlevel10k theme (~/powerlevel10k).
- Installs Zsh Auto Suggestions plugin (zsh-autosuggestions).
- Installs Zsh Syntax Highlighting plugin (zsh-syntax-highlighting).
- Copies the customized .zshrc dotfile from zsh_setup to ~/.zshrc.
- Sets Zsh as the default shell for the target user.
- Fixes file permissions for non-root users when run via sudo.

Usage:
    python3 setup_zsh.py
    # or with sudo:
    sudo python3 setup_zsh.py
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

def log(msg: str):
    print(f"\033[1;34m[Zsh Setup]\033[0m {msg}")

def log_success(msg: str):
    print(f"\033[1;32m[Zsh Setup OK]\033[0m {msg}")

def log_warn(msg: str):
    print(f"\033[1;33m[Zsh Setup Warning]\033[0m {msg}")

def log_error(msg: str):
    print(f"\033[1;31m[Zsh Setup Error]\033[0m {msg}")

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

def verify_packages():
    log("Step 1: Checking Zsh, Git & Zoxide installation...")
    missing = []

    for tool in ["zsh", "git", "zoxide"]:
        if not shutil.which(tool):
            missing.append(tool)

    if missing:
        log(f"Missing packages: {', '.join(missing)}")
        if shutil.which("pacman"):
            cmd = ["pacman", "-S", "--needed", "--noconfirm"] + missing
            if os.getuid() != 0:
                cmd = ["sudo"] + cmd
            try:
                subprocess.run(cmd, check=True)
                log_success("Installed missing packages via pacman.")
            except subprocess.CalledProcessError as e:
                log_error(f"Failed to install packages: {e}")
                sys.exit(1)
        else:
            log_error(f"Please install missing packages manually: {', '.join(missing)}")
            sys.exit(1)
    else:
        log_success("Zsh, Git, and Zoxide are already installed.")

def install_oh_my_zsh(user_home: Path, target_user: str):
    log("Step 2: Checking Oh My Zsh framework...")
    omz_dir = user_home / ".oh-my-zsh"

    if omz_dir.exists():
        log_success(f"Oh My Zsh directory already exists at {omz_dir}")
    else:
        repo_url = "https://github.com/ohmyzsh/ohmyzsh.git"
        log(f"Cloning Oh My Zsh from {repo_url} into {omz_dir}...")
        try:
            subprocess.run(["git", "clone", "--depth=1", repo_url, str(omz_dir)], check=True)
            log_success(f"Cloned Oh My Zsh to {omz_dir}")
        except subprocess.CalledProcessError as e:
            log_error(f"Failed to clone Oh My Zsh repository: {e}")
            sys.exit(1)

    if os.getuid() == 0 and target_user != "root":
        subprocess.run(["chown", "-R", f"{target_user}:{target_user}", str(omz_dir)], check=False)

def install_powerlevel10k(user_home: Path, target_user: str):
    log("Step 3: Installing Powerlevel10k theme...")
    p10k_dir = user_home / "powerlevel10k"
    omz_p10k = user_home / ".oh-my-zsh" / "custom" / "themes" / "powerlevel10k"

    repo_url = "https://github.com/romkatv/powerlevel10k.git"

    # Clone to ~/powerlevel10k
    if not p10k_dir.exists():
        log(f"Cloning Powerlevel10k to {p10k_dir}...")
        try:
            subprocess.run(["git", "clone", "--depth=1", repo_url, str(p10k_dir)], check=True)
            log_success(f"Cloned Powerlevel10k to {p10k_dir}")
        except subprocess.CalledProcessError as e:
            log_warn(f"Failed to clone Powerlevel10k: {e}")
    else:
        log_success(f"Powerlevel10k already present at {p10k_dir}")

    # Also clone to ~/.oh-my-zsh/custom/themes/powerlevel10k for OMZ theme compatibility
    if omz_p10k.parent.exists() and not omz_p10k.exists():
        log(f"Cloning Powerlevel10k to {omz_p10k}...")
        try:
            subprocess.run(["git", "clone", "--depth=1", repo_url, str(omz_p10k)], check=True)
            log_success(f"Cloned Powerlevel10k to {omz_p10k}")
        except Exception:
            pass

    if os.getuid() == 0 and target_user != "root":
        if p10k_dir.exists():
            subprocess.run(["chown", "-R", f"{target_user}:{target_user}", str(p10k_dir)], check=False)
        if omz_p10k.exists():
            subprocess.run(["chown", "-R", f"{target_user}:{target_user}", str(omz_p10k)], check=False)

def install_plugins(user_home: Path, target_user: str):
    log("Step 4: Installing Zsh plugins (Auto Suggestions & Syntax Highlighting)...")
    plugins_dir = user_home / ".oh-my-zsh" / "custom" / "plugins"
    os.makedirs(plugins_dir, exist_ok=True)

    plugins = {
        "zsh-autosuggestions": "https://github.com/zsh-users/zsh-autosuggestions",
        "zsh-syntax-highlighting": "https://github.com/zsh-users/zsh-syntax-highlighting.git"
    }

    for name, repo_url in plugins.items():
        plugin_path = plugins_dir / name
        if plugin_path.exists():
            log_success(f"Plugin '{name}' is already installed at {plugin_path}")
        else:
            log(f"Cloning plugin '{name}' from {repo_url}...")
            try:
                subprocess.run(["git", "clone", repo_url, str(plugin_path)], check=True)
                log_success(f"Installed plugin '{name}' -> {plugin_path}")
            except subprocess.CalledProcessError as e:
                log_warn(f"Failed to clone plugin '{name}': {e}")

    if os.getuid() == 0 and target_user != "root":
        subprocess.run(["chown", "-R", f"{target_user}:{target_user}", str(plugins_dir)], check=False)

def deploy_zshrc(user_home: Path, target_user: str):
    log("Step 5: Deploying .zshrc dotfile to home directory...")
    src_zshrc = SCRIPT_DIR / ".zshrc"
    dst_zshrc = user_home / ".zshrc"

    if src_zshrc.exists():
        if dst_zshrc.exists():
            log(f"Backing up existing .zshrc -> {dst_zshrc}.bak")
            shutil.copy2(dst_zshrc, Path(f"{dst_zshrc}.bak"))

        shutil.copy2(src_zshrc, dst_zshrc)
        log_success(f"Copied {src_zshrc.name} -> {dst_zshrc}")
    else:
        log_warn(f"Source .zshrc not found at {src_zshrc}")
        # Append powerlevel10k source line if file exists
        source_line = "source ~/powerlevel10k/powerlevel10k.zsh-theme\n"
        if not dst_zshrc.exists():
            dst_zshrc.touch()
        with open(dst_zshrc, "r") as f:
            content = f.read()
        if "powerlevel10k.zsh-theme" not in content:
            with open(dst_zshrc, "a") as f:
                f.write(f"\n# Powerlevel10k Zsh Theme\n{source_line}")
            log_success(f"Updated {dst_zshrc} with Powerlevel10k source line")

    if os.getuid() == 0 and target_user != "root":
        subprocess.run(["chown", f"{target_user}:{target_user}", str(dst_zshrc)], check=False)

def set_default_shell(target_user: str):
    log("Step 6: Setting Zsh as default shell...")
    zsh_bin = shutil.which("zsh") or "/bin/zsh"

    try:
        current_shell = os.environ.get("SHELL", "")
        if zsh_bin in current_shell:
            log_success(f"Default shell for {target_user} is already Zsh.")
            return

        log(f"Changing default shell to {zsh_bin} for user '{target_user}'...")
        if os.getuid() == 0:
            subprocess.run(["chsh", "-s", zsh_bin, target_user], check=True)
        else:
            subprocess.run(["chsh", "-s", zsh_bin], check=True)
        log_success(f"Set default shell to {zsh_bin}")
    except Exception as e:
        log_warn(f"Could not set default shell automatically: {e}. You can run: chsh -s {zsh_bin}")

def main():
    print("==================================================")
    print("   RamanOS Zsh, Powerlevel10k & Plugins Setup     ")
    print("==================================================")

    target_user, target_home = get_target_user_and_home()
    log(f"Configuring Zsh environment for user: '{target_user}' ({target_home})")

    verify_packages()
    install_oh_my_zsh(target_home, target_user)
    install_powerlevel10k(target_home, target_user)
    install_plugins(target_home, target_user)
    deploy_zshrc(target_home, target_user)
    set_default_shell(target_user)

    print("\n==================================================")
    print(" \033[1;32mZsh & Powerlevel10k Setup Complete!\033[0m")
    print(f" Home Config:  {target_home / '.zshrc'}")
    print(f" Theme Path:   {target_home / 'powerlevel10k'}")
    print(f" Plugins Path: {target_home / '.oh-my-zsh' / 'custom' / 'plugins'}")
    print(" Open a new terminal session or run 'zsh' to launch Powerlevel10k!")
    print("==================================================")

if __name__ == "__main__":
    main()
