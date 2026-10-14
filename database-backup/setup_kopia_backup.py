#!/usr/bin/env python3
"""
Automated Kopia Backup Setup Script
- Installs Kopia from official package repositories (Debian/Ubuntu/RHEL/CentOS)
- Configures Local repository, Cloud repository, or BOTH for 3-2-1 redundancy
- Generates the backup runner script (/usr/local/bin/kopia-db-backup.sh)
- Configures and enables automated systemd service & timer
"""

import os
import sys
import shutil
import subprocess

# ==============================================================================
# CONFIGURATION - Adjust settings as needed
# ==============================================================================
CONFIG = {
    # Backup Modes:
    # Set to True for the destinations you want to enable
    "ENABLE_LOCAL": True,
    "ENABLE_CLOUD": True,

    # --- Local Repository Settings ---
    "LOCAL_CONFIG_PATH": "/etc/kopia/local.config",
    "LOCAL_REPO_PATH": "/mnt/backups/kopia",
    "LOCAL_REPO_PASSWORD": "admin@123",

    # --- Cloud Repository Settings (S3 / Backblaze B2 / MinIO) ---
    "CLOUD_CONFIG_PATH": "/etc/kopia/cloud.config",
    "CLOUD_REPO_PASSWORD": "admin@123",
    "S3_BUCKET": "my-db-backups",
    "S3_REGION": "us-east-1",
    "S3_ACCESS_KEY": "YOUR_AWS_ACCESS_KEY",
    "S3_SECRET_KEY": "YOUR_AWS_SECRET_KEY",

    # --- Database Settings ---
    "DB_NAME": "rkmvmfamily_local",
    "DB_USER": "root",
    "DB_PASS": "abcd",
    "BACKUP_DIR": "/var/backups/db",

    # --- Schedule (Systemd OnCalendar format) ---
    # Examples: "hourly", "daily", "*-*-* 02:00:00" (every night at 2:00 AM)
    "SCHEDULE": "hourly",
}


def run(cmd, check=True, env=None, capture=False):
    """Run shell command safely."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        cmd,
        shell=True,
        check=check,
        env=full_env,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True
    )


def check_root():
    """Ensure script is run with root privileges."""
    if os.geteuid() != 0:
        print("[ERROR] This script must be run as root (e.g. sudo python3 setup_kopia_backup.py)")
        sys.exit(1)


def install_kopia():
    """Install Kopia using the official package repositories."""
    if shutil.which("kopia"):
        print("[+] Kopia is already installed.")
        run("kopia --version")
        return

    print("[*] Installing Kopia from official repository...")
    if os.path.exists("/etc/debian_version"):
        # Debian / Ubuntu
        run("apt-get update && apt-get install -y curl gpg")
        run("mkdir -p /etc/apt/keyrings")
        run("curl -s https://kopia.io/signing-key | gpg --dearmor --yes -o /etc/apt/keyrings/kopia-keyring.gpg")
        with open("/etc/apt/sources.list.d/kopia.list", "w") as f:
            f.write("deb [signed-by=/etc/apt/keyrings/kopia-keyring.gpg] http://packages.kopia.io/apt/ stable main\n")
        run("apt-get update && apt-get install -y kopia")
    elif os.path.exists("/etc/redhat-release"):
        # RHEL / CentOS / AlmaLinux / Fedora
        run("rpm --import https://kopia.io/signing-key")
        repo_data = (
            "[Kopia]\n"
            "name=Kopia\n"
            "baseurl=http://packages.kopia.io/rpm/stable/$basearch/\n"
            "gpgcheck=1\n"
            "enabled=1\n"
            "gpgkey=https://kopia.io/signing-key\n"
        )
        with open("/etc/yum.repos.d/kopia.repo", "w") as f:
            f.write(repo_data)
        pkg_manager = "dnf" if shutil.which("dnf") else "yum"
        run(f"{pkg_manager} install -y kopia")
    else:
        print("[ERROR] Unsupported distribution. Please install Kopia manually.")
        sys.exit(1)

    print("[+] Kopia installed successfully:")
    run("kopia --version")


def setup_repositories():
    """Initialize local and/or cloud Kopia repositories."""
    os.makedirs("/etc/kopia", exist_ok=True)
    os.chmod("/etc/kopia", 0o700)

    # 1. Setup Local Repository
    if CONFIG["ENABLE_LOCAL"]:
        print("[*] Configuring Local repository...")
        local_cfg = CONFIG["LOCAL_CONFIG_PATH"]
        env = {"KOPIA_PASSWORD": CONFIG["LOCAL_REPO_PASSWORD"]}
        os.makedirs(CONFIG["LOCAL_REPO_PATH"], exist_ok=True)

        status_check = run(f"kopia --config-file='{local_cfg}' repository status", check=False, capture=True, env=env)
        if status_check.returncode == 0:
            print("[+] Local repository already connected.")
        else:
            # Try connecting first (in case repository already exists on disk)
            connect_res = run(
                f"kopia --config-file='{local_cfg}' repository connect filesystem --path='{CONFIG['LOCAL_REPO_PATH']}'",
                check=False, env=env
            )
            if connect_res.returncode != 0:
                print("[*] Creating new local repository...")
                run(f"kopia --config-file='{local_cfg}' repository create filesystem --path='{CONFIG['LOCAL_REPO_PATH']}'", env=env)

        # Set retention policy for local repo
        run(
            f"kopia --config-file='{local_cfg}' policy set '{CONFIG['BACKUP_DIR']}' "
            "--keep-daily 7 --keep-weekly 4 --compression=zstd",
            env=env
        )
        print("[+] Local repository ready.")

    # 2. Setup Cloud Repository
    if CONFIG["ENABLE_CLOUD"]:
        print("[*] Configuring Cloud repository...")
        cloud_cfg = CONFIG["CLOUD_CONFIG_PATH"]
        env = {"KOPIA_PASSWORD": CONFIG["CLOUD_REPO_PASSWORD"]}

        status_check = run(f"kopia --config-file='{cloud_cfg}' repository status", check=False, capture=True, env=env)
        if status_check.returncode == 0:
            print("[+] Cloud repository already connected.")
        else:
            # Try connecting first
            connect_res = run(
                f"kopia --config-file='{cloud_cfg}' repository connect s3 "
                f"--bucket='{CONFIG['S3_BUCKET']}' --region='{CONFIG['S3_REGION']}' "
                f"--access-key='{CONFIG['S3_ACCESS_KEY']}' --secret-access-key='{CONFIG['S3_SECRET_KEY']}'",
                check=False, env=env
            )
            if connect_res.returncode != 0:
                print("[*] Creating new cloud repository...")
                run(
                    f"kopia --config-file='{cloud_cfg}' repository create s3 "
                    f"--bucket='{CONFIG['S3_BUCKET']}' --region='{CONFIG['S3_REGION']}' "
                    f"--access-key='{CONFIG['S3_ACCESS_KEY']}' --secret-access-key='{CONFIG['S3_SECRET_KEY']}'",
                    env=env
                )

        # Set retention policy for cloud repo
        run(
            f"kopia --config-file='{cloud_cfg}' policy set '{CONFIG['BACKUP_DIR']}' "
            "--keep-daily 14 --keep-weekly 8 --keep-monthly 12 --compression=zstd",
            env=env
        )
        print("[+] Cloud repository ready.")


def create_backup_script():
    """Create the backup worker script executed by systemd."""
    script_path = "/usr/local/bin/kopia-db-backup.sh"

    # Build snapshot commands conditionally based on configuration
    local_block = ""
    if CONFIG["ENABLE_LOCAL"]:
        local_block = f"""
# --- Snapshot to Local Repository ---
if [ -f "{CONFIG['LOCAL_CONFIG_PATH']}" ]; then
    KOPIA_PASSWORD="{CONFIG['LOCAL_REPO_PASSWORD']}" kopia --config-file="{CONFIG['LOCAL_CONFIG_PATH']}" snapshot create "$BACKUP_DIR"
fi
"""

    cloud_block = ""
    if CONFIG["ENABLE_CLOUD"]:
        cloud_block = f"""
# --- Snapshot to Cloud Repository ---
if [ -f "{CONFIG['CLOUD_CONFIG_PATH']}" ]; then
    KOPIA_PASSWORD="{CONFIG['CLOUD_REPO_PASSWORD']}" kopia --config-file="{CONFIG['CLOUD_CONFIG_PATH']}" snapshot create "$BACKUP_DIR"
fi
"""

    content = f"""#!/bin/bash
set -euo pipefail

BACKUP_DIR="{CONFIG['BACKUP_DIR']}"

# 1. Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# 2. Dump Database
mysqldump --single-transaction -u {CONFIG['DB_USER']} -p'{CONFIG['DB_PASS']}' {CONFIG['DB_NAME']} > "$BACKUP_DIR/mydb.sql"
{local_block}{cloud_block}
# 3. Clean temporary unencrypted dump file
rm -f "$BACKUP_DIR"/*
"""
    with open(script_path, "w") as f:
        f.write(content)

    os.chmod(script_path, 0o700)
    print(f"[+] Backup script created at: {script_path}")


def setup_systemd():
    """Create systemd service and timer for automated backups."""
    service_path = "/etc/systemd/system/kopia-backup.service"
    timer_path = "/etc/systemd/system/kopia-backup.timer"

    service_content = """[Unit]
Description=Automated Database Backup with Kopia (Local & Cloud)
After=network.target mysql.service mariadb.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/kopia-db-backup.sh
"""

    timer_content = f"""[Unit]
Description=Trigger Kopia Database Backup
Requires=kopia-backup.service

[Timer]
OnCalendar={CONFIG['SCHEDULE']}
Persistent=true

[Install]
WantedBy=timers.target
"""

    with open(service_path, "w") as f:
        f.write(service_content)

    with open(timer_path, "w") as f:
        f.write(timer_content)

    run("systemctl daemon-reload")
    run("systemctl enable --now kopia-backup.timer")
    print(f"[+] Systemd timer enabled (Schedule: {CONFIG['SCHEDULE']})")


def main():
    check_root()
    print("=== Starting Kopia Database Backup Setup ===")
    install_kopia()
    setup_repositories()
    create_backup_script()
    setup_systemd()
    print("\n[SUCCESS] Setup finished!")
    print("Test immediate run:")
    print("  sudo systemctl start kopia-backup.service")
    if CONFIG["ENABLE_LOCAL"]:
        print(f"  sudo KOPIA_PASSWORD=\"{CONFIG['LOCAL_REPO_PASSWORD']}\" kopia --config-file=\"{CONFIG['LOCAL_CONFIG_PATH']}\" snapshot list")
    if CONFIG["ENABLE_CLOUD"]:
        print(f"  sudo KOPIA_PASSWORD=\"{CONFIG['CLOUD_REPO_PASSWORD']}\" kopia --config-file=\"{CONFIG['CLOUD_CONFIG_PATH']}\" snapshot list")


if __name__ == "__main__":
    main()
